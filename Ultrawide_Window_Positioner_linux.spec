# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = []
hiddenimports += collect_submodules('PySide6.QtWidgets')
hiddenimports += collect_submodules('PySide6.QtGui')
hiddenimports += collect_submodules('PySide6.QtCore')


a = Analysis(
    ['src/main.py'],
    pathex=[],
    binaries=[('src/bin/kdotool', 'bin')],
    datas=[
        ('src/data/checkmark.svg', 'data'),
        ('src/data/Icon.png', 'data')
    ],
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
