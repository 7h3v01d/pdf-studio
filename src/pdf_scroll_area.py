from PyQt6.QtWidgets import QScrollArea
from PyQt6.QtCore import Qt

SINGLE_PAGE = 0
CONTINUOUS = 1

class PDFScrollArea(QScrollArea):
    """Custom QScrollArea: mouse-wheel page navigation in single-page mode,
    Ctrl+Wheel zoom in both modes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent

    def wheelEvent(self, event):
        if not self.parent.pdf_document:
            super().wheelEvent(event)
            return

        # Ctrl+Wheel → zoom
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.parent.zoom_in()
            else:
                self.parent.zoom_out()
            event.accept()
            return

        if self.parent.view_mode == SINGLE_PAGE:
            v_scroll = self.verticalScrollBar()
            at_top = v_scroll.value() == v_scroll.minimum()
            at_bottom = v_scroll.value() == v_scroll.maximum()
            delta = event.angleDelta().y()
            content_height = self.widget().height()
            viewport_height = self.viewport().height()
            content_fits = content_height <= viewport_height

            if content_fits or (delta > 0 and at_top) or (delta < 0 and at_bottom):
                if delta > 0 and self.parent.current_page > 0:
                    self.parent.prev_page()
                    return
                elif delta < 0 and self.parent.current_page < self.parent.total_pages - 1:
                    self.parent.next_page()
                    return

        super().wheelEvent(event)
