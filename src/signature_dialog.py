"""
signature_dialog.py
-------------------
Signature dialog with two modes:

  * Draw   — draw a signature with the mouse (transparent-background pixmap)
  * Import — load a PNG/JPG signature image (e.g. a scan or a phone photo),
             with optional "remove white background" for scans

Either way the dialog returns a QPixmap via ``self.signature_pixmap`` that the
main app stamps onto the page as an image. This is NOT a cryptographic /
digital signature — it is a visual ink stamp.
"""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QWidget, QSizePolicy,
                             QComboBox, QColorDialog, QRadioButton,
                             QStackedWidget, QCheckBox, QFileDialog,
                             QButtonGroup)
from PyQt6.QtGui import (QPixmap, QPainter, QPen, QColor, QCursor,
                         QImage)
from PyQt6.QtCore import Qt, QPoint, QSize


# Bound the working size of imported images so the white-key pass stays fast
# and the embedded signature doesn't bloat the PDF.
MAX_IMPORT_WIDTH = 1000


def make_white_transparent(pixmap: QPixmap, threshold: int = 235) -> QPixmap:
    """Return a copy of *pixmap* with near-white pixels made transparent.

    Ideal for scanned/photographed signatures on white paper.
    """
    img = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    if img.width() > MAX_IMPORT_WIDTH:
        img = img.scaledToWidth(
            MAX_IMPORT_WIDTH, Qt.TransformationMode.SmoothTransformation
        ).convertToFormat(QImage.Format.Format_ARGB32)
    w, h = img.width(), img.height()
    for y in range(h):
        for x in range(w):
            c = QColor(img.pixel(x, y))
            if c.red() >= threshold and c.green() >= threshold and c.blue() >= threshold:
                img.setPixelColor(x, y, QColor(0, 0, 0, 0))
    return QPixmap.fromImage(img)


class SignatureCanvas(QWidget):
    """A white canvas the user draws on with the mouse."""
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

    def set_pen_color(self, color: QColor):
        self._pen_color = color

    def set_pen_width(self, w: int):
        self._pen_width = w

    def clear(self):
        self._image.fill(Qt.GlobalColor.white)
        self.update()

    def is_blank(self) -> bool:
        white = QColor(Qt.GlobalColor.white).rgb()
        for y in range(0, self._image.height(), 4):
            for x in range(0, self._image.width(), 4):
                if self._image.pixel(x, y) != white:
                    return False
        return True

    def get_pixmap(self) -> QPixmap:
        """Return only the ink area as a transparent-background pixmap."""
        result = QImage(self._image.size(), QImage.Format.Format_ARGB32)
        result.fill(Qt.GlobalColor.transparent)
        for y in range(self._image.height()):
            for x in range(self._image.width()):
                px = QColor(self._image.pixel(x, y))
                if px.red() < 240 or px.green() < 240 or px.blue() < 240:
                    result.setPixelColor(x, y, px)
        return QPixmap.fromImage(result)

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
    """Modal dialog: draw OR import a signature image; returns a QPixmap."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Signature")
        self.setModal(True)
        self.signature_pixmap = None
        self._imported_raw = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        mode_row = QHBoxLayout()
        self.mode_draw   = QRadioButton("Draw signature")
        self.mode_import = QRadioButton("Import image file")
        self.mode_draw.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.mode_draw)
        grp.addButton(self.mode_import)
        mode_row.addWidget(self.mode_draw)
        mode_row.addWidget(self.mode_import)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_draw_page())
        self.stack.addWidget(self._build_import_page())
        layout.addWidget(self.stack)
        self.mode_draw.toggled.connect(
            lambda on: self.stack.setCurrentIndex(0 if on else 1))

        btn_row = QHBoxLayout()
        accept_btn = QPushButton("\u2714  Add Signature")
        accept_btn.setStyleSheet(
            "background:#2ecc71;color:white;font-weight:bold;padding:6px 14px;border-radius:4px;")
        accept_btn.clicked.connect(self._accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(accept_btn)
        layout.addLayout(btn_row)

    def _build_draw_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(QLabel("Draw your signature below."))
        self.canvas = SignatureCanvas()
        v.addWidget(self.canvas, alignment=Qt.AlignmentFlag.AlignCenter)

        tool_row = QHBoxLayout()
        tool_row.addWidget(QLabel("Thickness:"))
        self.width_combo = QComboBox()
        self.width_combo.addItems(["1", "2", "3", "4", "6", "8"])
        self.width_combo.setCurrentText("3")
        self.width_combo.currentTextChanged.connect(
            lambda val: self.canvas.set_pen_width(int(val)))
        tool_row.addWidget(self.width_combo)

        self.color_btn = QPushButton("Ink Colour")
        self.color_btn.clicked.connect(self._pick_color)
        tool_row.addWidget(self.color_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.canvas.clear)
        tool_row.addWidget(clear_btn)
        tool_row.addStretch()
        v.addLayout(tool_row)
        return page

    def _build_import_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(QLabel(
            "Choose a signature image (PNG, JPG). "
            "PNGs with a transparent background work best."))

        choose = QPushButton("\U0001F4C1  Choose image\u2026")
        choose.clicked.connect(self._choose_image)
        v.addWidget(choose)

        self.preview = QLabel("No image chosen")
        self.preview.setFixedSize(500, 150)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet(
            "border: 1px dashed #888; background: #fafafa; color:#888;")
        v.addWidget(self.preview, alignment=Qt.AlignmentFlag.AlignCenter)

        self.white_key = QCheckBox("Remove white background (recommended for scans)")
        self.white_key.setChecked(True)
        self.white_key.toggled.connect(self._refresh_preview)
        v.addWidget(self.white_key)
        return page

    def _choose_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose signature image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif);;All Files (*)")
        if not path:
            return
        pm = QPixmap(path)
        if pm.isNull():
            self.preview.setText("Could not load that image")
            self._imported_raw = None
            return
        self._imported_raw = pm
        self._refresh_preview()

    def _refresh_preview(self):
        if self._imported_raw is None:
            return
        pm = self._processed_import()
        scaled = pm.scaled(self.preview.size(),
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        self.preview.setPixmap(scaled)

    def _processed_import(self):
        pm = self._imported_raw
        if self.white_key.isChecked():
            return make_white_transparent(pm)
        if pm.width() > MAX_IMPORT_WIDTH:
            return pm.scaledToWidth(MAX_IMPORT_WIDTH,
                                    Qt.TransformationMode.SmoothTransformation)
        return pm

    def _pick_color(self):
        col = QColorDialog.getColor(QColor("#1a1a2e"), self, "Choose Ink Colour")
        if col.isValid():
            self.canvas.set_pen_color(col)
            self.color_btn.setStyleSheet(
                f"background:{col.name()};color:{'white' if col.lightness()<128 else 'black'};")

    def _accept(self):
        if self.mode_import.isChecked():
            if self._imported_raw is None:
                self.preview.setText("Please choose an image first")
                return
            self.signature_pixmap = self._processed_import()
        else:
            self.signature_pixmap = self.canvas.get_pixmap()
        self.accept()
