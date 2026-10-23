"""
Aba "Relatório" do Painel de Vigilância Epidemiológica - Pinheiro/MA.

O usuário escolhe QUAIS VARIÁVEIS entram no relatório (Ano, Agravo, Gênero,
Faixa etária, NS1, RT-PCR, Classificação) e, opcionalmente, uma variável para
CRUZAR com todas as outras (ex.: tudo separado por Gênero). O relatório aparece
na tela em tempo real — muda na hora em que o usuário altera as escolhas ou os
filtros da barra lateral — e o mesmo conteúdo pode ser baixado em PDF.

Uso no painel:
    from modules.relatorio_detalhado import renderizar_aba_relatorio
    renderizar_aba_relatorio(df_filtrado, populacao, filtros_texto, municipio, ubs, info_dados)
"""
import io
import os
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.lib.utils import ImageReader  # noqa: E402
from xml.sax.saxutils import escape as _esc  # noqa: E402

from reportlab.platypus import (  # noqa: E402
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from modules.comparacao_mapas import config_comparacao_do_painel, figura_comparacao_anos  # noqa: E402
from modules.creditos import (  # noqa: E402
    DESENVOLVIMENTO,
    EQUIPE,
    ORIENTACAO,
    RODAPE_SISTEMA,
    SOBRE_SISTEMA,
)

# =====================================================================
# CONFIGURAÇÃO DAS VARIÁVEIS DISPONÍVEIS
# =====================================================================
# nome exibido -> coluna interna do painel
VARIAVEIS = {
    "Ano": "Ano",
    "Agravo": "Tipo_Caso",
    "Gênero": "Genero",
    "Faixa etária": "Faixa_Etaria",
    "Resultado NS1": "RNS1",
    "Resultado RT-PCR (dengue)": "RTPCRDE",
    "Classificação final": "Classificacao",
}
PADRAO_VARIAVEIS = ["Ano", "Agravo", "Gênero", "Faixa etária"]
ORDEM_FAIXAS = ["0–9", "10–19", "20–29", "30–39", "40–49", "50–59", "60+", "Não informada"]
ORDEM_EXAMES = ["Positivo", "Negativo", "Inconclusivo", "Não realizado", "Não informado", "Ignorado", "Não se aplica"]

CORES_FIXAS = {
    "Dengue": "#E53935", "Chikungunya": "#FB8C00", "Zika": "#8E24AA",
    "Feminino": "#AD1457", "Masculino": "#1565C0", "Ignorado": "#78909C", "Não informado": "#B0BEC5",
    "Positivo": "#C62828", "Negativo": "#2E7D32", "Inconclusivo": "#F9A825", "Não realizado": "#90A4AE",
    "Descartado": "#78909C",
}
PALETA = ["#1E88E5", "#43A047", "#FB8C00", "#8E24AA", "#E53935", "#00897B", "#6D4C41", "#3949AB", "#C0CA33"]

AZUL = colors.HexColor("#0400EC")
AZUL_CLARO = colors.HexColor("#E8EAFE")
CINZA = colors.HexColor("#5F6368")
CINZA_LINHA = colors.HexColor("#D0D4DC")
LARGURA_UTIL = A4[0] - 4 * cm
TEXTO_MAPAS_CALOR = (
    "Mesmos mapas da comparação entre anos do painel (aba Mapa Geral). Cada mancha mostra onde os casos "
    "se concentraram: tons frios indicam poucos casos por perto e tons quentes, muitos casos próximos uns "
    "dos outros. Todos os anos usam a mesma escala de cores, então dá para comparar um ano com outro. "
    "Os nomes indicam o bairro e o número de casos do ano; quando os nomes se sobrepõem, aparece o do "
    "bairro com mais casos. A linha cinza é o limite do município."
)

# =====================================================================
# IDENTIDADE DO PROJETO (logos e créditos impressos em todo relatório)
# =====================================================================
PASTA_PROJETO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# As mesmas logos, na mesma ordem, da barra lateral do painel
LOGOS = [
    "assets/logo_pet.png",         # PET-Saúde UFMA
    "assets/brasao-normal.png",    # UFMA
    "assets/prefeitura_pho.jpg",   # Prefeitura de Pinheiro
    "assets/lageos.jpeg",          # LAGEOS
]


def _caminho_logo(relativo):
    """Procura a logo ao lado do projeto e, se não achar, na pasta de onde o painel foi aberto."""
    for base in (PASTA_PROJETO, os.getcwd()):
        caminho = os.path.join(base, relativo)
        if os.path.exists(caminho):
            return caminho
    return None


def versao_logos():
    """Muda sempre que uma logo é trocada — usado para o PDF não sair de um cache antigo."""
    datas = []
    for relativo in LOGOS:
        caminho = _caminho_logo(relativo)
        datas.append(os.path.getmtime(caminho) if caminho else 0)
    return tuple(datas)

# Textos de créditos: edite em modules/creditos.py (valem para o PDF e para o painel)


def _logo(relativo, altura):
    """Logo com a proporção original e altura fixa; None se o arquivo não existir."""
    caminho = _caminho_logo(relativo)
    if not caminho:
        return None
    try:
        largura_px, altura_px = ImageReader(caminho).getSize()
        return Image(caminho, width=altura * largura_px / altura_px, height=altura)
    except Exception:
        return None


def _faixa_logos(altura, espaco=10):
    """Uma linha centralizada com todas as logos encontradas; None se nenhuma existir."""
    logos = [lg for lg in (_logo(relativo, altura) for relativo in LOGOS) if lg]
    if not logos:
        return None
    faixa = Table([logos], hAlign="CENTER")
    faixa.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), espaco),
        ("RIGHTPADDING", (0, 0), (-1, -1), espaco),
    ]))
    return faixa


# =====================================================================
# FORMATAÇÃO (padrão brasileiro)
# =====================================================================
def _num(valor, casas=0):
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(parte, total, casas=1):
    return "–" if not total else f"{_num(100 * parte / total, casas)}%"


def _lista_pt(itens):
    itens = [str(i) for i in itens]
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


def _cor(categoria, indice):
    return CORES_FIXAS.get(str(categoria), PALETA[indice % len(PALETA)])


# =====================================================================
# ANÁLISE DE CADA VARIÁVEL (usada na tela E no PDF)
# =====================================================================
def _serie(df, nome_variavel):
    coluna = VARIAVEIS[nome_variavel]
    serie = df[coluna]
    if coluna == "Classificacao":
        serie = serie.fillna("").replace("", "Sem classificação")
    return serie.fillna("Não informado").astype(str) if coluna != "Ano" else serie


def _ordenar(nome_variavel, categorias, contagem=None):
    coluna = VARIAVEIS[nome_variavel]
    if coluna == "Ano":
        return sorted(categorias)
    if coluna == "Faixa_Etaria":
        return [c for c in ORDEM_FAIXAS if c in categorias]
    if coluna in ("RNS1", "RTPCRDE"):
        return [c for c in ORDEM_EXAMES if c in categorias] + [c for c in categorias if c not in ORDEM_EXAMES]
    if contagem is not None:
        return list(contagem.sort_values(ascending=False).index)
    return sorted(categorias)


def analisar_variavel(df, nome_variavel, comparacao=None):
    """
    Devolve um dicionário com:
      tabela  -> DataFrame pronto para exibir (Categoria, Casos, %, e colunas da comparação)
      cruz    -> crosstab categoria x comparação (ou None)
      texto   -> interpretação automática em português (com <b> para negrito)
    """
    total = len(df)
    serie = _serie(df, nome_variavel)
    contagem = serie.value_counts()
    ordem = _ordenar(nome_variavel, list(contagem.index), contagem)
    contagem = contagem.reindex(ordem)

    tabela = pd.DataFrame({
        nome_variavel: [str(c) for c in ordem],
        "Casos": contagem.values.astype(int),
        "%": [_pct(v, total) for v in contagem.values],
    })

    cruz = None
    if comparacao and comparacao != nome_variavel:
        serie_comp = _serie(df, comparacao)
        cruz = pd.crosstab(serie, serie_comp).reindex(ordem).fillna(0).astype(int)
        cruz = cruz[_ordenar(comparacao, list(cruz.columns), cruz.sum())]
        for coluna in cruz.columns:
            tabela[str(coluna)] = cruz[coluna].values

    texto = _texto_variavel(df, nome_variavel, contagem, total, cruz, comparacao)
    return {"titulo": nome_variavel, "tabela": tabela, "contagem": contagem, "cruz": cruz, "texto": texto}


def _texto_variavel(df, nome_variavel, contagem, total, cruz, comparacao):
    coluna = VARIAVEIS[nome_variavel]
    if not total:
        return "Não há casos para os filtros selecionados."
    frases = []

    if coluna == "Ano":
        anos = list(contagem.index)
        pico = contagem.idxmax()
        frases.append(
            f"Entre {anos[0]} e {anos[-1]} foram contabilizados <b>{_num(total)} casos</b>. "
            f"O ano com mais registros foi <b>{pico}</b> ({_num(contagem[pico])} casos)."
        )
        if len(anos) >= 2:
            atual, anterior = contagem[anos[-1]], contagem[anos[-2]]
            if anterior:
                variacao = 100 * (atual - anterior) / anterior
                sentido = "um aumento" if variacao > 0 else "uma redução"
                frases.append(
                    f"Em {anos[-1]} houve {_num(atual)} casos, <b>{sentido} de {_num(abs(variacao), 1)}%</b> "
                    f"em relação a {anos[-2]}."
                )
            media = contagem.iloc[:-1].mean()
            if media:
                razao = atual / media
                if razao >= 1.5:
                    frases.append(
                        f"Esse valor é <b>{_num(razao, 1)} vezes a média</b> dos anos anteriores "
                        f"({_num(media, 1)} casos/ano): <b>situação acima do padrão histórico</b>, que "
                        "recomenda intensificar as ações de vigilância e controle vetorial."
                    )
                elif razao <= 0.5:
                    frases.append(
                        f"Esse valor está bem abaixo da média dos anos anteriores ({_num(media, 1)} casos/ano). "
                        "Convém verificar se reflete redução real ou atraso na digitação das notificações."
                    )
    elif coluna in ("RNS1", "RTPCRDE"):
        pos = int(contagem.get("Positivo", 0))
        neg = int(contagem.get("Negativo", 0))
        inc = int(contagem.get("Inconclusivo", 0))
        realizados = pos + neg + inc
        nao = int(contagem.get("Não realizado", 0))
        if realizados:
            frases.append(
                f"O exame foi realizado em <b>{_num(realizados)} de {_num(total)} casos</b> ({_pct(realizados, total)}). "
                f"Entre os realizados, <b>{_num(pos)} foram positivos</b> (positividade de "
                f"<b>{_pct(pos, realizados)}</b>) e {_num(neg)} negativos."
            )
        else:
            frases.append(f"O exame não consta como realizado em nenhum dos {_num(total)} casos.")
        if nao:
            frases.append(
                f"Em {_num(nao)} casos ({_pct(nao, total)}) o exame não foi realizado; nesses casos a "
                "classificação costuma seguir o critério clínico-epidemiológico."
            )
    else:
        principais = contagem.sort_values(ascending=False)
        top = principais.index[0]
        frase = (f"A categoria mais frequente foi <b>{top}</b>, com {_num(principais.iloc[0])} casos "
                 f"({_pct(principais.iloc[0], total)}).")
        if len(principais) > 1:
            frase += (f" Em seguida vem {principais.index[1]} ({_num(principais.iloc[1])}; "
                      f"{_pct(principais.iloc[1], total)}).")
        frases.append(frase)
        if coluna == "Faixa_Etaria" and "Idade" in df.columns and df["Idade"].notna().any():
            idades = df["Idade"].dropna().astype(float)
            jovens = int(contagem.reindex(["0–9", "10–19"]).fillna(0).sum())
            idosos = int(contagem.get("60+", 0))
            frases.append(
                f"A idade variou de {_num(idades.min())} a {_num(idades.max())} anos (<b>mediana "
                f"{_num(idades.median())} anos</b>). Crianças e adolescentes (0–19) somam {_pct(jovens, total)} "
                f"e pessoas com 60 anos ou mais, {_pct(idosos, total)} — grupos com maior risco de agravamento."
            )
        if coluna == "Classificacao":
            descartados = int(contagem.get("Descartado", 0))
            sem = int(contagem.get("Sem classificação", 0))
            if descartados:
                frases.append(f"{_num(descartados)} notificações ({_pct(descartados, total)}) foram descartadas.")
            if sem:
                frases.append(f"{_num(sem)} ainda estão sem classificação final (em investigação).")

    if cruz is not None and not cruz.empty:
        destaques = []
        for categoria in cruz.sum(axis=1).sort_values(ascending=False).index[:3]:
            linha = cruz.loc[categoria]
            if linha.sum():
                dominante = linha.idxmax()
                destaques.append(f"em <b>{categoria}</b> predominou {dominante} ({_pct(linha.max(), linha.sum())})")
        if destaques:
            frases.append(f"Cruzando com {comparacao.lower()}: " + "; ".join(destaques) + ".")
    return " ".join(frases)


# =====================================================================
# GRÁFICOS (matplotlib — o mesmo gráfico vai para a tela e para o PDF)
# =====================================================================
def _estilizar(ax):
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    ax.spines["left"].set_color("#9AA0A6")
    ax.spines["bottom"].set_color("#9AA0A6")
    ax.tick_params(colors="#3C4043", labelsize=9)
    ax.set_axisbelow(True)


def grafico_variavel(analise):
    contagem, cruz = analise["contagem"], analise["cruz"]
    categorias = [str(c) for c in contagem.index]
    horizontal = max((len(c) for c in categorias), default=0) > 12
    fig, ax = plt.subplots(figsize=(8, max(2.6, 0.45 * len(categorias) + 1) if horizontal else 3.4))

    if cruz is None:
        valores = contagem.values
        cores = [_cor(c, i) for i, c in enumerate(categorias)]
        barras = (ax.barh(categorias, valores, color=cores) if horizontal
                  else ax.bar(categorias, valores, color=cores, width=0.6))
        for barra, valor in zip(barras, valores):
            if horizontal:
                ax.text(barra.get_width(), barra.get_y() + barra.get_height() / 2, f" {_num(valor)}",
                        va="center", fontsize=8.5)
            else:
                ax.text(barra.get_x() + barra.get_width() / 2, barra.get_height(), _num(valor),
                        ha="center", va="bottom", fontsize=8.5, fontweight="bold")
        maximo = max(valores) if len(valores) else 1
    else:
        acumulado = [0] * len(categorias)
        for i, comp in enumerate(cruz.columns):
            valores = cruz[comp].values
            if horizontal:
                ax.barh(categorias, valores, left=acumulado, color=_cor(comp, i), label=str(comp))
            else:
                ax.bar(categorias, valores, bottom=acumulado, color=_cor(comp, i), label=str(comp), width=0.6)
            acumulado = [a + v for a, v in zip(acumulado, valores)]
        for posicao, total in enumerate(acumulado):
            if horizontal:
                ax.text(total, posicao, f" {_num(total)}", va="center", fontsize=8.5)
            else:
                ax.text(posicao, total, _num(total), ha="center", va="bottom", fontsize=8.5, fontweight="bold")
        maximo = max(acumulado) if acumulado else 1
        ax.legend(frameon=False, fontsize=8, ncol=min(4, len(cruz.columns)),
                  loc="lower right" if horizontal else "upper left")

    if horizontal:
        ax.invert_yaxis()
        ax.set_xlim(0, maximo * 1.15 + 1)
        ax.set_xlabel("Casos")
        ax.grid(axis="x", color="#E8EAED")
    else:
        ax.set_ylim(0, maximo * 1.25 + 1)  # folga: rótulos nunca são cortados
        ax.set_ylabel("Casos")
        ax.grid(axis="y", color="#E8EAED")
        if len(categorias) > 6:
            plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    _estilizar(ax)
    fig.tight_layout()
    return fig


# =====================================================================
# RESUMO GERAL
# =====================================================================
def resumo_geral(df, populacao):
    total = len(df)
    anos = sorted(df["Ano"].unique())
    ano_recente = anos[-1]
    casos_recente = int((df["Ano"] == ano_recente).sum())
    incidencia = 10000 * casos_recente / populacao if populacao else 0
    por_agravo = df["Tipo_Caso"].value_counts()
    texto = (
        f"Foram analisados <b>{_num(total)} casos</b> entre {anos[0]} e {anos[-1]}. Por agravo: "
        + _lista_pt([f"<b>{a}</b> {_num(n)} ({_pct(n, total)})" for a, n in por_agravo.items()])
        + f". Em <b>{ano_recente}</b> foram {_num(casos_recente)} casos, uma taxa de "
          f"<b>{_num(incidencia, 1)} por 10.000 habitantes</b> (população de referência: {_num(populacao)})."
    )
    return {"total": total, "ano_recente": ano_recente, "casos_recente": casos_recente,
            "incidencia": incidencia, "n_agravos": len(por_agravo), "texto": texto}


# =====================================================================
# PDF
# =====================================================================
def _estilos():
    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle("titulo", parent=base["Title"], fontSize=18, leading=22, textColor=AZUL),
        "subtitulo": ParagraphStyle("sub", parent=base["Normal"], fontSize=10.5, leading=14,
                                    textColor=CINZA, alignment=TA_CENTER, spaceAfter=12),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontSize=14, leading=18, textColor=AZUL,
                             spaceBefore=10, spaceAfter=6),
        "corpo": ParagraphStyle("corpo", parent=base["Normal"], fontSize=10, leading=14.5,
                                alignment=TA_JUSTIFY, spaceAfter=6),
        "destaque": ParagraphStyle("dest", parent=base["Normal"], fontSize=10, leading=14,
                                   backColor=AZUL_CLARO, borderPadding=8, spaceBefore=4, spaceAfter=10),
        "nota": ParagraphStyle("nota", parent=base["Normal"], fontSize=8.5, leading=11.5, textColor=CINZA),
        "celula": ParagraphStyle("cel", parent=base["Normal"], fontSize=9, leading=11),
        "sobre": ParagraphStyle("sobre", parent=base["Normal"], fontSize=9.5, leading=13, spaceAfter=2),
        "sobre_rodape": ParagraphStyle("sobre_rod", parent=base["Normal"], fontSize=8.5, leading=11,
                                       textColor=CINZA, alignment=TA_CENTER),
    }


def _tabela_pdf(linhas, larguras=None):
    tabela = Table(linhas, colWidths=larguras, hAlign="LEFT", repeatRows=1)
    tabela.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, CINZA_LINHA),
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return tabela


def _imagem(fig, largura=LARGURA_UTIL):
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    imagem = Image(buffer)
    imagem.drawHeight = largura * imagem.imageHeight / imagem.imageWidth
    imagem.drawWidth = largura
    return imagem


# =====================================================================
# CASOS POR BAIRRO E AGRAVO (Dengue e Chikungunya)
# =====================================================================
def analisar_bairros(df):
    """Casos por bairro e agravo, do bairro com mais casos para o com menos."""
    if df is None or df.empty or "Bairro" not in df.columns:
        return None
    from modules.camadas_exames import padronizar_bairros

    bairro = padronizar_bairros(df["Bairro"])
    cruz = pd.crosstab(bairro, df["Tipo_Caso"])
    principais = [a for a in ("Dengue", "Chikungunya", "Zika") if a in cruz.columns]
    cruz = cruz[principais + [c for c in cruz.columns if c not in principais]]
    cruz["Total"] = cruz.sum(axis=1)
    cruz = cruz.sort_values(["Total"] + principais[:1], ascending=False)
    agravos = [c for c in cruz.columns if c != "Total"]

    total = int(cruz["Total"].sum())
    frases = [f"Os <b>{_num(total)} casos</b> estão distribuídos em <b>{len(cruz)} bairros/localidades</b>."]
    if "Dengue" in cruz.columns and cruz["Dengue"].sum():
        dengue = cruz["Dengue"].sort_values(ascending=False)
        top = [(b, int(v)) for b, v in dengue.head(3).items() if v]
        frases.append("Dengue concentrou-se em " + _lista_pt(
            [f"<b>{b}</b> ({_num(v)}; {_pct(v, dengue.sum())})" for b, v in top]) + ".")
    if "Chikungunya" in cruz.columns and cruz["Chikungunya"].sum():
        chik = cruz["Chikungunya"][cruz["Chikungunya"] > 0].sort_values(ascending=False)
        frases.append(f"Chikungunya teve <b>{_num(chik.sum())} caso(s)</b>, em " + _lista_pt(
            [f"<b>{b}</b> ({_num(v)})" for b, v in chik.items()]) + ".")
    if "Zona Rural" in cruz.index:
        frases.append(f"\"Zona Rural\" reúne vários povoados ({_num(cruz.at['Zona Rural', 'Total'])} casos).")

    tabela = cruz.reset_index().rename(columns={"index": "Bairro", cruz.index.name or "Bairro": "Bairro"})
    tabela.columns = ["Bairro"] + list(tabela.columns[1:])
    return {"cruz": cruz, "agravos": agravos, "tabela": tabela, "texto": " ".join(frases)}


def grafico_bairros(analise):
    """Barras horizontais lado a lado por bairro (uma cor por agravo, as mesmas do painel)."""
    cruz, agravos = analise["cruz"], analise["agravos"]
    bairros = list(cruz.index)
    n = len(bairros)
    altura_barra = 0.8 / max(len(agravos), 1)
    fig, ax = plt.subplots(figsize=(8, min(10.5, max(3.0, 0.34 * n + 1.2))))
    posicoes = range(n)
    for i, agravo in enumerate(agravos):
        valores = cruz[agravo].values
        ys = [p - 0.4 + altura_barra * (i + 0.5) for p in posicoes]
        barras = ax.barh(ys, valores, height=altura_barra, color=_cor(agravo, i), label=agravo)
        for barra, valor in zip(barras, valores):
            if valor:
                ax.text(barra.get_width(), barra.get_y() + barra.get_height() / 2, f" {_num(valor)}",
                        va="center", fontsize=7)
    ax.set_yticks(list(posicoes))
    ax.set_yticklabels(bairros, fontsize=8)
    ax.invert_yaxis()
    maximo = max(int(cruz[agravos].values.max()), 1) if agravos else 1
    ax.set_xlim(0, maximo * 1.15 + 1)
    ax.set_xlabel("Casos")
    ax.grid(axis="x", color="#E8EAED")
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    _estilizar(ax)
    fig.tight_layout()
    return fig


TEXTO_BAIRROS = (
    "Bairro informado na ficha de notificação. \"Zona Rural\" reúne vários povoados; "
    "\"(bairro não informado)\" são fichas sem o bairro preenchido."
)


def gerar_pdf(df, populacao, filtros_texto, variaveis, comparacao, incluir_mapa,
              municipio_gdf=None, ubs_gdf=None, info_dados=None, anos_mapa=None, config_mapa=None,
              incluir_bairros=True):
    info_dados = info_dados or {}
    e = _estilos()
    agora = datetime.now()
    buffer = io.BytesIO()

    def rodape(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(CINZA)
        canvas.drawString(2 * cm, 1.2 * cm, "Painel de Vigilância Epidemiológica – Pinheiro/MA · "
                                            f"gerado em {agora:%d/%m/%Y às %H:%M}")
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Página {doc.page}")
        canvas.setStrokeColor(AZUL)
        canvas.setLineWidth(2)
        canvas.line(2 * cm, A4[1] - 1.3 * cm, A4[0] - 2 * cm, A4[1] - 1.3 * cm)
        canvas.restoreState()

    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm,
                            title="Relatório Epidemiológico – Pinheiro/MA", author="PET-Saúde/I&SD – UFMA")
    # Cabeçalho: faixa com as logos da barra lateral, e o título logo abaixo
    h = []
    faixa = _faixa_logos(2.0 * cm)
    if faixa:
        h += [faixa, Spacer(1, 8)]
    h += [
        Paragraph("Relatório Epidemiológico de Arboviroses", e["titulo"]),
        Paragraph(f"Dengue, Chikungunya e Zika – Pinheiro/MA<br/>Projeto PET-Saúde/I&amp;SD – UFMA · "
                  f"Gerado em {agora:%d/%m/%Y às %H:%M}", e["subtitulo"]),
    ]
    linhas = [["Configuração do relatório", "Seleção"]]
    linhas += [[k, Paragraph(str(v), e["celula"])] for k, v in filtros_texto.items()]
    linhas.append(["Variáveis analisadas", Paragraph(", ".join(variaveis) or "–", e["celula"])])
    linhas.append(["Cruzamento", comparacao or "Nenhum"])
    h += [_tabela_pdf(linhas, [5.5 * cm, LARGURA_UTIL - 5.5 * cm]), Spacer(1, 8)]

    if df is None or df.empty:
        h.append(Paragraph("Não há casos para os filtros selecionados.", e["corpo"]))
        h += _bloco_sobre_sistema(e)
        doc.build(h, onFirstPage=rodape, onLaterPages=rodape)
        return buffer.getvalue()

    resumo = resumo_geral(df, populacao)
    h.append(Paragraph("Resumo", e["h1"]))
    h.append(Paragraph(resumo["texto"], e["destaque"]))

    for numero, nome in enumerate(variaveis, start=1):
        analise = analisar_variavel(df, nome, comparacao)
        cab = list(analise["tabela"].columns)
        corpo = analise["tabela"].astype(str).values.tolist()
        bloco = [
            Paragraph(f"{numero}. {nome}" + (f" × {comparacao}" if comparacao and comparacao != nome else ""), e["h1"]),
            _imagem(grafico_variavel(analise)),
            Paragraph(analise["texto"], e["corpo"]),
            _tabela_pdf([cab] + corpo),
            Spacer(1, 6),
        ]
        h.append(KeepTogether(bloco))

    proxima = len(variaveis) + 1
    analise_b = analisar_bairros(df) if incluir_bairros else None
    if analise_b is not None:
        h.append(PageBreak())
        h.append(Paragraph(f"{proxima}. Casos por bairro (Dengue e Chikungunya)", e["h1"]))
        h.append(_imagem(grafico_bairros(analise_b)))
        h.append(Paragraph(analise_b["texto"], e["corpo"]))
        h.append(_tabela_pdf([list(analise_b["tabela"].columns)] + analise_b["tabela"].astype(str).values.tolist()))
        h.append(Paragraph(TEXTO_BAIRROS, e["nota"]))
        proxima += 1

    if incluir_mapa:
        h.append(PageBreak())
        h.append(Paragraph(f"{proxima}. Mapas de calor por ano", e["h1"]))
        fig_mapas = (figura_comparacao_anos(df, municipio_gdf, ubs_gdf, anos=anos_mapa,
                                            config={**(config_mapa or {}), "mostrar_ubs": False})
                     if anos_mapa is None or len(anos_mapa) else None)
        if fig_mapas is not None:
            h.append(_imagem(fig_mapas))
            h.append(Paragraph(TEXTO_MAPAS_CALOR, e["nota"]))
        else:
            h.append(Paragraph("Não há casos com coordenadas para os anos escolhidos.", e["corpo"]))

    h.append(Paragraph("Nota metodológica", e["h1"]))
    for frase in (
        f"<b>Fonte:</b> {info_dados.get('fonte', 'planilha de notificações da Vigilância Epidemiológica')}.",
        "<b>Ano:</b> aba da planilha em que a notificação foi registrada. <b>Confirmado:</b> classificação "
        "final preenchida e diferente de “Descartado”; sem classificação = em investigação.",
        f"<b>Exclusões:</b> {_num(info_dados.get('n_sem_coordenada', 0))} notificação(ões) sem latitude/longitude e "
        f"{_num(info_dados.get('n_duplicatas', 0))} digitada(s) em duplicidade (mesma ficha, idade e agravo).",
        "<b>Limitações:</b> os números dependem da completude da planilha; notificações recentes podem ainda não "
        "ter classificação final, e a digitação tardia pode subestimar o ano corrente.",
    ):
        h.append(Paragraph(frase, e["corpo"]))

    h += _bloco_sobre_sistema(e)
    doc.build(h, onFirstPage=rodape, onLaterPages=rodape)
    return buffer.getvalue()


def _bloco_sobre_sistema(e):
    """Créditos do sistema e da equipe, com as logos — impresso no fim de todo relatório."""
    itens = [Spacer(1, 10), Paragraph("Sobre o sistema", e["h1"])]
    for rotulo, valor in SOBRE_SISTEMA:
        itens.append(Paragraph(f"<b>{_esc(rotulo)}:</b> {_esc(valor)}", e["sobre"]))

    itens.append(Paragraph("<b>Equipe:</b>", e["sobre"]))
    metade = (len(EQUIPE) + 1) // 2
    coluna_1 = [Paragraph(f"• {_esc(nome)}", e["sobre"]) for nome in EQUIPE[:metade]]
    coluna_2 = [Paragraph(f"• {_esc(nome)}", e["sobre"]) for nome in EQUIPE[metade:]]
    coluna_2 += [""] * (len(coluna_1) - len(coluna_2))
    equipe = Table(list(zip(coluna_1, coluna_2)), colWidths=[LARGURA_UTIL / 2] * 2, hAlign="LEFT")
    equipe.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    itens.append(equipe)
    itens.append(Spacer(1, 4))
    itens.append(Paragraph(f"<b>Desenvolvimento:</b> {_esc(DESENVOLVIMENTO)}", e["sobre"]))
    itens.append(Paragraph(f"<b>Orientação:</b> {_esc(ORIENTACAO)}", e["sobre"]))

    fechamento = [Paragraph(_esc(RODAPE_SISTEMA), e["sobre_rodape"])]
    faixa = _faixa_logos(1.5 * cm)
    if faixa:
        fechamento = [Spacer(1, 10), faixa, Spacer(1, 6)] + fechamento
    itens += fechamento
    return [KeepTogether(itens)]


# =====================================================================
# ABA NO STREAMLIT
# =====================================================================
def renderizar_aba_relatorio(df, populacao, filtros_texto, municipio_gdf=None, ubs_gdf=None,
                             info_dados=None, key_prefix="relatorio"):
    import streamlit as st

    # 'versao' muda quando este arquivo ou alguma logo é alterado: assim o painel
    # nunca entrega um PDF antigo guardado em cache depois de uma atualização.
    @st.cache_data(show_spinner=False, max_entries=8)
    def _pdf_em_cache(_df, assinatura_df, populacao, filtros_itens, variaveis, comparacao, incluir_mapa,
                      _municipio, _ubs, _info, versao, anos_mapa=None, config_mapa_itens=(),
                      incluir_bairros=True):
        return gerar_pdf(_df, populacao, dict(filtros_itens), list(variaveis), comparacao, incluir_mapa,
                         _municipio, _ubs, _info, anos_mapa=list(anos_mapa),
                         config_mapa=dict(config_mapa_itens), incluir_bairros=incluir_bairros)

    st.header("📑 Relatório personalizado")
    st.caption("Escolha as variáveis. O relatório abaixo se atualiza na hora, junto com os filtros da barra "
               "lateral, e pode ser baixado em PDF.")

    if df is None or df.empty:
        st.warning("Não há casos com os filtros atuais. Ajuste os filtros na barra lateral.")
        return

    disponiveis = [nome for nome, coluna in VARIAVEIS.items() if coluna in df.columns]
    col_a, col_b, col_c = st.columns([3, 2, 1])
    variaveis = col_a.multiselect(
        "Variáveis do relatório", disponiveis,
        default=[v for v in PADRAO_VARIAVEIS if v in disponiveis], key=f"{key_prefix}_variaveis",
    )
    comparacao = col_b.selectbox(
        "Cruzar todas com…", ["Nenhuma"] + disponiveis, key=f"{key_prefix}_comparacao",
        help="Separa cada variável pelas categorias desta (ex.: cada gráfico dividido por Gênero).",
    )
    comparacao = None if comparacao == "Nenhuma" else comparacao
    incluir_bairros = col_c.checkbox("Incluir casos por bairro", True, key=f"{key_prefix}_bairros")
    incluir_mapa = col_c.checkbox("Incluir mapas de calor", True, key=f"{key_prefix}_mapa")

    # ---------- resumo
    resumo = resumo_geral(df, populacao)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Casos analisados", _num(resumo["total"]))
    c2.metric(f"Casos em {resumo['ano_recente']}", _num(resumo["casos_recente"]))
    c3.metric("Incidência /10 mil hab.", _num(resumo["incidencia"], 1))
    c4.metric("Agravos", resumo["n_agravos"])
    st.markdown(resumo["texto"].replace("<b>", "**").replace("</b>", "**"))

    # ---------- uma seção por variável
    for numero, nome in enumerate(variaveis, start=1):
        analise = analisar_variavel(df, nome, comparacao)
        titulo = f"{numero}. {nome}" + (f" × {comparacao}" if comparacao and comparacao != nome else "")
        st.subheader(titulo)
        col_grafico, col_tabela = st.columns([3, 2])
        with col_grafico:
            fig = grafico_variavel(analise)
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
        with col_tabela:
            st.dataframe(analise["tabela"], hide_index=True, use_container_width=True)
        st.markdown(analise["texto"].replace("<b>", "**").replace("</b>", "**"))
        st.divider()

    proxima = len(variaveis) + 1
    analise_b = analisar_bairros(df) if incluir_bairros else None
    if analise_b is not None:
        st.subheader(f"{proxima}. Casos por bairro (Dengue e Chikungunya)")
        col_grafico, col_tabela = st.columns([3, 2])
        with col_grafico:
            fig = grafico_bairros(analise_b)
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
        with col_tabela:
            st.dataframe(analise_b["tabela"], hide_index=True, use_container_width=True)
        st.markdown(analise_b["texto"].replace("<b>", "**").replace("</b>", "**"))
        st.caption(TEXTO_BAIRROS)
        st.divider()
        proxima += 1

    if incluir_mapa:
        st.subheader(f"{proxima}. Mapas de calor por ano")
        anos_disponiveis = [int(a) for a in sorted(df.dropna(subset=["Latitude", "Longitude"])["Ano"].unique())]
        anos_mapa = st.multiselect(
            "Anos nos mapas", anos_disponiveis, default=anos_disponiveis, key=f"{key_prefix}_anos_mapa",
            help="Escolha os anos para comparar. A escala de cores é a mesma do painel e vale para todos os anos.",
        )
        # mesma aparência escolhida na comparação entre anos da aba Mapa Geral
        config_mapa = config_comparacao_do_painel(st.session_state)
        config_mapa["mostrar_ubs"] = False  # no relatório os mapas saem sem as UBS (no painel continuam)
        fig = figura_comparacao_anos(df, municipio_gdf, ubs_gdf, anos=anos_mapa, config=config_mapa) if anos_mapa else None
        if fig is not None:
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
            st.caption(TEXTO_MAPAS_CALOR)
        else:
            st.info("Escolha pelo menos um ano com casos para ver os mapas.")

    if not incluir_mapa:
        anos_mapa, config_mapa = [], {}

    # ---------- PDF com exatamente o que está na tela
    assinatura_df = str(pd.util.hash_pandas_object(df, index=False).sum())
    with st.spinner("Preparando o PDF..."):
        pdf = _pdf_em_cache(df, assinatura_df, populacao, tuple(sorted(filtros_texto.items())),
                            tuple(variaveis), comparacao, incluir_mapa, municipio_gdf, ubs_gdf, info_dados,
                            versao=(os.path.getmtime(os.path.abspath(__file__)),
                                    os.path.getmtime(os.path.join(os.path.dirname(os.path.abspath(__file__)), "creditos.py")),
                                    versao_logos(),
                                    os.path.getmtime(os.path.join(os.path.dirname(os.path.abspath(__file__)), "comparacao_mapas.py"))),
                            anos_mapa=tuple(anos_mapa) if incluir_mapa else (),
                            config_mapa_itens=tuple(sorted(config_mapa.items())) if incluir_mapa else (),
                            incluir_bairros=incluir_bairros)
    st.download_button(
        "📥 Baixar este relatório em PDF", data=pdf,
        file_name=f"relatorio_pinheiro_{datetime.now():%Y%m%d_%H%M}.pdf",
        mime="application/pdf", key=f"{key_prefix}_baixar", type="primary",
    )


# =====================================================================
# "SOBRE O SISTEMA" NA TELA (mesmos textos do PDF — edite só lá em cima)
# =====================================================================
def renderizar_sobre_sistema():
    """
    Nota de rodapé da Visão Geral: informações do sistema, equipe e logos,
    em texto pequeno e discreto (mesmos textos do relatório em PDF).
    """
    import html

    import streamlit as st

    def t(texto):
        return html.escape(texto.replace("&amp;", "&"))

    linhas = "".join(f"<b>{t(rotulo)}:</b> {t(valor)}<br>" for rotulo, valor in SOBRE_SISTEMA)
    equipe = "".join(f"• {t(nome)}<br>" for nome in EQUIPE)

    st.divider()
    caminhos = [c for c in (_caminho_logo(relativo) for relativo in LOGOS) if c]
    if caminhos:
        _, *colunas, _ = st.columns([3] + [1] * len(caminhos) + [3])
        for coluna, caminho in zip(colunas, caminhos):
            coluna.image(caminho, width=56)

    st.markdown(
        f"""
        <div style="font-size:0.78rem; line-height:1.45; opacity:0.75; margin-top:6px;">
          {linhas}
          <b>Equipe:</b>
          <div style="column-count:2; column-gap:32px; margin:2px 0 6px 0;">{equipe}</div>
          <b>Desenvolvimento:</b> {t(DESENVOLVIMENTO)}<br>
          <b>Orientação:</b> {t(ORIENTACAO)}
          <div style="text-align:center; margin-top:10px; opacity:0.85;">{t(RODAPE_SISTEMA)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
