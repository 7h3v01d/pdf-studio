# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for PDF Studio.
# Build with:  python -m PyInstaller "PDF Studio.spec"
#
# Optional features (Word/Excel export, OCR) depend on extra packages. Install
# the ones you want BEFORE building and they'll be bundled automatically:
#     pip install pdf2docx pytesseract pdf2image Pillow tabula-py openpyxl pandas
# (Excel export also needs Java, and OCR needs Tesseract + Poppler on the target
#  machine — those are external programs, not Python packages.)

from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Collect only the optional packages that genuinely need their data/submodules
# pulled and that aren't already handled by PyInstaller's built-in hooks.
# NOTE: do NOT collect_all('fontTools') — it drags in fontTools.pens.qtPen,
# which imports PyQt5 and makes PyInstaller abort on "multiple Qt bindings".
_extra_datas, _extra_bins, _extra_hidden = [], [], []
for _pkg in ("pdf2docx", "tabula"):
    try:
        d, b, h = collect_all(_pkg)
        _extra_datas += d
        _extra_bins += b
        _extra_hidden += h
    except Exception:
        pass  # package not installed — skip it

a = Analysis(
    ['pdf_reader.py'],
    pathex=[],
    binaries=_extra_bins,
    datas=[('icon.ico', '.'), ('fonts', 'fonts')] + _extra_datas,
    hiddenimports=['register_file_types'] + _extra_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Never bundle a second Qt binding — PyInstaller can't mix them and will
        # abort. PDF Studio uses PyQt6 only.
        'PyQt5', 'PySide2', 'PySide6',
        # Heavy libraries none of PDF Studio's features need — keeps the exe lean
        # even if they happen to be installed in the build environment.
        # (numpy is intentionally NOT excluded: pdf2docx depends on it.)
        'tensorflow', 'torch', 'matplotlib', 'IPython', 'pygame', 'notebook',
        'scipy', 'numba', 'llvmlite', 'pyarrow', 'sqlalchemy', 'zmq', 'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='PDF Studio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon='icon.ico',
)
