"""Derivación de features y descripción canónica sin datos personales."""

from __future__ import annotations

from typing import Any

from centinela.agents.transactions.schemas import TransactionInput

# Tasas de conversión a CLP para el MVP (datos sintéticos). En producción esto
# viene de un servicio de tipo de cambio, no de una constante.
FX_TO_CLP: dict[str, float] = {"CLP": 1.0, "USD": 950.0, "EUR": 1030.0, "UF": 38000.0}

NIGHT_START_HOUR = 0
NIGHT_END_HOUR = 6
GEO_ANOMALY_KM = 150.0


def to_clp(amount: float, currency: str) -> float:
    """Normaliza el monto a CLP. Moneda desconocida → se asume CLP y se avisa."""
    return round(amount * FX_TO_CLP.get(currency.upper(), 1.0), 2)


def derive_features(tx: TransactionInput) -> dict[str, Any]:
    """Features que consumen las reglas, el score fuzzy y el texto canónico."""
    amount_clp = to_clp(tx.amount, tx.currency)
    avg = max(tx.origin_account.avg_monthly_amount, 1.0)
    hour = tx.timestamp.hour

    velocity_score = min(1.0, tx.behavior.tx_last_hour / 6.0) * 0.7 + min(
        1.0, tx.behavior.tx_last_24h / 20.0
    ) * 0.3

    return {
        "amount_clp": amount_clp,
        "amount_ratio": round(amount_clp / avg, 4),
        "velocity_score": round(velocity_score, 4),
        "new_device_and_new_beneficiary": bool(
            tx.device.is_new_device and tx.destination_account.is_new_beneficiary
        ),
        "night_hours": NIGHT_START_HOUR <= hour < NIGHT_END_HOUR,
        "hour": hour,
        "geo_anomaly": tx.geo.distance_from_home_km >= GEO_ANOMALY_KM,
        "distance_from_home_km": tx.geo.distance_from_home_km,
        "ip_country_mismatch": tx.device.ip_country.upper()
        != tx.origin_account.country.upper(),
        "cross_border": tx.destination_account.country.upper()
        != tx.origin_account.country.upper(),
        "vpn": tx.device.vpn,
        "is_new_device": tx.device.is_new_device,
        "is_new_beneficiary": tx.destination_account.is_new_beneficiary,
        "account_age_days": tx.origin_account.age_days,
        "tx_last_hour": tx.behavior.tx_last_hour,
        "tx_last_24h": tx.behavior.tx_last_24h,
        "failed_logins_24h": tx.behavior.failed_logins_24h,
        "session_seconds": tx.behavior.session_seconds,
        "channel": tx.channel,
        "type": tx.type,
        "risk_tier": tx.customer_profile.risk_tier,
        "segment": tx.customer_profile.segment,
    }


# --- Descripción canónica ----------------------------------------------------
# Prohibido enviar datos personales al modelo: la plantilla usa rangos y
# categorías, jamás montos exactos, identificadores de cuenta ni nombres.


def _bucket_amount_ratio(ratio: float) -> str:
    if ratio < 0.25:
        return "muy por debajo del promedio"
    if ratio < 0.8:
        return "por debajo del promedio"
    if ratio < 1.5:
        return "en torno al promedio"
    if ratio < 3.0:
        return "entre 1,5 y 3 veces el promedio"
    return "más de 3 veces el promedio"


def _bucket_distance(km: float) -> str:
    if km < 20:
        return "dentro de la zona habitual"
    if km < 150:
        return "fuera de la zona habitual"
    return "muy lejos de la zona habitual"


def _bucket_age(days: int) -> str:
    if days < 30:
        return "cuenta abierta hace menos de un mes"
    if days < 365:
        return "cuenta de menos de un año"
    return "cuenta antigua"


def canonical_text(features: dict[str, Any]) -> str:
    """Texto canónico y estable usado para el embedding de similitud.

    Plantilla fija: dos transacciones con el mismo patrón producen textos casi
    idénticos, que es exactamente lo que la búsqueda por coseno necesita.
    """
    parts = [
        f"operacion tipo {features['type']} por canal {features['channel']}",
        f"monto {_bucket_amount_ratio(features['amount_ratio'])}",
        _bucket_age(int(features["account_age_days"])),
        "beneficiario nuevo" if features["is_new_beneficiary"] else "beneficiario conocido",
        "dispositivo nuevo" if features["is_new_device"] else "dispositivo conocido",
        "ip de otro pais" if features["ip_country_mismatch"] else "ip del pais de la cuenta",
        "con vpn" if features["vpn"] else "sin vpn",
        f"ubicacion {_bucket_distance(float(features['distance_from_home_km']))}",
        f"{'horario nocturno' if features['night_hours'] else 'horario diurno'}",
        f"{features['tx_last_hour']} operaciones en la ultima hora",
        f"{features['failed_logins_24h']} intentos de acceso fallidos",
        "sesion muy corta"
        if features["session_seconds"] < 20
        else ("sesion corta" if features["session_seconds"] < 60 else "sesion normal"),
        f"perfil {features['segment']} riesgo {features['risk_tier']}",
    ]
    return "; ".join(parts)
