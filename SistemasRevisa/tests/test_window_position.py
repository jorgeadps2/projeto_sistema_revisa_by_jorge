import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from revisa_integrado.ui.main_window import MainWindow


class WindowPositionTests(unittest.TestCase):
    def test_centers_splash_and_login_on_selected_monitor(self):
        for width, height in ((400, 80), (520, 250)):
            for left, top in ((1920, 0), (-1920, 0), (0, -1080)):
                with self.subTest(size=(width, height), origin=(left, top)):
                    window = Mock()
                    window._monitor_work_area.return_value = (
                        left, top, left + 1920, top + 1040)
                    MainWindow._center_window(window, width, height)
                    x = left + (1920 - width) // 2
                    y = top + (1040 - height) // 2
                    window.geometry.assert_called_once_with(
                        f"{width}x{height}+{x}+{y}")

    def test_uses_pointer_monitor_before_window_is_visible(self):
        window = Mock()
        window.winfo_ismapped.return_value = False
        window.winfo_pointerxy.return_value = (-500, 300)
        with patch("revisa_integrado.ui.main_window.sys.platform", "win32"), \
                patch("revisa_integrado.ui.main_window.monitor_work_area",
                      return_value=(-1920, 0, 0, 1040)) as monitor:
            self.assertEqual(
                MainWindow._monitor_work_area(window), (-1920, 0, 0, 1040))
        monitor.assert_called_once_with(-500, 300)

    def test_keeps_window_monitor_when_pointer_moves(self):
        window = Mock()
        window.winfo_ismapped.return_value = True
        window.winfo_rootx.return_value = 2000
        window.winfo_rooty.return_value = 200
        window.winfo_width.return_value = 400
        window.winfo_height.return_value = 80
        with patch("revisa_integrado.ui.main_window.sys.platform", "win32"), \
                patch("revisa_integrado.ui.main_window.monitor_work_area",
                      return_value=(1920, 0, 3840, 1040)) as monitor:
            MainWindow._monitor_work_area(window)
        monitor.assert_called_once_with(2200, 240)
        window.winfo_pointerxy.assert_not_called()

    def test_positions_main_window_before_maximizing_it(self):
        window = Mock()
        window._monitor_work_area.return_value = (0, 0, 1920, 1040)

        MainWindow._resize_shell_window(window)

        window.minsize.assert_called_once_with(980, 600)
        window._center_window.assert_called_once_with(1320, 820)
        window.state.assert_called_once_with("zoomed")
        self.assertEqual(
            [call[0] for call in window.mock_calls],
            ["_monitor_work_area", "minsize", "_center_window",
             "update_idletasks", "state"])

    def test_resizes_login_to_centered_window(self):
        window = Mock()

        MainWindow._resize_login_window(window, 520, 250)

        window.state.assert_called_once_with("normal")
        window.minsize.assert_called_once_with(480, 230)
        window._center_window.assert_called_once_with(520, 250)

    def test_centers_open_dialog_on_main_window_monitor(self):
        main_window = Mock()
        main_window._monitor_work_area.return_value = (-1920, 0, 0, 1040)
        dialog = Mock()
        dialog.winfo_width.return_value = 520
        dialog.winfo_height.return_value = 300

        MainWindow._center_open_toplevel(
            main_window, Mock(widget=dialog))

        dialog.geometry.assert_called_once_with("520x300+-1220+370")

    def test_login_footer_shows_developer_robot_without_overflow(self):
        window = MainWindow.__new__(MainWindow)
        tk.Tk.__init__(window)
        try:
            window.images = {}
            window._login_sync_status = Mock(return_value=("Sincronização desativada", "#667085"))
            window._login_signing_status = Mock(return_value=("Validade indisponível", "#667085"))
            footer = window._build_login_footer(window)
            footer.pack(fill="x")
            window.geometry("520x250")
            window.update()
            self.assertIn("developer_robot", window.images)
            self.assertEqual(window.images["developer_robot"].width(), 36)
            self.assertLessEqual(footer.winfo_reqwidth(), 520)
            for column in (0, 2, 4):
                cell = footer.grid_slaves(row=0, column=column)[0]
                content = cell.winfo_children()[0]
                self.assertLessEqual(content.winfo_reqwidth(), cell.winfo_width() - 14)
                self.assertLessEqual(content.winfo_reqheight(), cell.winfo_height() - 10)
                self.assertAlmostEqual(
                    content.winfo_x() + content.winfo_width() / 2,
                    cell.winfo_width() / 2, delta=1)
                self.assertAlmostEqual(
                    content.winfo_y() + content.winfo_height() / 2,
                    cell.winfo_height() / 2, delta=1)
        finally:
            window.destroy()

    def test_toolbar_buttons_use_width_of_widest_item(self):
        window = MainWindow.__new__(MainWindow)
        tk.Tk.__init__(window)
        try:
            window.icon_images = {}
            window.navigate = Mock()
            window.on_close = Mock()
            window._build_toolbar()
            window.geometry("900x300")
            window.update()

            toolbar = window.winfo_children()[0]
            scaling = float(window.tk.call("tk", "scaling"))
            expected_height = round(78 / scaling)
            self.assertEqual(toolbar.winfo_height(), expected_height)
            buttons = [child for child in toolbar.winfo_children()
                       if isinstance(child, tk.Button)]
            self.assertEqual(len(buttons), 7)
            self.assertEqual(len({button.winfo_height() for button in buttons}), 1)
            self.assertGreater(buttons[0].winfo_height(), round(58 / scaling))
            self.assertEqual(window.icon_images[("painel", 28, 0)].width(), 28)
            widths = {button.winfo_width() for button in buttons}
            self.assertEqual(len(widths), 1)
            widest_button = max(buttons, key=lambda button: button.winfo_reqwidth())
            self.assertEqual(
                widest_button.winfo_width(),
                max(button.winfo_reqwidth() for button in buttons),
            )
        finally:
            window.destroy()

    def test_real_shell_opens_maximized_and_modules_preserve_it(self):
        window = MainWindow.__new__(MainWindow)
        tk.Tk.__init__(window)
        try:
            window.withdraw()
            window.overrideredirect(True)
            window.geometry("400x80+400+300")
            window.deiconify()
            window.update()
            window.overrideredirect(False)
            window._resize_login_window()
            window.update()
            window.session = Mock()
            window._clear = Mock()
            window.apply_shell_style = Mock()
            window._build_toolbar = Mock()
            window._build_status_bar = Mock()
            window.update_header = Mock()
            window._prompt_meter_readings = Mock()

            def build_menu():
                menu = tk.Menu(window)
                menu.add_command(label="Arquivo")
                window.configure(menu=menu)

            window._build_menu = build_menu
            window.navigate = Mock()
            window.show_shell()
            window.update()
            self.assertEqual(window.state(), "zoomed")
            maximized_geometry = window.geometry()
            window.pages = {}
            window.modules = {}
            for key in ("folha", "energia"):
                frame = tk.Frame(window.content, width=1800, height=1000)
                window.modules[key] = {"container": frame}
                window._show_frame(key, frame, key)
                window.update()
                self.assertEqual(window.state(), "zoomed")
                self.assertEqual(window.geometry(), maximized_geometry)
            window.state("normal")
            window.update()

            def assert_centered():
                left, top, right, bottom = window._monitor_work_area()
                self.assertAlmostEqual(
                    window.winfo_x() + window.winfo_width() / 2,
                    (left + right) / 2, delta=2)
                self.assertAlmostEqual(
                    window.winfo_y() + window.winfo_height() / 2,
                    (top + bottom) / 2, delta=2)

            assert_centered()
            window.pages = {}
            window.modules = {}
            for key in ("folha", "energia"):
                frame = tk.Frame(window.content, width=1800, height=1000)
                window.modules[key] = {"container": frame}
                window.geometry("+0+0")
                window.update()
                window._show_frame(key, frame, key)
                window.update()
                assert_centered()
        finally:
            window.destroy()


if __name__ == "__main__":
    unittest.main()
