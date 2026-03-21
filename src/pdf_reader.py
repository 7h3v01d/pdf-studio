import sys
from PyQt6.QtWidgets import QApplication
from pdf_reader_app import PDFReader

if __name__ == '__main__':
    app = QApplication(sys.argv)
    QApplication.setQuitOnLastWindowClosed(True)
    reader = PDFReader()
    reader.show()
    sys.exit(app.exec())
