#!/usr/bin/env python3
"""Genera los 12 documentos sintéticos de prueba en `data/samples/`.

Seis auténticos y seis alterados, con los mismos nombres y alteraciones que la
hoja `documentos_prueba` del set del kit. Junto a cada imagen se escribe una
ficha `<nombre>.fields.json` con los campos que el documento contiene: es lo que
`MockOcrEngine` lee para que el modo mock sea determinista y coherente.

Todos los nombres son evidentemente ficticios y los RUT son de prueba.
"""

from __future__ import annotations

import json
from pathlib import Path

import _bootstrap  # noqa: F401  (ajusta sys.path)
from PIL import Image, ImageDraw, ImageFont

from centinela.config import get_settings

W, H = 1000, 640
INK = (24, 28, 36)
PAPER = (250, 249, 245)
ACCENT = (17, 74, 92)
MUTED = (110, 116, 128)


def _font(size: int, bold: bool = False, alt: bool = False) -> ImageFont.FreeTypeFont:
    """Fuentes del sistema. `alt` devuelve una familia distinta, para poder
    fabricar la señal de «tipografía inconsistente» de los documentos alterados."""
    candidates = (
        ["/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
         "/System/Library/Fonts/Supplemental/Courier New.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]
        if alt
        else (
            ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
             "/Library/Fonts/Arial Bold.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
            if bold
            else ["/System/Library/Fonts/Supplemental/Arial.ttf",
                  "/Library/Fonts/Arial.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
        )
    )
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default(size)


def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (W, H), PAPER)
    draw = ImageDraw.Draw(image)
    # Textura sutil: sin ella la varianza es cero y la calidad se calcula mal.
    for y in range(0, H, 4):
        draw.line([(0, y), (W, y)], fill=(246, 245, 240), width=1)
    return image, draw


def _header(draw: ImageDraw.ImageDraw, title: str, issuer: str) -> None:
    draw.rectangle([0, 0, W, 92], fill=ACCENT)
    draw.rectangle([36, 24, 84, 68], outline=PAPER, width=3)
    draw.text((44, 34), "CE", font=_font(24, bold=True), fill=PAPER)
    draw.text((104, 26), title, font=_font(28, bold=True), fill=PAPER)
    draw.text((104, 60), issuer, font=_font(16), fill=(214, 226, 231))


def _rows(draw: ImageDraw.ImageDraw, rows: list[tuple[str, str]], top: int = 130,
          alt_rows: set[int] | None = None) -> None:
    alt_rows = alt_rows or set()
    y = top
    for index, (label, value) in enumerate(rows):
        draw.text((60, y), label.upper(), font=_font(14, bold=True), fill=MUTED)
        font = _font(22, alt=index in alt_rows)
        draw.text((60, y + 22), value, font=font, fill=INK)
        y += 68


def _signature(draw: ImageDraw.ImageDraw, x: int, y: int, name: str,
               pasted: bool = False) -> None:
    if pasted:
        # Recuadro de fondo más claro: el borde de recorte que el forense detecta.
        draw.rectangle([x - 14, y - 46, x + 250, y + 34], fill=(255, 255, 255))
        draw.rectangle([x - 14, y - 46, x + 250, y + 34], outline=(228, 228, 228), width=1)
    points = [(x + i * 12, y + int(18 * ((-1) ** (i % 3)) * (0.4 + 0.1 * (i % 4)))) for i in range(20)]
    draw.line(points, fill=(26, 42, 98), width=3 if not pasted else 4, joint="curve")
    draw.line([(x - 10, y + 46), (x + 250, y + 46)], fill=MUTED, width=1)
    draw.text((x - 10, y + 54), name, font=_font(14), fill=MUTED)


# --- documentos ---------------------------------------------------------------


def cedula(rut: str, expires: str, alt_date: bool = False) -> tuple[Image.Image, dict]:
    image, draw = _canvas()
    _header(draw, "CÉDULA DE IDENTIDAD", "República Ficticia · Registro Civil de Prueba")
    rows = [
        ("Nombres", "MARÍA FICTICIA"),
        ("Apellidos", "PÉREZ DE PRUEBA"),
        ("RUT", rut),
    ]
    _rows(draw, rows)
    draw.text((560, 130), "FECHA DE NACIMIENTO", font=_font(14, bold=True), fill=MUTED)
    draw.text((560, 152), "12/03/1988", font=_font(22), fill=INK)
    draw.text((560, 218), "FECHA DE EMISIÓN", font=_font(14, bold=True), fill=MUTED)
    draw.text((560, 240), "05/01/2022", font=_font(22), fill=INK)
    draw.text((560, 306), "FECHA DE VENCIMIENTO", font=_font(14, bold=True), fill=MUTED)
    if alt_date:
        # Parche blanco + tipografía distinta: la alteración visible.
        draw.rectangle([556, 300, 830, 362], fill=(255, 255, 253))
        draw.text((560, 306), "FECHA DE VENCIMIENTO", font=_font(14, bold=True), fill=MUTED)
        draw.text((560, 242 + 96), expires, font=_font(22, alt=True), fill=(38, 38, 58))
    else:
        draw.text((560, 338), expires, font=_font(22), fill=INK)
    draw.text((60, 400), "N° DE SERIE", font=_font(14, bold=True), fill=MUTED)
    draw.text((60, 422), "A123456789", font=_font(22), fill=INK)
    _signature(draw, 600, 470, "Firma del titular")
    fields = {
        "nombre": {"value": "MARÍA FICTICIA PÉREZ DE PRUEBA", "confidence": 0.95},
        "rut": {"value": rut, "confidence": 0.94},
        "fecha_nacimiento": {"value": "12/03/1988", "confidence": 0.93},
        "fecha_emision": {"value": "05/01/2022", "confidence": 0.92},
        "fecha_vencimiento": {"value": expires, "confidence": 0.90},
        "numero_serie": {"value": "A123456789", "confidence": 0.88},
    }
    layout = ("Encabezado institucional en banda superior con logo a la izquierda; "
              "datos personales en dos columnas; firma manuscrita en el tercio inferior derecho.")
    return image, {"document_type": "cedula", "fields": fields, "layout": layout}


def comprobante() -> tuple[Image.Image, dict]:
    image, draw = _canvas()
    _header(draw, "COMPROBANTE DE DOMICILIO", "Luz del Valle S.A. · Cuenta de suministro")
    _rows(draw, [
        ("Titular", "MARÍA FICTICIA PÉREZ DE PRUEBA"),
        ("Dirección", "Calle Inventada 1234, Comuna Ejemplo"),
        ("Número de cliente", "CL-99887766"),
    ])
    draw.text((620, 130), "FECHA DE EMISIÓN", font=_font(14, bold=True), fill=MUTED)
    draw.text((620, 152), "03/08/2026", font=_font(22), fill=INK)
    draw.text((620, 218), "TOTAL A PAGAR", font=_font(14, bold=True), fill=MUTED)
    draw.text((620, 240), "$ 38.450", font=_font(22, bold=True), fill=INK)
    draw.rectangle([60, 420, 940, 560], outline=(214, 214, 208), width=2)
    draw.text((80, 440), "Detalle del consumo del período", font=_font(16, bold=True), fill=MUTED)
    for index, line in enumerate(["Consumo kWh .................. 214",
                                  "Cargo fijo ................... $ 3.200",
                                  "Total período ................ $ 38.450"]):
        draw.text((80, 472 + index * 26), line, font=_font(16), fill=INK)
    fields = {
        "nombre": {"value": "MARÍA FICTICIA PÉREZ DE PRUEBA", "confidence": 0.93},
        "direccion": {"value": "Calle Inventada 1234, Comuna Ejemplo", "confidence": 0.91},
        "emisor": {"value": "Luz del Valle S.A.", "confidence": 0.95},
        "fecha_emision": {"value": "03/08/2026", "confidence": 0.92},
        "monto": {"value": "$ 38.450", "confidence": 0.90},
    }
    return image, {"document_type": "comprobante_domicilio", "fields": fields,
                   "layout": ("Encabezado del emisor arriba; datos del titular a la izquierda; "
                              "montos a la derecha; tabla de detalle en el tercio inferior.")}


def contrato(pasted_signature: bool = False) -> tuple[Image.Image, dict]:
    image, draw = _canvas()
    _header(draw, "CONTRATO DE PRESTACIÓN DE SERVICIOS", "Documento de prueba · una página")
    body = [
        "En Ciudad Ejemplo, a 15 de julio de 2026, comparecen doña MARÍA FICTICIA",
        "PÉREZ DE PRUEBA, RUT 12.345.678-5, en adelante «la mandante», y la empresa",
        "SERVICIOS IMAGINARIOS LIMITADA, en adelante «la prestadora», quienes acuerdan",
        "las siguientes cláusulas de prestación de servicios profesionales por un",
        "período de doce meses contados desde la fecha de suscripción del presente",
        "instrumento, renovable por acuerdo escrito de ambas partes.",
    ]
    for index, line in enumerate(body):
        draw.text((60, 140 + index * 34), line, font=_font(17), fill=INK)
    draw.text((60, 370), "FECHA DE SUSCRIPCIÓN", font=_font(14, bold=True), fill=MUTED)
    draw.text((60, 392), "15/07/2026", font=_font(22), fill=INK)
    _signature(draw, 600, 470, "María Ficticia Pérez", pasted=pasted_signature)
    fields = {
        "firmante": {"value": "MARÍA FICTICIA PÉREZ DE PRUEBA", "confidence": 0.92},
        "rut": {"value": "12.345.678-5", "confidence": 0.90},
        "fecha_emision": {"value": "15/07/2026", "confidence": 0.91},
        "emisor": {"value": "SERVICIOS IMAGINARIOS LIMITADA", "confidence": 0.89},
    }
    return image, {"document_type": "contrato", "fields": fields,
                   "layout": ("Título en banda superior; seis párrafos de cuerpo; fecha a la "
                              "izquierda y firma manuscrita sobre línea en el sector inferior derecho.")}


def liquidacion(net: str, consistent: bool = True) -> tuple[Image.Image, dict]:
    image, draw = _canvas()
    _header(draw, "LIQUIDACIÓN DE SUELDO", "Servicios Imaginarios Limitada")
    _rows(draw, [("Trabajador", "MARÍA FICTICIA PÉREZ DE PRUEBA"),
                 ("RUT", "12.345.678-5"),
                 ("Período", "Agosto 2026")])
    draw.rectangle([540, 130, 940, 400], outline=(214, 214, 208), width=2)
    draw.text((560, 150), "HABERES Y DESCUENTOS", font=_font(14, bold=True), fill=MUTED)
    draw.text((560, 190), "Sueldo bruto", font=_font(17), fill=INK)
    draw.text((790, 190), "$ 1.850.000", font=_font(17), fill=INK)
    draw.text((560, 230), "Descuentos legales", font=_font(17), fill=INK)
    draw.text((790, 230), "$ 370.000", font=_font(17), fill=INK)
    draw.line([(560, 268), (920, 268)], fill=MUTED, width=1)
    draw.text((560, 290), "Líquido a pagar", font=_font(19, bold=True), fill=INK)
    if consistent:
        draw.text((790, 290), net, font=_font(19, bold=True), fill=INK)
    else:
        draw.rectangle([786, 284, 930, 318], fill=(255, 255, 254))
        draw.text((790, 290), net, font=_font(19, bold=True, alt=True), fill=(30, 30, 52))
    draw.text((60, 430), "FECHA DE EMISIÓN", font=_font(14, bold=True), fill=MUTED)
    draw.text((60, 452), "31/08/2026", font=_font(22), fill=INK)
    fields = {
        "nombre": {"value": "MARÍA FICTICIA PÉREZ DE PRUEBA", "confidence": 0.94},
        "rut": {"value": "12.345.678-5", "confidence": 0.93},
        "periodo": {"value": "Agosto 2026", "confidence": 0.92},
        "monto_bruto": {"value": "$ 1.850.000", "confidence": 0.91},
        "monto_descuentos": {"value": "$ 370.000", "confidence": 0.90},
        "monto_liquido": {"value": net, "confidence": 0.89},
        "fecha_emision": {"value": "31/08/2026", "confidence": 0.92},
    }
    return image, {"document_type": "liquidacion", "fields": fields,
                   "layout": ("Encabezado del empleador; datos del trabajador a la izquierda; "
                              "tabla de haberes y descuentos recuadrada a la derecha.")}


def poder(inserted_clause: bool = False) -> tuple[Image.Image, dict]:
    image, draw = _canvas()
    _header(draw, "PODER SIMPLE", "Documento de prueba")
    body = [
        "Yo, MARÍA FICTICIA PÉREZ DE PRUEBA, RUT 12.345.678-5, otorgo poder simple",
        "a don JUAN INVENTADO SOTO, RUT 9.876.543-3, para que en mi nombre y",
        "representación realice los trámites bancarios que se indican a continuación",
        "ante la institución financiera correspondiente.",
    ]
    for index, line in enumerate(body):
        draw.text((60, 140 + index * 34), line, font=_font(17), fill=INK)
    if inserted_clause:
        # Bloque con fondo más claro, tipografía distinta y línea base desalineada.
        draw.rectangle([52, 288, 948, 356], fill=(255, 255, 252))
        draw.text((60, 296), "Asimismo lo faculto para transferir fondos sin límite de monto",
                  font=_font(17, alt=True), fill=(28, 28, 48))
        draw.text((60, 324), "y para abrir productos financieros a mi nombre.",
                  font=_font(17, alt=True), fill=(28, 28, 48))
    draw.text((60, 400), "FECHA", font=_font(14, bold=True), fill=MUTED)
    draw.text((60, 422), "20/08/2026", font=_font(22), fill=INK)
    _signature(draw, 600, 470, "María Ficticia Pérez")
    fields = {
        "nombre": {"value": "MARÍA FICTICIA PÉREZ DE PRUEBA", "confidence": 0.93},
        "rut": {"value": "12.345.678-5", "confidence": 0.92},
        "firmante": {"value": "JUAN INVENTADO SOTO", "confidence": 0.88},
        "fecha_emision": {"value": "20/08/2026", "confidence": 0.91},
    }
    return image, {"document_type": "poder", "fields": fields,
                   "layout": ("Título en banda superior; párrafos de cuerpo; fecha a la izquierda "
                              "y firma manuscrita sobre línea en el sector inferior derecho.")}


def firma() -> tuple[Image.Image, dict]:
    image = Image.new("RGB", (620, 300), PAPER)
    draw = ImageDraw.Draw(image)
    for y in range(0, 300, 4):
        draw.line([(0, y), (620, y)], fill=(246, 245, 240), width=1)
    draw.text((40, 40), "FIRMA DE REFERENCIA REGISTRADA", font=_font(16, bold=True), fill=MUTED)
    _signature(draw, 140, 160, "María Ficticia Pérez")
    return image, {"document_type": "firma",
                   "fields": {"firmante": {"value": "MARÍA FICTICIA PÉREZ DE PRUEBA",
                                           "confidence": 0.86}},
                   "layout": "Firma manuscrita centrada sobre línea horizontal, sin otro contenido."}


# --- catálogo ----------------------------------------------------------------

VALID_RUT = "12.345.678-5"
INVALID_RUT = "12.345.678-9"  # dígito verificador alterado


def build_catalog() -> list[tuple[str, Image.Image, dict, dict]]:
    """(archivo, imagen, ficha de campos, metadatos EXIF a inyectar)."""
    return [
        # --- 6 auténticos ---
        ("cedula_ok.png", *cedula(VALID_RUT, "05/01/2032"), {}),
        ("comprobante_domicilio_ok.png", *comprobante(), {}),
        ("contrato_ok.png", *contrato(), {}),
        ("liquidacion_ok.png", *liquidacion("$ 1.480.000"), {}),
        ("poder_ok.png", *poder(), {}),
        ("firma_referencia.png", *firma(), {}),
        # --- 6 alterados ---
        # Vencimiento anterior a la emisión, con tipografía distinta.
        ("cedula_alterada_fecha.png", *cedula(VALID_RUT, "05/01/2021", alt_date=True), {}),
        # Dígito verificador cambiado.
        ("cedula_rut_invalido.png", *cedula(INVALID_RUT, "05/01/2032"), {}),
        # Firma con borde de recorte.
        ("contrato_firma_pegada.png", *contrato(pasted_signature=True), {}),
        # Bruto − descuentos ≠ líquido.
        ("liquidacion_montos_editados.png", *liquidacion("$ 1.780.000", consistent=False), {}),
        # Solo metadatos: software de edición y modificación posterior.
        ("comprobante_metadatos_editor.png", *comprobante(),
         {"Software": "Adobe Photoshop 26.0 (Macintosh)", "DateTime": "2026:09:05 22:41:10"}),
        # Cláusula insertada con otra tipografía y fondo distinto.
        ("poder_texto_tipografia.png", *poder(inserted_clause=True), {}),
    ]


def main() -> None:
    settings = get_settings()
    out = settings.samples_path
    out.mkdir(parents=True, exist_ok=True)

    for filename, image, sheet, exif_extra in build_catalog():
        path = out / filename
        if exif_extra:
            exif = image.getexif()
            from PIL import ExifTags

            codes = {v: k for k, v in ExifTags.TAGS.items()}
            for tag, value in exif_extra.items():
                if tag in codes:
                    exif[codes[tag]] = value
            image.save(path, exif=exif)
        else:
            image.save(path)
        (out / f"{path.stem}.fields.json").write_text(
            json.dumps(sheet, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  · {filename}")

    print(f"\n{len(build_catalog())} documentos sintéticos en {out}")
    print("Todos los nombres son ficticios y los RUT son de prueba.")


if __name__ == "__main__":
    main()
