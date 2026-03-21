"""
extract_pages_dialog.py
-----------------------
Extract a selection of pages from the current PDF into a new file.
Selection via checkbox list with thumbnails, or by typing a range string.
"""
import os
import fitz

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QFileDialog,
    QFrame, QMessageBox, QProgressBar, QCheckBox, QAbstractItemView,
    QScrollArea, QWidget, QSizePolicy, QButtonGroup, QRadioButton)
from PyQt6.QtGui import QIcon, QPixmap, QImage, QFont
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal


ACCENT  = "#2563EB"
ACCENT_L = "#EFF6FF"
DARK    = "#1e293b"
MID     = "#64748b"
LIGHT   = "#f8fafc"
SUCCESS = "#16a34a"
DANGER  = "#dc2626"


class ExtractWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(self, src_path: str, page_indices: list[int], out_path: str):
        super().__init__()
        self.src_path     = src_path
        self.page_indices = page_indices   # 0-based
        self.out_path     = out_path

    def run(self):
        try:
            src  = fitz.open(self.src_path)
            out  = fitz.open()
            n    = len(self.page_indices)
            for i, idx in enumerate(self.page_indices):
                self.progress.emit(int(i / n * 90),
                                   f"Extracting page {idx + 1}…")
                out.insert_pdf(src, from_page=idx, to_page=idx)
            self.progress.emit(95, "Saving…")
            out.save(self.out_path, garbage=3, deflate=True)
            out.close()
            src.close()
            self.progress.emit(100, "Done")
            self.finished.emit(True, self.out_path)
        except Exception as e:
            self.finished.emit(False, str(e))


class ExtractPagesDialog(QDialog):
    open_file_requested = pyqtSignal(str)

    def __init__(self, pdf_document: fitz.Document,
                 pdf_file_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Extract Pages")
        self.setModal(True)
        self.setMinimumSize(580, 580)
        self.resize(620, 640)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        self._doc      = pdf_document
        self._src_path = pdf_file_path
        self._total    = pdf_document.page_count
        self._worker   = None
        self._build_ui()

    # =========================================================================
    # UI
    # =========================================================================

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._make_header())

        body = QWidget()
        body.setStyleSheet(f"background: {LIGHT};")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 16, 20, 12)
        bl.setSpacing(10)

        # ── Selection mode toggle ─────────────────────────────────────────
        mode_row = QHBoxLayout()
        self._rb_visual  = QRadioButton("Select pages visually")
        self._rb_range   = QRadioButton("Enter page range")
        self._rb_visual.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self._rb_visual)
        grp.addButton(self._rb_range)
        for rb in [self._rb_visual, self._rb_range]:
            rb.setStyleSheet(f"font-size: 12px; color: {DARK};")
        mode_row.addWidget(self._rb_visual)
        mode_row.addSpacing(20)
        mode_row.addWidget(self._rb_range)
        mode_row.addStretch()
        bl.addLayout(mode_row)

        # ── Visual page list ──────────────────────────────────────────────
        self._visual_widget = QWidget()
        vl = QVBoxLayout(self._visual_widget)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(6)

        sel_row = QHBoxLayout()
        sel_all = QPushButton("Select All")
        sel_none = QPushButton("Select None")
        sel_even = QPushButton("Even Pages")
        sel_odd  = QPushButton("Odd Pages")
        for b in [sel_all, sel_none, sel_even, sel_odd]:
            b.setFixedHeight(26)
            b.setStyleSheet(self._small_btn_style())
            sel_row.addWidget(b)
        sel_row.addStretch()
        vl.addLayout(sel_row)

        self.page_list = QListWidget()
        self.page_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.page_list.setIconSize(QSize(80, 110))
        self.page_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.page_list.setSpacing(6)
        self.page_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self.page_list.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid #e2e8f0; border-radius: 6px;
                background: white;
            }}
            QListWidget::item {{
                border: 2px solid transparent;
                border-radius: 4px;
                padding: 4px;
            }}
        """)
        self._load_thumbnails()
        vl.addWidget(self.page_list)

        sel_all.clicked.connect(lambda: self._set_all(True))
        sel_none.clicked.connect(lambda: self._set_all(False))
        sel_even.clicked.connect(lambda: self._set_pattern("even"))
        sel_odd.clicked.connect(lambda: self._set_pattern("odd"))

        bl.addWidget(self._visual_widget)

        # ── Range input ───────────────────────────────────────────────────
        self._range_widget = QWidget()
        rl = QVBoxLayout(self._range_widget)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)
        hint = QLabel(
            f"Enter page numbers or ranges separated by commas.\n"
            f"Example:  1-3, 5, 7-9   (document has {self._total} pages)")
        hint.setStyleSheet(
            f"color: {MID}; font-size: 11px; background: {ACCENT_L};"
            f" border: 1px solid #bfdbfe; border-radius: 5px; padding: 8px 12px;")
        hint.setWordWrap(True)
        self._range_edit = QLineEdit()
        self._range_edit.setPlaceholderText(f"e.g.  1-3, 5, 7-{self._total}")
        self._range_edit.setStyleSheet(
            "border: 1px solid #e2e8f0; border-radius: 4px;"
            " padding: 6px 10px; font-size: 13px; background: white;")
        self._range_edit.setFixedHeight(38)
        rl.addWidget(hint)
        rl.addWidget(self._range_edit)
        rl.addStretch()
        self._range_widget.hide()
        bl.addWidget(self._range_widget)

        # Toggle between modes
        self._rb_visual.toggled.connect(self._toggle_mode)

        # ── Output path ───────────────────────────────────────────────────
        bl.addWidget(_divider())
        out_label = QLabel("Save extracted pages as:")
        out_label.setStyleSheet(
            f"font-size: 12px; font-weight: bold; color: {DARK};")
        bl.addWidget(out_label)
        out_row = QHBoxLayout()
        self._out_edit = QLineEdit()
        self._out_edit.setPlaceholderText("Choose output file path…")
        self._out_edit.setStyleSheet(
            "border: 1px solid #e2e8f0; border-radius: 4px;"
            " padding: 4px 8px; font-size: 12px; background: white;")
        browse = QPushButton("Browse…")
        browse.setFixedHeight(30)
        browse.setStyleSheet(self._small_btn_style())
        browse.clicked.connect(self._browse_output)
        out_row.addWidget(self._out_edit)
        out_row.addWidget(browse)
        bl.addLayout(out_row)

        bl.addStretch()
        root.addWidget(body, stretch=1)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{ background: #e2e8f0; border: none; }}
            QProgressBar::chunk {{ background: {ACCENT}; }}
        """)
        self.progress_bar.hide()
        root.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            f"color: {MID}; font-size: 11px; padding: 3px 16px;")
        root.addWidget(self.status_label)

        root.addWidget(self._make_footer())

    def _make_header(self):
        w = QWidget()
        w.setFixedHeight(64)
        w.setStyleSheet(f"background: {DARK};")
        row = QHBoxLayout(w)
        row.setContentsMargins(24, 0, 24, 0)
        row.setSpacing(14)
        icon = QLabel("✂")
        icon.setStyleSheet("font-size: 26px; background: transparent;")
        row.addWidget(icon)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel("Extract Pages")
        t.setStyleSheet("color: white; font-size: 17px; font-weight: bold;"
                        " background: transparent;")
        s = QLabel(
            f"Save a selection of pages as a new PDF  "
            f"·  {os.path.basename(self._src_path)}  "
            f"({self._total} pages)")
        s.setStyleSheet(f"color: #94a3b8; font-size: 11px; background: transparent;")
        col.addWidget(t)
        col.addWidget(s)
        row.addLayout(col)
        row.addStretch()
        return w

    def _make_footer(self):
        w = QWidget()
        w.setFixedHeight(54)
        w.setStyleSheet("background: #f1f5f9; border-top: 1px solid #e2e8f0;")
        row = QHBoxLayout(w)
        row.setContentsMargins(20, 0, 20, 0)
        row.setSpacing(8)

        self._sel_label = QLabel("")
        self._sel_label.setStyleSheet(
            f"color: {MID}; font-size: 11px;")
        row.addWidget(self._sel_label)
        row.addStretch()

        self.run_btn = QPushButton("✂  Extract")
        self.run_btn.setFixedSize(110, 34)
        self.run_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT}; color: white;
                border: none; border-radius: 5px;
                font-size: 13px; font-weight: bold;
            }}
            QPushButton:hover   {{ background: #1d4ed8; }}
            QPushButton:pressed {{ background: #1e40af; }}
            QPushButton:disabled{{ background: #93c5fd; }}
        """)
        self.run_btn.clicked.connect(self._run)

        close_btn = QPushButton("Close")
        close_btn.setFixedSize(80, 34)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: white; color: {DARK};
                border: 1px solid #cbd5e1; border-radius: 5px;
                font-size: 12px;
            }}
            QPushButton:hover {{ background: #f1f5f9; }}
        """)
        close_btn.clicked.connect(self.reject)
        row.addWidget(self.run_btn)
        row.addWidget(close_btn)
        return w

    # =========================================================================
    # Thumbnail loading
    # =========================================================================

    def _load_thumbnails(self):
        self.page_list.clear()
        for pn in range(self._total):
            page = self._doc.load_page(pn)
            pix  = page.get_pixmap(matrix=fitz.Matrix(0.18, 0.18))
            img  = QImage(pix.samples, pix.width, pix.height,
                          pix.stride, QImage.Format.Format_RGB888)
            qpix = QPixmap.fromImage(img)

            item = QListWidgetItem()
            item.setIcon(QIcon(qpix))
            item.setText(f"  {pn + 1}")
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter |
                                  Qt.AlignmentFlag.AlignBottom)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, pn)
            self.page_list.addItem(item)

        self.page_list.itemChanged.connect(self._update_sel_label)
        self._update_sel_label()

    # =========================================================================
    # Selection helpers
    # =========================================================================

    def _set_all(self, checked: bool):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.page_list.count()):
            self.page_list.item(i).setCheckState(state)

    def _set_pattern(self, pattern: str):
        for i in range(self.page_list.count()):
            item = self.page_list.item(i)
            pn   = item.data(Qt.ItemDataRole.UserRole)   # 0-based
            if pattern == "even":
                on = (pn % 2 == 1)   # even page numbers are 0-based odd
            else:
                on = (pn % 2 == 0)
            item.setCheckState(
                Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def _update_sel_label(self):
        n = sum(1 for i in range(self.page_list.count())
                if self.page_list.item(i).checkState() == Qt.CheckState.Checked)
        self._sel_label.setText(f"{n} of {self._total} pages selected")

    def _toggle_mode(self, visual: bool):
        self._visual_widget.setVisible(visual)
        self._range_widget.setVisible(not visual)

    def _selected_indices(self) -> list[int]:
        """Return sorted 0-based page indices from whichever mode is active."""
        if self._rb_visual.isChecked():
            return sorted(
                self.page_list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.page_list.count())
                if self.page_list.item(i).checkState() == Qt.CheckState.Checked)
        else:
            return self._parse_range(self._range_edit.text().strip())

    def _parse_range(self, text: str) -> list[int] | None:
        indices = set()
        for part in text.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                bits = part.split("-")
                if len(bits) != 2:
                    return None
                try:
                    s, e = int(bits[0]) - 1, int(bits[1]) - 1
                except ValueError:
                    return None
                if s < 0 or e >= self._total or s > e:
                    return None
                indices.update(range(s, e + 1))
            else:
                try:
                    n = int(part) - 1
                except ValueError:
                    return None
                if n < 0 or n >= self._total:
                    return None
                indices.add(n)
        return sorted(indices) if indices else None

    def _browse_output(self):
        base = os.path.splitext(os.path.basename(self._src_path))[0]
        suggestion = os.path.join(
            os.path.dirname(self._src_path), f"{base}_extract.pdf")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Extracted Pages As", suggestion, "PDF Files (*.pdf)")
        if path:
            self._out_edit.setText(path)

    # =========================================================================
    # Run
    # =========================================================================

    def _run(self):
        indices = self._selected_indices()
        if indices is None:
            QMessageBox.warning(self, "Extract Pages",
                                "Invalid page range — check your input.")
            return
        if not indices:
            QMessageBox.warning(self, "Extract Pages",
                                "No pages selected.")
            return
        out = self._out_edit.text().strip()
        if not out:
            QMessageBox.warning(self, "Extract Pages",
                                "Choose an output file path.")
            return
        if not out.lower().endswith(".pdf"):
            out += ".pdf"

        self.run_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.status_label.setText("Working…")

        self._worker = ExtractWorker(self._src_path, indices, out)
        self._worker.progress.connect(
            lambda pct, msg: (self.progress_bar.setValue(pct),
                              self.status_label.setText(msg)))
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _on_done(self, ok: bool, msg: str):
        self.run_btn.setEnabled(True)
        self.progress_bar.hide()
        if ok:
            self.status_label.setText(
                f"✔  Saved → {os.path.basename(msg)}")
            self.status_label.setStyleSheet(
                f"color: {SUCCESS}; font-size: 11px; padding: 3px 16px;"
                " font-weight: bold;")
            reply = QMessageBox.question(
                self, "Extract Complete",
                f"Pages extracted successfully.\n\n{msg}\n\nOpen it now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.open_file_requested.emit(msg)
                self.accept()
        else:
            self.status_label.setText(f"✖  {msg}")
            self.status_label.setStyleSheet(
                f"color: {DANGER}; font-size: 11px; padding: 3px 16px;"
                " font-weight: bold;")
            QMessageBox.critical(self, "Error", f"Extraction failed:\n{msg}")

    # =========================================================================
    # Helpers
    # =========================================================================

    @staticmethod
    def _small_btn_style():
        return (
            f"QPushButton {{ background: white; color: {DARK};"
            f" border: 1px solid #d0d0d0; border-radius: 4px;"
            f" font-size: 11px; padding: 2px 8px; }}"
            f"QPushButton:hover {{ background: #e3ebf8; border-color: #b5c9e8; }}"
            f"QPushButton:pressed {{ background: #c5d8f5; }}"
        )


def _divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet("background: #e2e8f0; border: none;")
    return f
