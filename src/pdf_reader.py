"""
pdf_reader.py
-------------
Application entry point.

Free, no-strings PDF viewer/editor. Launches straight into the main window —
no license check, no trial, no activation.

Command line:
    PDF Studio.exe  <file>        open a PDF/Word/Excel file (used by Windows
                                  file associations — the "%1")
    PDF Studio.exe  --register    register PDF Studio as a handler for PDF
                                  (and Word/Excel) files on Windows, then open
                                  Windows "Default apps" to confirm
    PDF Studio.exe  --register --pdf-only    register for .pdf only
    PDF Studio.exe  --unregister  remove those file associations
"""

import os
import sys


def _file_arg(argv):
    """First non-flag argument that points at an existing file."""
    for a in argv[1:]:
        if a and not a.startswith("-") and os.path.exists(a):
            return a
    return None


def _handle_registration(argv) -> bool:
    """If a --register/--unregister flag is present, do it and return True."""
    if "--register" not in argv and "--unregister" not in argv:
        return False
    if sys.platform != "win32":
        print("File-type registration is only available on Windows.")
        return True
    try:
        import register_file_types as reg
    except Exception as e:
        print(f"Could not load the registration helper: {e}")
        return True
    if "--unregister" in argv:
        reg.unregister()
        print("PDF Studio file associations removed.")
    else:
        exts = reg.register(pdf_only="--pdf-only" in argv)
        print("Registered PDF Studio for:", ", ".join(exts))
        reg.open_default_apps_settings()
    return True


if __name__ == "__main__":
    if _handle_registration(sys.argv):
        sys.exit(0)

    from PyQt6.QtWidgets import QApplication
    from pdf_reader_app import PDFReader

    app = QApplication(sys.argv)
    QApplication.setQuitOnLastWindowClosed(True)

    reader = PDFReader()
    reader.show()

    path = _file_arg(sys.argv)
    if path:
        # _open_pdf_path also routes Word/Excel files through conversion.
        reader._open_pdf_path(path)

    sys.exit(app.exec())
