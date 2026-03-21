"""
signature_dialog.py
-------------------
A simple draw-your-own-signature dialog.
Returns a QPixmap of the signature on a transparent background,
sized to 400×120 by default.
"""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QWidget, QSizePolicy,
                             QComboBox, QColorDialog)
from PyQt6.QtGui import (QPixmap, QPainter, QPen, QColor, QCursor,
                         QImage)
from PyQt6.QtCore import Qt, QPoint, QSize


class SignatureCanvas(QWidget):
    """
    A white canvas the user draws on with the mouse.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(500, 150)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        self._image = QImage(self.size(), QImage.Format.Format_ARGB32)
        self._image.fill(Qt.GlobalColor.white)
        self._drawing = False
        self._last_point = QPoint()
        self._pen_color = QColor("#1a1a2e")
        self._pen_width = 3

    # ── drawing helpers ──────────────────────────────────────────────────
    def set_pen_color(self, color: QColor):
        self._pen_color = color

    def set_pen_width(self, w: int):
        self._pen_width = w

    def clear(self):
        self._image.fill(Qt.GlobalColor.white)
        self.update()

    def get_pixmap(self) -> QPixmap:
        """Return only the ink area as a transparent-background pixmap."""
        # Build a transparent copy; paste ink pixels only
        result = QImage(self._image.size(), QImage.Format.Format_ARGB32)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        # Composite: white pixels → transparent; coloured pixels → keep
        for y in range(self._image.height()):
            for x in range(self._image.width()):
                px = QColor(self._image.pixel(x, y))
                if px.red() < 240 or px.green() < 240 or px.blue() < 240:
                    result.setPixelColor(x, y, px)
        painter.end()
        return QPixmap.fromImage(result)

    # ── mouse events ──────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drawing = True
            self._last_point = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self._drawing and event.buttons() & Qt.MouseButton.LeftButton:
            painter = QPainter(self._image)
            pen = QPen(self._pen_color, self._pen_width,
                       Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap,
                       Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(self._last_point, event.position().toPoint())
            painter.end()
            self._last_point = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drawing = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawImage(0, 0, self._image)


class SignatureDialog(QDialog):
    """
    Modal dialog: draw a signature, pick colour/thickness, confirm.
    Returns the drawn signature via self.signature_pixmap.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Draw Signature")
        self.setModal(True)
        self.signature_pixmap: QPixmap | None = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ── Info label ──────────────────────────────────────────────────
        info = QLabel("Draw your signature below. Click <b>Accept</b> when done.")
        info.setWordWrap(True)
        layout.addWidget(info)

        # ── Canvas ──────────────────────────────────────────────────────
        self.canvas = SignatureCanvas()
        layout.addWidget(self.canvas, alignment=Qt.AlignmentFlag.AlignCenter)

        # ── Toolbar row ──────────────────────────────────────────────────
        tool_row = QHBoxLayout()

        # Pen width
        tool_row.addWidget(QLabel("Thickness:"))
        self.width_combo = QComboBox()
        self.width_combo.addItems(["1", "2", "3", "4", "6", "8"])
        self.width_combo.setCurrentText("3")
        self.width_combo.currentTextChanged.connect(
            lambda v: self.canvas.set_pen_width(int(v)))
        tool_row.addWidget(self.width_combo)

        # Colour
        self.color_btn = QPushButton("Ink Colour")
        self.color_btn.clicked.connect(self._pick_color)
        tool_row.addWidget(self.color_btn)

        # Clear
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.canvas.clear)
        tool_row.addWidget(clear_btn)
        tool_row.addStretch()
        layout.addLayout(tool_row)

        # ── Accept / Cancel ──────────────────────────────────────────────
        btn_row = QHBoxLayout()
        accept_btn = QPushButton("✔  Accept Signature")
        accept_btn.setStyleSheet(
            "background:#2ecc71;color:white;font-weight:bold;padding:6px 14px;border-radius:4px;")
        accept_btn.clicked.connect(self._accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(accept_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _pick_color(self):
        col = QColorDialog.getColor(QColor("#1a1a2e"), self, "Choose Ink Colour")
        if col.isValid():
            self.canvas.set_pen_color(col)
            self.color_btn.setStyleSheet(
                f"background:{col.name()};color:{'white' if col.lightness()<128 else 'black'};")

    def _accept(self):
        self.signature_pixmap = self.canvas.get_pixmap()
        self.accept()
