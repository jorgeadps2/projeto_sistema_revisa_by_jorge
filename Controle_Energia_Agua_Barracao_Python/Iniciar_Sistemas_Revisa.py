import hashlib
import hmac
import json
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from time import monotonic
from tkinter import messagebox, ttk

from PIL import Image, ImageDraw, ImageTk
from central_windows import fit_program_window, process_tree_ids


BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
FOLHA_DIR = BASE_DIR.parent / "FolhaPagamentoRevisa"
ENERGIA_DIR = BASE_DIR / "Controle_Energia_Agua_Barracao"
LOGO_PATH = BASE_DIR / "assets" / "logo_central_revisa.png"
PAYROLL_DB = (
    Path(os.environ.get("LOCALAPPDATA", Path.home()))
    / "FolhaPagamentoRevisa"
    / "folha_pagamento.db"
)
SIGNING_CONFIG_PATH = (
    Path(os.environ.get("LOCALAPPDATA", Path.home()))
    / "FolhaPagamentoRevisa"
    / "assinatura_digital.json"
)
PASSWORD_ITERATIONS = 600_000
CENTRAL_ACCESS_ARGUMENT = "--central-authenticated"
CENTRAL_VERSION = "1.0"

BLUE = "#004B97"
BLUE_DARK = "#073365"
ORANGE = "#FF6500"
BACKGROUND = "#F3F6FA"
TEXT = "#192B43"
MUTED = "#65758B"
TOOLBAR = "#ECECEC"
COMPANY_NAME = "FTS DISTRIBUIDORA DE PEÇAS LTDA"
CENTRAL_USER = "JORGE"


def request_program_close(process_id):
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )
    user32.EnumWindows.argtypes = (callback_type, wintypes.LPARAM)
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = (
        wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
    )
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = (
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    )
    user32.PostMessageW.restype = wintypes.BOOL
    windows = []
    process_ids = process_tree_ids(process_id)

    @callback_type
    def collect_window(handle, unused):
        owner_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(handle, ctypes.byref(owner_pid))
        if (
            owner_pid.value in process_ids
            and user32.IsWindowVisible(handle)
        ):
            windows.append(handle)
        return True

    if not user32.EnumWindows(collect_window, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    if not windows:
        return False
    for handle in windows:
        if not user32.PostMessageW(handle, 0x0010, 0, 0):
            raise ctypes.WinError(ctypes.get_last_error())
    return True


def verify_payroll_password(password, database_path=PAYROLL_DB):
    if not database_path.is_file():
        raise RuntimeError(
            "Não encontrei o banco de dados da Folha de Pagamento. "
            "Abra a Folha uma vez para inicializar o sistema."
        )

    try:
        with closing(sqlite3.connect(str(database_path))) as connection:
            row = connection.execute(
                "SELECT salt, password_hash FROM app_auth WHERE id=1"
            ).fetchone()
    except sqlite3.Error as error:
        raise RuntimeError(
            f"Não foi possível verificar a senha da Folha de Pagamento: {error}"
        ) from error

    if row is None:
        raise RuntimeError(
            "A senha da Folha de Pagamento ainda não foi cadastrada. "
            "Abra a Folha e cadastre a senha antes de acessar a Central."
        )

    salt, expected_hash = row
    actual_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return hmac.compare_digest(actual_hash, expected_hash)


def signing_expiry_display(today=None):
    unavailable = (
        "Assinatura digital: validade indisponível",
        MUTED,
        "#F7F9FC",
    )
    try:
        with SIGNING_CONFIG_PATH.open(encoding="utf-8") as config_file:
            config = json.load(config_file)
    except (OSError, ValueError):
        return unavailable

    certificate = config.get("certificado")
    expiry_certificate = config.get("validade_certificado")
    if not isinstance(expiry_certificate, str) or not expiry_certificate:
        return unavailable
    if certificate is not None and not isinstance(certificate, str):
        return unavailable
    if certificate and os.path.normcase(os.path.abspath(certificate)) != os.path.normcase(
        os.path.abspath(expiry_certificate)
    ):
        return unavailable
    try:
        expires = datetime.strptime(config["validade"], "%Y-%m-%d").date()
    except (KeyError, TypeError, ValueError):
        return unavailable

    days = (expires - (today or datetime.now().date())).days
    date_text = expires.strftime("%d/%m/%Y")
    if days < 0:
        return (
            f"Assinatura digital VENCEU em {date_text}",
            "#991B1B",
            "#FEF2F2",
        )
    if days <= 30:
        when = "hoje" if days == 0 else f"em {days} dia(s)"
        return (
            f"Assinatura digital vence {when} ({date_text})",
            "#991B1B",
            "#FEF2F2",
        )
    return (
        f"Assinatura digital válida até {date_text} ({days} dias restantes)",
        "#991B1B",
        "#F0FDF4",
    )


class Launcher(tk.Tk):
    def __init__(self):
        if sys.platform == "win32":
            import ctypes
            result = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "Revisa.GerenciadorAdministrativo"
            )
            if result != 0:
                raise OSError(f"Não foi possível configurar o ícone da barra de tarefas: {result}")
        super().__init__()
        self.title("REVISA | Gerenciador Administrativo")
        self.protocol("WM_DELETE_WINDOW", self._close_launcher)
        self.geometry("1100x720")
        self.minsize(900, 600)
        self.configure(bg=BACKGROUND)
        self.withdraw()
        self.active_process = None
        self.pending_program = None
        self.switching_program = False
        self.closing_launcher = False
        self.window_fit_failed = False
        try:
            with Image.open(LOGO_PATH) as source:
                self.logo_source = source.convert("RGBA")
        except OSError as error:
            messagebox.showerror(
                "Logo não encontrada",
                f"Não foi possível carregar a logo da REVISA:\n{LOGO_PATH}\n\n{error}",
                parent=self,
            )
            self.destroy()
            return
        icon = self.logo_source.copy()
        icon.thumbnail((48, 48), Image.Resampling.LANCZOS)
        self.window_icon = ImageTk.PhotoImage(icon, master=self)
        self.iconphoto(True, self.window_icon)
        self.iconbitmap(str(BASE_DIR / "assets" / "revisa.ico"))
        if not self._authenticate():
            self.destroy()
            return
        self._build()
        self.after(300, self._check_active_program)
        self.deiconify()
        self.state("zoomed")

    def _authenticate(self):
        login = tk.Toplevel(self)
        login.title("Acesso ao Sistema")
        login.geometry("720x360")
        login.resizable(False, False)
        login.configure(bg="#E8EDF3")
        login.iconphoto(True, self.window_icon)
        login.iconbitmap(str(BASE_DIR / "assets" / "revisa.ico"))
        login.protocol("WM_DELETE_WINDOW", login.destroy)

        banner = tk.Frame(login, bg=BLUE_DARK, height=72)
        banner.pack(fill="x")
        banner.pack_propagate(False)
        tk.Label(
            banner,
            text="REVISA",
            bg=BLUE_DARK,
            fg="white",
            font=("Segoe UI", 21, "bold"),
        ).pack(side="left", padx=(24, 14), pady=18)
        tk.Frame(banner, bg=ORANGE, width=4).pack(
            side="left", fill="y", pady=17
        )
        tk.Label(
            banner,
            text="Gerenciador Administrativo",
            bg=BLUE_DARK,
            fg="#DCEBFA",
            font=("Segoe UI", 12, "bold"),
        ).pack(side="left", padx=14)
        tk.Frame(login, bg=ORANGE, height=4).pack(fill="x")

        body = tk.Frame(login, bg="#F4F6F9", padx=14, pady=10)
        logo_panel = tk.Frame(
            body,
            bg="white",
            width=138,
            height=138,
            highlightbackground="#D6DEE8",
            highlightthickness=1,
        )
        logo_panel.pack(side="left", anchor="n", padx=(0, 14))
        logo_panel.pack_propagate(False)
        logo_size = self.logo_source.copy()
        logo_size.thumbnail((120, 120), Image.Resampling.LANCZOS)
        self.login_logo = ImageTk.PhotoImage(logo_size, master=login)
        tk.Label(logo_panel, image=self.login_logo, bg="white").pack(
            expand=True, padx=8, pady=8
        )

        form = tk.Frame(body, bg="#F4F6F9")
        form.pack(side="left", fill="both", expand=True)
        style = ttk.Style(login)
        style.configure(
            "Login.TEntry",
            padding=(8, 7),
            fieldbackground="white",
            font=("Segoe UI", 10),
        )
        style.configure(
            "Login.TCombobox",
            padding=(6, 6),
            fieldbackground="white",
            font=("Segoe UI", 10),
        )
        tk.Label(
            form,
            text="Empresa",
            bg="#F4F6F9",
            fg=TEXT,
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        company = ttk.Combobox(
            form,
            values=(COMPANY_NAME,),
            state="readonly",
            style="Login.TCombobox",
        )
        company.current(0)
        company.grid(row=1, column=0, columnspan=3, sticky="ew")

        tk.Label(
            form,
            text="Usuário",
            bg="#F4F6F9",
            fg=TEXT,
            font=("Segoe UI", 9, "bold"),
        ).grid(row=2, column=0, sticky="w", pady=(12, 4))
        tk.Label(
            form,
            text="Senha",
            bg="#F4F6F9",
            fg=TEXT,
            font=("Segoe UI", 9, "bold"),
        ).grid(row=2, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(12, 4))
        username = ttk.Combobox(
            form,
            values=(CENTRAL_USER,),
            state="readonly",
            style="Login.TCombobox",
            width=20,
        )
        username.current(0)
        username.grid(row=3, column=0, sticky="ew")
        password = tk.StringVar()
        password_entry = ttk.Entry(
            form,
            textvariable=password,
            show="*",
            style="Login.TEntry",
        )
        password_entry.grid(row=3, column=1, sticky="ew", padx=(8, 8))
        form.columnconfigure(0, weight=3)
        form.columnconfigure(1, weight=2)
        form.columnconfigure(2, weight=0)

        message = tk.StringVar()
        tk.Label(
            form,
            textvariable=message,
            bg="#F4F6F9",
            fg="#B91C1C",
            wraplength=480,
            justify="left",
            font=("Segoe UI", 9),
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))

        authenticated = {"value": False}

        def submit(event=None):
            try:
                valid = verify_payroll_password(password.get())
            except RuntimeError as error:
                message.set(str(error))
                return
            if not valid:
                messagebox.showerror(
                    "Acesso não autorizado",
                    "Senha incorreta. Verifique a senha e tente novamente.",
                    parent=login,
                )
                password.set("")
                password_entry.focus_set()
                return
            authenticated["value"] = True
            login.destroy()

        tk.Button(
            form,
            text="▶  Entrar",
            command=submit,
            bg="#168447",
            fg="white",
            activebackground="#116D39",
            activeforeground="white",
            relief="flat",
            cursor="hand2",
            font=("Segoe UI", 10, "bold"),
            padx=14,
            pady=8,
        ).grid(row=3, column=2, sticky="ew")
        password_entry.bind("<Return>", submit)
        login.bind("<Escape>", lambda event: login.destroy())

        footer = tk.Frame(login, bg="white", height=84)
        footer.pack(side="bottom", fill="x", padx=10, pady=(0, 8))
        footer.pack_propagate(False)
        tk.Frame(footer, bg="#D6DEE8", height=1).pack(fill="x")
        footer_content = tk.Frame(footer, bg="white")
        footer_content.pack(fill="both", expand=True, padx=5)
        footer_items = (
            ("SISTEMAS REVISA", "Folha de pagamento\nEnergia e água"),
            ("ACESSO PROTEGIDO", "Entre com sua senha\nde administrador"),
            ("VALIDADE E VERSÃO", f"Gerenciador Administrativo\nVersão {CENTRAL_VERSION}"),
        )
        for column, (heading, detail) in enumerate(footer_items):
            footer_content.columnconfigure(column, weight=1, uniform="login_footer")
            panel = tk.Frame(
                footer_content,
                bg="#F7F9FC",
                highlightbackground="#D6DEE8",
                highlightthickness=1,
            )
            panel.grid(row=0, column=column, sticky="nsew", padx=3, pady=(4, 2))
            tk.Label(
                panel,
                text=heading,
                bg="#F7F9FC",
                fg=BLUE_DARK,
                font=("Segoe UI", 8, "bold"),
            ).pack(anchor="w", padx=7, pady=(4, 1))
            tk.Label(
                panel,
                text=detail,
                bg="#F7F9FC",
                fg=MUTED,
                justify="left",
                font=("Segoe UI", 8),
            ).pack(anchor="w", padx=7)
        tk.Label(
            footer_content,
            text="Desenvolvido por: Jorge Alberto de Paula",
            bg="white",
            fg=BLUE_DARK,
            font=("Segoe UI", 8, "bold"),
        ).grid(row=1, column=0, columnspan=3, sticky="w", padx=5, pady=(1, 0))

        body.pack(fill="both", expand=True)
        login.update_idletasks()
        x = max(0, (login.winfo_screenwidth() - login.winfo_width()) // 2)
        y = max(0, (login.winfo_screenheight() - login.winfo_height()) // 2)
        login.geometry(f"+{x}+{y}")
        login.lift()
        login.focus_force()
        login.grab_set()
        login.after(100, password_entry.focus_set)
        self.wait_window(login)
        return authenticated["value"]

    def _build(self):
        self._build_menu()
        toolbar = tk.Frame(self, bg=TOOLBAR, height=62, relief="raised", borderwidth=1)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)
        self.toolbar_images = {}
        self.toolbar_buttons = {}
        self._toolbar_button(
            toolbar, "Folha de pagamento", self.open_payroll, BLUE, "payroll"
        )
        self._toolbar_button(
            toolbar, "Energia e água", self.open_energy, ORANGE, "energy"
        )
        tk.Frame(toolbar, bg="#B8B8B8", width=1).pack(
            side="left", fill="y", padx=5, pady=5
        )
        self._toolbar_button(toolbar, "Sair", self._close_launcher, BLUE_DARK, "exit")
        self.signature_expiry_label = tk.Label(
            toolbar,
            text="",
            anchor="e",
            padx=10,
            font=("Segoe UI", 9, "bold"),
        )
        self.signature_expiry_label.pack(side="right", fill="y", padx=8)
        self._refresh_signature_expiry()
        self._build_status_bar()

        self.home_canvas = tk.Canvas(
            self,
            bg=BACKGROUND,
            highlightthickness=0,
            borderwidth=0,
        )
        self.home_canvas.pack(fill="both", expand=True)
        self.home_canvas.bind("<Configure>", self._render_home)

    def _build_menu(self):
        menu_bar = tk.Menu(self)
        systems_menu = tk.Menu(menu_bar, tearoff=False)
        systems_menu.add_command(
            label="Folha de pagamento",
            command=self.open_payroll,
        )
        systems_menu.add_command(
            label="Energia e água",
            command=self.open_energy,
        )
        menu_bar.add_cascade(label="Sistemas", menu=systems_menu)

        utilities_menu = tk.Menu(menu_bar, tearoff=False)
        utilities_menu.add_command(label="Sair", command=self.destroy)
        menu_bar.add_cascade(label="Utilitários", menu=utilities_menu)

        help_menu = tk.Menu(menu_bar, tearoff=False)
        help_menu.add_command(
            label="Sobre o Gerenciador Administrativo",
            command=lambda: messagebox.showinfo(
                "Sobre o Gerenciador Administrativo",
                f"Gerenciador Administrativo REVISA\nVersão {CENTRAL_VERSION}\n\n"
                "Desenvolvido por: Jorge Alberto de Paula",
                parent=self,
            ),
        )
        menu_bar.add_cascade(label="Ajuda", menu=help_menu)
        self.config(menu=menu_bar)

    def _toolbar_button(self, parent, label, command, accent, icon_name):
        icon = Image.new("RGBA", (72, 72), "#00000000")
        draw = ImageDraw.Draw(icon)
        draw.rounded_rectangle((3, 3, 69, 69), radius=17, fill="#FFFFFF")
        draw.rounded_rectangle(
            (3, 3, 69, 69),
            radius=17,
            outline=f"{accent}35",
            width=2,
        )
        if icon_name == "payroll":
            draw.rounded_rectangle(
                (13, 9, 53, 61), radius=6, fill="#2563EB"
            )
            draw.rounded_rectangle((18, 14, 48, 55), radius=3, fill="#EFF6FF")
            draw.rounded_rectangle((24, 6, 42, 17), radius=3, fill="#38BDF8")
            draw.line((24, 26, 42, 26), fill="#60A5FA", width=3)
            draw.line((24, 34, 39, 34), fill="#60A5FA", width=3)
            draw.line((24, 42, 36, 42), fill="#60A5FA", width=3)
            draw.ellipse((35, 36, 64, 65), fill="#16A34A", outline="#BBF7D0", width=2)
            draw.line((42, 50, 48, 56, 57, 45), fill="white", width=4)
        elif icon_name == "energy":
            draw.polygon(((22, 12), (9, 34), (8, 43), (13, 53), (23, 57),
                          (34, 52), (38, 42), (35, 32)), fill="#0EA5E9")
            draw.arc((13, 32, 32, 52), 55, 170, fill="#BAE6FD", width=3)
            draw.polygon(
                ((48, 8), (31, 37), (44, 37), (36, 64), (64, 28), (50, 28)),
                fill="#FBBF24", outline="#F97316", width=2,
            )
        else:
            draw.rounded_rectangle(
                (13, 11, 42, 61), radius=5, fill="#334155"
            )
            draw.rounded_rectangle((18, 16, 36, 56), radius=2, fill="#93C5FD")
            draw.line((30, 36, 61, 36), fill="#F97316", width=7)
            draw.line((49, 24, 61, 36, 49, 48), fill="#F97316", width=7)
        icon = icon.resize((42, 42), Image.Resampling.LANCZOS)
        self.toolbar_images[icon_name] = ImageTk.PhotoImage(icon, master=self)
        button = tk.Button(
            parent,
            text=label,
            image=self.toolbar_images[icon_name],
            command=command,
            bg=TOOLBAR,
            fg=TEXT,
            activebackground="#DCDCDC",
            activeforeground=TEXT,
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            font=("Segoe UI", 9),
            padx=10,
            pady=4,
            compound="left",
            highlightthickness=0,
        )
        button.pack(side="left", fill="y", padx=2)
        self.toolbar_buttons[icon_name] = button

    def _highlight_program(self, program):
        for name, button in self.toolbar_buttons.items():
            selected = name == program
            button.configure(
                bg=ORANGE if selected else TOOLBAR,
                fg="white" if selected else TEXT,
                activebackground="#E95B00" if selected else "#DCDCDC",
                activeforeground="white" if selected else TEXT,
            )

    def _check_active_program(self):
        if (
            not self.switching_program
            and self.active_process is not None
            and self.active_process.poll() is not None
        ):
            self.active_process = None
            self._highlight_program(None)
            self._refresh_signature_expiry()
        elif not self.switching_program and self.active_process is not None:
            self._fit_active_program()
        self.after(300, self._check_active_program)

    def _fit_active_program(self):
        if (
            sys.platform != "win32"
            or self.state() == "iconic"
            or self.window_fit_failed
        ):
            return
        canvas = self.home_canvas
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 32 or height < 32:
            return
        try:
            fit_program_window(
                self.active_process.pid,
                self.winfo_id(),
                (canvas.winfo_rootx() + 8, canvas.winfo_rooty() + 8,
                 width - 16, height - 16),
            )
        except OSError as error:
            self.window_fit_failed = True
            messagebox.showerror(
                "Falha ao ajustar a janela",
                f"Não foi possível encaixar o sistema na Central.\n\n{error}",
                parent=self,
            )

    def _refresh_signature_expiry(self):
        text, foreground, background = signing_expiry_display()
        self.signature_expiry_label.configure(
            text=text,
            fg=foreground,
            bg=background,
        )

    def _close_launcher(self):
        if self.closing_launcher:
            return
        self.closing_launcher = True
        self.pending_program = None
        if self.active_process is None or self.active_process.poll() is not None:
            self.destroy()
            return
        if self.switching_program:
            return
        self.switching_program = True
        self.close_requested = False
        self.close_deadline = monotonic() + 30
        self._wait_for_program_close()

    def _render_home(self, event):
        width, height = event.width, event.height
        if width < 10 or height < 10:
            return

        canvas = self.home_canvas
        canvas.delete("all")
        panel_width = min(int(width * 0.48), height - 8, 680)
        panel_left = (width - panel_width) // 2
        canvas.create_rectangle(
            panel_left,
            0,
            panel_left + panel_width,
            height,
            fill="white",
            outline="",
        )

        diameter = min(panel_width - 8, height - 12)
        logo_size = int(diameter * 0.98)
        resized_logo = self.logo_source.copy()
        resized_logo.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)
        self.logo_image = ImageTk.PhotoImage(resized_logo, master=canvas)
        canvas.create_image(
            width // 2,
            height // 2,
            image=self.logo_image,
            anchor="center",
        )

    def _build_status_bar(self):
        status = tk.Frame(self, bg="#D0D0D0", height=22)
        status.pack(fill="x", side="bottom")
        status.pack_propagate(False)

        status_fields = (
            ("FTS DISTRIBUIDORA DE PEÇAS LTDA", 3),
            ("JORGE", 1),
            (f"Versão: {CENTRAL_VERSION}", 1),
        )
        for column, (text, weight) in enumerate(status_fields):
            status.columnconfigure(column, weight=weight, uniform="status")
            label = tk.Label(
                status,
                text=text,
                bg="#F4F4F4",
                fg="#333333",
                anchor="w",
                relief="sunken",
                borderwidth=1,
                padx=4,
                font=("Tahoma", 8),
            )
            label.grid(row=0, column=column, sticky="nsew")

        status.columnconfigure(3, weight=2, uniform="status")
        self.status_datetime = tk.Label(
            status,
            bg="#F4F4F4",
            fg="#333333",
            anchor="center",
            relief="sunken",
            borderwidth=1,
            padx=4,
            font=("Tahoma", 8),
        )
        self.status_datetime.grid(row=0, column=3, sticky="nsew")
        self._update_status_datetime()

    def _update_status_datetime(self):
        self.status_datetime.configure(
            text=datetime.now().strftime("%d/%m/%Y %H:%M")
        )
        self.after(30_000, self._update_status_datetime)

    def _start(self, target, args, working_dir, label):
        if not target.is_file():
            messagebox.showerror(
                "Sistema não encontrado",
                f"Não encontrei o arquivo necessário para abrir {label}:\n\n{target}",
                parent=self,
            )
            return
        self.pending_program = (target, args, working_dir, label)
        if self.switching_program:
            return
        if self.active_process is not None and self.active_process.poll() is None:
            self.switching_program = True
            self.close_requested = False
            self.close_deadline = monotonic() + 30
            self._wait_for_program_close()
            return
        self._launch_pending_program()

    def _wait_for_program_close(self):
        if self.active_process.poll() is not None:
            self.active_process = None
            self._highlight_program(None)
            self._refresh_signature_expiry()
            self.switching_program = False
            if self.closing_launcher:
                self.destroy()
            else:
                self._launch_pending_program()
            return
        try:
            if not self.close_requested:
                self.close_requested = request_program_close(self.active_process.pid)
        except OSError as error:
            self.switching_program = False
            self.pending_program = None
            if self.closing_launcher:
                self.closing_launcher = False
                title = "Não foi possível fechar o sistema"
                detail = "Não foi possível fechar o sistema aberto."
            else:
                title = "Não foi possível trocar de sistema"
                detail = "Não foi possível fechar o sistema anterior."
            messagebox.showerror(
                title,
                f"{detail}\n\n{error}",
                parent=self,
            )
            return
        if monotonic() >= self.close_deadline:
            self.switching_program = False
            self.pending_program = None
            if self.closing_launcher:
                self.closing_launcher = False
                title = "Sistema ainda aberto"
                detail = "O sistema aberto não terminou de fechar. Feche-o antes de sair da Central."
            else:
                title = "Sistema anterior ainda aberto"
                detail = (
                    "O sistema anterior não terminou de fechar. "
                    "Conclua as operações ou feche-o antes de tentar novamente."
                )
            messagebox.showwarning(
                title,
                detail,
                parent=self,
            )
            return
        self.after(150, self._wait_for_program_close)

    def _launch_pending_program(self):
        target, args, working_dir, label = self.pending_program
        self.pending_program = None
        self._highlight_program(None)
        self.window_fit_failed = False
        try:
            self.home_canvas.update_idletasks()
            area_x = self.home_canvas.winfo_rootx()
            area_y = self.home_canvas.winfo_rooty()
            area_width = self.home_canvas.winfo_width()
            area_height = self.home_canvas.winfo_height()
            window_width = max(320, area_width - 16)
            window_height = max(240, area_height - 40)
            geometry = (
                f"--central-geometry={window_width}x{window_height}"
                f"+{area_x + 8}+{area_y + 8}"
            )
            args = [*args, geometry]
            self.active_process = subprocess.Popen(args, cwd=working_dir)
            program = {
                "folha_pagamento.py": "payroll",
                "controle_energia_agua.py": "energy",
            }.get(target.name)
            if getattr(sys, "frozen", False):
                program = next(
                    (name for name in ("payroll", "energy")
                     if f"--revisa-program={name}" in args),
                    None,
                )
            self._highlight_program(program)
        except OSError as error:
            messagebox.showerror(
                "Não foi possível abrir o sistema",
                f"O Windows não conseguiu iniciar {label}.\n\n{error}",
                parent=self,
            )

    def open_payroll(self):
        script = FOLHA_DIR / "folha_pagamento.py"
        args = [sys.executable, str(script), CENTRAL_ACCESS_ARGUMENT]
        if getattr(sys, "frozen", False):
            script = Path(sys.executable)
            args = [str(script), "--revisa-program=payroll", CENTRAL_ACCESS_ARGUMENT]
        self._start(
            script,
            args,
            script.parent,
            "a Folha de Pagamento",
        )

    def open_energy(self):
        script = ENERGIA_DIR / "controle_energia_agua.py"
        args = [sys.executable, str(script), CENTRAL_ACCESS_ARGUMENT]
        if getattr(sys, "frozen", False):
            script = Path(sys.executable)
            args = [str(script), "--revisa-program=energy", CENTRAL_ACCESS_ARGUMENT]
        self._start(
            script,
            args,
            script.parent,
            "o Controle de Energia e Água",
        )


def main():
    program = next(
        (value for value in sys.argv if value.startswith("--revisa-program=")),
        None,
    )
    if program is not None:
        import runpy

        modules = {
            "--revisa-program=payroll": "folha_pagamento",
            "--revisa-program=energy": "controle_energia_agua",
        }
        if program not in modules:
            raise ValueError(f"Sistema desconhecido: {program}")
        sys.argv.remove(program)
        runpy.run_module(modules[program], run_name="__main__")
        return
    Launcher().mainloop()


if __name__ == "__main__":
    main()
