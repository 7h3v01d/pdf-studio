# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for PDF Studio.
# Build with:  python -m PyInstaller "PDF Studio.spec"
#
# Optional Word/Excel export features depend on extra packages. Install
# the ones you want BEFORE building and they'll be bundled automatically:
#     pip install pdf2docx tabula-py openpyxl pandas
# OCR and image-export Python components are included in requirements.txt. The target machine
# only needs Tesseract itself; PDF Studio auto-detects it without PATH changes.

from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Collect only the optional packages that genuinely need their data/submodules
# pulled and that aren't already handled by PyInstaller's built-in hooks.
# NOTE: do NOT collect_all('fontTools') — it drags in fontTools.pens.qtPen,
# which imports PyQt5 and makes PyInstaller abort on "multiple Qt bindings".
_extra_datas, _extra_bins, _extra_hidden = [], [], []
for _pkg in ("pdf2docx", "cv2", "fire", "tabula"):
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
    datas=[
        ('icon.ico', '.'),
        ('fonts', 'fonts'),
        ('../assets/splashscreen.png', 'assets'),
        ('../LICENSE.txt', '.'),
        ('../NOTICE', '.'),
        ('../THIRD_PARTY_NOTICES.md', '.'),
        ('../LICENSING_DECISION_REQUIRED.md', '.'),
        ('../RELEASE_CHECKLIST.md', '.'),
        ('../licenses', 'licenses'),
        ('../release/build_manifest.json', 'release'),
        ('../release/release_policy.json', 'release'),
        ('../docs/PDF_Studio_Manual.pdf', 'docs'),
        ('../docs/PDF_Studio_Easy_Guide.pdf', 'docs'),
    ] + _extra_datas,
    hiddenimports=[
        'register_file_types', 'tesseract_setup', 'diagnostics_dialog',
        'runtime_support', 'app_metadata',
    ] + _extra_hidden,
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
