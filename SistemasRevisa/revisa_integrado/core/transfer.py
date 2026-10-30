"""Transferência controlada dos bancos entre dois computadores (por exemplo, via pasta do MEGA).

Regras:
- O pacote é gravado numa pasta parcial; o manifesto vem depois dos bancos e o marcador PRONTO por último.
- Depois de exportar, este computador deixa de ser o titular dos dados até importar um pacote mais novo.
- A importação é recusada se o pacote estiver incompleto, alterado, duplicado, antigo, for da própria
  máquina, for incompatível ou se os dados locais tiverem mudado desde a última sincronização.
- Antes de importar, os bancos locais são copiados para um backup verificado.
- Credenciais (acesso.json, assinatura_digital.json) nunca são transferidas. A senha principal, que fica
  na tabela app_auth do banco da Folha, é removida do pacote e a senha local é mantida na importação.
"""
import gc
import json
import os
import re
import shutil
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path

from . import backup
from .config import write_json_atomic

FORMAT_VERSION = 1
READY_MARKER = "PRONTO"
MANIFEST = "manifest.json"
PACKAGE_PREFIX = "SR-"
# Tabelas que pertencem a cada computador: não viajam no pacote e não contam como alteração de dados.
LOCAL_ONLY_TABLES = {"folha": ("app_auth",)}


class TransferError(Exception):
    pass


def load_state(path, default_titular=True):
    path = Path(path)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        state = {}
    except (OSError, ValueError) as error:
        raise TransferError(f"Estado da transferência ilegível ({path}): {error}") from error
    if not isinstance(state, dict):
        raise TransferError(f"Estado da transferência inválido: {path}")
    changed = False
    if not isinstance(state.get("maquina_id"), str):
        state["maquina_id"] = uuid.uuid4().hex
        changed = True
    state.setdefault("computador", os.environ.get("COMPUTERNAME", ""))
    state.setdefault("titular", default_titular)
    state.setdefault("ultimo_pacote", None)
    state.setdefault("ultimo_pacote_criado", None)
    state.setdefault("resumos_base", {})
    state.setdefault("importados", [])
    state.setdefault("historico", [])
    if changed:
        save_state(path, state)
    return state


def save_state(path, state):
    write_json_atomic(path, state)


def _history(state, event, **data):
    state["historico"].append({"quando": time.strftime("%Y-%m-%d %H:%M:%S"), "evento": event, **data})
    state["historico"] = state["historico"][-200:]


def _safe_name(text):
    return re.sub(r"[^A-Za-z0-9]+", "", text or "PC")[:15] or "PC"


def _digest(key, path):
    return backup.logical_digest(path, exclude=LOCAL_ONLY_TABLES.get(key, ()))


def _tables(con):
    return {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _strip_local_tables(key, path):
    """Esvazia as tabelas locais na cópia, sem deixar os dados apagados nas páginas livres do arquivo."""
    tables = LOCAL_ONLY_TABLES.get(key, ())
    if not tables:
        return
    with closing(sqlite3.connect(path)) as con:
        present = _tables(con)
        con.execute("PRAGMA secure_delete=ON")
        for table in tables:
            if table in present:
                con.execute(f'DELETE FROM "{table}"')
        con.commit()
        con.execute("VACUUM")


def _keep_local_tables(key, imported, local):
    """Copia para o banco importado as tabelas locais do banco que será substituído."""
    tables = LOCAL_ONLY_TABLES.get(key, ())
    if not tables or not Path(local).is_file():
        return
    with closing(sqlite3.connect(Path(local).resolve().as_uri() + "?mode=ro", uri=True)) as src, \
            closing(sqlite3.connect(imported)) as dst:
        source_tables, target_tables = _tables(src), _tables(dst)
        with dst:
            for table in tables:
                if table not in source_tables or table not in target_tables:
                    continue
                columns = [row[1] for row in src.execute(f'PRAGMA table_info("{table}")')]
                names = ", ".join(f'"{c}"' for c in columns)
                rows = src.execute(f'SELECT {names} FROM "{table}"').fetchall()
                dst.execute(f'DELETE FROM "{table}"')
                dst.executemany(f'INSERT INTO "{table}" ({names}) VALUES ({", ".join("?" * len(columns))})', rows)


def export_package(databases, transfer_dir, state, state_path, app_version):
    """databases: {chave: caminho}. Os módulos devem estar fechados. Retorna a pasta do pacote."""
    if not state.get("titular", True):
        raise TransferError("Este computador não é o titular atual dos dados. Importe o pacote mais "
                            "recente antes de exportar.")
    transfer_dir = Path(transfer_dir)
    transfer_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    package_id = f"{PACKAGE_PREFIX}{stamp}-{_safe_name(state.get('computador'))}-{uuid.uuid4().hex[:8]}"
    partial = transfer_dir / f".{package_id}.parcial"
    final = transfer_dir / package_id
    partial.mkdir()
    entries = {}
    for key, source in databases.items():
        source = Path(source)
        if not source.is_file():
            raise TransferError(f"Banco '{key}' não encontrado em {source}. Exportação cancelada.")
        target = partial / f"{key}.db"
        backup.snapshot_db(source, target)
        _strip_local_tables(key, target)
        info = backup.describe_db(target)
        if info["integridade"] != "ok":
            raise TransferError(f"Banco '{key}' com falha de integridade: {info['integridade']}")
        info["resumo_logico"] = _digest(key, target)
        if _digest(key, source) != info["resumo_logico"]:
            raise TransferError(f"O banco '{key}' mudou durante a exportação. Feche os módulos e tente novamente.")
        info["arquivo"] = target.name
        entries[key] = info
    manifest = {
        "formato": FORMAT_VERSION,
        "id": package_id,
        "criado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
        "criado_em_epoch": time.time(),
        "maquina_origem": state["maquina_id"],
        "computador_origem": state.get("computador", ""),
        "versao_app": app_version,
        "pacote_anterior": state.get("ultimo_pacote"),
        "bancos": entries,
    }
    write_json_atomic(partial / MANIFEST, manifest)
    os.replace(partial, final)
    (final / READY_MARKER).write_text(backup.sha256_file(final / MANIFEST), encoding="ascii")
    state["titular"] = False
    state["ultimo_pacote"] = package_id
    state["ultimo_pacote_criado"] = manifest["criado_em_epoch"]
    state["resumos_base"] = {key: info["resumo_logico"] for key, info in entries.items()}
    _history(state, "exportacao", pacote=package_id)
    save_state(state_path, state)
    for previous in list_packages(transfer_dir):
        if previous == final:
            continue
        previous_manifest, problems = read_package(previous)
        if previous_manifest is not None and not problems:
            shutil.rmtree(previous)
    return final


def read_package(folder):
    """Valida estrutura e integridade do pacote. Retorna (manifesto, problemas)."""
    folder = Path(folder)
    problems = []
    marker = folder / READY_MARKER
    manifest_path = folder / MANIFEST
    if not marker.is_file() or not manifest_path.is_file():
        return None, ["pacote incompleto (ainda sendo gravado ou sincronizado)"]
    try:
        expected = marker.read_text(encoding="ascii").strip()
    except (OSError, ValueError):
        return None, ["marcador PRONTO ilegível"]
    if backup.sha256_file(manifest_path) != expected:
        return None, ["manifesto alterado após a conclusão do pacote"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return None, [f"manifesto ilegível: {error}"]
    if manifest.get("formato") != FORMAT_VERSION:
        problems.append("formato de pacote incompatível")
    if manifest.get("id") != folder.name:
        problems.append("nome da pasta não corresponde ao pacote")
    for key, entry in (manifest.get("bancos") or {}).items():
        path = folder / str(entry.get("arquivo", ""))
        if not path.is_file():
            problems.append(f"{key}: arquivo ausente")
            continue
        if path.stat().st_size != entry.get("tamanho") or backup.sha256_file(path) != entry.get("sha256"):
            problems.append(f"{key}: arquivo alterado (tamanho ou SHA-256 divergente)")
            continue
        result = backup.integrity_check(path)
        if result != "ok":
            problems.append(f"{key}: integridade {result}")
    if not manifest.get("bancos"):
        problems.append("pacote sem bancos")
    return manifest, problems


def inspect_package(folder, state, local_databases, app_version):
    """Retorna dict com 'manifesto', 'bloqueios' (impedem a importação) e 'avisos' (exigem confirmação)."""
    manifest, problems = read_package(folder)
    result = {"pasta": str(folder), "manifesto": manifest, "bloqueios": list(problems), "avisos": []}
    if manifest is None:
        return result
    if manifest.get("maquina_origem") == state.get("maquina_id"):
        result["bloqueios"].append("pacote gerado por este mesmo computador")
    package_id = manifest.get("id")
    if package_id == state.get("ultimo_pacote") or package_id in state.get("importados", []):
        result["bloqueios"].append("pacote já importado ou exportado por este computador (duplicado)")
    last_created = state.get("ultimo_pacote_criado")
    if last_created is not None and manifest.get("criado_em_epoch", 0) <= last_created:
        result["bloqueios"].append("pacote mais antigo que os dados já sincronizados neste computador")
    if str(manifest.get("versao_app", "")).split(".")[0] != str(app_version).split(".")[0]:
        result["bloqueios"].append(f"versão incompatível ({manifest.get('versao_app')} x {app_version})")
    unknown = set(manifest.get("bancos", {})) - set(local_databases)
    if unknown:
        result["bloqueios"].append(f"bancos desconhecidos no pacote: {', '.join(sorted(unknown))}")
    base = state.get("resumos_base") or {}
    if state.get("ultimo_pacote") is None:
        result["avisos"].append("primeira sincronização deste computador: não há referência para "
                                "detectar alterações locais")
    elif manifest.get("pacote_anterior") != state.get("ultimo_pacote"):
        result["bloqueios"].append("conflito: o pacote não foi gerado a partir da última versão conhecida "
                                   "por este computador")
    for key in manifest.get("bancos", {}):
        local = Path(local_databases.get(key, ""))
        if not local.is_file():
            note = "; a senha principal deverá ser cadastrada neste computador" if key in LOCAL_ONLY_TABLES else ""
            result["avisos"].append(f"{key}: banco local ausente; será criado a partir do pacote{note}")
            continue
        if key in base and _digest(key, local) != base[key]:
            result["bloqueios"].append(f"{key}: há alterações locais desde a última sincronização (conflito)")
    return result


def _replace_with_retry(source, target, attempts=5, delay=0.2):
    for attempt in range(attempts):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            gc.collect()
            time.sleep(delay)


def import_package(folder, state, state_path, local_databases, backups_root, app_version,
                   accept_warnings=False, additional_backup_root=None):
    """Importa o pacote. Os módulos devem estar fechados. Retorna (pasta_backup, manifesto)."""
    folder = Path(folder)
    report = inspect_package(folder, state, local_databases, app_version)
    if report["bloqueios"]:
        raise TransferError("Importação recusada:\n- " + "\n- ".join(report["bloqueios"]))
    if report["avisos"] and not accept_warnings:
        raise TransferError("Importação requer confirmação:\n- " + "\n- ".join(report["avisos"]))
    manifest = report["manifesto"]
    existing = {key: path for key, path in local_databases.items() if Path(path).is_file()}
    backup_folder, backup_manifest = backup.create_backup(
        existing, backups_root, app_version, reason=f"antes_importacao {manifest['id']}", prefix="antes-importacao-")
    if any(entry.get("status") != "ok" for entry in backup_manifest["bancos"].values()):
        raise TransferError(f"Backup prévio com problemas ({backup_folder}). Importação cancelada.")
    if additional_backup_root:
        try:
            backup.mirror_backup(backup_folder, additional_backup_root)
        except (OSError, ValueError) as error:
            raise TransferError(
                f"Não foi possível salvar o backup adicional ({error}). "
                f"A importação foi cancelada; o backup principal está em {backup_folder}.") from error
    # Conexões SQLite não fechadas pelos módulos (presas em ciclos de referência) mantêm o
    # arquivo aberto e impedem a substituição no Windows.
    gc.collect()
    replaced = []
    temp = None
    try:
        for key, entry in manifest["bancos"].items():
            target = Path(local_databases[key])
            for suffix in ("-journal", "-wal"):
                if Path(str(target) + suffix).exists():
                    raise TransferError(f"{key}: arquivo {target.name}{suffix} presente; feche o módulo e tente novamente.")
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(target.name + ".importando.tmp")
            if temp.exists():
                raise TransferError(f"Arquivo temporário remanescente: {temp}")
            backup.snapshot_db(folder / entry["arquivo"], temp)
            _strip_local_tables(key, temp)
            if backup.integrity_check(temp) != "ok" or _digest(key, temp) != entry["resumo_logico"]:
                temp.unlink()
                raise TransferError(f"{key}: cópia temporária não confere com o pacote.")
            _keep_local_tables(key, temp, target)
            if backup.integrity_check(temp) != "ok":
                temp.unlink()
                raise TransferError(f"{key}: falha ao preservar os dados locais na cópia importada.")
            _replace_with_retry(temp, target)
            temp = None
            replaced.append(key)
    except Exception:
        if temp is not None and temp.exists():
            try:
                temp.unlink()
            except OSError:
                pass
        for key in replaced:
            saved = backup_folder / f"{key}.db"
            target = Path(local_databases[key])
            if saved.is_file():
                temp = target.with_name(target.name + ".restaurando.tmp")
                if temp.exists():
                    temp.unlink()
                backup.snapshot_db(saved, temp)
                _replace_with_retry(temp, target)
        raise
    state["titular"] = True
    state["ultimo_pacote"] = manifest["id"]
    state["ultimo_pacote_criado"] = manifest.get("criado_em_epoch")
    state["resumos_base"] = {key: entry["resumo_logico"] for key, entry in manifest["bancos"].items()}
    state["importados"] = (state.get("importados", []) + [manifest["id"]])[-200:]
    _history(state, "importacao", pacote=manifest["id"], backup=str(backup_folder))
    save_state(state_path, state)
    return backup_folder, manifest


def resume_ownership(state, state_path, local_databases, transfer_dir):
    """Retoma a titularidade somente se os dados locais não mudaram e não há pacote externo mais novo."""
    if state.get("titular", True):
        raise TransferError("Este computador já é o titular dos dados.")
    base = state.get("resumos_base")
    if not isinstance(base, dict) or not base:
        raise TransferError("Não há uma referência confiável para validar os dados locais.")
    if set(base) != set(local_databases):
        raise TransferError("A lista de bancos não corresponde ao último pacote; não é seguro retomar.")
    for key, expected in base.items():
        local = Path(local_databases.get(key, ""))
        if not local.is_file():
            raise TransferError(f"Banco local '{key}' não encontrado; não é seguro retomar.")
        if _digest(key, local) != expected:
            raise TransferError(
                f"O banco '{key}' mudou desde o último pacote. Receba a versão do outro computador "
                "antes de retomar.")

    last_created = state.get("ultimo_pacote_criado")
    for package in list_packages(transfer_dir):
        manifest, problems = read_package(package)
        if manifest is None:
            raise TransferError(
                f"O pacote {package.name} ainda está incompleto ou ilegível. Aguarde o MEGA "
                "sincronizar e tente novamente.")
        created = manifest.get("criado_em_epoch")
        if (manifest.get("maquina_origem") != state.get("maquina_id")
                and (last_created is None or created is None or created > last_created)):
            detail = "; ".join(problems) if problems else "aguardando importação neste computador"
            raise TransferError(
                f"Há um pacote mais recente do outro computador ({package.name}: {detail}). "
                "Sincronize esse pacote antes de retomar.")

    state["titular"] = True
    _history(state, "retomada_manual", pacote=state.get("ultimo_pacote"))
    save_state(state_path, state)


def list_packages(transfer_dir):
    transfer_dir = Path(transfer_dir)
    if not transfer_dir.is_dir():
        return []
    return sorted((p for p in transfer_dir.iterdir() if p.is_dir() and p.name.startswith(PACKAGE_PREFIX)),
                  key=lambda p: p.name, reverse=True)
