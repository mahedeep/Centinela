"""Agente de transacciones: umbrales, revisión humana, modo sombra y endpoints."""

from __future__ import annotations

import os

import pytest

from centinela.agents.base import BaseAgent
from centinela.agents.transactions.agent import TransactionAgent
from centinela.agents.transactions.schemas import TransactionInput
from centinela.config import get_settings, reset_settings_cache


# --- umbrales ----------------------------------------------------------------


def test_classify_applies_both_thresholds():
    agent = TransactionAgent()
    labels = ("aprobar", "validacion_adicional", "bloquear")
    settings = get_settings()
    assert agent.classify(0.0, labels) == "aprobar"
    assert agent.classify(settings.threshold_review - 0.01, labels) == "aprobar"
    assert agent.classify(settings.threshold_review, labels) == "validacion_adicional"
    assert agent.classify(settings.threshold_block - 0.01, labels) == "validacion_adicional"
    assert agent.classify(settings.threshold_block, labels) == "bloquear"
    assert agent.classify(1.0, labels) == "bloquear"


def test_weighted_score_renormalizes_over_available_sources():
    """Una fuente sin datos no vale cero: su peso se reparte."""
    score, breakdown = BaseAgent.weighted_score(
        {"rules": (0.45, 0.8), "similarity": (0.25, None), "model": (0.30, 0.8)}
    )
    assert score == pytest.approx(0.8)
    assert breakdown["renormalized"] is True
    assert breakdown["unavailable"] == ["similarity"]


def test_weighted_score_without_any_source_is_zero():
    score, breakdown = BaseAgent.weighted_score({"rules": (0.45, None)})
    assert score == 0.0
    assert breakdown["renormalized"] is False


# --- decisiones ---------------------------------------------------------------


def test_clean_transaction_is_approved(sample_transaction):
    decision = TransactionAgent().run(TransactionInput.model_validate(sample_transaction))
    assert decision.verdict == "aprobar"
    assert decision.requires_human_review is False
    assert decision.score < get_settings().threshold_review


def test_takeover_pattern_is_blocked_and_escalated(fraud_transaction):
    decision = TransactionAgent().run(TransactionInput.model_validate(fraud_transaction))
    assert decision.verdict == "bloquear"
    assert decision.requires_human_review is True, "Prohibido bloquear sin revisión humana"
    assert decision.score >= get_settings().threshold_block


def test_new_beneficiary_above_average_asks_for_step_up(sample_transaction):
    """El caso que el negocio quiere resolver con un código, no con una llamada."""
    payload = {**sample_transaction, "amount": 1_250_000, "type": "transferencia"}
    payload["destination_account"] = {
        **payload["destination_account"],
        "is_new_beneficiary": True,
    }
    decision = TransactionAgent().run(TransactionInput.model_validate(payload))
    assert decision.verdict == "validacion_adicional"
    assert decision.requires_human_review is False


def test_evidence_is_sorted_by_weight(fraud_transaction):
    decision = TransactionAgent().run(TransactionInput.model_validate(fraud_transaction))
    weights = [e.weight for e in decision.evidence]
    assert weights == sorted(weights, reverse=True)


def test_decision_records_cost_and_latency(fraud_transaction):
    decision = TransactionAgent().run(TransactionInput.model_validate(fraud_transaction))
    assert decision.latency_ms >= 0
    assert decision.tokens_in > 0
    assert decision.cost_usd == 0.0  # mock


# --- explicabilidad -----------------------------------------------------------

FORBIDDEN_IN_CUSTOMER_TEXT = (
    "score",
    "regla",
    "umbral",
    "modelo",
    "similitud",
    "peso",
    "evidencia",
    "vpn",
    "prompt",
)


@pytest.mark.parametrize("fixture_name", ["sample_transaction", "fraud_transaction"])
def test_customer_explanation_never_reveals_controls(request, fixture_name):
    payload = request.getfixturevalue(fixture_name)
    decision = TransactionAgent().run(TransactionInput.model_validate(payload))
    text = decision.explanation_customer.lower()
    assert text.strip()
    for forbidden in FORBIDDEN_IN_CUSTOMER_TEXT:
        assert forbidden not in text, f"«{forbidden}» no puede aparecer al cliente"


def test_analyst_explanation_lists_evidence(fraud_transaction):
    decision = TransactionAgent().run(TransactionInput.model_validate(fraud_transaction))
    assert "Evidencias por peso" in decision.explanation_analyst
    assert "new_device_and_new_beneficiary" in decision.explanation_analyst


# --- modo sombra --------------------------------------------------------------


def test_shadow_mode_never_blocks(fraud_transaction, temp_data_dir):
    os.environ["SHADOW_MODE"] = "true"
    reset_settings_cache()
    try:
        decision = TransactionAgent().run(TransactionInput.model_validate(fraud_transaction))
        assert decision.verdict == "aprobar"
        assert decision.shadow is True
        assert decision.requires_human_review is False
        assert decision.score >= get_settings().threshold_block, "El score real se conserva"
    finally:
        os.environ["SHADOW_MODE"] = "false"
        reset_settings_cache()


def test_shadow_mode_keeps_the_real_verdict_in_the_trace(fraud_transaction, temp_data_dir):
    from centinela.core.tracing import get_trace_store

    os.environ["SHADOW_MODE"] = "true"
    reset_settings_cache()
    try:
        decision = TransactionAgent().run(TransactionInput.model_validate(fraud_transaction))
        detail = get_trace_store().get_case(decision.trace_id)
        assert detail is not None
        assert detail.extra["real_verdict"] == "bloquear"
        assert detail.extra["real_requires_human_review"] is True
    finally:
        os.environ["SHADOW_MODE"] = "false"
        reset_settings_cache()


# --- endpoints ----------------------------------------------------------------


def test_evaluate_endpoint_returns_a_decision(client, fraud_transaction):
    response = client.post("/api/v1/transactions/evaluate", json=fraud_transaction)
    assert response.status_code == 200
    body = response.json()
    assert body["process"] == "transaction"
    assert body["verdict"] in ("aprobar", "validacion_adicional", "bloquear")
    assert body["trace_id"].startswith("tx-")


def test_evaluate_endpoint_rejects_invalid_payload(client):
    response = client.post("/api/v1/transactions/evaluate", json={"transaction_id": "x"})
    assert response.status_code == 422


def test_evaluate_endpoint_rejects_negative_amount(client, sample_transaction):
    response = client.post(
        "/api/v1/transactions/evaluate", json={**sample_transaction, "amount": -100}
    )
    assert response.status_code == 422


def test_batch_endpoint_evaluates_every_transaction(client, sample_transaction, fraud_transaction):
    response = client.post(
        "/api/v1/transactions/evaluate/batch",
        json={"transactions": [sample_transaction, fraud_transaction]},
    )
    assert response.status_code == 200
    decisions = response.json()
    assert len(decisions) == 2
    assert decisions[0]["verdict"] == "aprobar"
    assert decisions[1]["verdict"] == "bloquear"
    assert decisions[0]["trace_id"] != decisions[1]["trace_id"]


def test_batch_endpoint_enforces_the_limit(client, sample_transaction):
    response = client.post(
        "/api/v1/transactions/evaluate/batch",
        json={"transactions": [sample_transaction] * 201},
    )
    assert response.status_code == 422  # Pydantic corta antes en max_length


def test_rules_endpoint_exposes_the_catalog(client):
    body = client.get("/api/v1/transactions/rules").json()
    assert len(body["rules"]) >= 8
    assert body["rules"][0]["weight"] >= body["rules"][-1]["weight"]
