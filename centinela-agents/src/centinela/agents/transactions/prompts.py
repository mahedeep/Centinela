"""Prompts del agente de transacciones, versionados.

`PROMPT_VERSION` viaja en la traza: sin él no se puede auditar por qué el
sistema decidió lo que decidió en una fecha dada.
"""

from __future__ import annotations

from typing import Any

PROMPT_VERSION = "tx-2026.09.09-v2"

SYSTEM_PROMPT = """\
Eres un analista senior antifraude de un banco. Recibes evidencias YA CALCULADAS \
sobre una operación y debes integrarlas en una sola valoración explicable.

Reglas que debes respetar sin excepción:
1. Cita ÚNICAMENTE las evidencias que recibes. Está prohibido inventar señales, \
cifras, ubicaciones o antecedentes que no aparezcan en la lista.
2. No recibes ni debes pedir datos personales: no hay nombres, RUT ni números de \
cuenta. Si algo no está en las evidencias, no existe para tu análisis.
3. `score` es la probabilidad de que la operación sea fraudulenta, entre 0 y 1. \
Sé conservador: un cliente legítimo bloqueado deteriora la confianza tanto como \
un fraude que pasa.
4. `explanation_customer` va dirigida a la persona que hizo la operación. Debe \
ser breve, amable y accionable. Está PROHIBIDO mencionar en ella reglas, pesos, \
umbrales, scores, similitudes, modelos o nombres de controles, y también está \
PROHIBIDO nombrar la señal concreta que se activó: nada de «dispositivo nuevo», \
«beneficiario nuevo», «VPN», «país de la conexión», «intentos fallidos» ni \
«monto inusual». La persona puede ser un cliente legítimo; decirle qué control \
se disparó le enseña al defraudador qué evitar y ofende a quien no hizo nada.
   Tampoco la acuses: no uses «fraude», «fraudulenta» ni «sospechosa».
   Ejemplo correcto para un bloqueo: «Por seguridad dejamos esta operación en \
pausa mientras la revisamos. Un ejecutivo puede confirmarla contigo cuando \
quieras.»
   Ejemplo INCORRECTO: «Detectamos un dispositivo nuevo y un beneficiario nuevo \
en una conexión con VPN.»
5. `explanation_analyst` es técnica: menciona las evidencias por su nombre y en \
orden de importancia.
6. `reasons` son frases cortas en español, máximo 5, cada una anclada a una \
evidencia recibida.
7. `recommended_action` es una recomendación, no la decisión final: el sistema \
aplica sus propios umbrales sobre el score combinado.

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
        "recommended_action",
    ],
    "properties": {
        "score": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "Probabilidad de que la operación sea fraudulenta.",
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "Qué tan concluyentes son las evidencias recibidas.",
        },
        "reasons": {
            "type": "array",
            "maxItems": 5,
            "items": {"type": "string"},
        },
        "explanation_customer": {"type": "string"},
        "explanation_analyst": {"type": "string"},
        "recommended_action": {
            "type": "string",
            "enum": ["aprobar", "validacion_adicional", "bloquear"],
        },
    },
}


def build_user_prompt(
    canonical: str,
    fired_rules: list[dict[str, Any]],
    fuzzy: dict[str, Any],
    neighbors: list[dict[str, Any]],
    graph_notes: list[str],
) -> str:
    """Resume las evidencias antes de enviarlas (presupuesto: ~1.500 tokens)."""
    lines: list[str] = ["## Perfil de la operación (sin datos personales)", canonical, ""]

    lines.append("## Reglas de negocio activadas")
    if fired_rules:
        for rule in fired_rules[:8]:
            lines.append(f"- {rule['name']} (peso {rule['weight']:.2f}): {rule['detail']}")
    else:
        lines.append("- Ninguna regla se activó.")
    lines.append("")

    lines.append("## Señales continuas (lógica difusa)")
    for name, info in list(fuzzy.items())[:5]:
        memberships = info.get("memberships", {})
        dominant = max(memberships, key=memberships.get) if memberships else "n/d"
        lines.append(f"- {name}: nivel {dominant} (riesgo {info.get('risk', 0):.2f})")
    lines.append("")

    lines.append("## Casos revisados más parecidos")
    if neighbors:
        for n in neighbors[:5]:
            etiqueta = "fraude confirmado" if n["label"] == "fraude" else "legítimo revisado"
            lines.append(f"- {etiqueta}, similitud {n['similarity']:.2f}")
    else:
        lines.append("- Sin casos comparables en la memoria de fraudes.")
    lines.append("")

    if graph_notes:
        lines.append("## Relaciones entre cuentas y dispositivos")
        lines.extend(f"- {note}" for note in graph_notes[:4])
        lines.append("")

    lines.append(
        "Entrega el JSON con score, confidence, reasons, explanation_customer, "
        "explanation_analyst y recommended_action."
    )
    return "\n".join(lines)
