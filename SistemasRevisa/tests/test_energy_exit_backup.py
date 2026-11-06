import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from revisa_integrado.core import backup
from revisa_integrado.modules import energia, folha
from revisa_integrado.ui.main_window import MainWindow


class EnergyExitBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.database = self.root / "energia.db"
        with closing(sqlite3.connect(self.database)) as con, con:
            con.execute("CREATE TABLE records (value TEXT)")
            con.execute("INSERT INTO records VALUES ('saved')")
        self.destination = self.root / "Backup Folha Revisa"
        self.energy_path = patch.object(energia, "db_path", return_value=self.database)
        self.payroll_module = patch.object(
            folha, "module",
            return_value=SimpleNamespace(AUTO_BACKUP_DIR=str(self.destination)),
        )
        self.energy_path.start()
        self.payroll_module.start()
        self.addCleanup(self.energy_path.stop)
        self.addCleanup(self.payroll_module.stop)

    def test_saves_beside_payroll_without_overwriting_payroll_backup(self):
        self.destination.mkdir()
        payroll_backup = self.destination / "backup_saida.db"
        payroll_backup.write_bytes(b"payroll backup")

        target = energia.save_exit_backup()

        self.assertEqual(target, self.destination / "backup_energia_saida.db")
        self.assertEqual(backup.integrity_check(target), "ok")
        self.assertEqual(backup.logical_digest(target), backup.logical_digest(self.database))
        self.assertEqual(payroll_backup.read_bytes(), b"payroll backup")
        self.assertEqual(len(list(self.destination.iterdir())), 2)

    def test_updates_backup_including_committed_wal_data(self):
        target = energia.save_exit_backup()
        with closing(sqlite3.connect(self.database)) as con, con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("INSERT INTO records VALUES ('new')")
            con.commit()
            self.assertEqual(energia.save_exit_backup(), target)
            self.assertEqual(
                backup.logical_digest(target), backup.logical_digest(self.database))
            self.assertEqual(con.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertEqual(list(self.destination.iterdir()), [target])

    def test_invalid_snapshot_preserves_previous_backup_and_reports_error(self):
        target = energia.save_exit_backup()
        previous = target.read_bytes()
        with patch.object(backup, "integrity_check", return_value="invalid"):
            with self.assertRaisesRegex(ValueError, "invalid"):
                energia.save_exit_backup()
        self.assertEqual(target.read_bytes(), previous)
        self.assertEqual(list(self.destination.iterdir()), [target])

    def test_replace_failure_preserves_previous_backup_and_reports_error(self):
        target = energia.save_exit_backup()
        previous = target.read_bytes()
        with patch.object(energia.os, "replace", side_effect=PermissionError("blocked")):
            with self.assertRaisesRegex(PermissionError, "blocked"):
                energia.save_exit_backup()
        self.assertEqual(target.read_bytes(), previous)
        self.assertEqual(list(self.destination.iterdir()), [target])

    def test_missing_database_does_not_create_empty_backup(self):
        self.database.unlink()
        with self.assertRaises(sqlite3.OperationalError):
            energia.save_exit_backup()
        self.assertFalse((self.destination / "backup_energia_saida.db").exists())

    def test_close_modules_saves_energy_after_connection_is_closed(self):
        window = SimpleNamespace(
            modules={"energia": {"instance": Mock(), "container": Mock()}},
            log=Mock(),
        )
        instance = window.modules["energia"]["instance"]
        with patch.object(energia, "save_exit_backup") as save:
            save.side_effect = lambda: instance.encerrar.assert_called_once_with()
            self.assertEqual(MainWindow.close_modules(window), [])
        save.assert_called_once_with()

    def test_close_modules_reports_backup_failure(self):
        window = SimpleNamespace(
            modules={"energia": {"instance": Mock(), "container": Mock()}},
            log=Mock(),
        )
        with patch.object(energia, "save_exit_backup", side_effect=OSError("backup failed")):
            self.assertEqual(
                MainWindow.close_modules(window), ["energia: backup failed"])
        window.log.exception.assert_called_once()


if __name__ == "__main__":
    unittest.main()
