import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pypdf import PdfReader


class CurrentSalariesReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        source = Path(__file__).resolve().parents[1] / 'folha_pagamento.py'
        spec = importlib.util.spec_from_file_location('current_salaries_app', source)
        cls.app = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {'LOCALAPPDATA': cls.directory.name}):
            spec.loader.exec_module(cls.app)

    def test_report_contains_only_current_salary_for_active_employees(self):
        database = tempfile.NamedTemporaryFile(
            dir=self.directory.name, suffix='.db', delete=False)
        database.close()
        self.addCleanup(os.remove, database.name)
        with patch.object(self.app, 'DB_PATH', database.name):
            original_connect = self.app.connect
            connections = []

            def connect():
                connection = original_connect()
                connections.append(connection)
                return connection

            connection_patch = patch.object(
                self.app,'connect',side_effect=connect)
            connection_patch.start()
            self.addCleanup(connection_patch.stop)
            self.addCleanup(
                lambda: [connection.close() for connection in connections])
            self.app.init_db()
            with self.app.connect() as con:
                employee_id = con.execute(
                    'INSERT INTO employees(name,active) VALUES(?,1)',
                    ('Colaboradora ativa',),
                ).lastrowid
                con.execute(
                    'INSERT INTO employees(name,active) VALUES(?,0)',
                    ('Colaborador inativo',),
                )
                con.execute('''INSERT INTO employee_salary_history(
                    employee_id,salary,old_salary,effective_year,effective_month)
                    VALUES(?,?,?,?,?)''',
                    (employee_id,1800,1200,2025,1))
                con.execute('''INSERT INTO employee_salary_history(
                    employee_id,salary,old_salary,effective_year,effective_month)
                    VALUES(?,?,?,?,?)''',
                    (employee_id,2000,1800,9999,12))
                con.execute('''INSERT INTO employee_previous_salary_controls(
                    employee_id,amount) VALUES(?,?)''',(employee_id,1200))
                con.execute('''INSERT INTO employee_salary_register_updates(
                    employee_id,updated_on,amount,kind) VALUES(?,?,?,?)''',
                    (employee_id,'2025-01-01',1800,'dissidio'))

            path = str(Path(self.directory.name) / 'current_salaries.pdf')
            owner = SimpleNamespace(pdf_page_header=MagicMock())
            result = self.app.FolhaApp.write_current_salaries_report(
                owner,path)

        text = '\n'.join(page.extract_text() for page in PdfReader(path).pages)
        self.assertEqual(result,1)
        self.assertIn('Colaboradora ativa',text)
        self.assertIn('Salário atualizado',text)
        self.assertIn('1.800,00',text)
        self.assertNotIn('1.200,00',text)
        self.assertNotIn('2.000,00',text)
        self.assertNotIn('Colaborador inativo',text)
        self.assertNotIn('Salário anterior',text)
        self.assertNotIn('Dissídio',text)


if __name__ == '__main__':
    unittest.main()
