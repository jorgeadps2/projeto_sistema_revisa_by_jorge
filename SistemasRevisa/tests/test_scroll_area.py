import sys
import tkinter as tk
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from revisa_integrado.ui.scroll import ScrollArea, scrollbars_needed


class ScrollbarRuleTests(unittest.TestCase):
    def test_no_bars_when_content_fits(self):
        self.assertEqual(scrollbars_needed(800, 600, 700, 500, 17, 17), (False, False))

    def test_vertical_bar_when_content_is_taller(self):
        self.assertEqual(scrollbars_needed(800, 600, 700, 900, 17, 17), (True, False))

    def test_horizontal_bar_when_content_is_wider(self):
        self.assertEqual(scrollbars_needed(800, 600, 1000, 500, 17, 17), (False, True))

    def test_vertical_bar_caused_by_horizontal_bar(self):
        self.assertEqual(scrollbars_needed(800, 600, 1000, 590, 17, 17), (True, True))


class ScrollAreaWidgetTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk indisponível: {error}")
        self.root.geometry("300x200")

    def tearDown(self):
        self.root.destroy()

    def _area_with_content(self, width, height):
        area = ScrollArea(self.root, bg="white")
        area.pack(fill="both", expand=True)
        tk.Frame(area.inner, width=width, height=height).pack(fill="both", expand=True)
        for _ in range(3):
            self.root.update()
        return area

    def test_shows_both_bars_on_small_window(self):
        area = self._area_with_content(900, 700)
        self.assertTrue(area.vbar.winfo_manager())
        self.assertTrue(area.hbar.winfo_manager())

    def test_hides_bars_and_fills_space_when_content_fits(self):
        area = self._area_with_content(50, 50)
        self.assertFalse(area.vbar.winfo_manager())
        self.assertFalse(area.hbar.winfo_manager())
        self.assertGreaterEqual(area.inner.winfo_width(), 290)
        self.assertGreaterEqual(area.inner.winfo_height(), 190)


if __name__ == "__main__":
    unittest.main()
