#!/usr/bin/env python3
"""Carga el set de prueba del kit (`datos_prueba_centinela.xlsx`).

Lee la hoja `transacciones`, la convierte al esquema `TransactionInput` y la
deja en `data/synthetic/transactions_kit.json`, lista para `evaluate_transactions.py`.
También extrae `escenarios_demo` para que el front precargue los tres casos.

No depende de openpyxl ni pandas: un .xlsx es un ZIP con XML.
"""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import _bootstrap  # noqa: F401
from centinela.config import get_settings

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
T = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(node.text or "" for node in si.iter(T)) for si in root]


def _sheets(zf: zipfile.ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    targets = {rel.get("Id"): rel.get("Target") for rel in rels}
    return {
        sheet.get("name"): targets[sheet.get(REL)].lstrip("/")
        for sheet in workbook.find("m:sheets", NS)
    }


def read_sheet(path: Path, sheet_name: str) -> list[dict[str, str]]:
    """Devuelve la hoja como lista de diccionarios, usando la fila 1 como cabecera."""
    with zipfile.ZipFile(path) as zf:
        strings = _shared_strings(zf)
        target = _sheets(zf)[sheet_name]
        target = target if target.startswith("xl/") else f"xl/{target}"
        sheet = ET.fromstring(zf.read(target))

    rows: list[dict[str, str]] = []
    header: list[str] = []
    for row in sheet.iter(f"{{{NS['m']}}}row"):
        cells: dict[str, str] = {}
        for cell in row:
            column = re.match(r"([A-Z]+)", cell.get("r") or "A").group(1)
            kind = cell.get("t")
            formula = cell.find("m:f", NS)
            value_node = cell.find("m:v", NS)

            if value_node is not None:
                raw = value_node.text or ""
                value = strings[int(raw)] if kind == "s" and raw.isdigit() else raw
            else:
                inline = cell.find("m:is", NS)
                value = "".join(n.text or "" for n in inline.iter(T)) if inline is not None else ""

            # Los booleanos vienen como fórmulas =TRUE()/=FALSE() con valor 1/0.
            if formula is not None and (formula.text or "").upper() in ("TRUE()", "FALSE()"):
                value = "1" if (formula.text or "").upper() == "TRUE()" else "0"
            cells[column] = value

        if not header:
            header = [cells.get(chr(65 + i), "") for i in range(len(cells))]
            header = [cells[k] for k in sorted(cells, key=_col_index)]
            continue
        ordered = [cells.get(k, "") for k in sorted(cells, key=_col_index)]
        rows.append(dict(zip(header, ordered + [""] * (len(header) - len(ordered)))))
    return rows


def _col_index(column: str) -> int:
    value = 0
    for char in column:
        value = value * 26 + (ord(char) - 64)
    return value


def _bool(value: str) -> bool:
    return str(value).strip().lower() in ("1", "true", "verdadero", "si", "sí")


def _num(value: str, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def to_transaction(row: dict[str, str]) -> dict:
    """Aplana las columnas del .xlsx al esquema anidado `TransactionInput`."""
    return {
        "transaction_id": row["transaction_id"],
        "timestamp": row["timestamp"],
        "amount": _num(row["amount"]),
        "currency": row.get("currency") or "CLP",
        "channel": row.get("channel") or "app_movil",
        "type": row.get("type") or "transferencia",
        "origin_account": {
            "id": row["origin_account_id"],
            "age_days": int(_num(row["origin_age_days"])),
            "avg_monthly_amount": _num(row["origin_avg_monthly_amount"]),
            "country": row.get("origin_country") or "CL",
        },
        "destination_account": {
            "id": row["destination_account_id"],
            "bank": row.get("destination_bank", ""),
            "is_new_beneficiary": _bool(row.get("is_new_beneficiary", "0")),
            "country": row.get("destination_country") or "CL",
        },
        "device": {
            "id": row.get("device_id", ""),
            "is_new_device": _bool(row.get("is_new_device", "0")),
            "os": row.get("os", ""),
            "ip_country": row.get("ip_country") or "CL",
            "vpn": _bool(row.get("vpn", "0")),
        },
        "geo": {"distance_from_home_km": _num(row.get("distance_from_home_km", "0"))},
        "behavior": {
            "tx_last_hour": int(_num(row.get("tx_last_hour", "0"))),
            "tx_last_24h": int(_num(row.get("tx_last_24h", "0"))),
            "failed_logins_24h": int(_num(row.get("failed_logins_24h", "0"))),
            "session_seconds": int(_num(row.get("session_seconds", "0"))),
        },
        "customer_profile": {
            "segment": row.get("segment") or "persona_natural",
            "risk_tier": row.get("risk_tier") or "medio",
        },
    }


def scenario_to_transaction(row: dict[str, str], index: int) -> dict:
    """Los tres escenarios de demo traen solo las columnas que cambian."""
    now = datetime.now(timezone(timedelta(hours=-3))).replace(microsecond=0)
    return {
        "transaction_id": f"TX-DEMO-{index:02d}",
        "timestamp": now.isoformat(),
        "amount": _num(row["amount"]),
        "currency": "CLP",
        "channel": row.get("channel") or "app_movil",
        "type": row.get("type") or "transferencia",
        "origin_account": {
            "id": "ACC-1001",
            "age_days": 1450,
            "avg_monthly_amount": _num(row["origin_avg_monthly_amount"], 900_000),
            "country": "CL",
        },
        "destination_account": {
            "id": f"ACC-77{index:02d}",
            "bank": "OtroBanco",
            "is_new_beneficiary": _bool(row.get("is_new_beneficiary", "0")),
            "country": "CL",
        },
        "device": {
            "id": f"DEV-{index}",
            "is_new_device": _bool(row.get("is_new_device", "0")),
            "os": "Android",
            "ip_country": row.get("ip_country") or "CL",
            "vpn": _bool(row.get("vpn", "0")),
        },
        "geo": {"distance_from_home_km": _num(row.get("distance_from_home_km", "0"))},
        "behavior": {
            "tx_last_hour": int(_num(row.get("tx_last_hour", "0"))),
            "tx_last_24h": int(_num(row.get("tx_last_hour", "0"))) * 2,
            "failed_logins_24h": int(_num(row.get("failed_logins_24h", "0"))),
            "session_seconds": int(_num(row.get("session_seconds", "120"))),
        },
        "customer_profile": {"segment": "persona_natural", "risk_tier": "medio"},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xlsx", type=Path, help="Ruta a datos_prueba_centinela.xlsx")
    args = parser.parse_args()

    if not args.xlsx.exists():
        raise SystemExit(f"No existe el archivo: {args.xlsx}")

    out = get_settings().data_path / "synthetic"
    out.mkdir(parents=True, exist_ok=True)

    rows = read_sheet(args.xlsx, "transacciones")
    transactions = [
        {**to_transaction(r), "etiqueta": r.get("etiqueta", ""), "patron": r.get("patron") or None}
        for r in rows
        if r.get("transaction_id")
    ]
    path = out / "transactions_kit.json"
    path.write_text(json.dumps(transactions, ensure_ascii=False, indent=2), encoding="utf-8")
    fraud = sum(1 for t in transactions if t["etiqueta"] == "fraude")
    print(f"{len(transactions)} transacciones del kit → {path}")
    print(f"  fraude: {fraud} ({fraud / max(len(transactions), 1):.1%})")

    scenarios = read_sheet(args.xlsx, "escenarios_demo")
    payload = [
        {
            "escenario": r["escenario"],
            "veredicto_esperado": r["veredicto_esperado"],
            "explicacion": r.get("explicacion_para_la_clase", ""),
            "transaction": scenario_to_transaction(r, index + 1),
        }
        for index, r in enumerate(scenarios)
        if r.get("escenario")
    ]
    scenario_path = out / "demo_scenarios.json"
    scenario_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(payload)} escenarios de demo → {scenario_path}")


if __name__ == "__main__":
    main()
