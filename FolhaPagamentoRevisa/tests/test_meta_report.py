import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))
SPEC = importlib.util.spec_from_file_location(
    "meta_report_app", MODULE_DIR / "folha_pagamento.py")
APP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APP)


class MetaMonthDateRangeTests(unittest.TestCase):
    def test_selected_month_maps_to_full_month(self):
        self.assertEqual(
            APP.meta_month_date_range("Outubro", "2026"),
            ("2026-10-01", "2026-10-31"))

    def test_february_uses_leap_year_length(self):
        self.assertEqual(
            APP.meta_month_date_range("Fevereiro", "2024"),
            ("2024-02-01", "2024-02-29"))

    def test_december_stays_within_selected_year(self):
        self.assertEqual(
            APP.meta_month_date_range("Dezembro", "2026"),
            ("2026-12-01", "2026-12-31"))

    def test_rejects_unknown_month(self):
        with self.assertRaisesRegex(ValueError, "mês válido"):
            APP.meta_month_date_range("", "2026")

    def test_rejects_invalid_year(self):
        for year in ("26", "1899", "10000", "abcd"):
            with self.subTest(year=year), self.assertRaisesRegex(
                    ValueError, "ano válido"):
                APP.meta_month_date_range("Outubro", year)


if __name__ == "__main__":
    unittest.main()
