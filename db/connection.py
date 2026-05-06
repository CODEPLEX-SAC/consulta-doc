"""
Pool de conexiones a CockroachDB (compatible 100% con PostgreSQL wire protocol).
Todas las credenciales se leen desde variables de entorno.
"""
import os
import json
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_pool = None


def init_pool():
    global _pool
    import psycopg2
    import psycopg2.pool
    import psycopg2.extras

    _pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=int(os.getenv("DB_POOL_MIN", "2")),
        maxconn=int(os.getenv("DB_POOL_MAX", "20")),
        host=os.getenv("DB_HOST", "144.217.163.120"),
        port=int(os.getenv("DB_PORT", "26257")),
        dbname=os.getenv("DB_NAME", "consulta_sunat"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        sslmode=os.getenv("DB_SSL_MODE", "require"),
        connect_timeout=15,
    )

    # Registrar decodificador JSON para columnas JSONB
    psycopg2.extras.register_default_jsonb(globally=True, loads=json.loads)

    logger.info("CockroachDB pool inicializado (%s:%s/%s)",
                os.getenv("DB_HOST"), os.getenv("DB_PORT"), os.getenv("DB_NAME"))
    return _pool


def close_pool():
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None
        logger.info("CockroachDB pool cerrado")


def is_available() -> bool:
    return _pool is not None


@contextmanager
def get_db():
    """Context manager: obtiene una conexión del pool, commitea o rollbackea y la devuelve."""
    if _pool is None:
        raise RuntimeError("DB pool no inicializado")
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)
