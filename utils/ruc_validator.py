"""
Validación de RUC y conversión DNI → RUC tipo 10 (persona natural).
Algoritmo oficial SUNAT de dígito verificador.
"""

_PESOS = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]


def calcular_digito_verificador(ruc10: str) -> int:
    """Calcula el dígito verificador para los primeros 10 dígitos de un RUC."""
    suma = sum(int(d) * p for d, p in zip(ruc10, _PESOS))
    residuo = suma % 11
    digito = 11 - residuo
    if digito == 10:
        digito = 0
    elif digito == 11:
        digito = 1
    return digito


def dni_a_ruc(dni: str) -> str:
    """Convierte DNI de 8 dígitos a RUC tipo 10 (persona natural)."""
    if not dni or len(dni) != 8 or not dni.isdigit():
        raise ValueError(f"DNI inválido: {dni!r}")
    prefijo = "10" + dni
    digito = calcular_digito_verificador(prefijo)
    return prefijo + str(digito)


def validar_ruc(ruc: str) -> bool:
    """Valida formato y dígito verificador de un RUC."""
    if not ruc or len(ruc) != 11 or not ruc.isdigit():
        return False
    esperado = calcular_digito_verificador(ruc[:10])
    return int(ruc[10]) == esperado
