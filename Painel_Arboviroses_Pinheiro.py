"""
Painel de Arboviroses de Pinheiro/MA — VERSÃO PÚBLICA (por bairro)

Cópia do Passo8_PET_DASH_MARK5.py (versão da Vigilância) adaptada para consulta
pela população, sem ferir a LGPD:
  - NÃO lê latitude/longitude das notificações. Cada caso é colocado no ponto de
    referência do seu BAIRRO (assets/bairros_pinheiro.csv, editável).
  - O mapa mostra bolhas por bairro com o nome e o total de casos; o mapa de calor
    também é calculado por bairro.
  - Não há tabela nem CSV caso a caso: só contagens agregadas por bairro, ano e agravo.
  - Não mostra o link da planilha.
  - Zona Rural e notificações sem bairro não aparecem no mapa, mas entram em todas
    as contagens e gráficos.
  - A classificação final (confirmado/descartado) vem da coluna revisada à direita de
    CLASSIF (coluna Y, "CLASSIF (Josiedna e Adilson)").
  - Mapa próprio do RT-PCR de dengue positivo (coluna RTPCRDE), por bairro.
"""
import html
import json
import math
import os
import re
import sys
from datetime import datetime

# Garante que a pasta "modules" (ao lado deste arquivo) seja encontrada,
# não importa de qual pasta o "streamlit run" for executado.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import folium
import geopandas as gpd
import pandas as pd
import streamlit as st
from folium.plugins import HeatMap, MarkerCluster
from streamlit_folium import st_folium

# ---------------------------------------------------------------------
# Compatibilidade com folium 0.19+: o folium passou a converter os nomes das
# opções com .split(), e quebra ("'float' object has no attribute 'split'")
# quando um gradiente de mapa de calor usa números como chave, ex.:
# gradient={0.2: "#FFF9C4", 1.0: "#B71C1C"}. Este ajuste converte a chave para
# texto antes, e vale para TODOS os arquivos do painel (inclusive modules/).
# ---------------------------------------------------------------------
try:
    import folium.template as _folium_template

    if not getattr(_folium_template, "_camelize_compativel", False):
        _camelize_original = _folium_template.camelize
        _folium_template.camelize = lambda chave: _camelize_original(str(chave))
        _folium_template._camelize_compativel = True
except (ImportError, AttributeError):
    pass  # versões antigas do folium não têm esse problema


from modules.config import CORES_CASOS_MAPA, POPULACAO_PADRAO
from modules.dados import encontrar_campo_nome, load_geodata
from modules.comparacao_mapas import DESLOCAMENTO_REFERENCIA_GRAUS, calcular_pico, renderizar_comparacao_anos
from modules.graficos import renderizar_estatisticas_e_graficos, renderizar_visao_geral
from modules.exportacao import renderizar_exportacao_rodape, renderizar_tabela_ubs
from modules.relatorio_detalhado import renderizar_aba_relatorio
from modules.bairros import (
    adicionar_bolhas_bairros, adicionar_nomes_bairros, atribuir_coordenadas_bairro, carregar_referencia_bairros, renderizar_mapa_rtpcr,
    tabela_casos_por_bairro, texto_nao_mapeados,
)
from modules.camadas_exames import (
    CATEGORIAS_EXAME, adicionar_camadas_exame, adicionar_legenda_camadas, mascara_categoria,
    renderizar_bairros_prioritarios,
)
from modules.creditos import DESENVOLVIMENTO, EQUIPE, ORIENTACAO, RODAPE_SISTEMA, SOBRE_SISTEMA

# ================= FONTE DE DADOS =================
# ONLINE (deploy): Planilha Google da Vigilância, PRIVADA, lida por uma conta
# de serviço. O ID da planilha e a credencial ficam em .streamlit/secrets.toml
# (no computador) ou em "Secrets" do Streamlit Cloud — NUNCA no GitHub.
#
# LOCAL (desenvolvimento): se os secrets não existirem, o painel lê o Excel
# abaixo, que também não deve ir para o GitHub (está no .gitignore).
CAMINHO_EXCEL_PADRAO = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "assets", "Notificacoes_Dengue_Chikungunya_Pinheiro.xlsx"
)

# De quanto em quanto tempo (segundos) o painel busca de novo a planilha online.
INTERVALO_ATUALIZACAO = 60

# Faixa plausível de coordenadas para Pinheiro/MA e arredores.
LAT_MIN, LAT_MAX = -4.0, -1.0
LON_MIN, LON_MAX = -47.0, -43.0

# Colunas mostradas na tabela e no CSV exportado (interno -> exibido).
# Textos do rodapé (Sistema, Equipe, Desenvolvimento, Orientação): edite em modules/creditos.py

COLUNAS_EXIBICAO = {
    "Tipo_Caso": "Casos",
    "Ano": "Ano",
    "Genero": "Gênero",
    "RNS1": "RNS1",
    "RTPCRDE": "RTPCRDE",
    "Idade": "Idade",
}

# ================= CONFIGURAÇÃO =================
st.set_page_config(
    page_title="Painel de Vigilância Epidemiológica - Pinheiro/MA",
    layout="wide",
    page_icon="🏥",
)


# =====================================================================
# FUNÇÕES DE PADRONIZAÇÃO DOS DADOS
# =====================================================================
def _corrigir_coordenada(valor, digitos_inteiros):
    """
    Converte a coordenada para número. Se ela perdeu o separador decimal
    (ex.: '-2.531.708', '-253.685', '-450.854'), reconstrói o valor sabendo
    que a latitude de Pinheiro tem 1 dígito antes da vírgula (-2,xxx) e a
    longitude tem 2 (-45,xxx).
    """
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None

    limites = (LAT_MIN, LAT_MAX) if digitos_inteiros == 1 else (LON_MIN, LON_MAX)

    # 1) Valor já correto (número ou texto com um único separador decimal)
    try:
        numero = float(str(valor).strip().replace(",", "."))
        if limites[0] <= numero <= limites[1]:
            return numero
    except ValueError:
        pass

    # 2) Reconstrução a partir dos dígitos
    digitos = re.sub(r"\D", "", str(valor))
    if len(digitos) <= digitos_inteiros:
        return None
    return -float(digitos[:digitos_inteiros] + "." + digitos[digitos_inteiros:])


def _padronizar_resultado_exame(valor):
    """Uniformiza resultados de exame (corrige acentos perdidos e espaços)."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return "Não informado"
    texto = str(valor).strip().lower()
    if not texto:
        return "Não informado"
    if texto.startswith("pos") or texto.startswith("reag"):
        return "Positivo"
    if texto.startswith("neg") or ("reag" in texto and texto.startswith("n")):
        return "Negativo"
    if "realiz" in texto:
        return "Não realizado"
    if "inconcl" in texto:
        return "Inconclusivo"
    if "ign" in texto:
        return "Ignorado"
    return str(valor).strip().capitalize()


def _padronizar_genero(valor):
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return "Não informado"
    texto = str(valor).strip().lower()
    if texto in ("m", "masc", "masculino"):
        return "Masculino"
    if texto in ("f", "fem", "feminino"):
        return "Feminino"
    if texto in ("i", "ign", "ignorado"):
        return "Ignorado"
    return str(valor).strip().title() or "Não informado"


def _faixa_etaria(idade):
    if pd.isna(idade):
        return "Não informada"
    idade = int(idade)
    if idade < 10:
        return "0–9"
    if idade >= 60:
        return "60+"
    inicio = (idade // 10) * 10
    return f"{inicio}–{inicio + 9}"


ORDEM_FAIXAS = ["0–9", "10–19", "20–29", "30–39", "40–49", "50–59", "60+", "Não informada"]

APELIDOS_COLUNAS = {
    # Versão pública: LAT/LONG da planilha NÃO são lidas (o ponto vem do bairro).
    "agravo": "Tipo_Caso", "casos": "Tipo_Caso", "caso": "Tipo_Caso", "tipo_caso": "Tipo_Caso",
    "sexo": "Genero", "genero": "Genero", "gênero": "Genero",
    "idade": "Idade",
    "classif": "Classificacao", "classificacao": "Classificacao", "classificação": "Classificacao",
    "rns1": "RNS1",
    "rtpcrde": "RTPCRDE",
    "ano": "Ano",
    "data": "Data",
    "bairro": "Bairro",
}


def padronizar_df_casos(df):
    """
    Recebe os dados como vierem (planilha antiga, planilha nova ou CSV de
    notificações) e devolve sempre no formato que o dashboard usa.
    Retorna (df_padronizado, n_descartados_sem_dados).
    """
    if df is None or df.empty:
        return pd.DataFrame(), 0

    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    df = df.loc[:, [c for c in df.columns if c and not c.startswith("Unnamed")]]

    # Renomeia apelidos para os nomes internos (sem sobrescrever colunas já existentes)
    renomear = {}
    for coluna in df.columns:
        alvo = APELIDOS_COLUNAS.get(coluna.lower())
        if alvo and alvo != coluna and alvo not in df.columns and alvo not in renomear.values():
            renomear[coluna] = alvo
    df = df.rename(columns=renomear)

    # Remove espaços sobrando em todos os textos ("Dengue " -> "Dengue")
    for coluna in df.columns:
        if df[coluna].dtype == object:
            df[coluna] = df[coluna].astype(str).str.strip().replace({"": None, "nan": None, "None": None})

    # Coordenadas
    if "Latitude" in df.columns:
        df["Latitude"] = df["Latitude"].apply(lambda v: _corrigir_coordenada(v, 1)).astype(float)
    if "Longitude" in df.columns:
        df["Longitude"] = df["Longitude"].apply(lambda v: _corrigir_coordenada(v, 2)).astype(float)

    # Ano (direto ou a partir da data da notificação; por último, o nome da aba)
    if "Ano" in df.columns:
        df["Ano"] = pd.to_numeric(df["Ano"], errors="coerce")
    elif "Data" in df.columns:
        # Extrai só o ano do texto da data, sem converter para data completa
        # (assim um erro de digitação como 2422 não derruba a leitura).
        texto_data = df["Data"].astype(str).str.strip()
        ano_iso = texto_data.str.extract(r"^(\d{4})-\d{2}-\d{2}")[0]          # 2023-02-10
        ano_br4 = texto_data.str.extract(r"^\d{1,2}/\d{1,2}/(\d{4})$")[0]     # 10/02/2023
        ano_br2 = texto_data.str.extract(r"^\d{1,2}/\d{1,2}/(\d{2})$")[0]     # 10/02/23
        ano = pd.to_numeric(ano_iso.fillna(ano_br4), errors="coerce")
        ano = ano.fillna(pd.to_numeric(ano_br2, errors="coerce") + 2000)
        ano_atual = datetime.now().year
        df["Ano"] = ano.where(ano.between(2000, ano_atual + 1))  # ano impossível -> usa o da aba
    if "Ano_Aba" in df.columns:
        # A aba (2023, 2024, ...) é a fonte oficial do ano: a Vigilância organiza
        # as notificações por aba. A data só é usada se a aba não tiver ano.
        ano_aba = pd.to_numeric(df["Ano_Aba"], errors="coerce")
        df["Ano"] = ano_aba.fillna(df["Ano"]) if "Ano" in df.columns else ano_aba

    # Tipo de caso, gênero, idade e exames
    if "Tipo_Caso" in df.columns:
        df["Tipo_Caso"] = df["Tipo_Caso"].astype(str).str.strip().str.title()
    if "Genero" in df.columns:
        df["Genero"] = df["Genero"].apply(_padronizar_genero)
    if "Idade" in df.columns:
        df["Idade"] = pd.to_numeric(df["Idade"], errors="coerce").astype("Int64")
        df["Faixa_Etaria"] = df["Idade"].apply(_faixa_etaria)
    for exame in ("RNS1", "RTPCRDE"):
        if exame in df.columns:
            df[exame] = df[exame].apply(_padronizar_resultado_exame)

    # Linhas sem ano ou sem tipo de caso não têm como entrar nos filtros
    obrigatorias = [c for c in ("Ano", "Tipo_Caso") if c in df.columns]
    n_antes = len(df)
    df = df.dropna(subset=obrigatorias)
    n_descartados = n_antes - len(df)
    if "Ano" in df.columns:
        df["Ano"] = df["Ano"].astype(int)

    # Mantém SOMENTE as colunas do dashboard. Endereço, bairro, nº da ficha,
    # escolaridade etc. são descartados aqui e não chegam ao mapa nem às exportações.
    # O bairro é mantido só para o ranking de bairros prioritários (contagem agregada).
    manter = [c for c in list(COLUNAS_EXIBICAO) + ["Faixa_Etaria", "Classificacao", "Bairro"] if c in df.columns]
    df = df[manter]

    return df.reset_index(drop=True), n_descartados


def _eh_aba_de_ano(nome):
    return re.fullmatch(r"\s*\d{4}\s*", str(nome)) is not None


def usar_classificacao_revisada(dados):
    """Versão pública: a classificação final vem da coluna logo à DIREITA de CLASSIF
    (coluna Y, hoje "CLASSIF (Josiedna e Adilson)"), revisada pela equipe. A coluna é
    encontrada pela posição, então continua funcionando se o título for trocado.
    Se a aba não tiver essa coluna, vale a CLASSIF original."""
    colunas = list(dados.columns)
    posicoes = [i for i, c in enumerate(colunas) if str(c).strip().upper() == "CLASSIF"]
    if not posicoes or posicoes[0] + 1 >= len(colunas):
        return dados
    original, revisada = colunas[posicoes[0]], colunas[posicoes[0] + 1]
    if not str(revisada).strip() or str(revisada).strip().upper() in ("EVOLUÇÃO", "EVOLUCAO"):
        return dados  # aba ainda sem a coluna revisada
    return dados.drop(columns=[original]).rename(columns={revisada: "CLASSIF"})


def juntar_abas_notificacoes(abas):
    """
    Recebe {nome_da_aba: DataFrame} (uma aba por ano), remove notificações
    digitadas duas vezes na mesma aba (mesma ficha e mesma idade, fica a última)
    e devolve (df, n_duplicatas) SÓ com as colunas que o painel usa.
    Endereço, bairro, nº da ficha etc. são descartados aqui, antes de qualquer
    coisa ser guardada em cache.
    """
    partes, n_duplicatas = [], 0
    for nome_aba, dados in abas.items():
        if not _eh_aba_de_ano(nome_aba) or dados.empty:
            continue
        dados = dados.copy()
        dados.columns = [str(c).strip() for c in dados.columns]
        dados = usar_classificacao_revisada(dados)

        if "NFICHA" in dados.columns and "IDADE" in dados.columns:
            # Mesma ficha + mesma idade + MESMO agravo = digitada duas vezes.
            # (A mesma pessoa notificada para Dengue e Chikungunya são 2 notificações.)
            chave = dados["NFICHA"].astype(str).str.strip()
            idade = dados["IDADE"].astype(str).str.strip()
            agravo = dados["AGRAVO"].astype(str).str.strip().str.lower() if "AGRAVO" in dados.columns else ""
            tem_ficha = ~chave.isin(["", "nan", "None"])
            repetida = pd.concat(
                [chave.str.zfill(7), idade, pd.Series(agravo, index=dados.index)], axis=1
            ).duplicated(keep="last") & tem_ficha
            n_duplicatas += int(repetida.sum())
            dados = dados[~repetida]

        # Padroniza os nomes ANTES de juntar as abas (ex.: 2026 usa LONG, as outras LOG)
        renomear = {}
        for coluna in dados.columns:
            alvo = APELIDOS_COLUNAS.get(coluna.lower())
            if alvo and alvo not in renomear.values():
                renomear[coluna] = alvo
        dados = dados[list(renomear)].rename(columns=renomear)
        dados["Ano_Aba"] = str(nome_aba).strip()
        partes.append(dados)

    if not partes:
        return pd.DataFrame(), 0
    return pd.concat(partes, ignore_index=True), n_duplicatas


@st.cache_data(ttl=INTERVALO_ATUALIZACAO, show_spinner=False)
def carregar_planilha_vigilancia(planilha_id):
    """
    Lê a Planilha Google PRIVADA da Vigilância (todas as abas com nome de ano)
    usando a conta de serviço configurada nos secrets.
    Retorna (df, mensagem_erro, n_duplicatas, horario_leitura).
    """
    agora = datetime.now()
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        return pd.DataFrame(), "Faltam as bibliotecas gspread e google-auth (veja o requirements.txt).", 0, agora

    try:
        credenciais = Credentials.from_service_account_info(
            ler_chave_conta_servico(),
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        planilha = gspread.authorize(credenciais).open_by_key(planilha_id)
        titulos = [aba.title for aba in planilha.worksheets() if _eh_aba_de_ano(aba.title)]
        if not titulos:
            return pd.DataFrame(), "Nenhuma aba com nome de ano (ex.: 2023) foi encontrada na planilha.", 0, agora

        # Uma única chamada para todas as abas. Números vêm crus (sem a vírgula
        # do formato brasileiro) e datas vêm como texto (dd/mm/aaaa).
        resposta = planilha.values_batch_get(
            [f"'{titulo}'" for titulo in titulos],
            params={"valueRenderOption": "UNFORMATTED_VALUE", "dateTimeRenderOption": "FORMATTED_STRING"},
        )
    except Exception as erro:
        texto = str(erro)
        try:
            email = ler_chave_conta_servico().get("client_email", "e-mail da conta de serviço")
        except Exception:
            email = "e-mail da conta de serviço"
        if "403" in texto or "PERMISSION_DENIED" in texto or "SpreadsheetNotFound" in type(erro).__name__ or "404" in texto:
            return pd.DataFrame(), (
                f"Sem acesso à planilha. Compartilhe a planilha com **{email}** como **Leitor** "
                "e confira o ID em secrets."
            ), 0, agora
        return pd.DataFrame(), f"Erro ao ler a planilha online: {texto[:300]}", 0, agora

    abas = {}
    for titulo, faixa in zip(titulos, resposta.get("valueRanges", [])):
        linhas = faixa.get("values", [])
        if len(linhas) < 2:
            continue
        cabecalho = [str(c).strip() or f"_vazia_{i}" for i, c in enumerate(linhas[0])]
        n = len(cabecalho)
        corpo = [[str(v) for v in (linha + [""] * n)[:n]] for linha in linhas[1:] if any(str(v).strip() for v in linha)]
        abas[titulo] = pd.DataFrame(corpo, columns=cabecalho)

    df, n_duplicatas = juntar_abas_notificacoes(abas)
    return df, None, n_duplicatas, agora


@st.cache_data(show_spinner=False)
def carregar_excel_notificacoes(caminho, data_modificacao=None):
    """
    Modo local: lê o Excel de notificações (uma aba por ano).
    'data_modificacao' faz o cache ser refeito sempre que o arquivo é salvo.
    Retorna (df, mensagem_erro, n_duplicatas).
    """
    try:
        abas = pd.read_excel(caminho, sheet_name=None, dtype=str)
    except FileNotFoundError:
        return pd.DataFrame(), f"Arquivo não encontrado: {caminho}", 0
    except Exception as erro:
        return pd.DataFrame(), f"Não foi possível abrir o Excel: {erro}", 0

    df, n_duplicatas = juntar_abas_notificacoes(abas)
    if df.empty:
        return df, "Nenhuma aba com nome de ano (ex.: 2023) foi encontrada no Excel.", 0
    return df, None, n_duplicatas


def ler_chave_conta_servico():
    """
    Lê a chave da conta de serviço dos secrets. Aceita dois formatos:
      - gcp_service_account_json = '''{ ...conteúdo inteiro do .json colado... }'''
      - [gcp_service_account] com um campo por linha
    """
    if "gcp_service_account_json" in st.secrets:
        return json.loads(st.secrets["gcp_service_account_json"])
    return dict(st.secrets["gcp_service_account"])


def ler_secrets_planilha():
    """Devolve o ID da planilha online se os secrets estiverem configurados, senão None."""
    try:
        tem_chave = "gcp_service_account_json" in st.secrets or "gcp_service_account" in st.secrets
        if tem_chave and "planilha" in st.secrets:
            return str(st.secrets["planilha"]["id"]).strip() or None
    except Exception:
        pass  # sem arquivo de secrets -> modo local
    return None


def marcar_casos_dentro_do_municipio(df, municipio_gdf):
    """Adiciona a coluna Dentro_Municipio (True/False) usando o limite oficial."""
    df = df.copy()
    df["Dentro_Municipio"] = True
    if df.empty or "Latitude" not in df.columns or "Longitude" not in df.columns:
        return df
    try:
        limite = municipio_gdf.to_crs(epsg=4326) if municipio_gdf.crs else municipio_gdf
        poligono = limite.geometry.union_all() if hasattr(limite.geometry, "union_all") else limite.geometry.unary_union
        com_coord = df["Latitude"].notna() & df["Longitude"].notna()
        pontos = gpd.GeoSeries(
            gpd.points_from_xy(df.loc[com_coord, "Longitude"], df.loc[com_coord, "Latitude"]),
            index=df.index[com_coord],
            crs="EPSG:4326",
        )
        df.loc[com_coord, "Dentro_Municipio"] = pontos.within(poligono).values
        df.loc[~com_coord, "Dentro_Municipio"] = False
    except Exception:
        pass  # se der qualquer problema geográfico, não bloqueia o painel
    return df


def filtro_checkboxes(titulo, opcoes, prefixo):
    """
    Expander com 'Marcar/Desmarcar todos' + um checkbox por opção.
    Toda opção que aparece pela primeira vez na sessão entra MARCADA — quem abre
    o painel encontra tudo selecionado, e categorias novas (ex.: 'Ignorado' ao
    trocar para 'Todas as notificações') também já chegam marcadas. Depois disso,
    o painel respeita o que o usuário desmarcar.
    """
    vistas = st.session_state.setdefault(f"_{prefixo}_opcoes_vistas", set())
    for opcao in opcoes:
        if opcao not in vistas:
            st.session_state[f"{prefixo}_{opcao}"] = True
            vistas.add(opcao)

    with st.expander(titulo, expanded=True):
        col_a, col_b = st.columns(2)
        if col_a.button("Marcar todos", key=f"btn_marcar_{prefixo}", use_container_width=True):
            for opcao in opcoes:
                st.session_state[f"{prefixo}_{opcao}"] = True
        if col_b.button("Desmarcar todos", key=f"btn_desmarcar_{prefixo}", use_container_width=True):
            for opcao in opcoes:
                st.session_state[f"{prefixo}_{opcao}"] = False
        for opcao in opcoes:
            st.checkbox(str(opcao), key=f"{prefixo}_{opcao}")

    return [opcao for opcao in opcoes if st.session_state[f"{prefixo}_{opcao}"]]


def aplicar_filtros(df, filtros):
    """Aplica todos os filtros da barra lateral. Usado no mapa e na tabela."""
    if df.empty:
        return df

    resultado = df[df["Ano"].isin(filtros["anos"]) & df["Tipo_Caso"].isin(filtros["tipos"])]

    if "Genero" in resultado.columns:
        resultado = resultado[resultado["Genero"].isin(filtros["generos"])]

    if filtros.get("idade") and "Idade" in resultado.columns:
        idade_min, idade_max, idade_total_min, idade_total_max = filtros["idade"]
        if (idade_min, idade_max) != (idade_total_min, idade_total_max):
            resultado = resultado[resultado["Idade"].notna() & resultado["Idade"].between(idade_min, idade_max)]

    for exame in ("RNS1", "RTPCRDE"):
        if filtros.get(exame) is not None and exame in resultado.columns:
            resultado = resultado[resultado[exame].isin(filtros[exame])]

    if not filtros.get("incluir_fora", True) and "Dentro_Municipio" in resultado.columns:
        resultado = resultado[resultado["Dentro_Municipio"]]

    return resultado


ALTURA_MAPA = 620  # pixels

# =====================================================================
# POPULAÇÃO OFICIAL (API do IBGE)
# =====================================================================
CODIGO_IBGE_PINHEIRO = "2108603"
LINK_IBGE_CIDADES = "https://cidades.ibge.gov.br/brasil/ma/pinheiro/panorama"
_URL_AGREGADOS_IBGE = "https://servicodados.ibge.gov.br/api/v3/agregados/{tabela}/periodos/-1/variaveis/{variavel}?localidades=N6[{codigo}]"
# (tabela, variável, descrição) em ordem de preferência
_FONTES_POPULACAO_IBGE = [
    ("6579", "9324", "IBGE, estimativa"),        # População residente estimada
    ("4709", "93", "IBGE, Censo"),               # Censo Demográfico 2022
]


def _extrair_valor_ibge(resposta_json):
    """Lê a resposta da API de agregados do IBGE e devolve (valor, ano) do período mais recente."""
    for variavel in resposta_json:
        for resultado in variavel.get("resultados", []):
            for serie in resultado.get("series", []):
                valores = {
                    ano: valor for ano, valor in serie.get("serie", {}).items()
                    if str(valor).strip().isdigit()
                }
                if valores:
                    ano = max(valores)
                    return int(valores[ano]), ano
    return None, None


@st.cache_data(ttl=24 * 60 * 60, show_spinner=False)
def buscar_populacao_ibge(codigo=CODIGO_IBGE_PINHEIRO):
    """
    População oficial de Pinheiro/MA direto da API do IBGE (guardada por 24 h).
    Tenta a estimativa mais recente; se não houver, o Censo 2022. Sem internet,
    usa POPULACAO_PADRAO do config.py e avisa.
    Retorna (populacao, descricao_da_fonte, veio_do_ibge).
    """
    import urllib.request

    for tabela, variavel, descricao in _FONTES_POPULACAO_IBGE:
        url = _URL_AGREGADOS_IBGE.format(tabela=tabela, variavel=variavel, codigo=codigo)
        try:
            with urllib.request.urlopen(url, timeout=8) as resposta:
                valor, ano = _extrair_valor_ibge(json.loads(resposta.read().decode("utf-8")))
            if valor:
                return valor, f"{descricao} {ano}", True
        except Exception:
            continue
    return POPULACAO_PADRAO, "valor de referência do config.py (IBGE indisponível no momento)", False




def zoom_para_enquadrar(bounds, largura_px=900, altura_px=ALTURA_MAPA, margem=0.85):
    """
    Calcula o maior nível de zoom em que o retângulo 'bounds'
    (minx, miny, maxx, maxy, em graus) cabe inteiro no mapa.
    A largura é estimada para baixo para caber também em telas menores.
    """
    minx, miny, maxx, maxy = [float(v) for v in bounds]
    largura_graus = max(maxx - minx, 1e-6)
    altura_graus = max(maxy - miny, 1e-6)
    zoom_x = math.log2(largura_px * margem * 360 / (largura_graus * 256))
    zoom_y = math.log2(altura_px * margem * 360 / (altura_graus * 256))
    return int(max(3, min(16, math.floor(min(zoom_x, zoom_y)))))


def carregar_imagem(caminho, fallback_emoji="🖼️", width=110):
    if os.path.exists(caminho):
        try:
            st.image(caminho, width=width)
            return
        except Exception:
            pass
    st.markdown(f"<div style='text-align: center; font-size: 2.5em;'>{fallback_emoji}</div>", unsafe_allow_html=True)


# =====================================================================
# DADOS GEOGRÁFICOS
# =====================================================================
with st.spinner("🗺️ Carregando dados geográficos..."):
    municipio, ubs = load_geodata()

if municipio is None or ubs is None:
    st.error("""
    ❌ **Dados geográficos não carregados!**

    Verifique se os arquivos estão na pasta `assets/`:
    - assets/pinheiro.json
    - assets/ubs_pinheiro.json

    E se os nomes estão exatamente como acima (case-sensitive).
    """)
    st.stop()


# =====================================================================
# BARRA LATERAL
# =====================================================================
with st.sidebar:
    col1, col2, col3, col4 = st.columns(4)
    # Mesma ordem das logos do relatório em PDF (LOGOS em modules/relatorio_detalhado.py)
    with col1:
        carregar_imagem("assets/logo_pet.png", "🐾")         # PET-Saúde UFMA
    with col2:
        carregar_imagem("assets/brasao-normal.png", "🏛️")    # UFMA
    with col3:
        carregar_imagem("assets/prefeitura_pho.jpg", "🏢")   # Prefeitura de Pinheiro
    with col4:
        carregar_imagem("assets/lageos.jpeg", "🗺️")          # LAGEOS

    st.markdown("### 🏥 Projeto de Informação e Saúde Digital")
    st.markdown("PET-Saúde/I&SD – Universidade Federal do Maranhão")
    st.divider()

    # ---------------- FONTE DE DADOS ----------------
    st.subheader("📥 Fonte de Dados")

    planilha_id = ler_secrets_planilha()

    if planilha_id:
        # ---------- MODO ONLINE: planilha privada da Vigilância ----------
        if st.button("🔄 Atualizar agora", use_container_width=True):
            carregar_planilha_vigilancia.clear()

        with st.spinner("🦟 Lendo a planilha da Vigilância..."):
            df_bruto, erro_online, n_duplicatas, lido_em = carregar_planilha_vigilancia(planilha_id)

        if erro_online:
            st.error(f"❌ {erro_online}")
        else:
            st.success(f"✅ {len(df_bruto)} notificações · lidas às {lido_em.strftime('%H:%M:%S')}")
            st.caption(f"🔁 O painel busca a planilha de novo a cada {INTERVALO_ATUALIZACAO} segundos.")
            if n_duplicatas:
                st.caption(f"♻️ {n_duplicatas} notificação(ões) digitada(s) em duplicidade foram desconsideradas.")
    else:
        # ---------- MODO LOCAL: Excel no computador (desenvolvimento) ----------
        st.info("💻 Modo local: lendo o Excel da pasta `assets/` (planilha online não configurada).")
        caminho_excel = CAMINHO_EXCEL_PADRAO
        if not os.path.exists(caminho_excel):
            # Usa o Excel mais recente da pasta assets, qualquer que seja o nome
            pasta_assets = os.path.dirname(CAMINHO_EXCEL_PADRAO)
            excels = [
                os.path.join(pasta_assets, nome) for nome in os.listdir(pasta_assets)
                if nome.lower().endswith(".xlsx") and not nome.startswith("~$")
            ] if os.path.isdir(pasta_assets) else []
            if excels:
                caminho_excel = max(excels, key=os.path.getmtime)
        st.caption(f"📗 Arquivo: `{os.path.basename(caminho_excel)}`")
        data_modificacao = os.path.getmtime(caminho_excel) if os.path.exists(caminho_excel) else None
        with st.spinner("🦟 Lendo a planilha Excel..."):
            df_bruto, erro_excel, n_duplicatas = carregar_excel_notificacoes(caminho_excel, data_modificacao)
        if erro_excel:
            st.error(f"❌ {erro_excel}")
        else:
            hora = datetime.fromtimestamp(data_modificacao).strftime("%d/%m/%Y %H:%M")
            st.success(f"✅ {len(df_bruto)} notificações · arquivo salvo em {hora}")
            if n_duplicatas:
                st.caption(f"♻️ {n_duplicatas} notificação(ões) digitada(s) em duplicidade foram desconsideradas.")

    # ---------------- PADRONIZAÇÃO ----------------
    df_casos, n_sem_dados = padronizar_df_casos(df_bruto)
    # Cada caso vai para o ponto de referência do seu bairro (nunca o endereço)
    df_casos, resumo_bairros = atribuir_coordenadas_bairro(df_casos, carregar_referencia_bairros())
    if n_sem_dados:
        st.caption(f"⚠️ {n_sem_dados} registro(s) ignorado(s) por falta de ano ou tipo de caso.")

    faltando = [c for c in ("Bairro", "Tipo_Caso", "Ano") if c not in df_casos.columns]
    if not df_casos.empty and faltando:
        st.error(f"❌ Colunas obrigatórias não encontradas na planilha: {', '.join(faltando)}")
        df_casos = pd.DataFrame()

    # Ranking de bairros: usa todas as notificações, mesmo sem coordenada (o bairro vem da ficha)
    df_notificacoes_bairro = df_casos.copy()

    # Versão pública: TODAS as notificações entram nas contagens. Só as que não têm
    # ponto de bairro (Zona Rural, sem bairro) ficam fora do mapa.
    n_sem_coordenada = 0
    if not df_casos.empty:
        fora_do_mapa = texto_nao_mapeados(resumo_bairros)
        if fora_do_mapa:
            st.caption(f"📍 Fora do mapa (entram nas contagens): {fora_do_mapa}.")
    df_casos["Dentro_Municipio"] = True  # os pontos de bairro ficam todos em Pinheiro
    # Camadas por exame: todas as notificações com coordenada, antes do filtro de confirmados
    df_notificacoes = df_casos.copy()

    # ---------------- CONFIRMADOS x NOTIFICAÇÕES ----------------
    modo_classificacao = "📋 Todas as notificações"
    if not df_casos.empty and "Classificacao" in df_casos.columns and df_casos["Classificacao"].notna().any():
        classif = df_casos["Classificacao"].fillna("").str.strip().str.lower()
        descartado = classif == "descartado"
        sem_classificacao = classif == ""
        confirmado = ~descartado & ~sem_classificacao

        modo_classificacao = st.radio(
            "Quais casos contar?",
            ["✅ Somente confirmados", "📋 Todas as notificações"],
            index=0,
            help="Confirmado = CLASSIF preenchida e diferente de 'Descartado'. "
                 "Notificações com CLASSIF vazia (em investigação) só entram em 'Todas'.",
        )
        st.caption(
            f"{int(confirmado.sum())} confirmadas · {int(descartado.sum())} descartadas · "
            f"{int(sem_classificacao.sum())} sem classificação"
        )
        if modo_classificacao == "✅ Somente confirmados":
            df_casos = df_casos[confirmado].reset_index(drop=True)

    st.divider()

    # ---------------- POPULAÇÃO (oficial, direto do IBGE — não editável) ----------------
    populacao_municipio, fonte_populacao, ibge_ok = buscar_populacao_ibge()
    if ibge_ok:
        st.caption(
            f"👥 População de Pinheiro/MA: **{populacao_municipio:,.0f}".replace(",", ".")
            + f" hab.** · {fonte_populacao} · [IBGE Cidades]({LINK_IBGE_CIDADES})"
        )
    else:
        st.caption(
            f"👥 População: **{populacao_municipio:,.0f}".replace(",", ".")
            + f" hab.** · {fonte_populacao}"
        )

    st.divider()

    # ---------------- FILTROS ----------------
    filtros = {"anos": [], "tipos": [], "generos": [], "idade": None,
               "RNS1": None, "RTPCRDE": None, "incluir_fora": True}

    if not df_casos.empty:
        st.subheader("🔍 Filtros de Casos")

        filtros["anos"] = filtro_checkboxes("📅 Ano", sorted(df_casos["Ano"].unique()), "chk_ano")
        filtros["tipos"] = filtro_checkboxes("🦟 Tipo de Caso", sorted(df_casos["Tipo_Caso"].unique()), "chk_tipo")

        if "Genero" in df_casos.columns:
            filtros["generos"] = filtro_checkboxes("👤 Gênero", sorted(df_casos["Genero"].unique()), "chk_genero")

        if "Idade" in df_casos.columns and df_casos["Idade"].notna().any():
            idade_total_min = int(df_casos["Idade"].min())
            idade_total_max = int(df_casos["Idade"].max())
            with st.expander("🎂 Idade", expanded=False):
                if idade_total_min < idade_total_max:
                    idade_min, idade_max = st.slider(
                        "Faixa de idade (anos)", idade_total_min, idade_total_max,
                        (idade_total_min, idade_total_max),
                    )
                else:
                    idade_min = idade_max = idade_total_min
                st.caption("Com a faixa completa, casos sem idade informada também são incluídos.")
            filtros["idade"] = (idade_min, idade_max, idade_total_min, idade_total_max)

        exames_presentes = [e for e in ("RNS1", "RTPCRDE") if e in df_casos.columns]
        if exames_presentes:
            with st.expander("🧪 Exames", expanded=False):
                rotulos = {"RNS1": "Resultado NS1", "RTPCRDE": "Resultado RT-PCR (Dengue)"}
                for exame in exames_presentes:
                    opcoes = sorted(df_casos[exame].unique())
                    filtros[exame] = st.multiselect(rotulos[exame], opcoes, default=opcoes, key=f"ms_{exame}")

        n_fora = int((~df_casos["Dentro_Municipio"]).sum())
        if n_fora:
            filtros["incluir_fora"] = st.checkbox(
                f"Incluir {n_fora} caso(s) fora do limite municipal",
                True,
                help="Casos com coordenada fora de Pinheiro: residentes de outro município ou "
                     "coordenada digitada errada. Vale conferir as fichas.",
            )

        st.markdown("")
        mostrar_casos = st.checkbox("Mostrar casos no mapa", True)

        mostrar_nomes_bairros = st.checkbox("🏷️ Mostrar nomes dos bairros", True, key="nomes_bairros")

        st.markdown("**Visualização dos casos**")
        tipo_visualizacao = st.radio(
            "Como exibir os casos no mapa",
            ["📍 Bolhas por bairro", "🔥 Mapa de Calor (Rápido)", "📍🔥 Bolhas por bairro + Mapa de Calor"],
            index=0,
            label_visibility="collapsed",
        )

        agravo_calor, ano_calor = None, None
        raio_calor, raio_adaptativo = 20, True
        if "🔥" in tipo_visualizacao:
            # O mapa de calor mostra UM agravo por vez (nunca tudo misturado)
            agravos_disponiveis = list(filtros["tipos"])
            if agravos_disponiveis:
                agravo_calor = st.radio(
                    "🔥 Agravo no mapa de calor",
                    agravos_disponiveis,
                    index=agravos_disponiveis.index("Dengue") if "Dengue" in agravos_disponiveis else 0,
                    key="agravo_calor",
                    help="O calor mostra a concentração de um agravo de cada vez.",
                )
            else:
                st.caption("Marque ao menos um tipo de caso para ver o mapa de calor.")

            raio_calor = st.slider("Raio do mapa de calor", 10, 40, 20)
            raio_adaptativo = st.checkbox(
                "📐 Raio adaptável ao zoom", True,
                help="Ajusta o raio do calor ao zoom inicial do mapa.",
            )

            # Versão pública: cada ano marcado em "📅 Ano" vira uma camada do mapa
            # (liga/desliga no botão de camadas), então não há seletor de um ano por vez.

        # ---------------- MAPA DE CALOR DO RT-PCR ----------------
        camada_rtpcr = st.checkbox(
            "🧪 Mapa de calor: RT-PCR dengue positivo", False, key="camada_rtpcr",
            help="Coluna RTPCRDE. Entram todas as notificações com RT-PCR positivo, mesmo sem "
                 "classificação final, nos anos marcados acima.",
        )
        camadas_exame = [next(iter(CATEGORIAS_EXAME))] if camada_rtpcr else []
        if camada_rtpcr:
            st.caption("Desmarque **Mostrar casos no mapa** para ver só o calor do RT-PCR.")
    else:
        camadas_exame = []
        mostrar_nomes_bairros = True
        mostrar_casos = False
        tipo_visualizacao = "📍 Bolhas por bairro"
        agravo_calor, ano_calor = None, None
        raio_calor, raio_adaptativo = 20, True

    df_casos_filtrado = aplicar_filtros(df_casos, filtros)

    # Resumo dos filtros e da origem dos dados (usado no relatório em PDF)
    def _descrever(selecionados, todos):
        if not todos:
            return "–"
        return "Todos" if len(selecionados) == len(todos) else (", ".join(str(s) for s in selecionados) or "Nenhum")

    filtros_texto = {}
    if not df_casos.empty:
        filtros_texto["Casos contados"] = (
            "Somente confirmados" if modo_classificacao == "✅ Somente confirmados" else "Todas as notificações"
        )
        filtros_texto["Anos"] = _descrever(filtros["anos"], sorted(df_casos["Ano"].unique()))
        filtros_texto["Agravos"] = _descrever(filtros["tipos"], sorted(df_casos["Tipo_Caso"].unique()))
        if "Genero" in df_casos.columns:
            filtros_texto["Gênero"] = _descrever(filtros["generos"], sorted(df_casos["Genero"].unique()))
        if filtros.get("idade"):
            idade_min, idade_max, idade_total_min, idade_total_max = filtros["idade"]
            filtros_texto["Idade"] = (
                "Todas" if (idade_min, idade_max) == (idade_total_min, idade_total_max)
                else f"{idade_min} a {idade_max} anos"
            )
        for exame, rotulo in (("RNS1", "Resultado NS1"), ("RTPCRDE", "Resultado RT-PCR")):
            if filtros.get(exame) is not None:
                filtros_texto[rotulo] = _descrever(filtros[exame], sorted(df_casos[exame].unique()))
        filtros_texto["Casos fora do município"] = "Incluídos" if filtros.get("incluir_fora", True) else "Excluídos"

    info_dados = {
        "fonte": (
            "Google Planilha de notificações da Vigilância Epidemiológica de Pinheiro/MA"
            if planilha_id else "planilha Excel de notificações da Vigilância Epidemiológica de Pinheiro/MA"
        ),
        "n_duplicatas": n_duplicatas,
        "n_sem_coordenada": n_sem_coordenada,
        "modo": filtros_texto.get("Casos contados", "casos").lower(),
    }

    st.divider()

    # ---------------- MAPA BASE E ZOOM ----------------
    tile = st.radio("Mapa base", ["OpenStreetMap", "Satélite"], index=0)
    show_limites = st.checkbox("Mostrar limites municipais", True)
    cluster = st.checkbox("Agrupar UBS", True)

    enquadrar_municipio = st.checkbox(
        "🗺️ Mostrar o município inteiro", False,
        help="Desmarcado, o mapa abre na área urbana, onde ficam os bairros.",
    )
    if enquadrar_municipio:
        zoom = 10  # usado só no raio adaptável do mapa de calor
    else:
        zoom = st.slider("🔍 Nível de zoom", 10, 17, 14)


# =====================================================================
# CAMPO NOME DAS UBS
# =====================================================================
campo_nome = encontrar_campo_nome(ubs)
if campo_nome == "ID":
    ubs["ID"] = [f"UBS {i + 1}" for i in range(len(ubs))]


# =====================================================================
# CABEÇALHO
# =====================================================================
st.markdown("""
<div style="background: linear-gradient(90deg, #0400EC 0%, #2B3FE0 50%, #0400EC 100%);
            padding: 26px 32px; border-radius: 14px 14px 0 0; margin-bottom: 0;">
    <h1 style="color:white; margin:0; font-size:30px;">🏥 Painel de Vigilância Epidemiológica</h1>
    <p style="color:#E3E8FF; margin:6px 0 0 0; font-size:15px;">
        Casos de Dengue, Chikungunya e Zika por bairro — Pinheiro/MA · consulta pública
    </p>
</div>
<div style="display:flex; height:9px; border-radius:0 0 14px 14px; overflow:hidden; margin-bottom:10px;">
    <div style="flex:1; background-color:#F03D1F;"></div>
    <div style="flex:1; background-color:#0400EC;"></div>
    <div style="flex:1; background-color:#3CD032;"></div>
    <div style="flex:1; background-color:#FFCF00;"></div>
</div>
""", unsafe_allow_html=True)

st.caption(
    f"📅 Sessão iniciada em {datetime.now().strftime('%d/%m/%Y às %H:%M')} · "
    "Fonte dos dados: notificações da Vigilância Epidemiológica de Pinheiro/MA · PET-Saúde/I&SD"
)
st.markdown("")

aba_visao_geral, aba_mapa, aba_filtros, aba_relatorio = st.tabs(
    ["📊 Visão Geral", "🗺️ Mapa Geral", "🦟 Casos por Bairro", "📑 Relatório"]
)


# =====================================================================
# ABA 0: VISÃO GERAL
# =====================================================================
with aba_visao_geral:
    st.header("📊 Visão Geral dos Casos")
    st.caption("Resumo com base nos filtros selecionados na barra lateral.")
    renderizar_visao_geral(df_casos_filtrado, populacao_municipio)

    if not df_casos_filtrado.empty:
        st.divider()
        st.subheader("👥 Perfil dos casos")
        col_idade, col_exames = st.columns(2)

        with col_idade:
            if "Faixa_Etaria" in df_casos_filtrado.columns:
                st.markdown("**Casos por faixa etária**")
                if "Genero" in df_casos_filtrado.columns:
                    tabela_idade = pd.crosstab(df_casos_filtrado["Faixa_Etaria"], df_casos_filtrado["Genero"])
                else:
                    tabela_idade = df_casos_filtrado["Faixa_Etaria"].value_counts().to_frame("Casos")
                tabela_idade = tabela_idade.reindex([f for f in ORDEM_FAIXAS if f in tabela_idade.index])
                # Cores fixas por gênero (Feminino rosa, Masculino azul)
                cores_genero = {
                    "Feminino": "#FFABAB",
                    "Masculino": "#83C9FF",
                    "Ignorado": "#0068C9",
                    "Não informado": "#9E9E9E",
                    "Casos": "#83C9FF",
                }
                st.bar_chart(
                    tabela_idade,
                    color=[cores_genero.get(str(coluna), "#9E9E9E") for coluna in tabela_idade.columns],
                )
            else:
                st.info("Coluna de idade não encontrada nos dados.")

        with col_exames:
            exames = [e for e in ("RNS1", "RTPCRDE") if e in df_casos_filtrado.columns]
            if exames:
                st.markdown("**Resultado dos exames**")
                tabela_exames = pd.DataFrame({
                    {"RNS1": "NS1", "RTPCRDE": "RT-PCR"}[e]: df_casos_filtrado[e].value_counts()
                    for e in exames
                }).fillna(0).astype(int)
                st.bar_chart(tabela_exames)
            else:
                st.info("Colunas de exames (RNS1, RTPCRDE) não encontradas nos dados.")

    # ================= RODAPÉ: informações do sistema e da equipe =================
    st.divider()
    _linhas_sistema = "".join(
        f"<b>{html.escape(rotulo)}:</b> {html.escape(valor)}<br>" for rotulo, valor in SOBRE_SISTEMA
    )
    _linhas_equipe = "".join(f"• {html.escape(nome)}<br>" for nome in EQUIPE)
    st.markdown(
        f"""
        <div style="font-size:0.8rem; line-height:1.5; opacity:0.8;">
          {_linhas_sistema}<br>
          <b>Equipe:</b>
          <div style="column-count:2; column-gap:40px; margin:4px 0 8px 0;">{_linhas_equipe}</div>
          <b>Desenvolvimento:</b> {html.escape(DESENVOLVIMENTO)}<br>
          <b>Orientação:</b> {html.escape(ORIENTACAO)}
          <div style="text-align:center; margin-top:12px;"><small>{html.escape(RODAPE_SISTEMA)}</small></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =====================================================================
# ABA 1: MAPA GERAL
# =====================================================================
with aba_mapa:
    limite_wgs84 = municipio.to_crs(epsg=4326) if municipio.crs else municipio
    bounds = limite_wgs84.total_bounds  # (minx, miny, maxx, maxy) em graus
    centro = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]  # [lat, lon]

    # O st_folium não respeita o fit_bounds do folium, então o zoom que
    # enquadra o município inteiro é calculado aqui e passado diretamente.
    if enquadrar_municipio:
        zoom = zoom_para_enquadrar(bounds, altura_px=ALTURA_MAPA)
    else:
        # Versão pública: abre na área urbana (centro dos pontos de bairro)
        _ref = carregar_referencia_bairros()
        if not _ref.empty:
            centro = [float(_ref["Latitude"].median()), float(_ref["Longitude"].median())]

    m = folium.Map(
        location=centro,
        zoom_start=zoom,
        tiles="OpenStreetMap",
        attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        control_scale=True,
    )

    if tile == "Satélite":
        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Tiles &copy; Esri",
            name="Satélite",
            overlay=False,
            control=True,
        ).add_to(m)

    if show_limites and not municipio.empty:
        folium.GeoJson(
            municipio,
            style_function=lambda x: {"color": "#2E7D32", "weight": 2, "fillOpacity": 0.15, "fillColor": "#2E7D32"},
            name="Limite Municipal",
            tooltip="Município de Pinheiro/MA",
        ).add_to(m)

    # ---------------- CASOS ----------------
    aviso_calor = None
    pico_calor = 1
    if mostrar_casos and not df_casos_filtrado.empty:
        mostrar_marcadores = "📍" in tipo_visualizacao
        mostrar_mapa_calor = "🔥" in tipo_visualizacao

        gradiente_calor = {
            "Dengue": {"0.2": "#FFF9C4", "0.4": "#FFEE58", "0.6": "#FFA726", "0.8": "#EF5350", "1.0": "#B71C1C"},
            "Chikungunya": {"0.2": "#FFF3E0", "0.4": "#FFCC80", "0.6": "#FFA726", "0.8": "#FB8C00", "1.0": "#E65100"},
            "Zika": {"0.2": "#F3E5F5", "0.4": "#CE93D8", "0.6": "#AB47BC", "0.8": "#8E24AA", "1.0": "#4A148C"},
        }

        if raio_adaptativo:
            raio_calor_efetivo = max(8, min(60, int(raio_calor * (13 / max(zoom, 1)))))
        else:
            raio_calor_efetivo = raio_calor
        blur_calor = raio_calor_efetivo // 2 if raio_calor_efetivo > 2 else 1

        # Com o mapa de calor ligado, o mapa inteiro (calor E marcadores) mostra só o
        # agravo escolhido na barra lateral — e só o ano escolhido, se houver.
        df_mapa = df_casos_filtrado
        if mostrar_mapa_calor and agravo_calor:
            df_mapa = df_mapa[df_mapa["Tipo_Caso"] == agravo_calor]
            if ano_calor is not None:
                df_mapa = df_mapa[df_mapa["Ano"] == ano_calor]

        # Marcadores: UMA bolha por bairro (tamanho = nº de casos), com o nome do bairro.
        # Os anos marcados na barra lateral viram camadas no botão de camadas do mapa
        # (uma por ano, todas ligadas), para ligar/desligar cada ano ali também.
        anos_no_mapa = sorted(int(a) for a in df_mapa["Ano"].dropna().unique())
        if mostrar_marcadores and anos_no_mapa:
            com_ponto = df_mapa.dropna(subset=["Latitude", "Longitude"])
            maximo_bolha = int(com_ponto.groupby(["Ano", "Bairro"]).size().max()) if not com_ponto.empty else None
            for ano in anos_no_mapa:
                adicionar_bolhas_bairros(
                    m, df_mapa[df_mapa["Ano"] == ano], CORES_CASOS_MAPA, mostrar_nomes=mostrar_nomes_bairros,
                    nome_camada=f"📍 Casos por bairro · {ano}", mostrar=True,
                    maximo=maximo_bolha, rotulo_ano=ano,
                )
        if mostrar_nomes_bairros and anos_no_mapa:
            adicionar_nomes_bairros(m, df_mapa)

        # Mapa de calor: SÓ o agravo escolhido na barra lateral (e só o ano, se escolhido)
        if mostrar_mapa_calor and agravo_calor:
            # RÉGUA FIXA EM NÚMERO DE CASOS, igual para todos os anos.
            # O mapa de calor do folium pinta cada mapa em relação ao seu PRÓPRIO ponto
            # mais concentrado (um ano com 3 casos ficaria tão vermelho quanto um com 300).
            # Aqui calculamos o maior acúmulo de casos de TODOS os anos do agravo e
            # colocamos um ponto de referência invisível, fora da área do mapa, com esse
            # peso — assim o vermelho sempre significa o mesmo número de casos.
            base_escala = df_casos_filtrado[df_casos_filtrado["Tipo_Caso"] == agravo_calor]
            base_escala = base_escala[["Ano", "Latitude", "Longitude"]].dropna()
            pico_calor = int(calcular_pico(
                base_escala, centro[1], centro[0], zoom, 900, ALTURA_MAPA, raio_calor_efetivo, blur_calor,
            )) if not base_escala.empty else 1

            titulo_calor = agravo_calor + (f" ({ano_calor})" if ano_calor is not None else "")
            ponto_referencia = [centro[0] - DESLOCAMENTO_REFERENCIA_GRAUS,
                                centro[1] + DESLOCAMENTO_REFERENCIA_GRAUS, float(pico_calor)]
            if not df_mapa[["Latitude", "Longitude"]].dropna().empty:
                # Uma camada de calor por ano, todas com a mesma régua e todas ligadas
                for ano in anos_no_mapa:
                    pontos_ano = df_mapa[df_mapa["Ano"] == ano][["Latitude", "Longitude"]].dropna().values
                    if not len(pontos_ano):
                        continue
                    heat_data = [[lat, lon, 1.0] for lat, lon in pontos_ano] + [ponto_referencia]
                    fg_calor = folium.FeatureGroup(name=f"🦟 {agravo_calor} · {ano}",
                                                   show=True)
                    HeatMap(
                        heat_data, radius=raio_calor_efetivo, blur=blur_calor,
                        min_opacity=0.3, gradient=gradiente_calor.get(agravo_calor),
                    ).add_to(fg_calor)
                    fg_calor.add_to(m)
            else:
                aviso_calor = f"Nenhum caso de {titulo_calor} com os filtros atuais."

    # ---------------- MAPA DE CALOR DO RT-PCR ----------------
    contagem_camadas = {}
    if camadas_exame and not df_notificacoes.empty:
        df_camadas = df_notificacoes[df_notificacoes["Ano"].isin(filtros["anos"])]
        if not filtros.get("incluir_fora", True) and "Dentro_Municipio" in df_camadas.columns:
            df_camadas = df_camadas[df_camadas["Dentro_Municipio"]]
        raio_camadas = max(8, min(60, int(raio_calor * (13 / max(zoom, 1))))) if raio_adaptativo else raio_calor
        desfoque_camadas = max(raio_camadas // 2, 1)
        # Uma camada por ano (anos marcados), todas com a mesma régua de cores e ligadas
        positivos = df_camadas[mascara_categoria(df_camadas, camadas_exame[0])]
        base_rt = positivos[["Ano", "Latitude", "Longitude"]].dropna()
        pico_rt = calcular_pico(base_rt, centro[1], centro[0], zoom, 900, ALTURA_MAPA,
                                raio_camadas, desfoque_camadas) if not base_rt.empty else 1.0
        referencia_rt = [centro[0] - DESLOCAMENTO_REFERENCIA_GRAUS,
                         centro[1] + DESLOCAMENTO_REFERENCIA_GRAUS, float(pico_rt)]
        anos_rt = sorted(int(a) for a in df_camadas["Ano"].dropna().unique())
        for ano in anos_rt:
            parcial = adicionar_camadas_exame(
                m, df_camadas[df_camadas["Ano"] == ano], camadas_exame, raio=raio_camadas,
                desfoque=desfoque_camadas, sufixo=f" · {ano}", mostrar=True, icone="🦟",
                referencia=referencia_rt,
            )
            for nome_cat, n in parcial.items():
                contagem_camadas[nome_cat] = contagem_camadas.get(nome_cat, 0) + n
        adicionar_legenda_camadas(m, camadas_exame, contagem_camadas)

    # ---------------- UBS ----------------
    if not ubs.empty:
        camada_ubs = MarkerCluster(name="UBS").add_to(m) if cluster and len(ubs) > 1 else m

        for idx, row in ubs.iterrows():
            if hasattr(row.geometry, "x") and hasattr(row.geometry, "y"):
                lat, lon = row.geometry.y, row.geometry.x
            elif hasattr(row.geometry, "centroid"):
                lat, lon = row.geometry.centroid.y, row.geometry.centroid.x
            else:
                continue

            nome_ubs = str(row.get(campo_nome, f"UBS {idx + 1}"))
            popup_ubs = f"<b>{nome_ubs}</b><br>Lat: {lat:.6f}<br>Lon: {lon:.6f}"
            for col in ubs.columns:
                if col not in ["geometry", campo_nome] and pd.notna(row.get(col, None)):
                    popup_ubs += f"<br><b>{col}:</b> {row[col]}"

            folium.Marker(
                location=[lat, lon],
                popup=folium.Popup(popup_ubs, max_width=300),
                tooltip=nome_ubs,
                icon=folium.Icon(color="red", icon="plus-sign", prefix="glyphicon"),
            ).add_to(camada_ubs)

    folium.LayerControl().add_to(m)

    # ---------------- LEGENDA ----------------
    if mostrar_casos and not df_casos_filtrado.empty:
        itens_legenda = ""
        # Com calor ligado: só o agravo escolhido; só marcadores: todos os agravos filtrados
        if "🔥" in tipo_visualizacao and agravo_calor:
            tipos_legenda = [agravo_calor]
        else:
            tipos_legenda = sorted(df_casos_filtrado["Tipo_Caso"].unique())
        for tipo in tipos_legenda:
            cor = CORES_CASOS_MAPA.get(tipo, "#2196F3")
            itens_legenda += f"""
            <div style="display:flex; align-items:center; margin:4px 0;">
                <span style="display:inline-block; width:14px; height:14px; border-radius:50%;
                             background-color:{cor}; margin-right:8px; border:1px solid #333;"></span>
                <span style="font-size:13px; color:#222;">{tipo}</span>
            </div>
            """

        bloco_intensidade = ""
        if "🔥" in tipo_visualizacao and agravo_calor:
            paradas = gradiente_calor.get(agravo_calor, gradiente_calor["Dengue"])
            cores_gradiente = ", ".join(f"{cor} {float(pos) * 100:.0f}%" for pos, cor in paradas.items())
            titulo_calor_legenda = html.escape(agravo_calor + (f" · {ano_calor}" if ano_calor is not None else ""))
            # Marcas da régua em número de casos (a mesma para todos os anos)
            if pico_calor >= 3:
                marcas = ["1", str(round(pico_calor / 2)), f"{pico_calor}+"]
            elif pico_calor == 2:
                marcas = ["1", "2+"]
            else:
                marcas = ["1"]
            marcas_html = "".join(f"<span>{marca}</span>" for marca in marcas)
            bloco_intensidade = f"""
            <div style="margin-top:8px; padding-top:6px; border-top:1px solid #ddd;">
                <div style="font-size:11px; color:#555; margin-bottom:3px;">Calor: <b>{titulo_calor_legenda}</b></div>
                <div style="width:150px; height:10px; border-radius:4px;
                            background: linear-gradient(to right, {cores_gradiente});
                            border:1px solid #999;"></div>
                <div style="display:flex; justify-content:space-between; font-size:10px; color:#555; width:150px;">
                    {marcas_html}
                </div>
                <div style="font-size:10px; color:#777; width:150px; margin-top:2px;">
                    casos próximos · mesma escala em todos os anos
                </div>
            </div>
            """

        legend_html = f"""
        {{% macro html(this, kwargs) %}}
        <div style="position: fixed; bottom: 30px; left: 30px; z-index: 9999;
                    background-color: white; padding: 10px 14px; border-radius: 8px;
                    box-shadow: 0 1px 6px rgba(0,0,0,0.3); font-family: sans-serif;">
            <div style="font-weight:bold; font-size:13px; margin-bottom:6px; color:#111;">🦟 Tipo de Caso</div>
            {itens_legenda}
            {bloco_intensidade}
        </div>
        {{% endmacro %}}
        """
        legenda = folium.MacroElement()
        legenda._template = folium.map.Template(legend_html)
        m.get_root().add_child(legenda)

    st_folium(
        m, height=ALTURA_MAPA, use_container_width=True, returned_objects=[],
        center=tuple(centro), zoom=zoom, key="mapa_principal",
    )
    if aviso_calor:
        st.info(f"🔥 {aviso_calor}")
    if camadas_exame and not any(contagem_camadas.values()):
        st.info("🧪 Nenhuma notificação com RT-PCR positivo em bairro do mapa nos anos marcados.")

    if not df_casos.empty:
        st.divider()
        renderizar_mapa_rtpcr(df_notificacoes, filtros["anos"], municipio)
        st.divider()
        renderizar_bairros_prioritarios(df_notificacoes_bairro, filtros["anos"], key_prefix="bairros")

    if mostrar_casos and not df_casos_filtrado.empty:
        st.divider()
        # Botão liga/desliga em vez de expander: o comparacao_mapas.py já tem um
        # expander próprio por dentro, e o Streamlit não aceita expander dentro de expander.
        if st.toggle("📊 Comparação de Densidade entre Anos (Mapa de Calor)", value=False, key="mostrar_comparacao_anos"):
            st.caption("Densidade dos casos filtrados, um mapa por ano, lado a lado, com a mesma escala de cores.")
            renderizar_comparacao_anos(df_casos_filtrado, municipio, key_prefix="mapa", ubs_gdf=ubs)

        st.divider()
        renderizar_estatisticas_e_graficos(df_casos_filtrado, key_prefix="mapa", populacao=populacao_municipio)
        st.info("📑 Para um relatório explicativo com as variáveis que você escolher, abra a aba **Relatório**.")

    renderizar_tabela_ubs(ubs, key_prefix="mapa")
    st.divider()
    renderizar_exportacao_rodape(
        ubs, municipio, key_prefix="mapa", df_casos_pdf=df_casos_filtrado, populacao=populacao_municipio
    )


# =====================================================================
# ABA 2: FILTROS DE CASOS
# =====================================================================
with aba_filtros:
    st.header("🦟 Casos por Bairro")

    if not df_casos.empty:
        st.subheader("Casos por bairro, ano e agravo")
        st.caption("Contagens agregadas com os filtros da barra lateral. Por proteção de dados (LGPD), "
                   "esta versão pública não mostra registros individuais.")
        df_tabela = tabela_casos_por_bairro(df_casos_filtrado)
        st.success(f"{len(df_casos_filtrado)} casos em {df_tabela['Bairro'].nunique() if not df_tabela.empty else 0} "
                   "bairros/localidades com os filtros atuais.")
        st.dataframe(df_tabela, use_container_width=True, hide_index=True, key="df_bairros_aba2")
        st.download_button(
            label="📥 Baixar tabela por bairro (CSV)",
            data=df_tabela.to_csv(index=False, sep=";", encoding="utf-8-sig"),
            file_name="casos_por_bairro.csv",
            mime="text/csv",
            key="btn_csv_bairros_aba2",
        )

        st.divider()
        renderizar_exportacao_rodape(
            ubs, municipio, key_prefix="filtros", df_casos_pdf=df_casos_filtrado, populacao=populacao_municipio
        )
    else:
        st.warning("Nenhum dado de caso disponível. Verifique a fonte de dados na barra lateral.")


# =====================================================================
# ABA 3: RELATÓRIO PERSONALIZADO (atualiza em tempo real + PDF)
# =====================================================================
with aba_relatorio:
    renderizar_aba_relatorio(
        df_casos_filtrado, populacao_municipio, filtros_texto,
        municipio_gdf=municipio, ubs_gdf=ubs, info_dados=info_dados, key_prefix="relatorio",
    )