"""
Mapa de calor SUAVIZADO para o painel público (Painel_Arboviroses_Pinheiro.py).

As coordenadas reais das notificações são usadas SÓ aqui, no servidor, para calcular
uma superfície de densidade borrada (núcleo gaussiano de ~130 m). O navegador
recebe apenas uma IMAGEM pronta (ImageOverlay), nunca os pontos: dar zoom no mapa
não revela a localização dos casos, só amplia a imagem borrada.

O valor de cada pixel é aproximadamente o número de quarteirões com casos num raio de ~250 m, e a cor
segue a mesma regra do mapa de calor do painel da Vigilância (1 caso amarelo, cerca de
6 casos próximos vermelho), igual em todos os anos.
"""
import base64
import io
import math

import folium
import numpy as np

SIGMA_METROS = 130     # quanto o calor é "borrado" (desvio padrão do núcleo gaussiano).
                       # ≈ o calor do Passo8 com zoom na cidade; aumente para proteger mais.
CELULA_METROS = 120    # como no Leaflet.heat: casos no mesmo quadradinho contam uma vez
PIXEL_METROS = 40      # resolução da imagem
OPACIDADE_MAXIMA = 0.85


def _grade(limites):
    minx, miny, maxx, maxy = [float(v) for v in limites]
    lat0 = math.radians((miny + maxy) / 2)
    passo_x = PIXEL_METROS / (111320 * math.cos(lat0))
    passo_y = PIXEL_METROS / 110540
    nx = max(int(math.ceil((maxx - minx) / passo_x)), 1)
    ny = max(int(math.ceil((maxy - miny) / passo_y)), 1)
    return minx, miny, maxx, maxy, nx, ny


def densidade(lats, lons, limites):
    """Superfície (linhas do norte para o sul) com ~nº de casos por perto em cada pixel."""
    minx, miny, maxx, maxy, nx, ny = _grade(limites)
    lats = np.asarray(lats, dtype=float)
    lons = np.asarray(lons, dtype=float)
    ok = np.isfinite(lats) & np.isfinite(lons)
    lats, lons = lats[ok], lons[ok]
    # Como no Leaflet.heat (painel da Vigilância): vários casos no mesmo quadradinho de
    # ~120 m viram UMA mancha. Cada quadradinho ocupado entra uma vez, no seu centro.
    passo_y = CELULA_METROS / 110540
    passo_x = CELULA_METROS / (111320 * math.cos(math.radians((miny + maxy) / 2)))
    celulas = np.unique(np.stack([np.floor((lats - miny) / passo_y), np.floor((lons - minx) / passo_x)], axis=1), axis=0)
    lats = miny + (celulas[:, 0] + 0.5) * passo_y if len(celulas) else lats
    lons = minx + (celulas[:, 1] + 0.5) * passo_x if len(celulas) else lons
    contagem, _, _ = np.histogram2d(lats, lons, bins=[ny, nx], range=[[miny, maxy], [minx, maxx]])
    sigma = SIGMA_METROS / PIXEL_METROS
    k = np.arange(-int(4 * sigma), int(4 * sigma) + 1, dtype=float)
    nucleo = np.exp(-(k ** 2) / (2 * sigma ** 2))  # pico 1: um caso isolado vale 1 no centro
    contagem = contagem.astype(np.float32)
    nucleo = nucleo.astype(np.float32)
    suave = np.apply_along_axis(lambda v: np.convolve(v, nucleo, mode="same"), 0, contagem)
    suave = np.apply_along_axis(lambda v: np.convolve(v, nucleo, mode="same"), 1, suave)
    return np.flipud(suave)


def _paleta(gradiente):
    from matplotlib.colors import to_rgb

    paradas = sorted((float(p), to_rgb(c)) for p, c in gradiente.items())
    pos = np.array([p for p, _ in paradas])
    cores = np.array([c for _, c in paradas])
    t = np.linspace(0, 1, 256)
    return np.stack([np.interp(t, pos, cores[:, i]) for i in range(3)], axis=1)


def _png_data_uri(rgba):
    from PIL import Image

    imagem = Image.fromarray((np.clip(rgba, 0, 1) * 255).astype(np.uint8), mode="RGBA")
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def pico(lista_de_densidades):
    """Maior valor entre várias superfícies (régua comum)."""
    valores = [float(d.max()) for d in lista_de_densidades if d is not None and d.size]
    return max(valores + [1.0])


def adicionar_imagem_calor(mapa, dens, limites, gradiente, valor_maximo, nome, mostrar=True):
    """Coloca a superfície no mapa como imagem (sem pontos). Áreas sem casos ficam transparentes."""
    if dens is None or not dens.size or float(dens.max()) <= 0:
        return False
    # Mesma regra do mapa de calor do painel da Vigilância (Leaflet.heat, opacidade mínima
    # 0,3): cada caso próximo soma 30% de "calor" — 1 caso = 30%, 3 casos ≈ 66%,
    # 6 ou mais ≈ vermelho. A escala é em número de casos, igual em todos os anos.
    # ('valor_maximo' fica só por compatibilidade.)
    t = np.clip(1.0 - np.power(0.7, dens), 0, 1).astype(np.float32)
    visivel = np.clip(dens / 0.25, 0, 1)          # borda suave onde a densidade tende a zero
    paleta = _paleta(gradiente)
    rgba = np.zeros(dens.shape + (4,), dtype=np.float32)
    rgba[..., :3] = paleta[(t * 255).astype(int)]
    rgba[..., 3] = visivel * np.clip(t * 1.15, 0, OPACIDADE_MAXIMA)
    minx, miny, maxx, maxy = [float(v) for v in limites]
    folium.raster_layers.ImageOverlay(
        image=_png_data_uri(rgba), bounds=[[miny, minx], [maxy, maxx]],
        name=nome, show=mostrar, interactive=False, cross_origin=False, zindex=2,
    ).add_to(mapa)
    return True


# ======================= pontos em grade (mapa de calor igual ao do Passo8) =======================
CELULA_GRADE_METROS = 150  # tamanho do quadradinho enviado ao navegador


def coordenadas_em_grade(df, celula_metros=CELULA_GRADE_METROS):
    """Cópia do DataFrame com Latitude/Longitude = CENTRO do quadradinho de ~150 m onde
    está a coordenada real (Lat_Real/Lon_Real). É isso que vai para o mapa de calor do
    navegador: a contagem por quadradinho, nunca a coordenada real do caso.
    O Leaflet.heat (o mesmo do Passo8) já agrupa os casos em quadradinhos parecidos para
    desenhar, então o visual fica praticamente igual ao do painel da Vigilância."""
    saida = df.copy()
    if "Lat_Real" not in saida.columns or saida.empty:
        saida["Latitude"] = np.nan
        saida["Longitude"] = np.nan
        return saida
    lat = saida["Lat_Real"].astype(float)
    lon = saida["Lon_Real"].astype(float)
    passo_y = celula_metros / 110540
    passo_x = celula_metros / (111320 * math.cos(math.radians(-2.5)))
    saida["Latitude"] = (np.floor(lat / passo_y) + 0.5) * passo_y
    saida["Longitude"] = (np.floor(lon / passo_x) + 0.5) * passo_x
    return saida


def pontos_heatmap(df_grade):
    """[lat, lon, nº de casos] por quadradinho (o Leaflet soma os pesos, como no Passo8)."""
    dados = df_grade.dropna(subset=["Latitude", "Longitude"])
    if dados.empty:
        return []
    agrupado = dados.groupby(["Latitude", "Longitude"]).size().reset_index(name="n")
    return agrupado[["Latitude", "Longitude", "n"]].astype(float).values.tolist()
