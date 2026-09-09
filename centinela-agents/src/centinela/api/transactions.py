"""Endpoints del proceso A."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from centinela.agents.transactions.agent import TransactionAgent
from centinela.agents.transactions.rules_config import rules_table
from centinela.agents.transactions.schemas import BatchTransactionInput, TransactionInput
from centinela.schemas import Decision

router = APIRouter(prefix="/api/v1/transactions", tags=["transacciones"])

MAX_BATCH = 200


@router.post(
    "/evaluate",
    response_model=Decision,
    summary="Evalúa una transacción y devuelve una decisión explicable",
)
def evaluate(payload: TransactionInput) -> Decision:
    try:
        return TransactionAgent().run(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudo evaluar la transacción: {exc}",
        ) from exc


@router.post(
    "/evaluate/batch",
    response_model=list[Decision],
    summary="Evalúa un lote de transacciones (replay y modo sombra)",
)
def evaluate_batch(payload: BatchTransactionInput) -> list[Decision]:
    if len(payload.transactions) > MAX_BATCH:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"El lote admite un máximo de {MAX_BATCH} transacciones por llamada.",
        )
    agent = TransactionAgent()
    return [agent.run(tx) for tx in payload.transactions]


@router.get("/rules", summary="Catálogo de reglas y pesos vigentes (solo lectura)")
def rules() -> dict[str, object]:
    return {"rules": rules_table()}
