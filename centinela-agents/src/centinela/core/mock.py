"""Respuestas mock deterministas.

`MOCK_MODE=true` evita llamar a OpenAI: contingencia para demos, tests sin red y
desarrollo del front sin gastar tokens. Las respuestas se derivan de las
evidencias ya calculadas por el agente (`hint`), de modo que el mock es
*coherente* con la entrada y no un texto fijo.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

EMBEDDING_DIM = 256


def deterministic_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Embedding reproducible derivado del texto (hash → pseudoaleatorio → L2).

    No captura semántica real; sirve para que la búsqueda por coseno sea estable
    y testeable sin red. Textos parecidos comparten prefijo de tokens, así que
    la mezcla por token da alguna señal de solapamiento léxico.
    """
    vec = [0.0] * dim
    tokens = [t for t in text.lower().replace("\n", " ").split(" ") if t]
    if not tokens:
        tokens = ["<empty>"]
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        for i in range(dim):
            byte = digest[i % len(digest)]
            vec[i] += (byte / 255.0) - 0.5
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def mock_transaction_reasoning(hint: dict[str, Any]) -> dict[str, Any]:
    """Simula el razonamiento del modelo sobre las evidencias de una transacción."""
    rules_score = float(hint.get("rules_score", 0.0))
    similarity_score = hint.get("similarity_score")
    fired = list(hint.get("fired_rules", []))
    reasons: list[str] = [str(r) for r in hint.get("rule_details", [])][:4]

    # El "modelo" mock pondera reglas y similitud, y sube un poco cuando varias
    # señales independientes coinciden (efecto de combinación). Si no hay casos
    # comparables, la similitud no aporta ni resta: se renormaliza sobre reglas.
    combo_bonus = 0.08 if len(fired) >= 3 else 0.0
    if similarity_score is None:
        score = _clamp(rules_score + combo_bonus)
        similarity_score = 0.0
    else:
        similarity_score = float(similarity_score)
        score = _clamp(0.72 * rules_score + 0.28 * similarity_score + combo_bonus)
    confidence = _clamp(0.55 + 0.30 * min(len(fired), 4) / 4 + 0.15 * similarity_score)

    if similarity_score >= 0.55 and hint.get("neighbor_count"):
        reasons.append(
            f"Patrón similar a {hint.get('fraud_neighbors', 0)} caso(s) de fraude confirmado "
            f"(similitud {similarity_score:.2f})"
        )
    if hint.get("graph_flag"):
        reasons.append(str(hint["graph_flag"]))
    if not reasons:
        reasons = ["Sin señales de riesgo relevantes en esta operación"]

    if score >= 0.70:
        recommended = "bloquear"
        customer = (
            "Por seguridad dejamos esta operación en pausa mientras la revisamos. "
            "Un ejecutivo puede confirmarla contigo cuando quieras."
        )
    elif score >= 0.35:
        recommended = "validacion_adicional"
        customer = (
            "Para confirmar que eres tú, vamos a pedirte un código de verificación "
            "antes de completar la operación."
        )
    else:
        recommended = "aprobar"
        customer = "Tu operación se realizó correctamente."

    analyst = "Evidencias consideradas: " + (
        "; ".join(reasons[:5]) if reasons else "ninguna señal activa"
    )
    return {
        "score": round(score, 4),
        "confidence": round(confidence, 4),
        "reasons": reasons[:5],
        "explanation_customer": customer,
        "explanation_analyst": analyst,
        "recommended_action": recommended,
    }


def mock_document_reasoning(hint: dict[str, Any]) -> dict[str, Any]:
    """Simula el perito documental sobre hallazgos y checks."""
    vision_score = float(hint.get("vision_score", 0.0))
    checks_score = float(hint.get("checks_score", 0.0))
    failed = list(hint.get("failed_checks", []))
    findings = list(hint.get("finding_names", []))
    quality = float(hint.get("image_quality", 1.0))

    score = _clamp(0.55 * vision_score + 0.45 * checks_score)
    confidence = _clamp(0.45 + 0.35 * quality + 0.20 * min(len(findings), 3) / 3)

    reasons: list[str] = []
    for name in failed[:3]:
        reasons.append(f"Verificación en falla: {name}")
    for name in findings[:3]:
        reasons.append(f"Hallazgo forense: {name}")
    if quality < 0.4:
        reasons.append("Calidad de imagen insuficiente para verificar todos los elementos")
    if not reasons:
        reasons = ["Campos extraídos consistentes y sin señales de alteración visibles"]

    if quality < 0.4:
        customer = (
            "Necesitamos una foto más nítida del documento. Tómala con buena luz, "
            "sin reflejos y con el documento completo dentro del cuadro."
        )
    elif score >= 0.70:
        customer = (
            "No pudimos validar este documento en línea. Un ejecutivo te contactará "
            "para revisarlo contigo."
        )
    elif score >= 0.35:
        customer = (
            "Necesitamos revisar este documento con más detalle. Si puedes, súbelo "
            "nuevamente desde el original."
        )
    else:
        customer = "Tu documento fue validado correctamente. No necesitas hacer nada más."

    analyst = "Checks en falla: " + (", ".join(failed) if failed else "ninguno") + ". Hallazgos: " + (
        ", ".join(findings) if findings else "ninguno"
    ) + f". Calidad de imagen: {quality:.2f}."

    return {
        "score": round(score, 4),
        "confidence": round(confidence, 4),
        "reasons": reasons[:5],
        "explanation_customer": customer,
        "explanation_analyst": analyst,
    }


def mock_vision_extraction(hint: dict[str, Any]) -> dict[str, Any]:
    """Simula la llamada de visión de extracción.

    Usa las pistas del preproceso (nombre de archivo y texto OCR si lo hubo)
    para devolver campos plausibles y deterministas.
    """
    return {
        "document_type": hint.get("document_type", "otro"),
        "fields": hint.get("fields", {}),
        "layout": hint.get(
            "layout",
            "Encabezado con logo institucional arriba a la izquierda, bloque de datos "
            "al centro, firma y timbre en el tercio inferior.",
        ),
        "image_quality_comment": "Legible" if hint.get("image_quality", 1.0) >= 0.4 else "Baja",
    }


def mock_vision_forensics(hint: dict[str, Any]) -> dict[str, Any]:
    """Simula la llamada forense. Deriva hallazgos del nombre del archivo sintético."""
    name = str(hint.get("source_name", "")).lower()
    findings: list[dict[str, Any]] = []

    catalog: list[tuple[str, str, str, float, dict[str, float]]] = [
        (
            "fecha",
            "typography_mismatch",
            "La fecha de vencimiento usa una tipografía distinta al resto del documento.",
            0.82,
            {"x": 0.55, "y": 0.42, "width": 0.30, "height": 0.09},
        ),
        (
            "firma_pegada",
            "crop_border",
            "Borde de recorte visible alrededor de la firma; fondo distinto al del documento.",
            0.78,
            {"x": 0.55, "y": 0.72, "width": 0.32, "height": 0.16},
        ),
        (
            "montos",
            "digit_retouch",
            "Los dígitos del monto líquido presentan compresión distinta al resto de la tabla.",
            0.74,
            {"x": 0.58, "y": 0.60, "width": 0.28, "height": 0.08},
        ),
        (
            "tipografia",
            "inserted_text_block",
            "Bloque de texto con fondo más claro y línea base desalineada respecto del párrafo.",
            0.80,
            {"x": 0.10, "y": 0.50, "width": 0.78, "height": 0.14},
        ),
    ]
    for key, fname, detail, conf, region in catalog:
        if key in name:
            findings.append(
                {
                    "name": fname,
                    "detail": detail,
                    "confidence": conf,
                    "region": {"page": 1, **region},
                }
            )

    manipulation_score = _clamp(max((f["confidence"] for f in findings), default=0.05))
    return {"findings": findings, "manipulation_score": round(manipulation_score, 4)}


def mock_signature_comparison(hint: dict[str, Any]) -> dict[str, Any]:
    name = str(hint.get("source_name", "")).lower()
    if "firma_pegada" in name:
        return {
            "match_probability": 0.21,
            "differences": [
                "Inclinación del trazo distinta",
                "Presión y grosor uniformes, propios de una copia digital",
            ],
        }
    return {"match_probability": 0.88, "differences": []}
