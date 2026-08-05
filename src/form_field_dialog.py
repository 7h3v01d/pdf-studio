"""Properties dialog for fields created or selected in Form Designer."""
from __future__ import annotations

import fitz
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
)


class FormFieldPropertiesDialog(QDialog):
    def __init__(self, field: fitz.Widget, parent=None, *, custom_kind: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Form Field Properties")
        self.setMinimumWidth(410)

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit(str(field.field_name or ""))
        self.label_edit = QLineEdit(str(getattr(field, "field_label", "") or ""))
        self.required_check = QCheckBox("Required")
        self.read_only_check = QCheckBox("Read-only")
        self.multiline_check = QCheckBox("Allow multiple lines")
        self.editable_choice_check = QCheckBox("Allow values not in the list")
        self.choices_edit = QPlainTextEdit()
        self.choices_edit.setPlaceholderText("One dropdown choice per line")
        self.choices_edit.setMaximumHeight(120)

        flags = int(getattr(field, "field_flags", 0) or 0)
        self.required_check.setChecked(bool(flags & fitz.PDF_FIELD_IS_REQUIRED))
        self.read_only_check.setChecked(bool(flags & fitz.PDF_FIELD_IS_READ_ONLY))
        self.multiline_check.setChecked(bool(flags & fitz.PDF_TX_FIELD_IS_MULTILINE))
        self.editable_choice_check.setChecked(bool(flags & fitz.PDF_CH_FIELD_IS_EDIT))

        is_text = field.field_type == fitz.PDF_WIDGET_TYPE_TEXT
        is_date = custom_kind == "Date"
        is_dropdown = field.field_type == fitz.PDF_WIDGET_TYPE_COMBOBOX
        self._is_dropdown = is_dropdown

        if is_dropdown:
            self.choices_edit.setPlainText(
                "\n".join(str(value) for value in (field.choice_values or []))
            )

        type_name = getattr(field, "field_type_string", None) or "Form field"
        if is_date:
            type_name = "Date field"
        elif custom_kind == "Initials":
            type_name = "Initials signature field"
        elif custom_kind == "RadioGroup":
            type_name = "Radio group"

        form.addRow("Type:", QLabel(type_name))
        form.addRow("Field name:", self.name_edit)
        form.addRow("Tooltip / label:", self.label_edit)
        form.addRow("", self.required_check)
        form.addRow("", self.read_only_check)
        if is_text and not is_date:
            form.addRow("", self.multiline_check)
        if is_dropdown:
            form.addRow("Choices:", self.choices_edit)
            form.addRow("", self.editable_choice_check)
        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def values(self) -> dict:
        choices = [
            line.strip()
            for line in self.choices_edit.toPlainText().splitlines()
            if line.strip() or line == ""
        ]
        return {
            "name": self.name_edit.text(),
            "label": self.label_edit.text(),
            "required": self.required_check.isChecked(),
            "read_only": self.read_only_check.isChecked(),
            "multiline": self.multiline_check.isChecked(),
            "choices": choices if self._is_dropdown else None,
            "editable": (
                self.editable_choice_check.isChecked()
                if self._is_dropdown
                else None
            ),
        }
