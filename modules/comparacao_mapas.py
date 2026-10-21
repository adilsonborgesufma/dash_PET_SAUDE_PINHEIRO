"""
Comparação de mapas de calor entre anos.

Cada ano é mostrado como um mapa de calor suave (manchas azul → vermelho, ou
amarelo → vermelho) sobre o mapa de ruas, com o limite do município e as UBS.

COMO A ESCALA FICA IGUAL EM TODOS OS ANOS
O mapa de calor do Folium pinta cada mapa em relação ao PRÓPRIO ponto mais quente.
Sem cuidado, um ano com 24 casos ficaria tão vermelho quanto um com 155. Para evitar
isso, todos os mapas têm o mesmo tamanho e o mesmo zoom (calculados aqui), e cada
um recebe um ponto de referência invisível, bem longe da área mostrada, cujo peso é
igual ao ponto mais quente de TODOS os anos. Assim a régua de cores é a mesma e
a comparação entre anos é justa.
"""
import folium
import numpy as np
import streamlit as st
from folium.plugins import HeatMap
from streamlit_folium import st_folium

# ---- Estilos de cor do mapa de calor ----
ESTILOS_COR = {
    "Clássico (azul → vermelho)": {
        "stops": {0.4: "blue", 0.6: "cyan", 0.7: "lime", 0.8: "yellow", 1.0: "red"},
        "css": "linear-gradient(to right, #1d4ed8, #06b6d4, #22c55e, #facc15, #dc2626)",
    },
    "Suave (amarelo → vermelho)": {
        "stops": {0.3: "#FFF1B5", 0.5: "#FFD27F", 0.7: "#FFA040", 0.85: "#E8590C", 1.0: "#A4161A"},
        "css": "linear-gradient(to right, #FFF1B5, #FFD27F, #FFA040, #E8590C, #A4161A)",
    },
}

# ---- Mapas de fundo ----
FUNDOS = {
    "Ruas (OpenStreetMap)": {
        "tiles": "OpenStreetMap",
        "attr": '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        "max_zoom": 19,
    },
    "Cinza claro (Esri)": {
        "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        "attr": "Tiles &copy; Esri",
        "max_zoom": 16,
    },
}

# Largura x altura (px) dos mapas. Fixos de propósito: o zoom e a escala de cores
# só ficam idênticos entre os anos se todos os mapas tiverem exatamente o mesmo tamanho.
TAMANHOS_LADO_A_LADO = {"Pequeno": (380, 360), "Médio": (460, 380), "Grande": (620, 420)}
TAMANHOS_MAPA_GRANDE = {"Pequeno": (760, 500), "Médio": (940, 560), "Grande": (1180, 620)}
MARGEM_IFRAME = 0  # o st_folium usa exatamente a altura pedida (o antigo folium_static somava 10 px)

COR_CONTORNO = "#374151"
COR_UBS = "#1F3A5F"
OPACIDADE_MINIMA = 0.25
DESLOCAMENTO_REFERENCIA_GRAUS = 8.0


# ======================= cálculos (sem interface) =======================

def calcular_extensao(lons, lats, limites_municipio, enquadramento):
    """Janela (xmin, xmax, ymin, ymax) mostrada nos mapas.
    'casos' recorta na área dos casos (mais fácil de ler); 'municipio' mostra tudo."""
    if enquadramento == "municipio" or len(lons) == 0:
        minx, miny, maxx, maxy = limites_municipio
        return minx, maxx, miny, maxy

    xmin, xmax = float(np.min(lons)), float(np.max(lons))
    ymin, ymax = float(np.min(lats)), float(np.max(lats))
    largura = max(xmax - xmin, 0.01)   # janela mínima de ~1 km
    altura = max(ymax - ymin, 0.01)
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    folga = 1.25
    return (cx - largura * folga / 2, cx + largura * folga / 2,
            cy - altura * folga / 2, cy + altura * folga / 2)


def projetar_pixel(lons, lats, zoom):
    """Longitude/latitude -> pixel do mundo (Web Mercator, igual ao Leaflet)."""
    escala = 256.0 * 2.0 ** zoom
    lat_rad = np.radians(np.clip(np.asarray(lats, dtype=float), -85.05112878, 85.05112878))
    x = (np.asarray(lons, dtype=float) + 180.0) / 360.0 * escala
    y = (0.5 - np.log(np.tan(np.pi / 4.0 + lat_rad / 2.0)) / (2.0 * np.pi)) * escala
    return x, y


def calcular_zoom(extensao, largura_px, altura_px, zoom_maximo):
    """Maior zoom (em passos de 0,25) em que a extensão cabe no mapa."""
    xmin, xmax, ymin, ymax = extensao
    _, y_topo = projetar_pixel(0.0, ymax, 0)
    _, y_base = projetar_pixel(0.0, ymin, 0)
    fracao_x = max((xmax - xmin) / 360.0, 1e-9)
    fracao_y = max(abs(float(y_base) - float(y_topo)) / 256.0, 1e-9)
    z = np.log2(min(largura_px / (256.0 * fracao_x), altura_px / (256.0 * fracao_y)))
    z = np.floor(z * 4.0) / 4.0
    return float(np.clip(z, 6.0, zoom_maximo))


def calcular_pico(dados, centro_lon, centro_lat, zoom, largura_px, altura_px, raio, desfoque):
    """Maior número de casos que o Leaflet.heat soma numa mesma célula, considerando
    TODOS os anos. A célula do Leaflet mede (raio + desfoque) / 2 pixels; como o
    alinhamento da grade muda quando o usuário arrasta o mapa, testamos 4 alinhamentos
    e ficamos com o maior valor."""
    lado = (raio + desfoque) / 2.0
    cx, cy = projetar_pixel(centro_lon, centro_lat, zoom)
    pico = 0
    for _, d in dados.groupby("Ano"):
        x, y = projetar_pixel(d["Longitude"].values, d["Latitude"].values, zoom)
        px, py = x - cx + largura_px / 2.0, y - cy + altura_px / 2.0
        for dx in (0.0, lado / 2.0):
            for dy in (0.0, lado / 2.0):
                ix = np.floor((px + dx) / lado).astype(np.int64)
                iy = np.floor((py + dy) / lado).astype(np.int64)
                _, contagens = np.unique(ix * 1_000_003 + iy, return_counts=True)
                if len(contagens):
                    pico = max(pico, int(contagens.max()))
    return float(max(pico, 1))


def calcular_peso_referencia(pico, sensibilidade):
    """Peso do ponto de referência invisível (define a 'régua' comum de cores).
    Sensibilidade menor que 1 deixa o mapa mais frio (régua mais larga)."""
    return max(pico, 1.0) * (1.0 / sensibilidade if sensibilidade < 1.0 else 1.0)


def ajustar_gradiente(stops, sensibilidade):
    """Sensibilidade maior que 1 deixa o mapa mais quente: as cores aparecem antes.
    As chaves saem como TEXTO ("0.4"): o folium 0.19+ quebra com chaves numéricas
    ("'float' object has no attribute 'split'")."""
    divisor = max(sensibilidade, 1.0)
    return {str(round(float(posicao) / divisor, 4)): cor for posicao, cor in stops.items()}


# ======================= desenho =======================

def _pontos_ubs(ubs_gdf):
    pontos = []
    if ubs_gdf is None or len(ubs_gdf) == 0:
        return pontos
    for geom in ubs_gdf.geometry:
        if geom is None or geom.is_empty:
            continue
        p = geom if geom.geom_type == "Point" else geom.centroid
        pontos.append((p.y, p.x))
    return pontos


def criar_mapa_calor(df_ano, municipio_gdf, pontos_ubs, config):
    """Monta o mapa de calor (Folium) de um ano. Todos os anos recebem o mesmo
    centro, zoom, raio, desfoque e ponto de referência."""
    lat_c, lon_c = config["centro"]
    fundo = FUNDOS[config["fundo"]]
    mapa = folium.Map(
        location=[lat_c, lon_c], zoom_start=config["zoom"], tiles=None,
        zoom_snap=0.25, min_zoom=max(config["zoom"] - 2, 6), max_zoom=fundo["max_zoom"],
        control_scale=True, prefer_canvas=True,
    )
    folium.TileLayer(
        tiles=fundo["tiles"], attr=fundo["attr"], max_zoom=fundo["max_zoom"], name="Fundo",
    ).add_to(mapa)

    folium.GeoJson(
        municipio_gdf[["geometry"]],
        style_function=lambda _: {"color": COR_CONTORNO, "weight": 1.5, "fill": False},
        name="Limite municipal",
    ).add_to(mapa)

    pontos = [[lat, lon, 1.0] for lat, lon in df_ano[["Latitude", "Longitude"]].dropna().values]
    if pontos:
        # ponto de referência invisível: fica fora da área mostrada e fixa a régua de cores
        pontos.append([lat_c - DESLOCAMENTO_REFERENCIA_GRAUS,
                       lon_c + DESLOCAMENTO_REFERENCIA_GRAUS,
                       config["peso_referencia"]])
        HeatMap(
            pontos,
            radius=config["raio"], blur=config["desfoque"],
            min_opacity=OPACIDADE_MINIMA,
            gradient=config["gradiente"],
        ).add_to(mapa)

    if config["mostrar_ubs"]:
        for lat, lon in pontos_ubs:
            folium.CircleMarker(
                location=[lat, lon], radius=5, color="white", weight=1.5,
                fill=True, fill_color=COR_UBS, fill_opacity=1, tooltip="UBS",
            ).add_to(mapa)
    return mapa


def _legenda_html(estilo):
    css = ESTILOS_COR[estilo]["css"]
    return f"""
    <div style="max-width:440px;margin:4px 0 6px 0;font-family:sans-serif;">
      <div style="font-size:13px;color:#374151;margin-bottom:4px;"><b>Concentração de casos</b></div>
      <div style="height:12px;border-radius:6px;background:{css};border:1px solid #9CA3AF;"></div>
      <div style="display:flex;justify-content:space-between;font-size:12px;color:#6B7280;margin-top:2px;">
        <span>Poucos casos</span><span>Muitos casos</span>
      </div>
    </div>"""


def renderizar_comparacao_anos(df_base, municipio_gdf, key_prefix, raio=None, ubs_gdf=None):
    """Mostra os mapas de calor por ano, com escala comum e legenda.
    ('raio' é mantido só por compatibilidade com versões anteriores.)"""
    if df_base.empty:
        st.info("Nenhum caso encontrado com os filtros atuais para comparar.")
        return

    dados = df_base[["Ano", "Latitude", "Longitude"]].dropna()
    anos = [int(a) for a in sorted(dados["Ano"].unique())]
    if not anos:
        st.info("Nenhum caso com coordenadas válidas para comparar.")
        return

    # ---------------- controles ----------------
    col_a, col_b = st.columns(2)
    modo = col_a.radio(
        "Visualização",
        ["📊 Comparar anos lado a lado", "🔎 Um ano por vez (mapa grande)"],
        key=f"modo_{key_prefix}",
    )
    escolha_enq = col_b.radio(
        "Enquadramento", ["🔍 Área dos casos", "🗺️ Município inteiro"],
        key=f"enq_{key_prefix}",
    )
    lado_a_lado = modo.startswith("📊")
    enquadramento = "casos" if escolha_enq.startswith("🔍") else "municipio"

    with st.expander("⚙️ Ajustar aparência dos mapas", expanded=False):
        c1, c2 = st.columns(2)
        estilo = c1.selectbox("Cores", list(ESTILOS_COR), key=f"estilo_{key_prefix}")
        fundo = c2.selectbox("Mapa de fundo", list(FUNDOS), key=f"fundo_{key_prefix}")
        raio_px = c1.slider("Raio das manchas", 10, 40, 20, key=f"raio_{key_prefix}")
        desfoque = c2.slider("Suavidade (desfoque)", 5, 30, 15, key=f"desfoque_{key_prefix}")
        sensibilidade = c1.slider(
            "Sensibilidade das cores", 0.5, 2.0, 1.3, 0.1, key=f"sens_{key_prefix}",
            help="Valores maiores deixam o mapa mais 'quente' (chega ao vermelho com menos casos "
                 "próximos); menores deixam mais 'frio'. A mesma regra vale para todos os anos.",
        )
        tamanho = c2.selectbox(
            "Tamanho dos mapas", ["Pequeno", "Médio", "Grande"], index=1, key=f"tam_{key_prefix}",
            help="Se os mapas ficarem cortados na sua tela, escolha um tamanho menor.",
        )
        mostrar_ubs = st.checkbox("Mostrar UBS", True, key=f"ubs_{key_prefix}")

    # ---------------- zoom e escala, iguais para todos os anos ----------------
    largura, altura = (TAMANHOS_LADO_A_LADO if lado_a_lado else TAMANHOS_MAPA_GRANDE)[tamanho]
    extensao = calcular_extensao(
        dados["Longitude"].values, dados["Latitude"].values,
        municipio_gdf.total_bounds, enquadramento,
    )
    centro = ((extensao[2] + extensao[3]) / 2, (extensao[0] + extensao[1]) / 2)  # (lat, lon)
    zoom = calcular_zoom(extensao, largura, altura + MARGEM_IFRAME, FUNDOS[fundo]["max_zoom"])
    pico = calcular_pico(dados, centro[1], centro[0], zoom, largura, altura + MARGEM_IFRAME,
                         raio_px, desfoque)

    config = {
        "centro": centro, "zoom": zoom, "fundo": fundo,
        "raio": raio_px, "desfoque": desfoque,
        "peso_referencia": calcular_peso_referencia(pico, sensibilidade),
        "gradiente": ajustar_gradiente(ESTILOS_COR[estilo]["stops"], sensibilidade),
        "mostrar_ubs": mostrar_ubs,
    }
    pontos_ubs = _pontos_ubs(ubs_gdf)

    st.markdown(_legenda_html(estilo), unsafe_allow_html=True)

    # ---------------- mapas ----------------
    def titulo(ano):
        return f"**{ano}** · {int((dados['Ano'] == ano).sum())} casos"

    if lado_a_lado:
        por_linha = 2
        for inicio in range(0, len(anos), por_linha):
            colunas = st.columns(por_linha)
            for coluna, ano in zip(colunas, anos[inicio:inicio + por_linha]):
                with coluna:
                    st.markdown(titulo(ano))
                    mapa = criar_mapa_calor(
                        dados[dados["Ano"] == ano], municipio_gdf, pontos_ubs, config
                    )
                    st_folium(mapa, width=largura, height=altura, returned_objects=[],
                              key=f"mapa_{key_prefix}_{ano}_lado")
    else:
        ano = anos[0] if len(anos) == 1 else st.select_slider(
            "Ano", options=anos, value=anos[-1], key=f"ano_{key_prefix}"
        )
        st.markdown(titulo(ano))
        mapa = criar_mapa_calor(dados[dados["Ano"] == ano], municipio_gdf, pontos_ubs, config)
        st_folium(mapa, width=largura, height=altura, returned_objects=[],
                  key=f"mapa_{key_prefix}_{ano}_grande")

    st.caption(
        "**Como ler:** cada mancha mostra onde os casos notificados se concentraram. "
        "Tons frios (azul/verde, ou amarelo claro no estilo suave) indicam poucos casos por perto; "
        "tons quentes (laranja/vermelho) indicam muitos casos próximos uns dos outros. "
        "Todos os anos usam a mesma escala de cores, então dá para comparar um ano com outro. "
        "Os círculos azul-escuros são as UBS e a linha cinza é o limite do município."
    )

# ======================= versão estática (relatório e PDF) =======================
# O PDF não aceita mapa interativo. As funções abaixo desenham os MESMOS mapas da
# comparação entre anos como imagem: mesmo enquadramento, zoom, raio, desfoque,
# gradiente de cores e régua comum (calcular_pico), sobre o mesmo mapa de fundo.
# O desenho segue o Leaflet.heat usado no painel: os casos são somados em células
# de (raio + desfoque) / 2 pixels, cada célula vira uma mancha (círculo com desfoque)
# com opacidade = soma ÷ régua, e a opacidade final é pintada com o gradiente.

from functools import lru_cache  # noqa: E402

PADRAO_COMPARACAO = {
    "estilo": "Clássico (azul → vermelho)",
    "fundo": "Ruas (OpenStreetMap)",
    "raio": 20,
    "desfoque": 15,
    "sensibilidade": 1.3,
    "tamanho": "Médio",
    "enquadramento": "casos",
    "mostrar_ubs": True,
}
ESCALA_IMAGEM = 2  # desenha com o dobro de pixels: mesma aparência, mais nítido no PDF
URL_TILES = {
    "Ruas (OpenStreetMap)": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    "Cinza claro (Esri)": FUNDOS["Cinza claro (Esri)"]["tiles"],
}
CREDITO_FUNDO = {
    "Ruas (OpenStreetMap)": "© OpenStreetMap contributors",
    "Cinza claro (Esri)": "Tiles © Esri",
}


def config_comparacao_do_painel(estado, key_prefix="mapa"):
    """Lê a aparência escolhida na comparação entre anos do painel (aba Mapa Geral).
    Se o usuário não mexeu nela, valem os mesmos padrões do painel."""
    cfg = dict(PADRAO_COMPARACAO)
    pares = {"estilo": "estilo", "fundo": "fundo", "raio": "raio", "desfoque": "desfoque",
             "sensibilidade": "sens", "tamanho": "tam", "mostrar_ubs": "ubs"}
    for campo, chave in pares.items():
        valor = estado.get(f"{chave}_{key_prefix}")
        if valor is not None:
            cfg[campo] = valor
    enq = estado.get(f"enq_{key_prefix}")
    if enq:
        cfg["enquadramento"] = "casos" if str(enq).startswith("🔍") else "municipio"
    if cfg["estilo"] not in ESTILOS_COR:
        cfg["estilo"] = PADRAO_COMPARACAO["estilo"]
    if cfg["fundo"] not in FUNDOS:
        cfg["fundo"] = PADRAO_COMPARACAO["fundo"]
    return cfg


@lru_cache(maxsize=512)
def _baixar_tile(url):
    """Baixa um quadradinho do mapa de fundo (guardado em memória para não repetir)."""
    try:
        import requests
        from PIL import Image

        resposta = requests.get(url, timeout=6, headers={
            "User-Agent": "PainelVigilanciaPinheiro/1.0 (PET-Saude UFMA; relatorio)"})
        resposta.raise_for_status()
        import io as _io
        return Image.open(_io.BytesIO(resposta.content)).convert("RGB")
    except Exception:
        return None


def _fundo_mapa(fundo, zoom, x0, y0, largura, altura):
    """Mapa de fundo (imagem RGB) para a janela em pixels do mundo; None se não houver internet."""
    from PIL import Image

    z_tile = int(min(round(zoom), FUNDOS[fundo]["max_zoom"]))
    fator = 2.0 ** (zoom - z_tile)          # pixels da janela por pixel do tile
    tx0, ty0 = int(np.floor(x0 / fator / 256)), int(np.floor(y0 / fator / 256))
    tx1 = int(np.floor((x0 + largura) / fator / 256))
    ty1 = int(np.floor((y0 + altura) / fator / 256))
    if (tx1 - tx0 + 1) * (ty1 - ty0 + 1) > 120:
        return None
    mosaico = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256), (242, 239, 233))
    n = 2 ** z_tile
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            if not 0 <= ty < n:
                continue
            tile = _baixar_tile(URL_TILES[fundo].format(z=z_tile, x=tx % n, y=ty))
            if tile is None:
                return None
            mosaico.paste(tile, ((tx - tx0) * 256, (ty - ty0) * 256))
    esq, topo = x0 / fator - tx0 * 256, y0 / fator - ty0 * 256
    recorte = mosaico.crop((int(round(esq)), int(round(topo)),
                            int(round(esq + largura / fator)), int(round(topo + altura / fator))))
    return np.asarray(recorte.resize((int(largura), int(altura)), Image.BILINEAR))


def _carimbo(raio, desfoque):
    """Mancha de um ponto: círculo de raio 'raio' com desfoque gaussiano (como o canvas)."""
    r2 = raio + desfoque
    eixo = np.arange(-r2, r2 + 1, dtype=float)
    xx, yy = np.meshgrid(eixo, eixo)
    disco = (np.hypot(xx, yy) <= raio).astype(float)
    sigma = max(desfoque / 2.0, 0.5)
    k = np.arange(-int(3 * sigma), int(3 * sigma) + 1, dtype=float)
    nucleo = np.exp(-(k ** 2) / (2 * sigma ** 2))
    nucleo /= nucleo.sum()
    disco = np.apply_along_axis(lambda v: np.convolve(v, nucleo, mode="same"), 0, disco)
    disco = np.apply_along_axis(lambda v: np.convolve(v, nucleo, mode="same"), 1, disco)
    return np.clip(disco, 0.0, 1.0)


def _paleta(gradiente):
    """Gradiente {posição: cor} -> 256 cores RGB (igual à barra de cores do Leaflet.heat)."""
    from matplotlib.colors import to_rgb

    paradas = sorted((float(p), to_rgb(c)) for p, c in gradiente.items())
    pos = np.array([p for p, _ in paradas])
    cores = np.array([c for _, c in paradas])
    t = np.linspace(0, 1, 256)
    return np.stack([np.interp(t, pos, cores[:, i]) for i in range(3)], axis=1)


def _camada_calor(px, py, largura, altura, raio, desfoque, peso_referencia, gradiente):
    """Imagem RGBA do mapa de calor de um ano (mesmo algoritmo do Leaflet.heat)."""
    rgba = np.zeros((int(altura), int(largura), 4))
    if len(px) == 0:
        return rgba
    r2 = raio + desfoque
    lado = r2 / 2.0
    # 1) soma dos casos por célula, na posição média dos casos da célula
    ix, iy = np.floor(px / lado).astype(np.int64), np.floor(py / lado).astype(np.int64)
    celulas = {}
    for x, y, cx, cy in zip(px, py, ix, iy):
        s = celulas.setdefault((cx, cy), [0.0, 0.0, 0.0])
        s[0] += x
        s[1] += y
        s[2] += 1.0
    # 2) cada célula vira uma mancha; as manchas se sobrepõem como camadas semitransparentes
    carimbo = _carimbo(raio, desfoque)
    tamanho = carimbo.shape[0]
    resto = np.zeros((int(altura), int(largura)))      # soma de log(1 - opacidade)
    for sx, sy, soma in celulas.values():
        alfa = min(max(soma / peso_referencia, OPACIDADE_MINIMA), 1.0)
        x, y = int(round(sx / soma)) - r2, int(round(sy / soma)) - r2
        a0, a1 = max(0, -y), min(tamanho, int(altura) - y)
        b0, b1 = max(0, -x), min(tamanho, int(largura) - x)
        if a0 >= a1 or b0 >= b1:
            continue
        pedaco = np.clip(alfa * carimbo[a0:a1, b0:b1], 0.0, 0.999999)
        resto[y + a0:y + a1, x + b0:x + b1] += np.log1p(-pedaco)
    opacidade = 1.0 - np.exp(resto)
    # 3) a opacidade escolhe a cor no gradiente
    paleta = _paleta(gradiente)
    indice = np.clip((opacidade * 255).astype(int), 0, 255)
    rgba[..., :3] = paleta[indice]
    rgba[..., 3] = opacidade
    return rgba


def _contornos(geometria):
    if geometria is None or geometria.is_empty:
        return []
    partes = list(geometria.geoms) if hasattr(geometria, "geoms") else [geometria]
    aneis = []
    for parte in partes:
        if parte.geom_type == "Polygon":
            aneis.append(np.asarray(parte.exterior.coords))
            aneis += [np.asarray(i.coords) for i in parte.interiors]
        elif parte.geom_type in ("LineString", "LinearRing"):
            aneis.append(np.asarray(parte.coords))
    return aneis


def figura_comparacao_anos(df_base, municipio_gdf, ubs_gdf=None, anos=None, config=None,
                           por_linha=2, com_fundo=True):
    """Figura (matplotlib) com os mapas de calor dos anos escolhidos, lado a lado,
    idêntica à comparação do painel: a régua de cores considera TODOS os anos dos
    dados filtrados (como no painel), mesmo que só alguns anos sejam mostrados."""
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.patches import Rectangle

    cfg = dict(PADRAO_COMPARACAO)
    cfg.update(config or {})
    dados = df_base[["Ano", "Latitude", "Longitude"]].dropna()
    todos_anos = [int(a) for a in sorted(dados["Ano"].unique())]
    anos = [a for a in (anos or todos_anos) if a in todos_anos]
    if not anos or municipio_gdf is None or municipio_gdf.empty:
        return None

    municipio = municipio_gdf.to_crs(epsg=4326) if municipio_gdf.crs else municipio_gdf
    largura, altura = TAMANHOS_LADO_A_LADO.get(cfg["tamanho"], TAMANHOS_LADO_A_LADO["Médio"])
    extensao = calcular_extensao(dados["Longitude"].values, dados["Latitude"].values,
                                 municipio.total_bounds, cfg["enquadramento"])
    centro_lat, centro_lon = (extensao[2] + extensao[3]) / 2, (extensao[0] + extensao[1]) / 2
    zoom = calcular_zoom(extensao, largura, altura + MARGEM_IFRAME, FUNDOS[cfg["fundo"]]["max_zoom"])
    pico = calcular_pico(dados, centro_lon, centro_lat, zoom, largura, altura + MARGEM_IFRAME,
                         cfg["raio"], cfg["desfoque"])
    peso_ref = calcular_peso_referencia(pico, cfg["sensibilidade"])
    gradiente = ajustar_gradiente(ESTILOS_COR[cfg["estilo"]]["stops"], cfg["sensibilidade"])

    # tudo em dobro (pixels, raio, desfoque, zoom +1): mesma imagem, mais nítida
    e = ESCALA_IMAGEM
    z = zoom + np.log2(e)
    W, H, raio, desf = largura * e, altura * e, int(cfg["raio"] * e), int(cfg["desfoque"] * e)
    cx, cy = projetar_pixel(centro_lon, centro_lat, z)
    x0, y0 = float(cx) - W / 2.0, float(cy) - H / 2.0

    def para_tela(lons, lats):
        x, y = projetar_pixel(lons, lats, z)
        return np.asarray(x) - x0, np.asarray(y) - y0

    fundo = _fundo_mapa(cfg["fundo"], z, x0, y0, W, H) if com_fundo else None
    contornos = [para_tela(a[:, 0], a[:, 1]) for g in municipio.geometry for a in _contornos(g)]
    ubs = [(lat, lon) for lat, lon in _pontos_ubs(
        ubs_gdf.to_crs(epsg=4326) if ubs_gdf is not None and ubs_gdf.crs else ubs_gdf)]

    linhas = int(np.ceil(len(anos) / por_linha))
    colunas = min(por_linha, len(anos))
    largura_pol = 4.6 * colunas
    fig = plt.figure(figsize=(largura_pol, 0.75 + linhas * (4.6 * H / W + 0.45)))
    topo_legenda = 0.75 / (0.75 + linhas * (4.6 * H / W + 0.45))

    # legenda de cores, igual à do painel
    ax_leg = fig.add_axes([0.08, 1 - topo_legenda * 0.62, 0.84, topo_legenda * 0.22])
    # mesmas cores da legenda do painel (_legenda_html)
    import re as _re
    cores_legenda = _re.findall(r"#[0-9A-Fa-f]{6}", ESTILOS_COR[cfg["estilo"]]["css"])
    mapa_cores = LinearSegmentedColormap.from_list("calor", cores_legenda or list(_paleta(gradiente)))
    ax_leg.imshow(np.linspace(0, 1, 256)[None, :], aspect="auto", cmap=mapa_cores,
                  extent=(0, 1, 0, 1))
    ax_leg.set_xticks([0, 1])
    ax_leg.set_xticklabels(["Poucos casos", "Muitos casos"], fontsize=8, color="#6B7280")
    ax_leg.set_yticks([])
    ax_leg.set_title("Concentração de casos · mesma escala em todos os anos",
                     fontsize=9, color="#374151", loc="left", pad=3)
    for borda in ax_leg.spines.values():
        borda.set_color("#9CA3AF")

    altura_util = 1 - topo_legenda
    for i, ano in enumerate(anos):
        lin, col = divmod(i, por_linha)
        ax = fig.add_axes([col / colunas + 0.01, altura_util * (1 - (lin + 1) / linhas) + 0.005,
                           1 / colunas - 0.02, altura_util / linhas - 0.06 / linhas])
        if fundo is not None:
            ax.imshow(fundo, extent=(0, W, H, 0), zorder=0)
        else:
            ax.add_patch(Rectangle((0, 0), W, H, color="#F2EFE9", zorder=0))
        d = dados[dados["Ano"] == ano]
        px, py = para_tela(d["Longitude"].values, d["Latitude"].values)
        ax.imshow(_camada_calor(px, py, W, H, raio, desf, peso_ref, gradiente),
                  extent=(0, W, H, 0), zorder=2)
        for x, y in contornos:
            ax.plot(x, y, color=COR_CONTORNO, linewidth=1.1, zorder=3)
        if cfg["mostrar_ubs"] and ubs:
            ux, uy = para_tela([p[1] for p in ubs], [p[0] for p in ubs])
            ax.scatter(ux, uy, s=26, color=COR_UBS, edgecolor="white", linewidth=0.9, zorder=4)
        if fundo is not None:
            ax.text(W - 6, H - 6, CREDITO_FUNDO[cfg["fundo"]], fontsize=5.5, color="#374151",
                    ha="right", va="bottom", zorder=5,
                    bbox=dict(facecolor="white", alpha=0.75, edgecolor="none", pad=1.2))
        ax.set_xlim(0, W)
        ax.set_ylim(H, 0)
        ax.set_xticks([])
        ax.set_yticks([])
        for borda in ax.spines.values():
            borda.set_color("#D0D4DC")
        ax.set_title(f"{ano} · {int(len(d))} casos", fontsize=10, fontweight="bold",
                     loc="left", color="#111827", pad=4)
    return fig
