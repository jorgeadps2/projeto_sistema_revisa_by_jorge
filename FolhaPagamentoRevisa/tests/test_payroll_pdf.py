import importlib.util
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader


MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))
SPEC = importlib.util.spec_from_file_location(
    "payroll_pdf_app", MODULE_DIR / "folha_pagamento.py")
APP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APP)


class PayrollPdfTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "payroll.pdf"
        self.app = object.__new__(APP.FolhaBase)

    def row(self, name="Ana", notes=None):
        return dict(
            name=name, notes=notes, salary=1000, pf=100, overtime=20,
            vacation=30, meta=50, thirteenth=500, marmitex=10,
            advances=20, pharmacy=30, loan=40, other_deductions=50,
            total=1050, loan_installment="2 / 10")

    def generate(self, rows, month=10):
        story = []
        original_build = APP.SimpleDocTemplate.build

        def build(document, flowables, **kwargs):
            story.extend(deepcopy(flowables))
            return original_build(document, flowables, **kwargs)

        with patch.object(APP.FolhaBase, "payroll_report_rows",
                          return_value=({"status": "Fechada"}, rows)), \
                patch.object(APP.SimpleDocTemplate, "build", build):
            total = self.app.write_payroll_pdf(2026, month, str(self.path))
        reader = PdfReader(self.path)
        text = "\n".join(page.extract_text() for page in reader.pages)
        table = next(item for item in story if isinstance(item, APP.LongTable))
        return total, story, table, text, reader

    def test_credit_and_debit_colors_with_and_without_thirteenth(self):
        for month, earnings_count in ((10, 5), (11, 6), (12, 6)):
            with self.subTest(month=month):
                total, story, table, text, reader = self.generate([self.row()], month)
                self.assertEqual(total, 1050)
                green = APP.colors.HexColor("#15803d")
                red = APP.colors.HexColor("#b91c1c")
                for column in range(1, earnings_count + 1):
                    self.assertEqual(table._cellStyles[1][column].color, green)
                for column in range(earnings_count + 1, len(table._cellvalues[1]) - 1):
                    self.assertEqual(table._cellStyles[1][column].color, red)
                installment = table._cellvalues[1][-3]
                self.assertEqual(installment.style.textColor, red)
                self.assertEqual(table._cellStyles[1][-1].color, green)
                summary = next(item for item in story if type(item) is APP.Table)
                self.assertEqual(summary._cellvalues[0][0].style.textColor, green)
                self.assertEqual(summary._cellvalues[0][1].style.textColor, red)
                reference_style = summary._cellvalues[0][0].style
                self.assertEqual(reference_style.fontSize, table._cellStyles[1][1].fontsize)
                for summary_row in summary._cellvalues:
                    for cell in summary_row:
                        self.assertEqual(cell.style.fontSize, reference_style.fontSize)
                        self.assertEqual(cell.style.leading, reference_style.leading)
                        self.assertEqual(cell.style.fontName, reference_style.fontName)
                self.assertIn("1.050,00", text)
                self.assertNotIn("em verde", text)
                self.assertNotIn("em vermelho", text)
                self.assertIn("Crédito", text)
                self.assertIn("Débito", text)
                legend = story[0]
                self.assertEqual(legend.style.name, "PayrollLegend")
                self.assertEqual(legend.style.alignment, 0)
                markers = [fragment for fragment in legend.frags
                           if fragment.text == "\u2022"]
                self.assertEqual([marker.textColor for marker in markers],
                                 [green, red])
                self.assertEqual([marker.fontSize for marker in markers], [20, 20])
                self.assertLess(text.index("Crédito"), text.index("Folha a pagar"))
                self.assertTrue(reader.pages[0].get_contents().get_data())

    def test_compact_rows_preserve_font_size_and_reduce_height(self):
        _, _, table, _, _ = self.generate([self.row()])
        for row in table._cellStyles:
            for cell in row:
                self.assertEqual(cell.topPadding, 1.5)
                self.assertEqual(cell.bottomPadding, 1.5)
        self.assertEqual(table._cellStyles[1][1].fontsize, APP._scaled_font(6))
        original_spacing = deepcopy(table)
        original_spacing.setStyle(APP.TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        _, compact_height = table.wrap(800, 500)
        _, previous_height = original_spacing.wrap(800, 500)
        self.assertAlmostEqual(previous_height - compact_height, 6)

    def test_notes_are_escaped_multiline_and_marked_in_table_and_section(self):
        rows = [self.row("Ana & Cia", "Conferir <saldo> & ajuste\nSegunda linha"),
                self.row("Bruna", "   ")]
        total, story, table, text, _ = self.generate(rows)
        self.assertEqual(total, 2100)
        self.assertIn("Observações dos colaboradores", text)
        self.assertIn("Conferir <saldo> & ajuste", text)
        self.assertIn("Segunda linha", text)
        self.assertEqual(text.count("Ana & Cia"), 2)
        self.assertEqual(text.count("Bruna"), 1)
        self.assertIn("&#8226;", table._cellvalues[1][0].text)
        self.assertNotIn("&#8226;", table._cellvalues[2][0].text)
        observation = next(item for item in story
                           if isinstance(item, APP.Paragraph)
                           and "Conferir" in item.text)
        self.assertIn("<br/>Segunda linha", observation.text)
        markers = [fragment for fragment in observation.frags
                   if fragment.text == "\u2022"]
        self.assertTrue(markers)
        self.assertEqual(markers[0].textColor, APP.colors.HexColor("#dc2626"))
        name_fragment = next(fragment for fragment in observation.frags
                             if "Ana" in fragment.text)
        note_fragments = [fragment for fragment in observation.frags
                          if "Conferir" in fragment.text or "Segunda linha" in fragment.text]
        self.assertEqual(len(note_fragments), 2)
        self.assertEqual(name_fragment.fontSize, 7)
        for fragment in note_fragments:
            self.assertEqual(fragment.fontSize, 15)

    def test_no_notes_and_empty_payroll_do_not_add_observation_section(self):
        for rows in ([self.row(notes=None)], []):
            with self.subTest(rows=len(rows)):
                _, _, _, text, _ = self.generate(rows)
                self.assertNotIn("Observações dos colaboradores", text)

    def test_long_observations_and_many_employees_span_pages(self):
        rows = [self.row(f"Colaborador {index}", "Observacao extensa. " * 400)
                for index in range(45)]
        total, _, _, text, reader = self.generate(rows)
        self.assertEqual(total, 45 * 1050)
        self.assertGreater(len(reader.pages), 2)
        self.assertEqual(text.count("Colaborador 44"), 2)
        self.assertIn("Observacao extensa.", text)


if __name__ == "__main__":
    unittest.main()
