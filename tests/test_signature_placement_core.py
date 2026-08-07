from __future__ import annotations

import io

import fitz
import pytest
from PIL import Image, ImageDraw

from document_integrity_core import insert_signature_image_once
from form_designer_core import add_signature_field
from signature_placement_core import fit_signature_inside, unsigned_signature_field_at


def _signature_png() -> bytes:
    image = Image.new("RGBA", (300, 80), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.line((15, 45, 285, 35), fill=(10, 40, 180, 255), width=8)
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def test_signature_field_hit_and_aspect_fit_preserve_field():
    document = fitz.open()
    document.new_page(width=500, height=300)
    field = add_signature_field(
        document,
        0,
        fitz.Rect(120, 120, 420, 185),
        name="signature",
    )
    try:
        target = unsigned_signature_field_at(document, 0, fitz.Point(200, 150))
        assert target is not None
        assert target.xref == field.xref

        fitted = fit_signature_inside(target.rect, 300, 80)
        assert target.rect.contains(fitted)
        assert fitted.width / fitted.height == pytest.approx(300 / 80, rel=1e-4)

        insert_signature_image_once(
            document,
            page_number=0,
            rect=fitted,
            image_bytes=_signature_png(),
        )

        page = document.load_page(0)
        fields = list(page.widgets() or [])
        assert len(fields) == 1
        assert fields[0].field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE
        assert fields[0].field_name == "signature"
        assert len(page.get_images(full=True)) == 1
    finally:
        document.close()


def test_signature_field_hit_rejects_outside_point():
    document = fitz.open()
    document.new_page(width=300, height=200)
    add_signature_field(document, 0, fitz.Rect(100, 100, 250, 150))
    try:
        assert unsigned_signature_field_at(document, 0, fitz.Point(20, 20)) is None
    finally:
        document.close()
