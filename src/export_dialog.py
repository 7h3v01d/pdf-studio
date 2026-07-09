"""
export_dialog.py
----------------
Export dialog.

Supports:
  • Export → Microsoft Word (.docx)   via pdf2docx
  • Export → Microsoft Excel (.xlsx)  via tabula-py + openpyxl

Both run in a background QThread with a progress bar.
After export the user is offered "Open file?" via the OS default handler.

Requirements (pip):
    pdf2docx
    tabula-py
    openpyxl
    pandas

System:
    Java (required by tabula-py for Excel table extraction)
"""
from __future__ import annotations
import os
import subprocess
import sys

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QGroupBox, QRadioButton, QButtonGroup,
    QCheckBox, QFileDialog, QMessageBox, QFrame, QLineEdit,
    QSizePolicy)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont


# ── Dependency checks ────────────────────────────────────────────────────────

def _check_docx_deps() -> tuple[bool, str]:
    missing = []
    try:
        import pdf2docx  # noqa: F401
    except ImportError:
        missing.append("pdf2docx  (pip install pdf2docx)")
    if missing:
        return False, "Missing:\n• " + "\n• ".join(missing)
    return True, ""


def _check_xlsx_deps() -> tuple[bool, str]:
    missing = []
    for pkg, install in [("tabula", "tabula-py"),
                          ("openpyxl", "openpyxl"),
                          ("pandas", "pandas")]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(f"{pkg}  (pip install {install})")
    if missing:
        return False, "Missing:\n• " + "\n• ".join(missing)
    return True, ""


# ── Workers ───────────────────────────────────────────────────────────────────

class DocxWorker(QThread):
    progress = pyqtSignal(int, str)   # 0-100, message
    finished = pyqtSignal(str)        # output path
    error    = pyqtSignal(str)

    def __init__(self, pdf_path: str, out_path: str,
                 start_page: int, end_page: int):
        super().__init__()
        self.pdf_path   = pdf_path
        self.out_path   = out_path
        self.start_page = start_page   # 0-based
        self.end_page   = end_page     # 0-based inclusive

    def run(self):
        try:
            from pdf2docx import Converter
            self.progress.emit(5, "Initialising converter…")
            cv = Converter(self.pdf_path)
            self.progress.emit(15, "Converting pages…")
            cv.convert(
                self.out_path,
                start=self.start_page,
                end=self.end_page + 1,   # pdf2docx end is exclusive
            )
            cv.close()
            self.progress.emit(100, "Done ✓")
            self.finished.emit(self.out_path)
        except Exception as exc:
            self.error.emit(str(exc))


class XlsxWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, pdf_path: str, out_path: str,
                 all_pages: bool, page_idx: int):
        super().__init__()
        self.pdf_path  = pdf_path
        self.out_path  = out_path
        self.all_pages = all_pages
        self.page_idx  = page_idx   # 0-based, used when all_pages=False

    def run(self):
        try:
            import tabula
            import pandas as pd
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

            self.progress.emit(5, "Scanning for tables…")

            pages = "all" if self.all_pages else (self.page_idx + 1)
            dfs   = tabula.read_pdf(
                self.pdf_path,
                pages=pages,
                multiple_tables=True,
                silent=True,
            )

            if not dfs:
                self.error.emit(
                    "No tables detected in the selected page(s).\n\n"
                    "tabula-py extracts structured tables only. "
                    "If the PDF contains text but no grid/table layout, "
                    "use the Word export instead.")
                return

            self.progress.emit(40, f"Found {len(dfs)} table(s). Writing…")

            wb = openpyxl.Workbook()
            wb.remove(wb.active)   # remove default empty sheet

            header_fill   = PatternFill("solid", fgColor="2563EB")
            header_font   = Font(color="FFFFFF", bold=True, size=10)
            header_align  = Alignment(horizontal="center", vertical="center",
                                       wrap_text=True)
            thin_side     = Side(style="thin", color="CCCCCC")
            cell_border   = Border(left=thin_side, right=thin_side,
                                   top=thin_side,  bottom=thin_side)
            alt_fill      = PatternFill("solid", fgColor="EFF6FF")

            for t_idx, df in enumerate(dfs):
                df = df.dropna(how="all").fillna("")
                sheet_name = f"Table {t_idx + 1}"
                ws = wb.create_sheet(title=sheet_name)

                # Header row
                for col_idx, col_name in enumerate(df.columns, start=1):
                    cell = ws.cell(row=1, column=col_idx, value=str(col_name))
                    cell.font    = header_font
                    cell.fill    = header_fill
                    cell.alignment = header_align
                    cell.border  = cell_border
                ws.row_dimensions[1].height = 22

                # Data rows
                for row_idx, row in enumerate(df.itertuples(index=False), start=2):
                    for col_idx, val in enumerate(row, start=1):
                        cell = ws.cell(row=row_idx, column=col_idx,
                                       value=str(val) if val != "" else "")
                        cell.border = cell_border
                        if row_idx % 2 == 0:
                            cell.fill = alt_fill

                # Auto column width
                for col in ws.columns:
                    max_len = 0
                    col_letter = col[0].column_letter
                    for cell in col:
                        try:
                            max_len = max(max_len, len(str(cell.value or "")))
                        except Exception:
                            pass
                    ws.column_dimensions[col_letter].width = min(max_len + 4, 50)

                ws.freeze_panes = "A2"

                pct = 40 + int(55 * (t_idx + 1) / len(dfs))
                self.progress.emit(pct, f"Written {sheet_name}…")

            wb.save(self.out_path)
            self.progress.emit(100, "Done ✓")
            self.finished.emit(self.out_path)

        except Exception as exc:
            self.error.emit(str(exc))


# ── Dialog ────────────────────────────────────────────────────────────────────

class ExportDialog(QDialog):
    """
    Export PDF to Word or Excel.

    Usage:
        dlg = ExportDialog(pdf_path, total_pages, current_page, parent=self)
        dlg.exec()
    """

    def __init__(self, pdf_path: str, total_pages: int,
                 current_page: int, parent=None):
        super().__init__(parent)
        self.pdf_path     = pdf_path
        self.total_pages  = total_pages
        self.current_page = current_page
        self._worker: QThread | None = None

        self.setWindowTitle("Export PDF As…")
        self.setMinimumWidth(460)
        self.setModal(True)
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        # Header
        title = QLabel("📤  Export PDF As…")
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        title.setFont(f)
        root.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #ddd;")
        root.addWidget(sep)

        # ── Format selection ─────────────────────────────────────────────
        fmt_box = QGroupBox("Export format")
        fmt_layout = QVBoxLayout(fmt_box)
        fmt_layout.setSpacing(6)
        self._fmt_group = QButtonGroup(self)
        self._rb_docx = QRadioButton(
            "📝  Microsoft Word (.docx)\n"
            "    Preserves layout, text, images and columns.")
        self._rb_xlsx = QRadioButton(
            "📊  Microsoft Excel (.xlsx)\n"
            "    Extracts tables from the PDF into spreadsheet sheets.")
        self._rb_docx.setChecked(True)
        self._fmt_group.addButton(self._rb_docx, 0)
        self._fmt_group.addButton(self._rb_xlsx, 1)
        fmt_layout.addWidget(self._rb_docx)
        fmt_layout.addWidget(self._rb_xlsx)
        root.addWidget(fmt_box)

        # ── Page scope (Word only) ────────────────────────────────────────
        self._scope_box = QGroupBox("Pages  (Word export only)")
        scope_layout = QVBoxLayout(self._scope_box)
        scope_layout.setSpacing(4)
        self._scope_group = QButtonGroup(self)
        self._rb_all_pages  = QRadioButton(
            f"All pages  ({self.total_pages} pages)")
        self._rb_cur_page   = QRadioButton(
            f"Current page  (page {self.current_page + 1})")
        self._rb_pg_range   = QRadioButton("Page range:")
        self._rb_all_pages.setChecked(True)
        self._scope_group.addButton(self._rb_all_pages,  0)
        self._scope_group.addButton(self._rb_cur_page,   1)
        self._scope_group.addButton(self._rb_pg_range,   2)
        rr = QHBoxLayout()
        rr.setContentsMargins(20, 0, 0, 0)
        self._page_range_input = QLineEdit()
        self._page_range_input.setPlaceholderText("e.g.  1-5, 8, 12-15")
        self._page_range_input.setEnabled(False)
        self._page_range_input.setFixedWidth(200)
        rr.addWidget(self._page_range_input)
        rr.addStretch()
        scope_layout.addWidget(self._rb_all_pages)
        scope_layout.addWidget(self._rb_cur_page)
        scope_layout.addWidget(self._rb_pg_range)
        scope_layout.addLayout(rr)
        root.addWidget(self._scope_box)

        self._rb_pg_range.toggled.connect(self._page_range_input.setEnabled)
        self._rb_xlsx.toggled.connect(
            lambda checked: self._scope_box.setEnabled(not checked))

        # ── Options ───────────────────────────────────────────────────────
        self._cb_open = QCheckBox("Open file after export")
        self._cb_open.setChecked(True)
        root.addWidget(self._cb_open)

        # ── Progress ──────────────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setRange(0, 100)
        root.addWidget(self._progress)

        self._progress_label = QLabel("")
        self._progress_label.setVisible(False)
        self._progress_label.setStyleSheet("color:#555; font-size:11px;")
        root.addWidget(self._progress_label)

        # ── Buttons ───────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._btn_export = QPushButton("Export")
        self._btn_export.setDefault(True)
        self._btn_export.setStyleSheet(
            "background:#3a7bd5; color:white; font-weight:bold;"
            "border-radius:4px; padding:6px 18px;")
        self._btn_close  = QPushButton("Cancel")
        btn_row.addStretch()
        btn_row.addWidget(self._btn_close)
        btn_row.addWidget(self._btn_export)
        root.addLayout(btn_row)

        self._btn_export.clicked.connect(self._do_export)
        self._btn_close.clicked.connect(self._on_close)

    # ── Slots ─────────────────────────────────────────────────────────────

    def _do_export(self):
        is_xlsx = self._fmt_group.checkedId() == 1

        if is_xlsx:
            ok, msg = _check_xlsx_deps()
        else:
            ok, msg = _check_docx_deps()
        if not ok:
            QMessageBox.critical(self, "Missing Dependencies", msg)
            return

        # Choose output path
        ext  = ".xlsx" if is_xlsx else ".docx"
        desc = "Excel Files (*.xlsx)" if is_xlsx else "Word Documents (*.docx)"
        base = os.path.splitext(self.pdf_path)[0]
        default = base + ext
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Save Export As", default, desc)
        if not out_path:
            return

        # UI → running state
        self._btn_export.setEnabled(False)
        self._btn_close.setText("Stop")
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._progress_label.setVisible(True)
        self._progress_label.setText("Starting…")

        if is_xlsx:
            all_pages = (self._scope_group.checkedId() == 0)
            self._worker = XlsxWorker(
                self.pdf_path, out_path,
                all_pages=True,      # tabula handles all pages for xlsx
                page_idx=self.current_page)
        else:
            start, end = self._resolve_page_range()
            if start is None:
                self._btn_export.setEnabled(True)
                self._btn_close.setText("Cancel")
                self._progress.setVisible(False)
                self._progress_label.setVisible(False)
                return
            self._worker = DocxWorker(
                self.pdf_path, out_path, start, end)

        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(lambda p: self._on_finished(p))
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, pct: int, msg: str):
        self._progress.setValue(pct)
        self._progress_label.setText(msg)

    def _on_finished(self, out_path: str):
        self._progress.setValue(100)
        self._progress_label.setText("Export complete ✓")
        self._btn_close.setText("Close")
        self._btn_close.clicked.disconnect()
        self._btn_close.clicked.connect(self.accept)
        self._btn_export.setEnabled(False)

        if self._cb_open.isChecked():
            self._open_file(out_path)

    def _on_error(self, msg: str):
        self._progress.setVisible(False)
        self._progress_label.setVisible(False)
        self._btn_export.setEnabled(True)
        self._btn_close.setText("Cancel")
        QMessageBox.critical(self, "Export Error", msg)

    def _on_close(self):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(2000)
        self.reject()

    # ── Helpers ───────────────────────────────────────────────────────────

    def _resolve_page_range(self) -> tuple[int | None, int | None]:
        """Return (start, end) 0-based inclusive from scope selection."""
        btn_id = self._scope_group.checkedId()
        if btn_id == 0:
            return 0, self.total_pages - 1
        if btn_id == 1:
            return self.current_page, self.current_page
        raw = self._page_range_input.text().strip()
        if not raw:
            QMessageBox.warning(self, "Page Range",
                                "Please enter a page range.")
            return None, None
        try:
            pages = set()
            for part in raw.split(","):
                part = part.strip()
                if "-" in part:
                    a, b = part.split("-", 1)
                    pages.update(range(int(a) - 1, int(b)))
                else:
                    pages.add(int(part) - 1)
            pages = {p for p in pages if 0 <= p < self.total_pages}
            if not pages:
                raise ValueError("empty")
            return min(pages), max(pages)
        except Exception:
            QMessageBox.warning(self, "Page Range",
                                f"Could not parse range: '{raw}'")
            return None, None

    @staticmethod
    def _open_file(path: str):
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.run(["open", path], check=False)
            else:
                subprocess.run(["xdg-open", path], check=False)
        except Exception:
            pass
