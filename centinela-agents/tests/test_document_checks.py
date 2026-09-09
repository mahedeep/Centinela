"""Checks deterministas del proceso B: casos válidos e inválidos."""

from __future__ import annotations

from datetime import date

import pytest

from centinela.agents.documents import checks as dc
from centinela.schemas import Check

TODAY = date(2026, 9, 9)


def _fields(**kwargs) -> dict:
    return {k: {"value": v, "confidence": 0.9} for k, v in kwargs.items()}


# --- RUT módulo 11 ------------------------------------------------------------


@pytest.mark.parametrize("rut", ["12.345.678-5", "12345678-5", "9.876.543-3", "11.111.111-1"])
def test_valid_ruts_pass_module_11(rut):
    assert dc.rut_is_valid(rut) is True


@pytest.mark.parametrize("rut", ["12.345.678-9", "12.345.678-K", "1", "", "abc", "12.345.678"])
def test_invalid_ruts_fail_module_11(rut):
    assert dc.rut_is_valid(rut) is False


@pytest.mark.parametrize("rut", ["20.000.003-K", "20000017-k"])
def test_k_verifier_is_accepted_in_either_case(rut):
    """El resto 10 se escribe como K; la validación no distingue mayúsculas."""
    assert dc.rut_is_valid(rut) is True


def test_zero_verifier_is_accepted():
    """El resto 11 se escribe como 0."""
    assert dc.rut_is_valid("20.000.008-0") is True


def test_rut_check_is_critical_and_reports_status():
    assert dc.check_rut(_fields(rut="12.345.678-5")).status == "pass"
    failed = dc.check_rut(_fields(rut="12.345.678-9"))
    assert failed.status == "fail"
    assert failed.critical is True
    assert dc.check_rut({}).status == "pending", "Sin RUT extraído queda pendiente, no aprobado"


# --- fechas -------------------------------------------------------------------


def test_dates_pass_when_coherent():
    check = dc.check_dates(
        _fields(fecha_emision="05/01/2022", fecha_vencimiento="05/01/2032",
                fecha_nacimiento="12/03/1988"),
        TODAY,
    )
    assert check.status == "pass"


def test_expiry_before_issue_fails():
    check = dc.check_dates(
        _fields(fecha_emision="05/01/2022", fecha_vencimiento="05/01/2021"), TODAY
    )
    assert check.status == "fail"
    assert "vencimiento" in check.detail


def test_issue_date_in_the_future_fails():
    check = dc.check_dates(_fields(fecha_emision="01/01/2030"), TODAY)
    assert check.status == "fail"


def test_impossible_age_fails():
    check = dc.check_dates(_fields(fecha_nacimiento="01/01/1850"), TODAY)
    assert check.status == "fail"


def test_no_dates_is_pending_not_pass():
    assert dc.check_dates({}, TODAY).status == "pending"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("05/01/2022", date(2022, 1, 5)), ("2022-01-05", date(2022, 1, 5)),
     ("05-01-2022", date(2022, 1, 5)), ("no es fecha", None), ("", None)],
)
def test_parse_date_formats(raw, expected):
    assert dc.parse_date(raw) == expected


# --- aritmética ---------------------------------------------------------------


def test_arithmetic_passes_when_amounts_add_up():
    check = dc.check_arithmetic(
        _fields(monto_bruto="$ 1.850.000", monto_descuentos="$ 370.000",
                monto_liquido="$ 1.480.000"),
        "liquidacion",
    )
    assert check.status == "pass"


def test_arithmetic_fails_when_net_was_inflated():
    check = dc.check_arithmetic(
        _fields(monto_bruto="$ 1.850.000", monto_descuentos="$ 370.000",
                monto_liquido="$ 1.780.000"),
        "liquidacion",
    )
    assert check.status == "fail"
    assert check.critical is True


def test_arithmetic_is_pending_for_other_document_types():
    assert dc.check_arithmetic(_fields(), "cedula").status == "pending"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("$ 1.850.000", 1850000.0), ("1.234.567,89", 1234567.89), ("1234", 1234.0),
     ("$ 38.450", 38450.0), ("", None), ("no es monto", None)],
)
def test_parse_money(raw, expected):
    assert dc.parse_money(raw) == expected


# --- campos esperados ---------------------------------------------------------


def test_expected_fields_match_ignoring_rut_format():
    check = dc.check_expected_fields(
        _fields(rut="12.345.678-5"), {"rut": "12345678-5"}
    )
    assert check.status == "pass"


def test_expected_fields_mismatch_fails():
    check = dc.check_expected_fields(_fields(rut="12.345.678-5"), {"rut": "9.876.543-3"})
    assert check.status == "fail"
    assert check.critical is True


def test_expected_fields_missing_is_a_warning():
    check = dc.check_expected_fields(_fields(nombre="X"), {"rut": "12.345.678-5"})
    assert check.status == "warn"


def test_expected_fields_without_input_is_pending():
    assert dc.check_expected_fields(_fields(rut="12.345.678-5"), None).status == "pending"


# --- formato y metadatos ------------------------------------------------------


def test_format_check_uses_patterns_per_type():
    assert dc.check_format(_fields(rut="12.345.678-5"), "cedula").status == "pass"
    assert dc.check_format(_fields(rut="ABC"), "cedula").status == "fail"
    assert dc.check_format(_fields(), "tipo_inexistente").status == "pending"


def test_metadata_warns_on_editor_software():
    check = dc.check_metadata({"image": {"Software": "Adobe Photoshop 26.0"}}, _fields())
    assert check.status == "warn"
    assert "photoshop" in check.detail.lower()


def test_metadata_warns_when_modified_after_issue():
    check = dc.check_metadata(
        {"pdf": {"ModDate": "2026:09:05 22:41:10"}},
        _fields(fecha_emision="03/08/2026"),
    )
    assert check.status == "warn"


def test_metadata_passes_when_clean():
    assert dc.check_metadata({"image": {"Make": "Apple"}}, _fields()).status == "pass"


# --- firma --------------------------------------------------------------------


def test_signature_check_thresholds():
    assert dc.check_signature(0.88).status == "pass"
    assert dc.check_signature(0.21).status == "fail"
    assert dc.check_signature(None).status == "pending"
    assert dc.check_signature(0.21).critical is True


# --- agregación ---------------------------------------------------------------


def test_run_all_never_omits_a_check():
    results = dc.run_all(_fields(), "otro", {}, None, None, TODAY)
    names = {c.name for c in results}
    assert names == {
        "rut_modulo_11",
        "date_consistency",
        "arithmetic_consistency",
        "expected_fields_match",
        "format_by_type",
        "metadata_coherence",
        "signature_match",
    }
    assert all(c.status in ("pass", "fail", "warn", "pending") for c in results)


def test_checks_score_saturates_on_critical_failure():
    critical = [Check(name="rut_modulo_11", status="fail", critical=True)]
    assert dc.checks_score(critical) == 1.0


def test_checks_score_is_low_for_warnings_only():
    warns = [Check(name="metadata_coherence", status="warn", critical=False)]
    assert 0.0 < dc.checks_score(warns) < 0.35


def test_checks_score_of_clean_document_is_zero():
    clean = [Check(name="rut_modulo_11", status="pass", critical=True)]
    assert dc.checks_score(clean) == 0.0


def test_has_critical_failure_ignores_non_critical():
    assert dc.has_critical_failure([Check(name="x", status="fail", critical=False)]) is False
    assert dc.has_critical_failure([Check(name="x", status="fail", critical=True)]) is True
