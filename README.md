# PDF Studio

> **Phase 4.2 Windows selection fix:** scanned-text editing now preserves the
> last valid drag endpoint when Windows / Qt reports a collapsed mouse-release
> position. OCR starts only after the release event returns to the event loop,
> preventing a visible selection from being discarded before the editor opens.


A free, full-featured PDF reader and editor built with Python and PyQt6.

Created by **Leon Priest** ([github.com/7h3v01d](https://github.com/7h3v01d)) and released
under the **Apache License 2.0** — free to use, modify, and share.

---

## Features

### Viewing & Navigation
- **Open & View** — single-page and continuous scroll view modes, fit-width/fit-page zoom, rotate, dark mode, full-screen
- **Navigation Panel** — collapsible, resizable sidebar: Table of Contents, Bookmarks, Annotations, Forms, Page Thumbnails
- **Search** — full-text search with next/previous result navigation
- **Recent Files** — quick-open split-button for the last 10 opened files
- **Metadata Viewer** — inspect document properties

### Annotations & Markup
- **Annotations** — sticky notes, highlights, underlines, strikethrough, freehand drawing, eraser
- **Signatures & Stamps** — add a signature by **drawing** it or **importing a PNG/JPG image** (with automatic white-background removal for scans); **drag-and-drop** an image straight onto the page; insert text stamps. (Image stamp, not a cryptographic/digital signature.)
- **Redactions** — mark and permanently apply redactions
- **Scanned Text Replacement** — select text in a scan, OCR it, edit the result, preview the replacement, then apply a reversible overlay or a permanent pixel-removing replacement
- **Annotations Panel** — sidebar listing all annotations with jump-to and delete actions

### Editing & Page Management
- **Existing PDF Form Filling** — detects AcroForm fields and exposes text, multiline, checkbox, radio, dropdown, and list controls directly over the page
- **Forms Panel** — lists every field, identifies required/read-only fields, jumps to a selected field, toggles field highlighting, and resets one page or the whole form
- **Form Designer** — creates genuine text, checkbox, dropdown, date, linked Yes/No radio, signature, and initials fields on ordinary or scanned PDFs; select, move, resize, rename, configure, and delete fields before saving
- **OCR-Assisted Form Detection** — analyses the current page for labels, answer lines, outlined boxes, and checkbox squares; previews confidence-ranked suggestions and creates only the fields the user explicitly approves
- **Safe Form Flattening** — creates a separate, verified non-editable copy while preserving the editable original
- **Page Management** — add blank pages, remove pages, reorder via drag-and-drop thumbnails or move up/down
- **Full Undo/Redo** — annotations, markup, page insert/delete/move (including drag-to-reorder)
- **Merge & Split** — merge multiple PDFs or split one into separate files
- **Extract Pages** — extract a range or selection to a new PDF
- **Password Protection** — open password-protected PDFs; encrypt saved PDFs with AES-256, set open/permissions passwords and granular permission flags

### Existing PDF forms

When a PDF already contains interactive AcroForm fields, PDF Studio detects them
automatically. The **Forms** section in the left navigation panel lists every
field and lets you double-click one to jump directly to it. Fillable fields are
highlighted in blue by default; read-only fields are shown distinctly.

Supported controls include single-line and multiline text, checkboxes, radio
buttons, dropdowns, and list boxes. Signature fields are detected, but this
release does not perform cryptographic PDF signing. Embedded PDF JavaScript and
push-button actions are deliberately not executed.

Use **Tools → Reset Form Fields on Page** or **Reset All Form Fields** when
needed. **Flatten Form to Copy…** creates a separate PDF where the visible
answers are permanently baked into the pages and verifies that no interactive
widgets remain. It refuses to overwrite the editable original.

Form changes mark the document as unsaved. Closing PDF Studio or opening another
file prompts to save, discard, or cancel, and `Ctrl+S` persists field values
using a legal incremental PDF save.

### Creating fillable fields

Open the **Forms** section and enable **Design mode**. Choose **Text Field**,
**Checkbox**, **Dropdown**, **Date**, **Yes / No**, **Signature**, or **Initials**,
then click or drag on any ordinary or scanned page. Choose **Select** to
click an existing field, drag inside it to move it, or drag the lower-right
handle to resize it. **Properties…** changes the field name, tooltip, required
state, read-only state, multiline behaviour for ordinary text fields, and the
choice list or custom-entry setting for dropdowns.

Designer changes are real AcroForm widgets, not decorative rectangles. Press
`Ctrl+S`, reopen the PDF, and switch Design mode off to fill the fields normally.
The **Yes / No** tool creates a linked, mutually exclusive radio pair. Signature
and initials controls are genuine unsigned PDF signature placeholders; PDF
Studio preserves them but does not yet perform certificate-backed signing.

### OCR-assisted form detection

For scanned or complex forms, open the **Forms** section and choose **Detect
Current Page...**. PDF Studio uses an existing text layer when one is available;
otherwise it runs Tesseract OCR on that page. It combines recognised labels with
vector or scanned lines and boxes, then draws temporary coloured suggestion
outlines over the page.

Choose **More suggestions**, **Balanced**, or **High confidence**, then run the
detector. A resizable **Review Smart Form Suggestions** window opens automatically.
Its table shows whether each proposal will be used, the field type, detected
label, confidence, and the reason it was suggested. Untick anything incorrect
and press **Create Checked**. You can also check all, uncheck all, or keep only
suggestions at 80% confidence or above.

No PDF field is created until that confirmation. The Forms sidebar now keeps only
a compact detection summary plus **Review Suggestions...** and **Clear** buttons,
and the complete Forms panel scrolls instead of crushing controls when its
navigation section is short. Existing fields are excluded from overlapping
suggestions, and inferred answer areas receive lower confidence than fields
supported by visible geometry.

This first detector intentionally favours dependable text, date, checkbox,
signature, and initials fields. It does not claim perfect automatic layout
understanding; ambiguous fields should still be placed or corrected with Form
Designer.


### Editing text in a scanned page

A scanned PDF is a picture, so its letters are not native editable text. PDF
Studio now provides a controlled **Edit Text** workflow that replaces a selected
region without pretending the scan is a Word document:

1. Click **Edit Text** in the **EDIT SCAN** toolbar group, or choose
   **Tools → Edit Scanned Text...**.
2. Drag a rectangle around the word or line you want to change and release the
   mouse button. The page explicitly retains the drag through release.
3. A progress window appears immediately. PDF Studio uses an existing text layer
   when available; otherwise it OCRs only the selected region with one Tesseract
   recognition pass. This first release uses Tesseract's
   English model for selected-region OCR; manual replacement remains available
   for other languages.
4. Correct the recognised text, choose alignment, font size, text colour, and the
   sampled background colour, then review the live preview.
5. Apply either:
   - **Reversible white-out overlay** — recommended. Creates one opaque FreeText
     annotation, preserves the scan underneath, supports Ctrl+Z, and can be
     removed from the Annotations panel.
   - **Permanent erase + replacement** — removes text, line art, and image pixels
     inside the rectangle before inserting the new text. This cannot be undone in
     the current editing session.

Permanent replacements and applied redactions require **Save As**. PDF Studio
forces a clean, compact rewrite under a new filename so removed page content is
not left behind in an incremental PDF revision and the original remains
preserved. OCR failure does not block the editor; replacement text can still be
entered manually.

### How to confirm the OCR text layer

The OCR layer is intentionally invisible: the page should continue to look like
the original scan. After OCR, open the generated `_ocr.pdf` file (or choose
**Replace original**) and verify it in one of these ways:

1. Press **Ctrl+F**, enter a word visible on the scan, and press Enter.
2. Choose **Edit → Select All Text on Page**, then paste into Notepad.
3. Drag across a line, press **Ctrl+C**, and paste the copied text elsewhere.

PDF Studio now re-opens the saved result internally and reports the number of
searchable words it could verify. It will no longer report a successful OCR job
when no searchable text was embedded.

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
forms_panel.py           # AcroForm inventory, filling, and Form Designer controls
form_designer_core.py    # Tested create/move/resize/delete/property operations
form_detection_core.py   # OCR/layout analysis and approved-suggestion creation
form_detection_worker.py # Background current-page OCR and geometry detection
form_detection_review_model.py # Testable suggestion review/selection model
form_detection_review_dialog.py # Resizable approval table for detected fields
scan_text_edit_core.py  # Tested reversible/permanent scanned-text operations
scan_text_edit_dialog.py # OCR result editor and live replacement preview
scan_text_edit_worker.py # Background selected-region Tesseract worker
form_field_dialog.py     # Field-name, tooltip, flags, and multiline properties
password_dialog.py       # Password prompt and encryption settings dialogs
signature_dialog.py      # Draw-your-own signature dialog
merge_split_dialog.py    # Merge / split PDF dialog
extract_pages_dialog.py  # Extract pages dialog
ocr_dialog.py            # OCR settings, progress, background worker
tesseract_setup.py       # Tesseract detection, validation, saved location
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

The Python OCR components (`pytesseract` and `Pillow`) are installed from the
main `requirements.txt` and bundled into release builds. The only external
component is **Tesseract-OCR** itself.

| Dependency | Purpose | Download |
|---|---|---|
| **Tesseract-OCR** | OCR engine | [Windows installer](https://github.com/UB-Mannheim/tesseract/wiki) |

PDF Studio searches the normal Windows install locations automatically and
configures Tesseract directly. Users do **not** need to edit the system PATH.
If detection fails, the OCR dialog provides **Locate Tesseract…**, **Detect
Again**, and **Get Tesseract** controls. Poppler is not required; pages are
rendered directly with PyMuPDF.

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

## Testing

Install the development requirements once, then run the complete structural form suite:

```bat
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
run_tests.bat
```

Or run pytest directly:

```bat
.venv\Scripts\python.exe -m pytest tests -v
```

The suite verifies existing-form filling and flattening, Form Designer and Smart
Detection persistence, plus scanned-text overlays, overlay removal, permanent
text, vector-line, and raster replacement, background sampling, metadata, and
text fitting.

## Building a Windows .exe

**Build in a clean, isolated venv** — this is the #1 thing that prevents build
failures. If unrelated packages (a second Qt binding like PyQt5, pygame, your
other projects on the path, etc.) are visible to PyInstaller, the build can pull
them in or abort with errors like *"multiple Qt bindings packages"*.

**Easiest — one command:**

```bat
build_clean.bat
```

This creates a throwaway `.buildenv`, installs *only* PDF Studio's dependencies
plus PyInstaller, builds, and leaves the exe in `src\dist\`.

**Manual, in your own venv:**

```bat
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install pyinstaller
python -m pip install -r requirements.txt
cd src
python -m PyInstaller "PDF Studio.spec"
```

> **Always use `python -m PyInstaller`, not `pyinstaller`.** A bare `pyinstaller`
> command uses whichever copy is first on your PATH — often a *global* one that
> builds against your global environment (with all its unrelated packages),
> even when a venv is "activated". `python -m PyInstaller` uses the active
> interpreter's PyInstaller and its packages.

The executable appears in `src\dist\`.

**Optional features in the .exe:** Word/Excel export and OCR need extra Python
packages (already listed in `requirements.txt`). Whatever is installed in the
build environment gets bundled automatically. For a leaner exe with just the
viewer + Word export, install only `PyMuPDF PyQt6 pdf2docx pywin32` instead of
the full `requirements.txt`. (`numpy` must remain available — `pdf2docx` needs
it — so the spec no longer excludes it.)
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
| `Ctrl+Shift+P` | Print preview | | |
| `Ctrl+Q` | Quit | `F3 / Shift+F3` | Next / prev result |
| `Ctrl+Z / Ctrl+Y` | Undo / Redo | `Ctrl+C` | Copy text |
| `← / →` | Prev / next page | `Ctrl+B` | Add bookmark |
| `Ctrl+Home / End` | First / last page | `Escape` | Cancel active tool |
| `Ctrl++ / Ctrl+-` | Zoom in / out | `Ctrl+Shift+H / F` | Fit width / page |

---

## Changelog

### v3.2-alpha4 - PDF coordinate conversion correction

- Corrected PyMuPDF matrix inversion throughout page-coordinate conversion.
- Scanned-text selections now retain their real PDF rectangle instead of collapsing to an empty box.
- Also repairs click placement for signatures and stamps, freehand coordinate persistence, and point-based markup lookup.
- Added regression tests proving inverse matrices map points and rectangles correctly.

### v3.2-alpha3 - Windows drag-release handoff fix

- Preserve the last valid mouse-move endpoint instead of blindly trusting a collapsed Windows release coordinate.
- Map the global release position back into page coordinates as an independent fallback.
- Choose the endpoint that represents the largest completed drag rectangle.
- Start OCR on the next Qt event-loop turn after mouse release.
- Show an explicit **Selection captured** status before preparing the editor.
- Added drag-endpoint and minimum-selection regression tests.

### v3.2-alpha2 — scanned-text editor handoff reliability

- Explicitly retain the page mouse grab until a selected region is released.
- Show an immediate **Preparing Scanned-Text Editor** progress window.
- Reconstruct OCR text and confidence from one Tesseract data pass instead of launching recognition twice.
- Keep the OCR worker alive until its thread has actually finished.
- Open the manual replacement editor if OCR finishes without returning a result.
- Added OCR-data reconstruction and malformed-confidence tests.

### v3.2-alpha1 — OCR-assisted scanned-text replacement

- Added an **Edit Text** region tool for scanned pages.
- Uses an existing text layer when available and Tesseract OCR otherwise.
- Added a resizable editor with recognised text, replacement text, confidence, live preview, auto-fit font sizing, alignment, and colour controls.
- Added reversible opaque FreeText replacements with Ctrl+Z/Redo and Annotations-panel deletion.
- Added permanent erase-and-replace mode that removes vector text, line art, and raster pixels under the selected rectangle.
- Permanent removals now force Save As and a clean full PDF rewrite, preserving the source and avoiding incremental-revision residue.
- Added manual-entry fallback when OCR is unavailable or cannot read the region.
- Added vector-text, vector-line, raster-pixel, metadata, background-sampling,
  validation, and overlay-removal tests.

### v3.1-alpha2 — Smart Detection review UI

- Moved suggestion approval from the cramped sidebar into a resizable review dialog.
- Added full-width confidence, label, type, rationale, bulk-check, and create controls.
- Made the Forms section internally scrollable at constrained sidebar heights.

### v3.0 — Print preview
- **File → Print Preview…** (`Ctrl+Shift+P`) shows what will print before sending it to the printer
- Print and preview share one rendering path, so the preview always matches the printed output

### v3.1-alpha1 — OCR-assisted form detection

- Added current-page detection for labels, answer lines, outlined boxes, and checkbox squares.
- Uses native PDF text when available and Tesseract OCR for image-only pages.
- Added confidence filtering, page overlays, checkable suggestions, and explicit approval before field creation.
- Existing fields suppress overlapping suggestions; inferred geometry is deliberately lower confidence.
- Added raster/vector detection and approved-field persistence tests.

### v3.0-alpha3 — Rich form controls

- Added dropdown fields with editable choice lists.
- Added DD/MM/YYYY date fields with an in-app calendar control.
- Added linked Yes / No radio groups.
- Added genuine unsigned PDF signature and initials fields.
- Extended field properties and structural persistence tests.

### v3.0-alpha2 — Form Designer foundation
- Design/fill mode switch in the Forms sidebar and Tools menu
- Create genuine AcroForm text fields and checkboxes on existing or scanned pages
- Select, move, lower-right resize, rename, configure, and delete fields
- Required, read-only, tooltip, and multiline field properties
- Boundary-safe geometry, unique automatic names, unsaved-change protection, and reopen persistence tests

### v3.0-alpha1 — Existing forms foundation
- Forms sidebar with field inventory, jump-to-field, highlighting, page/all reset
- Reliable text, multiline, checkbox, radio, dropdown, and single-choice list filling
- Unsaved-form protection and corrected incremental save persistence
- Safe flatten-to-copy with structural and visual verification

### v2.9 — Printing fixed
- **Fixed: printing produced a single blank page.** The code called `QPrinter.pageRect(QPrinter.Unit.Pixel)`, but PyQt6 has no `Unit.Pixel` (it is `DevicePixel`). The resulting AttributeError was swallowed by a bare `except`, after the print job had already been opened — so the printer received an empty job. Page geometry now comes from the painter's viewport.
- Pages are now rendered at the printer's resolution instead of being rendered at 72 dpi and upscaled, so output is sharp rather than blocky
- Print failures now show a real error dialog instead of a silent status-bar message

### v2.8 — Built-exe runtime fixes
- LibreOffice conversion from the built .exe now works: external programs are launched with a cleaned environment (the PyInstaller temp dir is removed from PATH), fixing "bootstrap.ini is corrupt"; the LibreOffice profile now uses a valid file URI
- Build spec now bundles pdf2docx's native dependencies (opencv/cv2, fire), fixing "missing pdf2docx" for Word export in the .exe
- Word-export error now reports the real import failure instead of a generic message

### v2.7 — Build fixes
- Build spec no longer collect_all's fontTools (which pulled in PyQt5 and aborted the build with a "multiple Qt bindings" error); excludes other Qt bindings and heavy unused packages explicitly
- Build scripts use `python -m PyInstaller` so the active venv's PyInstaller is used, not a global one
- Added `build_clean.bat` for a foolproof isolated build

### v2.6 — Dark-mode popup + .exe export fix
- Message-box popups (e.g. "Set as Default PDF App") now use a themed background so their text is legible in dark mode
- Build spec now bundles optional packages (pdf2docx, etc.) when installed and no longer excludes numpy, fixing "missing pdf2docx" on Word export from the built .exe

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
