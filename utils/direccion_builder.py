"""
Construye la dirección completa desde los campos desglosados del Padrón SUNAT.
El formato resultante es compatible con el que devuelve la consulta pública.
"""

_VACIOS = {"", "-", "S/N", "N/A"}


def _v(val):
    s = (val or "").strip()
    return s if s and s.upper() not in _VACIOS else None


def armar_direccion(row: dict) -> str:
    """Arma la dirección completa a partir de los campos del Padrón."""
    partes = []

    tipo_via = _v(row.get("tipo_via"))
    nombre_via = _v(row.get("nombre_via"))
    if tipo_via and nombre_via:
        partes.append(f"{tipo_via} {nombre_via}")

    numero = _v(row.get("numero"))
    if numero:
        partes.append(f"NRO. {numero}")

    interior = _v(row.get("interior"))
    if interior:
        partes.append(f"INT. {interior}")

    manzana = _v(row.get("manzana"))
    if manzana:
        partes.append(f"MZA. {manzana}")

    lote = _v(row.get("lote"))
    if lote:
        partes.append(f"LT. {lote}")

    kilometro = _v(row.get("kilometro"))
    if kilometro:
        partes.append(f"KM. {kilometro}")

    direccion = " ".join(partes)

    tipo_zona = _v(row.get("tipo_zona"))
    codigo_zona = _v(row.get("codigo_zona"))
    if tipo_zona and codigo_zona:
        # Formato con espacios extra igual al de la consulta pública SUNAT
        direccion += f"      {tipo_zona} {codigo_zona}"

    return direccion.strip() or None
