"""Caché de respuestas finales en la tabla cache_consulta (CockroachDB)."""
import json
import logging
from datetime import datetime, timedelta
from db.connection import get_db

logger = logging.getLogger(__name__)


def get_cache(rucdni: str):
    """Retorna el payload cacheado si existe y no ha expirado, o None."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM cache_consulta WHERE rucdni = %s AND expira_en > now()",
                (rucdni,),
            )
            row = cur.fetchone()
            if not row:
                return None
            payload = row[0]
            if isinstance(payload, str):
                payload = json.loads(payload)
            return payload


def set_cache(rucdni: str, payload: dict, ttl_hours: int = 24, fuentes: str = None):
    """Guarda o actualiza una entrada en el caché."""
    expira_en = datetime.utcnow() + timedelta(hours=ttl_hours)
    payload_json = json.dumps(payload, ensure_ascii=False, default=str)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cache_consulta (rucdni, payload, fuentes, expira_en)
                VALUES (%s, %s::jsonb, %s, %s)
                ON CONFLICT (rucdni) DO UPDATE SET
                  payload   = EXCLUDED.payload,
                  fuentes   = EXCLUDED.fuentes,
                  expira_en = EXCLUDED.expira_en,
                  creado_en = now()
                """,
                (rucdni, payload_json, fuentes, expira_en),
            )


def limpiar_expirado() -> int:
    """Elimina entradas expiradas; retorna cuántas se eliminaron."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM cache_consulta WHERE expira_en < now()")
            return cur.rowcount
