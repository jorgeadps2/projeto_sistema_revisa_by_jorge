import sys
import gc
import tempfile
import tkinter as tk
from tkinter import font as tkfont
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from revisa_integrado.core import paths
from revisa_integrado.ui import theme
from revisa_integrado.ui.action_layout import InlineForms, configure_form, group_actions


class ActionLayoutTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry("1000x700")
        self.addCleanup(self.root.destroy)

    def test_compact_menu_size_hover_and_focus(self):
        row = ttk.Frame(self.root)
        row.pack()
        ttk.Button(row, text="Fechar folha").pack()
        trigger = group_actions(row, "Folha mensal")
        previous = tk.Menubutton(
            self.root, text=trigger.cget("text"), image=trigger.action_icon,
            compound="left", font=("Segoe UI Semibold", 11),
            relief="solid", bd=1, padx=14, pady=9)
        previous.pack()
        self.root.update()
        self.assertLessEqual(trigger.winfo_reqheight(), previous.winfo_reqheight() - 6)
        self.assertLess(trigger.winfo_reqwidth(), previous.winfo_reqwidth())
        self.assertGreaterEqual(trigger.winfo_reqheight(), 32)
        self.assertEqual(str(trigger.cget("takefocus")), "1")
        trigger.event_generate("<Enter>")
        self.assertEqual(trigger.cget("state"), "active")
        self.assertEqual(trigger.cget("activebackground"), theme.YELLOW)
        trigger.event_generate("<Leave>")
        self.assertEqual(trigger.cget("state"), "normal")
        self.assertEqual(trigger.cget("background"), theme.SURFACE)
        self.assertEqual(trigger.cget("highlightbackground"), theme.PAPER_BORDER)

    def test_primary_action_remains_the_original_button(self):
        row = ttk.Frame(self.root)
        row.pack()
        calls = []
        primary = ttk.Button(row, text="Adicionar", command=lambda: calls.append("add"))
        primary.pack(side="left")
        delete = ttk.Button(row, text="Excluir", command=lambda: calls.append("delete"))
        delete.pack(side="left")
        trigger = group_actions(row, "Ações", primary="Adicionar")
        menu = trigger.nametowidget(trigger.cget("menu"))
        self.root.update()
        self.assertTrue(primary.winfo_viewable())
        self.assertFalse(delete.winfo_viewable())
        self.assertEqual(menu.index("end"), 0)
        self.assertEqual(str(menu.entrycget(0, "foreground")), theme.DANGER)
        primary.invoke()
        primary.state(["disabled"])
        primary.invoke()
        menu.invoke(0)
        self.assertEqual(calls, ["add", "delete"])

    def test_menu_preserves_commands_labels_and_disabled_states(self):
        row = ttk.Frame(self.root)
        row.pack()
        calls = []
        source = ttk.Button(row, text="Fechar folha", command=lambda: calls.append("close"))
        source.pack()
        other = ttk.Button(row, text="Editar", state="disabled")
        other.pack()
        trigger = group_actions(row, "Folha mensal")
        menu = trigger.nametowidget(trigger.cget("menu"))
        menu.invoke(0)
        self.assertEqual(calls, ["close"])
        self.assertEqual(menu.entrycget(1, "state"), "disabled")
        source.configure(text="Reabrir folha", state="disabled")
        menu.tk.call(menu.cget("postcommand"))
        self.assertEqual(menu.entrycget(0, "label"), "Reabrir folha")
        self.assertEqual(menu.entrycget(0, "state"), "disabled")
        self.assertFalse(source.winfo_manager())

    def test_grouped_menu_and_submenu_highlight_actions_in_yellow(self):
        row = ttk.Frame(self.root)
        row.pack()
        calls = []
        submenu = tk.Menu(row, tearoff=False)
        submenu.add_command(label="Editar cadastro", command=lambda: calls.append("edit"))
        submenu.add_command(label="Excluir colaborador")
        ttk.Menubutton(row, text="Cadastro", menu=submenu).pack()
        trigger = group_actions(row, "Colaboradores")
        menu = trigger.nametowidget(trigger.cget("menu"))
        self.assertEqual(menu.entrycget(0, "menu"), str(submenu))
        for action_menu in (menu, submenu):
            action_menu.activate(0)
            self.assertEqual(action_menu.index("active"), 0)
            self.assertEqual(str(action_menu.cget("activebackground")), theme.YELLOW)
        self.assertEqual(str(submenu.entrycget(1, "activeforeground")), theme.DANGER)
        submenu.invoke(0)
        self.assertEqual(calls, ["edit"])

    def test_direct_action_replaces_menu_and_hides_original_button(self):
        row = ttk.Frame(self.root)
        row.pack()
        calls = []
        source = ttk.Button(row, text="Salvar e calcular energia")
        source.grid(row=0, column=0)
        trigger = group_actions(
            row, "Rateio de energia", command=lambda: calls.append("rateio"))

        self.assertIsInstance(trigger, tk.Button)
        self.assertEqual(trigger.cget("text"), "Rateio de energia")
        self.assertEqual(trigger.cget("background"), theme.SURFACE)
        self.assertEqual(trigger.cget("activebackground"), theme.YELLOW)
        self.assertNotIn("menu", trigger.keys())
        self.assertFalse(source.winfo_manager())
        trigger.invoke()
        self.assertEqual(calls, ["rateio"])

    def test_nested_forms_restore_parent_without_separate_windows(self):
        content = ttk.Frame(self.root)
        content.pack()
        host = InlineForms(self.root, content.pack_forget, lambda: content.pack())
        self.addCleanup(host.close_all)
        first = host.open()
        configure_form(first, "title", "Cadastro")
        ttk.Entry(first).pack()
        nested = host.open()
        configure_form(nested, "title", "Edição")
        self.root.update()
        self.assertFalse(content.winfo_ismapped())
        self.assertFalse(first.winfo_viewable())
        nested.destroy()
        self.root.update()
        self.assertTrue(first.winfo_ismapped())
        first.destroy()
        self.root.update()
        self.assertTrue(content.winfo_ismapped())
        self.assertEqual(host.stack, [])
        self.assertFalse(any(isinstance(child, tk.Toplevel) for child in self.root.winfo_children()))


class IntegratedModuleTests(unittest.TestCase):
    def setUp(self):
        paths.ensure_module_paths()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(gc.collect)
        self.root = tk.Tk()
        self.root.geometry("1200x780")
        self.errors = []
        self.root.report_callback_exception = lambda *error: self.errors.append(error)
        self.addCleanup(self.root.destroy)

    def test_payroll_build_and_employee_form_use_inline_navigation(self):
        import folha_pagamento as payroll
        with patch.object(payroll, "DB_PATH", str(Path(self.temp.name) / "folha.db")), \
                patch.object(payroll, "resource_path", side_effect=lambda name: str(
                    Path(self.temp.name) / name) if name.endswith(".db") else
                    Path(paths.FOLHA_SOURCE_DIR) / name):
            payroll.init_db()
            payroll.use_light_theme()
            app = payroll.FolhaPanel(self.root, centralized_actions=True,
                                     signing_status_callback=lambda: ("Teste", "ok", "09/01/2027"))
            app.pack(fill="both", expand=True)
            self.addCleanup(app.inline_forms.close_all)
            self.root.update()
            self.assertEqual(app.current_section, "dashboard")
            notice = app.signing_expiry_label
            self.assertEqual(notice.cget("text"), "Assinatura válida até 09/01/2027")
            self.assertEqual(notice.winfo_rgb(notice.cget("background")), notice.winfo_rgb("#B42318"))
            self.assertEqual(notice.winfo_rgb(notice.cget("foreground")), notice.winfo_rgb("white"))
            for compact in (True, False):
                app.set_compact_layout(compact)
                self.root.update()
                self.assertEqual(app.titlebar.pack_slaves(), [app.page_title])
                self.assertEqual(app.page_title.cget("text"), "Painel de controle")
            dashboard_buttons = self.descendants(app.dashboard_tab, ttk.Button)
            self.assertTrue({"Abrir folha mensal", "Colaboradores"}.isdisjoint(
                button.cget("text") for button in dashboard_buttons))
            style = ttk.Style(self.root)
            self.assertEqual(style.lookup(app.dashboard_tab.cget("style"), "background"), theme.PAPER)
            for name in ("payroll", "employees", "salaries", "loans"):
                selected = app.navigation_buttons[name]
                selected.invoke()
                self.root.update()
                self.assertEqual(app.current_section, name)
                self.assertEqual(ttk.Style(self.root).lookup(selected.cget("style"), "background"), theme.YELLOW)
                menus = self.descendants(app.current_page, tk.Menubutton)
                self.assertTrue(menus, name)
                if name == "payroll":
                    actions = next(menu for menu in menus
                                   if menu.cget("text").startswith("Folha mensal"))
                    reports = next(menu for menu in menus
                                   if menu.cget("text").startswith("Relatórios"))
                    self.assertEqual(actions.winfo_rooty(), reports.winfo_rooty())
                    self.assertEqual(actions.winfo_height(), reports.winfo_height())
            for index in range(3):
                app.loan_notebook.select(index)
                self.root.update()
                reports = [
                    menu for menu in self.descendants(app.current_page, tk.Menubutton)
                    if menu.cget("text").startswith("Relatórios")
                    and menu.winfo_viewable()]
                self.assertEqual(len(reports), 1)
                menu = reports[0].nametowidget(reports[0].cget("menu"))
                self.assertEqual(
                    [menu.entrycget(i, "label") for i in range(menu.index("end") + 1)],
                    ["Adiantamentos (PDF)", "Emprestimo (PDF)", "Meta (PDF)"])
            with patch.object(app, "generate_advance_report_dialog") as advance_report:
                menu.invoke(0)
                advance_report.assert_called_with(payroll.ADVANCE_KIND)
                menu.invoke(1)
                advance_report.assert_called_with(payroll.LOAN_KIND)
            for tree in (*app.loan_trees.values(), app.meta_tree):
                for column in tree["columns"]:
                    self.assertFalse(tree.column(column, "stretch"))
            long_name = "COLABORADOR COM NOME COMPLETO PARA TESTAR A LARGURA SEM CORTES"
            cell_font = tkfont.Font(font=ttk.Style(app).lookup("Treeview", "font"))
            self.assertGreater(cell_font.measure(long_name) + 24, 420)
            for tree, column, limit in (
                    (app.salary_tree, "name", 220),
                    (app.loan_trees["advances"], "employee", 420),
                    (app.loan_trees["loans"], "employee", 420),
                    (app.meta_tree, "employee", 420)):
                item = tree.insert("", "end")
                tree.set(item, column, long_name)
                app.autosize_treeview_columns(
                    tree, max_width=limit, full_text_columns=(column,))
                self.assertGreaterEqual(tree.column(column, "width"),
                                        cell_font.measure(long_name) + 24)
                self.assertFalse(tree.column(column, "stretch"))
                for other in tree["columns"]:
                    if other != column:
                        self.assertLessEqual(tree.column(other, "width"), limit)
            with patch.object(app, "selected_payroll_period", return_value=(2026, 11)), \
                    patch.object(app, "wait_window"):
                app.generate_advance_report_dialog(payroll.LOAN_KIND)
            self.root.update()
            dialogs = self.descendants(app, tk.Toplevel)
            self.assertEqual(len(dialogs), 1)
            dialog = dialogs[0]
            self.assertFalse(app.inline_forms.stack)
            self.assertLess(dialog.winfo_height(), 500)
            self.assertLess(dialog.winfo_width(), 800)
            self.assertTrue(app.current_page.winfo_ismapped())
            cancel = next(button for button in self.descendants(dialog, ttk.Button)
                          if button.cget("text") == "Cancelar")
            cancel.invoke()
            self.root.update()
            self.assertFalse(dialog.winfo_exists())
            app.navigate("employees")
            app.add_employee_dialog()
            self.root.update()
            self.assertEqual(len(app.inline_forms.stack), 1)
            self.assertFalse(app.current_page.winfo_ismapped())
            app.inline_forms.close_all()
            self.root.update()
            self.assertTrue(app.current_page.winfo_ismapped())
            app.add_employee_dialog()
            body = app.inline_forms.stack[-1][1]
            entry = self.descendants(body, ttk.Entry)[0]
            entry.insert(0, "Colaborador de teste")
            save = next(button for button in self.descendants(body, ttk.Button)
                        if button.cget("text") == "Salvar")
            self.root.update()
            self.assertLessEqual(save.winfo_rootx()+save.winfo_width(),
                                 self.root.winfo_rootx()+self.root.winfo_width())
            save.invoke()
            self.root.update()
            self.assertFalse(app.inline_forms.stack)
            with payroll.connect() as connection:
                self.assertEqual(connection.execute(
                    "SELECT name FROM employees WHERE name=?",
                    ("Colaborador de teste",)).fetchone()[0], "Colaborador de teste")
            self.assertEqual(self.errors, [])

    def test_energy_forms_and_tab_switch_keep_data_in_temporary_database(self):
        import controle_energia_agua as energy
        with patch.object(energy, "DB_PATH", Path(self.temp.name) / "energia.db"):
            energy.usar_tema_claro()
            container = tk.Frame(self.root)
            container.pack(fill="both", expand=True)
            app = energy.App(container, embutido=True)
            self.addCleanup(app.encerrar)
            self.root.update()
            notice = app.aviso_aberto
            self.assertEqual(notice.winfo_rgb(notice.cget("background")), notice.winfo_rgb("#B42318"))
            self.assertEqual(notice.winfo_rgb(notice.cget("foreground")), notice.winfo_rgb("white"))
            self.assertTrue(self.descendants(app.tab_mes, tk.Menubutton))
            self.assertTrue(self.descendants(app.tab_oc, tk.Menubutton))
            pdf = next(button for button in self.descendants(app.tab_rel, ttk.Button)
                       if button.cget("text") == "Gerar relatório em PDF")
            app.nb.select(app.tab_rel)
            self.root.update()
            self.assertTrue(pdf.winfo_viewable())
            style = ttk.Style(self.root)
            button_style = pdf.cget("style")
            self.assertEqual(style.lookup(button_style, "background"), theme.SURFACE)
            self.assertEqual(style.lookup(button_style, "background", ("active",)), theme.YELLOW)
            self.assertEqual(style.lookup(button_style, "background", ("pressed",)), theme.YELLOW_HOVER)
            app.nb.select(app.tab_mes)
            self.root.update()
            for open_form in (app.editar_contas_mes, app.editar_despesa, app.dialogo_relatorio_pdf):
                open_form()
                self.root.update()
                self.assertEqual(len(app.inline_forms.stack), 1)
                self.assertFalse(app.nb.winfo_ismapped())
                app.inline_forms.close_all()
                self.root.update()
                self.assertTrue(app.nb.winfo_ismapped())
            app.editar_contas_mes()
            app.nb.select(app.tab_oc)
            self.root.update()
            self.assertFalse(app.inline_forms.stack)
            self.assertEqual(self.errors, [])

    @staticmethod
    def descendants(widget, kind):
        result = []
        for child in widget.winfo_children():
            if isinstance(child, kind):
                result.append(child)
            result.extend(IntegratedModuleTests.descendants(child, kind))
        return result


if __name__ == "__main__":
    unittest.main()
