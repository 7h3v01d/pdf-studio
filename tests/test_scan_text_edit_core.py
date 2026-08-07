from __future__ import annotations

import fitz
import pytest
from PIL import Image, ImageDraw

from scan_text_edit_core import (
    MODE_OVERLAY,
    MODE_REDACT,
    ScanTextReplacement,
    apply_scan_text_replacement,
    choose_drag_endpoint,
    drag_rectangle_is_large_enough,
    fit_font_size,
    inverted_fitz_matrix,
    ocr_text_and_confidence,
    remove_overlay_replacement,
    sample_background_rgb,
)


def _document_with_text() -> fitz.Document:
    doc = fitz.open()
    page = doc.new_page(width=320, height=180)
    page.insert_text((40, 85), "ORIGINAL SCANNED VALUE", fontsize=16)
    return doc


def test_overlay_replacement_is_removable_and_preserves_underlying_content(tmp_path):
    doc = _document_with_text()
    result = apply_scan_text_replacement(
        doc,
        ScanTextReplacement(
            page_number=0,
            rect=(35, 62, 285, 96),
            replacement_text="REPLACEMENT VALUE",
            mode=MODE_OVERLAY,
        ),
    )
    assert result["reversible"] is True
    assert result["annotation_xref"]

    path = tmp_path / "overlay.pdf"
    doc.save(path)
    doc.close()

    reopened = fitz.open(path)
    page = reopened[0]
    annotations = list(page.annots() or [])
    assert len(annotations) == 1
    assert annotations[0].type[1] == "FreeText"
    assert "ORIGINAL SCANNED VALUE" in page.get_text()
    assert remove_overlay_replacement(
        reopened,
        page_number=0,
        annotation_xref=result["annotation_xref"],
    )
    assert list(reopened[0].annots() or []) == []
    assert "ORIGINAL SCANNED VALUE" in reopened[0].get_text()
    reopened.close()


def test_permanent_redaction_removes_original_and_burns_replacement(tmp_path):
    doc = _document_with_text()
    result = apply_scan_text_replacement(
        doc,
        ScanTextReplacement(
            page_number=0,
            rect=(35, 62, 285, 96),
            replacement_text="FINAL VALUE",
            mode=MODE_REDACT,
        ),
    )
    assert result["reversible"] is False

    path = tmp_path / "redacted.pdf"
    doc.save(path, garbage=3, deflate=True)
    doc.close()

    reopened = fitz.open(path)
    text = reopened[0].get_text()
    assert "ORIGINAL SCANNED VALUE" not in text
    assert "FINAL VALUE" in text
    assert list(reopened[0].annots() or []) == []
    reopened.close()


def test_font_fitting_auto_fits_but_positive_request_is_exact():
    automatic = fit_font_size("A long replacement phrase", (0, 0, 100, 20))
    assert 4 <= automatic < 12
    assert fit_font_size("Short", (0, 0, 100, 20), requested_size=0.5) == 0.5
    assert fit_font_size("Short", (0, 0, 100, 20), requested_size=12) == 12
    assert fit_font_size("Short", (0, 0, 100, 20), requested_size=48) == 48
    assert fit_font_size("Short", (0, 0, 100, 20), requested_size=100) == 72


def test_overlay_annotation_uses_the_explicit_font_size():
    doc = fitz.open()
    doc.new_page(width=320, height=180)
    result = apply_scan_text_replacement(
        doc,
        ScanTextReplacement(
            page_number=0,
            rect=(35, 62, 285, 130),
            replacement_text="X",
            mode=MODE_OVERLAY,
            font_size=48,
        ),
    )
    page = doc[0]
    annotation = page.first_annot
    assert annotation is not None
    spans = [
        span
        for block in annotation.get_text("dict")["blocks"]
        if block.get("type") == 0
        for line in block["lines"]
        for span in line["spans"]
    ]
    assert result["font_size"] == 48
    assert spans[0]["size"] == pytest.approx(48)
    doc.close()


def test_permanent_replacement_burns_the_explicit_font_size(tmp_path):
    doc = _document_with_text()
    result = apply_scan_text_replacement(
        doc,
        ScanTextReplacement(
            page_number=0,
            rect=(35, 62, 285, 96),
            replacement_text="X",
            mode=MODE_REDACT,
            font_size=48,
        ),
    )
    output = tmp_path / "exact_size_redaction.pdf"
    doc.save(output, garbage=4, clean=True, deflate=True)
    doc.close()

    reopened = fitz.open(output)
    spans = [
        span
        for block in reopened[0].get_text("dict")["blocks"]
        if block.get("type") == 0
        for line in block["lines"]
        for span in line["spans"]
    ]
    assert result["font_size"] == 48
    assert any(span["text"] == "X" and span["size"] == pytest.approx(48) for span in spans)
    assert list(reopened[0].annots() or []) == []
    reopened.close()


def test_background_sampling_ignores_dark_text_on_light_page():
    image = Image.new("RGB", (180, 60), (238, 242, 247))
    draw = ImageDraw.Draw(image)
    draw.text((10, 20), "dark text", fill=(10, 10, 10))
    sampled = sample_background_rgb(image)
    assert sampled[0] == pytest.approx(238 / 255, abs=0.03)
    assert sampled[1] == pytest.approx(242 / 255, abs=0.03)
    assert sampled[2] == pytest.approx(247 / 255, abs=0.03)


def test_replacement_rejects_empty_text():
    doc = fitz.open()
    doc.new_page()
    with pytest.raises(ValueError, match="cannot be empty"):
        apply_scan_text_replacement(
            doc,
            ScanTextReplacement(
                page_number=0,
                rect=(10, 10, 100, 40),
                replacement_text="   ",
            ),
        )
    doc.close()


def test_overlay_replacement_records_identifying_metadata():
    doc = _document_with_text()
    result = apply_scan_text_replacement(
        doc,
        ScanTextReplacement(
            page_number=0,
            rect=(35, 62, 285, 96),
            replacement_text="IDENTIFIED VALUE",
            mode=MODE_OVERLAY,
        ),
    )
    annot = doc[0].first_annot
    assert annot is not None
    assert annot.xref == result["annotation_xref"]
    assert annot.info.get("subject") == "PDF Studio scan text replacement"
    assert annot.info.get("content") == "IDENTIFIED VALUE"
    doc.close()


def test_permanent_redaction_removes_pixels_from_raster_scan(tmp_path):
    image = Image.new("RGB", (320, 180), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((35, 62, 285, 96), fill="black")
    image_path = tmp_path / "scan.png"
    image.save(image_path)

    doc = fitz.open()
    page = doc.new_page(width=320, height=180)
    page.insert_image(page.rect, filename=str(image_path))

    before = page.get_pixmap(alpha=False)
    before_image = Image.frombytes("RGB", (before.width, before.height), before.samples)
    assert max(before_image.getpixel((250, 80))) < 20

    apply_scan_text_replacement(
        doc,
        ScanTextReplacement(
            page_number=0,
            rect=(35, 62, 285, 96),
            replacement_text="X",
            mode=MODE_REDACT,
            background_color=(1, 1, 1),
        ),
    )
    output = tmp_path / "raster_replaced.pdf"
    doc.save(output, garbage=4, clean=True, deflate=True)
    doc.close()

    reopened = fitz.open(output)
    after = reopened[0].get_pixmap(alpha=False)
    after_image = Image.frombytes("RGB", (after.width, after.height), after.samples)
    assert min(after_image.getpixel((250, 80))) > 240
    assert "X" in reopened[0].get_text()
    reopened.close()


def test_permanent_redaction_blanks_overlapping_vector_line(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=300, height=150)
    page.draw_line((20, 75), (280, 75), color=(0, 0, 0), width=3)

    apply_scan_text_replacement(
        doc,
        ScanTextReplacement(
            page_number=0,
            rect=(100, 60, 200, 90),
            replacement_text="A",
            mode=MODE_REDACT,
            background_color=(1, 1, 1),
        ),
    )
    output = tmp_path / "vector_line_replaced.pdf"
    doc.save(output, garbage=4, clean=True, deflate=True)
    doc.close()

    reopened = fitz.open(output)
    pix = reopened[0].get_pixmap(alpha=False)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    # The line remains outside the selected rectangle but is blanked where it
    # crosses the permanent replacement area.
    assert max(image.getpixel((50, 75))) < 30
    assert min(image.getpixel((190, 75))) > 240
    assert max(image.getpixel((250, 75))) < 30
    reopened.close()


def test_ocr_data_is_reconstructed_without_a_second_tesseract_pass():
    data = {
        "text": ["", "LEON", "PRIEST", "", "NEXT", "LINE"],
        "conf": ["-1", "95", "85", "-1", "75", "65"],
        "block_num": [0, 1, 1, 1, 1, 1],
        "par_num": [0, 1, 1, 1, 1, 1],
        "line_num": [0, 1, 1, 1, 2, 2],
    }
    text, confidence = ocr_text_and_confidence(data)
    assert text == "LEON PRIEST\nNEXT LINE"
    assert confidence == pytest.approx(80.0)


def test_ocr_data_tolerates_missing_layout_columns():
    text, confidence = ocr_text_and_confidence(
        {"text": ["Alpha", "Beta"], "conf": ["90", "bad"]}
    )
    assert text == "Alpha\nBeta"
    assert confidence == pytest.approx(90.0)


def test_drag_endpoint_preserves_last_move_when_release_collapses_to_start():
    endpoint = choose_drag_endpoint(
        (100, 100),
        (260, 145),  # last visible mouse-move endpoint
        (101, 101),  # faulty Windows release endpoint
    )
    assert endpoint == (260.0, 145.0)
    assert drag_rectangle_is_large_enough((100, 100), endpoint)


def test_drag_endpoint_uses_release_when_it_extends_the_selection():
    endpoint = choose_drag_endpoint(
        (100, 100),
        (220, 135),
        (280, 155),
    )
    assert endpoint == (280.0, 155.0)


def test_drag_size_gate_rejects_clicks_and_one_dimensional_strokes():
    assert not drag_rectangle_is_large_enough((10, 10), (12, 13))
    assert not drag_rectangle_is_large_enough((10, 10), (100, 13))
    assert not drag_rectangle_is_large_enough((10, 10), (13, 100))
    assert drag_rectangle_is_large_enough((10, 10), (100, 40))


def test_inverted_fitz_matrix_returns_matrix_not_status_code():
    render = fitz.Matrix(2.0, 4.0)
    inverse = inverted_fitz_matrix(render)
    assert isinstance(inverse, fitz.Matrix)
    mapped = fitz.Point(200, 120) * inverse
    assert mapped.x == pytest.approx(100.0)
    assert mapped.y == pytest.approx(30.0)


def test_inverted_fitz_matrix_keeps_selection_rectangle_nonempty():
    render = fitz.Matrix(2.0, 2.0)
    inverse = inverted_fitz_matrix(render)
    selected_pixels = fitz.Rect(40, 60, 260, 120)
    selected_pdf = selected_pixels * inverse
    assert not selected_pdf.is_empty
    assert tuple(selected_pdf) == pytest.approx((20.0, 30.0, 130.0, 60.0))
