# Dashboard UBS – Pinheiro, Maranhão

Painel de Vigilância Epidemiológica de **Dengue, Chikungunya e Zika** do município de Pinheiro (MA), com a distribuição espacial dos casos e das Unidades Básicas de Saúde (UBS).

Desenvolvido no **Programa de Educação pelo Trabalho para a Saúde: Informação e Saúde Digital (PET-Saúde/I&SD)** – Universidade Federal do Maranhão (UFMA), em parceria com a Secretaria Municipal de Saúde de Pinheiro.

**Finalidade:** planejamento em saúde pública e vigilância epidemiológica.

---

## O que o painel faz

| Aba | Conteúdo |
|---|---|
| 📊 **Visão Geral** | Indicadores (total de casos, casos no ano, incidência por 10 mil habitantes), evolução por ano e agravo, perfil dos casos (faixa etária, gênero, exames NS1 e RT-PCR) |
| 🗺️ **Mapa Geral** | Mapa com limite municipal, UBS e casos (marcadores e/ou mapa de calor por agravo e por ano), comparação de densidade entre anos, estatísticas e gráficos |
| 🦟 **Filtros de Casos** | Tabela dos casos filtrados e download em CSV |
| 📑 **Relatório** | Relatório interpretativo com as variáveis escolhidas pelo usuário, com download em PDF |

**Filtros (barra lateral):** ano, tipo de caso, gênero, idade, resultado de exames, casos confirmados ou todas as notificações, e casos fora do limite municipal.

## Fonte dos dados

- **Notificações:** Google Planilha da Vigilância Epidemiológica de Pinheiro/MA (uma aba por ano), lida em modo **somente leitura** por uma conta de serviço do Google. A planilha **não é pública**.
- **População:** API oficial do IBGE (estimativa mais recente; se não houver, o Censo 2022), município 2108603.
- **Base cartográfica:** OpenStreetMap.

### Privacidade (LGPD)

- Só são lidas as colunas usadas no painel. Endereço, logradouro, bairro e número da ficha são descartados no momento da leitura.
- Os popups do mapa mostram localização arredondada (~110 m) e faixa etária em vez da idade exata.
- O relatório em PDF mostra a densidade em hexágonos, sem a localização individual dos casos.
- Nenhum dado de paciente, planilha ou credencial fica neste repositório (veja `.gitignore`).

## Regras de contagem

- **Ano:** aba da planilha em que a notificação foi registrada.
- **Caso confirmado:** classificação final preenchida e diferente de "Descartado"; sem classificação = em investigação.
- **Entram no painel** apenas notificações com latitude **e** longitude preenchidas.
- **Duplicidade:** mesma ficha, mesma idade e mesmo agravo na mesma aba (fica o último registro).
- **Incidência:** casos do ano ÷ população (IBGE) × 10.000.

## Estrutura

```
Passo8_PET_DASH_MARK5.py      arquivo principal (Streamlit)
modules/
  config.py                   constantes (cores, população de referência)
  dados.py                    leitura dos dados geográficos (município e UBS)
  graficos.py                 indicadores e gráficos
  comparacao_mapas.py         mapas de calor por ano, com escala comum
  relatorio_detalhado.py      aba Relatório e PDF
  exportacao.py               tabela de UBS e downloads
assets/                       limites geográficos (GeoJSON) e logos
requirements.txt              bibliotecas Python
```

## Como rodar no computador

```bash
python -m pip install -r requirements.txt
python -m streamlit run Passo8_PET_DASH_MARK5.py
```

Sem o arquivo `.streamlit/secrets.toml`, o painel roda em **modo local** e lê o Excel mais recente da pasta `assets/` (que não vai para o GitHub).

### Configuração da planilha online (`.streamlit/secrets.toml`)

```toml
gcp_service_account_json = '''
{ ...conteúdo da chave .json da conta de serviço... }
'''

[planilha]
id = "ID_DA_PLANILHA"
```

No Streamlit Community Cloud, o mesmo conteúdo vai em **Settings → Secrets** do app.

## Tecnologias

Python · Streamlit · GeoPandas · Folium · Plotly · Matplotlib · ReportLab · gspread

## Equipe

Anne Karine Martins Assunção da Silva · Jonatas da Silva Castro · Bruna Pereira Maia Silva · Geciane Pereira Aroucha · Luenne Sinara Ribeiro Pinheiro · Sônia Maria Silva Luz · Lindomar Christian da Trindade Filho · Cleiciane Cordeiro Coutinho · Nalleny Perpétua dos Santos Marinho · Cleyce Jane Costa Moraes · Alice Beatriz Tomaz Tavares · Enzo Marcos Costa Guterres · Lucas Gomes da Silva · Kauã de Assis Menezes Reis · Adilson Matheus Borges Machado

**Desenvolvimento:** Bruna Pereira Maia Silva, Geciane Pereira Aroucha e Adilson Matheus Borges Machado  
**Orientação:** Adilson Matheus Borges Machado

---

Município de Pinheiro/MA • Desenvolvido para pesquisa em saúde pública
