"""Runtime logging, paths, diagnostics and build-manifest helpers.

This module deliberately has no Qt dependency so it can be exercised by the
release tooling and test suite. GUI-specific enrichment is supplied by the
Diagnostics dialog.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.metadata as metadata
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import platform
import sys
import traceback
from typing import Any, Mapping

_LOG_NAME = "pdf_studio.log"
_MAX_LOG_BYTES = 2 * 1024 * 1024
_BACKUP_COUNT = 4
_DEPENDENCIES = (
    "PyMuPDF",
    "PyQt6",
    "PyQt6-Qt6",
    "PyQt6-sip",
    "Pillow",
    "pytesseract",
    "PyInstaller",
    "pyinstaller-hooks-contrib",
    "pytest",
)


def application_data_dir(app_folder: str = "PDFStudio") -> Path:
    """Return a writable per-user application-data directory."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
        return root / app_folder
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / app_folder
    base = os.environ.get("XDG_STATE_HOME")
    return (Path(base) if base else Path.home() / ".local" / "state") / app_folder


def log_directory() -> Path:
    return application_data_dir() / "logs"


def log_file_path() -> Path:
    return log_directory() / _LOG_NAME


def config_directory() -> Path:
    return application_data_dir() / "config"


def resource_path(relative_path: str | os.PathLike[str]) -> Path:
    """Resolve source-tree and PyInstaller bundled resources consistently."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root) / Path(relative_path)
    return Path(__file__).resolve().parent.parent / Path(relative_path)


def configure_logging(app_version: str, *, level: int = logging.INFO) -> Path:
    """Install bounded file logging and return the active log path.

    Repeated calls are idempotent for the same process. The handler is tagged
    so importing a module twice cannot duplicate every log message.
    """
    directory = log_directory()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / _LOG_NAME

    root = logging.getLogger()
    root.setLevel(level)
    for handler in root.handlers:
        if getattr(handler, "_pdf_studio_handler", False):
            return path

    handler = RotatingFileHandler(
        path,
        maxBytes=_MAX_LOG_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
        delay=True,
    )
    handler._pdf_studio_handler = True  # type: ignore[attr-defined]
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)s | %(threadName)s | %(name)s | %(message)s"
    ))
    root.addHandler(handler)
    logging.captureWarnings(True)
    logging.getLogger(__name__).info(
        "PDF Studio startup | version=%s | frozen=%s | executable=%s",
        app_version,
        bool(getattr(sys, "frozen", False)),
        sys.executable,
    )
    return path


def install_exception_hook() -> None:
    """Log otherwise-unhandled Python exceptions without hiding them."""
    previous = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            previous(exc_type, exc_value, exc_tb)
            return
        logging.getLogger("pdf_studio.unhandled").critical(
            "Unhandled exception",
            exc_info=(exc_type, exc_value, exc_tb),
        )
        previous(exc_type, exc_value, exc_tb)

    # Do not stack wrappers if setup is repeated in a test or embedded launch.
    if not getattr(sys.excepthook, "_pdf_studio_hook", False):
        _hook._pdf_studio_hook = True  # type: ignore[attr-defined]
        sys.excepthook = _hook


def dependency_versions(names: tuple[str, ...] = _DEPENDENCIES) -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in names:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "not installed"
        except Exception as exc:  # diagnostics must never crash the app
            versions[name] = f"unavailable ({type(exc).__name__})"
    return versions


def _safe_build_manifest() -> dict[str, Any] | None:
    path = resource_path("release/build_manifest.json")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return raw if isinstance(raw, dict) else None


def display_path(path: str | os.PathLike[str]) -> str:
    """Replace the current home directory with ~ before copying diagnostics."""
    try:
        value = str(Path(path).resolve())
        home = str(Path.home().resolve())
    except Exception:
        return str(path)
    if os.path.normcase(value).startswith(os.path.normcase(home)):
        suffix = value[len(home):].lstrip("\\/")
        return str(Path("~") / suffix) if suffix else "~"
    return value


def collect_diagnostics(
    app_name: str,
    app_version: str,
    *,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Collect support information without reading user documents."""
    info: dict[str, Any] = {
        "application": {
            "name": app_name,
            "version": app_version,
            "frozen": bool(getattr(sys, "frozen", False)),
        },
        "runtime": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": display_path(sys.executable),
            "architecture": platform.architecture()[0],
        },
        "operating_system": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
        },
        "paths": {
            "log_file": display_path(log_file_path()),
            "log_directory": display_path(log_directory()),
            "config_directory": display_path(config_directory()),
        },
        "dependencies": dependency_versions(),
        "build_manifest": _safe_build_manifest(),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        info["application_checks"] = dict(extra)
    return info


def format_diagnostics_report(info: Mapping[str, Any]) -> str:
    """Format diagnostics deterministically for clipboard/email support."""
    lines = ["PDF Studio Diagnostics", "=" * 22]

    def append_section(title: str, value: Any) -> None:
        lines.extend(["", title])
        lines.append("-" * len(title))
        if isinstance(value, Mapping):
            for key in sorted(value, key=str.lower):
                item = value[key]
                if isinstance(item, (dict, list, tuple)):
                    item = json.dumps(item, sort_keys=True, ensure_ascii=False)
                lines.append(f"{key}: {item}")
        else:
            lines.append(str(value))

    preferred = (
        "application",
        "runtime",
        "operating_system",
        "paths",
        "dependencies",
        "application_checks",
        "build_manifest",
    )
    for key in preferred:
        if key in info and info[key] is not None:
            append_section(key.replace("_", " ").title(), info[key])
    if "generated_utc" in info:
        lines.extend(["", f"Generated UTC: {info['generated_utc']}"])
    lines.extend([
        "",
        "Privacy note: no document contents are included. Review paths before sharing.",
    ])
    return "\n".join(lines) + "\n"


def log_current_exception(context: str) -> None:
    """Convenience helper for broad exception handlers at GUI boundaries."""
    logging.getLogger("pdf_studio.error").error(
        "%s\n%s", context, traceback.format_exc()
    )


def install_qt_message_logging() -> None:
    """Route Qt warnings/critical messages into the rotating application log."""
    try:
        from PyQt6.QtCore import QtMsgType, qInstallMessageHandler
    except Exception:
        return

    logger = logging.getLogger("qt")

    def _handler(mode, context, message):
        levels = {
            QtMsgType.QtDebugMsg: logging.DEBUG,
            QtMsgType.QtInfoMsg: logging.INFO,
            QtMsgType.QtWarningMsg: logging.WARNING,
            QtMsgType.QtCriticalMsg: logging.ERROR,
            QtMsgType.QtFatalMsg: logging.CRITICAL,
        }
        detail = message
        if context is not None:
            file_name = getattr(context, "file", None)
            line = getattr(context, "line", None)
            function = getattr(context, "function", None)
            if file_name or function:
                detail = f"{message} | {file_name or '?'}:{line or '?'} | {function or '?'}"
        logger.log(levels.get(mode, logging.INFO), detail)

    qInstallMessageHandler(_handler)
