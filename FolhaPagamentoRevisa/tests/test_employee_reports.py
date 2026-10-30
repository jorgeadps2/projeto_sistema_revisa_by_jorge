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
                role TEXT,
                sector TEXT,
                cpf TEXT,
                ctps TEXT,
                birth_date TEXT,
                admission_date TEXT,
                dismissal_date TEXT,
                pix TEXT,
                phone TEXT,
                email TEXT,
                bank TEXT,
                bank_agency TEXT,
                bank_account TEXT,
                address TEXT,
                address_number TEXT,
                bairro TEXT,
                cep TEXT,
                city TEXT,
                state TEXT
            )
        """)
        self.connection.executemany("""
            INSERT INTO employees
                (id,name,code,active,role,sector,cpf,ctps,birth_date,admission_date,
                 dismissal_date,pix,phone,email,bank,bank_agency,bank_account,
                 address,address_number,bairro,cep,city,state)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, [
            (1, "Ana Silva", "A-100", 1, "Mecânica", "Oficina", "123.456.789-00",
             "CTPS-123", "1990-01-02", "2024-01-15", "", "ana-pix@example.com",
             "(41) 99999-0000", "ana@example.com", "Banco Revisa", "Agência 123",
             "Conta 456", "Rua das Flores", "10", "Centro", "80000-000",
             "Curitiba", "PR"),
            (2, "Bruna Costa", "B-200", 0, "Auxiliar", "Administrativo",
             "987.654.321-00", "CTPS-456", "1992-03-04", "2023-08-01",
             "2025-03-10", "41999990000", "(41) 98888-0000", "bruna@example.com",
             "Banco Brasil", "Agência 789", "Conta 012", "Rua das Palmeiras",
             "20", "Jardim", "81000-000", "Curitiba", "PR"),
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
        self.assertEqual(count, 1)
        self.assertIn("Relatório de PIX", text)
        self.assertIn("ana-pix@example.com", text)
        self.assertIn("Ana Silva", text)
        self.assertNotIn("41999990000", text)
        self.assertNotIn("Bruna Costa", text)
        self.assertNotIn("Inativo", text)
        self.assertNotIn("Banco Revisa", text)
        self.assertNotIn("Conta 456", text)

    def test_bank_report_contains_only_account_list_for_one_employee(self):
        count, text = self.generate_report("bank", employee_id=1)
        self.assertEqual(count, 1)
        self.assertIn("Relatório de contas bancárias", text)
        self.assertIn("Ana Silva", text)
        self.assertIn("Banco Revisa", text)
        self.assertIn("Agência 123", text)
        self.assertIn("Conta 456", text)
        self.assertNotIn("Bruna Costa", text)
        self.assertNotIn("Inativo", text)

    def test_selecting_inactive_employee_does_not_include_them(self):
        count, text = self.generate_report("pix", employee_id=2)
        self.assertEqual(count, 0)
        self.assertNotIn("Bruna Costa", text)
        self.assertNotIn("Inativo", text)

    def test_phone_report_contains_only_phone_numbers(self):
        count, text = self.generate_report("phone")
        self.assertEqual(count, 1)
        self.assertIn("Relatório de telefones", text)
        self.assertIn("(41) 99999-0000", text)
        self.assertNotIn("Bruna Costa", text)
        self.assertNotIn("ana@example.com", text)

    def test_email_report_contains_only_email_addresses(self):
        count, text = self.generate_report("email", employee_id=1)
        self.assertEqual(count, 1)
        self.assertIn("Relatório de e-mails", text)
        self.assertIn("ana@example.com", text)
        self.assertNotIn("(41) 99999-0000", text)
        self.assertNotIn("Banco Revisa", text)

    def test_address_report_formats_address_as_one_compact_column(self):
        count, text = self.generate_report("address")
        self.assertEqual(count, 1)
        self.assertIn("Relatório de endereços", text)
        self.assertIn("Rua das Flores, 10, Centro, CEP 80000-000, Curitiba / PR", text)
        self.assertNotIn("Bruna Costa", text)
        self.assertNotIn("ana@example.com", text)

    def test_general_report_creates_one_complete_page_per_active_employee(self):
        self.connection.execute("UPDATE employees SET active=1 WHERE id=2")
        path=Path(self.temp_dir.name)/"general.pdf"
        with patch.object(APP,"connect",return_value=self.connection), \
                patch.object(APP,"employee_salary_for_period",return_value=4500), \
                patch.object(APP.FolhaBase,"pdf_page_header"):
            count=self.app.write_employee_report_pdf(str(path),"general")

        pages=PdfReader(path).pages
        self.assertEqual(count,2)
        self.assertEqual(len(pages),2)
        ana_text=pages[0].extract_text()
        bruna_text=pages[1].extract_text()
        for value in (
                "Ana Silva","Mecânica","Oficina","123.456.789-00","CTPS-123",
                "02/01/1990","15/01/2024","(41) 99999-0000","ana@example.com",
                "ana-pix@example.com","Banco Revisa","Agência 123","Conta 456",
                "Rua das Flores, 10, Centro","80000-000","Curitiba / PR","4.500,00"):
            with self.subTest(value=value):
                self.assertIn(value,ana_text)
        self.assertNotIn("Bruna Costa",ana_text)
        self.assertIn("Bruna Costa",bruna_text)
        self.assertNotIn("Ana Silva",bruna_text)

    def test_general_report_for_one_employee_has_one_page(self):
        path=Path(self.temp_dir.name)/"general-one.pdf"
        with patch.object(APP,"connect",return_value=self.connection), \
                patch.object(APP,"employee_salary_for_period",return_value=4500), \
                patch.object(APP.FolhaBase,"pdf_page_header"):
            count=self.app.write_employee_report_pdf(str(path),"general",employee_id=1)
        self.assertEqual(count,1)
        self.assertEqual(len(PdfReader(path).pages),1)

    def test_report_columns_expand_to_fit_content_without_filling_page(self):
        original_table = APP.LongTable
        tables = []

        def capture_table(*args, **kwargs):
            table = original_table(*args, **kwargs)
            tables.append(table)
            return table

        with patch.object(APP, "connect", return_value=self.connection), \
                patch.object(APP, "LongTable", side_effect=capture_table), \
                patch.object(APP.FolhaBase, "pdf_page_header"):
            self.app.write_employee_report_pdf(
                str(Path(self.temp_dir.name) / "short.pdf"), "pix")
            self.connection.execute(
                "UPDATE employees SET pix=? WHERE id=1",
                ("A much longer PIX key that needs a wider column",))
            self.app.write_employee_report_pdf(
                str(Path(self.temp_dir.name) / "long.pdf"), "pix")

        short_table,long_table=tables
        self.assertLessEqual(sum(short_table._argW),155*APP.mm)
        self.assertGreater(long_table._argW[2],short_table._argW[2])
        self.assertLessEqual(long_table._argW[2],80*APP.mm)
        self.assertEqual(short_table.hAlign,"CENTER")
        self.assertEqual(short_table._cellStyles[1][0].topPadding,2)
        self.assertEqual(short_table._cellStyles[1][0].bottomPadding,2)

    def test_rejects_unknown_report_type(self):
        with self.assertRaises(ValueError):
            self.generate_report("complete")


if __name__ == "__main__":
    unittest.main()
