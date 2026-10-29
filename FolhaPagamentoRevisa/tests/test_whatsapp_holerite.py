import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from contextlib import ExitStack
from urllib.parse import parse_qs, urlparse


class WhatsAppHoleriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        source = Path(__file__).resolve().parents[1] / 'folha_pagamento.py'
        spec = importlib.util.spec_from_file_location('whatsapp_holerite_app', source)
        cls.app = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {'LOCALAPPDATA': cls.directory.name}):
            spec.loader.exec_module(cls.app)

    def test_chat_url_includes_brazilian_phone_and_encoded_message(self):
        url = self.app.whatsapp_chat_url(
            '(11) 99999-1234', 'João & Maria', 2026, 10)

        parsed = urlparse(url)
        self.assertEqual(parsed.scheme, 'whatsapp')
        self.assertEqual(parsed.netloc, 'send')
        self.assertEqual(parse_qs(parsed.query)['phone'], ['5511999991234'])
        self.assertEqual(
            parse_qs(parsed.query)['text'][0],
            'Segue seu Holerite Adminstrativo')

    def test_chat_url_accepts_phone_with_country_code(self):
        url = self.app.whatsapp_chat_url(
            '+55 (11) 99999-1234', 'João', 2026, 1)

        self.assertEqual(parse_qs(urlparse(url).query)['phone'], ['5511999991234'])

    def test_chat_url_rejects_invalid_phone(self):
        with self.assertRaises(ValueError):
            self.app.whatsapp_chat_url('1234', 'João', 2026, 1)

    def test_pdf_dialog_generates_all_or_chosen_employee(self):
        for index,expected in ((0,None),(2,8)):
            with self.subTest(index=index), ExitStack() as stack:
                con=MagicMock()
                con.__enter__.return_value=con
                con.execute.return_value.fetchall.return_value=[
                    {'id':7,'name':'Pessoa um'},{'id':8,'name':'Pessoa dois'}]
                owner=MagicMock()
                owner.selected_payroll_period.return_value=(2026,10)
                combo=MagicMock()
                combo.current.return_value=index
                commands={}

                def button(*args,**kwargs):
                    commands[kwargs['text']]=kwargs['command']
                    return MagicMock()

                stack.enter_context(patch.object(self.app,'connect',return_value=con))
                stack.enter_context(patch.object(self.app.tk,'Toplevel'))
                for name in ('Frame','Label'):
                    stack.enter_context(patch.object(self.app.ttk,name))
                stack.enter_context(patch.object(
                    self.app.ttk,'Combobox',return_value=combo))
                stack.enter_context(patch.object(
                    self.app.ttk,'Button',side_effect=button))
                stack.enter_context(patch.object(
                    self.app,'temporary_pdf_path',return_value='test.pdf'))
                opened=stack.enter_context(patch.object(self.app,'open_pdf'))
                self.app.FolhaApp.generate_payslips_dialog(owner)
                commands['Gerar PDF']()
                owner.write_payslips_pdf.assert_called_once_with(
                    2026,10,'test.pdf',expected)
                opened.assert_called_once_with('test.pdf')

    def test_batch_saves_individual_pdf_without_phone_or_opening_whatsapp(self):
        employee = {'id': 7, 'name': 'Funcionario teste', 'phone': ''}
        con = MagicMock()
        con.__enter__.return_value = con
        con.execute.return_value.fetchone.return_value = {'id': 1}
        con.execute.return_value.fetchall.return_value = [employee]
        owner = MagicMock()
        owner.selected_payroll_period.return_value = (2026, 10)
        tree = MagicMock()
        tree.selection.return_value = ('7',)
        commands = {}

        def button(*args, **kwargs):
            commands[kwargs['text']] = kwargs['command']
            return MagicMock()

        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            stack.enter_context(patch.object(self.app, 'connect', return_value=con))
            for name in ('Toplevel',):
                stack.enter_context(patch.object(self.app.tk, name))
            for name in ('Frame', 'Label', 'Scrollbar'):
                stack.enter_context(patch.object(self.app.ttk, name))
            stack.enter_context(patch.object(self.app.ttk, 'Treeview', return_value=tree))
            stack.enter_context(patch.object(self.app.ttk, 'Button', side_effect=button))
            stack.enter_context(patch.object(
                self.app, 'ZAP_REPORTS_DIR', folder))
            messages = stack.enter_context(patch.object(self.app, 'messagebox'))
            browser = stack.enter_context(patch.object(self.app, 'open_whatsapp_desktop'))
            stack.enter_context(patch.object(self.app.os, 'startfile', create=True))
            stack.enter_context(patch.object(self.app.subprocess, 'Popen'))

            self.app.FolhaApp.send_payslips_whatsapp_batch_dialog(owner)
            commands['Salvar PDFs']()

            owner.write_payslips_pdf.assert_called_once()
            year, month, path, employee_id = owner.write_payslips_pdf.call_args.args
            self.assertEqual((year, month, employee_id), (2026, 10, 7))
            self.assertEqual(Path(path).parent.parent, Path(folder))
            self.assertTrue(Path(path).parent.is_dir())
            owner.saved_payslips_whatsapp_dialog.assert_called_once_with(
                2026, 10, [(employee, path)])
            browser.assert_not_called()
            messages.showerror.assert_not_called()
            messages.showwarning.assert_not_called()

    def test_locate_pdf_selects_exact_file_in_windows_explorer(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'Funcionario teste.pdf'
            path.write_bytes(b'%PDF-test')
            with patch.object(self.app.sys, 'platform', 'win32'), patch.object(
                    self.app.subprocess, 'Popen') as process:
                self.app.show_file_in_folder(str(path))
                process.assert_called_once_with(
                    f'explorer.exe /select,"{path}"')

    def test_locate_missing_pdf_does_not_open_explorer(self):
        with patch.object(self.app.os.path, 'isfile', return_value=False), patch.object(
                self.app.subprocess, 'Popen') as process:
            with self.assertRaises(FileNotFoundError):
                self.app.show_file_in_folder('missing.pdf')
            process.assert_not_called()

    def test_saved_list_opens_only_selected_employees_chat_and_pdf(self):
        commands = {}
        tree = MagicMock()
        tree.selection.return_value = ('1',)

        def button(*args, **kwargs):
            commands[kwargs['text']] = kwargs['command']
            return MagicMock()

        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            paths = [str(Path(folder) / f'Pessoa {index}.pdf') for index in range(2)]
            for path in paths:
                Path(path).write_bytes(b'%PDF-test')
            generated = [
                ({'id': 1, 'name': 'Pessoa um', 'phone': '11999991234'}, paths[0]),
                ({'id': 2, 'name': 'Pessoa dois', 'phone': '21988881234'}, paths[1]),
            ]
            stack.enter_context(patch.object(self.app.tk, 'Toplevel'))
            stack.enter_context(patch.object(self.app.tk, 'StringVar'))
            for name in ('Frame', 'Label', 'Scrollbar', 'Entry'):
                stack.enter_context(patch.object(self.app.ttk, name))
            stack.enter_context(patch.object(self.app.ttk, 'Treeview', return_value=tree))
            stack.enter_context(patch.object(self.app.ttk, 'Button', side_effect=button))
            messages = stack.enter_context(patch.object(self.app, 'messagebox'))
            browser = stack.enter_context(patch.object(
                self.app, 'open_whatsapp_desktop'))
            locate = stack.enter_context(patch.object(self.app, 'show_file_in_folder'))
            self.app.FolhaApp.saved_payslips_whatsapp_dialog(
                MagicMock(), 2026, 10, generated)
            commands['Abrir WhatsApp do selecionado']()
            self.assertEqual(
                parse_qs(urlparse(browser.call_args.args[0]).query)['phone'],
                ['5521988881234'])
            locate.assert_called_once_with(paths[1])
            messages.showerror.assert_not_called()
            tree.bind.assert_not_called()
            browser.reset_mock()
            locate.reset_mock()
            tree.selection.return_value = ('0',)
            commands['Abrir WhatsApp do selecionado']()
            self.assertEqual(
                parse_qs(urlparse(browser.call_args.args[0]).query)['phone'],
                ['5511999991234'])
            locate.assert_called_once_with(paths[0])
            tree.selection.return_value = ('1',)
            commands['Próximo colaborador']()
            tree.selection_set.assert_called_with('1')
            self.assertEqual(
                parse_qs(urlparse(browser.call_args.args[0]).query)['phone'],
                ['5521988881234'])
            self.assertEqual(locate.call_args.args[0], paths[1])
            browser.reset_mock()
            locate.reset_mock()
            commands['Próximo colaborador']()
            browser.assert_not_called()
            locate.assert_not_called()
            messages.showinfo.assert_called()

    def test_desktop_opens_windows_protocol(self):
        url = self.app.whatsapp_chat_url('11999991234', 'Pessoa', 2026, 10)
        with patch.object(self.app.sys, 'platform', 'win32'), patch.object(
                self.app.os, 'startfile', create=True) as start:
            self.app.open_whatsapp_desktop(url)
            start.assert_called_once_with(url)

    def test_desktop_reports_missing_app(self):
        with patch.object(self.app.sys, 'platform', 'win32'), patch.object(
                self.app.os, 'startfile', create=True, side_effect=OSError('Sem aplicativo')):
            with self.assertRaisesRegex(RuntimeError, 'Confira se ele está instalado'):
                self.app.open_whatsapp_desktop('whatsapp://send')
