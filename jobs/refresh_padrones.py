#!/usr/bin/env python3
"""
Job de actualización diaria de los Padrones Reducidos SUNAT.

Uso standalone (cron):
    python3 /ruta/al/proyecto/jobs/refresh_padrones.py [ruc|local_anexo]

Cron sugerido (6:30am Lima = 11:30 UTC):
    30 11 * * *  cd /ruta/al/proyecto && python3 jobs/refresh_padrones.py >> logs/refresh.log 2>&1

También es invocado internamente por el endpoint POST /admin/refresh-padron/{tipo}.
"""
import os
import sys
import logging

# Cuando se ejecuta directamente, añadir el directorio raíz al path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ROOT, ".env"))
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("refresh_padrones")

from db.connection import init_pool, close_pool
from services.padron_downloader import descargar_padron
from services.padron_importer import importar_padron_ruc, importar_padron_local_anexo
from repositories.meta_repository import (
    get_meta, upsert_meta_inicio, upsert_meta_error, upsert_meta_skipped
)


def refresh_padron(tipo: str) -> dict:
    """
    Descarga e importa un padrón.
    Retorna dict con: tipo, status ('ok'|'skipped'|'error'), filas, mensaje.
    """
    if tipo not in ("ruc", "local_anexo"):
        return {"tipo": tipo, "status": "error", "mensaje": f"Tipo desconocido: {tipo!r}"}

    logger.info("=== Iniciando refresh padrón %s ===", tipo)

    meta = get_meta(tipo)
    prev_hash = meta.get("hash_archivo") if meta else None

    upsert_meta_inicio(tipo)

    try:
        resultado = descargar_padron(tipo, prev_hash)

        if resultado.get("skipped"):
            upsert_meta_skipped(tipo)
            logger.info("Padrón %s sin cambios, import omitido", tipo)
            return {"tipo": tipo, "status": "skipped", "filas": meta.get("filas_importadas", 0)}

        ruta = resultado["ruta"]
        nuevo_hash = resultado["hash"]

        if tipo == "ruc":
            filas = importar_padron_ruc(ruta, nuevo_hash)
        else:
            filas = importar_padron_local_anexo(ruta, nuevo_hash)

        logger.info("Padrón %s actualizado: %s filas", tipo, f"{filas:,}")
        return {"tipo": tipo, "status": "ok", "filas": filas}

    except Exception as exc:
        msg = str(exc)[:500]
        logger.error("Error procesando padrón %s: %s", tipo, msg, exc_info=True)
        upsert_meta_error(tipo, msg)
        return {"tipo": tipo, "status": "error", "mensaje": msg}


def main():
    tipos = sys.argv[1:] or ["ruc", "local_anexo"]
    invalid = [t for t in tipos if t not in ("ruc", "local_anexo")]
    if invalid:
        print(f"Tipos no válidos: {invalid}. Usar 'ruc' y/o 'local_anexo'.")
        sys.exit(1)

    logger.info("=== Refresh padrones SUNAT iniciado: %s ===", tipos)
    init_pool()

    resultados = []
    for tipo in tipos:
        r = refresh_padron(tipo)
        resultados.append(r)

    close_pool()

    hubo_error = False
    for r in resultados:
        estado = r["status"]
        detalle = f"({r.get('filas', 0):,} filas)" if estado in ("ok", "skipped") else r.get("mensaje", "")
        logger.info("  %s: %s %s", r["tipo"], estado, detalle)
        if estado == "error":
            hubo_error = True

    logger.info("=== Refresh padrones SUNAT finalizado ===")

    if hubo_error:
        sys.exit(1)


if __name__ == "__main__":
    main()
