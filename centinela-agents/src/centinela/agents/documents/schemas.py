"""Esquemas del agente de documentos."""

from __future__ import annotations

from pydantic import BaseModel, Field

# `DocumentDecision` vive en `schemas/` porque `CaseDetail` lo referencia; aquí
# se reexporta para que el agente lo importe desde su propio módulo.
from centinela.schemas import DocumentDecision, DocumentType, FieldValue, Finding

__all__ = [
    "DocumentDecision",
    "DocumentType",
    "EvidenceRegionsResponse",
    "FieldValue",
    "ReferenceResponse",
]


class ReferenceResponse(BaseModel):
    """Respuesta al registrar una firma o plantilla de referencia."""

    reference_id: str
    document_type: DocumentType
    stored_at: str
    message: str = ""


class EvidenceRegionsResponse(BaseModel):
    """Regiones que el front dibuja como recuadros sobre la imagen."""

    trace_id: str
    pages_analyzed: int
    image_quality: float
    findings: list[Finding] = Field(default_factory=list)
    artifacts_available: bool = Field(
        default=False,
        description="false cuando la retención ya borró las imágenes procesadas.",
    )
