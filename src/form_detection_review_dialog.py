"""Resizable review dialog for OCR-assisted form-field suggestions."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from form_detection_review_model import (
    ReviewSuggestion,
    checked_records,
    normalise_review_suggestions,
    review_summary,
)


class FormDetectionReviewDialog(QDialog):
    """Review suggestions without crowding the navigation sidebar."""

    suggestion_selected = pyqtSignal(int, float, float, str)
    create_requested = pyqtSignal(object)
    clear_requested = pyqtSignal()

    COL_USE = 0
    COL_TYPE = 1
    COL_LABEL = 2
    COL_CONFIDENCE = 3
    COL_NOTES = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review Smart Form Suggestions")
        self.setModal(True)
        self.resize(820, 470)
        self.setMinimumSize(680, 380)

        self._suggestions: list[ReviewSuggestion] = []
        self._page_number = 0
        self._statistics: dict = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(9)

        heading = QLabel("Review detected form fields")
        heading.setStyleSheet("font-size: 15px; font-weight: 600;")
        root.addWidget(heading)

        self.summary_label = QLabel("No suggestions ready for review.")
        self.summary_label.setWordWrap(True)
        root.addWidget(self.summary_label)

        self.source_label = QLabel("")
        self.source_label.setWordWrap(True)
        self.source_label.setStyleSheet("color: palette(mid);")
        root.addWidget(self.source_label)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ("Use", "Type", "Detected label", "Confidence", "Why suggested")
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(self.COL_USE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_TYPE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_LABEL, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(
            self.COL_CONFIDENCE, QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(self.COL_NOTES, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._emit_current_selection)
        root.addWidget(self.table, 1)

        selection_row = QHBoxLayout()
        selection_row.setSpacing(6)
        self.check_all_button = QPushButton("Check All")
        self.uncheck_all_button = QPushButton("Uncheck All")
        self.high_confidence_button = QPushButton("Check 80%+")
        selection_row.addWidget(self.check_all_button)
        selection_row.addWidget(self.uncheck_all_button)
        selection_row.addWidget(self.high_confidence_button)
        selection_row.addStretch(1)
        root.addLayout(selection_row)

        action_row = QHBoxLayout()
        self.clear_button = QPushButton("Clear Suggestions")
        self.clear_button.setToolTip(
            "Remove the temporary previews without changing the PDF."
        )
        action_row.addWidget(self.clear_button)
        action_row.addStretch(1)

        self.button_box = QDialogButtonBox()
        self.create_button = self.button_box.addButton(
            "Create Checked", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.cancel_button = self.button_box.addButton(
            QDialogButtonBox.StandardButton.Cancel
        )
        action_row.addWidget(self.button_box)
        root.addLayout(action_row)

        self.check_all_button.clicked.connect(lambda: self._set_all_checked(True))
        self.uncheck_all_button.clicked.connect(lambda: self._set_all_checked(False))
        self.high_confidence_button.clicked.connect(self._check_high_confidence)
        self.create_button.clicked.connect(self._create_checked)
        self.cancel_button.clicked.connect(self.reject)
        self.clear_button.clicked.connect(self.clear_requested)

    def set_suggestions(
        self,
        suggestions,
        *,
        page_number: int = 0,
        statistics: dict | None = None,
    ) -> None:
        self._suggestions = normalise_review_suggestions(suggestions)
        self._page_number = max(0, int(page_number))
        self._statistics = dict(statistics or {})

        self.table.blockSignals(True)
        self.table.setRowCount(len(self._suggestions))
        for row, suggestion in enumerate(self._suggestions):
            use_item = QTableWidgetItem("")
            use_item.setFlags(
                (use_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                & ~Qt.ItemFlag.ItemIsEditable
            )
            use_item.setCheckState(Qt.CheckState.Checked)
            use_item.setData(Qt.ItemDataRole.UserRole, suggestion.suggestion_id)

            type_item = QTableWidgetItem(suggestion.type_label)
            label_item = QTableWidgetItem(suggestion.label)
            confidence_item = QTableWidgetItem(
                f"{suggestion.confidence_percent}%"
            )
            confidence_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            notes = suggestion.rationale or f"Detected from {suggestion.source}"
            notes_item = QTableWidgetItem(notes)
            notes_item.setToolTip(
                f"Source: {suggestion.source}\n"
                f"Page: {suggestion.page + 1}\n"
                f"Rectangle: {suggestion.rect}"
            )

            if suggestion.confidence_percent >= 85:
                brush = QBrush(QColor(34, 120, 70, 35))
            elif suggestion.confidence_percent >= 70:
                brush = QBrush(QColor(220, 145, 20, 35))
            else:
                brush = QBrush(QColor(190, 70, 45, 35))
            for item in (use_item, type_item, label_item, confidence_item, notes_item):
                item.setBackground(brush)

            self.table.setItem(row, self.COL_USE, use_item)
            self.table.setItem(row, self.COL_TYPE, type_item)
            self.table.setItem(row, self.COL_LABEL, label_item)
            self.table.setItem(row, self.COL_CONFIDENCE, confidence_item)
            self.table.setItem(row, self.COL_NOTES, notes_item)

        self.table.blockSignals(False)
        self.table.resizeRowsToContents()
        if self._suggestions:
            self.table.selectRow(0)

        self.summary_label.setText(
            review_summary(self._suggestions, page_number=self._page_number)
        )
        source = self._statistics.get("text_source", "text")
        words = int(self._statistics.get("words", 0) or 0)
        self.source_label.setText(
            f"Analysed {words} {source} word{'s' if words != 1 else ''}. "
            "Nothing is added to the PDF until you choose Create Checked."
        )
        enabled = bool(self._suggestions)
        self.table.setEnabled(enabled)
        self.create_button.setEnabled(enabled)
        self.check_all_button.setEnabled(enabled)
        self.uncheck_all_button.setEnabled(enabled)
        self.high_confidence_button.setEnabled(enabled)

    def checked_suggestions(self) -> list[dict]:
        checked_ids: list[str] = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self.COL_USE)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                checked_ids.append(str(item.data(Qt.ItemDataRole.UserRole) or ""))
        return checked_records(self._suggestions, checked_ids)

    def _set_all_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self.COL_USE)
            if item is not None:
                item.setCheckState(state)

    def _check_high_confidence(self) -> None:
        by_id = {item.suggestion_id: item for item in self._suggestions}
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self.COL_USE)
            if item is None:
                continue
            suggestion = by_id.get(str(item.data(Qt.ItemDataRole.UserRole) or ""))
            item.setCheckState(
                Qt.CheckState.Checked
                if suggestion is not None and suggestion.confidence >= 0.80
                else Qt.CheckState.Unchecked
            )

    def _emit_current_selection(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._suggestions):
            return
        suggestion = self._suggestions[row]
        self.suggestion_selected.emit(
            suggestion.page,
            suggestion.rect[0],
            suggestion.rect[1],
            suggestion.suggestion_id,
        )

    def _create_checked(self) -> None:
        records = self.checked_suggestions()
        if not records:
            QMessageBox.information(
                self,
                "No Suggestions Checked",
                "Check at least one suggestion before creating fields.",
            )
            return
        self.create_requested.emit(records)
