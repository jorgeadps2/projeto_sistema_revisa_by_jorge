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
    "employee_report_app", MODULE_DIR / "folha_pagamento.py")
APP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APP)


class EmployeeReportFilterTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute("""
            CREATE TABLE employees (
                id INTEGER PRIMARY KEY,
                name TEXT,
                code TEXT,
                role TEXT,
                sector TEXT,
                city TEXT,
                active INTEGER,
                admission_date TEXT,
                dismissal_date TEXT
            )
        """)
        self.connection.executemany("""
            INSERT INTO employees
                (id,name,code,role,sector,city,active,admission_date,dismissal_date)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, [
            (1, "Ana Silva", "A-100", "Mecânica", "Oficina", "Curitiba", 1,
             "2024-01-15", ""),
            (2, "Bruna Costa", "B-200", "Auxiliar", "Administrativo", "Londrina", 0,
             "2023-08-01", "2025-03-10"),
            (3, "Ana_100%", "C-300", "Mecânica", "Oficina", "Curitiba", 1,
             "2025-02-01", ""),
        ])
        self.addCleanup(self.connection.close)

    def filtered_ids(self, filters):
        clause, params = APP.employee_report_filter_clause(filters)
        rows = self.connection.execute(
            f"SELECT id FROM employees WHERE {clause} ORDER BY id", params)
        return [row[0] for row in rows]

    def test_combines_name_status_and_inclusive_admission_dates(self):
        self.assertEqual(self.filtered_ids({
            "name_or_code": "A-100",
            "status": "Ativos",
            "admission_from": "15/01/2024",
            "admission_to": "01/02/2025",
        }), [1])

    def test_filters_by_role_sector_city_and_dismissal_period(self):
        self.assertEqual(self.filtered_ids({
            "role": "Auxiliar",
            "sector": "Administrativo",
            "city": "Londrina",
            "status": "Inativos",
            "dismissal_from": "01/03/2025",
            "dismissal_to": "31/03/2025",
        }), [2])

    def test_name_filter_treats_like_wildcards_as_literal_text(self):
        self.assertEqual(self.filtered_ids({"name_or_code": "Ana_100%"}), [3])

    def test_rejects_invalid_dates_status_and_reversed_ranges(self):
        invalid_filters = (
            {"admission_from": "31/02/2025"},
            {"status": "Suspensos"},
            {"dismissal_from": "01/04/2025", "dismissal_to": "31/03/2025"},
        )
        for filters in invalid_filters:
            with self.subTest(filters=filters), self.assertRaises(ValueError):
                APP.employee_report_filter_clause(filters)

    def test_pdf_contains_all_personal_contact_address_and_payment_data(self):
        columns = (
            "id", "name", "code", "active", "role", "sector", "cpf", "ctps",
            "birth_date", "admission_date", "dismissal_date", "phone", "email",
            "bank", "bank_agency", "bank_account", "pix", "cep", "city", "state",
            "address", "address_number", "bairro",
        )
        self.connection.execute("DROP TABLE employees")
        self.connection.execute(
            "CREATE TABLE employees (" +
            ",".join(f"{column} TEXT" for column in columns) + ")")
        self.connection.execute(
            "INSERT INTO employees VALUES (" + ",".join("?" for _ in columns) + ")",
            (
                1, "Ana Silva", "A-100", 1, "Mecânica", "Oficina",
                "123.456.789-00", "CTPS-123", "1990-01-02", "2024-01-15", "",
                "(41) 99999-0000", "ana@example.com", "Banco Teste", "Ag 123",
                "Conta 456", "pix@example.com", "80000-000", "Curitiba", "PR",
                "Rua das Flores", "10", "Centro",
            ))
        self.connection.row_factory = sqlite3.Row
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        report_path = Path(temp_dir.name) / "employee-report-test.pdf"
        app = object.__new__(APP.FolhaBase)
        with patch.object(APP, "connect", return_value=self.connection), \
                patch.object(APP, "employee_salary_for_period", return_value=4500), \
                patch.object(APP.FolhaBase, "pdf_page_header"):
            count = app.write_employee_report_pdf(
                str(report_path), filters={"city": "Curitiba", "status": "Ativos"})
        text = "\n".join(page.extract_text() for page in PdfReader(report_path).pages)
        self.assertEqual(count, 1)
        for value in (
                "Ana Silva", "A-100", "Banco Teste", "Ag 123", "Conta 456",
                "pix@example.com", "ana@example.com", "99999-0000",
                "Rua das Flores", "10", "Centro", "80000-000", "Curitiba", "PR"):
            with self.subTest(value=value):
                self.assertIn(value, text)


if __name__ == "__main__":
    unittest.main()
