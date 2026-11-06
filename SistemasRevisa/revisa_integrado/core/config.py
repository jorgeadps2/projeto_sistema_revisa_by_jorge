import json
import os
import tempfile
from pathlib import Path

from . import paths

DEFAULTS = {
    "transferencia_habilitada": False,
    "pasta_transferencia": "",
    "pasta_backup_adicional": "",
    "leituras_confirmadas": [],
}


def write_json_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=path.stem + "_", suffix=".tmp", delete=False) as handle:
            temp = Path(handle.name)
            json.dump(data, handle, ensure_ascii=False, indent=1)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()


def load(path=None):
    path = Path(path or paths.config_path())
    data = dict(DEFAULTS)
    data["leituras_confirmadas"] = []
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return data
    except (OSError, ValueError) as error:
        raise ValueError(f"Configuração inválida em {path}: {error}") from error
    if not isinstance(stored, dict):
        raise ValueError(f"Configuração inválida em {path}.")
    data["transferencia_habilitada"] = stored.get("transferencia_habilitada") is True
    folder = stored.get("pasta_transferencia")
    data["pasta_transferencia"] = folder if isinstance(folder, str) else ""
    folder = stored.get("pasta_backup_adicional")
    data["pasta_backup_adicional"] = folder if isinstance(folder, str) else ""
    confirmations = stored.get("leituras_confirmadas")
    data["leituras_confirmadas"] = (
        sorted({item for item in confirmations if isinstance(item, str)})
        if isinstance(confirmations, list) else []
    )
    return data


def save(data, path=None):
    clean = {
        "transferencia_habilitada": data.get("transferencia_habilitada") is True,
        "pasta_transferencia": str(data.get("pasta_transferencia") or ""),
        "pasta_backup_adicional": str(data.get("pasta_backup_adicional") or ""),
        "leituras_confirmadas": sorted({
            item for item in data.get("leituras_confirmadas", [])
            if isinstance(item, str)
        }) if isinstance(data.get("leituras_confirmadas", []), list) else [],
    }
    write_json_atomic(path or paths.config_path(), clean)
    return clean


def transfer_dir(data):
    folder = data.get("pasta_transferencia")
    return Path(folder) if folder else paths.default_transfer_dir()


def additional_backup_dir(data):
    folder = data.get("pasta_backup_adicional")
    return Path(folder) if folder else None
