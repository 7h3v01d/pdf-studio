from __future__ import annotations

import json

import fitz
import pytest

from annotation_integrity_core import (
    atomic_write_json,
    filter_legacy_sidecar_notes,
    pending_markup_only,
    retire_baked_sidecar_state,
)


def _native_note_document():
    document = fitz.open()
    page = document.new_page(width=250, height=150)
    annotation = page.add_text_annot(fitz.Point(40, 50), "Native note")
    annotation.update()
    return document


def test_legacy_sidecar_note_already_native_is_not_loaded_twice():
    document = _native_note_document()
    try:
        filtered = filter_legacy_sidecar_notes(
            {0: [[40, 50, "Native note"], [80, 90, "Pending note"]]},
            document,
        )
        assert filtered == {0: [(80.0, 90.0, "Pending note")]}
    finally:
        document.close()


def test_pending_markup_excludes_baked_and_immediate_native_types():
    result = pending_markup_only({
        0: [
            {"type": "highlight", "baked": True},
            {"type": "underline", "rects": [[1, 2, 3, 4]]},
            {"type": "signature"},
            {"type": "stamp"},
        ]
    })
    assert result == {0: [{"type": "underline", "rects": [[1, 2, 3, 4]]}]}


def test_retire_baked_state_moves_native_compatible_content_out_of_sidecars():
    notes, markup = retire_baked_sidecar_state(
        {0: [(10, 10, "note")]},
        {0: [
            {"type": "highlight", "baked": True},
            {"type": "freehand", "points": [[1, 1], [2, 2]]},
        ]},
    )
    assert notes == {}
    assert markup == {0: [{"type": "freehand", "points": [[1, 1], [2, 2]]}]}


def test_atomic_json_failure_preserves_existing_sidecar(tmp_path):
    destination = tmp_path / "notes.json"
    destination.write_text('{"old": true}', encoding="utf-8")

    with pytest.raises(TypeError):
        atomic_write_json(destination, {"bad": object()})

    assert json.loads(destination.read_text(encoding="utf-8")) == {"old": True}
    assert not list(tmp_path.glob(".notes.json.pdfstudio-*.tmp"))


def test_atomic_json_deletes_empty_sidecar(tmp_path):
    destination = tmp_path / "notes.json"
    destination.write_text("{}", encoding="utf-8")
    atomic_write_json(destination, {})
    assert not destination.exists()
