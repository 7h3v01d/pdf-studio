"""
pdf_reader.py
-------------
Application entry point.

Free, no-strings PDF viewer/editor. Launches straight into the main
window — no license check, no trial, no activation.
"""

import sys
from PyQt6.QtWidgets import QApplication

from pdf_reader_app import PDFReader


if __name__ == '__main__':
    app = QApplication(sys.argv)
    QApplication.setQuitOnLastWindowClosed(True)

    reader = PDFReader()
    reader.show()
    sys.exit(app.exec())
