"""Área que preenche o espaço disponível e ganha barras de rolagem quando o conteúdo não cabe."""
import tkinter as tk
from tkinter import ttk


def scrollbars_needed(total_w, total_h, need_w, need_h, bar_w, bar_h):
    show_v = need_h > total_h
    show_h = need_w > total_w - (bar_w if show_v else 0)
    if show_h and not show_v:
        show_v = need_h > total_h - bar_h
    return show_v, show_h


class ScrollArea(tk.Frame):
    SELF_SCROLLING = ("Treeview", "Listbox", "Text", "TCombobox", "Combobox")

    def __init__(self, master, bg):
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, bg=bg)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.hbar = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vbar.set, xscrollcommand=self.hbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.window_id = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", self._layout)
        self.inner.bind("<Configure>", self._layout)
        self.bind("<Configure>", self._layout)
        self.bind_all("<MouseWheel>", self._on_wheel, add="+")
        self.bind_all("<Shift-MouseWheel>", self._on_shift_wheel, add="+")

    def _layout(self, _event=None):
        bar_w = self.vbar.winfo_reqwidth()
        bar_h = self.hbar.winfo_reqheight()
        total_w, total_h = self.winfo_width(), self.winfo_height()
        if total_w <= 1 or total_h <= 1:
            return
        need_w, need_h = self.inner.winfo_reqwidth(), self.inner.winfo_reqheight()
        show_v, show_h = scrollbars_needed(total_w, total_h, need_w, need_h, bar_w, bar_h)
        if show_v != bool(self.vbar.winfo_manager()):
            if show_v:
                self.vbar.pack(side="right", fill="y", before=self.canvas)
            else:
                self.vbar.pack_forget()
        if show_h != bool(self.hbar.winfo_manager()):
            if show_h:
                self.hbar.pack(side="bottom", fill="x", before=self.canvas)
            else:
                self.hbar.pack_forget()
        width = max(total_w - (bar_w if show_v else 0), need_w)
        height = max(total_h - (bar_h if show_h else 0), need_h)
        self.canvas.itemconfigure(self.window_id, width=width, height=height)
        self.canvas.configure(scrollregion=(0, 0, width, height))
        if not show_v:
            self.canvas.yview_moveto(0)
        if not show_h:
            self.canvas.xview_moveto(0)

    def _scroll_target(self, event):
        try:
            if not self.winfo_exists() or not self.winfo_ismapped():
                return None
            widget = self.winfo_containing(event.x_root, event.y_root)
            if widget is None or not str(widget).startswith(str(self)):
                return None
            if widget.winfo_class() in self.SELF_SCROLLING:
                return None
        except (KeyError, tk.TclError):
            return None
        return widget

    def _on_wheel(self, event):
        if self._scroll_target(event) is not None and self.vbar.winfo_manager():
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _on_shift_wheel(self, event):
        if self._scroll_target(event) is not None and self.hbar.winfo_manager():
            self.canvas.xview_scroll(int(-event.delta / 120), "units")
