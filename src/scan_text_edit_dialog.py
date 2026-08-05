"""Review and preview dialog for OCR-assisted scanned-text replacement."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QColorDialog,
    QMessageBox,
)

from scan_text_edit_core import (
    ALIGN_CENTER,
    ALIGN_LEFT,
    ALIGN_RIGHT,
    MODE_OVERLAY,
    MODE_REDACT,
    ScanTextReplacement,
    fit_font_size,
)


class ScanTextEditDialog(QDialog):
    def __init__(
        self,
        *,
        page_number: int,
        pdf_rect,
        preview_image: QImage,
        recognised_text: str,
        ocr_confidence: float,
        background_rgb: tuple[float, float, float],
        recognition_note: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Edit Scanned Text")
        self.setModal(True)
        self.resize(920, 610)
        self.setMinimumSize(760, 500)

        self.page_number = int(page_number)
        self.pdf_rect = tuple(float(v) for v in pdf_rect)
        self._source_image = preview_image.copy()
        self._background = QColor.fromRgbF(*background_rgb)
        self._text_color = QColor(Qt.GlobalColor.black)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(9)

        heading = QLabel(
            f"Page {self.page_number + 1} · selected region "
            f"{self.pdf_rect[2] - self.pdf_rect[0]:.0f} × "
            f"{self.pdf_rect[3] - self.pdf_rect[1]:.0f} pt"
        )
        heading.setStyleSheet("font-weight:600; font-size:14px;")
        root.addWidget(heading)

        columns = QHBoxLayout()
        columns.setSpacing(12)
        root.addLayout(columns, 1)

        preview_col = QVBoxLayout()
        preview_title = QLabel("Replacement preview")
        preview_title.setStyleSheet("font-weight:600;")
        preview_col.addWidget(preview_title)
        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setMinimumWidth(390)
        preview_scroll.setStyleSheet("QScrollArea { background:#2a2a2a; }")
        preview_host = QWidget()
        preview_layout = QVBoxLayout(preview_host)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        preview_layout.addWidget(self.preview_label, 1)
        preview_scroll.setWidget(preview_host)
        preview_col.addWidget(preview_scroll, 1)
        columns.addLayout(preview_col, 1)

        controls = QVBoxLayout()
        controls.setSpacing(8)
        columns.addLayout(controls, 1)

        confidence_text = recognition_note.strip() or (
            f"OCR confidence: {ocr_confidence:.0f}%"
            if ocr_confidence > 0
            else "OCR confidence unavailable - type the replacement manually"
        )
        self.ocr_status = QLabel(confidence_text)
        self.ocr_status.setStyleSheet("color:#555;")
        controls.addWidget(self.ocr_status)

        controls.addWidget(QLabel("Recognised text"))
        self.original_edit = QTextEdit()
        self.original_edit.setPlainText(recognised_text)
        self.original_edit.setReadOnly(True)
        self.original_edit.setMaximumHeight(105)
        controls.addWidget(self.original_edit)

        controls.addWidget(QLabel("Replacement text"))
        self.replacement_edit = QTextEdit()
        self.replacement_edit.setPlainText(recognised_text)
        self.replacement_edit.setPlaceholderText(
            "Type the corrected replacement text here…"
        )
        self.replacement_edit.setMinimumHeight(130)
        controls.addWidget(self.replacement_edit, 1)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Reversible white-out overlay", MODE_OVERLAY)
        self.mode_combo.addItem("Permanent redaction + replacement", MODE_REDACT)
        form.addRow("Apply as", self.mode_combo)

        self.font_size = QDoubleSpinBox()
        self.font_size.setRange(0.0, 72.0)
        self.font_size.setDecimals(1)
        self.font_size.setSingleStep(0.5)
        self.font_size.setSpecialValueText("Auto fit")
        self.font_size.setValue(0.0)
        form.addRow("Font size", self.font_size)

        self.alignment = QComboBox()
        self.alignment.addItem("Left", ALIGN_LEFT)
        self.alignment.addItem("Centre", ALIGN_CENTER)
        self.alignment.addItem("Right", ALIGN_RIGHT)
        form.addRow("Alignment", self.alignment)

        colour_row = QHBoxLayout()
        self.background_button = QPushButton("Background")
        self.text_button = QPushButton("Text colour")
        colour_row.addWidget(self.background_button)
        colour_row.addWidget(self.text_button)
        form.addRow("Colours", colour_row)
        controls.addLayout(form)

        self.safety_label = QLabel()
        self.safety_label.setWordWrap(True)
        self.safety_label.setObjectName("ScanTextSafety")
        controls.addWidget(self.safety_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply
        )
        self.apply_button = buttons.button(QDialogButtonBox.StandardButton.Apply)
        self.apply_button.setText("Apply Replacement")
        self.apply_button.clicked.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.replacement_edit.textChanged.connect(self._refresh_preview)
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        self.font_size.valueChanged.connect(self._refresh_preview)
        self.alignment.currentIndexChanged.connect(self._refresh_preview)
        self.background_button.clicked.connect(self._choose_background)
        self.text_button.clicked.connect(self._choose_text_color)

        self._update_colour_buttons()
        self._mode_changed()
        self._refresh_preview()


    def _validate_and_accept(self):
        try:
            self.replacement_plan().validated(self.pdf_rect)
        except ValueError as exc:
            QMessageBox.warning(self, "Replacement Text", str(exc))
            self.replacement_edit.setFocus()
            return
        self.accept()

    def replacement_plan(self) -> ScanTextReplacement:
        return ScanTextReplacement(
            page_number=self.page_number,
            rect=self.pdf_rect,
            original_text=self.original_edit.toPlainText(),
            replacement_text=self.replacement_edit.toPlainText(),
            mode=str(self.mode_combo.currentData()),
            font_size=float(self.font_size.value()),
            alignment=int(self.alignment.currentData()),
            text_color=(
                self._text_color.redF(),
                self._text_color.greenF(),
                self._text_color.blueF(),
            ),
            background_color=(
                self._background.redF(),
                self._background.greenF(),
                self._background.blueF(),
            ),
        )

    def _mode_changed(self):
        if self.mode_combo.currentData() == MODE_REDACT:
            self.safety_label.setText(
                "Permanent mode removes all PDF text, graphics, and image pixels "
                "under the selected rectangle. It cannot be undone after applying. "
                "PDF Studio will not save automatically."
            )
            self.safety_label.setStyleSheet(
                "background:#fff3cd; color:#664d03; padding:7px; border-radius:4px;"
            )
        else:
            self.safety_label.setText(
                "Recommended: creates one opaque FreeText annotation. The underlying "
                "scan remains intact and the replacement can later be deleted."
            )
            self.safety_label.setStyleSheet(
                "background:#e8f4fd; color:#0b4f71; padding:7px; border-radius:4px;"
            )
        self._refresh_preview()

    def _choose_background(self):
        selected = QColorDialog.getColor(
            self._background, self, "Replacement Background"
        )
        if selected.isValid():
            self._background = selected
            self._update_colour_buttons()
            self._refresh_preview()

    def _choose_text_color(self):
        selected = QColorDialog.getColor(
            self._text_color, self, "Replacement Text Colour"
        )
        if selected.isValid():
            self._text_color = selected
            self._update_colour_buttons()
            self._refresh_preview()

    def _update_colour_buttons(self):
        self.background_button.setStyleSheet(
            f"background:{self._background.name()}; color:"
            f"{'white' if self._background.lightness() < 128 else 'black'};"
        )
        self.text_button.setStyleSheet(
            f"background:{self._text_color.name()}; color:"
            f"{'white' if self._text_color.lightness() < 128 else 'black'};"
        )

    def _refresh_preview(self):
        if self._source_image.isNull():
            return
        pixmap = QPixmap.fromImage(self._source_image)
        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.fillRect(pixmap.rect(), self._background)
            painter.setPen(QPen(self._text_color))

            text = self.replacement_edit.toPlainText()
            pdf_width = max(1.0, self.pdf_rect[2] - self.pdf_rect[0])
            pixels_per_point = pixmap.width() / pdf_width
            point_size = fit_font_size(
                text or " ",
                self.pdf_rect,
                requested_size=float(self.font_size.value()),
            )
            font = QFont("Arial")
            font.setPixelSize(max(5, int(point_size * pixels_per_point)))
            painter.setFont(font)

            alignment = int(self.alignment.currentData())
            qt_align = {
                ALIGN_LEFT: Qt.AlignmentFlag.AlignLeft,
                ALIGN_CENTER: Qt.AlignmentFlag.AlignHCenter,
                ALIGN_RIGHT: Qt.AlignmentFlag.AlignRight,
            }[alignment]
            flags = qt_align | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap
            margin = max(2, int(3 * pixels_per_point))
            target = QRectF(
                margin,
                margin,
                max(1, pixmap.width() - margin * 2),
                max(1, pixmap.height() - margin * 2),
            )
            painter.drawText(target, int(flags), text)
        finally:
            painter.end()

        available = self.preview_label.size()
        if available.width() > 20 and available.height() > 20:
            pixmap = pixmap.scaled(
                max(20, available.width() - 10),
                max(20, available.height() - 10),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self.preview_label.setPixmap(pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_preview()
