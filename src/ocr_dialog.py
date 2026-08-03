"""
ocr_dialog.py
-------------
OCR dialog.

Runs pytesseract on pages rendered directly by PyMuPDF in a background
thread, bakes the resulting text layer back into the PDF, and re-opens the
result so the document becomes fully searchable and copy-able.

Requirements (bundled in the PDF Studio build):
    pytesseract
    Pillow

System:
    Tesseract-OCR  (auto-detected; it does not need to be added to PATH)
"""
from __future__ import annotations
import os
import sys
import html
import fitz  # PyMuPDF  (https://pymupdf.readthedocs.io/)
import tempfile
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QProgressBar, QCheckBox, QGroupBox, QRadioButton,
    QButtonGroup, QLineEdit, QMessageBox, QSizePolicy, QFrame)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from tesseract_setup import (
    TesseractStatus, choose_tesseract, configure_tesseract,
    open_tesseract_download_page,
)


# ── Availability check ────────────────────────────────────────────────────────

def _check_dependencies() -> tuple[bool, str, TesseractStatus]:
    """Return readiness for the bundled OCR components and Tesseract."""
    missing: list[str] = []
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        missing.append("The bundled Pillow imaging component is missing.")

    status = configure_tesseract()
    if not status.available:
        missing.append(status.detail)

    if missing:
        return False, "OCR is not ready:\n• " + "\n• ".join(missing), status
    return True, "", status


# ── Worker thread ─────────────────────────────────────────────────────────────

class OCRWorker(QThread):
    progress      = pyqtSignal(int, int, str)   # current, total, message
    finished      = pyqtSignal(str, int, int)   # path, embedded words, verified words
    cancelled     = pyqtSignal()
    error         = pyqtSignal(str)

    def __init__(self, pdf_path: str, page_indices: list[int],
                 lang: str, output_path: str, tesseract_exe: str):
        super().__init__()
        self.pdf_path     = pdf_path
        self.page_indices = page_indices   # 0-based
        self.lang         = lang
        self.output_path  = output_path
        self.tesseract_exe = tesseract_exe
        self._cancelled   = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        doc = None
        try:
            import fitz
            import pytesseract
            from PIL import Image

            # Do not rely on PATH inside the worker thread either.
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_exe

            doc = fitz.open(self.pdf_path)
            total = len(self.page_indices)
            recognised_words = 0
            embedded_words = 0

            for step, page_idx in enumerate(self.page_indices):
                if self._cancelled:
                    doc.close()
                    self.cancelled.emit()
                    return

                self.progress.emit(step, total,
                                   f"Processing page {page_idx + 1}…")

                # Render directly with PyMuPDF. This removes the separate
                # Poppler installation previously required by pdf2image.
                page = doc.load_page(page_idx)
                matrix = fitz.Matrix(300 / 72, 300 / 72)
                pix = page.get_pixmap(
                    matrix=matrix,
                    colorspace=fitz.csRGB,
                    alpha=False,
                )
                pil_img = Image.frombytes(
                    "RGB", (pix.width, pix.height), pix.samples)

                # Run Tesseract — get hOCR (bbox-aware XML)
                hocr_bytes = pytesseract.image_to_pdf_or_hocr(
                    pil_img,
                    lang=self.lang,
                    extension="hocr",
                    timeout=300,
                )

                if self._cancelled:
                    doc.close()
                    self.cancelled.emit()
                    return

                # Build an invisible text layer from hOCR and overlay onto page.
                recognised, embedded, _failed = self._overlay_hocr(
                    doc, page_idx, pil_img, hocr_bytes, self.lang)
                recognised_words += recognised
                embedded_words += embedded

            if self._cancelled:
                doc.close()
                self.cancelled.emit()
                return

            if recognised_words == 0:
                raise RuntimeError(
                    "Tesseract completed, but it did not recognise any words on "
                    "the selected pages. Check the OCR language, scan clarity, "
                    "and page orientation."
                )

            if embedded_words == 0:
                raise RuntimeError(
                    "Tesseract recognised text, but PDF Studio could not embed "
                    "the searchable layer. No verified OCR result was produced."
                )

            self.progress.emit(total, total, "Saving and verifying text layer…")
            self._save_document(doc)
            verified_words, verified_chars = self._verify_text_layer(
                self.output_path, self.page_indices)
            if verified_words == 0 or verified_chars == 0:
                raise RuntimeError(
                    "The OCR file was saved, but no searchable text could be "
                    "read back from it. The text layer was not verified."
                )

            # A few malformed boxes may be skipped without invalidating the job,
            # but never silently report success when every insertion failed.
            self.finished.emit(
                self.output_path, embedded_words, verified_words)

        except Exception as exc:
            self.error.emit(f"{type(exc).__name__}: {exc}")
        finally:
            if doc is not None:
                try:
                    if not doc.is_closed:
                        doc.close()
                except Exception:
                    pass

    def _save_document(self, doc: "fitz.Document") -> None:
        """Save normally, or atomically replace the source when requested."""
        source = os.path.normcase(os.path.abspath(self.pdf_path))
        target = os.path.normcase(os.path.abspath(self.output_path))

        if source != target:
            doc.save(self.output_path, garbage=3, deflate=True)
            doc.close()
            return

        output_dir = str(Path(self.output_path).resolve().parent)
        fd, temp_path = tempfile.mkstemp(
            prefix=".pdfstudio_ocr_", suffix=".pdf", dir=output_dir)
        os.close(fd)
        try:
            doc.save(temp_path, garbage=3, deflate=True)
            doc.close()
            os.replace(temp_path, self.output_path)
        except Exception:
            try:
                doc.close()
            except Exception:
                pass
            try:
                os.remove(temp_path)
            except OSError:
                pass
            raise

    @staticmethod
    def _verify_text_layer(output_path: str,
                           page_indices: list[int]) -> tuple[int, int]:
        """Re-open the saved PDF and prove that searchable text exists."""
        import fitz

        verified_words = 0
        verified_chars = 0
        with fitz.open(output_path) as check_doc:
            for page_idx in page_indices:
                if not 0 <= page_idx < check_doc.page_count:
                    continue
                page = check_doc.load_page(page_idx)
                words = page.get_text("words")
                verified_words += len(words)
                verified_chars += sum(len(str(word[4])) for word in words)
        return verified_words, verified_chars

    # ── hOCR → invisible text overlay ────────────────────────────────────

    @staticmethod
    def _overlay_hocr(doc: "fitz.Document", page_idx: int,
                      pil_img, hocr_bytes: bytes, lang: str):
        """Insert hOCR words invisibly and return recognised/embedded/fail counts."""
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
        font_name = _prepare_ocr_font(page, lang)

        def _find_all(node, tag):
            # Walk regardless of namespace
            results = []
            for child in node.iter():
                local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if local == tag:
                    results.append(child)
            return results

        recognised = 0
        embedded = 0
        failures = 0

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
            # itertext() also handles hOCR producers that nest formatting
            # elements inside the word span.
            text = " ".join("".join(span.itertext()).split())
            if not text:
                continue
            recognised += 1

            # Convert to PDF coordinates
            rect = fitz.Rect(x0 * sx, y0 * sy, x1 * sx, y1 * sy)
            if rect.is_empty or rect.is_infinite:
                continue

            # Font size: fill height of bbox
            fs = max(4.0, rect.height * 0.85)

            # Insert invisible text (render mode 3 = invisible)
            try:
                # insert_text expects a baseline point, not the top-left of
                # the word box. Positioning near the lower edge keeps search
                # highlights and drag-copy aligned with the scanned word.
                baseline = fitz.Point(
                    rect.x0,
                    rect.y1 - max(0.6, rect.height * 0.12),
                )
                page.insert_text(
                    baseline,
                    text + " ",
                    fontsize=fs,
                    fontname=font_name,
                    color=(0, 0, 0),
                    render_mode=3,   # invisible
                    overlay=True,
                )
                embedded += 1
            except Exception:
                failures += 1

        return recognised, embedded, failures


# ── Language helpers ──────────────────────────────────────────────────────────

# The bundled Atkinson font covers the Latin languages below. PyMuPDF also
# supplies built-in CJK fonts. Languages needing complex script shaping (for
# example Arabic or Devanagari) are intentionally not offered yet; silently
# producing an empty or corrupt searchable layer would be worse than a smaller,
# honest language list.
_LATIN_LANGS = {
    "eng", "fra", "deu", "spa", "ita", "por", "nld", "pol",
    "ces", "dan", "fin", "swe", "nor", "ron", "hun", "tur",
    "cat", "eus", "glg",
}
_CJK_FONTS = {
    "chi_sim": "china-s",
    "chi_tra": "china-t",
    "jpn": "japan",
    "kor": "korea",
}
_SUPPORTED_LANGS = _LATIN_LANGS | set(_CJK_FONTS)


def _resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


def _prepare_ocr_font(page: "fitz.Page", lang: str) -> str:
    """Return a PDF font name capable of preserving the selected script."""
    if lang in _CJK_FONTS:
        return _CJK_FONTS[lang]

    font_file = _resource_path("fonts/AtkinsonHyperlegible-Regular.ttf")
    if not font_file.is_file():
        raise RuntimeError(f"Bundled OCR font is missing: {font_file}")

    font_name = "PDFStudioOCR"
    page.insert_font(fontname=font_name, fontfile=str(font_file))
    return font_name


_LANG_DISPLAY = {
    "eng":     "English",
    "fra":     "French",
    "deu":     "German",
    "spa":     "Spanish",
    "ita":     "Italian",
    "por":     "Portuguese",
    "nld":     "Dutch",
    "pol":     "Polish",
    "ces":     "Czech",
    "dan":     "Danish",
    "fin":     "Finnish",
    "swe":     "Swedish",
    "nor":     "Norwegian",
    "ron":     "Romanian",
    "hun":     "Hungarian",
    "tur":     "Turkish",
    "cat":     "Catalan",
    "eus":     "Basque",
    "glg":     "Galician",
    "chi_sim": "Chinese (Simplified)",
    "chi_tra": "Chinese (Traditional)",
    "jpn":     "Japanese",
    "kor":     "Korean",
}


def _available_langs() -> list[tuple[str, str]]:
    """Return [(code, display_name)] for installed Tesseract languages."""
    try:
        import pytesseract
        status = configure_tesseract()
        if not status.available:
            return [("eng", "English")]
        codes = pytesseract.get_languages(config="")
        result = []
        for code in sorted(codes):
            if code not in _SUPPORTED_LANGS:
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
        self.replace_original = False
        self.embedded_word_count = 0
        self.verified_word_count = 0
        self._worker: OCRWorker | None = None
        self._tesseract_status = configure_tesseract()

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

        # ── OCR engine ────────────────────────────────────────────────────
        engine_box = QGroupBox("OCR engine")
        engine_layout = QVBoxLayout(engine_box)
        engine_layout.setSpacing(7)

        self._engine_status = QLabel()
        self._engine_status.setWordWrap(True)
        engine_layout.addWidget(self._engine_status)

        engine_buttons = QHBoxLayout()
        self._btn_detect = QPushButton("Detect Again")
        self._btn_locate = QPushButton("Locate Tesseract…")
        self._btn_download = QPushButton("Get Tesseract")
        engine_buttons.addWidget(self._btn_detect)
        engine_buttons.addWidget(self._btn_locate)
        engine_buttons.addWidget(self._btn_download)
        engine_buttons.addStretch()
        engine_layout.addLayout(engine_buttons)
        root.addWidget(engine_box)

        self._btn_detect.clicked.connect(self._refresh_tesseract)
        self._btn_locate.clicked.connect(self._locate_tesseract)
        self._btn_download.clicked.connect(open_tesseract_download_page)
        self._update_engine_status()

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
        self._reload_languages()
        lang_row.addWidget(self._lang_combo)
        lang_row.addStretch()
        root.addLayout(lang_row)

        # ── Output option ─────────────────────────────────────────────────
        self._cb_overwrite = QCheckBox(
            "Replace original after OCR  (unchecked = save as new file)")
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

    def _update_engine_status(self):
        status = self._tesseract_status
        if status.available and status.executable:
            version = html.escape(status.version)
            executable = html.escape(str(status.executable))
            self._engine_status.setText(
                f"✓ {version}<br>"
                f"<span style='color:#666'>{executable}</span>")
            self._engine_status.setStyleSheet("color:#287a36;")
        else:
            self._engine_status.setText(
                "✗ Tesseract is not currently available.<br>"
                "<span style='color:#666'>No Windows PATH editing is required; "
                "PDF Studio can use the installed executable directly.</span>")
            self._engine_status.setStyleSheet("color:#a33;")

    def _reload_languages(self):
        selected = self._lang_combo.currentData()
        self._lang_combo.clear()
        for code, name in _available_langs():
            self._lang_combo.addItem(name, userData=code)
        if selected:
            index = self._lang_combo.findData(selected)
            if index >= 0:
                self._lang_combo.setCurrentIndex(index)

    def _refresh_tesseract(self):
        self._tesseract_status = configure_tesseract()
        self._update_engine_status()
        self._reload_languages()

    def _locate_tesseract(self):
        status = choose_tesseract(self)
        if status.available:
            self._tesseract_status = status
            self._update_engine_status()
            self._reload_languages()

    def _next_output_path(self) -> str:
        """Avoid silently replacing an earlier OCR output file."""
        source = Path(self.pdf_path)
        candidate = source.with_name(f"{source.stem}_ocr{source.suffix}")
        counter = 2
        while candidate.exists():
            candidate = source.with_name(
                f"{source.stem}_ocr_{counter}{source.suffix}")
            counter += 1
        return str(candidate)

    def _replacement_output_path(self) -> str:
        """Create a unique sibling path; the main window replaces safely later."""
        source = Path(self.pdf_path).resolve()
        fd, temp_path = tempfile.mkstemp(
            prefix=f".{source.stem}_pdfstudio_ocr_",
            suffix=source.suffix,
            dir=str(source.parent),
        )
        os.close(fd)
        os.remove(temp_path)  # PyMuPDF requires the destination not to exist.
        return temp_path

    def _run_ocr(self):
        ok, msg, status = _check_dependencies()
        self._tesseract_status = status
        self._update_engine_status()
        if not ok:
            QMessageBox.warning(
                self,
                "OCR Not Ready",
                msg + "\n\nInstall Tesseract or use ‘Locate Tesseract…’, "
                      "then click Detect Again.",
            )
            return

        pages = self._resolve_pages()
        if pages is None:
            return   # validation error already shown

        lang = self._lang_combo.currentData() or "eng"

        self.replace_original = self._cb_overwrite.isChecked()
        if self.replace_original:
            # The main window still has the source PDF open. Save to a sibling
            # temporary file now; it will close the document and atomically
            # replace the original only after OCR has fully succeeded.
            out_path = self._replacement_output_path()
        else:
            out_path = self._next_output_path()

        # UI → running state
        self._btn_run.setEnabled(False)
        self._btn_cancel.setText("Stop")
        self._progress.setMaximum(len(pages))
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._progress_label.setVisible(True)
        self._progress_label.setText("Starting…")

        assert status.executable is not None
        self._worker = OCRWorker(
            self.pdf_path, pages, lang, out_path, str(status.executable))
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, current: int, total: int, msg: str):
        self._progress.setValue(current)
        self._progress_label.setText(msg)

    def _on_finished(self, out_path: str, embedded_words: int,
                     verified_words: int):
        self.output_path = out_path
        self.embedded_word_count = embedded_words
        self.verified_word_count = verified_words
        self._worker = None
        self._progress.setValue(self._progress.maximum())
        self._progress_label.setText(
            f"Done ✓  Searchable text verified ({verified_words:,} words). "
            "Open the OCR result, then press Ctrl+F to test it."
        )
        self._btn_cancel.setText("Close")
        self._btn_cancel.clicked.disconnect()
        self._btn_cancel.clicked.connect(self.accept)
        self._btn_run.setEnabled(False)

    def _on_cancelled(self):
        worker = self._worker
        self._worker = None
        self._remove_replacement_temp(worker)
        super().reject()

    def _on_error(self, msg: str):
        worker = self._worker
        self._worker = None
        self._remove_replacement_temp(worker)
        self._progress.setVisible(False)
        self._progress_label.setVisible(False)
        self._btn_run.setEnabled(True)
        self._btn_cancel.setText("Cancel")
        QMessageBox.critical(self, "OCR Error", msg)

    def _remove_replacement_temp(self, worker: OCRWorker | None):
        if not self.replace_original or worker is None:
            return
        try:
            Path(worker.output_path).unlink(missing_ok=True)
        except OSError:
            pass

    def _on_cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._btn_cancel.setEnabled(False)
            self._progress_label.setVisible(True)
            self._progress_label.setText(
                "Stopping after the current OCR operation…")
            return
        super().reject()

    def reject(self):
        """Do not destroy the dialog while its worker thread is still active."""
        self._on_cancel()

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._on_cancel()
            event.ignore()
            return
        super().closeEvent(event)

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
