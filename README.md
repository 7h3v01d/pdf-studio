# PDF Reader Pro

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

- **Open & View** — single-page and continuous scroll view modes, fit-width/fit-page zoom, rotate, dark mode, full-screen
- **Navigation** — page thumbnails, table of contents (TOC), bookmarks, page jump, keyboard shortcuts
- **Search** — full-text search with next/previous result navigation
- **Annotations** — sticky notes, highlights, underlines, strikethrough, freehand drawing, eraser
- **Signatures & Stamps** — draw and place a handwritten signature; insert text stamps
- **Redactions** — mark and permanently apply redactions
- **Form Filling** — interact with PDF form fields (text, checkboxes, dropdowns) directly in the viewer
- **Page Management** — add blank pages, remove pages, reorder via drag-and-drop thumbnails or move up/down
- **Merge & Split** — merge multiple PDFs or split a PDF into separate files
- **Extract Pages** — extract a range or selection of pages to a new PDF
- **Password Protection** — open password-protected PDFs; encrypt saved PDFs with AES-256, set open/permissions passwords and granular permission flags
- **Print** — send the current document to any system printer
- **Metadata Viewer** — inspect document properties
- **Recent Files** — quick-open menu for the last 10 opened files
- **Annotations Panel** — sidebar listing all annotations across the document with jump-to and delete actions

---

## Project Structure

```
pdf_reader.py            # Entry point — launches the application
pdf_reader_app.py        # Core application logic (PDFReader class)
pdf_reader_ui.py         # All UI construction (menus, toolbars, panels)
pdf_utils.py             # Utility functions (search, page ops, annotation I/O)
pdf_scroll_area.py       # Custom QScrollArea (wheel zoom + page-flip)
pdf_page_widget.py       # Custom QLabel for page rendering with form-field support
annotations_panel.py     # Sidebar panel listing all annotations
password_dialog.py       # Password prompt and encryption settings dialogs
signature_dialog.py      # Draw-your-own signature dialog
merge_split_dialog.py    # Merge / split PDF dialog
extract_pages_dialog.py  # Extract pages dialog
about_dialog.py          # About / keyboard shortcuts dialog
icon.ico                 # Application icon
```

---

## Requirements

- Python 3.10+
- See `requirements.txt`

---

## Installation

```bash
# 1. Clone or download the project
git clone https://github.com/your-username/pdf-reader-pro.git
cd pdf-reader-pro

# 2. (Recommended) Create a virtual environment
python -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt
```

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
| `Ctrl+C` | Copy selected text |
| `Ctrl+B` | Add bookmark |
| `Escape` | Cancel active tool |

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
