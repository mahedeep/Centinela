"""Verificaciones deterministas, ejecutadas en Python sin modelo.

Existen para que el modelo no decida solo: son reproducibles, auditables y
explicables sin apelar a una red neuronal. Un check **crítico** en `fail` fuerza
el veredicto mínimo `sospechoso`, aunque el resto del análisis salga limpio.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from centinela.agents.documents.preprocess import editor_software, modification_after_issue
from centinela.schemas import Check

# Checks cuya falla impide declarar el documento auténtico.
CRITICAL_CHECKS = {
    "rut_modulo_11",
    "date_consistency",
    "arithmetic_consistency",
    "signature_match",
    "expected_fields_match",
}

FIELD_PATTERNS: dict[str, dict[str, str]] = {
    "cedula": {
        "rut": r"^\d{1,2}\.?\d{3}\.?\d{3}-[\dkK]$",
        "numero_serie": r"^[A-Z0-9.\-]{6,20}$",
    },
    "comprobante_domicilio": {"emisor": r"^.{3,80}$"},
    "liquidacion": {"periodo": r"^.{3,40}$"},
    "contrato": {"firmante": r"^.{3,80}$"},
    "poder": {"rut": r"^\d{1,2}\.?\d{3}\.?\d{3}-[\dkK]$"},
}

DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%y")

MONEY_RE = re.compile(r"[^\d,\.\-]")


# --- utilidades --------------------------------------------------------------


def normalize_rut(value: str) -> str:
    return re.sub(r"[^0-9kK]", "", value or "").upper()


def rut_is_valid(value: str) -> bool:
    """Validación por módulo 11 (algoritmo del dígito verificador chileno)."""
    cleaned = normalize_rut(value)
    if len(cleaned) < 2 or not cleaned[:-1].isdigit():
        return False
    body, verifier = cleaned[:-1], cleaned[-1]
    total = 0
    multiplier = 2
    for digit in reversed(body):
        total += int(digit) * multiplier
        multiplier = 2 if multiplier == 7 else multiplier + 1
    remainder = 11 - (total % 11)
    expected = {11: "0", 10: "K"}.get(remainder, str(remainder))
    return expected == verifier


def parse_date(value: str) -> date | None:
    raw = (value or "").strip()
    if not raw:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def parse_money(value: str) -> float | None:
    """Convierte '$ 1.234.567' o '1.234.567,89' a float. None si no es un monto."""
    raw = MONEY_RE.sub("", value or "")
    if not raw:
        return None
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    elif raw.count(".") > 1:
        raw = raw.replace(".", "")
    elif "." in raw:
        integer, _, decimals = raw.partition(".")
        if len(decimals) == 3:  # separador de miles, no decimal
            raw = integer + decimals
    try:
        return float(raw)
    except ValueError:
        return None


def _get(fields: dict[str, Any], name: str) -> str:
    entry = fields.get(name)
    if isinstance(entry, dict):
        return str(entry.get("value", "")).strip()
    return str(entry or "").strip()


# --- checks individuales -----------------------------------------------------


def check_rut(fields: dict[str, Any]) -> Check:
    raw = _get(fields, "rut")
    if not raw:
        return Check(
            name="rut_modulo_11",
            status="pending",
            detail="No se extrajo un RUT del documento.",
            critical=True,
        )
    if rut_is_valid(raw):
        return Check(
            name="rut_modulo_11",
            status="pass",
            detail=f"RUT {raw} válido por módulo 11.",
            critical=True,
        )
    return Check(
        name="rut_modulo_11",
        status="fail",
        detail=f"El dígito verificador de {raw} no corresponde al cuerpo del RUT.",
        critical=True,
    )


def check_dates(fields: dict[str, Any], today: date | None = None) -> Check:
    """Emisión anterior al vencimiento y a hoy; nacimiento coherente con la edad."""
    reference = today or date.today()
    issued = parse_date(_get(fields, "fecha_emision"))
    expires = parse_date(_get(fields, "fecha_vencimiento"))
    born = parse_date(_get(fields, "fecha_nacimiento"))

    problems: list[str] = []
    if issued and expires and issued >= expires:
        problems.append(
            f"la fecha de emisión ({issued.isoformat()}) no es anterior al "
            f"vencimiento ({expires.isoformat()})"
        )
    if issued and issued > reference:
        problems.append(f"la fecha de emisión ({issued.isoformat()}) está en el futuro")
    if born:
        if born > reference:
            problems.append("la fecha de nacimiento está en el futuro")
        else:
            age = (reference - born).days / 365.25
            if age > 120:
                problems.append(f"la edad calculada ({age:.0f} años) es imposible")
            if issued and born > issued:
                problems.append("la emisión es anterior al nacimiento")

    if problems:
        return Check(
            name="date_consistency",
            status="fail",
            detail="Inconsistencia de fechas: " + "; ".join(problems) + ".",
            critical=True,
        )
    if not issued and not expires and not born:
        return Check(
            name="date_consistency",
            status="pending",
            detail="No se extrajeron fechas verificables.",
            critical=True,
        )
    return Check(
        name="date_consistency",
        status="pass",
        detail="Las fechas extraídas son coherentes entre sí y con la fecha actual.",
        critical=True,
    )


def check_arithmetic(fields: dict[str, Any], document_type: str) -> Check:
    """Liquidación: bruto − descuentos = líquido, con tolerancia de redondeo."""
    if document_type != "liquidacion":
        return Check(
            name="arithmetic_consistency",
            status="pending",
            detail="No aplica a este tipo de documento.",
            critical=True,
        )
    gross = parse_money(_get(fields, "monto_bruto"))
    deductions = parse_money(_get(fields, "monto_descuentos"))
    net = parse_money(_get(fields, "monto_liquido"))

    if gross is None or deductions is None or net is None:
        return Check(
            name="arithmetic_consistency",
            status="pending",
            detail="Faltan montos para verificar la suma.",
            critical=True,
        )
    expected = gross - deductions
    tolerance = max(1.0, abs(expected) * 0.005)
    if abs(expected - net) <= tolerance:
        return Check(
            name="arithmetic_consistency",
            status="pass",
            detail=f"Bruto − descuentos = líquido ({expected:,.0f}).",
            critical=True,
        )
    return Check(
        name="arithmetic_consistency",
        status="fail",
        detail=(
            f"La suma no cuadra: bruto {gross:,.0f} − descuentos {deductions:,.0f} = "
            f"{expected:,.0f}, pero el documento declara {net:,.0f}."
        ),
        critical=True,
    )


def check_expected_fields(fields: dict[str, Any], expected: dict[str, str] | None) -> Check:
    """Cruce contra lo declarado en el onboarding."""
    if not expected:
        return Check(
            name="expected_fields_match",
            status="pending",
            detail="No se entregaron campos esperados para cruzar.",
            critical=True,
        )
    mismatches: list[str] = []
    missing: list[str] = []
    for key, expected_value in expected.items():
        observed = _get(fields, key)
        if not observed:
            missing.append(key)
            continue
        if key == "rut":
            match = normalize_rut(observed) == normalize_rut(str(expected_value))
        else:
            match = observed.strip().lower() == str(expected_value).strip().lower()
        if not match:
            mismatches.append(f"{key}: se esperaba «{expected_value}» y se leyó «{observed}»")

    if mismatches:
        return Check(
            name="expected_fields_match",
            status="fail",
            detail="No coincide con lo declarado. " + "; ".join(mismatches) + ".",
            critical=True,
        )
    if missing:
        return Check(
            name="expected_fields_match",
            status="warn",
            detail=f"No se pudo leer en el documento: {', '.join(missing)}.",
            critical=True,
        )
    return Check(
        name="expected_fields_match",
        status="pass",
        detail="Los campos extraídos coinciden con lo declarado.",
        critical=True,
    )


def check_format(fields: dict[str, Any], document_type: str) -> Check:
    """Regex por campo según el tipo de documento."""
    patterns = FIELD_PATTERNS.get(document_type)
    if not patterns:
        return Check(
            name="format_by_type",
            status="pending",
            detail=f"No hay patrones definidos para el tipo '{document_type}'.",
        )
    problems: list[str] = []
    checked = 0
    for name, pattern in patterns.items():
        value = _get(fields, name)
        if not value:
            continue
        checked += 1
        if not re.match(pattern, value):
            problems.append(f"{name} («{value}») no sigue el formato esperado")
    if problems:
        return Check(name="format_by_type", status="fail", detail="; ".join(problems) + ".")
    if checked == 0:
        return Check(
            name="format_by_type",
            status="pending",
            detail="No se extrajeron campos con formato verificable.",
        )
    return Check(
        name="format_by_type",
        status="pass",
        detail=f"{checked} campo(s) con el formato esperado para '{document_type}'.",
    )


def check_metadata(metadata: dict[str, Any], fields: dict[str, Any]) -> Check:
    """Software de edición o modificación posterior a la emisión → `warn`.

    Es `warn` y no `fail` a propósito: un escaneo legítimo puede pasar por un
    editor. Basta para pedir el original, no para declarar el documento falso.
    """
    problems: list[str] = []
    software = editor_software(metadata)
    if software:
        problems.append(f"los metadatos declaran software de edición de imagen ({software})")
    issued = parse_date(_get(fields, "fecha_emision"))
    if modification_after_issue(metadata, datetime.combine(issued, datetime.min.time()) if issued else None):
        problems.append("la fecha de modificación del archivo es posterior a la emisión")

    if problems:
        return Check(
            name="metadata_coherence",
            status="warn",
            detail="Metadatos con señales de edición: " + "; ".join(problems) + ".",
        )
    return Check(
        name="metadata_coherence",
        status="pass",
        detail="Los metadatos del archivo no muestran señales de edición.",
    )


def check_signature(match_probability: float | None, threshold: float = 0.60) -> Check:
    if match_probability is None:
        return Check(
            name="signature_match",
            status="pending",
            detail="No se entregó una firma de referencia para comparar.",
            critical=True,
        )
    if match_probability >= threshold:
        return Check(
            name="signature_match",
            status="pass",
            detail=f"La firma coincide con la referencia (probabilidad {match_probability:.2f}).",
            critical=True,
        )
    return Check(
        name="signature_match",
        status="fail",
        detail=(
            f"La firma no coincide con la referencia registrada "
            f"(probabilidad {match_probability:.2f})."
        ),
        critical=True,
    )


# --- agregación --------------------------------------------------------------


def run_all(
    fields: dict[str, Any],
    document_type: str,
    metadata: dict[str, Any],
    expected_fields: dict[str, str] | None = None,
    signature_probability: float | None = None,
    today: date | None = None,
) -> list[Check]:
    """Ejecuta la batería completa. Ningún check se omite: si no aplica, va `pending`."""
    return [
        check_rut(fields),
        check_dates(fields, today),
        check_arithmetic(fields, document_type),
        check_expected_fields(fields, expected_fields),
        check_format(fields, document_type),
        check_metadata(metadata, fields),
        check_signature(signature_probability),
    ]


def checks_score(checks: list[Check]) -> float:
    """Score de la fuente «checks» en [0, 1] (1 = máxima sospecha).

    `fail` crítico pesa mucho más que `fail` no crítico; `warn` aporta poco;
    `pending` no aporta nada, pero tampoco limpia el documento.
    """
    weights = {("fail", True): 1.00, ("fail", False): 0.45, ("warn", True): 0.25,
               ("warn", False): 0.20, ("pass", True): 0.0, ("pass", False): 0.0,
               ("pending", True): 0.0, ("pending", False): 0.0}
    # OR ruidosa: un fail crítico satura el score, varios warns no lo hacen.
    product = 1.0
    for check in checks:
        product *= 1.0 - weights.get((check.status, check.critical), 0.0)
    return round(1.0 - product, 4)


def has_critical_failure(checks: list[Check]) -> bool:
    return any(c.status == "fail" and c.critical for c in checks)


def failed_names(checks: list[Check]) -> list[str]:
    return [c.name for c in checks if c.status == "fail"]
