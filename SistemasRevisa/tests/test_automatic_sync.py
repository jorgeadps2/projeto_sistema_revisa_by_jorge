import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from revisa_integrado.core import transfer
from revisa_integrado.ui import main_window
from revisa_integrado.ui.main_window import MainWindow


class AutomaticSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.shared = self.root / "Banco de Dados Sistema"
        self.settings = {
            "transferencia_habilitada": True,
            "pasta_transferencia": str(self.shared),
            "pasta_backup_adicional": "",
        }

    def computer(self, name):
        root = self.root / name
        root.mkdir()
        databases = {key: root / f"{key}.db" for key in ("folha", "energia")}
        for key, path in databases.items():
            with closing(sqlite3.connect(path)) as con, con:
                con.execute("CREATE TABLE records (value TEXT)")
                con.execute("INSERT INTO records VALUES (?)", (name,))
                if key == "folha":
                    con.execute("CREATE TABLE app_auth (id INTEGER PRIMARY KEY, password TEXT)")
                    con.execute("INSERT INTO app_auth VALUES (1, ?)", (name,))
        window = SimpleNamespace(
            log=Mock(), session=SimpleNamespace(authenticated=True, logout=Mock()),
            databases=Mock(return_value=databases), close_modules=Mock(return_value=[]),
            destroy=Mock(), busy=False,
        )
        window._automatic_sync_shutdown = lambda: MainWindow._automatic_sync_shutdown(window)
        return root, databases, window

    @contextmanager
    def environment(self, root):
        with patch.object(main_window.config, "load", return_value=self.settings), \
                patch.object(main_window.paths, "transfer_state_path", return_value=root / "state.json"), \
                patch.object(main_window.paths, "backups_dir", return_value=root / "backups"):
            yield

    def test_close_then_open_other_pc_transfers_both_banks_and_returns_changes(self):
        first_root, first_dbs, first = self.computer("first")
        second_root, second_dbs, second = self.computer("second")
        with self.environment(first_root), \
                patch.object(main_window.messagebox, "showinfo"):
            MainWindow.on_close(first)
        first.destroy.assert_called_once()
        first.close_modules.assert_called_once()
        self.assertTrue(transfer.load_state(first_root / "state.json")["titular"])
        package = transfer.list_packages(self.shared)[0]
        manifest, problems = transfer.read_package(package)
        self.assertEqual(problems, [])
        self.assertEqual(set(manifest["bancos"]), {"folha", "energia"})

        with self.environment(second_root):
            MainWindow._automatic_sync_startup(second)
        self.assertEqual(second.auto_sync_notice, "ok")
        for key in first_dbs:
            self.assertEqual(
                transfer._digest(key, first_dbs[key]),
                transfer._digest(key, second_dbs[key]))
        with closing(sqlite3.connect(second_dbs["folha"])) as con:
            self.assertEqual(con.execute("SELECT password FROM app_auth").fetchone()[0], "second")
        for path in second_dbs.values():
            with closing(sqlite3.connect(path)) as con, con:
                con.execute("INSERT INTO records VALUES ('changed on second')")
        with self.environment(second_root), \
                patch.object(main_window.messagebox, "showinfo"):
            MainWindow.on_close(second)
        with self.environment(first_root):
            MainWindow._automatic_sync_startup(first)
        self.assertEqual(first.auto_sync_notice, "ok")
        for key in first_dbs:
            self.assertEqual(
                transfer._digest(key, first_dbs[key]),
                transfer._digest(key, second_dbs[key]))
        with closing(sqlite3.connect(first_dbs["folha"])) as con:
            self.assertEqual(con.execute("SELECT password FROM app_auth").fetchone()[0], "first")
        self.assertTrue(list((first_root / "backups").iterdir()))
        self.assertTrue(list((second_root / "backups").iterdir()))

    def test_waiting_computer_does_not_export_or_overwrite_shared_package(self):
        root, _, window = self.computer("waiting")
        state = transfer.load_state(root / "state.json", default_titular=False)
        with self.environment(root), patch.object(transfer, "export_package") as export:
            self.assertIsNone(window._automatic_sync_shutdown())
        export.assert_not_called()
        self.assertFalse(transfer.load_state(root / "state.json")["titular"])
        self.assertFalse(state["titular"])

    def test_receiver_can_reopen_without_importing_the_same_package_again(self):
        first_root, _, first = self.computer("first")
        second_root, second_dbs, second = self.computer("second")
        with self.environment(first_root):
            first._automatic_sync_shutdown()
        with self.environment(second_root):
            MainWindow._automatic_sync_startup(second)
            self.assertEqual(second.auto_sync_notice, "ok")
            for path in second_dbs.values():
                with closing(sqlite3.connect(path)) as con, con:
                    con.execute("INSERT INTO records VALUES ('local work after receiving')")
            before = {
                key: transfer._digest(key, path) for key, path in second_dbs.items()
            }
            with patch.object(transfer, "import_package") as import_package:
                MainWindow._automatic_sync_startup(second)
            import_package.assert_not_called()
            self.assertEqual(second.auto_sync_notice, "ok")
            self.assertIsNone(MainWindow.transfer_blocked(second))
        self.assertEqual(
            before, {key: transfer._digest(key, path) for key, path in second_dbs.items()})

    def test_corrupted_received_package_still_blocks_reopening(self):
        first_root, _, first = self.computer("first")
        second_root, _, second = self.computer("second")
        with self.environment(first_root):
            package = first._automatic_sync_shutdown()
        with self.environment(second_root):
            MainWindow._automatic_sync_startup(second)
            self.assertEqual(second.auto_sync_notice, "ok")
            with closing(sqlite3.connect(package / "energia.db")) as con, con:
                con.execute("INSERT INTO records VALUES ('tampered')")
            MainWindow._automatic_sync_startup(second)
            self.assertEqual(second.auto_sync_notice, "falha")
            self.assertIn("alterado", MainWindow.transfer_blocked(second))

    def test_same_computer_can_reopen_after_closing_without_other_pc(self):
        root, _, window = self.computer("same-computer")

        for _ in range(3):
            with self.environment(root):
                window._automatic_sync_shutdown()
                MainWindow._automatic_sync_startup(window, prompt_for_resume=True)
                self.assertFalse(window.auto_sync_resume_pending)
                self.assertEqual(window.auto_sync_notice, "ok")
                self.assertIsNone(MainWindow.transfer_blocked(window))
            self.assertTrue(transfer.load_state(root / "state.json")["titular"])

    def test_other_pc_imports_after_first_pc_closed_several_times(self):
        first_root, first_dbs, first = self.computer("first")
        second_root, second_dbs, second = self.computer("second")
        for _ in range(3):
            with self.environment(first_root):
                first._automatic_sync_shutdown()
                MainWindow._automatic_sync_startup(first)
        with self.environment(second_root):
            MainWindow._automatic_sync_startup(second)
        self.assertEqual(second.auto_sync_notice, "ok")
        for key in first_dbs:
            self.assertEqual(
                transfer._digest(key, first_dbs[key]),
                transfer._digest(key, second_dbs[key]))

    def test_manual_send_cedes_turn_to_other_computer(self):
        root, databases, _ = self.computer("sender")
        state = transfer.load_state(root / "state.json")
        transfer.export_package(
            databases, self.shared, state, root / "state.json", main_window.APP_VERSION, cede_turn=True)
        self.assertFalse(transfer.load_state(root / "state.json")["titular"])

    def test_existing_holder_receives_newer_external_package_before_editing(self):
        first_root, first_dbs, first = self.computer("first")
        second_root, second_dbs, second = self.computer("second")
        with self.environment(first_root):
            original = first._automatic_sync_shutdown()
        state = transfer.load_state(second_root / "state.json")
        transfer.import_package(
            original, state, second_root / "state.json", second_dbs,
            second_root / "backups", main_window.APP_VERSION, accept_warnings=True)
        with closing(sqlite3.connect(second_dbs["energia"])) as con, con:
            con.execute("INSERT INTO records VALUES ('notebook change')")
        with self.environment(second_root):
            second._automatic_sync_shutdown()
        # A previous installation can still believe it owns the data.
        state = transfer.load_state(first_root / "state.json")
        state["titular"] = True
        transfer.save_state(first_root / "state.json", state)
        with self.environment(first_root):
            MainWindow._automatic_sync_startup(first)
        self.assertEqual(first.auto_sync_notice, "ok")
        self.assertEqual(
            transfer._digest("energia", first_dbs["energia"]),
            transfer._digest("energia", second_dbs["energia"]))

    def test_conflicting_branch_reports_failure_and_blocks_editing_and_export(self):
        first_root, first_dbs, first = self.computer("first")
        second_root, second_dbs, second = self.computer("second")
        with self.environment(first_root):
            sent = first._automatic_sync_shutdown()
        # The notebook exports before MEGA has delivered the first PC's package.
        sent.rename(self.root / sent.name)
        with self.environment(second_root):
            second._automatic_sync_shutdown()
        before = transfer._digest("energia", first_dbs["energia"])
        with self.environment(first_root):
            MainWindow._automatic_sync_startup(first)
            self.assertEqual(first.auto_sync_notice, "falha")
            self.assertIn("conflito", MainWindow.transfer_blocked(first))
            status, color = MainWindow._login_sync_status(first)
            self.assertEqual(status, "Sincronização: falha")
        self.assertEqual(transfer._digest("energia", first_dbs["energia"]), before)
        # The holder must not overwrite an external branch either.
        state = transfer.load_state(first_root / "state.json")
        state["titular"] = True
        transfer.save_state(first_root / "state.json", state)
        with self.assertRaisesRegex(transfer.TransferError, "outro computador"):
            transfer.export_package(
                first_dbs, self.shared, state, first_root / "state.json",
                main_window.APP_VERSION)

    def test_disabled_sync_does_not_export(self):
        root, _, window = self.computer("disabled")
        self.settings["transferencia_habilitada"] = False
        with self.environment(root), patch.object(transfer, "export_package") as export:
            self.assertIsNone(window._automatic_sync_shutdown())
        export.assert_not_called()

    def test_closing_login_without_authentication_does_not_export(self):
        _, _, window = self.computer("login")
        window.session.authenticated = False
        with patch.object(main_window.config, "load") as load:
            self.assertIsNone(window._automatic_sync_shutdown())
        load.assert_not_called()

    def test_export_failure_keeps_window_open_and_reports_failure(self):
        root, _, window = self.computer("failed")
        with self.environment(root), \
                patch.object(transfer, "export_package", side_effect=OSError("offline")), \
                patch.object(main_window.messagebox, "showerror") as error, \
                patch.object(main_window.messagebox, "showinfo") as info:
            MainWindow.on_close(window)
        window.destroy.assert_not_called()
        window.session.logout.assert_not_called()
        error.assert_called_once()
        info.assert_not_called()
        self.assertTrue(transfer.load_state(root / "state.json")["titular"])

    def test_backup_success_message_is_short_when_sync_is_disabled(self):
        root, _, window = self.computer("backup-success")
        window.modules = {"energia": object()}
        self.settings["transferencia_habilitada"] = False
        with self.environment(root), \
                patch.object(main_window.messagebox, "showinfo") as info:
            MainWindow.on_close(window)

        info.assert_called_once_with(
            "Backup finalizado", "Backup finalizado com sucesso.", parent=window)
        window.destroy.assert_called_once()

    def test_backup_success_message_does_not_mention_mega(self):
        _, _, window = self.computer("backup-sync")
        window._automatic_sync_shutdown = Mock(return_value=Path("package"))
        with patch.object(main_window.messagebox, "showinfo") as info:
            MainWindow.on_close(window)

        self.assertEqual(info.call_args.args[0], "Backup finalizado")
        self.assertEqual(info.call_args.args[1], "Backup finalizado com sucesso.")
        window.destroy.assert_called_once()

    def test_backup_failure_message_is_short_and_keeps_window_open(self):
        _, _, window = self.computer("backup-failed")
        window.close_modules.return_value = ["energia: backup failed"]
        with patch.object(main_window.messagebox, "showwarning") as warning:
            MainWindow.on_close(window)

        warning.assert_called_once_with(
            "Backup não finalizado",
            "Não foi possível finalizar o backup. O sistema permanecerá aberto.",
            parent=window)
        window.destroy.assert_not_called()

    def test_module_close_failure_does_not_export_or_exit(self):
        _, _, window = self.computer("module-error")
        window.close_modules.return_value = ["could not save"]
        window._automatic_sync_shutdown = Mock()
        with patch.object(main_window.messagebox, "showwarning") as warning:
            MainWindow.on_close(window)
        warning.assert_called_once()
        window._automatic_sync_shutdown.assert_not_called()
        window.destroy.assert_not_called()

    def test_busy_window_waits_before_closing_and_exporting(self):
        _, _, window = self.computer("busy")
        window.busy = True
        with patch.object(main_window.messagebox, "showinfo"):
            MainWindow.on_close(window)
        window.close_modules.assert_not_called()
        window.destroy.assert_not_called()

    def test_integrated_payroll_does_not_replace_package_with_legacy_backup(self):
        payroll = main_window.folha.module()
        for integrated in (True, False):
            with self.subTest(integrated=integrated):
                panel = SimpleNamespace(
                    centralized_actions=integrated, configure=Mock(),
                    load_newer_mega_backup=Mock(), _style=Mock(), _build=Mock(),
                    bind_all=Mock(), _apply_dialog_branding=Mock(), refresh_all=Mock(),
                )
                with patch.object(payroll.tk, "StringVar"):
                    payroll.FolhaBase._init_folha(panel)
                self.assertEqual(panel.load_newer_mega_backup.call_count, 0 if integrated else 1)


if __name__ == "__main__":
    unittest.main()
