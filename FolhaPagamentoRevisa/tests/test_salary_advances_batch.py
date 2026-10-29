import importlib.util
import os
from pathlib import Path
import tempfile
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import patch


class SalaryAdvancesBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        source = Path(__file__).resolve().parents[1] / 'folha_pagamento.py'
        spec = importlib.util.spec_from_file_location('batch_test_app', source)
        cls.app = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {'LOCALAPPDATA': cls.directory.name}):
            spec.loader.exec_module(cls.app)

    def setUp(self):
        database = tempfile.NamedTemporaryFile(
            dir=self.directory.name, suffix='.db', delete=False)
        database.close()
        self.addCleanup(os.remove, database.name)
        self.database_patch = patch.object(self.app, 'DB_PATH', database.name)
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
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
            for name, active in [('Ana', 1), ('Bruno', 1), ('Carlos', 1), ('Inativo', 0)]:
                con.execute('INSERT INTO employees(name,active) VALUES(?,?)', (name, active))
        self.owner = SimpleNamespace()
        for name in (
                'save_salary_advances_batch', 'loan_schedule_by_month', 'loan_months',
                'reconcile_loan_payroll_overrides', 'sync_loan_payrolls', 'apply_loan_installments'):
            setattr(self.owner, name, MethodType(getattr(self.app.FolhaApp, name), self.owner))

    def test_different_values_blank_zero_and_installments_across_year(self):
        result = self.owner.save_salary_advances_batch(
            [(1, '100,00'), (2, '250,01'), (3, '')], 2026, 12, 3, 'Lote teste')
        self.assertEqual(result, (2, 350.01))
        with self.app.connect() as con:
            loans = con.execute('SELECT * FROM employee_loans ORDER BY employee_id').fetchall()
            self.assertEqual(len(loans), 2)
            self.assertTrue(all(row['kind'] == self.app.ADVANCE_KIND for row in loans))
            self.assertTrue(all(row['notes'] == 'Lote teste' for row in loans))
            items = con.execute('''SELECT employee_id,SUM(advances) amount FROM payroll_items
                GROUP BY employee_id ORDER BY employee_id''').fetchall()
            self.assertAlmostEqual(items[0]['amount'], 100)
            self.assertAlmostEqual(items[1]['amount'], 250.01)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0], 2)
        self.assertEqual(
            self.owner.save_salary_advances_batch([(1, '0'), (2, '10')], 2027, 3, 1),
            (1, 10))

    def test_invalid_rows_leave_no_partial_batch(self):
        for value in ('inválido', '-10', 'nan', 'inf', '0,001'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.owner.save_salary_advances_batch([(1, '100'), (2, value)], 2026, 11, 2)
        with self.app.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM employee_loans').fetchone()[0], 0)

    def test_closed_payroll_in_schedule_blocks_whole_batch(self):
        with self.app.connect() as con:
            con.execute("INSERT INTO payrolls(year,month,status) VALUES(2027,1,'Fechada')")
        with self.assertRaisesRegex(ValueError, 'fechada'):
            self.owner.save_salary_advances_batch([(1, '100'), (2, '200')], 2026, 12, 2)
        with self.app.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM employee_loans').fetchone()[0], 0)

    def test_sync_failure_rolls_back_contracts_audit_and_payroll(self):
        with patch.object(self.owner, 'sync_loan_payrolls', side_effect=RuntimeError('sync')):
            with self.assertRaises(RuntimeError):
                self.owner.save_salary_advances_batch([(1, '100'), (2, '200')], 2026, 11, 2)
        with self.app.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM employee_loans').fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0], 0)

    def test_invalid_employee_period_count_or_empty_batch(self):
        cases = [
            ([(4, '100')], 2026, 11, 1),
            ([(999, '100')], 2026, 11, 1),
            ([(1, '100'), (1, '200')], 2026, 11, 1),
            ([(1, '')], 2026, 11, 1),
            ([(1, '100')], 2026, 0, 1),
            ([(1, '100')], 2026, 11, 601),
            ([(1, '100')], 9999, 12, 2),
        ]
        for entries, year, month, count in cases:
            with self.subTest(case=(entries, year, month, count)), self.assertRaises(ValueError):
                self.owner.save_salary_advances_batch(entries, year, month, count)

    def test_existing_manual_discount_salary_and_other_values_preserved(self):
        self.owner.save_salary_advances_batch([(1, '100')], 2026, 11, 1)
        with self.app.connect() as con:
            con.execute('''UPDATE payroll_items SET salary=3000,pf=100,pharmacy=20,
                advances_override=125 WHERE employee_id=1''')
        self.owner.save_salary_advances_batch([(1, '50')], 2026, 11, 1)
        with self.app.connect() as con:
            item = con.execute('SELECT * FROM payroll_items WHERE employee_id=1').fetchone()
            self.assertEqual(item['salary'], 3000)
            self.assertEqual(item['pf'], 100)
            self.assertEqual(item['pharmacy'], 20)
            self.assertEqual(item['advances_override'], 175)
            self.assertEqual(item['advances'], 175)
            self.assertEqual(item['total'], 2905)

    def test_register_menu_has_separate_actions_and_correct_contract_types(self):
        window = self.app.FolhaApp.__new__(self.app.FolhaApp)
        self.app.tk.Tk.__init__(window)
        window.withdraw()
        self.addCleanup(window.destroy)
        window.loans_tab = self.app.ttk.Frame(window)
        window.pay_year = SimpleNamespace(get=lambda: '2026')
        window.pay_month = SimpleNamespace(get=lambda: self.app.MONTHS[10])
        window._build_loans()
        menu = window.loan_actions_menu
        labels = [
            menu.entrycget(index, 'label')
            for index in range(menu.index('end') + 1)
            if menu.type(index) != 'separator'
        ]
        self.assertEqual(labels, [
            'Cadastrar empréstimo', 'Cadastrar adiantamento',
            'Cadastrar adiantamento em lote', 'Editar', 'Excluir', 'Quitar saldo'])
        for index, kind in ((0, self.app.LOAN_KIND), (1, self.app.ADVANCE_KIND)):
            menu.invoke(index)
            form = next(
                child for child in window.winfo_children()
                if isinstance(child, self.app.tk.Toplevel))
            self.assertEqual(form.title(), f'Cadastrar {kind.lower()}')
            fields = next(iter(form.winfo_children()))
            type_box = next(
                child for child in fields.winfo_children()
                if isinstance(child, self.app.ttk.Combobox)
                and tuple(child['values']) == self.app.LOAN_KINDS)
            self.assertEqual(type_box.get(), kind)
            form.destroy()

    def test_advance_filter_and_amounts_follow_closed_payroll_payments(self):
        self.owner.save_salary_advances_batch(
            [(1, '100'), (2, '100'), (3, '100')], 2026, 9, 1)
        self.owner.save_salary_advances_batch([(1, '50')], 2026, 11, 1)
        with self.app.connect() as con:
            con.execute('UPDATE payroll_items SET advances=40 WHERE employee_id=2')
            con.execute('UPDATE payroll_items SET advances=0 WHERE employee_id=3')
        window = self.app.FolhaApp.__new__(self.app.FolhaApp)
        self.app.tk.Tk.__init__(window)
        window.withdraw()
        self.addCleanup(window.destroy)
        window.loans_tab = self.app.ttk.Frame(window)
        window.pay_year = SimpleNamespace(get=lambda: '2026')
        selected_month = [8]
        window.pay_month = SimpleNamespace(
            get=lambda: self.app.MONTHS[selected_month[0]])
        window._build_loans()
        window.refresh_loans()
        advances = window.loan_trees['advances']
        self.assertEqual(tuple(window.advance_filter['values']), ('Pendentes', 'Quitados'))
        self.assertEqual(window.advance_filter.get(), 'Pendentes')
        self.assertEqual(len(advances.get_children()), 3)
        self.assertEqual(advances.set('1', 'paid'), self.app.brl(0))
        with self.app.connect() as con:
            con.execute("UPDATE payrolls SET status='Fechada' WHERE year=2026 AND month=9")
        window.refresh_loans()
        self.assertEqual(set(advances.get_children()), {'2', '3'})
        self.assertEqual(advances.set('2', 'status'), 'Parcial')
        self.assertEqual(advances.set('3', 'status'), 'Pendente')
        self.assertEqual(advances.set('2', 'paid'), self.app.brl(40))
        self.assertEqual(advances.set('2', 'principal'), self.app.brl(60))
        self.assertEqual(advances.set('3', 'principal'), self.app.brl(100))
        window.advance_filter.set('Pendentes')
        window.advance_filter.event_generate('<<ComboboxSelected>>')
        window.update()
        self.assertEqual(set(advances.get_children()), {'2', '3'})
        window.advance_filter.set('Quitados')
        window.advance_filter.event_generate('<<ComboboxSelected>>')
        window.update()
        self.assertEqual(advances.get_children(), ('1',))
        self.assertEqual(advances.set('1', 'status'), 'Quitado')
        window.loan_notebook.select(1)
        window.update()
        self.assertIs(window.loans_tree, window.loan_trees['loans'])
        window.loan_notebook.select(0)
        window.update()
        self.assertIs(window.loans_tree, advances)
        with self.app.connect() as con:
            con.execute("UPDATE payrolls SET status='Em revisão' WHERE year=2026 AND month=9")
        window.refresh_loans()
        self.assertEqual(advances.get_children(), ())
        window.advance_filter.set('Pendentes')
        window.refresh_loans()
        self.assertEqual(len(advances.get_children()), 3)
        selected_month[0] = 10
        window.refresh_loans()
        self.assertEqual(advances.get_children(), ('4',))
        self.assertIn('Novembro/2026', window.loan_period_label.cget('text'))


if __name__ == '__main__':
    unittest.main()
