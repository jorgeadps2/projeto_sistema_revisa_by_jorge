import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas


MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))
SPEC = importlib.util.spec_from_file_location(
    "payroll_external_report_app", MODULE_DIR / "folha_pagamento.py")
APP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APP)
from importar_pdf_folha import (
    append_employee_report_pages,
    extract_payroll_values,
)


class PayrollExternalReportTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.folder = Path(self.temp_dir.name)
        self.payslip_path = self.folder / "payslip.pdf"
        self.report_path = self.folder / "accounting.pdf"
        self.employees = [
            {"id": 1, "name": "Ana Silva"},
            {"id": 2, "name": "Bruna Costa"},
        ]

    def write_pdf(self, path, pages):
        document = Canvas(str(path))
        for lines in pages:
            for index, line in enumerate(lines):
                document.drawString(40, 780 - index * 20, line)
            document.showPage()
        document.save()

    def test_places_only_matching_employee_report_below_payslip_on_same_page(self):
        self.write_pdf(self.payslip_path, [["Holerite Ana Silva"]])
        self.write_pdf(self.report_path, [
            ["Envelope Ana Silva", "Competência: Outubro de 2026",
             "Valor líquido 1.234,56"],
            ["Envelope Bruna Costa", "Competência: Outubro de 2026",
             "Valor líquido 2.345,67"],
        ])

        append_employee_report_pages(
            self.report_path, self.payslip_path, 1, self.employees, 2026, 10)

        pages = PdfReader(self.payslip_path).pages
        self.assertEqual(len(pages), 1)
        page_text = pages[0].extract_text()
        self.assertIn("Holerite Ana Silva", page_text)
        self.assertIn("Envelope Ana Silva", page_text)
        self.assertNotIn("Bruna Costa", page_text)

        text_positions = {}

        def record_text_position(text, content_matrix, text_matrix, __, ___):
            position_y = (
                content_matrix[3] * text_matrix[5] + content_matrix[5])
            if "Holerite Ana Silva" in text:
                text_positions["payslip"] = float(position_y)
            if "Envelope Ana Silva" in text:
                text_positions["report"] = float(position_y)

        pages[0].extract_text(visitor_text=record_text_position)
        self.assertGreater(
            text_positions["payslip"], text_positions["report"])

    def test_places_first_report_below_payslip_and_preserves_additional_pages(self):
        self.write_pdf(self.payslip_path, [["Holerite Ana Silva"]])
        self.write_pdf(self.report_path, [
            ["Envelope Ana Silva parte 1", "Competência: Outubro de 2026",
             "Valor líquido 1.234,56"],
            ["Envelope Bruna Costa", "Competência: Outubro de 2026",
             "Valor líquido 2.345,67"],
            ["Envelope Ana Silva parte 2", "Competência: Outubro de 2026",
             "Valor líquido 1.234,56"],
        ])

        append_employee_report_pages(
            self.report_path, self.payslip_path, 1, self.employees, 2026, 10)

        pages = PdfReader(self.payslip_path).pages
        self.assertEqual(len(pages), 2)
        self.assertIn("Holerite Ana Silva", pages[0].extract_text())
        self.assertIn("parte 1", pages[0].extract_text())
        self.assertIn("parte 2", pages[1].extract_text())

    def test_keeps_only_upper_copy_when_external_page_has_two_copies(self):
        self.write_pdf(self.payslip_path, [["Holerite Ana Silva"]])
        document = Canvas(str(self.report_path), pagesize=(612, 792))
        for top in (760, 360):
            document.drawString(40, top, "Envelope Ana Silva")
            document.drawString(40, top - 20, "Competência: Outubro de 2026")
            document.drawString(40, top - 40, "Valor líquido 1.234,56")
        document.showPage()
        document.save()

        append_employee_report_pages(
            self.report_path, self.payslip_path, 1, self.employees, 2026, 10)

        pages = PdfReader(self.payslip_path).pages
        self.assertEqual(len(pages), 1)
        self.assertIn("Holerite Ana Silva", pages[0].extract_text())
        report_positions = []

        def record_report_positions(text, content_matrix, text_matrix, __, ___):
            if "Envelope Ana Silva" in text:
                report_positions.append(
                    content_matrix[3] * text_matrix[5] + content_matrix[5])

        pages[0].extract_text(visitor_text=record_report_positions)
        visible_positions = [
            position for position in report_positions
            if 36 <= position <= float(pages[0].mediabox.height)]
        self.assertEqual(len(visible_positions), 1)

    def test_all_payslips_are_followed_by_their_matching_external_pages(self):
        self.write_pdf(self.report_path, [
            ["Envelope Ana Silva", "Competência: Outubro de 2026",
             "Valor líquido 1.234,56"],
            ["Envelope Bruna Costa", "Competência: Outubro de 2026",
             "Valor líquido 2.345,67"],
        ])
        output_path = self.folder / "all-payslips.pdf"
        app = object.__new__(APP.FolhaBase)
        app.payroll_report_rows = lambda year, month: (
            {"id": 1}, [{"employee_id": 1}, {"employee_id": 2}])

        def write_payslip(year, month, path, employee_id):
            employee = next(
                item for item in self.employees if item["id"] == employee_id)
            self.write_pdf(path, [[f'Holerite {employee["name"]}']])

        def append_report(year, month, path, employee_id, report_path):
            append_employee_report_pages(
                report_path, path, employee_id, self.employees, year, month)

        app.write_payslips_pdf = write_payslip
        app.append_accounting_report_to_payslip = append_report
        app.write_payslips_with_accounting_report(
            2026, 10, str(output_path), None, str(self.report_path))

        pages = PdfReader(output_path).pages
        self.assertEqual(len(pages), 2)
        self.assertIn("Holerite Ana Silva", pages[0].extract_text())
        self.assertIn("Envelope Ana Silva", pages[0].extract_text())
        self.assertIn("Holerite Bruna Costa", pages[1].extract_text())
        self.assertIn("Envelope Bruna Costa", pages[1].extract_text())

    def test_refuses_page_matching_multiple_employees(self):
        self.write_pdf(self.payslip_path, [["Holerite Ana Silva"]])
        self.write_pdf(self.report_path, [
            ["Ana Silva e Bruna Costa", "Competência: Outubro de 2026",
             "Valor líquido 1.234,56"],
            ["Envelope Ana Silva", "Competência: Outubro de 2026",
             "Valor líquido 1.234,56"],
        ])

        with self.assertRaisesRegex(ValueError, "mais de um colaborador"):
            append_employee_report_pages(
                self.report_path, self.payslip_path, 1, self.employees, 2026, 10)

        self.assertEqual(len(PdfReader(self.payslip_path).pages), 1)

    def test_extracts_net_amount_before_total_label(self):
        entries, problems = extract_payroll_values(
            ["Envelope Ana Silva\nCompetência: Outubro de 2026\n"
             "1.234,56 Total Líquido"],
            self.employees,
            2026,
            10,
        )

        self.assertEqual(
            entries,
            [{"employee_id": 1, "name": "Ana Silva", "amount": 1234.56}],
        )
        self.assertEqual(problems, [])

    def test_finds_and_remembers_single_report_in_period_folder(self):
        period_folder = self.folder / "2026" / "102026"
        period_folder.mkdir(parents=True)
        report_path = period_folder / "accounting.pdf"
        report_path.touch()
        connection = sqlite3.connect(":memory:")
        connection.execute("""CREATE TABLE payroll_accounting_reports(
            year INTEGER, month INTEGER, path TEXT, updated_at TEXT,
            PRIMARY KEY(year, month))""")
        self.addCleanup(connection.close)
        app = object.__new__(APP.FolhaBase)

        with patch.object(APP, "ACCOUNTING_PDF_DIR", str(self.folder)), \
                patch.object(APP, "connect", return_value=connection), \
                patch.object(APP.filedialog, "askopenfilename") as choose_report:
            found = app.accounting_report_path_for_period(2026, 10)

        self.assertEqual(found, str(report_path))
        choose_report.assert_not_called()
        stored = connection.execute(
            "SELECT path FROM payroll_accounting_reports "
            "WHERE year=2026 AND month=10").fetchone()
        self.assertEqual(stored[0], str(report_path.resolve()))

    def test_does_not_prompt_if_period_folder_has_no_report(self):
        period_folder = self.folder / "2026" / "102026"
        period_folder.mkdir(parents=True)
        connection = sqlite3.connect(":memory:")
        connection.execute("""CREATE TABLE payroll_accounting_reports(
            year INTEGER, month INTEGER, path TEXT, updated_at TEXT,
            PRIMARY KEY(year, month))""")
        self.addCleanup(connection.close)
        app = object.__new__(APP.FolhaBase)

        with patch.object(APP, "ACCOUNTING_PDF_DIR", str(self.folder)), \
                patch.object(APP, "connect", return_value=connection), \
                patch.object(APP.filedialog, "askopenfilename") as choose_report:
            found = app.accounting_report_path_for_period(2026, 10)

        self.assertIsNone(found)
        choose_report.assert_not_called()


if __name__ == "__main__":
    unittest.main()
