"""
Módulo de carregamento e limpeza de dados.

Contém tudo relacionado a: ler os arquivos geográficos (município e UBS),
ler os CSVs locais de casos, ler e limpar dados vindos do Google Sheets
(incluindo o reparo automático de coordenadas corrompidas), e identificar
qual coluna da camada de UBS deve ser usada como nome de exibição.
"""
import os
import re
import traceback
from datetime import datetime

import pandas as pd
import geopandas as gpd
import streamlit as st
import numpy as np


@st.cache_data
def load_geodata():
    """Carrega município e UBS diretamente da pasta assets/"""
    try:
        caminho_municipio = "assets/pinheiro.json"
        caminho_ubs = "assets/ubs_pinheiro.json"

        if not os.path.exists(caminho_municipio):
            st.error(f"❌ Arquivo não encontrado: {caminho_municipio}")
            return None, None

        if not os.path.exists(caminho_ubs):
            st.error(f"❌ Arquivo não encontrado: {caminho_ubs}")
            return None, None

        municipio = gpd.read_file(caminho_municipio)
        ubs = gpd.read_file(caminho_ubs)

        municipio = municipio.to_crs(epsg=4326)
        ubs = ubs.to_crs(epsg=4326)

        return municipio, ubs

    except Exception as e:
        st.error(f"❌ Erro ao carregar dados geográficos: {str(e)}")
        st.code(traceback.format_exc())
        return None, None


@st.cache_data
def load_casos_data():
    """Carrega dados dos casos a partir dos CSVs na pasta assets"""
    todos_dados = []

    arquivos = [
        "planilha_2023.csv",
        "planilha_2024.csv",
        "planilha_2025.csv",
        "planilha_2026.csv"
    ]

    caminhos_possiveis = [
        "assets",
        "./assets",
        "../assets",
        ".",
        "",
    ]

    for arquivo in arquivos:
        arquivo_encontrado = False

        for caminho in caminhos_possiveis:
            if caminho:
                caminho_completo = os.path.join(caminho, arquivo)
            else:
                caminho_completo = arquivo

            try:
                if os.path.exists(caminho_completo):
                    df = pd.read_csv(caminho_completo, sep=';', encoding='utf-8')

                    df.columns = df.columns.str.strip()

                    mapeamento_colunas = {}

                    for col in df.columns:
                        col_clean = col.strip()
                        if col_clean in ['Latitude', 'Latitude']:
                            mapeamento_colunas[col] = 'Latitude'
                        elif col_clean in ['Longitude', 'Longitude']:
                            mapeamento_colunas[col] = 'Longitude'
                        elif col_clean in ['Casos', 'Casos']:
                            mapeamento_colunas[col] = 'Tipo_Caso'
                        elif col_clean in ['Ano', 'Anos', 'Ano', 'Anos']:
                            mapeamento_colunas[col] = 'Ano'
                        elif col_clean in ['Gênero', 'Gęnero', 'GÛnero', 'Genero']:
                            mapeamento_colunas[col] = 'Genero'

                    df = df.rename(columns=mapeamento_colunas)

                    colunas_necessarias = ['Latitude', 'Longitude', 'Tipo_Caso', 'Ano', 'Genero']
                    colunas_existentes = [col for col in colunas_necessarias if col in df.columns]

                    if len(colunas_existentes) >= 3:
                        df = df.dropna(subset=['Latitude', 'Longitude'], how='all')

                        df['Latitude'] = df['Latitude'].astype(str).str.replace(',', '.').str.strip()
                        df['Longitude'] = df['Longitude'].astype(str).str.replace(',', '.').str.strip()

                        df['Latitude'] = pd.to_numeric(df['Latitude'], errors='coerce')
                        df['Longitude'] = pd.to_numeric(df['Longitude'], errors='coerce')

                        df = df.dropna(subset=['Latitude', 'Longitude'])

                        if 'Ano' not in df.columns:
                            ano = arquivo.replace('planilha_', '').replace('.csv', '')
                            df['Ano'] = int(ano)
                        else:
                            df['Ano'] = pd.to_numeric(df['Ano'], errors='coerce')
                            df = df.dropna(subset=['Ano'])
                            df['Ano'] = df['Ano'].astype(int)

                        if 'Tipo_Caso' in df.columns:
                            df['Tipo_Caso'] = df['Tipo_Caso'].astype(str).str.strip()

                        if 'Genero' in df.columns:
                            df['Genero'] = df['Genero'].astype(str).str.strip()
                        else:
                            df['Genero'] = 'Não informado'

                        todos_dados.append(df)
                        arquivo_encontrado = True
                        break
                    else:
                        st.warning(f"⚠️ Arquivo {arquivo} não tem colunas necessárias. Colunas: {list(df.columns)}")

            except Exception as e:
                continue

        if not arquivo_encontrado:
            st.warning(f"⚠️ Arquivo não encontrado: {arquivo}")

    if todos_dados:
        df_combinado = pd.concat(todos_dados, ignore_index=True)
        return df_combinado
    else:
        return pd.DataFrame()



# ================= REPARO DE COORDENADAS CORROMPIDAS =================
# Faixa geográfica aproximada de Pinheiro/MA e entorno, com folga de segurança.
# Usada para "adivinhar" onde entra o ponto decimal em coordenadas que vieram
# corrompidas (ex: planilhas coladas no Google Sheets que converteram a vírgula
# decimal em pontos de milhar, virando "-2.531.708" em vez de "-2,531708").
LAT_MIN_ESPERADO, LAT_MAX_ESPERADO = -3.6, -1.8
LON_MIN_ESPERADO, LON_MAX_ESPERADO = -46.0, -44.0


def reparar_coordenada(valor_bruto, minimo, maximo):
    """
    Tenta interpretar corretamente uma coordenada geográfica que pode ter vindo
    em formato correto (com um único separador decimal) ou corrompida (com
    múltiplos pontos, como se fosse um número inteiro formatado com separador
    de milhar). Testa cada posição possível do ponto decimal e usa a primeira
    que resulta em um valor dentro da faixa geográfica esperada.
    """
    if pd.isna(valor_bruto):
        return np.nan

    texto = str(valor_bruto).strip()
    if texto == '' or texto.lower() == 'nan':
        return np.nan

    # Tentativa 1: já está em formato válido (uma vírgula ou um ponto decimal)
    texto_normalizado = texto.replace(',', '.')
    if texto_normalizado.count('.') <= 1:
        try:
            valor = float(texto_normalizado)
            if minimo <= valor <= maximo:
                return valor
        except ValueError:
            pass

    # Tentativa 2: número corrompido com múltiplos pontos/vírgulas — remove
    # tudo e testa reconstruir a posição correta do ponto decimal
    sinal = -1 if texto.strip().startswith('-') else 1
    apenas_digitos = texto.replace('.', '').replace(',', '').replace('-', '').replace('+', '')

    if not apenas_digitos.isdigit() or len(apenas_digitos) < 2:
        return np.nan

    for posicao in range(1, len(apenas_digitos)):
        try:
            candidato = sinal * float(f"{apenas_digitos[:posicao]}.{apenas_digitos[posicao:]}")
        except ValueError:
            continue
        if minimo <= candidato <= maximo:
            return candidato

    return np.nan


def _extrair_id_planilha_google(url_ou_id):
    """Extrai o ID da planilha a partir de uma URL completa do Google Sheets
    (ou aceita o ID já "puro", caso o usuário cole só o código)."""
    texto = url_ou_id.strip()
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", texto)
    if match:
        return match.group(1)
    # Se não encontrou padrão de URL, assume que já é o próprio ID
    return texto


def _extrair_gid_planilha_google(url_ou_id):
    """
    Extrai o identificador da ABA específica (gid) do link, se houver.
    Sem isso, a exportação sempre pega a PRIMEIRA aba da planilha (gid=0),
    mesmo que o link tenha sido copiado de uma aba diferente — foi essa a
    causa de só aparecer o ano de 2023: os dados novos foram importados para
    uma aba nova, mas o link continuava apontando (silenciosamente) para a
    aba original.
    """
    texto = url_ou_id.strip()
    match = re.search(r"[?#&]gid=(\d+)", texto)
    if match:
        return match.group(1)
    return None


@st.cache_data(show_spinner=False)
def _baixar_e_limpar_planilha_google(url_ou_id):
    """
    Baixa os dados de casos de uma planilha do Google Sheets publicamente
    compartilhada ("Qualquer pessoa com o link → Leitor") e aplica a mesma
    limpeza usada nos CSVs locais. Reconhece automaticamente dois formatos:

    1) Formato simples: colunas Latitude, Longitude, Casos, Ano, Genero
    2) Formato de ficha de notificação: colunas DATA, AGRAVO, SEXO, LAT, LOG,
       CLASSIF (usado nas planilhas de vigilância epidemiológica, como a da
       UFMA) — nesse caso, o ano é extraído da data e a classificação (caso
       confirmado ou descartado) é preservada na coluna 'Classificacao'.

    Esta função fica em cache normal do Streamlit (sem expirar sozinha); quem
    controla quando ela é chamada de novo é 'carregar_dados_google_sheets',
    que decide se o cache ainda está "fresco" com base no intervalo escolhido
    pelo usuário na barra lateral.
    """
    sheet_id = _extrair_id_planilha_google(url_ou_id)
    gid = _extrair_gid_planilha_google(url_ou_id)
    export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    if gid:
        export_url += f"&gid={gid}"

    try:
        df = pd.read_csv(export_url)
    except Exception as e:
        return pd.DataFrame(), f"Não foi possível ler a planilha: {e}"

    if df.empty:
        return pd.DataFrame(), "A planilha foi lida, mas está vazia."

    df.columns = [str(c).strip() for c in df.columns]
    colunas_lower = {c.lower(): c for c in df.columns}

    # ---- Detecta o formato da planilha ----
    tem_formato_simples = all(
        chave in colunas_lower for chave in ['latitude', 'longitude', 'casos']
    )
    tem_formato_ficha = all(
        chave in colunas_lower for chave in ['lat', 'log', 'agravo']
    )

    df_limpo = pd.DataFrame()

    if tem_formato_simples:
        df_limpo['Latitude'] = df[colunas_lower['latitude']].apply(
            lambda v: reparar_coordenada(v, LAT_MIN_ESPERADO, LAT_MAX_ESPERADO)
        )
        df_limpo['Longitude'] = df[colunas_lower['longitude']].apply(
            lambda v: reparar_coordenada(v, LON_MIN_ESPERADO, LON_MAX_ESPERADO)
        )
        df_limpo['Tipo_Caso'] = df[colunas_lower['casos']].astype(str).str.strip()

        if 'ano' in colunas_lower:
            df_limpo['Ano'] = pd.to_numeric(df[colunas_lower['ano']], errors='coerce')
        else:
            return pd.DataFrame(), "Planilha no formato simples precisa de uma coluna 'Ano'."

        if 'genero' in colunas_lower or 'gênero' in colunas_lower:
            chave_genero = colunas_lower.get('genero', colunas_lower.get('gênero'))
            df_limpo['Genero'] = df[chave_genero].astype(str).str.strip()
        else:
            df_limpo['Genero'] = 'Não informado'

        df_limpo['Classificacao'] = None

    elif tem_formato_ficha:
        df_limpo['Latitude'] = df[colunas_lower['lat']].apply(
            lambda v: reparar_coordenada(v, LAT_MIN_ESPERADO, LAT_MAX_ESPERADO)
        )
        df_limpo['Longitude'] = df[colunas_lower['log']].apply(
            lambda v: reparar_coordenada(v, LON_MIN_ESPERADO, LON_MAX_ESPERADO)
        )
        df_limpo['Tipo_Caso'] = df[colunas_lower['agravo']].astype(str).str.strip()

        if 'data' in colunas_lower:
            datas = pd.to_datetime(df[colunas_lower['data']], format='%d/%m/%y', errors='coerce')
            if datas.isna().all():
                # tenta formato alternativo (ano com 4 dígitos) antes de desistir
                datas = pd.to_datetime(df[colunas_lower['data']], dayfirst=True, errors='coerce')
            df_limpo['Ano'] = datas.dt.year
        elif 'ano' in colunas_lower:
            df_limpo['Ano'] = pd.to_numeric(df[colunas_lower['ano']], errors='coerce')
        else:
            return pd.DataFrame(), "Planilha de ficha de notificação precisa de uma coluna 'DATA' ou 'Ano'."

        if 'sexo' in colunas_lower:
            df_limpo['Genero'] = df[colunas_lower['sexo']].astype(str).str.strip()
        else:
            df_limpo['Genero'] = 'Não informado'

        if 'classif' in colunas_lower:
            df_limpo['Classificacao'] = df[colunas_lower['classif']].astype(str).str.strip()
        else:
            df_limpo['Classificacao'] = None

    else:
        colunas_encontradas = ", ".join(df.columns)
        return pd.DataFrame(), (
            "Não reconheci as colunas da planilha. Esperado (formato simples): "
            "Latitude, Longitude, Casos, Ano, Genero — ou (formato de ficha): "
            f"LAT, LOG, AGRAVO, DATA, SEXO, CLASSIF. Colunas encontradas: {colunas_encontradas}"
        )

    df_limpo = df_limpo.dropna(subset=['Latitude', 'Longitude', 'Ano'])
    df_limpo['Ano'] = df_limpo['Ano'].astype(int)
    df_limpo['Tipo_Caso'] = df_limpo['Tipo_Caso'].replace('nan', 'Não informado')
    df_limpo['Genero'] = df_limpo['Genero'].replace('nan', 'Não informado')

    if df_limpo.empty:
        return pd.DataFrame(), "Nenhuma linha válida após a limpeza (confira Latitude/Longitude/Ano)."

    return df_limpo, None


def carregar_dados_google_sheets(url_ou_id, intervalo_segundos, forcar_atualizacao=False):
    """
    Controla o "frescor" dos dados vindos do Google Sheets. Guarda o resultado
    e o horário do último download em st.session_state; só baixa de novo se
    o intervalo escolhido pelo usuário já tiver passado (ou se o botão
    "Atualizar agora" foi clicado). Retorna (dataframe, mensagem_de_erro,
    horario_da_ultima_atualizacao).
    """
    agora = datetime.now().timestamp()
    chave_dados = f"gsheets_dados::{url_ou_id}"
    chave_hora = f"gsheets_hora::{url_ou_id}"

    dados_em_cache = st.session_state.get(chave_dados)
    hora_em_cache = st.session_state.get(chave_hora)

    cache_valido = (
        not forcar_atualizacao
        and dados_em_cache is not None
        and hora_em_cache is not None
        and (agora - hora_em_cache) < intervalo_segundos
    )

    if cache_valido:
        df_cache, erro_cache = dados_em_cache
        return df_cache, erro_cache, hora_em_cache

    if forcar_atualizacao:
        _baixar_e_limpar_planilha_google.clear()

    df_novo, erro_novo = _baixar_e_limpar_planilha_google(url_ou_id)
    st.session_state[chave_dados] = (df_novo, erro_novo)
    st.session_state[chave_hora] = agora
    return df_novo, erro_novo, agora



def encontrar_campo_nome(gdf):
    possiveis_nomes = [
        'UBS Coco', 'UBS Kiola Sarney', 'UBS Pacas', 'UBS São José', 'NAME',
        'ubs_nome', 'ubs_name', 'estabelecimento',
        'local', 'endereco', 'descricao', 'farmacia',
        'unidade', 'ponto', 'ponto_de_atendimento'
    ]

    for nome in possiveis_nomes:
        if nome in gdf.columns:
            return nome

    colunas_texto = gdf.select_dtypes(include=['object', 'string']).columns
    if len(colunas_texto) > 0:
        return colunas_texto[0]

    colunas_nao_geo = [col for col in gdf.columns if col != 'geometry']
    if len(colunas_nao_geo) > 0:
        return colunas_nao_geo[0]

    return "ID"


