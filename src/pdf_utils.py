"""
pdf_utils.py
------------
Utility functions for page operations, search, annotation, and markup.
All functions receive the PDFReader instance as first argument.
"""
import json
import os
import fitz
from annotation_integrity_core import atomic_write_json, filter_legacy_sidecar_notes
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import Qt

from page_state_core import (
    capture_page_bound_state,
    delete_page_mapping,
    insert_page_mapping,
    move_page_mapping,
    move_page_to_final_index,
    qt_rows_moved_final_index,
    remap_page_bound_state,
)

# ─────────────────────────────────────────────────────────────────────────────
# Annotation I/O
# ─────────────────────────────────────────────────────────────────────────────

def load_annotations(pdf_document, pdf_file_path):
    """Load only deferred legacy notes not already native in the PDF.

    Native annotations are displayed directly from the PDF by the annotations
    panel.  Keeping them out of this sidecar collection prevents duplicate
    rendering and duplicate panel rows after save/reopen.
    """
    annotation_file = pdf_file_path + ".annotations.json"
    if not os.path.exists(annotation_file):
        return {}
    try:
        with open(annotation_file, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        return filter_legacy_sidecar_notes(raw, pdf_document)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        import logging
        logging.warning(
            "load_annotations: could not read '%s': %s", annotation_file, exc
        )
        return {}


def save_annotations(pdf_reader):
    """Atomically persist deferred sticky notes only.

    Successfully baked notes are retired from this collection, which deletes
    the now-empty sidecar instead of maintaining a second source of truth.
    """
    if not pdf_reader.pdf_file_path:
        return
    annotation_file = pdf_reader.pdf_file_path + ".annotations.json"
    try:
        atomic_write_json(annotation_file, pdf_reader.annotations)
    except Exception as exc:
        pdf_reader.status_bar.showMessage(f"Error saving annotations: {exc}")
        raise


# ─────────────────────────────────────────────────────────────────────────────
# Bookmarks (user-created, not TOC)
# ─────────────────────────────────────────────────────────────────────────────

def load_bookmarks(pdf_file_path):
    bm_file = pdf_file_path + ".bookmarks.json"
    if os.path.exists(bm_file):
        try:
            with open(bm_file) as f:
                return json.load(f)      # list of {page, label}
        except (OSError, ValueError) as e:
            import logging
            logging.warning("load_bookmarks: could not read '%s': %s", bm_file, e)
    return []


def save_bookmarks(pdf_reader):
    if pdf_reader.pdf_file_path:
        bm_file = pdf_reader.pdf_file_path + ".bookmarks.json"
        try:
            atomic_write_json(bm_file, pdf_reader.bookmarks)
        except OSError as e:
            pdf_reader.status_bar.showMessage(f"Warning: could not save bookmarks: {e}")
            raise


# ─────────────────────────────────────────────────────────────────────────────
# Search
# ─────────────────────────────────────────────────────────────────────────────

def _apply_search_navigation(pdf_reader):
    """Shared navigation after search index change."""
    pdf_reader.annotation_mode = False
    pdf_reader.toggle_annotation_mode(force_off=True)
    pdf_reader.update_view()
    is_single = (pdf_reader.view_mode == 0)
    pdf_reader.prev_button.setEnabled(pdf_reader.current_page > 0 and is_single)
    pdf_reader.next_button.setEnabled(
        pdf_reader.current_page < pdf_reader.total_pages - 1 and is_single)
    pdf_reader.move_up_button.setEnabled(pdf_reader.current_page > 0)
    pdf_reader.move_down_button.setEnabled(
        pdf_reader.current_page < pdf_reader.total_pages - 1)
    pdf_reader.thumbnail_list.setCurrentRow(pdf_reader.current_page)
    if pdf_reader.view_mode == 1:
        pdf_reader.scroll_to_page(pdf_reader.current_page)


def search_text(pdf_reader):
    search_term = pdf_reader.search_input.text().strip()
    if not search_term:
        pdf_reader.status_bar.showMessage("Enter a search term")
        return
    pdf_reader.search_results = []
    pdf_reader.current_search_index = -1
    try:
        for page_num in range(pdf_reader.total_pages):
            page = pdf_reader.pdf_document.load_page(page_num)
            rects = page.search_for(search_term)
            if rects:
                pdf_reader.search_results.append({"page": page_num, "rects": rects})
        if pdf_reader.search_results:
            pdf_reader.current_search_index = 0
            pdf_reader.current_page = pdf_reader.search_results[0]["page"]
            _apply_search_navigation(pdf_reader)
            pdf_reader.next_search_button.setEnabled(len(pdf_reader.search_results) > 1)
            pdf_reader.prev_search_button.setEnabled(False)
            pdf_reader.status_bar.showMessage(
                f"Found {len(pdf_reader.search_results)} matches")
        else:
            pdf_reader.next_search_button.setEnabled(False)
            pdf_reader.prev_search_button.setEnabled(False)
            pdf_reader.status_bar.showMessage("No matches found")
    except Exception as e:
        pdf_reader.status_bar.showMessage(f"Search error: {e}")


def next_search_result(pdf_reader):
    if pdf_reader.search_results and \
            pdf_reader.current_search_index < len(pdf_reader.search_results) - 1:
        pdf_reader.current_search_index += 1
        pdf_reader.current_page = \
            pdf_reader.search_results[pdf_reader.current_search_index]["page"]
        _apply_search_navigation(pdf_reader)
        pdf_reader.next_search_button.setEnabled(
            pdf_reader.current_search_index < len(pdf_reader.search_results) - 1)
        pdf_reader.prev_search_button.setEnabled(
            pdf_reader.current_search_index > 0)


def prev_search_result(pdf_reader):
    if pdf_reader.search_results and pdf_reader.current_search_index > 0:
        pdf_reader.current_search_index -= 1
        pdf_reader.current_page = \
            pdf_reader.search_results[pdf_reader.current_search_index]["page"]
        _apply_search_navigation(pdf_reader)
        pdf_reader.next_search_button.setEnabled(
            pdf_reader.current_search_index < len(pdf_reader.search_results) - 1)
        pdf_reader.prev_search_button.setEnabled(
            pdf_reader.current_search_index > 0)


# ─────────────────────────────────────────────────────────────────────────────
# Page operations  (add / remove / move / reorder)
# ─────────────────────────────────────────────────────────────────────────────

def _rebuild_after_page_op(pdf_reader, status_msg):
    pdf_reader.load_pages()
    pdf_reader._reload_form_cache()
    pdf_reader.update_view()
    pdf_reader.refresh_forms_panel()
    pdf_reader.refresh_annotations_panel()
    pdf_reader.refresh_bookmark_list()
    pdf_reader.load_thumbnails()
    pdf_reader.load_toc()
    pdf_reader.page_label.setText(f" / {pdf_reader.total_pages}")
    is_single = (pdf_reader.view_mode == 0)
    pdf_reader.prev_button.setEnabled(pdf_reader.current_page > 0 and is_single)
    pdf_reader.next_button.setEnabled(
        pdf_reader.current_page < pdf_reader.total_pages - 1 and is_single)
    pdf_reader.move_up_button.setEnabled(pdf_reader.current_page > 0)
    pdf_reader.move_down_button.setEnabled(
        pdf_reader.current_page < pdf_reader.total_pages - 1)
    pdf_reader.thumbnail_list.setCurrentRow(pdf_reader.current_page)
    pdf_reader.status_bar.showMessage(status_msg)


def add_page(pdf_reader):
    if not pdf_reader.pdf_document:
        pdf_reader.status_bar.showMessage("No PDF loaded")
        return
    try:
        page_count_before = pdf_reader.total_pages
        inserted_at = pdf_reader.current_page + 1
        before_state = capture_page_bound_state(pdf_reader)
        pdf_reader.pdf_document.insert_page(inserted_at)
        pdf_reader.total_pages += 1
        remap_page_bound_state(
            pdf_reader,
            insert_page_mapping(page_count_before, inserted_at),
        )
        after_state = capture_page_bound_state(pdf_reader)
        from undo_stack import Command
        pdf_reader._undo_stack.push(Command(
            kind="page_add",
            undo_data={"page": inserted_at, "state": before_state},
            redo_data={"page": inserted_at, "state": after_state},
        ))
        _rebuild_after_page_op(pdf_reader, "Blank page added")
    except Exception as e:
        pdf_reader.status_bar.showMessage(f"Error adding page: {e}")


def remove_page(pdf_reader):
    if not pdf_reader.pdf_document or pdf_reader.total_pages <= 1:
        pdf_reader.status_bar.showMessage("Cannot remove: one page minimum")
        return
    try:
        import fitz as _fitz
        cp = pdf_reader.current_page
        page_count_before = pdf_reader.total_pages
        before_state = capture_page_bound_state(pdf_reader)

        tmp = _fitz.open()
        tmp.insert_pdf(
            pdf_reader.pdf_document,
            from_page=cp,
            to_page=cp,
            annots=True,
            widgets=True,
        )
        page_bytes = tmp.tobytes(garbage=3, deflate=True)
        tmp.close()

        pdf_reader.pdf_document.delete_page(cp)
        pdf_reader.total_pages -= 1
        remap_page_bound_state(
            pdf_reader,
            delete_page_mapping(page_count_before, cp),
        )
        if pdf_reader.current_page >= pdf_reader.total_pages:
            pdf_reader.current_page = pdf_reader.total_pages - 1
        after_state = capture_page_bound_state(pdf_reader)
        from undo_stack import Command
        pdf_reader._undo_stack.push(Command(
            kind="page_remove",
            undo_data={
                "page": cp,
                "page_bytes": page_bytes,
                "state": before_state,
            },
            redo_data={"page": cp, "state": after_state},
        ))
        _rebuild_after_page_op(pdf_reader, "Page removed")
    except Exception as e:
        pdf_reader.status_bar.showMessage(f"Error removing page: {e}")


def move_page_up(pdf_reader):
    if not pdf_reader.pdf_document or pdf_reader.current_page <= 0:
        pdf_reader.status_bar.showMessage("Cannot move page up")
        return
    try:
        frm = pdf_reader.current_page
        to = frm - 1
        before_state = capture_page_bound_state(pdf_reader)
        move_page_to_final_index(pdf_reader.pdf_document, frm, to)
        remap_page_bound_state(
            pdf_reader,
            move_page_mapping(pdf_reader.total_pages, frm, to),
        )
        pdf_reader.current_page = to
        after_state = capture_page_bound_state(pdf_reader)
        from undo_stack import Command
        pdf_reader._undo_stack.push(Command(
            kind="page_move",
            undo_data={"from": to, "to": frm, "state": before_state},
            redo_data={"from": frm, "to": to, "state": after_state},
        ))
        _rebuild_after_page_op(pdf_reader, "Page moved up")
    except Exception as e:
        pdf_reader.status_bar.showMessage(f"Error moving page: {e}")


def move_page_down(pdf_reader):
    if not pdf_reader.pdf_document or \
            pdf_reader.current_page >= pdf_reader.total_pages - 1:
        pdf_reader.status_bar.showMessage("Cannot move page down")
        return
    try:
        frm = pdf_reader.current_page
        to = frm + 1
        before_state = capture_page_bound_state(pdf_reader)
        move_page_to_final_index(pdf_reader.pdf_document, frm, to)
        remap_page_bound_state(
            pdf_reader,
            move_page_mapping(pdf_reader.total_pages, frm, to),
        )
        pdf_reader.current_page = to
        after_state = capture_page_bound_state(pdf_reader)
        from undo_stack import Command
        pdf_reader._undo_stack.push(Command(
            kind="page_move",
            undo_data={"from": to, "to": frm, "state": before_state},
            redo_data={"from": frm, "to": to, "state": after_state},
        ))
        _rebuild_after_page_op(
            pdf_reader,
            f"Page moved to position {pdf_reader.current_page + 1}",
        )
    except Exception as e:
        pdf_reader.status_bar.showMessage(f"Error moving page: {e}")


def handle_thumbnail_reorder(pdf_reader, parent, start, end, destination, row):
    if not pdf_reader.pdf_document:
        return
    try:
        final_index = qt_rows_moved_final_index(
            pdf_reader.total_pages, start, end, row
        )
        if start == final_index:
            return
        before_state = capture_page_bound_state(pdf_reader)
        move_page_to_final_index(pdf_reader.pdf_document, start, final_index)
        mapping = move_page_mapping(
            pdf_reader.total_pages, start, final_index
        )
        remap_page_bound_state(pdf_reader, mapping)
        if pdf_reader.current_page == start:
            pdf_reader.current_page = final_index
        else:
            mapped_current = mapping.get(pdf_reader.current_page)
            if mapped_current is not None:
                pdf_reader.current_page = mapped_current
        after_state = capture_page_bound_state(pdf_reader)
        from undo_stack import Command
        pdf_reader._undo_stack.push(Command(
            kind="page_move",
            undo_data={
                "from": final_index, "to": start, "state": before_state
            },
            redo_data={
                "from": start, "to": final_index, "state": after_state
            },
        ))
        _rebuild_after_page_op(
            pdf_reader,
            f"Page moved from {start + 1} to {final_index + 1}",
        )
    except Exception as e:
        pdf_reader.status_bar.showMessage(f"Error reordering page: {e}")
