"""Bandeja del analista, detalle de casos y feedback."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status

from centinela.core.tracing import get_trace_store
from centinela.schemas import CaseDetail, CaseSummary, Feedback, FeedbackAck

router = APIRouter(prefix="/api/v1", tags=["casos"])


@router.get("/cases", response_model=list[CaseSummary], summary="Bandeja de casos")
def list_cases(
    process: Annotated[Literal["transaction", "document"] | None, Query()] = None,
    verdict: Annotated[str | None, Query()] = None,
    requires_human_review: Annotated[bool | None, Query()] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    order_by: Annotated[Literal["score", "created_at"], Query()] = "score",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CaseSummary]:
    return get_trace_store().list_cases(
        process=process,
        verdict=verdict,
        requires_human_review=requires_human_review,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
        order_by=order_by,
    )


@router.get(
    "/cases/{trace_id}",
    response_model=CaseDetail,
    summary="Detalle completo de un caso, con la traza",
)
def get_case(trace_id: str) -> CaseDetail:
    detail = get_trace_store().get_case(trace_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe un caso con trace_id '{trace_id}'.",
        )
    return detail


@router.post(
    "/feedback",
    response_model=FeedbackAck,
    summary="Etiqueta del analista; indexa el caso para que el agente aprenda",
)
def post_feedback(payload: Feedback) -> FeedbackAck:
    store = get_trace_store()
    detail = store.get_case(payload.trace_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe un caso con trace_id '{payload.trace_id}'.",
        )

    expected = (
        {"fraude_confirmado", "legitimo"}
        if detail.decision.process == "transaction"
        else {"documento_falso", "documento_autentico"}
    )
    if payload.label not in expected:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"La etiqueta '{payload.label}' no corresponde a un caso de tipo "
                f"'{detail.decision.process}'. Etiquetas válidas: {sorted(expected)}."
            ),
        )

    store.save_feedback(payload)

    # El ciclo de aprendizaje: el caso etiquetado entra a la memoria de similitud.
    indexed = False
    message = ""
    try:
        if detail.decision.process == "transaction":
            from centinela.agents.transactions.agent import index_case_from_feedback

            indexed = index_case_from_feedback(payload.trace_id, payload.label)
        else:
            from centinela.agents.documents.agent import index_document_from_feedback

            indexed = index_document_from_feedback(payload.trace_id, payload.label)
        if not indexed:
            message = "Feedback registrado, pero el caso no tenía texto canónico para indexar."
    except Exception as exc:  # noqa: BLE001 - el feedback no se pierde por esto
        message = f"Feedback registrado; la indexación falló: {exc}"

    return FeedbackAck(
        trace_id=payload.trace_id,
        label=payload.label,
        indexed=indexed,
        message=message or "Feedback registrado e indexado en la memoria de casos.",
    )
