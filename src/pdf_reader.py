"""
pdf_reader.py
-------------
Application entry point.

Free, no-strings PDF viewer/editor. Launches through a branded splash screen —
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
import time
import traceback


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


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if _handle_registration(argv):
        return 0

    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QMessageBox

    from about_dialog import APP_NAME, COMPANY_NAME
    from pdf_reader_app import PDFReader
    from splash_screen import PDFStudioSplash
    from startup_splash_core import MIN_SPLASH_MS, remaining_display_ms

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(COMPANY_NAME)
    QApplication.setQuitOnLastWindowClosed(True)

    splash = None
    started_at = time.monotonic()
    try:
        splash = PDFStudioSplash()
        splash.show()
        # Force the first paint before the heavier main-window construction.
        app.processEvents()
    except Exception:
        # A cosmetic resource failure must never prevent PDF Studio launching.
        traceback.print_exc()
        splash = None

    try:
        reader = PDFReader()
        # Give the already-visible splash another repaint opportunity after
        # the main window has finished constructing.
        app.processEvents()
    except Exception as exc:
        if splash is not None:
            splash.close()
            app.processEvents()
        traceback.print_exc()
        QMessageBox.critical(
            None,
            f"{APP_NAME} startup failed",
            "PDF Studio could not finish starting.\n\n"
            f"{type(exc).__name__}: {exc}",
        )
        return 1

    path = _file_arg(argv)

    def _show_main_window() -> None:
        reader.show()
        reader.raise_()
        reader.activateWindow()
        if path:
            # Open command-line / file-association documents only after the
            # splash has gone, so password prompts and errors cannot appear
            # behind an always-on-top startup window.
            QTimer.singleShot(0, lambda: reader._open_pdf_path(path))

    if splash is None:
        _show_main_window()
    else:
        elapsed_ms = (time.monotonic() - started_at) * 1000.0
        delay_ms = remaining_display_ms(elapsed_ms, MIN_SPLASH_MS)
        QTimer.singleShot(delay_ms, lambda: splash.fade_out(_show_main_window))

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
