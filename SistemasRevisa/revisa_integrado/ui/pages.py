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


def _fmt_time(path):
    try:
        return datetime.fromtimestamp(Path(path).stat().st_mtime).strftime("%d/%m/%Y %H:%M")
    except OSError:
        return "—"


def _signing_status(warning_days=30):
    text, status, _when = folha.signing_status(warning_days)
    colors = {
        "unavailable": t.MUTED,
        "expired": t.DANGER,
        "warning": t.WARNING,
        "ok": t.SUCCESS,
    }
    return text, colors[status]


def _verify_sync_password(self):
    remaining = self.sync_limiter.remaining_lock()
    if remaining > 0:
        messagebox.showwarning(
            "Sincronização protegida",
            f"Muitas tentativas. Aguarde {int(remaining) + 1} segundos.",
            parent=self,
        )
        return False
    password = simpledialog.askstring(
        "Acesso à sincronização",
        "Digite a senha principal para acessar a sincronização:",
        show="•",
        parent=self,
    )
    if password is None:
        return False
    try:
        valid = folha.verify_password(password)
    except Exception as error:
        self.log.exception("Falha ao validar a senha para acessar a sincronização")
        messagebox.showerror("Acesso à sincronização", str(error), parent=self)
        return False
    finally:
        password = None
    if not valid:
        self.sync_limiter.failure()
        self.log.warning("Senha recusada ao acessar a sincronização")
        messagebox.showerror("Acesso à sincronização", "Senha principal incorreta.", parent=self)
        return False
    self.sync_limiter.success()
    return True


# ---------------------------------------------------------------------- painel
def build_dashboard(self, frame):
    inner = _scrollable(frame)
    hero = tk.Frame(inner, bg=t.SURFACE, highlightbackground=t.BORDER, highlightthickness=1)
    hero.pack(fill="x")
    tk.Frame(hero, bg=t.ORANGE, width=5).pack(side="left", fill="y")
    logo = self._logo("dashboard", (300, 110))
    if logo:
        tk.Label(hero, image=logo, bg=t.SURFACE).pack(side="left", padx=(22, 26), pady=14)
    welcome = tk.Frame(hero, bg=t.SURFACE)
    welcome.pack(side="left", fill="both", expand=True, pady=14)
    t.label(welcome, f"Bem-vindo, {self.session.user}", 18, t.PRIMARY_DARK, True).pack(anchor="w")
    t.label(welcome, "Sistemas Revisa — Gerenciador Administrativo", 11, t.TEXT).pack(anchor="w")
    t.label(welcome, "Escolha um módulo no menu Módulos ou nos quadros abaixo.",
            10, t.MUTED).pack(anchor="w", pady=(6, 0))
    cards = tk.Frame(inner, bg=t.BG)
    cards.pack(fill="x", pady=(12, 0))
    for column in range(4):
        cards.columnconfigure(column, weight=1, uniform="cards")

    payroll = folha.summary()
    payroll_text = (f"{payroll['ativos']} colaboradores ativos ({payroll['total']} cadastrados)"
                    if payroll["status"] == "ok" else f"Banco: {payroll['status']}")
    energy = energia.summary()
    energy_text = (f"{energy['ocupantes']} inquilinos • último mês lançado: {energy['ultimo_mes']}"
                   if energy["status"] == "ok" else f"Banco: {energy['status']}")
    backups = backup.list_backups(paths.backups_dir())
    last_backup = backups[0][1].get("criado_em", "—") if backups and backups[0][1] else "nenhum backup registrado"
    try:
        settings = config.load()
        if settings["transferencia_habilitada"]:
            state = transfer.load_state(paths.transfer_state_path())
            transfer_text = ("Este computador é o titular dos dados" if state.get("titular", True)
                             else "Dados entregues ao outro computador — módulos bloqueados")
        else:
            transfer_text = "Transferência entre computadores desativada"
    except Exception as error:
        transfer_text = f"Estado indisponível: {error}"

    entries = (
        ("Folha de Pagamento", payroll_text, f"Banco atualizado em {_fmt_time(folha.db_path())}", MODULE_FOLHA, "Abrir Folha"),
        ("Energia e Água", energy_text,
         "Acesso liberado pelo login principal",
         MODULE_ENERGIA, "Abrir Energia e Água"),
        ("Backups", f"Último backup: {last_backup}", f"{len(backups)} backup(s) no histórico", "backups", "Ver backups"),
        ("Transferência", transfer_text, "Pasta e regras em Backups e Transferência", "backups", "Ver transferência"),
    )
    icons = {MODULE_FOLHA: "folha", MODULE_ENERGIA: "energia", "backups": "backups"}
    for index, (title, line1, line2, target, action) in enumerate(entries):
        box = tk.Frame(cards, bg=t.SURFACE, highlightbackground=t.BORDER, highlightthickness=1, padx=14, pady=12)
        box.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 6, 0 if index == 3 else 6))
        head = tk.Frame(box, bg=t.SURFACE)
        head.pack(fill="x")
        image = self._icon(icons.get(target, "backups") if title != "Transferência" else "admin", 28)
        if image:
            tk.Label(head, image=image, bg=t.SURFACE).pack(side="left", padx=(0, 8))
        t.label(head, title, 11, t.PRIMARY_DARK, True).pack(side="left")
        tk.Frame(box, bg=t.BORDER, height=1).pack(fill="x", pady=(8, 8))
        t.label(box, line1, 10, t.TEXT, wraplength=250, justify="left").pack(anchor="w")
        t.label(box, line2, 9, t.MUTED, wraplength=250, justify="left").pack(anchor="w", pady=(2, 10))
        t.button(box, action, lambda k=target: self.navigate(k)).pack(side="bottom", anchor="w")

    shortcuts = t.card(inner, "Backups e senhas")
    shortcuts.pack(fill="x", pady=(12, 0))
    t.label(shortcuts, "Acesse aqui as operações de backup e as alterações de senha dos módulos.",
            9, t.MUTED, wraplength=760, justify="left").pack(anchor="w")
    backup_actions = tk.Frame(shortcuts, bg=t.SURFACE)
    backup_actions.pack(fill="x", pady=(8, 10))
    t.button(backup_actions, "Gerenciar e criar backups",
             lambda: self.navigate("backups")).pack(side="left")
    t.button(backup_actions, "Abrir pasta de backups",
             self.open_backup_folder, kind="secondary").pack(side="left", padx=6)
    password_actions = tk.Frame(shortcuts, bg=t.SURFACE)
    password_actions.pack(fill="x")
    t.button(password_actions, "Alterar senha principal",
             lambda: self._menu_change_password(change_main_password),
             kind="secondary").pack(side="left")
    t.button(password_actions, "Alterar senha da Folha",
             lambda: self.change_module_password(MODULE_FOLHA),
             kind="secondary").pack(side="left", padx=6)
    t.button(password_actions, "Alterar senha de Energia e Água",
             lambda: self.change_module_password(MODULE_ENERGIA),
             kind="secondary").pack(side="left")

    text, color = _signing_status()
    status = t.card(inner, "Alertas")
    status.pack(fill="x", pady=(12, 0))
    t.label(status, text, 10, color).pack(anchor="w")
    legacy = []
    try:
        from .main_window import running_legacy_programs
        legacy = running_legacy_programs()
    except Exception:
        pass
    if legacy:
        t.label(status, "Programas anteriores abertos (feche-os para evitar uso simultâneo dos dados): "
                + ", ".join(legacy), 10, t.WARNING, wraplength=760, justify="left").pack(anchor="w", pady=(6, 0))
    else:
        t.label(status, "Nenhum programa anterior aberto.", 10, t.MUTED).pack(anchor="w", pady=(6, 0))


# ---------------------------------------------------------------------- backups e transferência
def build_backups(self, frame):
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
    t.label(section, "O sistema recebe automaticamente um pacote mais recente ao abrir. Fechar o programa "
            "não transfere a vez: quando quiser trocar de computador, use o botão de envio abaixo. Use "
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
        text=("Este computador pode editar. Fechar o sistema não envia dados."
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

    t.button(section, "Abrir pasta compartilhada", lambda: os.startfile(str(folder)),
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
    t.label(transfer_box, "A sincronização é protegida pela senha principal. O envio para outro computador "
            "é manual; fechar o sistema não cede a vez.",
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
                    "Ativar o recebimento automático ao abrir? O envio e a troca de computador serão "
                    "feitos manualmente na tela Backups e Transferência.\n\n"
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
    box = t.card(inner, APP_NAME)
    box.pack(fill="x")
    try:
        folha_version = folha.module().APP_VERSION
        energia_version = energia.module().APP_VERSION
    except Exception:
        folha_version = energia_version = "?"
    _kv(box, (
        ("Versão", APP_VERSION),
        ("Empresa", "FTS DISTRIBUIDORA DE PEÇAS LTDA"),
        ("Módulos", f"Folha de Pagamento {folha_version} • Energia e Água {energia_version}"),
        ("Programa", str(paths.program_dir())),
        ("Dados do sistema", str(paths.app_data_dir())),
        ("Backup legado da Folha (MEGA)", str(getattr(folha.module(), "AUTO_BACKUP_DIR", "—"))),
    ))
    t.label(box, "Folha de Pagamento e Energia e Água funcionam dentro desta janela, com os mesmos bancos de "
            "dados e regras dos programas anteriores, que continuam disponíveis para reversão.", 9, t.MUTED,
            wraplength=760, justify="left").pack(anchor="w", pady=(10, 0))
