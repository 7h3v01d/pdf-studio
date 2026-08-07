# PDF Studio - Third-Party Licences and Notices

**Licensing strategy:** selected. PDF Studio source is available under
`Apache-2.0 OR AGPL-3.0-only`. Official open-source binaries using the free
PyQt6 and PyMuPDF editions use the AGPL option for PDF Studio code and remain
subject to all applicable GPLv3/AGPLv3 obligations.

**Public binary status:** not yet approved. Reproducible-build, dependency,
clean-machine, and final approval evidence remain outstanding.

This file is an engineering inventory, not legal advice. A distributor must
review the exact package versions and licence texts included in the final build.

## Required Python runtime components

### PyMuPDF / MuPDF

- Purpose: PDF rendering, editing, forms, redaction, and document output.
- Published licence choice: GNU Affero General Public License version 3 or a
  commercial licence from Artifex.
- Official PDF Studio builds use the AGPL edition unless a commercial licence
  is explicitly recorded for that release.
- Bundled reference texts: `licenses/AGPL-3.0-PyMuPDF-COPYING.txt` and
  `licenses/AGPL-3.0.txt`.
- Project: https://pymupdf.readthedocs.io/

### PyQt6 and Qt 6

- Purpose: desktop user interface.
- PyQt6 licence choice published by Riverbank: GPL version 3 or a commercial
  Riverbank licence. PyQt6 is not offered under the LGPL.
- Official PDF Studio open-source builds use the GPL edition.
- Riverbank's GPL wheels include Qt libraries; those Qt libraries retain their
  own licence obligations.
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

## PDF Studio source and official binary distribution

PDF Studio code authored by Leon Priest is dual-licensed under
`Apache-2.0 OR AGPL-3.0-only`.

A recipient using the standalone source may select either option. Official
prebuilt binaries that include the GPL edition of PyQt6 and the AGPL edition of
PyMuPDF/MuPDF use the AGPL option for PDF Studio code. PyQt6 remains GPLv3,
PyMuPDF/MuPDF remains AGPLv3, and other components retain their own terms.

Every public binary release must provide the exact corresponding PDF Studio
source, build scripts, dependency locks, hashes, notices, licence texts, and
third-party corresponding-source information described in
`LICENSING_STRATEGY.md`.
