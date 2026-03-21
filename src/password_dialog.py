"""
password_dialog.py
------------------
Two dialogs:
  - PasswordPromptDialog  : ask user for password to open a locked PDF
  - PasswordProtectDialog : configure encryption settings before saving
"""
import fitz

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QCheckBox, QFrame, QWidget, QGroupBox,
    QGridLayout, QMessageBox)
from PyQt6.QtGui import QIcon, QFont
from PyQt6.QtCore import Qt


ACCENT   = "#2563EB"
ACCENT_L = "#EFF6FF"
DARK     = "#1e293b"
MID      = "#64748b"
LIGHT    = "#f8fafc"
DANGER   = "#dc2626"
SUCCESS  = "#16a34a"


# ── Shared helpers ────────────────────────────────────────────────────────────

def _divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet("background: #e2e8f0; border: none;")
    return f


def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {DARK};")
    return lbl


def _input_style() -> str:
    return (
        "QLineEdit {"
        "  border: 1px solid #e2e8f0; border-radius: 4px;"
        "  padding: 6px 10px; font-size: 13px; background: white;"
        "}"
        "QLineEdit:focus { border-color: #2563EB; }"
    )


def _primary_btn(label: str) -> QPushButton:
    btn = QPushButton(label)
    btn.setFixedHeight(34)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: {ACCENT}; color: white;
            border: none; border-radius: 5px;
            font-size: 13px; font-weight: bold; padding: 0 18px;
        }}
        QPushButton:hover   {{ background: #1d4ed8; }}
        QPushButton:pressed {{ background: #1e40af; }}
        QPushButton:disabled{{ background: #93c5fd; }}
    """)
    return btn


def _cancel_btn() -> QPushButton:
    btn = QPushButton("Cancel")
    btn.setFixedHeight(34)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: white; color: {DARK};
            border: 1px solid #cbd5e1; border-radius: 5px;
            font-size: 12px; padding: 0 14px;
        }}
        QPushButton:hover {{ background: #f1f5f9; }}
    """)
    return btn


# =============================================================================
# 1. Password Prompt Dialog  (open a locked PDF)
# =============================================================================

class PasswordPromptDialog(QDialog):
    """
    Shown when fitz.open() raises an authentication error.
    Returns the entered password via self.password on accept.
    """
    def __init__(self, filename: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Password Required")
        self.setModal(True)
        self.setFixedSize(400, 240)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.password: str = ""
        self._build_ui(filename)

    def _build_ui(self, filename: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QWidget()
        hdr.setFixedHeight(60)
        hdr.setStyleSheet(f"background: {DARK};")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 0, 20, 0)
        icon = QLabel("🔒")
        icon.setStyleSheet("font-size: 22px; background: transparent;")
        title = QLabel("Password Protected Document")
        title.setStyleSheet(
            "color: white; font-size: 14px; font-weight: bold;"
            " background: transparent;")
        hl.addWidget(icon)
        hl.addSpacing(8)
        hl.addWidget(title)
        hl.addStretch()
        root.addWidget(hdr)

        body = QWidget()
        body.setStyleSheet(f"background: {LIGHT};")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(24, 18, 24, 18)
        bl.setSpacing(10)

        if filename:
            fn_lbl = QLabel(f"<i>{filename}</i> is password protected.")
            fn_lbl.setStyleSheet(f"color: {MID}; font-size: 11px;")
            bl.addWidget(fn_lbl)

        bl.addWidget(_field_label("Enter password:"))

        self._pw_edit = QLineEdit()
        self._pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_edit.setPlaceholderText("Password…")
        self._pw_edit.setStyleSheet(_input_style())
        self._pw_edit.returnPressed.connect(self._accept)
        bl.addWidget(self._pw_edit)

        # Show password toggle
        show_cb = QCheckBox("Show password")
        show_cb.setStyleSheet(f"color: {MID}; font-size: 11px;")
        show_cb.toggled.connect(
            lambda on: self._pw_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if on
                else QLineEdit.EchoMode.Password))
        bl.addWidget(show_cb)

        root.addWidget(body, stretch=1)

        # Footer
        ftr = QWidget()
        ftr.setFixedHeight(52)
        ftr.setStyleSheet(
            "background: #f1f5f9; border-top: 1px solid #e2e8f0;")
        fl = QHBoxLayout(ftr)
        fl.setContentsMargins(20, 0, 20, 0)
        fl.addStretch()
        ok_btn = _primary_btn("Unlock")
        ok_btn.clicked.connect(self._accept)
        cn_btn = _cancel_btn()
        cn_btn.clicked.connect(self.reject)
        fl.addWidget(ok_btn)
        fl.addSpacing(6)
        fl.addWidget(cn_btn)
        root.addWidget(ftr)

    def _accept(self):
        self.password = self._pw_edit.text()
        if not self.password:
            self._pw_edit.setStyleSheet(
                _input_style() + "QLineEdit { border-color: #dc2626; }")
            return
        self.accept()


# =============================================================================
# 2. Password Protect Dialog  (encrypt on save)
# =============================================================================

class PasswordProtectDialog(QDialog):
    """
    Configure encryption for a PDF before saving.
    Returns settings via properties on accept:
      self.user_password   : str   (required to open)
      self.owner_password  : str   (required to change permissions)
      self.encryption      : int   (fitz.PDF_ENCRYPT_* constant)
      self.permissions     : int   (fitz perm flags)
      self.remove_password : bool  (True → save without any encryption)
    """
    def __init__(self, is_encrypted: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Document Security")
        self.setModal(True)
        self.setFixedSize(480, 520)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        # Result properties
        self.user_password   = ""
        self.owner_password  = ""
        self.encryption      = fitz.PDF_ENCRYPT_AES_256
        self.permissions     = self._default_perms()
        self.remove_password = False

        self._is_encrypted = is_encrypted
        self._build_ui()

    @staticmethod
    def _default_perms() -> int:
        return (fitz.PDF_PERM_PRINT
                | fitz.PDF_PERM_COPY
                | fitz.PDF_PERM_ANNOTATE)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QWidget()
        hdr.setFixedHeight(60)
        hdr.setStyleSheet(f"background: {DARK};")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 0, 20, 0)
        icon = QLabel("🔐")
        icon.setStyleSheet("font-size: 22px; background: transparent;")
        title = QLabel("Document Security Settings")
        title.setStyleSheet(
            "color: white; font-size: 14px; font-weight: bold;"
            " background: transparent;")
        hl.addWidget(icon)
        hl.addSpacing(8)
        hl.addWidget(title)
        hl.addStretch()
        root.addWidget(hdr)

        body = QWidget()
        body.setStyleSheet(f"background: {LIGHT};")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(24, 16, 24, 16)
        bl.setSpacing(14)

        # Remove password option (only if already encrypted)
        if self._is_encrypted:
            rm_box = QWidget()
            rm_box.setStyleSheet(
                f"background: #fef2f2; border: 1px solid #fecaca;"
                f" border-radius: 6px;")
            rml = QHBoxLayout(rm_box)
            rml.setContentsMargins(12, 8, 12, 8)
            self._rm_cb = QCheckBox("Remove password protection from this document")
            self._rm_cb.setStyleSheet(
                f"color: {DANGER}; font-size: 12px; font-weight: bold;")
            self._rm_cb.toggled.connect(self._toggle_remove)
            rml.addWidget(self._rm_cb)
            bl.addWidget(rm_box)
            bl.addWidget(_divider())

        # Password fields
        self._fields_widget = QWidget()
        self._fields_widget.setStyleSheet("background: transparent;")
        fw = QVBoxLayout(self._fields_widget)
        fw.setContentsMargins(0, 0, 0, 0)
        fw.setSpacing(10)

        # User password
        fw.addWidget(_field_label("Document open password  (required to view):"))
        self._user_pw = QLineEdit()
        self._user_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._user_pw.setPlaceholderText("Leave blank for no open password")
        self._user_pw.setStyleSheet(_input_style())
        fw.addWidget(self._user_pw)

        self._user_pw2 = QLineEdit()
        self._user_pw2.setEchoMode(QLineEdit.EchoMode.Password)
        self._user_pw2.setPlaceholderText("Confirm open password")
        self._user_pw2.setStyleSheet(_input_style())
        fw.addWidget(self._user_pw2)

        fw.addWidget(_divider())

        # Owner password
        fw.addWidget(_field_label("Permissions password  (required to change settings):"))
        self._owner_pw = QLineEdit()
        self._owner_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._owner_pw.setPlaceholderText("Recommended if setting restrictions")
        self._owner_pw.setStyleSheet(_input_style())
        fw.addWidget(self._owner_pw)

        # Show passwords toggle
        show_cb = QCheckBox("Show passwords")
        show_cb.setStyleSheet(f"color: {MID}; font-size: 11px;")
        show_cb.toggled.connect(self._toggle_show)
        fw.addWidget(show_cb)

        fw.addWidget(_divider())

        # Permissions
        fw.addWidget(_field_label("Allow:"))
        self._perm_print  = QCheckBox("Printing")
        self._perm_copy   = QCheckBox("Copying text & images")
        self._perm_modify = QCheckBox("Modifying the document")
        self._perm_annot  = QCheckBox("Adding annotations & form fill")
        for cb in [self._perm_print, self._perm_copy,
                   self._perm_modify, self._perm_annot]:
            cb.setChecked(True)
            cb.setStyleSheet(f"color: {DARK}; font-size: 12px;")
            fw.addWidget(cb)

        bl.addWidget(self._fields_widget)

        # Info note
        note = QLabel(
            "ℹ  Encryption uses AES-256.  The document is encrypted when saved.")
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color: {MID}; font-size: 10px; background: {ACCENT_L};"
            f" border: 1px solid #bfdbfe; border-radius: 4px; padding: 6px 10px;")
        bl.addWidget(note)

        root.addWidget(body, stretch=1)

        # Footer
        ftr = QWidget()
        ftr.setFixedHeight(52)
        ftr.setStyleSheet(
            "background: #f1f5f9; border-top: 1px solid #e2e8f0;")
        fl = QHBoxLayout(ftr)
        fl.setContentsMargins(20, 0, 20, 0)
        fl.addStretch()
        ok_btn = _primary_btn("Apply & Save")
        ok_btn.clicked.connect(self._accept)
        cn_btn = _cancel_btn()
        cn_btn.clicked.connect(self.reject)
        fl.addWidget(ok_btn)
        fl.addSpacing(6)
        fl.addWidget(cn_btn)
        root.addWidget(ftr)

    def _toggle_remove(self, checked: bool):
        self._fields_widget.setEnabled(not checked)
        self.remove_password = checked

    def _toggle_show(self, on: bool):
        mode = (QLineEdit.EchoMode.Normal if on
                else QLineEdit.EchoMode.Password)
        for w in [self._user_pw, self._user_pw2, self._owner_pw]:
            w.setEchoMode(mode)

    def _accept(self):
        if self.remove_password:
            self.accept()
            return

        u1 = self._user_pw.text()
        u2 = self._user_pw2.text()
        if u1 != u2:
            QMessageBox.warning(self, "Password Mismatch",
                                "The open passwords do not match.")
            return

        self.user_password  = u1
        self.owner_password = self._owner_pw.text() or u1  # fallback

        # Build permissions int
        perms = 0
        if self._perm_print.isChecked():
            perms |= fitz.PDF_PERM_PRINT
        if self._perm_copy.isChecked():
            perms |= fitz.PDF_PERM_COPY
        if self._perm_modify.isChecked():
            perms |= fitz.PDF_PERM_MODIFY
        if self._perm_annot.isChecked():
            perms |= fitz.PDF_PERM_ANNOTATE
        self.permissions = perms
        self.encryption  = fitz.PDF_ENCRYPT_AES_256
        self.accept()
