"""
Módulo de cálculos estatísticos simples, usados em vários lugares do
dashboard (cards, PDF, gráficos).
"""


def calcular_incidencia(total_casos, populacao):
    """Calcula a taxa de incidência por 10.000 habitantes."""
    if not populacao or populacao <= 0:
        return None
    return round((total_casos / populacao) * 10000, 2)


