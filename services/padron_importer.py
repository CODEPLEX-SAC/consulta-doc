"""
Importa los archivos TXT del Padrón Reducido SUNAT a CockroachDB.

Codificación de origen: ISO-8859-1 (latin-1), separador pipe |.
Se usan batches de 2000 filas, cada uno en su propia transacción,
para respetar el límite de transacciones largas de CockroachDB.
"""
import io
import os
import zipfile
import logging

from psycopg2.extras import execute_values

from db.connection import get_db
from repositories.meta_repository import upsert_meta_ok, upsert_meta_error
from utils.direccion_builder import armar_direccion

logger = logging.getLogger(__name__)

BATCH_SIZE = int(os.getenv("PADRON_BATCH_SIZE", "2000"))


# ── Padrón RUC ────────────────────────────────────────────────────────────────

def _abrir_txt(ruta: str):
    """Abre el archivo TXT o, si la ruta es un ZIP, devuelve el TXT interno como stream."""
    if ruta.lower().endswith(".zip"):
        zf = zipfile.ZipFile(ruta, "r")
        txt_files = [n for n in zf.namelist() if n.lower().endswith(".txt")]
        if not txt_files:
            zf.close()
            raise ValueError(f"No se encontró .txt dentro de {ruta}")
        raw = zf.open(txt_files[0])
        return io.TextIOWrapper(raw, encoding="latin-1", errors="replace"), zf
    else:
        f = open(ruta, encoding="latin-1", errors="replace")
        return f, None


def importar_padron_ruc(ruta: str, hash_archivo: str) -> int:
    """
    Lee el TXT del Padrón Reducido RUC (latin-1, pipe-sep) y hace UPSERT en batches.
    Acepta ruta al TXT o directamente al ZIP (sin extraer a disco).
    Columnas esperadas (validar con `head -5` si SUNAT cambia el formato):
      0:RUC 1:NOMBRE 2:ESTADO 3:CONDICION 4:UBIGEO 5:TIPO_VIA 6:NOMBRE_VIA
      7:COD_ZONA 8:TIPO_ZONA 9:NUMERO 10:INTERIOR 11:LOTE 12:DPTO_ADDR
      13:MANZANA 14:KM 15:FECHA_INSCRIPCION(YYYYMMDD)
    """
    total = 0
    batch = []

    try:
        stream, zf_handle = _abrir_txt(ruta)
        with stream:
            for linea in stream:
                linea = linea.rstrip("\r\n")
                if not linea:
                    continue

                campos = linea.split("|")
                if len(campos) < 16:
                    logger.debug("Línea con %d campos: %.60s", len(campos), linea)
                    continue

                row = _parse_ruc(campos)
                # Saltar header y filas con RUC no numérico
                if not row["ruc"] or not row["ruc"].isdigit():
                    continue

                batch.append(row)

                if len(batch) >= BATCH_SIZE:
                    _upsert_ruc(batch)
                    total += len(batch)
                    batch = []
                    if total % 500_000 == 0:
                        logger.info("Padrón RUC: %s filas procesadas", f"{total:,}")

            if batch:
                _upsert_ruc(batch)
                total += len(batch)

        if zf_handle:
            zf_handle.close()

        upsert_meta_ok("ruc", total, hash_archivo)
        logger.info("Import padrón RUC completo: %s filas", f"{total:,}")
        return total

    except Exception as exc:
        upsert_meta_error("ruc", str(exc))
        raise


# ── Padrón Local Anexo ────────────────────────────────────────────────────────

def importar_padron_local_anexo(ruta: str, hash_archivo: str) -> int:
    """
    Lee el TXT del Padrón Local Anexo (latin-1, pipe-sep) y hace UPSERT en batches.
    Columnas esperadas:
      0:RUC 1:COD_ESTABLECIMIENTO 2:TIPO_ESTABLECIMIENTO 3:UBIGEO 4:TIPO_VIA
      5:NOMBRE_VIA 6:COD_ZONA 7:TIPO_ZONA 8:NUMERO 9:INTERIOR 10:LOTE
      11:DPTO_ADDR 12:MANZANA 13:KM 14:ACTIVIDAD_ECONOMICA
    """
    total = 0
    batch = []

    try:
        stream, zf_handle = _abrir_txt(ruta)
        with stream:
            for linea in stream:
                linea = linea.rstrip("\r\n")
                if not linea:
                    continue

                campos = linea.split("|")
                if len(campos) < 12:
                    continue

                row = _parse_local_anexo(campos)
                if not row["ruc"] or not row["ruc"].isdigit():
                    continue

                batch.append(row)

                if len(batch) >= BATCH_SIZE:
                    _upsert_local_anexo(batch)
                    total += len(batch)
                    batch = []
                    if total % 500_000 == 0:
                        logger.info("Padrón Local Anexo: %s filas procesadas", f"{total:,}")

            if batch:
                _upsert_local_anexo(batch)
                total += len(batch)

        if zf_handle:
            zf_handle.close()

        upsert_meta_ok("local_anexo", total, hash_archivo)
        logger.info("Import padrón local anexo completo: %s filas", f"{total:,}")
        return total

    except Exception as exc:
        upsert_meta_error("local_anexo", str(exc))
        raise


# ── Parsers ───────────────────────────────────────────────────────────────────

def _c(s: str):
    """Limpia un campo: strip y None si vacío o solo guión."""
    v = s.strip()
    return v if v and v != "-" else None


def _fecha(s: str):
    """Convierte YYYYMMDD → YYYY-MM-DD o None."""
    v = (s or "").strip()
    if len(v) == 8 and v.isdigit():
        return f"{v[:4]}-{v[4:6]}-{v[6:8]}"
    return None


def _parse_ruc(c: list) -> dict:
    row = {
        "ruc":                  (c[0] or "").strip() or None,
        "nombre_razon":         _c(c[1]) or "",
        "estado_contribuyente": _c(c[2]),
        "condicion_domicilio":  _c(c[3]),
        "ubigeo":               _c(c[4]),
        "tipo_via":             _c(c[5]),
        "nombre_via":           _c(c[6]),
        "codigo_zona":          _c(c[7]),
        "tipo_zona":            _c(c[8]),
        "numero":               _c(c[9]),
        "interior":             _c(c[10]),
        "lote":                 _c(c[11]),
        "departamento_addr":    _c(c[12]),
        "manzana":              _c(c[13]),
        "kilometro":            _c(c[14]),
        "fecha_inscripcion":    _fecha(c[15]),
    }
    row["direccion_completa"] = armar_direccion(row)
    return row


def _parse_local_anexo(c: list) -> dict:
    # Formato real SUNAT (12 columnas, sin codigo/tipo establecimiento):
    # 0:RUC 1:UBIGEO 2:TIPO_VIA 3:NOMBRE_VIA 4:COD_ZONA 5:TIPO_ZONA
    # 6:NUMERO 7:KILOMETRO 8:INTERIOR 9:LOTE 10:DEPARTAMENTO 11:MANZANA
    row = {
        "ruc":                   (c[0] or "").strip() or None,
        "codigo_establecimiento": "0000",
        "tipo_establecimiento":  None,
        "ubigeo":                _c(c[1]),
        "tipo_via":              _c(c[2]),
        "nombre_via":            _c(c[3]),
        "codigo_zona":           _c(c[4]),
        "tipo_zona":             _c(c[5]),
        "numero":                _c(c[6]),
        "kilometro":             _c(c[7]),
        "interior":              _c(c[8]),
        "lote":                  _c(c[9]),
        "departamento_addr":     _c(c[10]),
        "manzana":               _c(c[11]) if len(c) > 11 else None,
        "actividad_economica":   None,
    }
    row["direccion_completa"] = armar_direccion(row)
    return row


# ── UPSERT helpers ────────────────────────────────────────────────────────────

def _upsert_ruc(batch: list):
    rows = [
        (
            r["ruc"], r["nombre_razon"], r["estado_contribuyente"],
            r["condicion_domicilio"], r["ubigeo"], r["tipo_via"],
            r["nombre_via"], r["codigo_zona"], r["tipo_zona"],
            r["numero"], r["interior"], r["lote"],
            r["departamento_addr"], r["manzana"], r["kilometro"],
            r["fecha_inscripcion"], r["direccion_completa"],
        )
        for r in batch
    ]
    with get_db() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO padron_reducido_ruc
                  (ruc, nombre_razon, estado_contribuyente, condicion_domicilio,
                   ubigeo, tipo_via, nombre_via, codigo_zona, tipo_zona,
                   numero, interior, lote, departamento_addr, manzana, kilometro,
                   fecha_inscripcion, direccion_completa)
                VALUES %s
                ON CONFLICT (ruc) DO UPDATE SET
                  nombre_razon          = EXCLUDED.nombre_razon,
                  estado_contribuyente  = EXCLUDED.estado_contribuyente,
                  condicion_domicilio   = EXCLUDED.condicion_domicilio,
                  ubigeo                = EXCLUDED.ubigeo,
                  tipo_via              = EXCLUDED.tipo_via,
                  nombre_via            = EXCLUDED.nombre_via,
                  codigo_zona           = EXCLUDED.codigo_zona,
                  tipo_zona             = EXCLUDED.tipo_zona,
                  numero                = EXCLUDED.numero,
                  interior              = EXCLUDED.interior,
                  lote                  = EXCLUDED.lote,
                  departamento_addr     = EXCLUDED.departamento_addr,
                  manzana               = EXCLUDED.manzana,
                  kilometro             = EXCLUDED.kilometro,
                  fecha_inscripcion     = EXCLUDED.fecha_inscripcion,
                  direccion_completa    = EXCLUDED.direccion_completa,
                  fecha_actualizacion   = now()
                """,
                rows,
                page_size=BATCH_SIZE,
            )


def _upsert_local_anexo(batch: list):
    # Deduplicar por (ruc, codigo_establecimiento) dentro del batch
    seen = {}
    for r in batch:
        seen[(r["ruc"], r["codigo_establecimiento"])] = r
    batch = list(seen.values())

    rows = [
        (
            r["ruc"], r["codigo_establecimiento"], r["tipo_establecimiento"],
            r["ubigeo"], r["tipo_via"], r["nombre_via"],
            r["codigo_zona"], r["tipo_zona"], r["numero"],
            r["interior"], r["lote"], r["departamento_addr"],
            r["manzana"], r["kilometro"], r["actividad_economica"],
            r["direccion_completa"],
        )
        for r in batch
    ]
    with get_db() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO padron_reducido_local_anexo
                  (ruc, codigo_establecimiento, tipo_establecimiento,
                   ubigeo, tipo_via, nombre_via, codigo_zona, tipo_zona,
                   numero, interior, lote, departamento_addr, manzana, kilometro,
                   actividad_economica, direccion_completa)
                VALUES %s
                ON CONFLICT (ruc, codigo_establecimiento) DO UPDATE SET
                  tipo_establecimiento = EXCLUDED.tipo_establecimiento,
                  ubigeo               = EXCLUDED.ubigeo,
                  tipo_via             = EXCLUDED.tipo_via,
                  nombre_via           = EXCLUDED.nombre_via,
                  codigo_zona          = EXCLUDED.codigo_zona,
                  tipo_zona            = EXCLUDED.tipo_zona,
                  numero               = EXCLUDED.numero,
                  interior             = EXCLUDED.interior,
                  lote                 = EXCLUDED.lote,
                  departamento_addr    = EXCLUDED.departamento_addr,
                  manzana              = EXCLUDED.manzana,
                  kilometro            = EXCLUDED.kilometro,
                  actividad_economica  = EXCLUDED.actividad_economica,
                  direccion_completa   = EXCLUDED.direccion_completa,
                  fecha_actualizacion  = now()
                """,
                rows,
                page_size=BATCH_SIZE,
            )
