from __future__ import annotations

from pathlib import Path

import pytest

from save_bundle_core import (
    StagedOperation,
    cleanup_staged_operations,
    commit_staged_operations,
    stage_json_payload,
)


def test_save_bundle_commits_replacement_creation_and_deletion(tmp_path):
    pdf = tmp_path / "document.pdf"
    annotations = tmp_path / "document.pdf.annotations.json"
    bookmarks = tmp_path / "document.pdf.bookmarks.json"
    pdf.write_bytes(b"OLD-PDF")
    annotations.write_text("old", encoding="utf-8")
    bookmarks.write_text("obsolete", encoding="utf-8")

    staged_pdf = tmp_path / ".staged.pdf"
    staged_pdf.write_bytes(b"NEW-PDF")
    operations = [
        StagedOperation(pdf, staged_pdf),
        stage_json_payload(annotations, {"0": [[10, 20, "note"]]}),
        stage_json_payload(bookmarks, []),
    ]
    try:
        commit_staged_operations(operations)
    finally:
        cleanup_staged_operations(operations)

    assert pdf.read_bytes() == b"NEW-PDF"
    assert "note" in annotations.read_text(encoding="utf-8")
    assert not bookmarks.exists()


def test_save_bundle_rolls_back_every_destination_after_late_failure(tmp_path):
    pdf = tmp_path / "document.pdf"
    sidecar = tmp_path / "document.pdf.annotations.json"
    pdf.write_bytes(b"ORIGINAL-PDF")
    sidecar.write_text("ORIGINAL-SIDECAR", encoding="utf-8")

    staged_pdf = tmp_path / ".staged.pdf"
    staged_pdf.write_bytes(b"NEW-PDF")
    missing = tmp_path / ".missing.json"
    operations = [
        StagedOperation(pdf, staged_pdf),
        StagedOperation(sidecar, missing),
    ]

    with pytest.raises(FileNotFoundError):
        commit_staged_operations(operations)

    assert pdf.read_bytes() == b"ORIGINAL-PDF"
    assert sidecar.read_text(encoding="utf-8") == "ORIGINAL-SIDECAR"


def test_invalid_json_payload_does_not_touch_existing_sidecar(tmp_path):
    destination = tmp_path / "document.pdf.markup.json"
    destination.write_text("ORIGINAL", encoding="utf-8")

    with pytest.raises(TypeError):
        stage_json_payload(destination, {"bad": object()})

    assert destination.read_text(encoding="utf-8") == "ORIGINAL"


def test_save_bundle_rolls_back_a_deleted_sidecar_after_late_failure(tmp_path):
    obsolete = tmp_path / "document.pdf.bookmarks.json"
    later = tmp_path / "document.pdf.markup.json"
    obsolete.write_text("OLD-BOOKMARKS", encoding="utf-8")
    later.write_text("OLD-MARKUP", encoding="utf-8")
    missing = tmp_path / ".missing-stage"

    operations = [
        StagedOperation(obsolete, None),
        StagedOperation(later, missing),
    ]
    with pytest.raises(FileNotFoundError):
        commit_staged_operations(operations)

    assert obsolete.read_text(encoding="utf-8") == "OLD-BOOKMARKS"
    assert later.read_text(encoding="utf-8") == "OLD-MARKUP"
