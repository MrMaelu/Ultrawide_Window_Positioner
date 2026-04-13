# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_all

tmp_hdr = collect_all('hdrcapture')
tmp_num = collect_all('numpy')

hiddenimports = []
hiddenimports += collect_submodules('PySide6.QtWidgets')
hiddenimports += collect_submodules('PySide6.QtGui')
hiddenimports += collect_submodules('PySide6.QtCore')
hiddenimports += tmp_hdr[2]
hiddenimports += tmp_num[2]

a = Analysis(
    ['src/main.py'],
    pathex=[],
    binaries=tmp_hdr[1] + tmp_num[1],
    datas=[
        ('src/data/checkmark.svg', 'data'),
        ('src/data/Icon.png', 'data'),
    ] + tmp_hdr[0] + tmp_num[0],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtQuick', 'PySide6.QtQml', 'PySide6.QtNetwork', 'PySide6.QtSql', 'PySide6.QtXml'],
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

excluded_binaries = [
    'libQt6Network.so.6',
    'libgtk-3.so.0',
    'libglycin-2.so.0'
]
a.binaries = [x for x in a.binaries if not any(err in x[0] for err in excluded_binaries)]

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Ultrawide Window Positioner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version.txt',
    icon='src/data/Icon.ico',
)
