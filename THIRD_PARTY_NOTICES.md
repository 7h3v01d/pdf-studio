# PDF Studio — Third-Party Licences and Notices

**Release status:** internal development alpha. Binary redistribution has not
been approved. This file is an engineering inventory, not legal advice.

PDF Studio depends on or can invoke the following software. A distributor must
review the exact versions and licence texts included in the final build.

## Required Python runtime components

### PyMuPDF / MuPDF

- Purpose: PDF rendering, editing, forms, redaction and document output.
- Licence choice published by the project: GNU Affero General Public License
  (AGPL) or a commercial licence from Artifex.
- Bundled reference text: `licenses/AGPL-3.0-PyMuPDF-COPYING.txt` and `licenses/AGPL-3.0.txt`.
- Project: https://pymupdf.readthedocs.io/

### PyQt6 and Qt 6

- Purpose: desktop user interface.
- PyQt6 licence choice published by Riverbank: GPL version 3 or a commercial
  Riverbank licence. PyQt6 is not offered under the LGPL.
- Riverbank's GPL wheels include the corresponding Qt libraries; those Qt
  libraries carry their own licence obligations.
- Bundled reference texts: `licenses/GPL-3.0.txt` and
  `licenses/LGPL-3.0.txt`.
- Project: https://www.riverbankcomputing.com/software/pyqt/

### Pillow

- Purpose: image conversion and encoding.
- Licence: HPND-style Pillow licence.
- Bundled text: `licenses/Pillow-License.txt`.

### pytesseract

- Purpose: Python integration with the separately installed Tesseract OCR
  executable.
- Licence: Apache License 2.0.
- Bundled text: `licenses/pytesseract-License.txt`.

## Build tooling

### PyInstaller

- Purpose: creation of the Windows executable.
- PyInstaller is distributed under GPL terms with a specific exception that
  permits bundling and distributing applications, subject to dependency
  licences. PyInstaller itself is build tooling and is not intentionally
  shipped as an importable application dependency.
- Project: https://pyinstaller.org/

## Separately installed or optional external software

### Tesseract OCR

Tesseract is installed separately by the user and is not bundled with PDF
Studio. It is licensed under Apache License 2.0.

### LibreOffice

LibreOffice may be invoked as an external application for Office-to-PDF
conversion. It is not bundled by PDF Studio. LibreOffice has its own MPL/LGPL
licensing and notices.

### Microsoft Office

When present, optional Windows automation may use the user's separately
licensed Microsoft Office installation. Microsoft Office is not bundled.

## PDF Studio source licence versus bundled distribution

The PDF Studio application source currently declares Apache License 2.0.
That declaration does not by itself resolve the obligations created when a
binary bundles GPL/AGPL dependencies. Before any public or family binary is
distributed, the project owner must deliberately choose and document a
compatible distribution strategy, such as:

1. distributing the complete combined work under terms satisfying the GPL and
   AGPL obligations, including corresponding source and notices; or
2. acquiring suitable commercial licences for PyMuPDF/MuPDF and PyQt6; or
3. replacing those dependencies with alternatives whose licences match the
   intended distribution model.

See `LICENSING_DECISION_REQUIRED.md` and `release/release_policy.json`.
