"""
consulta-doc — Microservicio de consulta RUC / DNI / Razón Social.

Failover automático:
  RUC/DNI      → SUNAT → PSE Peru → (DNI también ELDNI)
  Razón Social → SUNAT

Endpoint:
  GET /Servicios/consultaDocumento/{documento}

Ejemplos:
  GET /Servicios/consultaDocumento/20539782232   → RUC empresa
  GET /Servicios/consultaDocumento/72098347      → DNI persona
  GET /Servicios/consultaDocumento/GLORIA        → búsqueda por razón social
"""
import os
import re
import asyncio
import webbrowser
from threading import Timer
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from scrapers.sunat import SunatScraper
from scrapers.pseperu import PsePeruScraper
from scrapers.eldni import ElDniScraper

# ── Config desde entorno ──────────────────────────────────────────────

PORT = int(os.getenv("PORT", "8076"))
NODE_ENV = os.getenv("NODE_ENV", "development")

_cors_env = os.getenv("CORS_ORIGINS", "*")
CORS_ORIGINS = (
    ["*"]
    if _cors_env.strip() == "*"
    else ["*"] + [o.strip() for o in _cors_env.split(",") if o.strip()]
)

# ── App ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="consulta-doc",
    description=(
        "Microservicio de consulta pública peruana con failover automático.\n\n"
        "- **11 dígitos** → RUC  (SUNAT → PSE Peru)\n"
        "- **8 dígitos**  → DNI  (SUNAT → PSE Peru → ELDNI)\n"
        "- **texto**      → Razón Social (SUNAT, devuelve lista)"
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

# ── Scrapers y thread pool ───────────────────────────────────────────

_pool = ThreadPoolExecutor(max_workers=20)
_sunat = SunatScraper()
_pseperu = PsePeruScraper()
_eldni = ElDniScraper()


# ── Helpers ──────────────────────────────────────────────────────────

def _detectar_tipo(documento: str) -> str:
    if re.match(r"^\d{11}$", documento):
        return "ruc"
    if re.match(r"^\d{8}$", documento):
        return "dni"
    return "razon_social"


async def _run(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_pool, fn, *args)


# ── Endpoint principal ───────────────────────────────────────────────

@app.get(
    "/Servicios/consultaDocumento/{documento}",
    summary="Consultar RUC, DNI o Razón Social",
    tags=["Servicios"],
)
async def consultar_documento(documento: str):
    """
    Detecta automáticamente el tipo de documento y aplica failover:

    | Tipo          | Detección     | Fuentes en orden             |
    |---------------|---------------|------------------------------|
    | RUC           | 11 dígitos    | SUNAT → PSE Peru             |
    | DNI           | 8 dígitos     | SUNAT → PSE Peru → ELDNI     |
    | Razón Social  | texto libre   | SUNAT (lista de resultados)  |
    """
    doc = documento.strip().upper()
    tipo = _detectar_tipo(doc)
    errors = []

    # ── 1. SUNAT (primario) ───────────────────────────────────────────
    try:
        if tipo == "ruc":
            data = await _run(_sunat.consultar_ruc, doc)
        elif tipo == "dni":
            data = await _run(_sunat.consultar_dni, doc)
        else:
            data = await _run(_sunat.consultar_razon_social, documento.strip())

        return {"ok": True, "tipo": tipo, "fuente": "SUNAT", "data": data}

    except Exception as e:
        errors.append(f"SUNAT: {e}")

    # ── 2. PSE Peru (fallback — RUC y DNI) ───────────────────────────
    if tipo in ("ruc", "dni"):
        try:
            data = await _run(_pseperu.consultar, doc)
            return {"ok": True, "tipo": tipo, "fuente": "PSEPERU", "data": data}
        except Exception as e:
            errors.append(f"PSEPERU: {e}")

    # ── 3. ELDNI (fallback — solo DNI) ───────────────────────────────
    if tipo == "dni":
        try:
            data = await _run(_eldni.consultar_dni, doc)
            return {"ok": True, "tipo": tipo, "fuente": "ELDNI", "data": data}
        except Exception as e:
            errors.append(f"ELDNI: {e}")

    raise HTTPException(
        status_code=503,
        detail={
            "ok": False,
            "tipo": tipo,
            "documento": documento,
            "errors": errors,
            "message": "Todas las fuentes están no disponibles",
        },
    )


# ── Health ───────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def health():
    return {
        "ok": True,
        "api": "consulta-doc",
        "version": "1.0.0",
        "environment": NODE_ENV,
        "endpoint": "GET /Servicios/consultaDocumento/{documento}",
        "fuentes": ["SUNAT", "PSEPERU", "ELDNI"],
        "docs": "/docs",
    }


# ── Startup ──────────────────────────────────────────────────────────

@app.on_event("startup")
async def on_startup():
    proto = "https" if os.getenv("CERT") else "http"
    base = f"{proto}://localhost:{PORT}"
    print(f"\n  [OK] consulta-doc {NODE_ENV} -> {base}")
    print(f"  Swagger: {base}/docs\n")
    if NODE_ENV != "production":
        Timer(1.0, lambda: webbrowser.open(f"{base}/docs")).start()
