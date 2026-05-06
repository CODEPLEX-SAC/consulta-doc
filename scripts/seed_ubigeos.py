#!/usr/bin/env python3
"""
Carga el catálogo de ubigeos en la tabla ubigeos_sunat.
Usa el archivo data/ubigeos.json que ya existe en el proyecto.

Uso:
    python3 scripts/seed_ubigeos.py
"""
import os
import sys
import json
import logging

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ROOT, ".env"))
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
logger = logging.getLogger("seed_ubigeos")

from psycopg2.extras import execute_values
from db.connection import init_pool, get_db

UBIGEOS_JSON = os.path.join(_ROOT, "data", "ubigeos.json")


def seed():
    logger.info("Cargando %s", UBIGEOS_JSON)
    with open(UBIGEOS_JSON, encoding="utf-8") as f:
        data = json.load(f)

    rows = []
    for ubigeo, v in data.items():
        rows.append((
            ubigeo.strip(),
            v.get("d") or v.get("departamento", ""),
            v.get("p") or v.get("provincia", ""),
            v.get("di") or v.get("distrito", ""),
        ))

    if not rows:
        logger.error("El archivo de ubigeos está vacío o tiene formato inesperado")
        sys.exit(1)

    logger.info("Insertando %d ubigeos…", len(rows))
    with get_db() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO ubigeos_sunat (ubigeo, departamento, provincia, distrito)
                VALUES %s
                ON CONFLICT (ubigeo) DO UPDATE SET
                  departamento = EXCLUDED.departamento,
                  provincia    = EXCLUDED.provincia,
                  distrito     = EXCLUDED.distrito
                """,
                rows,
            )

    logger.info("Seed ubigeos completado: %d registros", len(rows))


if __name__ == "__main__":
    init_pool()
    seed()
