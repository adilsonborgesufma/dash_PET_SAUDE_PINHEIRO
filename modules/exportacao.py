"""
Módulo de exportação de dados: tabela de UBS e botões de download (CSV e GeoJSON).

- As informações do sistema e da equipe agora ficam na aba "Visão Geral"
  (função renderizar_sobre_sistema, em modules/relatorio_detalhado.py), com o mesmo
  texto do relatório em PDF — assim só existe UM lugar para editar os nomes.
- O relatório em PDF é gerado na aba "📑 Relatório".
"""
import streamlit as st

from modules.config import POPULACAO_PADRAO


def renderizar_tabela_ubs(ubs, key_prefix):
    # ================= TABELA DE DADOS DAS UBS =================
    st.subheader("📋 Dados das UBS")

    if not ubs.empty:
        dados_exibicao = ubs.copy()

        dados_exibicao['latitude'] = dados_exibicao.geometry.apply(
            lambda geom: geom.y if hasattr(geom, 'y') else None
        )
        dados_exibicao['longitude'] = dados_exibicao.geometry.apply(
            lambda geom: geom.x if hasattr(geom, 'x') else None
        )

        if 'geometry' in dados_exibicao.columns:
            dados_exibicao = dados_exibicao.drop(columns=['geometry'])

        st.dataframe(dados_exibicao, use_container_width=True, key=f"df_ubs_{key_prefix}")
    else:
        st.warning("Não há dados para exibir.")


def renderizar_exportacao_rodape(ubs, municipio, key_prefix, df_casos_pdf=None, populacao=POPULACAO_PADRAO):
    """
    Botões de exportação. Os parâmetros df_casos_pdf e populacao continuam aceitos
    para não quebrar as chamadas do arquivo principal, mas o PDF agora é feito na
    aba "📑 Relatório".
    """
    # ================= EXPORTAÇÃO =================
    st.subheader("📥 Exportar Dados")

    if ubs.empty or municipio.empty:
        st.caption("Dados geográficos indisponíveis para exportação.")
        return

    coluna_csv, coluna_ubs, coluna_municipio, coluna_pdf = st.columns(4)

    with coluna_csv:
        ubs_sem_geom = ubs.drop(columns=['geometry']) if 'geometry' in ubs.columns else ubs
        st.download_button(
            label="📊 Baixar UBS em CSV",
            data=ubs_sem_geom.to_csv(index=False, encoding='utf-8-sig'),
            file_name="ubs_pinheiro.csv",
            mime="text/csv",
            key=f"btn_csv_ubs_{key_prefix}",
        )

    with coluna_ubs:
        st.download_button(
            label="🗺️ Baixar UBS em GeoJSON",
            data=ubs.to_json(),
            file_name="ubs_pinheiro.geojson",
            mime="application/json",
            key=f"btn_geojson_ubs_{key_prefix}",
        )

    with coluna_municipio:
        st.download_button(
            label="🗺️ Baixar Município GeoJSON",
            data=municipio.to_json(),
            file_name="municipio_pinheiro.geojson",
            mime="application/json",
            key=f"btn_geojson_municipio_{key_prefix}",
        )

    with coluna_pdf:
        st.caption("📄 O relatório em PDF, com gráficos e interpretação, fica na aba **📑 Relatório**.")