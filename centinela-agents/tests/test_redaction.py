"""La barrera de lo que el cliente puede leer.

El prompt le pide al modelo que no revele controles; estos tests verifican que
el sistema no dependa de que obedezca.
"""

from __future__ import annotations

import pytest

from centinela.core.redaction import (
    SAFE_CUSTOMER_TEXT,
    find_leaks,
    sanitize_customer_text,
)


@pytest.mark.parametrize("verdict,text", list(SAFE_CUSTOMER_TEXT.items()))
def test_safe_texts_do_not_leak(verdict, text):
    assert find_leaks(text) == [], f"La redacción segura de '{verdict}' filtra"


@pytest.mark.parametrize(
    "text",
    [
        "Verifica que reconoces el acceso, el dispositivo y el beneficiario.",
        "Detectamos una conexión con VPN desde otro país.",
        "El score de riesgo superó el umbral configurado.",
        "La tipografía de la fecha no coincide con el resto.",
        "Los metadatos muestran edición con Photoshop.",
        "Encontramos indicios de fraude en tu operación.",
        "El dígito verificador del RUT es incorrecto.",
        "Detectamos un patrón similar a casos anteriores por similitud.",
    ],
)
def test_texts_that_reveal_controls_are_replaced(text):
    result, leaks = sanitize_customer_text(text, "bloquear")
    assert leaks, f"Debió detectarse una filtración en: {text}"
    assert result == SAFE_CUSTOMER_TEXT["bloquear"]


@pytest.mark.parametrize(
    "text",
    [
        "Tu operación se realizó correctamente.",
        "Necesitamos una foto más nítida del documento. Tómala con buena luz.",
        "Un ejecutivo te contactará para revisar la operación contigo.",
        "Para confirmar que eres tú, te enviaremos un código de verificación.",
    ],
)
def test_acceptable_texts_pass_through(text):
    result, leaks = sanitize_customer_text(text, "validacion_adicional")
    assert leaks == []
    assert result == text


def test_detection_ignores_accents_and_case():
    assert find_leaks("TIPOGRAFÍA distinta") == ["tipografia"]
    assert find_leaks("Metadatos del archivo") == ["metadato"]


def test_plurals_are_detected():
    assert "regla" in find_leaks("Se activaron varias reglas de negocio.")
    assert "dispositivo" in find_leaks("Detectamos dispositivos nuevos.")


def test_a_word_that_merely_contains_a_term_is_not_flagged():
    # «desregla» o «modelar» no deben confundirse con «regla» o «modelo».
    assert find_leaks("Vamos a desreglamentar el proceso.") == []


def test_empty_text_falls_back_to_the_safe_wording():
    result, leaks = sanitize_customer_text("", "aprobar")
    assert result == SAFE_CUSTOMER_TEXT["aprobar"]
    assert leaks == []


def test_unknown_verdict_uses_the_cautious_wording():
    result, _ = sanitize_customer_text("El score fue alto.", "veredicto_inexistente")
    assert result == SAFE_CUSTOMER_TEXT["sospechoso"]


def test_agent_replaces_a_leaking_model_text(sample_transaction, monkeypatch):
    """Si el modelo filtra, el agente devuelve la redacción segura y lo anota."""
    from centinela.agents.transactions import agent as tx_agent
    from centinela.agents.transactions.schemas import TransactionInput
    from centinela.core.tracing import get_trace_store

    def leaking_reasoning(_hint):
        return {
            "score": 0.9,
            "confidence": 0.9,
            "reasons": ["motivo"],
            "explanation_customer": "Detectamos un dispositivo nuevo con VPN.",
            "explanation_analyst": "detalle técnico",
            "recommended_action": "bloquear",
        }

    monkeypatch.setattr(tx_agent, "mock_transaction_reasoning", leaking_reasoning)

    decision = tx_agent.TransactionAgent().run(
        TransactionInput.model_validate(sample_transaction)
    )
    assert "dispositivo" not in decision.explanation_customer.lower()
    assert "vpn" not in decision.explanation_customer.lower()

    detail = get_trace_store().get_case(decision.trace_id)
    assert detail is not None
    redacted = detail.extra.get("customer_text_redacted")
    assert redacted is not None
    assert set(redacted["terms"]) >= {"dispositivo", "vpn"}
    # El texto original se conserva en la traza, para poder ajustar el prompt.
    assert "dispositivo" in redacted["original"].lower()
    assert "redacción segura" in decision.explanation_analyst
