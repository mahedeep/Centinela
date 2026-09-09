"""Esquemas de entrada del agente de transacciones."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Channel = Literal["app_movil", "web", "cajero", "sucursal", "call_center", "api"]
TxType = Literal["transferencia", "pago", "retiro", "compra"]


class OriginAccount(BaseModel):
    id: str
    age_days: int = Field(ge=0, description="Antigüedad de la cuenta en días.")
    avg_monthly_amount: float = Field(ge=0, description="Monto promedio mensual, en CLP.")
    country: str = "CL"


class DestinationAccount(BaseModel):
    id: str
    bank: str = ""
    is_new_beneficiary: bool = False
    country: str = "CL"


class Device(BaseModel):
    id: str = ""
    is_new_device: bool = False
    os: str = ""
    ip_country: str = "CL"
    vpn: bool = False


class Geo(BaseModel):
    lat: float | None = None
    lon: float | None = None
    distance_from_home_km: float = Field(default=0.0, ge=0.0)


class Behavior(BaseModel):
    tx_last_hour: int = Field(default=0, ge=0)
    tx_last_24h: int = Field(default=0, ge=0)
    failed_logins_24h: int = Field(default=0, ge=0)
    session_seconds: int = Field(default=0, ge=0)


class CustomerProfile(BaseModel):
    segment: Literal["persona_natural", "empresa"] = "persona_natural"
    risk_tier: Literal["bajo", "medio", "alto"] = "medio"


class TransactionInput(BaseModel):
    """Entrada del proceso A. Los identificadores son opacos (no hay PII)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "transaction_id": "TX-000123",
                "timestamp": "2026-09-08T14:32:10-03:00",
                "amount": 1250000,
                "currency": "CLP",
                "channel": "app_movil",
                "type": "transferencia",
                "origin_account": {
                    "id": "ACC-1001",
                    "age_days": 1450,
                    "avg_monthly_amount": 900000,
                    "country": "CL",
                },
                "destination_account": {
                    "id": "ACC-7781",
                    "bank": "OtroBanco",
                    "is_new_beneficiary": True,
                    "country": "CL",
                },
                "device": {
                    "id": "DEV-55",
                    "is_new_device": True,
                    "os": "Android",
                    "ip_country": "CL",
                    "vpn": False,
                },
                "geo": {"lat": -33.45, "lon": -70.66, "distance_from_home_km": 3.2},
                "behavior": {
                    "tx_last_hour": 3,
                    "tx_last_24h": 7,
                    "failed_logins_24h": 2,
                    "session_seconds": 40,
                },
                "customer_profile": {"segment": "persona_natural", "risk_tier": "medio"},
            }
        }
    )

    transaction_id: str
    timestamp: datetime
    amount: float = Field(gt=0)
    currency: str = "CLP"
    channel: Channel = "app_movil"
    type: TxType = "transferencia"
    origin_account: OriginAccount
    destination_account: DestinationAccount
    device: Device = Field(default_factory=Device)
    geo: Geo = Field(default_factory=Geo)
    behavior: Behavior = Field(default_factory=Behavior)
    customer_profile: CustomerProfile = Field(default_factory=CustomerProfile)


class BatchTransactionInput(BaseModel):
    """Lote para replay y modo sombra. Máximo 200 por llamada."""

    transactions: list[TransactionInput] = Field(min_length=1, max_length=200)
