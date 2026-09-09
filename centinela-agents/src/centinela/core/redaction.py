"""Barrera de lo que el cliente puede leer.

El prompt le pide al modelo que no revele controles en
`explanation_customer`, pero un prompt es una petición, no una garantía: en las
pruebas contra el modelo real aparecieron textos del tipo «verifica que
reconoces el acceso, el dispositivo y el beneficiario», que le dicen al cliente
exactamente qué señal se activó.

Este módulo verifica el texto antes de devolverlo y, si filtra, lo reemplaza por
la redacción segura del veredicto. El texto original y los términos detectados
quedan en la traza, para poder ajustar el prompt con evidencia.
"""

from __future__ import annotations

import re
import unicodedata

# Términos que revelan controles internos. Se comparan sin tildes y sin
# distinguir mayúsculas, sobre palabras completas o prefijos.
FORBIDDEN_CUSTOMER_TERMS: tuple[str, ...] = (
    # Mecánica de la decisión
    "score",
    "puntaje",
    "umbral",
    "regla",
    "modelo",
    "algoritmo",
    "similitud",
    "evidencia",
    "peso",
    "prompt",
    "inteligencia artificial",
    # Señales de transacciones
    "vpn",
    "dispositivo",
    "beneficiario",
    "geolocaliza",
    "direccion ip",
    "intentos fallidos",
    # Señales documentales
    "forense",
    "tipografia",
    "metadato",
    "recorte",
    "compresion",
    "pixel",
    "modulo 11",
    "digito verificador",
    # Calificaciones que dañan la confianza de un cliente legítimo
    "fraude",
    "fraudulent",
    "falsific",
    "adulterad",
)

# Redacción segura por veredicto. Es la misma que usa el agente cuando el
# modelo no devuelve texto.
SAFE_CUSTOMER_TEXT: dict[str, str] = {
    "aprobar": "Tu operación se realizó correctamente.",
    "validacion_adicional": (
        "Para confirmar que eres tú, vamos a pedirte un código de verificación "
        "antes de completar la operación."
    ),
    "bloquear": (
        "Por seguridad dejamos esta operación en pausa mientras la revisamos. "
        "Un ejecutivo puede confirmarla contigo cuando quieras."
    ),
    "autentico": "Tu documento fue validado correctamente. No necesitas hacer nada más.",
    "sospechoso": (
        "Necesitamos revisar este documento con más detalle. Si puedes, súbelo "
        "nuevamente desde el original."
    ),
    "falso": (
        "No pudimos validar este documento en línea. Un ejecutivo te contactará "
        "para revisarlo contigo."
    ),
}


def _fold(text: str) -> str:
    """Minúsculas sin tildes: «Tipografía» y «tipografia» son el mismo término."""
    normalized = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def find_leaks(text: str) -> list[str]:
    """Devuelve los términos prohibidos que aparecen en el texto."""
    folded = _fold(text)
    return [
        term
        for term in FORBIDDEN_CUSTOMER_TERMS
        # `\b` al inicio evita coincidencias dentro de otra palabra; sin `\b`
        # final, para que «reglas», «dispositivos» o «metadatos» también caigan.
        if re.search(rf"\b{re.escape(term)}", folded)
    ]


def sanitize_customer_text(text: str, verdict: str) -> tuple[str, list[str]]:
    """Devuelve (texto apto para el cliente, términos filtrados).

    Si el texto filtra un solo término, se descarta completo: intentar tachar
    palabras deja frases rotas y no garantiza que el resto no siga revelando el
    control.
    """
    safe = SAFE_CUSTOMER_TEXT.get(verdict, SAFE_CUSTOMER_TEXT["sospechoso"])
    candidate = (text or "").strip()
    if not candidate:
        return safe, []
    leaks = find_leaks(candidate)
    return (safe, leaks) if leaks else (candidate, [])
