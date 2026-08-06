"""
pdf_reader_app.py
-----------------
Core application logic.  Inherits all UI from PDFReaderUI.
"""
import sys
import os
import json
import logging
from dataclasses import asdict
from pathlib import Path
import fitz  # PyMuPDF
from PyQt6.QtWidgets import (
    QInputDialog, QMessageBox, QLabel, QMenu, QFileDialog,
    QApplication, QListWidgetItem, QLineEdit, QCheckBox, QComboBox,
    QRadioButton, QTextEdit, QColorDialog, QDialog, QVBoxLayout,
    QHBoxLayout, QPushButton, QSizePolicy, QListWidget, QButtonGroup,
    QAbstractItemView, QDateEdit, QProgressDialog)
from PyQt6.QtGui import (
    QPixmap, QImage, QPainter, QPen, QColor, QAction, QIcon,
    QCursor, QFont)
from PyQt6.QtCore import Qt, QRectF, QPoint, QSize, QSettings, QDate, QTimer
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog

from pdf_reader_ui import PDFReaderUI
from app_metadata import APP_NAME
from password_dialog import PasswordPromptDialog, PasswordProtectDialog
from undo_stack import UndoStack, Command
from form_designer_core import (
    DEFAULT_CHECKBOX_SIZE,
    DEFAULT_DATE_SIZE,
    DEFAULT_DROPDOWN_SIZE,
    DEFAULT_INITIALS_SIZE,
    DEFAULT_RADIO_GROUP_SIZE,
    DEFAULT_SIGNATURE_SIZE,
    DEFAULT_TEXT_SIZE,
    KIND_DATE,
    KIND_INITIALS,
    MIN_CHECKBOX_SIZE,
    MIN_CHOICE_SIZE,
    MIN_SIGNATURE_SIZE,
    MIN_TEXT_SIZE,
    add_checkbox_field,
    add_date_field,
    add_dropdown_field,
    add_radio_group,
    add_signature_field,
    add_text_field,
    delete_widget as delete_form_widget_core,
    move_or_resize_widget,
    normalise_rect,
    radio_option_label,
    update_widget_properties,
    unique_field_name,
    widget_custom_kind,
)
from form_detection_core import (
    create_fields_from_suggestions,
    words_from_native,
    vector_graphics_from_page,
)
from form_detection_worker import FormDetectionWorker
from form_detection_review_dialog import FormDetectionReviewDialog
from scan_text_edit_core import (
    MODE_OVERLAY as SCAN_MODE_OVERLAY,
    MODE_REDACT as SCAN_MODE_REDACT,
    ScanTextReplacement,
    apply_scan_text_replacement,
    choose_drag_endpoint,
    drag_rectangle_is_large_enough,
    inverted_fitz_matrix,
    remove_overlay_replacement,
    sample_background_rgb,
)
from scan_text_edit_dialog import ScanTextEditDialog
from scan_text_edit_worker import ScanTextOCRWorker
from tesseract_setup import configure_tesseract
from document_integrity_core import (
    apply_redactions_transactionally,
    clone_pdf_document,
    flatten_form_atomic,
    insert_signature_image_once,
    new_document_session_id,
    open_pdf_snapshot,
    save_pdf_atomic,
    sibling_staged_path,
    snapshot_pdf_bytes,
    validate_pdf_file,
)
from annotation_integrity_core import (
    atomic_write_json,
    pending_markup_only,
    retire_baked_sidecar_state,
)
from save_bundle_core import (
    StagedOperation,
    cleanup_staged_operations,
    commit_staged_operations,
    stage_json_payload,
)
from form_field_dialog import FormFieldPropertiesDialog
from page_state_core import move_page_to_final_index, restore_page_bound_state
from pdf_utils import (
    load_annotations, save_annotations, load_bookmarks, save_bookmarks,
    search_text, next_search_result, prev_search_result,
    add_page, remove_page, move_page_up, move_page_down,
    handle_thumbnail_reorder)


# ── Active tool constants ────────────────────────────────────────────────────
TOOL_NONE          = "none"
TOOL_ANNOTATE      = "annotate"
TOOL_HIGHLIGHT     = "highlight"
TOOL_UNDERLINE     = "underline"
TOOL_STRIKETHROUGH = "strikethrough"
TOOL_FREEHAND      = "freehand"
TOOL_ERASER        = "eraser"
TOOL_SIGNATURE     = "signature"
TOOL_REDACT        = "redact"
TOOL_SCAN_TEXT      = "scan_text"

FORM_TOOL_SELECT    = "select"
FORM_TOOL_TEXT      = "text"
FORM_TOOL_CHECKBOX  = "checkbox"
FORM_TOOL_DROPDOWN  = "dropdown"
FORM_TOOL_DATE      = "date"
FORM_TOOL_RADIO     = "radio"
FORM_TOOL_SIGNATURE = "signature"
FORM_TOOL_INITIALS  = "initials"

FORM_CREATE_TOOLS = {
    FORM_TOOL_TEXT, FORM_TOOL_CHECKBOX, FORM_TOOL_DROPDOWN, FORM_TOOL_DATE,
    FORM_TOOL_RADIO, FORM_TOOL_SIGNATURE, FORM_TOOL_INITIALS,
}

# Default on-page signature width in PDF points (aspect ratio preserved).
DEFAULT_SIG_WIDTH_PT = 200


class PDFReader(PDFReaderUI):
    def __init__(self):
        super().__init__()

        # ── App icon (title bar, taskbar, alt-tab) ───────────────────────
        import os as _os
        _icon_path = _os.path.join(
            _os.path.dirname(_os.path.abspath(__file__)), "icon.ico")
        if _os.path.exists(_icon_path):
            from PyQt6.QtGui import QIcon as _QIcon
            _app_icon = _QIcon(_icon_path)
            self.setWindowIcon(_app_icon)
            # Also set on the QApplication so taskbar + alt-tab use it
            from PyQt6.QtWidgets import QApplication as _QApp
            _QApp.instance().setWindowIcon(_app_icon)

        # ── Document state ───────────────────────────────────────────────
        self.pdf_document    = None
        self.pdf_file_path   = ""
        self._imported_source_path = None
        self._imported_temp_pdf_path = None
        self.current_page    = 0
        self.total_pages     = 0
        self.zoom_level      = 1.0
        self.rotation        = 0
        self.view_mode       = self.SINGLE_PAGE
        self.dark_mode       = False

        # ── Annotation / markup state ────────────────────────────────────
        self.annotations          = {}    # {page: [(x,y,text)]}
        self.markup_strokes       = {}    # {page: [{type, rects/points, color}]}
        self.active_tool          = TOOL_NONE
        self.annotation_mode      = False  # kept for back-compat
        self.markup_color         = QColor("#FFFF00")  # default yellow

        # Pending redaction boxes are valid only for one loaded-document session.
        self.pending_redactions = {}
        self._document_session_id = None
        self._pending_redaction_session_id = None

        # Freehand drawing buffers
        self._freehand_drawing    = False
        self._freehand_points     = []
        self._freehand_page       = -1

        # Signature placement
        self._pending_signature   = None   # QPixmap waiting to be placed
        self._sig_page_widget     = None
        self._sig_pos             = None

        # ── Search state ─────────────────────────────────────────────────
        self.search_results        = []
        self.current_search_index  = -1

        # ── Form field state ─────────────────────────────────────────────
        self.form_fields  = {}   # {page: [fitz.Widget]}
        # {page: [(Qt widget, fitz.Widget)]}; pairing avoids type gaps
        self.field_widgets = {}
        self._radio_groups = {}  # {(page, field_name): QButtonGroup}
        self._form_highlighting = True
        self._form_design_mode = False
        self._form_design_tool = FORM_TOOL_SELECT
        self._selected_form_ref = None  # (page_number, widget xref)
        self._form_drag_action = None   # create / move / resize
        self._form_drag_page = -1
        self._form_drag_start_pdf = None
        self._form_drag_original_rect = None
        self._form_preview_rect = None
        self._form_suggestions = []
        self._selected_form_suggestion_id = None
        self._form_detection_worker = None
        self._form_detection_context = None
        self._form_detection_statistics = {}
        self._form_detection_dialog = None

        # OCR-assisted scanned-text replacement. The context owns a copied
        # region image so it remains valid while the worker runs.
        self._scan_text_worker = None
        self._scan_text_context = None
        self._scan_text_progress = None
        self._scan_text_mouse_grab_widget = None
        self._requires_full_rewrite = False

        self.pages        = []   # cached fitz page objects

        # ── Text selection state ─────────────────────────────────────────
        self.is_selecting_text       = False
        self.selection_start_point   = None
        self.selection_end_point     = None
        self.current_selection_page  = -1
        self.context_menu_page_widget= None

        # ── Page widgets ─────────────────────────────────────────────────
        self.page_widgets = []

        # ── Bookmarks ────────────────────────────────────────────────────
        self.bookmarks = []   # list of {page, label}

        # ── Undo / Redo ───────────────────────────────────────────────────
        self._undo_stack = UndoStack()

        # Wrap push so any undoable change marks the doc as modified
        _orig_push = self._undo_stack.push
        def _push_and_mark(cmd):
            _orig_push(cmd)
            self._mark_modified()
        self._undo_stack.push = _push_and_mark

        # ── Form dirty tracking ───────────────────────────────────────────
        self._form_dirty = False

        # ── Recent files ─────────────────────────────────────────────────
        self.settings    = QSettings("LeonPriest", "PDFStudio")
        self.recent_files = self._load_recent_files()
        self._build_recent_menu()

        # ── Restore window geometry ───────────────────────────────────────
        geom = self.settings.value("window_geometry")
        if geom:
            self.restoreGeometry(geom)
        state = self.settings.value("window_state")
        if state:
            self.restoreState(state)

        # ── Restore UI preferences ────────────────────────────────────────
        saved_zoom = self.settings.value("prefs/zoom_level", 1.0, type=float)
        self.zoom_level = saved_zoom
        zoom_pct = f"{int(saved_zoom * 100)}%"
        if zoom_pct in [self.zoom_combo.itemText(i)
                        for i in range(self.zoom_combo.count())]:
            self.zoom_combo.blockSignals(True)
            self.zoom_combo.setCurrentText(zoom_pct)
            self.zoom_combo.blockSignals(False)

        if self.settings.value("prefs/view_mode", 0, type=int) == self.CONTINUOUS:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self.toggle_view_mode)

        if self.settings.value("prefs/dark_mode", False, type=bool):
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self.toggle_dark_mode)

        saved_color = self.settings.value("prefs/markup_color", "#FFFF00", type=str)
        self.markup_color = QColor(saved_color)
        self.markup_color_button.setStyleSheet(
            f"background:{saved_color};"
            f"color:{'white' if self.markup_color.lightness() < 128 else 'black'};"
        )

        # ── Thumbnail drag reorder ────────────────────────────────────────
        # Annotations panel signals
        self.annot_panel.jump_to_page.connect(self._annot_panel_jump)
        self.annot_panel.delete_annotation.connect(self._annot_panel_delete)

        self.thumbnail_list.model().rowsMoved.connect(
            lambda p, s, e, d, r: handle_thumbnail_reorder(self, p, s, e, d, r))

        # ── Thumbnail double-click ────────────────────────────────────────
        self.thumbnail_list.itemDoubleClicked.connect(self._thumbnail_double_clicked)

        self.update_status_bar()

    def _reset_document_session_state(self):
        """Clear every application-side value that belongs to one PDF session."""
        self.pending_redactions = {}
        self._pending_redaction_session_id = None
        self._imported_source_path = None
        self._imported_temp_pdf_path = None
        self.annotations = {}
        self.markup_strokes = {}
        self.bookmarks = []
        self.search_results = []
        self.current_search_index = -1
        self.selection_start_point = None
        self.selection_end_point = None
        self.current_selection_page = -1
        self.is_selecting_text = False
        self._freehand_drawing = False
        self._freehand_points = []
        self._freehand_page = -1
        self._pending_signature = None
        self._pending_stamp = None
        self.active_tool = TOOL_NONE
        self.annotation_mode = False
        self.form_fields = {}
        self.field_widgets = {}
        self._radio_groups = {}
        self._form_dirty = False
        self._form_design_mode = False
        self._form_design_tool = FORM_TOOL_SELECT
        self._selected_form_ref = None
        self._form_drag_action = None
        self._form_drag_page = -1
        self._form_drag_start_pdf = None
        self._form_drag_original_rect = None
        self._form_preview_rect = None
        self._form_suggestions = []
        self._selected_form_suggestion_id = None
        self._form_detection_context = None
        self._form_detection_statistics = {}
        self._scan_text_context = None
        self._requires_full_rewrite = False
        self.pages = []
        self._undo_stack.clear()

    def _capture_open_session(self):
        """Capture the current session so a failed document open can roll back."""
        return {
            "pdf_document": self.pdf_document,
            "pdf_file_path": self.pdf_file_path,
            "imported_source_path": self._imported_source_path,
            "imported_temp_pdf_path": self._imported_temp_pdf_path,
            "document_session_id": self._document_session_id,
            "pending_redaction_session_id": self._pending_redaction_session_id,
            "pending_redactions": self.pending_redactions,
            "annotations": self.annotations,
            "markup_strokes": self.markup_strokes,
            "bookmarks": self.bookmarks,
            "search_results": self.search_results,
            "current_search_index": self.current_search_index,
            "current_page": self.current_page,
            "total_pages": self.total_pages,
            "rotation": self.rotation,
            "requires_full_rewrite": self._requires_full_rewrite,
            "form_dirty": self._form_dirty,
            "undo": self._undo_stack.snapshot(),
            "window_title": self.windowTitle(),
        }

    def _restore_open_session(self, snapshot):
        """Restore a captured session after a new-document initialisation failure."""
        self._reset_document_session_state()
        self.pdf_document = snapshot["pdf_document"]
        self.pdf_file_path = snapshot["pdf_file_path"]
        self._imported_source_path = snapshot.get("imported_source_path")
        self._imported_temp_pdf_path = snapshot.get("imported_temp_pdf_path")
        self._document_session_id = snapshot["document_session_id"]
        self._pending_redaction_session_id = snapshot[
            "pending_redaction_session_id"
        ]
        self.pending_redactions = snapshot["pending_redactions"]
        self.annotations = snapshot["annotations"]
        self.markup_strokes = snapshot["markup_strokes"]
        self.bookmarks = snapshot["bookmarks"]
        self.search_results = snapshot["search_results"]
        self.current_search_index = snapshot["current_search_index"]
        self.current_page = snapshot["current_page"]
        self.total_pages = snapshot["total_pages"]
        self.rotation = snapshot["rotation"]
        self._requires_full_rewrite = snapshot["requires_full_rewrite"]
        self._form_dirty = snapshot["form_dirty"]
        self._undo_stack.restore(snapshot["undo"])
        self.setWindowTitle(snapshot["window_title"])
        if self.pdf_document is not None:
            self._refresh_after_document_replacement(self.current_page)
            self._enable_all_controls()
        else:
            self.pages = []
            self.update_view()
        self._update_undo_redo_labels()

    def _begin_document_session(self):
        self._document_session_id = new_document_session_id()
        self._pending_redaction_session_id = self._document_session_id

    def _refresh_after_document_replacement(self, preferred_page=0):
        """Rebuild page and form caches after an atomic in-memory commit."""
        self.total_pages = self.pdf_document.page_count if self.pdf_document else 0
        self.current_page = min(max(0, preferred_page), max(0, self.total_pages - 1))
        self.pages = []
        self._reload_form_cache()
        self.load_pages()
        self.update_view()
        self.load_thumbnails()
        self.load_toc()
        self.refresh_bookmark_list()
        self.refresh_annotations_panel()
        self.refresh_forms_panel()
        self.update_ui_on_page_change()
        self.page_label.setText(f" / {self.total_pages}")

    def _replace_document_from_snapshot(self, payload, *, preferred_page=None):
        """Replace the live PDF from validated bytes and rebuild all live caches."""
        replacement = open_pdf_snapshot(payload)
        old_document = self.pdf_document
        self.pdf_document = replacement
        if old_document is not None and old_document is not replacement:
            try:
                old_document.close()
            except Exception:
                pass
        self._requires_full_rewrite = True
        self._refresh_after_document_replacement(
            self.current_page if preferred_page is None else preferred_page
        )

    # =========================================================================
    # Recent files
    # =========================================================================

    def _load_recent_files(self):
        raw = self.settings.value("recent_files", [])
        return raw if isinstance(raw, list) else []

    def _save_recent_files(self):
        self.settings.setValue("recent_files", self.recent_files[:10])

    def _add_to_recent(self, path):
        if path in self.recent_files:
            self.recent_files.remove(path)
        self.recent_files.insert(0, path)
        self.recent_files = self.recent_files[:10]
        self._save_recent_files()
        self._build_recent_menu()

    def _build_recent_menu(self):
        """Attach a drop-down menu to open_button showing recent files."""
        menu = QMenu(self)
        if self.recent_files:
            for path in self.recent_files:
                act = QAction(os.path.basename(path), self)
                act.setToolTip(path)
                act.triggered.connect(lambda checked, p=path: self._open_pdf_path(p))
                menu.addAction(act)
            menu.addSeparator()
            clear_act = QAction("Clear Recent Files", self)
            clear_act.triggered.connect(self._clear_recent)
            menu.addAction(clear_act)
        else:
            menu.addAction(QAction("(no recent files)", self))
        self.open_button.setMenu(menu)

    def _clear_recent(self):
        self.recent_files = []
        self._save_recent_files()
        self._build_recent_menu()

    # =========================================================================
    # Open / Save
    # =========================================================================

    def open_pdf(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Open Document", "",
            "All supported (*.pdf *.docx *.doc *.rtf *.odt *.xlsx *.xls *.ods *.csv);;"
            "PDF Files (*.pdf);;"
            "Word Documents (*.docx *.doc *.rtf *.odt);;"
            "Excel Spreadsheets (*.xlsx *.xls *.ods *.csv);;"
            "All Files (*)")
        if file_name:
            self._open_pdf_path(file_name)

    def _open_office_document(self, src):
        """Convert a Word/Excel document to PDF, then open it for viewing."""
        import doc_import
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt

        name = os.path.basename(src)
        self.status_bar.showMessage(f"Converting {name} …  (this can take a few seconds)")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            pdf_path = doc_import.convert_to_pdf(src)
        except doc_import.ImportUnavailable as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Can't open this document", str(e))
            self.status_bar.showMessage("Open cancelled — no converter available")
            return
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(
                self, "Conversion failed",
                f"“{name}” could not be converted:\n\n{e}")
            self.status_bar.showMessage(f"Could not convert {name}")
            return
        QApplication.restoreOverrideCursor()

        # Open the converted PDF, but present it under the original filename.
        opened = self._open_pdf_path(
            pdf_path,
            display_path=src,
            skip_unsaved_prompt=True,
            imported_source_path=src,
            imported_temp_path=pdf_path,
        )
        if not opened:
            doc_import.cleanup_temporary_import(pdf_path)

    def _open_pdf_path(
        self,
        file_name,
        display_path=None,
        skip_unsaved_prompt=False,
        imported_source_path=None,
        imported_temp_path=None,
    ):
        logging.info("Opening document: %s", file_name)
        if (
            self._scan_text_worker is not None
            and self._scan_text_worker.isRunning()
        ):
            QMessageBox.information(
                self,
                "Scanned-Text OCR Running",
                "Wait for the selected-region OCR to finish before opening "
                "another document.",
            )
            return
        if (not skip_unsaved_prompt and self.pdf_document
                and not self._confirm_save_changes("open another document")):
            return
        if not os.path.exists(file_name):
            self.status_bar.showMessage(f"File not found: {file_name}")
            return

        # Word / Excel documents: convert to PDF first, then open that.
        import doc_import
        if display_path is None and doc_import.is_importable(file_name):
            self._open_office_document(file_name)
            return

        doc = None
        previous_session = None
        try:
            # ── File size warning for very large documents ────────────────
            try:
                file_size_mb = os.path.getsize(file_name) / (1024 * 1024)
                if file_size_mb > 150:
                    reply = QMessageBox.question(
                        self, "Large File",
                        f"This file is {file_size_mb:.0f} MB. Opening very large PDFs "                        f"may be slow.\n\nContinue?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Yes)
                    if reply != QMessageBox.StandardButton.Yes:
                        return
            except OSError:
                # Can't stat the file — proceed with open attempt anyway
                pass

            # ── Open & repair ─────────────────────────────────────────────
            try:
                doc = fitz.open(file_name)
            except fitz.FileDataError as fde:
                logging.exception("Corrupted PDF could not be opened: %s", file_name)
                QMessageBox.critical(
                    self, "Corrupted PDF",
                    f"The file appears to be corrupted and could not be opened.\n\n"
                    f"Detail: {fde}")
                self.status_bar.showMessage(f"Error: corrupted PDF – {file_name}")
                return
            except Exception as exc:
                logging.exception("PDF open failed: %s", file_name)
                QMessageBox.critical(self, "Open Error", str(exc))
                self.status_bar.showMessage(f"Error loading PDF: {exc}")
                return

            # ── Handle password-protected PDFs ────────────────────────────
            if doc.needs_pass:
                dlg = PasswordPromptDialog(
                    filename=os.path.basename(file_name), parent=self)
                if dlg.exec() != dlg.DialogCode.Accepted:
                    doc.close()
                    return
                if not doc.authenticate(dlg.password):
                    QMessageBox.critical(self, "Wrong Password",
                        "Incorrect password. The file could not be opened.")
                    doc.close()
                    return
            # Load file-bound sidecars before replacing the current session.
            loaded_annotations = load_annotations(doc, file_name)
            loaded_markup = self._load_markup_strokes(file_name)
            loaded_bookmarks = load_bookmarks(file_name)

            # Keep the current PDF alive until every new-session cache and UI
            # step succeeds. A later exception can then restore this session.
            previous_session = self._capture_open_session()
            old_document = previous_session["pdf_document"]
            self._reset_document_session_state()
            self.pdf_document = doc
            self.pdf_file_path = file_name
            self._imported_source_path = imported_source_path
            self._imported_temp_pdf_path = imported_temp_path
            self._begin_document_session()
            self.total_pages = self.pdf_document.page_count
            self.current_page = 0
            self.rotation = 0
            self._clear_tool_buttons()

            self.annotations = loaded_annotations
            self.markup_strokes = loaded_markup
            self.bookmarks = loaded_bookmarks
            self._clear_form_drag()
            self.clear_form_suggestions(update_view=False)
            self._update_undo_redo_labels()

            self._reload_form_cache()

            self.selection_start_point  = None
            self.selection_end_point    = None
            self.current_selection_page = -1

            self.load_pages()
            self.update_view()
            self.load_thumbnails()
            self.load_toc()
            self.refresh_bookmark_list()

            self._enable_all_controls()
            self.refresh_annotations_panel()
            self.refresh_forms_panel()
            self.update_ui_on_page_change()
            self.page_label.setText(f" / {self.total_pages}")
            shown = display_path or file_name
            suffix = "  (imported)" if display_path else ""
            self.setWindowTitle(f"{APP_NAME}  –  {os.path.basename(shown)}{suffix}")
            self.status_bar.showMessage(f"Opened: {shown}")
            self._add_to_recent(display_path or file_name)

            # Commit the session only after every cache and UI step succeeded.
            # The previous document remains live until this point.
            if old_document is not None and old_document is not doc:
                try:
                    old_document.close()
                except Exception:
                    logging.exception("Could not close the previous PDF after commit")
            previous_temp = previous_session.get("imported_temp_pdf_path")
            if previous_temp and previous_temp != imported_temp_path:
                if not doc_import.cleanup_temporary_import(previous_temp):
                    logging.warning(
                        "Could not remove previous Office conversion cache: %s",
                        previous_temp,
                    )
            logging.info("Document opened successfully: %s", shown)
            return True
        except Exception as e:
            logging.exception("Document session initialisation failed: %s", file_name)
            try:
                if doc is not None and doc is not (previous_session or {}).get("pdf_document"):
                    if not doc.is_closed:
                        doc.close()
            except Exception:
                logging.exception("Could not close failed new-document session")
            if previous_session is not None:
                try:
                    self._restore_open_session(previous_session)
                except Exception:
                    logging.exception("Could not restore previous document session")
            QMessageBox.critical(self, "Unexpected Error",
                f"An unexpected error occurred while opening the file:\n\n{e}")
            self.status_bar.showMessage(f"Error loading PDF: {e}")
            return False

    def _enable_all_controls(self):
        for w in [
            # toolbar
            self.prev_button, self.next_button, self.page_input,
            self.zoom_out_button, self.zoom_in_button,
            self.zoom_fit_width_button, self.zoom_fit_page_button,
            self.rotate_button, self.fullscreen_button,
            self.save_button, self.print_button,
            self.prev_search_button, self.next_search_button,
            # markup
            self.annotate_button, self.highlight_button, self.underline_button,
            self.strikethrough_button, self.freehand_button, self.eraser_button,
            self.signature_button, self.stamp_button, self.markup_color_button,
            self.redact_button, self.scan_text_button,
            # sidebar
            self.add_bookmark_button, self.remove_bookmark_button,
            # menu actions
            self._act_save, self._act_save_as, self._act_print, self._act_props,
            self._act_toggle_view, self._act_dark_mode, self._act_fullscreen,
            self._act_fit_width, self._act_fit_page,
            self._act_zoom_in, self._act_zoom_out, self._act_rotate,
            self._act_add_page, self._act_remove_page,
            self._act_move_up, self._act_move_down, self._act_bookmark,
            self._act_extract_pages, self._act_apply_redact,
            self._act_edit_scan_text,
            self._act_password,
            self._act_ocr, self._act_export_docx, self._act_export_xlsx,
            self._act_export_images,
            self._act_save_copy, self._act_reset_form, self._act_reset_all_forms,
            self._act_flatten_form, self._act_form_designer,
            self._act_detect_form_fields, self._act_form_properties,
            self._act_delete_form_field,
            self._act_undo, self._act_redo,
            self._act_copy_text, self._act_select_all,
            self._act_find, self._act_find_next, self._act_find_prev,
            # legacy compat
            self.save_as_button, self.properties_button,
            self.add_page_button, self.remove_page_button,
            self.move_up_button, self.move_down_button,
            self.view_mode_button, self.dark_mode_button, self.search_button,
        ]:
            w.setEnabled(True)

    def show_password_dialog(self):
        """Create a protected/unprotected copy through a staged PDF transaction."""
        if not self.pdf_document:
            return
        is_enc = self.pdf_document.is_encrypted
        dlg = PasswordProtectDialog(is_encrypted=is_enc, parent=self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Protected PDF", self.pdf_file_path or "protected.pdf",
            "PDF Files (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        if self.pdf_file_path and os.path.abspath(path) == os.path.abspath(self.pdf_file_path):
            QMessageBox.warning(
                self,
                "Choose a Different File",
                "Password changes are written as a validated new PDF. Choose a "
                "different filename so the open source remains recoverable.",
            )
            return

        clone = None
        try:
            self._autosave_form_data()
            clone = clone_pdf_document(self.pdf_document)
            self._prepare_document_for_save(
                clone, autosave_forms=False, mark_baked=False)
            if dlg.remove_password:
                save_kwargs = {
                    "encryption": fitz.PDF_ENCRYPT_NONE,
                    "garbage": 4,
                    "deflate": True,
                }
                validation_password = None
                success_text = f"Saved without password: {os.path.basename(path)}"
            else:
                save_kwargs = {
                    "encryption": dlg.encryption,
                    "user_pw": dlg.user_password,
                    "owner_pw": dlg.owner_password,
                    "permissions": dlg.permissions,
                    "garbage": 4,
                    "deflate": True,
                }
                validation_password = dlg.user_password or dlg.owner_password
                success_text = (
                    f"Password protected PDF saved: {os.path.basename(path)}")

            save_pdf_atomic(
                clone,
                path,
                save_kwargs=save_kwargs,
                validator=lambda staged: validate_pdf_file(
                    staged,
                    expected_pages=clone.page_count,
                    password=validation_password,
                ),
            )
            self.status_bar.showMessage(success_text)
            self._add_to_recent(path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Save Error",
                "The protected copy could not be completed. Any existing "
                f"destination was preserved.\n\n{type(exc).__name__}: {exc}",
            )
        finally:
            if clone is not None:
                clone.close()

    def apply_redactions(self, *, confirm=True):
        """Apply all pending boxes to a validated clone, then commit atomically."""
        if not self.pdf_document:
            return False
        total_boxes = sum(len(v) for v in self.pending_redactions.values())
        if total_boxes == 0:
            self.status_bar.showMessage(
                "No redactions pending. Use the Redact tool to draw boxes first.")
            return False

        if confirm:
            reply = QMessageBox.warning(
                self, "Apply Redactions",
                f"This will permanently black out {total_boxes} area(s) "
                f"across {len(self.pending_redactions)} page(s).\n\n"
                f"This action CANNOT be undone.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return False

        preferred_page = self.current_page
        try:
            staged = apply_redactions_transactionally(
                self.pdf_document,
                self.pending_redactions,
                redaction_session_id=self._pending_redaction_session_id,
                active_session_id=self._document_session_id,
            )
        except Exception as exc:
            logging.exception("Transactional redaction failed")
            QMessageBox.critical(
                self,
                "Redaction Error",
                "No page was changed because the complete redaction transaction "
                f"could not be validated.\n\n{type(exc).__name__}: {exc}",
            )
            self.status_bar.showMessage(f"Redaction transaction rejected: {exc}")
            return False

        old_document = self.pdf_document
        self.pdf_document = staged
        try:
            old_document.close()
        except Exception:
            pass
        self.pending_redactions.clear()
        self._pending_redaction_session_id = self._document_session_id
        self.active_tool = TOOL_NONE
        self._requires_full_rewrite = True
        self._mark_modified()
        self._sync_tool_buttons()
        self._update_cursor()
        self._refresh_after_document_replacement(preferred_page)
        self.status_bar.showMessage(
            "Redactions applied transactionally. Save As is required for a clean full rewrite.")
        return True

    def _mark_modified(self):
        """Put an asterisk in the title bar when there are unsaved changes."""
        title = self.windowTitle()
        if not title.startswith("*"):
            self.setWindowTitle("*" + title)

    def _clear_modified(self):
        """Remove the asterisk after a successful save."""
        title = self.windowTitle()
        if title.startswith("*"):
            self.setWindowTitle(title[1:])

    def _has_unsaved_changes(self):
        return bool(self.pdf_document and (
            self._form_dirty or self.windowTitle().startswith("*")
        ))

    def _confirm_save_changes(self, action="continue"):
        """Ask what to do with unsaved changes. Return True to proceed."""
        if not self._has_unsaved_changes():
            return True
        if self.pending_redactions:
            count = sum(len(items) for items in self.pending_redactions.values())
            reply = QMessageBox.warning(
                self,
                "Unapplied Redactions",
                f"This document has {count} unapplied redaction box(es).\n\n"
                "Choose Save to apply them transactionally and save a new PDF. "
                "Choose Discard to abandon all unsaved changes, or Cancel to stay "
                f"in the document before you {action}.",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return False
            if reply == QMessageBox.StandardButton.Discard:
                return True
            if not self.apply_redactions(confirm=False):
                return False
            return bool(self.save_pdf_as())

        reply = QMessageBox.warning(
            self, "Unsaved Changes",
            f"This document has unsaved changes. Save them before you {action}?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if reply == QMessageBox.StandardButton.Cancel:
            return False
        if reply == QMessageBox.StandardButton.Discard:
            return True
        return bool(self.save_pdf())

    def save_pdf(self):
        """Save the active PDF, forcing Save As for non-owned or rewritten data."""
        if not self.pdf_document:
            return False
        if self._imported_source_path:
            QMessageBox.information(
                self,
                "Save Imported Document As PDF",
                "This document was converted from an Office file. The open PDF "
                "is a temporary conversion cache, not a user-owned destination.\n\n"
                "Choose where to save the edited PDF.",
            )
            return self.save_pdf_as()
        if self._requires_full_rewrite:
            QMessageBox.information(
                self,
                "Save As Required",
                "This document contains permanently erased page content. "
                "PDF Studio must write a new, compact PDF so removed pixels or "
                "text are not retained in an incremental revision.\n\n"
                "Choose a new filename. The original file will be preserved.",
            )
            return self.save_pdf_as()
        if self.pdf_file_path:
            return self._do_save(self.pdf_file_path)
        return self.save_pdf_as()

    def save_pdf_as(self):
        """Save to a new PDF, reopen that copy, and continue editing it."""
        if not self.pdf_document:
            return False
        if self._imported_source_path:
            import doc_import
            default_path = doc_import.imported_pdf_default_path(
                self._imported_source_path
            )
        else:
            default_path = self.pdf_file_path or "document.pdf"
        if self._requires_full_rewrite and self.pdf_file_path and not self._imported_source_path:
            base, ext = os.path.splitext(self.pdf_file_path)
            default_path = base + "_edited" + (ext or ".pdf")
        file_name, _ = QFileDialog.getSaveFileName(
            self, "Save PDF As", default_path, "PDF Files (*.pdf)")
        if not file_name:
            return False
        if not file_name.lower().endswith(".pdf"):
            file_name += ".pdf"

        if self.pending_redactions:
            decision = self._prompt_pending_redactions_for_save_as()
            if decision == "cancel":
                return False
            if decision == "apply":
                if not self.apply_redactions(confirm=False):
                    return False
            elif decision == "discard":
                self.pending_redactions.clear()
                self._pending_redaction_session_id = self._document_session_id
                self.active_tool = TOOL_NONE
                self._sync_tool_buttons()
                self._update_cursor()
                self.refresh_annotations_panel()
                self.update_view()

        if (
            self._requires_full_rewrite
            and self.pdf_file_path
            and os.path.abspath(file_name) == os.path.abspath(self.pdf_file_path)
        ):
            QMessageBox.warning(
                self,
                "Choose a New Filename",
                "Permanent content removal cannot be saved incrementally over "
                "the open source PDF. Choose a different filename.",
            )
            return False

        old_page = self.current_page
        if not self._do_save(file_name, sidecar_path=file_name):
            return False

        # Reopen the new file so later Ctrl+S correctly saves incrementally to it.
        if not self._open_pdf_path(file_name, skip_unsaved_prompt=True):
            return False
        if self.pdf_document and self.total_pages:
            self.current_page = min(old_page, self.total_pages - 1)
            self.update_ui_on_page_change()
        return True

    def _prompt_pending_redactions_for_save_as(self):
        """Require an explicit decision before Save As can clear redaction boxes."""
        count = sum(len(items) for items in self.pending_redactions.values())
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Unapplied Redactions")
        box.setText(
            f"This document has {count} unapplied redaction box(es)."
        )
        box.setInformativeText(
            "Save As cannot silently carry pending destructive state into a "
            "new document session. Choose whether to apply the redactions, "
            "save without them, or cancel."
        )
        apply_button = box.addButton(
            "Apply Redactions and Save", QMessageBox.ButtonRole.AcceptRole
        )
        discard_button = box.addButton(
            "Save Without Redactions", QMessageBox.ButtonRole.DestructiveRole
        )
        cancel_button = box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(cancel_button)
        box.exec()
        clicked = box.clickedButton()
        if clicked is apply_button:
            return "apply"
        if clicked is discard_button:
            return "discard"
        return "cancel"

    def _prepare_document_for_save(
            self, document=None, *, autosave_forms=True, mark_baked=True):
        """Flush app-level markup into ``document`` without duplicating images."""
        target = document or self.pdf_document
        if target is None:
            raise RuntimeError("No PDF is available for save preparation.")
        if autosave_forms:
            self._autosave_form_data()

        for pn, items in self.annotations.items():
            if not (0 <= int(pn) < target.page_count):
                raise RuntimeError(
                    f"Sticky-note state references missing page {int(pn) + 1}."
                )
            page = target.load_page(int(pn))
            existing_positions = set()
            for annot in page.annots() or []:
                if annot.type[0] == 8:
                    pos = annot.rect.top_left
                    existing_positions.add((round(pos.x), round(pos.y)))
            for x, y, text in items:
                if (round(x), round(y)) not in existing_positions:
                    annot = page.add_text_annot(fitz.Point(x, y), text)
                    annot.set_colors(stroke=(1, 0.6, 0))
                    annot.update()

        # Signature images and stamps use immediate PDF persistence and are not
        # replayed from the sidecar during save preparation.
        for pn, strokes in self.markup_strokes.items():
            if not (0 <= int(pn) < target.page_count):
                raise RuntimeError(
                    f"Markup state references missing page {int(pn) + 1}."
                )
            page = target.load_page(int(pn))
            for stroke in strokes:
                if stroke.get("baked"):
                    continue
                stype = stroke.get("type")
                rects = [fitz.Rect(r) for r in stroke.get("rects", [])]
                color = stroke.get("color", [1, 1, 0])
                if stype == "highlight" and rects:
                    annot = page.add_highlight_annot(rects)
                    annot.set_colors(stroke=color)
                    annot.update()
                elif stype == "underline" and rects:
                    annot = page.add_underline_annot(rects)
                    annot.set_colors(stroke=color)
                    annot.update()
                elif stype == "strikethrough" and rects:
                    annot = page.add_strikeout_annot(rects)
                    annot.set_colors(stroke=color)
                    annot.update()
                elif stype == "freehand":
                    points = stroke.get("points", [])
                    if len(points) >= 2:
                        ink_list = [[fitz.Point(p[0], p[1]) for p in points]]
                        annot = page.add_ink_annot(ink_list)
                        annot.set_colors(stroke=color)
                        annot.set_border(width=stroke.get("width", 2))
                        annot.update()
                if mark_baked:
                    stroke["baked"] = True

    def _do_save(self, path, sidecar_path=None):
        """Atomically commit the PDF and every application sidecar as one bundle."""
        if not self.pdf_document:
            return False
        path = os.path.abspath(path)
        sidecar_path = os.path.abspath(sidecar_path or path)
        document_name = (
            os.path.abspath(self.pdf_document.name)
            if getattr(self.pdf_document, "name", None)
            else ""
        )
        same_file = bool(document_name and document_name == path)
        replaces_active_stream = bool(
            same_file
            or (
                self.pdf_file_path
                and os.path.abspath(self.pdf_file_path) == path
            )
        )
        if same_file and self._requires_full_rewrite:
            QMessageBox.warning(
                self,
                "Save As Required",
                "A clean full rewrite cannot replace the currently open source "
                "incrementally. Choose Save As and a new filename.",
            )
            return False

        preferred_page = self.current_page
        staged_document = None
        replacement = None
        staged_operations = []
        active_snapshot = None
        active_document_closed = False
        committed = False
        try:
            # Flush live form controls before cloning. All deferred annotations
            # are then prepared only on the independent staged document.
            self._autosave_form_data()
            if replaces_active_stream:
                active_snapshot = snapshot_pdf_bytes(self.pdf_document)
            staged_document = clone_pdf_document(self.pdf_document)
            self._prepare_document_for_save(
                staged_document, autosave_forms=False, mark_baked=False
            )
            new_annotations, new_markup = retire_baked_sidecar_state(
                self.annotations, self.markup_strokes
            )
            if replaces_active_stream:
                replacement = clone_pdf_document(staged_document)

            with sibling_staged_path(path) as staged_pdf:
                staged_document.save(
                    str(staged_pdf),
                    garbage=4 if self._requires_full_rewrite else 3,
                    clean=bool(self._requires_full_rewrite),
                    deflate=True,
                    encryption=fitz.PDF_ENCRYPT_KEEP,
                )
                validate_pdf_file(
                    staged_pdf, expected_pages=staged_document.page_count
                )
                staged_operations = [
                    StagedOperation(Path(path), Path(staged_pdf))
                ]
                staged_operations.append(
                    stage_json_payload(
                        sidecar_path + ".annotations.json", new_annotations
                    )
                )
                staged_operations.append(
                    stage_json_payload(
                        self._markup_path(sidecar_path), new_markup
                    )
                )
                staged_operations.append(
                    stage_json_payload(
                        sidecar_path + ".bookmarks.json", self.bookmarks
                    )
                )

                # Windows may deny atomic replacement while the source PDF is
                # still open. A validated in-memory snapshot and replacement
                # are already available, so release the source handle only at
                # the final commit boundary.
                if replaces_active_stream and self.pdf_document is not None:
                    self.pdf_document.close()
                    self.pdf_document = None
                    active_document_closed = True
                commit_staged_operations(staged_operations)
                committed = True

            # Only after the complete bundle commits may the live authority and
            # dirty state advance. Save As targets are opened transactionally
            # afterwards, so the old session remains untouched until that open
            # succeeds; a failed reopen can therefore restore every pending edit.
            if replaces_active_stream:
                self.annotations = new_annotations
                self.markup_strokes = new_markup
                if replacement is not None:
                    old_document = self.pdf_document
                    self.pdf_document = replacement
                    replacement = None
                    if old_document is not None:
                        try:
                            old_document.close()
                        except Exception:
                            logging.exception(
                                "Could not close the pre-save PDF handle"
                            )
                    active_document_closed = False
                self._form_dirty = False
                self._requires_full_rewrite = False
                self._clear_modified()
                if self.pending_redactions:
                    self._mark_modified()
                    self.status_bar.showMessage(
                        f"Saved: {path}. Unapplied redaction boxes remain pending."
                    )
                else:
                    self.status_bar.showMessage(f"Saved: {path}")
            else:
                self.status_bar.showMessage(
                    f"Saved new PDF: {path}. Opening the saved document..."
                )
            logging.info("PDF and sidecars saved successfully: %s", path)

            try:
                if replaces_active_stream:
                    self._refresh_after_document_replacement(preferred_page)
            except Exception:
                # The durable save has completed; a display refresh failure must
                # not be misreported as an unsuccessful file transaction.
                logging.exception("Post-save UI refresh failed")
            return True
        except Exception as exc:
            logging.exception("PDF save bundle failed: %s", path)
            if active_document_closed and active_snapshot is not None:
                try:
                    self.pdf_document = open_pdf_snapshot(active_snapshot)
                    active_document_closed = False
                    self._refresh_after_document_replacement(preferred_page)
                except Exception:
                    logging.exception(
                        "Could not restore the active PDF after save rollback"
                    )
            self._mark_modified()
            message = (
                "The PDF and its application sidecars could not be committed as "
                "one save transaction. Existing destination files were "
                "preserved and the document remains unsaved."
            )
            if committed:
                message = (
                    "The file data was committed, but a later application error "
                    "occurred. Review the diagnostics log before continuing."
                )
            QMessageBox.critical(
                self,
                "Save Error",
                f"{message}\n\n{type(exc).__name__}: {exc}",
            )
            self.status_bar.showMessage(f"Save error: {exc}")
            return False
        finally:
            cleanup_staged_operations(staged_operations)
            if replacement is not None:
                replacement.close()
            if staged_document is not None:
                staged_document.close()

    # =========================================================================
    # Markup stroke persistence (sidebar JSON file, separate from annotations)
    # =========================================================================

    def _markup_path(self, pdf_path):
        return pdf_path + ".markup.json"

    def _load_markup_strokes(self, pdf_path):
        """Load only deferred markup not already represented natively."""
        mp = self._markup_path(pdf_path)
        if not os.path.exists(mp):
            return {}
        try:
            with open(mp, encoding="utf-8") as handle:
                raw = json.load(handle)
            return pending_markup_only(raw)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            import logging
            logging.warning(
                "_load_markup_strokes: could not read '%s': %s", mp, exc
            )
            return {}

    def _save_markup_strokes(self, pdf_path):
        """Atomically persist deferred markup only."""
        mp = self._markup_path(pdf_path)
        try:
            atomic_write_json(mp, pending_markup_only(self.markup_strokes))
        except OSError as exc:
            self.status_bar.showMessage(
                f"Warning: could not save markup strokes: {exc}"
            )
            raise

    def _retire_baked_annotation_state(self):
        """Switch successfully saved annotations to the native PDF authority."""
        self.annotations, self.markup_strokes = retire_baked_sidecar_state(
            self.annotations,
            self.markup_strokes,
        )


    # =========================================================================
    # Active tool management
    # =========================================================================

    def set_markup_tool(self, tool: str):
        """Toggle a markup tool on/off; deactivates any other tool."""
        if self._form_design_mode:
            self.set_form_design_mode(False)
        if tool == TOOL_SCAN_TEXT and self._scan_text_worker is not None:
            self.status_bar.showMessage("Scanned-text OCR is already running.")
            return
        if self.active_tool == tool:
            self.active_tool = TOOL_NONE
        else:
            self.active_tool = tool
            self.annotation_mode = False
        self._sync_tool_buttons()
        self._update_cursor()
        if self.active_tool == TOOL_SCAN_TEXT:
            self.status_bar.showMessage(
                "Drag a rectangle around scanned text to OCR and replace it."
            )

    def clear_active_tool(self):
        self._release_scan_text_mouse_grab()
        self.active_tool = TOOL_NONE
        self.annotation_mode = False
        self._clear_tool_buttons()
        self._update_cursor()

    def _clear_tool_buttons(self):
        for btn in [self.annotate_button, self.highlight_button,
                    self.underline_button, self.strikethrough_button,
                    self.freehand_button, self.eraser_button,
                    self.signature_button, self.redact_button,
                    self.scan_text_button]:
            btn.setChecked(False)
        self._act_edit_scan_text.setChecked(False)

    def _sync_tool_buttons(self):
        mapping = {
            TOOL_ANNOTATE:      self.annotate_button,
            TOOL_HIGHLIGHT:     self.highlight_button,
            TOOL_UNDERLINE:     self.underline_button,
            TOOL_STRIKETHROUGH: self.strikethrough_button,
            TOOL_FREEHAND:      self.freehand_button,
            TOOL_ERASER:        self.eraser_button,
            TOOL_SIGNATURE:     self.signature_button,
            TOOL_REDACT:        self.redact_button,
            TOOL_SCAN_TEXT:      self.scan_text_button,
        }
        for tool, btn in mapping.items():
            btn.setChecked(self.active_tool == tool)
        self._act_edit_scan_text.setChecked(
            self.active_tool == TOOL_SCAN_TEXT
        )

    def _update_cursor(self):
        cursors = {
            TOOL_HIGHLIGHT:     Qt.CursorShape.IBeamCursor,
            TOOL_UNDERLINE:     Qt.CursorShape.IBeamCursor,
            TOOL_STRIKETHROUGH: Qt.CursorShape.IBeamCursor,
            TOOL_FREEHAND:      Qt.CursorShape.CrossCursor,
            TOOL_ERASER:        Qt.CursorShape.PointingHandCursor,
            TOOL_ANNOTATE:      Qt.CursorShape.CrossCursor,
            TOOL_SIGNATURE:     Qt.CursorShape.CrossCursor,
            TOOL_REDACT:        Qt.CursorShape.CrossCursor,
            TOOL_SCAN_TEXT:      Qt.CursorShape.CrossCursor,
        }
        if self._form_design_mode:
            shape = (
                Qt.CursorShape.CrossCursor
                if self._form_design_tool in (FORM_TOOL_TEXT, FORM_TOOL_CHECKBOX)
                else Qt.CursorShape.SizeAllCursor
            )
        else:
            shape = cursors.get(self.active_tool, Qt.CursorShape.ArrowCursor)
        cursor = QCursor(shape)
        for w in self.page_widgets:
            w.setCursor(cursor)

    # =========================================================================
    # Markup colour picker
    # =========================================================================

    def pick_markup_color(self):
        col = QColorDialog.getColor(self.markup_color, self, "Choose Markup Colour")
        if col.isValid():
            self.markup_color = col
            self.markup_color_button.setStyleSheet(
                f"background:{col.name()};"
                f"color:{'white' if col.lightness() < 128 else 'black'};")
            self.settings.setValue("prefs/markup_color", col.name())

    # =========================================================================
    # Signature
    # =========================================================================

    def place_signature(self):
        """Open draw-signature dialog then arm the placement tool."""
        from signature_dialog import SignatureDialog
        dlg = SignatureDialog(self)
        if dlg.exec() and dlg.signature_pixmap:
            self._pending_signature = dlg.signature_pixmap
            self.active_tool = TOOL_SIGNATURE
            self._sync_tool_buttons()
            self._update_cursor()
            self.status_bar.showMessage(
                "Click on the page where you want to place the signature.")
        else:
            self.active_tool = TOOL_NONE
            self._sync_tool_buttons()

    def _place_signature_at(self, page_num, page_widget, click_x, click_y):
        """Stamp the pending (drawn/imported) signature at the click point."""
        if not self._pending_signature:
            return
        self._stamp_signature_pixmap(
            page_num, page_widget, click_x, click_y, self._pending_signature)
        self._pending_signature = None
        self.active_tool = TOOL_NONE
        self._sync_tool_buttons()
        self._update_cursor()

    def _stamp_signature_pixmap(self, page_num, page_widget, click_x, click_y, pix):
        """Place any QPixmap onto a page as a signature image.

        Used by both click-to-place and drag-and-drop. The image is sized to a
        sensible default width in PDF points (preserving aspect ratio) so a
        large scan or a 500px drawing both land at a usable size.
        """
        if pix is None or pix.isNull():
            return
        matrix = fitz.Matrix(self.zoom_level, self.zoom_level).prerotate(self.rotation)
        try:
            inv = inverted_fitz_matrix(matrix)
        except ValueError:
            return

        # Click/drop point -> PDF coordinates
        pdf_pt = fitz.Point(click_x, click_y) * inv

        # Size in PDF points, aspect-preserved, capped to half the page width
        aspect = (pix.height() / pix.width()) if pix.width() else 0.3
        page = self.pdf_document.load_page(page_num)
        max_w = page.rect.width * 0.5
        sig_w = min(DEFAULT_SIG_WIDTH_PT, max_w)
        sig_h = sig_w * aspect
        pdf_rect = fitz.Rect(pdf_pt.x, pdf_pt.y, pdf_pt.x + sig_w, pdf_pt.y + sig_h)

        # Pixmap → PNG bytes
        from PyQt6.QtCore import QBuffer, QIODevice
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pix.save(buf, "PNG")
        img_bytes = bytes(buf.data())
        buf.close()

        before_snapshot = snapshot_pdf_bytes(self.pdf_document)
        try:
            insert_signature_image_once(
                self.pdf_document,
                page_number=page_num,
                rect=pdf_rect,
                image_bytes=img_bytes,
            )
            after_snapshot = snapshot_pdf_bytes(self.pdf_document)
        except Exception as exc:
            # A failed immediate insertion must not leave a partial native edit.
            try:
                self._replace_document_from_snapshot(
                    before_snapshot, preferred_page=page_num
                )
            except Exception:
                pass
            QMessageBox.critical(
                self, "Signature Error",
                f"The signature could not be placed.\n\n{type(exc).__name__}: {exc}")
            return
        self._undo_stack.push(Command(
            kind="native_document_change",
            undo_data={
                "pdf_bytes": before_snapshot,
                "page": page_num,
                "label": "Signature",
            },
            redo_data={
                "pdf_bytes": after_snapshot,
                "page": page_num,
                "label": "Signature",
            },
        ))
        self._update_undo_redo_labels()
        self._mark_modified()
        self.render_page_content(page_num, page_widget)
        self.status_bar.showMessage("Signature placed once. Save to persist it.")

    @staticmethod
    def _first_image_url(mime):
        exts = (".png", ".jpg", ".jpeg", ".bmp", ".gif")
        if not mime.hasUrls():
            return None
        for url in mime.urls():
            p = url.toLocalFile()
            if p and os.path.splitext(p)[1].lower() in exts:
                return p
        return None

    def _page_drag_enter(self, event):
        if self._first_image_url(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def _page_drop(self, event, page_widget):
        path = self._first_image_url(event.mimeData())
        if not path:
            event.ignore()
            return
        page_num = page_widget.property("page_num")
        px, py = self._pixel_coords(event, page_widget)
        if px is None:
            event.ignore()
            return
        self.place_dropped_image(page_num, page_widget, px, py, path)
        event.acceptProposedAction()

    def place_dropped_image(self, page_num, page_widget, x, y, path):
        """Handle an image file dropped onto a page — place it as a signature.

        If the image has no transparency (e.g. a scan on white paper), the
        white background is removed automatically so only the ink shows.
        """
        if not self.pdf_document:
            return
        from signature_dialog import make_white_transparent
        pix = QPixmap(path)
        if pix.isNull():
            self.status_bar.showMessage(f"Could not load image: {os.path.basename(path)}")
            return
        if not pix.hasAlphaChannel():
            pix = make_white_transparent(pix)
        self._stamp_signature_pixmap(page_num, page_widget, x, y, pix)

    # =========================================================================
    # Stamp
    # =========================================================================

    def place_stamp(self):
        stamps = ["APPROVED", "DRAFT", "CONFIDENTIAL", "REVIEWED",
                  "REJECTED", "FOR YOUR REVIEW", "VOID"]
        choice, ok = QInputDialog.getItem(
            self, "Insert Stamp", "Choose stamp:", stamps, 0, False)
        if ok and choice:
            self._pending_stamp = choice
            self.status_bar.showMessage(
                f"Click on the page to place '{choice}' stamp.")
            for w in self.page_widgets:
                w.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def _place_stamp_at(self, page_num, page_widget, click_x, click_y):
        text  = getattr(self, "_pending_stamp", None)
        if not text:
            return
        matrix = fitz.Matrix(self.zoom_level, self.zoom_level).prerotate(self.rotation)
        try:
            inv = inverted_fitz_matrix(matrix)
        except ValueError:
            return
        pdf_pt = fitz.Point(click_x, click_y) * inv
        before_snapshot = snapshot_pdf_bytes(self.pdf_document)
        try:
            page = self.pdf_document.load_page(page_num)
            rect = fitz.Rect(pdf_pt.x - 80, pdf_pt.y - 20,
                             pdf_pt.x + 80, pdf_pt.y + 20)
            page.draw_rect(rect, color=(0.8, 0.1, 0.1), width=2)
            page.insert_text(
                fitz.Point(pdf_pt.x - 70, pdf_pt.y + 8),
                text, fontsize=16, color=(0.8, 0.1, 0.1))
            after_snapshot = snapshot_pdf_bytes(self.pdf_document)
        except Exception as exc:
            try:
                self._replace_document_from_snapshot(
                    before_snapshot, preferred_page=page_num
                )
            except Exception:
                pass
            QMessageBox.critical(
                self, "Stamp Error",
                f"The stamp could not be placed.\n\n{type(exc).__name__}: {exc}")
            return
        self._pending_stamp = None
        self._undo_stack.push(Command(
            kind="native_document_change",
            undo_data={
                "pdf_bytes": before_snapshot,
                "page": page_num,
                "label": "Stamp",
            },
            redo_data={
                "pdf_bytes": after_snapshot,
                "page": page_num,
                "label": "Stamp",
            },
        ))
        self._update_undo_redo_labels()
        self._mark_modified()
        for w in self.page_widgets:
            w.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        self.render_page_content(page_num, page_widget)
        self.status_bar.showMessage(f"Stamp '{text}' placed.")

    # =========================================================================
    # Bookmarks
    # =========================================================================

    def add_bookmark(self):
        if not self.pdf_document:
            return
        label, ok = QInputDialog.getText(
            self, "Add Bookmark",
            f"Label for page {self.current_page + 1}:",
            text=f"Page {self.current_page + 1}")
        if ok and label:
            self.bookmarks.append({"page": self.current_page, "label": label})
            self.bookmarks.sort(key=lambda b: b["page"])
            self.refresh_bookmark_list()
            self._mark_modified()
            self.status_bar.showMessage(f"Bookmark added: {label}")

    def remove_bookmark(self):
        row = self.bookmark_list.currentRow()
        if row < 0 or row >= len(self.bookmarks):
            return
        removed = self.bookmarks.pop(row)
        self.refresh_bookmark_list()
        self._mark_modified()
        self.status_bar.showMessage(f"Bookmark removed: {removed['label']}")

    def goto_bookmark(self, item):
        idx = self.bookmark_list.row(item)
        if 0 <= idx < len(self.bookmarks):
            self.current_page = self.bookmarks[idx]["page"]
            self.update_ui_on_page_change()
            if self.view_mode == self.CONTINUOUS:
                self.scroll_to_page(self.current_page)

    def refresh_bookmark_list(self):
        self.bookmark_list.clear()
        for bm in self.bookmarks:
            self.bookmark_list.addItem(
                f"p.{bm['page'] + 1}  {bm['label']}")

    # =========================================================================
    # Page widget creation
    # =========================================================================

    def load_pages(self):
        for widget in self.page_widgets:
            self.pdf_layout.removeWidget(widget)
            widget.deleteLater()
        self.page_widgets = []
        self.field_widgets = {}

        if not self.pdf_document:
            return

        for page_num in range(self.total_pages):
            page_widget = QLabel()
            page_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            page_widget.setContextMenuPolicy(
                Qt.ContextMenuPolicy.CustomContextMenu)
            page_widget.customContextMenuRequested.connect(self._show_context_menu)
            page_widget.setProperty("page_num", page_num)
            page_widget.mousePressEvent   = lambda e, w=page_widget: self._handle_page_mouse_press(e, w)
            page_widget.mouseMoveEvent    = lambda e, w=page_widget: self._handle_page_mouse_move(e, w)
            page_widget.mouseReleaseEvent = lambda e, w=page_widget: self._handle_page_mouse_release(e, w)
            page_widget.setMouseTracking(True)
            # Drag & drop a signature/stamp image straight onto the page
            page_widget.setAcceptDrops(True)
            page_widget.dragEnterEvent = lambda e: self._page_drag_enter(e)
            page_widget.dragMoveEvent  = lambda e: self._page_drag_enter(e)
            page_widget.dropEvent      = lambda e, w=page_widget: self._page_drop(e, w)
            self.pdf_layout.addWidget(page_widget)
            self.page_widgets.append(page_widget)

    # =========================================================================
    # Rendering
    # =========================================================================

    def render_page_content(self, page_num, widget):
        if not self.pdf_document:
            return
        try:
            page   = self.pdf_document.load_page(page_num)
            matrix = fitz.Matrix(self.zoom_level, self.zoom_level).prerotate(self.rotation)
            pix    = page.get_pixmap(matrix=matrix, alpha=False)
            img    = QImage(pix.samples, pix.width, pix.height, pix.stride,
                            QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(img)

            painter = QPainter(pixmap)
            try:
                # ── Text selection highlight ──────────────────────────────
                if (self.selection_start_point and self.selection_end_point
                        and page_num == self.current_selection_page):
                    sx, sy = self.selection_start_point.x(), self.selection_start_point.y()
                    ex, ey = self.selection_end_point.x(),   self.selection_end_point.y()
                    label_size  = widget.size()
                    pixmap_size = pixmap.size()
                    xo = (label_size.width()  - pixmap_size.width())  // 2
                    yo = (label_size.height() - pixmap_size.height()) // 2
                    sel_rect = QRectF(min(sx, ex) - xo, min(sy, ey) - yo,
                                      abs(sx - ex), abs(sy - ey))
                    painter.setPen(QPen(QColor(0, 80, 255, 120), 1))
                    painter.setBrush(QColor(0, 80, 255, 40))
                    painter.drawRect(sel_rect)

                # ── Sticky-note annotations ───────────────────────────────
                if page_num in self.annotations:
                    pen = QPen(QColor(255, 140, 0), 2)
                    painter.setPen(pen)
                    font = painter.font()
                    font.setPointSize(11)
                    painter.setFont(font)
                    for x, y, text in self.annotations[page_num]:
                        sx = x * self.zoom_level
                        sy = y * self.zoom_level
                        painter.drawText(int(sx) - 10, int(sy) - 10, "📌")
                        painter.drawText(QRectF(sx, sy, 220, 60),
                                         Qt.TextFlag.TextWordWrap, text)

                # ── In-progress freehand stroke ───────────────────────────
                if (self._freehand_drawing and
                        self._freehand_page == page_num and
                        len(self._freehand_points) >= 2):
                    r, g, b = (self.markup_color.red(),
                               self.markup_color.green(),
                               self.markup_color.blue())
                    pen = QPen(QColor(r, g, b, 200), 3,
                               Qt.PenStyle.SolidLine,
                               Qt.PenCapStyle.RoundCap,
                               Qt.PenJoinStyle.RoundJoin)
                    painter.setPen(pen)
                    pts = self._freehand_points
                    for i in range(1, len(pts)):
                        painter.drawLine(pts[i - 1], pts[i])

                # ── Pending redaction previews (red bordered boxes) ──────
                if page_num in self.pending_redactions:
                    painter.setPen(QPen(QColor(200, 0, 0), 2,
                                        Qt.PenStyle.SolidLine))
                    painter.setBrush(QColor(200, 0, 0, 60))
                    for r in self.pending_redactions[page_num]:
                        painter.drawRect(QRectF(
                            r.x0 * self.zoom_level, r.y0 * self.zoom_level,
                            (r.x1 - r.x0) * self.zoom_level,
                            (r.y1 - r.y0) * self.zoom_level))

                # ── Persisted markup strokes ──────────────────────────────
                if page_num in self.markup_strokes:
                    for stroke in self.markup_strokes[page_num]:
                        stype = stroke["type"]
                        color_list = stroke.get("color", [1, 1, 0])
                        qcolor = QColor(
                            int(color_list[0] * 255),
                            int(color_list[1] * 255),
                            int(color_list[2] * 255), 120)
                        if stype in ("highlight",):
                            painter.setPen(Qt.PenStyle.NoPen)
                            painter.setBrush(qcolor)
                            for r in stroke.get("rects", []):
                                painter.drawRect(QRectF(
                                    r[0] * self.zoom_level,
                                    r[1] * self.zoom_level,
                                    (r[2] - r[0]) * self.zoom_level,
                                    (r[3] - r[1]) * self.zoom_level))
                        elif stype == "underline":
                            pen = QPen(
                                QColor(int(color_list[0]*255),
                                       int(color_list[1]*255),
                                       int(color_list[2]*255), 200), 2)
                            painter.setPen(pen)
                            for r in stroke.get("rects", []):
                                y_bot = r[3] * self.zoom_level
                                painter.drawLine(
                                    QPoint(int(r[0] * self.zoom_level), int(y_bot)),
                                    QPoint(int(r[2] * self.zoom_level), int(y_bot)))
                        elif stype == "strikethrough":
                            pen = QPen(
                                QColor(int(color_list[0]*255),
                                       int(color_list[1]*255),
                                       int(color_list[2]*255), 200), 2)
                            painter.setPen(pen)
                            for r in stroke.get("rects", []):
                                mid_y = ((r[1] + r[3]) / 2) * self.zoom_level
                                painter.drawLine(
                                    QPoint(int(r[0] * self.zoom_level), int(mid_y)),
                                    QPoint(int(r[2] * self.zoom_level), int(mid_y)))
                        elif stype == "freehand":
                            pts = stroke.get("points", [])
                            if len(pts) >= 2:
                                pen = QPen(
                                    QColor(int(color_list[0]*255),
                                           int(color_list[1]*255),
                                           int(color_list[2]*255), 200),
                                    stroke.get("width", 3),
                                    Qt.PenStyle.SolidLine,
                                    Qt.PenCapStyle.RoundCap,
                                    Qt.PenJoinStyle.RoundJoin)
                                painter.setPen(pen)
                                for i in range(1, len(pts)):
                                    painter.drawLine(
                                        QPoint(int(pts[i-1][0] * self.zoom_level),
                                               int(pts[i-1][1] * self.zoom_level)),
                                        QPoint(int(pts[i][0]   * self.zoom_level),
                                               int(pts[i][1]   * self.zoom_level)))

                # ── Search highlights ─────────────────────────────────────
                if self.search_results:
                    painter.setPen(Qt.PenStyle.NoPen)
                    for i, result in enumerate(self.search_results):
                        if result["page"] != page_num:
                            continue
                        is_cur = (i == self.current_search_index)
                        painter.setBrush(
                            QColor(255, 220, 0, 180) if is_cur
                            else QColor(255, 255, 0, 80))
                        for rect in result["rects"]:
                            painter.drawRect(QRectF(
                                rect.x0 * self.zoom_level,
                                rect.y0 * self.zoom_level,
                                (rect.x1 - rect.x0) * self.zoom_level,
                                (rect.y1 - rect.y0) * self.zoom_level))

                if self._form_suggestions:
                    self._paint_form_suggestion_overlay(painter, page_num)
                if self._form_design_mode:
                    self._paint_form_designer_overlay(painter, page_num)
            finally:
                painter.end()

            widget.setPixmap(pixmap)
            self._render_form_fields(page_num, widget)

        except Exception as e:
            widget.setText(f"Error rendering page {page_num + 1}: {e}")

    def render_single_page(self):
        if not self.page_widgets:
            return
        for i, widget in enumerate(self.page_widgets):
            if i == self.current_page:
                self.render_page_content(self.current_page, widget)
                widget.setVisible(True)
            else:
                widget.setVisible(False)
        self.scroll_area.verticalScrollBar().setValue(0)
        self.update_status_bar()

    def render_continuous_pages(self):
        if not self.page_widgets:
            return
        for w in self.page_widgets:
            w.setVisible(True)
        viewport_rect = self.scroll_area.viewport().rect()
        scroll_offset = self.scroll_area.verticalScrollBar().value()
        for i, widget in enumerate(self.page_widgets):
            widget_rect   = widget.geometry()
            widget_top    = (self.scroll_area.widget()
                             .mapFromParent(widget_rect.topLeft()).y()
                             - scroll_offset)
            widget_bottom = (self.scroll_area.widget()
                             .mapFromParent(widget_rect.bottomLeft()).y()
                             - scroll_offset)
            visible = ((widget_top  < viewport_rect.bottom() + 150) and
                       (widget_bottom > viewport_rect.top()    - 150))
            if visible:
                self.render_page_content(i, widget)
            else:
                widget.clear()
        self.scroll_to_page(self.current_page)
        self.update_status_bar()

    # =========================================================================
    # Form Designer
    # =========================================================================

    def set_form_design_mode(self, enabled):
        """Switch between ordinary form filling and structural field editing."""
        enabled = bool(enabled and self.pdf_document)
        if enabled:
            self._flush_form_controls()
        self._form_design_mode = enabled
        self._clear_form_drag()
        self._radio_groups = {}
        for pairs in self.field_widgets.values():
            for control, _field in pairs:
                control.hide()
                control.deleteLater()
        self.field_widgets = {}
        if enabled:
            self.active_tool = TOOL_NONE
            self.annotation_mode = False
            self._clear_tool_buttons()
            self.selection_start_point = None
            self.selection_end_point = None
            self.current_selection_page = -1
            self.status_bar.showMessage(
                "Form Designer enabled. Choose a field tool or select an existing field."
            )
        else:
            self._selected_form_ref = None
            self.status_bar.showMessage(
                "Form Designer closed. Interactive fields are ready to fill."
            )
        self._update_cursor()
        self.refresh_forms_panel()
        self.update_view()

    # =========================================================================
    # OCR-assisted form detection
    # =========================================================================

    def detect_form_fields_current_page(self, minimum_confidence=0.65):
        """Analyse the current page and present non-destructive suggestions."""
        if not self.pdf_document:
            return
        if self._form_detection_worker is not None:
            self.status_bar.showMessage("Form detection is already running.")
            return

        page_number = int(self.current_page)
        page = self.pdf_document.load_page(page_number)
        native_words = words_from_native(page)
        tesseract_status = configure_tesseract()
        if len(native_words) < 3 and (
            not tesseract_status.available or tesseract_status.executable is None
        ):
            QMessageBox.warning(
                self,
                "Form Detection Needs OCR",
                "This page has no usable text layer, so PDF Studio needs "
                "Tesseract OCR to recognise its labels.\n\n"
                + tesseract_status.detail,
            )
            return

        try:
            matrix = fitz.Matrix(180 / 72, 180 / 72)
            pixmap = page.get_pixmap(
                matrix=matrix, colorspace=fitz.csRGB, alpha=False
            )
            vector_graphics = vector_graphics_from_page(page)
            existing_rects = [
                [field.rect.x0, field.rect.y0, field.rect.x1, field.rect.y1]
                for field in self.form_fields.get(page_number, [])
            ]
            worker = FormDetectionWorker(
                page_number=page_number,
                page_rect=(page.rect.x0, page.rect.y0, page.rect.x1, page.rect.y1),
                image_size=(pixmap.width, pixmap.height),
                image_samples=bytes(pixmap.samples),
                native_words=[asdict(word) for word in native_words],
                vector_graphics=[asdict(item) for item in vector_graphics],
                existing_field_rects=existing_rects,
                tesseract_exe=(
                    str(tesseract_status.executable)
                    if tesseract_status.available and tesseract_status.executable
                    else ""
                ),
                minimum_confidence=float(minimum_confidence),
            )
        except Exception as exc:
            QMessageBox.warning(
                self, "Form Detection",
                f"The page could not be prepared for detection.\n\n"
                f"{type(exc).__name__}: {exc}",
            )
            return

        self.clear_form_suggestions(update_view=False)
        self._form_detection_worker = worker
        self._form_detection_context = (
            os.path.abspath(self.pdf_file_path or ""), page_number
        )
        worker.detection_complete.connect(self._form_detection_finished)
        worker.error.connect(self._form_detection_failed)
        worker.finished.connect(worker.deleteLater)
        self.forms_panel.set_detection_running(True)
        self.status_bar.showMessage(
            f"Analysing page {page_number + 1} for possible form fields…"
        )
        worker.start()

    def _form_detection_finished(self, suggestions, statistics):
        worker = self._form_detection_worker
        context = self._form_detection_context
        self._form_detection_worker = None
        self._form_detection_context = None
        self.forms_panel.set_detection_running(False)
        if context is None or not self.pdf_document:
            return
        expected_path, page_number = context
        if expected_path != os.path.abspath(self.pdf_file_path or ""):
            return

        self._form_suggestions = list(suggestions or [])
        self._form_detection_statistics = dict(statistics or {})
        self._selected_form_suggestion_id = (
            self._form_suggestions[0].get("suggestion_id")
            if self._form_suggestions else None
        )
        source = statistics.get("text_source", "text")
        count = len(self._form_suggestions)
        status = (
            f"Page {page_number + 1}: {count} suggestion"
            f"{'s' if count != 1 else ''}; "
            f"{statistics.get('words', 0)} {source} words analysed. "
            "Review the checked items before creating fields."
            if count else
            f"Page {page_number + 1}: no reliable field suggestions found. "
            "Try ‘More suggestions’ or place fields manually."
        )
        self.forms_panel.set_detection_suggestions(
            self._form_suggestions, status_text=status
        )
        self.status_bar.showMessage(status)
        self.update_view()
        if self._form_suggestions:
            self.show_form_detection_review()
        if worker is not None:
            worker = None

    def _form_detection_failed(self, message):
        self._form_detection_worker = None
        self._form_detection_context = None
        self._form_detection_statistics = {}
        self.forms_panel.set_detection_running(False)
        self.forms_panel.set_detection_suggestions(
            [], status_text="Form detection could not complete."
        )
        QMessageBox.warning(self, "Form Detection", str(message))
        self.status_bar.showMessage("Form detection failed.")

    def clear_form_suggestions(self, update_view=True):
        self._form_suggestions = []
        self._selected_form_suggestion_id = None
        self._form_detection_statistics = {}
        if hasattr(self, "forms_panel"):
            self.forms_panel.set_detection_suggestions(
                [], status_text="No suggestions yet"
            )
        dialog = getattr(self, "_form_detection_dialog", None)
        if dialog is not None and dialog.isVisible():
            dialog.reject()
        if update_view and self.pdf_document:
            self.update_view()

    def show_form_detection_review(self):
        """Open the full review window for the current detector results."""
        if not self._form_suggestions:
            self.status_bar.showMessage(
                "Run Smart Form Detection before opening the review window."
            )
            return
        if self._form_detection_dialog is None:
            dialog = FormDetectionReviewDialog(self)
            dialog.suggestion_selected.connect(self.select_form_suggestion)
            dialog.create_requested.connect(self.create_checked_form_suggestions)
            dialog.clear_requested.connect(self.clear_form_suggestions)
            self._form_detection_dialog = dialog
        dialog = self._form_detection_dialog
        page_number = int(self._form_suggestions[0].get("page", self.current_page))
        dialog.set_suggestions(
            self._form_suggestions,
            page_number=page_number,
            statistics=self._form_detection_statistics,
        )
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def select_form_suggestion(self, page_number, x, y, suggestion_id):
        if not self.pdf_document:
            return
        self._selected_form_suggestion_id = str(suggestion_id or "")
        self.current_page = max(0, min(int(page_number), self.total_pages - 1))
        self.update_ui_on_page_change()
        self.jump_to_form_field(int(page_number), float(x), float(y))
        self.update_view()

    def _paint_form_suggestion_overlay(self, painter, page_number):
        matrix = fitz.Matrix(self.zoom_level, self.zoom_level).prerotate(self.rotation)
        for suggestion in self._form_suggestions:
            if int(suggestion.get("page", -1)) != int(page_number):
                continue
            rect = fitz.Rect(suggestion.get("rect", (0, 0, 0, 0))) * matrix
            selected = (
                str(suggestion.get("suggestion_id", ""))
                == str(self._selected_form_suggestion_id or "")
            )
            colour = QColor(156, 39, 176, 235) if selected else QColor(220, 90, 25, 205)
            painter.setPen(QPen(
                colour, 2 if selected else 1,
                Qt.PenStyle.SolidLine if selected else Qt.PenStyle.DashLine,
            ))
            painter.setBrush(QColor(
                colour.red(), colour.green(), colour.blue(), 32
            ))
            painter.drawRect(QRectF(rect.x0, rect.y0, rect.width, rect.height))
            confidence = int(round(float(suggestion.get("confidence", 0.0)) * 100))
            painter.setPen(colour)
            painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            painter.drawText(
                QRectF(rect.x0 + 2, max(0.0, rect.y0 - 15), 150, 14),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"{suggestion.get('kind', 'field')} {confidence}%",
            )

    def create_checked_form_suggestions(self, suggestions):
        if not self.pdf_document:
            return
        records = [record for record in (suggestions or []) if record]
        if not records:
            self.status_bar.showMessage("Check at least one suggestion first.")
            return
        reply = QMessageBox.question(
            self,
            "Create Suggested Fields",
            f"Create {len(records)} reviewed form field"
            f"{'s' if len(records) != 1 else ''}?\n\n"
            "The PDF will be marked as modified, but the original file is not "
            "changed until you save.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        created_refs = []
        failed = []
        accepted_ids = set()
        for record in records:
            created_for_record, failed_for_record = create_fields_from_suggestions(
                self.pdf_document, [record]
            )
            if created_for_record:
                created_refs.extend(created_for_record)
                accepted_ids.add(str(record.get("suggestion_id", "")))
            failed.extend(failed_for_record)
        if created_refs:
            self._form_dirty = True
            self._mark_modified()
            self._reload_form_cache()
            self._form_suggestions = [
                item for item in self._form_suggestions
                if str(item.get("suggestion_id", "")) not in accepted_ids
            ]
            self._selected_form_suggestion_id = (
                self._form_suggestions[0].get("suggestion_id")
                if self._form_suggestions else None
            )
            self.refresh_forms_panel()
            self.forms_panel.set_detection_suggestions(self._form_suggestions)
            self.update_view()
            created = len(created_refs)
            dialog = getattr(self, "_form_detection_dialog", None)
            if dialog is not None:
                if self._form_suggestions:
                    page_number = int(
                        self._form_suggestions[0].get("page", self.current_page)
                    )
                    dialog.set_suggestions(
                        self._form_suggestions,
                        page_number=page_number,
                        statistics=self._form_detection_statistics,
                    )
                else:
                    dialog.accept()
            self.status_bar.showMessage(
                f"Created {created} suggested field"
                f"{'s' if created != 1 else ''}. Save the PDF to keep them."
            )
            QMessageBox.information(
                self,
                "Suggested Fields Created",
                f"Created {created} form field"
                f"{'s' if created != 1 else ''}.\n\n"
                "Save the PDF to keep the new fields.",
            )
        if failed:
            QMessageBox.warning(
                self, "Some Suggestions Were Not Created",
                "\n".join(failed[:8]),
            )

    def set_form_designer_tool(self, tool):
        if tool not in ({FORM_TOOL_SELECT} | FORM_CREATE_TOOLS):
            return
        if not self.pdf_document:
            return
        if not self._form_design_mode:
            self.set_form_design_mode(True)
        self._form_design_tool = tool
        self._clear_form_drag()
        self._update_cursor()
        self.forms_panel.set_designer_state(
            True, self._form_design_tool, self._selected_form_record()
        )
        self._act_form_designer.blockSignals(True)
        self._act_form_designer.setChecked(True)
        self._act_form_designer.blockSignals(False)
        messages = {
            FORM_TOOL_SELECT: "Select mode: click a field, drag to move, or drag its lower-right handle to resize.",
            FORM_TOOL_TEXT: "Text Field tool: drag a rectangle on the page.",
            FORM_TOOL_CHECKBOX: "Checkbox tool: click or drag on the page.",
            FORM_TOOL_DROPDOWN: "Dropdown tool: drag a rectangle, then edit its choices in Properties.",
            FORM_TOOL_DATE: "Date tool: click or drag to add a DD/MM/YYYY field.",
            FORM_TOOL_RADIO: "Yes / No tool: click or drag to create a linked radio pair.",
            FORM_TOOL_SIGNATURE: "Signature tool: drag an unsigned PDF signature field.",
            FORM_TOOL_INITIALS: "Initials tool: click or drag an unsigned initials field.",
        }
        self.status_bar.showMessage(messages[tool])
        self.update_view()

    def _clear_form_drag(self):
        self._form_drag_action = None
        self._form_drag_page = -1
        self._form_drag_start_pdf = None
        self._form_drag_original_rect = None
        self._form_preview_rect = None

    def _selected_form_widget(self):
        if not self.pdf_document or not self._selected_form_ref:
            return None
        page_number, xref = self._selected_form_ref
        for field in self.form_fields.get(page_number, []):
            if int(field.xref) == int(xref):
                return field
        return None

    def _selected_form_record(self):
        if not self._selected_form_ref:
            return None
        page_number, xref = self._selected_form_ref
        for record in self._form_records():
            if record["page"] == page_number and int(record["xref"]) == int(xref):
                return record
        return None

    def select_form_field(self, page_number, xref):
        """Select a field from the sidebar when Form Designer is active."""
        if not self._form_design_mode or not self.pdf_document:
            return
        if not any(
            int(field.xref) == int(xref)
            for field in self.form_fields.get(int(page_number), [])
        ):
            return
        self._selected_form_ref = (int(page_number), int(xref))
        self.current_page = int(page_number)
        self.forms_panel.select_record(page_number, xref)
        self.forms_panel.set_designer_state(
            True, self._form_design_tool, self._selected_form_record()
        )
        self.update_ui_on_page_change()

    def _select_form_ref(self, page_number, xref):
        self._selected_form_ref = (int(page_number), int(xref))
        self.forms_panel.select_record(page_number, xref)
        self.forms_panel.set_designer_state(
            self._form_design_mode,
            self._form_design_tool,
            self._selected_form_record(),
        )

    def _field_at_pdf_point(self, page_number, pdf_point):
        fields = self.form_fields.get(page_number, [])
        for field in reversed(fields):
            try:
                if field.rect.contains(pdf_point):
                    return field
            except Exception:
                continue
        return None

    def _constrain_form_rect(self, page_number, rect, field_type):
        page = self.pdf_document.load_page(page_number)
        if field_type in (
            fitz.PDF_WIDGET_TYPE_CHECKBOX,
            fitz.PDF_WIDGET_TYPE_RADIOBUTTON,
        ):
            minimum = (MIN_CHECKBOX_SIZE, MIN_CHECKBOX_SIZE)
        elif field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
            minimum = MIN_SIGNATURE_SIZE
        elif field_type in (
            fitz.PDF_WIDGET_TYPE_COMBOBOX,
            fitz.PDF_WIDGET_TYPE_LISTBOX,
        ):
            minimum = MIN_CHOICE_SIZE
        else:
            minimum = MIN_TEXT_SIZE
        return normalise_rect(
            fitz.Rect(rect), page.rect,
            min_width=minimum[0], min_height=minimum[1],
        )

    def _paint_form_designer_overlay(self, painter, page_number):
        """Draw field outlines and the active drag preview onto the page pixmap."""
        matrix = fitz.Matrix(self.zoom_level, self.zoom_level).prerotate(self.rotation)
        selected_xref = (
            self._selected_form_ref[1]
            if self._selected_form_ref and self._selected_form_ref[0] == page_number
            else None
        )

        for field in self.form_fields.get(page_number, []):
            tr = field.rect * matrix
            selected = int(field.xref) == int(selected_xref or -1)
            colour = QColor(24, 115, 204, 235) if selected else QColor(30, 145, 90, 190)
            painter.setPen(QPen(colour, 2 if selected else 1, Qt.PenStyle.SolidLine))
            painter.setBrush(QColor(colour.red(), colour.green(), colour.blue(), 28))
            painter.drawRect(QRectF(tr.x0, tr.y0, tr.width, tr.height))
            if selected:
                handle = 9
                painter.setBrush(colour)
                painter.drawRect(QRectF(tr.x1 - handle, tr.y1 - handle, handle, handle))

        if self._form_preview_rect is not None and self._form_drag_page == page_number:
            tr = self._form_preview_rect * matrix
            painter.setPen(QPen(QColor(225, 120, 15, 235), 2, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(255, 165, 40, 35))
            painter.drawRect(QRectF(tr.x0, tr.y0, tr.width, tr.height))

    def _handle_form_designer_press(self, event, page_widget, page_number, px, py):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pdf_point = self._to_pdf_point(px, py)
        if pdf_point is None:
            return
        page_rect = self.pdf_document.load_page(page_number).rect
        if not page_rect.contains(pdf_point):
            return

        self._form_drag_page = page_number
        self._form_drag_start_pdf = pdf_point

        if self._form_design_tool in FORM_CREATE_TOOLS:
            self._form_drag_action = "create"
            self._form_preview_rect = fitz.Rect(pdf_point, pdf_point)
            self.render_page_content(page_number, page_widget)
            return

        field = self._field_at_pdf_point(page_number, pdf_point)
        if field is None:
            self._selected_form_ref = None
            self._clear_form_drag()
            self.forms_panel.set_designer_state(True, self._form_design_tool, None)
            self.update_view()
            return

        self._select_form_ref(page_number, field.xref)
        self._form_drag_original_rect = fitz.Rect(field.rect)
        transformed = field.rect * fitz.Matrix(
            self.zoom_level, self.zoom_level
        ).prerotate(self.rotation)
        near_handle = abs(px - transformed.x1) <= 12 and abs(py - transformed.y1) <= 12
        self._form_drag_action = "resize" if near_handle else "move"
        self._form_preview_rect = fitz.Rect(field.rect)
        self.render_page_content(page_number, page_widget)

    def _handle_form_designer_move(self, event, page_widget, page_number, px, py):
        if (
            self._form_drag_action is None
            or self._form_drag_page != page_number
            or not (event.buttons() & Qt.MouseButton.LeftButton)
        ):
            return
        current = self._to_pdf_point(px, py)
        if current is None or self._form_drag_start_pdf is None:
            return

        if self._form_drag_action == "create":
            rect = fitz.Rect(self._form_drag_start_pdf, current)
            field_type = {
                FORM_TOOL_CHECKBOX: fitz.PDF_WIDGET_TYPE_CHECKBOX,
                FORM_TOOL_DROPDOWN: fitz.PDF_WIDGET_TYPE_COMBOBOX,
                FORM_TOOL_RADIO: fitz.PDF_WIDGET_TYPE_RADIOBUTTON,
                FORM_TOOL_SIGNATURE: fitz.PDF_WIDGET_TYPE_SIGNATURE,
                FORM_TOOL_INITIALS: fitz.PDF_WIDGET_TYPE_SIGNATURE,
            }.get(self._form_design_tool, fitz.PDF_WIDGET_TYPE_TEXT)
            if self._form_design_tool == FORM_TOOL_RADIO:
                page = self.pdf_document.load_page(page_number)
                self._form_preview_rect = normalise_rect(
                    rect, page.rect,
                    min_width=MIN_CHECKBOX_SIZE * 2,
                    min_height=MIN_CHECKBOX_SIZE,
                )
            else:
                self._form_preview_rect = self._constrain_form_rect(
                    page_number, rect, field_type
                )
        elif self._form_drag_original_rect is not None:
            field = self._selected_form_widget()
            if field is None:
                return
            original = fitz.Rect(self._form_drag_original_rect)
            if self._form_drag_action == "move":
                dx = current.x - self._form_drag_start_pdf.x
                dy = current.y - self._form_drag_start_pdf.y
                rect = fitz.Rect(
                    original.x0 + dx, original.y0 + dy,
                    original.x1 + dx, original.y1 + dy,
                )
            else:
                rect = fitz.Rect(original.x0, original.y0, current.x, current.y)
            self._form_preview_rect = self._constrain_form_rect(
                page_number, rect, field.field_type
            )
        self.render_page_content(page_number, page_widget)

    def _handle_form_designer_release(self, event, page_widget, page_number, px, py):
        if event.button() != Qt.MouseButton.LeftButton or self._form_drag_action is None:
            return
        if self._form_drag_page != page_number:
            self._clear_form_drag()
            return

        action = self._form_drag_action
        preview = fitz.Rect(self._form_preview_rect) if self._form_preview_rect else None
        start = self._form_drag_start_pdf
        try:
            if action == "create":
                if start is None:
                    return
                current = self._to_pdf_point(px, py) or start
                dragged = abs(current.x - start.x) >= 4 or abs(current.y - start.y) >= 4
                if not dragged:
                    default_width, default_height = {
                        FORM_TOOL_TEXT: DEFAULT_TEXT_SIZE,
                        FORM_TOOL_CHECKBOX: (DEFAULT_CHECKBOX_SIZE, DEFAULT_CHECKBOX_SIZE),
                        FORM_TOOL_DROPDOWN: DEFAULT_DROPDOWN_SIZE,
                        FORM_TOOL_DATE: DEFAULT_DATE_SIZE,
                        FORM_TOOL_RADIO: DEFAULT_RADIO_GROUP_SIZE,
                        FORM_TOOL_SIGNATURE: DEFAULT_SIGNATURE_SIZE,
                        FORM_TOOL_INITIALS: DEFAULT_INITIALS_SIZE,
                    }[self._form_design_tool]
                    preview = fitz.Rect(
                        start.x, start.y,
                        start.x + default_width, start.y + default_height,
                    )

                if self._form_design_tool == FORM_TOOL_TEXT:
                    field = add_text_field(self.pdf_document, page_number, preview)
                    created_fields = [field]
                elif self._form_design_tool == FORM_TOOL_CHECKBOX:
                    field = add_checkbox_field(self.pdf_document, page_number, preview)
                    created_fields = [field]
                elif self._form_design_tool == FORM_TOOL_DROPDOWN:
                    field = add_dropdown_field(self.pdf_document, page_number, preview)
                    created_fields = [field]
                elif self._form_design_tool == FORM_TOOL_DATE:
                    field = add_date_field(self.pdf_document, page_number, preview)
                    created_fields = [field]
                elif self._form_design_tool == FORM_TOOL_RADIO:
                    created_fields = add_radio_group(
                        self.pdf_document, page_number, preview
                    )
                    field = created_fields[0]
                elif self._form_design_tool == FORM_TOOL_SIGNATURE:
                    field = add_signature_field(
                        self.pdf_document, page_number, preview, initials=False
                    )
                    created_fields = [field]
                else:
                    field = add_signature_field(
                        self.pdf_document, page_number, preview, initials=True
                    )
                    created_fields = [field]

                selected_ref = (page_number, int(field.xref))
                if len(created_fields) > 1:
                    message = f"Added linked Yes / No radio group '{field.field_name}'."
                else:
                    message = (
                        f"Added {self._form_field_type_name(field)} "
                        f"'{field.field_name}'."
                    )
            else:
                if preview is None or not self._selected_form_ref:
                    return
                selected_ref = self._selected_form_ref
                field = move_or_resize_widget(
                    self.pdf_document, selected_ref[0], selected_ref[1], preview
                )
                message = (
                    f"{'Resized' if action == 'resize' else 'Moved'} field "
                    f"'{field.field_name}'."
                )

            self._form_dirty = True
            self._mark_modified()
            self._reload_form_cache()
            self._selected_form_ref = selected_ref
            self.refresh_forms_panel()
            self.forms_panel.select_record(*selected_ref)
            self.status_bar.showMessage(message + " Save the PDF to keep this change.")
        except Exception as exc:
            QMessageBox.warning(
                self, "Form Designer",
                f"The field could not be changed.\n\n{type(exc).__name__}: {exc}",
            )
        finally:
            self._clear_form_drag()
            self.update_view()

    def delete_selected_form_field(self):
        field = self._selected_form_widget()
        if field is None or not self._selected_form_ref:
            self.status_bar.showMessage("Select a form field first.")
            return
        page_number, xref = self._selected_form_ref
        name = field.field_name or "Unnamed field"
        reply = QMessageBox.question(
            self, "Delete Form Field",
            f'Delete the field "{name}" from page {page_number + 1}?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            if not delete_form_widget_core(self.pdf_document, page_number, xref):
                raise LookupError("The selected field no longer exists.")
            self._selected_form_ref = None
            self._form_dirty = True
            self._mark_modified()
            self._reload_form_cache()
            self.refresh_forms_panel()
            self.update_view()
            self.status_bar.showMessage(
                f'Deleted field "{name}". Save the PDF to keep this change.'
            )
        except Exception as exc:
            QMessageBox.warning(self, "Delete Form Field", str(exc))

    def edit_selected_form_properties(self):
        field = self._selected_form_widget()
        if field is None or not self._selected_form_ref:
            self.status_bar.showMessage("Select a form field first.")
            return
        if field.field_type not in (
            fitz.PDF_WIDGET_TYPE_TEXT,
            fitz.PDF_WIDGET_TYPE_CHECKBOX,
            fitz.PDF_WIDGET_TYPE_COMBOBOX,
            fitz.PDF_WIDGET_TYPE_RADIOBUTTON,
            fitz.PDF_WIDGET_TYPE_SIGNATURE,
        ):
            QMessageBox.information(
                self, "Form Field Properties",
                "Properties are not editable for this field type. It can still "
                "be moved, resized, or deleted.",
            )
            return
        dialog = FormFieldPropertiesDialog(
            field, self,
            custom_kind=widget_custom_kind(self.pdf_document, int(field.xref)),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        page_number, xref = self._selected_form_ref
        try:
            update_widget_properties(
                self.pdf_document, page_number, xref, **dialog.values()
            )
            self._form_dirty = True
            self._mark_modified()
            self._reload_form_cache()
            self._selected_form_ref = (page_number, xref)
            self.refresh_forms_panel()
            self.forms_panel.select_record(page_number, xref)
            self.update_view()
            self.status_bar.showMessage("Form field properties updated.")
        except ValueError as exc:
            QMessageBox.warning(self, "Form Field Properties", str(exc))
        except Exception as exc:
            QMessageBox.warning(
                self, "Form Field Properties",
                f"The field could not be updated.\n\n{type(exc).__name__}: {exc}",
            )

    # =========================================================================
    # Existing AcroForm fields
    # =========================================================================

    def _reload_form_cache(self):
        """Reload pages and live Widget objects from the current document."""
        self.form_fields = {}
        self.field_widgets = {}
        self._radio_groups = {}
        self.pages = []
        if not self.pdf_document:
            return
        for pn in range(self.pdf_document.page_count):
            page = self.pdf_document.load_page(pn)
            self.pages.append(page)
            self.form_fields[pn] = list(page.widgets() or [])

    @staticmethod
    def _form_field_type_name(field):
        return getattr(field, "field_type_string", None) or {
            fitz.PDF_WIDGET_TYPE_BUTTON: "Button",
            fitz.PDF_WIDGET_TYPE_CHECKBOX: "Checkbox",
            fitz.PDF_WIDGET_TYPE_COMBOBOX: "Dropdown",
            fitz.PDF_WIDGET_TYPE_LISTBOX: "List",
            fitz.PDF_WIDGET_TYPE_RADIOBUTTON: "Radio",
            fitz.PDF_WIDGET_TYPE_SIGNATURE: "Signature",
            fitz.PDF_WIDGET_TYPE_TEXT: "Text",
        }.get(field.field_type, "Unknown")

    def _form_records(self):
        records = []
        for page_num, fields in self.form_fields.items():
            for field in fields:
                flags = int(getattr(field, "field_flags", 0) or 0)
                rect = field.rect
                kind = widget_custom_kind(self.pdf_document, int(field.xref))
                type_name = self._form_field_type_name(field)
                if kind == KIND_DATE:
                    type_name = "Date"
                elif kind == KIND_INITIALS:
                    type_name = "Initials"
                option = radio_option_label(self.pdf_document, int(field.xref))
                records.append({
                    "page": page_num,
                    "name": field.field_name or getattr(field, "field_label", "") or "Unnamed field",
                    "type": field.field_type,
                    "type_name": type_name + (f" ({option})" if option else ""),
                    "value": field.field_value,
                    "required": bool(flags & fitz.PDF_FIELD_IS_REQUIRED),
                    "read_only": bool(flags & fitz.PDF_FIELD_IS_READ_ONLY),
                    "rect": [rect.x0, rect.y0, rect.x1, rect.y1],
                    "xref": field.xref,
                })
        return records

    def refresh_forms_panel(self):
        records = self._form_records() if self.pdf_document else []
        self.forms_panel.set_document_fields(
            records, document_open=bool(self.pdf_document)
        )
        self.forms_panel.set_highlight_checked(self._form_highlighting)
        self.forms_panel.set_designer_state(
            self._form_design_mode,
            self._form_design_tool,
            self._selected_form_record(),
        )
        has_fields = bool(records)
        self._act_reset_form.setEnabled(has_fields)
        self._act_reset_all_forms.setEnabled(has_fields)
        self._act_flatten_form.setEnabled(has_fields)
        self._act_form_designer.blockSignals(True)
        self._act_form_designer.setChecked(self._form_design_mode)
        self._act_detect_form_fields.setEnabled(bool(self.pdf_document))
        self._act_form_designer.blockSignals(False)
        has_selected = bool(self._form_design_mode and self._selected_form_record())
        self._act_form_properties.setEnabled(has_selected)
        self._act_delete_form_field.setEnabled(has_selected)
        if has_fields:
            self.status_bar.showMessage(
                f"Interactive form detected: {len(records)} field"
                f"{'s' if len(records) != 1 else ''}. Use the Forms panel to fill it."
            )

    def _field_tooltip(self, field, note=""):
        flags = int(getattr(field, "field_flags", 0) or 0)
        parts = [
            field.field_name or getattr(field, "field_label", "") or "Unnamed field",
            self._form_field_type_name(field),
        ]
        if flags & fitz.PDF_FIELD_IS_REQUIRED:
            parts.append("Required")
        if flags & fitz.PDF_FIELD_IS_READ_ONLY:
            parts.append("Read-only")
        if note:
            parts.append(note)
        return " · ".join(parts)

    def _style_form_widget(self, qt_widget, field, rect_height=None):
        flags = int(getattr(field, "field_flags", 0) or 0)
        read_only = bool(flags & fitz.PDF_FIELD_IS_READ_ONLY)
        base = {"medium": 13, "large": 16, "xlarge": 20}.get(
            getattr(self, "ui_size", "medium"), 13)
        font_size = max(10, min(base, int((rect_height or 22) * 0.6)))

        if self._form_highlighting:
            border = "#8a6d00" if read_only else "#2675c7"
            background = "rgba(245,240,205,190)" if read_only else "rgba(220,238,255,205)"
        else:
            border = "transparent"
            background = "rgba(255,255,255,18)"

        qt_widget.setStyleSheet(
            f"border: 1px solid {border}; background: {background}; "
            f"border-radius: 2px; font-size: {font_size}px;"
        )
        qt_widget.setEnabled(not read_only)

    def _render_form_fields(self, page_num, widget):
        if page_num in self.field_widgets:
            for qt_widget, _field in self.field_widgets[page_num]:
                qt_widget.hide()
                qt_widget.deleteLater()
            del self.field_widgets[page_num]

        fields = self.form_fields.get(page_num, [])
        if self._form_design_mode or not fields:
            return

        label_size = widget.size()
        pixmap_size = widget.pixmap().size() if widget.pixmap() else QSize(0, 0)
        x_offset = (label_size.width() - pixmap_size.width()) // 2
        y_offset = (label_size.height() - pixmap_size.height()) // 2
        matrix = fitz.Matrix(self.zoom_level, self.zoom_level).prerotate(self.rotation)
        self.field_widgets[page_num] = []

        for field in fields:
            tr = field.rect * matrix
            x = int(tr.x0 + x_offset)
            y = int(tr.y0 + y_offset)
            width = max(12, int(tr.width))
            height = max(12, int(tr.height))
            ftype = field.field_type
            flags = int(getattr(field, "field_flags", 0) or 0)
            value = field.field_value
            qt_widget = None

            if ftype == fitz.PDF_WIDGET_TYPE_TEXT:
                kind = widget_custom_kind(self.pdf_document, int(field.xref))
                multiline = bool(flags & fitz.PDF_TX_FIELD_IS_MULTILINE)
                if kind == KIND_DATE:
                    qt_widget = QDateEdit(widget)
                    qt_widget.setCalendarPopup(True)
                    qt_widget.setDisplayFormat("dd/MM/yyyy")
                    empty_date = QDate(1900, 1, 1)
                    qt_widget.setMinimumDate(empty_date)
                    qt_widget.setSpecialValueText("Not set")
                    parsed = QDate.fromString(str(value or ""), "dd/MM/yyyy")
                    qt_widget.setDate(parsed if parsed.isValid() else empty_date)
                    qt_widget.dateChanged.connect(
                        lambda date, f=field, sentinel=empty_date:
                            self._update_pdf_field(
                                f, "" if date == sentinel else date.toString("dd/MM/yyyy")
                            )
                    )
                elif multiline:
                    qt_widget = QTextEdit(widget)
                    qt_widget.setPlainText(str(value or ""))
                    qt_widget.textChanged.connect(
                        lambda f=field, control=qt_widget:
                            self._update_pdf_field(f, control.toPlainText())
                    )
                else:
                    qt_widget = QLineEdit(widget)
                    qt_widget.setText(str(value or ""))
                    if flags & fitz.PDF_TX_FIELD_IS_PASSWORD:
                        qt_widget.setEchoMode(QLineEdit.EchoMode.Password)
                    max_len = int(getattr(field, "text_maxlen", 0) or 0)
                    if max_len > 0:
                        qt_widget.setMaxLength(max_len)
                    qt_widget.textEdited.connect(
                        lambda text, f=field: self._update_pdf_field(f, text)
                    )
                qt_widget.setGeometry(x, y, width, height)

            elif ftype == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                qt_widget = QCheckBox(widget)
                qt_widget.setChecked(value not in (None, "", "Off", False, 0))
                size = max(16, min(width, height))
                qt_widget.setGeometry(x, y, size, size)
                qt_widget.toggled.connect(
                    lambda checked, f=field: self._save_button_field(f, checked)
                )

            elif ftype == fitz.PDF_WIDGET_TYPE_RADIOBUTTON:
                qt_widget = QRadioButton(widget)
                qt_widget.setChecked(value not in (None, "", "Off", False, 0))
                size = max(16, min(width, height))
                qt_widget.setGeometry(x, y, size, size)
                group_key = (page_num, field.field_name or f"xref-{field.xref}")
                group = self._radio_groups.get(group_key)
                if group is None:
                    group = QButtonGroup(widget)
                    group.setExclusive(True)
                    self._radio_groups[group_key] = group
                group.addButton(qt_widget)
                qt_widget.toggled.connect(
                    lambda checked, f=field:
                        self._save_button_field(f, True) if checked else None
                )

            elif ftype == fitz.PDF_WIDGET_TYPE_COMBOBOX:
                qt_widget = QComboBox(widget)
                choices = [str(choice) for choice in (field.choice_values or [])]
                qt_widget.addItems(choices)
                qt_widget.setEditable(bool(flags & fitz.PDF_CH_FIELD_IS_EDIT))
                if value not in (None, ""):
                    idx = qt_widget.findText(str(value))
                    if idx >= 0:
                        qt_widget.setCurrentIndex(idx)
                    elif qt_widget.isEditable():
                        qt_widget.setEditText(str(value))
                qt_widget.setGeometry(x, y, width, height)
                qt_widget.currentTextChanged.connect(
                    lambda text, f=field: self._update_pdf_field(f, text)
                )

            elif ftype == fitz.PDF_WIDGET_TYPE_LISTBOX:
                qt_widget = QListWidget(widget)
                multi = bool(flags & fitz.PDF_CH_FIELD_IS_MULTI_SELECT)
                # PyMuPDF 1.26 cannot write a Python list to /V reliably.
                # Keep editing deterministic by allowing one saved selection.
                qt_widget.setSelectionMode(
                    QAbstractItemView.SelectionMode.SingleSelection
                )
                selected = set(value if isinstance(value, (list, tuple)) else [value])
                for choice in (field.choice_values or []):
                    item = QListWidgetItem(str(choice))
                    qt_widget.addItem(item)
                    item.setSelected(choice in selected or str(choice) in {str(v) for v in selected})
                qt_widget.setGeometry(x, y, width, max(height, 42))
                qt_widget.itemSelectionChanged.connect(
                    lambda f=field, control=qt_widget:
                        self._save_list_field(f, control)
                )
                if multi:
                    qt_widget.setToolTip(self._field_tooltip(
                        field, "Multi-select form detected; this release saves one selection"))

            elif ftype == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                kind = widget_custom_kind(self.pdf_document, int(field.xref))
                unsigned_label = "Initials field" if kind == KIND_INITIALS else "Signature field"
                qt_widget = QPushButton(
                    "Signed" if bool(getattr(field, "is_signed", False)) else unsigned_label,
                    widget,
                )
                qt_widget.setGeometry(x, y, width, height)
                qt_widget.setEnabled(False)
                qt_widget.setToolTip(self._field_tooltip(
                    field, "Detected; cryptographic PDF signing is not yet supported"))

            elif ftype == fitz.PDF_WIDGET_TYPE_BUTTON:
                caption = getattr(field, "button_caption", None) or "PDF button"
                qt_widget = QPushButton(str(caption), widget)
                qt_widget.setGeometry(x, y, width, height)
                qt_widget.setEnabled(False)
                qt_widget.setToolTip(self._field_tooltip(
                    field, "Disabled because embedded PDF actions and JavaScript are not executed"))

            else:
                qt_widget = QLabel("Unsupported field", widget)
                qt_widget.setGeometry(x, y, width, height)

            if qt_widget is None:
                continue
            if ftype not in (fitz.PDF_WIDGET_TYPE_SIGNATURE, fitz.PDF_WIDGET_TYPE_BUTTON):
                if not qt_widget.toolTip():
                    qt_widget.setToolTip(self._field_tooltip(field))
                self._style_form_widget(qt_widget, field, height)
            self.field_widgets[page_num].append((qt_widget, field))
            qt_widget.show()

        widget.update()

    def _reposition_form_fields(self, page_num, widget):
        """Reposition existing Qt form controls when a page label resizes."""
        if self._form_design_mode:
            return
        pairs = self.field_widgets.get(page_num, [])
        if not pairs:
            return
        label_size = widget.size()
        pixmap_size = widget.pixmap().size() if widget.pixmap() else QSize(0, 0)
        x_offset = (label_size.width() - pixmap_size.width()) // 2
        y_offset = (label_size.height() - pixmap_size.height()) // 2
        matrix = fitz.Matrix(self.zoom_level, self.zoom_level).prerotate(self.rotation)
        for qt_widget, field in pairs:
            tr = field.rect * matrix
            width = max(12, int(tr.width))
            height = max(12, int(tr.height))
            if field.field_type in (fitz.PDF_WIDGET_TYPE_CHECKBOX,
                                    fitz.PDF_WIDGET_TYPE_RADIOBUTTON):
                width = height = max(16, min(width, height))
            elif field.field_type == fitz.PDF_WIDGET_TYPE_LISTBOX:
                height = max(height, 42)
            qt_widget.setGeometry(
                int(tr.x0 + x_offset), int(tr.y0 + y_offset), width, height)

    def _update_pdf_field(self, field, value, mark_modified=True):
        try:
            if field.field_value == value:
                return
            field.field_value = value
            field.update()
            if mark_modified:
                self._form_dirty = True
                self._mark_modified()
        except Exception as exc:
            self.status_bar.showMessage(f"Field update error: {exc}")

    def _save_button_field(self, field, checked):
        # PyMuPDF resolves True to the field's actual PDF on-state name.
        self._update_pdf_field(field, bool(checked))

    def _save_list_field(self, field, control):
        values = [item.text() for item in control.selectedItems()]
        self._update_pdf_field(field, values[0] if values else "")

    def _flush_form_controls(self):
        """Push every visible control into its Widget before saving/copying."""
        for pairs in self.field_widgets.values():
            for control, field in pairs:
                if isinstance(control, QLineEdit):
                    self._update_pdf_field(field, control.text(), mark_modified=False)
                elif isinstance(control, QTextEdit):
                    self._update_pdf_field(field, control.toPlainText(), mark_modified=False)
                elif isinstance(control, QDateEdit):
                    date = control.date()
                    value = "" if date == control.minimumDate() else date.toString("dd/MM/yyyy")
                    self._update_pdf_field(field, value, mark_modified=False)
                elif isinstance(control, QCheckBox):
                    self._update_pdf_field(field, control.isChecked(), mark_modified=False)
                elif isinstance(control, QRadioButton) and control.isChecked():
                    self._update_pdf_field(field, True, mark_modified=False)
                elif isinstance(control, QComboBox):
                    self._update_pdf_field(field, control.currentText(), mark_modified=False)
                elif isinstance(control, QListWidget):
                    values = [item.text() for item in control.selectedItems()]
                    self._update_pdf_field(
                        field, values[0] if values else "", mark_modified=False)

    def set_form_highlighting(self, enabled):
        self._form_highlighting = bool(enabled)
        for pairs in self.field_widgets.values():
            for control, field in pairs:
                if field.field_type not in (fitz.PDF_WIDGET_TYPE_SIGNATURE,
                                            fitz.PDF_WIDGET_TYPE_BUTTON):
                    self._style_form_widget(control, field, control.height())

    def jump_to_form_field(self, page_num, x, y):
        if not self.pdf_document or not (0 <= page_num < self.total_pages):
            return
        self.current_page = page_num
        self.update_ui_on_page_change()
        self.scroll_to_page(page_num)
        from PyQt6.QtCore import QTimer

        def focus_matching_control():
            for control, field in self.field_widgets.get(page_num, []):
                if abs(field.rect.x0 - x) < 1 and abs(field.rect.y0 - y) < 1:
                    if control.isEnabled():
                        control.setFocus()
                    break
        QTimer.singleShot(0, focus_matching_control)

    def _reset_form_pages(self, page_numbers):
        changed = 0
        try:
            for page_num in page_numbers:
                page = self.pdf_document.load_page(page_num)
                for field in list(page.widgets() or []):
                    default = getattr(field, "field_value_default", None)
                    if field.field_type in (fitz.PDF_WIDGET_TYPE_CHECKBOX,
                                            fitz.PDF_WIDGET_TYPE_RADIOBUTTON):
                        field.field_value = default not in (None, "", "Off", False, 0)
                    else:
                        field.field_value = default or ""
                    field.update()
                    changed += 1
            self._reload_form_cache()
            self._form_dirty = bool(changed)
            if changed:
                self._mark_modified()
            self.update_view()
            self.refresh_forms_panel()
            return changed
        except Exception as exc:
            QMessageBox.critical(self, "Reset Form Error", str(exc))
            return 0

    def reset_form(self):
        if not self.pdf_document:
            return
        fields = self.form_fields.get(self.current_page, [])
        if not fields:
            self.status_bar.showMessage("No form fields on this page.")
            return
        reply = QMessageBox.question(
            self, "Reset Form Page",
            f"Reset all {len(fields)} form field(s) on page {self.current_page + 1}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            changed = self._reset_form_pages([self.current_page])
            self.status_bar.showMessage(f"Reset {changed} field(s) on this page.")

    def reset_all_forms(self):
        if not self.pdf_document:
            return
        count = sum(len(fields) for fields in self.form_fields.values())
        if not count:
            self.status_bar.showMessage("This document has no form fields.")
            return
        reply = QMessageBox.warning(
            self, "Reset Entire Form",
            f"Reset all {count} form fields in this document?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            changed = self._reset_form_pages(range(self.total_pages))
            self.status_bar.showMessage(f"Reset {changed} form field(s).")

    def flatten_form_to_copy(self):
        """Bake widget appearances into a separate PDF, preserving the source."""
        if not self.pdf_document:
            return
        count = sum(len(fields) for fields in self.form_fields.values())
        if not count:
            QMessageBox.information(self, "Flatten Form",
                                    "This document has no interactive form fields.")
            return

        base, _ext = os.path.splitext(self.pdf_file_path or "form.pdf")
        default = base + "_filled_flattened.pdf"
        output_path, _ = QFileDialog.getSaveFileName(
            self, "Flatten Form to Copy", default, "PDF Files (*.pdf)")
        if not output_path:
            return
        if not output_path.lower().endswith(".pdf"):
            output_path += ".pdf"
        if self.pdf_file_path and os.path.abspath(output_path) == os.path.abspath(self.pdf_file_path):
            QMessageBox.warning(
                self, "Choose a Different File",
                "Flattening is intentionally copy-only. Choose a different filename "
                "so the editable original is preserved.")
            return

        reply = QMessageBox.warning(
            self, "Create Flattened Copy",
            "The new copy will preserve the visible answers but its form fields "
            "will no longer be editable.\n\n"
            "The original PDF will not be changed.\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self._autosave_form_data()
            flattened_count = flatten_form_atomic(
                self.pdf_document,
                output_path,
                prepare_clone=lambda clone: self._prepare_document_for_save(
                    clone, autosave_forms=False, mark_baked=False),
            )
            QMessageBox.information(
                self, "Flattened Copy Created",
                f"Created a non-editable filled copy with {flattened_count} field(s) baked "
                f"into the pages:\n\n{output_path}\n\n"
                "The original remains editable.")
            self.status_bar.showMessage(f"Flattened form copy saved: {output_path}")
        except Exception as exc:
            QMessageBox.critical(
                self, "Flatten Form Error",
                "The flattened copy could not be created. The existing destination "
                "and the open original were preserved.\n\n"
                f"{type(exc).__name__}: {exc}")

    # =========================================================================
    # OCR-assisted scanned-text replacement
    # =========================================================================

    def _release_scan_text_mouse_grab(self):
        widget = self._scan_text_mouse_grab_widget
        self._scan_text_mouse_grab_widget = None
        if widget is not None:
            try:
                widget.releaseMouse()
            except RuntimeError:
                pass

    def _show_scan_text_progress(self, page_number):
        self._close_scan_text_progress()
        progress = QProgressDialog(
            f"Recognising the selected text on page {int(page_number) + 1}…",
            "",
            0,
            0,
            self,
        )
        progress.setWindowTitle("Preparing Scanned-Text Editor")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        self._scan_text_progress = progress
        progress.show()
        QApplication.processEvents()

    def _close_scan_text_progress(self):
        progress = self._scan_text_progress
        self._scan_text_progress = None
        if progress is not None:
            progress.close()
            progress.deleteLater()

    def _begin_scan_text_edit(self, page_number, pdf_rect):
        """Render one selected region and recognise its existing text."""
        if not self.pdf_document or self._scan_text_worker is not None:
            return
        try:
            page = self.pdf_document.load_page(int(page_number))
            rect = fitz.Rect(pdf_rect)
            rect.normalize()
            rect &= page.rect
            if rect.is_empty or rect.width < 8 or rect.height < 8:
                self.status_bar.showMessage(
                    "The selected area is too small for scanned-text editing."
                )
                return

            # Roughly 216 DPI gives Tesseract enough detail without creating a
            # large full-page bitmap. Only the selected rectangle is rendered.
            matrix = fitz.Matrix(3.0, 3.0)
            pix = page.get_pixmap(
                matrix=matrix, clip=rect, colorspace=fitz.csRGB, alpha=False
            )
            image_samples = bytes(pix.samples)
            preview_image = QImage(
                image_samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format.Format_RGB888,
            ).copy()

            from PIL import Image

            pil_image = Image.frombytes(
                "RGB", (pix.width, pix.height), image_samples
            )
            background_rgb = sample_background_rgb(pil_image)
            self._scan_text_context = {
                "document_token": id(self.pdf_document),
                "page_number": int(page_number),
                "pdf_rect": tuple(rect),
                "preview_image": preview_image,
                "background_rgb": background_rgb,
                "ocr_result_received": False,
            }

            # Prefer an existing text layer when present. This avoids OCR drift
            # on already-searchable scans while keeping the same edit workflow.
            native_text = page.get_textbox(rect).strip()
            if native_text:
                self._show_scan_text_dialog(
                    native_text,
                    0.0,
                    recognition_note="Existing PDF text layer used",
                )
                return

            status = configure_tesseract()
            if not status.available or status.executable is None:
                QMessageBox.warning(
                    self,
                    "OCR Unavailable",
                    status.detail
                    + "\n\nThe replacement editor will still open so you can "
                    "type the new text manually.",
                )
                self._show_scan_text_dialog(
                    "",
                    0.0,
                    recognition_note="OCR unavailable - enter text manually",
                )
                return

            worker = ScanTextOCRWorker(
                image_size=(pix.width, pix.height),
                image_samples=image_samples,
                tesseract_exe=str(status.executable),
                language="eng",
                parent=self,
            )
            self._scan_text_worker = worker
            worker.completed.connect(self._scan_text_ocr_completed)
            worker.error.connect(self._scan_text_ocr_failed)
            worker.finished.connect(self._scan_text_ocr_finished)
            self.status_bar.showMessage(
                f"Recognising selected text on page {int(page_number) + 1}..."
            )
            self._show_scan_text_progress(page_number)
            worker.start()
        except Exception as exc:
            self._close_scan_text_progress()
            self._scan_text_context = None
            QMessageBox.critical(
                self,
                "Scanned Text Error",
                f"The selected region could not be prepared.\n\n"
                f"{type(exc).__name__}: {exc}",
            )

    def _scan_text_ocr_completed(self, recognised_text, confidence):
        if self._scan_text_context is not None:
            self._scan_text_context["ocr_result_received"] = True
        self._close_scan_text_progress()
        self._show_scan_text_dialog(str(recognised_text), float(confidence))

    def _scan_text_ocr_failed(self, detail):
        if self._scan_text_context is not None:
            self._scan_text_context["ocr_result_received"] = True
        self._close_scan_text_progress()
        QMessageBox.warning(
            self,
            "OCR Could Not Read This Region",
            "Tesseract could not recognise the selected area. You can still "
            "type replacement text manually.\n\n" + str(detail),
        )
        self._show_scan_text_dialog(
            "",
            0.0,
            recognition_note="OCR failed - enter text manually",
        )

    def _scan_text_ocr_finished(self):
        worker = self.sender()
        if worker is self._scan_text_worker:
            self._scan_text_worker = None
        if worker is not None:
            worker.deleteLater()

        # Let any queued completed/error signal run before deciding that the
        # thread ended without a result. This prevents a signal-order race on
        # fast Windows machines.
        QTimer.singleShot(0, self._scan_text_missing_result_fallback)

    def _scan_text_missing_result_fallback(self):
        context = self._scan_text_context
        if context and not context.get("ocr_result_received", False):
            self._close_scan_text_progress()
            context["ocr_result_received"] = True
            QMessageBox.warning(
                self,
                "OCR Ended Unexpectedly",
                "The OCR task ended without returning a result. The editor will "
                "open so you can enter the replacement manually.",
            )
            self._show_scan_text_dialog(
                "",
                0.0,
                recognition_note="OCR ended unexpectedly - enter text manually",
            )

    def _show_scan_text_dialog(
        self, recognised_text, confidence, *, recognition_note=""
    ):
        self._close_scan_text_progress()
        context = self._scan_text_context
        if (
            not context
            or not self.pdf_document
            or context.get("document_token") != id(self.pdf_document)
        ):
            self._scan_text_context = None
            return

        dialog = ScanTextEditDialog(
            page_number=context["page_number"],
            pdf_rect=context["pdf_rect"],
            preview_image=context["preview_image"],
            recognised_text=str(recognised_text or ""),
            ocr_confidence=float(confidence or 0.0),
            background_rgb=context["background_rgb"],
            recognition_note=recognition_note,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self._scan_text_context = None
            self.status_bar.showMessage("Scanned-text replacement cancelled.")
            return

        plan = dialog.replacement_plan()
        if plan.mode == SCAN_MODE_REDACT:
            reply = QMessageBox.warning(
                self,
                "Apply Permanent Replacement",
                "Permanent mode removes page text, line art, and image pixels "
                "inside the selected rectangle before inserting the replacement.\n\n"
                "It cannot be undone in the current editing session. Saving will "
                "require a new filename so the original PDF remains preserved.\n\n"
                "Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self._scan_text_context = None
                self.status_bar.showMessage("Permanent replacement cancelled.")
                return

        try:
            result = apply_scan_text_replacement(self.pdf_document, plan)
            if result["mode"] == SCAN_MODE_OVERLAY:
                self._undo_stack.push(
                    Command(
                        kind="scan_text_overlay",
                        redo_data={"plan": asdict(plan)},
                        undo_data={
                            "page": int(result["page_number"]),
                            "annotation_xref": int(result["annotation_xref"]),
                        },
                    )
                )
                self._mark_modified()
                message = (
                    "Reversible text replacement added. It can be removed from "
                    "the Annotations panel."
                )
            else:
                self._requires_full_rewrite = True
                self._mark_modified()
                message = (
                    "Permanent replacement applied. Use Save As to write a clean "
                    "edited copy while preserving the original."
                )

            page_number = int(result["page_number"])
            self._scan_text_context = None
            self.selection_start_point = None
            self.selection_end_point = None
            self.current_selection_page = -1
            self.render_page_content(page_number, self.page_widgets[page_number])
            self.refresh_annotations_panel()
            self._update_undo_redo_labels()
            self.status_bar.showMessage(message)
        except Exception as exc:
            self._scan_text_context = None
            QMessageBox.critical(
                self,
                "Replacement Failed",
                "The document was not saved.\n\n"
                f"{type(exc).__name__}: {exc}",
            )

    # =========================================================================
    # Mouse interaction on pages
    # =========================================================================

    def _pixel_coords(self, event, page_widget):
        """Returns click position relative to the rendered pixmap top-left."""
        pixmap = page_widget.pixmap()
        if not pixmap:
            return None, None
        label_size  = page_widget.size()
        pixmap_size = pixmap.size()
        xo = (label_size.width()  - pixmap_size.width())  // 2
        yo = (label_size.height() - pixmap_size.height()) // 2
        pos = event.position().toPoint()
        return pos.x() - xo, pos.y() - yo

    def _to_pdf_point(self, px, py):
        matrix = fitz.Matrix(self.zoom_level, self.zoom_level).prerotate(self.rotation)
        try:
            return fitz.Point(px, py) * inverted_fitz_matrix(matrix)
        except ValueError:
            return None

    def _handle_page_mouse_press(self, event, page_widget):
        page_num = page_widget.property("page_num")
        self.current_page = page_num
        if not self.pdf_document:
            return

        px, py = self._pixel_coords(event, page_widget)
        if px is None:
            return

        if not (0 <= px < (page_widget.pixmap().width() if page_widget.pixmap() else 0)):
            pass  # allow out-of-bounds for annotation placement check below

        btn = event.button()

        if self._form_design_mode:
            self._handle_form_designer_press(event, page_widget, page_num, px, py)
            return

        # ── Sticky note (📌) ─────────────────────────────────────────────
        if btn == Qt.MouseButton.LeftButton and self.active_tool == TOOL_ANNOTATE:
            pdf_pt = self._to_pdf_point(px, py)
            if pdf_pt:
                text, ok = QInputDialog.getText(
                    self, "Add Note", "Note text:")
                if ok and text:
                    item = (pdf_pt.x, pdf_pt.y, text)
                    self.annotations.setdefault(page_num, []).append(item)
                    self._undo_stack.push(Command(
                        kind="annotation_add",
                        redo_data={"page": page_num, "item": item},
                        undo_data={"page": page_num, "item": item},
                    ))
                    self._update_undo_redo_labels()
                    self._mark_modified()
                    self.render_page_content(page_num, page_widget)
                    self.status_bar.showMessage("Sticky note added.")
            return

        # ── Signature placement ───────────────────────────────────────────
        if btn == Qt.MouseButton.LeftButton and self.active_tool == TOOL_SIGNATURE:
            self._place_signature_at(page_num, page_widget, px, py)
            return

        # ── Stamp placement ───────────────────────────────────────────────
        if btn == Qt.MouseButton.LeftButton and hasattr(self, "_pending_stamp") \
                and self._pending_stamp:
            self._place_stamp_at(page_num, page_widget, px, py)
            return

        # ── Freehand start ────────────────────────────────────────────────
        if btn == Qt.MouseButton.LeftButton and self.active_tool == TOOL_FREEHAND:
            self._freehand_drawing = True
            self._freehand_points  = [QPoint(page_widget.mapFromGlobal(
                event.globalPosition().toPoint()))]
            # Store in pixmap coords directly
            self._freehand_points  = [QPoint(int(px), int(py))]
            self._freehand_page    = page_num
            return

        # ── Eraser ────────────────────────────────────────────────────────
        if btn == Qt.MouseButton.LeftButton and self.active_tool == TOOL_ERASER:
            self._erase_nearest_markup(page_num, px, py, page_widget)
            return

        # ── Region-selection tools ──────────────────────────────────────
        if (
            btn == Qt.MouseButton.LeftButton
            and self.active_tool in (TOOL_REDACT, TOOL_SCAN_TEXT)
        ):
            if self.active_tool == TOOL_SCAN_TEXT:
                self._release_scan_text_mouse_grab()
                try:
                    page_widget.grabMouse()
                    self._scan_text_mouse_grab_widget = page_widget
                except RuntimeError:
                    self._scan_text_mouse_grab_widget = None
            self.is_selecting_text = True
            self.selection_start_point = event.position().toPoint()
            self.selection_end_point = event.position().toPoint()
            self.current_selection_page = page_num
            self.update_view()
            return

        # ── Text selection ────────────────────────────────────────────────
        if btn == Qt.MouseButton.LeftButton:
            self.is_selecting_text       = True
            self.selection_start_point   = event.position().toPoint()
            self.selection_end_point     = event.position().toPoint()
            self.current_selection_page  = page_num
            self.update_view()

    def _handle_page_mouse_move(self, event, page_widget):
        page_num = page_widget.property("page_num")
        px, py   = self._pixel_coords(event, page_widget)
        if px is None:
            return

        if self._form_design_mode:
            self._handle_form_designer_move(event, page_widget, page_num, px, py)
            return

        if (self._freehand_drawing and
                self.active_tool == TOOL_FREEHAND and
                self._freehand_page == page_num and
                event.buttons() & Qt.MouseButton.LeftButton):
            self._freehand_points.append(QPoint(int(px), int(py)))
            self.render_page_content(page_num, page_widget)
            return

        if (self.is_selecting_text and
                page_num == self.current_selection_page and
                event.buttons() & Qt.MouseButton.LeftButton):
            self.selection_end_point = event.position().toPoint()
            self.update_view()

    def _handle_page_mouse_release(self, event, page_widget):
        page_num = page_widget.property("page_num")
        px, py   = self._pixel_coords(event, page_widget)

        if self._form_design_mode:
            self._handle_form_designer_release(event, page_widget, page_num, px, py)
            return

        if (self._freehand_drawing and
                self.active_tool == TOOL_FREEHAND and
                event.button() == Qt.MouseButton.LeftButton):
            self._freehand_drawing = False
            if len(self._freehand_points) >= 2:
                matrix = fitz.Matrix(self.zoom_level, self.zoom_level)
                try:
                    inv = inverted_fitz_matrix(matrix)
                except ValueError:
                    inv = fitz.Matrix(1, 1)
                pdf_pts = []
                for qpt in self._freehand_points:
                    fp = fitz.Point(qpt.x(), qpt.y()) * inv
                    pdf_pts.append([fp.x, fp.y])
                r, g, b = (self.markup_color.redF(),
                           self.markup_color.greenF(),
                           self.markup_color.blueF())
                stroke_fh = {
                    "type":   "freehand",
                    "points": pdf_pts,
                    "color":  [r, g, b],
                    "width":  3,
                }
                self.markup_strokes.setdefault(page_num, []).append(stroke_fh)
                self._undo_stack.push(Command(
                    kind="markup_add",
                    redo_data={"page": page_num, "stroke": stroke_fh},
                    undo_data={"page": page_num, "stroke": stroke_fh},
                ))
                self._update_undo_redo_labels()
                self._mark_modified()
            self._freehand_points = []
            self._freehand_page   = -1
            self.render_page_content(page_num, page_widget)
            return

        if (self.is_selecting_text and
                self.active_tool == TOOL_SCAN_TEXT and
                event.button() == Qt.MouseButton.LeftButton):
            # Capture every usable endpoint *before* releasing the widget mouse
            # grab. On Windows, event.position() can collapse back to the press
            # point during release even though mouse-move events drew a valid
            # rectangle. Preserve the last move point and also map the global
            # release position back into page-widget coordinates.
            start_point = self.selection_start_point
            previous_end = self.selection_end_point
            release_end = event.position().toPoint()
            try:
                global_end = page_widget.mapFromGlobal(
                    event.globalPosition().toPoint()
                )
            except (AttributeError, RuntimeError):
                global_end = None

            self._release_scan_text_mouse_grab()
            self.is_selecting_text = False
            pdf_rect = None

            if start_point is not None:
                end_x, end_y = choose_drag_endpoint(
                    (start_point.x(), start_point.y()),
                    (previous_end.x(), previous_end.y())
                    if previous_end is not None else None,
                    (release_end.x(), release_end.y()),
                    (global_end.x(), global_end.y())
                    if global_end is not None else None,
                )
                chosen_end = QPoint(round(end_x), round(end_y))
                self.selection_end_point = chosen_end
                if drag_rectangle_is_large_enough(
                    (start_point.x(), start_point.y()),
                    (chosen_end.x(), chosen_end.y()),
                ):
                    candidate = self._widget_coords_to_pdf_rect(
                        page_widget, start_point, chosen_end
                    )
                    if candidate is not None and not candidate.is_empty:
                        pdf_rect = fitz.Rect(candidate)

            self.selection_start_point = None
            self.selection_end_point = None
            self.current_selection_page = -1
            self.update_view()

            if pdf_rect is not None:
                # Let the mouse-release event return to Qt before creating a
                # progress dialog or starting OCR. This avoids another class of
                # Windows event-loop handoff failures.
                rect_values = tuple(pdf_rect)
                self.status_bar.showMessage(
                    "Selection captured. Preparing scanned-text editor..."
                )
                QTimer.singleShot(
                    0,
                    lambda page=int(page_num), rect=rect_values:
                        self._begin_scan_text_edit(page, rect),
                )
            else:
                self.status_bar.showMessage(
                    "The selection was not captured. Drag a box with visible "
                    "width and height around the scanned text."
                )
            return

        if (self.is_selecting_text and
                self.active_tool == TOOL_REDACT and
                event.button() == Qt.MouseButton.LeftButton):
            self.is_selecting_text   = False
            self.selection_end_point = event.position().toPoint()
            if (self.selection_start_point and
                    abs(self.selection_start_point.x() - self.selection_end_point.x()) > 5 and
                    abs(self.selection_start_point.y() - self.selection_end_point.y()) > 5):
                pdf_rect = self._widget_coords_to_pdf_rect(
                    page_widget, self.selection_start_point, self.selection_end_point)
                if pdf_rect:
                    if self._pending_redaction_session_id != self._document_session_id:
                        self.pending_redactions.clear()
                        self._pending_redaction_session_id = self._document_session_id
                    self.pending_redactions.setdefault(page_num, []).append(pdf_rect)
                    rect_values = tuple(pdf_rect)
                    self._undo_stack.push(Command(
                        kind="redaction_add",
                        undo_data={"page": page_num, "rect": rect_values},
                        redo_data={"page": page_num, "rect": rect_values},
                    ))
                    self._update_undo_redo_labels()
                    self._mark_modified()
                    self.status_bar.showMessage(
                        f"Redaction box added on page {page_num + 1}. "
                        f"Use Tools → Apply Redactions to burn in.")
            self.selection_start_point  = None
            self.selection_end_point    = None
            self.current_selection_page = -1
            self.update_view()
            return

        if (self.is_selecting_text and
                event.button() == Qt.MouseButton.LeftButton):
            self.is_selecting_text   = False
            self.selection_end_point = event.position().toPoint()
            if (self.selection_start_point and
                    abs(self.selection_start_point.x() - self.selection_end_point.x()) < 5 and
                    abs(self.selection_start_point.y() - self.selection_end_point.y()) < 5):
                # Tiny click: check for highlight/underline/strikethrough by word
                if self.active_tool in (TOOL_HIGHLIGHT, TOOL_UNDERLINE,
                                        TOOL_STRIKETHROUGH):
                    self._apply_markup_at_click(page_num, px, py, page_widget)
                self.selection_start_point  = None
                self.selection_end_point    = None
                self.current_selection_page = -1
            else:
                # Drag selection: apply markup tool to selected area
                if self.active_tool in (TOOL_HIGHLIGHT, TOOL_UNDERLINE,
                                        TOOL_STRIKETHROUGH):
                    self._apply_markup_to_selection(page_num, page_widget)
            self.update_view()

    def _apply_markup_at_click(self, page_num, px, py, page_widget):
        """Apply markup to the word under the cursor."""
        pdf_pt = self._to_pdf_point(px, py)
        if not pdf_pt:
            return
        page    = self.pdf_document.load_page(page_num)
        words   = page.get_text("words")
        for w in words:
            wr = fitz.Rect(w[:4])
            if wr.contains(pdf_pt):
                self._store_markup(page_num, [list(wr)], page_widget)
                return

    def _apply_markup_to_selection(self, page_num, page_widget):
        """Apply markup to all text in the current drag-selection rectangle."""
        if not self.selection_start_point or not self.selection_end_point:
            return
        pdf_rect = self._widget_coords_to_pdf_rect(
            page_widget,
            self.selection_start_point,
            self.selection_end_point)
        if not pdf_rect:
            return
        page  = self.pdf_document.load_page(page_num)
        words = page.get_text("words")
        rects = []
        for w in words:
            wr = fitz.Rect(w[:4])
            if pdf_rect.intersects(wr):
                rects.append(list(wr))
        if rects:
            self._store_markup(page_num, rects, page_widget)

    def _store_markup(self, page_num, rects, page_widget):
        r, g, b = (self.markup_color.redF(),
                   self.markup_color.greenF(),
                   self.markup_color.blueF())
        stroke = {
            "type":  self.active_tool,
            "rects": rects,
            "color": [r, g, b],
        }
        self.markup_strokes.setdefault(page_num, []).append(stroke)
        self._undo_stack.push(Command(
            kind="markup_add",
            redo_data={"page": page_num, "stroke": stroke},
            undo_data={"page": page_num, "stroke": stroke},
        ))
        self._update_undo_redo_labels()
        self._mark_modified()
        self.render_page_content(page_num, page_widget)
        self.refresh_annotations_panel()
        self.status_bar.showMessage(
            f"{self.active_tool.capitalize()} applied.")

    def _erase_nearest_markup(self, page_num, px, py, page_widget):
        """Remove the nearest markup stroke or annotation to the click point."""
        removed = False
        pdf_pt = self._to_pdf_point(px, py)
        if pdf_pt and page_num in self.markup_strokes:
            strokes = self.markup_strokes[page_num]
            best_idx, best_dist = -1, float("inf")
            for i, stroke in enumerate(strokes):
                for r in stroke.get("rects", []):
                    cr = fitz.Rect(r)
                    cx, cy = (cr.x0 + cr.x1) / 2, (cr.y0 + cr.y1) / 2
                    d = ((cx - pdf_pt.x) ** 2 + (cy - pdf_pt.y) ** 2) ** 0.5
                    if d < best_dist:
                        best_dist, best_idx = d, i
                for pt in stroke.get("points", []):
                    d = ((pt[0] - pdf_pt.x) ** 2 + (pt[1] - pdf_pt.y) ** 2) ** 0.5
                    if d < best_dist:
                        best_dist, best_idx = d, i
            if best_idx >= 0 and best_dist < 30:
                removed_stroke = strokes.pop(best_idx)
                self._undo_stack.push(Command(
                    kind="markup_remove",
                    redo_data={"page": page_num, "stroke": removed_stroke},
                    undo_data={"page": page_num, "stroke": removed_stroke},
                ))
                self._update_undo_redo_labels()
                removed = True
        if not removed and page_num in self.annotations and self.annotations[page_num]:
            # Also allow erasing sticky notes
            best_idx, best_dist = -1, float("inf")
            for i, (x, y, _) in enumerate(self.annotations[page_num]):
                sx = x * self.zoom_level
                sy = y * self.zoom_level
                d = ((sx - px) ** 2 + (sy - py) ** 2) ** 0.5
                if d < best_dist:
                    best_dist, best_idx = d, i
            if best_idx >= 0 and best_dist < 40:
                removed_note = self.annotations[page_num].pop(best_idx)
                self._undo_stack.push(Command(
                    kind="annotation_remove",
                    redo_data={"page": page_num, "item": removed_note},
                    undo_data={"page": page_num, "item": removed_note},
                ))
                self._update_undo_redo_labels()
                if not self.annotations[page_num]:
                    del self.annotations[page_num]
                removed = True
        if removed:
            self.render_page_content(page_num, page_widget)
            self.status_bar.showMessage("Markup erased.")
        else:
            self.status_bar.showMessage("Nothing to erase near click.")

    # =========================================================================
    # Context menu
    # =========================================================================

    def _show_context_menu(self, pos):
        page_widget = self.sender()
        if not page_widget:
            return
        page_num = page_widget.property("page_num")
        self.context_menu_page_widget = page_widget
        menu = QMenu(self)

        copy_act = QAction("Copy Selected Text  Ctrl+C", self)
        copy_act.triggered.connect(self.copy_selected_text)
        copy_act.setEnabled(
            bool(self.selection_start_point and self.selection_end_point
                 and self.current_selection_page == page_num))
        menu.addAction(copy_act)
        menu.addSeparator()

        del_act = QAction("Erase Nearest Markup", self)
        px = pos.x(); py = pos.y()
        if page_widget.pixmap():
            ls = page_widget.size(); ps = page_widget.pixmap().size()
            px -= (ls.width() - ps.width()) // 2
            py -= (ls.height() - ps.height()) // 2
        del_act.triggered.connect(
            lambda: self._erase_nearest_markup(page_num, px, py, page_widget))
        menu.addAction(del_act)
        menu.addSeparator()

        bm_act = QAction(f"Bookmark Page {page_num + 1}", self)
        bm_act.triggered.connect(self.add_bookmark)
        menu.addAction(bm_act)

        menu.exec(page_widget.mapToGlobal(pos))

    # =========================================================================
    # Text selection helpers
    # =========================================================================

    def _widget_coords_to_pdf_rect(self, page_widget, start_point, end_point):
        page_num = page_widget.property("page_num")
        if page_num is None or not self.pdf_document:
            return None
        pixmap = page_widget.pixmap()
        if not pixmap:
            return None
        label_size  = page_widget.size()
        pixmap_size = pixmap.size()
        xo = (label_size.width()  - pixmap_size.width())  // 2
        yo = (label_size.height() - pixmap_size.height()) // 2
        sx = start_point.x() - xo; sy = start_point.y() - yo
        ex = end_point.x()   - xo; ey = end_point.y()   - yo
        x0 = max(0, min(sx, ex)); y0 = max(0, min(sy, ey))
        x1 = min(pixmap_size.width(),  max(sx, ex))
        y1 = min(pixmap_size.height(), max(sy, ey))
        matrix = fitz.Matrix(self.zoom_level, self.zoom_level).prerotate(self.rotation)
        try:
            inv = inverted_fitz_matrix(matrix)
        except ValueError:
            return None
        result = fitz.Rect(x0, y0, x1, y1) * inv
        result.normalize()
        return result

    def copy_selected_text(self):
        if (not self.selection_start_point or
                not self.selection_end_point or
                self.current_selection_page == -1):
            self.status_bar.showMessage("No text selected.")
            return
        page_widget = self.page_widgets[self.current_selection_page]
        pdf_rect = self._widget_coords_to_pdf_rect(
            page_widget, self.selection_start_point, self.selection_end_point)
        if pdf_rect:
            try:
                page = self.pdf_document.load_page(self.current_selection_page)
                text = page.get_textbox(pdf_rect).strip()
                if text:
                    QApplication.clipboard().setText(text)
                    self.status_bar.showMessage("Text copied to clipboard.")
                else:
                    self.status_bar.showMessage("No text in selected area.")
            except Exception as e:
                self.status_bar.showMessage(f"Copy error: {e}")
        self.selection_start_point  = None
        self.selection_end_point    = None
        self.current_selection_page = -1
        self.update_view()

    # =========================================================================
    # View update / navigation
    # =========================================================================

    def update_view(self):
        if not self.pdf_document:
            return
        if self.view_mode == self.SINGLE_PAGE:
            self.render_single_page()
        else:
            self.render_continuous_pages()

    def update_status_bar(self):
        if not self.pdf_document:
            self.status_bar.showMessage("Ready  –  Open a PDF to begin")
            return
        sr_str = (f"Match {self.current_search_index + 1}/{len(self.search_results)}"
                  if self.search_results and self.current_search_index >= 0
                  else "")
        tool_str = (f" | Tool: {self.active_tool}"
                    if self.active_tool != TOOL_NONE else "")
        mode_str = "Continuous" if self.view_mode == self.CONTINUOUS else "Single page"
        self.status_bar.showMessage(
            f"Page {self.current_page + 1}/{self.total_pages}  |  "
            f"Zoom {int(self.zoom_level * 100)}%  |  "
            f"Rotate {self.rotation}°  |  {mode_str}{tool_str}  {sr_str}")
        self.page_input.setText(str(self.current_page + 1))

    def update_ui_on_page_change(self):
        self._autosave_form_data()
        self.active_tool     = TOOL_NONE
        self.annotation_mode = False
        self._clear_tool_buttons()
        self._update_cursor()
        self.selection_start_point  = None
        self.selection_end_point    = None
        self.current_selection_page = -1
        self.update_view()
        is_single = (self.view_mode == self.SINGLE_PAGE)
        self.prev_button.setEnabled(self.current_page > 0 and is_single)
        self.next_button.setEnabled(
            self.current_page < self.total_pages - 1 and is_single)
        self.move_up_button.setEnabled(self.current_page > 0)
        self.move_down_button.setEnabled(self.current_page < self.total_pages - 1)
        self.thumbnail_list.setCurrentRow(self.current_page)
        self.page_input.setText(str(self.current_page + 1))

    def scroll_to_page(self, page_num):
        if self.view_mode == self.CONTINUOUS and 0 <= page_num < len(self.page_widgets):
            target = self.page_widgets[page_num]
            pos    = self.scroll_area.widget().mapFromParent(target.pos())
            self.scroll_area.verticalScrollBar().setValue(pos.y())

    def prev_page(self):
        if self.view_mode == self.SINGLE_PAGE and self.current_page > 0:
            self.current_page -= 1
            self.update_ui_on_page_change()

    def next_page(self):
        if (self.view_mode == self.SINGLE_PAGE and
                self.current_page < self.total_pages - 1):
            self.current_page += 1
            self.update_ui_on_page_change()

    def goto_page(self):
        try:
            pn = int(self.page_input.text()) - 1
            if 0 <= pn < self.total_pages:
                self.current_page = pn
                self.update_ui_on_page_change()
            else:
                self.status_bar.showMessage("Invalid page number")
        except ValueError:
            self.status_bar.showMessage("Enter a valid number")

    # =========================================================================
    # Zoom / Rotation
    # =========================================================================

    def zoom_in(self):
        idx = self.zoom_combo.currentIndex()
        if idx < self.zoom_combo.count() - 1:
            self.zoom_combo.setCurrentIndex(idx + 1)
            self.change_zoom(self.zoom_combo.currentText())

    def zoom_out(self):
        idx = self.zoom_combo.currentIndex()
        if idx > 0:
            self.zoom_combo.setCurrentIndex(idx - 1)
            self.change_zoom(self.zoom_combo.currentText())

    def change_zoom(self, text):
        if text in ("Fit Width", "Fit Page"):
            return
        try:
            self.zoom_level = int(text.strip("%")) / 100.0
            self.update_view()
        except ValueError:
            self.status_bar.showMessage(f"Invalid zoom value: '{text}'")

    def set_zoom_fit_width(self):
        self.set_zoom_fit("width")

    def set_zoom_fit_page(self):
        self.set_zoom_fit("page")

    def set_zoom_fit(self, mode):
        if not self.pdf_document:
            return
        page   = self.pdf_document.load_page(self.current_page)
        rect   = page.rect
        vp     = self.scroll_area.viewport().size()
        avail_w = vp.width()  - self.pdf_layout.spacing()
        avail_h = vp.height() - self.pdf_layout.spacing()
        if mode == "width":
            new_zoom = avail_w / rect.width
        else:
            new_zoom = min(avail_w / rect.width, avail_h / rect.height)
        self.zoom_level = max(0.1, min(10.0, new_zoom))
        zoom_text = f"{int(self.zoom_level * 100)}%"
        items = [self.zoom_combo.itemText(i) for i in range(self.zoom_combo.count())]
        if zoom_text not in items:
            self.zoom_combo.blockSignals(True)
            self.zoom_combo.addItem(zoom_text)
            self.zoom_combo.blockSignals(False)
        self.zoom_combo.setCurrentText(zoom_text)
        self.update_view()

    def rotate_page(self):
        self.rotation = (self.rotation + 90) % 360
        self.update_view()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    # =========================================================================
    # View mode / dark mode
    # =========================================================================

    def toggle_view_mode(self):
        self.view_mode = (self.CONTINUOUS if self.view_mode == self.SINGLE_PAGE
                          else self.SINGLE_PAGE)
        if self.view_mode == self.CONTINUOUS:
            self.view_mode_button.setText("Single Page")
            self.prev_button.setEnabled(False)
            self.next_button.setEnabled(False)
        else:
            self.view_mode_button.setText("Continuous")
            self.prev_button.setEnabled(self.current_page > 0)
            self.next_button.setEnabled(self.current_page < self.total_pages - 1)
        self.settings.setValue("prefs/view_mode", self.view_mode)
        self.update_view()

    def toggle_dark_mode(self):
        self.dark_mode = not self.dark_mode
        if self.dark_mode:
            self.scroll_area.setStyleSheet("background-color: #1e1e1e;")
            self.dark_mode_button.setText("Light Mode")
        else:
            self.scroll_area.setStyleSheet("background-color: #f0f0f0;")
            self.dark_mode_button.setText("Dark Mode")
        self.settings.setValue("prefs/dark_mode", self.dark_mode)

    # =========================================================================
    # Annotation mode (back-compat shim → routes to active_tool)
    # =========================================================================

    def toggle_annotation_mode(self, force_off=False):
        if force_off:
            if self.active_tool == TOOL_ANNOTATE:
                self.active_tool = TOOL_NONE
            self.annotation_mode = False
            self._sync_tool_buttons()
            self._update_cursor()
        else:
            if self.active_tool == TOOL_ANNOTATE:
                self.active_tool = TOOL_NONE
                self.annotation_mode = False
            else:
                self.active_tool = TOOL_ANNOTATE
                self.annotation_mode = True
            self._sync_tool_buttons()
            self._update_cursor()

    # =========================================================================
    # Thumbnails / TOC
    # =========================================================================

    def refresh_annotations_panel(self):
        """Rebuild the annotations sidebar panel."""
        if hasattr(self, 'annot_panel'):
            self.annot_panel.refresh(
                self.pdf_document,
                self.annotations,
                self.markup_strokes,
                self.pending_redactions)

    def load_thumbnails(self):
        self.thumbnail_list.clear()
        if self.pdf_document:
            for pn in range(self.total_pages):
                page = self.pdf_document.load_page(pn)
                pix  = page.get_pixmap(matrix=fitz.Matrix(0.2, 0.2))
                img  = QImage(pix.samples, pix.width, pix.height, pix.stride,
                              QImage.Format.Format_RGB888)
                item = QListWidgetItem(f"Page {pn + 1}")
                item.setIcon(QIcon(QPixmap.fromImage(img)))
                self.thumbnail_list.addItem(item)

    def thumbnail_clicked(self, item):
        self.current_page = self.thumbnail_list.row(item)
        self.update_ui_on_page_change()
        if self.view_mode == self.CONTINUOUS:
            self.scroll_to_page(self.current_page)

    def load_toc(self):
        self.toc_list.clear()
        if self.pdf_document:
            for level, title, pn in self.pdf_document.get_toc():
                if pn <= self.total_pages:
                    item = QListWidgetItem("  " * (level - 1) + title)
                    item.setData(Qt.ItemDataRole.UserRole, pn - 1)
                    self.toc_list.addItem(item)

    def toc_clicked(self, item):
        self.current_page = item.data(Qt.ItemDataRole.UserRole)
        self.update_ui_on_page_change()
        if self.view_mode == self.CONTINUOUS:
            self.scroll_to_page(self.current_page)

    # =========================================================================
    # Resize event
    # =========================================================================

    def _annot_panel_jump(self, page: int):
        """Called when user double-clicks or requests refresh in annotations panel."""
        if page == -1:
            # Refresh signal
            self.refresh_annotations_panel()
            return
        if self.pdf_document and 0 <= page < self.total_pages:
            self.current_page = page
            self.update_ui_on_page_change()
            if self.view_mode == self.CONTINUOUS:
                self.scroll_to_page(page)

    def _annot_panel_delete(self, data: dict):
        """Remove an annotation from its single authoritative backing store."""
        source = data.get("source")
        page = int(data.get("page", -1))
        changed = False

        if source == "note":
            x, y = data.get("x"), data.get("y")
            items = self.annotations.get(page, [])
            removed_item = next(
                (
                    item for item in items
                    if abs(item[0] - x) < 1 and abs(item[1] - y) < 1
                ),
                None,
            )
            if removed_item is not None:
                items.remove(removed_item)
                if not items:
                    self.annotations.pop(page, None)
                self._undo_stack.push(Command(
                    kind="annotation_remove",
                    undo_data={"page": page, "item": removed_item},
                    redo_data={"page": page, "item": removed_item},
                ))
                changed = True

        elif source == "markup":
            index = data.get("stroke_idx")
            strokes = self.markup_strokes.get(page, [])
            if index is not None and 0 <= int(index) < len(strokes):
                removed_stroke = strokes.pop(int(index))
                if not strokes:
                    self.markup_strokes.pop(page, None)
                self._undo_stack.push(Command(
                    kind="markup_remove",
                    undo_data={"page": page, "stroke": removed_stroke},
                    redo_data={"page": page, "stroke": removed_stroke},
                ))
                changed = True

        elif source == "redaction":
            index = data.get("rect_idx")
            rects = self.pending_redactions.get(page, [])
            if index is not None and 0 <= int(index) < len(rects):
                removed_rect = tuple(rects.pop(int(index)))
                if not rects:
                    self.pending_redactions.pop(page, None)
                self._undo_stack.push(Command(
                    kind="redaction_remove",
                    undo_data={"page": page, "rect": removed_rect},
                    redo_data={"page": page, "rect": removed_rect},
                ))
                changed = True

        elif source == "pdf":
            xref = data.get("annot_xref")
            if xref and self.pdf_document and 0 <= page < self.total_pages:
                before_snapshot = snapshot_pdf_bytes(self.pdf_document)
                pdf_page = self.pdf_document.load_page(page)
                for annotation in pdf_page.annots() or []:
                    if annotation.xref == xref:
                        pdf_page.delete_annot(annotation)
                        after_snapshot = snapshot_pdf_bytes(self.pdf_document)
                        self._undo_stack.push(Command(
                            kind="native_document_change",
                            undo_data={
                                "pdf_bytes": before_snapshot,
                                "page": page,
                                "label": "Annotation deletion",
                            },
                            redo_data={
                                "pdf_bytes": after_snapshot,
                                "page": page,
                                "label": "Annotation deletion",
                            },
                        ))
                        changed = True
                        break

        if not changed:
            self.status_bar.showMessage("Annotation was already removed.")
            return

        self._mark_modified()
        self._update_undo_redo_labels()
        if 0 <= page < len(self.page_widgets):
            self.render_page_content(page, self.page_widgets[page])
        self.refresh_annotations_panel()
        self.status_bar.showMessage("Annotation deleted.")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.pdf_document:
            return
        ct = self.zoom_combo.currentText()
        if ct == "Fit Width":
            self.set_zoom_fit_width()
        elif ct == "Fit Page":
            self.set_zoom_fit_page()
        else:
            self.update_view()

    # =========================================================================
    # Print
    # =========================================================================

    def _ask_page_range(self):
        """Prompt for a page range. Returns (start, end) 0-based, or None."""
        page_range, ok = QInputDialog.getText(
            self, "Print Pages",
            f"Page range (e.g. 1-5 or 'all'):",
            text=f"1-{self.total_pages}")
        if not ok:
            return None
        if page_range.strip().lower() == "all":
            return 0, self.total_pages - 1
        try:
            if "-" in page_range:
                s, e = map(int, page_range.split("-"))
                start_page = max(0, s - 1)
                end_page   = min(self.total_pages - 1, e - 1)
            else:
                start_page = end_page = int(page_range) - 1
                if not (0 <= start_page < self.total_pages):
                    raise ValueError
        except ValueError:
            self.status_bar.showMessage("Invalid page range")
            return None
        if start_page > end_page:
            self.status_bar.showMessage("Invalid page range")
            return None
        return start_page, end_page

    def _render_to_printer(self, printer, start_page, end_page):
        """Paint the given page range onto a QPrinter.

        Shared by Print and Print Preview so that what the user sees in the
        preview is produced by exactly the same code that goes to the printer.
        Raises on failure; callers report it.
        """
        painter = QPainter()
        if not painter.begin(printer):
            raise RuntimeError("Could not start the print job — the printer "
                               "may be unavailable.")
        try:
            # Paint area in device pixels. The painter's viewport is already in
            # the painter's coordinate space (unlike pageLayout().paintRectPixels(),
            # whose origin is the margin offset).
            target = painter.viewport()
            dpi = printer.resolution() or 300

            for pn in range(start_page, end_page + 1):
                if pn > start_page:
                    printer.newPage()

                page = self.pdf_document.load_page(pn)

                # Render at the printer's resolution rather than rendering at
                # 72 dpi and upscaling. Cap the zoom so a huge page can't
                # exhaust memory.
                zoom = min(dpi / 72.0, 8.0)
                matrix = fitz.Matrix(zoom, zoom).prerotate(self.rotation)
                pix = page.get_pixmap(matrix=matrix, alpha=False)

                fmt = (QImage.Format.Format_RGB888 if pix.n == 3
                       else QImage.Format.Format_RGBA8888)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
                if img.isNull():
                    raise RuntimeError(f"Could not render page {pn + 1}")
                # Copy: QImage does not own the PyMuPDF buffer, which is freed
                # when `pix` goes out of scope.
                pixmap = QPixmap.fromImage(img.copy())

                scaled = pixmap.scaled(
                    target.width(), target.height(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
                x = target.x() + (target.width()  - scaled.width())  // 2
                y = target.y() + (target.height() - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)
        finally:
            painter.end()

    def print_preview(self):
        """Show a print preview before sending anything to the printer."""
        if not self.pdf_document:
            return
        rng = self._ask_page_range()
        if rng is None:
            return
        start_page, end_page = rng

        from PyQt6.QtPrintSupport import QPrintPreviewDialog

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle("Print Preview")
        # Open large: the whole point is that it can actually be seen.
        preview.resize(1000, 800)

        self._preview_error = None

        def _paint(p):
            try:
                self._render_to_printer(p, start_page, end_page)
            except Exception as e:
                self._preview_error = e

        preview.paintRequested.connect(_paint)
        preview.exec()

        if self._preview_error is not None:
            e = self._preview_error
            QMessageBox.critical(
                self, "Preview failed",
                f"The document could not be rendered:\n\n{type(e).__name__}: {e}")
            self.status_bar.showMessage("Print preview failed")
        else:
            self.status_bar.showMessage("Print preview closed")

    def print_pdf(self):
        if not self.pdf_document:
            return
        rng = self._ask_page_range()
        if rng is None:
            return
        start_page, end_page = rng

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog  = QPrintDialog(printer, self)
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return

        try:
            self._render_to_printer(printer, start_page, end_page)
            n = end_page - start_page + 1
            self.status_bar.showMessage(
                f"Sent {n} page{'s' if n != 1 else ''} to the printer "
                f"({start_page + 1}\u2013{end_page + 1})")
        except Exception as e:
            # Report loudly: a silent status-bar message previously hid real
            # failures behind an apparently-successful but blank print job.
            QMessageBox.critical(
                self, "Print failed",
                f"The document could not be printed:\n\n{type(e).__name__}: {e}")
            self.status_bar.showMessage("Print failed")

    # =========================================================================
    # Metadata / Properties
    # =========================================================================

    def show_metadata(self):
        if not self.pdf_document:
            return
        m = self.pdf_document.metadata
        info = "\n".join([
            f"Title:     {m.get('title',  'N/A')}",
            f"Author:    {m.get('author', 'N/A')}",
            f"Producer:  {m.get('producer', 'N/A')}",
            f"Creator:   {m.get('creator',  'N/A')}",
            f"Created:   {m.get('creationDate', 'N/A')}",
            f"Modified:  {m.get('modDate', 'N/A')}",
            f"Format:    {m.get('format',  'N/A')}",
            f"Pages:     {self.total_pages}",
            f"File:      {self.pdf_file_path}",
        ])
        QMessageBox.information(self, "Document Properties", info)

    # =========================================================================
    # Window geometry persistence
    # =========================================================================

    # =========================================================================
    # OCR
    # =========================================================================

    def _show_ocr(self):
        if not self.pdf_document:
            return

        # OCR reads the on-disk PDF. Refuse to ignore unsaved in-memory edits.
        if self.windowTitle().startswith("*"):
            QMessageBox.warning(
                self,
                "Save Before OCR",
                "This document has unsaved changes. Save it before running OCR "
                "so the searchable copy includes your latest edits.",
            )
            return

        from ocr_dialog import OCRDialog
        dlg = OCRDialog(
            pdf_path=self.pdf_file_path,
            total_pages=self.total_pages,
            current_page=self.current_page,
            parent=self)
        if not dlg.exec() or not dlg.output_path:
            return

        if dlg.replace_original:
            self._finish_ocr_replacement(
                dlg.output_path,
                self.pdf_file_path,
                dlg.verified_word_count,
            )
            return

        reply = QMessageBox.question(
            self, "OCR Complete",
            f"OCR finished and the text layer was verified "
            f"({dlg.verified_word_count:,} searchable words).\n\n"
            f"Output saved to:\n{dlg.output_path}\n\n"
            "You are still viewing the original PDF until you open the OCR "
            "result. Open it now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if reply == QMessageBox.StandardButton.Yes:
            self._open_pdf_path(dlg.output_path)
            self.status_bar.showMessage(
                f"OCR text layer verified: {dlg.verified_word_count:,} words. "
                "Press Ctrl+F to search, or use Edit → Select All Text on Page."
            )

    def _finish_ocr_replacement(self, temporary_path: str,
                                original_path: str,
                                verified_words: int = 0):
        """Close the source document, atomically replace it, and reopen it."""
        old_document = self.pdf_document
        self.pdf_document = None
        self.pages = []
        self.form_fields = {}

        try:
            if old_document is not None:
                old_document.close()
            os.replace(temporary_path, original_path)
        except Exception as exc:
            # Restore a usable document even when Windows, antivirus, or file
            # permissions prevent replacement. Keep the OCR result for recovery.
            self._open_pdf_path(original_path)
            QMessageBox.critical(
                self,
                "Could Not Replace Original",
                "OCR completed, but PDF Studio could not replace the original "
                f"file.\n\n{type(exc).__name__}: {exc}\n\n"
                f"The OCR result has been kept at:\n{temporary_path}",
            )
            return

        self._open_pdf_path(original_path)
        QMessageBox.information(
            self,
            "OCR Complete",
            "OCR finished, the searchable text layer was verified, and the "
            "original PDF was replaced safely.\n\n"
            f"Searchable words: {verified_words:,}\n"
            f"{original_path}\n\n"
            "Test it with Ctrl+F, or use Edit → Select All Text on Page.",
        )
        self.status_bar.showMessage(
            f"OCR text layer verified: {verified_words:,} words. "
            "Press Ctrl+F to search."
        )

    # =========================================================================
    # Export
    # =========================================================================

    def _show_export(self, fmt: str = "docx"):
        if not self.pdf_document:
            return
        from export_dialog import ExportDialog
        dlg = ExportDialog(
            pdf_path=self.pdf_file_path,
            total_pages=self.total_pages,
            current_page=self.current_page,
            parent=self)
        dlg.select_format(fmt)
        dlg.exec()

    def closeEvent(self, event):
        """Protect unsaved form and annotation changes before closing."""
        self._autosave_form_data()
        if not self._confirm_save_changes("close PDF Studio"):
            event.ignore()
            return

        self.settings.setValue("window_geometry", self.saveGeometry())
        self.settings.setValue("window_state", self.saveState())
        self._save_sidebar_state()
        self.settings.setValue("prefs/zoom_level", self.zoom_level)
        self.settings.setValue("prefs/view_mode", self.view_mode)
        self.settings.setValue("prefs/dark_mode", self.dark_mode)
        self.settings.setValue("prefs/markup_color", self.markup_color.name())
        if (
            self._form_detection_worker is not None
            and self._form_detection_worker.isRunning()
        ):
            QMessageBox.information(
                self,
                "Form Detection Running",
                "Form detection is still analysing a page. Close PDF Studio "
                "after the analysis completes.",
            )
            event.ignore()
            return
        self._form_detection_worker = None
        if (
            self._scan_text_worker is not None
            and self._scan_text_worker.isRunning()
        ):
            QMessageBox.information(
                self,
                "Scanned-Text OCR Running",
                "OCR is still analysing a selected region. Close PDF Studio "
                "after that operation completes.",
            )
            event.ignore()
            return
        self._scan_text_worker = None
        if self.pdf_document is not None:
            try:
                self.pdf_document.close()
            except Exception:
                pass
            self.pdf_document = None
        if self._imported_temp_pdf_path:
            import doc_import
            doc_import.cleanup_temporary_import(self._imported_temp_pdf_path)
            self._imported_temp_pdf_path = None
            self._imported_source_path = None
        event.accept()

    # =========================================================================
    # Save a Copy  (Phase 0 – new safe save option)
    # =========================================================================

    def save_a_copy(self):
        """Save a validated staged copy without mutating the active document."""
        if not self.pdf_document:
            return False
        default = self.pdf_file_path or "copy.pdf"
        base, ext = os.path.splitext(default)
        default = base + "_copy" + (ext or ".pdf")
        file_name, _ = QFileDialog.getSaveFileName(
            self, "Save a Copy", default, "PDF Files (*.pdf)")
        if not file_name:
            return False
        if not file_name.lower().endswith(".pdf"):
            file_name += ".pdf"
        if self.pdf_file_path and os.path.abspath(file_name) == os.path.abspath(self.pdf_file_path):
            QMessageBox.warning(
                self, "Choose a Different File",
                "Save a Copy cannot replace the document currently open. "
                "Choose a different filename.")
            return False

        clone = None
        try:
            self._autosave_form_data()
            clone = clone_pdf_document(self.pdf_document)
            self._prepare_document_for_save(
                clone, autosave_forms=False, mark_baked=False)
            save_pdf_atomic(
                clone,
                file_name,
                save_kwargs={
                    "garbage": 4 if self._requires_full_rewrite else 3,
                    "clean": bool(self._requires_full_rewrite),
                    "deflate": True,
                    "encryption": fitz.PDF_ENCRYPT_KEEP,
                },
            )
            self.status_bar.showMessage(f"Copy saved: {file_name}")
            return True
        except Exception as exc:
            logging.exception("Save a Copy failed: %s", file_name)
            QMessageBox.critical(
                self,
                "Save Copy Error",
                "The copy could not be completed. Any existing destination was "
                f"preserved.\n\n{type(exc).__name__}: {exc}",
            )
            return False
        finally:
            if clone is not None:
                clone.close()

    # =========================================================================
    # Undo / Redo  (Phase 0 – annotation & markup; Phase 2 – page ops)
    # =========================================================================

    def undo(self):
        cmd = self._undo_stack.pop_undo()
        if cmd is None:
            self.status_bar.showMessage("Nothing to undo.")
            return
        self._apply_command(cmd, direction="undo")
        self._update_undo_redo_labels()

    def redo(self):
        cmd = self._undo_stack.pop_redo()
        if cmd is None:
            self.status_bar.showMessage("Nothing to redo.")
            return
        self._apply_command(cmd, direction="redo")
        self._update_undo_redo_labels()

    def _apply_command(self, cmd, direction):
        """Apply undo or redo payload for the given command."""
        data = cmd.undo_data if direction == "undo" else cmd.redo_data
        kind = cmd.kind
        self._mark_modified()

        if kind == "annotation_add":
            page_num, item = data["page"], data["item"]
            if direction == "undo":
                self.annotations.get(page_num, [])
                lst = self.annotations.setdefault(page_num, [])
                if item in lst:
                    lst.remove(item)
            else:
                self.annotations.setdefault(page_num, []).append(item)
            self._finish_markup_undo(page_num, "Sticky note undone." if direction == "undo" else "Sticky note redone.")

        elif kind == "annotation_remove":
            page_num, item = data["page"], data["item"]
            if direction == "undo":
                self.annotations.setdefault(page_num, []).append(item)
            else:
                lst = self.annotations.get(page_num, [])
                if item in lst:
                    lst.remove(item)
            self._finish_markup_undo(page_num, "Annotation undone." if direction == "undo" else "Annotation redone.")

        elif kind in ("markup_add", "markup_remove"):
            page_num = data["page"]
            stroke   = data["stroke"]
            strokes  = self.markup_strokes.setdefault(page_num, [])
            if (kind == "markup_add" and direction == "undo") or                (kind == "markup_remove" and direction == "redo"):
                # Remove it
                if stroke in strokes:
                    strokes.remove(stroke)
            else:
                # Add it back
                strokes.append(stroke)
            msg = "Annotation undone." if direction == "undo" else "Annotation redone."
            self._finish_markup_undo(page_num, msg)

        elif kind in ("redaction_add", "redaction_remove"):
            page_num = int(data["page"])
            rect = fitz.Rect(data["rect"])
            rects = self.pending_redactions.setdefault(page_num, [])
            remove = (
                (kind == "redaction_add" and direction == "undo")
                or (kind == "redaction_remove" and direction == "redo")
            )
            if remove:
                for index, existing in enumerate(rects):
                    if fitz.Rect(existing) == rect:
                        rects.pop(index)
                        break
                if not rects:
                    self.pending_redactions.pop(page_num, None)
            else:
                rects.append(rect)
            self._pending_redaction_session_id = self._document_session_id
            self._finish_markup_undo(
                page_num,
                "Redaction box undone." if direction == "undo"
                else "Redaction box redone.",
            )

        elif kind == "native_document_change":
            page_num = int(data.get("page", self.current_page))
            label = str(data.get("label", "Native PDF change"))
            self._replace_document_from_snapshot(
                data["pdf_bytes"], preferred_page=page_num
            )
            self._mark_modified()
            self.status_bar.showMessage(
                f"{label} {'undone' if direction == 'undo' else 'redone'}."
            )

        elif kind == "scan_text_overlay":
            if direction == "undo":
                page_num = int(data["page"])
                removed = remove_overlay_replacement(
                    self.pdf_document,
                    page_number=page_num,
                    annotation_xref=int(data["annotation_xref"]),
                )
                message = (
                    "Text replacement undone."
                    if removed
                    else "The text replacement was already removed."
                )
            else:
                plan = ScanTextReplacement(**data["plan"])
                result = apply_scan_text_replacement(self.pdf_document, plan)
                page_num = int(result["page_number"])
                cmd.undo_data["page"] = page_num
                cmd.undo_data["annotation_xref"] = int(
                    result["annotation_xref"]
                )
                message = "Text replacement redone."
            self._finish_markup_undo(page_num, message)

        elif kind == "page_add":
            page_num = data["page"]
            if direction == "undo":
                # Remove the added page
                if self.pdf_document and self.pdf_document.page_count > 1:
                    self.pdf_document.delete_page(page_num)
                    self.total_pages -= 1
                    if self.current_page >= self.total_pages:
                        self.current_page = self.total_pages - 1
            else:
                # Re-add it
                if self.pdf_document:
                    self.pdf_document.insert_page(page_num)
                    self.total_pages += 1
            if data.get("state") is not None:
                restore_page_bound_state(self, data["state"])
            self._finish_page_op("Page insert undone." if direction == "undo" else "Page insert redone.")

        elif kind == "page_remove":
            page_num = data["page"]
            page_bytes = data.get("page_bytes")
            if direction == "undo" and page_bytes and self.pdf_document:
                tmp = fitz.open(stream=page_bytes, filetype="pdf")
                try:
                    self.pdf_document.insert_pdf(
                        tmp,
                        from_page=0,
                        to_page=0,
                        start_at=page_num,
                        annots=True,
                        widgets=True,
                    )
                finally:
                    tmp.close()
                self.total_pages += 1
                if data.get("state") is not None:
                    restore_page_bound_state(self, data["state"])
                self._finish_page_op("Page deletion undone.")
            elif direction == "redo" and self.pdf_document:
                self.pdf_document.delete_page(page_num)
                self.total_pages -= 1
                if data.get("state") is not None:
                    restore_page_bound_state(self, data["state"])
                if self.current_page >= self.total_pages:
                    self.current_page = self.total_pages - 1
                self._finish_page_op("Page deletion redone.")

        elif kind == "page_move":
            frm = data["from"]
            to  = data["to"]
            if self.pdf_document:
                move_page_to_final_index(self.pdf_document, frm, to)
            if data.get("state") is not None:
                restore_page_bound_state(self, data["state"])
            else:
                self.current_page = to
            self._finish_page_op("Page move undone." if direction == "undo" else "Page move redone.")

    def _finish_markup_undo(self, page_num, msg):
        if 0 <= page_num < len(self.page_widgets):
            self.render_page_content(page_num, self.page_widgets[page_num])
        self.refresh_annotations_panel()
        self.status_bar.showMessage(msg)
        self._update_undo_redo_labels()

    def _finish_page_op(self, msg):
        from pdf_utils import _rebuild_after_page_op
        _rebuild_after_page_op(self, msg)
        self._update_undo_redo_labels()

    def _update_undo_redo_labels(self):
        """Keep Edit > Undo and Edit > Redo labels and enabled state in sync."""
        can_undo = self._undo_stack.can_undo()
        can_redo = self._undo_stack.can_redo()
        cmd_u = self._undo_stack.peek_undo()
        cmd_r = self._undo_stack.peek_redo()
        kind_map = {
            "annotation_add":    "Note",
            "annotation_remove": "Note Erase",
            "markup_add":        "Markup",
            "markup_remove":     "Markup Erase",
            "scan_text_overlay": "Text Replacement",
            "native_document_change": "Native PDF Change",
            "redaction_add":     "Redaction Box",
            "redaction_remove":  "Redaction Box Removal",
            "page_add":          "Insert Page",
            "page_remove":       "Delete Page",
            "page_move":         "Move Page",
        }
        u_label = f"Undo {kind_map.get(cmd_u.kind, '')}".strip() if cmd_u else "Undo"
        r_label = f"Redo {kind_map.get(cmd_r.kind, '')}".strip() if cmd_r else "Redo"
        self._act_undo.setText(f"&{u_label}\tCtrl+Z")
        self._act_redo.setText(f"&{r_label}\tCtrl+Y")
        self._act_undo.setEnabled(can_undo)
        self._act_redo.setEnabled(can_redo)

    def _select_all_text_on_page(self):
        """Select all text on the current page and copy it to the clipboard."""
        if not self.pdf_document:
            return
        try:
            page = self.pdf_document.load_page(self.current_page)
            text = page.get_text("text").strip()
            if text:
                QApplication.clipboard().setText(text)
                self.status_bar.showMessage(
                    f"Page {self.current_page + 1}: all text copied to clipboard "
                    f"({len(text)} chars).")
            else:
                self.status_bar.showMessage(
                    "No selectable text on this page (may be a scanned image).")
        except Exception as e:
            self.status_bar.showMessage(f"Select all error: {e}")

    # =========================================================================
    # Form persistence
    # =========================================================================

    def _autosave_form_data(self):
        """Flush controls into the in-memory document; disk save remains explicit."""
        if not self.pdf_document:
            return
        self._flush_form_controls()
        if not self._form_dirty:
            return
        import logging
        for page_num, fields in self.form_fields.items():
            for field in fields:
                try:
                    field.update()
                except Exception as exc:
                    logging.warning(
                        "_autosave_form_data: failed updating field on page %d: %s",
                        page_num, exc)

    # =========================================================================
    # Thumbnail double-click  (Phase 2)
    # =========================================================================

    def _thumbnail_double_clicked(self, item):
        """Jump to page and center it in the viewport."""
        row = self.thumbnail_list.row(item)
        if not (0 <= row < self.total_pages):
            return
        self.current_page = row
        self.update_ui_on_page_change()
        if self.view_mode == self.CONTINUOUS:
            self.scroll_to_page(self.current_page)
        else:
            # In single-page mode just ensure scroll is reset to top
            self.scroll_area.verticalScrollBar().setValue(0)
        self.status_bar.showMessage(f"Jumped to page {self.current_page + 1}.")

        # =========================================================================
    # Utility hooks (called by UI signals or shortcuts)
    # =========================================================================

    def focus_search(self):
        self.search_input.setFocus()
        self.search_input.selectAll()

    def start_search(self):
        search_text(self)

    def next_search_result(self):
        next_search_result(self)

    def prev_search_result(self):
        prev_search_result(self)

    def add_page_action(self):
        add_page(self)
        self._update_undo_redo_labels()

    def remove_page_action(self):
        remove_page(self)
        self._update_undo_redo_labels()

    def move_page_up_action(self):
        move_page_up(self)
        self._update_undo_redo_labels()

    def move_page_down_action(self):
        move_page_down(self)
        self._update_undo_redo_labels()


