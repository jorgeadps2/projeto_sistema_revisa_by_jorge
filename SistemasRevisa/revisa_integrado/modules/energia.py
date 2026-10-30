"""Adaptador do Controle de Energia e Água (controle_energia_agua.py, sem duplicar regras)."""
import sqlite3
from contextlib import closing
from pathlib import Path

from ..core import paths

KEY = "energia"
TITLE = "Energia e Água"


def module():
    paths.ensure_module_paths()
    import controle_energia_agua
    return controle_energia_agua


def db_path():
    return Path(module().DB_PATH)


def access_path():
    return Path(module().ACESSO_PATH)


def data_dir():
    return Path(module().PASTA)


def change_password(parent):
    energia = module()
    energia.usar_tema_claro()
    return bool(energia.solicitar_acesso(parent, alterar=True))


def create_app(container):
    energia = module()
    energia.usar_tema_claro()
    return energia.App(container, embutido=True)


def summary():
    if not db_path().is_file():
        return {"status": "ausente"}
    try:
        with closing(sqlite3.connect(db_path().resolve().as_uri() + "?mode=ro", uri=True)) as con:
            tenants = con.execute("SELECT COUNT(*) FROM ocupantes").fetchone()[0]
            last = con.execute("SELECT ano, mes FROM meses ORDER BY ano DESC, mes DESC LIMIT 1").fetchone()
    except sqlite3.Error as error:
        return {"status": f"erro: {error}"}
    return {"status": "ok", "ocupantes": tenants, "ultimo_mes": f"{last[1]:02d}/{last[0]}" if last else "—"}
