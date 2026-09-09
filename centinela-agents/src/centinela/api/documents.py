"""Endpoints del proceso B."""

from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from centinela.agents.documents.agent import DocumentAgent, DocumentInput
from centinela.agents.documents.preprocess import (
    DocumentTooLargeError,
    UnsupportedDocumentError,
    prepare,
)
from centinela.agents.documents.schemas import (
    DocumentDecision,
    EvidenceRegionsResponse,
    ReferenceResponse,
)
from centinela.config import get_settings
from centinela.core.llm import LLMClient
from centinela.core.tracing import get_trace_store
from centinela.core.vector_store import NS_TEMPLATES, get_vector_store
from centinela.schemas import Finding, Region, utcnow

router = APIRouter(prefix="/api/v1/documents", tags=["documentos"])


def _parse_expected(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="`expected_fields` debe ser un objeto JSON válido.",
        ) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="`expected_fields` debe ser un objeto JSON (campo → valor esperado).",
        )
    return {str(k): str(v) for k, v in parsed.items()}


@router.post(
    "/validate",
    response_model=DocumentDecision,
    summary="Valida un documento y determina si es auténtico, sospechoso o falso",
)
async def validate(
    file: Annotated[UploadFile, File(description="JPG, PNG o PDF de hasta 10 MB.")],
    document_type: Annotated[str | None, Form()] = None,
    reference_id: Annotated[str | None, Form()] = None,
    expected_fields: Annotated[str | None, Form(description="JSON campo → valor")] = None,
) -> DocumentDecision:
    content = await file.read()
    payload = DocumentInput(
        content=content,
        filename=file.filename or "documento",
        document_type=document_type or None,
        reference_id=reference_id or None,
        expected_fields=_parse_expected(expected_fields),
    )
    try:
        return DocumentAgent().run(payload)  # type: ignore[return-value]
    except DocumentTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        ) from exc
    except UnsupportedDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudo validar el documento: {exc}",
        ) from exc


@router.post(
    "/references",
    response_model=ReferenceResponse,
    summary="Registra una firma o plantilla de referencia",
)
async def register_reference(
    file: Annotated[UploadFile, File()],
    document_type: Annotated[str, Form()] = "firma",
    label: Annotated[str | None, Form(description="Etiqueta libre, sin datos personales")] = None,
) -> ReferenceResponse:
    settings = get_settings()
    content = await file.read()
    try:
        prepared = prepare(content, file.filename or "referencia")
    except DocumentTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        ) from exc
    except UnsupportedDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc

    reference_id = f"REF-{uuid.uuid4().hex[:12]}"
    directory = settings.data_path / "references"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{reference_id}.png"
    path.write_bytes(prepared.pages[0])

    # La plantilla se indexa para que la similitud pueda reconocerla luego.
    canonical = f"plantilla de referencia tipo {document_type}; etiqueta {label or 'sin etiqueta'}"
    try:
        vector = LLMClient().embed([canonical])[0]
        get_vector_store().upsert(
            NS_TEMPLATES,
            reference_id,
            canonical,
            vector,
            label="plantilla",
            meta={"document_type": document_type, "label": label or ""},
        )
    except Exception:  # noqa: BLE001 - la referencia sirve igual para comparar firmas
        pass

    return ReferenceResponse(
        reference_id=reference_id,
        document_type=document_type,  # type: ignore[arg-type]
        stored_at=utcnow().isoformat(),
        message="Referencia registrada. Úsala en `reference_id` al validar un documento.",
    )


@router.get(
    "/{trace_id}/evidence",
    response_model=EvidenceRegionsResponse,
    summary="Regiones de los hallazgos para dibujar sobre la imagen",
)
def evidence(trace_id: str) -> EvidenceRegionsResponse:
    store = get_trace_store()
    detail = store.get_case(trace_id)
    if detail is None or detail.decision.process != "document":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe un caso de documento con trace_id '{trace_id}'.",
        )
    raw = detail.extra.get("findings", [])
    findings = [
        Finding(
            name=f.get("name", "hallazgo"),
            detail=f.get("detail", ""),
            confidence=float(f.get("confidence", 0.0)),
            region=Region.model_validate(f["region"]) if f.get("region") else None,
        )
        for f in raw
    ]
    return EvidenceRegionsResponse(
        trace_id=trace_id,
        pages_analyzed=int((detail.extra.get("features") or {}).get("pages_analyzed", 1)),
        image_quality=float((detail.extra.get("features") or {}).get("image_quality", 1.0)),
        findings=findings,
        artifacts_available=store.get_artifacts_dir(trace_id) is not None,
    )


@router.get(
    "/{trace_id}/page/{page}",
    summary="Imagen procesada de una página (solo analista/supervisor)",
    response_class=FileResponse,
    responses={200: {"content": {"image/png": {}}, "description": "Página renderizada"}},
)
def page_image(trace_id: str, page: int) -> FileResponse:

    directory = get_trace_store().get_artifacts_dir(trace_id)
    if directory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Las imágenes de este caso ya no están disponibles (retención vencida).",
        )
    path = directory / f"page-{page}.png"
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Página inexistente.")
    return FileResponse(path, media_type="image/png")
