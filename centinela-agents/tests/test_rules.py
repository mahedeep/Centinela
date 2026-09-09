"""Cada regla, el score fuzzy y la combinación."""

from __future__ import annotations

import pytest

from centinela.agents.transactions.features import canonical_text, derive_features, to_clp
from centinela.agents.transactions.rules_config import TRANSACTION_RULES, build_engine
from centinela.agents.transactions.schemas import TransactionInput
from centinela.core.rules import RuleEngine, ramp_up, trapezoid


def _context(sample: dict, **overrides) -> dict:
    features = derive_features(TransactionInput.model_validate(sample))
    features.update(overrides)
    return features


def test_every_rule_has_a_weight_and_justification():
    assert len(TRANSACTION_RULES) >= 8, "El caso exige al menos 8 reglas con peso."
    for rule in TRANSACTION_RULES:
        assert 0.0 < rule.weight <= 1.0
        assert rule.description.strip(), f"{rule.name} sin justificación"


def test_rule_names_are_unique():
    names = [r.name for r in TRANSACTION_RULES]
    assert len(names) == len(set(names))


def test_no_rule_fires_on_a_clean_transaction(sample_transaction):
    engine = build_engine()
    fired, _ = engine.evaluate_rules(_context(sample_transaction))
    assert fired == [], f"Reglas activadas sin motivo: {[e.name for e in fired]}"


@pytest.mark.parametrize(
    ("rule_name", "overrides"),
    [
        ("new_device_and_new_beneficiary", {"new_device_and_new_beneficiary": True}),
        ("amount_over_3x_average", {"amount_ratio": 4.2}),
        ("ip_country_mismatch", {"ip_country_mismatch": True}),
        ("velocity_over_5_per_hour", {"tx_last_hour": 7}),
        ("failed_logins_3_or_more", {"failed_logins_24h": 3}),
        ("vpn_with_high_amount", {"vpn": True, "amount_clp": 2_000_000}),
        ("account_age_under_30_days", {"account_age_days": 12}),
        ("session_under_20_seconds", {"session_seconds": 8}),
        ("night_hours_with_geo_anomaly", {"night_hours": True, "geo_anomaly": True}),
        ("cross_border_new_beneficiary", {"is_new_beneficiary": True, "cross_border": True}),
        ("new_beneficiary_amount_above_average", {"is_new_beneficiary": True, "amount_ratio": 1.4}),
        (
            "structuring_pattern",
            {"tx_last_hour": 6, "amount_ratio": 0.3, "is_new_beneficiary": True},
        ),
    ],
)
def test_each_rule_fires_on_its_own_pattern(sample_transaction, rule_name, overrides):
    engine = build_engine()
    fired, _ = engine.evaluate_rules(_context(sample_transaction, **overrides))
    assert rule_name in [e.name for e in fired]


def test_rule_evidence_carries_type_and_detail(sample_transaction):
    engine = build_engine()
    fired, _ = engine.evaluate_rules(_context(sample_transaction, amount_ratio=5.0))
    evidence = next(e for e in fired if e.name == "amount_over_3x_average")
    assert evidence.type == "rule"
    assert evidence.value is True
    assert evidence.detail.strip()


# --- funciones de pertenencia -------------------------------------------------


def test_trapezoid_edges():
    assert trapezoid(-1, 0, 1, 2, 3) == 0.0
    assert trapezoid(0, 0, 1, 2, 3) == 0.0
    assert trapezoid(1, 0, 1, 2, 3) == 1.0
    assert trapezoid(2, 0, 1, 2, 3) == 1.0
    assert trapezoid(3, 0, 1, 2, 3) == 0.0
    assert trapezoid(0.5, 0, 1, 2, 3) == pytest.approx(0.5)
    assert trapezoid(2.5, 0, 1, 2, 3) == pytest.approx(0.5)


def test_ramp_up_edges():
    assert ramp_up(0, 1, 3) == 0.0
    assert ramp_up(1, 1, 3) == 0.0
    assert ramp_up(3, 1, 3) == 1.0
    assert ramp_up(2, 1, 3) == pytest.approx(0.5)


def test_fuzzy_score_is_monotonic_in_amount_ratio():
    engine = build_engine()
    scores = [
        engine.fuzzy_score(
            {"amount_ratio": ratio, "velocity_score": 0.0, "distance_from_home_km": 0.0}
        )[0]
        for ratio in (0.1, 1.0, 2.0, 3.0, 5.0)
    ]
    assert scores == sorted(scores), f"El riesgo difuso debe crecer con el monto: {scores}"


def test_fuzzy_score_ignores_missing_variables():
    engine = build_engine()
    score, detail = engine.fuzzy_score({"amount_ratio": 5.0})
    assert "velocity_score" not in detail
    assert score == pytest.approx(1.0)


def test_fuzzy_score_of_empty_input_is_zero():
    engine = build_engine()
    score, detail = engine.fuzzy_score({})
    assert score == 0.0
    assert detail == {}


# --- combinación --------------------------------------------------------------


def test_noisy_or_is_bounded_and_monotonic():
    assert RuleEngine.noisy_or([]) == 0.0
    assert RuleEngine.noisy_or([0.5]) == pytest.approx(0.5)
    assert RuleEngine.noisy_or([0.5, 0.5]) == pytest.approx(0.75)
    assert RuleEngine.noisy_or([0.9, 0.9, 0.9]) < 1.0
    assert RuleEngine.noisy_or([0.3, 0.4]) > RuleEngine.noisy_or([0.3])


def test_combined_score_grows_with_risk(sample_transaction, fraud_transaction):
    engine = build_engine()
    clean = derive_features(TransactionInput.model_validate(sample_transaction))
    risky = derive_features(TransactionInput.model_validate(fraud_transaction))

    def score(features):
        return engine.combined_score(
            features,
            {
                "amount_ratio": features["amount_ratio"],
                "velocity_score": features["velocity_score"],
                "distance_from_home_km": features["distance_from_home_km"],
            },
        )[0]

    assert score(clean) < 0.1
    assert score(risky) > 0.6


# --- features y texto canónico ------------------------------------------------


def test_to_clp_normalizes_currency():
    assert to_clp(100, "CLP") == 100
    assert to_clp(1, "USD") > 100
    assert to_clp(100, "XYZ") == 100  # moneda desconocida: se asume CLP


def test_canonical_text_leaks_no_personal_data(fraud_transaction):
    tx = TransactionInput.model_validate(fraud_transaction)
    text = canonical_text(derive_features(tx))
    assert tx.origin_account.id not in text
    assert tx.destination_account.id not in text
    assert tx.device.id not in text
    assert str(int(tx.amount)) not in text
    assert "beneficiario nuevo" in text


def test_canonical_text_is_stable(sample_transaction):
    tx = TransactionInput.model_validate(sample_transaction)
    first = canonical_text(derive_features(tx))
    second = canonical_text(derive_features(tx))
    assert first == second
