"""
ocr_dialog.py
-------------
OCR dialog.

Runs pytesseract + pdf2image on the open document in a background thread,
bakes the resulting text layer back into the PDF via PyMuPDF, and re-opens
the result so the document becomes fully searchable and copy-able.

Requirements (pip):
    pytesseract
    pdf2image
    Pillow

System:
    Tesseract-OCR  (https://github.com/UB-Mannheim/tesseract/wiki  – Windows)
    poppler         (for pdf2image on Windows: https://github.com/oschwartz10612/poppler-windows)
"""
from __future__ import annotations
import os
import fitz  # PyMuPDF  (https://pymupdf.readthedocs.io/)
import tempfile

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QProgressBar, QCheckBox, QGroupBox, QRadioButton,
    QButtonGroup, QLineEdit, QMessageBox, QSizePolicy, QFrame)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont


# ── Availability check ────────────────────────────────────────────────────────

def _check_dependencies() -> tuple[bool, str]:
    """Return (ok, message). ok=True means both tesseract and pdf2image work."""
    missing = []
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
    except Exception:
        missing.append("Tesseract-OCR (not installed or not on PATH)")
    try:
        import pdf2image  # noqa: F401
    except ImportError:
        missing.append("pdf2image  (pip install pdf2image)")
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        missing.append("Pillow  (pip install Pillow)")
    if missing:
        return False, "Missing dependencies:\n• " + "\n• ".join(missing)
    return True, ""


# ── Worker thread ─────────────────────────────────────────────────────────────

class OCRWorker(QThread):
    progress      = pyqtSignal(int, int, str)   # current, total, message
    finished      = pyqtSignal(str)             # path to OCR'd PDF
    error         = pyqtSignal(str)

    def __init__(self, pdf_path: str, page_indices: list[int],
                 lang: str, output_path: str):
        super().__init__()
        self.pdf_path     = pdf_path
        self.page_indices = page_indices   # 0-based
        self.lang         = lang
        self.output_path  = output_path
        self._cancelled   = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            import fitz
            import pytesseract
            from pdf2image import convert_from_path

            doc  = fitz.open(self.pdf_path)
            total = len(self.page_indices)

            for step, page_idx in enumerate(self.page_indices):
                if self._cancelled:
                    doc.close()
                    self.error.emit("OCR cancelled.")
                    return

                self.progress.emit(step, total,
                                   f"Processing page {page_idx + 1}…")

                # Render that page to a PIL image at 300 dpi
                images = convert_from_path(
                    self.pdf_path,
                    dpi=300,
                    first_page=page_idx + 1,
                    last_page=page_idx + 1,
                )
                if not images:
                    continue
                pil_img = images[0]

                # Run Tesseract — get hOCR (bbox-aware XML)
                hocr_bytes = pytesseract.image_to_pdf_or_hocr(
                    pil_img, lang=self.lang, extension="hocr")

                # Build a tiny invisible text layer from hOCR and overlay onto page
                self._overlay_hocr(doc, page_idx, pil_img, hocr_bytes)

            self.progress.emit(total, total, "Saving…")
            doc.save(self.output_path, garbage=3, deflate=True)
            doc.close()
            self.finished.emit(self.output_path)

        except Exception as exc:
            self.error.emit(str(exc))

    # ── hOCR → invisible text overlay ────────────────────────────────────

    @staticmethod
    def _overlay_hocr(doc: "fitz.Document", page_idx: int,
                      pil_img, hocr_bytes: bytes):
        """Parse hOCR and insert invisible (OCR) text onto the fitz page."""
        import fitz
        from xml.etree import ElementTree as ET
        import re

        page    = doc.load_page(page_idx)
        pg_rect = page.rect
        img_w, img_h = pil_img.size  # pixels at 300 dpi

        # Scale factor: map pixel coords → PDF pt coords
        sx = pg_rect.width  / img_w
        sy = pg_rect.height / img_h

        root = ET.fromstring(hocr_bytes)
        ns   = {"h": "http://www.w3.org/1999/xhtml"}

        def _find_all(node, tag):
            # Walk regardless of namespace
            results = []
            for child in node.iter():
                local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if local == tag:
                    results.append(child)
            return results

        words = _find_all(root, "span")
        for span in words:
            cls = span.get("class", "")
            if "ocrx_word" not in cls:
                continue
            title = span.get("title", "")
            m = re.search(r"bbox\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", title)
            if not m:
                continue
            x0, y0, x1, y1 = (int(m.group(i)) for i in range(1, 5))
            text = (span.text or "").strip()
            if not text:
                continue

            # Convert to PDF coordinates
            rect = fitz.Rect(x0 * sx, y0 * sy, x1 * sx, y1 * sy)
            if rect.is_empty or rect.is_infinite:
                continue

            # Font size: fill height of bbox
            fs = max(4.0, rect.height * 0.85)

            # Insert invisible text (render mode 3 = invisible)
            try:
                page.insert_text(
                    rect.tl,
                    text + " ",
                    fontsize=fs,
                    color=(0, 0, 0),
                    render_mode=3,   # invisible
                    overlay=True,
                )
            except Exception:
                pass  # skip malformed words silently


# ── Language helpers ──────────────────────────────────────────────────────────

_LANG_DISPLAY = {
    "eng":     "English",
    "fra":     "French",
    "deu":     "German",
    "spa":     "Spanish",
    "ita":     "Italian",
    "por":     "Portuguese",
    "nld":     "Dutch",
    "pol":     "Polish",
    "rus":     "Russian",
    "chi_sim": "Chinese (Simplified)",
    "chi_tra": "Chinese (Traditional)",
    "jpn":     "Japanese",
    "kor":     "Korean",
    "ara":     "Arabic",
    "hin":     "Hindi",
}


def _available_langs() -> list[tuple[str, str]]:
    """Return [(code, display_name)] for installed Tesseract languages."""
    try:
        import pytesseract
        codes = pytesseract.get_languages(config="")
        result = []
        for code in sorted(codes):
            if code == "osd":
                continue
            result.append((code, _LANG_DISPLAY.get(code, code)))
        return result or [("eng", "English")]
    except Exception:
        return [("eng", "English")]


# ── Dialog ────────────────────────────────────────────────────────────────────

class OCRDialog(QDialog):
    """
    OCR settings + progress dialog.

    Usage:
        dlg = OCRDialog(pdf_path, total_pages, current_page, parent=self)
        if dlg.exec():
            output_path = dlg.output_path   # path to the OCR'd PDF
    """

    def __init__(self, pdf_path: str, total_pages: int,
                 current_page: int, parent=None):
        super().__init__(parent)
        self.pdf_path     = pdf_path
        self.total_pages  = total_pages
        self.current_page = current_page
        self.output_path  = ""
        self._worker: OCRWorker | None = None

        self.setWindowTitle("Run OCR")
        self.setMinimumWidth(420)
        self.setModal(True)
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        # ── Header ────────────────────────────────────────────────────────
        title = QLabel("🔍  Run OCR on Document")
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        title.setFont(f)
        root.addWidget(title)

        subtitle = QLabel(
            "Makes scanned pages searchable and copy-able by adding an\n"
            "invisible text layer using Tesseract OCR.")
        subtitle.setStyleSheet("color: #666; font-size: 11px;")
        root.addWidget(subtitle)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #ddd;")
        root.addWidget(sep)

        # ── Page scope ────────────────────────────────────────────────────
        scope_box = QGroupBox("Pages to process")
        scope_layout = QVBoxLayout(scope_box)
        scope_layout.setSpacing(6)

        self._scope_group = QButtonGroup(self)
        self._rb_all     = QRadioButton(f"All pages  ({self.total_pages} pages)")
        self._rb_current = QRadioButton(f"Current page only  (page {self.current_page + 1})")
        self._rb_range   = QRadioButton("Page range:")
        self._rb_all.setChecked(True)

        self._scope_group.addButton(self._rb_all,     0)
        self._scope_group.addButton(self._rb_current, 1)
        self._scope_group.addButton(self._rb_range,   2)

        range_row = QHBoxLayout()
        range_row.setContentsMargins(20, 0, 0, 0)
        self._range_input = QLineEdit()
        self._range_input.setPlaceholderText("e.g.  1-5, 8, 12-15")
        self._range_input.setEnabled(False)
        self._range_input.setFixedWidth(200)
        range_row.addWidget(self._range_input)
        range_row.addStretch()

        scope_layout.addWidget(self._rb_all)
        scope_layout.addWidget(self._rb_current)
        scope_layout.addWidget(self._rb_range)
        scope_layout.addLayout(range_row)
        root.addWidget(scope_box)

        self._rb_range.toggled.connect(self._range_input.setEnabled)

        # ── Language ──────────────────────────────────────────────────────
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("OCR Language:"))
        self._lang_combo = QComboBox()
        self._lang_combo.setFixedWidth(200)
        for code, name in _available_langs():
            self._lang_combo.addItem(name, userData=code)
        lang_row.addWidget(self._lang_combo)
        lang_row.addStretch()
        root.addLayout(lang_row)

        # ── Output option ─────────────────────────────────────────────────
        self._cb_overwrite = QCheckBox(
            "Replace original file  (unchecked = save as new file)")
        self._cb_overwrite.setChecked(False)
        root.addWidget(self._cb_overwrite)

        # ── Progress bar (hidden until run) ───────────────────────────────
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setMinimum(0)
        root.addWidget(self._progress)

        self._progress_label = QLabel("")
        self._progress_label.setVisible(False)
        self._progress_label.setStyleSheet("color: #555; font-size: 11px;")
        root.addWidget(self._progress_label)

        # ── Buttons ───────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._btn_run    = QPushButton("▶  Run OCR")
        self._btn_run.setDefault(True)
        self._btn_run.setStyleSheet(
            "background:#3a7bd5; color:white; font-weight:bold;"
            "border-radius:4px; padding:6px 18px;")
        self._btn_cancel = QPushButton("Cancel")
        btn_row.addStretch()
        btn_row.addWidget(self._btn_cancel)
        btn_row.addWidget(self._btn_run)
        root.addLayout(btn_row)

        self._btn_run.clicked.connect(self._run_ocr)
        self._btn_cancel.clicked.connect(self._on_cancel)

    # ── Slots ─────────────────────────────────────────────────────────────

    def _run_ocr(self):
        ok, msg = _check_dependencies()
        if not ok:
            QMessageBox.critical(self, "Missing Dependencies", msg)
            return

        pages = self._resolve_pages()
        if pages is None:
            return   # validation error already shown

        lang = self._lang_combo.currentData() or "eng"

        if self._cb_overwrite.isChecked():
            out_path = self.pdf_path
        else:
            base, ext = os.path.splitext(self.pdf_path)
            out_path  = base + "_ocr" + ext

        # UI → running state
        self._btn_run.setEnabled(False)
        self._btn_cancel.setText("Stop")
        self._progress.setMaximum(len(pages))
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._progress_label.setVisible(True)
        self._progress_label.setText("Starting…")

        self._worker = OCRWorker(self.pdf_path, pages, lang, out_path)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, current: int, total: int, msg: str):
        self._progress.setValue(current)
        self._progress_label.setText(msg)

    def _on_finished(self, out_path: str):
        self.output_path = out_path
        self._progress.setValue(self._progress.maximum())
        self._progress_label.setText("Done ✓")
        self._btn_cancel.setText("Close")
        self._btn_cancel.clicked.disconnect()
        self._btn_cancel.clicked.connect(self.accept)
        self._btn_run.setEnabled(False)

    def _on_error(self, msg: str):
        self._progress.setVisible(False)
        self._progress_label.setVisible(False)
        self._btn_run.setEnabled(True)
        self._btn_cancel.setText("Cancel")
        QMessageBox.critical(self, "OCR Error", msg)

    def _on_cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)
        self.reject()

    # ── Helpers ───────────────────────────────────────────────────────────

    def _resolve_pages(self) -> list[int] | None:
        """Return 0-based page indices from the current scope selection."""
        btn_id = self._scope_group.checkedId()
        if btn_id == 0:
            return list(range(self.total_pages))
        if btn_id == 1:
            return [self.current_page]
        # Range parse
        raw = self._range_input.text().strip()
        if not raw:
            QMessageBox.warning(self, "Page Range", "Please enter a page range.")
            return None
        indices = set()
        try:
            for part in raw.split(","):
                part = part.strip()
                if "-" in part:
                    a, b = part.split("-", 1)
                    for i in range(int(a) - 1, int(b)):
                        if 0 <= i < self.total_pages:
                            indices.add(i)
                else:
                    i = int(part) - 1
                    if 0 <= i < self.total_pages:
                        indices.add(i)
        except ValueError:
            QMessageBox.warning(self, "Page Range",
                                f"Could not parse range: '{raw}'\n"
                                "Use format: 1-5, 8, 12-15")
            return None
        if not indices:
            QMessageBox.warning(self, "Page Range",
                                "No valid pages in that range.")
            return None
        return sorted(indices)
