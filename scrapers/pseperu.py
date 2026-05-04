"""
PSE Peru API — fallback 1 para RUC y DNI.
Endpoint público: GET /Servicios/consultaDocumento/{documento}
"""
import requests

BASE_URL = "https://backend.pseperu.pe/Servicios/consultaDocumento"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}

TIMEOUT = 10


class PsePeruScraper:

    def consultar(self, documento: str) -> dict:
        resp = requests.get(
            f"{BASE_URL}/{documento}",
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()

        data = resp.json()

        if not data:
            raise ValueError(f"PSE Peru no devolvió datos para {documento}")

        return data
