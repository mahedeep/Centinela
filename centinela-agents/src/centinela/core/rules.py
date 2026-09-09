"""Motor de reglas y score fuzzy.

Diseño (justificado en `docs/REGLAS.md`):

- Cada regla es una función pura `contexto -> bool` con un peso en [0, 1].
- La combinación NO es una suma: es una **OR ruidosa**
  `1 - Π(1 - wᵢ)` sobre las reglas que se activaron. Así el score queda acotado
  en [0, 1] sin normalizaciones arbitrarias, y añadir una regla débil nunca
  empuja el total por encima de lo que aportan las fuertes.
- El score fuzzy usa funciones de pertenencia trapezoidales (bajo/medio/alto)
  sobre variables continuas, para no depender de cortes duros.
- El score de la fuente "reglas" que consume el agente es
  `0,60 · OR_ruidosa + 0,40 · fuzzy`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from centinela.schemas import Evidence

RULES_NOISY_OR_WEIGHT = 0.60
RULES_FUZZY_WEIGHT = 0.40


@dataclass(frozen=True)
class Rule:
    """Una regla de negocio explícita y auditable."""

    name: str
    weight: float
    description: str
    predicate: Callable[[dict[str, Any]], bool]
    detail_template: str = ""

    def evaluate(self, context: dict[str, Any]) -> tuple[bool, Evidence]:
        try:
            fired = bool(self.predicate(context))
        except (KeyError, TypeError, ValueError):
            fired = False
        detail = self.detail_template.format(**context) if fired and self.detail_template else (
            self.description if fired else f"No se cumple: {self.description}"
        )
        return fired, Evidence(
            type="rule",
            name=self.name,
            value=fired,
            weight=self.weight,
            detail=detail,
        )


# --- Funciones de pertenencia ------------------------------------------------


def trapezoid(x: float, a: float, b: float, c: float, d: float) -> float:
    """Pertenencia trapezoidal: 0 antes de `a`, sube hasta 1 en [b, c], baja a 0 en `d`."""
    if x <= a or x >= d:
        return 0.0
    if b <= x <= c:
        return 1.0
    if a < x < b:
        return (x - a) / (b - a) if b > a else 1.0
    return (d - x) / (d - c) if d > c else 1.0


def ramp_up(x: float, a: float, b: float) -> float:
    """Rampa creciente: 0 hasta `a`, 1 desde `b`."""
    if x <= a:
        return 0.0
    if x >= b:
        return 1.0
    return (x - a) / (b - a)


@dataclass(frozen=True)
class FuzzyVariable:
    """Variable continua con tres conjuntos difusos y un peso en el score."""

    name: str
    weight: float
    low: tuple[float, float, float, float]
    medium: tuple[float, float, float, float]
    high: tuple[float, float]  # rampa creciente (a, b)

    def memberships(self, x: float) -> dict[str, float]:
        return {
            "bajo": trapezoid(x, *self.low),
            "medio": trapezoid(x, *self.medium),
            "alto": ramp_up(x, *self.high),
        }

    def risk(self, x: float) -> float:
        """Defuzzificación por centroide sobre riesgos {bajo:0, medio:0,5, alto:1}."""
        m = self.memberships(x)
        total = m["bajo"] + m["medio"] + m["alto"]
        if total == 0.0:
            return 0.0
        return (m["bajo"] * 0.0 + m["medio"] * 0.5 + m["alto"] * 1.0) / total


class RuleEngine:
    """Evalúa un conjunto de reglas y produce evidencias + score combinado."""

    def __init__(self, rules: Sequence[Rule], fuzzy_variables: Sequence[FuzzyVariable] = ()):
        self.rules = list(rules)
        self.fuzzy_variables = list(fuzzy_variables)

    # -- reglas -------------------------------------------------------------
    def evaluate_rules(self, context: dict[str, Any]) -> tuple[list[Evidence], list[Evidence]]:
        """Devuelve (evidencias de reglas activadas, todas las evidencias)."""
        all_ev: list[Evidence] = []
        fired: list[Evidence] = []
        for rule in self.rules:
            did_fire, evidence = rule.evaluate(context)
            all_ev.append(evidence)
            if did_fire:
                fired.append(evidence)
        fired.sort(key=lambda e: e.weight, reverse=True)
        return fired, all_ev

    @staticmethod
    def noisy_or(weights: Sequence[float]) -> float:
        """`1 - Π(1 - w)`. Acotado, monótono y sin normalización arbitraria."""
        product = 1.0
        for w in weights:
            product *= 1.0 - max(0.0, min(1.0, float(w)))
        return round(1.0 - product, 6)

    # -- fuzzy --------------------------------------------------------------
    def fuzzy_score(self, values: dict[str, float]) -> tuple[float, dict[str, Any]]:
        """Media ponderada del riesgo difuso de cada variable presente."""
        detail: dict[str, Any] = {}
        numerator = 0.0
        denominator = 0.0
        for var in self.fuzzy_variables:
            if var.name not in values:
                continue
            x = float(values[var.name])
            risk = var.risk(x)
            detail[var.name] = {
                "value": x,
                "memberships": {k: round(v, 4) for k, v in var.memberships(x).items()},
                "risk": round(risk, 4),
            }
            numerator += var.weight * risk
            denominator += var.weight
        score = round(numerator / denominator, 6) if denominator else 0.0
        return score, detail

    # -- combinación --------------------------------------------------------
    def combined_score(
        self, context: dict[str, Any], fuzzy_values: dict[str, float]
    ) -> tuple[float, list[Evidence], dict[str, Any]]:
        fired, all_ev = self.evaluate_rules(context)
        rules_component = self.noisy_or([e.weight for e in fired])
        fuzzy_component, fuzzy_detail = self.fuzzy_score(fuzzy_values)
        score = round(
            RULES_NOISY_OR_WEIGHT * rules_component + RULES_FUZZY_WEIGHT * fuzzy_component, 6
        )
        breakdown = {
            "noisy_or": rules_component,
            "fuzzy": fuzzy_component,
            "fuzzy_detail": fuzzy_detail,
            "fired_rules": [e.name for e in fired],
            "rules_evaluated": len(all_ev),
        }
        return score, fired, breakdown
