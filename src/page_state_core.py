"""Central remapping and snapshot support for page-indexed application state."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

import fitz


_PAGE_DICT_ATTRS = ("annotations", "markup_strokes", "pending_redactions")
_PAGE_RECORD_ATTRS = ("bookmarks", "search_results")
_PAGE_SCALAR_ATTRS = (
    "current_selection_page",
    "_freehand_page",
    "_form_drag_page",
)


def insert_page_mapping(page_count_before: int, inserted_at: int) -> dict[int, int]:
    if not 0 <= inserted_at <= page_count_before:
        raise ValueError("Inserted page index is outside the document.")
    return {
        old: old if old < inserted_at else old + 1
        for old in range(page_count_before)
    }


def delete_page_mapping(page_count_before: int, deleted_at: int) -> dict[int, int | None]:
    if not 0 <= deleted_at < page_count_before:
        raise ValueError("Deleted page index is outside the document.")
    return {
        old: (None if old == deleted_at else old if old < deleted_at else old - 1)
        for old in range(page_count_before)
    }



def native_move_target(page_count: int, source: int, final_index: int) -> int:
    """Translate a desired final page index to PyMuPDF ``move_page`` semantics.

    PyMuPDF interprets the destination as an insertion point in the pre-removal
    page sequence.  Moving downward therefore needs an offset of one; moving to
    the last final position uses ``-1``.
    """
    if page_count < 1:
        raise ValueError("Cannot move a page in an empty document.")
    if not 0 <= source < page_count or not 0 <= final_index < page_count:
        raise ValueError("Moved page index is outside the document.")
    if source == final_index:
        return source
    if source < final_index:
        return -1 if final_index == page_count - 1 else final_index + 1
    return final_index


def move_page_to_final_index(
    document: fitz.Document, source: int, final_index: int
) -> None:
    """Move a real PDF page to ``final_index`` using final-index semantics."""
    if document is None or document.is_closed:
        raise ValueError("A live PDF document is required.")
    target = native_move_target(document.page_count, source, final_index)
    if source != final_index:
        document.move_page(source, target)


def qt_rows_moved_final_index(
    page_count: int, start: int, end: int, destination_child: int
) -> int:
    """Translate Qt ``rowsMoved`` insertion semantics to a final page index.

    Qt reports the row before which the moved block is inserted in the original
    model.  When moving downward, removing the source block shifts that index
    upward by the block size. PDF Studio currently permits one-page thumbnail
    moves, but the calculation supports any contiguous block.
    """
    if page_count < 1:
        raise ValueError("Cannot reorder an empty document.")
    if not (0 <= start <= end < page_count):
        raise ValueError("Moved thumbnail range is outside the document.")
    if not 0 <= destination_child <= page_count:
        raise ValueError("Thumbnail destination is outside the document.")
    block_size = end - start + 1
    final_index = (
        destination_child - block_size
        if destination_child > end
        else destination_child
    )
    max_final = page_count - block_size
    if not 0 <= final_index <= max_final:
        raise ValueError("Thumbnail destination does not produce a valid final index.")
    return final_index

def move_page_mapping(page_count: int, source: int, destination: int) -> dict[int, int]:
    if not 0 <= source < page_count or not 0 <= destination < page_count:
        raise ValueError("Moved page index is outside the document.")
    mapping = {index: index for index in range(page_count)}
    if source < destination:
        mapping[source] = destination
        for index in range(source + 1, destination + 1):
            mapping[index] = index - 1
    elif destination < source:
        mapping[source] = destination
        for index in range(destination, source):
            mapping[index] = index + 1
    return mapping


def capture_page_bound_state(owner: Any) -> dict[str, Any]:
    """Capture all known application state whose meaning depends on page index."""
    snapshot: dict[str, Any] = {}
    for attr in _PAGE_DICT_ATTRS + _PAGE_RECORD_ATTRS + _PAGE_SCALAR_ATTRS:
        snapshot[attr] = deepcopy(getattr(owner, attr, None))
    snapshot["current_page"] = int(getattr(owner, "current_page", 0))
    snapshot["current_search_index"] = int(
        getattr(owner, "current_search_index", -1)
    )
    selected_form_ref = getattr(owner, "_selected_form_ref", None)
    snapshot["_selected_form_ref"] = deepcopy(selected_form_ref)
    return snapshot


def _map_page(mapping: Mapping[int, int | None], page: Any) -> int | None:
    try:
        page_number = int(page)
    except (TypeError, ValueError):
        return None
    return mapping.get(page_number)


def remap_page_bound_state(owner: Any, mapping: Mapping[int, int | None]) -> None:
    """Apply one authoritative page-index mapping to every known sidecar store."""
    for attr in _PAGE_DICT_ATTRS:
        original = getattr(owner, attr, {}) or {}
        remapped = {}
        for page, value in original.items():
            new_page = _map_page(mapping, page)
            if new_page is not None:
                remapped[new_page] = value
        setattr(owner, attr, remapped)

    for attr in _PAGE_RECORD_ATTRS:
        original = getattr(owner, attr, []) or []
        remapped_records = []
        for record in original:
            if not isinstance(record, dict) or "page" not in record:
                continue
            new_page = _map_page(mapping, record["page"])
            if new_page is None:
                continue
            updated = dict(record)
            updated["page"] = new_page
            remapped_records.append(updated)
        setattr(owner, attr, remapped_records)

    for attr in _PAGE_SCALAR_ATTRS:
        value = getattr(owner, attr, -1)
        if value is None or int(value) < 0:
            continue
        new_page = _map_page(mapping, value)
        setattr(owner, attr, -1 if new_page is None else new_page)

    selected_form_ref = getattr(owner, "_selected_form_ref", None)
    if isinstance(selected_form_ref, tuple) and len(selected_form_ref) >= 2:
        new_page = _map_page(mapping, selected_form_ref[0])
        owner._selected_form_ref = (
            None if new_page is None else (new_page, *selected_form_ref[1:])
        )

    # Search-result selection becomes unreliable whenever rows are removed.
    results = getattr(owner, "search_results", []) or []
    current_search = int(getattr(owner, "current_search_index", -1))
    owner.current_search_index = (
        min(current_search, len(results) - 1) if results else -1
    )

    # Detection suggestions and form caches reference live page objects / xrefs.
    # They are rebuilt or explicitly discarded after every page operation.
    if hasattr(owner, "_form_suggestions"):
        owner._form_suggestions = []
    if hasattr(owner, "_selected_form_suggestion_id"):
        owner._selected_form_suggestion_id = None
    if hasattr(owner, "_form_detection_context"):
        owner._form_detection_context = None


def restore_page_bound_state(owner: Any, snapshot: Mapping[str, Any]) -> None:
    """Restore a complete page-bound snapshot during page-operation undo/redo."""
    for attr in _PAGE_DICT_ATTRS + _PAGE_RECORD_ATTRS + _PAGE_SCALAR_ATTRS:
        if attr in snapshot:
            setattr(owner, attr, deepcopy(snapshot[attr]))
    if "current_page" in snapshot:
        owner.current_page = int(snapshot["current_page"])
    if "current_search_index" in snapshot:
        owner.current_search_index = int(snapshot["current_search_index"])
    if "_selected_form_ref" in snapshot:
        owner._selected_form_ref = deepcopy(snapshot["_selected_form_ref"])
