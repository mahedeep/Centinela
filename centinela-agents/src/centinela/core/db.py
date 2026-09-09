"""Persistencia MVP: SQLite vía SQLAlchemy 2.0.

Tres tablas: `traces` (una fila por decisión), `feedback` (etiquetas del
analista) y `vectors` (vector store simple: embedding como JSON).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from centinela.config import get_settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TraceRow(Base):
    __tablename__ = "traces"

    trace_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    process: Mapped[str] = mapped_column(String(32), index=True)
    verdict: Mapped[str] = mapped_column(String(32), index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    shadow: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    model: Mapped[str] = mapped_column(String(64), default="")
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)

    decision_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    inputs_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    prompts_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    extra_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    prompt_version: Mapped[str] = mapped_column(String(32), default="")
    artifacts_dir: Mapped[str] = mapped_column(Text, default="")
    purged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class FeedbackRow(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(32), index=True)
    analyst: Mapped[str] = mapped_column(String(64), default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class VectorRow(Base):
    __tablename__ = "vectors"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(48), index=True)
    label: Mapped[str] = mapped_column(String(48), index=True, default="")
    text: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[list[float]] = mapped_column(JSON, default=list)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class GraphEdgeRow(Base):
    """Grafo ligero cuenta → destino → dispositivo, para señales de consistencia."""

    __tablename__ = "graph_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    origin_account: Mapped[str] = mapped_column(String(64), index=True)
    destination_account: Mapped[str] = mapped_column(String(64), index=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    amount_clp: Mapped[float] = mapped_column(Float, default=0.0)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    trace_id: Mapped[str] = mapped_column(String(64), default="", index=True)


_engine = None
_SessionFactory: sessionmaker[Session] | None = None


def get_engine():
    global _engine, _SessionFactory
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.sqlalchemy_url,
            future=True,
            connect_args={"check_same_thread": False}
            if settings.sqlalchemy_url.startswith("sqlite")
            else {},
        )
        Base.metadata.create_all(_engine)
        _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def get_session() -> Session:
    get_engine()
    assert _SessionFactory is not None
    return _SessionFactory()


def reset_engine() -> None:
    """Los tests usan una base temporal por sesión."""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None
