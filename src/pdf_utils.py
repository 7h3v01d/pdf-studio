"""
pdf_utils.py
------------
Utility functions for page operations, search, annotation, and markup.
All functions receive the PDFReader instance as first argument.
"""
import json
import os
import fitz
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import Qt


# ─────────────────────────────────────────────────────────────────────────────
# Annotation I/O
# ─────────────────────────────────────────────────────────────────────────────

def load_annotations(pdf_document, pdf_file_path):
    annotations = {}
    if pdf_document:
        try:
            for page_num in range(pdf_document.page_count):
                page = pdf_document.load_page(page_num)
                for annot in page.annots():
                    if annot.type[0] == 8:
                        pos = annot.rect.top_left
                        text = annot.info["content"]
                        annotations.setdefault(page_num, []).append(
                            (pos.x, pos.y, text))
        except Exception as e:
            import logging
            logging.warning("load_annotations: failed reading embedded annotations: %s", e)

    annotation_file = pdf_file_path + ".annotations.json"
    if os.path.exists(annotation_file):
        try:
            with open(annotation_file, "r") as f:
                json_annotations = {int(k): v for k, v in json.load(f).items()}
            for page_num, items in json_annotations.items():
                existing = annotations.get(page_num, [])
                for x, y, text in items:
                    if not any(abs(ex - x) < 1 and abs(ey - y) < 1 and et == text
                                for ex, ey, et in existing):
                        existing.append((x, y, text))
                annotations[page_num] = existing
        except (OSError, ValueError, KeyError) as e:
            import logging
            logging.warning("load_annotations: could not read '%s': %s", annotation_file, e)
    return annotations


def save_annotations(pdf_reader):
    if pdf_reader.pdf_file_path:
        annotation_file = pdf_reader.pdf_file_path + ".annotations.json"
        try:
            with open(annotation_file, "w") as f:
                json.dump(pdf_reader.annotations, f)
            pdf_reader.status_bar.showMessage("Annotations saved")
        except Exception as e:
            pdf_reader.status_bar.showMessage(f"Error saving annotations: {e}")


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
            with open(bm_file, "w") as f:
                json.dump(pdf_reader.bookmarks, f)
        except OSError as e:
            pdf_reader.status_bar.showMessage(f"Warning: could not save bookmarks: {e}")


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
    pdf_reader.update_view()
    pdf_reader.pages = [
        pdf_reader.pdf_document.load_page(i)
        for i in range(pdf_reader.total_pages)]
    pdf_reader.form_fields = {
        i: list(p.widgets()) for i, p in enumerate(pdf_reader.pages)}
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
        inserted_at = pdf_reader.current_page + 1
        pdf_reader.pdf_document.insert_page(inserted_at)
        pdf_reader.total_pages += 1
        new_ann = {}
        for pn, v in pdf_reader.annotations.items():
            if pn <= pdf_reader.current_page:
                new_ann[pn] = v
            else:
                new_ann[pn + 1] = v
        pdf_reader.annotations = new_ann
        new_sr = []
        for r in pdf_reader.search_results:
            if r["page"] <= pdf_reader.current_page:
                new_sr.append(r)
            else:
                new_sr.append({"page": r["page"] + 1, "rects": r["rects"]})
        pdf_reader.search_results = new_sr
        from undo_stack import Command
        pdf_reader._undo_stack.push(Command(
            kind="page_add",
            undo_data={"page": inserted_at},
            redo_data={"page": inserted_at},
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

        # Snapshot the page as a single-page PDF bytes so undo can restore it
        tmp = _fitz.open()
        tmp.insert_pdf(pdf_reader.pdf_document, from_page=cp, to_page=cp)
        page_bytes = tmp.tobytes()
        tmp.close()

        pdf_reader.pdf_document.delete_page(cp)
        pdf_reader.total_pages -= 1
        if pdf_reader.current_page >= pdf_reader.total_pages:
            pdf_reader.current_page = pdf_reader.total_pages - 1
        new_ann = {
            (pn if pn < cp else pn - 1): v
            for pn, v in pdf_reader.annotations.items()
            if pn != cp}
        pdf_reader.annotations = new_ann
        new_sr = [
            (r if r["page"] < cp else {"page": r["page"] - 1, "rects": r["rects"]})
            for r in pdf_reader.search_results
            if r["page"] != cp]
        pdf_reader.search_results = new_sr
        from undo_stack import Command
        pdf_reader._undo_stack.push(Command(
            kind="page_remove",
            undo_data={"page": cp, "page_bytes": page_bytes},
            redo_data={"page": cp},
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
        to  = frm - 1
        pdf_reader.pdf_document.move_page(frm, to)
        pdf_reader.current_page = to
        from undo_stack import Command
        pdf_reader._undo_stack.push(Command(
            kind="page_move",
            undo_data={"from": to, "to": frm},
            redo_data={"from": frm, "to": to},
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
        to  = frm + 1
        pdf_reader.pdf_document.move_page(frm, to)
        pdf_reader.current_page = to
        from undo_stack import Command
        pdf_reader._undo_stack.push(Command(
            kind="page_move",
            undo_data={"from": to, "to": frm},
            redo_data={"from": frm, "to": to},
        ))
        _rebuild_after_page_op(pdf_reader,
                               f"Page moved to position {pdf_reader.current_page + 1}")
    except Exception as e:
        pdf_reader.status_bar.showMessage(f"Error moving page: {e}")


def handle_thumbnail_reorder(pdf_reader, parent, start, end, destination, row):
    if not pdf_reader.pdf_document:
        return
    try:
        pdf_reader.pdf_document.move_page(start, row)
        if pdf_reader.current_page == start:
            pdf_reader.current_page = row
        elif start < pdf_reader.current_page <= row:
            pdf_reader.current_page -= 1
        elif row <= pdf_reader.current_page < start:
            pdf_reader.current_page += 1
        new_ann = {}
        for pn in range(pdf_reader.total_pages):
            if pn == start:
                new_ann[row] = pdf_reader.annotations.get(pn, [])
            elif start < pn <= row:
                new_ann[pn - 1] = pdf_reader.annotations.get(pn, [])
            elif row < pn <= start:
                new_ann[pn + 1] = pdf_reader.annotations.get(pn, [])
            else:
                new_ann[pn] = pdf_reader.annotations.get(pn, [])
        pdf_reader.annotations = new_ann
        new_sr = []
        for r in pdf_reader.search_results:
            pn = r["page"]
            if pn == start:
                new_sr.append({"page": row, "rects": r["rects"]})
            elif start < pn <= row:
                new_sr.append({"page": pn - 1, "rects": r["rects"]})
            elif row < pn <= start:
                new_sr.append({"page": pn + 1, "rects": r["rects"]})
            else:
                new_sr.append(r)
        pdf_reader.search_results = new_sr
        from undo_stack import Command
        pdf_reader._undo_stack.push(Command(
            kind="page_move",
            undo_data={"from": row, "to": start},
            redo_data={"from": start, "to": row},
        ))
        _rebuild_after_page_op(pdf_reader,
                               f"Page moved from {start + 1} to {row + 1}")
    except Exception as e:
        pdf_reader.status_bar.showMessage(f"Error reordering page: {e}")
