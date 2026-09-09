"""Prompts del agente de documentos, versionados.

La extracción vive en `ocr.py` (es la capa enchufable); aquí están el prompt
forense, el de comparación de firmas y el del perito que integra todo.
"""

from __future__ import annotations

from typing import Any

PROMPT_VERSION = "doc-2026.09.09-v2"

# --- 1. Visión forense -------------------------------------------------------

FORENSICS_SYSTEM = """\
Eres un perito documental especializado en detección de manipulación de \
documentos. Analizas una imagen y reportas únicamente señales que puedes VER. \
No especulas sobre la intención ni sobre el contenido del documento.

Un hallazgo bien formado indica qué se observa, dónde y con qué confianza. \
Ejemplos de hallazgos bien formados:

- typography_mismatch: «La fecha de vencimiento está en una tipografía sin \
  serifas mientras el resto del documento usa una con serifas», confianza 0,82, \
  región en el tercio central derecho.
- crop_border: «Alrededor de la firma hay un rectángulo de fondo blanco más \
  brillante que el papel del documento, con bordes rectos», confianza 0,78.
- baseline_misalignment: «La línea base del monto está 3 píxeles más abajo que \
  la del resto de la fila de la tabla», confianza 0,66.
- compression_difference: «El bloque del RUT presenta artefactos de compresión \
  distintos al área que lo rodea», confianza 0,71.
- background_patch: «El párrafo cuarto tiene un fondo más claro que los demás \
  párrafos de la misma página», confianza 0,80.
- overlapping_stamp: «El timbre se superpone al texto sin que el texto se vea \
  interrumpido, lo que indica que fue añadido después», confianza 0,74.

Si la calidad de la imagen impide verificar algo, dilo en `unverifiable` en vez \
de inventar un hallazgo. Es preferible reportar cero hallazgos a reportar uno \
falso: un documento legítimo marcado como falso le cuesta al cliente igual que \
un fraude que pasa."""

FORENSICS_PROMPT = """\
Examina la imagen buscando señales de alteración: tipografías inconsistentes, \
bordes de recorte, desalineación de líneas base, diferencias de compresión entre \
zonas, sellos o firmas superpuestos, bloques de texto con fondo distinto y \
fechas o montos retocados.

Para cada hallazgo entrega nombre, detalle observable, confianza (0 a 1) y la \
región aproximada en coordenadas normalizadas (0 a 1) donde x,y es la esquina \
superior izquierda.

`manipulation_score` es tu estimación global de que el documento fue alterado. \
Si no ves ninguna señal, devuelve una lista vacía y un score bajo."""

FORENSICS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["findings", "manipulation_score", "unverifiable"],
    "properties": {
        "findings": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "detail", "confidence", "region"],
                "properties": {
                    "name": {"type": "string"},
                    "detail": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "region": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["page", "x", "y", "width", "height"],
                        "properties": {
                            "page": {"type": "integer", "minimum": 1},
                            "x": {"type": "number", "minimum": 0, "maximum": 1},
                            "y": {"type": "number", "minimum": 0, "maximum": 1},
                            "width": {"type": "number", "minimum": 0, "maximum": 1},
                            "height": {"type": "number", "minimum": 0, "maximum": 1},
                        },
                    },
                },
            },
        },
        "manipulation_score": {"type": "number", "minimum": 0, "maximum": 1},
        "unverifiable": {
            "type": "array",
            "maxItems": 5,
            "items": {"type": "string"},
            "description": "Elementos que la calidad de la imagen impide verificar.",
        },
    },
}

# --- 2. Comparación de firmas ------------------------------------------------

SIGNATURE_SYSTEM = """\
Eres un perito calígrafo. Comparas dos imágenes de firma: la primera es la del \
documento en revisión, la segunda es la referencia registrada. Evalúas trazo, \
inclinación, proporciones, puntos de inicio y término, y presión aparente. \
Una copia digital pegada suele mostrar grosor uniforme y bordes limpios."""

SIGNATURE_PROMPT = """\
Compara la firma del documento (primera imagen) con la firma de referencia \
(segunda imagen). Entrega `match_probability` entre 0 y 1 y la lista de \
diferencias observables que sustentan tu evaluación."""

SIGNATURE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["match_probability", "differences"],
    "properties": {
        "match_probability": {"type": "number", "minimum": 0, "maximum": 1},
        "differences": {"type": "array", "maxItems": 6, "items": {"type": "string"}},
    },
}

# --- 3. Razonamiento del perito ----------------------------------------------

REASONING_SYSTEM = """\
Eres un perito documental senior. Recibes hallazgos forenses y verificaciones \
deterministas YA EJECUTADAS sobre un documento, y debes integrarlos en una sola \
valoración explicable.

Reglas que debes respetar sin excepción:
1. Cita ÚNICAMENTE los hallazgos y checks que recibes. Está prohibido inventar \
señales, campos o antecedentes.
2. `score` es la probabilidad de que el documento sea falsificado, entre 0 y 1.
3. Lo que la calidad de la imagen impide verificar se declara como pendiente, \
jamás como aprobado.
4. `explanation_customer` va dirigida a la persona que subió el documento. Debe \
ser breve y decirle QUÉ HACER (volver a fotografiar, traer el original, hablar \
con un ejecutivo). Está PROHIBIDO mencionar en ella qué señal forense se \
detectó, qué check falló, scores, umbrales o modelos: nada de «tipografía», \
«metadatos», «recorte», «RUT inválido», «montos que no cuadran» ni «alterado». \
Tampoco la acuses de falsificar: quien subió el documento puede ser un cliente \
legítimo con una foto mala.
   Ejemplo correcto: «No pudimos validar este documento en línea. Un ejecutivo \
te contactará para revisarlo contigo.»
   Ejemplo INCORRECTO: «La fecha de vencimiento tiene una tipografía distinta.»
5. `explanation_analyst` es técnica: nombra los checks en falla y los hallazgos \
con su región y confianza.
6. `reasons` son frases cortas en español, máximo 5, cada una anclada a una \
evidencia recibida.

Responde solo con el JSON pedido."""

REASONING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "score",
        "confidence",
        "reasons",
        "explanation_customer",
        "explanation_analyst",
    ],
    "properties": {
        "score": {"type": "number", "minimum": 0, "maximum": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reasons": {"type": "array", "maxItems": 5, "items": {"type": "string"}},
        "explanation_customer": {"type": "string"},
        "explanation_analyst": {"type": "string"},
    },
}


def build_reasoning_prompt(
    document_type: str,
    fields: dict[str, Any],
    checks: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    neighbors: list[dict[str, Any]],
    image_quality: float,
    unverifiable: list[str],
) -> str:
    lines = [
        f"## Documento",
        f"Tipo detectado: {document_type}. Calidad de imagen: {image_quality:.2f}.",
        "",
        "## Campos extraídos",
    ]
    if fields:
        for name, entry in list(fields.items())[:12]:
            value = entry.get("value", "") if isinstance(entry, dict) else entry
            confidence = entry.get("confidence", 0) if isinstance(entry, dict) else 0
            lines.append(f"- {name}: «{value}» (confianza {float(confidence):.2f})")
    else:
        lines.append("- No se extrajo ningún campo legible.")
    lines.append("")

    lines.append("## Verificaciones deterministas")
    for check in checks:
        marker = "CRÍTICO " if check.get("critical") else ""
        lines.append(
            f"- [{check['status'].upper()}] {marker}{check['name']}: {check.get('detail', '')}"
        )
    lines.append("")

    lines.append("## Hallazgos forenses")
    if findings:
        for finding in findings[:8]:
            region = finding.get("region") or {}
            where = (
                f" (región x={region.get('x', 0):.2f}, y={region.get('y', 0):.2f}, "
                f"página {region.get('page', 1)})"
                if region
                else ""
            )
            lines.append(
                f"- {finding['name']} (confianza {float(finding.get('confidence', 0)):.2f}): "
                f"{finding.get('detail', '')}{where}"
            )
    else:
        lines.append("- Sin señales de alteración visibles.")
    lines.append("")

    if neighbors:
        lines.append("## Documentos comparables en la memoria de casos")
        for n in neighbors[:5]:
            etiqueta = {
                "falso": "documento falso confirmado",
                "autentico": "documento auténtico",
                "plantilla": "plantilla de referencia",
            }.get(n.get("label", ""), n.get("label", "sin etiqueta"))
            lines.append(f"- {etiqueta}, similitud {n['similarity']:.2f}")
        lines.append("")

    if unverifiable:
        lines.append("## No verificable por la calidad de la imagen")
        lines.extend(f"- {item}" for item in unverifiable[:5])
        lines.append("")

    lines.append(
        "Entrega el JSON con score, confidence, reasons, explanation_customer y "
        "explanation_analyst."
    )
    return "\n".join(lines)
