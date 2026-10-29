import importlib.util
import os
from contextlib import ExitStack, closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pypdf import PdfReader


class EmployeeBankDetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        source = Path(__file__).resolve().parents[1] / 'folha_pagamento.py'
        spec = importlib.util.spec_from_file_location('employee_bank_details_app', source)
        cls.app = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {'LOCALAPPDATA': cls.directory.name}):
            spec.loader.exec_module(cls.app)

    def test_migration_preserves_bank_fields_in_employee_report(self):
        database_path = str(Path(self.directory.name) / 'legacy_employee.db')
        with sqlite3.connect(database_path) as con:
            con.execute('''CREATE TABLE employees(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                email TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                pix TEXT DEFAULT '',
                role TEXT DEFAULT '',
                sector TEXT DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
            con.execute(
                'INSERT INTO employees(name) VALUES(?)',('Colaboradora teste',))

        connect = self.app.connect
        with ExitStack() as stack, \
                patch.object(self.app,'DB_PATH',database_path), \
                patch.object(self.app,'connect',side_effect=lambda:
                    stack.enter_context(closing(connect()))):
            self.app.init_db()
            con=self.app.connect()
            try:
                columns={
                    row['name'] for row in con.execute(
                        'PRAGMA table_info(employees)').fetchall()
                }
                self.assertTrue({'bank','bank_agency','bank_account'} <= columns)
                con.execute('''UPDATE employees
                    SET bank=?,bank_agency=?,bank_account=? WHERE name=?''',
                    ('Banco Exemplo','0123','45678-9','Colaboradora teste'))
                con.commit()
            finally:
                con.close()

            path = str(Path(self.directory.name) / 'employee_report.pdf')
            owner = SimpleNamespace(pdf_page_header=MagicMock())
            self.app.FolhaApp.write_employee_report_pdf(owner,path)

        text = '\n'.join(page.extract_text() for page in PdfReader(path).pages)
        self.assertIn('Banco Exemplo',text)
        self.assertIn('0123',text)
        self.assertIn('45678-9',text)

    def test_employee_lists_show_bank_details_for_active_and_inactive(self):
        owner = MagicMock()
        owner._tab_action_layout.return_value = (MagicMock(),MagicMock())
        with patch.multiple(
                self.app.ttk,Frame=MagicMock(),Label=MagicMock(),
                Button=MagicMock(),Menubutton=MagicMock(),Notebook=MagicMock()), \
                patch.object(self.app.tk,'Menu'):
            self.app.FolhaApp._build_employees(owner)

        columns = owner._create_employee_tree.call_args_list[0].args[1]
        headings = owner._create_employee_tree.call_args_list[0].args[2]
        self.assertEqual(tuple(column for column,_,_ in headings),columns)
        for column,title in (
                ('bank','Banco'),('bank_agency','Agência'),
                ('bank_account','Conta')):
            self.assertIn(column,columns)
            self.assertIn(title,[heading for _,heading,_ in headings])
        self.assertEqual(
            owner._create_employee_tree.call_args_list[1].args[1],columns)

        database_path = str(Path(self.directory.name) / 'employee_lists.db')
        sqlite3.connect(database_path).close()
        connect = self.app.connect
        with ExitStack() as stack, \
                patch.object(self.app,'DB_PATH',database_path), \
                patch.object(self.app,'connect',side_effect=lambda:
                    stack.enter_context(closing(connect()))):
            self.app.init_db()
            with self.app.connect() as con:
                for name,active,bank,agency,account in (
                        ('Ativa',1,'Banco A','0012','000345-6'),
                        ('Inativa',0,'Banco B','0034','000789-0'),
                        ('Sem banco',1,'','','')):
                    con.execute('''INSERT INTO employees(
                        name,active,bank,bank_agency,bank_account)
                        VALUES(?,?,?,?,?)''',(name,active,bank,agency,account))
            owner.emp_tree = MagicMock()
            owner.inactive_emp_tree = MagicMock()
            self.app.FolhaApp.load_employees(owner)

        for tree,expected in (
                (owner.emp_tree,[
                    ('Ativa','Banco A','0012','000345-6','Ativo'),
                    ('Sem banco','','','','Ativo')]),
                (owner.inactive_emp_tree,[
                    ('Inativa','Banco B','0034','000789-0','Inativo')])):
            actual = []
            for call in tree.insert.call_args_list:
                values = call.kwargs['values']
                self.assertEqual(len(values),len(columns))
                row = dict(zip(columns,values))
                actual.append(tuple(row[key] for key in (
                    'name','bank','bank_agency','bank_account','active')))
            self.assertEqual(actual,expected)


if __name__ == '__main__':
    unittest.main()
