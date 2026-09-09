"""Configuración de tests: base temporal por sesión y MOCK_MODE forzado.

Ningún test toca la red. `MOCK_MODE=true` se fija antes de importar el paquete.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ["MOCK_MODE"] = "true"
os.environ["SHADOW_MODE"] = "false"
os.environ["OPENAI_API_KEY"] = ""
os.environ["EXPORT_OPENAPI"] = "false"


@pytest.fixture(scope="session", autouse=True)
def temp_data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Aísla base de datos, trazas y muestras en un directorio temporal."""
    directory = tmp_path_factory.mktemp("centinela-data")
    os.environ["DATA_DIR"] = str(directory)
    os.environ["DATABASE_URL"] = f"sqlite:///{directory / 'test.db'}"

    from centinela.config import reset_settings_cache
    from centinela.core.db import get_engine, reset_engine

    reset_settings_cache()
    reset_engine()
    (directory / "samples").mkdir(parents=True, exist_ok=True)
    (directory / "traces").mkdir(parents=True, exist_ok=True)
    get_engine()
    yield directory
    reset_engine()


@pytest.fixture()
def client(temp_data_dir: Path):
    from fastapi.testclient import TestClient

    from centinela.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def sample_transaction() -> dict:
    """Transacción base, legítima. Los tests la modifican según lo que prueban."""
    return {
        "transaction_id": "TX-TEST-0001",
        "timestamp": "2026-09-08T14:32:10-03:00",
        "amount": 85_000,
        "currency": "CLP",
        "channel": "app_movil",
        "type": "pago",
        "origin_account": {
            "id": "ACC-1001",
            "age_days": 1450,
            "avg_monthly_amount": 900_000,
            "country": "CL",
        },
        "destination_account": {
            "id": "ACC-7001",
            "bank": "OtroBanco",
            "is_new_beneficiary": False,
            "country": "CL",
        },
        "device": {
            "id": "DEV-1",
            "is_new_device": False,
            "os": "iOS",
            "ip_country": "CL",
            "vpn": False,
        },
        "geo": {"distance_from_home_km": 2.1},
        "behavior": {
            "tx_last_hour": 0,
            "tx_last_24h": 1,
            "failed_logins_24h": 0,
            "session_seconds": 180,
        },
        "customer_profile": {"segment": "persona_natural", "risk_tier": "medio"},
    }


@pytest.fixture()
def fraud_transaction(sample_transaction: dict) -> dict:
    """Toma de cuenta: dispositivo y beneficiario nuevos, IP extranjera, VPN."""
    payload = {**sample_transaction}
    payload["transaction_id"] = "TX-TEST-FRAUD"
    payload["amount"] = 3_900_000
    payload["type"] = "transferencia"
    payload["channel"] = "web"
    payload["destination_account"] = {**payload["destination_account"], "is_new_beneficiary": True}
    payload["device"] = {
        "id": "DEV-999",
        "is_new_device": True,
        "os": "Android",
        "ip_country": "BR",
        "vpn": True,
    }
    payload["geo"] = {"distance_from_home_km": 640.0}
    payload["behavior"] = {
        "tx_last_hour": 3,
        "tx_last_24h": 7,
        "failed_logins_24h": 5,
        "session_seconds": 22,
    }
    return payload
