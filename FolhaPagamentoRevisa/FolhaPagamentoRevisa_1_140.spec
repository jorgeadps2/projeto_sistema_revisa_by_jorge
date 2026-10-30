# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_submodules

datas = [('logo_revisa.png', '.'), ('assinatura_logo.png', '.'), ('folha_pagamento.ico', '.')]
hiddenimports = []
datas += collect_data_files('pyhanko')
datas += collect_data_files('pyhanko_certvalidator')
hiddenimports += collect_submodules('pyhanko')
hiddenimports += collect_submodules('pyhanko_certvalidator')
hiddenimports += collect_submodules('cryptography')


a = Analysis(
    ['folha_pagamento.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='FolhaPagamentoRevisa_1_140',
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
    icon=['folha_pagamento.ico'],
)
