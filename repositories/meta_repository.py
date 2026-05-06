"""Acceso a la tabla padron_meta (estado del último import)."""
from db.connection import get_db


def get_meta(padron_tipo: str):
    """Retorna los metadatos del padrón indicado o None."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT padron_tipo, ultima_descarga, ultima_importacion,
                       filas_importadas, estado_ultimo_import, mensaje_error, hash_archivo
                FROM padron_meta
                WHERE padron_tipo = %s
                """,
                (padron_tipo,),
            )
            row = cur.fetchone()
            if not row:
                return None
            cols = [
                "padron_tipo", "ultima_descarga", "ultima_importacion",
                "filas_importadas", "estado_ultimo_import", "mensaje_error", "hash_archivo",
            ]
            return dict(zip(cols, row))


def upsert_meta_inicio(padron_tipo: str):
    """Marca el inicio de un proceso de descarga/import."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO padron_meta (padron_tipo, ultima_descarga, estado_ultimo_import)
                VALUES (%s, now(), 'in_progress')
                ON CONFLICT (padron_tipo) DO UPDATE SET
                  ultima_descarga      = now(),
                  estado_ultimo_import = 'in_progress',
                  mensaje_error        = NULL
                """,
                (padron_tipo,),
            )


def upsert_meta_ok(padron_tipo: str, filas: int, hash_archivo: str):
    """Registra un import exitoso."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO padron_meta
                  (padron_tipo, ultima_importacion, filas_importadas,
                   estado_ultimo_import, hash_archivo)
                VALUES (%s, now(), %s, 'ok', %s)
                ON CONFLICT (padron_tipo) DO UPDATE SET
                  ultima_importacion   = now(),
                  filas_importadas     = %s,
                  estado_ultimo_import = 'ok',
                  hash_archivo         = %s
                """,
                (padron_tipo, filas, hash_archivo, filas, hash_archivo),
            )


def upsert_meta_error(padron_tipo: str, mensaje: str):
    """Registra un import fallido."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO padron_meta (padron_tipo, estado_ultimo_import, mensaje_error)
                VALUES (%s, 'error', %s)
                ON CONFLICT (padron_tipo) DO UPDATE SET
                  estado_ultimo_import = 'error',
                  mensaje_error        = %s
                """,
                (padron_tipo, mensaje[:500], mensaje[:500]),
            )


def upsert_meta_skipped(padron_tipo: str):
    """Registra que el padrón no cambió (hash idéntico)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO padron_meta (padron_tipo, ultima_descarga, estado_ultimo_import)
                VALUES (%s, now(), 'ok')
                ON CONFLICT (padron_tipo) DO UPDATE SET
                  ultima_descarga      = now(),
                  estado_ultimo_import = 'ok'
                """,
                (padron_tipo,),
            )
