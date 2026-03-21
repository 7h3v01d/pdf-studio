from PyQt6.QtWidgets import QLabel

class PDFPageWidget(QLabel):
    """
    A custom QLabel that automatically repositions its child form fields
    whenever it is resized.
    """
    def __init__(self, app_instance, page_num, parent=None):
        super().__init__(parent)
        self.app = app_instance
        self.page_num = page_num

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.page_num in self.app.field_widgets:
            self.app._reposition_form_fields(self.page_num, self)
