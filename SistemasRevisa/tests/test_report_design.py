import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from revisa_integrado.core import paths

paths.ensure_module_paths()
import folha_pagamento as payroll
import controle_energia_agua as energy


class ReportDesignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.addCleanup(self.connection.close)
        self.enterContext(patch.object(payroll, "connect", return_value=self.connection))
        self.enterContext(patch.object(payroll, "DB_PATH", str(Path(self.temp.name) / "empty.db")))
        original_resource = payroll.resource_path
        self.enterContext(patch.object(payroll, "resource_path", side_effect=lambda name:
                     str(Path(self.temp.name) / name) if name.endswith(".db")
                     else original_resource(name)))
        payroll.init_db()
        self.name = "COLABORADOR EXEMPLO COM NOME COMPLETO PARA VALIDAR O RELATORIO"
        self.connection.execute(
            "INSERT INTO employees(id,name,code,role,admission_date,pix,email,phone) "
            "VALUES(1,?,'001','FUNCAO EXEMPLO','2024-01-01','CHAVE FICTICIA',"
            "'exemplo@example.invalid','TELEFONE FICTICIO')", (self.name,))
        self.connection.execute(
            "INSERT INTO employee_salary_history(employee_id,salary,effective_year,effective_month) "
            "VALUES(1,3200,2026,1)")
        for month in range(1, 13):
            pid = self.connection.execute(
                "INSERT INTO payrolls(year,month) VALUES(2026,?)", (month,)).lastrowid
            self.connection.execute(
                "INSERT INTO payroll_items(payroll_id,employee_id,salary,pf,overtime,"
                "marmitex,notes,total,thirteenth) VALUES(?,1,3200,180,240,110,?,3510,0)",
                (pid, "Observacao de exemplo com <simbolos> & texto."))
        for kind in payroll.LOAN_KINDS:
            self.connection.execute(
                "INSERT INTO employee_loans(employee_id,principal,installment_count,"
                "start_year,start_month,kind,notes) VALUES(1,1200,6,2026,11,?,'Exemplo')",
                (kind,))
        self.connection.execute(
            "INSERT INTO employee_meta_entries(employee_id,entry_date,amount,notes) "
            "VALUES(1,'2026-11-05',200,'Controle separado')")
        self.connection.commit()
        self.app = object.__new__(payroll.FolhaBase)

    def generators(self):
        app = self.app
        result = [
            ("folha", lambda p: app.write_payroll_pdf(2026, 11, p)),
            ("demonstrativo", lambda p: app.write_payslips_pdf(2026, 11, p)),
            ("anual", lambda p: app.write_annual_report_pdf(2026, p)),
            ("anual-individual", lambda p: app.write_annual_report_pdf(2026, p, 1)),
            ("meta", lambda p: app.write_meta_report_pdf("2026-11-01", "2026-11-30", p)),
            ("salarios", app.write_current_salaries_report),
        ]
        for report_type in ("general", "pix", "bank", "phone", "email", "address"):
            result.append((report_type, lambda p, kind=report_type:
                           app.write_employee_report_pdf(p, kind)))
        for kind in (*payroll.LOAN_KINDS, None):
            for month in (None, (2026, 11)):
                result.append((f"{kind or 'geral'}-{month}", lambda p, k=kind, m=month:
                               app.write_employee_general_report_pdf(
                                   2026, 11, p, report_kind=k, only_month=m)))
        return result

    def assert_pdf_branding(self, path):
        reader = PdfReader(path)
        self.assertTrue(reader.pages)
        self.assertEqual(reader.metadata.author, "FTS Distribuidora de Peças Ltda")
        for page in reader.pages:
            text = page.extract_text()
            self.assertIn("FTS Distribuidora de Peças Ltda", text)
            self.assertIn("Emissão:", text)
            self.assertIn("Página", text)
            self.assertTrue(page.images)
            self.assertNotIn("[ANALÍTICO]", text)
        return "\n".join(page.extract_text() for page in reader.pages)

    def test_all_payroll_reports_keep_data_and_use_approved_branding(self):
        for name, generate in self.generators():
            with self.subTest(report=name):
                output = str(Path(self.temp.name) / f"{name}.pdf")
                generate(output)
                text = self.assert_pdf_branding(output)
                self.assertIn("COLABORADOR EXEMPLO", text)
                self.assertIn("RELATORIO", text)

    def test_energy_monthly_and_individual_reports_keep_scope_and_branding(self):
        app = object.__new__(energy.App)
        app.conn = sqlite3.connect(":memory:")
        app.conn.row_factory = sqlite3.Row
        self.addCleanup(app.conn.close)
        app.criar_banco()
        month = app.garantir_mes(2026, 11)
        occupant = app.conn.execute(
            "INSERT INTO ocupantes(nome) VALUES('OCUPANTE EXEMPLO')").lastrowid
        app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id,aluguel) VALUES(?,?,1000)",
            (month, occupant))
        app.conn.commit()
        for selected in (None, occupant):
            with self.subTest(occupant=selected):
                output = str(Path(self.temp.name) / f"energia-{selected}.pdf")
                app.gerar_relatorio_pdf(output, 2026, 11, selected)
                text = self.assert_pdf_branding(output)
                self.assertIn("OCUPANTE EXEMPLO", text)
                self.assertIn("1.000,00", text)
                if selected:
                    self.assertNotIn("Contas e rateios do mês", text)

    def test_redesigned_payslip_keeps_accounting_envelope_on_same_page(self):
        report = str(Path(self.temp.name) / "accounting.pdf")
        canvas = Canvas(report)
        for index, text in enumerate((
                f"Envelope {self.name}", "Competência: Novembro de 2026",
                "Valor líquido 3.110,00")):
            canvas.drawString(40, 780 - index * 20, text)
        canvas.showPage()
        canvas.save()
        output = str(Path(self.temp.name) / "combined.pdf")
        self.app.write_payslips_with_accounting_report(2026, 11, output, 1, report)
        pages = PdfReader(output).pages
        self.assertEqual(len(pages), 1)
        self.assertIn("Cálculo Folha de Pagamento", pages[0].extract_text())
        self.assertIn(f"Envelope {self.name}", pages[0].extract_text())


if __name__ == "__main__":
    unittest.main()
