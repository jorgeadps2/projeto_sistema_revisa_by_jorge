import sys
import ctypes
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from revisa_integrado.ui.main_window import (
    MainWindow,
    STARTUP_SPLASH_HEIGHT,
    STARTUP_SPLASH_WIDTH,
    STARTUP_SPLASH_WINDOW_HEIGHT,
)
from revisa_integrado.ui import theme as t


class WindowPositionTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Barra de tarefas do Windows")
    def test_borderless_login_is_a_visible_taskbar_app_window(self):
        from ctypes import wintypes

        window = MainWindow.__new__(MainWindow)
        tk.Tk.__init__(window)
        try:
            window.log = Mock()
            for start_visible in (False, True):
                with self.subTest(start_visible=start_visible):
                    if start_visible:
                        window.deiconify()
                    else:
                        window.withdraw()
                    window.update()
                    window._resize_login_window()
                    window.deiconify()
                    window.update()
                    user32 = ctypes.WinDLL("user32", use_last_error=True)
                    user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
                    user32.GetAncestor.restype = wintypes.HWND
                    user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
                    user32.GetWindowLongW.restype = wintypes.LONG
                    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
                    user32.IsWindowVisible.restype = wintypes.BOOL
                    user32.GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)
                    user32.GetWindow.restype = wintypes.HWND
                    handle = user32.GetAncestor(window.winfo_id(), 2)
                    style = user32.GetWindowLongW(handle, -20)
                    self.assertTrue(style & 0x00040000, "WS_EX_APPWINDOW ausente")
                    self.assertFalse(style & 0x00000080, "WS_EX_TOOLWINDOW presente")
                    self.assertTrue(user32.IsWindowVisible(handle))
                    self.assertFalse(user32.GetWindow(handle, 4), "Janela tem proprietário")
                    self.assertTrue(window.overrideredirect())
        finally:
            window.destroy()

    def test_centers_splash_and_login_on_selected_monitor(self):
        for width, height in (
                (STARTUP_SPLASH_WIDTH, STARTUP_SPLASH_WINDOW_HEIGHT),
                (520, 250)):
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

    def test_startup_splash_uses_native_app_style_and_progress_content(self):
        window = MainWindow.__new__(MainWindow)
        tk.Tk.__init__(window)
        try:
            window.startup_splash_label = tk.Canvas(
                window, width=STARTUP_SPLASH_WIDTH, height=STARTUP_SPLASH_HEIGHT,
                bg=t.SURFACE, highlightthickness=0)
            window.startup_splash_image = tk.PhotoImage(width=40, height=40)
            window.startup_splash_label.pack()
            window._update_startup_splash(72)
            window.update_idletasks()

            canvas = window.startup_splash_label
            self.assertEqual(canvas.winfo_reqwidth(), STARTUP_SPLASH_WIDTH)
            self.assertEqual(canvas.winfo_reqheight(), STARTUP_SPLASH_HEIGHT)
            texts = [
                canvas.itemcget(item, "text")
                for item in canvas.find_all()
                if canvas.type(item) == "text"
            ]
            self.assertNotIn("Sistema Interno está iniciando", texts)
            self.assertNotIn("Sistema Interno", texts)
            self.assertNotIn("R", texts)
            self.assertIn(
                "Preparando os módulos e verificando os arquivos.", texts)
            self.assertIn("Carregando recursos", texts)
            self.assertIn("72%", texts)
            self.assertIn("Verificando arquivos", texts)
            self.assertIn("Preparando módulos", texts)
            self.assertIn("Finalizando abertura", texts)
            self.assertIn("REVISA", texts)
            for item in canvas.find_all():
                if canvas.type(item) != "text":
                    continue
                bounds = canvas.bbox(item)
                if bounds:
                    self.assertGreaterEqual(bounds[0], 0)
                    self.assertLessEqual(bounds[2], STARTUP_SPLASH_WIDTH)
                    self.assertGreaterEqual(bounds[1], 0)
                    self.assertLessEqual(bounds[3], STARTUP_SPLASH_HEIGHT)
            self.assertEqual(canvas.cget("bg"), t.SURFACE)
            self.assertIn(
                t.PRIMARY_DARK,
                [
                    canvas.itemcget(item, "fill")
                    for item in canvas.find_all()
                    if canvas.type(item) != "image"
                ],
            )
            image_items = [
                item for item in canvas.find_all()
                if canvas.type(item) == "image"
            ]
            self.assertEqual(len(image_items), 1)
            top_accent_items = [
                item for item in canvas.find_all()
                if canvas.type(item) == "rectangle"
                and canvas.bbox(item)[1] == 0
                and canvas.bbox(item)[3] <= 4
            ]
            self.assertEqual(top_accent_items, [])
            progress_marker_items = [
                item for item in canvas.find_all()
                if canvas.type(item) == "oval"
                and canvas.bbox(item)[1] < 110
            ]
            self.assertEqual(progress_marker_items, [])
        finally:
            window.destroy()

    def test_startup_splash_uses_native_window_titlebar(self):
        window = MainWindow.__new__(MainWindow)
        tk.Tk.__init__(window)
        try:
            window.startup_splash_started = 0
            window._center_window = Mock()
            window._show_startup_splash()

            self.assertTrue(window.overrideredirect())
            self.assertEqual(window.title(), "")
            self.assertEqual(window.startup_splash_image.width(), 40)
            window._center_window.assert_called_once_with(
                STARTUP_SPLASH_WIDTH, STARTUP_SPLASH_WINDOW_HEIGHT)
            window._close_startup_splash()
            self.assertEqual(window.title(), "Sistema Interno")
        finally:
            window.destroy()

    def test_startup_splash_marks_all_stages_complete_at_100_percent(self):
        window = MainWindow.__new__(MainWindow)
        tk.Tk.__init__(window)
        try:
            window.startup_splash_label = tk.Canvas(
                window, width=STARTUP_SPLASH_WIDTH, height=STARTUP_SPLASH_HEIGHT,
                bg=t.SURFACE, highlightthickness=0)
            window.startup_splash_image = tk.PhotoImage(width=40, height=40)
            window.startup_splash_label.pack()
            window._update_startup_splash(100)
            texts = [
                window.startup_splash_label.itemcget(item, "text")
                for item in window.startup_splash_label.find_all()
                if window.startup_splash_label.type(item) == "text"
            ]
            self.assertIn("100%", texts)
            self.assertEqual(texts.count("✓"), 3)
            self.assertIn("Verificando arquivos", texts)
            self.assertIn("Preparando módulos", texts)
            self.assertIn("Finalizando abertura", texts)
        finally:
            window.destroy()

    def test_startup_splash_reaches_100_before_finishing(self):
        window = Mock()

        MainWindow._complete_startup_splash(window)

        self.assertEqual(
            [call[0] for call in window.mock_calls],
            ["_update_startup_splash", "update", "after"],
        )
        window._update_startup_splash.assert_called_once_with(100)
        window.after.assert_called_once_with(500)

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
        window.minsize.assert_called_once_with(560, 310)
        window._center_window.assert_called_once_with(520, 250)
        window.overrideredirect.assert_called_once_with(True)
        window._enable_login_taskbar.assert_called_once()

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
            window.geometry("560x310")
            window.update()
            self.assertIn("developer_robot", window.images)
            self.assertEqual(window.images["developer_robot"].width(), 36)
            self.assertLessEqual(footer.winfo_reqwidth(), 560)
            for column in (0, 2):
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

    def test_login_certificate_preserves_expiration_and_status(self):
        for status, when, color in (
                ("ok", "09/01/2027", t.SUCCESS),
                ("warning", "15/11/2026", t.WARNING),
                ("expired", "01/11/2026", t.DANGER),
                ("unavailable", "", t.MUTED)):
            with self.subTest(status=status), patch(
                    "revisa_integrado.ui.main_window.folha.signing_status",
                    return_value=("Detalhes", status, when)):
                text, actual_color = MainWindow._login_signing_status()
                self.assertEqual(actual_color, color)
                self.assertEqual(text, f"Certificado · Vcto: {when}" if when
                                 else "Certificado · validade indisponível")
                self.assertNotIn("OK", text)

    def test_approved_login_layout_and_password_controls(self):
        window = MainWindow.__new__(MainWindow)
        tk.Tk.__init__(window)
        try:
            window.clock_job = None
            window.images = {}
            window.modules = {}
            window.pages = {}
            window.log = Mock()
            window._login_sync_status = Mock(return_value=("Sincronização: OK", t.SUCCESS))
            window._login_signing_status = Mock(
                return_value=("Certificado · Vcto: 09/01/2027", t.SUCCESS))
            window.limiter = Mock()
            window.limiter.remaining_lock.return_value = 0
            window.session = Mock()
            window.show_shell = Mock()
            window.on_close = Mock()

            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)

            with patch("revisa_integrado.ui.main_window.folha.status", return_value="ok"), \
                    patch("revisa_integrado.ui.main_window.folha.prepare_existing_database"):
                window.show_login()
            window.update()
            self.assertEqual(window.login_size, (560, 310))
            self.assertEqual((window.winfo_width(), window.winfo_height()), (560, 310))
            self.assertTrue(window.overrideredirect())
            window.login_close_button.invoke()
            window.on_close.assert_called_once()
            window._start_login_drag(Mock(x_root=window.winfo_x() + 15,
                                          y_root=window.winfo_y() + 10))
            window._drag_login(Mock(x_root=415, y_root=310))
            window.update()
            self.assertEqual((window.winfo_x(), window.winfo_y()), (400, 300))
            texts = [child.cget("text") for child in descendants(window)
                     if isinstance(child, tk.Label)]
            self.assertIn("Empresa", texts)
            self.assertIn("Usuário", texts)
            self.assertNotIn("SISTEMAS REVISA", texts)
            self.assertFalse(any("Versão" in text for text in texts))
            for widget in descendants(window):
                if isinstance(widget, (tk.Label, tk.Entry, tk.Button)):
                    self.assertLessEqual(widget.winfo_reqwidth(), widget.winfo_width() + 2,
                                         str(widget))
                    self.assertLessEqual(widget.winfo_reqheight(), widget.winfo_height() + 2,
                                         str(widget))
                    self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(),
                                         window.winfo_rootx() + window.winfo_width())
                    self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(),
                                         window.winfo_rooty() + window.winfo_height())
            field = window.login_fields[0]
            self.assertEqual(field.winfo_height(), window.login_button.winfo_height())
            self.assertEqual(field.winfo_rooty(), window.login_button.winfo_rooty())
            self.assertLessEqual(field.winfo_width(), 200)
            user = field.master.grid_slaves(row=1, column=0)[0]
            self.assertGreater(field.winfo_width(), user.winfo_width())
            self.assertEqual(
                window.login_button.winfo_rootx() + window.login_button.winfo_width(),
                field.master.winfo_rootx() + field.master.winfo_width())
            self.assertEqual(window.login_show_button.winfo_rootx(), field.winfo_rootx())
            self.assertLessEqual(window.login_button.winfo_width(), 100)
            self.assertLess(window.login_button.winfo_width(),
                            field.master.winfo_width() // 2)
            self.assertGreaterEqual(window.login_button.winfo_rootx(),
                                    field.winfo_rootx() + field.winfo_width() + 6)
            field.insert(0, "senha-de-teste")
            window.login_show_button.invoke()
            self.assertEqual(field.cget("show"), "")
            window.login_show_button.invoke()
            self.assertEqual(field.cget("show"), "•")
            with patch("revisa_integrado.ui.main_window.folha.verify_password", return_value=False):
                window.login_button.invoke()
            self.assertEqual(window.login_message.cget("text"), "Senha incorreta.")
            self.assertEqual(field.get(), "")
            window.show_shell.assert_not_called()
            window.update()
            self.assertGreaterEqual(window.login_message.winfo_height(),
                                    window.login_message.winfo_reqheight())
            with patch("revisa_integrado.ui.main_window.folha.verify_password", return_value=True):
                field.insert(0, "senha-de-teste")
                window.login_button.invoke()
            window.session.login.assert_called_once_with("JORGE")
            window.show_shell.assert_called_once()
        finally:
            window.destroy()

    def test_login_setup_and_missing_database_fit_without_creating_data(self):
        for state in ("sem_senha", "ausente", "erro"):
            with self.subTest(state=state):
                window = MainWindow.__new__(MainWindow)
                tk.Tk.__init__(window)
                try:
                    window.clock_job = None
                    window.images = {}
                    window.modules = {}
                    window.pages = {}
                    window.log = Mock()
                    window._login_sync_status = Mock(
                        return_value=("Sincronização: falha", t.DANGER))
                    window._login_signing_status = Mock(
                        return_value=("Certificado · validade indisponível", t.MUTED))
                    with patch("revisa_integrado.ui.main_window.folha.status",
                               return_value=state), \
                            patch("revisa_integrado.ui.main_window.folha.prepare_existing_database",
                                  side_effect=RuntimeError("Falha de teste") if state == "erro" else None), \
                            patch("revisa_integrado.ui.main_window.folha.min_password_length",
                                  return_value=8), \
                            patch("revisa_integrado.ui.main_window.folha.db_path",
                                  return_value=Path("C:\\Dados\\folha.db")), \
                            patch("revisa_integrado.ui.main_window.folha.create_new_database") as create:
                        window.show_login()
                        window.update()
                        create.assert_not_called()
                    self.assertLessEqual(window.login_body.winfo_reqheight(),
                                         window.login_body.winfo_height())
                    self.assertLessEqual(window.login_body.winfo_reqwidth(),
                                         window.login_body.winfo_width())
                    if state == "sem_senha":
                        self.assertEqual(len(window.login_fields), 2)
                        self.assertEqual(window.login_button.cget("text"), "Salvar senha")
                    elif state == "erro":
                        window.log.exception.assert_called_once()
                finally:
                    window.destroy()

    def test_toolbar_buttons_match_compact_reference_width(self):
        window = MainWindow.__new__(MainWindow)
        tk.Tk.__init__(window)
        try:
            window.icon_images = {}
            window.modules = {}
            window.current = None
            window.navigate = Mock()
            window.on_close = Mock()
            window.maxsize(3000, 2000)
            window.geometry("1320x900")
            window.update()
            window._build_toolbar()
            window.update()

            toolbar = window.winfo_children()[0]
            self.assertEqual(toolbar.winfo_height(), 72)
            buttons = [child for child in toolbar.winfo_children()
                       if isinstance(child, tk.Button)]
            self.assertEqual(len(buttons), 7)
            self.assertEqual(len({button.winfo_width() for button in buttons}), 1)
            admin_button = next(button for button in buttons
                                if button.cget("text") == "Administração")
            self.assertGreaterEqual(buttons[0].winfo_width(),
                                    admin_button.winfo_reqwidth())
            self.assertTrue(all(
                buttons[index + 1].winfo_x()
                - (buttons[index].winfo_x() + buttons[index].winfo_width()) >= 16
                for index in range(len(buttons) - 1)
            ))
            self.assertEqual(buttons[0].cget("compound"), "top")
            self.assertEqual(int(admin_button.cget("wraplength")), 0)
            self.assertEqual(window.icon_images[("painel", 20, 0)].width(), 20)
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
            self.assertFalse(window.overrideredirect())
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
