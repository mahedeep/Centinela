"""Grafo ligero cuenta ↔ destino ↔ dispositivo.

No es un motor de grafos: es una tabla de aristas con dos consultas de ventana
móvil, suficientes para las dos señales de consistencia que pide el caso
(cuenta mula y dispositivo compartido). El grafo completo queda para la wave 2.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from centinela.core.db import GraphEdgeRow, get_session
from centinela.schemas import Evidence

WINDOW_HOURS = 24
MULE_DISTINCT_ORIGINS = 3
DEVICE_MAX_ACCOUNTS = 2


def record_edge(
    origin_account: str,
    destination_account: str,
    device_id: str,
    amount_clp: float,
    trace_id: str,
    occurred_at: datetime | None = None,
) -> None:
    moment = occurred_at or datetime.now(timezone.utc)
    with get_session() as session:
        session.add(
            GraphEdgeRow(
                origin_account=origin_account,
                destination_account=destination_account,
                device_id=device_id or "",
                amount_clp=amount_clp,
                occurred_at=moment.replace(tzinfo=None),
                trace_id=trace_id,
            )
        )
        session.commit()


def analyze(
    origin_account: str,
    destination_account: str,
    device_id: str,
    *,
    now: datetime | None = None,
) -> tuple[list[Evidence], list[str]]:
    """Devuelve evidencias de consistencia y notas legibles para el prompt."""
    moment = (now or datetime.now(timezone.utc)).replace(tzinfo=None)
    since = moment - timedelta(hours=WINDOW_HOURS)

    with get_session() as session:
        distinct_origins = int(
            session.scalar(
                select(func.count(func.distinct(GraphEdgeRow.origin_account))).where(
                    GraphEdgeRow.destination_account == destination_account,
                    GraphEdgeRow.origin_account != origin_account,
                    GraphEdgeRow.occurred_at >= since,
                )
            )
            or 0
        )
        device_accounts = 0
        if device_id:
            device_accounts = int(
                session.scalar(
                    select(func.count(func.distinct(GraphEdgeRow.origin_account))).where(
                        GraphEdgeRow.device_id == device_id,
                        GraphEdgeRow.origin_account != origin_account,
                        GraphEdgeRow.occurred_at >= since,
                    )
                )
                or 0
            )

    evidence: list[Evidence] = []
    notes: list[str] = []

    # +1 porque la cuenta de origen actual también cuenta como remitente.
    total_origins = distinct_origins + 1
    if total_origins >= MULE_DISTINCT_ORIGINS:
        detail = (
            f"La cuenta de destino recibió fondos de {total_origins} cuentas distintas "
            f"en las últimas {WINDOW_HOURS} horas (patrón de cuenta recolectora)"
        )
        evidence.append(
            Evidence(
                type="consistency",
                name="destination_multiple_origins_24h",
                value=total_origins,
                weight=0.28,
                detail=detail,
            )
        )
        notes.append(detail)

    total_device_accounts = device_accounts + 1
    if device_id and total_device_accounts > DEVICE_MAX_ACCOUNTS:
        detail = (
            f"El dispositivo está asociado a {total_device_accounts} cuentas distintas "
            f"en las últimas {WINDOW_HOURS} horas"
        )
        evidence.append(
            Evidence(
                type="consistency",
                name="device_shared_across_accounts",
                value=total_device_accounts,
                weight=0.24,
                detail=detail,
            )
        )
        notes.append(detail)

    return evidence, notes
