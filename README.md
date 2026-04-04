# PDF Reader Pro v2.5

A professional PDF reader and editor built with Python and PyQt6.  
Developed by **Leon** @ **KeystoneAI**.

---

⚠️ **LICENSE & USAGE NOTICE — READ FIRST**

This repository is **source-available for private technical evaluation and testing only**.

- ❌ No commercial use  
- ❌ No production use  
- ❌ No academic, institutional, or government use  
- ❌ No research, benchmarking, or publication  
- ❌ No redistribution, sublicensing, or derivative works  
- ❌ No independent development based on this code  

All rights remain exclusively with the author.  
Use of this software constitutes acceptance of the terms defined in **LICENSE.txt**.

---

## Features

### Viewing & Navigation
- **Open & View** — single-page and continuous scroll view modes, fit-width/fit-page zoom, rotate, dark mode, full-screen
- **Navigation Panel** — collapsible, resizable sidebar with four independent sections: Table of Contents, Bookmarks, Annotations, and Page Thumbnails
- **Search** — full-text search with next/previous result navigation
- **Recent Files** — quick-open split-button for the last 10 opened files
- **Metadata Viewer** — inspect document properties

### Annotations & Markup
- **Annotations** — sticky notes, highlights, underlines, strikethrough, freehand drawing, eraser
- **Signatures & Stamps** — draw and place a handwritten signature; insert text stamps
- **Redactions** — mark and permanently apply redactions
- **Annotations Panel** — sidebar listing all annotations across the document with jump-to and delete actions

### Editing & Page Management
- **Form Filling** — interact with PDF form fields (text, checkboxes, dropdowns) directly in the viewer
- **Page Management** — add blank pages, remove pages, reorder via drag-and-drop thumbnails or move up/down
- **Full Undo/Redo** — complete history for annotations, markup, page insert, page delete, and page move (including drag-to-reorder)
- **Merge & Split** — merge multiple PDFs or split a PDF into separate files
- **Extract Pages** — extract a range or selection of pages to a new PDF
- **Password Protection** — open password-protected PDFs; encrypt saved PDFs with AES-256, set open/permissions passwords and granular permission flags

### OCR & Export *(v1.1)*
- **OCR** — `Tools → Run OCR…` makes scanned pages fully searchable and copy-able by adding an invisible text layer via Tesseract. Supports: all pages / current page / custom range; language selection from all installed Tesseract languages; non-blocking background processing with live progress; save as new file or overwrite original
- **Export to Word** — `File → Export As → Microsoft Word (.docx)` preserves layout, text, images and columns via `pdf2docx`. Supports page range selection
- **Export to Excel** — `File → Export As → Microsoft Excel (.xlsx)` extracts tables into styled spreadsheet sheets with headers, alternating rows and frozen panes via `tabula-py`

### Output & Printing
- **Save / Save As / Save a Copy** — flexible save options; title bar shows `*` when there are unsaved changes
- **Print** — send the current document to any system printer

### Preferences & Persistence
- Zoom level, view mode (single/continuous), dark mode, and markup colour are remembered across sessions
- Navigation panel section collapse state and splitter sizes are remembered across sessions
- Window geometry and state are remembered across sessions

---

## Project Structure

```
pdf_reader.py            # Entry point — launches the application
pdf_reader_app.py        # Core application logic (PDFReader class)
pdf_reader_ui.py         # All UI construction (menus, toolbars, panels, NavSection)
pdf_utils.py             # Utility functions (search, page ops, annotation I/O, undo push)
pdf_scroll_area.py       # Custom QScrollArea (wheel zoom + page-flip)
pdf_page_widget.py       # Custom QLabel for page rendering with form-field support
annotations_panel.py     # Sidebar panel listing all annotations
password_dialog.py       # Password prompt and encryption settings dialogs
signature_dialog.py      # Draw-your-own signature dialog
merge_split_dialog.py    # Merge / split PDF dialog
extract_pages_dialog.py  # Extract pages dialog
ocr_dialog.py            # OCR settings, progress, and background worker
export_dialog.py         # Export to Word / Excel with progress
about_dialog.py          # About / keyboard shortcuts dialog
undo_stack.py            # Lightweight command stack (annotation, markup, page ops)
icon.ico                 # Application icon
```

---

## Requirements

- Python 3.10+
- See `requirements.txt` for core dependencies
- See **Optional Dependencies** below for OCR and Export features

---

## Installation

```bash
# 1. Clone or download the project
git clone https://github.com/your-username/pdf-reader-pro.git
cd pdf-reader-pro/src

# 2. (Recommended) Create a virtual environment
python -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows

# 3. Install core dependencies
pip install -r requirements.txt
```

---

## Optional Dependencies

These are only required if you use the OCR or Export features. The app runs fine without them — the menu items will show a friendly error if a dependency is missing when you try to use them.

### OCR  (`Tools → Run OCR…`)

```bash
pip install pytesseract pdf2image Pillow
```

**System requirements:**

| Dependency | Purpose | Download |
|---|---|---|
| **Tesseract-OCR** | OCR engine | [Windows installer](https://github.com/UB-Mannheim/tesseract/wiki) — add to PATH |
| **Poppler** | PDF → image rendering for pdf2image | [poppler-windows](https://github.com/oschwartz10612/poppler-windows) — add `bin/` to PATH |

Additional Tesseract language packs can be installed separately; the language dropdown auto-populates from whatever is installed.

### Export to Word  (`File → Export As → Word`)

```bash
pip install pdf2docx
```

### Export to Excel  (`File → Export As → Excel`)

```bash
pip install tabula-py openpyxl pandas
```

**System requirements:**

| Dependency | Purpose | Download |
|---|---|---|
| **Java** | Required by tabula-py | [java.com](https://www.java.com/en/download/) |

---

## Running

```bash
python pdf_reader.py
```

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+O` | Open file |
| `Ctrl+S` | Save |
| `Ctrl+Shift+S` | Save As |
| `Ctrl+P` | Print |
| `Ctrl+Q` | Quit |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |
| `← / →` | Previous / next page |
| `Ctrl+Home` | First page |
| `Ctrl+End` | Last page |
| `Ctrl++ / Ctrl+-` | Zoom in / out |
| `Ctrl+Wheel` | Zoom in / out |
| `Ctrl+Shift+H` | Fit width |
| `Ctrl+Shift+F` | Fit page |
| `Ctrl+R` | Rotate 90° |
| `F11` | Toggle full screen |
| `F4` | Toggle navigation panel |
| `Ctrl+F` | Focus search box |
| `F3 / Shift+F3` | Next / previous search result |
| `Ctrl+C` | Copy selected text |
| `Ctrl+B` | Add bookmark |
| `Escape` | Cancel active tool |

---

## Changelog

### v1.1 — OCR & Export
- Added `Tools → Run OCR…` — makes scanned PDFs searchable via Tesseract
- Added `File → Export As → Microsoft Word (.docx)`
- Added `File → Export As → Microsoft Excel (.xlsx)`
- Zoom level, view mode, dark mode, and markup colour now persist across sessions
- Title bar shows `*` prefix when document has unsaved changes
- Undo/Redo now fully covers page insert, delete, and move (including drag-to-reorder)
- Edit menu Undo/Redo labels update dynamically (e.g. "Undo Insert Page")

### v1.0 — Initial Release
- Full viewer with single-page and continuous scroll modes
- Annotations, markup, signatures, stamps, and redactions
- Form field interaction
- Page management, merge/split, extract pages
- Password protection (AES-256)
- Collapsible, resizable Navigation Panel (Contents / Bookmarks / Annotations / Thumbnails)
- Full-text search, bookmarks, TOC, recent files

---

## Contribution Policy

Feedback, bug reports, and suggestions are welcome.

You may submit:

- Issues
- Design feedback
- Pull requests for review

However:

- Contributions do not grant any license or ownership rights
- The author retains full discretion over acceptance and future use
- Contributors receive no rights to reuse, redistribute, or derive from this code

---

## License

This project is not open-source.

It is licensed under a private evaluation-only license.  
See LICENSE.txt for full terms.
