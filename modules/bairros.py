"""
Localização dos casos POR BAIRRO (Painel_Arboviroses_Pinheiro.py, versão pública).

O painel público não lê a latitude/longitude das notificações. Cada caso é colocado
no ponto de referência do seu bairro, definido em assets/bairros_pinheiro.csv
(Bairro;Latitude;Longitude;Observacao). Assim o mapa mostra quantos casos há em
cada bairro, nunca onde mora cada pessoa (LGPD).

A Vigilância pode corrigir ou acrescentar bairros nesse arquivo (por exemplo, usando
o ponto da praça ou da igreja do bairro). "Zona Rural" e notificações sem bairro não
têm ponto no mapa, mas continuam em todas as contagens e gráficos.
"""
import os
import unicodedata

import folium
import pandas as pd

CAMINHO_BAIRROS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "bairros_pinheiro.csv"
)
SEM_BAIRRO = "(bairro não informado)"
ZONA_RURAL = "Zona Rural"


def _chave(texto):
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().split())


def carregar_referencia_bairros(caminho=CAMINHO_BAIRROS):
    """Tabela de pontos de referência dos bairros (vazia se o arquivo não existir)."""
    if not os.path.exists(caminho):
        return pd.DataFrame(columns=["Bairro", "Latitude", "Longitude", "chave"])
    tabela = pd.read_csv(caminho, sep=";", dtype=str).fillna("")
    tabela["Latitude"] = pd.to_numeric(tabela["Latitude"].str.replace(",", "."), errors="coerce")
    tabela["Longitude"] = pd.to_numeric(tabela["Longitude"].str.replace(",", "."), errors="coerce")
    tabela = tabela.dropna(subset=["Latitude", "Longitude"])
    tabela["chave"] = tabela["Bairro"].map(_chave)
    return tabela.drop_duplicates("chave")


def atribuir_coordenadas_bairro(df, referencia):
    """Coloca cada caso no ponto do seu bairro. Devolve (df, resumo dos não mapeados).
    Casos sem bairro, da Zona Rural ou de bairro fora da tabela ficam sem ponto (NaN)."""
    df = df.copy()
    resumo = {"zona_rural": 0, "sem_bairro": 0, "fora_da_tabela": {}}
    if df.empty:
        df["Latitude"], df["Longitude"] = pd.Series(dtype=float), pd.Series(dtype=float)
        return df, resumo

    texto = df["Bairro"] if "Bairro" in df.columns else pd.Series("", index=df.index)
    texto = texto.fillna("").astype(str).str.strip()
    vazio = texto.str.lower().isin(["", "nan", "none"])
    chaves = texto.map(_chave)

    por_chave = referencia.set_index("chave") if not referencia.empty else pd.DataFrame()
    # grafia: a da tabela de referência; se não houver, a mais frequente na planilha
    grafia_planilha = texto[~vazio].groupby(chaves[~vazio]).agg(lambda s: s.value_counts().index[0])
    nome = chaves.map(lambda c: por_chave["Bairro"].get(c) if c in por_chave.index else grafia_planilha.get(c))
    df["Bairro"] = nome.where(~vazio, SEM_BAIRRO)

    mapeado = chaves.isin(por_chave.index) & ~vazio
    df["Latitude"] = chaves.map(por_chave["Latitude"] if not por_chave.empty else {}).where(mapeado)
    df["Longitude"] = chaves.map(por_chave["Longitude"] if not por_chave.empty else {}).where(mapeado)

    rural = chaves.eq(_chave(ZONA_RURAL))
    resumo["zona_rural"] = int(rural.sum())
    resumo["sem_bairro"] = int(vazio.sum())
    outros = df.loc[~mapeado & ~vazio & ~rural, "Bairro"].value_counts()
    resumo["fora_da_tabela"] = {str(k): int(v) for k, v in outros.items()}
    return df, resumo


def texto_nao_mapeados(resumo):
    partes = []
    if resumo["zona_rural"]:
        partes.append(f"{resumo['zona_rural']} da Zona Rural")
    if resumo["sem_bairro"]:
        partes.append(f"{resumo['sem_bairro']} sem bairro")
    fora = resumo["fora_da_tabela"]
    if fora:
        partes.append(f"{sum(fora.values())} de bairro sem ponto no mapa ({', '.join(fora)})")
    return "; ".join(partes)


def adicionar_bolhas_bairros(mapa, df, cores_agravo, mostrar_nomes=True,
                             nome_camada="Casos por bairro", mostrar=True, maximo=None, rotulo_ano=None):
    """Uma bolha por bairro (tamanho = nº de casos) com o nome do bairro.
    O popup mostra só contagens por agravo e por ano, nunca dados individuais.
    'maximo' fixa a escala do tamanho (útil para comparar camadas de anos diferentes)."""
    dados = df.dropna(subset=["Latitude", "Longitude"])
    if dados.empty:
        return 0
    camada = folium.FeatureGroup(name=nome_camada, show=mostrar)
    maximo = maximo or dados.groupby("Bairro").size().max()
    for bairro, grupo in dados.groupby("Bairro"):
        total = len(grupo)
        lat, lon = float(grupo["Latitude"].iloc[0]), float(grupo["Longitude"].iloc[0])
        por_agravo = grupo["Tipo_Caso"].value_counts()
        dominante = por_agravo.index[0]
        cor = cores_agravo.get(dominante, "#1E88E5")
        raio = 7 + 23 * (total / maximo) ** 0.5
        linhas = [f"<b>{bairro}</b>" + (f" · {rotulo_ano}" if rotulo_ano is not None else ""),
                  f"<b>{total}</b> caso(s)"]
        linhas += [f"{agravo}: {n}" for agravo, n in por_agravo.items()]
        por_ano = grupo["Ano"].value_counts().sort_index()
        linhas.append("Por ano: " + ", ".join(f"{int(a)}: {n}" for a, n in por_ano.items()))
        folium.CircleMarker(
            location=[lat, lon], radius=raio, color=cor, weight=2,
            fill=True, fill_color=cor, fill_opacity=0.45,
            popup=folium.Popup("<br>".join(linhas), max_width=260),
            tooltip=f"{bairro}{f' · {rotulo_ano}' if rotulo_ano is not None else ''}: {total} caso(s)",
        ).add_to(camada)
        if mostrar_nomes and rotulo_ano is None:
            folium.Marker(
                location=[lat, lon],
                icon=folium.DivIcon(
                    icon_size=(160, 30), icon_anchor=(80, -int(raio) + 2),
                    html=(f'<div style="text-align:center;font:600 11px sans-serif;color:#1F2937;'
                          f'text-shadow:0 0 3px #fff,0 0 3px #fff,0 0 3px #fff;white-space:nowrap;">'
                          f'{bairro} · {total}</div>'),
                ),
            ).add_to(camada)
    camada.add_to(mapa)
    return dados["Bairro"].nunique()


def adicionar_nomes_bairros(mapa, df, nome_camada="🏷️ Nomes dos bairros"):
    """Camada só com o nome de cada bairro e o total de casos (anos marcados)."""
    dados = df.dropna(subset=["Latitude", "Longitude"])
    if dados.empty:
        return
    camada = folium.FeatureGroup(name=nome_camada, show=True)
    for bairro, grupo in dados.groupby("Bairro"):
        folium.Marker(
            location=[float(grupo["Latitude"].iloc[0]), float(grupo["Longitude"].iloc[0])],
            icon=folium.DivIcon(
                icon_size=(160, 30), icon_anchor=(80, 8),
                html=(f'<div style="text-align:center;font:600 11px sans-serif;color:#1F2937;'
                      f'text-shadow:0 0 3px #fff,0 0 3px #fff,0 0 3px #fff;white-space:nowrap;">'
                      f'{bairro} · {len(grupo)}</div>'),
            ),
        ).add_to(camada)
    camada.add_to(mapa)


def tabela_casos_por_bairro(df):
    """Tabela agregada (sem dados individuais): bairro x agravo x ano."""
    if df.empty:
        return pd.DataFrame()
    tabela = (df.groupby(["Bairro", "Ano", "Tipo_Caso"]).size()
              .rename("Casos").reset_index()
              .rename(columns={"Tipo_Caso": "Agravo"}))
    totais = tabela.groupby("Bairro")["Casos"].transform("sum")
    return tabela.assign(_t=totais).sort_values(["_t", "Bairro", "Ano", "Agravo"],
                                                ascending=[False, True, True, True]).drop(columns="_t")


def renderizar_mapa_rtpcr(df_notificacoes, anos_marcados, municipio_gdf, altura=520, key_prefix="mapa_rtpcr"):
    """Mapa próprio do RT-PCR de dengue positivo (coluna RTPCRDE), por bairro.
    Cada ano marcado na barra lateral vira uma camada (liga/desliga no botão de camadas
    do mapa), todas com a mesma régua de cores; os nomes dos bairros ficam numa camada à parte."""
    import streamlit as st
    from streamlit_folium import st_folium

    from folium.plugins import HeatMap

    from modules.calor_suavizado import coordenadas_em_grade, pontos_heatmap
    from modules.comparacao_mapas import DESLOCAMENTO_REFERENCIA_GRAUS, calcular_pico
    from modules.camadas_exames import CATEGORIAS_EXAME, adicionar_legenda_camadas, mascara_categoria

    nome = next(iter(CATEGORIAS_EXAME))  # "RT-PCR dengue positivo"
    st.subheader("🧪 Mapa de calor: RT-PCR de dengue positivo")
    if df_notificacoes is None or df_notificacoes.empty:
        st.info("Sem notificações para o mapa do RT-PCR.")
        return

    anos = sorted(int(a) for a in anos_marcados)
    dados = df_notificacoes[df_notificacoes["Ano"].isin(anos)]
    positivos = dados[mascara_categoria(dados, nome)]
    no_mapa = positivos.dropna(subset=["Latitude", "Longitude"])
    if not anos:
        st.info("Marque ao menos um ano na barra lateral.")
        return

    referencia = carregar_referencia_bairros()
    centro = ([float(referencia["Latitude"].median()), float(referencia["Longitude"].median())]
              if not referencia.empty else [-2.525, -45.085])
    zoom = 14
    mapa = folium.Map(location=centro, zoom_start=zoom, tiles="OpenStreetMap", control_scale=True)
    if municipio_gdf is not None and not municipio_gdf.empty:
        folium.GeoJson(
            municipio_gdf[["geometry"]],
            style_function=lambda _: {"color": "#374151", "weight": 1.5, "fill": False},
            name="Limite municipal",
        ).add_to(mapa)

    # Mesmo mapa de calor do Passo8, com a contagem por quadradinho de ~150 m (nunca a
    # coordenada real), uma camada por ano, todas com a mesma régua de cores.
    raio, desfoque = 18, 9
    grade = coordenadas_em_grade(positivos)
    base = grade[["Ano", "Latitude", "Longitude"]].dropna()
    maximo = calcular_pico(base, centro[1], centro[0], zoom, 900, altura, raio, desfoque) if not base.empty else 1.0
    ponto_ref = [centro[0] - DESLOCAMENTO_REFERENCIA_GRAUS, centro[1] + DESLOCAMENTO_REFERENCIA_GRAUS, float(maximo)]
    for ano in anos:
        pontos_ano = pontos_heatmap(grade[grade["Ano"] == ano])
        if not pontos_ano:
            continue
        camada = folium.FeatureGroup(name=f"🦟 {nome} · {ano}", show=True)
        HeatMap(pontos_ano + [ponto_ref], radius=raio, blur=desfoque, min_opacity=0.3,
                gradient=CATEGORIAS_EXAME[nome]["gradiente"]).add_to(camada)
        camada.add_to(mapa)
    contagem = {nome: len(base)}
    adicionar_nomes_bairros(mapa, no_mapa, nome_camada="🏷️ Bairros (RT-PCR positivos)")
    adicionar_legenda_camadas(mapa, [nome], contagem)
    folium.LayerControl(collapsed=False).add_to(mapa)
    st_folium(mapa, height=altura, use_container_width=True, returned_objects=[],
              center=tuple(centro), zoom=zoom, key=f"{key_prefix}_{'_'.join(map(str, anos))}")

    st.caption(
        f"{len(positivos)} notificação(ões) com RT-PCR de dengue positivo (coluna RTPCRDE) em "
        f"{', '.join(map(str, anos))}. O calor usa a contagem de casos em quadradinhos de cerca de 150 m "
        "(a localização exata das notificações não é mostrada); os nomes indicam quantos positivos há em "
        "cada bairro. Use o botão de camadas do mapa para ligar e desligar cada ano; todos os anos usam "
        "a mesma escala de cores."
    )
