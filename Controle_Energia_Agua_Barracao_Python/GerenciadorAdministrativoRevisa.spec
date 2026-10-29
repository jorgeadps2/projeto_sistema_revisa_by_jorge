# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

base = Path(SPECPATH)
payroll = base.parent / "FolhaPagamentoRevisa"
energy = base / "Controle_Energia_Agua_Barracao"

datas = [
    (str(base / "assets" / "logo_central_revisa.png"), "assets"),
    (str(base / "assets" / "revisa.ico"), "assets"),
    (str(payroll / "logo_revisa.png"), "."),
    (str(payroll / "assinatura_logo.png"), "."),
    (str(payroll / "folha_pagamento.ico"), "."),
    (str(energy / "assets" / "revisa_logo.jpeg"), "assets"),
    (str(energy / "assets" / "imovel.png"), "assets"),
]
hiddenimports = ["folha_pagamento", "controle_energia_agua", "importar_pdf_folha"]
for package in ("pyhanko", "pyhanko_certvalidator"):
    datas += collect_data_files(package)
    hiddenimports += collect_submodules(package)
hiddenimports += collect_submodules("cryptography")

a = Analysis(
    [str(base / "Iniciar_Sistemas_Revisa.py")],
    pathex=[str(payroll), str(energy)],
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
    name="GerenciadorAdministrativoRevisa",
    icon=str(base / "assets" / "revisa.ico"),
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
)
