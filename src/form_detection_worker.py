"""Background worker for OCR-assisted form detection on one page."""
from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
import fitz

from form_detection_core import (
    GraphicPrimitive,
    OCRWord,
    detect_form_suggestions,
    raster_graphics_from_image,
    words_from_tesseract_data,
)


class FormDetectionWorker(QThread):
    detection_complete = pyqtSignal(object, object)  # suggestions, statistics
    error = pyqtSignal(str)

    def __init__(
        self,
        *,
        page_number: int,
        page_rect: tuple[float, float, float, float],
        image_size: tuple[int, int],
        image_samples: bytes,
        native_words: list[dict],
        vector_graphics: list[dict],
        existing_field_rects: list[list[float]],
        tesseract_exe: str,
        language: str = "eng",
        minimum_confidence: float = 0.60,
    ):
        super().__init__()
        self.page_number = int(page_number)
        self.page_rect = fitz.Rect(page_rect)
        self.image_size = tuple(image_size)
        self.image_samples = bytes(image_samples)
        self.native_words = [OCRWord(**item) for item in native_words]
        self.vector_graphics = [GraphicPrimitive(**item) for item in vector_graphics]
        self.existing_field_rects = existing_field_rects
        self.tesseract_exe = str(tesseract_exe or "")
        self.language = language
        self.minimum_confidence = float(minimum_confidence)

    def run(self):
        try:
            from PIL import Image

            image = Image.frombytes("RGB", self.image_size, self.image_samples)
            words = list(self.native_words)
            text_source = "native"
            if len(words) < 3:
                if not self.tesseract_exe:
                    raise RuntimeError(
                        "This page has no usable text layer and Tesseract OCR is not ready."
                    )
                import pytesseract
                from pytesseract import Output

                pytesseract.pytesseract.tesseract_cmd = self.tesseract_exe
                data = pytesseract.image_to_data(
                    image,
                    lang=self.language,
                    config="--psm 11",
                    output_type=Output.DICT,
                    timeout=180,
                )
                words = words_from_tesseract_data(
                    data, self.image_size, self.page_rect
                )
                text_source = "ocr"

            raster_graphics = raster_graphics_from_image(image, self.page_rect)
            graphics = list(self.vector_graphics) + raster_graphics
            suggestions = detect_form_suggestions(
                page_number=self.page_number,
                page_rect=self.page_rect,
                words=words,
                graphics=graphics,
                existing_field_rects=self.existing_field_rects,
                minimum_confidence=self.minimum_confidence,
            )
            statistics = {
                "words": len(words),
                "text_source": text_source,
                "vector_graphics": len(self.vector_graphics),
                "raster_graphics": len(raster_graphics),
                "suggestions": len(suggestions),
            }
            self.detection_complete.emit(
                [suggestion.as_record() for suggestion in suggestions], statistics
            )
        except Exception as exc:
            self.error.emit(f"{type(exc).__name__}: {exc}")
