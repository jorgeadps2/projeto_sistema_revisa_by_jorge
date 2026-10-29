import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Paragraph
from pypdf import PdfReader


class LoanReportLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        source = Path(__file__).resolve().parents[1] / 'folha_pagamento.py'
        spec = importlib.util.spec_from_file_location('report_layout_app', source)
        cls.app = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {'LOCALAPPDATA': cls.directory.name}):
            spec.loader.exec_module(cls.app)

    def report_rows(self, count=1):
        return [
            dict(
                employee_id=index, loan_id=index, name='Colaborador com nome muito longo ' * 4,
                kind=kind, principal=123456789.12, paid=12345678.12,
                balance=111111111.0, paid_installments=12, pending_installments=108,
                installment_count=120, installment_amount=1234567.89,
                next_due='Novembro/2026 - Parcela 13 de 120',
                monthly_details=[
                    dict(year=2026, month=11, scheduled=1234567.89,
                         paid=0, pending=1234567.89, installment_number=13,
                         installment_count=120, settlement=False),
                ],
            )
            for index in range(count) for kind in self.app.LOAN_KINDS
        ]

    def assert_table_layout(self, table):
        self.assertLessEqual(sum(table._colWidths), (210 - 24) * mm + 0.01)
        self.assertGreaterEqual(table.spaceAfter, 8 * mm)
        for row_index, row in enumerate(table._cellvalues):
            for column_index, value in enumerate(row):
                style = table._cellStyles[row_index][column_index]
                available = (
                    table._colWidths[column_index]
                    - style.leftPadding - style.rightPadding
                )
                values = value if isinstance(value, (tuple, list)) else [value]
                for cell in values:
                    if isinstance(cell, Paragraph):
                        self.assertLessEqual(cell.style.fontSize, 5.5)
                        cell.wrap(available, 10000)
                        if cell.blPara.kind == 0:
                            spaces = [line[0] for line in cell.blPara.lines]
                        else:
                            spaces = [line.extraSpace for line in cell.blPara.lines]
                        self.assertTrue(all(space >= -0.01 for space in spaces))
                    else:
                        self.assertLessEqual(
                            stringWidth(str(cell), style.fontname, style.fontsize),
                            available + 0.01,
                            f'Cell exceeds column: {cell}',
                        )

    def generate_report(self, only_month=None, count=1):
        rows = self.report_rows(count)
        owner = SimpleNamespace(
            loan_report_data=lambda year, month, selected_kind, employee_id: [
                row for row in rows if row['kind'] == selected_kind
            ],
            pdf_page_header=MagicMock(),
        )
        tables = []
        original = self.app.LongTable

        def capture(*args, **kwargs):
            table = original(*args, **kwargs)
            tables.append(table)
            return table

        connection = MagicMock()
        connection.__enter__.return_value.execute.return_value.fetchall.return_value = [
            dict(id=index, code=str(index), name='Colaborador', active=True)
            for index in range(count)
        ]
        path = str(Path(self.directory.name) / 'report.pdf')
        with patch.object(self.app, 'LongTable', side_effect=capture), patch.object(
                self.app, 'connect', return_value=connection):
            result = self.app.FolhaApp.write_employee_general_report_pdf(
                owner, 2026, 10, path, only_month=only_month)
        self.assertGreater(Path(path).stat().st_size, 1000)
        self.assertEqual(result[0], count)
        self.assertAlmostEqual(result[1], 111111111.0 * count * 2)
        for table in tables:
            self.assert_table_layout(table)
        return owner

    def test_employee_report_wraps_status_and_large_values(self):
        self.generate_report()

    def test_employee_month_report_wraps_total_label(self):
        self.generate_report(only_month=(2026, 11))

    def test_employee_report_generates_multiple_pages(self):
        owner = self.generate_report(count=65)
        self.assertGreater(owner.pdf_page_header.call_count, 1)
        reader = PdfReader(str(Path(self.directory.name) / 'report.pdf'))
        total = len(reader.pages)
        for index, page in enumerate(reader.pages, 1):
            self.assertIn(f'Página {index} de {total}', page.extract_text())

    def test_page_totals_preserve_content_and_header_images(self):
        for page_size in (self.app.A4, self.app.landscape(self.app.A4)):
            for count in (1, 3):
                with self.subTest(page_size=page_size, count=count):
                    path = str(Path(self.directory.name) / 'numbered.pdf')
                    story = []
                    for index in range(1, count + 1):
                        if index > 1:
                            story.append(self.app.PageBreak())
                        story.append(Paragraph(
                            f'Conteudo exclusivo {index}',
                            self.app.getSampleStyleSheet()['Normal']))

                    def header(canvas, document):
                        self.app.FolhaApp.pdf_page_header(
                            None, canvas, page_size, '26/10/2026', document.page)

                    self.app.SimpleDocTemplate(
                        path, pagesize=page_size, topMargin=24 * mm,
                    ).build(
                        story, onFirstPage=header, onLaterPages=header,
                        canvasmaker=self.app.NumberedReportCanvas)
                    reader = PdfReader(path)
                    self.assertEqual(len(reader.pages), count)
                    for index, page in enumerate(reader.pages, 1):
                        text = page.extract_text()
                        self.assertEqual(text.count(f'Página {index} de {count}'), 1)
                        self.assertIn(f'Conteudo exclusivo {index}', text)
                        self.assertTrue(page.images)

    def test_empty_reports(self):
        self.generate_report(count=0)

    def test_payslip_discriminates_loan_and_advance_installment_values(self):
        row=dict(
            employee_id=1,name='Colaborador teste',salary=2000,pf=0,
            overtime=0,vacation=0,thirteenth=0,marmitex=0,
            advances=80,pharmacy=0,loan=140,other_deductions=0,
            total=1780,loan_installment='Emp 2/10 + Vale')
        owner=SimpleNamespace(
            payroll_report_rows=lambda year,month: ({'id':1},[row]),
            pdf_page_header=MagicMock())
        connection=MagicMock()
        connection.__enter__.return_value.execute.return_value.fetchall.return_value=[]
        tables=[]
        original=self.app.Table

        def capture(*args,**kwargs):
            table=original(*args,**kwargs)
            tables.append(table)
            return table

        def installments(con,employee_id,year,month,kind):
            return [(2,10,100),(1,5,50)] if kind==self.app.LOAN_KIND else [(1,1,80)]

        path=str(Path(self.directory.name)/'payslip.pdf')
        with patch.object(self.app,'connect',return_value=connection), patch.object(
                self.app,'loan_installment_details',side_effect=installments), patch.object(
                self.app,'Table',side_effect=capture):
            self.app.FolhaApp.write_payslips_pdf(owner,2026,10,path)
        deduction_rows=tables[1]._cellvalues
        descriptions={
            cell.getPlainText():cells[2]
            for cells in deduction_rows
            for cell in (cells[0] if isinstance(cells[0],(tuple,list)) else [cells[0]])
            if isinstance(cell,Paragraph)}
        loan_text=next(text for text in descriptions if text.startswith('Empr'))
        advance_text=next(text for text in descriptions if text.startswith('Adiantamento'))
        self.assertIn('2/10: R$ 100,00',loan_text)
        self.assertIn('1/5: R$ 50,00',loan_text)
        self.assertIn('2/10: R$ 100,00 | 1/5: R$ 50,00',loan_text)
        loan_paragraph=next(
            cell for cells in deduction_rows
            for cell in (cells[0] if isinstance(cells[0],(tuple,list)) else [cells[0]])
            if isinstance(cell,Paragraph) and cell.getPlainText()==loan_text)
        self.assertIn(
            f'<font size="{loan_paragraph.style.fontSize-1}">',
            loan_paragraph.text)
        self.assertNotIn('R$ 80,00',loan_text)
        self.assertIn('1/1: R$ 80,00',advance_text)
        self.assertEqual(descriptions[loan_text],'R$ 140,00')
        self.assertEqual(descriptions[advance_text],'R$ 80,00')
        self.assertGreater(Path(path).stat().st_size,1000)

    def test_summary_report_removed(self):
        self.assertFalse(hasattr(self.app.FolhaApp, 'write_loan_report_pdf'))
        self.assertFalse(hasattr(self.app.FolhaApp, 'generate_loan_report_dialog'))

    def test_employee_dialog_passes_selected_employee(self):
        connection = MagicMock()
        connection.__enter__.return_value.execute.return_value.fetchall.return_value = [
            dict(id=42, name='Funcionario selecionado')]
        owner = SimpleNamespace(
            selected_payroll_period=lambda: (2026, 10),
            write_employee_general_report_pdf=MagicMock(),
            wait_window=MagicMock(),
        )
        employee_box = MagicMock()
        employee_box.current.return_value = 1
        period_box = MagicMock()
        period_box.current.return_value = 0
        month_box = MagicMock()

        def button(*args, **kwargs):
            if kwargs.get('text') == 'Gerar PDF':
                kwargs['command']()
            return MagicMock()

        path = str(Path(self.directory.name) / 'selected.pdf')
        with patch.object(self.app, 'connect', return_value=connection), patch.object(
                self.app.tk, 'Toplevel'), patch.object(
                self.app.tk, 'StringVar'), patch.object(
                self.app.ttk, 'Frame'), patch.object(
                self.app.ttk, 'Label'), patch.object(
                self.app.ttk, 'Spinbox'), patch.object(
                self.app.ttk, 'Combobox',
                side_effect=[employee_box, period_box, month_box]), patch.object(
                self.app.ttk, 'Button', side_effect=button), patch.object(
                self.app, 'temporary_pdf_path', return_value=path), patch.object(
                self.app, 'open_pdf') as open_pdf:
            self.app.FolhaApp.generate_advance_report_dialog(owner)
        owner.write_employee_general_report_pdf.assert_called_once_with(
            2026, 10, path, employee_id=42, only_month=None)
        open_pdf.assert_called_once_with(path)


if __name__ == '__main__':
    unittest.main()
