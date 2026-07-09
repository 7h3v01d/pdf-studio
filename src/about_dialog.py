"""
about_dialog.py
---------------
About / Help dialog.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QScrollArea, QFrame, QSizePolicy)
from PyQt6.QtGui import QFont, QColor, QPainter, QLinearGradient, QPixmap, QPen
from PyQt6.QtCore import Qt, QSize, QRect


# ── App metadata — SINGLE SOURCE OF TRUTH ────────────────────────────────────
# Change APP_NAME here and the whole app (title bar, About box, menus) follows.
APP_NAME      = "PDF Studio"
APP_VERSION   = "2.0.0"
COMPANY_NAME  = "Leon Priest"
LEAD_DEV      = "Leon Priest · github.com/7h3v01d"
DESCRIPTION = (
    "A professional PDF reader and editor for modern document workflows.\n"
    "Open, annotate, sign, redact, fill forms, and organize PDF files\n"
    "within a clean, capable, and production-ready interface."
)
COPYRIGHT     = "© 2025 Leon Priest — Apache License 2.0"
BUILT_WITH    = "PyMuPDF (MuPDF)  ·  PyQt6  ·  Python 3"
# ─────────────────────────────────────────────────────────────────────────────

ACCENT   = "#2563EB"   # accent
ACCENT_L = "#EFF6FF"   # light tint
DARK     = "#1e293b"
MID      = "#64748b"
LIGHT    = "#f8fafc"


def _logo_pixmap(size: int = 64) -> QPixmap:
    """Load the real app icon if available, else generate a placeholder."""
    import os
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
    if os.path.exists(icon_path):
        pix = QPixmap(icon_path)
        if not pix.isNull():
            return pix.scaled(size, size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
    # Fallback: generate K monogram
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Gradient circle background
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QColor("#2563EB"))
    grad.setColorAt(1.0, QColor("#1d4ed8"))
    p.setBrush(grad)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(2, 2, size - 4, size - 4)

    # Logo mark (simplified pentagon / arch)
    p.setPen(QPen(QColor("white"), 2.5, Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    cx, cy = size // 2, size // 2
    half = size // 4
    # Draw a simple "K" monogram
    font = QFont("Segoe UI", size // 3, QFont.Weight.Bold)
    p.setFont(font)
    p.setPen(QColor("white"))
    p.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "K")

    p.end()
    return px


class AboutDialog(QDialog):
    """
    Professional About / Help dialog.
    Two tabs: About  |  Keyboard Shortcuts
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setModal(True)
        self.setFixedSize(560, 480)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._build_ui()

    # =========================================================================
    # UI construction
    # =========================================================================

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header banner ─────────────────────────────────────────────────
        root.addWidget(self._make_header())

        # ── Tab widget ────────────────────────────────────────────────────
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.addTab(self._make_about_tab(),    "  About  ")
        tabs.addTab(self._make_shortcuts_tab(),"  Keyboard Shortcuts  ")
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: {LIGHT};
            }}
            QTabBar::tab {{
                background: #e2e8f0;
                color: {MID};
                padding: 8px 20px;
                font-size: 12px;
                border: none;
                border-bottom: 2px solid transparent;
            }}
            QTabBar::tab:selected {{
                background: {LIGHT};
                color: {ACCENT};
                font-weight: bold;
                border-bottom: 2px solid {ACCENT};
            }}
            QTabBar::tab:hover:!selected {{
                background: #dbeafe;
                color: {ACCENT};
            }}
        """)
        root.addWidget(tabs, stretch=1)

        # ── Footer ────────────────────────────────────────────────────────
        root.addWidget(self._make_footer())

    def _make_header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(110)
        w.setStyleSheet(f"background: {DARK};")
        row = QHBoxLayout(w)
        row.setContentsMargins(28, 0, 28, 0)
        row.setSpacing(20)

        # Logo
        logo_lbl = QLabel()
        logo_lbl.setPixmap(_logo_pixmap(60))
        logo_lbl.setFixedSize(60, 60)
        row.addWidget(logo_lbl)

        # Title block
        text_col = QVBoxLayout()
        text_col.setSpacing(3)

        app_lbl = QLabel(APP_NAME)
        app_lbl.setStyleSheet(
            "color: white; font-size: 22px; font-weight: bold; background: transparent;")
        text_col.addWidget(app_lbl)

        sub_lbl = QLabel(f"Version {APP_VERSION}  ·  {COMPANY_NAME}")
        sub_lbl.setStyleSheet(
            f"color: #93c5fd; font-size: 12px; background: transparent;")
        text_col.addWidget(sub_lbl)

        dev_lbl = QLabel(LEAD_DEV)
        dev_lbl.setStyleSheet(
            f"color: #64748b; font-size: 11px; background: transparent;")
        text_col.addWidget(dev_lbl)

        row.addLayout(text_col)
        row.addStretch()
        return w

    def _make_about_tab(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background: {LIGHT};")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(18)

        # Description card
        layout.addWidget(self._card(
            "About This Application",
            DESCRIPTION,
            icon="📄"
        ))

        # Built with card
        layout.addWidget(self._card(
            "Built With",
            BUILT_WITH,
            icon="🔧"
        ))

        # Company card
        layout.addWidget(self._card(
            "Company",
            f"{COMPANY_NAME}\n{LEAD_DEV}",
            icon="🏢"
        ))

        layout.addStretch()
        return w

    def _make_shortcuts_tab(self) -> QWidget:
        outer = QWidget()
        outer.setStyleSheet(f"background: {LIGHT};")
        ol = QVBoxLayout(outer)
        ol.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        inner = QWidget()
        inner.setStyleSheet(f"background: {LIGHT};")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(32, 20, 32, 20)
        layout.setSpacing(14)

        groups = [
            ("File", [
                ("Ctrl+O",           "Open file"),
                ("Ctrl+S",           "Save"),
                ("Ctrl+Shift+S",     "Save As"),
                ("Ctrl+P",           "Print"),
                ("Ctrl+Q",           "Quit"),
            ]),
            ("Navigation", [
                ("← / →",            "Previous / next page"),
                ("Ctrl+← / →",       "Previous / next page"),
                ("Ctrl+Home",        "First page"),
                ("Ctrl+End",         "Last page"),
                ("Enter  (page box)","Go to typed page number"),
            ]),
            ("Zoom & View", [
                ("Ctrl++ / Ctrl+-",  "Zoom in / out"),
                ("Ctrl+Wheel",       "Zoom in / out"),
                ("Ctrl+Shift+H",     "Fit width"),
                ("Ctrl+Shift+F",     "Fit page"),
                ("Ctrl+R",           "Rotate 90°"),
                ("F11",              "Toggle full screen"),
                ("F4",               "Toggle navigation panel"),
            ]),
            ("Search & Edit", [
                ("Ctrl+F",           "Focus search box"),
                ("Enter  (search)",  "Find next result"),
                ("Ctrl+C",           "Copy selected text"),
                ("Ctrl+B",           "Add bookmark"),
                ("Escape",           "Cancel active tool"),
            ]),
        ]

        for group_title, shortcuts in groups:
            layout.addWidget(self._shortcut_group(group_title, shortcuts))

        layout.addStretch()
        scroll.setWidget(inner)
        ol.addWidget(scroll)
        return outer

    # =========================================================================
    # Component helpers
    # =========================================================================

    def _card(self, title: str, body: str, icon: str = "") -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: white;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }}
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        if icon:
            icon_lbl = QLabel(icon)
            icon_lbl.setStyleSheet("font-size: 16px; background: transparent; border: none;")
            title_row.addWidget(icon_lbl)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {DARK};"
            " background: transparent; border: none;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        cl.addLayout(title_row)

        body_lbl = QLabel(body)
        body_lbl.setWordWrap(True)
        body_lbl.setStyleSheet(
            f"font-size: 12px; color: {MID}; background: transparent; border: none;"
            " line-height: 1.5;")
        cl.addWidget(body_lbl)

        return card

    def _shortcut_group(self, title: str, items: list) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Group heading
        heading = QLabel(title.upper())
        heading.setStyleSheet(
            f"color: {ACCENT}; font-size: 10px; font-weight: bold;"
            " letter-spacing: 1px; padding: 0 0 6px 0; background: transparent;")
        layout.addWidget(heading)

        # Separator line
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: #e2e8f0; background: #e2e8f0;")
        line.setFixedHeight(1)
        layout.addWidget(line)

        # Rows
        for i, (key, desc) in enumerate(items):
            row = QWidget()
            row.setStyleSheet(
                f"background: {'white' if i % 2 == 0 else LIGHT};"
                " border-radius: 0px;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(10, 6, 10, 6)

            key_lbl = QLabel(key)
            key_lbl.setFixedWidth(160)
            key_lbl.setStyleSheet(
                f"background: {ACCENT_L}; color: {ACCENT};"
                " font-family: 'Consolas', 'Courier New', monospace;"
                " font-size: 11px; font-weight: bold;"
                " border: 1px solid #bfdbfe; border-radius: 4px;"
                " padding: 2px 8px;")
            key_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(
                f"color: {MID}; font-size: 12px; background: transparent;")

            rl.addWidget(key_lbl)
            rl.addSpacing(12)
            rl.addWidget(desc_lbl)
            rl.addStretch()
            layout.addWidget(row)

        return w

    def _make_footer(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(50)
        w.setStyleSheet("background: #f1f5f9; border-top: 1px solid #e2e8f0;")
        row = QHBoxLayout(w)
        row.setContentsMargins(24, 0, 24, 0)

        copy_lbl = QLabel(COPYRIGHT)
        copy_lbl.setStyleSheet(f"color: {MID}; font-size: 11px; background: transparent;")
        row.addWidget(copy_lbl)
        row.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setFixedSize(80, 30)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT};
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: #1d4ed8; }}
            QPushButton:pressed {{ background: #1e40af; }}
        """)
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        return w
