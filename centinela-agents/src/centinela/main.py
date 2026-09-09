"""Aplicación FastAPI de Centinela.

Arranca la API, monta los routers, configura CORS y exporta `openapi.json`
(el contrato que consume la web app).
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from centinela import __version__
from centinela.api import cases, documents, health, metrics, transactions
from centinela.config import get_settings
from centinela.core.db import get_engine
from centinela.core.tracing import get_trace_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s · %(message)s")
logger = logging.getLogger("centinela")

DESCRIPTION = """\
API de agentes de **Centinela**, plataforma antifraude multimodal.

Dos procesos, un mismo contrato de salida (`Decision`):

- `POST /api/v1/transactions/evaluate` — aprobar · validación adicional · bloquear
- `POST /api/v1/documents/validate` — auténtico · sospechoso · falso

Toda decisión es explicable y trazable bajo un `trace_id`. Los casos bloqueados
y las excepciones siempre pasan por una persona.

**Datos sintéticos.** Este servicio se construyó como proyecto académico y no
debe procesar datos reales de clientes sin gobierno y consentimiento.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    get_engine()  # crea las tablas si no existen
    settings.traces_path.mkdir(parents=True, exist_ok=True)

    # Retención: al arrancar se limpian las imágenes cuyo plazo venció.
    try:
        purged = get_trace_store().purge_expired_artifacts()
        if purged:
            logger.info("Retención: se borraron artefactos de %d caso(s).", len(purged))
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo ejecutar la retención al arrancar: %s", exc)

    if settings.export_openapi:
        try:
            path = settings.repo_root / "openapi.json"
            path.write_text(
                json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.info("Contrato exportado a %s", path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo exportar openapi.json: %s", exc)

    logger.info(
        "Centinela %s · mock_mode=%s · shadow_mode=%s · ocr_engine=%s",
        __version__,
        settings.mock_mode or not settings.has_openai,
        settings.shadow_mode,
        settings.ocr_engine,
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Centinela · API de agentes antifraude",
        description=DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        contact={"name": settings.team_name},
        license_info={"name": "MIT"},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        # Cualquier puerto de localhost/127.0.0.1 y los subdominios de Lovable.
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
        r"|^https://.*\.lovable\.(app|dev)$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(transactions.router)
    app.include_router(documents.router)
    app.include_router(cases.router)
    app.include_router(metrics.router)

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc), "code": "invalid_input"})

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {
            "service": "Centinela · API de agentes antifraude",
            "version": __version__,
            "docs": "/docs",
            "health": "/api/v1/health",
        }

    return app


app = create_app()
