"""Preproceso de documentos: PDF → imagen, orientación, calidad y metadatos."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
from PIL import ExifTags, Image, ImageOps

from centinela.config import get_settings

# Software de edición cuya presencia en los metadatos es señal de alerta.
EDITOR_SOFTWARE_HINTS = (
    "photoshop",
    "gimp",
    "illustrator",
    "canva",
    "paint",
    "pixelmator",
    "inkscape",
    "affinity",
    "snapseed",
    "picsart",
)

MAX_SIDE_PX = 1600  # Reduce el costo de la llamada de visión sin perder legibilidad.


@dataclass
class PreparedDocument:
    """Resultado del preproceso, listo para visión y checks."""

    pages: list[bytes] = field(default_factory=list)
    page_sizes: list[tuple[int, int]] = field(default_factory=list)
    image_quality: float = 1.0
    quality_detail: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    source_name: str = ""
    mime: str = "image/png"

    @property
    def pages_analyzed(self) -> int:
        return len(self.pages)


class DocumentTooLargeError(ValueError):
    pass


class UnsupportedDocumentError(ValueError):
    pass


def _to_png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _normalize(image: Image.Image) -> Image.Image:
    """Corrige orientación EXIF y limita el lado mayor."""
    image = ImageOps.exif_transpose(image)
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    if max(image.size) > MAX_SIDE_PX:
        ratio = MAX_SIDE_PX / max(image.size)
        image = image.resize(
            (max(1, int(image.width * ratio)), max(1, int(image.height * ratio))),
            Image.LANCZOS,
        )
    return image


def compute_quality(image: Image.Image) -> tuple[float, dict[str, float]]:
    """Calidad en [0, 1] a partir de nitidez, contraste y resolución.

    - Nitidez: varianza del laplaciano (aproximado con NumPy, sin OpenCV).
    - Contraste: desviación estándar de la luminancia.
    - Resolución: lado menor contra un mínimo razonable para leer texto.
    """
    gray = np.asarray(image.convert("L"), dtype=np.float64) / 255.0
    if gray.size == 0:
        return 0.0, {"sharpness": 0.0, "contrast": 0.0, "resolution": 0.0}

    # Laplaciano 3×3 por diferencias finitas.
    laplacian = (
        -4.0 * gray[1:-1, 1:-1]
        + gray[:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, :-2]
        + gray[1:-1, 2:]
    ) if gray.shape[0] > 2 and gray.shape[1] > 2 else np.zeros((1, 1))

    sharpness_raw = float(np.var(laplacian))
    contrast_raw = float(np.std(gray))
    min_side = min(image.size)

    sharpness = float(np.clip(sharpness_raw / 0.004, 0.0, 1.0))
    contrast = float(np.clip(contrast_raw / 0.22, 0.0, 1.0))
    resolution = float(np.clip(min_side / 800.0, 0.0, 1.0))

    quality = round(0.45 * sharpness + 0.35 * contrast + 0.20 * resolution, 4)
    return quality, {
        "sharpness": round(sharpness, 4),
        "contrast": round(contrast, 4),
        "resolution": round(resolution, 4),
        "sharpness_raw": round(sharpness_raw, 6),
        "contrast_raw": round(contrast_raw, 6),
    }


def extract_image_metadata(image: Image.Image) -> dict[str, Any]:
    """EXIF relevante: software, fechas y fabricante."""
    meta: dict[str, Any] = {"format": image.format or "", "size": list(image.size)}
    try:
        raw = image.getexif()
    except Exception:  # noqa: BLE001 - EXIF ausente o corrupto no es un error
        return meta
    if not raw:
        return meta
    names = {v: k for k, v in ExifTags.TAGS.items()}
    for tag in ("Software", "DateTime", "DateTimeOriginal", "DateTimeDigitized", "Make", "Model"):
        code = names.get(tag)
        if code is not None and code in raw:
            meta[tag] = str(raw[code])
    return meta


def extract_pdf_metadata(raw: bytes) -> dict[str, Any]:
    """Productor, creador y fechas del PDF."""
    meta: dict[str, Any] = {}
    try:
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(raw)
        for key in ("Producer", "Creator", "CreationDate", "ModDate", "Title"):
            try:
                value = document.get_metadata_value(key)
            except Exception:  # noqa: BLE001
                value = None
            if value:
                meta[key] = str(value)
        meta["page_count"] = len(document)
        document.close()
    except Exception as exc:  # noqa: BLE001 - PDF ilegible se reporta, no revienta
        meta["error"] = str(exc)
    return meta


def looks_like_pdf(raw: bytes) -> bool:
    return raw[:5] == b"%PDF-"


def prepare(raw: bytes, filename: str = "") -> PreparedDocument:
    """Punto de entrada del preproceso. Acepta JPG, PNG y PDF."""
    settings = get_settings()
    if len(raw) > settings.max_upload_mb * 1024 * 1024:
        raise DocumentTooLargeError(
            f"El archivo supera el máximo de {settings.max_upload_mb} MB."
        )
    if not raw:
        raise UnsupportedDocumentError("El archivo está vacío.")

    prepared = PreparedDocument(source_name=filename)

    if looks_like_pdf(raw):
        prepared.metadata = {"pdf": extract_pdf_metadata(raw)}
        prepared.pages, prepared.page_sizes = _render_pdf(raw, settings.max_pdf_pages,
                                                          settings.pdf_render_dpi)
    else:
        try:
            image = Image.open(io.BytesIO(raw))
            image.load()
        except Exception as exc:  # noqa: BLE001
            raise UnsupportedDocumentError(
                "Formato no soportado. Usa JPG, PNG o PDF."
            ) from exc
        prepared.metadata = {"image": extract_image_metadata(image)}
        normalized = _normalize(image)
        prepared.pages = [_to_png_bytes(normalized)]
        prepared.page_sizes = [normalized.size]

    if not prepared.pages:
        raise UnsupportedDocumentError("No se pudo extraer ninguna página del documento.")

    qualities: list[float] = []
    details: list[dict[str, float]] = []
    for page in prepared.pages:
        with Image.open(io.BytesIO(page)) as page_image:
            quality, detail = compute_quality(page_image)
        qualities.append(quality)
        details.append(detail)

    # La compuerta usa la mejor página: si una está nítida, el documento es legible.
    best = int(np.argmax(qualities))
    prepared.image_quality = qualities[best]
    prepared.quality_detail = {**details[best], "per_page": qualities}  # type: ignore[dict-item]
    return prepared


def _render_pdf(raw: bytes, max_pages: int, dpi: int) -> tuple[list[bytes], list[tuple[int, int]]]:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(raw)
    pages: list[bytes] = []
    sizes: list[tuple[int, int]] = []
    try:
        for index in range(min(len(document), max_pages)):
            page = document[index]
            bitmap = page.render(scale=dpi / 72.0)
            image = _normalize(bitmap.to_pil())
            pages.append(_to_png_bytes(image))
            sizes.append(image.size)
    finally:
        document.close()
    return pages, sizes


def modification_after_issue(metadata: dict[str, Any], issue_date: datetime | None) -> bool:
    """True si los metadatos muestran una edición posterior a la fecha de emisión."""
    if issue_date is None:
        return False
    candidates: list[str] = []
    for section in metadata.values():
        if isinstance(section, dict):
            for key in ("ModDate", "DateTime", "DateTimeDigitized"):
                if section.get(key):
                    candidates.append(str(section[key]))
    for value in candidates:
        parsed = _parse_loose_date(value)
        if parsed and parsed.date() > issue_date.date():
            return True
    return False


def editor_software(metadata: dict[str, Any]) -> str | None:
    """Devuelve el software de edición detectado en los metadatos, si lo hay."""
    for section in metadata.values():
        if not isinstance(section, dict):
            continue
        for key in ("Software", "Producer", "Creator"):
            value = str(section.get(key, "")).lower()
            for hint in EDITOR_SOFTWARE_HINTS:
                if hint in value:
                    return str(section[key])
    return None


def _parse_loose_date(value: str) -> datetime | None:
    cleaned = value.replace("D:", "").strip()
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y%m%d%H%M%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned[: len(fmt) + 4], fmt)
        except ValueError:
            continue
    return None
