"""
themes.py
---------
Appearance + accessibility system for PDF Studio.

Provides two full application themes and an app-wide text/UI size scale,
built with low-vision readability as the first priority:

  * "hc_light"        — High-Contrast Light: near-black text on pure white
  * "dark_industrial" — Dark Industrial: obsidian / teal / phosphor, high contrast

Both themes render all UI text in Atkinson Hyperlegible (bundled in ./fonts,
SIL Open Font License) — a typeface designed by the Braille Institute to
maximise legibility for readers with low vision.

The size scale (medium / large / xlarge) enlarges every menu, toolbar,
panel and control across the whole app — the single most useful lever for
central-vision loss such as macular degeneration.

Nothing here gates features or phones home; it is pure presentation.
"""
from __future__ import annotations

import os

from PyQt6.QtGui import QFont, QFontDatabase


# ── Font ─────────────────────────────────────────────────────────────────────

FONT_FAMILY_FALLBACK = '"Atkinson Hyperlegible", "Segoe UI", "Arial", sans-serif'
_installed_family: str | None = None


def _font_dir() -> str:
    """Locate the bundled fonts folder in both source and PyInstaller runs."""
    import sys
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    cand = os.path.join(base, "fonts")
    if os.path.isdir(cand):
        return cand
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")


def install_fonts() -> str:
    """Register the bundled Atkinson Hyperlegible faces once.

    Returns the resolved family name (falls back to a system sans if the
    bundled files are missing, so the app never fails to start over a font).
    """
    global _installed_family
    if _installed_family is not None:
        return _installed_family

    family = "Atkinson Hyperlegible"
    loaded_any = False
    fdir = _font_dir()
    if os.path.isdir(fdir):
        for fn in os.listdir(fdir):
            if fn.lower().endswith((".ttf", ".otf")):
                fid = QFontDatabase.addApplicationFont(os.path.join(fdir, fn))
                if fid != -1:
                    loaded_any = True
                    fams = QFontDatabase.applicationFontFamilies(fid)
                    if fams:
                        family = fams[0]

    _installed_family = family if loaded_any else "Segoe UI"
    return _installed_family


# ── Size scale ───────────────────────────────────────────────────────────────
# base = primary UI text size (px). icon = toolbar icon px. pad scales chrome.

SIZE_SCALES: dict[str, dict] = {
    "medium": {"label": "Medium",      "base": 14, "icon": 20, "pad": 6, "app_pt": 10},
    "large":  {"label": "Large",       "base": 17, "icon": 26, "pad": 8, "app_pt": 13},
    "xlarge": {"label": "Extra Large", "base": 21, "icon": 32, "pad": 10, "app_pt": 16},
}
DEFAULT_SIZE = "large"   # start large — this app's first user has low vision


# ── Theme palettes ───────────────────────────────────────────────────────────

THEMES: dict[str, dict] = {
    "hc_light": {
        "label": "High-Contrast Light",
        "is_dark": False,
        "radius": 6,
        "window": "#e9e9e9",
        "chrome": "#ffffff",
        "chrome_border": "#a8a8a8",
        "menubar_bg": "#ffffff", "menubar_fg": "#141414", "menubar_sel": "#d9e6fb",
        "menu_bg": "#ffffff", "menu_border": "#7a7a7a",
        "sel_bg": "#0a5ad6", "sel_fg": "#ffffff",
        "text": "#141414", "disabled_fg": "#9a9a9a",
        "tb_hover_bg": "#dbe8fc", "tb_hover_border": "#6a9be0",
        "tb_pressed_bg": "#b9d2f7", "tb_pressed_border": "#3a7bd5",
        "tb_checked_bg": "#cfe0fb", "tb_checked_border": "#0a5ad6", "tb_checked_fg": "#0a3f9c",
        "input_bg": "#ffffff", "input_border": "#7a7a7a",
        "pill_bg": "#dcdcdc", "pill_fg": "#333333",
        "dock_title_bg": "#e2e2e2", "dock_title_fg": "#141414",
        "list_bg": "#ffffff", "list_border": "#a8a8a8", "list_hover": "#e8f0fc",
        "navheader_bg": "#e2e2e2", "navheader_hover": "#d4d4d4", "navarrow": "#444444",
        "navtitle": "#141414", "navsection_bg": "#f2f2f2",
        "navsection_border": "#cfcfcf", "navbody_bg": "#ffffff",
        "splitter": "#bdbdbd", "splitter_hover": "#0a5ad6",
        "btn_bg": "#ffffff", "btn_border": "#7a7a7a",
        "btn_hover_bg": "#dbe8fc", "btn_hover_border": "#6a9be0", "btn_pressed": "#b9d2f7",
        "btn_disabled_fg": "#9a9a9a", "btn_disabled_bg": "#efefef",
        "status_bg": "#e2e2e2", "status_fg": "#2a2a2a",
        "tip_bg": "#fffce0", "tip_fg": "#141414", "tip_border": "#7a7a7a",
    },
    "dark_industrial": {
        "label": "Dark Industrial",
        "is_dark": True,
        "radius": 0,
        "window": "#05080b",
        "chrome": "#0e141b",
        "chrome_border": "#1c2530",
        "menubar_bg": "#0b0f14", "menubar_fg": "#cdd6df", "menubar_sel": "#17212b",
        "menu_bg": "#0e141b", "menu_border": "#24303c",
        "sel_bg": "#2fd6c3", "sel_fg": "#05201c",
        "text": "#e6edf3", "disabled_fg": "#4a5763",
        "tb_hover_bg": "#16222d", "tb_hover_border": "#2a3a49",
        "tb_pressed_bg": "#1b2b38", "tb_pressed_border": "#2fd6c3",
        "tb_checked_bg": "#0e2b2a", "tb_checked_border": "#2fd6c3", "tb_checked_fg": "#4be08a",
        "input_bg": "#0b0f14", "input_border": "#2a3a49",
        "pill_bg": "#16222d", "pill_fg": "#8fa3b3",
        "dock_title_bg": "#0b0f14", "dock_title_fg": "#8fa3b3",
        "list_bg": "#0b0f14", "list_border": "#1c2530", "list_hover": "#121c25",
        "navheader_bg": "#0b0f14", "navheader_hover": "#121c25", "navarrow": "#6b7d8c",
        "navtitle": "#9fb0bf", "navsection_bg": "#0e141b",
        "navsection_border": "#1c2530", "navbody_bg": "#0b0f14",
        "splitter": "#1c2530", "splitter_hover": "#2fd6c3",
        "btn_bg": "#0e141b", "btn_border": "#2a3a49",
        "btn_hover_bg": "#16222d", "btn_hover_border": "#365062", "btn_pressed": "#1b2b38",
        "btn_disabled_fg": "#4a5763", "btn_disabled_bg": "#0b0f14",
        "status_bg": "#0b0f14", "status_fg": "#7d8b99",
        "tip_bg": "#0b0f14", "tip_fg": "#e6edf3", "tip_border": "#2fd6c3",
    },
}
DEFAULT_THEME = "hc_light"


def theme_keys() -> list[str]:
    return list(THEMES.keys())


def size_keys() -> list[str]:
    return list(SIZE_SCALES.keys())


def resolve_theme(key: str | None) -> str:
    return key if key in THEMES else DEFAULT_THEME


def resolve_size(key: str | None) -> str:
    return key if key in SIZE_SCALES else DEFAULT_SIZE


# ── Stylesheet builder ───────────────────────────────────────────────────────

def build_stylesheet(theme_key: str, size_key: str, font_family: str | None = None) -> str:
    t = THEMES[resolve_theme(theme_key)]
    s = SIZE_SCALES[resolve_size(size_key)]
    fam = font_family or FONT_FAMILY_FALLBACK

    base = s["base"]
    s2 = max(12, base - 2)     # secondary text (status bar, dock titles)
    s3 = max(11, base - 3)     # micro labels (pills) — never below 11px
    rad = t["radius"]
    pad = s["pad"]

    return f"""
        * {{ font-family: {fam}; }}

        QMainWindow, QDialog, QWidget {{ color: {t['text']}; }}
        QMainWindow {{ background: {t['window']}; }}
        QAbstractScrollArea {{ background: {t['window']}; }}

        QMenuBar {{
            background: {t['menubar_bg']};
            color: {t['menubar_fg']};
            padding: {pad // 2}px {pad}px;
            font-size: {base}px;
            border-bottom: 1px solid {t['chrome_border']};
        }}
        QMenuBar::item {{ padding: {pad // 2 + 1}px {pad + 4}px; border-radius: {rad}px; }}
        QMenuBar::item:selected {{ background: {t['menubar_sel']}; }}

        QMenu {{
            background: {t['menu_bg']};
            color: {t['text']};
            border: 1px solid {t['menu_border']};
            font-size: {base}px;
            padding: 4px 0;
        }}
        QMenu::item {{ padding: {pad}px {pad + 20}px {pad}px {pad + 16}px; }}
        QMenu::item:selected {{ background: {t['sel_bg']}; color: {t['sel_fg']}; }}
        QMenu::item:disabled {{ color: {t['disabled_fg']}; }}
        QMenu::separator {{ height: 1px; background: {t['chrome_border']}; margin: 3px 8px; }}
        QMenu::indicator {{ width: {base}px; height: {base}px; }}

        QToolBar {{
            background: {t['chrome']};
            border: none;
            border-bottom: 1px solid {t['chrome_border']};
            spacing: 2px;
            padding: {pad // 2}px {pad}px;
        }}
        QToolBar::separator {{ width: 1px; background: {t['chrome_border']}; margin: 4px 4px; }}

        QToolButton {{
            background: transparent;
            border: 1px solid transparent;
            border-radius: {rad}px;
            padding: {pad // 2}px {pad}px;
            font-size: {base}px;
            color: {t['text']};
        }}
        QToolButton:hover {{ background: {t['tb_hover_bg']}; border-color: {t['tb_hover_border']}; }}
        QToolButton:pressed {{ background: {t['tb_pressed_bg']}; border-color: {t['tb_pressed_border']}; }}
        QToolButton:checked {{
            background: {t['tb_checked_bg']};
            border-color: {t['tb_checked_border']};
            color: {t['tb_checked_fg']};
            font-weight: bold;
        }}
        QToolButton:disabled {{ color: {t['disabled_fg']}; }}
        QToolButton::menu-button {{
            border-left: 1px solid {t['chrome_border']};
            border-radius: 0 {rad}px {rad}px 0;
            width: {max(16, base)}px;
        }}

        QLineEdit {{
            border: 1px solid {t['input_border']};
            border-radius: {rad}px;
            padding: {pad // 2 + 1}px {pad}px;
            background: {t['input_bg']};
            color: {t['text']};
            font-size: {base}px;
            selection-background-color: {t['sel_bg']};
            selection-color: {t['sel_fg']};
        }}
        QLineEdit:focus {{ border-color: {t['sel_bg']}; }}

        QComboBox {{
            border: 1px solid {t['input_border']};
            border-radius: {rad}px;
            padding: {pad // 2}px {pad}px;
            background: {t['input_bg']};
            color: {t['text']};
            font-size: {base}px;
        }}
        QComboBox:focus {{ border-color: {t['sel_bg']}; }}
        QComboBox::drop-down {{ border: none; width: {base + 6}px; }}
        QComboBox QAbstractItemView {{
            background: {t['menu_bg']};
            color: {t['text']};
            border: 1px solid {t['menu_border']};
            selection-background-color: {t['sel_bg']};
            selection-color: {t['sel_fg']};
            font-size: {base}px;
        }}

        QLabel#SectionPill {{
            background: {t['pill_bg']};
            color: {t['pill_fg']};
            font-size: {s3}px;
            font-weight: bold;
            letter-spacing: 0.8px;
            border-radius: {rad}px;
            padding: 2px 6px;
        }}

        QDockWidget::title {{
            background: {t['dock_title_bg']};
            color: {t['dock_title_fg']};
            padding: {pad // 2 + 1}px 8px;
            font-size: {s2}px;
            font-weight: bold;
        }}

        QListWidget {{
            border: 1px solid {t['list_border']};
            background: {t['list_bg']};
            color: {t['text']};
            font-size: {base}px;
            outline: none;
        }}
        QListWidget::item {{ padding: {pad // 2}px {pad}px; }}
        QListWidget::item:selected {{ background: {t['sel_bg']}; color: {t['sel_fg']}; }}
        QListWidget::item:hover:!selected {{ background: {t['list_hover']}; }}

        QTreeWidget, QTreeView {{
            background: {t['list_bg']};
            color: {t['text']};
            border: 1px solid {t['list_border']};
            font-size: {base}px;
            outline: none;
        }}
        QTreeView::item:selected {{ background: {t['sel_bg']}; color: {t['sel_fg']}; }}
        QTreeView::item:hover:!selected {{ background: {t['list_hover']}; }}

        QLabel#SectionLabel {{
            color: {t['navarrow']};
            font-size: {s3}px;
            font-weight: bold;
            letter-spacing: 0.8px;
            padding: 4px 2px 2px 2px;
        }}

        QWidget#NavSectionHeader {{ background: {t['navheader_bg']}; border-top: 1px solid {t['navsection_border']}; }}
        QWidget#NavSectionHeader:hover {{ background: {t['navheader_hover']}; }}
        QLabel#NavArrow {{ color: {t['navarrow']}; font-size: {s3}px; font-weight: bold; }}
        QLabel#NavIcon  {{ color: {t['navtitle']}; font-size: {base}px; }}
        QLabel#NavTitle {{ color: {t['navtitle']}; font-size: {s3}px; font-weight: bold; letter-spacing: 0.7px; }}
        QWidget#NavSection {{ background: {t['navsection_bg']}; border-bottom: 1px solid {t['navsection_border']}; }}
        QWidget#NavSectionBody {{ background: {t['navbody_bg']}; }}

        QSplitter#NavSplitter::handle {{ background: {t['splitter']}; height: 3px; }}
        QSplitter#NavSplitter::handle:hover {{ background: {t['splitter_hover']}; }}

        QScrollArea#NavScrollArea {{ background: transparent; border: none; }}

        QPushButton {{
            background: {t['btn_bg']};
            border: 1px solid {t['btn_border']};
            border-radius: {rad}px;
            padding: {pad // 2 + 1}px {pad + 2}px;
            font-size: {base}px;
            color: {t['text']};
        }}
        QPushButton:hover {{ background: {t['btn_hover_bg']}; border-color: {t['btn_hover_border']}; }}
        QPushButton:pressed {{ background: {t['btn_pressed']}; }}
        QPushButton:disabled {{ color: {t['btn_disabled_fg']}; background: {t['btn_disabled_bg']}; }}

        QCheckBox, QRadioButton {{ color: {t['text']}; font-size: {base}px; spacing: 8px; }}
        QCheckBox::indicator, QRadioButton::indicator {{ width: {base}px; height: {base}px; }}

        QStatusBar {{
            background: {t['status_bg']};
            color: {t['status_fg']};
            font-size: {s2}px;
            padding: 2px 8px;
        }}
        QStatusBar::item {{ border: none; }}

        QToolTip {{
            background: {t['tip_bg']};
            color: {t['tip_fg']};
            border: 1px solid {t['tip_border']};
            padding: 4px 8px;
            font-size: {s2}px;
        }}

        QMessageBox, QInputDialog {{ background: {t['chrome']}; }}
        QMessageBox QLabel, QInputDialog QLabel {{
            color: {t['text']};
            font-size: {base}px;
        }}
    """


def tint_icon(icon, color_hex: str, size: int = 24):
    """Return a copy of *icon* recoloured to a solid *color_hex*.

    Preserves the icon's shape (alpha) and replaces its colour — used to make
    dark monochrome toolbar glyphs legible on dark themes. Returns the original
    icon unchanged if it has no usable pixmap.
    """
    from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
    from PyQt6.QtCore import QSize, Qt

    src = icon.pixmap(QSize(size, size))
    if src.isNull():
        return icon
    tinted = QPixmap(src.size())
    tinted.fill(Qt.GlobalColor.transparent)
    p = QPainter(tinted)
    p.drawPixmap(0, 0, src)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    p.fillRect(tinted.rect(), QColor(color_hex))
    p.end()
    return QIcon(tinted)


def app_font(size_key: str, family: str | None = None) -> QFont:
    """QFont for QApplication so unstyled dialogs also pick up family + scale."""
    s = SIZE_SCALES[resolve_size(size_key)]
    f = QFont(family or "Atkinson Hyperlegible")
    f.setPointSize(s["app_pt"])
    return f
