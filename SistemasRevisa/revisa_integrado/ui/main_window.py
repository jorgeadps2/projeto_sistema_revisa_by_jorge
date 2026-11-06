"""Janela principal única do Sistemas Revisa."""
import os
import sqlite3
import subprocess
import sys
import threading
import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path
from time import monotonic
from tkinter import filedialog, messagebox, ttk

from .. import APP_NAME, APP_VERSION
from ..core import backup, config, paths, transfer
from ..core.logs import get_logger
from ..core.security import AttemptLimiter, Session, MODULE_ENERGIA, MODULE_FOLHA
from ..modules import energia, folha
from . import theme as t
from .scroll import ScrollArea

USER_NAME = "JORGE"
COMPANY_NAME = "SISTEMA INTERNO JORGE ALBERTO"
LOGIN_BRAND_WIDTH = 96
LOGIN_BRAND_GAP = 8
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


def monitor_work_area(x, y):
    import ctypes
    from ctypes import wintypes

    class MonitorInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.MonitorFromPoint.argtypes = (wintypes.POINT, wintypes.DWORD)
    user32.MonitorFromPoint.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = (wintypes.HANDLE, ctypes.POINTER(MonitorInfo))
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    monitor = user32.MonitorFromPoint(wintypes.POINT(x, y), 2)
    info = MonitorInfo()
    info.cbSize = ctypes.sizeof(info)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    rect = info.rcWork
    return rect.left, rect.top, rect.right, rect.bottom


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
        self.withdraw()
        self.log = get_logger()
        self.session = Session()
        self.limiter = AttemptLimiter()
        self.sync_limiter = AttemptLimiter()
        self.modules = {}
        self.pages = {}
        self.current = None
        self.images = {}
        self.icon_images = {}
        self.login_size = (520, 250)
        self.clock_job = None
        self.busy = False
        self.meter_reminder_prompted_date = None
        self.title(f"v{APP_VERSION}")
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
        self.bind_class("Toplevel", "<Map>", self._center_open_toplevel, add="+")
        self.auto_sync_notice = ""
        self.auto_sync_resume_pending = False
        self._show_startup_splash()
        try:
            self._automatic_sync_startup(prompt_for_resume=True)
            self._wait_for_startup_splash()
            self.show_login()
        finally:
            self._close_startup_splash()
        if self.current is None:
            self._resize_login_window(*self.login_size)
        self.deiconify()
        self.lift()
        if self._confirm_local_resume():
            self.show_login()

    def _show_startup_splash(self):
        self.startup_splash_started = monotonic()
        self.minsize(0, 0)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#F0F0F0")
        self.geometry("400x80")
        self.startup_splash_label = tk.Label(
            self,
            text="AGUARDE, INICIALIZANDO O SISTEMA...",
            bg="#F0F0F0",
            fg="#000000",
            font=("Segoe UI", 11, "bold"),
        )
        self.startup_splash_label.pack(fill="both", expand=True)
        self._center_window(400, 80)
        self.deiconify()
        self.update()

    def _wait_for_startup_splash(self):
        remaining_ms = 3000 - int((monotonic() - self.startup_splash_started) * 1000)
        if remaining_ms > 0:
            self.after(remaining_ms)

    def _close_startup_splash(self):
        splash_label = getattr(self, "startup_splash_label", None)
        if splash_label is not None and splash_label.winfo_exists():
            splash_label.destroy()
        self.startup_splash_label = None
        self.attributes("-topmost", False)
        self.overrideredirect(False)

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

    # ------------------------------------------------------------------ login
    def _monitor_work_area(self):
        if self.winfo_ismapped():
            x = self.winfo_rootx() + self.winfo_width() // 2
            y = self.winfo_rooty() + self.winfo_height() // 2
        else:
            x, y = self.winfo_pointerxy()
        if sys.platform == "win32":
            try:
                return monitor_work_area(x, y)
            except OSError:
                self.log.exception("Não foi possível identificar o monitor da janela")
        return 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()

    def _center_window(self, width, height):
        self.update_idletasks()
        left, top, right, bottom = self._monitor_work_area()
        screen_w, screen_h = right - left, bottom - top
        width, height = min(width, screen_w - 40), min(height, screen_h - 80)
        x = left + (screen_w - width) // 2
        y = top + (screen_h - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _center_open_toplevel(self, event):
        window = event.widget
        window.update_idletasks()
        width, height = window.winfo_width(), window.winfo_height()
        left, top, right, bottom = self._monitor_work_area()
        screen_w, screen_h = right - left, bottom - top
        width, height = min(width, screen_w - 40), min(height, screen_h - 80)
        x = left + (screen_w - width) // 2
        y = top + (screen_h - height) // 2
        window.geometry(f"{width}x{height}+{x}+{y}")

    def _resize_login_window(self, width=520, height=250):
        try:
            self.state("normal")
        except tk.TclError:
            pass
        self.minsize(480, 230)
        self._center_window(width, height)

    def _resize_shell_window(self):
        width, height = 1320, 820
        left, top, right, bottom = self._monitor_work_area()
        screen_w, screen_h = right - left, bottom - top
        width, height = min(width, screen_w - 40), min(height, screen_h - 80)
        self.minsize(min(980, screen_w - 40), min(600, screen_h - 80))
        self._center_window(width, height)
        self.update_idletasks()
        self.state("zoomed")

    def show_login(self):
        self._clear()
        self.modules.clear()
        self.pages.clear()
        self.current = None
        outer = tk.Frame(self, bg=t.BG)
        outer.pack(fill="both", expand=True)
        box = tk.Frame(outer, bg=t.SURFACE, highlightbackground=t.BORDER, highlightthickness=1)
        box.pack(fill="both", expand=True)
        box.columnconfigure(0, weight=1)
        box.rowconfigure(2, weight=1)
        header = tk.Frame(box, bg=t.PRIMARY, height=44)
        header.grid(row=0, column=0, sticky="ew")
        header.pack_propagate(False)
        heading = tk.Frame(header, bg=t.PRIMARY)
        heading.pack(side="left", fill="y", padx=12, pady=3)
        t.label(heading, "SISTEMAS REVISA", 12, "#FFFFFF", True, bg=t.PRIMARY).pack(anchor="w")
        t.label(heading, "ACESSO AO SISTEMA", 7, "#DCEBFA", True, bg=t.PRIMARY).pack(anchor="w")
        tk.Frame(box, bg=t.ORANGE, height=3).grid(row=1, column=0, sticky="ew")
        content = tk.Frame(box, bg=t.SURFACE, padx=10, pady=6)
        content.grid(row=2, column=0, sticky="nsew")
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)
        footer = self._build_login_footer(box)
        footer.grid(row=3, column=0, sticky="ew")
        brand = tk.Frame(content, bg=t.SURFACE, width=LOGIN_BRAND_WIDTH)
        brand.grid(row=0, column=0, sticky="ns", padx=(0, LOGIN_BRAND_GAP))
        brand.pack_propagate(False)
        logo = self._logo("login", (64, 64))
        if logo:
            tk.Label(brand, image=logo, bg=t.SURFACE).pack(pady=(0, 2))
        t.label(brand, "FTS DISTRIBUIDORA\nDE PEÇAS LTDA", 7, t.PRIMARY_DARK, True,
                bg=t.SURFACE, wraplength=94, justify="center").pack(fill="x")
        body = tk.Frame(content, bg=t.SURFACE)
        body.grid(row=0, column=1, sticky="nsew")
        self.login_body = body
        login_size = (520, 250)
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
        else:
            if state == "ausente":
                login_size = (580, 390)
                self._login_missing_database(body)
            elif state == "sem_senha":
                login_size = (520, 360)
                self._login_form(body, create=True)
            else:
                self._login_form(body, create=False)
        self.login_size = login_size
        self._resize_login_window(*login_size)

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
        form.grid(
            row=0,
            column=0,
            padx=(0, LOGIN_BRAND_WIDTH + LOGIN_BRAND_GAP),
        )
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
        footer = tk.Frame(parent, bg=t.PRIMARY, height=66)
        footer.rowconfigure(0, weight=1)
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
            cell = tk.Frame(footer, bg=t.PRIMARY, padx=7, pady=5)
            cell.grid(row=0, column=index * 2, sticky="nsew")
            content = tk.Frame(cell, bg=t.PRIMARY)
            content.pack(expand=True)
            cell = content
            if index == 0:
                if "developer_robot" not in self.images:
                    from PIL import Image, ImageTk
                    try:
                        with Image.open(paths.asset("robo_desenvolvedor.png")) as source:
                            image = source.convert("RGBA")
                            image.thumbnail((36, 36), Image.Resampling.LANCZOS)
                            self.images["developer_robot"] = ImageTk.PhotoImage(image, master=self)
                    except OSError:
                        self.log.exception("Falha ao carregar a imagem do desenvolvedor")
                        raise
                tk.Label(cell, image=self.images["developer_robot"], bg=t.PRIMARY,
                         borderwidth=0).pack(side="left", padx=(0, 6))
                text_cell = tk.Frame(cell, bg=t.PRIMARY)
                text_cell.pack(side="left")
                cell = text_cell
            t.label(cell, heading, 7, "#FFFFFF", True, bg=t.PRIMARY).pack(anchor="center")
            if value:
                t.label(cell, value, 7, color, bg=t.PRIMARY,
                        wraplength=103 if index == 0 else 145,
                        justify="center").pack(anchor="center", pady=(2, 0))
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
                 font=("Segoe UI", 7), padx=3, pady=1, wraplength=145,
                 justify="center", anchor="center").pack(anchor="center", pady=(2, 0))

    def _login_sync_status(self):
        try:
            settings = config.load()
            if not settings["transferencia_habilitada"]:
                return "Sincronização: desativada", t.MUTED
            state = transfer.load_state(paths.transfer_state_path())
        except Exception as error:
            self.log.exception("Falha ao consultar o status da sincronização no login")
            return "Sincronização: falha", t.DANGER
        if self.auto_sync_notice == "falha":
            return "Sincronização: falha", t.DANGER
        if not state.get("titular", True):
            return "Sincronização: aguardando o outro PC", t.WARNING
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
        self.apply_shell_style()
        self._build_menu()
        self._build_toolbar()
        self._build_status_bar()
        self.content = tk.Frame(self, bg=t.BG)
        self.content.pack(side="top", fill="both", expand=True)
        self.update_header()
        self.navigate("painel")
        self.after_idle(self._prompt_meter_readings)
        self._resize_shell_window()

    def _prompt_meter_readings(self):
        today = date.today()
        if today.day < 5:
            return
        if self.meter_reminder_prompted_date == today:
            return
        previous_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        try:
            settings = config.load()
        except (OSError, ValueError) as error:
            self.log.exception("Falha ao consultar a confirmação da leitura de energia")
            messagebox.showerror(
                "Leituras dos medidores",
                f"Não foi possível verificar a confirmação da leitura:\n{error}",
                parent=self,
            )
            return
        period = f"{previous_month:%Y-%m}"
        if period in settings["leituras_confirmadas"]:
            return
        self.meter_reminder_prompted_date = today
        if self._ask_meter_reading_status(previous_month):
            settings["leituras_confirmadas"].append(period)
            try:
                config.save(settings)
            except (OSError, ValueError) as error:
                self.log.exception("Falha ao salvar a confirmação da leitura de energia")
                messagebox.showerror(
                    "Leitura não confirmada",
                    f"Não foi possível salvar a confirmação:\n{error}",
                    parent=self,
                )
                self.after(24 * 60 * 60 * 1000, self._prompt_meter_readings)
                return
        else:
            self.after(24 * 60 * 60 * 1000, self._prompt_meter_readings)

    def _ask_meter_reading_status(self, period):
        dialog = tk.Toplevel(self)
        dialog.title("Leitura do medidor")
        dialog.configure(bg=t.SURFACE)
        dialog.resizable(False, False)
        dialog.transient(self)
        result = {"ok": False}
        body = tk.Frame(dialog, bg=t.SURFACE, padx=24, pady=20)
        body.pack(fill="both", expand=True)
        t.label(body, "Leitura de energia", 14, t.TEXT, True).pack(anchor="w")
        t.label(
            body,
            f"As leituras referentes a {period:%m/%Y} estão preenchidas e conferidas?",
            10,
            t.MUTED,
            wraplength=360,
            justify="left",
        ).pack(anchor="w", pady=(8, 16))
        buttons = tk.Frame(body, bg=t.SURFACE)
        buttons.pack(fill="x")

        def finish(confirmed):
            result["ok"] = confirmed
            dialog.destroy()

        t.button(buttons, "Leitura OK", lambda: finish(True)).pack(side="left")
        t.button(
            buttons, "Não OK", lambda: finish(False), kind="secondary"
        ).pack(side="left", padx=(8, 0))
        dialog.protocol("WM_DELETE_WINDOW", lambda: finish(False))
        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dialog.winfo_reqwidth()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dialog.winfo_reqheight()) // 3
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
        dialog.grab_set()
        self.wait_window(dialog)
        return result["ok"]

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

    def _build_toolbar(self):
        bar = tk.Frame(self, bg="#F0F0F0", height=78, relief="groove", bd=1)
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)
        shortcuts = (
            ("Painel", "painel", lambda: self.navigate("painel")),
            ("Folha", "folha", lambda: self.navigate(MODULE_FOLHA)),
            ("Energia e Água", "energia", lambda: self.navigate(MODULE_ENERGIA)),
            ("Backups", "backups", lambda: self.navigate("backups")),
            ("Administração", "admin", lambda: self.navigate("admin")),
            ("Sobre", "sobre", lambda: self.navigate("sobre")),
            ("Sair", "sair", self.on_close),
        )
        buttons = []
        for label, icon, command in shortcuts:
            image = self._icon(icon, 28)
            button = tk.Button(
                bar, text=label, image=image or "", compound="top", command=command,
                bg="#F0F0F0", fg=t.TEXT, activebackground="#DCEBFA", activeforeground=t.TEXT,
                relief="flat", bd=0, font=("Segoe UI", 9), padx=8, pady=4,
                highlightthickness=0, cursor="hand2",
            )
            buttons.append(button)
            button.bind("<Enter>", lambda _event, item=button: item.configure(bg="#E3EDF7"))
            button.bind("<Leave>", lambda _event, item=button: item.configure(bg="#F0F0F0"))
        bar.update_idletasks()
        cell_width = max(button.winfo_reqwidth() for button in buttons)
        bar.grid_rowconfigure(0, weight=1)
        for column, button in enumerate(buttons):
            bar.grid_columnconfigure(column, minsize=cell_width, uniform="toolbar")
            button.grid(row=0, column=column, sticky="nsew", padx=2)

    def _menu_change_password(self, dialog):
        try:
            self.session.require()
        except PermissionError:
            self.show_login()
            return
        from .pages import verify_main_password
        if not verify_main_password(
                self, "Alterar senha", "Digite a senha principal para continuar:"):
            return
        dialog(self)

    def open_backup_folder(self):
        from .pages import verify_main_password
        if not verify_main_password(
                self, "Acesso aos backups", "Digite a senha principal para abrir os backups:"):
            return
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
        from .pages import verify_main_password
        if not verify_main_password(
                self, "Alterar senha", "Digite a senha principal para continuar:"):
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
        if getattr(self, "status_user", None) and self.status_user.winfo_exists():
            self.status_user.configure(text=f"Usuário: {self.session.user}  •  sessão desde {started}")
            title = getattr(self, "current_title", PAGE_TITLES.get(self.current, "—"))
            self.status_module.configure(text=f"Módulo: {title}")

    def _show_frame(self, key, frame, title):
        for other in list(self.pages.values()) + [m["container"] for m in self.modules.values()]:
            if other is not frame and other.winfo_exists():
                other.pack_forget()
        frame.pack(fill="both", expand=True)
        self.current = key
        self.current_title = title
        self.update_header()
        if key in (MODULE_FOLHA, MODULE_ENERGIA) and self.state() == "normal":
            self.update_idletasks()
            self._center_window(self.winfo_width(), self.winfo_height())

    def navigate(self, key):
        try:
            self.session.require()
        except PermissionError:
            self.show_login()
            return
        if self.busy:
            messagebox.showinfo("Aguarde", "Há uma operação em andamento.", parent=self)
            return
        if key == "backups":
            from .pages import verify_main_password
            if not verify_main_password(
                    self, "Acesso a backups e transferência",
                    "Digite a senha principal para abrir esta área:"):
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
            if getattr(self, "auto_sync_notice", "") == "falha":
                return ("Não foi possível receber os dados sincronizados: "
                        + getattr(self, "auto_sync_error", "consulte o log da sincronização."))
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
                paths.transfer_state_path(), APP_VERSION, cede_turn=True)
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
            "tempo. Ao fechar, os dois bancos serão enviados automaticamente para a pasta compartilhada.",
            parent=self)
        self.navigate("backups")

    def _confirm_local_resume(self):
        if not self.auto_sync_resume_pending:
            return False
        self.auto_sync_resume_pending = False
        if not messagebox.askyesno(
                "Continuar neste computador?",
                "Este computador enviou os dados ao fechar. Quer continuar usando este PC agora?\n\n"
                "Só confirme se o outro computador não importou este pacote ou está fechado sem "
                "alterações. Se ele estiver usando os dados, trabalhar nos dois PCs pode criar "
                "divergências. A retomada será recusada se os dados locais mudaram ou se houver "
                "um pacote mais recente do outro computador.",
                icon="warning", default="no", parent=self):
            return False
        try:
            settings = config.load()
            state_path = paths.transfer_state_path()
            state = transfer.load_state(state_path)
            transfer.resume_ownership(
                state, state_path, self.databases(), config.transfer_dir(settings))
        except Exception as error:
            self.log.exception("Falha ao retomar a titularidade neste computador")
            self.auto_sync_notice = "falha"
            self.auto_sync_error = str(error)
            messagebox.showerror(
                "Não foi possível continuar neste PC",
                f"Os dados não foram liberados para edição:\n{error}",
                parent=self)
            return False
        self.log.info("Titularidade retomada neste PC após confirmação na abertura")
        return True

    def _automatic_sync_startup(self, prompt_for_resume=False):
        self.auto_sync_notice = ""
        self.auto_sync_error = ""
        self.auto_sync_resume_pending = False
        try:
            settings = config.load()
            if not settings["transferencia_habilitada"]:
                return
            folder = config.transfer_dir(settings)
            state_path = paths.transfer_state_path()
            packages = transfer.list_packages(folder)
            state = transfer.load_state(state_path, default_titular=not packages)
            if not packages:
                if not state.get("titular", True):
                    raise transfer.TransferError(
                        "Nenhum pacote disponível. Aguarde o MEGA concluir a sincronização.")
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
            if (prompt_for_resume and own_package_found
                    and not state.get("titular", True)):
                self.auto_sync_resume_pending = True
            self.auto_sync_notice = "ok" if own_package_found or state.get("titular", True) else "falha"
        except Exception as error:
            self.log.exception("Falha na sincronização automática ao iniciar")
            self.auto_sync_notice = "falha"
            self.auto_sync_error = str(error)

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
                "ative a sincronização e feche o sistema para enviar os dois bancos. "
                "Aguarde o MEGA terminar de enviar "
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
                "mais recente, configure a sincronização e feche o sistema. "
                "Aguarde o MEGA concluir o envio e tente "
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
                # A Folha já tem rolagem própria; o Energia precisa dela em telas menores (notebook).
                scroll_area = ScrollArea(module_content, bg=t.BG)
                scroll_area.pack(fill="both", expand=True)
                instance = energia.create_app(scroll_area.inner)
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
                    target = energia.save_exit_backup()
                    self.log.info("Backup de Energia e Água salvo em %s", target)
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

    def _automatic_sync_shutdown(self):
        if not self.session.authenticated:
            return None
        settings = config.load()
        if not settings["transferencia_habilitada"]:
            return None
        state_path = paths.transfer_state_path()
        state = transfer.load_state(state_path)
        if not state.get("titular", True):
            return None
        package = transfer.export_package(
            self.databases(), config.transfer_dir(settings), state, state_path, APP_VERSION)
        self.log.info("Sincronização automática ao fechar exportou %s", package)
        return package

    def on_close(self):
        if self.busy:
            messagebox.showinfo(
                "Operação em andamento",
                "Aguarde a operação terminar antes de fechar o sistema.",
                parent=self)
            return
        energy_was_open = MODULE_ENERGIA in getattr(self, "modules", {})
        problems = self.close_modules()
        if problems:
            if any(problem.startswith(f"{MODULE_ENERGIA}:") for problem in problems):
                messagebox.showwarning(
                    "Backup não finalizado",
                    "Não foi possível finalizar o backup. O sistema permanecerá aberto.",
                    parent=self)
            else:
                messagebox.showwarning(
                    "Fechamento dos módulos", "\n".join(problems), parent=self)
            return
        try:
            package = self._automatic_sync_shutdown()
        except Exception:
            self.log.exception("Falha na sincronização automática ao fechar")
            messagebox.showerror(
                "Backup não finalizado",
                "Não foi possível finalizar o backup. O sistema permanecerá aberto.",
                parent=self)
            return
        if package is not None:
            messagebox.showinfo(
                "Backup finalizado",
                "Backup finalizado com sucesso.",
                parent=self)
        elif energy_was_open:
            messagebox.showinfo(
                "Backup finalizado",
                "Backup finalizado com sucesso.",
                parent=self)
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
