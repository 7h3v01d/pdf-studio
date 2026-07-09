# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for PDF Studio.
# Build with:  pyinstaller "PDF Studio.spec"

block_cipher = None

a = Analysis(
    ['pdf_reader.py'],
    pathex=[],
    binaries=[],
    datas=[('icon.ico', '.'), ('fonts', 'fonts')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tensorflow', 'torch', 'matplotlib', 'scipy',
        'numpy', 'IPython', 'pygame',
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
