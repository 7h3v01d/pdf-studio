![PDF Studio](docs/images/banner.png)

**A Windows-first PDF reader and editor built with Python, PyQt6, and PyMuPDF.**

PDF Studio combines everyday PDF viewing and annotation with OCR, interactive
forms, form design, smart form detection, and controlled editing of text inside
scanned pages.

Created by **Leon Priest** — [github.com/7h3v01d](https://github.com/7h3v01d)  
Application source released under **Apache-2.0**; bundled dependency obligations remain under review.

![PDF Studio application window](docs/images/screenshot.png)

## Current release

| | |
|---|---|
| **Version** | `3.2.0-alpha12` |
| **Status** | Internal alpha — integrity hardening in progress |
| **Primary platform** | Windows 10 / 11 |
| **Python** | 3.11 for the supported build workflow |
| **Automated tests** | 117 passing in the source package |
| **OCR engine** | Tesseract, detected automatically without editing PATH |

The current release closes the last confidentiality gap in save recovery. Original
transaction backups now live under PDF Studio's controlled local application-data
recovery area rather than beside user documents. A successful save cannot silently
leave pre-redaction copies behind: cleanup is verified, residual copies trigger a
prominent privacy warning, and the user can retry deletion or open the exact folder.
Office imports now use full-UUID, marker-owned workspaces under a dedicated cache
root, so filename resemblance alone can never establish deletion ownership.

> **Distribution status:** this build remains an internal alpha. Public and family
> binary distribution is deliberately blocked by `release/release_policy.json`
> until the PyMuPDF/MuPDF and PyQt6 licensing strategy is explicitly resolved,
> approved, and recorded.

---

## Highlights

### Read and navigate

- Branded startup splash with a 4.5-second minimum display and smooth fade
- Single-page and continuous-scroll viewing
- Fit width, fit page, zoom, rotation, full screen, and dark mode
- Table of contents, bookmarks, annotations, forms, and page thumbnails
- Full-text search with next/previous navigation
- Recent files and document metadata
- Password-protected PDF opening
- Print and print preview

### Annotate and organise

- Notes, highlights, underlines, strikethrough, and freehand drawing
- Eraser, redaction, stamps, and image signatures
- Drag-and-drop signature images
- Undo and redo for supported editing operations
- Insert, remove, reorder, extract, merge, and split pages
- Save, Save As, and Save a Copy

### OCR and scanned documents

- Add an invisible, searchable OCR text layer
- Verify that searchable words were actually embedded
- Select and replace text inside a scanned page
- Choose reversible white-out overlays or permanent erase-and-replace
- Sample the page background and preview replacement text
- Preserve the original PDF when permanent changes require a clean rewrite

### Interactive forms

- Fill existing AcroForm fields
- Create text fields, checkboxes, dropdowns, dates, radio groups, signatures,
  and initials placeholders
- Move, resize, rename, configure, and delete fields
- Detect likely form fields from labels, lines, boxes, and checkbox geometry
- Review confidence-ranked suggestions before creating anything
- Flatten a completed form to a separate non-editable copy

### Import and export

- Open Word, Excel, OpenDocument, RTF, and CSV files through Microsoft Office
  or LibreOffice conversion
- Treat Office conversions as temporary viewing caches: `Ctrl+S` always opens
  **Save As**, defaults to the original document folder and `.pdf` name, and
  removes the temporary conversion after the session ends
- Export PDF pages to PNG, JPEG, WebP, TIFF, BMP, or static GIF
- Choose current page, all pages, or a discontiguous page range
- Select image resolution up to 1200 DPI, lossy quality, and transparency where supported
- Export PDF content to Word with `pdf2docx`
- Export detected tables to Excel with `tabula-py`
- Encrypt saved PDFs with AES-256 and configurable permissions

---

## Quick start on Windows

### Run from source

1. Install Python 3.11.
2. Extract the project.
3. Run:

```bat
setup.bat
```

The setup script creates `.venv`, installs the core dependencies, and generates
helper scripts. Then launch PDF Studio with:

```bat
run.bat
```

The equivalent manual commands are:

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe src\pdf_reader.py
```

### Build the Windows executable

Use the isolated build script:

```bat
build_clean.bat
```

It creates a temporary `.buildenv`, installs only the required build packages,
and runs PyInstaller. The result is written under:

```text
src\dist\
```

Using the clean build environment avoids accidental inclusion of unrelated
packages or a second Qt binding.

### Startup splash

PDF Studio displays `assets/splashscreen.png` immediately at launch. The main
window is prepared behind it, the artwork remains visible for at least 4.5
seconds, and then fades out over 350 milliseconds. The startup path uses Qt
timers rather than `time.sleep()`, so the application does not deliberately
freeze its event loop. If the splash asset cannot be loaded, PDF Studio falls
back to a normal launch instead of refusing to start.

---

## Tesseract OCR setup

The Python OCR packages are included in `requirements.txt`. OCR also requires
the external **Tesseract-OCR** application.

Recommended Windows installer:
[UB Mannheim Tesseract builds](https://github.com/UB-Mannheim/tesseract/wiki)

PDF Studio searches common installation locations and the Windows registry,
then configures `pytesseract` with the exact path to `tesseract.exe`.

**Users do not need to edit the Windows system PATH.**

When automatic detection fails, the OCR window provides:

- **Detect Again**
- **Locate Tesseract…**
- **Get Tesseract**

Poppler is not required; PDF pages are rendered directly through PyMuPDF.

---

## Core workflows

### Add a searchable OCR layer

1. Open a scanned PDF.
2. Choose **Tools → Run OCR…**.
3. Select the page range and installed language.
4. Save to a new `_ocr.pdf` file or deliberately replace the source.
5. Open the OCR result and test it with `Ctrl+F` or copy/paste.

The page should still look like the original scan. The added text is
intentionally invisible. PDF Studio verifies the saved result and refuses to
report success when no searchable words were embedded.

When **Save As** is used while redaction boxes are still pending, PDF Studio now
requires an explicit choice: apply them transactionally, save without them and
discard the boxes, or cancel. Pending destructive state is never silently lost
during the new-document reopen.

### Fill an existing PDF form

Interactive fields are detected automatically. Open **Forms** in the navigation
panel to list fields, jump to them, toggle highlighting, or reset values.

Supported controls include:

- single-line and multiline text
- checkboxes
- radio buttons
- dropdowns
- single-choice list boxes
- unsigned signature fields

Form edits mark the document as unsaved and are protected by the normal
save/discard/cancel prompts. Embedded PDF JavaScript and push-button actions are
not executed.

### Create a fillable form

1. Expand **Forms**.
2. Enable **Design mode**.
3. Select a field type.
4. Click or drag on the page to place it.
5. Use **Select** to move or resize the field.
6. Open **Properties…** to configure its name, tooltip, flags, or choices.
7. Save, turn Design mode off, and fill the form normally.

The designer creates genuine AcroForm widgets rather than decorative overlays.

### Detect fields on a scanned form

1. Open **Forms → Smart Form Detection**.
2. Choose **More suggestions**, **Balanced**, or **High confidence**.
3. Select **Detect Current Page…**.
4. Review the proposals in the resizable review window.
5. Untick incorrect suggestions and choose **Create Checked**.

Detection can use native PDF text or Tesseract OCR. Existing fields suppress
overlapping suggestions, and no field is created without explicit approval.

### Replace text in a scan

1. Choose **Tools → Edit Scanned Text…**. The toolbar shortcut may also be
   available when the full toolbar width is visible.
2. Drag a tight rectangle around a word, number, or short line.
3. Release the mouse and wait for **Preparing Scanned-Text Editor**.
4. Correct the recognised text and review the preview.
5. Choose one of the following:

**Reversible white-out overlay**

- Preserves the original scan beneath an opaque FreeText annotation
- Supports undo and redo
- Can be removed from the Annotations panel

**Permanent erase and replacement**

- Removes text, line art, and image pixels inside the selected rectangle
- Burns the replacement into the page
- Requires confirmation
- Forces Save As to a new `_edited.pdf` file
- Performs a clean rewrite so removed content is not retained in an incremental
  revision

Selected-region OCR currently defaults to Tesseract's English model. Other
languages can still be entered manually in the replacement editor.

### Flatten a completed form

Use **Flatten Form to Copy…** to create a separate PDF whose visible answers are
baked into the pages and whose interactive widgets have been removed. PDF
Studio verifies the flattened result and does not overwrite the editable source.

---

### Export PDF pages as images

Choose:

```text
File → Export As → Image Files (.png, .jpg, .webp, .tiff, .bmp, .gif)…
```

Then select:

- **All pages**, **Current page**, or a range such as `1-3, 6, 9-10`
- PNG, JPEG, WebP, TIFF, BMP, or GIF
- Resolution from 36 to 1200 DPI; 300 DPI is a strong default for posters and printing
- JPEG/WebP quality
- Transparent background for PNG, WebP, and TIFF

A single selected page is saved to one chosen image file. Multiple selected
pages are written as numbered files such as `poster_page_001.png`. GIF export is
intentionally static: a multi-page PDF produces one GIF per selected page, not
an animation.

The exporter stages every image before replacing destination files. A failed or
cancelled multi-page run therefore does not leave a half-exported set or destroy
pre-existing images.

## Optional integrations

The core reader, editor, forms, and OCR Python components are installed from
`requirements.txt`. These integrations are optional.

### Export to Word

```bat
.venv\Scripts\python.exe -m pip install pdf2docx
```

### Export to Excel

```bat
.venv\Scripts\python.exe -m pip install tabula-py openpyxl pandas
```

`tabula-py` also requires a Java runtime.

### High-fidelity Word and Excel import

```bat
.venv\Scripts\python.exe -m pip install pywin32
```

On Windows, PDF Studio prefers Microsoft Word or Excel automation when Office is
installed. LibreOffice is used as the free fallback converter.

---

## Testing

Install the development requirements once:

```bat
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Run the test suite with:

```bat
run_tests.bat
```

or:

```bat
.venv\Scripts\python.exe -m pytest tests -v
```

Current expected result:

```text
81 passed
```

The suite covers:

- existing-form value persistence and flattening
- field creation, naming, movement, resizing, properties, and deletion
- dropdown, date, radio, signature, and initials structures
- smart-detection review and approved-field persistence
- reversible scanned-text overlays and metadata
- permanent vector-text, vector-line, and raster-pixel removal
- background sampling and font fitting
- mouse-selection endpoint handling
- inverse-matrix point and rectangle conversion
- strict page-range parsing and discontiguous page selection
- transactional redaction, save, flatten, import, merge, split, and extract helpers
- complete page-state remapping and undo snapshots
- staged DOCX/XLSX validation and destination preservation
- worker-dialog close/cancellation guards and thread-completion handoff
- annotation-sidecar retirement and atomic JSON persistence
- transactional document-open rollback
- PNG/JPEG/GIF rendering, DPI dimensions, and transparent PNG output
- transactional cleanup when a later page fails
- startup minimum-duration timing and active-screen splash scaling
- document-session redaction binding and all-plan validation
- transactional redaction clones that leave the active PDF untouched on failure
- bytes-safe single signature-image persistence
- atomic PDF destination preservation for save/copy/flatten failures
- valid and authenticated encrypted staged output
- isolated LibreOffice workspaces, return-code checks, and PDF validation
- central insert/delete/move remapping for annotations, markup, redactions,
  bookmarks, searches, selections, and page-operation undo snapshots

These automated tests validate the document model and critical conversion paths.
They do not replace final Windows GUI interaction testing.

---

## Project structure

```text
src/
├── pdf_reader.py                    Application entry point
├── pdf_reader_app.py                Main application logic
├── pdf_reader_ui.py                 Menus, toolbars, and navigation UI
├── pdf_page_widget.py               Page rendering and pointer interaction
├── pdf_scroll_area.py               Zoom and scrolling behaviour
├── pdf_utils.py                     Shared PDF operations and coordinates
├── annotations_panel.py             Annotation inventory and controls
├── forms_panel.py                   Forms inventory and designer controls
├── form_designer_core.py            Tested AcroForm editing operations
├── form_field_dialog.py             Field properties editor
├── form_detection_core.py           OCR/layout form suggestion engine
├── form_detection_worker.py         Background page analysis
├── form_detection_review_model.py   Testable review-state model
├── form_detection_review_dialog.py  Suggestion approval window
├── scan_text_edit_core.py           Replacement and redaction engine
├── scan_text_edit_worker.py         Selected-region OCR worker
├── scan_text_edit_dialog.py         Replacement editor and preview
├── ocr_dialog.py                    Full-document OCR workflow
├── tesseract_setup.py               Tesseract discovery and validation
├── merge_split_dialog.py            Merge and split operations
├── extract_pages_dialog.py          Page extraction
├── export_dialog.py                 Word, Excel, and image export
├── image_export_core.py             Tested page rendering and transactional output
├── pdf_job_core.py                  Transactional merge, split, and extraction jobs
├── office_export_core.py            Atomic DOCX/XLSX staging and validation
├── annotation_integrity_core.py     Native/sidecar annotation authority rules
├── document_integrity_core.py       PDF staging, snapshots, and validation
├── page_state_core.py               Page remapping and native move adapter
├── save_bundle_core.py              Atomic PDF-plus-sidecar commit and rollback
├── splash_screen.py                 Transparent splash window and fade animation
├── startup_splash_core.py           Tested timing and screen-fitting rules
├── signature_dialog.py              Drawn signature editor
├── password_dialog.py               Opening and encryption passwords
├── undo_stack.py                    Undo/redo command stack
└── about_dialog.py                  Product metadata and About window

tests/                               Structural and regression tests
docs/                                User Manual, Easy Guide, and documentation images
├── images/                          README/manual artwork only
assets/                              Runtime startup assets only
└── splashscreen.png                 Boot splash used by source and packaged builds
```

Repository boundary: `assets/` is reserved for runtime application resources and
currently contains only `splashscreen.png`. README and manual artwork belongs in
`docs/images/`. The release audit enforces this separation.

Application metadata is centralised in `src/app_metadata.py`:

```python
APP_NAME = "PDF Studio"
APP_VERSION = "3.2.0-alpha12"
COMPANY_NAME = "Leon Priest"
```

The PyInstaller output name is configured in `src/PDF Studio.spec`.

---

## Known limitations

- This is an alpha release and should not be the only copy of important files.
- Certificate-backed digital signing is not implemented. Signature fields and
  image signatures are supported, but they are different features.
- Selected-region OCR currently defaults to English.
- Scanned-text replacement approximates the original typeface; it does not
  reconstruct the source font perfectly.
- Automatic form detection is intentionally conservative and still requires
  review.
- Complex Word/Excel conversion fidelity depends on Microsoft Office or
  LibreOffice being installed.
- Multi-selection list boxes currently retain one selected value through the
  PyMuPDF-backed form layer.

---

## Windows file association

From inside PDF Studio, choose:

```text
File → Set as Default PDF App…
```

The application registers itself per-user and opens Windows Default Apps for the
final confirmation. Windows does not allow an application to silently take over
`.pdf` associations.

Command-line alternatives:

```bat
register_pdf.bat
unregister_pdf.bat

"PDF Studio.exe" --register
"PDF Studio.exe" --register --pdf-only
"PDF Studio.exe" --unregister
```

---

## Keyboard shortcuts

| Shortcut | Action | Shortcut | Action |
|---|---|---|---|
| `Ctrl+O` | Open | `Ctrl+S` | Save |
| `Ctrl+Shift+S` | Save As | `Ctrl+P` | Print |
| `Ctrl+Shift+P` | Print preview | `Ctrl+F` | Search |
| `F3` / `Shift+F3` | Next / previous result | `Ctrl+C` | Copy selected text |
| `Ctrl+Z` / `Ctrl+Y` | Undo / redo | `Ctrl+R` | Rotate 90° |
| `Ctrl++` / `Ctrl+-` | Zoom in / out | `Ctrl+Shift+H` | Fit width |
| `Ctrl+Shift+F` | Fit page | `F4` | Toggle navigation panel |
| `F11` | Full screen | `Escape` | Cancel active tool |
| `←` / `→` | Previous / next page | `Ctrl+Home` / `Ctrl+End` | First / last page |
| `Ctrl+B` | Add bookmark | `Ctrl+Q` | Quit |

---

## Diagnostics and support

Open **Help → Diagnostics…** to view or copy a support report containing the
application version, Windows/Python/runtime versions, dependency versions,
Tesseract status, build-manifest information, and the locations of bounded log
files. The report does not include PDF text or document contents. Review paths
before sharing it.

Application logs are written under the current user's local application-data
folder and rotate automatically so they cannot grow without bound.

## Release-assurance workflow

- `build_clean.bat` creates a fresh Python 3.11 environment, validates dependencies, runs tests and the internal release audit, captures exact versions, generates a build manifest, and produces an **internal-only** executable.
- `capture_release_environment.bat` records exact versions from an already passing `.venv`.
- `prepare_release_wheelhouse.bat` downloads those exact packages and records SHA-256 hashes for offline rebuilding.
- `release_check.bat` deliberately fails while licensing/approval gates remain unresolved.
- `build_release.bat` works only after the release policy, exact locks, wheel hashes, clean-machine evidence, and public-release audit all pass.
- `RELEASE_CHECKLIST.md` defines the required Windows 10/11 and licensing sign-off evidence.


## Recent changelog

### 3.2.0-alpha12 — confidential recovery V

- Moved transaction recovery data from document folders into PDF Studio's controlled local application-data recovery directory.
- Added `SaveBundleRecoveryCleanupIncomplete` for saves that commit successfully but leave original recovery copies behind.
- Added verified cleanup retries and a prominent privacy warning with **Retry Deletion** and **Open Recovery Folder** actions.
- Prevented secure-redaction completion claims while pre-redaction recovery copies still exist.
- Replaced filename-based Office-import ownership with full-UUID workspaces, ownership markers, and dedicated `%TEMP%\PDF Studio\Imports` storage.
- Made stale import cleanup require marker-proven ownership and conservative age checks.
- Added confidentiality, controlled-recovery-root, retry-cleanup, and import-ownership regressions; the suite now reports 117 passing tests.

### 3.2.0-alpha12 — recovery integrity IV

- Replaced best-effort save rollback with an explicit recovery protocol.
- Preserved untouched original destination copies until rollback is proven complete.
- Added `SaveBundleRollbackIncomplete` with the original commit error, every failed restoration, and a durable recovery-directory path.
- Added human-readable and JSON recovery manifests beside preserved backups.
- Changed the Save Error UI so it never claims destination preservation after an incomplete rollback.
- Made rollback attempt every committed destination even after an earlier restoration fails.
- Removed partial PDF Studio Office-import caches after failed conversion or validation.
- Added conservative startup cleanup for owned `pdfstudio_import_*.pdf` caches older than seven days.
- Added compounded commit/rollback fault injection and cache-hygiene regressions; the suite now reports 112 passing tests.

### 3.2.0-alpha10 — controller integrity III

- Added a final-index adapter for PyMuPDF page moves and routed toolbar,
  thumbnail, undo, and redo operations through it.
- Added real page-content regression tests for downward, last-position, and
  reverse page moves, plus Qt thumbnail destination translation.
- Made Save As require an explicit apply/discard/cancel decision whenever
  unapplied redaction boxes exist.
- Completed document-open transactions: failed new sessions close and roll back;
  successful sessions close the previous document only after the commit point.
- Marked imported Office sessions as temporary conversions. `Ctrl+S` now invokes
  Save As with `<original-name>.pdf`, and owned cache files are removed safely.
- Replaced independent PDF/sidecar writes with one staged, validated,
  rollback-capable save bundle for the PDF, notes, markup, and bookmarks.
- Released the active source handle only at the atomic commit boundary so Windows
  can replace a same-file destination safely, with in-memory restoration on failure.
- Replaced the false-positive document-open source test with AST-scoped rollback
  assertions and expanded the suite to 103 passing tests.

### 3.2.0-alpha9 — release assurance I

- Added rotating per-user application logs and unhandled-exception capture.
- Added **Help → Diagnostics…** with runtime, dependency, Tesseract, build, and path information.
- Added **Help → Third-Party Licences and Notices…** and bundled licence references.
- Centralised application metadata so diagnostics, About, startup, and build tooling share one version.
- Added a fail-closed release policy that blocks public binaries until a licensing strategy is approved.
- Added exact environment capture, offline wheelhouse hashing/verification, source/build manifests, and executable SHA-256 output.
- Replaced permissive setup/build scripts with Python 3.11 checks, `pip check`, tests, release audit, clean packaging, and explicit failure exits.
- Added separate internal-build and release-approved build paths.
- Added a clean Windows 10/11 release checklist and fail-closed machine-result evidence gate.
- Added eight release-assurance regressions; the suite now reports 89 passing tests.

### 3.2.0-alpha8 — integrity hardening II

- Replaced direct merge and extraction output with validated staged PDF commits.
- Made split output an all-parts transaction with rollback of replaced files.
- Added cooperative cancellation to merge, split, extract, Word, Excel, and image workers.
- Prevented Escape, the Close button, and the window close control from destroying active worker threads.
- Added staged OOXML generation and structural DOCX/XLSX validation before destination replacement.
- Made native PDF annotations authoritative after save and retired duplicate sidecar entries.
- Migrated legacy note/markup sidecars without double-rendering native annotations.
- Added atomic JSON sidecar writes and fail-closed page-reference validation.
- Added bounded PDF snapshot undo for image signatures, stamps, and native annotation deletion.
- Added rollback-safe same-file save preparation and transactional document opening.
- Added 20 orchestration and integrity regressions; the suite now reports 81 passing tests.

### 3.2.0-alpha7 — integrity hardening I

- Added a central document-session reset and opaque session identity.
- Bound pending redactions to the document session that created them.
- Added dirty-state handling for redaction creation/removal, signatures, stamps,
  and annotation-panel deletion.
- Replaced sequential live redaction mutation with validated clone-and-commit.
- Replaced signature sidecar replay with one immediate bytes-safe insertion.
- Made flatten-to-copy operate on a clone and atomically replace only validated output.
- Added staged atomic output for Save As, Save a Copy, and password-protected copies.
- Isolated each LibreOffice conversion in a unique output workspace and required a
  successful return code plus a freshly generated valid PDF.
- Added central page-state mapping and complete sidecar snapshots for page-operation
  undo/redo.
- Added 16 integrity regression tests; the suite now reports 61 passing tests.
- Kept release classification at internal alpha while remaining orchestration and
  licensing work is completed.

### 3.2.0-alpha6 — branded startup splash

- Added the supplied transparent 750 × 500 PDF Studio splash artwork.
- Added a 4.5-second minimum display without blocking `time.sleep()`.
- Added a 350 ms fade before revealing the prepared main window.
- Added active-screen centring, high-DPI scaling, and source/PyInstaller resource lookup.
- Added a non-fatal fallback when the cosmetic splash asset is unavailable.
- Added four startup timing and sizing regression tests.

### 3.2.0-alpha5 — PDF page image export

- Added PNG, JPEG, WebP, TIFF, BMP, and static GIF export.
- Added current-page, all-page, and discontiguous page-range selection.
- Added DPI, quality, and supported-transparency controls.
- Added numbered page filenames for multi-page exports.
- Added transactional staging and rollback protection.
- Added 12 image-export regression tests.

### 3.2.0-alpha4 — PDF coordinate conversion correction

- Corrected the PyMuPDF matrix-inversion implementation.
- Fixed scanned-text selections collapsing into empty PDF rectangles.
- Corrected the same conversion path for signatures, stamps, freehand
  annotations, and point-based markup lookup.
- Added inverse-matrix point and rectangle regression tests.

### 3.2.0-alpha3 — Windows selection handoff

- Preserved the last valid drag endpoint when release coordinates collapse.
- Added local, global, and last-painted endpoint candidates.
- Queued OCR after the mouse-release event returned to Qt.
- Added selection-state and minimum-size regression tests.

### 3.2.0-alpha2 — scanned-text OCR reliability

- Added a visible preparation window.
- Reduced selected-region OCR to one Tesseract data pass.
- Hardened worker/thread lifetime and abnormal-exit handling.
- Opened the editor for manual replacement when OCR fails.

### 3.2.0-alpha1 — scanned-text replacement

- Added selected-region OCR and replacement preview.
- Added reversible overlay and permanent erase-and-replace modes.
- Added clean-rewrite Save As protection for permanent removal.

### 3.1.0-alpha2 — Smart Detection review dialog

- Moved proposal review out of the cramped navigation sidebar.
- Added resizable confidence, label, rationale, and bulk-selection controls.
- Made the Forms panel internally scrollable.

### 3.1.0-alpha1 — OCR-assisted form detection

- Added native-text and Tesseract-backed current-page analysis.
- Added label, line, box, checkbox, date, and signature suggestions.
- Added explicit approval before creating persistent AcroForm fields.

### 3.0.0-alpha3 — rich form controls

- Added dropdowns, date fields, linked Yes/No radios, signatures, and initials.

### 3.0.0-alpha2 — Form Designer

- Added genuine field creation, selection, movement, resizing, properties, and
  deletion.

### 3.0.0-alpha1 — existing forms

- Added form detection, filling, persistence, reset, and verified flattening.

---

## Documentation

The project includes:

- `docs/PDF_Studio_Manual.pdf`
- `docs/PDF_Studio_Easy_Guide.pdf`
- Markdown sources and build scripts for both documents

---

## License

Copyright © 2025–2026 Leon Priest.

Licensed under the [Apache License 2.0](LICENSE.txt). You may use, modify, and
distribute the project subject to the licence terms and preservation of the
required notices.
