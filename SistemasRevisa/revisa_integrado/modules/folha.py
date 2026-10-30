"""Adaptador da Folha de Pagamento (folha_pagamento.py, sem duplicar regras de negócio)."""
import sqlite3
import json
from contextlib import closing
from datetime import datetime
from pathlib import Path

from ..core import paths

KEY = "folha"
TITLE = "Folha de Pagamento"


def module():
    paths.ensure_module_paths()
    import folha_pagamento
    return folha_pagamento


def db_path():
    return Path(module().DB_PATH)


def data_dir():
    return Path(module().DATA_DIR)


def signing_config_path():
    return data_dir() / "assinatura_digital.json"


def signing_status(warning_days=30):
    try:
        data = json.loads(signing_config_path().read_text(encoding="utf-8"))
        expires = datetime.strptime(data["validade"], "%Y-%m-%d").date()
    except (OSError, ValueError, KeyError, TypeError):
        return "Assinatura digital: validade indisponível", "unavailable", ""
    days = (expires - datetime.now().date()).days
    when = expires.strftime("%d/%m/%Y")
    if days < 0:
        return f"Assinatura digital VENCEU em {when}", "expired", when
    if days <= warning_days:
        return f"Assinatura digital vence em {days} dia(s) ({when})", "warning", when
    return f"Assinatura digital válida até {when} ({days} dias)", "ok", when


def _readonly():
    return closing(sqlite3.connect(db_path().resolve().as_uri() + "?mode=ro", uri=True))


def status():
    """'ausente', 'sem_senha' ou 'ok'. Não cria o banco."""
    if not db_path().is_file():
        return "ausente"
    try:
        with _readonly() as con:
            row = con.execute("SELECT 1 FROM app_auth WHERE id=1").fetchone()
    except sqlite3.Error:
        return "sem_senha"
    return "ok" if row else "sem_senha"


def prepare_existing_database():
    """Aplica as migrações da Folha (como o programa autônomo faz ao iniciar). Nunca cria banco novo."""
    if not db_path().is_file():
        raise FileNotFoundError(f"Banco da Folha não encontrado: {db_path()}")
    module().init_db()


def create_new_database():
    if db_path().is_file():
        raise FileExistsError(f"O banco da Folha já existe: {db_path()}")
    module().init_db()


def verify_password(password):
    if not db_path().is_file():
        raise FileNotFoundError(f"Banco da Folha não encontrado: {db_path()}")
    return module().verify_password(password)


def min_password_length():
    return module().PASSWORD_MIN_LENGTH


def set_password(new_password, confirmation, current_password=None):
    folha = module()
    if status() == "ok":
        if current_password is None or not folha.verify_password(current_password):
            raise ValueError("Senha atual incorreta.")
    if len(new_password) < folha.PASSWORD_MIN_LENGTH:
        raise ValueError(f"Use uma senha com pelo menos {folha.PASSWORD_MIN_LENGTH} caracteres.")
    if new_password != confirmation:
        raise ValueError("A confirmação não corresponde à nova senha.")
    folha.save_password(new_password)


def create_panel(master):
    folha = module()
    folha.use_light_theme()
    return folha.FolhaPanel(
        master, centralized_actions=True, signing_status_callback=signing_status)


def summary():
    if not db_path().is_file():
        return {"status": "ausente"}
    try:
        with _readonly() as con:
            active = con.execute("SELECT COUNT(*) FROM employees WHERE active=1").fetchone()[0]
            total = con.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    except sqlite3.Error as error:
        return {"status": f"erro: {error}"}
    return {"status": "ok", "ativos": active, "total": total}
