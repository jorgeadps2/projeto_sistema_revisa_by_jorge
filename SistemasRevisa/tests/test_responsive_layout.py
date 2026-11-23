import gc
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from revisa_integrado.core import paths
from revisa_integrado.ui.main_window import MainWindow


class ResponsiveLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.window = MainWindow.__new__(MainWindow)
        tk.Tk.__init__(self.window)
        self.window.maxsize(3000, 2000)
        self.window.tk.call("tk", "scaling", 96 / 72)
        self.window.icon_images = {}
        self.window.images = {}
        self.window.modules = {}
        self.window.current = None
        self.window.log = Mock()
        self.errors = []
        self.window.report_callback_exception = lambda *error: self.errors.append(error)
        self.addCleanup(gc.collect)
        self.addCleanup(self.window.destroy)
        self.window.geometry("1366x680")
        self.window._build_toolbar()
        self.window.update()

    def test_sidebar_actions_fit_across_resolutions_and_dpi(self):
        for width, height, dpi in (
                (980, 600, 144), (1024, 680, 96), (1024, 680, 144), (1366, 680, 120),
                (1366, 680, 144), (1366, 720, 144), (1920, 1000, 96)):
            with self.subTest(width=width, height=height, dpi=dpi):
                self.window.shell_toolbar.destroy()
                self.window.tk.call("tk", "scaling", dpi / 72)
                self.window.geometry(f"{width}x{height}")
                self.window._build_toolbar()
                self.window.update()
                toolbar = self.window.shell_toolbar
                buttons = list(self.window.sidebar_buttons.values())
                self.assertEqual(len(buttons), 7)
                self.assertEqual(len({button.winfo_width() for button in buttons}), 1)
                self.assertTrue(all(button.winfo_viewable() for button in buttons))
                self.assertTrue(all(button.cget("compound") == "left" for button in buttons))
                self.assertGreaterEqual(buttons[0].winfo_width(), 210)
                self.assertGreaterEqual(buttons[0].winfo_height(), 40 if height >= 800 else 32)
                minimum_gap = 2 if height < 520 * dpi / 96 else 6
                self.assertGreaterEqual(buttons[1].winfo_y() - buttons[0].winfo_y()
                                        - buttons[0].winfo_height(), minimum_gap)
                for button in buttons:
                    self.assertLessEqual(button.winfo_reqwidth(), button.winfo_width())
                    self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                                         toolbar.winfo_rooty() + toolbar.winfo_height())

    def test_resizing_payroll_restores_large_layout_and_preserves_page_and_form(self):
        paths.ensure_module_paths()
        import folha_pagamento as payroll

        with patch.object(payroll, "DB_PATH", str(Path(self.temp.name) / "folha.db")):
            payroll.init_db()
            payroll.use_light_theme()
            app = payroll.FolhaPanel(
                self.window, centralized_actions=True,
                signing_status_callback=lambda: ("Teste", "ok", "09/01/2027"))
            app.pack(fill="both", expand=True)
            self.window.modules["folha"] = {"instance": app}
            self.window.current = "folha"
            self.window._update_responsive_layout()
            self.window.update()
            compact_top = app.scroll_host.winfo_rooty()
            compact_content = app.scroll_host.winfo_height()
            self.assertTrue(app.compact_layout)
            self.assertLessEqual(app.navigation_toolbar.winfo_height(), 38)
            self.assertEqual(ttk.Style(app).lookup("Treeview", "rowheight"), 24)
            for button in app.navigation_buttons.values():
                self.assertTrue(button.winfo_viewable())
            notice = app.signing_expiry_label
            self.assertLessEqual(notice.winfo_x() + notice.winfo_width(), app.winfo_width())
            self.window.geometry("1920x1000")
            self.window.update()
            self.assertFalse(app.compact_layout)
            self.assertTrue(self.window.sidebar_buttons["folha"].winfo_viewable())
            self.assertEqual(ttk.Style(app).lookup("Treeview", "rowheight"), 30)
            self.assertGreaterEqual(app.scroll_host.winfo_rooty() - compact_top, 40)
            self.assertGreaterEqual(
                app.scroll_host.winfo_height() - compact_content, 200)
            app.navigate("employees")
            app.add_employee_dialog()
            self.window.update()
            form = app.inline_forms.stack[-1][1]
            entry = next(child for child in self.descendants(form)
                         if isinstance(child, ttk.Entry))
            entry.insert(0, "Unsaved employee")
            self.window.geometry("1024x680")
            self.window.update()
            self.assertTrue(app.compact_layout)
            self.assertEqual(app.current_section, "employees")
            self.assertEqual(entry.get(), "Unsaved employee")
            app.inline_forms.close_all()
            app.navigate("dashboard")
            self.window.update()
            app.reapply_style()
            self.assertEqual(ttk.Style(app).lookup("Treeview", "rowheight"), 24)
            self.assertEqual(self.errors, [])
            app.destroy()

    def test_dashboard_shows_summary_and_resources_without_duplicate_controls(self):
        frame = tk.Frame(self.window)
        frame.pack(fill="both", expand=True)
        self.window.build_dashboard(frame)
        self.window.update()
        widgets = list(self.descendants(frame))
        self.assertFalse(any(isinstance(widget, (tk.Entry, tk.Menubutton)) for widget in widgets))
        labels = {widget.cget("text") for widget in widgets
                  if isinstance(widget, tk.Label) and widget.winfo_viewable()}
        self.assertTrue({"Resumo do sistema", "Backups verificáveis", "Geração em PDF"} <= labels)
        frame.destroy()
        self.assertEqual(self.errors, [])

    @staticmethod
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from ResponsiveLayoutTests.descendants(child)


if __name__ == "__main__":
    unittest.main()
