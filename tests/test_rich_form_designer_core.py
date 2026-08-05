from pathlib import Path

import fitz

from form_designer_core import (
    KIND_DATE,
    KIND_INITIALS,
    add_date_field,
    add_dropdown_field,
    add_radio_group,
    add_signature_field,
    delete_widget,
    radio_group_member_refs,
    update_widget_properties,
    widget_custom_kind,
)


def test_rich_fields_save_reopen_and_update(tmp_path: Path) -> None:
    path = tmp_path / "rich_fields.pdf"
    doc = fitz.open()
    doc.new_page(width=420, height=500)

    dropdown = add_dropdown_field(
        doc, 0, fitz.Rect(30, 30, 220, 60), choices=("", "Red", "Blue")
    )
    date = add_date_field(doc, 0, fitz.Rect(30, 80, 170, 110))
    signature = add_signature_field(doc, 0, fitz.Rect(30, 130, 250, 195))
    initials = add_signature_field(
        doc, 0, fitz.Rect(280, 130, 370, 175), initials=True
    )

    update_widget_properties(
        doc,
        0,
        int(dropdown.xref),
        name="favourite_colour",
        label="Favourite colour",
        required=True,
        read_only=False,
        choices=("", "Red", "Blue", "Green"),
        editable=False,
    )
    doc.save(path, garbage=3, deflate=True)
    doc.close()

    doc = fitz.open(path)
    try:
        page = doc.load_page(0)
        fields = {field.field_name: field for field in page.widgets() or []}
        assert fields["favourite_colour"].choice_values == ["", "Red", "Blue", "Green"]
        assert fields["favourite_colour"].field_flags & fitz.PDF_FIELD_IS_REQUIRED
        assert widget_custom_kind(doc, int(fields["date_field"].xref)) == KIND_DATE
        assert fields["date_field"].text_maxlen == 10
        assert fields["signature"].field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE
        assert widget_custom_kind(doc, int(fields["initials"].xref)) == KIND_INITIALS
        assert not fields["signature"].is_signed
    finally:
        doc.close()


def test_yes_no_radio_group_is_exclusive_and_deletes_as_group(tmp_path: Path) -> None:
    path = tmp_path / "radio.pdf"
    doc = fitz.open()
    doc.new_page(width=300, height=200)
    radios = add_radio_group(doc, 0, fitz.Rect(40, 40, 120, 65))
    assert len(radios) == 2
    refs = radio_group_member_refs(doc, int(radios[0].xref))
    assert len(refs) == 2
    assert radios[0].field_name == radios[1].field_name == "yes_no"

    update_widget_properties(
        doc,
        0,
        int(radios[0].xref),
        name="consent_choice",
        label="Consent choice",
        required=True,
        read_only=False,
    )

    page = doc.load_page(0)
    renamed = list(page.widgets() or [])
    assert {field.field_name for field in renamed} == {"consent_choice"}
    assert all(field.field_flags & fitz.PDF_FIELD_IS_REQUIRED for field in renamed)

    second_xref = int(renamed[1].xref)
    page = doc.load_page(0)
    second = next(field for field in page.widgets() or [] if int(field.xref) == second_xref)
    second.field_value = second.on_state()
    second.update()
    doc.save(path, garbage=3, deflate=True)
    doc.close()

    doc = fitz.open(path)
    page = doc.load_page(0)
    fields = list(page.widgets() or [])
    assert sum(field.field_value == field.on_state() for field in fields) == 1
    selected = next(field for field in fields if field.field_value == field.on_state())
    assert selected.on_state() == "No"
    assert delete_widget(doc, 0, int(fields[0].xref))
    assert list(doc.load_page(0).widgets() or []) == []
    doc.save(tmp_path / "radio_deleted.pdf", garbage=3, deflate=True)
    doc.close()

    reopened = fitz.open(tmp_path / "radio_deleted.pdf")
    try:
        assert list(reopened.load_page(0).widgets() or []) == []
    finally:
        reopened.close()
