import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
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
        original_connect = APP.connect

        def tracked_connect():
            connection = original_connect()
            self.addCleanup(connection.close)
            return connection

        self.enterContext(patch.object(APP, "connect", side_effect=tracked_connect))
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

    def test_remembers_selected_antares_folder_as_default(self):
        mega_folder = self.folder / "MEGA" / "PDFs"
        mega_folder.mkdir(parents=True)

        with patch.object(APP, "DATA_DIR", str(self.folder)), \
                patch.object(APP, "SIGN_CONFIG_NAME", "config.json"), \
                patch.object(APP, "ACCOUNTING_PDF_DIR", str(self.folder / "old")):
            APP.save_signing_config(pasta_pdf_antares=str(mega_folder))

            self.assertEqual(
                APP.accounting_pdf_initial_directory(), str(mega_folder))

    def test_suggests_the_saved_pdf_for_each_payroll_period(self):
        october_path = self.folder / "MEGA" / "outubro folha.pdf"
        october_path.parent.mkdir(parents=True)
        october_path.write_bytes(b"%PDF-")
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("""CREATE TABLE payroll_accounting_reports(
            year INTEGER, month INTEGER, path TEXT, pdf_data BLOB, updated_at TEXT,
            PRIMARY KEY(year, month))""")
        connection.execute(
            "INSERT INTO payroll_accounting_reports(year,month,path) VALUES(2026,10,?)",
            (str(october_path),))
        self.addCleanup(connection.close)

        with patch.object(APP, "connect", return_value=connection), \
                patch.object(APP, "DATA_DIR", str(self.folder)), \
                patch.object(APP, "SIGN_CONFIG_NAME", "config.json"), \
                patch.object(APP, "ACCOUNTING_PDF_DIR", str(self.folder / "old")):
            APP.save_signing_config(
                pasta_pdf_antares=str(october_path.parent))

            self.assertEqual(
                APP.accounting_pdf_selection_defaults(2026, 10),
                (str(october_path.parent), october_path.name))
            self.assertEqual(
                APP.accounting_pdf_selection_defaults(2026, 11),
                (str(october_path.parent), None))

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

    def test_accounts_for_translated_text_when_finding_available_space(self):
        document = Canvas(str(self.payslip_path), pagesize=(612, 792))
        document.saveState()
        document.translate(0, 100)
        document.drawString(40, 0, "Holerite Ana Silva")
        document.restoreState()
        document.showPage()
        document.save()
        self.write_pdf(self.report_path, [[
            "Envelope Ana Silva", "Competência: Outubro de 2026",
            "Valor líquido 1.234,56",
        ]])

        append_employee_report_pages(
            self.report_path, self.payslip_path, 1, self.employees, 2026, 10)

        page = PdfReader(self.payslip_path).pages[0]
        self.assertIn("Holerite Ana Silva", page.extract_text())
        self.assertIn("Envelope Ana Silva", page.extract_text())

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
        self.write_pdf(report_path, [["Envelope Ana Silva"]])
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("""CREATE TABLE payroll_accounting_reports(
            year INTEGER, month INTEGER, path TEXT, pdf_data BLOB, updated_at TEXT,
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
        connection.row_factory = sqlite3.Row
        connection.execute("""CREATE TABLE payroll_accounting_reports(
            year INTEGER, month INTEGER, path TEXT, pdf_data BLOB, updated_at TEXT,
            PRIMARY KEY(year, month))""")
        self.addCleanup(connection.close)
        app = object.__new__(APP.FolhaBase)

        with patch.object(APP, "ACCOUNTING_PDF_DIR", str(self.folder)), \
                patch.object(APP, "connect", return_value=connection), \
                patch.object(APP.filedialog, "askopenfilename") as choose_report:
            found = app.accounting_report_path_for_period(2026, 10)

        self.assertIsNone(found)
        choose_report.assert_not_called()

    def create_database(self, path):
        with closing(sqlite3.connect(path)):
            pass
        with patch.object(APP, "DB_PATH", str(path)):
            APP.init_db()

    def test_import_saves_pdf_and_recovers_it_without_source_or_database_changes(self):
        database = self.folder / "source.db"
        self.create_database(database)
        self.write_pdf(self.report_path, [
            ["Envelope Ana Silva", "Competência: Outubro de 2026",
             "Valor líquido 1.234,56"]])
        original = self.report_path.read_bytes()
        app = object.__new__(APP.FolhaBase)
        with patch.object(APP, "DB_PATH", str(database)), \
                patch.object(APP, "DATA_DIR", str(self.folder / "other-pc")):
            with APP.connect() as con:
                con.execute("INSERT INTO employees(id,name) VALUES(1,'Ana Silva')")
                con.execute("INSERT INTO payrolls(id,year,month) VALUES(1,2026,10)")
                con.execute("""INSERT INTO payroll_items(
                    payroll_id,employee_id,salary,total) VALUES(1,1,1000,1000)""")
            app.save_accounting_pdf_values(2026, 10, [{
                "employee_id": 1, "amount": 1234.56, "previous_salary": 1000,
            }], str(self.report_path))
            self.report_path.unlink()
            before = database.read_bytes()
            restored = app.accounting_report_path_for_period(2026, 10)
            self.assertEqual(Path(restored).read_bytes(), original)
            self.assertIn("Envelope Ana Silva", PdfReader(restored).pages[0].extract_text())
            self.assertEqual(database.read_bytes(), before)
            Path(restored).write_bytes(b"damaged cache")
            restored = app.accounting_report_path_for_period(2026, 10)
            self.assertEqual(Path(restored).read_bytes(), original)

    def test_missing_source_rolls_back_salary_import(self):
        database = self.folder / "source.db"
        self.create_database(database)
        app = object.__new__(APP.FolhaBase)
        with patch.object(APP, "DB_PATH", str(database)):
            with APP.connect() as con:
                con.execute("INSERT INTO employees(id,name) VALUES(1,'Ana Silva')")
                con.execute("INSERT INTO payrolls(id,year,month) VALUES(1,2026,10)")
                con.execute("""INSERT INTO payroll_items(
                    payroll_id,employee_id,salary,total) VALUES(1,1,1000,1000)""")
            with self.assertRaises(FileNotFoundError):
                app.save_accounting_pdf_values(2026, 10, [{
                    "employee_id": 1, "amount": 1234.56, "previous_salary": 1000,
                }], str(self.report_path))
            with APP.connect() as con:
                self.assertEqual(con.execute("SELECT salary FROM payroll_items").fetchone()[0], 1000)
                self.assertEqual(con.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0], 0)

    def test_migration_embeds_available_legacy_pdf(self):
        database = self.folder / "legacy.db"
        self.write_pdf(self.report_path, [["Envelope Ana Silva"]])
        original = self.report_path.read_bytes()
        with closing(sqlite3.connect(database)) as con, con:
            con.execute("""CREATE TABLE payroll_accounting_reports(
                year INTEGER,month INTEGER,path TEXT,updated_at TEXT,
                PRIMARY KEY(year,month))""")
            con.execute("INSERT INTO payroll_accounting_reports VALUES(2026,10,?,NULL)",
                        (str(self.report_path),))
        with patch.object(APP, "DB_PATH", str(database)):
            APP.init_db()
            APP.init_db()
            with APP.connect() as con:
                self.assertEqual(con.execute(
                    "SELECT pdf_data FROM payroll_accounting_reports").fetchone()[0], original)

    def test_missing_legacy_pdf_requires_selection_instead_of_omitting_attachment(self):
        database = self.folder / "legacy.db"
        self.create_database(database)
        app = object.__new__(APP.FolhaBase)
        with patch.object(APP, "DB_PATH", str(database)), \
                patch.object(APP, "ACCOUNTING_PDF_DIR", str(self.folder / "missing")), \
                patch.object(APP.filedialog, "askopenfilename", return_value="") as choose:
            with APP.connect() as con:
                con.execute("""INSERT INTO payroll_accounting_reports(year,month,path)
                    VALUES(2026,10,?)""", (str(self.report_path),))
            with self.assertRaisesRegex(ValueError, "não está disponível"):
                app.accounting_report_path_for_period(2026, 10)
            choose.assert_called_once()

    def test_selected_replacement_is_embedded(self):
        database = self.folder / "legacy.db"
        self.create_database(database)
        self.write_pdf(self.report_path, [["Envelope Ana Silva"]])
        app = object.__new__(APP.FolhaBase)
        with patch.object(APP, "DB_PATH", str(database)), \
                patch.object(APP, "ACCOUNTING_PDF_DIR", str(self.folder / "missing")), \
                patch.object(APP.filedialog, "askopenfilename", return_value=str(self.report_path)):
            with APP.connect() as con:
                con.execute("""INSERT INTO payroll_accounting_reports(year,month,path)
                    VALUES(2026,10,'missing.pdf')""")
            self.assertEqual(app.accounting_report_path_for_period(2026, 10), str(self.report_path))
            with APP.connect() as con:
                self.assertEqual(con.execute(
                    "SELECT pdf_data FROM payroll_accounting_reports").fetchone()[0],
                    self.report_path.read_bytes())

    def test_pdf_survives_real_transfer_and_is_attached_on_other_pc(self):
        sys.path.insert(0, str(MODULE_DIR.parent / "SistemasRevisa"))
        from revisa_integrado.core import transfer

        source = self.folder / "source.db"
        target = self.folder / "target.db"
        self.create_database(source)
        self.write_pdf(self.report_path, [
            ["Envelope Ana Silva", "Competência: Outubro de 2026",
             "Valor líquido 1.234,56"]])
        with patch.object(APP, "DB_PATH", str(source)), APP.connect() as con:
            con.execute("INSERT INTO employees(id,name) VALUES(1,'Ana Silva')")
            con.execute("INSERT INTO payrolls(id,year,month) VALUES(1,2026,10)")
            con.execute("""INSERT INTO payroll_items(
                payroll_id,employee_id,salary,total) VALUES(1,1,1000,1000)""")
            APP.store_accounting_report(con, 2026, 10, str(self.report_path))
        sender = transfer.load_state(self.folder / "sender.json")
        package = transfer.export_package(
            {"folha": source}, self.folder / "packages", sender,
            self.folder / "sender.json", "2.0.0")
        self.report_path.unlink()
        receiver = transfer.load_state(self.folder / "receiver.json", default_titular=False)
        transfer.import_package(
            package, receiver, self.folder / "receiver.json", {"folha": target},
            self.folder / "backups", "2.0.0", accept_warnings=True)
        app = object.__new__(APP.FolhaBase)
        with patch.object(APP, "DB_PATH", str(target)), \
                patch.object(APP, "DATA_DIR", str(self.folder / "other-pc")):
            restored = app.accounting_report_path_for_period(2026, 10)
            self.write_pdf(self.payslip_path, [["Demonstrativo de Pagamento Ana Silva"]])
            before = transfer._digest("folha", target)
            app.append_accounting_report_to_payslip(
                2026, 10, str(self.payslip_path), 1, restored)
            self.assertEqual(transfer._digest("folha", target), before)
        text = PdfReader(self.payslip_path).pages[0].extract_text()
        self.assertIn("Demonstrativo de Pagamento Ana Silva", text)
        self.assertIn("Envelope Ana Silva", text)


if __name__ == "__main__":
    unittest.main()
