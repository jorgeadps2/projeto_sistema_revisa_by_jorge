import sys
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from revisa_integrado.ui import pages


class AboutLayoutTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk indisponível: {error}")
        self.addCleanup(self.root.destroy)
        self.root.geometry("650x650")
        frame = tk.Frame(self.root)
        frame.pack(fill="both", expand=True)
        module = SimpleNamespace(APP_VERSION="1.0", AUTO_BACKUP_DIR="C:\\Backup")
        app = SimpleNamespace(_icon=lambda *args: None)
        with patch.object(pages.folha, "module", return_value=module), \
                patch.object(pages.energia, "module", return_value=module), \
                patch.object(pages.energia, "exit_backup_path", return_value=Path("C:\\Backup\\energia.db")):
            pages.build_about(app, frame)
        canvas = next(child for child in frame.winfo_children() if isinstance(child, tk.Canvas))
        inner = canvas.winfo_children()[0]
        self.cards = inner.winfo_children()[1]
        self.info, self.technical = self.cards.winfo_children()
        self.resize(650)

    def resize(self, width):
        self.root.geometry(f"{width}x650")
        for _ in range(3):
            self.root.update()

    def test_cards_do_not_overlap_after_growing_window(self):
        self.resize(1365)
        self.assertEqual(int(self.info.grid_info()["columnspan"]), 1)
        self.assertEqual(int(self.technical.grid_info()["columnspan"]), 1)
        self.assertLessEqual(
            self.info.winfo_x() + self.info.winfo_width(),
            self.technical.winfo_x(),
        )

    def test_cards_stack_and_separate_after_repeated_resizing(self):
        for width in (1365, 650, 980, 1365):
            with self.subTest(width=width):
                self.resize(width)
                if width < 800:
                    self.assertLessEqual(
                        self.info.winfo_y() + self.info.winfo_height(),
                        self.technical.winfo_y(),
                    )
                else:
                    self.assertLessEqual(
                        self.info.winfo_x() + self.info.winfo_width(),
                        self.technical.winfo_x(),
                    )

    def test_text_fits_inside_cards(self):
        def check_children(parent):
            for child in parent.winfo_children():
                if isinstance(child, tk.Label) and child.cget("text"):
                    self.assertLessEqual(child.winfo_reqwidth(), child.winfo_width() + 2,
                                         child.cget("text"))
                self.assertLessEqual(child.winfo_x() + child.winfo_width(),
                                     parent.winfo_width(), str(child))
                check_children(child)

        for width in (650, 980, 1365):
            with self.subTest(width=width):
                self.resize(width)
                check_children(self.info)
                check_children(self.technical)


if __name__ == "__main__":
    unittest.main()
