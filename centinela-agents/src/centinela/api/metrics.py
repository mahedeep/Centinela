"""KPIs para el dashboard del supervisor."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from centinela.config import get_settings
from centinela.core.tracing import get_trace_store
from centinela.schemas import MetricsResponse

router = APIRouter(prefix="/api/v1", tags=["métricas"])


@router.get("/metrics", response_model=MetricsResponse, summary="KPIs, costo y modo sombra")
def metrics(
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
) -> MetricsResponse:
    return get_trace_store().metrics(date_from=date_from, date_to=date_to)


@router.get("/settings", summary="Configuración visible (umbrales y pesos, solo lectura)")
def public_settings() -> dict[str, object]:
    """Lo que el rol Supervisor puede ver en Ajustes. Ningún secreto sale por aquí."""
    settings = get_settings()
    return {
        "mock_mode": settings.mock_mode or not settings.has_openai,
        "shadow_mode": settings.shadow_mode,
        "thresholds": {
            "review": settings.threshold_review,
            "block": settings.threshold_block,
        },
        "weights": {
            "transactions": {
                "rules": settings.w_tx_rules,
                "similarity": settings.w_tx_similarity,
                "model": settings.w_tx_model,
            },
            "documents": {
                "vision": settings.w_doc_vision,
                "checks": settings.w_doc_checks,
                "model": settings.w_doc_model,
            },
        },
        "documents": {
            "max_upload_mb": settings.max_upload_mb,
            "max_pdf_pages": settings.max_pdf_pages,
            "min_image_quality": settings.min_image_quality,
            "ocr_engine": settings.ocr_engine,
            "trace_retention_days": settings.trace_retention_days,
        },
        "pricing_usd_per_1m_tokens": {
            "chat_input": settings.price_chat_input_per_1m,
            "chat_output": settings.price_chat_output_per_1m,
            "embedding_input": settings.price_embedding_input_per_1m,
            "nota": "Verificar contra la lista de precios vigente de OpenAI.",
        },
        "team": settings.team_name,
    }
