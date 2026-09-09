"""Capa de OCR / extracción de documentos, enchufable.

El caso exige que la extracción principal sea el **modelo multimodal de visión**
(`OCR_ENGINE=vision`), pero deja la puerta abierta a otros motores. Esta capa
define un único contrato —`OcrEngine`— y tres implementaciones:

- `VisionOcrEngine`  : OpenAI multimodal. Es el motor por defecto y el único que
                       clasifica el documento, extrae campos con confianza y
                       describe el layout en una sola llamada.
- `TesseractOcrEngine`: OCR local, **desactivado por defecto**. Solo texto plano;
                       útil como contingencia sin red o para comparar costo.
                       Requiere `pip install -e ".[ocr-local]"` y el binario
                       `tesseract` instalado en el sistema.
- `MockOcrEngine`     : determinista, sin red. Lee la ficha de campos sintéticos
                       que acompaña a cada documento de `data/samples/`.

Para agregar un motor nuevo (Document AI, Textract, Azure DI) basta con
implementar `OcrEngine.extract` y registrarlo en `build_ocr_engine`.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from centinela.config import Settings, get_settings
from centinela.core.llm import LLMClient
from centinela.core.mock import mock_vision_extraction

logger = logging.getLogger(__name__)


@dataclass
class OcrResult:
    """Salida normalizada de cualquier motor de extracción."""

    document_type: str = "otro"
    fields: dict[str, dict[str, Any]] = field(default_factory=dict)
    layout: str = ""
    raw_text: str = ""
    engine: str = "vision"
    notes: list[str] = field(default_factory=list)

    def field_value(self, name: str) -> str:
        entry = self.fields.get(name)
        return str(entry.get("value", "")) if isinstance(entry, dict) else ""


# JSON Schema de la llamada de extracción. `strict: true` obliga al modelo a
# devolver exactamente esta forma.
EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["document_type", "fields", "layout", "image_quality_comment"],
    "properties": {
        "document_type": {
            "type": "string",
            "enum": [
                "cedula",
                "comprobante_domicilio",
                "contrato",
                "poder",
                "liquidacion",
                "firma",
                "otro",
            ],
        },
        "fields": {
            "type": "array",
            "description": "Campos legibles en el documento. Lista vacía si no hay ninguno.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "value", "confidence"],
                "properties": {
                    "name": {
                        "type": "string",
                        "description": (
                            "nombre | rut | fecha_emision | fecha_vencimiento | "
                            "fecha_nacimiento | direccion | emisor | numero_serie | "
                            "firmante | monto_bruto | monto_descuentos | monto_liquido | "
                            "monto | periodo"
                        ),
                    },
                    "value": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "layout": {
            "type": "string",
            "description": "Posición relativa de logos, sellos, firmas y tablas.",
        },
        "image_quality_comment": {"type": "string"},
    },
}

EXTRACTION_SYSTEM = """\
Eres un perito en lectura de documentos. Transcribes exactamente lo que ves, sin \
completar ni corregir. Si un campo está ilegible, no lo inventes: omítelo o \
declara una confianza baja. Nunca deduzcas un valor a partir del contexto."""

EXTRACTION_PROMPT = """\
Analiza la imagen del documento y devuelve el JSON pedido.

1. Clasifica el tipo de documento.
2. Extrae los campos que sean legibles, con su confianza entre 0 y 1. Transcribe \
los valores tal como aparecen, respetando puntos, guiones y formato de fecha.
3. Describe el layout: posición relativa de logos, sellos, firmas, tablas y \
bloques de texto.

No emitas juicio sobre autenticidad en esta llamada: eso se evalúa aparte."""


class OcrEngine(ABC):
    """Contrato único de la capa de extracción."""

    name: str = "base"

    @abstractmethod
    def extract(
        self, pages: Sequence[bytes], hint: dict[str, Any] | None = None
    ) -> OcrResult: ...


def _normalize_fields(items: Any) -> dict[str, dict[str, Any]]:
    """Lista `[{name, value, confidence}]` → diccionario indexado por nombre."""
    fields: dict[str, dict[str, Any]] = {}
    if isinstance(items, dict):  # tolerancia al formato del mock
        for key, value in items.items():
            if isinstance(value, dict):
                fields[str(key)] = {
                    "value": str(value.get("value", "")),
                    "confidence": float(value.get("confidence", 0.8)),
                    "source": value.get("source", "vision"),
                }
            else:
                fields[str(key)] = {"value": str(value), "confidence": 0.8, "source": "vision"}
        return fields
    for item in items or []:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        fields[str(item["name"]).strip().lower()] = {
            "value": str(item.get("value", "")).strip(),
            "confidence": float(item.get("confidence", 0.0)),
            "source": "vision",
        }
    return fields


class VisionOcrEngine(OcrEngine):
    """Extracción con el modelo multimodal (motor por defecto).

    Una sola llamada por documento: clasifica, extrae campos y describe layout.
    El prompt 02 prohíbe enviar el documento al modelo más de dos veces por
    evaluación; esta es la primera (la segunda es la forense) y su resultado se
    reutiliza en todas las etapas posteriores.
    """

    name = "vision"

    def __init__(self, llm: LLMClient, settings: Settings | None = None):
        self.llm = llm
        self.settings = settings or get_settings()

    def extract(self, pages: Sequence[bytes], hint: dict[str, Any] | None = None) -> OcrResult:
        hint = dict(hint or {})
        prompt = EXTRACTION_PROMPT
        if hint.get("document_type_declared"):
            prompt += (
                f"\n\nEl usuario declaró que el documento es de tipo "
                f"'{hint['document_type_declared']}'. Verifícalo: si no coincide con lo "
                f"que ves, informa el tipo real."
            )

        payload = self.llm.describe_image(
            list(pages)[:2],  # las dos primeras páginas bastan para clasificar y extraer
            prompt,
            EXTRACTION_SCHEMA,
            system=EXTRACTION_SYSTEM,
            schema_name="extraccion_documento",
            mock_fn=mock_vision_extraction,
            mock_hint=hint,
        )
        return OcrResult(
            document_type=str(payload.get("document_type", "otro")),
            fields=_normalize_fields(payload.get("fields")),
            layout=str(payload.get("layout", "")),
            engine=self.name,
            notes=[str(payload.get("image_quality_comment", ""))],
        )


class TesseractOcrEngine(OcrEngine):
    """OCR local. Desactivado por defecto (`OCR_ENGINE=tesseract` para activarlo).

    Devuelve texto plano: no clasifica ni estructura campos, así que se combina
    con el motor de visión cuando se necesita estructura. Existe como
    contingencia offline y para comparar costo, no como reemplazo.
    """

    name = "tesseract"

    def __init__(self, language: str = "spa"):
        self.language = language

    def extract(self, pages: Sequence[bytes], hint: dict[str, Any] | None = None) -> OcrResult:
        try:
            import io

            import pytesseract
            from PIL import Image
        except ImportError as exc:  # pragma: no cover - depende del entorno
            raise RuntimeError(
                "OCR_ENGINE=tesseract requiere `pip install -e \".[ocr-local]\"` y el "
                "binario `tesseract` instalado en el sistema."
            ) from exc

        chunks: list[str] = []
        for page in pages:
            with Image.open(io.BytesIO(page)) as image:
                chunks.append(pytesseract.image_to_string(image, lang=self.language))
        text = "\n".join(chunks)
        return OcrResult(
            document_type=str((hint or {}).get("document_type_declared", "otro")),
            fields={},
            layout="",
            raw_text=text,
            engine=self.name,
            notes=["Tesseract entrega texto plano: los campos se derivan de los checks."],
        )


class MockOcrEngine(OcrEngine):
    """Extracción determinista para tests y demos sin tokens.

    Lee la ficha `data/samples/<archivo>.fields.json` que genera
    `scripts/make_sample_documents.py`. Si no existe, devuelve campos vacíos.
    """

    name = "mock"

    def __init__(self, samples_dir: Path | None = None):
        self.samples_dir = samples_dir or get_settings().samples_path

    def extract(self, pages: Sequence[bytes], hint: dict[str, Any] | None = None) -> OcrResult:
        hint = dict(hint or {})
        source = Path(str(hint.get("source_name", ""))).name
        sidecar = self.samples_dir / f"{Path(source).stem}.fields.json"

        if sidecar.exists():
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            return OcrResult(
                document_type=str(data.get("document_type", "otro")),
                fields=_normalize_fields(data.get("fields", {})),
                layout=str(data.get("layout", "")),
                engine=self.name,
            )

        payload = mock_vision_extraction(hint)
        return OcrResult(
            document_type=str(payload.get("document_type", "otro")),
            fields=_normalize_fields(payload.get("fields", {})),
            layout=str(payload.get("layout", "")),
            engine=self.name,
            notes=["Sin ficha sintética asociada: extracción vacía."],
        )


def build_ocr_engine(llm: LLMClient, settings: Settings | None = None) -> OcrEngine:
    """Fábrica del motor de extracción, según `OCR_ENGINE`.

    En `MOCK_MODE=true` siempre se usa el motor mock, sea cual sea `OCR_ENGINE`:
    ningún motor debe tocar la red durante tests o demos.
    """
    settings = settings or get_settings()
    if settings.mock_mode or not settings.has_openai:
        return MockOcrEngine()
    if settings.ocr_engine == "tesseract":
        return TesseractOcrEngine()
    if settings.ocr_engine == "mock":
        return MockOcrEngine()
    return VisionOcrEngine(llm, settings)
