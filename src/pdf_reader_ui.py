"""
pdf_reader_ui.py
----------------
UI layout, menu bar, toolbars, sidebar, shortcuts, and styles.
All logic is implemented in the derived PDFReader class (pdf_reader_app.py).
"""
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel,
    QToolBar, QLineEdit, QStatusBar, QComboBox, QDockWidget,
    QListWidget, QMenu, QMenuBar, QSizePolicy, QToolButton, QHBoxLayout,
    QFrame, QMessageBox)
from PyQt6.QtGui import QIcon, QShortcut, QKeySequence, QAction, QFont
from PyQt6.QtCore import Qt, QSize
from pdf_scroll_area import PDFScrollArea

from about_dialog import APP_NAME, AboutDialog
from merge_split_dialog import MergeSplitDialog
from annotations_panel import AnnotationsPanel

SINGLE_PAGE = 0
CONTINUOUS  = 1


class PDFReaderUI(QMainWindow):
    SINGLE_PAGE = SINGLE_PAGE
    CONTINUOUS  = CONTINUOUS

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Reader Pro")
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
        self._act_props   = QAction("&Properties",self)
        self._act_quit    = QAction("&Quit",       self)
        self._act_open.setIcon(QIcon.fromTheme("document-open"))
        self._act_save.setIcon(QIcon.fromTheme("document-save"))
        self._act_save_as.setIcon(QIcon.fromTheme("document-save-as"))
        self._act_print.setIcon(QIcon.fromTheme("document-print"))
        self._act_props.setIcon(QIcon.fromTheme("document-properties"))
        self._act_quit.setShortcut("Ctrl+Q")
        file_menu.addAction(self._act_open)
        file_menu.addSeparator()
        file_menu.addAction(self._act_save)
        file_menu.addAction(self._act_save_as)
        file_menu.addSeparator()
        file_menu.addAction(self._act_print)
        file_menu.addAction(self._act_props)
        file_menu.addSeparator()
        file_menu.addAction(self._act_quit)

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
        self._act_merge_split   = QAction("&Merge / Split PDFs…",  self)
        self._act_password      = QAction("&Password Protect…",       self)
        self._act_extract_pages = QAction("&Extract Pages…",          self)
        self._act_apply_redact  = QAction("Apply &Redactions",          self)
        self._act_merge_split.setIcon(QIcon.fromTheme("document-new"))
        self._act_extract_pages.setIcon(QIcon.fromTheme("document-save"))
        self._act_apply_redact.setIcon(QIcon.fromTheme("edit-delete"))
        tools_menu.addAction(self._act_merge_split)
        tools_menu.addAction(self._act_extract_pages)
        tools_menu.addAction(self._act_password)
        tools_menu.addSeparator()
        tools_menu.addAction(self._act_apply_redact)

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
        self.main_toolbar = tb

        # Open split-button
        self.open_button.setIcon(QIcon.fromTheme("document-open"))
        self.open_button.setText(" Open")
        self.open_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.open_button.setToolTip("Open PDF  (Ctrl+O)\nArrow ▾ → recent files")
        self.open_button.setAutoRaise(True)
        tb.addWidget(self.open_button)

        self._tb_btn(tb, self.save_button,  "document-save",  "Save  (Ctrl+S)")
        self._tb_btn(tb, self.print_button, "document-print", "Print  (Ctrl+P)")

        tb.addSeparator()

        # Navigation
        self._tb_btn(tb, self.prev_button, "go-previous", "Previous Page  (←)")
        self.page_input.setFixedWidth(46)
        self.page_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_input.setPlaceholderText("1")
        tb.addWidget(self.page_input)
        self.page_label.setContentsMargins(2, 0, 4, 0)
        tb.addWidget(self.page_label)
        self._tb_btn(tb, self.next_button, "go-next", "Next Page  (→)")

        tb.addSeparator()

        # Zoom
        self._tb_btn(tb, self.zoom_out_button, "zoom-out", "Zoom Out  (Ctrl+-)")
        self.zoom_combo.addItems(["25%","50%","75%","100%","125%","150%","200%","300%","400%"])
        self.zoom_combo.setCurrentText("100%")
        self.zoom_combo.setFixedWidth(80)
        tb.addWidget(self.zoom_combo)
        self._tb_btn(tb, self.zoom_in_button, "zoom-in", "Zoom In  (Ctrl++)")

        self.zoom_fit_width_button.setText("⇔")
        self.zoom_fit_width_button.setToolTip("Fit Width  (Ctrl+Shift+H)")
        self.zoom_fit_width_button.setAutoRaise(True)
        tb.addWidget(self.zoom_fit_width_button)

        self.zoom_fit_page_button.setText("⛶")
        self.zoom_fit_page_button.setToolTip("Fit Page  (Ctrl+Shift+F)")
        self.zoom_fit_page_button.setAutoRaise(True)
        tb.addWidget(self.zoom_fit_page_button)

        tb.addSeparator()

        self._tb_btn(tb, self.rotate_button,    "image-rotate",   "Rotate 90°  (Ctrl+R)")
        self._tb_btn(tb, self.fullscreen_button, "view-fullscreen","Full Screen  (F11)")

        tb.addSeparator()

        # Search (inline)
        self.search_input.setFixedWidth(170)
        self.search_input.setPlaceholderText("🔍  Search…")
        self.search_input.setClearButtonEnabled(True)
        tb.addWidget(self.search_input)
        self._tb_btn(tb, self.prev_search_button, "go-previous", "Previous Result")
        self._tb_btn(tb, self.next_search_button, "go-next",     "Next Result")

        self.setStatusBar(self.status_bar)

    @staticmethod
    def _tb_btn(tb, btn, icon_name, tip):
        btn.setIcon(QIcon.fromTheme(icon_name))
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
        self.sidebar.setMinimumWidth(185)
        sw = QWidget()
        sl = QVBoxLayout(sw)
        sl.setContentsMargins(4, 6, 4, 4)
        sl.setSpacing(4)

        sl.addWidget(_section_label("📑 CONTENTS"))
        self.toc_list.setMaximumHeight(160)
        sl.addWidget(self.toc_list)

        sl.addWidget(_section_label("🔖 BOOKMARKS"))
        bm_row = QHBoxLayout()
        bm_row.setSpacing(4)
        self.add_bookmark_button    = QPushButton("+ Add")
        self.remove_bookmark_button = QPushButton("− Remove")
        self.add_bookmark_button.setFixedHeight(24)
        self.remove_bookmark_button.setFixedHeight(24)
        bm_row.addWidget(self.add_bookmark_button)
        bm_row.addWidget(self.remove_bookmark_button)
        sl.addLayout(bm_row)
        self.bookmark_list.setMaximumHeight(120)
        sl.addWidget(self.bookmark_list)

        sl.addWidget(_section_label("💬 ANNOTATIONS"))
        sl.addWidget(self.annot_panel)

        sl.addWidget(_section_label("🖼 THUMBNAILS"))
        self.thumbnail_list.setIconSize(QSize(90, 120))
        self.thumbnail_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.thumbnail_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.thumbnail_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        sl.addWidget(self.thumbnail_list, stretch=1)

        self.sidebar.setWidget(sw)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.sidebar)

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
        self._act_open.triggered.connect(self.open_pdf)
        self._act_save.triggered.connect(self.save_pdf)
        self._act_save_as.triggered.connect(self.save_pdf_as)
        self._act_print.triggered.connect(self.print_pdf)
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
        self._act_about.triggered.connect(self._show_about)
        self._act_shortcuts.triggered.connect(self._show_shortcuts_help)

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
        QShortcut(QKeySequence("Ctrl+O"),       self, self.open_pdf)
        QShortcut(QKeySequence("Ctrl+S"),       self, self.save_pdf)
        QShortcut(QKeySequence("Ctrl+P"),       self, self.print_pdf)
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

    def _show_shortcuts_help(self):
        dlg = AboutDialog(self)
        # Jump straight to shortcuts tab (index 1)
        dlg.findChild(__import__("PyQt6.QtWidgets", fromlist=["QTabWidget"]).QTabWidget).setCurrentIndex(1)
        dlg.exec()

    # =========================================================================
    # Styles
    # =========================================================================

    def _apply_styles(self):
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

            /* Sidebar section labels */
            QLabel#SectionLabel {
                color: #888;
                font-size: 9px;
                font-weight: bold;
                letter-spacing: 0.8px;
                padding: 4px 2px 2px 2px;
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
            self._act_save, self._act_save_as, self._act_print, self._act_props,
            self._act_toggle_view, self._act_dark_mode, self._act_fullscreen,
            self._act_fit_width, self._act_fit_page,
            self._act_zoom_in, self._act_zoom_out, self._act_rotate,
            self._act_add_page, self._act_remove_page,
            self._act_move_up, self._act_move_down, self._act_bookmark,
            self._act_extract_pages, self._act_apply_redact,
            self._act_password,
            # legacy compat
            self.save_as_button, self.properties_button,
            self.add_page_button, self.remove_page_button,
            self.move_up_button, self.move_down_button,
            self.view_mode_button, self.dark_mode_button, self.search_button,
        ]:
            w.setEnabled(False)
        self.status_bar.showMessage("Ready  –  open a PDF to begin")


# ── Module helpers ───────────────────────────────────────────────────────────

def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("SectionLabel")
    return lbl


def _pill(toolbar: QToolBar, text: str):
    lbl = QLabel(f" {text} ")
    lbl.setObjectName("SectionPill")
    toolbar.addWidget(lbl)
