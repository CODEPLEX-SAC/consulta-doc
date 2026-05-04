"""
Lookup de ubigeo a partir de la dirección fiscal de SUNAT.

SUNAT incluye al final de la dirección:
    ... DEPARTAMENTO - PROVINCIA - DISTRITO

Se parsea ese sufijo y se busca en el índice invertido del
dataset INEI/RENIEC (data/ubigeos.json).
"""
import json
import unicodedata
import os
import re

_DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'ubigeos.json')


def _norm(text: str) -> str:
    """Mayúsculas sin acentos ni caracteres especiales."""
    text = text.upper().strip()
    text = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in text if not unicodedata.combining(c))


def _build_index(data: dict) -> dict:
    """
    Construye dos índices:
      1. (prov_norm, dist_norm)  → ubigeo  (match exacto)
      2. dist_norm               → [ubigeo, ...]  (fallback por distrito solo)
    """
    by_prov_dist: dict = {}
    by_dist: dict = {}

    for ubigeo, loc in data.items():
        pn = _norm(loc.get('p', ''))
        dn = _norm(loc.get('di', ''))

        key = (pn, dn)
        if key not in by_prov_dist:
            by_prov_dist[key] = ubigeo

        if dn not in by_dist:
            by_dist[dn] = []
        by_dist[dn].append(ubigeo)

    return by_prov_dist, by_dist


with open(_DATA_PATH, encoding='utf-8') as f:
    _raw = json.load(f)

_BY_PROV_DIST, _BY_DIST = _build_index(_raw)


def from_address(direccion: str) -> str | None:
    """
    Extrae el código ubigeo de 6 dígitos desde la dirección SUNAT.

    Formato esperado al final de la dirección:
        '... DEPARTAMENTO - PROVINCIA - DISTRITO'

    Ejemplos:
        'AV. PROCERES ... LIMA - LIMA - LOS OLIVOS'  → '150117'
        'JR. LIMA 123 CUSCO - CUSCO - CUSCO'         → '080101'
    """
    if not direccion:
        return None

    # Separar por ' - ' y tomar los últimos 2 o 3 tokens
    parts = [p.strip() for p in direccion.split(' - ')]
    if len(parts) < 2:
        return None

    distrito_raw  = parts[-1]
    provincia_raw = parts[-2]

    # Intentar match exacto provincia + distrito
    key = (_norm(provincia_raw), _norm(distrito_raw))
    if key in _BY_PROV_DIST:
        return _BY_PROV_DIST[key]

    # Fallback: solo distrito (si es único)
    dn = _norm(distrito_raw)
    matches = _BY_DIST.get(dn, [])
    if len(matches) == 1:
        return matches[0]

    # Si hay varios distritos con ese nombre, intentar con el departamento
    # El departamento suele ser la última palabra de parts[-3]
    if len(parts) >= 3:
        # El departamento está al final del bloque previo
        dept_words = parts[-3].split()
        # Buscar coincidencia por (dept_norm, dist_norm)
        for ubigeo in matches:
            loc = _raw[ubigeo]
            dept_norm = _norm(loc.get('d', ''))
            # Chequear si alguna palabra final de parts[-3] coincide con el dept
            for w in reversed(dept_words[-3:]):
                if _norm(w) in dept_norm or dept_norm in _norm(w):
                    return ubigeo

    return matches[0] if matches else None
