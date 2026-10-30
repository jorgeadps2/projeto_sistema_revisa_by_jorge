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
    "employee_reports_app", MODULE_DIR / "folha_pagamento.py")
APP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APP)


class EmployeeReportTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("""
            CREATE TABLE employees (
                id INTEGER PRIMARY KEY,
                name TEXT,
                code TEXT,
                active INTEGER,
                pix TEXT,
                bank TEXT,
                bank_agency TEXT,
                bank_account TEXT
            )
        """)
        self.connection.executemany("""
            INSERT INTO employees
                (id,name,code,active,pix,bank,bank_agency,bank_account)
            VALUES (?,?,?,?,?,?,?,?)
        """, [
            (1, "Ana Silva", "A-100", 1, "ana-pix@example.com",
             "Banco Revisa", "Agência 123", "Conta 456"),
            (2, "Bruna Costa", "B-200", 0, "41999990000",
             "Banco Brasil", "Agência 789", "Conta 012"),
        ])
        self.addCleanup(self.connection.close)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.app = object.__new__(APP.FolhaBase)

    def generate_report(self, report_type, employee_id=None):
        path = Path(self.temp_dir.name) / f"{report_type}-{employee_id}.pdf"
        with patch.object(APP, "connect", return_value=self.connection), \
                patch.object(APP.FolhaBase, "pdf_page_header"):
            count = self.app.write_employee_report_pdf(
                str(path), report_type, employee_id)
        text = "\n".join(page.extract_text() for page in PdfReader(path).pages)
        return count, text

    def test_pix_report_contains_only_pix_list_for_all_employees(self):
        count, text = self.generate_report("pix")
        self.assertEqual(count, 2)
        self.assertIn("Relatório de PIX", text)
        self.assertIn("ana-pix@example.com", text)
        self.assertIn("41999990000", text)
        self.assertIn("Ana Silva", text)
        self.assertIn("Bruna Costa", text)
        self.assertNotIn("Banco Revisa", text)
        self.assertNotIn("Conta 456", text)

    def test_bank_report_contains_only_account_list_for_one_employee(self):
        count, text = self.generate_report("bank", employee_id=2)
        self.assertEqual(count, 1)
        self.assertIn("Relatório de contas bancárias", text)
        self.assertIn("Bruna Costa", text)
        self.assertIn("Banco Brasil", text)
        self.assertIn("Agência 789", text)
        self.assertIn("Conta 012", text)
        self.assertNotIn("Ana Silva", text)
        self.assertNotIn("41999990000", text)

    def test_rejects_unknown_report_type(self):
        with self.assertRaises(ValueError):
            self.generate_report("complete")


if __name__ == "__main__":
    unittest.main()
