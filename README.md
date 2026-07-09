# PDF Studio

A free, full-featured PDF reader and editor built with Python and PyQt6.

Created by **Leon Priest** ([github.com/7h3v01d](https://github.com/7h3v01d)) and released
under the **Apache License 2.0** — free to use, modify, and share.

---

<img width="1920" height="1080" alt="pdf_studio_light icons" src="https://github.com/user-attachments/assets/163d44cb-0c1b-48cb-8501-d73bf7025a8c" />

---

## Features

### Viewing & Navigation
- **Open & View** — single-page and continuous scroll view modes, fit-width/fit-page zoom, rotate, dark mode, full-screen
- **Navigation Panel** — collapsible, resizable sidebar: Table of Contents, Bookmarks, Annotations, Page Thumbnails
- **Search** — full-text search with next/previous result navigation
- **Recent Files** — quick-open split-button for the last 10 opened files
- **Metadata Viewer** — inspect document properties

### Annotations & Markup
- **Annotations** — sticky notes, highlights, underlines, strikethrough, freehand drawing, eraser
- **Signatures & Stamps** — add a signature by **drawing** it or **importing a PNG/JPG image** (with automatic white-background removal for scans); **drag-and-drop** an image straight onto the page; insert text stamps. (Image stamp, not a cryptographic/digital signature.)
- **Redactions** — mark and permanently apply redactions
- **Annotations Panel** — sidebar listing all annotations with jump-to and delete actions

### Editing & Page Management
- **Form Filling** — text fields, checkboxes, dropdowns directly in the viewer
- **Page Management** — add blank pages, remove pages, reorder via drag-and-drop thumbnails or move up/down
- **Full Undo/Redo** — annotations, markup, page insert/delete/move (including drag-to-reorder)
- **Merge & Split** — merge multiple PDFs or split one into separate files
- **Extract Pages** — extract a range or selection to a new PDF
- **Password Protection** — open password-protected PDFs; encrypt saved PDFs with AES-256, set open/permissions passwords and granular permission flags

### OCR & Export
- **OCR** — `Tools → Run OCR…` adds an invisible searchable text layer via Tesseract (all/current/custom range; language selection; background processing; save-new or overwrite)
- **Export to Word** — `File → Export As → Word (.docx)` preserves layout/text/images/columns via `pdf2docx`
- **Export to Excel** — `File → Export As → Excel (.xlsx)` extracts tables into styled sheets via `tabula-py`

### Open Word & Excel
- **Open Word/Excel documents** — `File → Open` now accepts `.docx .doc .rtf .odt` and `.xlsx .xls .ods .csv`. The document is converted to PDF and opened for viewing and markup.
- **Fidelity:** for an exact copy, the app uses **Microsoft Word/Excel** via automation when they're installed (identical to their own "Save as PDF"). If Office isn't present it falls back to **LibreOffice** (free) — very faithful, though not guaranteed pixel-identical for complex layouts. If neither is installed, it explains what to install.

### Output & Printing
- **Save / Save As / Save a Copy** — title bar shows `*` on unsaved changes
- **Print** — send the current document to any system printer

### Preferences & Persistence
- Zoom, view mode, dark mode, markup colour, panel state, and window geometry are remembered across sessions

---

## Project Structure

```
pdf_reader.py            # Entry point — launches the application
pdf_reader_app.py        # Core application logic (PDFReader class)
pdf_reader_ui.py         # UI construction (menus, toolbars, panels, NavSection)
pdf_utils.py             # Utilities (search, page ops, annotation I/O, undo push)
pdf_scroll_area.py       # Custom QScrollArea (wheel zoom + page-flip)
pdf_page_widget.py       # Custom QLabel page rendering with form-field support
annotations_panel.py     # Sidebar panel listing all annotations
password_dialog.py       # Password prompt and encryption settings dialogs
signature_dialog.py      # Draw-your-own signature dialog
merge_split_dialog.py    # Merge / split PDF dialog
extract_pages_dialog.py  # Extract pages dialog
ocr_dialog.py            # OCR settings, progress, background worker
export_dialog.py         # Export to Word / Excel with progress
about_dialog.py          # About dialog + app metadata (APP_NAME, APP_VERSION, COMPANY_NAME)
undo_stack.py            # Lightweight command stack
icon.ico                 # Application icon
```

> **Renaming the app:** the product name, version, and author live in one place —
> the constants at the top of `src/about_dialog.py` (`APP_NAME`, `APP_VERSION`,
> `COMPANY_NAME`). Change `APP_NAME` and the whole app (title bar, About box,
> menus) follows. The build output name is set in `src/PDF Studio.spec`.

---

## Requirements

- Python 3.10+
- Core: `PyMuPDF`, `PyQt6` (see `requirements.txt`)
- Optional deps for OCR/Export — see below

---

## Installation

```bash
cd pdf-studio/src

python -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows

pip install -r ../requirements.txt
```

---

## Optional Dependencies

Only needed for OCR/Export. The app runs fine without them — the relevant menu
item shows a friendly error if a dependency is missing.

### OCR  (`Tools → Run OCR…`)
```bash
pip install pytesseract pdf2image Pillow
```
| Dependency | Purpose | Download |
|---|---|---|
| **Tesseract-OCR** | OCR engine | [Windows installer](https://github.com/UB-Mannheim/tesseract/wiki) — add to PATH |
| **Poppler** | PDF → image for pdf2image | [poppler-windows](https://github.com/oschwartz10612/poppler-windows) — add `bin/` to PATH |

### Export to Word
```bash
pip install pdf2docx
```

### Export to Excel
```bash
pip install tabula-py openpyxl pandas
```
| Dependency | Purpose | Download |
|---|---|---|
| **Java** | Required by tabula-py | [java.com](https://www.java.com/en/download/) |

### Open Word / Excel documents

Highest fidelity uses the Office apps themselves (recommended on Windows):

```bash
pip install pywin32          # enables the Microsoft Word/Excel conversion path
```

| Dependency | Purpose | Notes |
|---|---|---|
| **Microsoft Office** | Exact Word/Excel-rendered PDF | Best fidelity; used automatically if installed |
| **LibreOffice** | Free fallback converter | [libreoffice.org](https://www.libreoffice.org/download) — very faithful, not guaranteed identical |

---

## Running

```bash
python pdf_reader.py
```

## Building a Windows .exe

```bash
buildit.bat          # runs: pyinstaller "PDF Studio.spec"
```
The executable appears in `src/dist/`.

---

## Make PDF Studio open your PDFs (Windows)

PDF Studio accepts a file path on launch, so once it's associated with `.pdf`,
double-clicking a PDF opens it here.

**Easiest — from inside the app:** `File -> Set as Default PDF App...`. This
registers PDF Studio (per-user, no admin needed) and opens Windows' *Default
apps* page. Set **PDF Studio** as the default for `.pdf` there.

**Or, per file in Explorer:** right-click a PDF -> *Open with* -> *Choose
another app* -> **PDF Studio** -> tick *Always use this app*.

> Windows 10/11 deliberately won't let an app silently make itself the default
> handler (anti-hijacking). So there's always a one-time confirmation — the app
> can register itself as an option, but you pick it as the default once.

**From source / the built .exe:**

```bat
register_pdf.bat            :: register .pdf + Word/Excel (per-user)
unregister_pdf.bat          :: remove the associations
```

The built executable also supports the flags directly:

```bat
"PDF Studio.exe" --register              :: .pdf + Word/Excel
"PDF Studio.exe" --register --pdf-only   :: .pdf only
"PDF Studio.exe" --unregister
```

---

## Keyboard Shortcuts

| Shortcut | Action | Shortcut | Action |
|---|---|---|---|
| `Ctrl+O` | Open | `Ctrl+R` | Rotate 90° |
| `Ctrl+S` | Save | `F11` | Full screen |
| `Ctrl+Shift+S` | Save As | `F4` | Toggle nav panel |
| `Ctrl+P` | Print | `Ctrl+F` | Focus search |
| `Ctrl+Q` | Quit | `F3 / Shift+F3` | Next / prev result |
| `Ctrl+Z / Ctrl+Y` | Undo / Redo | `Ctrl+C` | Copy text |
| `← / →` | Prev / next page | `Ctrl+B` | Add bookmark |
| `Ctrl+Home / End` | First / last page | `Escape` | Cancel active tool |
| `Ctrl++ / Ctrl+-` | Zoom in / out | `Ctrl+Shift+H / F` | Fit width / page |

---

## Changelog

### v2.5 — Windows file association
- Opening a file passed on the command line now works, so double-clicking an associated PDF opens it (previously launched to a blank window)
- `File -> Set as Default PDF App...` registers PDF Studio for PDF/Word/Excel (per-user, no admin) and opens Windows Default apps to confirm
- `register_pdf.bat` / `unregister_pdf.bat` helpers, and `--register` / `--unregister` command-line flags

### v2.4 — Dark-mode icon fix
- Toolbar icons are now tinted to the theme's text colour on dark themes, so the dark glyphs stay legible on the dark toolbar; light themes are unchanged

### v2.3 — Signatures & form polish
- Signatures can now be **imported from a PNG/JPG image**, not just drawn, with optional white-background removal for scanned/photographed signatures
- **Drag-and-drop** an image file directly onto a page to place it as a signature
- Signatures now place at a sensible default size (previously could land oversized)
- Form-field text scales with the accessibility text-size setting

### v2.2 — Open Word & Excel
- `File → Open` now opens `.docx .doc .rtf .odt .xlsx .xls .ods .csv`, converting to PDF for viewing and markup
- Uses Microsoft Word/Excel via automation when installed (exact copy); falls back to LibreOffice (free) otherwise
- Clear guidance shown if no converter is available

### v2.1 — Accessibility & themes
- Two switchable app themes: High-Contrast Light and Dark Industrial (View → Appearance), remembered across launches
- App-wide text size control (Medium / Large / Extra Large) for low-vision readability
- All UI text set in Atkinson Hyperlegible (bundled, SIL OFL) — designed for low vision
- Toolbar buttons now carry text labels (also fixes blank icon-only buttons on Windows, which has no icon theme)
- Larger, scalable toolbar icons

### v2.0 — Free release
- Removed the licensing/trial system entirely — no trial, activation, or feature gating
- Relicensed under the Apache License 2.0
- Rebranded to **PDF Studio** by Leon Priest; name/version centralised in `about_dialog.py`
- Unified all persisted settings under a single store

### v1.1 — OCR & Export
- `Run OCR`, `Export As → Word`, `Export As → Excel`; preference persistence; unsaved `*`; fuller Undo/Redo

### v1.0 — Initial release
- Full viewer, annotations/markup/signatures/stamps/redactions, forms, page management, merge/split, extract, AES-256 protection, nav panel, search, bookmarks, TOC, recent files

---

## License

Apache License 2.0 — see `LICENSE.txt` for the full text and `NOTICE` for
third-party attributions.
