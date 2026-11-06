"""Páginas internas da janela principal (funções ligadas a MainWindow como métodos)."""
import json
import os
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .. import APP_NAME, APP_VERSION
from ..core import backup, config, paths, transfer
from ..core.security import MODULE_ENERGIA, MODULE_FOLHA
from ..modules import energia, folha
from . import theme as t


def _scrollable(frame):
    canvas = tk.Canvas(frame, bg=t.BG, highlightthickness=0, bd=0)
    bar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
    inner = tk.Frame(canvas, bg=t.BG, padx=20, pady=16)
    window = canvas.create_window(0, 0, window=inner, anchor="nw")
    canvas.configure(yscrollcommand=bar.set)
    canvas.pack(side="left", fill="both", expand=True)

    def update_bar(_event=None):
        # A barra de rolagem só aparece quando o conteúdo não cabe na janela.
        canvas.configure(scrollregion=canvas.bbox("all"))
        needed = inner.winfo_reqheight() > canvas.winfo_height() > 1
        if needed and not bar.winfo_ismapped():
            bar.pack(side="right", fill="y")
        elif not needed and bar.winfo_ismapped():
            bar.pack_forget()
            canvas.yview_moveto(0)

    inner.bind("<Configure>", update_bar)

    def resize(event):
        canvas.itemconfigure(window, width=event.width)
        update_bar()

    canvas.bind("<Configure>", resize)

    def wheel(event):
        try:
            if not canvas.winfo_exists() or not canvas.winfo_ismapped() or not bar.winfo_ismapped():
                return
            widget = canvas.winfo_containing(event.x_root, event.y_root)
            if widget is not None and str(widget).startswith(str(canvas)):
                canvas.yview_scroll(int(-event.delta / 120), "units")
        except (tk.TclError, KeyError):
            return

    canvas.bind_all("<MouseWheel>", wheel, add="+")
    return inner


def _kv(parent, rows, bg=t.SURFACE):
    grid = tk.Frame(parent, bg=bg)
    grid.pack(fill="x")
    for index, (name, value) in enumerate(rows):
        t.label(grid, name, 9, t.MUTED, True, bg=bg).grid(row=index, column=0, sticky="nw", padx=(0, 14), pady=2)
        t.label(grid, value, 9, t.TEXT, bg=bg, wraplength=980, justify="left").grid(row=index, column=1, sticky="w", pady=2)
    return grid


def _signing_status(warning_days=30):
    text, status, _when = folha.signing_status(warning_days)
    colors = {
        "unavailable": t.MUTED,
        "expired": t.DANGER,
        "warning": t.WARNING,
        "ok": t.SUCCESS,
    }
    return text, colors[status]


def verify_main_password(self, title="Acesso protegido", prompt="Digite a senha principal:"):
    remaining = self.sync_limiter.remaining_lock()
    if remaining > 0:
        messagebox.showwarning(
            title,
            f"Muitas tentativas. Aguarde {int(remaining) + 1} segundos.",
            parent=self,
        )
        return False
    password = simpledialog.askstring(
        title,
        prompt,
        show="•",
        parent=self,
    )
    if password is None:
        return False
    try:
        valid = folha.verify_password(password)
    except Exception as error:
        self.log.exception("Falha ao validar a senha para acessar uma área protegida")
        messagebox.showerror(title, str(error), parent=self)
        return False
    finally:
        password = None
    if not valid:
        self.sync_limiter.failure()
        self.log.warning("Senha principal recusada ao acessar uma área protegida")
        messagebox.showerror(title, "Senha principal incorreta.", parent=self)
        return False
    self.sync_limiter.success()
    return True


def _verify_sync_password(self):
    return verify_main_password(
        self,
        "Acesso à sincronização",
        "Digite a senha principal para acessar a sincronização:",
    )


# ---------------------------------------------------------------------- painel
def build_dashboard(self, frame):
    canvas = tk.Frame(frame, bg="#F3F6FB")
    canvas.pack(fill="both", expand=True)
    logo_panel = tk.Frame(canvas, bg=t.SURFACE)
    logo_panel.place(relx=0.5, rely=0.5, anchor="center")
    logo_label = tk.Label(logo_panel, bg=t.SURFACE, borderwidth=0)
    logo_label.pack()

    try:
        from PIL import Image, ImageTk

        with Image.open(paths.asset("logo_central_revisa.png")) as source:
            original = source.convert("RGBA")
    except OSError:
        self.log.exception("Falha ao carregar a logo do painel principal")
        t.label(canvas, "Não foi possível carregar a imagem do painel.", 11, t.DANGER,
                bg="#F3F6FB").place(relx=0.5, rely=0.5, anchor="center")
        return

    last_size = None

    def resize_logo(event):
        nonlocal last_size
        size = min(int(event.width * 0.5), int(event.height * 0.96))
        if size < 1 or size == last_size:
            return
        last_size = size
        image = original.copy()
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image, master=self)
        self.images["dashboard"] = photo
        logo_label.configure(image=photo, width=image.width, height=image.height)

    canvas.bind("<Configure>", resize_logo)


# ---------------------------------------------------------------------- backups e transferência
def build_backups(self, frame):
    toolbar = tk.Frame(frame, bg=t.BG)
    toolbar.pack(fill="x")
    t.button(toolbar, "← Voltar ao painel", lambda: self.navigate("painel"),
             kind="secondary").pack(anchor="w", padx=12, pady=(8, 4))
    inner = _scrollable(frame)
    section = t.card(inner, "Backups verificáveis")
    section.pack(fill="x")
    t.label(section, f"Pasta: {paths.backups_dir()}", 9, t.MUTED, wraplength=760, justify="left").pack(anchor="w")
    t.label(section, "Cada backup é feito pela API de backup do SQLite, recebe um manifesto com SHA-256 e "
            "verificação de integridade, e nunca é apagado pelo programa.", 9, t.MUTED,
            wraplength=760, justify="left").pack(anchor="w", pady=(2, 10))
    actions = tk.Frame(section, bg=t.SURFACE)
    actions.pack(fill="x", pady=(0, 8))
    additional_path = t.label(section, "Cópia adicional: desativada", 9, t.MUTED,
                              wraplength=760, justify="left")
    additional_path.pack(anchor="w", pady=(0, 6))
    additional_actions = tk.Frame(section, bg=t.SURFACE)
    additional_actions.pack(fill="x", pady=(0, 8))
    tree = ttk.Treeview(section, style="Shell.Treeview", columns=("data", "motivo", "status", "pasta"),
                        show="headings", height=7)
    for column, text, width in (("data", "Data", 140), ("motivo", "Motivo", 200), ("status", "Situação", 160), ("pasta", "Pasta", 360)):
        tree.heading(column, text=text)
        tree.column(column, width=width, anchor="w")
    tree.pack(fill="x")
    message = t.label(section, "", 9, t.MUTED, wraplength=760, justify="left")
    message.pack(anchor="w", pady=(8, 0))

    def refresh_additional_path():
        try:
            settings = config.load()
        except ValueError as error:
            additional_path.configure(text=f"Configuração inválida: {error}", fg=t.DANGER)
            return None
        folder = config.additional_backup_dir(settings)
        additional_path.configure(
            text=f"Cópia adicional: {folder or 'desativada'}",
            fg=t.MUTED,
        )
        return settings

    def choose_additional_path():
        settings = refresh_additional_path()
        if settings is None:
            return
        chosen = filedialog.askdirectory(
            parent=self,
            title="Escolha a pasta para a cópia adicional dos backups",
            initialdir=str(paths.backups_dir().parent),
        )
        if not chosen:
            return
        chosen_path = Path(chosen).resolve()
        primary_root = paths.backups_dir().resolve()
        if chosen_path == primary_root or primary_root in chosen_path.parents:
            messagebox.showerror(
                "Pasta inválida",
                "Escolha uma pasta fora da pasta principal de backups.",
                parent=self,
            )
            return
        settings["pasta_backup_adicional"] = chosen
        try:
            config.save(settings)
        except OSError as error:
            messagebox.showerror("Backup", f"Não foi possível salvar a configuração: {error}", parent=self)
            return
        refresh_additional_path()

    def disable_additional_path():
        settings = refresh_additional_path()
        if settings is None:
            return
        settings["pasta_backup_adicional"] = ""
        try:
            config.save(settings)
        except OSError as error:
            messagebox.showerror("Backup", f"Não foi possível salvar a configuração: {error}", parent=self)
            return
        refresh_additional_path()

    def create_backup():
        folder, manifest = backup.create_backup(
            self.databases(), paths.backups_dir(), APP_VERSION,
            "manual", self.extra_backup_files())
        mirror_folder = None
        try:
            settings = config.load()
        except ValueError as error:
            return folder, manifest, None, ValueError(
                f"Não foi possível ler a pasta de backup adicional: {error}")
        additional_root = config.additional_backup_dir(settings)
        if additional_root:
            try:
                mirror_folder = backup.mirror_backup(folder, additional_root)
            except (OSError, ValueError) as error:
                return folder, manifest, None, error
        return folder, manifest, mirror_folder, None

    def refresh():
        tree.delete(*tree.get_children())
        for folder, manifest in backup.list_backups(paths.backups_dir()):
            if manifest is None:
                tree.insert("", "end", iid=str(folder), values=("—", "—", "manifesto ilegível", folder.name))
                continue
            state = "com problemas" if manifest.get("problemas") else "ok"
            tree.insert("", "end", iid=str(folder), values=(manifest.get("criado_em", ""), manifest.get("motivo", ""), state, folder.name))

    def create():
        try:
            self.commit_open_modules()
        except Exception as error:
            messagebox.showerror("Backup", f"Não foi possível gravar as alterações pendentes: {error}", parent=self)
            return
        message.configure(text="Criando backup…", fg=t.MUTED)

        def done(value, error):
            if error:
                self.log.error("Falha no backup manual: %s", error)
                message.configure(text=f"Falha no backup: {error}", fg=t.DANGER)
                return
            folder, manifest, mirror_folder, mirror_error = value
            self.log.info("Backup manual criado em %s", folder)
            if mirror_folder:
                self.log.info("Cópia adicional do backup criada em %s", mirror_folder)
            warnings = list(manifest["problemas"])
            if mirror_error:
                self.log.error("Backup adicional falhou; backup principal preservado em %s: %s",
                               folder, mirror_error)
                warnings.append(f"Cópia adicional falhou: {mirror_error}")
            if warnings:
                message.configure(
                    text=f"Backup principal criado em {folder} com avisos:\n- " + "\n- ".join(warnings),
                    fg=t.WARNING,
                )
            elif mirror_folder and not mirror_error:
                message.configure(text=f"Backup criado e verificado em:\n{folder}\nCópia adicional:\n{mirror_folder}", fg=t.SUCCESS)
            elif not mirror_error:
                message.configure(text=f"Backup criado e verificado em {folder}", fg=t.SUCCESS)
            if section.winfo_exists():
                refresh()

        self.run_in_thread(create_backup, done)

    def verify():
        selected = tree.selection()
        if not selected:
            message.configure(text="Selecione um backup na lista.", fg=t.WARNING)
            return
        ok, problems, _ = backup.verify_backup(selected[0])
        message.configure(text="Backup íntegro: hashes e integridade conferem." if ok
                          else "Problemas:\n- " + "\n- ".join(problems), fg=t.SUCCESS if ok else t.DANGER)

    def open_folder():
        folder = paths.backups_dir()
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder))

    t.button(actions, "Criar backup agora", create).pack(side="left")
    t.button(actions, "Verificar selecionado", verify, kind="secondary").pack(side="left", padx=6)
    t.button(actions, "Abrir pasta de backups", open_folder, kind="secondary").pack(side="left")
    t.button(additional_actions, "Escolher pasta adicional…", choose_additional_path,
             kind="secondary").pack(side="left")
    t.button(additional_actions, "Desativar cópia adicional", disable_additional_path,
             kind="secondary").pack(side="left", padx=6)
    refresh_additional_path()
    refresh()

    guide = t.card(inner, "Como restaurar um backup")
    guide.pack(fill="x", pady=(12, 0))
    t.label(guide, "1. Feche o Sistemas Revisa.\n"
            "2. Verifique o backup escolhido com o botão \"Verificar selecionado\".\n"
            f"3. Copie o banco atual para um lugar seguro (por exemplo, renomeando com a data).\n"
            f"4. Copie folha.db para {folha.db_path()} (renomeando para folha_pagamento.db) e/ou "
            f"energia.db para {energia.db_path()} (renomeando para controle_energia_agua.db).\n"
            "5. Abra o sistema e confira os dados. O backup original permanece intacto.",
            9, t.TEXT, wraplength=760, justify="left").pack(anchor="w")

    _build_transfer(self, inner)


def _build_transfer(self, inner):
    section = t.card(inner, "Transferência entre computadores")
    section.pack(fill="x", pady=(12, 0))
    t.label(section, "Esta área contém informações e acesso à pasta compartilhada.",
            9, t.MUTED, wraplength=760, justify="left").pack(anchor="w")
    t.button(section, "Acessar sincronização…",
             lambda: _unlock_transfer(self, section), kind="secondary").pack(anchor="w", pady=(8, 0))


def _unlock_transfer(self, section):
    if not _verify_sync_password(self):
        return
    for child in section.winfo_children():
        child.destroy()
    _show_transfer_details(self, section)


def _show_transfer_details(self, section):
    try:
        settings = config.load()
    except ValueError as error:
        t.label(section, str(error), 10, t.DANGER, wraplength=760).pack(anchor="w")
        return
    folder = config.transfer_dir(settings)
    t.label(section, "O sistema recebe automaticamente um pacote mais recente ao abrir e envia os dois "
            "bancos ao fechar; você pode reabrir no mesmo computador quantas vezes quiser. O botão abaixo "
            "cede a vez ao outro computador. Use "
            "somente um computador por vez e espere o MEGA concluir a sincronização antes de abrir o outro. "
            "Senhas e configurações de assinatura nunca são transferidas.", 9, t.MUTED,
            wraplength=760, justify="left").pack(anchor="w")
    t.label(section, f"Pasta compartilhada: {folder}", 9, t.MUTED, wraplength=760, justify="left").pack(anchor="w", pady=(2, 8))
    if not settings["transferencia_habilitada"]:
        t.label(section, "A sincronização entre computadores está desativada. Configure-a em Administração e Segurança.",
                10, t.WARNING, wraplength=760, justify="left").pack(anchor="w")
        return
    try:
        state = transfer.load_state(paths.transfer_state_path())
    except transfer.TransferError as error:
        t.label(section, str(error), 10, t.DANGER, wraplength=760).pack(anchor="w")
        return
    holder = state.get("titular", True)
    _kv(section, (
        ("Este computador", f"{state.get('computador')} ({state['maquina_id'][:8]})"),
        ("Permissão de edição", "Liberada" if holder else "Aguardando os dados mais recentes"),
        ("Último pacote", state.get("ultimo_pacote") or "nenhum"),
    ))
    tree = ttk.Treeview(section, style="Shell.Treeview", columns=("pacote", "origem", "data"), show="headings", height=6)
    for column, text, width in (("pacote", "Pacote", 380), ("origem", "Origem", 160), ("data", "Criado em", 160)):
        tree.heading(column, text=text)
        tree.column(column, width=width, anchor="w")
    tree.pack(fill="x")
    message = t.label(section, "", 9, t.MUTED, wraplength=760, justify="left")
    message.pack(anchor="w", pady=(8, 0))
    message.configure(
        text=("Este computador pode editar. Ao fechar, os dois bancos serão enviados automaticamente."
              if holder else "Este computador aguarda o pacote mais recente e não pode editar."),
        fg=t.SUCCESS if holder else t.WARNING,
    )
    for package in transfer.list_packages(folder):
        manifest, _ = transfer.read_package(package)
        tree.insert("", "end", iid=str(package), values=(
            package.name, (manifest or {}).get("computador_origem", "?"), (manifest or {}).get("criado_em", "incompleto")))

    if holder:
        t.button(section, "Enviar dados e ceder a vez…",
                 self.send_data_to_other_computer, kind="secondary").pack(anchor="w", pady=(10, 0))
    else:
        t.button(section, "Retomar neste PC…",
                 self.resume_on_this_computer, kind="secondary").pack(anchor="w", pady=(10, 0))

    def open_shared_folder():
        try:
            if not Path(folder).is_dir():
                raise FileNotFoundError(
                    "A pasta não existe neste computador. Se a pasta do MEGA mudou de lugar, "
                    "reconfigure a sincronização em Administração e Segurança.")
            os.startfile(str(folder))
        except OSError as error:
            self.log.error("Falha ao abrir a pasta compartilhada %s: %s", folder, error)
            messagebox.showerror("Pasta compartilhada", f"Não foi possível abrir:\n{folder}\n\n{error}", parent=self)

    t.button(section, "Abrir pasta compartilhada", open_shared_folder,
             kind="secondary").pack(anchor="w", pady=(10, 0))


# ---------------------------------------------------------------------- administração
def build_admin(self, frame):
    inner = _scrollable(frame)
    session = t.card(inner, "Sessão")
    session.pack(fill="x")
    _kv(session, (
        ("Usuário", self.session.user),
        ("Início", self.session.started.strftime("%d/%m/%Y %H:%M:%S")),
        ("Folha de Pagamento", "liberada"),
        ("Energia e Água", "liberado"),
    ))

    checks = t.card(inner, "Bancos de dados")
    checks.pack(fill="x", pady=(12, 0))
    _kv(checks, (
        ("Folha", str(folha.db_path())),
        ("Energia e Água", str(energia.db_path())),
        ("Dados do sistema", str(paths.app_data_dir())),
        ("Logs", str(paths.logs_dir())),
    ))
    result = t.label(checks, "", 9, t.MUTED, wraplength=760, justify="left")

    def integrity():
        lines = []
        for key, path in self.databases().items():
            if not Path(path).is_file():
                lines.append(f"{key}: banco ausente")
            else:
                lines.append(f"{key}: integridade {backup.integrity_check(path)}")
        result.configure(text="\n".join(lines), fg=t.SUCCESS if all(l.endswith(" ok") for l in lines) else t.DANGER)
        self.log.info("Verificação de integridade: %s", "; ".join(lines))

    t.button(checks, "Verificar integridade (somente leitura)", integrity, kind="secondary").pack(anchor="w", pady=(10, 0))
    result.pack(anchor="w", pady=(6, 0))

    transfer_box = t.card(inner, "Sincronização entre computadores")
    transfer_box.pack(fill="x", pady=(12, 0))
    t.label(transfer_box, "A configuração é protegida pela senha principal. Com a sincronização ativa, "
            "os dois bancos são enviados ao fechar e recebidos ao abrir no outro computador.",
            9, t.MUTED, wraplength=760, justify="left").pack(anchor="w")
    t.button(transfer_box, "Acessar sincronização…",
             lambda: _unlock_admin_sync(self, transfer_box), kind="secondary").pack(anchor="w", pady=(8, 0))


def _unlock_admin_sync(self, transfer_box):
    if not _verify_sync_password(self):
        return
    for child in transfer_box.winfo_children():
        child.destroy()
    _build_admin_sync_controls(self, transfer_box)


def _build_admin_sync_controls(self, transfer_box):
    try:
        settings = config.load()
    except ValueError as error:
        t.label(transfer_box, str(error), 10, t.DANGER).pack(anchor="w")
        return
    t.label(transfer_box, f"Sincronização entre computadores: {'ATIVA' if settings['transferencia_habilitada'] else 'desativada'}\n"
            f"Pasta: {config.transfer_dir(settings)}", 10, t.TEXT, justify="left").pack(anchor="w")
    buttons = tk.Frame(transfer_box, bg=t.SURFACE)
    buttons.pack(fill="x", pady=(10, 0))

    def toggle():
        enable = not settings["transferencia_habilitada"]
        state_path = paths.transfer_state_path()
        try:
            if enable and not messagebox.askyesno(
                    "Sincronização entre computadores",
                    "Ativar o envio automático dos bancos da Folha e de Energia e Água ao fechar "
                    "e o recebimento ao abrir no outro computador?\n\n"
                    "Use somente um computador por vez e espere o MEGA terminar de sincronizar antes "
                    "de trocar de máquina.", default="no", parent=self):
                return
            if enable and not state_path.exists():
                packages = transfer.list_packages(config.transfer_dir(settings))
                if packages:
                    transfer.load_state(state_path, default_titular=False)
                elif not messagebox.askyesno(
                        "Primeiro computador",
                        "Não encontrei um pacote nesta pasta. Este computador contém os dados originais "
                        "e será o primeiro titular da sincronização?\n\nAtive esta opção somente no PC que "
                        "já possui os dados corretos. No outro PC, conecte depois que o primeiro pacote "
                        "aparecer na pasta compartilhada.",
                        icon="warning", default="no", parent=self):
                    return
                else:
                    transfer.load_state(state_path, default_titular=True)
            elif not enable:
                state = transfer.load_state(state_path)
                if not state.get("titular", True):
                    messagebox.showwarning(
                        "Sincronização não pode ser desativada",
                        "Este computador não possui a versão mais recente. Aguarde e abra o pacote "
                        "sincronizado antes de desativar.",
                        parent=self,
                    )
                    return
                elif not messagebox.askyesno(
                        "Desativar sincronização entre computadores",
                        "Desativar a sincronização? Os dados deixarão de ser enviados e recebidos.",
                        default="no", parent=self):
                    return
            settings["transferencia_habilitada"] = enable
            config.save(settings)
            self.log.warning("Sincronização entre computadores %s", "ativada" if enable else "desativada")
            if enable:
                self._automatic_sync_startup()
            self.navigate("admin")
        except Exception as error:
            self.log.exception("Falha ao alterar sincronização automática")
            messagebox.showerror("Sincronização", str(error), parent=self)

    def choose_folder():
        if settings["transferencia_habilitada"]:
            messagebox.showwarning(
                "Sincronização ativa",
                "Desative a sincronização antes de trocar a pasta compartilhada.",
                parent=self,
            )
            return
        chosen = filedialog.askdirectory(parent=self, title="Pasta de transferência (sincronizada pelo MEGA)",
                                         initialdir=str(config.transfer_dir(settings).parent))
        if not chosen:
            return
        settings["pasta_transferencia"] = chosen
        config.save(settings)
        self.log.info("Pasta de transferência alterada para %s", chosen)
        self.navigate("admin")

    t.button(buttons, "Desativar sincronização" if settings["transferencia_habilitada"]
             else "Ativar sincronização…", toggle,
             kind="secondary").pack(side="left")
    t.button(buttons, "Escolher pasta compartilhada…", choose_folder, kind="secondary").pack(side="left", padx=6)
    t.button(buttons, "Conectar como receptor…", self.connect_as_sync_receiver,
             kind="secondary").pack(side="left", padx=6)


def change_main_password(self):
    win = tk.Toplevel(self)
    win.title("Alterar senha principal")
    win.configure(bg=t.SURFACE)
    win.resizable(False, False)
    win.transient(self)
    body = tk.Frame(win, bg=t.SURFACE, padx=26, pady=20)
    body.pack(fill="both", expand=True)
    t.label(body, "Alterar senha principal", 14, t.TEXT, True).pack(anchor="w")
    t.label(body, "Usada no Sistemas Revisa, na Folha e no Gerenciador anterior.", 9, t.MUTED).pack(anchor="w", pady=(0, 8))
    fields = []
    for name in ("Senha atual", f"Nova senha (mínimo {folha.min_password_length()} caracteres)", "Confirme a nova senha"):
        t.label(body, name, 9, t.MUTED, True).pack(anchor="w", pady=(6, 3))
        field = t.entry(body, show="•")
        field.pack(fill="x", ipady=4)
        fields.append(field)
    message = t.label(body, "", 9, t.DANGER, wraplength=320)
    message.pack(fill="x", pady=(6, 0))

    def save():
        current, new, confirm = (field.get() for field in fields)
        for field in fields:
            field.delete(0, "end")
        try:
            folha.set_password(new, confirm, current_password=current)
        except Exception as error:
            message.configure(text=str(error))
            self.log.warning("Alteração da senha principal recusada")
            return
        self.log.info("Senha principal alterada")
        win.destroy()
        messagebox.showinfo("Senha alterada", "Senha principal alterada com sucesso.", parent=self)

    buttons = tk.Frame(body, bg=t.SURFACE)
    buttons.pack(fill="x", pady=(10, 0))
    t.button(buttons, "Salvar", save).pack(side="left")
    t.button(buttons, "Cancelar", win.destroy, kind="secondary").pack(side="left", padx=6)
    for field in fields:
        field.bind("<Return>", lambda _e: save())
    fields[0].focus_set()
    win.update_idletasks()
    x = self.winfo_rootx() + (self.winfo_width() - win.winfo_reqwidth()) // 2
    y = self.winfo_rooty() + (self.winfo_height() - win.winfo_reqheight()) // 3
    win.geometry(f"+{max(0, x)}+{max(0, y)}")
    win.grab_set()
    return win


# ---------------------------------------------------------------------- sobre
def build_about(self, frame):
    inner = _scrollable(frame)
    heading = tk.Frame(inner, bg=t.BG)
    heading.pack(fill="x", pady=(0, 14))
    icon = self._icon("sobre", 32)
    if icon:
        tk.Label(heading, image=icon, bg=t.BG).pack(side="left", padx=(0, 10))
    title = tk.Frame(heading, bg=t.BG)
    title.pack(side="left", fill="x", expand=True)
    t.label(title, "Sobre o REVISA", 18, t.PRIMARY_DARK, True, bg=t.BG).pack(anchor="w")
    t.label(title, "Informações do sistema, módulos instalados e armazenamento.", 9, t.MUTED,
            bg=t.BG).pack(anchor="w", pady=(3, 0))

    try:
        folha_version = folha.module().APP_VERSION
        energia_version = energia.module().APP_VERSION
    except Exception:
        folha_version = energia_version = "?"

    cards = tk.Frame(inner, bg=t.BG)
    cards.pack(fill="both", expand=True)
    cards.columnconfigure(0, weight=3, uniform="about")
    cards.columnconfigure(1, weight=2, uniform="about")

    def card_header(parent, text, icon_name):
        row = tk.Frame(parent, bg=t.SURFACE)
        row.pack(fill="x")
        image = self._icon(icon_name, 24)
        if image:
            tk.Label(row, image=image, bg=t.SURFACE).pack(side="left", padx=(0, 8))
        t.label(row, text, 11, t.PRIMARY_DARK, True).pack(side="left", anchor="w")
        tk.Frame(parent, bg=t.BORDER, height=1).pack(fill="x", pady=(8, 12))

    info = t.card(cards, padding=16)
    info.grid(row=0, column=0, sticky="nsew", padx=(0, 7), pady=(0, 8))
    card_header(info, APP_NAME, "sobre")

    details = tk.Frame(info, bg=t.SURFACE)
    details.pack(fill="x")
    detail_rows = (
        ("Versão", APP_VERSION),
        ("Desenvolvido por", "Jorge Alberto de Paula"),
        ("Empresa", "FTS Distribuidora de Peças Ltda."),
        ("Módulos", f"Folha de Pagamento {folha_version} · Energia e Água {energia_version}"),
    )
    detail_values = []
    for index, (name, value) in enumerate(detail_rows):
        cell = tk.Frame(details, bg=t.SURFACE)
        cell.grid(row=index // 2, column=index % 2, sticky="nw", padx=(0, 12), pady=(0, 14))
        details.columnconfigure(index % 2, weight=1, uniform="details")
        t.label(cell, name, 9, t.MUTED, bg=t.SURFACE).pack(anchor="w", pady=(0, 4))
        value_label = t.label(cell, value, 10, t.TEXT, True, bg=t.SURFACE,
                              wraplength=260, justify="left", anchor="w")
        value_label.pack(anchor="w")
        detail_values.append(value_label)

    callout = tk.Frame(info, bg=t.SURFACE_ALT, highlightbackground=t.BORDER, highlightthickness=1,
                       padx=11, pady=9)
    callout.pack(fill="x", pady=(2, 0))
    callout_label = t.label(
        callout,
        "Folha de Pagamento e Energia e Água funcionam dentro desta janela, com os mesmos bancos "
        "de dados e regras dos programas anteriores, que continuam disponíveis para reversão.",
        9, t.MUTED, bg=t.SURFACE_ALT, wraplength=520, justify="left",
    )
    callout_label.pack(anchor="w")

    technical = t.card(cards, padding=16)
    technical.grid(row=0, column=1, sticky="nsew", padx=(7, 0), pady=(0, 8))
    card_header(technical, "Informações técnicas", "painel")

    module_rows = (
        ("folha", "Folha de Pagamento", folha_version),
        ("energia", "Energia e Água", energia_version),
    )
    for icon_name, name, version in module_rows:
        row = tk.Frame(technical, bg=t.SURFACE)
        row.pack(fill="x", pady=(0, 5))
        image = self._icon(icon_name, 24)
        if image:
            tk.Label(row, image=image, bg=t.SURFACE).pack(side="left", padx=(0, 8))
        labels = tk.Frame(row, bg=t.SURFACE)
        labels.pack(side="left", fill="x", expand=True)
        t.label(labels, name, 9, t.TEXT, True).pack(anchor="w")
        t.label(labels, f"Módulo integrado · versão {version}", 8, t.MUTED).pack(anchor="w", pady=(2, 0))
        t.label(row, "Integrado", 8, t.PRIMARY_DARK, True, bg=t.HOVER,
                padx=7, pady=3).pack(side="right", padx=(6, 0))

    tk.Frame(technical, bg=t.BORDER, height=1).pack(fill="x", pady=(8, 10))
    technical_rows = (
        ("Programa", str(paths.program_dir())),
        ("Dados do sistema", str(paths.app_data_dir())),
        ("Backup legado da Folha (MEGA)", str(getattr(folha.module(), "AUTO_BACKUP_DIR", "—"))),
        ("Backup automático de Energia e Água (MEGA)", str(energia.exit_backup_path())),
    )
    path_values = []
    for name, value in technical_rows:
        section = tk.Frame(technical, bg=t.SURFACE)
        section.pack(fill="x", pady=(0, 8))
        t.label(section, name, 8, t.MUTED, bg=t.SURFACE).pack(anchor="w", pady=(0, 2))
        value_label = t.label(section, value, 8, t.TEXT, bg=t.SURFACE,
                              wraplength=420, justify="left", anchor="w")
        value_label.pack(fill="x", anchor="w")
        path_values.append((section, value_label))

    def resize_content(event):
        cards_width = event.width
        if cards_width >= 760:
            info.grid_configure(row=0, column=0, columnspan=1, padx=(0, 7))
            technical.grid_configure(row=0, column=1, columnspan=1, padx=(7, 0))
        else:
            info.grid_configure(row=0, column=0, columnspan=2, padx=0)
            technical.grid_configure(row=1, column=0, columnspan=2, padx=0)

    def resize_info(event):
        column_width = max(100, event.width // 2 - 20)
        for value_label in detail_values:
            value_label.configure(wraplength=column_width)

    def resize_callout(event):
        callout_label.configure(wraplength=max(100, event.width - 26))

    def resize_technical(event):
        for section, value_label in path_values:
            value_label.configure(wraplength=max(100, section.winfo_width() - 2))

    cards.bind("<Configure>", resize_content, add="+")
    details.bind("<Configure>", resize_info, add="+")
    callout.bind("<Configure>", resize_callout, add="+")
    technical.bind("<Configure>", resize_technical, add="+")
