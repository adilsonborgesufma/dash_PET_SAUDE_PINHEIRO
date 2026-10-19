"""
Preferências do usuário persistidas em disco (arquivo local .json), para
que coisas como o link da planilha do Google Sheets não se percam quando o
dashboard é fechado e reaberto — sem precisar colar o link de novo toda vez.

Isso é diferente do st.session_state, que só dura enquanto a aba do
navegador está aberta.
"""
import json
import os

CAMINHO_PREFERENCIAS = ".dashboard_preferencias.json"


def carregar_preferencias():
    """Lê as preferências salvas. Se o arquivo não existir ou estiver
    corrompido, retorna um dicionário vazio (o dashboard usa os padrões)."""
    if not os.path.exists(CAMINHO_PREFERENCIAS):
        return {}
    try:
        with open(CAMINHO_PREFERENCIAS, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def salvar_preferencia(chave, valor):
    """Salva (ou atualiza) uma preferência no arquivo local, sem apagar as
    outras já salvas."""
    preferencias = carregar_preferencias()
    if preferencias.get(chave) == valor:
        return  # já está salvo, evita escrever no disco à toa
    preferencias[chave] = valor
    try:
        with open(CAMINHO_PREFERENCIAS, "w", encoding="utf-8") as f:
            json.dump(preferencias, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # se não conseguir salvar (ex: disco somente leitura), ignora
