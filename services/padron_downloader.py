"""
Descarga los Padrones Reducidos de SUNAT usando HTTP streaming.
No carga el ZIP completo en memoria — los archivos son cientos de MB.
"""
import os
import hashlib
import zipfile
import logging
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

_URLS = {
    "ruc": os.getenv(
        "PADRON_RUC_URL",
        "http://www2.sunat.gob.pe/padron_reducido_ruc.zip",
    ),
    "local_anexo": os.getenv(
        "PADRON_LOCAL_ANEXO_URL",
        "https://www.sunat.gob.pe/descargaPRR/padron_reducido_local_anexo.zip",
    ),
}

TMP_DIR = Path(os.getenv("PADRON_TMP_DIR", "/tmp"))
_TIMEOUT = int(os.getenv("PADRON_DOWNLOAD_TIMEOUT_MS", "1800000")) / 1000
_MIN_BYTES = 10 * 1024 * 1024  # 10 MB mínimo
_MAX_RETRIES = 3

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}


def descargar_padron(tipo: str, prev_hash: str = None) -> dict:
    """
    Descarga el padrón del tipo indicado ('ruc' o 'local_anexo').
    Retorna {'skipped': True} si el hash no cambió, o
             {'skipped': False, 'ruta': str, 'hash': str} si hay datos nuevos.
    """
    url = _URLS.get(tipo)
    if not url:
        raise ValueError(f"Tipo de padrón desconocido: {tipo!r}")

    zip_path = TMP_DIR / f"padron_{tipo}.zip"
    txt_path = TMP_DIR / f"padron_{tipo}.txt"

    logger.info("Descargando padrón %s desde %s", tipo, url)
    _download_stream(url, zip_path)

    size = zip_path.stat().st_size
    if size < _MIN_BYTES:
        raise ValueError(
            f"Archivo descargado demasiado pequeño ({size:,} bytes). "
            "Posible error en la descarga."
        )

    nuevo_hash = _sha256(zip_path)
    logger.info("SHA256 padrón %s: %s", tipo, nuevo_hash)

    if prev_hash and nuevo_hash == prev_hash:
        logger.info("Padrón %s sin cambios desde la última descarga", tipo)
        return {"skipped": True, "hash": nuevo_hash}

    # Devolver la ruta del ZIP directamente — el importer lee sin extraer
    return {"skipped": False, "ruta": str(zip_path), "zip": True, "hash": nuevo_hash}


def _download_stream(url: str, dest: Path):
    for intento in range(1, _MAX_RETRIES + 1):
        try:
            with requests.get(
                url, stream=True, headers=_HEADERS, timeout=_TIMEOUT
            ) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
            return
        except Exception as exc:
            logger.warning("Descarga intento %d/%d falló: %s", intento, _MAX_RETRIES, exc)
            if intento == _MAX_RETRIES:
                raise


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _unzip(zip_path: Path, txt_dest: Path):
    with zipfile.ZipFile(zip_path, "r") as zf:
        txt_files = [n for n in zf.namelist() if n.lower().endswith(".txt")]
        if not txt_files:
            raise ValueError(f"No se encontró archivo .txt en {zip_path}")
        with zf.open(txt_files[0]) as src, open(txt_dest, "wb") as dst:
            dst.write(src.read())
    logger.info("Archivo descomprimido: %s", txt_dest)
