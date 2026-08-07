from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from signature_dialog import SignatureCanvas


def _app():
    return QApplication.instance() or QApplication([])


def _ink_metrics(canvas: SignatureCanvas):
    image = canvas.get_pixmap().toImage()
    colored = []
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.alpha() > 0:
                colored.append(color)
    return colored


def test_signature_style_changes_redraw_existing_ink():
    app = _app()
    assert app is not None
    canvas = SignatureCanvas()
    canvas._strokes = [[QPoint(40, 75), QPoint(460, 75)]]
    canvas._rebuild_image()

    canvas.set_pen_width(1)
    thin_count = len(_ink_metrics(canvas))

    chosen = QColor("#c2185b")
    canvas.set_pen_color(chosen)
    canvas.set_pen_width(8)
    thick_pixels = _ink_metrics(canvas)

    assert len(thick_pixels) > thin_count * 3
    assert any(
        abs(pixel.red() - chosen.red()) < 12
        and abs(pixel.green() - chosen.green()) < 12
        and abs(pixel.blue() - chosen.blue()) < 12
        for pixel in thick_pixels
    )
