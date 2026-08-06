from __future__ import annotations

import fitz

from document_integrity_core import open_pdf_snapshot, snapshot_pdf_bytes
from undo_stack import Command, UndoStack


def test_pdf_snapshot_round_trip_preserves_native_change():
    document = fitz.open()
    page = document.new_page(width=250, height=150)
    page.insert_text((40, 70), "BEFORE")
    before = snapshot_pdf_bytes(document)
    page.insert_text((40, 100), "AFTER")
    after = snapshot_pdf_bytes(document)
    document.close()

    restored_before = open_pdf_snapshot(before)
    restored_after = open_pdf_snapshot(after)
    try:
        assert "AFTER" not in restored_before[0].get_text()
        assert "AFTER" in restored_after[0].get_text()
    finally:
        restored_before.close()
        restored_after.close()


def test_undo_stack_evicts_old_binary_snapshots_to_memory_budget():
    stack = UndoStack(max_history=100, max_history_bytes=20)
    stack.push(Command("native", {"pdf_bytes": b"a" * 12}, {"pdf_bytes": b"b" * 12}))
    # One command itself exceeds the budget and is evicted rather than allowing
    # unbounded memory retention.
    assert not stack.can_undo()

    stack = UndoStack(max_history=100, max_history_bytes=25)
    stack.push(Command("one", {"pdf_bytes": b"a" * 5}, {"pdf_bytes": b"b" * 5}))
    stack.push(Command("two", {"pdf_bytes": b"c" * 10}, {"pdf_bytes": b"d" * 10}))
    assert stack.peek_undo().kind == "two"
    # Oldest command was evicted to stay under 30 bytes.
    stack.pop_undo()
    assert not stack.can_undo()
