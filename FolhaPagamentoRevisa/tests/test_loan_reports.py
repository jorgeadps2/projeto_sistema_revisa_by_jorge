import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))
SPEC = importlib.util.spec_from_file_location(
    "loan_reports_app", MODULE_DIR / "folha_pagamento.py")
APP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APP)


class LoanReportTypeTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("""
            CREATE TABLE employees (
                id INTEGER PRIMARY KEY,
                code TEXT,
                name TEXT,
                active INTEGER
            )
        """)
        self.addCleanup(self.connection.close)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.app = object.__new__(APP.FolhaBase)

    def generate_report(self, report_kind):
        path = Path(self.temp_dir.name) / f"{report_kind or 'general'}.pdf"
        requested_kinds = []

        def loan_report_data(year, month, kind, employee_id):
            requested_kinds.append(kind)
            return []

        with patch.object(APP, "connect", return_value=self.connection), \
                patch.object(self.app, "loan_report_data", side_effect=loan_report_data), \
                patch.object(APP.FolhaBase, "pdf_page_header"):
            result = self.app.write_employee_general_report_pdf(
                2026, 10, str(path), report_kind=report_kind)

        text = "\n".join(page.extract_text() for page in PdfReader(path).pages)
        return requested_kinds, result, text

    def test_loan_report_includes_only_loan_data(self):
        requested_kinds, result, text = self.generate_report(APP.LOAN_KIND)
        self.assertEqual(requested_kinds, [APP.LOAN_KIND])
        self.assertEqual(result, (0, 0.0))
        self.assertIn("Relatório de Empréstimos por Colaborador", text)
        self.assertIn("Não há empréstimos cadastrados", text)
        self.assertNotIn("Não há adiantamentos cadastrados", text)

    def test_advance_report_includes_only_advance_data(self):
        requested_kinds, result, text = self.generate_report(APP.ADVANCE_KIND)
        self.assertEqual(requested_kinds, [APP.ADVANCE_KIND])
        self.assertEqual(result, (0, 0.0))
        self.assertIn("Relatório de Adiantamentos por Colaborador", text)
        self.assertIn("Não há adiantamentos cadastrados", text)
        self.assertNotIn("Não há empréstimos cadastrados", text)

    def test_unspecified_report_kind_keeps_general_report(self):
        requested_kinds, _, text = self.generate_report(None)
        self.assertEqual(requested_kinds, list(APP.LOAN_KINDS))
        self.assertIn("Relatório Geral por Colaborador", text)
        self.assertIn("Não há empréstimos ou adiantamentos cadastrados", text)

    def test_rejects_unknown_report_kind(self):
        with self.assertRaisesRegex(ValueError, "Selecione empréstimos"):
            self.app.write_employee_general_report_pdf(
                2026, 10, "unused.pdf", report_kind="Outro")


if __name__ == "__main__":
    unittest.main()
