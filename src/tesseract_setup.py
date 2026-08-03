"""
tesseract_setup.py
------------------
Reliable Tesseract discovery and configuration for PDF Studio.

PDF Studio does not require Tesseract to be added to the Windows PATH.  This
module locates tesseract.exe, validates it, configures pytesseract directly,
and remembers a manually selected location using the application's QSettings.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Iterable

from PyQt6.QtCore import QSettings, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget


_SETTINGS_ORG = "LeonPriest"
_SETTINGS_APP = "PDFStudio"
_SETTINGS_KEY = "ocr/tesseract_executable"
_DOWNLOAD_URL = "https://github.com/UB-Mannheim/tesseract/wiki"


@dataclass(frozen=True)
class TesseractStatus:
    available: bool
    executable: Path | None = None
    version: str = ""
    detail: str = ""


def _settings() -> QSettings:
    return QSettings(_SETTINGS_ORG, _SETTINGS_APP)


def _normalise(path: str | os.PathLike[str]) -> str:
    return os.path.normcase(os.path.abspath(os.path.expandvars(str(path))))


def _no_window_flags() -> int:
    if sys.platform == "win32":
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return 0


def validate_tesseract(executable: str | os.PathLike[str]) -> TesseractStatus:
    """Validate a specific Tesseract executable without relying on PATH."""
    path = Path(os.path.expandvars(str(executable))).expanduser()
    if not path.is_file():
        return TesseractStatus(False, detail=f"File not found: {path}")

    try:
        result = subprocess.run(
            [str(path), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            creationflags=_no_window_flags(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return TesseractStatus(
            False,
            executable=path,
            detail=f"Could not start Tesseract: {exc}",
        )

    output = (result.stdout or result.stderr or "").strip()
    first_line = output.splitlines()[0] if output else ""
    if result.returncode != 0:
        return TesseractStatus(
            False,
            executable=path,
            detail=first_line or f"Tesseract exited with code {result.returncode}.",
        )

    return TesseractStatus(
        True,
        executable=path.resolve(),
        version=first_line or "Tesseract detected",
        detail="Ready",
    )


def _registry_candidates() -> Iterable[Path]:
    """Yield likely install locations recorded by Windows installers."""
    if sys.platform != "win32":
        return []

    try:
        import winreg
    except ImportError:
        return []

    candidates: list[Path] = []
    keys = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Tesseract-OCR"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Tesseract-OCR"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Tesseract-OCR"),
    )
    for root, key_name in keys:
        try:
            with winreg.OpenKey(root, key_name) as key:
                for value_name in ("InstallDir", "Path", ""):
                    try:
                        value, _ = winreg.QueryValueEx(key, value_name)
                    except OSError:
                        continue
                    if value:
                        candidates.append(Path(os.path.expandvars(str(value))))
        except OSError:
            continue
    return candidates


def _candidate_executables() -> Iterable[Path]:
    """Yield candidates in priority order, with no recursive disk scanning."""
    saved = _settings().value(_SETTINGS_KEY, "", type=str).strip()
    if saved:
        yield Path(saved)

    discovered = shutil.which("tesseract.exe") or shutil.which("tesseract")
    if discovered:
        yield Path(discovered)

    # Supports a future portable distribution containing a Tesseract-OCR folder
    # beside PDF Studio.exe, without changing any system settings.
    app_dir = Path(sys.executable).resolve().parent
    source_dir = Path(__file__).resolve().parent
    for base in (app_dir, source_dir, source_dir.parent):
        yield base / "Tesseract-OCR" / "tesseract.exe"
        yield base / "tesseract.exe"

    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local_app_data = os.environ.get("LOCALAPPDATA", "")

    yield Path(program_files) / "Tesseract-OCR" / "tesseract.exe"
    yield Path(program_files_x86) / "Tesseract-OCR" / "tesseract.exe"
    if local_app_data:
        yield Path(local_app_data) / "Programs" / "Tesseract-OCR" / "tesseract.exe"
        yield Path(local_app_data) / "Tesseract-OCR" / "tesseract.exe"

    for candidate in _registry_candidates():
        if candidate.name.lower() == "tesseract.exe":
            yield candidate
        else:
            yield candidate / "tesseract.exe"


def find_tesseract() -> TesseractStatus:
    """Locate and validate Tesseract, preferring the user's saved selection."""
    seen: set[str] = set()
    for candidate in _candidate_executables():
        key = _normalise(candidate)
        if key in seen:
            continue
        seen.add(key)

        status = validate_tesseract(candidate)
        if status.available:
            _settings().setValue(_SETTINGS_KEY, str(status.executable))
            return status

    return TesseractStatus(
        False,
        detail=(
            "Tesseract OCR was not found. Install it normally, then use "
            "‘Locate Tesseract…’ if PDF Studio does not detect it automatically."
        ),
    )


def configure_tesseract(
    executable: str | os.PathLike[str] | None = None,
) -> TesseractStatus:
    """Configure pytesseract to use an explicit executable path."""
    try:
        import pytesseract
    except ImportError:
        return TesseractStatus(
            False,
            detail="The bundled Python OCR component (pytesseract) is missing.",
        )

    status = validate_tesseract(executable) if executable else find_tesseract()
    if not status.available or status.executable is None:
        return status

    pytesseract.pytesseract.tesseract_cmd = str(status.executable)
    _settings().setValue(_SETTINGS_KEY, str(status.executable))
    return status


def choose_tesseract(parent: QWidget | None = None) -> TesseractStatus:
    """Let the user locate tesseract.exe and validate the selection."""
    initial = _settings().value(_SETTINGS_KEY, "", type=str).strip()
    initial_dir = str(Path(initial).parent) if initial else r"C:\Program Files\Tesseract-OCR"

    filename, _ = QFileDialog.getOpenFileName(
        parent,
        "Locate Tesseract OCR",
        initial_dir,
        "Tesseract executable (tesseract.exe);;Applications (*.exe);;All files (*)",
    )
    if not filename:
        return TesseractStatus(False, detail="No file selected.")

    status = configure_tesseract(filename)
    if not status.available:
        QMessageBox.warning(
            parent,
            "Invalid Tesseract Location",
            "PDF Studio could not use the selected file.\n\n" + status.detail,
        )
    return status


def open_tesseract_download_page() -> bool:
    """Open the maintained Windows Tesseract installer page."""
    return QDesktopServices.openUrl(QUrl(_DOWNLOAD_URL))
