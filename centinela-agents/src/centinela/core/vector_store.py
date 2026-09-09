"""Vector store del MVP: embeddings como JSON en SQLite + coseno con NumPy.

`VectorStore` es la interfaz; `SQLiteVectorStore` la implementación actual.
Para migrar a pgvector/Supabase basta con otra implementación de la interfaz.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
from sqlalchemy import select

from centinela.core.db import VectorRow, get_session

# Espacios de nombres del store.
NS_TRANSACTIONS = "transactions"
NS_DOCUMENTS = "documents"
NS_TEMPLATES = "document_templates"


@dataclass(frozen=True)
class Neighbor:
    """Vecino recuperado, tal como se guarda en la traza y se muestra al analista."""

    id: str
    label: str
    similarity: float
    text: str
    meta: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "similarity": round(self.similarity, 4),
            "meta": self.meta,
        }


class VectorStore(ABC):
    @abstractmethod
    def upsert(
        self,
        namespace: str,
        item_id: str,
        text: str,
        embedding: Sequence[float],
        label: str = "",
        meta: dict[str, Any] | None = None,
    ) -> None: ...

    @abstractmethod
    def search(
        self, namespace: str, embedding: Sequence[float], k: int = 5, label: str | None = None
    ) -> list[Neighbor]: ...

    @abstractmethod
    def count(self, namespace: str, label: str | None = None) -> int: ...


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Coseno acotado a [-1, 1]; devuelve 0 si algún vector es nulo."""
    va, vb = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    if va.size == 0 or vb.size == 0 or va.size != vb.size:
        return 0.0
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0.0:
        return 0.0
    return float(np.clip(np.dot(va, vb) / denom, -1.0, 1.0))


class SQLiteVectorStore(VectorStore):
    """Búsqueda exacta por coseno. Suficiente hasta ~10⁴ vectores."""

    def upsert(
        self,
        namespace: str,
        item_id: str,
        text: str,
        embedding: Sequence[float],
        label: str = "",
        meta: dict[str, Any] | None = None,
    ) -> None:
        key = f"{namespace}:{item_id}"
        with get_session() as session:
            row = session.get(VectorRow, key)
            if row is None:
                row = VectorRow(id=key, namespace=namespace)
                session.add(row)
            row.label = label
            row.text = text
            row.embedding = [float(x) for x in embedding]
            row.meta = meta or {}
            session.commit()

    def search(
        self, namespace: str, embedding: Sequence[float], k: int = 5, label: str | None = None
    ) -> list[Neighbor]:
        with get_session() as session:
            stmt = select(VectorRow).where(VectorRow.namespace == namespace)
            if label is not None:
                stmt = stmt.where(VectorRow.label == label)
            rows = list(session.scalars(stmt))

        if not rows:
            return []

        query = np.asarray(embedding, dtype=np.float64)
        dim = query.size
        usable = [r for r in rows if r.embedding and len(r.embedding) == dim]
        if not usable:
            return []

        matrix = np.asarray([r.embedding for r in usable], dtype=np.float64)
        norms = np.linalg.norm(matrix, axis=1) * (np.linalg.norm(query) or 1.0)
        norms[norms == 0.0] = 1.0
        sims = np.clip(matrix @ query / norms, -1.0, 1.0)

        order = np.argsort(-sims)[: max(0, k)]
        return [
            Neighbor(
                id=usable[i].id.split(":", 1)[-1],
                label=usable[i].label,
                similarity=float(sims[i]),
                text=usable[i].text,
                meta=usable[i].meta or {},
            )
            for i in order
        ]

    def count(self, namespace: str, label: str | None = None) -> int:
        with get_session() as session:
            stmt = select(VectorRow).where(VectorRow.namespace == namespace)
            if label is not None:
                stmt = stmt.where(VectorRow.label == label)
            return len(list(session.scalars(stmt)))


def stable_id(*parts: str) -> str:
    """Identificador corto y reproducible para un item del store."""
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        _store = SQLiteVectorStore()
    return _store


def set_vector_store(store: VectorStore | None) -> None:
    """Punto de inyección para los tests."""
    global _store
    _store = store
