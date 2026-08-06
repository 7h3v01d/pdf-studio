from __future__ import annotations

import os
from pathlib import Path

import fitz
import pytest

from document_integrity_core import (
    DocumentIntegrityError,
    apply_redactions_transactionally,
    flatten_form_atomic,
    insert_signature_image_once,
    save_pdf_atomic,
    validate_redaction_plan,
)


def _text_pdf(lines=("SECRET-A", "SECRET-B")) -> fitz.Document:
    doc = fitz.open()
    for text in lines:
        page = doc.new_page(width=300, height=200)
        page.insert_text((50, 80), text, fontsize=18)
    return doc


def _tiny_png_bytes() -> bytes:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 4, 4), False)
    pix.clear_with(255)
    return pix.tobytes("png")


def test_redaction_plan_rejects_another_document_session():
    doc = _text_pdf(("SECRET",))
    try:
        with pytest.raises(DocumentIntegrityError, match="different document session"):
            validate_redaction_plan(
                doc,
                {0: [fitz.Rect(40, 55, 170, 90)]},
                redaction_session_id="session-a",
                active_session_id="session-b",
            )
    finally:
        doc.close()


def test_redaction_plan_validates_every_page_before_mutation():
    doc = _text_pdf()
    original = doc[0].get_text()
    try:
        with pytest.raises(DocumentIntegrityError, match="outside this document"):
            apply_redactions_transactionally(
                doc,
                {
                    0: [fitz.Rect(40, 55, 170, 90)],
                    99: [fitz.Rect(40, 55, 170, 90)],
                },
                redaction_session_id="same",
                active_session_id="same",
            )
        assert doc[0].get_text() == original
    finally:
        doc.close()


def test_transactional_redaction_changes_clone_not_active_document():
    doc = _text_pdf(("TOP SECRET",))
    try:
        result = apply_redactions_transactionally(
            doc,
            {0: [fitz.Rect(40, 55, 190, 95)]},
            redaction_session_id="same",
            active_session_id="same",
        )
        try:
            assert "TOP SECRET" in doc[0].get_text()
            assert "TOP SECRET" not in result[0].get_text()
            assert result.page_count == doc.page_count
        finally:
            result.close()
    finally:
        doc.close()


def test_atomic_save_preserves_existing_destination_when_validation_fails(tmp_path):
    destination = tmp_path / "existing.pdf"
    destination.write_bytes(b"ORIGINAL USER FILE")
    doc = _text_pdf(("NEW",))
    try:
        with pytest.raises(RuntimeError, match="late verification failure"):
            save_pdf_atomic(
                doc,
                destination,
                validator=lambda _path: (_ for _ in ()).throw(
                    RuntimeError("late verification failure")
                ),
            )
        assert destination.read_bytes() == b"ORIGINAL USER FILE"
        assert not list(tmp_path.glob(".*.pdfstudio-*.pdf"))
    finally:
        doc.close()


def test_flatten_atomic_preserves_existing_destination_on_prepare_failure(tmp_path):
    source = fitz.open()
    page = source.new_page(width=300, height=200)
    widget = fitz.Widget()
    widget.field_name = "name"
    widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    widget.rect = fitz.Rect(50, 60, 200, 90)
    page.add_widget(widget)
    destination = tmp_path / "flattened.pdf"
    destination.write_bytes(b"PREVIOUS FILE")
    try:
        with pytest.raises(RuntimeError, match="prepare failed"):
            flatten_form_atomic(
                source,
                destination,
                prepare_clone=lambda _clone: (_ for _ in ()).throw(
                    RuntimeError("prepare failed")
                ),
            )
        assert destination.read_bytes() == b"PREVIOUS FILE"
    finally:
        source.close()


def test_flatten_atomic_creates_valid_noninteractive_copy(tmp_path):
    source = fitz.open()
    page = source.new_page(width=300, height=200)
    widget = fitz.Widget()
    widget.field_name = "name"
    widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    widget.field_value = "Leon"
    widget.rect = fitz.Rect(50, 60, 200, 90)
    page.add_widget(widget)
    destination = tmp_path / "flattened.pdf"
    try:
        count = flatten_form_atomic(source, destination)
        assert count == 1
        check = fitz.open(destination)
        try:
            assert list(check[0].widgets() or []) == []
        finally:
            check.close()
    finally:
        source.close()


def test_signature_image_is_inserted_once_and_survives_save(tmp_path):
    doc = _text_pdf(("SIGN HERE",))
    try:
        xref = insert_signature_image_once(
            doc,
            page_number=0,
            rect=fitz.Rect(50, 100, 150, 140),
            image_bytes=_tiny_png_bytes(),
        )
        assert xref > 0
        assert len(doc[0].get_images(full=True)) == 1
        output = tmp_path / "signed.pdf"
        save_pdf_atomic(doc, output)
        reopened = fitz.open(output)
        try:
            assert len(reopened[0].get_images(full=True)) == 1
        finally:
            reopened.close()
    finally:
        doc.close()


def test_signature_rejects_integer_list_payload():
    doc = _text_pdf(("SIGN HERE",))
    try:
        with pytest.raises(TypeError, match="bytes-like"):
            insert_signature_image_once(
                doc,
                page_number=0,
                rect=fitz.Rect(50, 100, 150, 140),
                image_bytes=[1, 2, 3],  # type: ignore[arg-type]
            )
    finally:
        doc.close()


def test_atomic_encrypted_save_validates_with_password(tmp_path):
    doc = _text_pdf(("PRIVATE",))
    output = tmp_path / "protected.pdf"
    try:
        save_pdf_atomic(
            doc,
            output,
            save_kwargs={
                "encryption": fitz.PDF_ENCRYPT_AES_256,
                "user_pw": "reader",
                "owner_pw": "owner",
                "permissions": fitz.PDF_PERM_ACCESSIBILITY,
                "garbage": 4,
                "deflate": True,
            },
            validator=lambda path: __import__("document_integrity_core").validate_pdf_file(
                path, expected_pages=1, password="reader"
            ),
        )
        check = fitz.open(output)
        try:
            assert check.needs_pass
            assert check.authenticate("reader")
            assert "PRIVATE" in check[0].get_text()
        finally:
            check.close()
    finally:
        doc.close()
