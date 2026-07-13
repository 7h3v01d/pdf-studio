"""
pdf_reader_ui.py
----------------
UI layout, menu bar, toolbars, sidebar, shortcuts, and styles.
All logic is implemented in the derived PDFReader class (pdf_reader_app.py).
"""
import sys
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel,
    QToolBar, QLineEdit, QStatusBar, QComboBox, QDockWidget,
    QListWidget, QMenu, QMenuBar, QSizePolicy, QToolButton, QHBoxLayout,
    QFrame, QMessageBox, QSplitter, QScrollArea, QApplication)
from PyQt6.QtGui import QIcon, QShortcut, QKeySequence, QAction, QActionGroup, QFont
from PyQt6.QtCore import Qt, QSize, QSettings
from pdf_scroll_area import PDFScrollArea

from about_dialog import APP_NAME, AboutDialog
import themes
from merge_split_dialog import MergeSplitDialog
from annotations_panel import AnnotationsPanel

SINGLE_PAGE = 0
CONTINUOUS  = 1

_NAV_SECTION_KEY = "nav_panel/sections"


class _NavHeader(QWidget):
    """Header bar that captures clicks anywhere across its full width,
    including on child label widgets."""

    def __init__(self, on_click, parent=None):
        super().__init__(parent)
        self._on_click = on_click
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(26)
        self.setObjectName("NavSectionHeader")

    def mousePressEvent(self, event):
        self._on_click()
        event.accept()


class NavSection(QWidget):
    """
    A collapsible sidebar section with a clickable header and a body widget.

    The header shows an expand/collapse arrow, an emoji icon, and a title.
    Clicking anywhere on the header (including the labels) toggles collapse.
    Collapsed state persists via QSettings.
    """

    HEADER_H     = 26   # fixed header height in pixels
    EXPANDED_MIN = 80   # minimum height when open — prevents splitter trapping
    EXPAND_SHARE = 150  # default pixels claimed when expanding

    def __init__(self, icon: str, title: str, body: QWidget,
                 settings_key: str, parent=None):
        super().__init__(parent)
        self._settings_key = settings_key
        self._body = body
        self._collapsed = False
        # Remember the last expanded size so we can restore it on re-expand
        self._last_expanded_size = self.EXPAND_SHARE

        self.setObjectName("NavSection")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header (proper subclass so all child clicks bubble up) ────────
        self._header = _NavHeader(self.toggle, self)

        hl = QHBoxLayout(self._header)
        hl.setContentsMargins(6, 0, 6, 0)
        hl.setSpacing(5)

        self._arrow = QLabel("▾")
        self._arrow.setObjectName("NavArrow")
        self._arrow.setFixedWidth(12)
        self._arrow.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        icon_lbl = QLabel(icon)
        icon_lbl.setObjectName("NavIcon")
        icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("NavTitle")
        title_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        hl.addWidget(self._arrow)
        hl.addWidget(icon_lbl)
        hl.addWidget(title_lbl)
        hl.addStretch()

        root.addWidget(self._header)
        root.addWidget(self._body)

        # Collapsed state is restored in _post_splitter_init() AFTER the
        # widget is parented to the splitter, so _repack_splitter() works.

    # ── Public ────────────────────────────────────────────────────────────

    def post_splitter_init(self):
        """Call once after all NavSections have been added to the splitter."""
        settings = QSettings("LeonPriest", "PDFStudio")
        if settings.value(self._settings_key, False, type=bool):
            self._apply_collapsed(True, save=False)

    def toggle(self):
        # Snapshot current size before collapsing so we can restore it
        splitter = self.parent()
        if isinstance(splitter, QSplitter):
            idx = splitter.indexOf(self)
            if idx >= 0:
                sz = splitter.sizes()[idx]
                if sz > self.HEADER_H:
                    self._last_expanded_size = sz
        self._apply_collapsed(not self._collapsed)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def body(self) -> QWidget:
        return self._body

    # ── Internal ──────────────────────────────────────────────────────────

    def _apply_collapsed(self, collapsed: bool, save: bool = True):
        self._collapsed = collapsed
        self._body.setVisible(not collapsed)
        self._arrow.setText("▸" if collapsed else "▾")

        if save:
            settings = QSettings("LeonPriest", "PDFStudio")
            settings.setValue(self._settings_key, collapsed)

        self._repack_splitter()

    def _repack_splitter(self):
        """Redistribute splitter sizes cleanly after a collapse or expand."""
        splitter = self.parent()
        if not isinstance(splitter, QSplitter):
            return
        idx = splitter.indexOf(self)
        if idx < 0:
            return

        n = splitter.count()
        current = list(splitter.sizes())

        # Total available height (sum of all sections = splitter content height)
        total = sum(current)
        if total <= 0:
            return

        def is_open(i):
            w = splitter.widget(i)
            return isinstance(w, NavSection) and not w.is_collapsed()

        if self._collapsed:
            # ── Collapsing ────────────────────────────────────────────────
            # freed is always non-negative: clamp so we never donate negative px
            freed = max(0, current[idx] - self.HEADER_H)
            current[idx] = self.HEADER_H

            # Give freed space to the nearest open neighbour
            # Prefer the one below, fall back to the one above
            donated = False
            for i in range(idx + 1, n):
                if is_open(i):
                    current[i] += freed
                    donated = True
                    break
            if not donated:
                for i in range(idx - 1, -1, -1):
                    if is_open(i):
                        current[i] += freed
                        donated = True
                        break
            # If ALL others are also collapsed, the freed space just disappears
            # (the splitter will have dead space at the bottom — acceptable).

        else:
            # ── Expanding ─────────────────────────────────────────────────
            # How much space to claim: restore last known size, clamped to
            # what's actually available from open neighbours.
            open_others = [i for i in range(n) if i != idx and is_open(i)]

            available_from_others = sum(current[i] for i in open_others)
            # Never steal more than leaves each open neighbour with EXPANDED_MIN
            max_steal = sum(
                max(0, current[i] - self.EXPANDED_MIN) for i in open_others
            )
            want = max(self.EXPANDED_MIN,
                       min(self._last_expanded_size, max_steal))

            if want > 0 and open_others:
                # Take proportionally from open neighbours
                steal_total = sum(current[i] for i in open_others)
                for i in open_others:
                    share = current[i] / steal_total if steal_total else 0
                    current[i] = max(self.EXPANDED_MIN,
                                     current[i] - int(want * share))
            current[idx] = want

        splitter.setSizes(current)

    def minimumSizeHint(self):
        if self._collapsed:
            return QSize(0, self.HEADER_H)
        return QSize(0, self.HEADER_H + self.EXPANDED_MIN)

    def sizeHint(self):
        if self._collapsed:
            return QSize(200, self.HEADER_H)
        return QSize(200, self._last_expanded_size)


class PDFReaderUI(QMainWindow):
    SINGLE_PAGE = SINGLE_PAGE
    CONTINUOUS  = CONTINUOUS

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setGeometry(100, 100, 1100, 740)
        self.setMinimumSize(800, 500)

        # ── All button / control declarations ──────────────────────────────
        # Open (split button: left=open dialog, arrow=recent)
        self.open_button = QToolButton()
        self.open_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)

        # Navigation
        self.prev_button  = QToolButton()
        self.next_button  = QToolButton()
        self.page_input   = QLineEdit()
        self.page_label   = QLabel("/ 0")

        # Zoom
        self.zoom_out_button       = QToolButton()
        self.zoom_combo            = QComboBox()
        self.zoom_in_button        = QToolButton()
        self.zoom_fit_width_button = QToolButton()
        self.zoom_fit_page_button  = QToolButton()

        # Search (inline in toolbar — no separate search button)
        self.search_input       = QLineEdit()
        self.prev_search_button = QToolButton()
        self.next_search_button = QToolButton()

        # Other toolbar actions
        self.save_button       = QToolButton()
        self.print_button      = QToolButton()
        self.rotate_button     = QToolButton()
        self.fullscreen_button = QToolButton()

        # Markup
        self.annotate_button      = QToolButton()
        self.highlight_button     = QToolButton()
        self.underline_button     = QToolButton()
        self.strikethrough_button = QToolButton()
        self.freehand_button      = QToolButton()
        self.eraser_button        = QToolButton()
        self.markup_color_button  = QToolButton()
        self.signature_button     = QToolButton()
        self.stamp_button         = QToolButton()
        self.redact_button        = QToolButton()

        # Legacy compat: logic in pdf_reader_app.py references these
        self.view_mode_button   = QPushButton("Continuous")
        self.dark_mode_button   = QPushButton("Dark Mode")
        self.save_as_button     = QPushButton("Save As")
        self.properties_button  = QPushButton("Properties")
        self.add_page_button    = QPushButton()
        self.remove_page_button = QPushButton()
        self.move_up_button     = QPushButton()
        self.move_down_button   = QPushButton()
        self.search_button      = QPushButton()   # kept for compat

        # Sidebar
        self.thumbnail_list  = QListWidget()
        self.toc_list        = QListWidget()
        self.bookmark_list   = QListWidget()
        self.annot_panel     = AnnotationsPanel()

        # Status
        self.status_bar = QStatusBar()

        self._setup_menu_bar()
        self._setup_main_toolbar()
        self._setup_markup_toolbar()
        self._setup_sidebar()
        self._setup_viewport()
        self._wire_signals()
        self._setup_shortcuts()
        self._apply_styles()
        self._set_initial_state()

    # =========================================================================
    # Menu bar
    # =========================================================================

    def _setup_menu_bar(self):
        mb = self.menuBar()

        # ── File ─────────────────────────────────────────────────────────
        file_menu = mb.addMenu("&File")
        self._act_open    = QAction("&Open…",     self)
        self._act_save    = QAction("&Save",       self)
        self._act_save_as = QAction("Save &As…",  self)
        self._act_print   = QAction("&Print…",    self)
        self._act_preview = QAction("Print Pre&view…", self)
        self._act_props   = QAction("&Properties",self)
        self._act_quit    = QAction("&Quit",       self)
        self._act_save_copy = QAction("Save a &Copy…", self)
        self._act_open.setIcon(QIcon.fromTheme("document-open"))
        self._act_save.setIcon(QIcon.fromTheme("document-save"))
        self._act_save_as.setIcon(QIcon.fromTheme("document-save-as"))
        self._act_save_copy.setIcon(QIcon.fromTheme("document-save-as"))
        self._act_print.setIcon(QIcon.fromTheme("document-print"))
        self._act_props.setIcon(QIcon.fromTheme("document-properties"))
        self._act_quit.setShortcut("Ctrl+Q")
        file_menu.addAction(self._act_open)
        file_menu.addSeparator()
        file_menu.addAction(self._act_save)
        file_menu.addAction(self._act_save_as)
        file_menu.addAction(self._act_save_copy)
        file_menu.addSeparator()
        # Export As submenu — actions defined after Tools menu below
        self._export_menu = file_menu.addMenu("📤  Export &As")
        file_menu.addSeparator()
        file_menu.addAction(self._act_preview)
        file_menu.addAction(self._act_print)
        file_menu.addAction(self._act_props)
        file_menu.addSeparator()
        if sys.platform == "win32":
            self._act_setdefault = QAction("Set as Default PDF App…", self)
            self._act_setdefault.triggered.connect(self._set_default_pdf_app)
            file_menu.addAction(self._act_setdefault)
            file_menu.addSeparator()
        file_menu.addAction(self._act_quit)

        # ── Edit ─────────────────────────────────────────────────────────
        edit_menu = mb.addMenu("&Edit")
        self._act_undo          = QAction("&Undo",              self)
        self._act_redo          = QAction("&Redo",              self)
        self._act_copy_text     = QAction("&Copy Selected Text", self)
        self._act_select_all    = QAction("Select &All Text on Page", self)
        self._act_find          = QAction("&Find…",             self)
        self._act_find_next     = QAction("Find &Next",         self)
        self._act_find_prev     = QAction("Find &Previous",     self)
        self._act_undo.setShortcut("Ctrl+Z")
        self._act_redo.setShortcut("Ctrl+Y")
        self._act_copy_text.setShortcut("Ctrl+C")
        self._act_find.setShortcut("Ctrl+F")
        self._act_find_next.setShortcut("F3")
        self._act_find_prev.setShortcut("Shift+F3")
        self._act_undo.setIcon(QIcon.fromTheme("edit-undo"))
        self._act_redo.setIcon(QIcon.fromTheme("edit-redo"))
        self._act_copy_text.setIcon(QIcon.fromTheme("edit-copy"))
        self._act_find.setIcon(QIcon.fromTheme("edit-find"))
        edit_menu.addAction(self._act_undo)
        edit_menu.addAction(self._act_redo)
        edit_menu.addSeparator()
        edit_menu.addAction(self._act_copy_text)
        edit_menu.addAction(self._act_select_all)
        edit_menu.addSeparator()
        edit_menu.addAction(self._act_find)
        edit_menu.addAction(self._act_find_next)
        edit_menu.addAction(self._act_find_prev)

        # ── View ─────────────────────────────────────────────────────────
        view_menu = mb.addMenu("&View")
        self._act_toggle_view = QAction("&Continuous Scroll", self, checkable=True)
        self._act_dark_mode   = QAction("&Dark Background",   self, checkable=True)
        self._act_fullscreen  = QAction("&Full Screen",       self, checkable=True)
        self._act_sidebar     = QAction("&Navigation Panel",  self, checkable=True, checked=True)
        self._act_fit_width   = QAction("Fit &Width",         self)
        self._act_fit_page    = QAction("Fit &Page",          self)
        self._act_zoom_in     = QAction("Zoom &In",           self)
        self._act_zoom_out    = QAction("Zoom &Out",          self)
        self._act_rotate      = QAction("&Rotate 90°",        self)
        view_menu.addAction(self._act_toggle_view)
        view_menu.addAction(self._act_dark_mode)
        view_menu.addAction(self._act_fullscreen)
        view_menu.addAction(self._act_sidebar)
        view_menu.addSeparator()
        view_menu.addAction(self._act_fit_width)
        view_menu.addAction(self._act_fit_page)
        view_menu.addSeparator()
        view_menu.addAction(self._act_zoom_in)
        view_menu.addAction(self._act_zoom_out)
        view_menu.addAction(self._act_rotate)

        # ── Appearance (themes + text size) ──────────────────────────────
        view_menu.addSeparator()
        if not hasattr(self, "ui_theme"):
            self._load_appearance_prefs()
        appearance = view_menu.addMenu("&Appearance")

        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        self._theme_actions = {}
        for key in themes.theme_keys():
            act = QAction(themes.THEMES[key]["label"], self, checkable=True)
            act.setChecked(key == self.ui_theme)
            act.triggered.connect(lambda _=False, k=key: self.set_theme(k))
            theme_group.addAction(act)
            appearance.addAction(act)
            self._theme_actions[key] = act

        appearance.addSeparator()
        size_header = QAction("Text Size", self)
        size_header.setEnabled(False)
        appearance.addAction(size_header)

        size_group = QActionGroup(self)
        size_group.setExclusive(True)
        self._size_actions = {}
        for key in themes.size_keys():
            act = QAction(themes.SIZE_SCALES[key]["label"], self, checkable=True)
            act.setChecked(key == self.ui_size)
            act.triggered.connect(lambda _=False, k=key: self.set_ui_size(k))
            size_group.addAction(act)
            appearance.addAction(act)
            self._size_actions[key] = act

        # ── Pages ────────────────────────────────────────────────────────
        pages_menu = mb.addMenu("&Pages")
        self._act_add_page    = QAction("&Insert Blank Page", self)
        self._act_remove_page = QAction("&Delete Page",       self)
        self._act_move_up     = QAction("Move Page &Up",      self)
        self._act_move_down   = QAction("Move Page &Down",    self)
        self._act_bookmark    = QAction("Add &Bookmark",      self)
        self._act_add_page.setIcon(QIcon.fromTheme("list-add"))
        self._act_remove_page.setIcon(QIcon.fromTheme("list-remove"))
        self._act_move_up.setIcon(QIcon.fromTheme("go-up"))
        self._act_move_down.setIcon(QIcon.fromTheme("go-down"))
        pages_menu.addAction(self._act_add_page)
        pages_menu.addAction(self._act_remove_page)
        pages_menu.addSeparator()
        pages_menu.addAction(self._act_move_up)
        pages_menu.addAction(self._act_move_down)
        pages_menu.addSeparator()
        pages_menu.addAction(self._act_bookmark)

        # ── Tools ────────────────────────────────────────────────────────
        tools_menu = mb.addMenu("&Tools")
        self._act_merge_split   = QAction("&Merge / Split PDFs…",    self)
        self._act_password      = QAction("&Password Protect…",      self)
        self._act_extract_pages = QAction("&Extract Pages…",         self)
        self._act_apply_redact  = QAction("Apply &Redactions",       self)
        self._act_reset_form    = QAction("&Reset Form Fields",      self)
        self._act_ocr           = QAction("🔍  Run &OCR…",           self)
        self._act_merge_split.setIcon(QIcon.fromTheme("document-new"))
        self._act_extract_pages.setIcon(QIcon.fromTheme("document-save"))
        self._act_apply_redact.setIcon(QIcon.fromTheme("edit-delete"))
        tools_menu.addAction(self._act_merge_split)
        tools_menu.addAction(self._act_extract_pages)
        tools_menu.addAction(self._act_password)
        tools_menu.addSeparator()
        tools_menu.addAction(self._act_apply_redact)
        tools_menu.addSeparator()
        tools_menu.addAction(self._act_reset_form)
        tools_menu.addSeparator()
        tools_menu.addAction(self._act_ocr)

        # ── File → Export As submenu ──────────────────────────────────────
        # (inserted into File menu after it's built — we patch it below)
        self._act_export_docx = QAction("Microsoft &Word (.docx)…",  self)
        self._act_export_xlsx = QAction("Microsoft &Excel (.xlsx)…", self)

        # Populate Export As submenu (actions declared above in Tools block)
        self._export_menu.addAction(self._act_export_docx)
        self._export_menu.addAction(self._act_export_xlsx)

        # ── Help ─────────────────────────────────────────────────────────
        help_menu = mb.addMenu("&Help")
        self._act_about     = QAction(f"&About {APP_NAME}", self)
        self._act_shortcuts = QAction("Keyboard &Shortcuts", self)
        help_menu.addAction(self._act_about)
        help_menu.addSeparator()
        help_menu.addAction(self._act_shortcuts)

    # =========================================================================
    # Main toolbar
    # =========================================================================

    def _setup_main_toolbar(self):
        tb = QToolBar("Main")
        tb.setIconSize(QSize(18, 18))
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)
        tb.setObjectName("MainToolBar")
        self.main_toolbar = tb

        # Open split-button
        self.open_button.setIcon(QIcon.fromTheme("document-open"))
        self.open_button.setText(" Open")
        self.open_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.open_button.setToolTip("Open PDF  (Ctrl+O)\nArrow ▾ → recent files")
        self.open_button.setAutoRaise(True)
        tb.addWidget(self.open_button)

        self._tb_btn(tb, self.save_button,  "document-save",  "Save  (Ctrl+S)",  "Save")
        self._tb_btn(tb, self.print_button, "document-print", "Print  (Ctrl+P)", "Print")

        tb.addSeparator()

        # Navigation
        self._tb_btn(tb, self.prev_button, "go-previous", "Previous Page  (←)", "Prev")
        self.page_input.setFixedWidth(46)
        self.page_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_input.setPlaceholderText("1")
        tb.addWidget(self.page_input)
        self.page_label.setContentsMargins(2, 0, 4, 0)
        tb.addWidget(self.page_label)
        self._tb_btn(tb, self.next_button, "go-next", "Next Page  (→)", "Next")

        tb.addSeparator()

        # Zoom
        self._tb_btn(tb, self.zoom_out_button, "zoom-out", "Zoom Out  (Ctrl+-)", "Zoom −")
        self.zoom_combo.addItems(["25%","50%","75%","100%","125%","150%","200%","300%","400%"])
        self.zoom_combo.setCurrentText("100%")
        self.zoom_combo.setFixedWidth(80)
        tb.addWidget(self.zoom_combo)
        self._tb_btn(tb, self.zoom_in_button, "zoom-in", "Zoom In  (Ctrl++)", "Zoom +")

        self.zoom_fit_width_button.setText("Fit W")
        self.zoom_fit_width_button.setToolTip("Fit Width  (Ctrl+Shift+H)")
        self.zoom_fit_width_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.zoom_fit_width_button.setAutoRaise(True)
        tb.addWidget(self.zoom_fit_width_button)

        self.zoom_fit_page_button.setText("Fit Pg")
        self.zoom_fit_page_button.setToolTip("Fit Page  (Ctrl+Shift+F)")
        self.zoom_fit_page_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.zoom_fit_page_button.setAutoRaise(True)
        tb.addWidget(self.zoom_fit_page_button)

        tb.addSeparator()

        self._tb_btn(tb, self.rotate_button,    "image-rotate",   "Rotate 90°  (Ctrl+R)", "Rotate")
        self._tb_btn(tb, self.fullscreen_button, "view-fullscreen","Full Screen  (F11)", "Full")

        tb.addSeparator()

        # Search (inline)
        self.search_input.setFixedWidth(170)
        self.search_input.setPlaceholderText("🔍  Search…")
        self.search_input.setClearButtonEnabled(True)
        tb.addWidget(self.search_input)
        self._tb_btn(tb, self.prev_search_button, "go-previous", "Previous Result", "Prev")
        self._tb_btn(tb, self.next_search_button, "go-next",     "Next Result", "Next")

        self.setStatusBar(self.status_bar)

    @staticmethod
    def _tb_btn(tb, btn, icon_name, tip, label=""):
        btn.setIcon(QIcon.fromTheme(icon_name))
        if label:
            # A visible text label keeps the button usable even when the
            # platform has no icon theme (e.g. Windows), and doubles as a
            # low-vision aid. Toolbar-wide style/size is set in _apply_styles.
            btn.setText(label)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setToolTip(tip)
        btn.setAutoRaise(True)
        tb.addWidget(btn)

    # =========================================================================
    # Markup toolbar
    # =========================================================================

    def _setup_markup_toolbar(self):
        tb = QToolBar("Markup & Sign")
        tb.setIconSize(QSize(14, 14))
        tb.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)
        tb.setObjectName("MarkupToolBar")
        self.markup_toolbar = tb

        def _mk(btn, label, tip, checkable=True):
            btn.setText(label)
            btn.setToolTip(tip)
            btn.setCheckable(checkable)
            btn.setAutoRaise(True)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            tb.addWidget(btn)

        _pill(tb, "ANNOTATE")
        _mk(self.annotate_button,      "📌 Note",       "Sticky note")
        _mk(self.highlight_button,     "Highlight",     "Highlight text  (drag to select)")
        _mk(self.underline_button,     "Underline",     "Underline text")
        _mk(self.strikethrough_button, "Strikethrough", "Strikethrough text")
        _mk(self.freehand_button,      "✏ Draw",        "Freehand ink")
        _mk(self.eraser_button,        "Eraser",        "Erase nearby markup")

        # Colour swatch button
        self.markup_color_button.setText("  ◉  ")
        self.markup_color_button.setToolTip("Markup colour")
        self.markup_color_button.setAutoRaise(True)
        self.markup_color_button.setCheckable(False)
        self.markup_color_button.setStyleSheet(
            "QToolButton { background:#FFFF00; border:1px solid #aaa;"
            " border-radius:3px; min-width:26px; font-size:13px; padding:1px 4px; }")
        tb.addWidget(self.markup_color_button)

        tb.addSeparator()
        _pill(tb, "FILL & SIGN")
        _mk(self.signature_button, "✍ Signature", "Draw and place a signature")
        _mk(self.stamp_button,     "⬛ Stamp",      "Insert a text stamp", checkable=False)

        tb.addSeparator()
        _pill(tb, "REDACT")
        _mk(self.redact_button, "⬛ Redact", "Drag a box to mark text/area for redaction\nThen use Tools → Apply Redactions")

    # =========================================================================
    # Sidebar
    # =========================================================================

    def _setup_sidebar(self):
        self.sidebar = QDockWidget("Navigation", self)
        self.sidebar.setObjectName("NavDock")
        self.sidebar.setMinimumWidth(200)

        # ── Contents body ─────────────────────────────────────────────────
        self.toc_list.setMinimumHeight(40)

        # ── Bookmarks body ────────────────────────────────────────────────
        bm_body = QWidget()
        bm_body.setObjectName("NavSectionBody")
        bm_vl = QVBoxLayout(bm_body)
        bm_vl.setContentsMargins(4, 2, 4, 4)
        bm_vl.setSpacing(3)
        bm_row = QHBoxLayout()
        bm_row.setSpacing(4)
        self.add_bookmark_button    = QPushButton("+ Add")
        self.remove_bookmark_button = QPushButton("− Remove")
        self.add_bookmark_button.setFixedHeight(24)
        self.remove_bookmark_button.setFixedHeight(24)
        bm_row.addWidget(self.add_bookmark_button)
        bm_row.addWidget(self.remove_bookmark_button)
        bm_vl.addLayout(bm_row)
        self.bookmark_list.setMinimumHeight(40)
        bm_vl.addWidget(self.bookmark_list)

        # ── Thumbnails body ───────────────────────────────────────────────
        self.thumbnail_list.setIconSize(QSize(90, 120))
        self.thumbnail_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.thumbnail_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.thumbnail_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.thumbnail_list.setMinimumHeight(60)

        # ── NavSection wrappers ───────────────────────────────────────────
        self._nav_contents    = NavSection("📑", "CONTENTS",    self.toc_list,      "nav/contents")
        self._nav_bookmarks   = NavSection("🔖", "BOOKMARKS",   bm_body,            "nav/bookmarks")
        self._nav_annotations = NavSection("💬", "ANNOTATIONS", self.annot_panel,   "nav/annotations")
        self._nav_thumbnails  = NavSection("🖼", "THUMBNAILS",  self.thumbnail_list, "nav/thumbnails")

        # ── Splitter ──────────────────────────────────────────────────────
        self._nav_splitter = QSplitter(Qt.Orientation.Vertical)
        self._nav_splitter.setObjectName("NavSplitter")
        self._nav_splitter.setChildrenCollapsible(True)   # we manage sizes ourselves
        self._nav_splitter.addWidget(self._nav_contents)
        self._nav_splitter.addWidget(self._nav_bookmarks)
        self._nav_splitter.addWidget(self._nav_annotations)
        self._nav_splitter.addWidget(self._nav_thumbnails)

        # Default proportional sizes (pixels) — thumbnails gets the most space
        self._nav_splitter.setSizes([140, 130, 130, 300])

        # Now that all sections are parented to the splitter, restore collapsed
        # state — this must happen AFTER addWidget() so parent() is valid.
        for sec in (self._nav_contents, self._nav_bookmarks,
                    self._nav_annotations, self._nav_thumbnails):
            sec.post_splitter_init()

        # Restore saved splitter sizes (applied after collapse state so the
        # saved sizes correctly reflect collapsed=26 sections).
        settings = QSettings("LeonPriest", "PDFStudio")
        splitter_state = settings.value("nav/splitter_state")
        if splitter_state:
            self._nav_splitter.restoreState(splitter_state)

        # Splitter goes directly into the dock — no scroll wrapper,
        # which would break self.parent() in NavSection._repack_splitter()
        self.sidebar.setWidget(self._nav_splitter)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.sidebar)

    def _save_sidebar_state(self):
        """Persist splitter sizes — call from closeEvent."""
        settings = QSettings("LeonPriest", "PDFStudio")
        settings.setValue("nav/splitter_state", self._nav_splitter.saveState())

    # =========================================================================
    # PDF viewport
    # =========================================================================

    def _setup_viewport(self):
        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.layout = QVBoxLayout(self.main_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.pdf_container = QWidget()
        self.pdf_layout    = QVBoxLayout(self.pdf_container)
        self.pdf_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pdf_layout.setContentsMargins(0, 0, 0, 0)
        self.pdf_layout.setSpacing(10)

        self.scroll_area = PDFScrollArea(self)
        self.scroll_area.setWidget(self.pdf_container)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background-color: #f0f0f0;")
        self.layout.addWidget(self.scroll_area)

    # =========================================================================
    # Signal wiring
    # =========================================================================

    def _wire_signals(self):
        # Menu actions
        # Edit menu
        self._act_undo.triggered.connect(self.undo)
        self._act_redo.triggered.connect(self.redo)
        self._act_copy_text.triggered.connect(self.copy_selected_text)
        self._act_select_all.triggered.connect(self._select_all_text_on_page)
        self._act_find.triggered.connect(self.focus_search)
        self._act_find_next.triggered.connect(self.next_search_result)
        self._act_find_prev.triggered.connect(self.prev_search_result)

        self._act_open.triggered.connect(self.open_pdf)
        self._act_save.triggered.connect(self.save_pdf)
        self._act_save_as.triggered.connect(self.save_pdf_as)
        self._act_save_copy.triggered.connect(self.save_a_copy)
        self._act_print.triggered.connect(self.print_pdf)
        self._act_preview.triggered.connect(self.print_preview)
        self._act_props.triggered.connect(self.show_metadata)
        self._act_quit.triggered.connect(self.close)
        self._act_toggle_view.triggered.connect(self.toggle_view_mode)
        self._act_dark_mode.triggered.connect(self.toggle_dark_mode)
        self._act_fullscreen.triggered.connect(self.toggle_fullscreen)
        self._act_sidebar.triggered.connect(
            lambda checked: self.sidebar.setVisible(checked))
        self._act_fit_width.triggered.connect(self.set_zoom_fit_width)
        self._act_fit_page.triggered.connect(self.set_zoom_fit_page)
        self._act_zoom_in.triggered.connect(self.zoom_in)
        self._act_zoom_out.triggered.connect(self.zoom_out)
        self._act_rotate.triggered.connect(self.rotate_page)
        self._act_add_page.triggered.connect(self.add_page_action)
        self._act_remove_page.triggered.connect(self.remove_page_action)
        self._act_move_up.triggered.connect(self.move_page_up_action)
        self._act_move_down.triggered.connect(self.move_page_down_action)
        self._act_bookmark.triggered.connect(self.add_bookmark)
        self._act_merge_split.triggered.connect(self._show_merge_split)
        self._act_password.triggered.connect(self.show_password_dialog)
        self._act_extract_pages.triggered.connect(self._show_extract_pages)
        self._act_apply_redact.triggered.connect(self.apply_redactions)
        self._act_reset_form.triggered.connect(self.reset_form)
        self._act_about.triggered.connect(self._show_about)
        self._act_shortcuts.triggered.connect(self._show_shortcuts_help)
        self._act_ocr.triggered.connect(self._show_ocr)
        self._act_export_docx.triggered.connect(
            lambda: self._show_export("docx"))
        self._act_export_xlsx.triggered.connect(
            lambda: self._show_export("xlsx"))

        # Main toolbar
        self.open_button.clicked.connect(self.open_pdf)
        self.save_button.clicked.connect(self.save_pdf)
        self.print_button.clicked.connect(self.print_pdf)
        self.prev_button.clicked.connect(self.prev_page)
        self.next_button.clicked.connect(self.next_page)
        self.page_input.returnPressed.connect(self.goto_page)
        self.zoom_out_button.clicked.connect(self.zoom_out)
        self.zoom_in_button.clicked.connect(self.zoom_in)
        self.zoom_combo.currentTextChanged.connect(self.change_zoom)
        self.zoom_fit_width_button.clicked.connect(self.set_zoom_fit_width)
        self.zoom_fit_page_button.clicked.connect(self.set_zoom_fit_page)
        self.rotate_button.clicked.connect(self.rotate_page)
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        self.search_input.returnPressed.connect(self.start_search)
        self.search_input.textChanged.connect(self._on_search_cleared)
        self.prev_search_button.clicked.connect(self.prev_search_result)
        self.next_search_button.clicked.connect(self.next_search_result)

        # Markup toolbar
        self.annotate_button.clicked.connect(self.toggle_annotation_mode)
        self.highlight_button.clicked.connect(
            lambda: self.set_markup_tool("highlight"))
        self.underline_button.clicked.connect(
            lambda: self.set_markup_tool("underline"))
        self.strikethrough_button.clicked.connect(
            lambda: self.set_markup_tool("strikethrough"))
        self.freehand_button.clicked.connect(
            lambda: self.set_markup_tool("freehand"))
        self.eraser_button.clicked.connect(
            lambda: self.set_markup_tool("eraser"))
        self.markup_color_button.clicked.connect(self.pick_markup_color)
        self.signature_button.clicked.connect(self.place_signature)
        self.stamp_button.clicked.connect(self.place_stamp)
        self.redact_button.clicked.connect(lambda: self.set_markup_tool("redact"))

        # Sidebar
        self.thumbnail_list.itemClicked.connect(self.thumbnail_clicked)
        self.toc_list.itemClicked.connect(self.toc_clicked)
        self.add_bookmark_button.clicked.connect(self.add_bookmark)
        self.remove_bookmark_button.clicked.connect(self.remove_bookmark)
        self.bookmark_list.itemDoubleClicked.connect(self.goto_bookmark)

        # Legacy compat (app logic calls these directly)
        self.view_mode_button.clicked.connect(self.toggle_view_mode)
        self.dark_mode_button.clicked.connect(self.toggle_dark_mode)
        self.save_as_button.clicked.connect(self.save_pdf_as)
        self.properties_button.clicked.connect(self.show_metadata)
        self.add_page_button.clicked.connect(self.add_page_action)
        self.remove_page_button.clicked.connect(self.remove_page_action)
        self.move_up_button.clicked.connect(self.move_page_up_action)
        self.move_down_button.clicked.connect(self.move_page_down_action)
        self.search_button.clicked.connect(self.start_search)

    def _on_search_cleared(self, text):
        if not text and hasattr(self, 'search_results'):
            self.search_results = []
            self.current_search_index = -1
            if hasattr(self, 'pdf_document') and self.pdf_document:
                self.update_view()

    # =========================================================================
    # Shortcuts
    # =========================================================================

    def _setup_shortcuts(self):
        # Undo/Redo shortcuts live on the Edit menu actions (setShortcut)
        # Additional aliases
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, self.redo)
        QShortcut(QKeySequence("F3"),           self, self.next_search_result)
        QShortcut(QKeySequence("Shift+F3"),     self, self.prev_search_result)
        QShortcut(QKeySequence("Ctrl+O"),       self, self.open_pdf)
        QShortcut(QKeySequence("Ctrl+S"),       self, self.save_pdf)
        QShortcut(QKeySequence("Ctrl+P"),       self, self.print_pdf)
        QShortcut(QKeySequence("Ctrl+Shift+P"), self, self.print_preview)
        QShortcut(QKeySequence("Ctrl+F"),       self, self.focus_search)
        QShortcut(QKeySequence("Ctrl+C"),       self, self.copy_selected_text)
        QShortcut(QKeySequence("Ctrl+B"),       self, self.add_bookmark)
        QShortcut(QKeySequence("Ctrl+R"),       self, self.rotate_page)
        QShortcut(QKeySequence("Ctrl++"),       self, self.zoom_in)
        QShortcut(QKeySequence("Ctrl+="),       self, self.zoom_in)
        QShortcut(QKeySequence("Ctrl+-"),       self, self.zoom_out)
        QShortcut(QKeySequence("Ctrl+Shift+H"), self, self.set_zoom_fit_width)
        QShortcut(QKeySequence("Ctrl+Shift+F"), self, self.set_zoom_fit_page)
        QShortcut(QKeySequence("F11"),          self, self.toggle_fullscreen)
        QShortcut(QKeySequence("F4"),           self,
                  lambda: self.sidebar.setVisible(not self.sidebar.isVisible()))
        QShortcut(QKeySequence("Left"),         self, self.prev_page)
        QShortcut(QKeySequence("Right"),        self, self.next_page)
        QShortcut(QKeySequence("Ctrl+Left"),    self, self.prev_page)
        QShortcut(QKeySequence("Ctrl+Right"),   self, self.next_page)
        QShortcut(QKeySequence("Ctrl+Home"),    self, self._go_first_page)
        QShortcut(QKeySequence("Ctrl+End"),     self, self._go_last_page)
        QShortcut(QKeySequence("Escape"),       self, self.clear_active_tool)

    def _go_first_page(self):
        if hasattr(self, 'pdf_document') and self.pdf_document:
            self.current_page = 0
            self.update_ui_on_page_change()

    def _go_last_page(self):
        if hasattr(self, 'pdf_document') and self.pdf_document:
            self.current_page = self.total_pages - 1
            self.update_ui_on_page_change()

    def _show_merge_split(self):
        from merge_split_dialog import MergeSplitDialog
        current = getattr(self, "pdf_file_path", "")
        dlg = MergeSplitDialog(current_pdf_path=current, parent=self)
        dlg.open_file_requested.connect(self._open_pdf_path)
        dlg.exec()

    def _show_extract_pages(self):
        if not hasattr(self, 'pdf_document') or not self.pdf_document:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Extract Pages", "Open a PDF first.")
            return
        from extract_pages_dialog import ExtractPagesDialog
        dlg = ExtractPagesDialog(self.pdf_document, self.pdf_file_path, parent=self)
        dlg.open_file_requested.connect(self._open_pdf_path)
        dlg.exec()

    def _show_about(self):
        dlg = AboutDialog(self)
        dlg.exec()

    def _set_default_pdf_app(self):
        """Register PDF Studio as a handler for PDF files, then open the
        Windows Default apps page so the user can confirm the default."""
        if sys.platform != "win32":
            QMessageBox.information(
                self, "Windows only",
                "Setting the default app is only available on Windows.")
            return
        try:
            import register_file_types as reg
            reg.register(pdf_only=False)
        except Exception as e:
            QMessageBox.warning(
                self, "Couldn't register",
                f"PDF Studio could not register file types:\n\n{e}")
            return
        QMessageBox.information(
            self, "Almost done",
            "PDF Studio has been added as an option for PDF (and Word/Excel) "
            "files.\n\n"
            "Windows will now open its 'Default apps' page. Set \"PDF Studio\" "
            "as the default for .pdf there — or right-click any PDF -> Open "
            "with -> choose PDF Studio and tick \"Always\".")
        try:
            import register_file_types as reg
            reg.open_default_apps_settings()
        except Exception:
            pass

    def _show_shortcuts_help(self):
        dlg = AboutDialog(self)
        # Jump straight to shortcuts tab (index 1)
        dlg.findChild(__import__("PyQt6.QtWidgets", fromlist=["QTabWidget"]).QTabWidget).setCurrentIndex(1)
        dlg.exec()

    # =========================================================================
    # Styles
    # =========================================================================

    # =========================================================================
    # Appearance: themes + text size (accessibility)
    # =========================================================================

    def _load_appearance_prefs(self):
        """Read persisted theme/size and install the bundled font (once)."""
        st = QSettings("LeonPriest", "PDFStudio")
        self.ui_theme = themes.resolve_theme(st.value("appearance/theme", themes.DEFAULT_THEME))
        self.ui_size  = themes.resolve_size(st.value("appearance/size",   themes.DEFAULT_SIZE))
        self.ui_font_family = themes.install_fonts()

    def _apply_styles(self):
        if not hasattr(self, "ui_theme"):
            self._load_appearance_prefs()

        # App-wide font so unstyled dialogs also scale + use the legible face.
        app = QApplication.instance()
        if app is not None:
            app.setFont(themes.app_font(self.ui_size, self.ui_font_family))

        self.setStyleSheet(
            themes.build_stylesheet(self.ui_theme, self.ui_size, self.ui_font_family)
        )
        self._apply_toolbar_scale()

    def _apply_toolbar_scale(self):
        """Scale toolbar icon sizes and show labels under icons."""
        icon_px = themes.SIZE_SCALES[self.ui_size]["icon"]
        for tb_name in ("main_toolbar", "markup_toolbar"):
            tb = getattr(self, tb_name, None)
            if tb is None:
                continue
            tb.setIconSize(QSize(icon_px, icon_px))
        # Main toolbar buttons: labels under icons so they read + click easily.
        if getattr(self, "main_toolbar", None) is not None:
            from PyQt6.QtWidgets import QToolButton as _QTB
            for b in self.main_toolbar.findChildren(_QTB):
                if b.text():
                    b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self._recolor_toolbar_icons()

    def _recolor_toolbar_icons(self):
        """Tint toolbar icons to the theme's text colour on dark themes so the
        dark monochrome glyphs stay legible; restore originals on light themes."""
        from PyQt6.QtWidgets import QToolButton
        theme = themes.THEMES[self.ui_theme]
        icon_px = themes.SIZE_SCALES[self.ui_size]["icon"]
        for tb_name in ("main_toolbar", "markup_toolbar"):
            tb = getattr(self, tb_name, None)
            if tb is None:
                continue
            for b in tb.findChildren(QToolButton):
                orig = getattr(b, "_orig_icon", None)
                if orig is None:
                    orig = b.icon()
                    if orig.isNull():
                        continue
                    b._orig_icon = orig      # stash once, tint from original
                if theme.get("is_dark"):
                    b.setIcon(themes.tint_icon(orig, theme["text"], icon_px))
                else:
                    b.setIcon(orig)

    def set_theme(self, theme_key: str):
        self.ui_theme = themes.resolve_theme(theme_key)
        QSettings("LeonPriest", "PDFStudio").setValue("appearance/theme", self.ui_theme)
        self._apply_styles()
        self._sync_appearance_menu()

    def set_ui_size(self, size_key: str):
        self.ui_size = themes.resolve_size(size_key)
        QSettings("LeonPriest", "PDFStudio").setValue("appearance/size", self.ui_size)
        self._apply_styles()
        self._sync_appearance_menu()

    def _sync_appearance_menu(self):
        for key, act in getattr(self, "_theme_actions", {}).items():
            act.setChecked(key == self.ui_theme)
        for key, act in getattr(self, "_size_actions", {}).items():
            act.setChecked(key == self.ui_size)

    def _apply_styles_LEGACY(self):
        self.setStyleSheet("""
            QMainWindow { background: #f0f0f0; }

            /* Menu bar */
            QMenuBar {
                background: #2c2c2c;
                color: #e0e0e0;
                padding: 2px 4px;
                font-size: 12px;
            }
            QMenuBar::item { padding: 3px 10px; border-radius: 3px; }
            QMenuBar::item:selected { background: #444; }
            QMenu {
                background: #ffffff;
                border: 1px solid #ccc;
                font-size: 12px;
                padding: 4px 0;
            }
            QMenu::item { padding: 5px 28px 5px 24px; }
            QMenu::item:selected { background: #3a7bd5; color: #fff; }
            QMenu::separator { height: 1px; background: #e0e0e0; margin: 3px 8px; }
            QMenu::indicator { width: 14px; height: 14px; }

            /* Toolbars */
            QToolBar {
                background: #f5f5f5;
                border: none;
                border-bottom: 1px solid #ddd;
                spacing: 1px;
                padding: 3px 6px;
            }
            QToolBar::separator {
                width: 1px;
                background: #ddd;
                margin: 4px 4px;
            }

            /* Tool buttons */
            QToolButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 3px 6px;
                font-size: 12px;
                color: #1a1a1a;
            }
            QToolButton:hover {
                background: #e3ebf8;
                border-color: #b5c9e8;
            }
            QToolButton:pressed {
                background: #c5d8f5;
                border-color: #7aa5d8;
            }
            QToolButton:checked {
                background: #ddeaff;
                border-color: #3a7bd5;
                color: #1a4aaa;
                font-weight: bold;
            }
            QToolButton:disabled { color: #b0b0b0; }
            QToolButton::menu-button {
                border-left: 1px solid #ccc;
                border-radius: 0 4px 4px 0;
                width: 14px;
            }

            /* Inputs */
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 3px 6px;
                background: #fff;
                font-size: 12px;
                selection-background-color: #3a7bd5;
            }
            QLineEdit:focus { border-color: #3a7bd5; }

            /* Zoom combo */
            QComboBox {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 2px 4px;
                background: #fff;
                font-size: 12px;
            }
            QComboBox:focus { border-color: #3a7bd5; }
            QComboBox::drop-down { border: none; }

            /* Markup pill labels */
            QLabel#SectionPill {
                background: #e2e2e2;
                color: #555;
                font-size: 9px;
                font-weight: bold;
                letter-spacing: 0.8px;
                border-radius: 3px;
                padding: 2px 6px;
            }

            /* Sidebar dock */
            QDockWidget::title {
                background: #2c2c2c;
                color: #e0e0e0;
                padding: 5px 8px;
                font-size: 11px;
                font-weight: bold;
            }
            QListWidget {
                border: 1px solid #e2e2e2;
                background: #fafafa;
                font-size: 12px;
                outline: none;
            }
            QListWidget::item { padding: 3px 6px; }
            QListWidget::item:selected { background: #3a7bd5; color: #fff; }
            QListWidget::item:hover:!selected { background: #eaf0fb; }

            /* Sidebar section labels (legacy) */
            QLabel#SectionLabel {
                color: #888;
                font-size: 9px;
                font-weight: bold;
                letter-spacing: 0.8px;
                padding: 4px 2px 2px 2px;
            }

            /* ── Collapsible nav sections ─────────────────────────── */
            QWidget#NavSectionHeader {
                background: #2c2c2c;
                border-top: 1px solid #444;
            }
            QWidget#NavSectionHeader:hover {
                background: #3a3a3a;
            }
            QLabel#NavArrow {
                color: #aaa;
                font-size: 10px;
                font-weight: bold;
            }
            QLabel#NavIcon {
                font-size: 12px;
            }
            QLabel#NavTitle {
                color: #e0e0e0;
                font-size: 10px;
                font-weight: bold;
                letter-spacing: 0.7px;
            }
            QWidget#NavSection {
                background: #f8f8f8;
                border-bottom: 1px solid #e0e0e0;
            }
            QWidget#NavSectionBody {
                background: #fafafa;
            }

            /* Splitter handle — thin dark groove between sections */
            QSplitter#NavSplitter::handle {
                background: #d0d0d0;
                height: 3px;
            }
            QSplitter#NavSplitter::handle:hover {
                background: #3a7bd5;
            }

            /* Remove border from the nav scroll area */
            QScrollArea#NavScrollArea {
                background: transparent;
                border: none;
            }

            /* Sidebar buttons */
            QPushButton {
                background: #fff;
                border: 1px solid #d0d0d0;
                border-radius: 3px;
                padding: 3px 8px;
                font-size: 12px;
                color: #1a1a1a;
            }
            QPushButton:hover { background: #e3ebf8; border-color: #b5c9e8; }
            QPushButton:pressed { background: #c5d8f5; }
            QPushButton:disabled { color: #b8b8b8; background: #f5f5f5; }

            /* Status bar */
            QStatusBar {
                background: #2c2c2c;
                color: #c0c0c0;
                font-size: 11px;
                padding: 2px 8px;
            }
            QStatusBar::item { border: none; }
        """)

    # =========================================================================
    # Initial disabled state
    # =========================================================================

    def _set_initial_state(self):
        for w in [
            self.prev_button, self.next_button, self.page_input,
            self.zoom_out_button, self.zoom_in_button,
            self.zoom_fit_width_button, self.zoom_fit_page_button,
            self.rotate_button, self.fullscreen_button,
            self.save_button, self.print_button,
            self.prev_search_button, self.next_search_button,
            self.annotate_button, self.highlight_button,
            self.underline_button, self.strikethrough_button,
            self.freehand_button, self.eraser_button,
            self.markup_color_button, self.signature_button, self.stamp_button,
            self.redact_button,
            self.add_bookmark_button, self.remove_bookmark_button,
            self._act_save, self._act_save_as, self._act_print, self._act_preview,
            self._act_props,
            self._act_toggle_view, self._act_dark_mode, self._act_fullscreen,
            self._act_fit_width, self._act_fit_page,
            self._act_zoom_in, self._act_zoom_out, self._act_rotate,
            self._act_add_page, self._act_remove_page,
            self._act_move_up, self._act_move_down, self._act_bookmark,
            self._act_extract_pages, self._act_apply_redact,
            self._act_password,
            self._act_ocr, self._act_export_docx, self._act_export_xlsx,
            # legacy compat
            self._act_save_copy, self._act_reset_form,
            self._act_undo, self._act_redo,
            self._act_copy_text, self._act_select_all,
            self._act_find, self._act_find_next, self._act_find_prev,
            self.save_as_button, self.properties_button,
            self.add_page_button, self.remove_page_button,
            self.move_up_button, self.move_down_button,
            self.view_mode_button, self.dark_mode_button, self.search_button,
        ]:
            w.setEnabled(False)
        self.status_bar.showMessage("Ready  –  open a PDF to begin")


    # ── OCR / Export stubs (implemented in PDFReader) ───────────────────────

    def _show_ocr(self):
        pass   # overridden in pdf_reader_app.py

    def _show_export(self, fmt: str):
        pass   # overridden in pdf_reader_app.py


# ── Module helpers ───────────────────────────────────────────────────────────

def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("SectionLabel")
    return lbl


def _pill(toolbar: QToolBar, text: str):
    lbl = QLabel(f" {text} ")
    lbl.setObjectName("SectionPill")
    toolbar.addWidget(lbl)
