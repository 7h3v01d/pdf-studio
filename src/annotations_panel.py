"""
annotations_panel.py
--------------------
A QWidget panel listing every annotation in the open PDF.
Embed it in the sidebar dock as a collapsible section.

Usage:
    panel = AnnotationsPanel(parent_app)
    sidebar_layout.addWidget(panel)

Call panel.refresh(pdf_document, annotations, markup_strokes)
whenever annotations change.
"""
import fitz

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMenu, QAbstractItemView,
    QSizePolicy, QFrame)
from PyQt6.QtGui import QIcon, QColor, QFont
from PyQt6.QtCore import Qt, QSize, pyqtSignal


ACCENT   = "#2563EB"
ACCENT_L = "#EFF6FF"
DARK     = "#1e293b"
MID      = "#64748b"
LIGHT    = "#f8fafc"
DANGER   = "#dc2626"

# Type label → (emoji, colour)
TYPE_META = {
    "note":          ("📌", "#f59e0b"),
    "highlight":     ("▌",  "#facc15"),
    "underline":     ("U̲",  "#3b82f6"),
    "strikethrough": ("S̶",  "#6b7280"),
    "freehand":      ("✏",  "#8b5cf6"),
    "signature":     ("✍",  "#10b981"),
    "stamp":         ("⬛",  "#1e293b"),
    "redaction":     ("⬛",  "#dc2626"),
    "pdf_highlight": ("▌",  "#facc15"),
    "pdf_underline": ("U̲",  "#3b82f6"),
    "pdf_strike":    ("S̶",  "#6b7280"),
    "pdf_ink":       ("✏",  "#8b5cf6"),
    "pdf_text":      ("📌", "#f59e0b"),
    "pdf_other":     ("◆",  "#64748b"),
}


class AnnotationsPanel(QWidget):
    """
    Sidebar panel: lists all annotations.
    Signals:
        jump_to_page(int)         – scroll viewer to this 0-based page
        delete_annotation(dict)   – caller should remove this annotation
    """
    jump_to_page      = pyqtSignal(int)
    delete_annotation = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AnnotationsPanel")
        self._items_data: list[dict] = []   # parallel list to list widget rows
        self._build_ui()

    # =========================================================================
    # UI
    # =========================================================================

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        # Toolbar row: count label + refresh + clear-all
        bar = QHBoxLayout()
        bar.setSpacing(4)
        self._count_label = QLabel("0 annotations")
        self._count_label.setStyleSheet(
            f"color: {MID}; font-size: 10px; font-weight: bold;")
        bar.addWidget(self._count_label)
        bar.addStretch()

        self._refresh_btn = QPushButton("⟳")
        self._refresh_btn.setFixedSize(22, 22)
        self._refresh_btn.setToolTip("Refresh annotation list")
        self._refresh_btn.setStyleSheet(self._icon_btn_style())
        bar.addWidget(self._refresh_btn)
        layout.addLayout(bar)

        # List widget
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid #e2e8f0;
                border-radius: 4px;
                background: white;
                font-size: 11px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 5px 6px;
                border-bottom: 1px solid #f1f5f9;
            }}
            QListWidget::item:selected {{
                background: {ACCENT_L};
                color: {ACCENT};
                border-left: 3px solid {ACCENT};
            }}
            QListWidget::item:hover:!selected {{ background: #f8fafc; }}
            QListWidget::item:alternate {{ background: #fafafa; }}
        """)
        layout.addWidget(self.list_widget)

        # Signals
        self.list_widget.itemDoubleClicked.connect(self._on_double_click)
        self.list_widget.customContextMenuRequested.connect(
            self._on_context_menu)
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)

    # =========================================================================
    # Public API
    # =========================================================================

    def refresh(self,
                pdf_document,           # fitz.Document or None
                annotations: dict,      # {page: [(x,y,text)]}
                markup_strokes: dict,   # {page: [{type,rects/points,...}]}
                pending_redactions: dict = None):  # {page: [fitz.Rect]}
        """Rebuild the list from current document state."""
        self.list_widget.clear()
        self._items_data.clear()

        if not pdf_document:
            self._count_label.setText("0 annotations")
            return

        all_items: list[dict] = []

        # ── 1. Sticky-note annotations (our own store) ────────────────────
        for page_num, items in sorted(annotations.items()):
            for x, y, text in items:
                all_items.append({
                    "source":   "note",
                    "type":     "note",
                    "page":     page_num,
                    "text":     text[:80],
                    "x": x, "y": y,
                })

        # ── 2. Markup strokes (highlight, underline, freehand …) ──────────
        for page_num, strokes in sorted(markup_strokes.items()):
            for idx, stroke in enumerate(strokes):
                stype = stroke.get("type", "unknown")
                preview = ""
                if stype in ("highlight", "underline", "strikethrough"):
                    rects = stroke.get("rects", [])
                    preview = f"{len(rects)} word(s)"
                elif stype == "freehand":
                    pts = stroke.get("points", [])
                    preview = f"{len(pts)} points"
                elif stype == "signature":
                    preview = "Placed signature"
                elif stype == "stamp":
                    preview = stroke.get("text", "Stamp")
                all_items.append({
                    "source":  "markup",
                    "type":    stype,
                    "page":    page_num,
                    "stroke_idx": idx,
                    "text":    preview,
                })

        # ── 3. Pending redactions ─────────────────────────────────────────
        if pending_redactions:
            for page_num, rects in sorted(pending_redactions.items()):
                for i, r in enumerate(rects):
                    all_items.append({
                        "source":  "redaction",
                        "type":    "redaction",
                        "page":    page_num,
                        "rect_idx": i,
                        "text":    f"({r.x0:.0f},{r.y0:.0f})–({r.x1:.0f},{r.y1:.0f})",
                    })

        # ── 4. Native PDF annotations (from fitz) ────────────────────────
        PDF_TYPE_MAP = {
            8:  "pdf_text",       # Text / sticky note
            9:  "pdf_highlight",
            10: "pdf_underline",
            11: "pdf_strike",
            15: "pdf_ink",
        }
        for page_num in range(pdf_document.page_count):
            page = pdf_document.load_page(page_num)
            for annot in page.annots():
                atype_int = annot.type[0]
                atype     = PDF_TYPE_MAP.get(atype_int, "pdf_other")
                content   = annot.info.get("content", "") or annot.info.get("title", "")
                all_items.append({
                    "source":  "pdf",
                    "type":    atype,
                    "page":    page_num,
                    "annot_xref": annot.xref,
                    "text":    content[:80] if content else annot.type[1],
                })

        # Sort by page then source
        all_items.sort(key=lambda d: (d["page"], d["source"]))

        # ── Populate list widget ──────────────────────────────────────────
        for item_data in all_items:
            self._items_data.append(item_data)
            self.list_widget.addItem(self._make_list_item(item_data))

        n = len(all_items)
        self._count_label.setText(
            f"{n} annotation{'s' if n != 1 else ''}")

    # =========================================================================
    # List item factory
    # =========================================================================

    def _make_list_item(self, data: dict) -> QListWidgetItem:
        itype    = data.get("type", "pdf_other")
        emoji, colour = TYPE_META.get(itype, ("◆", MID))
        page_num = data["page"]
        text     = data.get("text", "")

        # Display text: "p.3  ▌  Highlight text preview…"
        display = f"p.{page_num + 1}   {emoji}  {_type_label(itype)}"
        if text:
            display += f"\n      {text}"

        item = QListWidgetItem(display)
        item.setData(Qt.ItemDataRole.UserRole, len(self._items_data) - 1)
        item.setToolTip(
            f"Page {page_num + 1} · {_type_label(itype)}\n{text}")
        return item

    # =========================================================================
    # Interaction
    # =========================================================================

    def _on_double_click(self, item: QListWidgetItem):
        idx  = item.data(Qt.ItemDataRole.UserRole)
        if idx is None or idx >= len(self._items_data):
            return
        page = self._items_data[idx]["page"]
        self.jump_to_page.emit(page)

    def _on_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None or idx >= len(self._items_data):
            return
        data = self._items_data[idx]

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: white; border: 1px solid #e2e8f0;
                    font-size: 12px; }
            QMenu::item { padding: 5px 24px; }
            QMenu::item:selected { background: #dbeafe; color: #1e40af; }
        """)
        go_act  = menu.addAction(f"▶  Go to Page {data['page'] + 1}")
        menu.addSeparator()
        del_act = menu.addAction("🗑  Delete This Annotation")
        del_act.setStyleSheet(f"color: {DANGER};")

        chosen = menu.exec(self.list_widget.mapToGlobal(pos))
        if chosen == go_act:
            self.jump_to_page.emit(data["page"])
        elif chosen == del_act:
            self.delete_annotation.emit(data)

    def _on_refresh_clicked(self):
        """Signal the parent app to call refresh() again."""
        # The parent app connects to this via a lambda that calls refresh()
        self.jump_to_page.emit(-1)   # -1 = refresh-only signal

    # =========================================================================
    # Style helper
    # =========================================================================

    @staticmethod
    def _icon_btn_style() -> str:
        return (
            f"QPushButton {{ background: transparent; border: 1px solid #e2e8f0;"
            f" border-radius: 3px; color: {MID}; font-size: 13px; }}"
            f"QPushButton:hover {{ background: #e3ebf8; }}"
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _type_label(t: str) -> str:
    return {
        "note":          "Sticky Note",
        "highlight":     "Highlight",
        "underline":     "Underline",
        "strikethrough": "Strikethrough",
        "freehand":      "Drawing",
        "signature":     "Signature",
        "stamp":         "Stamp",
        "redaction":     "Redaction (pending)",
        "pdf_highlight": "Highlight",
        "pdf_underline": "Underline",
        "pdf_strike":    "Strikethrough",
        "pdf_ink":       "Ink / Drawing",
        "pdf_text":      "Text Note",
        "pdf_other":     "Annotation",
    }.get(t, t.replace("_", " ").title())
