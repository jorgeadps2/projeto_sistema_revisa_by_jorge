import importlib.util
import sys
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch


MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))
SPEC = importlib.util.spec_from_file_location(
    "payroll_cell_colors_app", MODULE_DIR / "folha_pagamento.py")
APP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APP)


class PayrollCellColorsTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.root.geometry("1100x180+-2000+-2000")
        self.app = object.__new__(APP.FolhaBase)
        columns = (
            "name", "note_marker", "salary", "pf", "overtime", "vacation",
            "thirteenth", "marmitex", "advances", "pharmacy", "loan",
            "loan_installment", "total")
        tree = ttk.Treeview(self.root, columns=columns, show="headings",
                            style="Payroll.Treeview", height=3)
        ttk.Style(tree).configure("Payroll.Treeview", rowheight=24)
        ttk.Style(tree).map("Payroll.Treeview",
                            background=[("selected", "#cbd5e1")])
        for column in columns:
            tree.heading(column, text=column)
            tree.column(column, width=75, minwidth=26, stretch=False)
        tree.tag_configure("review", background="#fdf6d0")
        tree.tag_configure("closed", background="#e6f6ec")
        tree.tag_configure("note", background="#ffedd5")
        self.values = ("Ana", "\u25cf") + ("100,00",) * 11
        tree.insert("", "end", iid="1", values=self.values, tags=("note",))
        tree.insert("", "end", iid="2",
                    values=("Bruna", "") + self.values[2:], tags=("review",))
        tree.pack(fill="both", expand=True)
        self.app.pay_tree = tree
        self.app.payroll_cell_labels = {}
        self.root.update()

    def refresh(self):
        self.app._refresh_payroll_note_markers()
        self.root.update_idletasks()

    def test_colors_backgrounds_and_selection(self):
        self.refresh()
        labels = self.app.payroll_cell_labels
        for column in ("salary", "pf", "overtime", "vacation", "thirteenth", "total"):
            self.assertEqual(labels["1", column].cget("fg"), "#15803d")
        for column in ("marmitex", "advances", "pharmacy", "loan", "loan_installment"):
            self.assertEqual(labels["1", column].cget("fg"), "#b91c1c")
        self.assertEqual(labels["1", "note_marker"].cget("fg"), "#dc2626")
        self.assertEqual(labels["1", "salary"].cget("bg"), "#ffedd5")
        self.assertEqual(labels["2", "salary"].cget("bg"), "#fdf6d0")
        self.assertNotIn(("1", "name"), labels)
        self.assertNotIn(("2", "note_marker"), labels)
        self.app.pay_tree.item("2", tags=("closed",))
        self.refresh()
        self.assertEqual(labels["2", "salary"].cget("bg"), "#e6f6ec")
        self.app._select_payroll_note_marker("1")
        self.refresh()
        self.assertEqual(labels["1", "salary"].cget("bg"), "#cbd5e1")
        self.assertEqual(labels["1", "salary"].cget("fg"), "#15803d")

    def test_updates_removal_scroll_and_resize(self):
        self.refresh()
        tree = self.app.pay_tree
        tree.set("1", "salary", "250,00")
        tree.set("1", "note_marker", "")
        self.refresh()
        self.assertEqual(self.app.payroll_cell_labels["1", "salary"].cget("text"), "250,00")
        self.assertNotIn(("1", "note_marker"), self.app.payroll_cell_labels)
        self.root.geometry("400x180+-2000+-2000")
        self.root.update()
        self.refresh()
        self.assertNotIn(("1", "total"), self.app.payroll_cell_labels)
        tree.xview_moveto(1)
        self.root.update()
        self.refresh()
        self.assertIn(("1", "total"), self.app.payroll_cell_labels)
        self.assertNotIn(("1", "salary"), self.app.payroll_cell_labels)
        tree.delete("1")
        self.refresh()
        self.assertFalse(any(key[0] == "1" for key in self.app.payroll_cell_labels))

    def test_double_click_keeps_existing_edit_action(self):
        self.refresh()
        with patch.object(APP.FolhaBase, "edit_selected_item") as edit:
            self.app._select_payroll_note_marker("1", edit=True)
        self.assertEqual(self.app.pay_tree.selection(), ("1",))
        edit.assert_called_once_with()

    def test_vertical_scroll_removes_offscreen_cells(self):
        tree = self.app.pay_tree
        for index in range(3, 25):
            tree.insert("", "end", iid=str(index), values=self.values,
                        tags=("review",))
        self.root.update()
        self.refresh()
        self.assertIn(("1", "salary"), self.app.payroll_cell_labels)
        tree.yview_moveto(1)
        self.root.update()
        self.refresh()
        self.assertNotIn(("1", "salary"), self.app.payroll_cell_labels)
        self.assertIn(("24", "salary"), self.app.payroll_cell_labels)


if __name__ == "__main__":
    unittest.main()
