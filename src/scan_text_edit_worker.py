"""Background OCR worker for one selected page region."""
from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal


class ScanTextOCRWorker(QThread):
    completed = pyqtSignal(str, float)  # recognised text, mean confidence
    error = pyqtSignal(str)

    def __init__(
        self,
        *,
        image_size: tuple[int, int],
        image_samples: bytes,
        tesseract_exe: str,
        language: str = "eng",
        parent=None,
    ):
        super().__init__(parent)
        self.image_size = tuple(image_size)
        self.image_samples = bytes(image_samples)
        self.tesseract_exe = str(tesseract_exe)
        self.language = str(language or "eng")

    def run(self):
        try:
            from PIL import Image
            import pytesseract
            from pytesseract import Output

            pytesseract.pytesseract.tesseract_cmd = self.tesseract_exe
            image = Image.frombytes("RGB", self.image_size, self.image_samples)
            data = pytesseract.image_to_data(
                image,
                lang=self.language,
                config="--psm 6",
                output_type=Output.DICT,
                timeout=45,
            )
            from scan_text_edit_core import ocr_text_and_confidence

            text, mean_confidence = ocr_text_and_confidence(data)
            self.completed.emit(text, mean_confidence)
        except Exception as exc:
            self.error.emit(f"{type(exc).__name__}: {exc}")
