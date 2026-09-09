#!/usr/bin/env python3
"""Evalúa el agente de documentos sobre los 12 documentos sintéticos.

Reporta precisión, recall, los checks que fallan con más frecuencia, latencia y
costo por documento en `reports/documents_eval.md`.

Registra primero `firma_referencia.png` como referencia, porque el contrato con
la firma pegada solo puede evaluarse comparando contra ella.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import _bootstrap  # noqa: F401
from centinela.agents.documents.agent import DocumentAgent, DocumentInput
from centinela.agents.documents.preprocess import prepare
from centinela.config import get_settings
from centinela.core.db import get_engine
from centinela.core.llm import LLMClient
from centinela.core.vector_store import NS_TEMPLATES, get_vector_store

# Etiquetas y veredictos esperados, tomados de la hoja `documentos_prueba`.
CATALOG: list[dict[str, object]] = [
    {"archivo": "cedula_ok.png", "tipo": "cedula", "etiqueta": "autentico",
     "esperado": ["autentico"], "alteracion": "ninguna"},
    {"archivo": "comprobante_domicilio_ok.png", "tipo": "comprobante_domicilio",
     "etiqueta": "autentico", "esperado": ["autentico"], "alteracion": "ninguna"},
    {"archivo": "contrato_ok.png", "tipo": "contrato", "etiqueta": "autentico",
     "esperado": ["autentico"], "alteracion": "ninguna"},
    {"archivo": "liquidacion_ok.png", "tipo": "liquidacion", "etiqueta": "autentico",
     "esperado": ["autentico"], "alteracion": "ninguna"},
    {"archivo": "poder_ok.png", "tipo": "poder", "etiqueta": "autentico",
     "esperado": ["autentico"], "alteracion": "ninguna"},
    {"archivo": "firma_referencia.png", "tipo": "firma", "etiqueta": "autentico",
     "esperado": ["autentico"], "alteracion": "ninguna"},
    {"archivo": "cedula_alterada_fecha.png", "tipo": "cedula", "etiqueta": "falso",
     "esperado": ["falso"], "alteracion": "fecha de vencimiento retocada"},
    {"archivo": "cedula_rut_invalido.png", "tipo": "cedula", "etiqueta": "falso",
     "esperado": ["sospechoso", "falso"], "alteracion": "dígito verificador cambiado"},
    {"archivo": "contrato_firma_pegada.png", "tipo": "contrato", "etiqueta": "falso",
     "esperado": ["falso"], "alteracion": "firma copiada de otro documento",
     "usa_referencia": True},
    {"archivo": "liquidacion_montos_editados.png", "tipo": "liquidacion", "etiqueta": "falso",
     "esperado": ["falso"], "alteracion": "líquido a pagar aumentado"},
    {"archivo": "comprobante_metadatos_editor.png", "tipo": "comprobante_domicilio",
     "etiqueta": "falso", "esperado": ["sospechoso"], "alteracion": "metadatos de editor"},
    {"archivo": "poder_texto_tipografia.png", "tipo": "poder", "etiqueta": "falso",
     "esperado": ["falso"], "alteracion": "cláusula agregada con otra tipografía"},
]

REFERENCE_FILE = "firma_referencia.png"


def register_reference(samples: Path, settings) -> str | None:
    """Registra la firma de referencia igual que `POST /documents/references`."""
    path = samples / REFERENCE_FILE
    if not path.exists():
        return None
    prepared = prepare(path.read_bytes(), REFERENCE_FILE)
    reference_id = "REF-EVAL-FIRMA"
    directory = settings.data_path / "references"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{reference_id}.png").write_bytes(prepared.pages[0])
    try:
        canonical = "plantilla de referencia tipo firma; etiqueta evaluacion"
        vector = LLMClient().embed([canonical])[0]
        get_vector_store().upsert(
            NS_TEMPLATES, reference_id, canonical, vector, label="plantilla",
            meta={"document_type": "firma"},
        )
    except Exception:  # noqa: BLE001
        pass
    return reference_id


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("reports/documents_eval.md"))
    parser.add_argument(
        "--declare-type",
        action="store_true",
        help="Envía `document_type` declarado (por defecto el agente clasifica solo).",
    )
    args = parser.parse_args()

    get_engine()
    samples = settings.samples_path
    missing = [c["archivo"] for c in CATALOG if not (samples / str(c["archivo"])).exists()]
    if missing:
        raise SystemExit(
            "Faltan documentos de prueba: "
            + ", ".join(missing)
            + "\nCorre antes: python scripts/make_sample_documents.py"
        )

    reference_id = register_reference(samples, settings)
    mock = settings.mock_mode or not settings.has_openai
    agent = DocumentAgent()

    results: list[dict[str, object]] = []
    latencies: list[int] = []
    cost = 0.0
    tokens_in = tokens_out = 0
    check_failures: dict[str, int] = {}
    confusion = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}

    started = time.perf_counter()
    for case in CATALOG:
        path = samples / str(case["archivo"])
        payload = DocumentInput(
            content=path.read_bytes(),
            filename=path.name,
            document_type=str(case["tipo"]) if args.declare_type else None,
            reference_id=reference_id if case.get("usa_referencia") else None,
        )
        decision = agent.run(payload)

        latencies.append(decision.latency_ms)
        cost += decision.cost_usd
        tokens_in += decision.tokens_in
        tokens_out += decision.tokens_out
        for check in decision.checks:
            if check.status == "fail":
                check_failures[check.name] = check_failures.get(check.name, 0) + 1

        expected = list(case["esperado"])  # type: ignore[arg-type]
        correct = decision.verdict in expected
        is_fake = case["etiqueta"] == "falso"
        flagged = decision.verdict in ("sospechoso", "falso")
        if is_fake and flagged:
            confusion["tp"] += 1
        elif is_fake:
            confusion["fn"] += 1
        elif flagged:
            confusion["fp"] += 1
        else:
            confusion["tn"] += 1

        results.append(
            {
                "archivo": case["archivo"],
                "etiqueta": case["etiqueta"],
                "esperado": "/".join(expected),
                "verdicto": decision.verdict,
                "correcto": correct,
                "score": decision.score,
                "calidad": decision.image_quality,
                "tipo_detectado": decision.document_type_detected,
                "checks_fail": [c.name for c in decision.checks if c.status == "fail"],
                "checks_warn": [c.name for c in decision.checks if c.status == "warn"],
                "hallazgos": [f.name for f in decision.findings],
                "trace_id": decision.trace_id,
                "latency_ms": decision.latency_ms,
                "cost_usd": decision.cost_usd,
            }
        )

    elapsed = time.perf_counter() - started
    correct_count = sum(1 for r in results if r["correcto"])
    tp, fp, fn, tn = confusion["tp"], confusion["fp"], confusion["fn"], confusion["tn"]
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    p50 = statistics.median(latencies)
    p95 = sorted(latencies)[max(0, int(0.95 * (len(latencies) - 1)))]
    cost_per_doc = cost / len(results)

    lines = [
        "# Evaluación · agente de documentos",
        "",
        f"- Fecha: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- Documentos: {len(results)} (6 auténticos, 6 alterados) en `{samples}`",
        f"- Modo: {'MOCK (sin llamadas a OpenAI)' if mock else 'REAL contra OpenAI'}",
        f"- Modelo de visión: {settings.openai_vision_model} · "
        f"motor de extracción: {agent.ocr.name}",
        f"- Pesos: forense {settings.w_doc_vision} · checks {settings.w_doc_checks} "
        f"· modelo {settings.w_doc_model}",
        f"- Compuertas: calidad < {settings.min_image_quality} ⇒ sospechoso · "
        f"check crítico en fail ⇒ mínimo sospechoso · hallazgo forense ≥ 0,80 ⇒ falso",
        f"- Tiempo total: {elapsed:.1f} s",
        "",
        "## Resultado",
        "",
        f"**{correct_count}/{len(results)}** veredictos coinciden con lo esperado.",
        "",
        "| Métrica | Valor |",
        "|---|---|",
        f"| Precisión (detectar alterados) | {precision:.3f} |",
        f"| Recall (detectar alterados) | {recall:.3f} |",
        f"| Verdaderos positivos | {tp} |",
        f"| Falsos positivos | {fp} |",
        f"| Falsos negativos | {fn} |",
        f"| Verdaderos negativos | {tn} |",
        "",
        "## Detalle por documento",
        "",
        "| Documento | Etiqueta | Esperado | Veredicto | ✓ | Score | Calidad | Checks en falla | Hallazgos |",
        "|---|---|---|---|:-:|---:|---:|---|---|",
    ]
    for r in results:
        lines.append(
            f"| `{r['archivo']}` | {r['etiqueta']} | {r['esperado']} | **{r['verdicto']}** "
            f"| {'✓' if r['correcto'] else '✗'} | {float(r['score']):.3f} "
            f"| {float(r['calidad']):.2f} "
            f"| {', '.join(r['checks_fail']) or '—'} "  # type: ignore[arg-type]
            f"| {', '.join(r['hallazgos']) or '—'} |"  # type: ignore[arg-type]
        )

    lines += ["", "## Checks que fallan con más frecuencia", "",
              "| Check | Veces en falla |", "|---|---:|"]
    if check_failures:
        for name, count in sorted(check_failures.items(), key=lambda kv: -kv[1]):
            lines.append(f"| `{name}` | {count} |")
    else:
        lines.append("| — | 0 |")

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
        f"| **Costo por documento** | **USD {cost_per_doc:.8f}** |",
        "",
    ]
    if mock:
        lines += [
            "> En modo mock el costo es cero por construcción. Para comparar "
            "`gpt-5.6-luna` contra `gpt-5.6-terra` (o los modelos reales que tengas "
            "habilitados), corre con `MOCK_MODE=false` y luego repite cambiando "
            "`OPENAI_VISION_MODEL`; ambas corridas escriben este mismo reporte, así "
            "que renombra el primero antes de repetir.",
            "",
        ]
    lines += [
        "> Los precios usados provienen de `config.py`. Verificar contra la lista de "
        "precios vigente de OpenAI antes de reportar cifras.",
    ]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    json_path = args.out.with_suffix(".json")
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{correct_count}/{len(results)} veredictos correctos · "
          f"precisión {precision:.3f} · recall {recall:.3f}")
    print(f"Latencia p50/p95: {p50:.0f}/{p95:.0f} ms · costo por documento USD {cost_per_doc:.8f}")
    for r in results:
        if not r["correcto"]:
            print(f"  ✗ {r['archivo']}: {r['verdicto']} (esperado {r['esperado']})")
    print(f"Reporte → {args.out}")


if __name__ == "__main__":
    main()
