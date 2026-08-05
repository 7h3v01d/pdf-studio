"""Forms sidebar for filling existing AcroForms and designing new fields."""
from __future__ import annotations

from typing import Iterable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


FIELD_TYPE_LABELS = {
    0: "Unknown",
    1: "Button",
    2: "Checkbox",
    3: "Dropdown",
    4: "List",
    5: "Radio",
    6: "Signature",
    7: "Text",
}


class FormsPanel(QWidget):
    """Navigation and design panel for AcroForm fields."""

    jump_to_field = pyqtSignal(int, float, float)
    field_selected = pyqtSignal(int, int)
    highlight_changed = pyqtSignal(bool)
    reset_page_requested = pyqtSignal()
    reset_all_requested = pyqtSignal()
    flatten_copy_requested = pyqtSignal()

    design_mode_changed = pyqtSignal(bool)
    designer_tool_requested = pyqtSignal(str)
    delete_selected_requested = pyqtSignal()
    properties_requested = pyqtSignal()

    detect_page_requested = pyqtSignal(float)
    review_suggestions_requested = pyqtSignal()
    clear_suggestions_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 3, 4, 4)
        layout.setSpacing(5)

        self.summary_label = QLabel("No document open")
        self.summary_label.setWordWrap(True)
        self.summary_label.setObjectName("FormsSummary")
        layout.addWidget(self.summary_label)

        self.field_list = QListWidget()
        self.field_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.field_list.setAlternatingRowColors(True)
        self.field_list.setMinimumHeight(80)
        self.field_list.itemActivated.connect(self._activate_item)
        self.field_list.itemDoubleClicked.connect(self._activate_item)
        self.field_list.currentItemChanged.connect(self._selection_changed)
        layout.addWidget(self.field_list, 1)

        self.highlight_checkbox = QCheckBox("Highlight fillable fields")
        self.highlight_checkbox.setChecked(True)
        self.highlight_checkbox.toggled.connect(self.highlight_changed)
        layout.addWidget(self.highlight_checkbox)

        row = QHBoxLayout()
        row.setSpacing(4)
        self.reset_page_button = QPushButton("Reset Page")
        self.reset_all_button = QPushButton("Reset All")
        row.addWidget(self.reset_page_button)
        row.addWidget(self.reset_all_button)
        layout.addLayout(row)

        self.flatten_button = QPushButton("Flatten Form to Copy…")
        self.flatten_button.setToolTip(
            "Create a separate non-editable PDF with the current form values "
            "permanently drawn onto the pages. The original remains editable."
        )
        layout.addWidget(self.flatten_button)

        detection_separator = QFrame()
        detection_separator.setFrameShape(QFrame.Shape.HLine)
        detection_separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(detection_separator)

        detection_title = QLabel("SMART FORM DETECTION")
        detection_title.setObjectName("FormsDetectionTitle")
        layout.addWidget(detection_title)

        self.detection_help = QLabel(
            "Analyse the current page, then review suggestions in a separate "
            "resizable window before creating fields."
        )
        self.detection_help.setWordWrap(True)
        layout.addWidget(self.detection_help)

        detection_controls = QHBoxLayout()
        detection_controls.setSpacing(4)
        self.confidence_combo = QComboBox()
        self.confidence_combo.addItem("More suggestions", 0.55)
        self.confidence_combo.addItem("Balanced", 0.65)
        self.confidence_combo.addItem("High confidence", 0.78)
        self.confidence_combo.setCurrentIndex(1)
        self.confidence_combo.setToolTip(
            "Higher confidence produces fewer, more conservative suggestions."
        )
        self.detect_page_button = QPushButton("Detect Current Page…")
        detection_controls.addWidget(self.confidence_combo)
        detection_controls.addWidget(self.detect_page_button, 1)
        layout.addLayout(detection_controls)

        self.detection_status = QLabel("No suggestions yet")
        self.detection_status.setWordWrap(True)
        self.detection_status.setObjectName("FormsDetectionStatus")
        layout.addWidget(self.detection_status)

        review_row = QHBoxLayout()
        review_row.setSpacing(4)
        self.review_suggestions_button = QPushButton("Review Suggestions…")
        self.review_suggestions_button.setToolTip(
            "Open the full suggestion review window."
        )
        self.clear_suggestions_button = QPushButton("Clear")
        review_row.addWidget(self.review_suggestions_button, 1)
        review_row.addWidget(self.clear_suggestions_button)
        layout.addLayout(review_row)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        designer_title = QLabel("FORM DESIGNER")
        designer_title.setObjectName("FormsDesignerTitle")
        layout.addWidget(designer_title)

        self.design_mode_checkbox = QCheckBox("Design mode")
        self.design_mode_checkbox.setToolTip(
            "Switch from filling fields to creating, moving, resizing, and deleting them."
        )
        self.design_mode_checkbox.toggled.connect(self.design_mode_changed)
        layout.addWidget(self.design_mode_checkbox)

        tool_grid = QGridLayout()
        tool_grid.setHorizontalSpacing(4)
        tool_grid.setVerticalSpacing(4)
        self.select_button = QPushButton("Select")
        self.text_button = QPushButton("Text Field")
        self.checkbox_button = QPushButton("Checkbox")
        self.dropdown_button = QPushButton("Dropdown")
        self.date_button = QPushButton("Date")
        self.radio_button = QPushButton("Yes / No")
        self.signature_button = QPushButton("Signature")
        self.initials_button = QPushButton("Initials")
        self._designer_buttons = (
            ("select", self.select_button),
            ("text", self.text_button),
            ("checkbox", self.checkbox_button),
            ("dropdown", self.dropdown_button),
            ("date", self.date_button),
            ("radio", self.radio_button),
            ("signature", self.signature_button),
            ("initials", self.initials_button),
        )
        for index, (_key, button) in enumerate(self._designer_buttons):
            button.setCheckable(True)
            tool_grid.addWidget(button, index // 2, index % 2)
        layout.addLayout(tool_grid)

        for key, button in self._designer_buttons:
            button.clicked.connect(
                lambda _checked=False, selected=key:
                    self.designer_tool_requested.emit(selected)
            )

        self.selected_label = QLabel("No field selected")
        self.selected_label.setWordWrap(True)
        layout.addWidget(self.selected_label)

        selected_row = QHBoxLayout()
        selected_row.setSpacing(4)
        self.properties_button = QPushButton("Properties…")
        self.delete_button = QPushButton("Delete Field")
        selected_row.addWidget(self.properties_button)
        selected_row.addWidget(self.delete_button)
        layout.addLayout(selected_row)

        self.designer_help = QLabel(
            "Choose a field type, then click or drag on a page. Yes / No creates a "
            "linked radio pair. Signature and Initials create unsigned PDF signature "
            "placeholders. In Select mode, drag to move or use the lower-right handle "
            "to resize."
        )
        self.designer_help.setWordWrap(True)
        self.designer_help.setObjectName("FormsDesignerHelp")
        layout.addWidget(self.designer_help)

        self.reset_page_button.clicked.connect(self.reset_page_requested)
        self.reset_all_button.clicked.connect(self.reset_all_requested)
        self.flatten_button.clicked.connect(self.flatten_copy_requested)
        self.properties_button.clicked.connect(self.properties_requested)
        self.delete_button.clicked.connect(self.delete_selected_requested)
        self.detect_page_button.clicked.connect(
            lambda: self.detect_page_requested.emit(
                float(self.confidence_combo.currentData())
            )
        )
        self.review_suggestions_button.clicked.connect(
            self.review_suggestions_requested
        )
        self.clear_suggestions_button.clicked.connect(
            self.clear_suggestions_requested
        )

        self._document_open = False
        self._detection_suggestions = []
        self.set_document_fields([], document_open=False)
        self.set_detection_suggestions([], status_text="No suggestions yet")
        self.set_designer_state(False, "select", None)

    def set_document_fields(
        self,
        fields: Iterable[dict],
        *,
        document_open: bool = True,
    ) -> None:
        records = list(fields)
        self._document_open = bool(document_open)
        self.field_list.clear()

        pages = {record["page"] for record in records}
        if not document_open:
            self.summary_label.setText("No document open")
        elif records:
            self.summary_label.setText(
                f"{len(records)} field{'s' if len(records) != 1 else ''} "
                f"on {len(pages)} page{'s' if len(pages) != 1 else ''}. "
                "Double-click a field to jump to it."
            )
        else:
            self.summary_label.setText(
                "This document has no interactive form fields. Use Form Designer to add some."
            )

        for record in records:
            name = record.get("name") or "Unnamed field"
            ftype = record.get("type_name") or FIELD_TYPE_LABELS.get(
                record.get("type", 0), "Unknown"
            )
            flags = []
            if record.get("required"):
                flags.append("required")
            if record.get("read_only"):
                flags.append("read-only")
            suffix = f"  ({', '.join(flags)})" if flags else ""

            item = QListWidgetItem(
                f"Page {record['page'] + 1} · {name}\n{ftype}{suffix}"
            )
            item.setData(Qt.ItemDataRole.UserRole, record)
            value = record.get("value")
            item.setToolTip(
                f"Name: {name}\nType: {ftype}\nPage: {record['page'] + 1}"
                + (f"\nCurrent value: {value}" if value not in (None, "", []) else "")
            )
            self.field_list.addItem(item)

        has_fields = bool(records)
        self.field_list.setEnabled(has_fields)
        self.highlight_checkbox.setEnabled(has_fields)
        self.reset_page_button.setEnabled(has_fields)
        self.reset_all_button.setEnabled(has_fields)
        self.flatten_button.setEnabled(has_fields)

        self.detect_page_button.setEnabled(document_open)
        self.confidence_combo.setEnabled(document_open)
        self.design_mode_checkbox.setEnabled(document_open)
        for _key, button in self._designer_buttons:
            button.setEnabled(document_open and self.design_mode_checkbox.isChecked())

    def set_highlight_checked(self, checked: bool) -> None:
        self.highlight_checkbox.blockSignals(True)
        self.highlight_checkbox.setChecked(checked)
        self.highlight_checkbox.blockSignals(False)

    def set_designer_state(
        self,
        enabled: bool,
        tool: str,
        selected_record: dict | None,
    ) -> None:
        self.design_mode_checkbox.blockSignals(True)
        self.design_mode_checkbox.setChecked(bool(enabled))
        self.design_mode_checkbox.blockSignals(False)

        for key, button in self._designer_buttons:
            button.blockSignals(True)
            button.setChecked(bool(enabled and tool == key))
            button.setEnabled(bool(self._document_open and enabled))
            button.blockSignals(False)

        if selected_record:
            name = selected_record.get("name") or "Unnamed field"
            ftype = selected_record.get("type_name") or FIELD_TYPE_LABELS.get(
                selected_record.get("type", 0), "Unknown"
            )
            self.selected_label.setText(
                f"Selected: {name} ({ftype}, page {selected_record.get('page', 0) + 1})"
            )
        else:
            self.selected_label.setText("No field selected")

        has_selection = bool(enabled and selected_record)
        self.properties_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)

    def set_detection_running(self, running: bool) -> None:
        self.detect_page_button.setEnabled(bool(self._document_open and not running))
        self.confidence_combo.setEnabled(bool(self._document_open and not running))
        if running:
            self.detection_status.setText(
                "Analysing the current page with OCR and layout detection…"
            )
        has_suggestions = bool(self._detection_suggestions)
        self.review_suggestions_button.setEnabled(has_suggestions and not running)
        self.clear_suggestions_button.setEnabled(has_suggestions and not running)

    def set_detection_suggestions(
        self, suggestions: Iterable[dict], *, status_text: str = ""
    ) -> None:
        self._detection_suggestions = list(suggestions)
        count = len(self._detection_suggestions)
        if status_text:
            self.detection_status.setText(status_text)
        elif count:
            self.detection_status.setText(
                f"{count} suggestion{'s' if count != 1 else ''} ready. "
                "Open Review Suggestions to inspect and approve them."
            )
        else:
            self.detection_status.setText(
                "No reliable field suggestions were found on this page."
            )
        self.review_suggestions_button.setEnabled(bool(count))
        self.clear_suggestions_button.setEnabled(bool(count))

    def select_record(self, page_number: int, xref: int) -> None:
        for index in range(self.field_list.count()):
            item = self.field_list.item(index)
            record = item.data(Qt.ItemDataRole.UserRole) or {}
            if int(record.get("page", -1)) == int(page_number) and int(
                record.get("xref", -1)
            ) == int(xref):
                self.field_list.blockSignals(True)
                self.field_list.setCurrentItem(item)
                self.field_list.scrollToItem(item)
                self.field_list.blockSignals(False)
                return

    def _activate_item(self, item: QListWidgetItem) -> None:
        record = item.data(Qt.ItemDataRole.UserRole) or {}
        rect = record.get("rect") or [0.0, 0.0, 0.0, 0.0]
        self.jump_to_field.emit(
            int(record.get("page", 0)), float(rect[0]), float(rect[1])
        )

    def _selection_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            return
        record = current.data(Qt.ItemDataRole.UserRole) or {}
        page = int(record.get("page", -1))
        xref = int(record.get("xref", -1))
        if page >= 0 and xref >= 0:
            self.field_selected.emit(page, xref)
