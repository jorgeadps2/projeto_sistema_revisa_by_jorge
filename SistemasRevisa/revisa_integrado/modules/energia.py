"""Adaptador do Controle de Energia e Água (controle_energia_agua.py, sem duplicar regras)."""
import os
import sqlite3
import tempfile
from contextlib import closing
from datetime import date
from pathlib import Path

from ..core import backup, paths
from . import folha

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


def exit_backup_path():
    return Path(folha.module().AUTO_BACKUP_DIR) / "backup_energia_saida.db"


def save_exit_backup():
    target = exit_backup_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".energia-backup-", dir=target.parent) as temp:
        snapshot = Path(temp) / target.name
        backup.snapshot_db(db_path(), snapshot)
        with closing(sqlite3.connect(snapshot)) as con:
            con.execute("PRAGMA journal_mode=DELETE")
        integrity = backup.integrity_check(snapshot)
        if integrity != "ok":
            raise ValueError(f"Backup de Energia e Água inválido: {integrity}")
        os.replace(snapshot, target)
    return target


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


def pending_meter_readings(today=None):
    today = today or date.today()
    path = db_path()
    if not path.is_file():
        return []
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as con:
        con.row_factory = sqlite3.Row
        columns = {row["name"] for row in con.execute("PRAGMA table_info(lancamentos)")}
        occupant_columns = {
            row["name"] for row in con.execute("PRAGMA table_info(ocupantes)")
        }
        if "leitura_informada" in columns:
            confirmed = (
                "CASE WHEN COALESCE(l.leitura_informada, 0)=1 OR "
                "COALESCE(l.leitura_final, 0) != "
                "COALESCE(l.leitura_inicial, 0) THEN 1 ELSE 0 END"
            )
        else:
            confirmed = (
                "CASE WHEN COALESCE(l.leitura_final, 0) != "
                "COALESCE(l.leitura_inicial, 0) THEN 1 ELSE 0 END"
            )
        rent = "COALESCE(l.aluguel, 0)" if "aluguel" in columns else "0"
        energy_charge = "COALESCE(l.cobrar_energia, 1)" if "cobrar_energia" in columns else "1"
        if "avisar_leitura" in occupant_columns:
            reading_alert = "COALESCE(o.avisar_leitura, 0)"
            eligibility = "avisar_leitura=1"
        else:
            reading_alert = "1"
            eligibility = "aluguel>0 AND cobrar_energia=1"
        rows = con.execute(
            f"""
            WITH ranked AS (
                SELECT o.nome, {rent} AS aluguel, {energy_charge} AS cobrar_energia,
                       {reading_alert} AS avisar_leitura,
                       CASE WHEN m.ano=? AND m.mes=? THEN {confirmed} ELSE 0 END
                           AS leitura_informada,
                       ROW_NUMBER() OVER (
                           PARTITION BY o.id
                           ORDER BY CASE WHEN m.ano=? AND m.mes=? THEN 0 ELSE 1 END,
                                    m.ano DESC, m.mes DESC
                       ) AS ordem
                FROM ocupantes o
                JOIN lancamentos l ON l.ocupante_id=o.id
                JOIN meses m ON m.id=l.mes_id
                WHERE o.ativo=1 AND {reading_alert}=1 AND m.ano*100+m.mes<=?
            )
            SELECT nome FROM ranked
            WHERE ordem=1 AND {eligibility} AND leitura_informada=0
            ORDER BY nome
            """,
            (today.year, today.month, today.year, today.month,
             today.year * 100 + today.month),
        ).fetchall()
    return [row["nome"] for row in rows]
