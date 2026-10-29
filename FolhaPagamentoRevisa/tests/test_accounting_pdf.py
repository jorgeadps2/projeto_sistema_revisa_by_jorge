import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

from importar_pdf_folha import extract_payroll_values, read_payroll_pdf
import test_salary_advances_batch


class AccountingPdfParserTests(unittest.TestCase):
    def test_pdf_layout_keeps_net_value_beside_label_despite_drawing_order(self):
        from reportlab.pdfgen.canvas import Canvas
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'synthetic.pdf')
            canvas = Canvas(path)
            canvas.drawString(40, 780, 'Setembro de 2026')
            canvas.drawString(40, 750, 'ANA SILVA')
            canvas.drawString(40, 650, 'Total Liquido')
            canvas.drawString(40, 600, 'Outra informacao')
            canvas.drawString(400, 650, '1.234,56')
            canvas.save()
            rows, problems = read_payroll_pdf(
                path, [dict(id=7, name='Ana Silva')], 2026, 9)
            self.assertEqual(rows[0]['amount'], 1234.56)
            self.assertEqual(problems, [])

    def test_total_liquido_label_with_spacing_and_line_breaks(self):
        for label in ('Total Líquido     1.234,56', 'Total Líquido\n1.234,56'):
            with self.subTest(label=label):
                rows, problems = extract_payroll_values(
                    ['Setembro de 2026\nANA SILVA\n' + label],
                    [dict(id=7, name='Ana Silva')], 2026, 9)
                self.assertEqual(rows[0]['amount'], 1234.56)
                self.assertEqual(problems, [])

    def test_exact_name_period_and_net_amount(self):
        rows, problems = extract_payroll_values(
            ['Setembro de 2026\nANA SILVA\nValor Líquido => 1.234,56'],
            [dict(id=7, name='Ana Silva')], 2026, 9)
        self.assertEqual(rows[0]['employee_id'], 7)
        self.assertEqual(rows[0]['amount'], 1234.56)
        self.assertEqual(problems, [])

    def test_all_employees_are_eligible_including_previously_excluded_names(self):
        for name in ('PESSOA DE TESTE', 'COLABORADOR FICTÍCIO'):
            with self.subTest(name=name):
                rows, _ = extract_payroll_values(
                    [f'09/2026 {name} Total Líquido 100,00'],
                    [dict(id=1, name=name)], 2026, 9)
                self.assertEqual(rows[0]['employee_id'], 1)

    def test_unsafe_pages_are_not_imported(self):
        for text in (
                '08/2026 Ana Silva Valor líquido 100,00',
                '09/2026 Ana Silva Bruno Lima Valor líquido 100,00',
                '09/2026 Ana Silva Total vencimentos 100,00',
                '09/2026 desconhecido Valor líquido 100,00'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                extract_payroll_values([text], [
                    dict(id=1, name='Ana Silva'), dict(id=2, name='Bruno Lima')], 2026, 9)

    def test_duplicate_copies_and_conflicting_amounts(self):
        employees = [dict(id=1, name='Ana Silva')]
        page = '09/2026 Ana Silva Líquido a receber 100,00'
        rows, _ = extract_payroll_values([page, page], employees, 2026, 9)
        self.assertEqual(len(rows), 1)
        with self.assertRaises(ValueError):
            extract_payroll_values([page, page.replace('100,00', '200,00')], employees, 2026, 9)


class AccountingPdfSaveTests(unittest.TestCase):
    setUpClass = classmethod(test_salary_advances_batch.SalaryAdvancesBatchTests.setUpClass.__func__)
    setUp = test_salary_advances_batch.SalaryAdvancesBatchTests.setUp

    def test_preview_shows_only_import_name_amount_and_toggles_colors(self):
        self.owner.save_salary_advances_batch([(1, '10')], 2026, 9, 1)
        window = self.app.FolhaApp.__new__(self.app.FolhaApp)
        self.app.tk.Tk.__init__(window)
        window.withdraw()
        self.addCleanup(window.destroy)
        window.selected_payroll_period = lambda: (2026, 9)

        def check(form):
            window.deiconify()
            form.deiconify()
            form.update()

            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)

            table = next(child for child in descendants(form)
                         if isinstance(child, self.app.ttk.Treeview))
            self.assertEqual(tuple(table['columns']), ('include', 'name', 'new'))
            self.assertEqual(table.item('1', 'tags'), ('included',))
            self.assertEqual(table.set('1', 'include'), 'Sim')
            x, y, width, height = table.bbox('1', 'include')
            table.event_generate('<Button-1>', x=x + 10, y=y + height // 2)
            self.assertEqual(table.set('1', 'include'), 'Não')
            self.assertEqual(table.item('1', 'tags'), ('excluded',))
            table.event_generate('<Button-1>', x=x + 10, y=y + height // 2)
            self.assertEqual(table.set('1', 'include'), 'Sim')
            self.assertEqual(table.item('1', 'tags'), ('included',))
            form.destroy()

        with patch.object(
                self.app.filedialog, 'askopenfilename',
                return_value='synthetic.pdf') as choose_pdf, patch.object(
                self.app, 'read_payroll_pdf',
                return_value=([dict(employee_id=1, name='Ana', amount=100)], [])), patch.object(
                window, 'wait_window', side_effect=check):
            window.import_accounting_pdf_dialog()
        self.assertEqual(
            choose_pdf.call_args.kwargs['initialdir'],
            self.app.ACCOUNTING_PDF_DIR)

    def test_only_included_employees_are_updated_without_name_exclusions(self):
        self.owner.save_salary_advances_batch([(1, '10'), (2, '10'), (3, '10')], 2026, 9, 1)
        with self.app.connect() as con:
            con.execute("UPDATE employees SET name='Jorge Alberto de Paula' WHERE id=1")
            con.execute("UPDATE employees SET name='Wesley Carlos Silva' WHERE id=2")
        self.app.FolhaApp.save_accounting_pdf_values(self.owner, 2026, 9, [
            dict(employee_id=1, amount=100, previous_salary=0),
            dict(employee_id=2, amount=200, previous_salary=0)])
        with self.app.connect() as con:
            rows = con.execute(
                'SELECT salary,advances FROM payroll_items ORDER BY employee_id').fetchall()
            self.assertEqual([row['salary'] for row in rows], [100, 200, 0])
            self.assertEqual([row['advances'] for row in rows], [10, 10, 10])

    def test_save_preserves_other_fields_and_rolls_back_invalid_employee(self):
        self.owner.save_salary_advances_batch([(1, '100')], 2026, 9, 1)
        with self.app.connect() as con:
            con.execute('UPDATE payroll_items SET salary=1000,pf=50,pharmacy=20 WHERE employee_id=1')
            con.execute("UPDATE employees SET name='Jorge Alberto de Paula' WHERE id=2")
        save = self.app.FolhaApp.save_accounting_pdf_values
        save(self.owner, 2026, 9, [dict(employee_id=1, amount=900, previous_salary=1000)])
        with self.app.connect() as con:
            row = con.execute('SELECT * FROM payroll_items WHERE employee_id=1').fetchone()
            self.assertEqual(row['salary'], 900)
            self.assertEqual(row['pf'], 50)
            self.assertEqual(row['advances'], 100)
            self.assertEqual(row['pharmacy'], 20)
            self.assertEqual(row['total'], 830)
        with self.assertRaises(ValueError):
            save(self.owner, 2026, 9, [
                dict(employee_id=1, amount=800, previous_salary=900),
                dict(employee_id=999, amount=800, previous_salary=0)])
        with self.app.connect() as con:
            self.assertEqual(con.execute(
                'SELECT salary FROM payroll_items WHERE employee_id=1').fetchone()[0], 900)
            con.execute("UPDATE payrolls SET status='Fechada'")
        with self.assertRaises(ValueError):
            save(self.owner, 2026, 9, [dict(employee_id=1, amount=800, previous_salary=900)])
