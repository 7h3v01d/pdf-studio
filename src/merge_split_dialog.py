"""
merge_split_dialog.py
---------------------
Merge multiple PDFs into one, or split a PDF into parts.
Two tabs: Merge  |  Split
Standalone dialog — no dependency on the main app state.
"""
import os
import fitz

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QListWidget, QListWidgetItem, QFileDialog,
    QLineEdit, QRadioButton, QButtonGroup, QFrame, QSizePolicy,
    QMessageBox, QProgressBar, QSpinBox, QScrollArea, QAbstractItemView)
from PyQt6.QtGui import QIcon, QFont, QColor
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal


# ── Shared style constants (matches app palette) ─────────────────────────────
ACCENT  = "#2563EB"
DARK    = "#1e293b"
MID     = "#64748b"
LIGHT   = "#f8fafc"
SUCCESS = "#16a34a"
DANGER  = "#dc2626"


# ─────────────────────────────────────────────────────────────────────────────
# Background worker threads
# ─────────────────────────────────────────────────────────────────────────────

class MergeWorker(QThread):
    progress = pyqtSignal(int, str)   # (percent, message)
    finished = pyqtSignal(bool, str)  # (success, message)

    def __init__(self, input_paths: list[str], output_path: str):
        super().__init__()
        self.input_paths = input_paths
        self.output_path = output_path

    def run(self):
        try:
            merged = fitz.open()
            total = len(self.input_paths)
            for i, path in enumerate(self.input_paths):
                self.progress.emit(
                    int((i / total) * 90),
                    f"Adding: {os.path.basename(path)}")
                src = fitz.open(path)
                merged.insert_pdf(src)
                src.close()
            self.progress.emit(95, "Saving…")
            merged.save(self.output_path, garbage=3, deflate=True)
            merged.close()
            self.progress.emit(100, "Done")
            self.finished.emit(True, self.output_path)
        except Exception as e:
            self.finished.emit(False, str(e))


class SplitWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str, list)  # (success, message, output_files)

    def __init__(self, input_path: str, output_dir: str,
                 mode: str, value: int, ranges: list[tuple]):
        """
        mode  : 'every_n'   – split every N pages
                'fixed'     – split into N equal parts
                'ranges'    – split by explicit page ranges [(s,e), ...]
        """
        super().__init__()
        self.input_path = input_path
        self.output_dir = output_dir
        self.mode       = mode
        self.value      = value     # N (pages or parts)
        self.ranges     = ranges    # used when mode == 'ranges'

    def run(self):
        out_files = []
        try:
            src   = fitz.open(self.input_path)
            total = src.page_count
            base  = os.path.splitext(os.path.basename(self.input_path))[0]

            if self.mode == "every_n":
                n = max(1, self.value)
                chunks = [(i, min(i + n - 1, total - 1))
                          for i in range(0, total, n)]
            elif self.mode == "fixed":
                n = max(1, self.value)
                size = total // n
                rem  = total % n
                chunks, start = [], 0
                for i in range(n):
                    end = start + size + (1 if i < rem else 0) - 1
                    chunks.append((start, end))
                    start = end + 1
            else:  # ranges
                chunks = self.ranges

            for idx, (s, e) in enumerate(chunks):
                pct = int(((idx) / len(chunks)) * 95)
                self.progress.emit(pct, f"Writing part {idx + 1}/{len(chunks)}…")
                out_name = f"{base}_part{idx + 1:03d}.pdf"
                out_path = os.path.join(self.output_dir, out_name)
                part = fitz.open()
                part.insert_pdf(src, from_page=s, to_page=e)
                part.save(out_path, garbage=3, deflate=True)
                part.close()
                out_files.append(out_path)

            src.close()
            self.progress.emit(100, "Done")
            self.finished.emit(True, f"Created {len(out_files)} file(s)", out_files)
        except Exception as e:
            self.finished.emit(False, str(e), [])


# ─────────────────────────────────────────────────────────────────────────────
# Main dialog
# ─────────────────────────────────────────────────────────────────────────────

class MergeSplitDialog(QDialog):
    # Emitted when a merge or split produces a file the caller may want to open
    open_file_requested = pyqtSignal(str)

    def __init__(self, current_pdf_path: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Merge / Split PDFs")
        self.setModal(True)
        self.setMinimumSize(620, 560)
        self.resize(660, 600)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._current_pdf = current_pdf_path
        self._worker = None
        self._build_ui()

    # =========================================================================
    # Top-level layout
    # =========================================================================

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        root.addWidget(self._make_header())

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._make_merge_tab(), "  ⊕  Merge PDFs  ")
        self.tabs.addTab(self._make_split_tab(), "  ✂  Split PDF  ")
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; background: {LIGHT}; }}
            QTabBar::tab {{
                background: #e2e8f0; color: {MID};
                padding: 9px 22px; font-size: 12px;
                border: none; border-bottom: 2px solid transparent;
            }}
            QTabBar::tab:selected {{
                background: {LIGHT}; color: {ACCENT};
                font-weight: bold; border-bottom: 2px solid {ACCENT};
            }}
            QTabBar::tab:hover:!selected {{ background: #dbeafe; color: {ACCENT}; }}
        """)
        root.addWidget(self.tabs, stretch=1)

        # Progress bar (hidden until job runs)
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

        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            f"color: {MID}; font-size: 11px; padding: 4px 16px;")
        root.addWidget(self.status_label)

        # Footer
        root.addWidget(self._make_footer())

    # =========================================================================
    # Header
    # =========================================================================

    def _make_header(self):
        w = QWidget()
        w.setFixedHeight(64)
        w.setStyleSheet(f"background: {DARK};")
        row = QHBoxLayout(w)
        row.setContentsMargins(24, 0, 24, 0)
        row.setSpacing(14)

        icon = QLabel("📄")
        icon.setStyleSheet("font-size: 28px; background: transparent;")
        row.addWidget(icon)

        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel("Merge / Split PDFs")
        t.setStyleSheet("color: white; font-size: 17px; font-weight: bold;"
                        " background: transparent;")
        s = QLabel("Combine multiple PDFs into one, or split a PDF into parts.")
        s.setStyleSheet(f"color: #94a3b8; font-size: 11px; background: transparent;")
        col.addWidget(t)
        col.addWidget(s)
        row.addLayout(col)
        row.addStretch()
        return w

    # =========================================================================
    # Merge tab
    # =========================================================================

    def _make_merge_tab(self):
        w = QWidget()
        w.setStyleSheet(f"background: {LIGHT};")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # Instructions
        layout.addWidget(_info_label(
            "Add PDFs in the order you want them merged. "
            "Drag rows to reorder, or use the Up/Down buttons."))

        # File list
        self.merge_list = QListWidget()
        self.merge_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.merge_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.merge_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.merge_list.setAlternatingRowColors(True)
        self.merge_list.setMinimumHeight(200)
        self.merge_list.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid #e2e8f0; border-radius: 6px;
                background: white; font-size: 12px;
            }}
            QListWidget::item {{ padding: 6px 10px; }}
            QListWidget::item:selected {{ background: #dbeafe; color: {DARK}; }}
            QListWidget::item:alternate {{ background: #f8fafc; }}
        """)
        layout.addWidget(self.merge_list)

        # List controls row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self._merge_add_btn  = _action_btn("+ Add Files",  ACCENT)
        self._merge_rem_btn  = _action_btn("− Remove",     "#64748b")
        self._merge_up_btn   = _action_btn("↑ Up",         "#64748b")
        self._merge_dn_btn   = _action_btn("↓ Down",       "#64748b")
        self._merge_clr_btn  = _action_btn("✕ Clear All",  DANGER)
        for b in [self._merge_add_btn, self._merge_rem_btn,
                  self._merge_up_btn,  self._merge_dn_btn,
                  self._merge_clr_btn]:
            btn_row.addWidget(b)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # If a PDF is already open, offer to pre-load it
        if self._current_pdf:
            preload = QPushButton(
                f"  ⊕  Add currently open PDF  ({os.path.basename(self._current_pdf)})")
            preload.setStyleSheet(f"""
                QPushButton {{
                    background: {ACCENT_L}; color: {ACCENT};
                    border: 1px dashed {ACCENT}; border-radius: 5px;
                    font-size: 11px; padding: 5px 10px;
                }}
                QPushButton:hover {{ background: #dbeafe; }}
            """)
            preload.clicked.connect(
                lambda: self._merge_add_path(self._current_pdf))
            layout.addWidget(preload)

        # Output path
        layout.addWidget(_divider())
        layout.addWidget(_field_label("Output file:"))
        out_row = QHBoxLayout()
        self.merge_out_edit = QLineEdit()
        self.merge_out_edit.setPlaceholderText("Choose where to save the merged PDF…")
        self.merge_out_edit.setStyleSheet(_input_style())
        browse_btn = _action_btn("Browse…", "#64748b", small=True)
        browse_btn.clicked.connect(self._browse_merge_output)
        out_row.addWidget(self.merge_out_edit)
        out_row.addWidget(browse_btn)
        layout.addLayout(out_row)

        layout.addStretch()

        # Signals
        self._merge_add_btn.clicked.connect(self._merge_add_files)
        self._merge_rem_btn.clicked.connect(self._merge_remove_selected)
        self._merge_up_btn.clicked.connect(self._merge_move_up)
        self._merge_dn_btn.clicked.connect(self._merge_move_down)
        self._merge_clr_btn.clicked.connect(self.merge_list.clear)

        return w

    # ── Merge helpers ─────────────────────────────────────────────────────

    def _merge_add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add PDFs", "", "PDF Files (*.pdf)")
        for p in paths:
            self._merge_add_path(p)

    def _merge_add_path(self, path):
        # Avoid exact duplicates
        for i in range(self.merge_list.count()):
            if self.merge_list.item(i).data(Qt.ItemDataRole.UserRole) == path:
                return
        item = QListWidgetItem(f"  📄  {os.path.basename(path)}")
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setToolTip(path)
        self.merge_list.addItem(item)

    def _merge_remove_selected(self):
        for item in self.merge_list.selectedItems():
            self.merge_list.takeItem(self.merge_list.row(item))

    def _merge_move_up(self):
        row = self.merge_list.currentRow()
        if row > 0:
            item = self.merge_list.takeItem(row)
            self.merge_list.insertItem(row - 1, item)
            self.merge_list.setCurrentRow(row - 1)

    def _merge_move_down(self):
        row = self.merge_list.currentRow()
        if row < self.merge_list.count() - 1:
            item = self.merge_list.takeItem(row)
            self.merge_list.insertItem(row + 1, item)
            self.merge_list.setCurrentRow(row + 1)

    def _browse_merge_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Merged PDF As", "merged.pdf", "PDF Files (*.pdf)")
        if path:
            self.merge_out_edit.setText(path)

    # =========================================================================
    # Split tab
    # =========================================================================

    def _make_split_tab(self):
        w = QWidget()
        w.setStyleSheet(f"background: {LIGHT};")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # Source file
        layout.addWidget(_field_label("Source PDF:"))
        src_row = QHBoxLayout()
        self.split_src_edit = QLineEdit()
        self.split_src_edit.setPlaceholderText("Choose a PDF to split…")
        self.split_src_edit.setStyleSheet(_input_style())
        self.split_src_edit.textChanged.connect(self._update_split_page_info)
        src_browse = _action_btn("Browse…", "#64748b", small=True)
        src_browse.clicked.connect(self._browse_split_source)
        src_row.addWidget(self.split_src_edit)
        src_row.addWidget(src_browse)
        layout.addLayout(src_row)

        if self._current_pdf:
            use_current = QPushButton(
                f"  ✂  Use currently open PDF  ({os.path.basename(self._current_pdf)})")
            use_current.setStyleSheet(f"""
                QPushButton {{
                    background: {ACCENT_L}; color: {ACCENT};
                    border: 1px dashed {ACCENT}; border-radius: 5px;
                    font-size: 11px; padding: 5px 10px;
                }}
                QPushButton:hover {{ background: #dbeafe; }}
            """)
            use_current.clicked.connect(
                lambda: (self.split_src_edit.setText(self._current_pdf)))
            layout.addWidget(use_current)

        # Page count info
        self.split_info_label = QLabel("")
        self.split_info_label.setStyleSheet(
            f"color: {ACCENT}; font-size: 11px; font-weight: bold;")
        layout.addWidget(self.split_info_label)

        layout.addWidget(_divider())

        # Split mode
        layout.addWidget(_field_label("Split method:"))
        self._split_group = QButtonGroup(self)

        self._rb_every_n = QRadioButton("Every  ")
        self._rb_every_n.setChecked(True)
        self._spin_every_n = QSpinBox()
        self._spin_every_n.setRange(1, 9999)
        self._spin_every_n.setValue(1)
        self._spin_every_n.setFixedWidth(64)
        self._spin_every_n.setStyleSheet(_input_style())
        row_n = QHBoxLayout()
        row_n.addWidget(self._rb_every_n)
        row_n.addWidget(self._spin_every_n)
        row_n.addWidget(QLabel("pages"))
        row_n.addStretch()

        self._rb_fixed = QRadioButton("Into  ")
        self._spin_fixed = QSpinBox()
        self._spin_fixed.setRange(2, 9999)
        self._spin_fixed.setValue(2)
        self._spin_fixed.setFixedWidth(64)
        self._spin_fixed.setStyleSheet(_input_style())
        row_f = QHBoxLayout()
        row_f.addWidget(self._rb_fixed)
        row_f.addWidget(self._spin_fixed)
        row_f.addWidget(QLabel("equal parts"))
        row_f.addStretch()

        self._rb_ranges = QRadioButton("Custom page ranges:")
        self._ranges_edit = QLineEdit()
        self._ranges_edit.setPlaceholderText(
            "e.g.  1-3, 4-7, 8-10  (1-based, comma separated)")
        self._ranges_edit.setStyleSheet(_input_style())
        self._ranges_edit.setEnabled(False)

        for rb in [self._rb_every_n, self._rb_fixed, self._rb_ranges]:
            self._split_group.addButton(rb)

        self._rb_every_n.toggled.connect(self._sync_split_controls)
        self._rb_fixed.toggled.connect(self._sync_split_controls)
        self._rb_ranges.toggled.connect(self._sync_split_controls)

        mode_widget = QWidget()
        mode_widget.setStyleSheet(
            f"background: white; border: 1px solid #e2e8f0; border-radius: 6px;")
        ml = QVBoxLayout(mode_widget)
        ml.setContentsMargins(14, 12, 14, 12)
        ml.setSpacing(10)
        ml.addLayout(row_n)
        ml.addLayout(row_f)
        ml.addWidget(self._rb_ranges)
        ml.addWidget(self._ranges_edit)
        layout.addWidget(mode_widget)

        layout.addWidget(_divider())

        # Output directory
        layout.addWidget(_field_label("Output folder:"))
        out_row = QHBoxLayout()
        self.split_out_edit = QLineEdit()
        self.split_out_edit.setPlaceholderText(
            "Folder where split files will be saved…")
        self.split_out_edit.setStyleSheet(_input_style())
        out_browse = _action_btn("Browse…", "#64748b", small=True)
        out_browse.clicked.connect(self._browse_split_output_dir)
        out_row.addWidget(self.split_out_edit)
        out_row.addWidget(out_browse)
        layout.addLayout(out_row)

        layout.addStretch()
        return w

    # ── Split helpers ─────────────────────────────────────────────────────

    def _browse_split_source(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose PDF to Split", "", "PDF Files (*.pdf)")
        if path:
            self.split_src_edit.setText(path)

    def _browse_split_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Choose Output Folder")
        if path:
            self.split_out_edit.setText(path)

    def _update_split_page_info(self, path):
        if path and os.path.exists(path):
            try:
                doc = fitz.open(path)
                n = doc.page_count
                doc.close()
                self.split_info_label.setText(f"  ℹ  {n} pages")
                self._spin_every_n.setMaximum(n)
                self._spin_fixed.setMaximum(n)
            except Exception:
                self.split_info_label.setText("  ⚠  Could not read file")
        else:
            self.split_info_label.setText("")

    def _sync_split_controls(self):
        self._spin_every_n.setEnabled(self._rb_every_n.isChecked())
        self._spin_fixed.setEnabled(self._rb_fixed.isChecked())
        self._ranges_edit.setEnabled(self._rb_ranges.isChecked())

    def _parse_ranges(self, text: str, total: int) -> list[tuple] | None:
        """Parse '1-3, 4-7, 10' into 0-based (start, end) tuples."""
        chunks = []
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
            else:
                try:
                    s = e = int(part) - 1
                except ValueError:
                    return None
            if s < 0 or e >= total or s > e:
                return None
            chunks.append((s, e))
        return chunks if chunks else None

    # =========================================================================
    # Footer
    # =========================================================================

    def _make_footer(self):
        w = QWidget()
        w.setFixedHeight(54)
        w.setStyleSheet("background: #f1f5f9; border-top: 1px solid #e2e8f0;")
        row = QHBoxLayout(w)
        row.setContentsMargins(20, 0, 20, 0)
        row.setSpacing(8)

        self.run_btn = QPushButton("▶  Run")
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

        row.addStretch()
        row.addWidget(self.run_btn)
        row.addWidget(close_btn)
        return w

    # =========================================================================
    # Run
    # =========================================================================

    def _run(self):
        if self.tabs.currentIndex() == 0:
            self._run_merge()
        else:
            self._run_split()

    def _run_merge(self):
        # Validate inputs
        paths = [self.merge_list.item(i).data(Qt.ItemDataRole.UserRole)
                 for i in range(self.merge_list.count())]
        if len(paths) < 2:
            self._warn("Add at least 2 PDF files to merge.")
            return
        out = self.merge_out_edit.text().strip()
        if not out:
            self._warn("Choose an output file path.")
            return
        if not out.lower().endswith(".pdf"):
            out += ".pdf"

        self._start_worker()
        self._worker = MergeWorker(paths, out)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_merge_done)
        self._worker.start()

    def _run_split(self):
        src = self.split_src_edit.text().strip()
        if not src or not os.path.exists(src):
            self._warn("Choose a valid source PDF.")
            return
        out_dir = self.split_out_edit.text().strip()
        if not out_dir or not os.path.isdir(out_dir):
            self._warn("Choose a valid output folder.")
            return

        # Determine mode and parse
        try:
            doc   = fitz.open(src)
            total = doc.page_count
            doc.close()
        except Exception as e:
            self._warn(f"Cannot open source PDF: {e}")
            return

        if self._rb_every_n.isChecked():
            mode, value, ranges = "every_n", self._spin_every_n.value(), []
        elif self._rb_fixed.isChecked():
            mode, value, ranges = "fixed", self._spin_fixed.value(), []
        else:
            ranges = self._parse_ranges(self._ranges_edit.text(), total)
            if ranges is None:
                self._warn(
                    "Invalid page ranges.\n"
                    "Use comma-separated ranges like: 1-3, 4-7, 8-10")
                return
            mode, value = "ranges", 0

        self._start_worker()
        self._worker = SplitWorker(src, out_dir, mode, value, ranges)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_split_done)
        self._worker.start()

    # =========================================================================
    # Worker callbacks
    # =========================================================================

    def _start_worker(self):
        self.run_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.status_label.setText("Working…")

    def _on_progress(self, pct: int, msg: str):
        self.progress_bar.setValue(pct)
        self.status_label.setText(msg)

    def _on_merge_done(self, ok: bool, msg: str):
        self._finish_worker()
        if ok:
            self.status_label.setText(f"✔  Merged successfully → {os.path.basename(msg)}")
            self.status_label.setStyleSheet(
                f"color: {SUCCESS}; font-size: 11px; padding: 4px 16px; font-weight: bold;")
            reply = QMessageBox.question(
                self, "Merge Complete",
                f"PDF merged successfully.\n\n{msg}\n\nOpen it now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.open_file_requested.emit(msg)
                self.accept()
        else:
            self._show_error(f"Merge failed: {msg}")

    def _on_split_done(self, ok: bool, msg: str, files: list):
        self._finish_worker()
        if ok:
            self.status_label.setText(f"✔  {msg}")
            self.status_label.setStyleSheet(
                f"color: {SUCCESS}; font-size: 11px; padding: 4px 16px; font-weight: bold;")
            summary = "\n".join(f"  • {os.path.basename(f)}" for f in files[:10])
            if len(files) > 10:
                summary += f"\n  … and {len(files) - 10} more"
            reply = QMessageBox.question(
                self, "Split Complete",
                f"Split into {len(files)} file(s):\n\n{summary}\n\nOpen first part?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes and files:
                self.open_file_requested.emit(files[0])
                self.accept()
        else:
            self._show_error(f"Split failed: {msg}")

    def _finish_worker(self):
        self.run_btn.setEnabled(True)
        self.progress_bar.hide()

    # =========================================================================
    # Helpers
    # =========================================================================

    def _warn(self, msg: str):
        QMessageBox.warning(self, "PDF Merge / Split", msg)

    def _show_error(self, msg: str):
        self.status_label.setText(f"✖  {msg}")
        self.status_label.setStyleSheet(
            f"color: {DANGER}; font-size: 11px; padding: 4px 16px; font-weight: bold;")
        QMessageBox.critical(self, "Error", msg)


# ── Module-level widget helpers ───────────────────────────────────────────────

ACCENT_L = "#EFF6FF"


def _action_btn(label: str, color: str, small: bool = False) -> QPushButton:
    btn = QPushButton(label)
    h = 26 if small else 30
    btn.setFixedHeight(h)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: white; color: {color};
            border: 1px solid {color}; border-radius: 4px;
            font-size: 12px; padding: 2px 10px;
        }}
        QPushButton:hover   {{ background: #f0f4ff; }}
        QPushButton:pressed {{ background: #dbeafe; }}
    """)
    return btn


def _info_label(text: str) -> QLabel:
    lbl = QLabel(f"ℹ  {text}")
    lbl.setWordWrap(True)
    lbl.setStyleSheet(
        f"color: {MID}; font-size: 11px; background: {ACCENT_L};"
        f" border: 1px solid #bfdbfe; border-radius: 5px; padding: 7px 12px;")
    return lbl


def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {DARK}; font-size: 12px; font-weight: bold;")
    return lbl


def _divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet("background: #e2e8f0; border: none;")
    return f


def _input_style() -> str:
    return (
        "QLineEdit, QSpinBox {"
        "  border: 1px solid #e2e8f0; border-radius: 4px;"
        "  padding: 4px 8px; background: white; font-size: 12px;"
        "}"
        "QLineEdit:focus, QSpinBox:focus { border-color: #2563EB; }"
    )
