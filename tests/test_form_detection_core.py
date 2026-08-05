from __future__ import annotations

import fitz
from PIL import Image, ImageDraw

from form_detection_core import (
    GraphicPrimitive,
    OCRWord,
    detect_form_suggestions,
    raster_graphics_from_image,
)


def _word(text, rect, confidence=1.0):
    return OCRWord(text=text, rect=tuple(rect), confidence=confidence, source="native")


def test_label_and_vector_geometry_produce_reviewable_suggestions():
    page_rect = fitz.Rect(0, 0, 600, 800)
    words = [
        _word("Full", (40, 50, 66, 62)),
        _word("Name:", (70, 50, 112, 62)),
        _word("Date:", (40, 100, 75, 112)),
        _word("Signature:", (40, 160, 100, 172)),
    ]
    graphics = [
        GraphicPrimitive("hline", (125, 61, 350, 62), 1.0, "vector"),
        GraphicPrimitive("box", (90, 94, 205, 118), 1.0, "vector"),
        GraphicPrimitive("box", (115, 145, 330, 190), 1.0, "vector"),
    ]

    suggestions = detect_form_suggestions(
        page_number=0,
        page_rect=page_rect,
        words=words,
        graphics=graphics,
    )

    assert [item.kind for item in suggestions] == ["text", "date", "signature"]
    assert all(item.confidence >= 0.60 for item in suggestions)
    assert suggestions[0].label == "Full Name"
    assert suggestions[1].name == "date"


def test_existing_field_overlap_suppresses_duplicate_suggestion():
    page_rect = fitz.Rect(0, 0, 600, 800)
    suggestions = detect_form_suggestions(
        page_number=0,
        page_rect=page_rect,
        words=[_word("Email:", (40, 50, 85, 62))],
        graphics=[GraphicPrimitive("hline", (100, 61, 350, 62))],
        existing_field_rects=[(95, 40, 355, 66)],
    )
    assert suggestions == []


def test_raster_scan_detects_checkbox_and_answer_box():
    image = Image.new("RGB", (800, 1000), "white")
    draw = ImageDraw.Draw(image)
    # checkbox outline
    draw.rectangle((120, 150, 150, 180), outline="black", width=3)
    # wide answer rectangle
    draw.rectangle((260, 250, 650, 300), outline="black", width=3)

    page_rect = fitz.Rect(0, 0, 400, 500)
    graphics = raster_graphics_from_image(image, page_rect)
    boxes = [item for item in graphics if item.kind == "box"]

    assert any(12 <= item.fitz_rect.width <= 20 for item in boxes)
    assert any(item.fitz_rect.width >= 180 and item.fitz_rect.height >= 20 for item in boxes)

    suggestions = detect_form_suggestions(
        page_number=0,
        page_rect=page_rect,
        words=[
            _word("Agree", (35, 73, 56, 84)),
            _word("Account:", (70, 127, 120, 139)),
        ],
        graphics=graphics,
    )
    assert any(item.kind == "checkbox" for item in suggestions)
    assert any(item.kind == "text" for item in suggestions)


def test_inferred_label_suggestion_is_lower_confidence_and_requires_review():
    page_rect = fitz.Rect(0, 0, 600, 800)
    suggestions = detect_form_suggestions(
        page_number=2,
        page_rect=page_rect,
        words=[_word("Phone:", (40, 50, 82, 62), 0.90)],
        graphics=[],
    )
    assert len(suggestions) == 1
    suggestion = suggestions[0]
    assert suggestion.page == 2
    assert suggestion.kind == "text"
    assert 0.60 <= suggestion.confidence < 0.80
    assert "inferred" in suggestion.rationale.lower()


def test_approved_suggestions_create_real_persistent_fields(tmp_path):
    from form_detection_core import create_fields_from_suggestions

    path = tmp_path / "detected_fields.pdf"
    doc = fitz.open()
    doc.new_page(width=400, height=500)
    suggestions = [
        {
            "page": 0,
            "kind": "text",
            "rect": (100, 50, 280, 76),
            "label": "Full Name",
            "name": "full_name",
            "multiline": False,
        },
        {
            "page": 0,
            "kind": "checkbox",
            "rect": (100, 100, 120, 120),
            "label": "I agree",
            "name": "agree",
        },
        {
            "page": 0,
            "kind": "date",
            "rect": (100, 150, 220, 176),
            "label": "Date",
            "name": "date",
        },
    ]
    created, failures = create_fields_from_suggestions(doc, suggestions)
    assert failures == []
    assert len(created) == 3
    doc.save(path)
    doc.close()

    with fitz.open(path) as check:
        widgets = list(check[0].widgets() or [])
        assert [widget.field_name for widget in widgets] == [
            "full_name", "agree", "date"
        ]
        assert [widget.field_label for widget in widgets] == [
            "Full Name", "I agree", "Date"
        ]
