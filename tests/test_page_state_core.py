from __future__ import annotations

from types import SimpleNamespace

from page_state_core import (
    capture_page_bound_state,
    delete_page_mapping,
    insert_page_mapping,
    move_page_mapping,
    remap_page_bound_state,
    restore_page_bound_state,
)


def _owner():
    return SimpleNamespace(
        annotations={0: ["a"], 1: ["b"], 2: ["c"]},
        markup_strokes={0: ["m0"], 2: ["m2"]},
        pending_redactions={1: ["r1"], 2: ["r2"]},
        bookmarks=[{"page": 0, "label": "A"}, {"page": 2, "label": "C"}],
        search_results=[{"page": 1, "rects": []}, {"page": 2, "rects": []}],
        current_selection_page=2,
        _freehand_page=1,
        _form_drag_page=2,
        current_page=1,
        current_search_index=1,
        _selected_form_ref=(2, 99),
        _form_suggestions=[object()],
        _selected_form_suggestion_id="suggestion",
        _form_detection_context={"page": 2},
    )


def test_insert_mapping_shifts_every_page_bound_collection():
    owner = _owner()
    remap_page_bound_state(owner, insert_page_mapping(3, 1))
    assert owner.annotations == {0: ["a"], 2: ["b"], 3: ["c"]}
    assert owner.markup_strokes == {0: ["m0"], 3: ["m2"]}
    assert owner.pending_redactions == {2: ["r1"], 3: ["r2"]}
    assert [item["page"] for item in owner.bookmarks] == [0, 3]
    assert [item["page"] for item in owner.search_results] == [2, 3]
    assert owner._selected_form_ref == (3, 99)
    assert owner._form_suggestions == []


def test_delete_mapping_drops_deleted_page_and_shifts_later_state():
    owner = _owner()
    remap_page_bound_state(owner, delete_page_mapping(3, 1))
    assert owner.annotations == {0: ["a"], 1: ["c"]}
    assert owner.pending_redactions == {1: ["r2"]}
    assert [item["page"] for item in owner.search_results] == [1]
    assert owner._freehand_page == -1
    assert owner.current_search_index == 0


def test_move_mapping_tracks_source_and_intervening_pages_both_directions():
    assert move_page_mapping(4, 1, 3) == {0: 0, 1: 3, 2: 1, 3: 2}
    assert move_page_mapping(4, 3, 1) == {0: 0, 1: 2, 2: 3, 3: 1}


def test_snapshot_restore_recovers_sidecar_state_for_undo():
    owner = _owner()
    before = capture_page_bound_state(owner)
    remap_page_bound_state(owner, delete_page_mapping(3, 1))
    restore_page_bound_state(owner, before)
    assert owner.annotations == {0: ["a"], 1: ["b"], 2: ["c"]}
    assert owner.pending_redactions == {1: ["r1"], 2: ["r2"]}
    assert owner.bookmarks[-1]["page"] == 2
    assert owner._selected_form_ref == (2, 99)


def _labelled_document(page_count=4):
    import fitz

    document = fitz.open()
    for index in range(page_count):
        page = document.new_page()
        page.insert_text((72, 72), f"PAGE-{index}")
    return document


def _page_labels(document):
    return [document.load_page(i).get_text().strip() for i in range(document.page_count)]


def test_real_pdf_move_down_uses_final_index_semantics():
    from page_state_core import move_page_to_final_index

    document = _labelled_document()
    try:
        move_page_to_final_index(document, 1, 2)
        assert _page_labels(document) == ["PAGE-0", "PAGE-2", "PAGE-1", "PAGE-3"]
    finally:
        document.close()


def test_real_pdf_move_to_last_and_back_restores_page_content_order():
    from page_state_core import move_page_to_final_index

    document = _labelled_document()
    try:
        move_page_to_final_index(document, 1, 3)
        assert _page_labels(document) == ["PAGE-0", "PAGE-2", "PAGE-3", "PAGE-1"]
        move_page_to_final_index(document, 3, 1)
        assert _page_labels(document) == ["PAGE-0", "PAGE-1", "PAGE-2", "PAGE-3"]
    finally:
        document.close()


def test_qt_thumbnail_destination_is_translated_to_final_index():
    from page_state_core import qt_rows_moved_final_index

    # Move row 1 downward so Qt inserts it before original row 3: final row 2.
    assert qt_rows_moved_final_index(4, 1, 1, 3) == 2
    # Move row 3 upward before row 1: final row 1.
    assert qt_rows_moved_final_index(4, 3, 3, 1) == 1
    # Moving to the append position places the item last.
    assert qt_rows_moved_final_index(4, 0, 0, 4) == 3
