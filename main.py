"""
consulta-doc — Microservicio de consulta RUC / DNI.

Fuentes de datos:
  1. Caché    → CockroachDB (cache_consulta)          [< 50ms]
  2. Padrón   → CockroachDB (padron_reducido_ruc)     [local, instantáneo]
  3. SUNAT    → Scraper web e-consultaruc.sunat.gob.pe
  4. PSE Peru → API REST externa (fallback)
  5. ELDNI    → Scraper web eldni.com (solo DNI, fallback)

Endpoints principales:
  GET /Servicios/consultaDocumento/{documento}
  GET /Servicios/consultaDocumento/{documento}/anexos
  GET /health
  POST /admin/refresh-padron/{tipo}
  GET  /admin/stats
"""
# Cargar .env PRIMERO, antes de cualquier otro import que use os.getenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import json
import os
import re
import logging
import asyncio
import webbrowser
from datetime import datetime
from threading import Timer
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, Request, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from starlette.responses import Response

from scrapers.sunat import SunatScraper
from scrapers.pseperu import PsePeruScraper
from scrapers.eldni import ElDniScraper
from scrapers.ubigeo import from_address as ubigeo_from_address

# ── DB — importación condicional (el servicio arranca aunque falte psycopg2) ──

_db_available = False
_db_error_msg = ""

try:
    from db.connection import init_pool, close_pool, is_available
    from db.migrate import run_migrations
    from repositories.padron_repository import buscar_por_ruc, buscar_anexos_por_ruc
    from repositories.cache_repository import get_cache, set_cache, limpiar_expirado
    from repositories.meta_repository import get_meta
    from services.padron_downloader import descargar_padron
    from services.padron_importer import importar_padron_ruc, importar_padron_local_anexo
    from jobs.refresh_padrones import refresh_padron as _refresh_padron_job
    from utils.ruc_validator import dni_a_ruc
    _db_imports_ok = True
except ImportError as _e:
    _db_imports_ok = False
    _db_error_msg = str(_e)

# ── Respuesta JSON con caracteres especiales sin escapar ──────────────────────

class UnicodeJSONResponse(Response):
    media_type = "application/json"

    def render(self, content) -> bytes:
        return json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


# ── Config ─────────────────────────────────────────────────────────────────────

PORT          = int(os.getenv("PORT", "8076"))
NODE_ENV      = os.getenv("NODE_ENV", "development")
CACHE_TTL_H   = int(os.getenv("CACHE_TTL_HOURS", "24"))
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("consulta-doc")

# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="consulta-doc",
    description=(
        "Microservicio de consulta pública peruana.\n\n"
        "- **11 dígitos** → RUC  (Padrón SUNAT + scraper)\n"
        "- **8 dígitos**  → DNI  (SUNAT → PSE Peru → ELDNI)"
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

_cors_origins = os.getenv("CORS_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins.split(",") if _cors_origins != "*" else ["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ── Scrapers ───────────────────────────────────────────────────────────────────

_pool   = ThreadPoolExecutor(max_workers=20)
_sunat  = SunatScraper()
_pse    = PsePeruScraper()
_eldni  = ElDniScraper()


async def _run(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_pool, fn, *args)


# ── Auth para admin ────────────────────────────────────────────────────────────

_api_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


async def _require_admin(api_key: str = Depends(_api_key_header)):
    if not ADMIN_API_KEY or api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Clave de administrador inválida")
    return api_key


# ── Helpers de limpieza ────────────────────────────────────────────────────────

# Estados y condiciones oficiales SUNAT (en orden de mayor a menor longitud
# para que el match greedy funcione correctamente)
_ESTADOS = [
    "BAJA PROV. POR OFICIO",
    "SUSPENSION TEMPORAL",
    "BAJA PROVISIONAL",
    "BAJA DEFINITIVA",
    "BAJA DE OFICIO",
    "ACTIVO",
    "INHABILITADO",
]
_CONDICIONES = [
    "NO HALLADO",
    "NO HABIDO",
    "PENDIENTE",
    "HABIDO",
    "NO APLICABLE",
]


def _limpiar_campo(raw: str, opciones: list) -> str:
    """Retorna el término oficial que aparezca al inicio del string crudo."""
    if not raw:
        return None
    texto = raw.strip().upper()
    for opcion in opciones:
        if texto.startswith(opcion):
            return opcion
    # Fallback: todo antes de la primera fecha o paréntesis
    for sep in ("FECHA", "(", " DESDE", " AL "):
        idx = texto.find(sep)
        if idx > 0:
            return texto[:idx].strip()
    return texto


# ── Formatters ─────────────────────────────────────────────────────────────────

def _format_ruc(raw: dict, fuente: str) -> dict:
    estado    = _limpiar_campo(raw.get("estado"),    _ESTADOS)
    condicion = _limpiar_campo(raw.get("condicion"), _CONDICIONES)
    activo      = 1 if estado and "ACTIVO" in estado else 0
    estadosunat = 1 if condicion and "HABIDO" in condicion else 2
    direccion   = raw.get("direccion")
    ubigeo      = raw.get("ubigeo") or ubigeo_from_address(direccion)

    return {
        "success": True,
        "data": {
            "rucdni":      raw.get("ruc"),
            "nombrerazon": raw.get("razon_social"),
            "activo":      activo,
            "estadosunat": estadosunat,
            "direccion":   direccion,
            "ubigeo":      ubigeo,
            "estado":      estado,
            "condicion":   condicion,
        },
    }


def _format_dni(raw: dict, fuente: str) -> dict:
    nombre_completo = (raw.get("nombre") or "").strip()
    partes = nombre_completo.split()
    if len(partes) >= 3:
        ape_paterno, ape_materno, nombres = partes[0], partes[1], " ".join(partes[2:])
    elif len(partes) == 2:
        ape_paterno, ape_materno, nombres = partes[0], None, partes[1]
    else:
        ape_paterno = ape_materno = None
        nombres = nombre_completo

    apellidos  = " ".join(p for p in [ape_paterno, ape_materno] if p)
    estado_raw = (raw.get("estado") or "ACTIVO").upper()
    activo     = 0 if "BAJA" in estado_raw else 1

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
            "estadosunat": 1,
        },
    }


def _format_pseperu(raw: dict) -> dict:
    if isinstance(raw, dict) and "data" in raw:
        inner     = raw["data"]
        estado    = _limpiar_campo(inner.get("estado"),    _ESTADOS)
        condicion = _limpiar_campo(inner.get("condicion"), _CONDICIONES)
        activo      = 1 if estado and "ACTIVO" in estado else 0
        estadosunat = 1 if condicion and "HABIDO" in condicion else 2
        return {
            "success": True,
            "data": {
                "rucdni":      inner.get("rucdni"),
                "nombrerazon": inner.get("nombrerazon"),
                "activo":      activo,
                "estadosunat": estadosunat,
                "direccion":   inner.get("direccion"),
                "ubigeo":      inner.get("ubigeo"),
                "estado":      estado,
                "condicion":   condicion,
            },
        }
    return {"success": True, "data": raw}


def _format_from_padron(padron: dict) -> dict:
    """Construye una respuesta usando solo datos del Padrón (scraper no disponible)."""
    estado    = _limpiar_campo(padron.get("estado_contribuyente"), _ESTADOS)
    condicion = _limpiar_campo(padron.get("condicion_domicilio"),  _CONDICIONES)
    activo      = 1 if estado and "ACTIVO" in estado else 0
    estadosunat = 1 if condicion and "HABIDO" in condicion else 2

    return {
        "success": True,
        "data": {
            "rucdni":      padron.get("ruc"),
            "nombrerazon": padron.get("nombre_razon"),
            "activo":      activo,
            "estadosunat": estadosunat,
            "direccion":   padron.get("direccion_completa"),
            "ubigeo":      padron.get("ubigeo"),
            "estado":      estado,
            "condicion":   condicion,
        },
    }


def _enrich_with_padron(result: dict, padron: dict) -> dict:
    """Enriquece el resultado del scraper con datos del Padrón (ubigeo + dirección backup)."""
    data = dict(result.get("data") or {})

    # ubigeo SIEMPRE del Padrón (más preciso que el derivado de texto de dirección)
    if padron.get("ubigeo"):
        data["ubigeo"] = padron["ubigeo"]

    # Dirección: usar la del Padrón si el scraper devolvió vacía
    dir_actual = (data.get("direccion") or "").strip()
    if dir_actual in ("", "-") and padron.get("direccion_completa"):
        data["direccion"] = padron["direccion_completa"]

    return {**result, "data": data}


# ── Endpoint principal ─────────────────────────────────────────────────────────

@app.get(
    "/Servicios/consultaDocumento/{documento}",
    summary="Consultar RUC o DNI",
    tags=["Servicios"],
    response_class=UnicodeJSONResponse,
)
async def consultar_documento(documento: str):
    """
    Detecta el tipo por longitud y ejecuta el flujo completo:

    | Longitud | Tipo | Flujo                                             |
    |----------|------|--------------------------------------------------|
    | 11       | RUC  | Caché → Padrón → SUNAT → PSE Peru               |
    | 8        | DNI  | Caché → SUNAT → PSE Peru → ELDNI                |
    """
    doc = documento.strip()

    if not re.match(r"^\d{8}$|^\d{11}$", doc):
        return UnicodeJSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Documento no válido. Debe tener 8 (DNI) o 11 (RUC) dígitos.",
            },
        )

    tipo = "ruc" if len(doc) == 11 else "dni"

    # Para DNI: derivar RUC tipo-10 para la búsqueda en Padrón
    ruc_padron = None
    if tipo == "dni" and _db_available and _db_imports_ok:
        try:
            ruc_padron = dni_a_ruc(doc)
        except Exception:
            pass

    cache_key = doc

    # 1. Caché
    if _db_available:
        try:
            cached = await _run(get_cache, cache_key)
            if cached:
                return UnicodeJSONResponse(content=cached)
        except Exception as exc:
            logger.warning("Cache lookup falló: %s", exc)

    # 2. Padrón (solo para RUC o cuando tenemos el RUC derivado del DNI)
    padron = None
    if _db_available:
        lookup_ruc = doc if tipo == "ruc" else ruc_padron
        if lookup_ruc:
            try:
                padron = await _run(buscar_por_ruc, lookup_ruc)
            except Exception as exc:
                logger.warning("Padrón lookup falló para %s: %s", lookup_ruc, exc)

    errors = []

    # 3. SUNAT scraper
    result = None
    try:
        if tipo == "ruc":
            raw    = await _run(_sunat.consultar_ruc, doc)
            result = _format_ruc(raw, "SUNAT")
        else:
            raw    = await _run(_sunat.consultar_dni, doc)
            result = _format_dni(raw, "SUNAT")
    except Exception as exc:
        errors.append(f"SUNAT: {exc}")

    # 4. PSE Peru (fallback)
    if not result:
        try:
            raw    = await _run(_pse.consultar, doc)
            result = _format_pseperu(raw)
        except Exception as exc:
            errors.append(f"PSEPERU: {exc}")

    # 5. ELDNI (solo DNI, último fallback)
    if not result and tipo == "dni":
        try:
            raw    = await _run(_eldni.consultar_dni, doc)
            result = _format_dni(raw, "ELDNI")
        except Exception as exc:
            errors.append(f"ELDNI: {exc}")

    # 6. Solo Padrón (si todos los scrapers fallaron y tenemos datos locales)
    if not result and padron:
        result = _format_from_padron(padron)

    if not result:
        return UnicodeJSONResponse(
            status_code=503,
            content={
                "success": False,
                "message": "Todas las fuentes no disponibles.",
                "errors":  errors,
            },
        )

    # 7. Enriquecer con datos del Padrón (ubigeo + dirección)
    if padron and tipo == "ruc" and result.get("fuente") != "PADRON":
        result = _enrich_with_padron(result, padron)

    # 8. Guardar en caché
    if _db_available and result.get("success"):
        try:
            await _run(set_cache, cache_key, result, CACHE_TTL_H, None)
        except Exception as exc:
            logger.warning("Cache set falló: %s", exc)

    return UnicodeJSONResponse(content=result)


# ── Endpoint: Establecimientos anexos ─────────────────────────────────────────

@app.get(
    "/Servicios/consultaDocumento/{documento}/anexos",
    summary="Establecimientos anexos de un RUC",
    tags=["Servicios"],
    response_class=UnicodeJSONResponse,
)
async def consultar_anexos(documento: str):
    """Devuelve la lista de establecimientos (casa matriz + sucursales) de un RUC."""
    doc = documento.strip()

    if not re.match(r"^\d{11}$", doc):
        return UnicodeJSONResponse(
            status_code=400,
            content={"success": False, "message": "Se requiere un RUC de 11 dígitos."},
        )

    if not _db_available:
        return UnicodeJSONResponse(
            status_code=503,
            content={"success": False, "message": "Base de datos no disponible."},
        )

    try:
        anexos = await _run(buscar_anexos_por_ruc, doc)
    except Exception as exc:
        logger.error("Error consultando anexos de %s: %s", doc, exc)
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Error consultando establecimientos."},
        )

    return {
        "success": True,
        "data": {
            "rucdni":          doc,
            "establecimientos": anexos,
        },
    }


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"], include_in_schema=False)
def health_simple():
    return {
        "success": True,
        "api":     "consulta-doc",
        "version": "2.0.0",
        "docs":    "/docs",
    }


@app.get("/health", tags=["Health"])
async def health_detallado():
    """Estado del servicio con métricas de los padrones y conexión a DB."""
    resultado = {
        "status":  "ok",
        "api":     "consulta-doc",
        "version": "2.0.0",
        "db":      "disconnected",
    }

    if not _db_available:
        resultado["status"]  = "degraded"
        resultado["warning"] = "DB no disponible — operando solo con scrapers"
        if _db_error_msg:
            resultado["db_error"] = _db_error_msg
        return resultado

    resultado["db"] = "connected"

    for tipo in ("ruc", "local_anexo"):
        try:
            meta = await _run(get_meta, tipo)
            if not meta:
                resultado[f"padron_{tipo}"] = {"estado": "no_cargado"}
                if resultado["status"] == "ok":
                    resultado["status"] = "warning"
                continue

            ultima = meta.get("ultima_importacion")
            antiguedad_h = None
            if ultima:
                delta = datetime.utcnow() - ultima.replace(tzinfo=None)
                antiguedad_h = delta.total_seconds() / 3600

            estado_padron = meta.get("estado_ultimo_import") or "unknown"
            if antiguedad_h is not None and antiguedad_h > 168:  # 7 días
                estado_padron = "desactualizado"
                if resultado["status"] == "ok":
                    resultado["status"] = "warning"

            resultado[f"padron_{tipo}"] = {
                "ultima_actualizacion": ultima.isoformat() + "Z" if ultima else None,
                "antiguedad_horas":     round(antiguedad_h, 1) if antiguedad_h is not None else None,
                "filas":               meta.get("filas_importadas"),
                "estado":              estado_padron,
            }
        except Exception as exc:
            resultado[f"padron_{tipo}"] = {"estado": "error", "mensaje": str(exc)}

    return resultado


# ── Admin: refresh manual ──────────────────────────────────────────────────────

@app.post(
    "/admin/refresh-padron/{tipo}",
    tags=["Admin"],
    dependencies=[Depends(_require_admin)],
)
async def admin_refresh_padron(tipo: str, background_tasks: BackgroundTasks):
    """
    Fuerza la descarga e importación del padrón indicado.
    Requiere header `X-Admin-Key` con la clave configurada en ADMIN_API_KEY.
    El proceso corre en background; usar GET /health para ver el resultado.
    """
    if tipo not in ("ruc", "local_anexo"):
        raise HTTPException(
            status_code=400,
            detail="Tipo debe ser 'ruc' o 'local_anexo'",
        )
    if not _db_available:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")

    def _run_refresh():
        try:
            _refresh_padron_job(tipo)
        except Exception as exc:
            logger.error("Error en refresh background de padrón %s: %s", tipo, exc)

    background_tasks.add_task(_run_refresh)
    return {
        "success": True,
        "mensaje": f"Refresh de padrón '{tipo}' iniciado en background.",
        "hint":    "Consulta GET /health para ver el estado cuando termine.",
    }


# ── Admin: estadísticas ────────────────────────────────────────────────────────

@app.get(
    "/admin/stats",
    tags=["Admin"],
    dependencies=[Depends(_require_admin)],
)
async def admin_stats():
    """Estadísticas de la BD: tamaño de tablas y estado del caché."""
    if not _db_available:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")

    from db.connection import get_db

    def _query():
        with get_db() as conn:
            with conn.cursor() as cur:
                stats = {}

                for tabla in (
                    "padron_reducido_ruc",
                    "padron_reducido_local_anexo",
                    "ubigeos_sunat",
                    "cache_consulta",
                ):
                    try:
                        cur.execute(f"SELECT count(*) FROM {tabla}")
                        stats[tabla] = {"filas": cur.fetchone()[0]}
                    except Exception as exc:
                        stats[tabla] = {"error": str(exc)}

                # Caché: cuántas entradas activas vs expiradas
                try:
                    cur.execute(
                        "SELECT "
                        "  count(*) FILTER (WHERE expira_en > now()) AS activas, "
                        "  count(*) FILTER (WHERE expira_en <= now()) AS expiradas "
                        "FROM cache_consulta"
                    )
                    r = cur.fetchone()
                    stats["cache_consulta"]["activas"]   = r[0]
                    stats["cache_consulta"]["expiradas"] = r[1]
                except Exception:
                    pass

                return stats

    stats = await _run(_query)
    return {"success": True, "stats": stats}


# ── Startup / Shutdown ─────────────────────────────────────────────────────────

@app.on_event("startup")
async def on_startup():
    global _db_available, _db_error_msg

    proto = "https" if os.getenv("CERT") else "http"
    base  = f"{proto}://localhost:{PORT}"
    print(f"\n  [OK] consulta-doc v2.0 {NODE_ENV} → {base}")
    print(f"  Swagger: {base}/docs\n")

    if _db_imports_ok:
        db_host = os.getenv("DB_HOST", "")
        db_name = os.getenv("DB_NAME", "")
        if db_host and db_name and os.getenv("DB_USER") and os.getenv("DB_PASSWORD"):
            try:
                init_pool()
                run_migrations()
                _db_available = True
                logger.info("CockroachDB conectado y migraciones aplicadas")
            except Exception as exc:
                _db_available = False
                _db_error_msg = str(exc)
                logger.warning(
                    "No se pudo conectar a CockroachDB (%s). "
                    "El servicio operará solo con scrapers. Error: %s",
                    db_host, exc,
                )
        else:
            logger.info(
                "Variables DB_HOST/DB_NAME/DB_USER/DB_PASSWORD no configuradas. "
                "Operando sin base de datos."
            )
    else:
        logger.warning(
            "psycopg2 no instalado (%s). Operando sin base de datos.", _db_error_msg
        )

    if NODE_ENV != "production":
        Timer(1.0, lambda: webbrowser.open(f"{base}/docs")).start()


@app.on_event("shutdown")
async def on_shutdown():
    if _db_available and _db_imports_ok:
        try:
            close_pool()
        except Exception:
            pass
