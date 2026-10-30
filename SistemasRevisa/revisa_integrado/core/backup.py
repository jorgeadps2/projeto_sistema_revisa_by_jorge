"""Backups verificáveis. Nunca apaga backups existentes."""
import hashlib
import json
import os
import shutil
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from .config import write_json_atomic

FORMAT_VERSION = 1


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def is_sqlite_file(path):
    try:
        with open(path, "rb") as handle:
            return handle.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def integrity_check(path):
    try:
        with closing(_readonly(path)) as con:
            return con.execute("PRAGMA integrity_check").fetchone()[0]
    except sqlite3.Error as error:
        return f"erro: {error}"


def table_counts(path):
    with closing(_readonly(path)) as con:
        names = [row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {name: con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in names}


def schema_info(path):
    with closing(_readonly(path)) as con:
        tables = [row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        version = con.execute("PRAGMA user_version").fetchone()[0]
    return {"tabelas": tables, "user_version": version}


def logical_digest(path, exclude=()):
    """Resumo do conteúdo das tabelas, independente da organização física do arquivo."""
    digest = hashlib.sha256()
    with closing(_readonly(path)) as con:
        names = [row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for name in names:
            if name in exclude:
                continue
            digest.update(b"\x00T" + name.encode("utf-8"))
            rows = sorted(repr(tuple(row)) for row in con.execute(f'SELECT * FROM "{name}"'))
            for row in rows:
                digest.update(b"\x00R" + row.encode("utf-8"))
    return digest.hexdigest().upper()


def snapshot_db(source, target):
    """Cópia consistente via API de backup do SQLite; a origem é aberta somente leitura."""
    target = Path(target)
    if target.exists():
        raise FileExistsError(f"Destino já existe: {target}")
    with closing(_readonly(source)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)


def describe_db(path):
    return {
        "tamanho": Path(path).stat().st_size,
        "sha256": sha256_file(path),
        "integridade": integrity_check(path),
        "resumo_logico": logical_digest(path),
        "registros": table_counts(path),
        "esquema": schema_info(path),
    }


def _new_folder(root, prefix):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for index in range(100):
        name = f"{prefix}{stamp}" + (f"-{index}" if index else "")
        final = root / name
        partial = root / f".{name}.parcial"
        if not final.exists() and not partial.exists():
            partial.mkdir()
            return partial, final
    raise FileExistsError("Não foi possível criar uma pasta de backup exclusiva.")


def create_backup(databases, root, app_version, reason="manual", extra_files=None, prefix=""):
    """databases: {chave: caminho_db}; extra_files: {chave: caminho}. Retorna (pasta, manifesto)."""
    partial, final = _new_folder(root, prefix)
    manifest = {
        "formato": FORMAT_VERSION,
        "sistema": "Sistemas Revisa",
        "versao_app": app_version,
        "motivo": reason,
        "criado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
        "computador": os.environ.get("COMPUTERNAME", ""),
        "bancos": {},
        "arquivos": {},
        "problemas": [],
    }
    for key, source in databases.items():
        source = Path(source)
        entry = {"origem": str(source)}
        if not source.is_file():
            entry["status"] = "ausente"
            manifest["problemas"].append(f"{key}: banco ausente em {source}")
        else:
            target = partial / f"{key}.db"
            snapshot_db(source, target)
            entry.update(describe_db(target))
            entry["arquivo"] = target.name
            entry["integridade_origem"] = integrity_check(source)
            entry["status"] = "ok" if entry["integridade"] == "ok" else "falha"
            if entry["status"] != "ok":
                manifest["problemas"].append(f"{key}: integridade {entry['integridade']}")
        manifest["bancos"][key] = entry
    for key, source in (extra_files or {}).items():
        source = Path(source)
        if not source.is_file():
            manifest["arquivos"][key] = {"origem": str(source), "status": "ausente"}
            continue
        target = partial / f"{key}{source.suffix}"
        shutil.copy2(source, target)
        manifest["arquivos"][key] = {"origem": str(source), "arquivo": target.name,
                                     "tamanho": target.stat().st_size, "sha256": sha256_file(target),
                                     "status": "ok" if sha256_file(source) == sha256_file(target) else "falha"}
        if manifest["arquivos"][key]["status"] != "ok":
            manifest["problemas"].append(f"{key}: cópia divergente")
    write_json_atomic(partial / "manifest.json", manifest)
    os.replace(partial, final)
    return final, manifest


def mirror_backup(folder, root):
    """Copia um backup validado para outro destino, sem substituir cópias existentes."""
    folder = Path(folder)
    root = Path(root)
    valid, problems, _ = verify_backup(folder)
    if not valid:
        raise ValueError(f"Backup de origem inválido: {'; '.join(problems)}")
    root_path = root.resolve()
    primary_root = folder.parent.resolve()
    if root_path == primary_root or primary_root in root_path.parents:
        raise ValueError("A pasta adicional precisa ser diferente da pasta principal de backups.")
    if root_path == folder.resolve() or folder.resolve() in root_path.parents:
        raise ValueError("A pasta adicional não pode ficar dentro do próprio backup.")
    partial, final = _new_folder(root, f"{folder.name}-copia-")
    try:
        shutil.copytree(folder, partial, dirs_exist_ok=True)
        os.replace(partial, final)
    except OSError:
        if partial.exists():
            shutil.rmtree(partial, ignore_errors=True)
        raise
    valid, problems, _ = verify_backup(final)
    if not valid:
        raise OSError(f"A cópia adicional não passou na verificação: {'; '.join(problems)}")
    return final


def verify_backup(folder):
    folder = Path(folder)
    problems = []
    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return False, [f"manifesto ilegível: {error}"], None
    for group in ("bancos", "arquivos"):
        for key, entry in manifest.get(group, {}).items():
            if entry.get("status") == "ausente":
                continue
            path = folder / entry.get("arquivo", "")
            if not path.is_file():
                problems.append(f"{key}: arquivo ausente")
                continue
            if sha256_file(path) != entry.get("sha256"):
                problems.append(f"{key}: SHA-256 diferente do manifesto")
            if group == "bancos":
                result = integrity_check(path)
                if result != "ok":
                    problems.append(f"{key}: integridade {result}")
    return not problems, problems, manifest


def list_backups(root):
    root = Path(root)
    if not root.is_dir():
        return []
    items = []
    for folder in sorted((p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")), reverse=True):
        try:
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest = None
        items.append((folder, manifest))
    return items
