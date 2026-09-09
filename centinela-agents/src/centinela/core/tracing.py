"""Trazabilidad: `trace_id`, registro de decisiones, métricas y retención.

Cada decisión guarda entradas, prompts usados, modelo, tokens, costo, salida
estructurada y timestamp. Los prompts jamás salen hacia el cliente: viven en la
traza y solo los ven analista y supervisor.
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import func, select

from centinela.config import get_settings
from centinela.core.db import FeedbackRow, TraceRow, get_session
from centinela.schemas import (
    CaseDetail,
    DocumentDecision,
    CaseSummary,
    DailyPoint,
    Decision,
    Feedback,
    MetricsResponse,
    ProcessMetrics,
    VerdictCount,
)

BLOCKING_VERDICTS = {"bloquear", "falso"}
POSITIVE_LABELS = {"fraude_confirmado", "documento_falso"}
NEGATIVE_LABELS = {"legitimo", "documento_autentico"}


def new_trace_id(process: str) -> str:
    """`tx-<hex>` o `doc-<hex>`: legible en logs y único."""
    prefix = "tx" if process == "transaction" else "doc"
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


def _aware(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class TraceStore:
    """Escritura y lectura de trazas. Toda consulta del front pasa por aquí."""

    def save(
        self,
        decision: Decision,
        *,
        inputs: dict[str, Any] | None = None,
        prompts: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
        prompt_version: str = "",
        artifacts_dir: str = "",
    ) -> None:
        with get_session() as session:
            row = session.get(TraceRow, decision.trace_id)
            if row is None:
                row = TraceRow(trace_id=decision.trace_id)
                session.add(row)
            row.process = decision.process
            row.verdict = decision.verdict
            row.score = decision.score
            row.confidence = decision.confidence
            row.requires_human_review = decision.requires_human_review
            row.shadow = decision.shadow
            row.model = decision.model
            row.tokens_in = decision.tokens_in
            row.tokens_out = decision.tokens_out
            row.cost_usd = decision.cost_usd
            row.latency_ms = decision.latency_ms
            row.created_at = _aware(decision.created_at).replace(tzinfo=None)
            row.decision_json = json.loads(decision.model_dump_json())
            row.inputs_json = inputs or {}
            row.prompts_json = prompts or {}
            row.extra_json = extra or {}
            row.prompt_version = prompt_version
            row.artifacts_dir = artifacts_dir
            session.commit()

    # -- lectura ------------------------------------------------------------
    def list_cases(
        self,
        *,
        process: str | None = None,
        verdict: str | None = None,
        requires_human_review: bool | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "score",
    ) -> list[CaseSummary]:
        with get_session() as session:
            stmt = select(TraceRow)
            if process:
                stmt = stmt.where(TraceRow.process == process)
            if verdict:
                stmt = stmt.where(TraceRow.verdict == verdict)
            if requires_human_review is not None:
                stmt = stmt.where(TraceRow.requires_human_review == requires_human_review)
            if date_from:
                stmt = stmt.where(TraceRow.created_at >= _aware(date_from).replace(tzinfo=None))
            if date_to:
                stmt = stmt.where(TraceRow.created_at <= _aware(date_to).replace(tzinfo=None))

            column = TraceRow.created_at if order_by == "created_at" else TraceRow.score
            stmt = stmt.order_by(column.desc()).limit(limit).offset(offset)
            rows = list(session.scalars(stmt))

            labels = self._feedback_labels(session, [r.trace_id for r in rows])

        now = datetime.now(timezone.utc)
        return [
            CaseSummary(
                trace_id=r.trace_id,
                process=r.process,  # type: ignore[arg-type]
                verdict=r.verdict,  # type: ignore[arg-type]
                score=r.score,
                confidence=r.confidence,
                requires_human_review=r.requires_human_review,
                shadow=r.shadow,
                created_at=_aware(r.created_at),
                cost_usd=r.cost_usd,
                latency_ms=r.latency_ms,
                feedback_label=labels.get(r.trace_id),  # type: ignore[arg-type]
                age_seconds=(now - _aware(r.created_at)).total_seconds(),
            )
            for r in rows
        ]

    @staticmethod
    def _feedback_labels(session: Any, trace_ids: Iterable[str]) -> dict[str, str]:
        ids = list(trace_ids)
        if not ids:
            return {}
        stmt = select(FeedbackRow).where(FeedbackRow.trace_id.in_(ids)).order_by(FeedbackRow.id)
        return {fb.trace_id: fb.label for fb in session.scalars(stmt)}

    def get_case(self, trace_id: str) -> CaseDetail | None:
        with get_session() as session:
            row = session.get(TraceRow, trace_id)
            if row is None:
                return None
            fb_rows = list(
                session.scalars(
                    select(FeedbackRow)
                    .where(FeedbackRow.trace_id == trace_id)
                    .order_by(FeedbackRow.id)
                )
            )
            extra = row.extra_json or {}
            # Un caso de documento se valida como `DocumentDecision`: validarlo
            # como `Decision` descartaría checks, fields y findings, que es
            # justamente lo que la pantalla del analista necesita.
            model = DocumentDecision if row.process == "document" else Decision
            return CaseDetail(
                decision=model.model_validate(row.decision_json),
                inputs=row.inputs_json or {},
                prompts=row.prompts_json or {},
                prompt_version=row.prompt_version,
                weights=extra.get("weights", {}),
                neighbors=extra.get("neighbors", []),
                extra=extra,
                feedback=[
                    Feedback(
                        trace_id=fb.trace_id,
                        label=fb.label,  # type: ignore[arg-type]
                        analyst=fb.analyst,
                        comment=fb.comment,
                    )
                    for fb in fb_rows
                ],
            )

    def get_artifacts_dir(self, trace_id: str) -> Path | None:
        with get_session() as session:
            row = session.get(TraceRow, trace_id)
            if row is None or not row.artifacts_dir or row.purged_at is not None:
                return None
            path = Path(row.artifacts_dir)
            return path if path.exists() else None

    # -- feedback -----------------------------------------------------------
    def save_feedback(self, feedback: Feedback) -> None:
        with get_session() as session:
            session.add(
                FeedbackRow(
                    trace_id=feedback.trace_id,
                    label=feedback.label,
                    analyst=feedback.analyst,
                    comment=feedback.comment,
                )
            )
            session.commit()

    # -- retención ----------------------------------------------------------
    def purge_expired_artifacts(self, *, now: datetime | None = None) -> list[str]:
        """Borra las imágenes procesadas cuyo plazo de retención venció.

        `now` es inyectable para poder probarlo con reloj simulado.
        """
        settings = get_settings()
        moment = _aware(now)
        cutoff = (moment - timedelta(days=settings.trace_retention_days)).replace(tzinfo=None)

        purged: list[str] = []
        with get_session() as session:
            stmt = select(TraceRow).where(
                TraceRow.artifacts_dir != "",
                TraceRow.purged_at.is_(None),
                TraceRow.created_at <= cutoff,
            )
            for row in session.scalars(stmt):
                directory = Path(row.artifacts_dir)
                if directory.exists():
                    shutil.rmtree(directory, ignore_errors=True)
                row.purged_at = moment.replace(tzinfo=None)
                purged.append(row.trace_id)
            session.commit()
        return purged

    # -- métricas -----------------------------------------------------------
    def metrics(
        self, *, date_from: datetime | None = None, date_to: datetime | None = None
    ) -> MetricsResponse:
        with get_session() as session:
            stmt = select(TraceRow)
            if date_from:
                stmt = stmt.where(TraceRow.created_at >= _aware(date_from).replace(tzinfo=None))
            if date_to:
                stmt = stmt.where(TraceRow.created_at <= _aware(date_to).replace(tzinfo=None))
            rows = list(session.scalars(stmt))
            feedback_rows = list(session.scalars(select(FeedbackRow)))
            feedback_count = int(session.scalar(select(func.count(FeedbackRow.id))) or 0)

        response = MetricsResponse(
            total_volume=len(rows),
            total_cost_usd=round(sum(r.cost_usd for r in rows), 6),
            feedback_count=feedback_count,
        )
        response.cost_per_event_usd = (
            round(response.total_cost_usd / len(rows), 8) if rows else 0.0
        )

        for process in ("transaction", "document"):
            subset = [r for r in rows if r.process == process]
            if not subset:
                continue
            latencies = sorted(r.latency_ms for r in subset)
            verdicts: dict[str, int] = {}
            for r in subset:
                verdicts[r.verdict] = verdicts.get(r.verdict, 0) + 1
            cost = round(sum(r.cost_usd for r in subset), 6)
            response.by_process.append(
                ProcessMetrics(
                    process=process,  # type: ignore[arg-type]
                    volume=len(subset),
                    block_rate=round(
                        sum(1 for r in subset if r.verdict in BLOCKING_VERDICTS) / len(subset), 4
                    ),
                    human_review_rate=round(
                        sum(1 for r in subset if r.requires_human_review) / len(subset), 4
                    ),
                    latency_p50_ms=_percentile(latencies, 0.50),
                    latency_p95_ms=_percentile(latencies, 0.95),
                    cost_usd=cost,
                    cost_per_event_usd=round(cost / len(subset), 8),
                    verdicts=[VerdictCount(verdict=k, count=v) for k, v in sorted(verdicts.items())],
                )
            )

        # Modo sombra: cuántos se habrían bloqueado.
        shadow_rows = [r for r in rows if r.shadow]
        thresholds = get_settings()
        response.shadow_approved = len(shadow_rows)
        response.shadow_would_block = sum(
            1 for r in shadow_rows if r.score >= thresholds.threshold_block
        )

        # Costo por modelo.
        by_model: dict[str, dict[str, Any]] = {}
        for r in rows:
            entry = by_model.setdefault(
                r.model or "desconocido",
                {"model": r.model or "desconocido", "events": 0, "tokens_in": 0,
                 "tokens_out": 0, "cost_usd": 0.0},
            )
            entry["events"] += 1
            entry["tokens_in"] += r.tokens_in
            entry["tokens_out"] += r.tokens_out
            entry["cost_usd"] = round(entry["cost_usd"] + r.cost_usd, 6)
        response.by_model = sorted(by_model.values(), key=lambda e: -e["cost_usd"])

        # Evidencias más frecuentes (solo las que se activaron).
        counter: dict[str, int] = {}
        for r in rows:
            for ev in (r.decision_json or {}).get("evidence", []):
                if ev.get("type") == "rule" and not ev.get("value"):
                    continue
                counter[ev.get("name", "?")] = counter.get(ev.get("name", "?"), 0) + 1
        response.top_evidence = [
            {"name": k, "count": v}
            for k, v in sorted(counter.items(), key=lambda kv: -kv[1])[:10]
        ]

        # Serie temporal por día y veredicto.
        series: dict[tuple[str, str], int] = {}
        for r in rows:
            day = _aware(r.created_at).date().isoformat()
            series[(day, r.verdict)] = series.get((day, r.verdict), 0) + 1
        response.timeseries = [
            DailyPoint(date=d, verdict=v, count=c) for (d, v), c in sorted(series.items())
        ]

        # Precisión estimada sobre los casos etiquetados por el analista.
        verdict_by_trace = {r.trace_id: r.verdict for r in rows}
        matched = 0
        total = 0
        for fb in feedback_rows:
            verdict = verdict_by_trace.get(fb.trace_id)
            if verdict is None:
                continue
            total += 1
            flagged = verdict in BLOCKING_VERDICTS or verdict in {"validacion_adicional", "sospechoso"}
            if (fb.label in POSITIVE_LABELS and flagged) or (
                fb.label in NEGATIVE_LABELS and not flagged
            ):
                matched += 1
        response.estimated_accuracy = round(matched / total, 4) if total else None
        return response


def _percentile(sorted_values: list[int], q: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    position = q * (len(sorted_values) - 1)
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    fraction = position - low
    return round(sorted_values[low] * (1 - fraction) + sorted_values[high] * fraction, 2)


_trace_store: TraceStore | None = None


def get_trace_store() -> TraceStore:
    global _trace_store
    if _trace_store is None:
        _trace_store = TraceStore()
    return _trace_store
