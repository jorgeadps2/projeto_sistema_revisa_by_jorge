# -*- mode: python ; coding: utf-8 -*-
# Sistemas Revisa integrado: Central + Folha de Pagamento + Energia e Água em um único executável.
# Nenhum banco de dados, acesso.json ou credencial é empacotado.
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

base = Path(SPECPATH)
root = base.parent
central_assets = root / "Controle_Energia_Agua_Barracao_Python" / "assets"
payroll = root / "FolhaPagamentoRevisa"
energy = root / "Controle_Energia_Agua_Barracao_Python" / "Controle_Energia_Agua_Barracao"

datas = [
    (str(central_assets / "logo_central_revisa.png"), "assets"),
    (str(central_assets / "robo_desenvolvedor.png"), "assets"),
    (str(central_assets / "revisa.ico"), "assets"),
    (str(payroll / "logo_revisa.png"), "."),
    (str(payroll / "assinatura_logo.png"), "."),
    (str(payroll / "folha_pagamento.ico"), "."),
    (str(energy / "assets" / "revisa_logo.jpeg"), "assets"),
    (str(energy / "assets" / "logo_revisa.png"), "assets"),
    (str(energy / "assets" / "imovel.png"), "assets"),
]
hiddenimports = ["folha_pagamento", "controle_energia_agua", "importar_pdf_folha"]
hiddenimports += collect_submodules("revisa_integrado")
for package in ("pyhanko", "pyhanko_certvalidator"):
    datas += collect_data_files(package)
    hiddenimports += collect_submodules(package)
hiddenimports += collect_submodules("cryptography")

# Python 3.15 can load stable-ABI signing extensions through the abi3t shim.
runtime_dlls = [
    (str(path), ".")
    for path in (
        Path(sys.base_prefix) / "python3.dll",
        Path(sys.base_prefix) / "abi3t-compat" / "python3t.dll",
    )
    if path.is_file()
]

a = Analysis(
    [str(base / "app.py")],
    pathex=[str(base), str(payroll), str(energy)],
    binaries=runtime_dlls,
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
    name="Sistemas_Revisa",
    icon=str(central_assets / "revisa.ico"),
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
