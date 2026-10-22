"""
Mapa de calor do RT-PCR de dengue positivo (coluna RTPCRDE) e ranking de bairros.

A camada usa TODAS as notificações com RT-PCR de dengue positivo, mesmo as que
ainda não têm classificação final: o RT-PCR positivo já confirma a infecção e é o
sinal mais rápido para orientar ações de controle vetorial.

O ranking de bairros soma os casos RT-PCR positivos por bairro. Ele inclui também
as notificações sem latitude/longitude, porque o bairro vem da ficha.
"""
import unicodedata

import folium
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from folium.plugins import HeatMap

CATEGORIAS_EXAME = {
    "RT-PCR dengue positivo": {
        "coluna": "RTPCRDE", "valor": "Positivo", "cor": "#6A1B9A", "raio_marcador": 4,
        "gradiente": {"0.2": "#F3E5F5", "0.4": "#CE93D8", "0.6": "#AB47BC", "0.8": "#7B1FA2", "1.0": "#4A148C"},
        "curto": "RT-PCR+",
    },
}
SEM_BAIRRO = "(bairro não informado)"


def mascara_categoria(df, nome):
    """True nas notificações que pertencem à categoria."""
    regra = CATEGORIAS_EXAME[nome]
    if "coluna" in regra:
        if regra["coluna"] not in df.columns:
            return pd.Series(False, index=df.index)
        return df[regra["coluna"]].astype(str).str.strip().eq(regra["valor"])
    if "Classificacao" not in df.columns:
        return pd.Series(False, index=df.index)
    # Dengue, Dengue com sinais de alarme, Dengue grave
    return df["Classificacao"].fillna("").astype(str).str.strip().str.lower().str.startswith(regra["classificacao"])


def _chave(texto):
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().split())


def padronizar_bairros(serie):
    """Junta grafias diferentes do mesmo bairro ('Joao Castelo' e 'João  Castelo'),
    usando a grafia mais frequente na planilha."""
    texto = serie.fillna("").astype(str).str.strip()
    texto = texto.where(~texto.str.lower().isin(["", "nan", "none"]), SEM_BAIRRO)
    chaves = texto.map(_chave)
    grafia = texto.groupby(chaves).agg(lambda s: s.value_counts().index[0])
    return chaves.map(grafia)


# ======================= mapa =======================

def adicionar_camadas_exame(mapa, df, categorias, raio, desfoque, sufixo="", mostrar=True, referencia=None,
                            icone="🔥"):
    """Mapa de calor de cada categoria (liga/desliga também pelo botão de camadas do mapa).
    'sufixo' entra no nome da camada (ex.: " · 2026"); 'referencia' = [lat, lon, peso] de um
    ponto invisível que fixa a escala de cores (mesma régua em todas as camadas)."""
    contagem = {}
    if df is None or df.empty:
        return contagem
    for nome in categorias:
        regra = CATEGORIAS_EXAME[nome]
        dados = df[mascara_categoria(df, nome)].dropna(subset=["Latitude", "Longitude"])
        contagem[nome] = len(dados)
        if dados.empty:
            continue
        camada = folium.FeatureGroup(name=f"{icone} {nome}{sufixo}", show=mostrar)
        pontos = [[lat, lon, 1.0] for lat, lon in dados[["Latitude", "Longitude"]].values.tolist()]
        if referencia is not None:
            pontos.append(list(referencia))
        HeatMap(
            pontos,
            radius=raio, blur=desfoque, min_opacity=0.3, gradient=regra["gradiente"],
        ).add_to(camada)
        camada.add_to(mapa)
    return contagem


def adicionar_legenda_camadas(mapa, categorias, contagem):
    itens = ""
    for nome in categorias:
        regra = CATEGORIAS_EXAME[nome]
        paradas = ", ".join(f"{cor} {float(p) * 100:.0f}%" for p, cor in regra["gradiente"].items())
        itens += (f'<div style="font-size:12px;color:#222;margin:2px 0 3px 0;">{nome} '
                  f'({contagem.get(nome, 0)} casos)</div>'
                  f'<div style="width:160px;height:10px;border-radius:4px;'
                  f'background:linear-gradient(to right,{paradas});border:1px solid #999;"></div>'
                  f'<div style="display:flex;justify-content:space-between;width:160px;font-size:10px;'
                  f'color:#555;"><span>poucos</span><span>muitos</span></div>')
    html_legenda = f"""
    {{% macro html(this, kwargs) %}}
    <div style="position: fixed; bottom: 40px; right: 14px; z-index: 9999; background: white;
                padding: 8px 12px; border-radius: 8px; box-shadow: 0 1px 6px rgba(0,0,0,.3);
                font-family: sans-serif;">
        <div style="font-weight:bold;font-size:13px;margin-bottom:4px;color:#111;">🧪 Mapa de calor</div>
        {itens}
    </div>
    {{% endmacro %}}
    """
    legenda = folium.MacroElement()
    legenda._template = folium.map.Template(html_legenda)
    mapa.get_root().add_child(legenda)


# ======================= bairros prioritários =======================

def tabela_bairros(df):
    """Casos por bairro em cada categoria, do mais prioritário para o menos."""
    if df is None or df.empty:
        return pd.DataFrame()
    base = df.copy()
    base["Bairro"] = padronizar_bairros(base["Bairro"] if "Bairro" in base.columns else pd.Series(index=base.index))
    tabela = pd.DataFrame({"Bairro": base["Bairro"]})
    for nome in CATEGORIAS_EXAME:
        tabela[nome] = mascara_categoria(base, nome).astype(int)
    tabela["Notificações"] = 1
    tabela = tabela.groupby("Bairro").sum()
    tabela = tabela.sort_values(list(CATEGORIAS_EXAME) + ["Notificações"], ascending=False)
    return tabela.reset_index()


def renderizar_bairros_prioritarios(df_bairros, anos_marcados, key_prefix="bairros"):
    """Seção abaixo do mapa: quais bairros concentram mais casos positivos."""
    st.subheader("🏘️ Bairros prioritários")
    if df_bairros is None or df_bairros.empty or "Ano" not in df_bairros.columns:
        st.info("Sem notificações para montar o ranking de bairros.")
        return

    anos_disponiveis = sorted(int(a) for a in df_bairros["Ano"].dropna().unique())
    anos_marcados = [int(a) for a in anos_marcados if int(a) in anos_disponiveis] or anos_disponiveis
    criterio = next(iter(CATEGORIAS_EXAME))  # RT-PCR dengue positivo
    periodo = st.radio(
        "Período", [f"Só {anos_marcados[-1]} (ano mais recente)", "Anos marcados na barra lateral"],
        key=f"{key_prefix}_periodo", horizontal=True,
    )
    anos = [anos_marcados[-1]] if periodo.startswith("Só") else anos_marcados

    dados = df_bairros[df_bairros["Ano"].isin(anos)]
    tabela = tabela_bairros(dados)
    if tabela.empty:
        st.info("Sem notificações no período escolhido.")
        return
    tabela = tabela.sort_values([criterio, "Notificações"], ascending=False).reset_index(drop=True)
    com_casos = tabela[tabela[criterio] > 0]
    texto_anos = ", ".join(str(a) for a in anos)

    if com_casos.empty:
        st.success(f"Nenhum caso de **{criterio}** em {texto_anos}.")
    else:
        total = int(com_casos[criterio].sum())
        top = com_casos.head(3)
        destaque = "; ".join(
            f"**{b}** ({int(v)}, {100 * v / total:.0f}%)".replace(".", ",")
            for b, v in zip(top["Bairro"], top[criterio])
        )
        st.markdown(f"Em **{texto_anos}**, os bairros com mais casos de **{criterio}** foram: {destaque}. "
                    f"Total no período: **{total}** casos em **{len(com_casos)}** bairros.")

        grafico = com_casos.head(10).iloc[::-1]
        cor = CATEGORIAS_EXAME[criterio]["cor"]
        fig = go.Figure(go.Bar(
            x=grafico[criterio], y=grafico["Bairro"], orientation="h", marker_color=cor,
            text=grafico[criterio], textposition="outside", cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>Casos: %{x}<extra></extra>",
        ))
        fig.update_layout(
            title=dict(text=f"Bairros com mais casos · {criterio} · {texto_anos}", font=dict(size=15)),
            height=max(260, 34 * len(grafico) + 90), margin=dict(t=60, b=30, l=10, r=30),
            xaxis=dict(title="Casos", rangemode="tozero"), yaxis=dict(title=""),
        )
        fig.update_xaxes(range=[0, max(grafico[criterio].max(), 1) * 1.2])
        st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_grafico")

    st.dataframe(tabela, hide_index=True, use_container_width=True, key=f"{key_prefix}_tabela")
    sem_bairro = int(tabela.loc[tabela["Bairro"] == SEM_BAIRRO, "Notificações"].sum())
    st.caption(
        "Contagem por bairro das notificações com **RT-PCR de dengue positivo** (coluna RTPCRDE) no período, "
        "inclusive as que ainda não têm latitude/longitude (o bairro vem da ficha). "
        "\"Notificações\" é o total de notificações do bairro no período. \"Zona Rural\" reúne vários povoados."
        + (f" {sem_bairro} notificação(ões) sem bairro preenchido." if sem_bairro else "")
    )
    st.caption(
        "⚠️ O ranking apoia a priorização das áreas. A indicação de bloqueio de transmissão e de "
        "aplicação de inseticida (UBV/fumacê) é decisão técnica da Vigilância e do controle vetorial."
    )
    st.download_button(
        "📥 Baixar ranking de bairros (CSV)",
        data=tabela.to_csv(index=False, sep=";", encoding="utf-8-sig"),
        file_name=f"bairros_prioritarios_{'_'.join(str(a) for a in anos)}.csv",
        mime="text/csv", key=f"{key_prefix}_csv",
    )
