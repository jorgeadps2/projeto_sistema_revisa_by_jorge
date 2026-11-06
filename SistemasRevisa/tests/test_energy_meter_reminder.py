import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from revisa_integrado.modules import energia
from revisa_integrado.ui.main_window import MainWindow
from revisa_integrado.core import config


class EnergyMeterReminderTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = Path(self.temp_dir.name) / "energia.db"
        with closing(sqlite3.connect(self.database)) as con:
            con.executescript(
                """
                CREATE TABLE meses(id INTEGER PRIMARY KEY, ano INTEGER, mes INTEGER);
                CREATE TABLE ocupantes(
                    id INTEGER PRIMARY KEY, nome TEXT, ativo INTEGER
                );
                CREATE TABLE lancamentos(
                    id INTEGER PRIMARY KEY, mes_id INTEGER, ocupante_id INTEGER,
                    aluguel REAL, cobrar_energia INTEGER, leitura_inicial REAL,
                    leitura_final REAL, leitura_informada INTEGER
                );
                INSERT INTO meses VALUES(1, 2026, 2);
                INSERT INTO meses VALUES(2, 2026, 3);
                INSERT INTO ocupantes VALUES(1, 'ENERGIA PENDENTE', 1);
                INSERT INTO ocupantes VALUES(2, 'SEM ALUGUEL', 1);
                INSERT INTO ocupantes VALUES(3, 'ISENTO DE ENERGIA', 1);
                INSERT INTO ocupantes VALUES(4, 'LEITURA INFORMADA', 1);
                INSERT INTO ocupantes VALUES(5, 'INATIVO', 0);
                INSERT INTO lancamentos VALUES(1, 2, 1, 500, 1, 100, 100, 0);
                INSERT INTO lancamentos VALUES(2, 2, 2, 0, 1, 100, 100, 0);
                INSERT INTO lancamentos VALUES(3, 2, 3, 500, 0, 100, 100, 0);
                INSERT INTO lancamentos VALUES(4, 2, 4, 500, 1, 100, 110, 1);
                INSERT INTO lancamentos VALUES(5, 2, 5, 500, 1, 100, 100, 0);
                """
            )
            con.commit()

    def test_lists_only_active_renters_charged_for_energy_without_readings(self):
        with patch.object(energia, "db_path", return_value=self.database):
            pending = energia.pending_meter_readings(date(2026, 3, 1))

        self.assertEqual(pending, ["ENERGIA PENDENTE"])

    def test_existing_reading_difference_counts_as_informed_without_flag(self):
        with closing(sqlite3.connect(self.database)) as con:
            con.execute(
                "INSERT INTO ocupantes VALUES(6, 'LEITURA JA PREENCHIDA', 1)"
            )
            con.execute(
                "INSERT INTO lancamentos VALUES(6, 2, 6, 500, 1, 26447, 26992, 0)"
            )
            con.commit()

        with patch.object(energia, "db_path", return_value=self.database):
            pending = energia.pending_meter_readings(date(2026, 3, 1))

        self.assertNotIn("LEITURA JA PREENCHIDA", pending)

    def test_uses_latest_available_month_before_current_month_is_created(self):
        with closing(sqlite3.connect(self.database)) as con:
            con.execute("DELETE FROM lancamentos WHERE mes_id=2")
            con.execute(
                "INSERT INTO lancamentos VALUES(6, 1, 1, 500, 1, 100, 100, 1)"
            )
            con.commit()

        with patch.object(energia, "db_path", return_value=self.database):
            pending = energia.pending_meter_readings(date(2026, 3, 1))

        self.assertEqual(pending, ["ENERGIA PENDENTE"])

    def test_selected_tenant_is_reminded_even_without_energy_charge(self):
        with closing(sqlite3.connect(self.database)) as con:
            con.execute(
                "ALTER TABLE ocupantes ADD COLUMN avisar_leitura INTEGER NOT NULL DEFAULT 1"
            )
            con.execute("UPDATE ocupantes SET avisar_leitura=0")
            con.execute(
                "INSERT INTO ocupantes VALUES(6, 'AVISO SELECIONADO', 1, 1)"
            )
            con.execute(
                "INSERT INTO lancamentos VALUES(6, 2, 6, 0, 0, 100, 100, 0)"
            )
            con.commit()

        with patch.object(energia, "db_path", return_value=self.database):
            pending = energia.pending_meter_readings(date(2026, 3, 1))

        self.assertEqual(pending, ["AVISO SELECIONADO"])

    def test_old_database_without_confirmation_column_uses_reading_difference(self):
        legacy = Path(self.temp_dir.name) / "legacy.db"
        with closing(sqlite3.connect(legacy)) as con:
            con.executescript(
                """
                CREATE TABLE meses(id INTEGER PRIMARY KEY, ano INTEGER, mes INTEGER);
                CREATE TABLE ocupantes(
                    id INTEGER PRIMARY KEY, nome TEXT, ativo INTEGER
                );
                CREATE TABLE lancamentos(
                    id INTEGER PRIMARY KEY, mes_id INTEGER, ocupante_id INTEGER,
                    aluguel REAL, cobrar_energia INTEGER, leitura_inicial REAL,
                    leitura_final REAL
                );
                INSERT INTO meses VALUES(1, 2026, 3);
                INSERT INTO ocupantes VALUES(1, 'LEITURA A CONFIRMAR', 1);
                INSERT INTO ocupantes VALUES(2, 'LEITURA JA LANÇADA', 1);
                INSERT INTO lancamentos VALUES(1, 1, 1, 500, 1, 100, 100);
                INSERT INTO lancamentos VALUES(2, 1, 2, 500, 1, 100, 110);
                """
            )
            con.commit()

        with patch.object(energia, "db_path", return_value=legacy):
            pending = energia.pending_meter_readings(date(2026, 3, 1))

        self.assertEqual(pending, ["LEITURA A CONFIRMAR"])

    def test_startup_prompt_confirms_previous_month_and_persists_ok(self):
        window = MainWindow.__new__(MainWindow)
        window.meter_reminder_prompted_date = None
        window.after = Mock()
        window.log = Mock()
        settings = {"leituras_confirmadas": []}
        with patch("revisa_integrado.ui.main_window.date") as today, \
                patch.object(config, "load", return_value=settings), \
                patch.object(config, "save") as save, \
                patch.object(window, "_ask_meter_reading_status",
                             return_value=True) as prompt:
            today.today.return_value = date(2026, 11, 5)
            window._prompt_meter_readings()

        prompt.assert_called_once_with(date(2026, 10, 1))
        save.assert_called_once_with({"leituras_confirmadas": ["2026-10"]})
        window.after.assert_not_called()

    def test_startup_prompt_repeats_daily_until_reading_is_ok(self):
        window = MainWindow.__new__(MainWindow)
        window.meter_reminder_prompted_date = None
        window.after = Mock()
        with patch("revisa_integrado.ui.main_window.date") as today, \
                patch.object(config, "load", return_value={"leituras_confirmadas": []}), \
                patch.object(window, "_ask_meter_reading_status",
                             return_value=False) as prompt:
            today.today.return_value = date(2026, 3, 4)
            window._prompt_meter_readings()

            prompt.assert_not_called()
            window.after.assert_not_called()

            today.today.return_value = date(2026, 3, 5)
            window._prompt_meter_readings()

        prompt.assert_called_once_with(date(2026, 2, 1))
        window.after.assert_called_once_with(
            24 * 60 * 60 * 1000, window._prompt_meter_readings)

    def test_confirmed_month_is_not_prompted_again_after_reopening(self):
        window = MainWindow.__new__(MainWindow)
        window.meter_reminder_prompted_date = None
        with patch("revisa_integrado.ui.main_window.date") as today, \
                patch.object(config, "load", return_value={
                    "leituras_confirmadas": ["2026-10"],
                }), \
                patch.object(window, "_ask_meter_reading_status") as prompt:
            today.today.return_value = date(2026, 11, 6)
            window._prompt_meter_readings()

        prompt.assert_not_called()

    def test_not_ok_reprompts_the_next_day(self):
        window = MainWindow.__new__(MainWindow)
        window.meter_reminder_prompted_date = None
        window.after = Mock()
        today = Mock()
        today.today.side_effect = [date(2026, 11, 5), date(2026, 11, 6)]
        with patch("revisa_integrado.ui.main_window.date", today), \
                patch.object(config, "load", return_value={"leituras_confirmadas": []}), \
                patch.object(window, "_ask_meter_reading_status",
                             return_value=False) as prompt:
            window._prompt_meter_readings()
            callback = window.after.call_args.args[1]
            callback()

        self.assertEqual(prompt.call_count, 2)
        self.assertEqual(prompt.call_args.args[0], date(2026, 10, 1))

    def test_confirmations_survive_config_save(self):
        path = Path(self.temp_dir.name) / "config.json"
        data = {
            "transferencia_habilitada": True,
            "pasta_transferencia": "shared",
            "pasta_backup_adicional": "",
            "leituras_confirmadas": ["2026-10"],
        }
        config.save(data, path)
        loaded = config.load(path)

        self.assertEqual(loaded["leituras_confirmadas"], ["2026-10"])
        config.save(loaded, path)
        self.assertEqual(config.load(path)["leituras_confirmadas"], ["2026-10"])

    def test_startup_prompt_shows_message_error_if_confirmation_storage_fails(self):
        window = MainWindow.__new__(MainWindow)
        window.meter_reminder_prompted_date = None
        window.after = Mock()
        window.log = Mock()
        with patch("revisa_integrado.ui.main_window.date") as today, \
                patch.object(config, "load", side_effect=OSError("read failed")), \
                patch("revisa_integrado.ui.main_window.messagebox.showerror") as error:
            today.today.return_value = date(2026, 11, 5)
            window._prompt_meter_readings()

        error.assert_called_once()
        window.after.assert_not_called()

    def test_startup_prompt_does_not_repeat_twice_on_same_day(self):
        window = MainWindow.__new__(MainWindow)
        window.meter_reminder_prompted_date = None
        window.after = Mock()
        with patch("revisa_integrado.ui.main_window.date") as today, \
                patch.object(config, "load", return_value={"leituras_confirmadas": []}), \
                patch.object(window, "_ask_meter_reading_status",
                             return_value=False) as prompt:
            today.today.return_value = date(2026, 11, 5)
            window._prompt_meter_readings()
            window._prompt_meter_readings()
        prompt.assert_called_once()


if __name__ == "__main__":
    unittest.main()
