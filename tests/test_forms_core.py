from __future__ import annotations

import os
import tempfile
from pathlib import Path

import fitz


def add_widget(page, field_type, name, rect, *, value=None, choices=None, flags=0, label=None):
    widget = fitz.Widget()
    widget.field_type = field_type
    widget.field_name = name
    widget.field_label = label or name
    widget.rect = fitz.Rect(rect)
    widget.field_flags = flags
    if choices is not None:
        widget.choice_values = list(choices)
    if value is not None:
        widget.field_value = value
    widget.text_font = "Helv"
    widget.text_fontsize = 11
    widget.field_value_default = value
    page.add_widget(widget)


def make_fixture(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 55), "PDF Studio Phase 1 Form Fixture", fontsize=16)

    page.insert_text((50, 105), "Name:")
    add_widget(page, fitz.PDF_WIDGET_TYPE_TEXT, "full_name", (140, 85, 420, 112), value="")

    page.insert_text((50, 150), "Notes:")
    add_widget(
        page, fitz.PDF_WIDGET_TYPE_TEXT, "notes", (140, 125, 420, 200),
        value="", flags=fitz.PDF_TX_FIELD_IS_MULTILINE,
    )

    page.insert_text((50, 235), "Agree:")
    add_widget(page, fitz.PDF_WIDGET_TYPE_CHECKBOX, "agree", (140, 215, 162, 237))

    page.insert_text((50, 280), "Colour:")
    add_widget(
        page, fitz.PDF_WIDGET_TYPE_COMBOBOX, "colour", (140, 258, 300, 287),
        value="Blue", choices=["Blue", "Green", "Red"],
    )

    page.insert_text((50, 330), "Priority:")
    add_widget(
        page, fitz.PDF_WIDGET_TYPE_LISTBOX, "priority", (140, 305, 300, 375),
        value="Medium", choices=["Low", "Medium", "High"],
    )

    page.insert_text((50, 420), "Reference (read-only):")
    add_widget(
        page, fitz.PDF_WIDGET_TYPE_TEXT, "reference", (220, 398, 420, 427),
        value="REF-2026-001", flags=fitz.PDF_FIELD_IS_READ_ONLY,
    )

    page.insert_text((50, 475), "Signature:")
    add_widget(page, fitz.PDF_WIDGET_TYPE_SIGNATURE, "signature", (140, 445, 420, 500))

    doc.save(path)
    doc.close()


def count_widgets(path: Path) -> int:
    doc = fitz.open(path)
    try:
        return sum(len(list(page.widgets() or [])) for page in doc)
    finally:
        doc.close()


def update_and_verify(source: Path, saved: Path, flat: Path) -> None:
    doc = fitz.open(source)
    page = doc[0]
    values = {}
    for field in list(page.widgets() or []):
        if field.field_name == "full_name":
            field.field_value = "Leon Test"
            field.update()
        elif field.field_name == "notes":
            field.field_value = "Line one\nLine two"
            field.update()
        elif field.field_name == "agree":
            field.field_value = True
            field.update()
        elif field.field_name == "colour":
            field.field_value = "Green"
            field.update()
        elif field.field_name == "priority":
            field.field_value = "High"
            field.update()
    doc.save(saved, garbage=3, deflate=True)
    doc.close()

    reopened = fitz.open(saved)
    try:
        values = {w.field_name: w.field_value for w in reopened[0].widgets() or []}
        assert values["full_name"] == "Leon Test", values
        assert values["notes"] == "Line one\nLine two", values
        assert values["agree"] not in (None, "", "Off", False), values
        assert values["colour"] == "Green", values
        assert values["priority"] == "High", values

        clone = fitz.open()
        clone.insert_pdf(reopened, annots=True, widgets=True, join_duplicates=True)
        clone.bake(annots=False, widgets=True)
        clone.save(flat, garbage=4, deflate=True)
        clone.close()
    finally:
        reopened.close()

    assert count_widgets(flat) == 0
    flat_doc = fitz.open(flat)
    try:
        text = "\n".join(page.get_text("text") for page in flat_doc)
        assert "Leon Test" in text, text
        assert "Green" in text, text
        assert "High" in text, text
    finally:
        flat_doc.close()


def test_form_values_persist_and_flatten(tmp_path: Path) -> None:
    """Filled AcroForm values must persist and flatten into page content."""
    source = tmp_path / "fixture.pdf"
    saved = tmp_path / "filled.pdf"
    flat = tmp_path / "filled_flat.pdf"

    make_fixture(source)
    assert count_widgets(source) == 7

    update_and_verify(source, saved, flat)

    assert count_widgets(saved) == 7
    assert count_widgets(flat) == 0


def main() -> None:
    """Allow this test module to remain useful as a standalone smoke test."""
    base = Path(tempfile.mkdtemp(prefix="pdfstudio_forms_"))
    source = base / "fixture.pdf"
    saved = base / "filled.pdf"
    flat = base / "filled_flat.pdf"

    make_fixture(source)
    assert count_widgets(source) == 7
    update_and_verify(source, saved, flat)

    print(f"PASS fixture={source}")
    print(f"PASS saved widgets={count_widgets(saved)}")
    print(f"PASS flattened widgets={count_widgets(flat)}")


if __name__ == "__main__":
    main()
