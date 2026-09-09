#!/usr/bin/env python3
"""Genera datos sintéticos y siembra la memoria de casos confirmados.

- 1.000 transacciones etiquetadas (3 % fraude) con cinco patrones realistas.
- 20 casos de fraude confirmado y 20 legítimos revisados, indexados en el vector
  store para que la similitud tenga con qué comparar desde el primer día.

Semilla fija: el set es reproducible. Todos los identificadores son ficticios.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone

import _bootstrap  # noqa: F401
from centinela.agents.transactions.features import canonical_text, derive_features
from centinela.agents.transactions.schemas import TransactionInput
from centinela.config import get_settings
from centinela.core.db import get_engine
from centinela.core.llm import LLMClient
from centinela.core.vector_store import NS_TRANSACTIONS, get_vector_store, stable_id

SEED = 20260909
FRAUD_RATE = 0.03
BASE_DATE = datetime(2026, 9, 1, tzinfo=timezone(timedelta(hours=-3)))

PATTERNS = (
    "cuenta_mula",
    "account_takeover",
    "beneficiario_nuevo",
    "fraccionamiento",
    "nocturna_ubicacion_inusual",
)


def _legit(rng: random.Random, index: int) -> dict:
    avg = rng.choice([250_000, 500_000, 900_000, 1_800_000, 2_800_000])
    return {
        "transaction_id": f"TX-S{index:06d}",
        "timestamp": (BASE_DATE + timedelta(minutes=rng.randint(0, 43_200))).replace(
            hour=rng.randint(8, 22)
        ).isoformat(),
        "amount": round(avg * rng.uniform(0.03, 1.1)),
        "currency": "CLP",
        "channel": rng.choice(["app_movil", "app_movil", "web", "sucursal", "cajero"]),
        "type": rng.choice(["transferencia", "pago", "compra", "retiro"]),
        "origin_account": {
            "id": f"ACC-{rng.randint(1000, 1999)}",
            "age_days": rng.randint(400, 3600),
            "avg_monthly_amount": avg,
            "country": "CL",
        },
        "destination_account": {
            "id": f"ACC-{rng.randint(7000, 7999)}",
            "bank": rng.choice(["OtroBanco", "Banco Sur", "PagoYa", "Banco Ejemplo"]),
            "is_new_beneficiary": rng.random() < 0.18,
            "country": "CL",
        },
        "device": {
            "id": f"DEV-{rng.randint(1, 120)}",
            "is_new_device": rng.random() < 0.06,
            "os": rng.choice(["Android", "iOS", "Windows", "macOS"]),
            "ip_country": "CL",
            "vpn": rng.random() < 0.03,
        },
        "geo": {"distance_from_home_km": round(rng.uniform(0.2, 25.0), 1)},
        "behavior": {
            "tx_last_hour": rng.choice([0, 0, 0, 1, 1, 2]),
            "tx_last_24h": rng.randint(0, 8),
            "failed_logins_24h": rng.choice([0, 0, 0, 0, 1]),
            "session_seconds": rng.randint(45, 420),
        },
        "customer_profile": {
            "segment": rng.choice(["persona_natural"] * 9 + ["empresa"]),
            "risk_tier": rng.choice(["bajo", "medio", "medio", "alto"]),
        },
    }


def _fraud(rng: random.Random, index: int, pattern: str) -> dict:
    tx = _legit(rng, index)
    dest = tx["destination_account"]
    device = tx["device"]
    behavior = tx["behavior"]
    avg = tx["origin_account"]["avg_monthly_amount"]

    if pattern == "cuenta_mula":
        # Varias cuentas distintas fondean el mismo destino en pocas horas.
        dest["id"] = f"ACC-{7900 + (index % 4)}"
        dest["is_new_beneficiary"] = True
        tx["amount"] = round(avg * rng.uniform(0.8, 1.8))
        tx["type"] = "transferencia"
        behavior["tx_last_hour"] = rng.randint(2, 4)
    elif pattern == "account_takeover":
        # Dispositivo nuevo, IP extranjera, intentos fallidos, sesión mínima.
        device.update(
            is_new_device=True,
            ip_country=rng.choice(["BR", "PE", "AR", "VE"]),
            vpn=rng.random() < 0.7,
            id=f"DEV-{rng.randint(900, 999)}",
        )
        dest["is_new_beneficiary"] = True
        tx["amount"] = round(avg * rng.uniform(2.5, 5.0))
        tx["channel"] = rng.choice(["web", "app_movil"])
        behavior.update(
            failed_logins_24h=rng.randint(3, 7),
            session_seconds=rng.randint(8, 25),
            tx_last_hour=rng.randint(1, 3),
        )
        tx["geo"]["distance_from_home_km"] = round(rng.uniform(300, 4000), 1)
    elif pattern == "beneficiario_nuevo":
        # Ingeniería social: un pago único, grande, a alguien nuevo.
        dest["is_new_beneficiary"] = True
        tx["amount"] = round(avg * rng.uniform(1.4, 3.2))
        tx["type"] = "transferencia"
        behavior["session_seconds"] = rng.randint(30, 90)
    elif pattern == "fraccionamiento":
        # Muchos montos pequeños seguidos para no gatillar el control de monto.
        dest["is_new_beneficiary"] = True
        tx["amount"] = round(avg * rng.uniform(0.15, 0.35))
        behavior.update(tx_last_hour=rng.randint(6, 12), tx_last_24h=rng.randint(14, 30))
        behavior["session_seconds"] = rng.randint(15, 60)
    elif pattern == "nocturna_ubicacion_inusual":
        stamp = datetime.fromisoformat(tx["timestamp"]).replace(hour=rng.randint(0, 5))
        tx["timestamp"] = stamp.isoformat()
        tx["geo"]["distance_from_home_km"] = round(rng.uniform(200, 2500), 1)
        device["is_new_device"] = rng.random() < 0.6
        dest["is_new_beneficiary"] = True
        tx["amount"] = round(avg * rng.uniform(1.2, 3.5))
    return tx


def generate(count: int = 1000) -> list[dict]:
    rng = random.Random(SEED)
    rows: list[dict] = []
    fraud_count = int(count * FRAUD_RATE)
    fraud_positions = set(rng.sample(range(count), fraud_count))

    for index in range(count):
        if index in fraud_positions:
            pattern = PATTERNS[index % len(PATTERNS)]
            rows.append({**_fraud(rng, index, pattern), "etiqueta": "fraude", "patron": pattern})
        else:
            rows.append({**_legit(rng, index), "etiqueta": "legitimo", "patron": None})
    return rows


def seed_vector_store(rows: list[dict], per_label: int = 20) -> int:
    """Indexa casos confirmados como memoria inicial de similitud."""
    store = get_vector_store()
    client = LLMClient()

    frauds = [r for r in rows if r["etiqueta"] == "fraude"][:per_label]
    legits = [r for r in rows if r["etiqueta"] == "legitimo"][:per_label]

    indexed = 0
    for row in frauds + legits:
        payload = {k: v for k, v in row.items() if k not in ("etiqueta", "patron")}
        tx = TransactionInput.model_validate(payload)
        canonical = canonical_text(derive_features(tx))
        label = "fraude" if row["etiqueta"] == "fraude" else "legitimo"
        vector = client.embed([canonical])[0]
        store.upsert(
            NS_TRANSACTIONS,
            stable_id(row["transaction_id"]),
            canonical,
            vector,
            label=label,
            meta={
                "source": "seed_synthetic",
                "transaction_id": row["transaction_id"],
                "patron": row["patron"],
            },
        )
        indexed += 1
    return indexed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--no-index", action="store_true", help="No sembrar el vector store.")
    args = parser.parse_args()

    settings = get_settings()
    get_engine()

    rows = generate(args.count)
    out = settings.data_path / "synthetic"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "transactions.json"
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    fraud = sum(1 for r in rows if r["etiqueta"] == "fraude")
    print(f"{len(rows)} transacciones sintéticas → {path}")
    print(f"  fraude: {fraud} ({fraud / len(rows):.1%}) · legítimas: {len(rows) - fraud}")

    if not args.no_index:
        indexed = seed_vector_store(rows)
        print(f"  {indexed} casos indexados en el vector store (memoria de similitud)")
        if settings.mock_mode or not settings.has_openai:
            print("  NOTA: embeddings deterministas de MOCK_MODE, no semánticos.")


if __name__ == "__main__":
    main()
