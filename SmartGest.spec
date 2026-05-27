# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/icon.ico', 'assets')],
    hiddenimports=[
        'calendario',
        'movimentacao',
        'entradas',
        'cadastro',
        'historico',
        'estoque',
        'estoque_adm',
        'estoque_baixo',
        'inventario',
        'valorizacao',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'scipy',
        'notebook',
        'IPython',
        'jupyter',
        'pytest',
        'unittest',
        'tkinter',
        'PyQt5',
        'PyQt6',
        'PySide2',
    ],
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [('O', None, 'OPTION'), ('O', None, 'OPTION')],
    exclude_binaries=True,
    name='SmartGest',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='assets/icon.ico',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SmartGest',
)
