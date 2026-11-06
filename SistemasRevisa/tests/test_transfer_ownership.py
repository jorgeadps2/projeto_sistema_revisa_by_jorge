import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from revisa_integrado.core import backup, transfer


class TransferOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.database = self.root / "folha.db"
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT)")
            connection.execute("INSERT INTO records (value) VALUES ('base')")
        self.transfer_dir = self.root / "packages"
        self.transfer_dir.mkdir()
        self.state_path = self.root / "state.json"
        self.state = {
            "maquina_id": "this-machine",
            "titular": False,
            "ultimo_pacote": "SR-previous",
            "ultimo_pacote_criado": 100,
            "resumos_base": {"folha": transfer._digest("folha", self.database)},
            "historico": [],
        }

    def test_resume_unchanged_local_data(self):
        transfer.resume_ownership(
            self.state, self.state_path, {"folha": self.database}, self.transfer_dir)

        saved = transfer.load_state(self.state_path)
        self.assertTrue(saved["titular"])
        self.assertEqual(saved["historico"][-1]["evento"], "retomada_manual")

    def test_refuses_package_missing_an_expected_database(self):
        energy_database = self.root / "energia.db"
        with closing(sqlite3.connect(energy_database)) as connection, connection:
            connection.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT)")
            connection.execute("INSERT INTO records (value) VALUES ('energy')")

        package = self.transfer_dir / "SR-20261030-120000-OTHER-12345678"
        package.mkdir()
        database_copy = package / "folha.db"
        backup.snapshot_db(self.database, database_copy)
        manifest = {
            "formato": transfer.FORMAT_VERSION,
            "id": package.name,
            "maquina_origem": "other-machine",
            "criado_em_epoch": 101,
            "pacote_anterior": self.state["ultimo_pacote"],
            "versao_app": "1.0",
            "bancos": {
                "folha": {
                    "arquivo": database_copy.name,
                    "tamanho": database_copy.stat().st_size,
                    "sha256": backup.sha256_file(database_copy),
                    "resumo_logico": transfer._digest("folha", database_copy),
                }
            },
        }
        manifest_path = package / transfer.MANIFEST
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        (package / transfer.READY_MARKER).write_text(
            backup.sha256_file(manifest_path), encoding="ascii")

        report = transfer.inspect_package(
            package,
            self.state,
            {"folha": self.database, "energia": energy_database},
            "1.0",
        )

        self.assertIn("bancos ausentes no pacote: energia", report["bloqueios"])

    def test_refuses_to_resume_if_local_data_changed(self):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("INSERT INTO records (value) VALUES ('changed')")

        with self.assertRaisesRegex(transfer.TransferError, "mudou desde o último pacote"):
            transfer.resume_ownership(
                self.state, self.state_path, {"folha": self.database}, self.transfer_dir)

        self.assertFalse(self.state["titular"])

    def test_refuses_to_resume_when_newer_external_package_exists(self):
        package = self.transfer_dir / "SR-20261030-120000-OTHER-12345678"
        package.mkdir()
        database_copy = package / "folha.db"
        backup.snapshot_db(self.database, database_copy)
        manifest = {
            "formato": transfer.FORMAT_VERSION,
            "id": package.name,
            "maquina_origem": "other-machine",
            "criado_em_epoch": 101,
            "bancos": {
                "folha": {
                    "arquivo": database_copy.name,
                    "tamanho": database_copy.stat().st_size,
                    "sha256": backup.sha256_file(database_copy),
                }
            },
        }
        manifest_path = package / transfer.MANIFEST
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        (package / transfer.READY_MARKER).write_text(
            backup.sha256_file(manifest_path), encoding="ascii")

        with self.assertRaisesRegex(transfer.TransferError, "pacote mais recente do outro computador"):
            transfer.resume_ownership(
                self.state, self.state_path, {"folha": self.database}, self.transfer_dir)

        self.assertFalse(self.state["titular"])


if __name__ == "__main__":
    unittest.main()
