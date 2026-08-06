"""
doc_import.py
-------------
Open Word / Excel documents in PDF Studio by converting them to PDF for
viewing and markup.

Fidelity policy
---------------
"Replicate the document exactly" is only truly achievable by letting the
program that OWNS the format render it. So the engine order is:

  1. Native Microsoft Office via COM automation  (Windows + Office installed)
       - Word  -> Word.Application.ExportAsFixedFormat  (identical to Word's
         own "Save as PDF" — the highest fidelity possible)
       - Excel -> Excel.Application.ExportAsFixedFormat
  2. LibreOffice headless  (cross-platform, free)
       - Very faithful, but NOT guaranteed pixel-identical to Word/Excel for
         complex layouts.
  3. Neither available -> raise ImportUnavailable with clear guidance.

Conversions land in a temp file; the caller opens that PDF. Nothing is
written back to the original document.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import uuid
import time
import re
import json
from datetime import datetime, timezone
from pathlib import Path

import fitz

# Extensions we can import. Word-like route through Word/Writer; spreadsheet
# extensions route through Excel/Calc.
WORD_EXTS  = {".docx", ".doc", ".rtf", ".odt"}
EXCEL_EXTS = {".xlsx", ".xls", ".ods", ".csv"}
IMPORT_EXTS = WORD_EXTS | EXCEL_EXTS


class ImportUnavailable(Exception):
    """No conversion engine is available on this machine."""


class ConversionError(Exception):
    """A converter was found but the conversion failed."""


def is_importable(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMPORT_EXTS


def category(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in EXCEL_EXTS:
        return "excel"
    return "word"


# ── Engine discovery ─────────────────────────────────────────────────────────

def _on_windows() -> bool:
    return sys.platform == "win32"


def _clean_subprocess_env():
    """Environment safe for launching external programs from a PyInstaller build.

    A frozen app prepends its unpacked temp dir (sys._MEIPASS) to PATH and sets
    library-path variables. External programs like LibreOffice then load the
    wrong DLLs and fail with errors such as "bootstrap.ini is corrupt".
    Restoring the pre-PyInstaller values fixes it. Harmless from source.
    """
    env = dict(os.environ)
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        for var in ("PATH", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
            orig = env.get(var + "_ORIG")
            if orig is not None:
                env[var] = orig
            elif meipass and var in env:
                parts = [
                    p for p in env[var].split(os.pathsep)
                    if p and os.path.normcase(os.path.abspath(p))
                    != os.path.normcase(os.path.abspath(meipass))
                ]
                env[var] = os.pathsep.join(parts)
    return env


def _find_soffice() -> str | None:
    """Locate the LibreOffice binary on PATH or in common install dirs."""
    for name in ("soffice", "soffice.exe", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    candidates = [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/usr/bin/soffice",
        "/usr/bin/libreoffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def _office_com_available(kind: str) -> bool:
    """True if Word/Excel COM automation is usable on this machine."""
    if not _on_windows():
        return False
    try:
        import win32com.client  # noqa: F401  (pywin32)
    except Exception:
        return False
    return True


def available_engines() -> dict:
    """Report what this machine can use (for diagnostics / About)."""
    return {
        "word_com":    _office_com_available("word"),
        "excel_com":   _office_com_available("excel"),
        "libreoffice": _find_soffice() is not None,
    }


def _validate_converted_pdf(path: str, *, started_at: float | None = None) -> str:
    """Require a fresh, parseable PDF before a converter may report success."""
    if not os.path.isfile(path):
        raise ConversionError("The converter did not create the expected PDF.")
    if started_at is not None:
        try:
            # Filesystem timestamp precision differs, so tolerate two seconds.
            if os.path.getmtime(path) < started_at - 2.0:
                raise ConversionError("The converter output is stale.")
        except OSError as exc:
            raise ConversionError(f"Could not inspect converter output: {exc}") from exc
    try:
        check = fitz.open(path)
    except Exception as exc:
        raise ConversionError(f"The converter output is not a valid PDF: {exc}") from exc
    try:
        if check.page_count < 1:
            raise ConversionError("The converter output contains no pages.")
        for page_number in range(check.page_count):
            _ = check.load_page(page_number).rect
    finally:
        check.close()
    return path



def imported_pdf_default_path(source_path: str) -> str:
    """Return the durable PDF destination suggested for an imported document."""
    source = Path(source_path).expanduser().resolve()
    return str(source.with_suffix(".pdf"))


_IMPORT_CACHE_OWNER = "PDF Studio Office import cache"
_IMPORT_CACHE_SCHEMA = 1
_IMPORT_SESSION_RE = re.compile(r"^[0-9a-f]{32}$")
_IMPORT_MARKER = "import_owner.json"
_IMPORT_OUTPUT = "converted.pdf"


def import_cache_root(*, temp_root: Path | None = None) -> Path:
    """Return the dedicated root for PDF Studio Office conversion caches."""
    root = (temp_root or Path(tempfile.gettempdir())).expanduser().resolve()
    return root / "PDF Studio" / "Imports"


def _create_import_workspace() -> tuple[Path, Path]:
    session_id = uuid.uuid4().hex
    workspace = import_cache_root() / session_id
    workspace.mkdir(parents=True, mode=0o700)
    marker = workspace / _IMPORT_MARKER
    marker.write_text(
        json.dumps(
            {
                "schema_version": _IMPORT_CACHE_SCHEMA,
                "owner": _IMPORT_CACHE_OWNER,
                "session_id": session_id,
                "created_utc": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return workspace, workspace / _IMPORT_OUTPUT


def _owned_import_workspace(candidate: Path, *, temp_root: Path | None = None) -> Path | None:
    """Return the marker-proven workspace owning ``candidate``, if any."""
    raw_candidate = candidate.expanduser()
    try:
        if raw_candidate.is_symlink():
            return None
        resolved = raw_candidate.resolve()
        workspace = resolved.parent
        root = import_cache_root(temp_root=temp_root).resolve()
    except OSError:
        return None
    if resolved.name != _IMPORT_OUTPUT:
        return None
    if workspace.parent != root or not _IMPORT_SESSION_RE.fullmatch(workspace.name):
        return None
    if workspace.is_symlink():
        return None
    marker = workspace / _IMPORT_MARKER
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("owner") != _IMPORT_CACHE_OWNER:
        return None
    if payload.get("session_id") != workspace.name:
        return None
    return workspace


def _is_owned_temporary_import(candidate: Path, *, temp_root: Path | None = None) -> bool:
    return _owned_import_workspace(candidate, temp_root=temp_root) is not None


def cleanup_temporary_import(path: str | None) -> bool:
    """Delete a complete marker-owned Office conversion workspace."""
    if not path:
        return False
    workspace = _owned_import_workspace(Path(path))
    if workspace is None:
        return False
    try:
        shutil.rmtree(workspace)
    except OSError:
        return False
    return not workspace.exists()


def cleanup_stale_temporary_imports(
    *,
    max_age_seconds: float = 7 * 24 * 60 * 60,
    now: float | None = None,
) -> list[str]:
    """Remove only marker-owned import workspaces older than the age limit."""
    if max_age_seconds < 0:
        raise ValueError("max_age_seconds cannot be negative.")
    root = import_cache_root()
    cutoff = (time.time() if now is None else float(now)) - max_age_seconds
    removed: list[str] = []
    try:
        candidates = list(root.iterdir()) if root.is_dir() else []
    except OSError:
        return removed
    for workspace in candidates:
        if workspace.is_symlink() or not workspace.is_dir():
            continue
        candidate = workspace / _IMPORT_OUTPUT
        owned = _owned_import_workspace(candidate)
        if owned is None:
            continue
        try:
            marker_stat = (workspace / _IMPORT_MARKER).stat()
            if marker_stat.st_mtime > cutoff:
                continue
            shutil.rmtree(workspace)
            if not workspace.exists():
                removed.append(str(workspace.resolve()))
        except OSError:
            continue
    return removed


# ── Public entry point ───────────────────────────────────────────────────────

def convert_to_pdf(src_path: str, prefer: str | None = None) -> str:
    """Convert an Office document to a marker-owned temporary PDF cache."""
    if not os.path.exists(src_path):
        raise ConversionError(f"File not found: {src_path}")

    cat = category(src_path)
    _workspace, out_path = _create_import_workspace()
    out_pdf = str(out_path)

    use_office = _office_com_available(cat) and prefer != "libreoffice"
    use_lo = _find_soffice() is not None
    try:
        if use_office and prefer != "libreoffice":
            try:
                if cat == "excel":
                    return _convert_excel_com(src_path, out_pdf)
                return _convert_word_com(src_path, out_pdf)
            except Exception as exc:
                # Remove a partial Office output but retain the proven-owned
                # workspace for the LibreOffice fallback.
                out_path.unlink(missing_ok=True)
                if not use_lo:
                    raise ConversionError(
                        f"Microsoft {'Excel' if cat == 'excel' else 'Word'} could "
                        f"not convert this file:\n\n{exc}"
                    ) from exc

        if use_lo:
            return _convert_libreoffice(src_path, out_pdf)

        raise ImportUnavailable(
            "To open Word and Excel files, this app needs one of:\n\n"
            "  • Microsoft Office (Word / Excel) — gives an exact copy, and is "
            "the recommended option on Windows; or\n"
            "  • LibreOffice (free) — https://www.libreoffice.org/download\n\n"
            "Install either one, then try opening the document again."
        )
    except Exception:
        cleanup_temporary_import(out_pdf)
        raise

# ── Native Microsoft Office (highest fidelity) ───────────────────────────────

def _convert_word_com(src_path: str, out_pdf: str) -> str:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    word = None
    doc = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = False
        doc = word.Documents.Open(os.path.abspath(src_path), ReadOnly=True)
        # wdExportFormatPDF = 17 — identical to Word's "Save as PDF"
        doc.ExportAsFixedFormat(
            OutputFileName=os.path.abspath(out_pdf),
            ExportFormat=17,
        )
        return _validate_converted_pdf(out_pdf)
    finally:
        try:
            if doc is not None:
                doc.Close(SaveChanges=False)
        except Exception:
            pass
        try:
            if word is not None:
                word.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()


def _convert_excel_com(src_path: str, out_pdf: str) -> str:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    excel = None
    wb = None
    try:
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        wb = excel.Workbooks.Open(os.path.abspath(src_path), ReadOnly=True)
        # xlTypePDF = 0
        wb.ExportAsFixedFormat(0, os.path.abspath(out_pdf))
        return _validate_converted_pdf(out_pdf)
    finally:
        try:
            if wb is not None:
                wb.Close(SaveChanges=False)
        except Exception:
            pass
        try:
            if excel is not None:
                excel.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()


# ── LibreOffice headless (free fallback) ─────────────────────────────────────

def _convert_libreoffice(src_path: str, out_pdf: str, timeout: int = 120) -> str:
    soffice = _find_soffice()
    if not soffice:
        raise ImportUnavailable("LibreOffice was not found.")

    # Both the LibreOffice profile and output workspace are unique per run.
    # Same-basename conversions can therefore never consume one another's files.
    profile = tempfile.mkdtemp(prefix="pdfstudio_lo_profile_")
    workspace = tempfile.mkdtemp(prefix="pdfstudio_lo_output_")
    from pathlib import Path
    profile_uri = Path(profile).as_uri()
    cmd = [
        soffice,
        "--headless",
        "--norestore",
        "--nolockcheck",
        f"-env:UserInstallation={profile_uri}",
        "--convert-to", "pdf",
        "--outdir", workspace,
        os.path.abspath(src_path),
    ]
    started_at = time.time()
    try:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=_clean_subprocess_env(),
            )
        except subprocess.TimeoutExpired as exc:
            raise ConversionError("LibreOffice took too long and was stopped.") from exc

        details = (proc.stderr or proc.stdout or "").strip()[:400]
        if proc.returncode != 0:
            raise ConversionError(
                "LibreOffice reported a conversion failure."
                + (f"\n\n{details}" if details else "")
            )

        produced = os.path.join(
            workspace,
            os.path.splitext(os.path.basename(src_path))[0] + ".pdf",
        )
        _validate_converted_pdf(produced, started_at=started_at)

        # The public target is already unique, but commit with os.replace only
        # after full validation so an existing file is never consumed as input.
        os.makedirs(os.path.dirname(os.path.abspath(out_pdf)), exist_ok=True)
        os.replace(produced, out_pdf)
        return _validate_converted_pdf(out_pdf, started_at=started_at)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
        shutil.rmtree(workspace, ignore_errors=True)

