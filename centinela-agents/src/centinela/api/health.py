"""Estado del servicio."""

from __future__ import annotations

from fastapi import APIRouter

from centinela import __version__
from centinela.config import get_settings
from centinela.schemas import HealthResponse

router = APIRouter(prefix="/api/v1", tags=["salud"])


@router.get("/health", response_model=HealthResponse, summary="Estado del servicio")
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        mock_mode=settings.mock_mode or not settings.has_openai,
        shadow_mode=settings.shadow_mode,
        version=__version__,
        openai_configured=settings.has_openai,
        models={
            "chat": settings.openai_chat_model,
            "vision": settings.openai_vision_model,
            "embedding": settings.openai_embedding_model,
            "ocr_engine": settings.ocr_engine,
        },
    )
