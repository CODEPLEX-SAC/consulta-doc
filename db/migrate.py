"""
Ejecuta las migraciones SQL en orden.
Lleva un registro en la tabla _migrations para no reaplicar migraciones ya ejecutadas.
"""
import logging
from pathlib import Path
from db.connection import get_db

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def run_migrations():
    migrations = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migrations:
        logger.warning("No se encontraron archivos de migración en %s", MIGRATIONS_DIR)
        return

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS _migrations (
                    filename   VARCHAR(200) PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT now()
                )
            """)
        conn.commit()

    for mf in migrations:
        filename = mf.name
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM _migrations WHERE filename = %s", (filename,))
                if cur.fetchone():
                    continue

                logger.info("Aplicando migración: %s", filename)
                cur.execute(mf.read_text(encoding="utf-8"))
                cur.execute("INSERT INTO _migrations (filename) VALUES (%s)", (filename,))

            logger.info("Migración aplicada: %s", filename)

    logger.info("Todas las migraciones aplicadas")
