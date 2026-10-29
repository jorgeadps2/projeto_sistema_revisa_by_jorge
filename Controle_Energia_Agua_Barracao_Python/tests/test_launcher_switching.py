import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date
from unittest.mock import Mock, patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "Iniciar_Sistemas_Revisa.py"
SPEC = importlib.util.spec_from_file_location("central_launcher", MODULE_PATH)
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


class SigningExpiryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "assinatura_digital.json"
        self.config = {
            "certificado": r"C:\certificados\atual.pfx",
            "validade_certificado": r"C:\certificados\atual.pfx",
            "validade": "2026-12-15",
        }
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")
        self.config_path_patch = patch.object(
            launcher, "SIGNING_CONFIG_PATH", self.config_path
        )
        self.config_path_patch.start()
        self.addCleanup(self.config_path_patch.stop)
        self.addCleanup(self.temp_dir.cleanup)

    def test_displays_validity_near_system_buttons(self):
        text, foreground, background = launcher.signing_expiry_display(
            today=date(2026, 10, 29)
        )
        self.assertEqual(
            text,
            "Assinatura digital válida até 15/12/2026 (47 dias restantes)",
        )
        self.assertEqual(foreground, "#991B1B")
        self.assertEqual(background, "#F0FDF4")

    def test_warns_when_certificate_expires_within_30_days(self):
        self.config["validade"] = "2026-11-15"
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")
        text, foreground, background = launcher.signing_expiry_display(
            today=date(2026, 10, 29)
        )
        self.assertEqual(text, "Assinatura digital vence em 17 dia(s) (15/11/2026)")
        self.assertEqual(foreground, "#991B1B")
        self.assertEqual(background, "#FEF2F2")

    def test_warns_when_certificate_is_expired(self):
        self.config["validade"] = "2026-10-28"
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")
        text, foreground, background = launcher.signing_expiry_display(
            today=date(2026, 10, 29)
        )
        self.assertEqual(text, "Assinatura digital VENCEU em 28/10/2026")
        self.assertEqual(foreground, "#991B1B")
        self.assertEqual(background, "#FEF2F2")

    def test_does_not_show_expiry_for_a_different_certificate(self):
        self.config["certificado"] = r"C:\certificados\novo.pfx"
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")
        text, _, _ = launcher.signing_expiry_display()
        self.assertEqual(text, "Assinatura digital: validade indisponível")


class SwitchingTests(unittest.TestCase):
    def setUp(self):
        self.app = Mock()
        self.app.active_process = None
        self.app.pending_program = None
        self.app.switching_program = False
        self.app.closing_launcher = False
        self.target = Mock()
        self.target.is_file.return_value = True
        self.program = (self.target, ["python", "program.py"], Path.cwd(), "teste")

    def test_closing_launcher_without_running_program_destroys_immediately(self):
        launcher.Launcher._close_launcher(self.app)
        self.assertTrue(self.app.closing_launcher)
        self.app.destroy.assert_called_once_with()

    def test_closing_launcher_requests_program_close_and_waits(self):
        self.app.active_process = Mock(pid=123)
        self.app.active_process.poll.return_value = None
        with patch.object(launcher, "request_program_close", return_value=True) as close:
            launcher.Launcher._close_launcher(self.app)
            self.app._wait_for_program_close.assert_called_once_with()
            launcher.Launcher._wait_for_program_close(self.app)
        self.assertTrue(self.app.closing_launcher)
        self.assertTrue(self.app.switching_program)
        close.assert_called_once_with(123)
        self.app.destroy.assert_not_called()
        self.app.after.assert_called_once_with(150, self.app._wait_for_program_close)

    def test_launcher_closes_after_active_program_exits(self):
        self.app.active_process = Mock(pid=123)
        self.app.active_process.poll.return_value = 0
        self.app.closing_launcher = True
        launcher.Launcher._wait_for_program_close(self.app)
        self.app.destroy.assert_called_once_with()
        self.app._launch_pending_program.assert_not_called()

    def test_closing_launcher_while_switching_cancels_pending_program(self):
        self.app.active_process = Mock(pid=123)
        self.app.active_process.poll.return_value = None
        self.app.switching_program = True
        self.app.pending_program = self.program
        launcher.Launcher._close_launcher(self.app)
        self.assertTrue(self.app.closing_launcher)
        self.assertIsNone(self.app.pending_program)
        self.app._wait_for_program_close.assert_not_called()

    def test_first_program_opens_immediately(self):
        launcher.Launcher._start(self.app, *self.program)
        self.assertEqual(self.app.pending_program, self.program)
        self.app._launch_pending_program.assert_called_once_with()

    def test_running_program_must_close_first(self):
        self.app.active_process = Mock(pid=123)
        self.app.active_process.poll.return_value = None
        launcher.Launcher._start(self.app, *self.program)
        self.assertTrue(self.app.switching_program)
        self.app._wait_for_program_close.assert_called_once_with()
        self.app._launch_pending_program.assert_not_called()

    def test_latest_click_wins_without_starting_duplicate_switches(self):
        self.app.switching_program = True
        launcher.Launcher._start(self.app, *self.program)
        self.assertEqual(self.app.pending_program, self.program)
        self.app._wait_for_program_close.assert_not_called()
        self.app._launch_pending_program.assert_not_called()

    def test_waits_until_process_exits_and_requests_close_only_once(self):
        self.app.active_process = Mock(pid=123)
        self.app.active_process.poll.return_value = None
        self.app.close_requested = False
        self.app.close_deadline = time.monotonic() + 30
        with patch.object(launcher, "request_program_close", return_value=True) as close:
            launcher.Launcher._wait_for_program_close(self.app)
            launcher.Launcher._wait_for_program_close(self.app)
        close.assert_called_once_with(123)
        self.assertEqual(self.app.after.call_count, 2)
        self.app._launch_pending_program.assert_not_called()
        self.app.active_process.poll.return_value = 0
        launcher.Launcher._wait_for_program_close(self.app)
        self.assertIsNone(self.app.active_process)
        self.assertFalse(self.app.switching_program)
        self.app._launch_pending_program.assert_called_once_with()

    def test_timeout_keeps_previous_process_without_opening_another(self):
        previous = Mock(pid=123)
        previous.poll.return_value = None
        self.app.active_process = previous
        self.app.close_requested = True
        self.app.close_deadline = 0
        with patch.object(launcher.messagebox, "showwarning") as warning:
            launcher.Launcher._wait_for_program_close(self.app)
        warning.assert_called_once()
        self.assertIs(self.app.active_process, previous)
        self.assertIsNone(self.app.pending_program)
        self.app._launch_pending_program.assert_not_called()
        previous.terminate.assert_not_called()

    def test_close_error_is_reported_without_opening_another(self):
        self.app.active_process = Mock(pid=123)
        self.app.active_process.poll.return_value = None
        self.app.close_requested = False
        with (
            patch.object(launcher, "request_program_close", side_effect=OSError("test")),
            patch.object(launcher.messagebox, "showerror") as error,
        ):
            launcher.Launcher._wait_for_program_close(self.app)
        error.assert_called_once()
        self.assertIsNone(self.app.pending_program)
        self.app._launch_pending_program.assert_not_called()

    def test_launched_process_is_tracked_and_geometry_is_preserved(self):
        self.target.name = "folha_pagamento.py"
        self.app.pending_program = self.program
        canvas = self.app.home_canvas
        canvas.winfo_rootx.return_value = 10
        canvas.winfo_rooty.return_value = 80
        canvas.winfo_width.return_value = 1200
        canvas.winfo_height.return_value = 620
        with patch.object(launcher.subprocess, "Popen") as start:
            launcher.Launcher._launch_pending_program(self.app)
        self.assertIs(self.app.active_process, start.return_value)
        self.assertIsNone(self.app.pending_program)
        self.assertEqual(
            start.call_args.args[0],
            ["python", "program.py", "--central-geometry=1184x580+18+88"],
        )
        self.app._highlight_program.assert_called_with("payroll")

    def test_buttons_highlight_only_the_open_program(self):
        self.app.toolbar_buttons = {name: Mock() for name in ("payroll", "energy", "exit")}
        for selected in ("payroll", "energy", None):
            launcher.Launcher._highlight_program(self.app, selected)
            for name, button in self.app.toolbar_buttons.items():
                options = button.configure.call_args.kwargs
                self.assertEqual(
                    options["bg"], launcher.ORANGE if name == selected else launcher.TOOLBAR
                )

    def test_manual_close_clears_highlight(self):
        self.app.active_process = Mock()
        self.app.active_process.poll.return_value = 0
        launcher.Launcher._check_active_program(self.app)
        self.assertIsNone(self.app.active_process)
        self.app._highlight_program.assert_called_once_with(None)
        self.app.after.assert_called_once_with(300, self.app._check_active_program)

    def test_running_program_keeps_highlight(self):
        self.app.active_process = Mock()
        self.app.active_process.poll.return_value = None
        launcher.Launcher._check_active_program(self.app)
        self.app._highlight_program.assert_not_called()
        self.app._fit_active_program.assert_called_once_with()

    def test_fit_uses_full_window_bounds_inside_central(self):
        self.app.state.return_value = "normal"
        self.app.window_fit_failed = False
        self.app.active_process = Mock(pid=123)
        self.app.winfo_id.return_value = 456
        canvas = self.app.home_canvas
        canvas.winfo_width.return_value = 1200
        canvas.winfo_height.return_value = 620
        canvas.winfo_rootx.return_value = 10
        canvas.winfo_rooty.return_value = 80
        with (
            patch.object(sys, "platform", "win32"),
            patch.object(launcher, "fit_program_window") as fit,
        ):
            launcher.Launcher._fit_active_program(self.app)
        fit.assert_called_once_with(123, 456, (18, 88, 1184, 604))

    def test_fit_skips_minimized_central(self):
        self.app.state.return_value = "iconic"
        with patch.object(launcher, "fit_program_window") as fit:
            launcher.Launcher._fit_active_program(self.app)
        fit.assert_not_called()

    def test_fit_error_is_reported_once(self):
        self.app.state.return_value = "normal"
        self.app.window_fit_failed = False
        self.app.active_process = Mock(pid=123)
        self.app.home_canvas.winfo_width.return_value = 1200
        self.app.home_canvas.winfo_height.return_value = 620
        self.app.home_canvas.winfo_rootx.return_value = 10
        self.app.home_canvas.winfo_rooty.return_value = 80
        with (
            patch.object(sys, "platform", "win32"),
            patch.object(launcher, "fit_program_window", side_effect=OSError("test")),
            patch.object(launcher.messagebox, "showerror") as error,
        ):
            launcher.Launcher._fit_active_program(self.app)
            launcher.Launcher._fit_active_program(self.app)
        error.assert_called_once()

    @unittest.skipUnless(sys.platform == "win32", "Windows window positioning")
    def test_native_window_fits_and_resizes_for_descendant_process(self):
        import ctypes
        from ctypes import wintypes
        import tkinter as tk

        owner = tk.Tk()
        owner.withdraw()
        owner.update_idletasks()
        child_code = (
            "import tkinter as tk; "
            "root=tk.Tk(); root.geometry('800x600'); "
            "root.title('Central fit test'); "
            "root.after(20000, root.destroy); root.mainloop()"
        )
        parent_code = (
            "import subprocess,sys; "
            "sys.exit(subprocess.call([sys.executable,'-c',sys.argv[1]]))"
        )
        process = subprocess.Popen([sys.executable, "-c", parent_code, child_code])
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
        user32.FindWindowW.restype = wintypes.HWND
        user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
        user32.GetWindowRect.restype = wintypes.BOOL
        try:
            deadline = time.monotonic() + 10
            fitted = False
            while time.monotonic() < deadline:
                owner.update()
                fitted = launcher.fit_program_window(
                    process.pid, owner.winfo_id(), (40, 100, 500, 320)
                )
                if fitted:
                    break
                time.sleep(0.1)
            self.assertTrue(fitted)
            handle = user32.FindWindowW("TkTopLevel", "Central fit test")
            self.assertTrue(handle)
            for bounds in ((40, 100, 500, 320), (80, 120, 360, 260)):
                self.assertTrue(launcher.fit_program_window(
                    process.pid, owner.winfo_id(), bounds
                ))
                rect = wintypes.RECT()
                self.assertTrue(user32.GetWindowRect(handle, ctypes.byref(rect)))
                self.assertEqual(
                    (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top),
                    bounds,
                )
            self.assertTrue(launcher.request_program_close(process.pid))
            self.assertEqual(process.wait(timeout=10), 0)
        finally:
            if process.poll() is None:
                launcher.request_program_close(process.pid)
                process.wait(timeout=25)
            owner.destroy()

    def test_launch_failure_clears_highlight(self):
        self.app.pending_program = self.program
        canvas = self.app.home_canvas
        canvas.winfo_rootx.return_value = 0
        canvas.winfo_rooty.return_value = 80
        canvas.winfo_width.return_value = 1200
        canvas.winfo_height.return_value = 620
        with (
            patch.object(launcher.subprocess, "Popen", side_effect=OSError("test")),
            patch.object(launcher.messagebox, "showerror") as error,
        ):
            launcher.Launcher._launch_pending_program(self.app)
        error.assert_called_once()
        self.app._highlight_program.assert_called_once_with(None)

    def test_frozen_programs_use_the_executable(self):
        executable = str(Path.cwd() / "GerenciadorAdministrativoRevisa.exe")
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", executable),
        ):
            for name, method in (
                ("payroll", launcher.Launcher.open_payroll),
                ("energy", launcher.Launcher.open_energy),
            ):
                method(self.app)
                target, args, folder, label = self.app._start.call_args.args
                self.assertEqual(target, Path(executable))
                self.assertEqual(folder, Path(executable).parent)
                self.assertEqual(
                    args,
                    [executable, f"--revisa-program={name}", "--central-authenticated"],
                )

    def test_executable_dispatch_preserves_other_arguments(self):
        for program, module in (
            ("payroll", "folha_pagamento"),
            ("energy", "controle_energia_agua"),
        ):
            with (
                patch.object(sys, "argv", [
                    "GerenciadorAdministrativoRevisa.exe",
                    f"--revisa-program={program}",
                    "--central-authenticated",
                    "--central-geometry=1200x580+10+80",
                ]),
                patch("runpy.run_module") as run,
            ):
                launcher.main()
                run.assert_called_once_with(module, run_name="__main__")
                self.assertNotIn(f"--revisa-program={program}", sys.argv)
                self.assertIn("--central-geometry=1200x580+10+80", sys.argv)

    @unittest.skipUnless(sys.platform == "win32", "Windows window messaging")
    def test_windows_close_runs_tk_close_handler(self):
        code = (
            "import tkinter as tk, sys; "
            "root=tk.Tk(); root.withdraw(); "
            "window=tk.Toplevel(root); window.geometry('180x80'); "
            "window.title('Central close test'); "
            "window.protocol('WM_DELETE_WINDOW', lambda: sys.exit(23)); "
            "root.after(10000, lambda: sys.exit(24)); "
            "root.mainloop()"
        )
        process = subprocess.Popen([sys.executable, "-c", code])
        try:
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                if launcher.request_program_close(process.pid):
                    break
                time.sleep(0.1)
            self.assertEqual(process.wait(timeout=12), 23)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
