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
CENTRAL_VERSION = "1.0"

BLUE = "#3B82F6"
BLUE_DARK = "#1D4ED8"
ORANGE = "#FF6500"
BACKGROUND = "#0B1220"
SURFACE = "#111C2E"
SURFACE_ALT = "#16243A"
BORDER = "#24344D"
TEXT = "#E6EDF7"
MUTED = "#8FA3BF"
TOOLBAR = "#0E1726"
ACCENT = "#2563EB"
ACCENT_HOVER = "#1E40AF"
SIDEBAR_HOVER = "#1A2840"
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
        "#475569",
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
        self._configure_dark_style()
        if not self._authenticate():
            self.destroy()
            return
        self._build()
        self.after(300, self._check_active_program)
        self.deiconify()
        self.state("zoomed")

    def _configure_dark_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Login.TEntry",
            padding=(10, 8),
            fieldbackground=SURFACE_ALT,
            foreground=TEXT,
            insertcolor=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
        )
        style.map(
            "Login.TEntry",
            bordercolor=[("focus", BLUE)],
            lightcolor=[("focus", BLUE)],
        )
        style.configure(
            "Login.TCombobox",
            padding=(8, 7),
            fieldbackground=SURFACE_ALT,
            background=SURFACE_ALT,
            foreground=TEXT,
            arrowcolor=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
        )
        style.map(
            "Login.TCombobox",
            fieldbackground=[("readonly", SURFACE_ALT)],
            background=[("readonly", SURFACE_ALT)],
            foreground=[("readonly", TEXT)],
            selectbackground=[("readonly", SURFACE_ALT)],
            selectforeground=[("readonly", TEXT)],
        )
        self.option_add("*TCombobox*Listbox.background", SURFACE_ALT)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", "white")

    def _authenticate(self):
        login = tk.Toplevel(self)
        login.title("Acesso ao Sistema")
        login.resizable(False, False)
        login.configure(bg=BACKGROUND)
        login.iconphoto(True, self.window_icon)
        login.iconbitmap(str(BASE_DIR / "assets" / "revisa.ico"))
        login.protocol("WM_DELETE_WINDOW", login.destroy)

        tk.Frame(login, bg=ACCENT, height=4).pack(fill="x")
        card = tk.Frame(
            login,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=28,
            pady=22,
        )
        card.pack(fill="both", expand=True, padx=18, pady=18)

        header = tk.Frame(card, bg=SURFACE)
        header.pack(fill="x")
        logo = self.logo_source.copy()
        logo.thumbnail((64, 64), Image.Resampling.LANCZOS)
        self.login_logo = ImageTk.PhotoImage(logo, master=login)
        tk.Label(header, image=self.login_logo, bg=SURFACE).pack(
            side="left", padx=(0, 12)
        )
        titles = tk.Frame(header, bg=SURFACE)
        titles.pack(side="left", fill="x")
        tk.Label(
            titles,
            text="REVISA",
            bg=SURFACE,
            fg=TEXT,
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w")
        tk.Label(
            titles,
            text="Gerenciador Administrativo",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor="w")
        tk.Frame(card, bg=BORDER, height=1).pack(fill="x", pady=(16, 6))

        def field_label(text):
            tk.Label(
                card,
                text=text,
                bg=SURFACE,
                fg=MUTED,
                font=("Segoe UI Semibold", 9),
            ).pack(anchor="w", pady=(10, 4))

        field_label("Empresa")
        company = ttk.Combobox(
            card,
            values=(COMPANY_NAME,),
            state="readonly",
            style="Login.TCombobox",
            width=38,
        )
        company.current(0)
        company.pack(fill="x")

        field_label("Usuário")
        username = ttk.Combobox(
            card,
            values=(CENTRAL_USER,),
            state="readonly",
            style="Login.TCombobox",
        )
        username.current(0)
        username.pack(fill="x")

        field_label("Senha")
        password = tk.StringVar()
        password_entry = ttk.Entry(
            card,
            textvariable=password,
            show="*",
            style="Login.TEntry",
        )
        password_entry.pack(fill="x")

        message = tk.StringVar()
        tk.Label(
            card,
            textvariable=message,
            bg=SURFACE,
            fg="#F87171",
            wraplength=340,
            justify="left",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(8, 0))

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
            card,
            text="Entrar",
            command=submit,
            bg=ACCENT,
            fg="white",
            activebackground=ACCENT_HOVER,
            activeforeground="white",
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            font=("Segoe UI Semibold", 11),
            pady=9,
        ).pack(fill="x", pady=(10, 0))
        password_entry.bind("<Return>", submit)
        login.bind("<Escape>", lambda event: login.destroy())

        tk.Label(
            card,
            text="Acesso protegido • use a senha de administrador",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 8),
        ).pack(anchor="center", pady=(14, 0))
        tk.Label(
            card,
            text=(
                "Desenvolvido por: Jorge Alberto de Paula  •  "
                f"Versão {CENTRAL_VERSION}"
            ),
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 8),
        ).pack(anchor="center", pady=(2, 0))

        login.update_idletasks()
        x = max(0, (login.winfo_screenwidth() - login.winfo_reqwidth()) // 2)
        y = max(0, (login.winfo_screenheight() - login.winfo_reqheight()) // 2)
        login.geometry(f"+{x}+{y}")
        login.lift()
        login.focus_force()
        login.grab_set()
        login.after(100, password_entry.focus_set)
        self.wait_window(login)
        return authenticated["value"]

    def _build(self):
        self._build_menu()
        self._build_status_bar()
        self.toolbar_images = {}
        self.toolbar_buttons = {}
        self.selected_program = None

        sidebar = tk.Frame(self, bg=TOOLBAR, width=236)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Frame(self, bg=BORDER, width=1).pack(side="left", fill="y")

        brand = tk.Frame(sidebar, bg=TOOLBAR)
        brand.pack(fill="x", padx=18, pady=(20, 6))
        brand_logo = self.logo_source.copy()
        brand_logo.thumbnail((40, 40), Image.Resampling.LANCZOS)
        self.sidebar_logo = ImageTk.PhotoImage(brand_logo, master=self)
        tk.Label(brand, image=self.sidebar_logo, bg=TOOLBAR).pack(
            side="left", padx=(0, 10)
        )
        brand_text = tk.Frame(brand, bg=TOOLBAR)
        brand_text.pack(side="left")
        tk.Label(
            brand_text,
            text="REVISA",
            bg=TOOLBAR,
            fg=TEXT,
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        tk.Label(
            brand_text,
            text="Gerenciador Administrativo",
            bg=TOOLBAR,
            fg=MUTED,
            font=("Segoe UI", 8),
        ).pack(anchor="w")
        tk.Frame(sidebar, bg=BORDER, height=1).pack(fill="x", padx=16, pady=(12, 14))
        tk.Label(
            sidebar,
            text="SISTEMAS",
            bg=TOOLBAR,
            fg=MUTED,
            font=("Segoe UI Semibold", 8),
        ).pack(anchor="w", padx=22, pady=(0, 6))
        self._toolbar_button(
            sidebar, "Folha de pagamento", self.open_payroll, BLUE, "payroll"
        )
        self._toolbar_button(
            sidebar, "Energia e água", self.open_energy, ORANGE, "energy"
        )
        self._toolbar_button(
            sidebar, "Sair", self._close_launcher, BLUE_DARK, "exit", side="bottom"
        )
        tk.Frame(sidebar, bg=BORDER, height=1).pack(
            side="bottom", fill="x", padx=16, pady=(10, 6)
        )
        self.signature_expiry_label = tk.Label(
            sidebar,
            text="",
            anchor="w",
            justify="left",
            wraplength=184,
            padx=10,
            pady=8,
            font=("Segoe UI", 8, "bold"),
        )
        self.signature_expiry_label.pack(side="bottom", fill="x", padx=16)
        tk.Label(
            sidebar,
            text="CERTIFICADO DIGITAL",
            bg=TOOLBAR,
            fg=MUTED,
            font=("Segoe UI Semibold", 8),
        ).pack(side="bottom", anchor="w", padx=22, pady=(0, 6))
        self._refresh_signature_expiry()

        main = tk.Frame(self, bg=BACKGROUND)
        main.pack(side="left", fill="both", expand=True)
        header = tk.Frame(main, bg=BACKGROUND, height=64)
        header.pack(fill="x", padx=24)
        header.pack_propagate(False)
        self.page_title = tk.Label(
            header,
            text="Painel inicial",
            bg=BACKGROUND,
            fg=TEXT,
            font=("Segoe UI Semibold", 16),
        )
        self.page_title.pack(side="left", pady=(14, 0))
        tk.Label(
            header,
            text=COMPANY_NAME,
            bg=BACKGROUND,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(side="right", pady=(18, 0))
        tk.Frame(main, bg=BORDER, height=1).pack(fill="x", padx=24)

        self.home_canvas = tk.Canvas(
            main,
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

    def _icon_image(self, icon_name, size, tile):
        icon = Image.new("RGBA", (72, 72), "#00000000")
        draw = ImageDraw.Draw(icon)
        draw.rounded_rectangle((3, 3, 69, 69), radius=17, fill=tile)
        if icon_name == "payroll":
            draw.rounded_rectangle((13, 9, 53, 61), radius=6, fill="#2563EB")
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
            draw.rounded_rectangle((13, 11, 42, 61), radius=5, fill="#64748B")
            draw.rounded_rectangle((18, 16, 36, 56), radius=2, fill="#93C5FD")
            draw.line((30, 36, 61, 36), fill="#F87171", width=7)
            draw.line((49, 24, 61, 36, 49, 48), fill="#F87171", width=7)
        return icon.resize((size, size), Image.Resampling.LANCZOS)

    def _toolbar_button(self, parent, label, command, accent, icon_name, side="top"):
        self.toolbar_images[icon_name] = ImageTk.PhotoImage(
            self._icon_image(icon_name, 30, SURFACE_ALT), master=self
        )
        button = tk.Button(
            parent,
            text=f"  {label}",
            image=self.toolbar_images[icon_name],
            command=command,
            bg=TOOLBAR,
            fg=TEXT,
            activebackground=SIDEBAR_HOVER,
            activeforeground=TEXT,
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            font=("Segoe UI Semibold", 10),
            anchor="w",
            padx=12,
            pady=7,
            compound="left",
            highlightthickness=0,
        )
        pack_options = {"pady": (0, 14)} if side == "bottom" else {"pady": 2}
        button.pack(side=side, fill="x", padx=12, **pack_options)

        def hover(_event, inside):
            if self.toolbar_buttons.get(getattr(self, "selected_program", None)) is button:
                return
            button.configure(bg=SIDEBAR_HOVER if inside else TOOLBAR)

        button.bind("<Enter>", lambda event: hover(event, True))
        button.bind("<Leave>", lambda event: hover(event, False))
        self.toolbar_buttons[icon_name] = button

    def _highlight_program(self, program):
        self.selected_program = program
        for name, button in self.toolbar_buttons.items():
            selected = name == program
            button.configure(
                bg=ACCENT if selected else TOOLBAR,
                fg="white" if selected else TEXT,
                activebackground=ACCENT_HOVER if selected else SIDEBAR_HOVER,
                activeforeground="white" if selected else TEXT,
            )
        titles = {"payroll": "Folha de pagamento", "energy": "Energia e água"}
        page_title = getattr(self, "page_title", None)
        if page_title is not None:
            page_title.configure(text=titles.get(program, "Painel inicial"))

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
        self.card_images = {}
        margin = 28
        card_width = max(220, min(400, (width - margin * 3) // 2))
        card_height = 200
        left = max(margin, (width - (card_width * 2 + margin)) // 2)
        top = max(96, int(height * 0.16))

        canvas.create_text(
            left,
            top - 58,
            text=f"Bem-vindo, {CENTRAL_USER.title()}",
            anchor="w",
            fill=TEXT,
            font=("Segoe UI Semibold", 18),
        )
        canvas.create_text(
            left,
            top - 28,
            text="Escolha um sistema para começar. Ele será aberto nesta área.",
            anchor="w",
            fill=MUTED,
            font=("Segoe UI", 10),
        )

        cards = (
            (
                "payroll",
                "Folha de pagamento",
                "Colaboradores, salários, folha mensal,\n"
                "proventos, descontos e relatórios.",
                self.open_payroll,
            ),
            (
                "energy",
                "Energia e água",
                "Leituras, rateios entre inquilinos,\n"
                "recebimentos, relatórios e backup.",
                self.open_energy,
            ),
        )
        for index, (name, title, detail, command) in enumerate(cards):
            x = left + index * (card_width + margin)
            y = top
            tag = f"card_{name}"
            outline_tag = f"{tag}_outline"
            self._round_rect(
                canvas, x, y, x + card_width, y + card_height, 16,
                fill=SURFACE, outline=BORDER, width=1, tags=(tag, outline_tag),
            )
            canvas.create_rectangle(
                x + 18, y + 1, x + card_width - 18, y + 4,
                fill=ACCENT, outline="", tags=tag,
            )
            self.card_images[name] = ImageTk.PhotoImage(
                self._icon_image(name, 56, SURFACE_ALT), master=canvas
            )
            canvas.create_image(
                x + 26, y + 26, image=self.card_images[name], anchor="nw", tags=tag
            )
            canvas.create_text(
                x + 26, y + 104, text=title, anchor="nw", fill=TEXT,
                font=("Segoe UI Semibold", 15), tags=tag,
            )
            canvas.create_text(
                x + 26, y + 136, text=detail, anchor="nw", fill=MUTED,
                font=("Segoe UI", 9), tags=tag,
            )
            canvas.create_text(
                x + card_width - 24, y + 42, text="Abrir  ›", anchor="e",
                fill=BLUE, font=("Segoe UI Semibold", 10), tags=tag,
            )
            canvas.tag_bind(tag, "<Button-1>", lambda _event, run=command: run())
            canvas.tag_bind(
                tag,
                "<Enter>",
                lambda _event, item=outline_tag: (
                    canvas.itemconfigure(item, outline=BLUE, width=2),
                    canvas.configure(cursor="hand2"),
                ),
            )
            canvas.tag_bind(
                tag,
                "<Leave>",
                lambda _event, item=outline_tag: (
                    canvas.itemconfigure(item, outline=BORDER, width=1),
                    canvas.configure(cursor=""),
                ),
            )

        logo_space = height - (top + card_height) - 48
        logo_size = min(logo_space, 220)
        if logo_size >= 90:
            resized_logo = self.logo_source.copy()
            resized_logo.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)
            self.logo_image = ImageTk.PhotoImage(resized_logo, master=canvas)
            canvas.create_image(
                width // 2,
                top + card_height + 24 + logo_space // 2,
                image=self.logo_image,
                anchor="center",
            )

    @staticmethod
    def _round_rect(canvas, x1, y1, x2, y2, radius, **options):
        points = (
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        )
        return canvas.create_polygon(points, smooth=True, **options)

    def _build_status_bar(self):
        status = tk.Frame(self, bg="#080E19", height=26)
        status.pack(fill="x", side="bottom")
        status.pack_propagate(False)
        tk.Frame(status, bg=BORDER, height=1).place(relx=0, rely=0, relwidth=1)

        status_fields = (
            (COMPANY_NAME, 3),
            (CENTRAL_USER, 1),
            (f"Versão: {CENTRAL_VERSION}", 1),
        )
        for column, (text, weight) in enumerate(status_fields):
            status.columnconfigure(column, weight=weight, uniform="status")
            label = tk.Label(
                status,
                text=text,
                bg="#080E19",
                fg=MUTED,
                anchor="w",
                padx=10,
                font=("Segoe UI", 8),
            )
            label.grid(row=0, column=column, sticky="nsew", pady=(1, 0))

        status.columnconfigure(3, weight=2, uniform="status")
        self.status_datetime = tk.Label(
            status,
            bg="#080E19",
            fg=MUTED,
            anchor="e",
            padx=10,
            font=("Segoe UI", 8),
        )
        self.status_datetime.grid(row=0, column=3, sticky="nsew", pady=(1, 0))
        status.rowconfigure(0, weight=1)
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
            if program is None:
                raise ValueError(f"Sistema desconhecido: {target.name}")
            args = [*args, geometry]
            self.active_process = subprocess.Popen(args, cwd=working_dir)
            self._highlight_program(program)
        except OSError as error:
            messagebox.showerror(
                "Não foi possível abrir o sistema",
                f"O Windows não conseguiu iniciar {label}.\n\n{error}",
                parent=self,
            )

    def open_payroll(self):
        script = FOLHA_DIR / "folha_pagamento.py"
        args = [sys.executable, str(script)]
        if getattr(sys, "frozen", False):
            script = Path(sys.executable)
            args = [str(script), "--revisa-program=payroll"]
        self._start(
            script,
            args,
            script.parent,
            "a Folha de Pagamento",
        )

    def open_energy(self):
        script = ENERGIA_DIR / "controle_energia_agua.py"
        args = [sys.executable, str(script)]
        if getattr(sys, "frozen", False):
            script = Path(sys.executable)
            args = [str(script), "--revisa-program=energy"]
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
