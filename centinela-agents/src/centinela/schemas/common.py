"""Esquemas Pydantic compartidos por ambos agentes.

`Decision` es el contrato único de salida: simplifica el front y la auditoría.
No modificar sin actualizar `openapi.json` y `docs/API.md`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ProcessName = Literal["transaction", "document"]

TransactionVerdict = Literal["aprobar", "validacion_adicional", "bloquear"]
DocumentVerdict = Literal["autentico", "sospechoso", "falso"]
Verdict = Literal[
    "aprobar", "validacion_adicional", "bloquear", "autentico", "sospechoso", "falso"
]

EvidenceType = Literal["rule", "similarity", "vision", "metadata", "consistency"]
CheckStatus = Literal["pass", "fail", "warn", "pending"]

FeedbackLabel = Literal[
    "fraude_confirmado", "legitimo", "documento_falso", "documento_autentico"
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Evidence(BaseModel):
    """Una señal que sustenta la decisión. El analista las ve ordenadas por peso."""

    model_config = ConfigDict(populate_by_name=True)

    type: EvidenceType
    name: str = Field(description="Identificador estable de la señal, en inglés.")
    value: Any = Field(description="Valor observado (bool, número, texto o lista).")
    weight: float = Field(ge=0.0, le=1.0, description="Peso relativo dentro de su fuente.")
    detail: str = Field(default="", description="Explicación en una frase, en español.")


class Region(BaseModel):
    """Región normalizada (0-1) sobre la imagen, para dibujar recuadros en el front."""

    page: int = Field(default=1, ge=1)
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(ge=0.0, le=1.0)
    height: float = Field(ge=0.0, le=1.0)


class Finding(BaseModel):
    """Hallazgo forense con región y confianza (proceso de documentos)."""

    name: str
    detail: str
    confidence: float = Field(ge=0.0, le=1.0)
    region: Region | None = None


class Check(BaseModel):
    """Verificación determinista ejecutada en Python, sin modelo."""

    name: str
    status: CheckStatus
    detail: str = ""
    critical: bool = Field(
        default=False,
        description="Si es crítico y falla, el veredicto mínimo es `sospechoso`.",
    )


class Usage(BaseModel):
    """Consumo de un proveedor para una decisión."""

    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    calls: int = 0


class Decision(BaseModel):
    """Salida única de ambos procesos."""

    model_config = ConfigDict(populate_by_name=True)

    trace_id: str
    process: ProcessName
    verdict: Verdict
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    requires_human_review: bool = False
    shadow: bool = Field(
        default=False, description="true si SHADOW_MODE forzó el veredicto a `aprobar`."
    )
    explanation_customer: str = Field(
        default="",
        description="Texto breve y amable. Jamás menciona reglas, umbrales, "
        "modelos, scores ni hallazgos forenses.",
    )
    explanation_analyst: str = Field(default="", description="Texto técnico para el analista.")
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    created_at: datetime = Field(default_factory=utcnow)


DocumentType = Literal[
    "cedula", "comprobante_domicilio", "contrato", "poder", "liquidacion", "firma", "otro"
]


class FieldValue(BaseModel):
    """Campo extraído de un documento, con su confianza."""

    value: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: Literal["vision", "ocr", "metadata", "expected"] = "vision"


class DocumentDecision(Decision):
    """`Decision` + lo específico del proceso B.

    Vive en este módulo, junto a `Decision` y `CaseDetail`, porque los tres se
    referencian entre sí: `CaseDetail.decision` debe poder ser un
    `DocumentDecision` completo para que la pantalla del analista reciba
    `checks`, `fields` y `findings`.
    """

    document_type_detected: DocumentType = "otro"
    fields: dict[str, FieldValue] = Field(default_factory=dict)
    checks: list[Check] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    pages_analyzed: int = 1
    image_quality: float = Field(default=1.0, ge=0.0, le=1.0)


class Feedback(BaseModel):
    """Etiqueta del analista. Cierra el ciclo de aprendizaje: indexa el caso."""

    trace_id: str
    label: FeedbackLabel
    analyst: str = Field(min_length=1, description="Identificador del analista.")
    comment: str = ""


class FeedbackAck(BaseModel):
    trace_id: str
    label: FeedbackLabel
    indexed: bool = Field(description="true si el caso se indexó en el vector store.")
    message: str = ""


class CaseSummary(BaseModel):
    """Fila de la bandeja del analista."""

    trace_id: str
    process: ProcessName
    verdict: Verdict
    score: float
    confidence: float
    requires_human_review: bool
    shadow: bool = False
    created_at: datetime
    cost_usd: float = 0.0
    latency_ms: int = 0
    feedback_label: FeedbackLabel | None = None
    age_seconds: float = 0.0


class CaseDetail(BaseModel):
    """Detalle completo: decisión + traza interna (solo roles analista/supervisor).

    `decision` es una unión: para un caso de documento hay que devolver
    `DocumentDecision` completo —con `checks`, `fields` y `findings`—, porque la
    pantalla del analista los necesita. Validarlo como `Decision` descartaría
    esos campos silenciosamente.
    """

    decision: DocumentDecision | Decision
    inputs: dict[str, Any] = Field(default_factory=dict)
    prompts: dict[str, Any] = Field(
        default_factory=dict, description="Prompts usados. Nunca se exponen al cliente."
    )
    prompt_version: str = ""
    weights: dict[str, float | None] = Field(
        default_factory=dict,
        description="Pesos usados y score de cada fuente. `null` = fuente sin datos.",
    )
    neighbors: list[dict[str, Any]] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
    feedback: list[Feedback] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"] = "ok"
    mock_mode: bool
    shadow_mode: bool = False
    version: str = ""
    openai_configured: bool = False
    models: dict[str, str] = Field(default_factory=dict)


class VerdictCount(BaseModel):
    verdict: str
    count: int


class DailyPoint(BaseModel):
    date: str
    verdict: str
    count: int


class ProcessMetrics(BaseModel):
    process: ProcessName
    volume: int = 0
    block_rate: float = 0.0
    human_review_rate: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    cost_usd: float = 0.0
    cost_per_event_usd: float = 0.0
    verdicts: list[VerdictCount] = Field(default_factory=list)


class MetricsResponse(BaseModel):
    generated_at: datetime = Field(default_factory=utcnow)
    total_volume: int = 0
    total_cost_usd: float = 0.0
    cost_per_event_usd: float = 0.0
    feedback_count: int = 0
    estimated_accuracy: float | None = Field(
        default=None, description="Precisión sobre los casos que tienen feedback."
    )
    shadow_would_block: int = 0
    shadow_approved: int = 0
    by_process: list[ProcessMetrics] = Field(default_factory=list)
    by_model: list[dict[str, Any]] = Field(default_factory=list)
    top_evidence: list[dict[str, Any]] = Field(default_factory=list)
    timeseries: list[DailyPoint] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    detail: str
    code: str = "error"
    trace_id: str | None = None

