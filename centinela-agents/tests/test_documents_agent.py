"""Agente de documentos: preproceso, compuertas, endpoints y retención."""

from __future__ import annotations

import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PIL import Image

from centinela.agents.documents.agent import DocumentAgent, DocumentInput
from centinela.agents.documents.ocr import MockOcrEngine, OcrResult, build_ocr_engine
from centinela.agents.documents.preprocess import (
    DocumentTooLargeError,
    UnsupportedDocumentError,
    compute_quality,
    prepare,
)
from centinela.config import get_settings
from centinela.core.llm import LLMClient
from centinela.core.tracing import get_trace_store


# --- utilidades ---------------------------------------------------------------


def _png(width: int = 900, height: int = 600, noisy: bool = True) -> bytes:
    """Imagen sintética con textura, para que la calidad no salga degenerada."""
    image = Image.new("RGB", (width, height), (250, 249, 245))
    if noisy:
        pixels = image.load()
        for y in range(0, height, 3):
            for x in range(0, width, 3):
                pixels[x, y] = (20, 24, 32)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _blurry_png() -> bytes:
    """Imagen plana: sin nitidez ni contraste, cae bajo la compuerta de calidad."""
    image = Image.new("RGB", (300, 200), (200, 200, 200))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture()
def samples(temp_data_dir: Path) -> Path:
    """Genera un documento sintético mínimo con su ficha de campos."""
    directory = temp_data_dir / "samples"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "cedula_ok.png").write_bytes(_png())
    (directory / "cedula_ok.fields.json").write_text(
        json.dumps(
            {
                "document_type": "cedula",
                "fields": {
                    "rut": {"value": "12.345.678-5", "confidence": 0.94},
                    "fecha_emision": {"value": "05/01/2022", "confidence": 0.92},
                    "fecha_vencimiento": {"value": "05/01/2032", "confidence": 0.9},
                },
                "layout": "Encabezado arriba, datos al centro, firma abajo.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (directory / "cedula_alterada_fecha.png").write_bytes(_png())
    (directory / "cedula_alterada_fecha.fields.json").write_text(
        json.dumps(
            {
                "document_type": "cedula",
                "fields": {
                    "rut": {"value": "12.345.678-5", "confidence": 0.94},
                    "fecha_emision": {"value": "05/01/2022", "confidence": 0.92},
                    "fecha_vencimiento": {"value": "05/01/2021", "confidence": 0.8},
                },
                "layout": "Encabezado arriba, datos al centro, firma abajo.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return directory


# --- preproceso ---------------------------------------------------------------


def test_prepare_reads_a_png():
    prepared = prepare(_png(), "documento.png")
    assert prepared.pages_analyzed == 1
    assert 0.0 <= prepared.image_quality <= 1.0
    assert "image" in prepared.metadata


def test_prepare_rejects_oversized_files():
    settings = get_settings()
    oversized = b"x" * (settings.max_upload_mb * 1024 * 1024 + 1)
    with pytest.raises(DocumentTooLargeError):
        prepare(oversized, "grande.png")


def test_prepare_rejects_unsupported_formats():
    with pytest.raises(UnsupportedDocumentError):
        prepare(b"esto no es una imagen", "archivo.txt")
    with pytest.raises(UnsupportedDocumentError):
        prepare(b"", "vacio.png")


def test_prepare_downscales_large_images():
    prepared = prepare(_png(3000, 2000), "grande.png")
    assert max(prepared.page_sizes[0]) <= 1600


def test_pdf_is_rendered_to_images():
    """Conversión PDF → imagen, respetando el máximo de páginas."""
    pdfium = pytest.importorskip("pypdfium2")
    document = pdfium.PdfDocument.new()
    for _ in range(3):
        document.new_page(400, 600)
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()

    prepared = prepare(buffer.getvalue(), "documento.pdf")
    assert prepared.pages_analyzed == 3
    assert "pdf" in prepared.metadata
    assert all(page[:8].startswith(b"\x89PNG") for page in prepared.pages)


def test_pdf_page_limit_is_enforced():
    pdfium = pytest.importorskip("pypdfium2")
    settings = get_settings()
    document = pdfium.PdfDocument.new()
    for _ in range(settings.max_pdf_pages + 3):
        document.new_page(300, 400)
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()

    prepared = prepare(buffer.getvalue(), "largo.pdf")
    assert prepared.pages_analyzed == settings.max_pdf_pages


def test_quality_ranks_sharp_above_flat():
    with Image.open(io.BytesIO(_png())) as sharp, Image.open(io.BytesIO(_blurry_png())) as flat:
        sharp_quality, _ = compute_quality(sharp)
        flat_quality, _ = compute_quality(flat)
    assert sharp_quality > flat_quality
    assert flat_quality < get_settings().min_image_quality


# --- capa de OCR --------------------------------------------------------------


def test_mock_engine_is_used_in_mock_mode():
    engine = build_ocr_engine(LLMClient())
    assert isinstance(engine, MockOcrEngine)
    assert engine.name == "mock"


def test_mock_engine_reads_the_sidecar_fields(samples: Path):
    result = MockOcrEngine(samples).extract([_png()], {"source_name": "cedula_ok.png"})
    assert isinstance(result, OcrResult)
    assert result.document_type == "cedula"
    assert result.field_value("rut") == "12.345.678-5"


def test_mock_engine_without_sidecar_returns_empty_fields(samples: Path):
    result = MockOcrEngine(samples).extract([_png()], {"source_name": "desconocido.png"})
    assert result.fields == {}


# --- decisiones y compuertas ---------------------------------------------------


def test_clean_document_is_authentic(samples: Path):
    path = samples / "cedula_ok.png"
    decision = DocumentAgent().run(
        DocumentInput(content=path.read_bytes(), filename=path.name)
    )
    assert decision.verdict == "autentico"
    assert decision.requires_human_review is False
    assert decision.document_type_detected == "cedula"
    assert decision.fields["rut"].value == "12.345.678-5"


def test_critical_check_failure_forces_at_least_suspicious(samples: Path):
    path = samples / "cedula_alterada_fecha.png"
    decision = DocumentAgent().run(
        DocumentInput(content=path.read_bytes(), filename=path.name)
    )
    assert decision.verdict in ("sospechoso", "falso")
    assert decision.requires_human_review is True
    assert any(c.name == "date_consistency" and c.status == "fail" for c in decision.checks)


def test_low_quality_forces_suspicious_and_asks_for_a_new_capture():
    decision = DocumentAgent().run(
        DocumentInput(content=_blurry_png(), filename="borrosa.png")
    )
    assert decision.image_quality < get_settings().min_image_quality
    assert decision.verdict in ("sospechoso", "falso")
    assert decision.requires_human_review is True
    assert "nítida" in decision.explanation_customer


def test_expected_fields_mismatch_is_detected(samples: Path):
    path = samples / "cedula_ok.png"
    decision = DocumentAgent().run(
        DocumentInput(
            content=path.read_bytes(),
            filename=path.name,
            expected_fields={"rut": "9.876.543-3"},
        )
    )
    assert decision.verdict in ("sospechoso", "falso")
    assert any(
        c.name == "expected_fields_match" and c.status == "fail" for c in decision.checks
    )


def test_every_check_is_reported_even_when_not_applicable(samples: Path):
    path = samples / "cedula_ok.png"
    decision = DocumentAgent().run(
        DocumentInput(content=path.read_bytes(), filename=path.name)
    )
    assert len(decision.checks) == 7
    assert any(c.status == "pending" for c in decision.checks)


# --- explicabilidad -----------------------------------------------------------


def test_customer_text_never_names_a_failed_check(samples: Path):
    path = samples / "cedula_alterada_fecha.png"
    decision = DocumentAgent().run(
        DocumentInput(content=path.read_bytes(), filename=path.name)
    )
    text = decision.explanation_customer.lower()
    for forbidden in ("check", "rut", "módulo", "score", "forense", "tipografía", "metadatos"):
        assert forbidden not in text
    assert "date_consistency" in decision.explanation_analyst


def test_analyst_text_lists_every_check(samples: Path):
    path = samples / "cedula_ok.png"
    decision = DocumentAgent().run(
        DocumentInput(content=path.read_bytes(), filename=path.name)
    )
    for check in decision.checks:
        assert check.name in decision.explanation_analyst


# --- endpoints ----------------------------------------------------------------


def test_validate_endpoint_accepts_multipart(client, samples: Path):
    path = samples / "cedula_ok.png"
    response = client.post(
        "/api/v1/documents/validate",
        files={"file": (path.name, path.read_bytes(), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["process"] == "document"
    assert body["trace_id"].startswith("doc-")
    assert len(body["checks"]) == 7


def test_validate_endpoint_rejects_a_text_file(client):
    response = client.post(
        "/api/v1/documents/validate",
        files={"file": ("nota.txt", b"no soy una imagen", "text/plain")},
    )
    assert response.status_code == 415


def test_validate_endpoint_rejects_malformed_expected_fields(client, samples: Path):
    path = samples / "cedula_ok.png"
    response = client.post(
        "/api/v1/documents/validate",
        files={"file": (path.name, path.read_bytes(), "image/png")},
        data={"expected_fields": "no es json"},
    )
    assert response.status_code == 422


def test_references_endpoint_returns_an_id(client):
    response = client.post(
        "/api/v1/documents/references",
        files={"file": ("firma.png", _png(400, 200), "image/png")},
        data={"document_type": "firma"},
    )
    assert response.status_code == 200
    assert response.json()["reference_id"].startswith("REF-")


def test_evidence_endpoint_returns_regions(client, samples: Path):
    path = samples / "cedula_alterada_fecha.png"
    trace_id = client.post(
        "/api/v1/documents/validate",
        files={"file": (path.name, path.read_bytes(), "image/png")},
    ).json()["trace_id"]

    response = client.get(f"/api/v1/documents/{trace_id}/evidence")
    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"] == trace_id
    assert body["artifacts_available"] is True
    for finding in body["findings"]:
        if finding["region"]:
            assert 0.0 <= finding["region"]["x"] <= 1.0
            assert 0.0 <= finding["region"]["width"] <= 1.0


def test_evidence_endpoint_404s_for_a_transaction(client, fraud_transaction):
    trace_id = client.post(
        "/api/v1/transactions/evaluate", json=fraud_transaction
    ).json()["trace_id"]
    assert client.get(f"/api/v1/documents/{trace_id}/evidence").status_code == 404


def test_page_image_endpoint_serves_the_processed_page(client, samples: Path):
    path = samples / "cedula_ok.png"
    trace_id = client.post(
        "/api/v1/documents/validate",
        files={"file": (path.name, path.read_bytes(), "image/png")},
    ).json()["trace_id"]

    response = client.get(f"/api/v1/documents/{trace_id}/page/1")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert client.get(f"/api/v1/documents/{trace_id}/page/99").status_code == 404


# --- retención ----------------------------------------------------------------


def test_artifacts_are_stored_inside_data_traces(samples: Path):
    path = samples / "cedula_ok.png"
    decision = DocumentAgent().run(
        DocumentInput(content=path.read_bytes(), filename=path.name)
    )
    directory = get_trace_store().get_artifacts_dir(decision.trace_id)
    assert directory is not None
    assert directory.parent == get_settings().traces_path
    assert (directory / "page-1.png").exists()


def test_retention_deletes_images_after_the_configured_days(samples: Path):
    """Reloj simulado: el borrado no espera siete días reales."""
    path = samples / "cedula_ok.png"
    decision = DocumentAgent().run(
        DocumentInput(content=path.read_bytes(), filename=path.name)
    )
    store = get_trace_store()
    directory = store.get_artifacts_dir(decision.trace_id)
    assert directory is not None and directory.exists()

    settings = get_settings()
    before_expiry = datetime.now(timezone.utc) + timedelta(
        days=settings.trace_retention_days - 1
    )
    assert store.purge_expired_artifacts(now=before_expiry) == []
    assert directory.exists(), "No debe borrar antes de que venza la retención"

    after_expiry = datetime.now(timezone.utc) + timedelta(
        days=settings.trace_retention_days + 1
    )
    purged = store.purge_expired_artifacts(now=after_expiry)
    assert decision.trace_id in purged
    assert not directory.exists()
    assert store.get_artifacts_dir(decision.trace_id) is None


def test_evidence_endpoint_reports_when_artifacts_expired(client, samples: Path):
    path = samples / "cedula_ok.png"
    trace_id = client.post(
        "/api/v1/documents/validate",
        files={"file": (path.name, path.read_bytes(), "image/png")},
    ).json()["trace_id"]

    store = get_trace_store()
    store.purge_expired_artifacts(
        now=datetime.now(timezone.utc)
        + timedelta(days=get_settings().trace_retention_days + 1)
    )
    body = client.get(f"/api/v1/documents/{trace_id}/evidence").json()
    assert body["artifacts_available"] is False
