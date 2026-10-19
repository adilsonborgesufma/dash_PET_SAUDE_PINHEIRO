"""
Módulo de estatísticas e gráficos: os cards de números, a "Visão Geral"
resumida e todos os gráficos com seletor (Análise Temporal, Análise de
Crescimento e Redução), usados nas 3 abas do dashboard.
"""
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from modules.estatisticas import calcular_incidencia

CORES_GRAFICOS = {
    'Dengue': '#EF5350',
    'Chikungunya': '#FFA726',
    'Zika': '#AB47BC'
}
CORES_TIPOS = {'Dengue': '#EF5350', 'Chikungunya': '#FFA726', 'Zika': '#AB47BC'}


def renderizar_estatisticas_e_graficos(df_base, key_prefix, populacao):
    if df_base.empty:
        st.info("Nenhum caso encontrado com os filtros atuais.")
        return

    st.subheader("📊 Estatísticas dos Casos")

    total_casos = len(df_base)
    incidencia = calcular_incidencia(total_casos, populacao)

    col_card1, col_card2, col_card3, col_card4 = st.columns(4)

    with col_card1:
        st.metric(label="📊 Total de Casos", value=total_casos, delta=None)

    with col_card2:
        if incidencia is not None:
            st.metric(
                label="📈 Incidência (por 10.000 hab.)",
                value=incidencia,
                delta=f"pop. considerada: {populacao:,}".replace(",", ".")
            )
        else:
            st.metric(label="📈 Incidência", value="N/D")

    with col_card3:
        tipo_mais_comum = df_base['Tipo_Caso'].mode()[0]
        count_tipo = len(df_base[df_base['Tipo_Caso'] == tipo_mais_comum])
        st.metric(
            label=f"🦟 Mais comum: {tipo_mais_comum}",
            value=count_tipo,
            delta=f"{count_tipo/total_casos*100:.1f}% do total"
        )

    with col_card4:
        ano_mais_casos = df_base['Ano'].mode()[0]
        count_ano = len(df_base[df_base['Ano'] == ano_mais_casos])
        st.metric(
            label=f"📅 Ano com mais casos: {ano_mais_casos}",
            value=count_ano,
            delta=f"{count_ano/total_casos*100:.1f}% do total"
        )

    # ===== CARDS POR ANO =====
    st.divider()
    st.subheader("📅 Distribuição por Ano")

    anos_no_df = sorted(df_base['Ano'].unique())
    cols_ano = st.columns(len(anos_no_df))

    for i, ano in enumerate(anos_no_df):
        count_ano = len(df_base[df_base['Ano'] == ano])
        with cols_ano[i]:
            st.metric(
                label=f"📅 {ano}",
                value=count_ano,
                delta=f"{count_ano/total_casos*100:.1f}%" if total_casos > 0 else None
            )

    # ===== CARDS POR TIPO DE CASO =====
    st.divider()
    st.subheader("📊 Distribuição por Tipo de Caso")

    tipos_no_df = sorted(df_base['Tipo_Caso'].unique())
    cols_tipo = st.columns(len(tipos_no_df))

    for i, tipo in enumerate(tipos_no_df):
        count_tipo = len(df_base[df_base['Tipo_Caso'] == tipo])
        cor = CORES_TIPOS.get(tipo, '#2196F3')

        with cols_tipo[i]:
            st.markdown(f"""
            <div style="text-align: center; padding: 10px; border-radius: 10px; background-color: #f5f5f5;">
                <div style="font-size: 0.9em; color: #666;">{tipo}</div>
                <div style="font-size: 2em; font-weight: bold; color: {cor};">{count_tipo}</div>
                <div style="font-size: 0.8em; color: #888;">{count_tipo/total_casos*100:.1f}% do total</div>
            </div>
            """, unsafe_allow_html=True)

    # ================= GRÁFICOS (SELEÇÃO ESTILO "BIBLIOSHINY") =================
    st.divider()
    st.subheader("📈 Análise Temporal dos Casos")

    opcoes_temporais = [
        "Evolução Total de Casos",
        "Evolução por Tipo de Caso",
        "Barras Empilhadas + Total",
        "Distribuição por Tipo (Pizza)",
        "Casos por Ano e Gênero",
        "Casos por Gênero e Tipo",
    ]

    grafico_temporal_escolhido = st.radio(
        "Selecione o gráfico",
        opcoes_temporais,
        horizontal=True,
        key=f"radio_temporal_{key_prefix}"
    )

    if grafico_temporal_escolhido == "Evolução Total de Casos":
        evolucao_total = df_base.groupby('Ano').size().reset_index(name='Total')
        media_historica = evolucao_total['Total'].mean()

        fig1 = px.bar(
            evolucao_total, x='Ano', y='Total',
            title='Evolução Total de Casos por Ano',
            text='Total', color_discrete_sequence=['#1a73e8']
        )
        fig1.update_traces(textposition='outside')
        fig1.add_hline(
            y=media_historica,
            line_dash="dash",
            line_color="#E53935",
            annotation_text=f"Média histórica: {media_historica:.1f}",
            annotation_position="top left"
        )
        fig1.update_layout(xaxis_title='Ano', yaxis_title='Número de Casos', showlegend=False)
        st.plotly_chart(fig1, use_container_width=True, key=f"fig1_{key_prefix}")

        ultimo_ano = evolucao_total.loc[evolucao_total['Ano'].idxmax()]
        if ultimo_ano['Total'] > media_historica:
            st.warning(
                f"⚠️ O ano de {int(ultimo_ano['Ano'])} está **acima** da média histórica "
                f"({int(ultimo_ano['Total'])} casos vs. média de {media_historica:.1f}) — "
                f"pode indicar tendência de alta."
            )
        else:
            st.success(
                f"✅ O ano de {int(ultimo_ano['Ano'])} está **dentro ou abaixo** da média histórica "
                f"({int(ultimo_ano['Total'])} casos vs. média de {media_historica:.1f})."
            )

    elif grafico_temporal_escolhido == "Evolução por Tipo de Caso":
        evolucao_tipo = df_base.groupby(['Ano', 'Tipo_Caso']).size().reset_index(name='Contagem')
        fig2 = px.line(
            evolucao_tipo, x='Ano', y='Contagem', color='Tipo_Caso',
            title='Evolução por Tipo de Caso', markers=True,
            color_discrete_map=CORES_GRAFICOS
        )
        fig2.update_layout(xaxis_title='Ano', yaxis_title='Número de Casos')
        st.plotly_chart(fig2, use_container_width=True, key=f"fig2_{key_prefix}")

    elif grafico_temporal_escolhido == "Barras Empilhadas + Total":
        evolucao_tipo = df_base.groupby(['Ano', 'Tipo_Caso']).size().reset_index(name='Contagem')
        pivot = evolucao_tipo.pivot(index='Ano', columns='Tipo_Caso', values='Contagem').fillna(0)
        pivot = pivot.sort_index()

        fig3 = go.Figure()
        for tipo in pivot.columns:
            fig3.add_trace(go.Bar(
                x=pivot.index, y=pivot[tipo], name=tipo,
                marker_color=CORES_GRAFICOS.get(tipo, '#2196F3'),
                text=pivot[tipo], textposition='inside', insidetextanchor='middle',
                hovertemplate=f'{tipo}: %{{y}}<extra></extra>'
            ))
        total_por_ano = pivot.sum(axis=1)
        fig3.add_trace(go.Scatter(
            x=total_por_ano.index, y=total_por_ano.values,
            name='Total', mode='lines+markers',
            line=dict(color='#1a73e8', width=3), marker=dict(size=10, color='#1a73e8'),
            text=total_por_ano.values, textposition='top center',
            hovertemplate='Total: %{y}<extra></extra>'
        ))
        fig3.update_layout(
            title='Evolução dos Casos por Tipo (barras) e Total (linha)',
            xaxis_title='Ano', yaxis_title='Número de Casos',
            barmode='stack',
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='center', x=0.5),
            height=450
        )
        st.plotly_chart(fig3, use_container_width=True, key=f"fig3_{key_prefix}")

    elif grafico_temporal_escolhido == "Distribuição por Tipo (Pizza)":
        tipo_counts = df_base['Tipo_Caso'].value_counts()
        fig4 = px.pie(
            values=tipo_counts.values, names=tipo_counts.index,
            title='Distribuição por Tipo de Caso',
            color=tipo_counts.index, color_discrete_map=CORES_GRAFICOS, hole=0.3
        )
        fig4.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig4, use_container_width=True, key=f"fig4_{key_prefix}")

    elif grafico_temporal_escolhido == "Casos por Ano e Gênero":
        if 'Genero' in df_base.columns:
            evolucao_genero = df_base.groupby(['Ano', 'Genero']).size().reset_index(name='Contagem')
            fig5 = px.bar(
                evolucao_genero, x='Ano', y='Contagem', color='Genero',
                title='Casos por Ano e Gênero', barmode='group',
                color_discrete_map={'Feminino': '#E91E63', 'Masculino': '#2196F3', 'Ignorado': '#9E9E9E', 'Não informado': '#9E9E9E'}
            )
            fig5.update_layout(xaxis_title='Ano', yaxis_title='Número de Casos')
            st.plotly_chart(fig5, use_container_width=True, key=f"fig5_{key_prefix}")
        else:
            st.info("Coluna 'Genero' não disponível.")

    elif grafico_temporal_escolhido == "Casos por Gênero e Tipo":
        if 'Genero' in df_base.columns:
            genero_tipo = df_base.groupby(['Genero', 'Tipo_Caso']).size().reset_index(name='Contagem')
            fig6 = px.bar(
                genero_tipo, x='Genero', y='Contagem', color='Tipo_Caso',
                title='Casos por Gênero e Tipo', barmode='stack',
                color_discrete_map=CORES_GRAFICOS
            )
            fig6.update_layout(xaxis_title='Gênero', yaxis_title='Número de Casos')
            st.plotly_chart(fig6, use_container_width=True, key=f"fig6_{key_prefix}")
        else:
            st.info("Coluna 'Genero' não disponível.")

    # ================= ANÁLISE DE CRESCIMENTO E REDUÇÃO =================
    st.divider()
    st.subheader("📊 Análise de Crescimento e Redução")

    opcoes_crescimento = [
        "Heatmap: Casos por Ano e Tipo",
        "Variação por Tipo de Caso (2023 → 2026)",
        "Resumo Rápido",
    ]

    grafico_crescimento_escolhido = st.radio(
        "Selecione a análise",
        opcoes_crescimento,
        horizontal=True,
        key=f"radio_crescimento_{key_prefix}"
    )

    pivot_tipo = df_base.pivot_table(
        index='Ano', columns='Tipo_Caso',
        values='Latitude', aggfunc='count', fill_value=0
    ).sort_index()

    if grafico_crescimento_escolhido == "Heatmap: Casos por Ano e Tipo":
        fig7 = go.Figure(data=go.Heatmap(
            z=pivot_tipo.values,
            x=pivot_tipo.columns,
            y=pivot_tipo.index,
            colorscale='Blues',
            reversescale=True,
            text=pivot_tipo.values,
            texttemplate='%{text}',
            textfont={"size": 12, "color": "black"},
            hovertemplate='Ano: %{y}<br>Tipo: %{x}<br>Casos: %{z}<extra></extra>'
        ))
        fig7.update_layout(
            title='Número de Casos por Ano e Tipo',
            xaxis_title='Tipo de Caso',
            yaxis_title='Ano',
            height=350
        )
        st.plotly_chart(fig7, use_container_width=True, key=f"fig7_{key_prefix}")

    elif grafico_crescimento_escolhido == "Variação por Tipo de Caso (2023 → 2026)":
        st.markdown("### 📈 Variação por Tipo de Caso (2023 → 2026)")
        anos_pivot = pivot_tipo.index
        if len(anos_pivot) >= 2:
            primeiro_ano = anos_pivot[0]
            ultimo_ano = anos_pivot[-1]
            for tipo in pivot_tipo.columns:
                inicial = pivot_tipo.loc[primeiro_ano, tipo]
                final = pivot_tipo.loc[ultimo_ano, tipo]
                if inicial == 0:
                    status = "Sem dados iniciais"
                    cor = "#666"
                    variacao = 0
                else:
                    variacao = ((final - inicial) / inicial) * 100
                    if variacao > 0:
                        status = "AUMENTO"
                        cor = "#E53935"
                    elif variacao < 0:
                        status = "REDUÇÃO"
                        cor = "#43A047"
                    else:
                        status = "ESTÁVEL"
                        cor = "#1565C0"
                st.markdown(
                    f"""
                    <div style="background-color: #f5f5f5; padding: 8px 12px; border-radius: 8px; margin: 6px 0;
                                display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-weight: bold; color: #222;">{tipo}</span>
                        <span style="color: {cor}; font-weight: bold;">
                            {status} {variacao:+.1f}%
                        </span>
                        <span style="color: #555; font-size: 0.9em;">
                            {inicial} → {final} casos
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
        else:
            st.info("Dados insuficientes para análise por tipo.")

    elif grafico_crescimento_escolhido == "Resumo Rápido":
        st.markdown("### 📋 Resumo Rápido")
        tipo_mais_frequente = df_base['Tipo_Caso'].mode()[0]
        ano_com_mais_casos = df_base['Ano'].mode()[0]
        genero_mais_frequente = df_base['Genero'].mode()[0] if 'Genero' in df_base.columns else "Não informado"
        st.markdown(
            f"""
            <div style="background-color: #f5f5f5; padding: 15px; border-radius: 10px; margin: 10px 0; color: #222;">
                <p style="margin: 2px 0;"><b>🦟 Tipo mais comum:</b> {tipo_mais_frequente}</p>
                <p style="margin: 2px 0;"><b>📅 Ano com mais casos:</b> {ano_com_mais_casos}</p>
                <p style="margin: 2px 0;"><b>👤 Gênero mais afetado:</b> {genero_mais_frequente}</p>
            </div>
            """,
            unsafe_allow_html=True
        )



def renderizar_visao_geral(df_base, populacao):
    if df_base.empty:
        st.info("Nenhum caso encontrado com os filtros atuais. Ajuste os filtros na barra lateral.")
        return

    total_casos = len(df_base)
    incidencia = calcular_incidencia(total_casos, populacao)
    tipo_mais_comum = df_base['Tipo_Caso'].mode()[0]
    ano_mais_casos = df_base['Ano'].mode()[0]

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📊 Total de Casos", total_casos)
    with col2:
        st.metric("📈 Incidência (/10.000 hab.)", incidencia if incidencia is not None else "N/D")
    with col3:
        st.metric("🦟 Tipo Mais Comum", tipo_mais_comum)
    with col4:
        st.metric("📅 Ano com Mais Casos", int(ano_mais_casos))

    st.markdown("")

    evolucao_total = df_base.groupby('Ano').size().reset_index(name='Total')
    media_historica = evolucao_total['Total'].mean()
    ultimo_registro = evolucao_total.loc[evolucao_total['Ano'].idxmax()]

    fig = px.bar(
        evolucao_total, x='Ano', y='Total',
        title='Evolução Total de Casos por Ano',
        text='Total', color_discrete_sequence=['#00897B']
    )
    fig.update_traces(textposition='outside')
    fig.add_hline(
        y=media_historica,
        line_dash="dash",
        line_color="#E53935",
        annotation_text=f"Média histórica: {media_historica:.1f}",
        annotation_position="top left"
    )
    fig.update_layout(xaxis_title='Ano', yaxis_title='Número de Casos', showlegend=False, height=380)
    st.plotly_chart(fig, use_container_width=True, key="fig_visao_geral")

    if ultimo_registro['Total'] > media_historica:
        st.warning(
            f"⚠️ **Atenção:** o ano de {int(ultimo_registro['Ano'])} está acima da média histórica "
            f"({int(ultimo_registro['Total'])} casos vs. média de {media_historica:.1f} casos/ano). "
            f"Recomenda-se atenção redobrada na vigilância epidemiológica."
        )
    else:
        st.success(
            f"✅ O ano de {int(ultimo_registro['Ano'])} está dentro ou abaixo da média histórica "
            f"({int(ultimo_registro['Total'])} casos vs. média de {media_historica:.1f} casos/ano)."
        )

    st.caption(
        "💡 A incidência é calculada como (total de casos ÷ população) × 10.000 habitantes. "
        "Ajuste a população em '⚙️ Configurações Avançadas' na barra lateral."
    )