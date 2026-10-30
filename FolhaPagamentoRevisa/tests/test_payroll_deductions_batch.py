import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))
SPEC = importlib.util.spec_from_file_location(
    "payroll_deductions_batch_app", MODULE_DIR / "folha_pagamento.py")
APP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APP)


class PayrollDeductionsBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.connection = sqlite3.connect(
            str(Path(self.temp_dir.name) / "payroll.db"))
        self.connection.row_factory = sqlite3.Row
        self.addCleanup(self.connection.close)
        self.connection.executescript("""
            CREATE TABLE employees (
                id INTEGER PRIMARY KEY, name TEXT, active INTEGER,
                admission_date TEXT, dismissal_date TEXT, inactive_since TEXT
            );
            CREATE TABLE employee_salary_history (
                employee_id INTEGER, salary REAL, effective_year INTEGER,
                effective_month INTEGER
            );
            CREATE TABLE annual_employees (
                employee_id INTEGER, year INTEGER, salary_base REAL
            );
            CREATE TABLE payrolls (
                id INTEGER PRIMARY KEY, year INTEGER, month INTEGER, status TEXT,
                notes TEXT DEFAULT '', loan_only INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE payroll_items (
                id INTEGER PRIMARY KEY, payroll_id INTEGER, employee_id INTEGER,
                salary REAL DEFAULT 0, pf REAL DEFAULT 0, overtime REAL DEFAULT 0,
                vacation REAL DEFAULT 0, meta REAL DEFAULT 0, thirteenth REAL DEFAULT 0,
                marmitex REAL DEFAULT 0, advances REAL DEFAULT 0, pharmacy REAL DEFAULT 0,
                other_deductions REAL DEFAULT 0, loan REAL DEFAULT 0, total REAL DEFAULT 0,
                source TEXT DEFAULT '', notes TEXT DEFAULT ''
            );
            CREATE TABLE audit_log (action TEXT, details TEXT);
            INSERT INTO employees(id,name,active) VALUES
                (1,'Ana',1),(2,'Bruna',1);
            INSERT INTO payrolls(id,year,month,status) VALUES
                (1,2026,10,'Em revisão');
            INSERT INTO payroll_items(
                id,payroll_id,employee_id,salary,marmitex,advances,pharmacy,
                other_deductions,loan,total,notes
            ) VALUES
                (1,1,1,1000,100,20,50,30,10,790,'manter observação'),
                (2,1,2,2000,0,0,0,0,0,2000,'');
        """)
        self.app = object.__new__(APP.FolhaBase)

    def save(self, entries):
        with patch.object(APP, "connect", return_value=self.connection), \
                patch.object(APP.FolhaBase, "apply_loan_installments", lambda *args: None):
            return self.app.save_payroll_deductions_batch(2026, 10, entries)

    def test_updates_multiple_employees_and_preserves_blank_fields(self):
        result = self.save([(1, "120,00", ""), (2, "", "45,50")])

        self.assertEqual(result, (2, 120.0, 45.5))
        first = self.connection.execute(
            "SELECT * FROM payroll_items WHERE employee_id=1").fetchone()
        second = self.connection.execute(
            "SELECT * FROM payroll_items WHERE employee_id=2").fetchone()
        self.assertEqual((first["marmitex"], first["pharmacy"], first["total"]),
                         (120, 50, 770))
        self.assertEqual(first["notes"], "manter observação")
        self.assertEqual((second["marmitex"], second["pharmacy"], second["total"]),
                         (0, 45.5, 1954.5))
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0], 2)

    def test_zero_clears_value_and_blank_only_batch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Informe Marmitex ou Farmácia"):
            self.save([(1, "", "")])

        self.save([(1, "0", "")])
        row = self.connection.execute(
            "SELECT marmitex,pharmacy,total FROM payroll_items WHERE employee_id=1").fetchone()
        self.assertEqual(tuple(row), (0, 50, 890))

    def test_rejects_negative_amount_and_closed_payroll(self):
        with self.assertRaisesRegex(ValueError, "não pode ser negativo"):
            self.save([(1, "-1", "")])

        self.connection.execute(
            "UPDATE payrolls SET status='Fechada' WHERE id=1")
        with self.assertRaisesRegex(ValueError, "está fechada"):
            self.save([(1, "10", "")])

    def test_promotes_loan_only_payroll_and_syncs_active_employees(self):
        self.connection.execute(
            "UPDATE payrolls SET loan_only=1 WHERE id=1")
        self.connection.execute(
            "DELETE FROM payroll_items WHERE employee_id=2")
        self.connection.execute(
            "INSERT INTO employee_salary_history VALUES (2,2000,2026,1)")

        self.save([(1, "110", "")])

        payroll = self.connection.execute(
            "SELECT loan_only FROM payrolls WHERE id=1").fetchone()
        second = self.connection.execute(
            "SELECT salary FROM payroll_items WHERE employee_id=2").fetchone()
        self.assertEqual(payroll["loan_only"], 0)
        self.assertEqual(second["salary"], 2000)

    def test_creates_payroll_for_selected_month_when_missing(self):
        self.connection.execute("DELETE FROM payroll_items")
        self.connection.execute("DELETE FROM payrolls")
        self.connection.execute(
            "INSERT INTO employee_salary_history VALUES (1,1000,2026,1)")
        self.connection.execute(
            "INSERT INTO employee_salary_history VALUES (2,2000,2026,1)")

        self.save([(1, "", "25")])

        payroll = self.connection.execute(
            "SELECT id,loan_only FROM payrolls WHERE year=2026 AND month=10").fetchone()
        items = self.connection.execute(
            "SELECT employee_id,salary,pharmacy FROM payroll_items WHERE payroll_id=? ORDER BY employee_id",
            (payroll["id"],)).fetchall()
        self.assertEqual(payroll["loan_only"], 0)
        self.assertEqual([tuple(row) for row in items], [(1,1000,25),(2,2000,0)])


if __name__ == "__main__":
    unittest.main()
