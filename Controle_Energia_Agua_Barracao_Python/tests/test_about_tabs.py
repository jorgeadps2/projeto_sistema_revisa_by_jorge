import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch


BASE = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def label_texts(widget):
    texts = []
    for child in widget.winfo_children():
        if child.winfo_class() in ("TLabel", "Label"):
            texts.append(str(child.cget("text")))
        texts.extend(label_texts(child))
    return texts


class AboutTabsTests(unittest.TestCase):
    def test_payroll_about_navigation_and_removed_footer(self):
        source = BASE.parent / "FolhaPagamentoRevisa"
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"LOCALAPPDATA": directory}),
            patch.object(sys, "path", [str(source), *sys.path]),
            patch.object(sys, "argv", ["test", "--central-geometry=1000x600+0+0"]),
        ):
            module = load_module("payroll_about_test", source / "folha_pagamento.py")
            original_connect = module.connect
            connections = []

            def connect():
                connection = original_connect()
                connections.append(connection)
                return connection

            module.connect = connect
            module.init_db()
            with patch.object(module.FolhaApp, "load_newer_mega_backup"):
                app = module.FolhaApp()
            try:
                app.withdraw()
                app.navigation_buttons["about"].invoke()
                app.update_idletasks()
                self.assertEqual(app.current_section, "about")
                self.assertEqual(app.current_page, app.about_tab)
                texts = label_texts(app.about_tab)
                self.assertIn(module.APP_NAME, texts)
                self.assertIn(module.APP_VERSION, texts)
                self.assertIn(module.DB_PATH, texts)
                self.assertIn("Jorge Alberto de Paula", texts)
                for child in app.winfo_children():
                    if child.winfo_class() == "TFrame":
                        self.assertNotEqual(child.pack_info().get("side"), "bottom")
                app.navigation_buttons["payroll"].invoke()
                self.assertEqual(app.current_section, "payroll")
            finally:
                app.destroy()
                for connection in connections:
                    connection.close()

    def test_energy_about_navigation_preserves_backup_button(self):
        source = BASE / "Controle_Energia_Agua_Barracao" / "controle_energia_agua.py"
        module = load_module("energy_about_test", source)
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(module, "DB_PATH", Path(directory) / "energy.db"),
            patch.object(sys, "argv", ["test", "--central-geometry=1000x600+0+0"]),
        ):
            root = tk.Tk()
            root.withdraw()
            app = module.App(root)
            try:
                app.botoes_navegacao[3].invoke()
                root.update()
                self.assertEqual(app.nb.select(), str(app.tab_sobre))
                self.assertEqual(app.titulo_pagina.cget("text"), "Sobre")
                texts = label_texts(app.tab_sobre)
                self.assertIn(module.APP_NAME, texts)
                self.assertIn(module.APP_VERSION, texts)
                self.assertIn(str(module.DB_PATH), texts)
                self.assertIn("Jorge Alberto de Paula", texts)
                self.assertEqual(len(app.icones_navegacao), 5)
                self.assertEqual(app.botoes_navegacao[3].cget("style"), "ToolbarSelected.TButton")
                app.botoes_navegacao[0].invoke()
                root.update()
                self.assertEqual(app.nb.select(), str(app.tab_mes))
            finally:
                app.conn.close()
                root.destroy()


if __name__ == "__main__":
    unittest.main()
