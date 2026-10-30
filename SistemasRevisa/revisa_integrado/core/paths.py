import os
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[3]
FOLHA_SOURCE_DIR = SOURCE_ROOT / "FolhaPagamentoRevisa"
ENERGIA_SOURCE_DIR = SOURCE_ROOT / "Controle_Energia_Agua_Barracao_Python" / "Controle_Energia_Agua_Barracao"
CENTRAL_ASSETS_DIR = SOURCE_ROOT / "Controle_Energia_Agua_Barracao_Python" / "assets"


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def local_appdata():
    value = os.environ.get("LOCALAPPDATA")
    return Path(value) if value else Path.home() / "AppData" / "Local"


def app_data_dir():
    return local_appdata() / "SistemasRevisa"


def backups_dir():
    return app_data_dir() / "backups"


def logs_dir():
    return app_data_dir() / "logs"


def config_path():
    return app_data_dir() / "config.json"


def transfer_state_path():
    return app_data_dir() / "transferencia_estado.json"


def program_dir():
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return SOURCE_ROOT / "SistemasRevisa"


def default_transfer_dir():
    return program_dir() / "Transferencia Sistemas Revisa"


def asset(name):
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "assets" / name
    return CENTRAL_ASSETS_DIR / name


def ensure_module_paths():
    """No modo código-fonte, torna importáveis os módulos da Folha e do Energia."""
    if is_frozen():
        return
    for folder in (FOLHA_SOURCE_DIR, ENERGIA_SOURCE_DIR):
        text = str(folder)
        if text not in sys.path:
            sys.path.append(text)
