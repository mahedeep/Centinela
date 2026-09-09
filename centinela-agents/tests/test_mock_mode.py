"""El modo mock: determinista, sin red y sin costo."""

from __future__ import annotations

from centinela.agents.transactions.agent import TransactionAgent
from centinela.agents.transactions.schemas import TransactionInput
from centinela.core.llm import LLMClient
from centinela.core.mock import mock_transaction_reasoning


def test_llm_client_reports_mock_mode():
    assert LLMClient().mock is True


def test_embeddings_are_deterministic_without_network():
    client = LLMClient()
    first = client.embed(["una transaccion cualquiera"])
    second = client.embed(["una transaccion cualquiera"])
    assert first == second
    assert len(first[0]) == 256


def test_mock_calls_cost_nothing():
    client = LLMClient()
    client.embed(["texto"])
    assert client.usage.cost_usd == 0.0
    assert client.usage.tokens_in > 0, "El consumo se estima igual, para poder dimensionar"


def test_same_transaction_yields_same_decision(sample_transaction):
    first = TransactionAgent().run(TransactionInput.model_validate(sample_transaction))
    second = TransactionAgent().run(TransactionInput.model_validate(sample_transaction))
    assert first.verdict == second.verdict
    assert first.score == second.score
    assert first.trace_id != second.trace_id, "Cada evaluación tiene su propia traza"


def test_mock_reasoning_scales_with_evidence():
    low = mock_transaction_reasoning({"rules_score": 0.05, "similarity_score": None})
    high = mock_transaction_reasoning(
        {
            "rules_score": 0.85,
            "similarity_score": None,
            "fired_rules": ["a", "b", "c"],
            "rule_details": ["detalle"],
        }
    )
    assert low["score"] < high["score"]
    assert low["recommended_action"] == "aprobar"
    assert high["recommended_action"] == "bloquear"


def test_mock_customer_text_never_leaks_internals():
    result = mock_transaction_reasoning(
        {"rules_score": 0.9, "similarity_score": 0.8, "fired_rules": ["a", "b", "c"]}
    )
    text = result["explanation_customer"].lower()
    for forbidden in ("score", "regla", "umbral", "modelo", "similitud", "peso"):
        assert forbidden not in text


def test_usage_is_per_evaluation_not_per_agent(sample_transaction):
    """Un agente reutilizado no debe acumular el consumo de la llamada anterior."""
    agent = TransactionAgent()
    first = agent.run(TransactionInput.model_validate(sample_transaction))
    second = agent.run(TransactionInput.model_validate(sample_transaction))
    assert second.tokens_in == first.tokens_in
    assert second.tokens_in < 1500, "Presupuesto de entrada por evaluación"
