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


# ── Public entry point ───────────────────────────────────────────────────────

def convert_to_pdf(src_path: str, prefer: str | None = None) -> str:
    """Convert an office document to a temporary PDF and return its path.

    prefer: force an engine ("office" or "libreoffice") for testing; default
    picks the highest-fidelity engine available.
    """
    if not os.path.exists(src_path):
        raise ConversionError(f"File not found: {src_path}")

    cat = category(src_path)
    out_pdf = os.path.join(
        tempfile.gettempdir(),
        f"pdfstudio_import_{uuid.uuid4().hex[:8]}.pdf",
    )

    use_office = _office_com_available(cat) and prefer != "libreoffice"
    use_lo = _find_soffice() is not None

    if use_office and prefer != "libreoffice":
        try:
            if cat == "excel":
                return _convert_excel_com(src_path, out_pdf)
            return _convert_word_com(src_path, out_pdf)
        except Exception as e:
            # Native Office failed (odd install, macro prompt, etc.) — fall
            # through to LibreOffice rather than failing outright.
            if not use_lo:
                raise ConversionError(
                    f"Microsoft {'Excel' if cat == 'excel' else 'Word'} could not "
                    f"convert this file:\n\n{e}"
                )

    if use_lo:
        return _convert_libreoffice(src_path, out_pdf)

    raise ImportUnavailable(
        "To open Word and Excel files, this app needs one of:\n\n"
        "  • Microsoft Office (Word / Excel) — gives an exact copy, and is the\n"
        "    recommended option on Windows; or\n"
        "  • LibreOffice (free) — https://www.libreoffice.org/download\n\n"
        "Install either one, then try opening the document again."
    )


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
        return out_pdf
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
        return out_pdf
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

    out_dir = os.path.dirname(out_pdf)
    # A unique per-run profile avoids the "another instance is running" lock
    # when the user already has LibreOffice open.
    profile = os.path.join(
        tempfile.gettempdir(), f"pdfstudio_lo_{uuid.uuid4().hex[:8]}"
    )
    cmd = [
        soffice,
        "--headless",
        "--norestore",
        "--nolockcheck",
        f"-env:UserInstallation=file://{profile}",
        "--convert-to", "pdf",
        "--outdir", out_dir,
        os.path.abspath(src_path),
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        raise ConversionError("LibreOffice took too long and was stopped.")
    finally:
        shutil.rmtree(profile, ignore_errors=True)

    # LibreOffice writes <basename>.pdf into out_dir; rename to our target.
    produced = os.path.join(
        out_dir, os.path.splitext(os.path.basename(src_path))[0] + ".pdf"
    )
    if os.path.exists(produced):
        if os.path.abspath(produced) != os.path.abspath(out_pdf):
            shutil.move(produced, out_pdf)
        return out_pdf

    raise ConversionError(
        "LibreOffice did not produce a PDF.\n\n"
        f"{(proc.stderr or proc.stdout or '').strip()[:400]}"
    )
