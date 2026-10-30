import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from revisa_integrado.core import backup, config


class BackupMirrorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.database = self.root / "folha.db"
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT)")
            connection.execute("INSERT INTO records (value) VALUES ('preservado')")
        self.primary = self.root / "primary"
        self.additional = self.root / "additional"

    def test_mirror_is_verified_and_does_not_replace_previous_copies(self):
        source, _ = backup.create_backup({"folha": self.database}, self.primary, "1.0")

        first = backup.mirror_backup(source, self.additional)
        second = backup.mirror_backup(source, self.additional)

        self.assertNotEqual(first, second)
        self.assertTrue(backup.verify_backup(first)[0])
        self.assertTrue(backup.verify_backup(second)[0])
        self.assertTrue(backup.verify_backup(source)[0])

    def test_mirror_rejects_primary_folder_as_additional_destination(self):
        source, _ = backup.create_backup({"folha": self.database}, self.primary, "1.0")

        with self.assertRaisesRegex(ValueError, "diferente da pasta principal"):
            backup.mirror_backup(source, self.primary)

    def test_mirror_rejects_destination_nested_in_primary_folder(self):
        source, _ = backup.create_backup({"folha": self.database}, self.primary, "1.0")

        with self.assertRaisesRegex(ValueError, "diferente da pasta principal"):
            backup.mirror_backup(source, self.primary / "additional")

    def test_config_preserves_additional_backup_folder(self):
        config_path = self.root / "config.json"
        config.save({"pasta_backup_adicional": str(self.additional)}, config_path)

        settings = config.load(config_path)

        self.assertEqual(config.additional_backup_dir(settings), self.additional)


if __name__ == "__main__":
    unittest.main()
