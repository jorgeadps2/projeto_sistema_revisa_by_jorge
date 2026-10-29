import importlib.util
import os
from pathlib import Path
import tempfile
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import patch

from pypdf import PdfReader


class MetaEntriesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        source = Path(__file__).resolve().parents[1] / 'folha_pagamento.py'
        spec = importlib.util.spec_from_file_location('meta_test_app', source)
        cls.app = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {'LOCALAPPDATA': cls.directory.name}):
            spec.loader.exec_module(cls.app)

    def setUp(self):
        database = tempfile.NamedTemporaryFile(
            dir=self.directory.name, suffix='.db', delete=False)
        database.close()
        self.addCleanup(os.remove, database.name)
        database_patch = patch.object(self.app, 'DB_PATH', database.name)
        database_patch.start()
        self.addCleanup(database_patch.stop)
        original_connect = self.app.connect
        connections = []

        def connect():
            connection = original_connect()
            connections.append(connection)
            return connection

        connection_patch = patch.object(self.app, 'connect', side_effect=connect)
        connection_patch.start()
        self.addCleanup(connection_patch.stop)
        self.addCleanup(lambda: [connection.close() for connection in connections])
        self.app.init_db()
        with self.app.connect() as con:
            con.execute("INSERT INTO employees(name) VALUES('Ana')")
            con.execute("INSERT INTO employees(name) VALUES('Bruno')")
            con.execute("INSERT INTO employees(name,active) VALUES('Inativo',0)")
            payroll_id = con.execute(
                'INSERT INTO payrolls(year,month) VALUES(2026,10)').lastrowid
            con.execute('''INSERT INTO payroll_items(
                payroll_id,employee_id,salary,pf,meta,total) VALUES(?,1,3000,100,50,3150)''',
                (payroll_id,))
            con.execute("UPDATE payrolls SET status='Fechada' WHERE id=?", (payroll_id,))
        self.owner = SimpleNamespace()
        for name in (
                'save_meta_entry', 'delete_meta_entry', 'meta_report_data',
                '_save_meta_entry_in_connection', 'save_meta_batch',
                'write_meta_report_pdf', 'sync_all_loans', 'loan_months',
                'sync_loan_payrolls', 'apply_loan_installments'):
            setattr(self.owner, name, MethodType(getattr(self.app.FolhaApp, name), self.owner))
        self.owner.pdf_page_header = lambda *args: None

    def payroll_snapshot(self):
        with self.app.connect() as con:
            return {
                table: [tuple(row) for row in con.execute(f'SELECT * FROM {table} ORDER BY id')]
                for table in ('payrolls', 'payroll_items', 'employee_loans', 'employee_loan_adjustments')
            }

    def test_create_edit_delete_never_change_payroll_even_when_closed(self):
        original = self.payroll_snapshot()
        entry_id = self.owner.save_meta_entry(1, '28/10/2026', '123,45', 'Meta outubro')
        self.owner.sync_all_loans()
        self.assertEqual(self.payroll_snapshot(), original)
        row = self.owner.meta_report_data('01/10/2026', '31/10/2026')[0]
        self.assertEqual((row['entry_date'], row['amount'], row['notes']),
                         ('2026-10-28', 123.45, 'Meta outubro'))
        self.owner.save_meta_entry(2, '29/10/2026', '200,00', 'Revisado', entry_id)
        self.assertEqual(self.payroll_snapshot(), original)
        self.owner.delete_meta_entry(entry_id)
        self.assertEqual(self.owner.meta_report_data('01/10/2026', '31/10/2026'), [])
        self.assertEqual(self.payroll_snapshot(), original)
        with self.app.connect() as con:
            self.assertEqual([row[0] for row in con.execute('SELECT action FROM audit_log')],
                             ['Cadastro de Meta', 'Edição de Meta', 'Exclusão de Meta'])

    def test_invalid_inputs_do_not_save_anything(self):
        for value in ('', '0', '-1', 'nan', 'inf', '0,001', 'inválido'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.owner.save_meta_entry(1, '28/10/2026', value)
        for date in ('', '31/02/2026', 'não é data'):
            with self.subTest(date=date), self.assertRaises(ValueError):
                self.owner.save_meta_entry(1, date, '100')
        for employee_id in (3, 999):
            with self.subTest(employee_id=employee_id), self.assertRaises(ValueError):
                self.owner.save_meta_entry(employee_id, '28/10/2026', '100')
        with self.app.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM employee_meta_entries').fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0], 0)

    def test_inactive_history_can_be_consulted_edited_and_not_orphaned(self):
        entry_id = self.owner.save_meta_entry(1, '28/10/2026', '100')
        with self.app.connect() as con:
            con.execute('UPDATE employees SET active=0 WHERE id=1')
        self.owner.save_meta_entry(1, '28/10/2026', '150', 'Correção', entry_id)
        self.assertEqual(self.owner.meta_report_data('01/10/2026', '31/10/2026', 1)[0]['amount'], 150)
        with self.app.connect() as con, self.assertRaises(self.app.sqlite3.IntegrityError):
            con.execute('DELETE FROM employees WHERE id=1')
        with self.assertRaises(ValueError):
            self.owner.save_meta_entry(1, '28/10/2026', '10')

    def test_missing_entries_and_invalid_periods_raise(self):
        with self.assertRaises(ValueError):
            self.owner.save_meta_entry(1, '28/10/2026', '100', entry_id=999)
        with self.assertRaises(ValueError):
            self.owner.delete_meta_entry(999)
        for start, end in (('', ''), ('31/10/2026', '01/10/2026'), ('31/02/2026', '31/10/2026')):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                self.owner.meta_report_data(start, end)

    def test_audit_failure_rolls_back_meta(self):
        with self.app.connect() as con:
            con.execute('''CREATE TRIGGER reject_meta_audit BEFORE INSERT ON audit_log
                BEGIN SELECT RAISE(ABORT,'audit failure'); END''')
        with self.assertRaises(self.app.sqlite3.IntegrityError):
            self.owner.save_meta_entry(1, '28/10/2026', '100')
        self.assertEqual(self.owner.meta_report_data('01/10/2026', '31/10/2026'), [])

    def test_period_employee_filters_pdf_totals_and_persistence(self):
        self.owner.save_meta_entry(1, '01/10/2026', '100,25', 'Primeiro <teste> & observação\nSegunda linha')
        self.owner.save_meta_entry(1, '31/10/2026', '200,50', 'Último dia')
        self.owner.save_meta_entry(2, '15/10/2026', '50', 'Outra pessoa')
        self.owner.save_meta_entry(1, '01/11/2026', '900', 'Fora do período')
        self.app.init_db()
        rows = self.owner.meta_report_data('01/10/2026', '31/10/2026', 1)
        self.assertEqual(len(rows), 2)
        path = str(Path(self.directory.name) / 'meta_filtered.pdf')
        self.assertEqual(
            self.owner.write_meta_report_pdf('01/10/2026', '31/10/2026', path, 1),
            (2, 300.75))
        text = '\n'.join(page.extract_text() for page in PdfReader(path).pages)
        for expected in ('Relatório de Meta', 'Ana', '300,75', 'Primeiro <teste> & observação',
                         'Segunda linha', '01/10/2026', '31/10/2026', 'Página 1 de 1'):
            self.assertIn(expected, text)
        self.assertNotIn('Bruno', text)
        self.assertNotIn('Fora do período', text)
        self.assertEqual(
            self.owner.write_meta_report_pdf('01/10/2026', '31/10/2026', path),
            (3, 350.75))
        self.assertEqual(
            self.owner.write_meta_report_pdf('01/12/2026', '31/12/2026', path),
            (0, 0))
        self.assertIn('Nenhum lançamento', PdfReader(path).pages[0].extract_text())

    def test_pdf_multiple_pages_repeat_headers_and_page_numbers(self):
        for index in range(90):
            self.owner.save_meta_entry(1, '28/10/2026', '10,01', f'Lançamento número {index}')
        path = str(Path(self.directory.name) / 'meta_pages.pdf')
        self.assertEqual(
            self.owner.write_meta_report_pdf('01/10/2026', '31/10/2026', path),
            (90, 900.90))
        reader = PdfReader(path)
        self.assertGreater(len(reader.pages), 1)
        for index, page in enumerate(reader.pages, 1):
            text = page.extract_text()
            self.assertIn('Colaborador', text)
            self.assertIn(f'Página {index} de {len(reader.pages)}', text)
        self.assertIn('900,90', reader.pages[-1].extract_text())

    def test_meta_report_matches_compact_table_style_and_fits_page(self):
        self.owner.save_meta_entry(
            1, '28/10/2026', '123456789,12', 'Observação longa ' * 60)
        with self.app.connect() as con:
            con.execute('UPDATE employees SET name=? WHERE id=1', ('Nome longo ' * 15,))
        tables = []
        original_table = self.app.LongTable

        def capture(*args, **kwargs):
            table = original_table(*args, **kwargs)
            tables.append(table)
            return table

        path = str(Path(self.directory.name) / 'meta_layout.pdf')
        with patch.object(self.app, 'LongTable', side_effect=capture):
            self.assertEqual(self.owner.write_meta_report_pdf(
                '01/10/2026', '31/10/2026', path), (1, 123456789.12))
        table = tables[0]
        self.assertAlmostEqual(sum(table._colWidths), self.app.A4[0] - 24 * self.app.mm - 12)
        self.assertEqual(table.repeatRows, 1)
        self.assertEqual(table.spaceAfter, 8 * self.app.mm)

        def contents(value):
            return value[0] if isinstance(value, (tuple, list)) else value

        self.assertEqual([contents(cell).getPlainText() for cell in table._cellvalues[0]],
                         ['Colaborador', 'Data', 'Valor total', 'Observações'])
        self.assertEqual(contents(table._cellvalues[-1][0]).getPlainText(), 'TOTAL GERAL')
        for row_index, row in enumerate(table._cellvalues):
            for column_index, value in enumerate(row):
                value = contents(value)
                style = table._cellStyles[row_index][column_index]
                self.assertEqual(style.leftPadding, 3)
                self.assertEqual(style.topPadding, 1.5)
                if isinstance(value, self.app.Paragraph):
                    self.assertLessEqual(value.style.fontSize, 5.5)
                    if row_index == 0 or column_index in (1, 2):
                        self.assertEqual(value.style.alignment, 1)
                    available = table._colWidths[column_index] - style.leftPadding - style.rightPadding
                    value.wrap(available, 10000)
                    lines = value.blPara.lines
                    spaces = [line[0] for line in lines] if value.blPara.kind == 0 else [
                        line.extraSpace for line in lines]
                    self.assertTrue(all(space >= -0.01 for space in spaces))
        text = '\n'.join(page.extract_text() for page in PdfReader(path).pages)
        self.assertIn('123.456.789,12', text)
        self.assertIn('TOTAL GERAL', text)

    def make_window(self):
        window = self.app.FolhaApp.__new__(self.app.FolhaApp)
        self.app.tk.Tk.__init__(window)
        window.withdraw()
        self.addCleanup(window.destroy)
        window.loans_tab = self.app.ttk.Frame(window)
        window.pay_year = SimpleNamespace(get=lambda: '2026')
        window.pay_month = SimpleNamespace(get=lambda: self.app.MONTHS[9])
        window._build_loans()
        window.meta_start_var.set('01/10/2026')
        window.meta_end_var.set('31/10/2026')
        window.refresh_loans()
        window.update()
        return window

    def test_meta_tab_filters_form_crud_and_report_callback(self):
        window = self.make_window()
        self.assertEqual([window.loan_notebook.tab(tab, 'text')
                          for tab in window.loan_notebook.tabs()],
                         ['Adiantamentos', 'Empréstimos', 'Meta'])
        window.loan_notebook.select(2)
        window.update()
        self.assertIn('Meta:', window.loan_period_label.cget('text'))
        menu = window.meta_actions_menu
        self.assertEqual([
            menu.entrycget(index, 'label')
            for index in range(menu.index('end') + 1)
            if menu.type(index) != 'separator'
        ], ['Cadastrar Meta', 'Cadastrar Meta em lote', 'Editar', 'Excluir'])
        self.assertEqual(menu.type(2), 'separator')
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        action_buttons = [
            widget for widget in descendants(window.loans_tab)
            if isinstance(widget, self.app.ttk.Menubutton)
            and widget.cget('text') == 'Cadastrar / ações'
        ]
        self.assertEqual(len(action_buttons), 2)
        for button in action_buttons:
            self.assertEqual(button.cget('style'), 'Orange.TMenubutton')
            self.assertTrue(button.cget('image'))
            self.assertEqual(button.pack_info()['fill'], 'x')
        report_button = next(
            widget for widget in descendants(window.loans_tab)
            if isinstance(widget, self.app.ttk.Button)
            and widget.cget('text') == 'Meta (PDF)')
        self.assertEqual(report_button.cget('style'), 'Report.TButton')
        self.assertEqual(report_button.master.cget('text'), 'Relatórios')
        self.assertTrue(report_button.cget('image'))
        menu.invoke(0)
        form = next(child for child in window.winfo_children()
                    if isinstance(child, self.app.tk.Toplevel))
        fields = form.winfo_children()[0]
        fields.grid_slaves(row=2, column=1)[0].delete(0, 'end')
        fields.grid_slaves(row=2, column=1)[0].insert(0, '28/10/2026')
        fields.grid_slaves(row=3, column=1)[0].insert(0, '123,45')
        fields.grid_slaves(row=4, column=1)[0].insert('1.0', 'Meta pela interface')
        buttons = fields.grid_slaves(row=5, column=0)[0]
        with patch.object(self.app.messagebox, 'showinfo'):
            next(button for button in buttons.winfo_children()
                 if button.cget('text') == 'Salvar').invoke()
        self.assertEqual(len(window.meta_tree.get_children()), 1)
        entry_id = window.meta_tree.get_children()[0]
        window.meta_tree.selection_set(entry_id)
        menu.invoke(3)
        form = next(child for child in window.winfo_children()
                    if isinstance(child, self.app.tk.Toplevel))
        self.assertEqual(form.title(), 'Editar Meta')
        form.destroy()
        window.meta_employee_box.current(window.meta_employee_ids.index(2))
        window.refresh_meta()
        self.assertEqual(window.meta_tree.get_children(), ())
        window.meta_employee_box.current(0)
        window.refresh_meta()
        with patch.object(window, 'write_meta_report_pdf') as write, patch.object(
                self.app, 'open_pdf') as open_pdf, patch.object(
                self.app, 'temporary_pdf_path', return_value='test_meta.pdf'):
            window.generate_meta_report()
            write.assert_called_once_with('2026-10-01', '2026-10-31', 'test_meta.pdf', None)
            open_pdf.assert_called_once_with('test_meta.pdf')
        window.meta_tree.selection_set(entry_id)
        with patch.object(self.app.messagebox, 'askyesno', return_value=True):
            menu.invoke(4)
        self.assertEqual(window.meta_tree.get_children(), ())
        window.loan_notebook.select(1)
        window.update()
        self.assertIs(window.loans_tree, window.loan_trees['loans'])
        window.loan_notebook.select(0)
        window.update()
        self.assertIs(window.loans_tree, window.loan_trees['advances'])

    def test_meta_columns_follow_loan_table_layout(self):
        entry_id = self.owner.save_meta_entry(1, '28/10/2026', '123,45', 'Observação')
        window = self.make_window()
        tree = window.meta_tree
        self.assertEqual(tuple(tree['columns']), ('employee', 'date', 'amount', 'notes'))
        self.assertEqual(tuple(tree.item(str(entry_id), 'values')),
                         ('Ana', '28/10/2026', 'R$ 123,45', 'Observação'))
        for column in tree['columns']:
            self.assertEqual(str(tree.heading(column, 'anchor')), 'center')
            self.assertEqual(str(tree.column(column, 'anchor')),
                             'w' if column in ('employee', 'notes') else 'center')
            self.assertEqual(bool(tree.column(column, 'stretch')), column == 'notes')
            self.assertLessEqual(tree.column(column, 'width'), 180)
        self.assertEqual(tree.heading('amount', 'text'),
                         window.loan_trees['advances'].heading('total_amount', 'text'))
        window.meta_start_var.set('01/12/2026')
        window.meta_end_var.set('31/12/2026')
        window.refresh_meta()
        self.assertEqual(tree.get_children(), ())
        self.assertTrue(tree.column('notes', 'stretch'))
        self.assertFalse(tree.column('employee', 'stretch'))

    def test_employee_with_only_meta_history_cannot_be_deleted(self):
        self.owner.save_meta_entry(2, '28/10/2026', '100')
        window = self.make_window()
        window.selected_employee_tree = lambda: SimpleNamespace(selection=lambda: ('2',))
        with patch.object(self.app.messagebox, 'askyesno', return_value=True), patch.object(
                self.app.messagebox, 'showwarning') as warning:
            window.delete_selected_employee()
        self.assertIn('lançamentos de Meta', warning.call_args.args[1])
        with self.app.connect() as con:
            self.assertIsNotNone(con.execute('SELECT id FROM employees WHERE id=2').fetchone())

    def test_meta_batch_same_amount_subset_and_no_payroll_effect(self):
        snapshot = self.payroll_snapshot()
        self.assertEqual(self.owner.save_meta_batch([1, 2], '28/10/2026', '123,45', 'Lote'),
                         (2, 246.90))
        rows = self.owner.meta_report_data('01/10/2026', '31/10/2026')
        self.assertEqual([(row['employee_id'], row['amount'], row['notes']) for row in rows],
                         [(1, 123.45, 'Lote'), (2, 123.45, 'Lote')])
        self.assertEqual(self.owner.save_meta_batch([2], '29/10/2026', '10'), (1, 10))
        self.assertEqual(self.payroll_snapshot(), snapshot)
        self.owner.sync_all_loans()
        self.assertEqual(self.payroll_snapshot(), snapshot)
        path = str(Path(self.directory.name) / 'meta_batch.pdf')
        self.assertEqual(
            self.owner.write_meta_report_pdf('01/10/2026', '31/10/2026', path),
            (3, 256.90))
        self.assertIn('256,90', PdfReader(path).pages[-1].extract_text())

    def test_invalid_meta_batch_is_atomic_including_audit(self):
        for employee_ids, date, amount in (
                ([], '28/10/2026', '10'), ([1, 1], '28/10/2026', '10'),
                ([1, 3], '28/10/2026', '10'), ([1, 999], '28/10/2026', '10'),
                ([1, 2], '31/02/2026', '10'), ([1, 2], '28/10/2026', 'nan'),
                ([1, 2], '28/10/2026', '0')):
            with self.subTest(employee_ids=employee_ids, date=date, amount=amount):
                with self.assertRaises(ValueError):
                    self.owner.save_meta_batch(employee_ids, date, amount)
                with self.app.connect() as con:
                    self.assertEqual(con.execute('SELECT COUNT(*) FROM employee_meta_entries').fetchone()[0], 0)
                    self.assertEqual(con.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0], 0)
        with self.app.connect() as con:
            con.execute('''CREATE TRIGGER reject_second_meta BEFORE INSERT ON audit_log
                WHEN (SELECT COUNT(*) FROM employee_meta_entries)=2
                BEGIN SELECT RAISE(ABORT,'audit failure'); END''')
        with self.assertRaises(self.app.sqlite3.IntegrityError):
            self.owner.save_meta_batch([1, 2], '28/10/2026', '10')
        with self.app.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM employee_meta_entries').fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0], 0)

    def widgets(self, widget):
        for child in widget.winfo_children():
            yield child
            yield from self.widgets(child)

    def current_form(self, window):
        return next(child for child in window.winfo_children()
                    if isinstance(child, self.app.tk.Toplevel))

    def test_meta_batch_ui_selects_actives_and_allows_exclusions(self):
        window = self.make_window()
        window.meta_actions_menu.invoke(1)
        form = self.current_form(window)
        widgets = list(self.widgets(form))
        checkboxes = [widget for widget in widgets if isinstance(widget, self.app.ttk.Checkbutton)]
        self.assertEqual([box.cget('text') for box in checkboxes], ['Ana', 'Bruno'])
        self.assertTrue(all('selected' in box.state() for box in checkboxes))
        checkboxes[0].invoke()
        entries = [widget for widget in widgets if isinstance(widget, self.app.ttk.Entry)]
        entries[0].delete(0, 'end')
        entries[0].insert(0, '28/10/2026')
        entries[1].insert(0, '250,50')
        entries[2].insert(0, 'Meta lote')
        save = next(widget for widget in widgets
                    if isinstance(widget, self.app.ttk.Button) and widget.cget('text') == 'Salvar lote')
        with patch.object(self.app.messagebox, 'showinfo'):
            save.invoke()
        rows = window.meta_report_data('01/10/2026', '31/10/2026')
        self.assertEqual([(row['name'], row['amount'], row['notes']) for row in rows],
                         [('Bruno', 250.50, 'Meta lote')])

    def test_meta_batch_ui_selection_actions_and_empty_selection(self):
        window = self.make_window()
        window.add_meta_batch_dialog()
        form = self.current_form(window)
        widgets = list(self.widgets(form))
        checkboxes = [widget for widget in widgets if isinstance(widget, self.app.ttk.Checkbutton)]
        buttons = {widget.cget('text'): widget for widget in widgets
                   if isinstance(widget, self.app.ttk.Button)}
        buttons['Desmarcar todos'].invoke()
        self.assertTrue(all('selected' not in box.state() for box in checkboxes))
        entries = [widget for widget in widgets if isinstance(widget, self.app.ttk.Entry)]
        entries[1].insert(0, '100')
        with patch.object(self.app.messagebox, 'showerror') as error:
            buttons['Salvar lote'].invoke()
        self.assertIn('pelo menos um', error.call_args.args[1])
        self.assertTrue(form.winfo_exists())
        buttons['Selecionar todos'].invoke()
        self.assertTrue(all('selected' in box.state() for box in checkboxes))
        form.destroy()

    def test_inactive_employees_absent_from_all_inclusion_forms(self):
        window = self.make_window()
        for open_form in (
                lambda: window.loan_actions_menu.invoke(0),
                lambda: window.loan_actions_menu.invoke(1),
                window.add_employee_loan_dialog, window.meta_entry_dialog):
            open_form()
            form = self.current_form(window)
            boxes = [widget for widget in self.widgets(form)
                     if isinstance(widget, self.app.ttk.Combobox)]
            self.assertEqual(tuple(boxes[0]['values']), ('Ana', 'Bruno'))
            form.destroy()
        with patch.object(window, 'wait_window'):
            window.add_salary_advances_batch_dialog()
        form = self.current_form(window)
        labels = [widget.cget('text') for widget in self.widgets(form)
                  if isinstance(widget, self.app.ttk.Label)]
        self.assertIn('Ana', labels)
        self.assertIn('Bruno', labels)
        self.assertNotIn('Inativo', labels)
        form.destroy()
        with self.app.connect() as con:
            con.execute("UPDATE payrolls SET status='Em revisão'")
        window.item_dialog()
        form = self.current_form(window)
        boxes = [widget for widget in self.widgets(form)
                 if isinstance(widget, self.app.ttk.Combobox)]
        self.assertEqual(tuple(boxes[0]['values']), ('Bruno',))
        form.destroy()

    def test_deactivation_while_forms_open_blocks_new_entries(self):
        window = self.make_window()
        for open_form in (
                lambda: window.loan_actions_menu.invoke(0),
                lambda: window.loan_actions_menu.invoke(1),
                window.add_employee_loan_dialog, window.meta_entry_dialog):
            with self.app.connect() as con:
                con.execute('UPDATE employees SET active=1 WHERE id=1')
            open_form()
            form = self.current_form(window)
            widgets = list(self.widgets(form))
            entries = [widget for widget in widgets if isinstance(widget, self.app.ttk.Entry)]
            if form.title() == 'Cadastrar Meta':
                amount_entry = entries[1]
            else:
                amount_entry = entries[0]
            amount_entry.insert(0, '100')
            with self.app.connect() as con:
                con.execute('UPDATE employees SET active=0 WHERE id=1')
            save = next(widget for widget in widgets
                        if isinstance(widget, self.app.ttk.Button)
                        and widget.cget('text') in ('Salvar', 'Salvar empréstimo'))
            with patch.object(self.app.messagebox, 'showerror') as error:
                save.invoke()
            self.assertTrue(error.called)
            form.destroy()
        with self.app.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM employee_loans').fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM employee_meta_entries').fetchone()[0], 0)

    def test_inactive_meta_edit_uses_history_label_not_selection_list(self):
        entry_id = self.owner.save_meta_entry(1, '28/10/2026', '100')
        with self.app.connect() as con:
            con.execute('UPDATE employees SET active=0 WHERE id=1')
        window = self.make_window()
        window.meta_entry_dialog(entry_id)
        form = self.current_form(window)
        self.assertFalse(any(isinstance(widget, self.app.ttk.Combobox)
                             for widget in self.widgets(form)))
        self.assertTrue(any(isinstance(widget, self.app.ttk.Label)
                            and 'registro histórico' in widget.cget('text')
                            for widget in self.widgets(form)))
        form.destroy()

    def test_payroll_inclusion_rechecks_active_status_at_save(self):
        window = self.make_window()
        with self.app.connect() as con:
            con.execute("UPDATE payrolls SET status='Em revisão'")
        window.item_dialog()
        form = self.current_form(window)
        with self.app.connect() as con:
            con.execute('UPDATE employees SET active=0 WHERE id=2')
        save = next(widget for widget in self.widgets(form)
                    if isinstance(widget, self.app.ttk.Button)
                    and widget.cget('text') == 'Salvar lançamento')
        with patch.object(self.app.messagebox, 'showerror') as error:
            save.invoke()
        self.assertIn('ativo', error.call_args.args[1])
        with self.app.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM payroll_items WHERE employee_id=2').fetchone()[0], 0)
        form.destroy()

    def test_no_active_employees_blocks_meta_batch_form(self):
        window = self.make_window()
        with self.app.connect() as con:
            con.execute('UPDATE employees SET active=0')
        with patch.object(self.app.messagebox, 'showwarning') as warning:
            window.add_meta_batch_dialog()
        warning.assert_called_once()
        self.assertFalse(any(isinstance(child, self.app.tk.Toplevel)
                             for child in window.winfo_children()))


if __name__ == '__main__':
    unittest.main()
