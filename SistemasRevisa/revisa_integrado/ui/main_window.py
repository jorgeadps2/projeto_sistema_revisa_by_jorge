"""Janela principal única do Sistemas Revisa."""
import os
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import APP_NAME, APP_VERSION
from ..core import backup, config, paths, transfer
from ..core.logs import get_logger
from ..core.security import AttemptLimiter, Session, MODULE_ENERGIA, MODULE_FOLHA
from ..modules import energia, folha
from . import theme as t

USER_NAME = "JORGE"
COMPANY_NAME = "FTS DISTRIBUIDORA DE PEÇAS LTDA"
LEGACY_PROCESSES = {
    "FolhaPagamentoRevisa_1_140.exe": (MODULE_FOLHA,),
    "Controle_Energia_Agua.exe": (MODULE_ENERGIA,),
    "GerenciadorAdministrativoRevisa.exe": (MODULE_FOLHA, MODULE_ENERGIA),
}
NAVIGATION = (
    ("painel", "Painel geral", "painel"),
    (MODULE_FOLHA, "Folha de Pagamento", "folha"),
    (MODULE_ENERGIA, "Energia e Água", "energia"),
    ("backups", "Backups e Transferência", "backups"),
    ("admin", "Administração e Segurança", "admin"),
    ("sobre", "Sobre", "sobre"),
)
PAGE_TITLES = {key: text for key, text, _icon in NAVIGATION}


def running_legacy_programs():
    try:
        output = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True,
                                errors="replace", timeout=15,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    names = {line.split(",")[0].strip('"').lower() for line in output.splitlines() if line}
    return [name for name in LEGACY_PROCESSES if name.lower() in names]


class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.log = get_logger()
        self.session = Session()
        self.limiter = AttemptLimiter()
        self.sync_limiter = AttemptLimiter()
        self.modules = {}
        self.pages = {}
        self.current = None
        self.images = {}
        self.icon_images = {}
        self.clock_job = None
        self.busy = False
        self.title(f"{APP_NAME}  •  v{APP_VERSION}")
        self.configure(bg=t.BG)
        try:
            self.iconbitmap(str(paths.asset("revisa.ico")))
        except tk.TclError:
            pass
        self.minsize(560, 280)
        self._center_window(610, 300)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.auto_sync_notice = ""
        self._automatic_sync_startup()
        self.show_login()

    # ------------------------------------------------------------------ utilidades
    def _clear(self):
        if self.clock_job is not None:
            try:
                self.after_cancel(self.clock_job)
            except tk.TclError:
                pass
            self.clock_job = None
        self.config(menu="")
        for child in self.winfo_children():
            if not isinstance(child, tk.Toplevel):
                child.destroy()

    def _icon(self, name, size, gap=0):
        key = (name, size, gap)
        if key not in self.icon_images:
            try:
                from .icons import photo
                self.icon_images[key] = photo(name, size, self, gap)
            except Exception:
                self.log.exception("Falha ao desenhar o ícone %s", name)
                self.icon_images[key] = None
        return self.icon_images[key]

    def _logo(self, key, size):
        if key in self.images:
            return self.images[key]
        try:
            from PIL import Image, ImageTk
            with Image.open(paths.asset("logo_central_revisa.png")) as source:
                image = source.convert("RGBA")
                image.thumbnail(size)
                self.images[key] = ImageTk.PhotoImage(image, master=self)
        except Exception:
            self.images[key] = None
        return self.images[key]

    def apply_shell_style(self):
        self.style.configure("Shell.Treeview", background=t.SURFACE, fieldbackground=t.SURFACE,
                             foreground=t.TEXT, rowheight=24, borderwidth=0, font=t.FONT_SMALL)
        self.style.map("Shell.Treeview", background=[("selected", t.SELECTED)], foreground=[("selected", t.TEXT)])
        self.style.configure("Shell.Treeview.Heading", background=t.STATUS_BG, foreground=t.PRIMARY_DARK,
                             font=("Segoe UI Semibold", 9), relief="flat")
        self.style.map("Shell.Treeview.Heading", background=[("active", t.SELECTED)])

    def _title_band(self, subtitle=""):
        band = tk.Frame(self, bg=t.PRIMARY, height=36)
        band.pack(side="top", fill="x")
        band.pack_propagate(False)
        tk.Label(band, text="Sistemas Revisa", bg=t.PRIMARY, fg="#FFFFFF",
                 font=("Segoe UI Semibold", 14)).pack(side="left", padx=(14, 8))
        title = tk.Label(band, text=subtitle, bg=t.PRIMARY, fg="#DCEBFA", font=("Segoe UI", 11))
        title.pack(side="left")
        info = tk.Label(band, text="", bg=t.PRIMARY, fg="#DCEBFA", font=t.FONT_SMALL)
        info.pack(side="right", padx=14)
        tk.Frame(self, bg=t.ORANGE, height=3).pack(side="top", fill="x")
        return title, info

    # ------------------------------------------------------------------ login
    def _center_window(self, width, height):
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        width, height = min(width, screen_w - 40), min(height, screen_h - 80)
        self.geometry(f"{width}x{height}+{max(0, (screen_w - width) // 2)}+"
                      f"{max(0, (screen_h - height) // 2)}")

    def _resize_login_window(self):
        try:
            self.state("normal")
        except tk.TclError:
            pass
        self.minsize(560, 280)
        self._center_window(610, 300)

    def _resize_shell_window(self):
        width, height = 1320, 820
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        width, height = min(width, screen_w - 40), min(height, screen_h - 80)
        self.minsize(min(980, screen_w - 40), min(600, screen_h - 80))
        self._center_window(width, height)
        self.after_idle(self.state, "zoomed")

    def show_login(self):
        self._clear()
        self.modules.clear()
        self.pages.clear()
        self.current = None
        self._resize_login_window()
        outer = tk.Frame(self, bg=t.BG)
        outer.pack(fill="both", expand=True)
        box = tk.Frame(outer, bg=t.SURFACE, highlightbackground=t.BORDER, highlightthickness=1)
        box.pack(fill="both", expand=True)
        box.columnconfigure(0, weight=1)
        box.rowconfigure(2, weight=1)
        header = tk.Frame(box, bg=t.PRIMARY, height=54)
        header.grid(row=0, column=0, sticky="ew")
        header.pack_propagate(False)
        heading = tk.Frame(header, bg=t.PRIMARY)
        heading.pack(side="left", fill="y", padx=16, pady=5)
        t.label(heading, "SISTEMAS REVISA", 15, "#FFFFFF", True, bg=t.PRIMARY).pack(anchor="w")
        t.label(heading, "ACESSO AO SISTEMA", 8, "#DCEBFA", True, bg=t.PRIMARY).pack(anchor="w")
        tk.Frame(box, bg=t.ORANGE, height=3).grid(row=1, column=0, sticky="ew")
        content = tk.Frame(box, bg=t.SURFACE, padx=12, pady=8)
        content.grid(row=2, column=0, sticky="nsew")
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)
        footer = self._build_login_footer(box)
        footer.grid(row=3, column=0, sticky="ew")
        brand = tk.Frame(content, bg=t.SURFACE, width=135)
        brand.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        brand.pack_propagate(False)
        logo = self._logo("login", (108, 100))
        if logo:
            tk.Label(brand, image=logo, bg=t.SURFACE).pack(pady=(0, 6))
        tk.Frame(brand, bg=t.BORDER, height=1).pack(fill="x", pady=(0, 7))
        t.label(brand, "FTS DISTRIBUIDORA DE PEÇAS LTDA", 9, t.PRIMARY_DARK, True,
                bg=t.SURFACE, wraplength=132, justify="center").pack(fill="x")
        body = tk.Frame(content, bg=t.SURFACE)
        body.grid(row=0, column=1, sticky="nsew")
        self.login_body = body
        try:
            state = folha.status()
            if state != "ausente":
                folha.prepare_existing_database()
                state = folha.status()
        except Exception as error:
            self.log.exception("Falha ao preparar o banco da Folha")
            t.label(body, "Não foi possível abrir o banco principal", 14, t.TEXT, True).pack(pady=(4, 6))
            t.label(body, str(error), 10, t.MUTED, wraplength=380, justify="left").pack(anchor="w")
            t.button(body, "Tentar novamente", self.show_login).pack(fill="x", pady=(16, 0))
            return
        if state == "ausente":
            self._center_window(650, 420)
            self._login_missing_database(body)
        elif state == "sem_senha":
            self._center_window(610, 430)
            self._login_form(body, create=True)
        else:
            self._login_form(body, create=False)

    def _login_missing_database(self, body):
        t.label(body, "Banco da Folha não encontrado", 15, t.TEXT, True).pack(pady=(4, 6))
        t.label(body, f"O sistema procurou o banco em:\n{folha.db_path()}\n\n"
                "Nenhum banco foi criado. Se este computador já tinha dados, restaure um backup "
                "verificado nessa pasta antes de continuar.", 10, t.MUTED, wraplength=400,
                justify="left").pack(anchor="w")
        t.button(body, "Tentar novamente", self.show_login).pack(fill="x", pady=(16, 6))
        t.button(body, "Conectar à sincronização automática…", self.connect_auto_sync,
                 kind="secondary").pack(fill="x", pady=(0, 6))
        t.button(body, "Criar banco novo (instalação nova)…", self.create_new_payroll_database,
                 kind="secondary").pack(fill="x")
        t.button(body, "Sair", self.on_close, kind="secondary").pack(fill="x", pady=(6, 0))

    def create_new_payroll_database(self):
        if not messagebox.askyesno(
                "Criar banco novo",
                "Criar um banco de dados NOVO e VAZIO para a Folha de Pagamento?\n\n"
                "Use somente em uma instalação nova. Se existem dados em outro lugar, escolha Não "
                "e restaure o backup.", icon="warning", default="no", parent=self):
            return
        try:
            folha.create_new_database()
            self.log.warning("Banco novo da Folha criado por confirmação explícita: %s", folha.db_path())
        except Exception as error:
            messagebox.showerror("Falha ao criar banco", str(error), parent=self)
        self.show_login()

    def _login_form(self, body, create):
        form = tk.Frame(body, bg=t.SURFACE)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        form.grid(row=0, column=0)
        if create:
            t.label(form, "Cadastre a senha principal", 14, t.TEXT, True).pack(anchor="w", pady=(2, 4))
        else:
            t.label(form, "Entrar no sistema", 15, t.TEXT, True).pack(anchor="w", pady=(2, 4))
        t.label(form, f"Usuário: {USER_NAME}", 10, t.MUTED).pack(anchor="w", pady=(0, 5))
        command = self.do_create_password if create else self.do_login
        self.login_fields = []
        if create:
            password_fields = tk.Frame(form, bg=t.SURFACE)
            password_fields.pack(anchor="w")
            for name in (f"Nova senha (mínimo {folha.min_password_length()} caracteres)",
                         "Confirme a nova senha"):
                t.label(password_fields, name, 9, t.MUTED, True).pack(anchor="w", pady=(4, 2))
                field = t.entry(password_fields, show="•", width=24)
                field.pack(fill="x", ipady=3)
                self.login_fields.append(field)
            self.login_button = t.button(password_fields, "Salvar senha", command)
            self.login_button.pack(fill="x", pady=(6, 3))
        else:
            t.label(form, "Senha", 9, t.MUTED, True).pack(anchor="w", pady=(2, 2))
            actions = tk.Frame(form, bg=t.SURFACE)
            actions.pack(anchor="w", pady=(0, 3))
            field = t.entry(actions, show="•", width=22)
            field.pack(side="left", ipady=3)
            self.login_button = t.button(actions, "Entrar", command)
            self.login_button.pack(side="right", padx=(8, 0))
            self.login_fields = [field]
        self.login_message = t.label(form, "", 9, t.DANGER, wraplength=360)
        self.login_message.pack(fill="x", pady=(2, 0))
        if create:
            t.button(form, "Sair", self.on_close, kind="danger").pack(anchor="w", pady=(3, 0))
        for field in self.login_fields:
            field.bind("<Return>", lambda _e: command())
        self.login_fields[0].focus_set()

    def _build_login_footer(self, parent):
        footer = tk.Frame(parent, bg=t.PRIMARY, height=76)
        footer.pack_propagate(False)
        for column in (0, 2, 4):
            footer.columnconfigure(column, weight=1, uniform="login_footer")

        columns = (
            ("Desenvolvido por", "Jorge Alberto de Paula", "#FFFFFF"),
            ("Suporte Técnico", "", t.TEXT),
            ("Validade e Versão", f"Sistemas Revisa v{APP_VERSION}", "#FFFFFF"),
        )
        for index, (heading, value, color) in enumerate(columns):
            if index:
                tk.Frame(footer, bg=t.BORDER, width=1).grid(
                    row=0, column=index * 2 - 1, sticky="ns", pady=9)
            cell = tk.Frame(footer, bg=t.PRIMARY, padx=9, pady=7)
            cell.grid(row=0, column=index * 2, sticky="nsew")
            t.label(cell, heading, 8, "#FFFFFF", True, bg=t.PRIMARY).pack(anchor="w")
            if value:
                t.label(cell, value, 8, color, bg=t.PRIMARY,
                        wraplength=165, justify="left").pack(anchor="w", pady=(2, 0))
            else:
                sync_text, sync_color = self._login_sync_status()
                signing_text, signing_color = self._login_signing_status()
                self._login_status_badge(cell, sync_text, sync_color)
                self._login_status_badge(cell, signing_text, signing_color)
        return footer

    @staticmethod
    def _login_status_badge(parent, text, color):
        palette = {
            t.SUCCESS: ("#DCFCE7", "#166534"),
            t.DANGER: ("#FEE2E2", "#991B1B"),
            t.WARNING: ("#FEF3C7", "#92400E"),
            t.MUTED: ("#E2E8F0", "#334155"),
        }
        background, foreground = palette.get(color, ("#DBEAFE", "#1E3A8A"))
        tk.Label(parent, text=text, bg=background, fg=foreground,
                 font=("Segoe UI", 8), padx=4, pady=1, wraplength=165,
                 justify="left", anchor="w").pack(anchor="w", pady=(2, 0))

    def _login_sync_status(self):
        try:
            settings = config.load()
            if not settings["transferencia_habilitada"]:
                return "Sincronização: desativada", t.MUTED
            state = transfer.load_state(paths.transfer_state_path())
        except Exception as error:
            self.log.exception("Falha ao consultar o status da sincronização no login")
            return "Sincronização: falha", t.DANGER
        if not state.get("titular", True):
            return "Sincronização: aguardando o outro PC", t.WARNING
        if self.auto_sync_notice == "falha":
            return "Sincronização: falha", t.DANGER
        if self.auto_sync_notice == "ok":
            return "Sincronização: OK", t.SUCCESS
        return "Sincronização: ativa", t.SUCCESS

    @staticmethod
    def _login_signing_status():
        from .pages import _signing_status

        text, color = _signing_status(warning_days=15)
        if " VENCEU em " in text:
            text = "Assinatura digital vencida"
        elif text.startswith("Assinatura digital vence em"):
            text = text.split(" (", 1)[0]
        elif text.startswith("Assinatura digital válida até"):
            text = "Assinatura digital: OK"
        return text, color

    def do_login(self):
        remaining = self.limiter.remaining_lock()
        if remaining > 0:
            self.login_message.configure(text=f"Muitas tentativas. Aguarde {int(remaining) + 1} segundos.")
            return
        field = self.login_fields[0]
        password = field.get()
        field.delete(0, "end")
        self.login_button.configure(state="disabled")
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            valid = folha.verify_password(password)
        except Exception as error:
            self.log.exception("Erro ao verificar a senha principal")
            valid = None
            self.login_message.configure(text=f"Não foi possível verificar a senha: {error}")
        finally:
            password = None
            self.config(cursor="")
            if self.login_button.winfo_exists():
                self.login_button.configure(state="normal")
        if valid is None:
            return
        if not valid:
            self.limiter.failure()
            self.log.warning("Tentativa de login recusada")
            self.login_message.configure(text="Senha incorreta.")
            field.focus_set()
            return
        self.limiter.success()
        self.session.login(USER_NAME)
        self.log.info("Login principal aceito (usuário %s)", USER_NAME)
        self.show_shell()

    def do_create_password(self):
        new, confirm = (field.get() for field in self.login_fields)
        try:
            folha.set_password(new, confirm)
        except Exception as error:
            self.login_message.configure(text=str(error))
            return
        finally:
            for field in self.login_fields:
                field.delete(0, "end")
        self.log.info("Senha principal cadastrada")
        messagebox.showinfo("Senha cadastrada", "Senha principal cadastrada. Entre com a nova senha.", parent=self)
        self.show_login()

    # ------------------------------------------------------------------ shell
    def show_shell(self):
        self.session.require()
        self._clear()
        self._resize_shell_window()
        self.apply_shell_style()
        self._build_menu()
        self.header_title, self.header_info = self._title_band()
        self._build_status_bar()
        self.content = tk.Frame(self, bg=t.BG)
        self.content.pack(side="top", fill="both", expand=True)
        self.update_header()
        self.navigate("painel")

    def _build_menu(self):
        from .pages import change_main_password
        bar = tk.Menu(self, tearoff=0)
        go = self.navigate

        def submenu(label, items):
            menu = tk.Menu(bar, tearoff=0)
            for item in items:
                if item is None:
                    menu.add_separator()
                    continue
                text, icon, command = item
                image = self._icon(icon, 16)
                menu.add_command(label=text, command=command, image=image or "", compound="left")
            bar.add_cascade(label=label, menu=menu)

        submenu("Arquivo", (("Painel geral", "painel", lambda: go("painel")), None,
                            ("Sair", "sair", self.on_close)))
        submenu("Módulos", (("Folha de Pagamento", "folha", lambda: go(MODULE_FOLHA)),
                            ("Energia e Água", "energia", lambda: go(MODULE_ENERGIA))))
        submenu("Backups", (("Gerenciar backups e transferência", "backups", lambda: go("backups")),
                            ("Abrir pasta de backups", "backups", self.open_backup_folder)))
        submenu("Senhas", (("Alterar senha principal…", "senha",
                            lambda: self._menu_change_password(change_main_password)),
                           ("Alterar senha da Folha…", "senha",
                            lambda: self.change_module_password(MODULE_FOLHA)),
                           ("Alterar senha de Energia e Água…", "senha",
                            lambda: self.change_module_password(MODULE_ENERGIA))))
        submenu("Administração", (("Administração e Segurança", "admin", lambda: go("admin")),))
        submenu("Sobre", (("Sistemas Revisa", "sobre", lambda: go("sobre")),
                          ("Folha de Pagamento", "folha", lambda: self.show_module_about(MODULE_FOLHA)),
                          ("Energia e Água", "energia", lambda: self.show_module_about(MODULE_ENERGIA))))
        self.config(menu=bar)
        self.menu_bar = bar

    def _menu_change_password(self, dialog):
        try:
            self.session.require()
        except PermissionError:
            self.show_login()
            return
        dialog(self)

    def open_backup_folder(self):
        folder = paths.backups_dir()
        try:
            folder.mkdir(parents=True, exist_ok=True)
            os.startfile(str(folder))
        except OSError as error:
            self.log.exception("Falha ao abrir a pasta de backups")
            messagebox.showerror("Backups", f"Não foi possível abrir a pasta:\n{folder}\n\n{error}", parent=self)

    def change_module_password(self, key):
        try:
            self.session.require(key)
        except PermissionError:
            self.show_login()
            return
        if self.busy:
            messagebox.showinfo("Aguarde", "Há uma operação em andamento.", parent=self)
            return
        if key == MODULE_ENERGIA:
            try:
                energia.change_password(self)
            except Exception as error:
                self.log.exception("Falha ao alterar a senha de Energia e Água")
                messagebox.showerror("Alterar senha", str(error), parent=self)
            return
        if key != MODULE_FOLHA:
            raise ValueError(f"Módulo de senha desconhecido: {key}")
        record = self.modules.get(MODULE_FOLHA)
        if record is None:
            self.open_module(MODULE_FOLHA)
            record = self.modules.get(MODULE_FOLHA)
        if record is not None:
            self.after_idle(record["instance"].change_password_dialog)

    def show_module_about(self, key):
        if key not in (MODULE_FOLHA, MODULE_ENERGIA):
            raise ValueError(f"Módulo desconhecido: {key}")
        if self.busy:
            messagebox.showinfo("Aguarde", "Há uma operação em andamento.", parent=self)
            return
        self.open_module(key)
        record = self.modules.get(key)
        if record is None:
            return
        if key == MODULE_FOLHA:
            record["instance"].navigate("about")
        else:
            record["instance"].nb.select(record["instance"].tab_sobre)

    def _build_status_bar(self):
        bar = tk.Frame(self, bg=t.STATUS_BG, highlightbackground=t.BORDER, highlightthickness=1)
        bar.pack(side="bottom", fill="x")

        def cell(text="", side="left", expand=False):
            widget = tk.Label(bar, text=text, bg=t.STATUS_BG, fg=t.TEXT, font=("Segoe UI", 9), anchor="w", padx=10, pady=3)
            widget.pack(side=side, fill="x", expand=expand)
            tk.Frame(bar, bg=t.BORDER, width=1).pack(side=side, fill="y", pady=3)
            return widget

        self.status_user = cell()
        self.status_module = cell()
        self.status_company = cell(COMPANY_NAME, expand=True)
        self.status_clock = cell(side="right")
        cell(f"Versão {APP_VERSION}", side="right")
        self._tick_clock()

    def _tick_clock(self):
        if not getattr(self, "status_clock", None) or not self.status_clock.winfo_exists():
            self.clock_job = None
            return
        self.status_clock.configure(text=datetime.now().strftime("%d/%m/%Y  %H:%M"))
        self.clock_job = self.after(30000, self._tick_clock)

    def update_header(self):
        started = self.session.started.strftime("%d/%m/%Y %H:%M") if self.session.started else "—"
        self.header_info.configure(text=f"{COMPANY_NAME}")
        if getattr(self, "status_user", None) and self.status_user.winfo_exists():
            self.status_user.configure(text=f"Usuário: {self.session.user}  •  sessão desde {started}")
            self.status_module.configure(text=f"Módulo: {PAGE_TITLES.get(self.current, '—')}")

    def _show_frame(self, key, frame, title):
        for other in list(self.pages.values()) + [m["container"] for m in self.modules.values()]:
            if other is not frame and other.winfo_exists():
                other.pack_forget()
        frame.pack(fill="both", expand=True)
        self.current = key
        self.header_title.configure(text=f"—  {title}")
        self.update_header()

    def navigate(self, key):
        try:
            self.session.require()
        except PermissionError:
            self.show_login()
            return
        if self.busy:
            messagebox.showinfo("Aguarde", "Há uma operação em andamento.", parent=self)
            return
        if key in (MODULE_FOLHA, MODULE_ENERGIA):
            self.open_module(key)
            return
        builders = {"painel": (self.build_dashboard, "Painel geral"),
                    "backups": (self.build_backups, "Backups e Transferência"),
                    "admin": (self.build_admin, "Administração e Segurança"),
                    "sobre": (self.build_about, "Sobre")}
        builder, title = builders[key]
        old = self.pages.pop(key, None)
        if old is not None:
            old.destroy()
        self.apply_shell_style()
        frame = tk.Frame(self.content, bg=t.BG)
        self.pages[key] = frame
        builder(frame)
        self._show_frame(key, frame, title)

    # ------------------------------------------------------------------ módulos
    def transfer_blocked(self):
        try:
            settings = config.load()
            if not settings["transferencia_habilitada"]:
                return None
            state = transfer.load_state(paths.transfer_state_path())
        except Exception as error:
            return f"Não foi possível ler o estado da transferência: {error}"
        if not state.get("titular", True):
            return ("Os dados foram exportados para o outro computador (pacote "
                    f"{state.get('ultimo_pacote')}). Este computador está aguardando o pacote "
                    "mais recente do MEGA. Aguarde a sincronização e reabra o programa. Se o outro "
                    "computador não importou nem alterou esses dados, use Backups e Transferência > "
                    "Acessar sincronização > Retomar neste PC.")
        return None

    def send_data_to_other_computer(self):
        if self.busy:
            messagebox.showinfo("Aguarde", "Há uma operação em andamento.", parent=self)
            return
        try:
            settings = config.load()
            if not settings["transferencia_habilitada"]:
                raise transfer.TransferError("Ative a sincronização antes de enviar os dados.")
            state = transfer.load_state(paths.transfer_state_path())
            if not state.get("titular", True):
                raise transfer.TransferError(
                    "Este computador está aguardando os dados do outro. Receba o pacote mais recente "
                    "antes de enviar novamente.")
        except Exception as error:
            messagebox.showerror("Sincronização", str(error), parent=self)
            return
        if not messagebox.askyesno(
                "Enviar dados e ceder a vez",
                "Os módulos serão fechados e os dados atuais serão enviados para a pasta compartilhada. "
                "Este computador ficará bloqueado para edição até receber um pacote mais recente.\n\n"
                "Use esta opção somente quando realmente for trocar para o outro computador. "
                "Aguarde o MEGA concluir a sincronização antes de abrir o outro PC.",
                default="no", parent=self):
            return
        problems = self.close_modules()
        if problems:
            messagebox.showerror(
                "Sincronização não realizada",
                "Não foi possível fechar todos os módulos. Os dados não foram enviados:\n\n"
                + "\n".join(problems),
                parent=self)
            return
        try:
            package = transfer.export_package(
                self.databases(), config.transfer_dir(settings), state,
                paths.transfer_state_path(), APP_VERSION)
        except Exception as error:
            self.log.exception("Falha ao enviar os dados para o outro computador")
            messagebox.showerror(
                "Sincronização não realizada",
                f"Não foi possível enviar os dados: {error}",
                parent=self)
            return
        self.log.info("Transferência manual exportou %s", package)
        messagebox.showinfo(
            "Dados enviados para sincronização",
            f"Pacote criado em:\n{package}\n\nAguarde o MEGA concluir a sincronização "
            "antes de abrir o sistema no outro computador.",
            parent=self)
        self.navigate("backups")

    def resume_on_this_computer(self):
        try:
            settings = config.load()
            if not settings["transferencia_habilitada"]:
                raise transfer.TransferError("A sincronização entre computadores está desativada.")
            self._automatic_sync_startup()
            state_path = paths.transfer_state_path()
            state = transfer.load_state(state_path)
            if state.get("titular", True):
                messagebox.showinfo(
                    "Sincronização", "Este computador já recebeu os dados mais recentes.",
                    parent=self)
                self.navigate("backups")
                return
        except Exception as error:
            self.log.exception("Falha ao verificar os dados antes de retomar")
            messagebox.showerror("Sincronização", str(error), parent=self)
            return
        if not messagebox.askyesno(
                "Retomar neste computador",
                "Só retome se o outro computador NÃO importou este pacote ou já foi fechado sem "
                "fazer alterações. O programa não consegue detectar se o outro PC está usando os dados.\n\n"
                "Se o outro computador importou o pacote e fez alterações, cancele e aguarde que ele "
                "envie um pacote mais recente. Retomar durante o uso simultâneo pode criar divergência "
                "entre os dados.",
                icon="warning", default="no", parent=self):
            return
        try:
            transfer.resume_ownership(
                state, state_path, self.databases(), config.transfer_dir(settings))
        except Exception as error:
            self.log.exception("Falha ao retomar a titularidade neste computador")
            messagebox.showerror("Não foi possível retomar", str(error), parent=self)
            return
        self.log.warning("Titularidade retomada manualmente após confirmação")
        messagebox.showinfo(
            "Computador liberado",
            "Este computador pode voltar a editar os dados. Não use os dois computadores ao mesmo "
            "tempo; para trocar, escolha “Enviar dados e ceder a vez” na tela de sincronização.",
            parent=self)
        self.navigate("backups")

    def _automatic_sync_startup(self):
        self.auto_sync_notice = ""
        try:
            settings = config.load()
            if not settings["transferencia_habilitada"]:
                return
            folder = config.transfer_dir(settings)
            state_path = paths.transfer_state_path()
            packages = transfer.list_packages(folder)
            state = transfer.load_state(state_path, default_titular=not packages)
            if state.get("titular", True):
                return
            if not packages:
                self.auto_sync_notice = "falha"
                return
            own_package_found = False
            for package in packages:
                report = transfer.inspect_package(package, state, self.databases(), APP_VERSION)
                manifest = report["manifesto"]
                if manifest and manifest.get("maquina_origem") == state.get("maquina_id"):
                    own_package_found = True
                    continue
                expected_blocks = (
                    "pacote gerado por este mesmo computador",
                    "pacote já importado ou exportado por este computador (duplicado)",
                    "pacote mais antigo que os dados já sincronizados neste computador",
                )
                if report["bloqueios"] and all(
                        any(block == expected for expected in expected_blocks)
                        for block in report["bloqueios"]):
                    continue
                if report["bloqueios"]:
                    raise transfer.TransferError(
                        f"Não foi possível sincronizar {package.name}: "
                        + "; ".join(report["bloqueios"]))
                backup_folder, manifest = transfer.import_package(
                    package, state, state_path, self.databases(), paths.backups_dir(),
                    APP_VERSION, accept_warnings=True,
                    additional_backup_root=config.additional_backup_dir(settings))
                self.log.info("Sincronização automática importou %s (backup prévio %s)",
                              manifest["id"], backup_folder)
                self.auto_sync_notice = "ok"
                return
            self.auto_sync_notice = "ok" if own_package_found else "falha"
        except Exception as error:
            self.log.exception("Falha na sincronização automática ao iniciar")
            self.auto_sync_notice = "falha"

    def connect_auto_sync(self):
        folder = filedialog.askdirectory(
            parent=self,
            title="Selecione a pasta do MEGA que contém os pacotes do Sistemas Revisa",
            initialdir=str(paths.default_transfer_dir().parent),
        )
        if not folder:
            return
        packages = transfer.list_packages(folder)
        if not packages:
            messagebox.showerror(
                "Sincronização ainda não disponível",
                "Não encontrei pacotes completos nesta pasta. No computador que já possui os dados, "
                "ative a sincronização, use Backups e Transferência > Acessar sincronização > "
                "Enviar dados e ceder a vez e aguarde o MEGA terminar de enviar "
                "o primeiro pacote. Depois, tente novamente.",
                parent=self,
            )
            return
        try:
            state_path = paths.transfer_state_path()
            state = transfer.load_state(state_path, default_titular=False)
            if state.get("titular", True):
                raise transfer.TransferError(
                    "Este computador já é titular dos dados. Não conecte outro computador com os dois "
                    "titulares ao mesmo tempo.")
            settings = config.load()
            settings["pasta_transferencia"] = folder
            settings["transferencia_habilitada"] = True
            config.save(settings)
        except Exception as error:
            messagebox.showerror("Falha ao configurar sincronização", str(error), parent=self)
            return
        self._automatic_sync_startup()
        if self.auto_sync_notice == "falha":
            messagebox.showwarning("Sincronização automática", "Sincronização automática falha", parent=self)
        self.show_login()

    def connect_as_sync_receiver(self):
        folder = filedialog.askdirectory(
            parent=self,
            title="Selecione a pasta do MEGA com os dados do outro computador",
            initialdir=str(paths.default_transfer_dir().parent),
        )
        if not folder:
            return
        packages = transfer.list_packages(folder)
        if not packages:
            messagebox.showwarning(
                "Nenhum pacote encontrado",
                "Ainda não há um pacote completo nesta pasta. No computador que contém a alteração "
                "mais recente, configure a sincronização e use Backups e Transferência > Acessar "
                "sincronização > Enviar dados e ceder a vez. Aguarde o MEGA concluir o envio e tente "
                "novamente.",
                parent=self,
            )
            return
        try:
            state_path = paths.transfer_state_path()
            state = transfer.load_state(state_path, default_titular=True)
            if state.get("ultimo_pacote") is not None or state.get("importados"):
                raise transfer.TransferError(
                    "Este computador já tem um histórico de sincronização. Não é seguro conectá-lo como "
                    "receptor sem uma reconciliação dos dados.")
            package = packages[0]
            report = transfer.inspect_package(package, state, self.databases(), APP_VERSION)
            if report["bloqueios"]:
                raise transfer.TransferError(
                    f"O pacote {package.name} não pode ser importado:\n- "
                    + "\n- ".join(report["bloqueios"]))
            warning = ("\n\nAvisos:\n- " + "\n- ".join(report["avisos"])) if report["avisos"] else ""
            if not messagebox.askyesno(
                    "Receber dados do outro computador",
                    f"Importar o pacote mais recente ({package.name})?\n\n"
                    "O banco atual deste computador será preservado em um backup verificado antes "
                    f"de receber os dados do outro PC.{warning}\n\n"
                    "Confirme somente se este pacote contém os dados corretos e mais recentes.",
                    icon="warning", default="no", parent=self):
                return
            problems = self.close_modules()
            if problems:
                messagebox.showerror("Importação cancelada", "\n".join(problems), parent=self)
                return
            settings = config.load()
            settings["pasta_transferencia"] = str(folder)
            settings["transferencia_habilitada"] = True
            config.save(settings)
            state["titular"] = False
            transfer.save_state(state_path, state)
            backup_folder, manifest = transfer.import_package(
                package, state, state_path, self.databases(), paths.backups_dir(),
                APP_VERSION, accept_warnings=True)
            self.log.info("Este computador recebeu %s como receptor (backup prévio %s)",
                          manifest["id"], backup_folder)
            messagebox.showinfo(
                "Sincronização conectada",
                f"Dados do outro computador recebidos.\nBackup dos dados anteriores:\n{backup_folder}\n\n"
                "Da próxima vez, abra e feche o sistema no computador ativo e aguarde o MEGA "
                "terminar antes de trocar de máquina.",
                parent=self,
            )
            self.navigate("admin")
        except Exception as error:
            self.log.exception("Falha ao conectar este computador como receptor")
            messagebox.showerror(
                "Sincronização não concluída",
                f"{error}\n\nNão edite os dados neste computador até a conexão ser concluída.",
                parent=self,
            )

    def _confirm_legacy_closed(self, key):
        running = [name for name in running_legacy_programs() if key in LEGACY_PROCESSES[name]]
        if not running:
            return True
        return messagebox.askyesno(
            "Programa anterior aberto",
            "Os seguintes programas anteriores estão abertos e usam os mesmos dados:\n\n"
            + "\n".join(running) + "\n\nFeche-os antes de continuar para evitar alterações simultâneas.\n"
            "Continuar mesmo assim?", icon="warning", default="no", parent=self)

    def open_module(self, key):
        blocked = self.transfer_blocked()
        if blocked:
            messagebox.showwarning("Módulo bloqueado", blocked, parent=self)
            return
        record = self.modules.get(key)
        if record is not None:
            if key == MODULE_FOLHA:
                record["instance"].reapply_style()
            else:
                record["instance"].configurar_estilo()
            self._show_frame(key, record["container"], folha.TITLE if key == MODULE_FOLHA else energia.TITLE)
            return
        if key == MODULE_ENERGIA and not self._confirm_energy_database():
            return
        if not self._confirm_legacy_closed(key):
            return
        self.session.require(key)
        container = tk.Frame(self.content, bg=t.BG)
        module_toolbar = tk.Frame(container, bg=t.BG)
        module_toolbar.pack(fill="x")
        t.button(module_toolbar, "← Voltar ao painel", lambda: self.navigate("painel"),
                 kind="secondary").pack(anchor="w", padx=12, pady=(8, 4))
        module_content = tk.Frame(container, bg=t.BG)
        module_content.pack(fill="both", expand=True)
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            if key == MODULE_FOLHA:
                folha.prepare_existing_database()
                instance = folha.create_panel(module_content)
                instance.pack(fill="both", expand=True)
            else:
                instance = energia.create_app(module_content)
        except Exception as error:
            self.log.exception("Falha ao abrir o módulo %s", key)
            container.destroy()
            messagebox.showerror("Falha ao abrir o módulo", f"{error}", parent=self)
            return
        finally:
            self.config(cursor="")
        self.modules[key] = {"container": container, "instance": instance}
        self.log.info("Módulo aberto: %s", key)
        self._show_frame(key, container, folha.TITLE if key == MODULE_FOLHA else energia.TITLE)

    def _confirm_energy_database(self):
        """O login principal já libera o Energia; aqui só se evita criar banco vazio sem confirmação."""
        if energia.db_path().is_file():
            return True
        if not messagebox.askyesno(
                "Banco de Energia e Água não encontrado",
                f"Não encontrei o banco em:\n{energia.db_path()}\n\nCriar um banco NOVO e VAZIO? "
                "Escolha Não se existem dados a restaurar.", icon="warning", default="no", parent=self):
            return False
        self.log.warning("Banco novo do Energia autorizado explicitamente: %s", energia.db_path())
        return True

    def close_modules(self):
        problems = []
        for key in (MODULE_FOLHA, MODULE_ENERGIA):
            record = self.modules.pop(key, None)
            if record is None:
                continue
            try:
                if key == MODULE_FOLHA:
                    record["instance"].close_module()
                else:
                    record["instance"].encerrar()
                self.log.info("Módulo fechado: %s", key)
            except Exception as error:
                self.log.exception("Falha ao fechar o módulo %s", key)
                problems.append(f"{key}: {error}")
            finally:
                if record["container"].winfo_exists():
                    record["container"].destroy()
        return problems

    def commit_open_modules(self):
        record = self.modules.get(MODULE_ENERGIA)
        if record is not None and getattr(record["instance"], "conn", None) is not None:
            record["instance"].conn.commit()

    def on_close(self):
        if self.busy and not messagebox.askyesno(
                "Operação em andamento", "Há uma operação em andamento. Sair mesmo assim?",
                default="no", parent=self):
            return
        problems = self.close_modules()
        if problems:
            messagebox.showwarning("Fechamento dos módulos", "\n".join(problems), parent=self)
        self.session.logout()
        self.log.info("Programa encerrado")
        self.destroy()

    # ------------------------------------------------------------------ dados comuns
    def databases(self):
        return {MODULE_FOLHA: folha.db_path(), MODULE_ENERGIA: energia.db_path()}

    def extra_backup_files(self):
        return {"energia_acesso": energia.access_path(), "folha_assinatura": folha.signing_config_path()}

    def run_in_thread(self, work, done):
        self.busy = True
        self.config(cursor="watch")
        result = {}

        def runner():
            try:
                result["value"] = work()
            except Exception as error:
                result["error"] = error

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()

        def poll():
            if thread.is_alive():
                self.after(150, poll)
                return
            self.busy = False
            self.config(cursor="")
            done(result.get("value"), result.get("error"))

        self.after(150, poll)

    from .pages import build_about, build_admin, build_backups, build_dashboard  # noqa: E402
