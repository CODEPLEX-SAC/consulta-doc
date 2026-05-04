"""
SUNAT scraper — fuente primaria para RUC, DNI y búsqueda por razón social.
Replica el flujo real del navegador: sesión → numRnd → consulta.
"""
import re
import requests
from bs4 import BeautifulSoup

SUNAT_URL = "https://e-consultaruc.sunat.gob.pe/cl-ti-itmrconsruc/jcrS00Alias"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-PE,es;q=0.9",
    "Referer": SUNAT_URL,
}

TIMEOUT = 15


def _clean(text: str) -> str:
    return " ".join(text.replace("\n", " ").split())


def _get_num_rnd(session: requests.Session) -> str:
    resp = session.post(
        f"{SUNAT_URL}?accion=consPorTipdoc&nrodoc=12345678&contexto=ti-it&modo=1&tipdoc=1",
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    match = re.search(r'name="numRnd" value="(.*?)"', resp.text)
    return match.group(1) if match else ""


def _extract_campos(soup: BeautifulSoup) -> dict:
    """
    Extrae TODOS los pares label → valor del HTML de SUNAT.

    SUNAT usa tres estructuras distintas en la misma página:
      1. col-sm-5 (label h4) + col-sm-7 (valor en <p> o <h4>)  — campos simples
      2. col-sm-3 (label h4) + col-sm-3 (valor en <p>)          — campos compactos (2 por fila)
      3. col-sm-5 (label h4) + col-sm-7 (valor en <table>)      — campos con lista

    Estrategia: recorrer cada h4.list-group-item-heading,
    buscar el siguiente div hermano y extraer el valor.
    """
    campos: dict = {}

    for h4 in soup.find_all("h4", class_="list-group-item-heading"):
        label = _clean(h4.get_text()).rstrip(":")
        if not label:
            continue

        parent_div = h4.parent  # col-sm-X
        next_div = parent_div.find_next_sibling("div")
        if not next_div:
            continue

        # ── Valor en <p> ────────────────────────────────────────────
        p_tag = next_div.find("p")
        if p_tag:
            value = _clean(p_tag.get_text())
            campos[label.lower()] = value if value not in ("-", "") else None
            continue

        # ── Valor en <table> (lista de ítems) ───────────────────────
        table = next_div.find("table")
        if table:
            rows = [
                _clean(tr.get_text())
                for tr in table.find_all("tr")
                if _clean(tr.get_text())
            ]
            campos[label.lower()] = rows if rows else None
            continue

        # ── Valor en otro <h4> (ej: "RUC - Razón Social") ───────────
        h4_val = next_div.find("h4")
        if h4_val:
            value = _clean(h4_val.get_text())
            campos[label.lower()] = value if value else None

    return campos


def _get(campos: dict, *keys) -> any:
    """Busca el primer campo cuyo label contenga alguna de las claves dadas."""
    for key in keys:
        key_lower = key.lower()
        for label, value in campos.items():
            if key_lower in label:
                return value
    return None


class SunatScraper:

    # ── RUC ──────────────────────────────────────────────────────────

    def consultar_ruc(self, ruc: str) -> dict:
        with requests.Session() as s:
            s.get(SUNAT_URL, headers=HEADERS, timeout=TIMEOUT)
            num_rnd = _get_num_rnd(s)

            resp = s.post(
                f"{SUNAT_URL}?accion=consPorRuc&nroRuc={ruc}"
                f"&contexto=ti-it&modo=1&numRnd={num_rnd}",
                headers=HEADERS,
                timeout=TIMEOUT,
            )
            resp.raise_for_status()

            if "no se encontr" in resp.text.lower():
                raise ValueError(f"RUC {ruc} no encontrado en SUNAT")

            return self._parse_ruc(resp.text, ruc)

    def _parse_ruc(self, html: str, ruc: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        campos = _extract_campos(soup)

        # ── RUC + Razón Social del encabezado ─────────────────────
        ruc_header = _get(campos, "número de ruc", "numero de ruc")
        razon_social = None
        ruc_num = ruc

        if ruc_header and " - " in str(ruc_header):
            parts = str(ruc_header).split(" - ", 1)
            ruc_num = parts[0].strip()
            razon_social = parts[1].strip()

        # Fallback: buscar en los h4 directamente
        if not razon_social:
            for h4 in soup.find_all("h4", class_="list-group-item-heading"):
                text = _clean(h4.get_text())
                if " - " in text and re.match(r"^\d{11}", text):
                    parts = text.split(" - ", 1)
                    ruc_num = parts[0].strip()
                    razon_social = parts[1].strip()
                    break

        if not razon_social:
            raise ValueError("No se encontró razón social en la respuesta de SUNAT")

        # ── Actividades económicas como lista ─────────────────────
        actividades_raw = _get(campos, "actividad(es) económica", "actividades económica", "actividad economica")

        return {
            "ruc": ruc_num,
            "razon_social": razon_social,
            "nombre_comercial": _get(campos, "nombre comercial"),
            "tipo_contribuyente": _get(campos, "tipo contribuyente"),
            "estado": _get(campos, "estado del contribuyente"),
            "condicion": _get(campos, "condición del contribuyente", "condicion del contribuyente"),
            "fecha_inscripcion": _get(campos, "fecha de inscripción", "fecha de inscripcion"),
            "fecha_inicio_actividades": _get(campos, "fecha de inicio de actividades", "inicio de actividades"),
            "direccion": _get(campos, "domicilio fiscal"),
            "actividad_comercio_exterior": _get(campos, "actividad comercio exterior"),
            "sistema_emision_comprobante": _get(campos, "sistema emisión de comprobante", "sistema emision de comprobante"),
            "sistema_contabilidad": _get(campos, "sistema contabilidad"),
            "actividades_economicas": actividades_raw,
            "comprobantes_pago": _get(campos, "comprobantes de pago"),
            "sistema_emision_electronica": _get(campos, "sistema de emisión electrónica", "sistema de emision electronica"),
            "emisor_electronico_desde": _get(campos, "emisor electrónico desde", "emisor electronico desde"),
            "comprobantes_electronicos": _get(campos, "comprobantes electrónicos", "comprobantes electronicos"),
            "afiliado_ple_desde": _get(campos, "afiliado al ple"),
            "padrones": _get(campos, "padrones"),
        }

    # ── DNI ──────────────────────────────────────────────────────────

    def consultar_dni(self, dni: str) -> dict:
        with requests.Session() as s:
            s.get(SUNAT_URL, headers=HEADERS, timeout=TIMEOUT)

            payload = {
                "accion": "consPorTipdoc",
                "razSoc": "", "nroRuc": "",
                "nrodoc": dni,
                "contexto": "ti-it", "modo": "1",
                "search1": "", "rbtnTipo": "2",
                "tipdoc": "1", "search2": dni,
                "search3": "", "codigo": "",
            }

            resp = s.post(SUNAT_URL, data=payload, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()

            if "no se encontr" in resp.text.lower():
                raise ValueError(f"DNI {dni} no encontrado en SUNAT")

            return self._parse_dni(resp.text, dni)

    def _parse_dni(self, html: str, dni: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")

        item = soup.select_one(".aRucs")
        if not item:
            raise ValueError(f"DNI {dni} no encontrado en SUNAT")

        h4s = item.find_all("h4")
        nombre = _clean(h4s[1].get_text()) if len(h4s) > 1 else _clean(h4s[0].get_text())

        estado_tag = item.select_one("span.text-success, span.text-danger")
        estado = estado_tag.get_text(strip=True) if estado_tag else "DESCONOCIDO"

        return {"dni": dni, "nombre": nombre, "estado": estado}

    # ── RAZÓN SOCIAL ─────────────────────────────────────────────────

    def consultar_razon_social(self, razon_social: str) -> list:
        with requests.Session() as s:
            s.get(SUNAT_URL, headers=HEADERS, timeout=TIMEOUT)
            num_rnd = _get_num_rnd(s)

            payload = {
                "accion": "consPorRazonSoc",
                "razSoc": razon_social,
                "nroRuc": "", "nrodoc": "",
                "contexto": "ti-it", "modo": "1",
                "numRnd": num_rnd,
                "search1": razon_social,
                "rbtnTipo": "1", "tipdoc": "1",
                "search2": "", "search3": "", "codigo": "",
            }

            resp = s.post(SUNAT_URL, data=payload, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()

            if "no se encontr" in resp.text.lower():
                return []

            return self._parse_lista(resp.text)

    def _parse_lista(self, html: str) -> list:
        soup = BeautifulSoup(html, "html.parser")
        results = []

        for item in soup.select(".aRucs"):
            h4s = item.find_all("h4")
            if not h4s:
                continue

            ruc_raw = re.sub(r"^RUC[:\s]+", "", _clean(h4s[0].get_text())).strip()
            nombre = _clean(h4s[1].get_text()) if len(h4s) > 1 else ""

            estado_tag = item.select_one("span.text-success, span.text-danger")
            estado = estado_tag.get_text(strip=True) if estado_tag else "DESCONOCIDO"

            results.append({"ruc": ruc_raw, "razon_social": nombre, "estado": estado})

        return results
