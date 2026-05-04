"""
ELDNI scraper — fallback 2, exclusivo para DNI.
"""
import requests
from bs4 import BeautifulSoup

ELDNI_URL = "https://eldni.com/pe/buscar-datos-por-dni"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-PE,es;q=0.9",
    "Referer": ELDNI_URL,
}

TIMEOUT = 10


class ElDniScraper:

    def consultar_dni(self, dni: str) -> dict:
        with requests.Session() as s:
            resp = s.get(ELDNI_URL, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            token_input = soup.find("input", {"name": "_token"})
            if not token_input:
                raise ValueError("No se pudo obtener CSRF token de ELDNI")

            resp = s.post(
                ELDNI_URL,
                data={"_token": token_input.get("value"), "dni": dni},
                headers=HEADERS,
                timeout=TIMEOUT,
            )
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            nombre_tag = soup.find("h5")
            if not nombre_tag:
                raise ValueError(f"DNI {dni} no encontrado en ELDNI")

            return {
                "dni": dni,
                "nombre": nombre_tag.get_text(strip=True),
                "estado": "NO DISPONIBLE",
            }
