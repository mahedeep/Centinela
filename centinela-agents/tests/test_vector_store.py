"""Vector store: coseno, kNN, filtrado por etiqueta y upsert."""

from __future__ import annotations

import pytest

from centinela.core.mock import deterministic_embedding
from centinela.core.vector_store import (
    SQLiteVectorStore,
    cosine_similarity,
    stable_id,
)

NS = "test_vectors"


@pytest.fixture()
def store(temp_data_dir) -> SQLiteVectorStore:
    return SQLiteVectorStore()


def test_cosine_of_identical_vectors_is_one():
    vector = [0.1, 0.2, 0.3]
    assert cosine_similarity(vector, vector) == pytest.approx(1.0)


def test_cosine_of_orthogonal_vectors_is_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_handles_degenerate_inputs():
    assert cosine_similarity([], [1.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert cosine_similarity([1.0, 2.0], [1.0]) == 0.0  # dimensiones distintas


def test_deterministic_embedding_is_reproducible():
    assert deterministic_embedding("hola mundo") == deterministic_embedding("hola mundo")
    assert deterministic_embedding("hola") != deterministic_embedding("mundo")


def test_deterministic_embedding_is_normalized():
    vector = deterministic_embedding("una transaccion cualquiera")
    norm = sum(v * v for v in vector) ** 0.5
    assert norm == pytest.approx(1.0, abs=1e-9)


def test_upsert_and_search_returns_nearest_first(store):
    for text, label in [
        ("beneficiario nuevo dispositivo nuevo vpn", "fraude"),
        ("beneficiario conocido dispositivo conocido sin vpn", "legitimo"),
    ]:
        store.upsert(NS, stable_id(text), text, deterministic_embedding(text), label=label)

    query = deterministic_embedding("beneficiario nuevo dispositivo nuevo vpn")
    neighbors = store.search(NS, query, k=2)
    assert len(neighbors) == 2
    assert neighbors[0].label == "fraude"
    assert neighbors[0].similarity > neighbors[1].similarity
    assert neighbors[0].similarity == pytest.approx(1.0, abs=1e-6)


def test_search_filters_by_label(store):
    for text, label in [("caso a", "fraude"), ("caso b", "legitimo")]:
        store.upsert(NS, stable_id(text), text, deterministic_embedding(text), label=label)
    only_fraud = store.search(NS, deterministic_embedding("caso a"), k=5, label="fraude")
    assert {n.label for n in only_fraud} == {"fraude"}


def test_search_on_empty_namespace_returns_nothing(store):
    assert store.search("namespace_vacio", deterministic_embedding("x"), k=5) == []


def test_upsert_replaces_instead_of_duplicating(store):
    item_id = stable_id("mismo caso")
    store.upsert(NS, item_id, "version 1", deterministic_embedding("v1"), label="fraude")
    before = store.count(NS)
    store.upsert(NS, item_id, "version 2", deterministic_embedding("v2"), label="legitimo")
    assert store.count(NS) == before
    found = store.search(NS, deterministic_embedding("v2"), k=1)
    assert found[0].label == "legitimo"


def test_search_ignores_vectors_of_other_dimension(store):
    # Namespace propio: NS_TRANSACTIONS lo comparten los tests de feedback.
    namespace = "test_dimensiones"
    store.upsert(namespace, "corto", "corto", [0.1, 0.2], label="fraude")
    store.upsert(
        namespace, "normal", "normal", deterministic_embedding("normal"), label="fraude"
    )
    neighbors = store.search(namespace, deterministic_embedding("normal"), k=5)
    assert [n.id for n in neighbors] == ["normal"]


def test_stable_id_is_deterministic():
    assert stable_id("a", "b") == stable_id("a", "b")
    assert stable_id("a", "b") != stable_id("b", "a")
