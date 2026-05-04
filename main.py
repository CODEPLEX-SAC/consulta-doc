"""
consulta-doc — Microservicio de consulta RUC / DNI.

Failover automático:
  RUC  → SUNAT → PSE Peru
  DNI  → SUNAT → PSE Peru → ELDNI

Endpoint:
  GET /Servicios/consultaDocumento/{documento}

La respuesta replica exactamente la estructura que consumen
los sistemas internos (ServiceController.php de backend-codeplex).
"""
import os
import re
import asyncio
import webbrowser
from threading import Timer
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from scrapers.sunat import SunatScraper
from scrapers.pseperu import PsePeruScraper
from scrapers.eldni import ElDniScraper
from scrapers.ubigeo import from_address as ubigeo_from_address

# ── Config ────────────────────────────────────────────────────────────

PORT     = int(os.getenv("PORT", "8076"))
NODE_ENV = os.getenv("NODE_ENV", "development")

# ── App ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="consulta-doc",
    description=(
        "Microservicio de consulta pública peruana.\n\n"
        "- **11 dígitos** → RUC  (SUNAT → PSE Peru)\n"
        "- **8 dígitos**  → DNI  (SUNAT → PSE Peru → ELDNI)"
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

# ── Scrapers ──────────────────────────────────────────────────────────

_pool   = ThreadPoolExecutor(max_workers=20)
_sunat  = SunatScraper()
_pse    = PsePeruScraper()
_eldni  = ElDniScraper()


# ── Formatters ────────────────────────────────────────────────────────

def _format_ruc(raw: dict, fuente: str) -> dict:
    """
    Convierte la respuesta cruda del scraper SUNAT al formato
    estándar consumido por backend-codeplex y demás clientes.
    """
    estado_raw   = (raw.get("estado")   or "").upper()
    condicion_raw = (raw.get("condicion") or "").upper()

    activo      = 1 if "ACTIVO" in estado_raw else 0
    estadosunat = 1 if "HABIDO" in condicion_raw else 2

    direccion = raw.get("direccion")
    ubigeo    = raw.get("ubigeo") or ubigeo_from_address(direccion)

    return {
        "success": True,
        "fuente": fuente,
        "data": {
            "rucdni":      raw.get("ruc"),
            "nombrerazon": raw.get("razon_social"),
            "activo":      activo,
            "estadosunat": estadosunat,
            "direccion":   direccion,
            "ubigeo":      ubigeo,
            "estado":      "ACTIVO" if activo      else "INHABILITADO",
            "condicion":   "HABIDO" if estadosunat == 1 else "DE BAJA",
        },
    }


def _format_dni(raw: dict, fuente: str) -> dict:
    """
    Convierte la respuesta cruda del scraper al formato estándar.
    SUNAT devuelve el nombre completo; se separa con la convención
    RENIEC: APELLIDO_PATERNO APELLIDO_MATERNO NOMBRE(S).
    """
    nombre_completo = (raw.get("nombre") or "").strip()
    partes = nombre_completo.split()

    if len(partes) >= 3:
        ape_paterno = partes[0]
        ape_materno = partes[1]
        nombres     = " ".join(partes[2:])
    elif len(partes) == 2:
        ape_paterno = partes[0]
        ape_materno = None
        nombres     = partes[1]
    else:
        ape_paterno = None
        ape_materno = None
        nombres     = nombre_completo

    apellidos = " ".join(p for p in [ape_paterno, ape_materno] if p)
    estado_raw = (raw.get("estado") or "ACTIVO").upper()
    activo = 0 if "BAJA" in estado_raw else 1

    return {
        "success": True,
        "fuente": fuente,
        "data": {
            "rucdni":      raw.get("dni"),
            "nombres":     nombres   or None,
            "apellidos":   apellidos or None,
            "nombrerazon": nombre_completo or None,
            "direccion":   raw.get("direccion"),
            "ubigeo":      raw.get("ubigeo"),
            "activo":      activo,
            "estadosunat": 1,  # si fue encontrado asumimos HABIDO
        },
    }


def _format_pseperu(raw: dict) -> dict:
    """
    PSE Peru ya devuelve el formato estándar (mismo endpoint path).
    Normaliza y garantiza los campos requeridos.
    """
    # Si ya viene en formato { success, data }
    if isinstance(raw, dict) and "data" in raw:
        return raw

    # Si viene como objeto plano, lo envolvemos
    return {"success": True, "fuente": "PSEPERU", "data": raw}


async def _run(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_pool, fn, *args)


# ── Endpoint ──────────────────────────────────────────────────────────

@app.get(
    "/Servicios/consultaDocumento/{documento}",
    summary="Consultar RUC o DNI",
    tags=["Servicios"],
    response_description="Datos del contribuyente en formato estándar",
)
async def consultar_documento(documento: str):
    """
    Detecta el tipo por longitud y ejecuta el failover:

    | Longitud | Tipo | Cadena de fuentes           |
    |----------|------|-----------------------------|
    | 11       | RUC  | SUNAT → PSE Peru            |
    | 8        | DNI  | SUNAT → PSE Peru → ELDNI    |
    | otro     | —    | 400 Bad Request             |
    """
    doc = documento.strip()

    if not re.match(r"^\d{8}$|^\d{11}$", doc):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Número de documento no válido. Debe tener 8 (DNI) o 11 (RUC) dígitos.",
            },
        )

    tipo   = "ruc" if len(doc) == 11 else "dni"
    errors = []

    # ── 1. SUNAT ─────────────────────────────────────────────────────
    try:
        if tipo == "ruc":
            raw = await _run(_sunat.consultar_ruc, doc)
            return _format_ruc(raw, "SUNAT")
        else:
            raw = await _run(_sunat.consultar_dni, doc)
            return _format_dni(raw, "SUNAT")
    except Exception as e:
        errors.append(f"SUNAT: {e}")

    # ── 2. PSE Peru ───────────────────────────────────────────────────
    try:
        raw = await _run(_pse.consultar, doc)
        return _format_pseperu(raw)
    except Exception as e:
        errors.append(f"PSEPERU: {e}")

    # ── 3. ELDNI (solo DNI) ───────────────────────────────────────────
    if tipo == "dni":
        try:
            raw = await _run(_eldni.consultar_dni, doc)
            return _format_dni(raw, "ELDNI")
        except Exception as e:
            errors.append(f"ELDNI: {e}")

    return JSONResponse(
        status_code=503,
        content={
            "success": False,
            "message": "Todas las fuentes están no disponibles.",
            "errors": errors,
        },
    )


# ── Health ────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def health():
    return {
        "success": True,
        "api": "consulta-doc",
        "version": "1.0.0",
        "environment": NODE_ENV,
        "endpoint": "GET /Servicios/consultaDocumento/{documento}",
        "fuentes": ["SUNAT", "PSEPERU", "ELDNI"],
        "docs": "/docs",
    }


# ── Startup ───────────────────────────────────────────────────────────

@app.on_event("startup")
async def on_startup():
    proto = "https" if os.getenv("CERT") else "http"
    base  = f"{proto}://localhost:{PORT}"
    print(f"\n  [OK] consulta-doc {NODE_ENV} → {base}")
    print(f"  Swagger: {base}/docs\n")
    if NODE_ENV != "production":
        Timer(1.0, lambda: webbrowser.open(f"{base}/docs")).start()
