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


def adicionar_bolhas_bairros(mapa, df, cores_agravo, mostrar_nomes=True):
    """Uma bolha por bairro (tamanho = nº de casos) com o nome do bairro.
    O popup mostra só contagens por agravo e por ano, nunca dados individuais."""
    dados = df.dropna(subset=["Latitude", "Longitude"])
    if dados.empty:
        return 0
    camada = folium.FeatureGroup(name="Casos por bairro")
    maximo = dados.groupby("Bairro").size().max()
    for bairro, grupo in dados.groupby("Bairro"):
        total = len(grupo)
        lat, lon = float(grupo["Latitude"].iloc[0]), float(grupo["Longitude"].iloc[0])
        por_agravo = grupo["Tipo_Caso"].value_counts()
        dominante = por_agravo.index[0]
        cor = cores_agravo.get(dominante, "#1E88E5")
        raio = 7 + 23 * (total / maximo) ** 0.5
        linhas = [f"<b>{bairro}</b>", f"<b>{total}</b> caso(s)"]
        linhas += [f"{agravo}: {n}" for agravo, n in por_agravo.items()]
        por_ano = grupo["Ano"].value_counts().sort_index()
        linhas.append("Por ano: " + ", ".join(f"{int(a)}: {n}" for a, n in por_ano.items()))
        folium.CircleMarker(
            location=[lat, lon], radius=raio, color=cor, weight=2,
            fill=True, fill_color=cor, fill_opacity=0.45,
            popup=folium.Popup("<br>".join(linhas), max_width=260),
            tooltip=f"{bairro}: {total} caso(s)",
        ).add_to(camada)
        if mostrar_nomes:
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
