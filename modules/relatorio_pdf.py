"""
Módulo de geração de relatório em PDF. Se a biblioteca fpdf2 não estiver
instalada, FPDF_DISPONIVEL fica False e o botão de exportar PDF é escondido
pelo app principal (sem quebrar o resto do dashboard).
"""
from datetime import datetime

try:
    from fpdf import FPDF
    FPDF_DISPONIVEL = True
except ImportError:
    FPDF_DISPONIVEL = False

from modules.estatisticas import calcular_incidencia


def gerar_pdf_relatorio(df_base, populacao, titulo="Relatório de Casos - Pinheiro/MA"):
    """Gera um PDF simples (texto) com o resumo dos casos filtrados."""
    if not FPDF_DISPONIVEL or df_base.empty:
        return None

    pdf = FPDF()
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, titulo, ln=True, align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 8, f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True, align="C")
    pdf.ln(6)

    total = len(df_base)
    incidencia = calcular_incidencia(total, populacao)
    tipo_mais_comum = df_base['Tipo_Caso'].mode()[0] if not df_base.empty else "N/A"
    ano_mais_casos = df_base['Ano'].mode()[0] if not df_base.empty else "N/A"
    genero_mais_frequente = df_base['Genero'].mode()[0] if 'Genero' in df_base.columns and not df_base.empty else "N/A"

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Resumo Geral", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, f"Total de casos: {total}", ln=True)
    if incidencia is not None:
        pdf.cell(0, 7, f"Incidencia estimada: {incidencia} por 10.000 habitantes (populacao considerada: {populacao})", ln=True)
    pdf.cell(0, 7, f"Tipo de caso mais comum: {tipo_mais_comum}", ln=True)
    pdf.cell(0, 7, f"Ano com mais casos: {ano_mais_casos}", ln=True)
    pdf.cell(0, 7, f"Genero mais afetado: {genero_mais_frequente}", ln=True)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Casos por Ano", ln=True)
    pdf.set_font("Helvetica", "", 11)
    for ano in sorted(df_base['Ano'].unique()):
        c = len(df_base[df_base['Ano'] == ano])
        pdf.cell(0, 7, f"{ano}: {c} casos ({c/total*100:.1f}% do total)", ln=True)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Casos por Tipo", ln=True)
    pdf.set_font("Helvetica", "", 11)
    for tipo in sorted(df_base['Tipo_Caso'].unique()):
        c = len(df_base[df_base['Tipo_Caso'] == tipo])
        pdf.cell(0, 7, f"{tipo}: {c} casos ({c/total*100:.1f}% do total)", ln=True)

    if 'Genero' in df_base.columns:
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 8, "Casos por Genero", ln=True)
        pdf.set_font("Helvetica", "", 11)
        for genero in sorted(df_base['Genero'].unique()):
            c = len(df_base[df_base['Genero'] == genero])
            pdf.cell(0, 7, f"{genero}: {c} casos ({c/total*100:.1f}% do total)", ln=True)

    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 9)
    pdf.multi_cell(0, 5, "Dashboard UBS - Pinheiro/MA | PET-Saude/I&SD - Universidade Federal do Maranhao")

    saida = pdf.output(dest='S')
    return bytes(saida)


