"""
Mapa de calor SUAVIZADO para o painel público (Painel_Arboviroses_Pinheiro.py).

As coordenadas reais das notificações são usadas SÓ aqui, no servidor, para calcular
uma superfície de densidade bem borrada (núcleo gaussiano de ~1 km). O navegador
recebe apenas uma IMAGEM pronta (ImageOverlay), nunca os pontos: dar zoom no mapa
não revela a localização dos casos, só amplia a imagem borrada.

O valor de cada pixel é aproximadamente o número de casos num raio de ~1 km.
Todas as camadas de um mesmo tipo (por exemplo, Dengue de 2023 a 2026) usam a mesma
escala de cores, para comparar os anos.
"""
import base64
import io
import math

import folium
import numpy as np

SIGMA_METROS = 1000    # quanto o calor é "borrado" (desvio padrão do núcleo gaussiano)
PIXEL_METROS = 60      # resolução da imagem
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
    contagem, _, _ = np.histogram2d(lats[ok], lons[ok], bins=[ny, nx], range=[[miny, maxy], [minx, maxx]])
    sigma = SIGMA_METROS / PIXEL_METROS
    k = np.arange(-int(4 * sigma), int(4 * sigma) + 1, dtype=float)
    nucleo = np.exp(-(k ** 2) / (2 * sigma ** 2))  # pico 1: um caso isolado vale 1 no centro
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
    # Como no mapa de calor do painel da Vigilância (Leaflet.heat): todo caso aparece pelo
    # menos na cor de 30% da escala; daí até o vermelho conforme os casos se acumulam.
    bruto = np.clip(dens / max(valor_maximo, 1e-9), 0, 1)
    visivel = np.clip(dens / 0.25, 0, 1)          # borda suave onde a densidade tende a zero
    t = np.clip(0.3 + 0.7 * bruto ** 0.6, 0, 1)
    paleta = _paleta(gradiente)
    rgba = np.zeros(dens.shape + (4,))
    rgba[..., :3] = paleta[(t * 255).astype(int)]
    rgba[..., 3] = visivel * (0.45 + (OPACIDADE_MAXIMA - 0.45) * bruto ** 0.6)
    minx, miny, maxx, maxy = [float(v) for v in limites]
    folium.raster_layers.ImageOverlay(
        image=_png_data_uri(rgba), bounds=[[miny, minx], [maxy, maxx]],
        name=nome, show=mostrar, interactive=False, cross_origin=False, zindex=2,
    ).add_to(mapa)
    return True
