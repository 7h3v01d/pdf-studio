"""Support diagnostics and bundled notice viewers."""
from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, PYQT_VERSION_STR, QT_VERSION_STR
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from app_metadata import APP_NAME, APP_VERSION
from runtime_support import (
    collect_diagnostics,
    config_directory,
    display_path,
    format_diagnostics_report,
    log_directory,
    resource_path,
)


def _tesseract_checks() -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        from tesseract_setup import find_tesseract

        status = find_tesseract()
        result["tesseract_status"] = "ready" if status.available else "not detected"
        result["tesseract_version"] = status.version or status.detail
        result["tesseract_executable"] = display_path(status.executable) if status.executable else ""
    except Exception as exc:
        result["tesseract_status"] = f"check failed ({type(exc).__name__})"
    return result


class DiagnosticsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} Diagnostics")
        self.setMinimumSize(720, 520)
        self.resize(820, 620)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        root = QVBoxLayout(self)
        intro = QLabel(
            "Copy this report when asking for support. It contains runtime and "
            "dependency information, but no PDF text or document contents."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        root.addWidget(self.report, 1)

        buttons = QHBoxLayout()
        refresh = QPushButton("Refresh")
        copy = QPushButton("Copy Diagnostics")
        save = QPushButton("Save Report…")
        logs = QPushButton("Open Log Folder")
        config = QPushButton("Open Config Folder")
        close = QPushButton("Close")
        for button in (refresh, copy, save, logs, config):
            buttons.addWidget(button)
        buttons.addStretch()
        buttons.addWidget(close)
        root.addLayout(buttons)

        refresh.clicked.connect(self.refresh)
        copy.clicked.connect(self.copy_report)
        save.clicked.connect(self.save_report)
        logs.clicked.connect(lambda: self._open_folder(log_directory()))
        config.clicked.connect(lambda: self._open_folder(config_directory()))
        close.clicked.connect(self.accept)
        self.refresh()

    def refresh(self) -> None:
        extra = {
            "qt_version": QT_VERSION_STR,
            "pyqt_version": PYQT_VERSION_STR,
            **_tesseract_checks(),
        }
        info = collect_diagnostics(APP_NAME, APP_VERSION, extra=extra)
        self.report.setPlainText(format_diagnostics_report(info))

    def copy_report(self) -> None:
        QApplication.clipboard().setText(self.report.toPlainText())
        QMessageBox.information(self, "Diagnostics Copied", "The diagnostics report was copied to the clipboard.")

    def save_report(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Diagnostics",
            f"PDF_Studio_{APP_VERSION}_diagnostics.txt",
            "Text files (*.txt);;All files (*)",
        )
        if not filename:
            return
        try:
            Path(filename).write_text(self.report.toPlainText(), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Could Not Save", str(exc))

    def _open_folder(self, path: Path) -> None:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "Could Not Open Folder", str(exc))
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.warning(self, "Could Not Open Folder", str(path))


class BundledTextDialog(QDialog):
    """Read-only viewer for a bundled Markdown/text resource."""

    def __init__(self, title: str, resource_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(700, 520)
        self.resize(820, 650)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        root = QVBoxLayout(self)
        viewer = QPlainTextEdit()
        viewer.setReadOnly(True)
        viewer.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        path = resource_path(resource_name)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            text = f"Could not load bundled resource:\n{path}\n\n{exc}"
        viewer.setPlainText(text)
        root.addWidget(viewer, 1)

        row = QHBoxLayout()
        open_external = QPushButton("Open Externally")
        close = QPushButton("Close")
        row.addWidget(open_external)
        row.addStretch()
        row.addWidget(close)
        root.addLayout(row)
        open_external.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        )
        close.clicked.connect(self.accept)
