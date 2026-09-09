#!/usr/bin/env python3
"""Evalúa el agente de transacciones sobre un set etiquetado.

Reporta precisión, recall, tasa de falsos positivos, latencia p50/p95, costo
total y costo por evento, y escribe `reports/transactions_eval.md`.

Objetivo de referencia del MVP: recall ≥ 0,80 con falsos positivos ≤ 0,05.

Un caso se cuenta como **positivo del sistema** cuando el veredicto no es
`aprobar`: tanto `bloquear` como `validacion_adicional` implican fricción para
el cliente, y ese es el costo que el negocio quiere medir. El reporte también
desglosa qué pasa si solo se cuenta `bloquear`.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import _bootstrap  # noqa: F401
from centinela.agents.transactions.agent import TransactionAgent
from centinela.agents.transactions.schemas import TransactionInput
from centinela.config import get_settings
from centinela.core.db import get_engine

FRICTION_VERDICTS = {"bloquear", "validacion_adicional"}


def _metrics(tp: int, fp: int, fn: int, tn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "false_positive_rate": round(fpr, 4),
        "f1": round(f1, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=settings.data_path / "synthetic" / "transactions_kit.json",
        help="JSON generado por load_xlsx.py o seed_synthetic.py",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=0,
        help="Número de casos a evaluar. 0 = todos (recomendado solo en MOCK_MODE).",
    )
    parser.add_argument("--out", type=Path, default=Path("reports/transactions_eval.md"))
    args = parser.parse_args()

    if not args.dataset.exists():
        raise SystemExit(
            f"No existe {args.dataset}. Corre antes:\n"
            f"  python scripts/seed_synthetic.py\n"
            f"  python scripts/load_xlsx.py <ruta al xlsx>"
        )

    get_engine()
    rows = json.loads(args.dataset.read_text(encoding="utf-8"))
    if args.sample and args.sample < len(rows):
        rows = rows[: args.sample]

    mock = settings.mock_mode or not settings.has_openai
    if not mock and (args.sample == 0 or args.sample > 200):
        print("AVISO: sin MOCK_MODE esto consume tokens reales. Usa --sample 100.")

    agent = TransactionAgent()
    latencies: list[int] = []
    cost = 0.0
    tokens_in = tokens_out = 0
    by_verdict: dict[str, int] = {}
    by_pattern: dict[str, dict[str, int]] = {}
    confusion = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    confusion_block = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    errors: list[str] = []

    started = time.perf_counter()
    for index, row in enumerate(rows, start=1):
        label = row.get("etiqueta", "legitimo")
        pattern = row.get("patron") or "-"
        payload = {k: v for k, v in row.items() if k not in ("etiqueta", "patron")}
        try:
            decision = agent.run(TransactionInput.model_validate(payload))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{row.get('transaction_id', index)}: {exc}")
            continue

        latencies.append(decision.latency_ms)
        cost += decision.cost_usd
        tokens_in += decision.tokens_in
        tokens_out += decision.tokens_out
        by_verdict[decision.verdict] = by_verdict.get(decision.verdict, 0) + 1

        is_fraud = label == "fraude"
        flagged = decision.verdict in FRICTION_VERDICTS
        blocked = decision.verdict == "bloquear"
        for target, positive in ((confusion, flagged), (confusion_block, blocked)):
            if is_fraud and positive:
                target["tp"] += 1
            elif is_fraud:
                target["fn"] += 1
            elif positive:
                target["fp"] += 1
            else:
                target["tn"] += 1

        if is_fraud:
            bucket = by_pattern.setdefault(pattern, {"total": 0, "detectados": 0, "bloqueados": 0})
            bucket["total"] += 1
            bucket["detectados"] += int(flagged)
            bucket["bloqueados"] += int(blocked)

        if index % 100 == 0:
            print(f"  {index}/{len(rows)}…")

    elapsed = time.perf_counter() - started
    friction = _metrics(**confusion)
    block_only = _metrics(**confusion_block)
    evaluated = len(latencies)
    if not evaluated:
        raise SystemExit("No se pudo evaluar ninguna transacción.")

    p50 = statistics.median(latencies)
    p95 = sorted(latencies)[max(0, int(0.95 * (len(latencies) - 1)))]
    cost_per_event = cost / evaluated

    goal_ok = friction["recall"] >= 0.80 and friction["false_positive_rate"] <= 0.05

    lines = [
        "# Evaluación · agente de transacciones",
        "",
        f"- Fecha: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- Dataset: `{args.dataset}` · {evaluated} casos evaluados",
        f"- Modo: {'MOCK (sin llamadas a OpenAI)' if mock else 'REAL contra OpenAI'}",
        f"- Modelo: {settings.openai_chat_model} · embeddings {settings.openai_embedding_model}",
        f"- Umbrales: revisión {settings.threshold_review} · bloqueo {settings.threshold_block}",
        f"- Pesos: reglas {settings.w_tx_rules} · similitud {settings.w_tx_similarity} "
        f"· modelo {settings.w_tx_model}",
        f"- Tiempo total: {elapsed:.1f} s",
        "",
        "## Resultado frente al objetivo del MVP",
        "",
        f"**{'CUMPLE' if goal_ok else 'NO CUMPLE'}** el objetivo de referencia "
        f"(recall ≥ 0,80 y falsos positivos ≤ 0,05).",
        "",
        "## Métricas",
        "",
        "Positivo del sistema = el caso genera fricción (`bloquear` o `validacion_adicional`).",
        "",
        "| Métrica | Con fricción | Solo bloqueo |",
        "|---|---|---|",
        f"| Precisión | {friction['precision']:.3f} | {block_only['precision']:.3f} |",
        f"| Recall | {friction['recall']:.3f} | {block_only['recall']:.3f} |",
        f"| Tasa de falsos positivos | {friction['false_positive_rate']:.3f} "
        f"| {block_only['false_positive_rate']:.3f} |",
        f"| F1 | {friction['f1']:.3f} | {block_only['f1']:.3f} |",
        f"| Verdaderos positivos | {friction['tp']} | {block_only['tp']} |",
        f"| Falsos positivos | {friction['fp']} | {block_only['fp']} |",
        f"| Falsos negativos | {friction['fn']} | {block_only['fn']} |",
        f"| Verdaderos negativos | {friction['tn']} | {block_only['tn']} |",
        "",
        "## Distribución de veredictos",
        "",
        "| Veredicto | Casos | %|",
        "|---|---:|---:|",
    ]
    for verdict, count in sorted(by_verdict.items(), key=lambda kv: -kv[1]):
        lines.append(f"| `{verdict}` | {count} | {count / evaluated:.1%} |")

    if by_pattern:
        lines += [
            "",
            "## Detección por patrón de fraude",
            "",
            "| Patrón | Casos | Detectados | Bloqueados | Recall |",
            "|---|---:|---:|---:|---:|",
        ]
        for pattern, bucket in sorted(by_pattern.items()):
            recall = bucket["detectados"] / bucket["total"] if bucket["total"] else 0
            lines.append(
                f"| {pattern} | {bucket['total']} | {bucket['detectados']} "
                f"| {bucket['bloqueados']} | {recall:.2f} |"
            )

    lines += [
        "",
        "## Latencia y costo",
        "",
        "| Métrica | Valor |",
        "|---|---|",
        f"| Latencia p50 | {p50:.0f} ms |",
        f"| Latencia p95 | {p95:.0f} ms |",
        f"| Tokens de entrada | {tokens_in:,} |",
        f"| Tokens de salida | {tokens_out:,} |",
        f"| Costo total | USD {cost:.6f} |",
        f"| **Costo por evento** | **USD {cost_per_event:.8f}** |",
        "",
    ]
    if mock:
        lines.append(
            "> En modo mock el costo es cero por construcción y la latencia no incluye "
            "red. Para cifras de costo reales, corre con `MOCK_MODE=false` y "
            "`--sample 100`."
        )
    lines += [
        "",
        "> Los precios usados provienen de `config.py` "
        f"(entrada USD {settings.price_chat_input_per_1m}/1M, salida "
        f"USD {settings.price_chat_output_per_1m}/1M). Verificar contra la lista de "
        "precios vigente de OpenAI antes de reportar cifras.",
    ]
    if errors:
        lines += ["", "## Errores", ""] + [f"- {e}" for e in errors[:20]]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nRecall (fricción): {friction['recall']:.3f} · "
          f"FP: {friction['false_positive_rate']:.3f} · "
          f"Precisión: {friction['precision']:.3f}")
    print(f"Latencia p50/p95: {p50:.0f}/{p95:.0f} ms · costo por evento USD {cost_per_event:.8f}")
    print(f"Objetivo del MVP: {'CUMPLE' if goal_ok else 'NO CUMPLE'}")
    print(f"Reporte → {args.out}")


if __name__ == "__main__":
    main()
