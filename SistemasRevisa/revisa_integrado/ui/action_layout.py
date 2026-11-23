"""Menus de ações e formulários internos compartilhados pelos módulos integrados."""
import tkinter as tk
from tkinter import ttk

from . import theme as t
from .icons import photo


def configure_module_actions(style):
    style.configure("ModuleNav.TFrame", background=t.PAPER)
    for name, selected, padding in (
        ("ModuleNav.TButton", False, (10, 6)),
        ("ModuleSelected.TButton", True, (10, 6)),
        ("Compact.ModuleNav.TButton", False, (6, 3)),
        ("Compact.ModuleSelected.TButton", True, (6, 3)),
        ("ModulePrimary.TButton", False, (10, 6)),
    ):
        normal = t.YELLOW if selected else t.SURFACE
        hover = t.YELLOW_HOVER if selected else t.YELLOW
        style.configure(name, background=normal, foreground=t.NAVY, padding=padding,
                        font=t.FONT_BOLD, bordercolor=t.YELLOW if selected else t.PAPER_BORDER,
                        lightcolor=normal, darkcolor=normal, focuscolor=t.NAVY, relief="flat")
        style.map(name, background=[("disabled", t.STATUS_BG), ("pressed", t.YELLOW_HOVER), ("active", hover)],
                  foreground=[("disabled", t.MUTED), ("active", t.NAVY)])


def group_actions(parent, title, command=None, *, primary=None):
    sources = [
        child for child in parent.winfo_children()
        if isinstance(child, (ttk.Button, ttk.Menubutton))
        and not getattr(child, "_grouped_action", False)
    ]
    if not sources:
        return
    for source in sources:
        if (command is None and isinstance(source, ttk.Button)
                and source.winfo_manager() == "pack" and source.cget("text") == primary):
            source.configure(style="ModulePrimary.TButton")
            source.pack(side="left", padx=(0, 10), pady=4)
            source._grouped_action = True
            sources.remove(source)
            break
    if not sources:
        return
    trigger_class = tk.Button if command is not None else tk.Menubutton
    trigger = trigger_class(
        parent, text=f"{title}  ▾", bg=t.SURFACE, fg=t.NAVY,
        activebackground=t.YELLOW, activeforeground=t.NAVY,
        font=t.FONT_BOLD, relief="flat", bd=0,
        highlightthickness=1, highlightbackground=t.PAPER_BORDER, highlightcolor=t.PRIMARY,
        padx=10, pady=6, cursor="hand2", takefocus=True,
    )
    if command is not None:
        trigger.configure(text=title, command=command)
    if command is None:
        menu = tk.Menu(trigger, tearoff=False, font=("Segoe UI", 10),
                       bg=t.SURFACE, fg=t.TEXT, activebackground=t.YELLOW,
                       activeforeground=t.NAVY)
        trigger.configure(menu=menu)
    icon_name = "folha" if title in {"Folha mensal", "Salários", "Relatórios"} else "admin"
    if title in {"Contas e pagamentos", "Rateios"}:
        icon_name = "energia"
    trigger.action_icon = photo(icon_name, 20, parent)
    trigger.configure(image=trigger.action_icon, compound="left")
    grid_layout = sources[0].winfo_manager() == "grid"
    if grid_layout:
        source_grid = sources[0].grid_info()
        trigger.grid(row=source_grid["row"], column=source_grid["column"], sticky="ew", pady=8)
    else:
        trigger.pack(side="left", padx=(0, 10), pady=4)

    if command is None:
        for source in sources:
            if isinstance(source, ttk.Menubutton) and source.cget("menu"):
                submenu = source.nametowidget(source.cget("menu"))
                submenu.configure(activebackground=t.YELLOW, activeforeground=t.NAVY)
                last = submenu.index("end")
                for index in range(0 if last is None else last + 1):
                    if submenu.type(index) == "command" and submenu.entrycget(index, "label").lower().startswith("excluir"):
                        submenu.entryconfigure(index, foreground=t.DANGER, activeforeground=t.DANGER)

        def refresh():
            menu.delete(0, "end")
            for source in sources:
                if not source.winfo_exists():
                    continue
                options = {"label": source.cget("text"),
                           "state": "disabled" if source.instate(("disabled",)) else "normal"}
                image = source.cget("image")
                if image:
                    options.update(image=image, compound="left")
                if source.cget("text").lower().startswith("excluir"):
                    if menu.index("end") is not None:
                        menu.add_separator()
                    options.update(foreground=t.DANGER, activeforeground=t.DANGER)
                if isinstance(source, ttk.Menubutton):
                    menu.add_cascade(menu=source.cget("menu"), **options)
                else:
                    menu.add_command(command=source.invoke, **options)

        menu.configure(postcommand=refresh)
    for source in sources:
        source._grouped_action = True
        if source.winfo_manager() == "grid":
            source.grid_remove()
        else:
            source.pack_forget()
    if command is None:
        refresh()
    return trigger


class InlineForms:
    def __init__(self, parent, hide_content, restore_content):
        self.parent = parent
        self.hide_content = hide_content
        self.restore_content = restore_content
        self.stack = []

    def open(self):
        if self.stack:
            self.stack[-1][0].pack_forget()
        else:
            self.hide_content()
        outer = tk.Frame(self.parent, bg=t.PAPER)
        outer.pack(fill="both", expand=True)
        header = tk.Frame(outer, bg=t.SURFACE, padx=16, pady=10)
        header.pack(fill="x")
        back = t.button(header, "← Voltar", lambda: None, kind="secondary")
        back.pack(side="left", padx=(0, 14))
        title = t.label(header, "", 14, t.NAVY, True)
        title.pack(side="left")
        canvas = tk.Canvas(outer, bg=t.PAPER, bd=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)
        body = tk.Frame(canvas, bg=t.PAPER, padx=16, pady=16)
        back.configure(command=body.destroy)
        window = canvas.create_window(0, 0, window=body, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        body._inline_title = title
        def layout(_event=None):
            canvas.itemconfigure(window, width=canvas.winfo_width(),
                                 height=max(canvas.winfo_height(), body.winfo_reqheight()))
            canvas.configure(scrollregion=canvas.bbox("all"))

        canvas.bind("<Configure>", layout)
        body.bind("<Configure>", layout)

        def wheel(event):
            widget = body.winfo_containing(event.x_root, event.y_root)
            if widget is not None and str(widget).startswith(str(outer)):
                canvas.yview_scroll(int(-event.delta / 120), "units")

        wheel_binding = outer.bind_all("<MouseWheel>", wheel, add="+")
        self.stack.append((outer, body))

        def closed(event):
            if event.widget is not body:
                return
            outer._root()._unbind(("bind", "all", "<MouseWheel>"), wheel_binding)
            self.stack.remove((outer, body))
            outer.destroy()
            if self.stack:
                self.stack[-1][0].pack(fill="both", expand=True)
            else:
                self.restore_content()

        body.bind("<Destroy>", closed, add="+")
        return body

    def close_all(self):
        while self.stack:
            self.stack[-1][1].destroy()


def configure_form(form, option, *args):
    if isinstance(form, tk.Toplevel):
        return getattr(form, option)(*args)
    if option == "title":
        form._inline_title.configure(text=args[0])
    elif option not in {"transient", "grab_set", "resizable", "geometry", "minsize"}:
        raise ValueError(f"Configuração de formulário desconhecida: {option}")
