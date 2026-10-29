import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch


class PayrollObservationMarkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        source = Path(__file__).resolve().parents[1] / 'folha_pagamento.py'
        spec = importlib.util.spec_from_file_location('payroll_marker_app', source)
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
            self.payroll_id = con.execute(
                'INSERT INTO payrolls(year,month) VALUES(2026,10)').lastrowid
            self.item_id = con.execute('''INSERT INTO payroll_items(
                payroll_id,employee_id,salary,total,notes) VALUES(?,1,3000,3000,'')''',
                (self.payroll_id,)).lastrowid
        self.window = self.app.FolhaApp.__new__(self.app.FolhaApp)
        self.app.tk.Tk.__init__(self.window)
        self.window.withdraw()
        self.addCleanup(self.window.destroy)
        self.window.current_payroll_year = 2026
        self.window.current_payroll_month = 10
        self.window.payroll_tab = self.app.ttk.Frame(self.window)
        self.window.load_dashboard = Mock()
        self.window._build_payroll()

    def test_marker_and_colors_follow_notes_in_open_and_closed_payrolls(self):
        for status, base_tag in (
                ('Em revisão', 'launch_partial'), ('Fechada', 'launch_full')):
            for note in ('Conferir férias\nSegunda linha', '', ' \n\t ', None):
                has_note = bool(note and note.strip())
                with self.subTest(status=status, note=note):
                    with self.app.connect() as con:
                        con.execute("UPDATE payrolls SET status='Em revisão' WHERE id=?",
                                    (self.payroll_id,))
                        con.execute('UPDATE payroll_items SET notes=? WHERE id=?',
                                    (note, self.item_id))
                        con.execute('UPDATE payrolls SET status=? WHERE id=?',
                                    (status, self.payroll_id))
                    self.window.load_payroll()
                    tree = self.window.pay_tree
                    self.assertEqual(tree.set(str(self.item_id), 'name'), 'Ana')
                    self.assertEqual(tree.set(str(self.item_id), 'note_marker'),
                                     '●' if has_note else '')
                    self.assertEqual(tree.item(str(self.item_id), 'tags'),
                                     (base_tag + ('_note' if has_note else ''),))
                    self.assertEqual(tree.set(str(self.item_id), 'total'), 'R$ 3.000,00')
                    tree.selection_set(str(self.item_id))
                    self.assertEqual(self.window.selected_item(), self.item_id)
                    self.assertIn('● vermelha', self.window.pay_note.cget('text'))
                    observations = self.window.payroll_observations.get('1.0', 'end-1c')
                    self.assertNotIn('[OBS]', observations)
                    if has_note:
                        self.assertTrue(observations.startswith('● Ana\n'))
                        self.assertIn('employee_marker',
                                      self.window.payroll_observations.tag_names('1.0'))
                        self.assertNotIn('employee_marker',
                                         self.window.payroll_observations.tag_names('1.2'))
                    else:
                        self.assertNotIn('●', observations)
                    self.assertIn(note.strip() if has_note else
                                  'Nenhuma observação de colaborador nesta folha.',
                                  observations)
                    self.assertEqual(str(self.window.payroll_edit_buttons[0]['state']),
                                     'disabled' if status == 'Fechada' else 'normal')
                    with self.app.connect() as con:
                        self.assertEqual(con.execute(
                            'SELECT name FROM employees WHERE id=1').fetchone()[0], 'Ana')

    def test_saving_and_removing_observation_refreshes_marker(self):
        self.window.load_payroll()
        for note, expected_marker in (
                ('Conferir pagamento', '●'), ('', '')):
            self.window.pay_tree.selection_set(str(self.item_id))
            self.window.edit_selected_item()
            form = next(child for child in self.window.winfo_children()
                        if isinstance(child, self.app.tk.Toplevel))
            body = form.winfo_children()[0]
            note_frame = next(child for child in body.winfo_children()
                              if any(isinstance(widget, self.app.tk.Text)
                                     for widget in child.winfo_children()))
            text = next(child for child in note_frame.winfo_children()
                        if isinstance(child, self.app.tk.Text))
            text.delete('1.0', 'end')
            text.insert('1.0', note)
            buttons = next(child for child in body.winfo_children()
                           if any(isinstance(widget, self.app.ttk.Button)
                                  and widget.cget('text') == 'Salvar lançamento'
                                  for widget in child.winfo_children()))
            next(button for button in buttons.winfo_children()
                 if button.cget('text') == 'Salvar lançamento').invoke()
            self.assertFalse(form.winfo_exists())
            self.assertEqual(self.window.pay_tree.set(str(self.item_id), 'name'),
                             'Ana')
            self.assertEqual(self.window.pay_tree.set(str(self.item_id), 'note_marker'),
                             expected_marker)
            with self.app.connect() as con:
                self.assertEqual(con.execute(
                    'SELECT notes FROM payroll_items WHERE id=?',
                    (self.item_id,)).fetchone()[0], note)

    def test_marker_is_scoped_to_selected_month_and_survives_reload(self):
        with self.app.connect() as con:
            con.execute('UPDATE payroll_items SET notes=? WHERE id=?',
                        ('Somente outubro', self.item_id))
            con.execute('INSERT INTO payrolls(year,month) VALUES(2026,11)')
        self.window.load_payroll()
        self.assertEqual(self.window.pay_tree.set(str(self.item_id), 'note_marker'), '●')
        self.window.pay_month.set(self.app.MONTHS[10])
        self.window.load_payroll()
        for item in self.window.pay_tree.get_children():
            self.assertEqual(self.window.pay_tree.set(item, 'name'), 'Ana')
            self.assertEqual(self.window.pay_tree.set(item, 'note_marker'), '')
        self.window.pay_month.set(self.app.MONTHS[9])
        self.window.load_payroll()
        self.assertEqual(self.window.pay_tree.set(str(self.item_id), 'note_marker'), '●')

    def test_marker_is_right_aligned_and_only_background_changes(self):
        self.window.load_payroll()
        tree = self.window.pay_tree
        columns = tuple(tree['columns'])
        self.assertEqual(columns[:3], ('name', 'note_marker', 'salary'))
        self.assertEqual(tree.heading('note_marker', 'text'), '')
        self.assertEqual(str(tree.column('note_marker', 'anchor')), 'e')
        self.assertEqual(tree.column('note_marker', 'width'), 26)
        self.assertFalse(tree.column('note_marker', 'stretch'))
        for tag, background in (
                ('launch_full', '#e6f6ec'), ('launch_partial', '#fdf6d0'),
                ('launch_full_note', '#ffedd5'), ('launch_partial_note', '#ffedd5')):
            self.assertEqual(str(tree.tag_configure(tag, 'foreground')), '#000000')
            self.assertEqual(str(tree.tag_configure(tag, 'background')), background)
        style = self.app.ttk.Style(tree)
        self.assertEqual(str(style.lookup(tree['style'], 'foreground')), '#000000')
        self.assertEqual(str(style.lookup(tree['style'], 'foreground', ('selected',))),
                         '#000000')
        for tag in ('employee_name', 'employee_note'):
            self.assertEqual(
                self.window.payroll_observations.tag_cget(tag, 'foreground'), '#000000')
        self.assertEqual(
            self.window.payroll_observations.tag_cget('employee_marker', 'foreground'),
            '#dc2626')

    def test_red_marker_tracks_selection_scrolling_and_removal(self):
        window = self.window
        window.geometry('1000x700+20+20')
        window.payroll_tab.pack(fill='both', expand=True)
        window.deiconify()
        with self.app.connect() as con:
            con.execute('UPDATE payroll_items SET notes=? WHERE id=?',
                        ('Conferir pagamento', self.item_id))
        window.load_payroll()
        window.update()
        item = str(self.item_id)
        label = window.payroll_note_markers[item]
        self.assertEqual(label.cget('text'), '●')
        self.assertEqual(str(label.cget('fg')), '#dc2626')
        self.assertEqual(str(label.cget('bg')), '#ffedd5')
        x, y, width, height = window.pay_tree.bbox(item, 'note_marker')
        self.assertEqual(label.winfo_x(), x)
        self.assertEqual(label.winfo_y(), y)
        self.assertEqual(label.winfo_width(), width - 4)
        label.event_generate('<Button-1>')
        window.update()
        self.assertEqual(window.selected_item(), self.item_id)
        self.assertEqual(str(label.cget('fg')), '#dc2626')
        style = self.app.ttk.Style(window.pay_tree)
        self.assertEqual(str(label.cget('bg')), str(style.lookup(
            window.pay_tree['style'], 'background', ('selected',))))
        with patch.object(window, 'edit_selected_item') as edit:
            window._select_payroll_note_marker(item, edit=True)
            edit.assert_called_once_with()
        window.pay_tree.xview_moveto(1)
        window.update()
        self.assertNotIn(item, window.payroll_note_markers)
        window.pay_tree.xview_moveto(0)
        window.update()
        self.assertEqual(str(window.payroll_note_markers[item].cget('fg')), '#dc2626')
        with self.app.connect() as con:
            con.execute('UPDATE payrolls SET status=? WHERE id=?',
                        ('Fechada', self.payroll_id))
        window.load_payroll()
        window.update()
        self.assertEqual(str(window.payroll_note_markers[item].cget('fg')), '#dc2626')
        with self.app.connect() as con:
            con.execute("UPDATE payrolls SET status='Em revisão' WHERE id=?",
                        (self.payroll_id,))
            con.execute("UPDATE payroll_items SET notes='' WHERE id=?", (self.item_id,))
        window.load_payroll()
        window.update()
        self.assertNotIn(item, window.payroll_note_markers)


if __name__ == '__main__':
    unittest.main()
