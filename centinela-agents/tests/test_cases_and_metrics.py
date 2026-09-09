"""Bandeja del analista, ciclo de feedback y KPIs del supervisor."""

from __future__ import annotations

import pytest


@pytest.fixture()
def blocked_case(client, fraud_transaction) -> dict:
    return client.post("/api/v1/transactions/evaluate", json=fraud_transaction).json()


@pytest.fixture()
def approved_case(client, sample_transaction) -> dict:
    return client.post("/api/v1/transactions/evaluate", json=sample_transaction).json()


# --- bandeja ------------------------------------------------------------------


def test_cases_are_listed_after_evaluation(client, blocked_case):
    cases = client.get("/api/v1/cases").json()
    assert blocked_case["trace_id"] in [c["trace_id"] for c in cases]


def test_cases_are_ordered_by_score_desc(client, blocked_case, approved_case):
    cases = client.get("/api/v1/cases").json()
    scores = [c["score"] for c in cases]
    assert scores == sorted(scores, reverse=True)


def test_cases_filter_by_human_review(client, blocked_case, approved_case):
    cases = client.get("/api/v1/cases", params={"requires_human_review": True}).json()
    ids = [c["trace_id"] for c in cases]
    assert blocked_case["trace_id"] in ids
    assert approved_case["trace_id"] not in ids


def test_cases_filter_by_process_and_verdict(client, blocked_case):
    cases = client.get(
        "/api/v1/cases", params={"process": "transaction", "verdict": "bloquear"}
    ).json()
    assert all(c["process"] == "transaction" and c["verdict"] == "bloquear" for c in cases)


def test_case_summary_reports_sla_age(client, blocked_case):
    case = next(
        c
        for c in client.get("/api/v1/cases").json()
        if c["trace_id"] == blocked_case["trace_id"]
    )
    assert case["age_seconds"] >= 0


# --- detalle ------------------------------------------------------------------


def test_case_detail_contains_the_full_trace(client, blocked_case):
    detail = client.get(f"/api/v1/cases/{blocked_case['trace_id']}").json()
    assert detail["decision"]["trace_id"] == blocked_case["trace_id"]
    assert detail["prompt_version"].startswith("tx-")
    assert detail["weights"]["rules"] > 0
    assert "system" in detail["prompts"], "Los prompts viven en la traza"
    assert detail["inputs"]["transaction_id"] == "TX-TEST-FRAUD"


def test_case_detail_404s_for_unknown_trace(client):
    assert client.get("/api/v1/cases/no-existe").status_code == 404


# --- feedback -----------------------------------------------------------------


def test_feedback_is_saved_and_indexed(client, blocked_case):
    response = client.post(
        "/api/v1/feedback",
        json={
            "trace_id": blocked_case["trace_id"],
            "label": "fraude_confirmado",
            "analyst": "analista.prueba",
            "comment": "Cliente confirmó que no reconoce la operación.",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["indexed"] is True

    detail = client.get(f"/api/v1/cases/{blocked_case['trace_id']}").json()
    assert detail["feedback"][0]["label"] == "fraude_confirmado"
    assert detail["feedback"][0]["analyst"] == "analista.prueba"


def test_feedback_appears_in_the_case_list(client, blocked_case):
    client.post(
        "/api/v1/feedback",
        json={
            "trace_id": blocked_case["trace_id"],
            "label": "legitimo",
            "analyst": "analista.prueba",
        },
    )
    case = next(
        c
        for c in client.get("/api/v1/cases").json()
        if c["trace_id"] == blocked_case["trace_id"]
    )
    assert case["feedback_label"] == "legitimo"


def test_feedback_rejects_a_label_from_the_other_process(client, blocked_case):
    response = client.post(
        "/api/v1/feedback",
        json={
            "trace_id": blocked_case["trace_id"],
            "label": "documento_falso",
            "analyst": "analista.prueba",
        },
    )
    assert response.status_code == 422


def test_feedback_404s_for_unknown_trace(client):
    response = client.post(
        "/api/v1/feedback",
        json={"trace_id": "no-existe", "label": "legitimo", "analyst": "x"},
    )
    assert response.status_code == 404


def test_feedback_requires_an_analyst(client, blocked_case):
    response = client.post(
        "/api/v1/feedback",
        json={"trace_id": blocked_case["trace_id"], "label": "legitimo", "analyst": ""},
    )
    assert response.status_code == 422


def test_confirmed_fraud_enters_the_similarity_memory(client, blocked_case):
    """El ciclo de aprendizaje sin reentrenar: la memoria de casos crece."""
    from centinela.core.vector_store import NS_TRANSACTIONS, get_vector_store

    store = get_vector_store()
    before = store.count(NS_TRANSACTIONS, label="fraude")
    client.post(
        "/api/v1/feedback",
        json={
            "trace_id": blocked_case["trace_id"],
            "label": "fraude_confirmado",
            "analyst": "analista.prueba",
        },
    )
    assert store.count(NS_TRANSACTIONS, label="fraude") == before + 1


# --- métricas -----------------------------------------------------------------


def test_metrics_aggregate_volume_and_cost(client, blocked_case, approved_case):
    metrics = client.get("/api/v1/metrics").json()
    assert metrics["total_volume"] >= 2
    assert metrics["cost_per_event_usd"] >= 0
    transaction = next(p for p in metrics["by_process"] if p["process"] == "transaction")
    assert transaction["volume"] >= 2
    assert 0 <= transaction["block_rate"] <= 1
    assert 0 <= transaction["human_review_rate"] <= 1
    assert transaction["latency_p95_ms"] >= transaction["latency_p50_ms"]


def test_metrics_include_top_evidence_and_timeseries(client, blocked_case):
    metrics = client.get("/api/v1/metrics").json()
    assert metrics["top_evidence"], "El dashboard grafica las evidencias más frecuentes"
    assert metrics["timeseries"]
    assert {"date", "verdict", "count"} <= set(metrics["timeseries"][0])


def test_metrics_estimate_accuracy_from_feedback(client, blocked_case):
    client.post(
        "/api/v1/feedback",
        json={
            "trace_id": blocked_case["trace_id"],
            "label": "fraude_confirmado",
            "analyst": "analista.prueba",
        },
    )
    metrics = client.get("/api/v1/metrics").json()
    assert metrics["feedback_count"] >= 1
    assert metrics["estimated_accuracy"] is not None


def test_settings_endpoint_exposes_no_secrets(client):
    body = client.get("/api/v1/settings").json()
    assert body["thresholds"]["review"] > 0
    assert body["weights"]["transactions"]["rules"] > 0
    serialized = str(body).lower()
    assert "api_key" not in serialized
    assert "sk-" not in serialized


# --- regresión: el detalle de un documento no debe perder sus campos hijos ----


def test_document_case_detail_keeps_checks_fields_and_findings(client, temp_data_dir):
    """`Decision.model_validate` descartaba los campos de `DocumentDecision`.

    La pantalla del analista los necesita: sin ellos no puede mostrar las
    verificaciones ni dibujar las regiones sobre la imagen.
    """
    import io

    from PIL import Image

    image = Image.new('RGB', (900, 600), (250, 249, 245))
    pixels = image.load()
    for y in range(0, 600, 3):
        for x in range(0, 900, 3):
            pixels[x, y] = (20, 24, 32)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')

    trace_id = client.post(
        '/api/v1/documents/validate',
        files={'file': ('cedula_alterada_fecha.png', buffer.getvalue(), 'image/png')},
    ).json()['trace_id']

    detail = client.get(f'/api/v1/cases/{trace_id}').json()
    decision = detail['decision']
    assert len(decision['checks']) == 7
    assert 'document_type_detected' in decision
    assert 'image_quality' in decision
    assert decision['pages_analyzed'] == 1
    assert isinstance(decision['findings'], list)
