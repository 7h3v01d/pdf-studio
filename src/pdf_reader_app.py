"""
pdf_reader_app.py
-----------------
Core application logic.  Inherits all UI from PDFReaderUI.
"""
import sys
import os
import json
import fitz  # PyMuPDF
from PyQt6.QtWidgets import (
    QInputDialog, QMessageBox, QLabel, QMenu, QFileDialog,
    QApplication, QListWidgetItem, QLineEdit, QCheckBox, QComboBox,
    QRadioButton, QTextEdit, QColorDialog, QDialog, QVBoxLayout,
    QHBoxLayout, QPushButton, QSizePolicy)
from PyQt6.QtGui import (
    QPixmap, QImage, QPainter, QPen, QColor, QAction, QIcon,
    QCursor, QFont)
from PyQt6.QtCore import Qt, QRectF, QPoint, QSize, QSettings
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog

from pdf_reader_ui import PDFReaderUI
from about_dialog import APP_NAME
from password_dialog import PasswordPromptDialog, PasswordProtectDialog
from undo_stack import UndoStack, Command
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

        # Pending redaction boxes: {page_num: [fitz.Rect, ...]}
        self.pending_redactions = {}

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
        self.field_widgets = {}  # {page: [Qt widgets]}
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
        self._open_pdf_path(pdf_path, display_path=src)

    def _open_pdf_path(self, file_name, display_path=None):
        if not os.path.exists(file_name):
            self.status_bar.showMessage(f"File not found: {file_name}")
            return

        # Word / Excel documents: convert to PDF first, then open that.
        import doc_import
        if display_path is None and doc_import.is_importable(file_name):
            self._open_office_document(file_name)
            return

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
                QMessageBox.critical(
                    self, "Corrupted PDF",
                    f"The file appears to be corrupted and could not be opened.\n\n"
                    f"Detail: {fde}")
                self.status_bar.showMessage(f"Error: corrupted PDF – {file_name}")
                return
            except Exception as exc:
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
            self.pdf_document   = doc
            self.pdf_file_path  = file_name
            self.total_pages    = self.pdf_document.page_count
            self.current_page   = 0
            self.rotation       = 0
            self.search_results = []
            self.current_search_index = -1
            self.active_tool    = TOOL_NONE
            self.annotation_mode = False
            self._clear_tool_buttons()

            self.annotations = load_annotations(self.pdf_document, file_name)
            self.markup_strokes = self._load_markup_strokes(file_name)
            self._undo_stack.clear()
            self._form_dirty = False
            self._update_undo_redo_labels()
            self.bookmarks   = load_bookmarks(file_name)

            self.form_fields = {}
            self.pages       = []
            for pn in range(self.total_pages):
                page = self.pdf_document.load_page(pn)
                self.form_fields[pn] = list(page.widgets())
                self.pages.append(page)

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
            self.update_ui_on_page_change()
            self.page_label.setText(f" / {self.total_pages}")
            shown = display_path or file_name
            suffix = "  (imported)" if display_path else ""
            self.setWindowTitle(f"{APP_NAME}  –  {os.path.basename(shown)}{suffix}")
            self.status_bar.showMessage(f"Opened: {shown}")
            self._add_to_recent(display_path or file_name)
        except Exception as e:
            QMessageBox.critical(self, "Unexpected Error",
                f"An unexpected error occurred while opening the file:\n\n{e}")
            self.status_bar.showMessage(f"Error loading PDF: {e}")

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
            self.redact_button,
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
            self._act_password,
            self._act_ocr, self._act_export_docx, self._act_export_xlsx,
            self._act_save_copy, self._act_reset_form,
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
        """Open the password protect/remove dialog and apply to save."""
        if not self.pdf_document:
            return
        is_enc = self.pdf_document.is_encrypted
        dlg = PasswordProtectDialog(is_encrypted=is_enc, parent=self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        # Choose save path
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Protected PDF", self.pdf_file_path or "protected.pdf",
            "PDF Files (*.pdf)")
        if not path:
            return

        try:
            if dlg.remove_password:
                # Save without encryption
                self.pdf_document.save(path, encryption=fitz.PDF_ENCRYPT_NONE)
                self.status_bar.showMessage(
                    f"Saved without password: {os.path.basename(path)}")
            else:
                self.pdf_document.save(
                    path,
                    encryption=dlg.encryption,
                    user_pw=dlg.user_password,
                    owner_pw=dlg.owner_password,
                    permissions=dlg.permissions,
                    garbage=3, deflate=True)
                self.status_bar.showMessage(
                    f"Password protected PDF saved: {os.path.basename(path)}")
            self._add_to_recent(path)
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))

    def apply_redactions(self):
        """Burn all pending redaction boxes into the PDF permanently."""
        if not self.pdf_document:
            return
        total_boxes = sum(len(v) for v in self.pending_redactions.values())
        if total_boxes == 0:
            self.status_bar.showMessage(
                "No redactions pending. Use the Redact tool to draw boxes first.")
            return

        reply = QMessageBox.warning(
            self, "Apply Redactions",
            f"This will permanently black out {total_boxes} area(s) "
            f"across {len(self.pending_redactions)} page(s).\n\n"
            f"This action CANNOT be undone.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            for page_num, rects in self.pending_redactions.items():
                page = self.pdf_document.load_page(page_num)
                for r in rects:
                    annot = page.add_redact_annot(r)
                    annot.set_colors(fill=(0, 0, 0))
                    annot.update()
                page.apply_redactions()
            self.pending_redactions.clear()
            self.active_tool = TOOL_NONE
            self._sync_tool_buttons()
            self._update_cursor()
            self.update_view()
            self.refresh_annotations_panel()
            self.status_bar.showMessage(
                "Redactions applied. Save the document to make them permanent.")
        except Exception as e:
            self.status_bar.showMessage(f"Redaction error: {e}")

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

    def save_pdf(self):
        """Incremental save back to the same file, or prompt if no path set."""
        if not self.pdf_document:
            return
        if self.pdf_file_path:
            self._do_save(self.pdf_file_path)
        else:
            self.save_pdf_as()

    def save_pdf_as(self):
        if not self.pdf_document:
            return
        file_name, _ = QFileDialog.getSaveFileName(
            self, "Save PDF As", "", "PDF Files (*.pdf)")
        if file_name:
            self._do_save(file_name)
            self.pdf_file_path = file_name
            self.setWindowTitle(f"{APP_NAME}  –  {os.path.basename(file_name)}")

    def _do_save(self, path):
        try:
            # Bake annotations
            for pn, items in self.annotations.items():
                page = self.pdf_document.load_page(pn)
                existing_positions = set()
                for annot in page.annots():
                    if annot.type[0] == 8:
                        pos = annot.rect.top_left
                        existing_positions.add((round(pos.x), round(pos.y)))
                for x, y, text in items:
                    if (round(x), round(y)) not in existing_positions:
                        a = page.add_text_annot(fitz.Point(x, y), text)
                        a.set_colors(stroke=(1, 0.6, 0))
                        a.update()

            # Bake markup strokes (highlight / underline / strikethrough)
            for pn, strokes in self.markup_strokes.items():
                page = self.pdf_document.load_page(pn)
                for stroke in strokes:
                    if stroke.get("baked"):
                        continue
                    stype  = stroke["type"]
                    rects  = [fitz.Rect(r) for r in stroke.get("rects", [])]
                    color  = stroke.get("color", [1, 1, 0])
                    if stype == "highlight" and rects:
                        a = page.add_highlight_annot(rects)
                        a.set_colors(stroke=color)
                        a.update()
                    elif stype == "underline" and rects:
                        a = page.add_underline_annot(rects)
                        a.set_colors(stroke=color)
                        a.update()
                    elif stype == "strikethrough" and rects:
                        a = page.add_strikeout_annot(rects)
                        a.set_colors(stroke=color)
                        a.update()
                    elif stype == "freehand":
                        points = stroke.get("points", [])
                        if len(points) >= 2:
                            ink_list = [[fitz.Point(p[0], p[1]) for p in points]]
                            a = page.add_ink_annot(ink_list)
                            a.set_colors(stroke=color)
                            a.set_border(width=stroke.get("width", 2))
                            a.update()
                    elif stype == "signature":
                        # Signature is baked as an image annotation
                        img_bytes = stroke.get("image_bytes")
                        rect      = fitz.Rect(stroke.get("rect", [0, 0, 100, 50]))
                        if img_bytes:
                            page.insert_image(rect, stream=img_bytes)
                    stroke["baked"] = True

            self.pdf_document.save(path, garbage=3, deflate=True)
            save_annotations(self)
            self._save_markup_strokes(path)
            save_bookmarks(self)
            self._clear_modified()
            self.status_bar.showMessage(f"Saved: {path}")
        except Exception as e:
            self.status_bar.showMessage(f"Save error: {e}")

    # =========================================================================
    # Markup stroke persistence (sidebar JSON file, separate from annotations)
    # =========================================================================

    def _markup_path(self, pdf_path):
        return pdf_path + ".markup.json"

    def _load_markup_strokes(self, pdf_path):
        mp = self._markup_path(pdf_path)
        if os.path.exists(mp):
            try:
                with open(mp) as f:
                    raw = json.load(f)
                return {int(k): v for k, v in raw.items()}
            except (OSError, ValueError, KeyError) as e:
                import logging
                logging.warning("_load_markup_strokes: could not read '%s': %s", mp, e)
        return {}

    def _save_markup_strokes(self, pdf_path):
        mp = self._markup_path(pdf_path)
        try:
            with open(mp, "w") as f:
                json.dump(self.markup_strokes, f)
        except OSError as e:
            self.status_bar.showMessage(f"Warning: could not save markup strokes: {e}")

    # =========================================================================
    # Active tool management
    # =========================================================================

    def set_markup_tool(self, tool: str):
        """Toggle a markup tool on/off; deactivates any other tool."""
        if self.active_tool == tool:
            self.active_tool = TOOL_NONE
        else:
            self.active_tool = tool
            self.annotation_mode = False
        self._sync_tool_buttons()
        self._update_cursor()

    def clear_active_tool(self):
        self.active_tool = TOOL_NONE
        self.annotation_mode = False
        self._clear_tool_buttons()
        self._update_cursor()

    def _clear_tool_buttons(self):
        for btn in [self.annotate_button, self.highlight_button,
                    self.underline_button, self.strikethrough_button,
                    self.freehand_button, self.eraser_button,
                    self.signature_button]:
            btn.setChecked(False)

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
        }
        for tool, btn in mapping.items():
            btn.setChecked(self.active_tool == tool)

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
        }
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
            inv = matrix.invert()
        except ValueError:
            return

        # Click/drop point → PDF coordinates
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

        self.markup_strokes.setdefault(page_num, []).append({
            "type":        "signature",
            "rect":        list(pdf_rect),
            "image_bytes": list(img_bytes),
        })

        page.insert_image(pdf_rect, stream=img_bytes)
        self.render_page_content(page_num, page_widget)
        self.status_bar.showMessage("Signature placed. Save to embed permanently.")

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
            inv = matrix.invert()
        except ValueError:
            return
        pdf_pt = fitz.Point(click_x, click_y) * inv
        page   = self.pdf_document.load_page(page_num)
        rect   = fitz.Rect(pdf_pt.x - 80, pdf_pt.y - 20,
                           pdf_pt.x + 80, pdf_pt.y + 20)
        page.draw_rect(rect, color=(0.8, 0.1, 0.1), width=2)
        page.insert_text(
            fitz.Point(pdf_pt.x - 70, pdf_pt.y + 8),
            text, fontsize=16, color=(0.8, 0.1, 0.1))
        self._pending_stamp = None
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
            save_bookmarks(self)
            self.status_bar.showMessage(f"Bookmark added: {label}")

    def remove_bookmark(self):
        row = self.bookmark_list.currentRow()
        if row < 0 or row >= len(self.bookmarks):
            return
        removed = self.bookmarks.pop(row)
        self.refresh_bookmark_list()
        save_bookmarks(self)
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
    # Form fields
    # =========================================================================

    def _render_form_fields(self, page_num, widget):
        if page_num in self.field_widgets:
            for fw in self.field_widgets[page_num]:
                fw.deleteLater()
            del self.field_widgets[page_num]

        if page_num not in self.form_fields or not self.form_fields[page_num]:
            return

        # Form-field text scales with the accessibility text-size setting,
        # capped by the field's own height so it never overflows.
        _base = {"medium": 13, "large": 16, "xlarge": 20}.get(
            getattr(self, "ui_size", "medium"), 13)

        label_size  = widget.size()
        pixmap_size = widget.pixmap().size() if widget.pixmap() else QSize(0, 0)
        x_offset = (label_size.width()  - pixmap_size.width())  // 2
        y_offset = (label_size.height() - pixmap_size.height()) // 2
        matrix   = fitz.Matrix(self.zoom_level, self.zoom_level).prerotate(self.rotation)
        self.field_widgets[page_num] = []

        for field in self.form_fields[page_num]:
            tr = field.rect * matrix
            ftype = field.field_type

            if ftype == fitz.PDF_WIDGET_TYPE_TEXT:
                multiline = bool(field.field_flags & fitz.PDF_TX_FIELD_IS_MULTILINE)
                if multiline:
                    fw = QTextEdit(widget)
                    fw.setPlainText(field.field_value or "")
                    fw.textChanged.connect(
                        lambda f=field, te=fw: self._update_pdf_field(f, te.toPlainText()))
                else:
                    fw = QLineEdit(widget)
                    fw.setText(field.field_value or "")
                    fw.editingFinished.connect(
                        lambda f=field, le=fw: self._update_pdf_field(f, le.text()))
                fw.setGeometry(int(tr.x0 + x_offset), int(tr.y0 + y_offset),
                               int(tr.width), int(tr.height))
                _fs = max(11, min(_base, int(tr.height * 0.6)))
                fw.setStyleSheet(
                    "border: 1px solid #4a90d9; background: rgba(220,235,255,180);"
                    f"border-radius: 2px; font-size: {_fs}px;")
                fw.setToolTip(field.field_name or "Text field")
                self.field_widgets[page_num].append(fw)
                fw.show()

            elif ftype == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                fw = QCheckBox(widget)
                fw.setChecked(field.field_value not in ("", "Off", None))
                cb_size = min(int(tr.width), int(tr.height))
                fw.setGeometry(int(tr.x0 + x_offset), int(tr.y0 + y_offset),
                               cb_size, cb_size)
                fw.stateChanged.connect(
                    lambda state, f=field: self._save_checkbox_field(f, state))
                fw.setToolTip(field.field_name or "Checkbox")
                self.field_widgets[page_num].append(fw)
                fw.show()

            elif ftype == fitz.PDF_WIDGET_TYPE_RADIOBUTTON:
                fw = QRadioButton(widget)
                fw.setChecked(field.field_value not in ("", "Off", None))
                rb_size = min(int(tr.width), int(tr.height))
                fw.setGeometry(int(tr.x0 + x_offset), int(tr.y0 + y_offset),
                               rb_size, rb_size)
                fw.toggled.connect(
                    lambda checked, f=field: self._update_pdf_field(
                        f, f.field_name if checked else "Off"))
                fw.setToolTip(field.field_name or "Radio button")
                self.field_widgets[page_num].append(fw)
                fw.show()

            elif ftype == fitz.PDF_WIDGET_TYPE_COMBOBOX:
                fw = QComboBox(widget)
                for choice in (field.choice_values or []):
                    fw.addItem(choice)
                if field.field_value:
                    idx = fw.findText(field.field_value)
                    if idx >= 0:
                        fw.setCurrentIndex(idx)
                fw.setGeometry(int(tr.x0 + x_offset), int(tr.y0 + y_offset),
                               int(tr.width), int(tr.height))
                fw.currentTextChanged.connect(
                    lambda txt, f=field: self._update_pdf_field(f, txt))
                fw.setToolTip(field.field_name or "Combo box")
                self.field_widgets[page_num].append(fw)
                fw.show()

            elif ftype == fitz.PDF_WIDGET_TYPE_LISTBOX:
                fw = QListWidgetItem()  # placeholder; list boxes are rare
                # A full listbox widget could be added here if needed

        widget.update()

    def _reposition_form_fields(self, page_num, widget):
        """Reposition existing Qt form widgets when the page label resizes."""
        if page_num not in self.field_widgets or \
                page_num not in self.form_fields:
            return
        label_size  = widget.size()
        pixmap_size = widget.pixmap().size() if widget.pixmap() else QSize(0, 0)
        x_offset = (label_size.width()  - pixmap_size.width())  // 2
        y_offset = (label_size.height() - pixmap_size.height()) // 2
        matrix   = fitz.Matrix(self.zoom_level, self.zoom_level).prerotate(self.rotation)
        for fw, field in zip(self.field_widgets[page_num], self.form_fields[page_num]):
            tr = field.rect * matrix
            fw.setGeometry(int(tr.x0 + x_offset), int(tr.y0 + y_offset),
                           int(tr.width), int(tr.height))

    def _update_pdf_field(self, field, value):
        try:
            field.field_value = value
            field.update()
            self._form_dirty = True
        except Exception as e:
            self.status_bar.showMessage(f"Field update error: {e}")

    def _save_checkbox_field(self, fitz_widget, state):
        try:
            field_values = fitz_widget.field_values()
            off_val = field_values[0] if len(field_values) > 0 else "Off"
            on_val  = field_values[1] if len(field_values) > 1 else "Yes"
        except (AttributeError, TypeError):
            off_val, on_val = "Off", "Yes"
        value = on_val if state == Qt.CheckState.Checked.value else off_val
        try:
            fitz_widget.field_value = value
            fitz_widget.update()
            self._form_dirty = True
        except Exception as e:
            self.status_bar.showMessage(f"Checkbox error: {e}")

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
            return fitz.Point(px, py) * matrix.invert()
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
                    save_annotations(self)
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

        # ── Redaction drag start ─────────────────────────────────────────
        if btn == Qt.MouseButton.LeftButton and self.active_tool == TOOL_REDACT:
            self.is_selecting_text       = True
            self.selection_start_point   = event.position().toPoint()
            self.selection_end_point     = event.position().toPoint()
            self.current_selection_page  = page_num
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

        if (self._freehand_drawing and
                self.active_tool == TOOL_FREEHAND and
                event.button() == Qt.MouseButton.LeftButton):
            self._freehand_drawing = False
            if len(self._freehand_points) >= 2:
                matrix = fitz.Matrix(self.zoom_level, self.zoom_level)
                try:
                    inv = matrix.invert()
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
            self._freehand_points = []
            self._freehand_page   = -1
            self.render_page_content(page_num, page_widget)
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
                    self.pending_redactions.setdefault(page_num, []).append(pdf_rect)
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
            inv = matrix.invert()
        except ValueError:
            return None
        return fitz.Rect(x0, y0, x1, y1) * inv

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
        """Remove an annotation entry from its backing store."""
        source = data.get("source")
        page   = data.get("page", -1)

        if source == "note":
            x, y = data.get("x"), data.get("y")
            if page in self.annotations:
                self.annotations[page] = [
                    (ax, ay, t) for ax, ay, t in self.annotations[page]
                    if not (abs(ax - x) < 1 and abs(ay - y) < 1)]
                if not self.annotations[page]:
                    del self.annotations[page]
                save_annotations(self)

        elif source == "markup":
            idx = data.get("stroke_idx")
            if page in self.markup_strokes and idx is not None:
                strokes = self.markup_strokes[page]
                if 0 <= idx < len(strokes):
                    strokes.pop(idx)

        elif source == "redaction":
            ridx = data.get("rect_idx")
            if page in self.pending_redactions and ridx is not None:
                rects = self.pending_redactions[page]
                if 0 <= ridx < len(rects):
                    rects.pop(ridx)
                if not self.pending_redactions[page]:
                    del self.pending_redactions[page]

        elif source == "pdf":
            xref = data.get("annot_xref")
            if xref and self.pdf_document:
                p = self.pdf_document.load_page(page)
                for annot in p.annots():
                    if annot.xref == xref:
                        p.delete_annot(annot)
                        break

        # Re-render and refresh panel
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
        from ocr_dialog import OCRDialog
        dlg = OCRDialog(
            pdf_path=self.pdf_file_path,
            total_pages=self.total_pages,
            current_page=self.current_page,
            parent=self)
        if dlg.exec() and dlg.output_path:
            # Reload the OCR'd document
            reply = QMessageBox.question(
                self, "OCR Complete",
                f"OCR finished.\n\nOutput saved to:\n{dlg.output_path}"
                "\n\nOpen the OCR'd document now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes)
            if reply == QMessageBox.StandardButton.Yes:
                self._open_pdf_path(dlg.output_path)

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
        # Pre-select format
        if fmt == "xlsx":
            dlg._rb_xlsx.setChecked(True)
        dlg.exec()

    def closeEvent(self, event):
        """Auto-save form data and persist window geometry on close."""
        self._autosave_form_data()
        self.settings.setValue("window_geometry", self.saveGeometry())
        self.settings.setValue("window_state", self.saveState())
        self._save_sidebar_state()
        self.settings.setValue("prefs/zoom_level",   self.zoom_level)
        self.settings.setValue("prefs/view_mode",    self.view_mode)
        self.settings.setValue("prefs/dark_mode",    self.dark_mode)
        self.settings.setValue("prefs/markup_color", self.markup_color.name())
        super().closeEvent(event)

    # =========================================================================
    # Save a Copy  (Phase 0 – new safe save option)
    # =========================================================================

    def save_a_copy(self):
        """Save a copy of the current document to a new path without changing
        the working path (safe alternative to Save As)."""
        if not self.pdf_document:
            return
        default = self.pdf_file_path or "copy.pdf"
        if default:
            import os as _os
            base, ext = _os.path.splitext(default)
            default = base + "_copy" + ext
        file_name, _ = QFileDialog.getSaveFileName(
            self, "Save a Copy", default, "PDF Files (*.pdf)")
        if file_name:
            try:
                self.pdf_document.save(file_name, garbage=3, deflate=True)
                self.status_bar.showMessage(f"Copy saved: {file_name}")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", str(e))

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
            self._finish_page_op("Page insert undone." if direction == "undo" else "Page insert redone.")

        elif kind == "page_remove":
            page_num  = data["page"]
            page_bytes = data.get("page_bytes")
            if direction == "undo" and page_bytes and self.pdf_document:
                # Re-insert from saved bytes
                tmp = fitz.open(stream=page_bytes, filetype="pdf")
                self.pdf_document.insert_pdf(tmp, from_page=0, to_page=0,
                                              start_at=page_num)
                self.total_pages += 1
                self.current_page = page_num
                self._finish_page_op("Page deletion undone.")
            elif direction == "redo" and self.pdf_document:
                self.pdf_document.delete_page(page_num)
                self.total_pages -= 1
                if self.current_page >= self.total_pages:
                    self.current_page = self.total_pages - 1
                self._finish_page_op("Page deletion redone.")

        elif kind == "page_move":
            frm = data["from"]
            to  = data["to"]
            if self.pdf_document:
                self.pdf_document.move_page(frm, to)
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
    # Form: auto-save & reset  (Phase 2)
    # =========================================================================

    def _autosave_form_data(self):
        """Persist in-memory form field values back into the fitz document."""
        if not self.pdf_document or not self._form_dirty:
            return
        import logging
        for page_num, fields in self.form_fields.items():
            for field in fields:
                try:
                    field.update()
                except Exception as e:
                    logging.warning(
                        "_autosave_form_data: failed updating field on page %d: %s",
                        page_num, e)
        self._form_dirty = False

    def reset_form(self):
        """Reset all form fields on the current page to their default values."""
        if not self.pdf_document:
            return
        pn = self.current_page
        if pn not in self.form_fields:
            self.status_bar.showMessage("No form fields on this page.")
            return
        reply = QMessageBox.question(
            self, "Reset Form",
            f"Reset all form fields on page {pn + 1} to their defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            page = self.pdf_document.load_page(pn)
            for widget in page.widgets():
                widget.field_value = widget.field_value_default or ""
                widget.update()
            self.form_fields[pn] = list(page.widgets())
            self.render_page_content(pn, self.page_widgets[pn])
            self.status_bar.showMessage(f"Form fields on page {pn + 1} reset.")
        except Exception as e:
            self.status_bar.showMessage(f"Reset error: {e}")

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


