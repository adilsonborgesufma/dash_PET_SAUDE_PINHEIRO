"""
Gráficos e indicadores do Painel de Vigilância Epidemiológica - Pinheiro/MA.

Funções chamadas pelo arquivo principal:
    renderizar_visao_geral(df, populacao)
    renderizar_estatisticas_e_graficos(df, key_prefix, populacao)

O DataFrame recebido já vem filtrado e padronizado pelo painel, com as colunas:
    Ano (inteiro), Tipo_Caso, Genero, Idade, Faixa_Etaria, RNS1, RTPCRDE, ...

Regras usadas em todos os gráficos:
  - Ano é tratado como CATEGORIA (2023, 2024...) — nunca aparece "2.023,5".
  - O eixo vertical tem folga de 25% acima da maior barra, e os rótulos não são
    cortados (cliponaxis=False).
  - A cor de cada agravo é a mesma do mapa (CORES_CASOS_MAPA do config.py).
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    from modules.config import CORES_CASOS_MAPA
except Exception:  # se o config mudar, o gráfico continua funcionando
    CORES_CASOS_MAPA = {}

CORES_PADRAO = {"Dengue": "#E53935", "Chikungunya": "#FB8C00", "Zika": "#8E24AA"}
CORES_GENERO = {"Feminino": "#AD1457", "Masculino": "#1565C0", "Ignorado": "#78909C", "Não informado": "#B0BEC5"}
COR_UNICA = "#00897B"
COR_MEDIA = "#C62828"
ORDEM_FAIXAS = ["0–9", "10–19", "20–29", "30–39", "40–49", "50–59", "60+", "Não informada"]


# =====================================================================
# AUXILIARES
# =====================================================================
def _num(valor, casas=0):
    """Formata no padrão brasileiro: 1234.5 -> '1.234,5'."""
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _cor_agravo(agravo):
    return CORES_CASOS_MAPA.get(agravo) or CORES_PADRAO.get(agravo, "#1E88E5")


def _layout(fig, titulo, eixo_x, eixo_y="Número de Casos", altura=380, maximo=None, legenda=True):
    fig.update_layout(
        title=dict(text=titulo, font=dict(size=16)),
        height=altura,
        margin=dict(t=70, b=40, l=10, r=10),
        bargap=0.25,
        hovermode="closest",
        showlegend=legenda,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1),
    )
    fig.update_xaxes(title_text=eixo_x, type="category", showgrid=False)
    fig.update_yaxes(title_text=eixo_y, rangemode="tozero", separatethousands=True)
    if maximo is not None:
        fig.update_yaxes(range=[0, max(maximo, 1) * 1.25])
    fig.update_traces(cliponaxis=False, selector=dict(type="bar"))
    return fig


def _plotar(fig, chave):
    st.plotly_chart(fig, use_container_width=True, key=chave)


def _ordem_anos(df):
    return [int(a) for a in sorted(df["Ano"].dropna().unique())]


# =====================================================================
# VISÃO GERAL
# =====================================================================
def renderizar_visao_geral(df, populacao):
    """Indicadores principais + evolução anual por agravo."""
    if df is None or df.empty:
        st.info("Nenhum caso encontrado com os filtros atuais. Ajuste os filtros na barra lateral.")
        return

    anos = _ordem_anos(df)
    ano_atual = anos[-1]
    por_ano = df.groupby("Ano").size().reindex(anos, fill_value=0)
    casos_atual = int(por_ano[ano_atual])
    incidencia = 10000 * casos_atual / populacao if populacao else 0

    delta = None
    if len(anos) >= 2 and por_ano[anos[-2]]:
        variacao = 100 * (casos_atual - por_ano[anos[-2]]) / por_ano[anos[-2]]
        delta = f"{'+' if variacao >= 0 else ''}{_num(variacao, 1)}% vs {anos[-2]}"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total de casos", _num(len(df)), help=f"Soma de {anos[0]} a {ano_atual} com os filtros atuais.")
    c2.metric(f"Casos em {ano_atual}", _num(casos_atual), delta=delta, delta_color="inverse")
    c3.metric(f"Incidência {ano_atual}", f"{_num(incidencia, 1)} /10 mil hab.",
              help=f"Casos de {ano_atual} ÷ população ({_num(populacao)}) × 10.000.")
    c4.metric("Anos analisados", f"{anos[0]}–{ano_atual}" if len(anos) > 1 else str(ano_atual))

    # Casos por agravo (indicadores pequenos com a cor do mapa)
    por_agravo = df["Tipo_Caso"].value_counts()
    colunas = st.columns(max(len(por_agravo), 1))
    for coluna, (agravo, quantidade) in zip(colunas, por_agravo.items()):
        coluna.markdown(
            f"<div style='border-left:4px solid {_cor_agravo(agravo)}; padding:4px 10px;'>"
            f"<div style='font-size:13px; opacity:0.8;'>{agravo}</div>"
            f"<div style='font-size:22px; font-weight:600;'>{_num(quantidade)}</div>"
            f"<div style='font-size:12px; opacity:0.7;'>{_num(100 * quantidade / len(df), 1)}% do total</div></div>",
            unsafe_allow_html=True,
        )

    st.markdown("")
    tabela = pd.crosstab(df["Ano"], df["Tipo_Caso"]).reindex(anos, fill_value=0)
    fig = go.Figure()
    for agravo in tabela.columns:
        fig.add_bar(
            x=[str(a) for a in anos], y=tabela[agravo], name=agravo,
            marker_color=_cor_agravo(agravo),
            hovertemplate=f"<b>{agravo}</b><br>Ano: %{{x}}<br>Casos: %{{y}}<extra></extra>",
        )
    totais = tabela.sum(axis=1)
    fig.add_scatter(
        x=[str(a) for a in anos], y=totais, mode="text", text=[_num(t) for t in totais],
        textposition="top center", showlegend=False, hoverinfo="skip", cliponaxis=False,
    )
    fig.update_layout(barmode="stack")
    _layout(fig, "Casos por ano e agravo", "Ano", maximo=totais.max())
    _plotar(fig, "visao_geral_ano_agravo")


# =====================================================================
# ESTATÍSTICAS E GRÁFICOS (abaixo do mapa)
# =====================================================================
def renderizar_estatisticas_e_graficos(df, key_prefix="mapa", populacao=None):
    """Evolução anual com média histórica e alerta, agravo por ano e gênero por ano."""
    if df is None or df.empty:
        return

    st.subheader("📈 Estatísticas dos casos filtrados")
    anos = _ordem_anos(df)
    ano_atual = anos[-1]
    por_ano = df.groupby("Ano").size().reindex(anos, fill_value=0)

    # ---------- 1. Evolução total com média histórica
    # Média histórica = média dos anos ANTERIORES ao mais recente (o ano atual
    # não entra na média com a qual ele mesmo é comparado).
    anteriores = por_ano.drop(ano_atual)
    media = float(anteriores.mean()) if len(anteriores) else None

    fig = go.Figure()
    fig.add_bar(
        x=[str(a) for a in anos], y=por_ano.values, marker_color=COR_UNICA, name="Casos",
        text=[_num(v) for v in por_ano.values], textposition="outside",
        hovertemplate="Ano: %{x}<br>Casos: %{y}<extra></extra>",
    )
    if media is not None:
        fig.add_hline(
            y=media, line_dash="dash", line_color=COR_MEDIA, line_width=1.5,
            annotation_text=f"Média dos anos anteriores: {_num(media, 1)}",
            annotation_position="top left", annotation_font_color=COR_MEDIA,
        )
    _layout(fig, "Evolução Total de Casos por Ano", "Ano", maximo=max(por_ano.max(), media or 0), legenda=False)
    _plotar(fig, f"{key_prefix}_evolucao_total")

    if media:
        atual = int(por_ano[ano_atual])
        razao = atual / media
        if razao > 1:
            st.warning(
                f"**Atenção:** {ano_atual} está **acima da média** dos anos anteriores "
                f"({_num(atual)} casos vs. média de {_num(media, 1)} casos/ano; {_num(razao, 1)}× a média). "
                "Recomenda-se atenção redobrada na vigilância epidemiológica."
            )
        else:
            st.success(
                f"{ano_atual} está **dentro ou abaixo da média** dos anos anteriores "
                f"({_num(atual)} casos vs. média de {_num(media, 1)} casos/ano)."
            )
    if populacao:
        st.caption(
            f"Incidência em {ano_atual}: **{_num(10000 * por_ano[ano_atual] / populacao, 1)} casos por 10.000 "
            f"habitantes** (população de referência: {_num(populacao)})."
        )

    col_esq, col_dir = st.columns(2)

    # ---------- 2. Agravo por ano (barras agrupadas)
    with col_esq:
        tabela = pd.crosstab(df["Ano"], df["Tipo_Caso"]).reindex(anos, fill_value=0)
        fig = go.Figure()
        for agravo in tabela.columns:
            fig.add_bar(
                x=[str(a) for a in anos], y=tabela[agravo], name=agravo, marker_color=_cor_agravo(agravo),
                text=[_num(v) if v else "" for v in tabela[agravo]], textposition="outside",
                hovertemplate=f"<b>{agravo}</b><br>Ano: %{{x}}<br>Casos: %{{y}}<extra></extra>",
            )
        fig.update_layout(barmode="group")
        _layout(fig, "Casos por agravo e ano", "Ano", maximo=tabela.to_numpy().max(), altura=360)
        _plotar(fig, f"{key_prefix}_agravo_ano")

    # ---------- 3. Gênero por ano (barras agrupadas)
    with col_dir:
        if "Genero" in df.columns:
            tabela = pd.crosstab(df["Ano"], df["Genero"]).reindex(anos, fill_value=0)
            ordem = [g for g in ("Feminino", "Masculino", "Ignorado", "Não informado") if g in tabela.columns]
            ordem += [g for g in tabela.columns if g not in ordem]
            fig = go.Figure()
            for genero in ordem:
                fig.add_bar(
                    x=[str(a) for a in anos], y=tabela[genero], name=genero,
                    marker_color=CORES_GENERO.get(genero, "#90A4AE"),
                    text=[_num(v) if v else "" for v in tabela[genero]], textposition="outside",
                    hovertemplate=f"<b>{genero}</b><br>Ano: %{{x}}<br>Casos: %{{y}}<extra></extra>",
                )
            fig.update_layout(barmode="group")
            _layout(fig, "Casos por gênero e ano", "Ano", maximo=tabela.to_numpy().max(), altura=360)
            _plotar(fig, f"{key_prefix}_genero_ano")

    # ---------- 4. Faixa etária (barras) — se houver idade
    if "Faixa_Etaria" in df.columns:
        contagem = df["Faixa_Etaria"].value_counts()
        faixas = [f for f in ORDEM_FAIXAS if f in contagem.index]
        fig = go.Figure()
        fig.add_bar(
            x=faixas, y=[contagem[f] for f in faixas], marker_color=COR_UNICA,
            text=[_num(contagem[f]) for f in faixas], textposition="outside",
            hovertemplate="Faixa: %{x} anos<br>Casos: %{y}<extra></extra>",
        )
        _layout(fig, "Casos por faixa etária", "Faixa etária (anos)",
                maximo=contagem.max(), altura=340, legenda=False)
        _plotar(fig, f"{key_prefix}_faixa_etaria")

    # ---------- Tabela-resumo (os mesmos números dos gráficos)
    with st.expander("📋 Ver tabela por ano e agravo"):
        tabela = pd.crosstab(df["Ano"], df["Tipo_Caso"], margins=True, margins_name="Total")
        tabela.index = tabela.index.astype(str)
        st.dataframe(tabela, use_container_width=True)
