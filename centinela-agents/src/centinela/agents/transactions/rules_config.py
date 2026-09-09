"""Catálogo de reglas y variables difusas del proceso A.

Cada regla lleva una línea de justificación; la tabla completa con los pesos
está en `docs/REGLAS.md`. Los pesos son valores **iniciales** que exigen
calibración con línea base y piloto en modo sombra antes de bloquear a nadie.
"""

from __future__ import annotations

from centinela.core.rules import FuzzyVariable, Rule, RuleEngine

HIGH_AMOUNT_CLP = 1_000_000.0

TRANSACTION_RULES: list[Rule] = [
    Rule(
        name="new_beneficiary_amount_above_average",
        weight=0.45,
        description=(
            "Beneficiario nuevo que recibe más que el promedio mensual del cliente"
        ),
        # Es el patrón de pago único de la ingeniería social (falso ejecutivo,
        # compra inexistente, arriendo falso): el dinero sale una sola vez, a
        # alguien a quien el cliente nunca le había transferido, por sobre lo que
        # ese cliente mueve al mes. Peso alto a propósito: por sí solo debe
        # alcanzar el umbral de validación adicional —el negocio quiere resolver
        # este caso con un código, no con una llamada— pero jamás el de bloqueo.
        predicate=lambda c: c["is_new_beneficiary"] and c["amount_ratio"] > 1.2,
        detail_template=(
            "Beneficiario nuevo recibiendo {amount_ratio}× el promedio mensual del cliente"
        ),
    ),
    Rule(
        name="new_beneficiary",
        weight=0.10,
        description="Beneficiario nuevo (primera transferencia a esa cuenta)",
        # Señal débil por sí sola: la mayoría de los beneficiarios nuevos son
        # legítimos. Suma poco, pero acompaña a las combinaciones peligrosas.
        predicate=lambda c: c["is_new_beneficiary"],
        detail_template="Primera transferencia hacia esta cuenta de destino",
    ),
    Rule(
        name="new_device_and_new_beneficiary",
        weight=0.30,
        description="Dispositivo nuevo y beneficiario nuevo en la misma sesión",
        predicate=lambda c: c["new_device_and_new_beneficiary"],
        detail_template=(
            "Dispositivo nuevo y beneficiario nuevo en la misma sesión: combinación "
            "típica de toma de cuenta"
        ),
    ),
    Rule(
        name="amount_over_3x_average",
        weight=0.25,
        description="Monto mayor a 3× el promedio mensual de la cuenta",
        predicate=lambda c: c["amount_ratio"] > 3.0,
        detail_template="Monto {amount_ratio}× el promedio mensual de la cuenta",
    ),
    Rule(
        name="ip_country_mismatch",
        weight=0.22,
        description="País de la IP distinto al país de la cuenta",
        predicate=lambda c: c["ip_country_mismatch"],
        detail_template="La conexión proviene de un país distinto al de la cuenta",
    ),
    Rule(
        name="velocity_over_5_per_hour",
        weight=0.20,
        description="Más de 5 transacciones en la última hora",
        predicate=lambda c: c["tx_last_hour"] > 5,
        detail_template="{tx_last_hour} operaciones en la última hora",
    ),
    Rule(
        name="structuring_pattern",
        weight=0.30,
        description=(
            "Varias operaciones de monto bajo en una hora hacia un beneficiario nuevo"
        ),
        # Fraccionamiento: el defraudador parte el monto para quedar por debajo
        # del control de monto. Cada operación aislada parece inofensiva; la
        # firma del patrón es la combinación velocidad + beneficiario nuevo +
        # monto muy por debajo del promedio del cliente.
        predicate=lambda c: (
            c["tx_last_hour"] >= 4 and c["amount_ratio"] < 0.5 and c["is_new_beneficiary"]
        ),
        detail_template=(
            "{tx_last_hour} operaciones de monto bajo en una hora hacia un beneficiario nuevo"
        ),
    ),
    Rule(
        name="failed_logins_3_or_more",
        weight=0.18,
        description="Tres o más intentos de acceso fallidos en 24 horas",
        predicate=lambda c: c["failed_logins_24h"] >= 3,
        detail_template="{failed_logins_24h} intentos de acceso fallidos en 24 horas",
    ),
    Rule(
        name="vpn_with_high_amount",
        weight=0.16,
        description=f"VPN activa con monto sobre {HIGH_AMOUNT_CLP:,.0f} CLP",
        predicate=lambda c: c["vpn"] and c["amount_clp"] >= HIGH_AMOUNT_CLP,
        detail_template="VPN activa en una operación de monto alto",
    ),
    Rule(
        name="account_age_under_30_days",
        weight=0.15,
        description="Cuenta de origen con menos de 30 días de antigüedad",
        predicate=lambda c: c["account_age_days"] < 30,
        detail_template="Cuenta de origen abierta hace {account_age_days} días",
    ),
    Rule(
        name="session_under_20_seconds",
        weight=0.12,
        description="Sesión de menos de 20 segundos antes de operar",
        predicate=lambda c: 0 < c["session_seconds"] < 20,
        detail_template="Sesión de {session_seconds} segundos antes de operar",
    ),
    Rule(
        name="night_hours_with_geo_anomaly",
        weight=0.12,
        description="Horario nocturno (00:00–06:00) desde una ubicación inusual",
        predicate=lambda c: c["night_hours"] and c["geo_anomaly"],
        detail_template="Operación nocturna a {distance_from_home_km} km del domicilio",
    ),
    Rule(
        name="cross_border_new_beneficiary",
        weight=0.14,
        description="Beneficiario nuevo en otro país",
        predicate=lambda c: c["is_new_beneficiary"] and c["cross_border"],
        detail_template="Beneficiario nuevo domiciliado en otro país",
    ),
]

# Variables continuas: evitan que un corte duro decida el caso por sí solo.
TRANSACTION_FUZZY: list[FuzzyVariable] = [
    FuzzyVariable(
        name="amount_ratio",
        weight=0.40,
        low=(-1.0, 0.0, 0.8, 1.5),
        medium=(0.8, 1.5, 2.5, 3.5),
        high=(2.5, 4.0),
    ),
    FuzzyVariable(
        name="velocity_score",
        weight=0.35,
        low=(-1.0, 0.0, 0.20, 0.40),
        medium=(0.20, 0.40, 0.60, 0.80),
        high=(0.55, 0.85),
    ),
    FuzzyVariable(
        name="distance_from_home_km",
        weight=0.25,
        low=(-1.0, 0.0, 20.0, 60.0),
        medium=(20.0, 60.0, 150.0, 300.0),
        high=(150.0, 500.0),
    ),
]


def build_engine() -> RuleEngine:
    return RuleEngine(TRANSACTION_RULES, TRANSACTION_FUZZY)


def rules_table() -> list[dict[str, object]]:
    """Tabla de reglas para la documentación y el endpoint de ajustes."""
    return [
        {"name": r.name, "weight": r.weight, "description": r.description}
        for r in sorted(TRANSACTION_RULES, key=lambda r: -r.weight)
    ]
