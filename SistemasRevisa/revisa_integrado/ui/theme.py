"""Tema claro do Sistemas Revisa (estilo de sistema administrativo Windows tradicional)."""
import tkinter as tk

PRIMARY = "#0875C9"
PRIMARY_DARK = "#064B82"
ORANGE = "#FF4B12"
BG = "#F2F4F8"
SURFACE = "#FFFFFF"
SURFACE_ALT = "#F7F9FC"
BORDER = "#D5DCE5"
TEXT = "#20252B"
MUTED = "#667085"
HOVER = "#EAF3FC"
SELECTED = "#DCEBFA"
STATUS_BG = "#E9EDF3"
ACCENT = PRIMARY
ACCENT_HOVER = PRIMARY_DARK
ACCENT_LIGHT = PRIMARY
SUCCESS = "#15803D"
WARNING = "#B45309"
DANGER = "#C62828"

# Paleta da abertura, do acesso e do painel integrado.
NAVY = "#0C1726"
NAVY_HOVER = "#20334A"
YELLOW = "#FFD21F"
YELLOW_HOVER = "#F2C30A"
PAPER = "#F7F6F3"
PAPER_BORDER = "#E4E1DC"
NAV_TEXT = "#DCE5EF"
NAV_MUTED = "#A6B4C6"

FONT = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)
FONT_BOLD = ("Segoe UI Semibold", 10)
FONT_TITLE = ("Segoe UI Semibold", 18)
FONT_SUBTITLE = ("Segoe UI Semibold", 13)

# normal, hover, texto, borda
_BUTTONS = {
    "primary": (PRIMARY, PRIMARY_DARK, "#FFFFFF", PRIMARY_DARK),
    "revisa": (YELLOW, YELLOW_HOVER, NAVY, YELLOW),
    "secondary": ("#F3F5F8", "#E2E8F0", TEXT, "#B9C3D0"),
    "danger": ("#FDECEC", "#F9D5D5", "#B42318", "#E6A3A3"),
}


def button(parent, text, command, kind="primary", **options):
    normal, hover, foreground, border = _BUTTONS[kind]
    widget = tk.Button(parent, text=text, command=command, bg=normal, fg=foreground,
                       activebackground=hover, activeforeground=foreground, relief="flat", bd=0,
                       font=FONT_BOLD, padx=14, pady=5, cursor="hand2", highlightthickness=1,
                       highlightbackground=border, highlightcolor=border, **options)
    widget.bind("<Enter>", lambda _e: widget.configure(bg=hover) if str(widget["state"]) != "disabled" else None)
    widget.bind("<Leave>", lambda _e: widget.configure(bg=normal))
    return widget


def label(parent, text="", size=10, color=TEXT, bold=False, bg=SURFACE, **options):
    family = "Segoe UI Semibold" if bold else "Segoe UI"
    return tk.Label(parent, text=text, bg=bg, fg=color, font=(family, size), **options)


def card(parent, title=None, bg=SURFACE, padding=16):
    frame = tk.Frame(parent, bg=bg, highlightbackground=BORDER, highlightthickness=1, padx=padding, pady=padding)
    if title:
        label(frame, title, 11, PRIMARY_DARK, True, bg=bg).pack(anchor="w")
        tk.Frame(frame, bg=BORDER, height=1).pack(fill="x", pady=(4, 10))
    return frame


def entry(parent, show=None, width=34):
    return tk.Entry(parent, show=show, width=width, bg="#FFFFFF", fg=TEXT, insertbackground=TEXT,
                    relief="flat", highlightthickness=1, highlightbackground="#B9C3D0", highlightcolor=PRIMARY,
                    disabledbackground=SURFACE_ALT, font=("Segoe UI", 11))
