from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from form_designer_core import (
    add_checkbox_field,
    add_text_field,
    delete_widget,
    find_widget,
    move_or_resize_widget,
    update_widget_properties,
)


def widget_records(path: Path) -> list[dict]:
    document = fitz.open(path)
    try:
        records = []
        for page_number in range(document.page_count):
            page = document.load_page(page_number)
            for widget in page.widgets() or []:
                records.append(
                    {
                        "page": page_number,
                        "xref": widget.xref,
                        "name": widget.field_name,
                        "type": widget.field_type,
                        "label": widget.field_label,
                        "flags": int(widget.field_flags or 0),
                        "rect": tuple(round(value, 2) for value in widget.rect),
                    }
                )
        return records
    finally:
        document.close()


def test_designer_create_move_resize_properties_delete_and_reopen(tmp_path: Path) -> None:
    source = tmp_path / "designed.pdf"
    document = fitz.open()
    document.new_page(width=400, height=300)

    text = add_text_field(document, 0, fitz.Rect(40, 50, 240, 80))
    checkbox = add_checkbox_field(document, 0, fitz.Rect(40, 110, 65, 135))
    assert text.field_name == "text_field"
    assert checkbox.field_name == "checkbox"

    text_xref = int(text.xref)
    checkbox_xref = int(checkbox.xref)

    move_or_resize_widget(document, 0, text_xref, fitz.Rect(70, 65, 310, 105))
    update_widget_properties(
        document,
        0,
        text_xref,
        name="customer_name",
        label="Customer name",
        required=True,
        read_only=False,
        multiline=False,
    )

    assert delete_widget(document, 0, checkbox_xref)
    assert not delete_widget(document, 0, checkbox_xref)
    document.save(source, garbage=3, deflate=True)
    document.close()

    records = widget_records(source)
    assert len(records) == 1
    record = records[0]
    assert record["name"] == "customer_name"
    assert record["label"] == "Customer name"
    assert record["type"] == fitz.PDF_WIDGET_TYPE_TEXT
    assert record["flags"] & fitz.PDF_FIELD_IS_REQUIRED
    assert record["rect"] == (70.0, 65.0, 310.0, 105.0)

    reopened = fitz.open(source)
    try:
        page = reopened.load_page(0)
        field = next(iter(page.widgets() or []))
        field.field_value = "Leon Test"
        field.update()
        reopened.saveIncr()
    finally:
        reopened.close()

    reopened = fitz.open(source)
    try:
        page = reopened.load_page(0)
        field = next(iter(page.widgets() or []))
        assert field.field_value == "Leon Test"
    finally:
        reopened.close()


def test_designer_names_are_unique_and_duplicate_rename_is_rejected() -> None:
    document = fitz.open()
    document.new_page(width=250, height=200)
    first = add_text_field(document, 0, fitz.Rect(10, 10, 100, 30))
    second = add_text_field(document, 0, fitz.Rect(10, 50, 100, 70))

    assert first.field_name == "text_field"
    assert second.field_name == "text_field_2"

    with pytest.raises(ValueError, match="already exists"):
        update_widget_properties(
            document,
            0,
            int(second.xref),
            name="text_field",
            label="Duplicate",
            required=False,
            read_only=False,
            multiline=False,
        )
    document.close()


def test_designer_rectangles_remain_inside_page() -> None:
    document = fitz.open()
    page = document.new_page(width=120, height=90)
    field = add_text_field(document, 0, fitz.Rect(110, 85, 111, 86))
    assert page.rect.contains(field.rect)
    assert field.rect.width >= 50
    assert field.rect.height >= 18

    moved = move_or_resize_widget(
        document, 0, int(field.xref), fitz.Rect(-100, -100, -20, -50)
    )
    assert page.rect.contains(moved.rect)
    document.close()
