import sys
import tkinter as tk
from tkinter import messagebox

from . import APP_NAME, APP_VERSION
from .core import paths
from .core.logs import setup_logging
from .core.security import SingleInstance, ignored_arguments


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    log = setup_logging()
    log.info("Iniciando %s %s (congelado=%s)", APP_NAME, APP_VERSION, paths.is_frozen())
    legacy = ignored_arguments(argv)
    if legacy:
        log.warning("Argumentos legados ignorados (não liberam acesso): %s", ", ".join(legacy))
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Revisa.SistemasRevisa")
        except (AttributeError, OSError):
            pass
    instance = SingleInstance()
    if not instance.acquire():
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(APP_NAME, "O Sistemas Revisa já está aberto neste computador.", parent=root)
        root.destroy()
        log.info("Segunda instância recusada")
        return 1
    try:
        paths.ensure_module_paths()
        from .ui.main_window import MainWindow
        window = MainWindow()
        window.mainloop()
    except Exception:
        log.exception("Erro fatal")
        raise
    finally:
        instance.release()
    return 0
