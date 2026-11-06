# -*- coding: utf-8 -*-
"""
CONTROLE DE ENERGIA E ÁGUA - BARRACÃO
Aplicativo local em Python/Tkinter + SQLite.
Desenvolvido para iniciar novos registros em 2026, sem importar anos anteriores.
"""
import os, sys, sqlite3, shutil, subprocess, math, re
import hashlib, hmac, json, secrets, tempfile
import unicodedata
from pathlib import Path
from datetime import datetime, date
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

APP_NAME = "Controle de Energia e Água - Barracão"
APP_VERSION = "1.0"
ANO_INICIAL = 2026
COBRANCAS = (
    ("energia", "Energia"), ("agua", "Água"),
    ("aluguel", "Aluguel"), ("outras", "Outras despesas"), ("ajuste", "Ajustes"),
)
RATEIOS_DESPESAS = {"pessoas":"Por pessoas", "inquilinos":"Mesmo valor para cada inquilino"}
FUNDO = "#0B1220"
SUPERFICIE = "#111C2E"
SUPERFICIE_ALT = "#16243A"
BORDA = "#24344D"
BARRA = "#0E1726"
TEXTO_CLARO = "#E6EDF7"
TEXTO_SUAVE = "#8FA3BF"
AZUL = "#2563EB"
AZUL_ESCURO = "#1D4ED8"
COR_HOVER = "#22324D"
TEXTO_HOVER = "#ffffff"
TEXTO_DESATIVADO = "#5B6B82"
ROLAGEM_ATIVA = "#2A3B57"
AZUL_DESTAQUE = "#60A5FA"
COR_PRESSIONADO = AZUL
TEMA_CLARO = False


def usar_tema_claro():
    """Tema claro usado somente pelo Sistemas Revisa integrado; o programa autônomo não chama esta função."""
    global FUNDO, SUPERFICIE, SUPERFICIE_ALT, BORDA, BARRA, TEXTO_CLARO, TEXTO_SUAVE, AZUL, AZUL_ESCURO
    global COR_HOVER, TEXTO_HOVER, TEXTO_DESATIVADO, ROLAGEM_ATIVA, AZUL_DESTAQUE, COR_PRESSIONADO, TEMA_CLARO
    FUNDO = "#F2F4F8"; SUPERFICIE = "#FFFFFF"; SUPERFICIE_ALT = "#E9EEF5"; BORDA = "#D5DCE5"
    BARRA = "#FFFFFF"; TEXTO_CLARO = "#20252B"; TEXTO_SUAVE = "#667085"; AZUL = "#0875C9"
    AZUL_ESCURO = "#064B82"; COR_HOVER = "#DCEBFA"; TEXTO_HOVER = "#064B82"; TEXTO_DESATIVADO = "#98A2B3"
    ROLAGEM_ATIVA = "#B9C3D0"; AZUL_DESTAQUE = "#FF4B12"; COR_PRESSIONADO = "#B9D7F2"; TEMA_CLARO = True
NOMES_MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)

def chave_nome_ocupante(nome):
    nome=nome.upper().replace("\u00c3\u2022","\u00d5").replace("\u00c3\u2013","\u00d6")
    normalizado=unicodedata.normalize("NFKD",nome.upper())
    return "".join(
        caractere for caractere in normalizado
        if caractere.isalnum() and not unicodedata.combining(caractere)
    )

def pasta_dados():
    # Mantém o banco fora da pasta temporária do PyInstaller.
    if getattr(sys, "frozen", False):
        root = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "ControleEnergiaAguaBarracao"
    else:
        root = Path(__file__).resolve().parent
    root.mkdir(parents=True, exist_ok=True)
    return root

PASTA = pasta_dados()
DB_PATH = PASTA / "controle_energia_agua.db"
ACESSO_PATH = PASTA / "acesso.json"

def caminho_recurso(nome):
    base=Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parent))
    return base/nome


def geometria_central_dos_argumentos():
    argumento=next(
        (valor for valor in sys.argv if valor.startswith("--central-geometry=")),
        None)
    if argumento is None:
        return None
    correspondencia=re.fullmatch(
        r"--central-geometry=(\d+)x(\d+)\+(-?\d+)\+(-?\d+)",
        argumento)
    if correspondencia is None:
        raise ValueError("Geometria da janela da Central inválida.")
    largura,altura,x,y=map(int,correspondencia.groups())
    if largura<320 or altura<240:
        raise ValueError("A área da Central é pequena demais para abrir o Controle.")
    return largura,altura,x,y


def mostrar_logo_acesso(parent):
    from PIL import Image,ImageTk
    with Image.open(caminho_recurso("assets/revisa_logo.jpeg")) as original:
        imagem=original.convert("RGB")
        imagem.thumbnail((84,84),Image.Resampling.LANCZOS)
    foto=ImageTk.PhotoImage(imagem)
    logo=tk.Label(parent,image=foto,bg=SUPERFICIE)
    logo.image=foto
    logo.pack(anchor="center",pady=(0,8))
    return logo

def configurar_icone_aplicativo(root):
    from PIL import Image,ImageTk
    with Image.open(caminho_recurso("assets/imovel.png")) as original:
        imagem=original.convert("RGBA")
        imagem.thumbnail((64,64),Image.Resampling.LANCZOS)
    icone=ImageTk.PhotoImage(imagem,master=root)
    root.iconphoto(True,icone)
    root._icone_aplicativo=icone

def resumo_segredo(valor,sal):
    return hashlib.pbkdf2_hmac("sha256",valor.encode("utf-8"),sal,600_000).hex()

def ler_acesso():
    try:
        texto=ACESSO_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    dados=json.loads(texto)
    if not isinstance(dados,dict) or dados.get("versao")!=1:
        raise ValueError("Arquivo de acesso inválido. Restaure uma cópia segura de acesso.json.")
    for campo,tamanho in (("sal",32),("senha",64),("sal_recuperacao",32),("recuperacao",64)):
        valor=dados.get(campo)
        if not isinstance(valor,str) or len(valor)!=tamanho or any(c not in "0123456789abcdef" for c in valor):
            raise ValueError("Arquivo de acesso inválido. Restaure uma cópia segura de acesso.json.")
    return dados

def conferir_acesso(dados,valor,recuperacao=False):
    campo="recuperacao" if recuperacao else "senha"
    sal="sal_recuperacao" if recuperacao else "sal"
    if recuperacao:
        valor=valor.strip().upper()
    return hmac.compare_digest(resumo_segredo(valor,bytes.fromhex(dados[sal])),dados[campo])


def salvar_acesso(senha,confirmacao):
    if len(senha)<8:
        raise ValueError("Use uma senha com pelo menos 8 caracteres.")
    if senha!=confirmacao:
        raise ValueError("A confirmação não corresponde à nova senha.")
    codigo=secrets.token_hex(16).upper()
    sal=secrets.token_bytes(16)
    sal_recuperacao=secrets.token_bytes(16)
    dados={"versao":1,"sal":sal.hex(),"senha":resumo_segredo(senha,sal),
           "sal_recuperacao":sal_recuperacao.hex(),"recuperacao":resumo_segredo(codigo,sal_recuperacao)}
    temporario=None
    try:
        with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",dir=ACESSO_PATH.parent,
                                         prefix="acesso_",suffix=".tmp",delete=False) as arquivo:
            temporario=Path(arquivo.name)
            json.dump(dados,arquivo)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario,ACESSO_PATH)
    finally:
        if temporario is not None and temporario.exists():
            temporario.unlink()
    return codigo

def solicitar_acesso(root,alterar=False):
    try:
        dados=ler_acesso()
        if alterar and dados is None:
            raise ValueError("Arquivo de acesso não encontrado. Feche e reabra o programa para cadastrar a senha.")
    except (OSError,ValueError) as erro:
        messagebox.showerror("Não foi possível verificar o acesso",str(erro),parent=root)
        return False
    autorizado=False
    modo="alterar" if alterar else ("entrar" if dados else "cadastrar")
    win=tk.Toplevel(root)
    win.title("Acesso ao controle")
    win.configure(bg=FUNDO)
    win.resizable(False,False)
    if alterar:
        win.transient(root)
    estilo=ttk.Style(win)
    try: estilo.theme_use("clam")
    except tk.TclError: pass
    estilo.configure("Acesso.TEntry",padding=(9,6),fieldbackground=SUPERFICIE_ALT,foreground=TEXTO_CLARO,
                     insertcolor=TEXTO_CLARO,bordercolor=BORDA,lightcolor=BORDA,darkcolor=BORDA)
    estilo.map("Acesso.TEntry",bordercolor=[("focus",AZUL)],lightcolor=[("focus",AZUL)])
    estilo.configure("Acesso.TButton",padding=(10,8),background=AZUL,foreground="#ffffff",
                     font=("Segoe UI Semibold",10),relief="flat",borderwidth=0,focuscolor=AZUL)
    estilo.map("Acesso.TButton",background=[("pressed",AZUL_ESCURO),("active",AZUL_ESCURO)],foreground=[("active","#ffffff")])
    estilo.configure("AcessoSecundario.TButton",padding=(10,6),background=SUPERFICIE_ALT,foreground=TEXTO_CLARO,
                     font=("Segoe UI",9),relief="flat",borderwidth=0,focuscolor=SUPERFICIE_ALT)
    estilo.map("AcessoSecundario.TButton",background=[("pressed",COR_PRESSIONADO),("active",COR_HOVER)],foreground=[("active",TEXTO_HOVER)])
    tk.Frame(win,bg=AZUL,height=4).pack(fill="x")
    moldura=tk.Frame(win,bg=SUPERFICIE,padx=26,pady=18,highlightbackground=BORDA,highlightthickness=1)
    moldura.pack(fill="both",expand=True,padx=16,pady=16)
    segredo=tk.StringVar()
    nova=tk.StringVar()
    confirmacao=tk.StringVar()

    def centralizar():
        win.update_idletasks()
        largura,altura=win.winfo_reqwidth(),win.winfo_reqheight()
        x=max(0,(win.winfo_screenwidth()-largura)//2)
        y=max(0,(win.winfo_screenheight()-altura)//2)
        win.geometry(f"+{x}+{y}")

    def mostrar_codigo(codigo):
        for widget in moldura.winfo_children():
            widget.destroy()
        mostrar_logo_acesso(moldura)
        tk.Label(moldura,text="Guarde seu código de recuperação",bg=SUPERFICIE,fg=TEXTO_CLARO,
                 font=("Segoe UI",13,"bold")).pack(anchor="w",pady=(0,10))
        campo=ttk.Entry(moldura,width=40,style="Acesso.TEntry")
        campo.insert(0,codigo)
        campo.configure(state="readonly")
        campo.pack(fill="x",pady=6)
        tk.Label(moldura,text="Anote ou copie este código e guarde em local seguro.\n"
                 "Ele permite redefinir a senha e só é mostrado agora.\n"
                 "O código anterior deixa de funcionar.",bg=SUPERFICIE,fg=TEXTO_SUAVE,
                 justify="left").pack(anchor="w",pady=6)
        ttk.Button(moldura,text="Guardei o código — continuar",style="Acesso.TButton",command=win.destroy).pack(fill="x",pady=(8,0))
        centralizar()

    def salvar():
        nonlocal autorizado
        try:
            if modo=="entrar":
                if not conferir_acesso(dados,segredo.get()):
                    raise ValueError("Senha incorreta.")
                autorizado=True
                win.destroy()
                return
            if modo in ("alterar","recuperar"):
                if not conferir_acesso(dados,segredo.get(),recuperacao=modo=="recuperar"):
                    raise ValueError("Código de recuperação incorreto." if modo=="recuperar" else "Senha atual incorreta.")
            codigo=salvar_acesso(nova.get(),confirmacao.get())
        except (OSError,ValueError) as erro:
            messagebox.showerror("Acesso não autorizado",str(erro),parent=win)
            return
        autorizado=True
        segredo.set("");nova.set("");confirmacao.set("")
        mostrar_codigo(codigo)

    def montar_formulario():
        for widget in moldura.winfo_children():
            widget.destroy()
        mostrar_logo_acesso(moldura)
        titulo={"entrar":"Digite sua senha","cadastrar":"Cadastre sua senha",
                "alterar":"Alterar senha","recuperar":"Recuperar acesso"}[modo]
        tk.Label(moldura,text="CONTROLE DE ENERGIA E ÁGUA",bg=SUPERFICIE,fg=AZUL_DESTAQUE,
                 font=("Segoe UI Semibold",8)).pack(anchor="center")
        tk.Label(moldura,text=titulo,bg=SUPERFICIE,fg=TEXTO_CLARO,font=("Segoe UI",15,"bold")).pack(anchor="center",pady=(0,8))
        campos=[]
        if modo!="cadastrar":
            campos.append(("Código de recuperação" if modo=="recuperar" else "Senha atual" if modo=="alterar" else "Senha",segredo))
        if modo!="entrar":
            campos.extend((("Nova senha (mínimo 8 caracteres)",nova),("Confirme a nova senha",confirmacao)))
        primeiro=None
        for rotulo,variavel in campos:
            tk.Label(moldura,text=rotulo,bg=SUPERFICIE,fg=TEXTO_SUAVE,font=("Segoe UI Semibold",9)).pack(anchor="w",pady=(8,4))
            campo=ttk.Entry(moldura,textvariable=variavel,show="*",width=40,style="Acesso.TEntry")
            campo.pack(fill="x")
            campo.bind("<Return>",lambda evento:salvar())
            if primeiro is None:
                primeiro=campo
        ttk.Button(moldura,text="Entrar" if modo=="entrar" else "Salvar senha",style="Acesso.TButton",command=salvar).pack(fill="x",pady=(16,6))
        if modo=="entrar":
            ttk.Button(moldura,text="Esqueci a senha",style="AcessoSecundario.TButton",command=recuperar).pack(fill="x",pady=3)
        ttk.Button(moldura,text="Cancelar",style="AcessoSecundario.TButton",command=win.destroy).pack(fill="x",pady=3)
        primeiro.focus_set()
        centralizar()

    def recuperar():
        nonlocal modo
        modo="recuperar"
        segredo.set("")
        montar_formulario()

    montar_formulario()
    win.grab_set()
    root.wait_window(win)
    return autorizado

def moeda(v):
    try: return f"R$ {float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError): return "R$ 0,00"

def numero(v, campo):
    s = str(v or "0").strip().replace("R$", "").replace(" ", "")
    if "," in s: s = s.replace(".", "").replace(",", ".")
    try:
        valor = float(s)
        if not math.isfinite(valor):
            raise ValueError
        return valor
    except ValueError: raise ValueError(f"Informe um número válido no campo: {campo}.")

def dividir_valor_por_meses(valor,quantidade):
    if not math.isfinite(valor) or valor<=0 or quantidade<1:
        raise ValueError("Informe um valor positivo e ao menos um mês.")
    centavos=round(valor*100)
    if centavos<quantidade:
        raise ValueError(
            "O valor total precisa ser suficiente para deixar ao menos R$ 0,01 em cada mês."
        )
    base,resto=divmod(centavos,quantidade)
    return [(base+(indice<resto))/100 for indice in range(quantidade)]

def vincular_restauracao_modal(root,win):
    def restaurar(_evento=None):
        if not win.winfo_exists():
            return
        if win.state()=="iconic":
            win.deiconify()
        win.lift()
        win.grab_set()

    def ao_restaurar(_evento):
        if win.winfo_exists():
            win.after_idle(restaurar)

    binding_id=root.bind("<Map>",ao_restaurar,add="+")
    if binding_id:
        win.bind(
            "<Destroy>",
            lambda evento: root.unbind("<Map>",binding_id) if evento.widget is win else None,
            add="+",
        )

def data_iso(v):
    v = (v or "").strip()
    if not v: return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try: return datetime.strptime(v, fmt).strftime("%Y-%m-%d")
        except ValueError: pass
    raise ValueError("Data inválida. Use DD/MM/AAAA.")


def lancamento_vencido(ano,mes,hoje=None):
    hoje=hoje or date.today()
    ano_vencimento,mes_vencimento=(ano+1,1) if mes==12 else (ano,mes+1)
    return (hoje.year,hoje.month,hoje.day)>(ano_vencimento,mes_vencimento,10)


class App:
    def __init__(self, root, embutido=False):
        self.root = root
        self.embutido = embutido
        if not embutido:
            self.configurar_janela()
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.criar_banco()
        self.configurar_estilo()
        self.montar()
        self.atualizar()

    def configurar_janela(self):
        self.root.title(f"{APP_NAME}  •  v{APP_VERSION}")
        geometria_central=geometria_central_dos_argumentos()
        if geometria_central is None:
            self.root.geometry("1240x780")
            self.root.minsize(1000, 780)
        else:
            largura,altura,x,y=geometria_central
            self.root.geometry(f"{largura}x{altura}+{x}+{y}")
            self.root.minsize(320,240)

    def criar_banco(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS meses(
          id INTEGER PRIMARY KEY, ano INTEGER NOT NULL, mes INTEGER NOT NULL,
          conta_energia REAL NOT NULL DEFAULT 0, conta_agua REAL NOT NULL DEFAULT 0,
          total_kwh REAL NOT NULL DEFAULT 0, usar_rateio_energia INTEGER NOT NULL DEFAULT 0,
          iluminacao_publica REAL NOT NULL DEFAULT 0,
          total_pessoas_agua INTEGER NOT NULL DEFAULT 0,
          usar_rateio_despesas INTEGER NOT NULL DEFAULT 1,
          limpeza_calha REAL NOT NULL DEFAULT 0, observacoes TEXT DEFAULT '',
          UNIQUE(ano,mes));
        CREATE TABLE IF NOT EXISTS ocupantes(
          id INTEGER PRIMARY KEY, nome TEXT NOT NULL UNIQUE, ativo INTEGER NOT NULL DEFAULT 1,
          observacoes TEXT NOT NULL DEFAULT '',
          avisar_leitura INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS lancamentos(
          id INTEGER PRIMARY KEY, mes_id INTEGER NOT NULL, ocupante_id INTEGER NOT NULL,
          leitura_inicial REAL DEFAULT 0, leitura_final REAL DEFAULT 0, tarifa_kwh REAL DEFAULT 0,
          leitura_informada INTEGER NOT NULL DEFAULT 0,
          numero_pessoas INTEGER NOT NULL DEFAULT 0, agua_partes REAL DEFAULT 0, aluguel REAL DEFAULT 0, outras_despesas REAL DEFAULT 0,
          ajuste REAL DEFAULT 0, observacoes TEXT DEFAULT '',
          FOREIGN KEY(mes_id) REFERENCES meses(id), FOREIGN KEY(ocupante_id) REFERENCES ocupantes(id),
          UNIQUE(mes_id,ocupante_id));
        CREATE TABLE IF NOT EXISTS pagamentos(
          id INTEGER PRIMARY KEY, lancamento_id INTEGER NOT NULL, data_pagamento TEXT NOT NULL,
          valor REAL NOT NULL, forma TEXT DEFAULT '', observacoes TEXT DEFAULT '',
          revertido_em TEXT DEFAULT NULL,
          FOREIGN KEY(lancamento_id) REFERENCES lancamentos(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS despesas_mes(
          id INTEGER PRIMARY KEY, mes_id INTEGER NOT NULL,
          descricao TEXT NOT NULL, valor REAL NOT NULL CHECK(valor>0),
          rateio TEXT NOT NULL DEFAULT 'pessoas',
          ocupante_id INTEGER,
          FOREIGN KEY(mes_id) REFERENCES meses(id));
        """)
        colunas_lancamentos = {
            row["name"] for row in self.conn.execute("PRAGMA table_info(lancamentos)")
        }
        colunas_pagamentos={r["name"] for r in self.conn.execute("PRAGMA table_info(pagamentos)")}
        colunas_ocupantes={r["name"] for r in self.conn.execute("PRAGMA table_info(ocupantes)")}
        migrar_aviso_leitura="avisar_leitura" not in colunas_ocupantes
        if "observacoes" not in colunas_ocupantes:
            self.conn.execute(
                "ALTER TABLE ocupantes ADD COLUMN observacoes TEXT NOT NULL DEFAULT ''"
            )
        if migrar_aviso_leitura:
            self.conn.execute(
                "ALTER TABLE ocupantes ADD COLUMN avisar_leitura INTEGER NOT NULL DEFAULT 0"
            )
        if "revertido_em" not in colunas_pagamentos:
            self.conn.execute("ALTER TABLE pagamentos ADD COLUMN revertido_em TEXT DEFAULT NULL")
        colunas_despesas={r["name"] for r in self.conn.execute("PRAGMA table_info(despesas_mes)")}
        if "rateio" not in colunas_despesas:
            self.conn.execute("ALTER TABLE despesas_mes ADD COLUMN rateio TEXT NOT NULL DEFAULT 'pessoas'")
        if "ocupante_id" not in colunas_despesas:
            self.conn.execute("ALTER TABLE despesas_mes ADD COLUMN ocupante_id INTEGER")
        if "numero_pessoas" not in colunas_lancamentos:
            self.conn.execute(
                "ALTER TABLE lancamentos ADD COLUMN numero_pessoas INTEGER NOT NULL DEFAULT 0"
            )
        if "leitura_informada" not in colunas_lancamentos:
            self.conn.execute(
                "ALTER TABLE lancamentos ADD COLUMN leitura_informada INTEGER NOT NULL DEFAULT 0"
            )
            self.conn.execute(
                "UPDATE lancamentos SET leitura_informada=1 "
                "WHERE COALESCE(leitura_final,0) != COALESCE(leitura_inicial,0)"
            )
        if "outras_despesas" not in colunas_lancamentos:
            self.conn.execute(
                "ALTER TABLE lancamentos ADD COLUMN outras_despesas REAL NOT NULL DEFAULT 0"
            )
            if "portao" in colunas_lancamentos:
                self.conn.execute(
                    "UPDATE lancamentos SET outras_despesas=portao WHERE portao IS NOT NULL"
                )
        colunas_meses = {row["name"] for row in self.conn.execute("PRAGMA table_info(meses)")}
        for campo,tipo in (("total_kwh","REAL"),("usar_rateio_energia","INTEGER"),("iluminacao_publica","REAL")):
            if campo not in colunas_meses:
                self.conn.execute(f"ALTER TABLE meses ADD COLUMN {campo} {tipo} NOT NULL DEFAULT 0")
        if "total_pessoas_agua" not in colunas_meses:
            self.conn.execute(
                "ALTER TABLE meses ADD COLUMN total_pessoas_agua INTEGER NOT NULL DEFAULT 0"
            )
        if "usar_rateio_despesas" not in colunas_meses:
            # Meses antigos preservam cobranças individuais até ativar o novo rateio.
            self.conn.execute("ALTER TABLE meses ADD COLUMN usar_rateio_despesas INTEGER NOT NULL DEFAULT 0")
        for tabela in ("ocupantes", "lancamentos"):
            colunas={r["name"] for r in self.conn.execute(f"PRAGMA table_info({tabela})")}
            for chave,_ in COBRANCAS:
                campo=f"cobrar_{chave}"
                if campo not in colunas:
                    self.conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {campo} INTEGER NOT NULL DEFAULT 1")
        if migrar_aviso_leitura:
            hoje=date.today()
            self.conn.execute(
                """
                UPDATE ocupantes AS o
                SET avisar_leitura=COALESCE((
                    SELECT CASE
                        WHEN COALESCE(l.aluguel,0)>0 AND COALESCE(l.cobrar_energia,1)=1
                        THEN 1 ELSE 0
                    END
                    FROM lancamentos l
                    JOIN meses m ON m.id=l.mes_id
                    WHERE l.ocupante_id=o.id
                      AND m.ano*100+m.mes<=?
                    ORDER BY CASE WHEN m.ano=? AND m.mes=? THEN 0 ELSE 1 END,
                             m.ano DESC,m.mes DESC
                    LIMIT 1
                ),0)
                """,
                (hoje.year*100+hoje.month,hoje.year,hoje.month),
            )
        campos_regras=",".join(f"cobrar_{chave} INTEGER NOT NULL DEFAULT 1" for chave,_ in COBRANCAS)
        self.conn.execute(
            f"CREATE TABLE IF NOT EXISTS padroes_cobranca (ocupante_id INTEGER NOT NULL,"
            f"periodo INTEGER NOT NULL,{campos_regras},PRIMARY KEY(ocupante_id,periodo))"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS padroes_pessoas ("
            "ocupante_id INTEGER NOT NULL,periodo INTEGER NOT NULL,"
            "numero_pessoas INTEGER NOT NULL CHECK(numero_pessoas>=0),"
            "PRIMARY KEY(ocupante_id,periodo))"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pagamentos_lancamento_revertido "
            "ON pagamentos(lancamento_id,revertido_em)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_lancamentos_ocupante_mes "
            "ON lancamentos(ocupante_id,mes_id)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_despesas_mes_rateio_ocupante "
            "ON despesas_mes(mes_id,rateio,ocupante_id)"
        )
        # Nomes encontrados na planilha recente; novos ocupantes podem ser cadastrados.
        for nome in ("REVISA", "GUSTAVO", "MARCOS - MM FULGÕES", "GERSON", "MAURI"):
            self.conn.execute("INSERT OR IGNORE INTO ocupantes(nome) VALUES(?)", (nome,))
        self.conn.commit()

    def configurar_estilo(self):
        self.root.configure(bg=FUNDO)
        s=ttk.Style()
        try: s.theme_use("clam")
        except tk.TclError: pass
        s.configure(".", font=("Segoe UI", 10),background=FUNDO,foreground=TEXTO_CLARO,
                    bordercolor=BORDA,lightcolor=BORDA,darkcolor=BORDA,troughcolor=SUPERFICIE)
        s.configure("TFrame", background=FUNDO)
        s.configure("TLabel", background=FUNDO, foreground=TEXTO_CLARO)
        s.configure("TLabelframe",background=FUNDO,bordercolor=BORDA)
        s.configure("TLabelframe.Label",background=FUNDO,foreground=TEXTO_CLARO)
        s.configure("TButton", padding=7,background=SUPERFICIE_ALT,foreground=TEXTO_CLARO)
        s.map("TButton",background=[("pressed",COR_PRESSIONADO),("active",COR_HOVER)],
              foreground=[("disabled",TEXTO_DESATIVADO),("active",TEXTO_HOVER)])
        s.configure("TEntry",fieldbackground="#ffffff",foreground="#18212b",insertcolor="#18212b")
        s.configure("TCombobox",fieldbackground="#ffffff",foreground="#25313c",selectbackground="#dce7f0",selectforeground="#25313c",
                    background=SUPERFICIE_ALT,arrowcolor=TEXTO_CLARO)
        s.map("TCombobox",fieldbackground=[("readonly","#ffffff")],foreground=[("readonly","#25313c")])
        s.configure("TCheckbutton",background=FUNDO,foreground=TEXTO_CLARO,indicatorbackground="#ffffff",focuscolor=FUNDO)
        s.configure("TRadiobutton",background=FUNDO,foreground=TEXTO_CLARO,indicatorbackground="#ffffff",focuscolor=FUNDO)
        s.map("TCheckbutton",background=[("active",SUPERFICIE_ALT)],foreground=[("active",TEXTO_CLARO)])
        s.map("TRadiobutton",background=[("active",SUPERFICIE_ALT)],foreground=[("active",TEXTO_CLARO)])
        s.configure("TScrollbar",background=SUPERFICIE_ALT,troughcolor=SUPERFICIE,arrowcolor=TEXTO_CLARO,bordercolor=BORDA)
        s.map("TScrollbar",background=[("active",ROLAGEM_ATIVA)])
        s.configure("Treeview", rowheight=28, background="#ffffff", fieldbackground="#ffffff", foreground="#25313c")
        s.map("Treeview",background=[("selected","#dce7f0")],foreground=[("selected","#25313c")])
        s.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"),background="#e9edf0",foreground="#25313c")
        s.map("Treeview.Heading",background=[("active","#e1e8ed")])
        s.configure("TNotebook", background=FUNDO,bordercolor=BORDA)
        s.configure("TNotebook.Tab", padding=(14, 9), font=("Segoe UI", 10, "bold"),background=SUPERFICIE,foreground=TEXTO_SUAVE)
        s.map("TNotebook.Tab",background=[("selected",AZUL),("active",SUPERFICIE_ALT)],
              foreground=[("selected","#ffffff"),("active",TEXTO_CLARO)])
        s.configure("Toolbar.TFrame",background=BARRA)
        s.configure("Toolbar.TButton",padding=(14,9),font=("Segoe UI Semibold",10),
                    background=BARRA,foreground=TEXTO_CLARO,relief="flat",borderwidth=0,focuscolor=BARRA)
        s.map("Toolbar.TButton",background=[("pressed",COR_PRESSIONADO),("active",SUPERFICIE_ALT)],foreground=[("active",TEXTO_HOVER)])
        s.configure("ToolbarSelected.TButton",padding=(14,9),font=("Segoe UI Semibold",10),
                    background=AZUL,foreground="#ffffff",relief="flat",borderwidth=0,focuscolor=AZUL)
        s.map("ToolbarSelected.TButton",background=[("pressed",AZUL_ESCURO),("active",AZUL_ESCURO)],
              foreground=[("active","#ffffff")])
        s.configure("PageHeading.TLabel",font=("Segoe UI Semibold",14),foreground=TEXTO_CLARO)
        s.configure("Sub.TLabel",font=("Segoe UI",9),foreground=TEXTO_SUAVE)
        s.configure("TButton",padding=(9,5),font=("Segoe UI Semibold",9),relief="flat",borderwidth=0,focuscolor=SUPERFICIE_ALT)
        s.configure("Treeview",rowheight=30,borderwidth=0)
        s.configure("Treeview.Heading",font=("Segoe UI Semibold",9),padding=8)
        s.layout("Navigation.TNotebook.Tab",[])
        self.root.option_add("*Toplevel.background",FUNDO)
        self.root.option_add("*TCombobox*Listbox.background","#ffffff")
        self.root.option_add("*TCombobox*Listbox.foreground","#25313c")
        self.root.option_add("*TCombobox*Listbox.selectBackground","#dce7f0")
        self.root.option_add("*TCombobox*Listbox.selectForeground","#25313c")

    def configurar_estilo_formulario(self,win):
        win.configure(bg=FUNDO)
        style=ttk.Style(win)
        style.configure("Form.TFrame",background=FUNDO)
        style.configure("Form.TLabel",background=FUNDO,foreground=TEXTO_CLARO)
        style.configure("Form.Title.TLabel",background=FUNDO,foreground=TEXTO_CLARO,font=("Segoe UI",16,"bold"))
        style.configure("Form.Subtitle.TLabel",background=FUNDO,foreground=TEXTO_SUAVE)
        style.configure("Form.TLabelframe",background=FUNDO,foreground=TEXTO_CLARO,bordercolor=BORDA)
        style.configure("Form.TLabelframe.Label",background=FUNDO,foreground=TEXTO_CLARO,font=("Segoe UI",10,"bold"))
        style.configure("Form.TEntry",fieldbackground="#ffffff",foreground="#18212b")
        style.configure("Form.TCheckbutton",background=FUNDO,foreground=TEXTO_CLARO)
        style.map("Form.TCheckbutton",background=[("active",SUPERFICIE_ALT)])

    def montar(self):
        toolbar=ttk.Frame(self.root,style="Toolbar.TFrame",padding=(12,8))
        toolbar.pack(fill="x")
        self.icones_navegacao=self.criar_icones_navegacao()
        self.botoes_navegacao={}
        navigation_labels = [(0, "Lançamentos" if self.embutido else "Lançamentos mensais"),
                             (1, "Inquilinos"),
                             (2, "Relatórios" if self.embutido else "Relatórios e backup")]
        if not self.embutido:
            navigation_labels.append((3, "Sobre"))
        for indice,texto in navigation_labels:
            botao=ttk.Button(
                toolbar,text=texto,style="Toolbar.TButton",image=self.icones_navegacao[4 if indice==3 else indice],
                compound="top",width=(14 if self.embutido else (8 if indice==3 else (22 if indice==0 else 14))),
                command=lambda aba=indice:self.nb.select(aba),
            )
            botao.pack(side="left",padx=(0,6))
            self.botoes_navegacao[indice]=botao
        if not self.embutido:
            ttk.Button(toolbar,text="Backup rápido",style="Toolbar.TButton",
                       image=self.icones_navegacao[3],compound="top",width=16,
                       command=self.backup_rapido).pack(side="right")
            self.icone_senha=self.criar_icone_senha()
            self.botao_alterar_senha=ttk.Button(
                toolbar,text="Alterar senha",style="Toolbar.TButton",
                image=self.icone_senha,compound="top",width=14,
                command=lambda:solicitar_acesso(self.root,alterar=True))
            self.botao_alterar_senha.pack(side="right",padx=(0,6))
        if self.embutido:
            self.aviso_aberto=tk.Label(
                toolbar, text="", bg="#FFF7ED", fg="#9A3412",
                font=("Segoe UI Semibold",9), anchor="w", justify="left",
                padx=9, pady=5, relief="solid", bd=1, cursor="hand2",
            )
            self.aviso_aberto.configure(highlightthickness=0)
            self.aviso_aberto.bind("<Button-1>", self.mostrar_detalhes_aberto)
        else:
            self.aviso_aberto=tk.Label(
                self.root,text="",bg="#ffe8e8",fg="#8b2525",
                font=("Segoe UI",11,"bold"),anchor="center",justify="center",
                padx=12,pady=6)
        tk.Frame(self.root,bg=BORDA,height=1).pack(fill="x")
        cabecalho=ttk.Frame(self.root,padding=(20,12))
        cabecalho.pack(fill="x")
        self.titulo_pagina=ttk.Label(cabecalho,text="Lançamentos mensais",style="PageHeading.TLabel")
        self.titulo_pagina.pack(side="left")
        ttk.Label(cabecalho,text="REVISA | Energia e Água • Barracão 1 e 2",style="Sub.TLabel").pack(side="right")
        self.nb=ttk.Notebook(self.root,style="Navigation.TNotebook"); self.nb.pack(fill="both",expand=True,padx=16,pady=(0,8))
        self.tab_mes=ttk.Frame(self.nb,padding=12)
        self.tab_oc=ttk.Frame(self.nb,padding=12); self.tab_rel=ttk.Frame(self.nb,padding=12)
        self.nb.add(self.tab_mes,text="Lançamentos mensais")
        self.nb.add(self.tab_oc,text="Inquilinos")
        self.nb.add(self.tab_rel,text="Relatórios" if self.embutido else "Relatórios e backup")
        self.tab_sobre=ttk.Frame(self.nb,padding=12)
        self.nb.add(self.tab_sobre,text="Sobre")
        self.nb.bind("<<NotebookTabChanged>>",self.atualizar_navegacao)
        self.atualizar_navegacao()
        self.montar_mes(); self.montar_ocupantes(); self.montar_relatorios()
        self.montar_sobre()
        tk.Frame(self.root,bg=BORDA,height=1).pack(fill="x")
        footer=ttk.Frame(self.root,padding=(18,6),style="Toolbar.TFrame")
        footer.pack(fill="x")
        ttk.Label(footer,text="REVISA | Energia e Água • Desenvolvedor: Jorge Alberto de Paula",style="Sub.TLabel").pack(side="left")
        ttk.Label(footer,text=f"Versão {APP_VERSION} | Dados locais",style="Sub.TLabel").pack(side="right")

    def criar_icone_senha(self):
        from PIL import Image, ImageDraw, ImageTk
        imagem=Image.new("RGBA",(64,64))
        desenho=ImageDraw.Draw(imagem)
        desenho.arc((18,6,46,38),180,360,fill="#93a4bb",width=7)
        desenho.line((18,22,18,30),fill="#93a4bb",width=7)
        desenho.line((46,22,46,30),fill="#93a4bb",width=7)
        desenho.rounded_rectangle((10,28,54,58),radius=7,fill="#4777ce",outline="#334b68",width=2)
        desenho.ellipse((27,36,37,46),fill="#ffffff")
        desenho.line((32,44,32,52),fill="#ffffff",width=4)
        return ImageTk.PhotoImage(imagem.resize((24,24),Image.Resampling.LANCZOS),master=self.root)

    def criar_icones_navegacao(self):
        from PIL import Image, ImageDraw, ImageTk
        icones=[]
        for tipo in range(5):
            imagem=Image.new("RGBA",(64,64))
            desenho=ImageDraw.Draw(imagem)
            if tipo==0:
                desenho.rounded_rectangle((8,12,56,56),radius=5,fill="#ffffff",outline="#334b68",width=3)
                desenho.rectangle((8,16,56,27),fill="#4777ce")
                for x in (20,44):
                    desenho.line((x,7,x,19),fill="#334b68",width=5)
                for x in (20,32,44):
                    for y in (36,46):
                        desenho.rectangle((x-2,y-2,x+2,y+2),fill="#4777ce")
            elif tipo==1:
                desenho.ellipse((23,7,43,27),fill="#f3c595",outline="#334b68",width=2)
                desenho.rounded_rectangle((13,31,53,57),radius=12,fill="#4777ce",outline="#334b68",width=2)
            elif tipo==2:
                desenho.rounded_rectangle((12,5,52,59),radius=4,fill="#ffffff",outline="#334b68",width=3)
                for y in (16,24):
                    desenho.line((20,y,44,y),fill="#718da9",width=3)
                for x,y in ((23,43),(33,35),(43,29)):
                    desenho.rectangle((x-3,y,x+3,51),fill="#4777ce")
            elif tipo==4:
                desenho.ellipse((8,8,56,56),fill="#4777ce",outline="#334b68",width=2)
                desenho.ellipse((29,18,35,24),fill="#ffffff")
                desenho.line((32,31,32,46),fill="#ffffff",width=5)
            else:
                desenho.rounded_rectangle((8,7,56,57),radius=4,fill="#4777ce",outline="#334b68",width=3)
                desenho.rectangle((19,8,44,27),fill="#dce7f0",outline="#334b68",width=2)
                desenho.rectangle((18,35,46,55),fill="#ffffff",outline="#334b68",width=2)
                desenho.rectangle((36,11,40,23),fill="#4777ce")
            icones.append(ImageTk.PhotoImage(
                imagem.resize((24,24),Image.Resampling.LANCZOS),master=self.root,
            ))
        return icones

    def atualizar_navegacao(self,_evento=None):
        selecionada=self.nb.index(self.nb.select())
        self.titulo_pagina.configure(text=self.nb.tab(selecionada,"text"))
        for indice,botao in self.botoes_navegacao.items():
            botao.configure(style="ToolbarSelected.TButton" if indice==selecionada else "Toolbar.TButton")

    def montar_sobre(self):
        ttk.Label(self.tab_sobre,text=APP_NAME,style="PageHeading.TLabel").pack(anchor="w",pady=(0,12))
        detalhes=(
            ("Versão",APP_VERSION),
            ("Desenvolvedor","Jorge Alberto de Paula"),
            ("Sistema","REVISA | Energia e Água • Barracão 1 e 2"),
            ("Finalidade","Controle de inquilinos, consumo de energia e água, aluguéis, despesas e pagamentos."),
            ("Armazenamento","Dados locais em banco SQLite. Faça backups regularmente."),
            ("Banco de dados",str(DB_PATH)),
        )
        for titulo,valor in detalhes:
            ttk.Label(self.tab_sobre,text=titulo,font=("Segoe UI",10,"bold")).pack(anchor="w",pady=(6,1))
            ttk.Label(self.tab_sobre,text=valor,wraplength=620,justify="left").pack(anchor="w")

    def montar_mes(self):
        f=ttk.Frame(self.tab_mes); f.pack(fill="x",pady=(0,8))
        self.m_ano=tk.StringVar(value="2026"); self.m_mes=tk.StringVar(value=f"{date.today().month:02d}")
        ttk.Label(f,text="Ano").pack(side="left")
        ano=ttk.Combobox(f,textvariable=self.m_ano,values=[str(y) for y in range(2026,2041)],width=7,state="readonly")
        ano.pack(side="left",padx=5)
        ano.bind("<<ComboboxSelected>>",lambda _:self.carregar_lancamentos())
        ttk.Label(f,text="Mês").pack(side="left")
        mes=ttk.Combobox(f,textvariable=self.m_mes,values=[f"{i:02d}" for i in range(1,13)],width=5,state="readonly")
        mes.pack(side="left",padx=5)
        mes.bind("<<ComboboxSelected>>",lambda _:self.carregar_lancamentos())
        ttk.Button(f,text="Nova conta / editar contas do mês",command=self.editar_contas_mes).pack(side="left",padx=5)
        ttk.Button(f,text="Pagamentos / reverter",command=self.registrar_pagamento).pack(side="left",padx=5)
        corpo=ttk.Frame(self.tab_mes)
        corpo.pack(fill="both",expand=True)
        corpo.columnconfigure(0,weight=1)
        corpo.rowconfigure(0,weight=1)
        planilha=ttk.Frame(corpo)
        planilha.grid(row=0,column=0,sticky="nsew")
        fundo_rateio="#fff7d6"
        estilo=ttk.Style()
        estilo.configure("Rateio.TNotebook",background=fundo_rateio)
        estilo.configure("Rateio.TNotebook.Tab",background="#f5e8b3",foreground="#25313c",padding=(22,12),font=("Segoe UI",11,"bold"))
        estilo.map("Rateio.TNotebook.Tab",background=[("selected","#ffe59a"),("active","#fff0bc")],foreground=[("selected","#18212b"),("active","#25313c")])
        lateral=ttk.Notebook(corpo,width=350,style="Rateio.TNotebook")
        lateral.grid(row=0,column=1,sticky="ns",padx=(12,0))
        energia_box=tk.Frame(lateral,bg=fundo_rateio,padx=18,pady=18)
        agua_box=tk.Frame(lateral,bg=fundo_rateio,padx=18,pady=18)
        energia_box.columnconfigure(0,weight=1)
        agua_box.columnconfigure(0,weight=1)
        lateral.add(energia_box,text="Energia")
        lateral.add(agua_box,text="Água")
        self.energia_total_var=tk.StringVar(value="0")
        self.energia_kwh_var=tk.StringVar(value="0")
        self.energia_iluminacao_var=tk.StringVar(value="0")
        self.energia_previa=tk.StringVar(value="Informe a conta e os kWh")
        for indice,(label,variavel) in enumerate((
            ("Valor total da conta (R$)",self.energia_total_var),
            ("Consumo total da conta (kWh)",self.energia_kwh_var),
            ("Iluminação pública incluída (R$)",self.energia_iluminacao_var),
        )):
            tk.Label(energia_box,text=label,bg=fundo_rateio,fg="#25313c",font=("Segoe UI",11)).grid(row=indice*2,column=0,sticky="w",pady=(10,6))
            tk.Entry(energia_box,textvariable=variavel,width=24,bg="#ffffff",fg="#18212b",insertbackground="#18212b",font=("Segoe UI",12),relief="solid",bd=1).grid(row=indice*2+1,column=0,sticky="ew",ipady=4)
            variavel.trace_add("write",lambda *_:self.atualizar_previa_energia())
        tk.Label(energia_box,textvariable=self.energia_previa,bg=fundo_rateio,fg="#17645e",font=("Segoe UI",11,"bold"),wraplength=310,justify="left").grid(row=6,column=0,sticky="w",pady=12)
        tk.Label(energia_box,text="A iluminação já faz parte do total.\nCada consumo recebe energia + iluminação por kWh, sem duplicar.\n\nREVISA recebe o restante da conta; saldo negativo é crédito.",bg=fundo_rateio,fg="#25313c",wraplength=310,justify="left").grid(row=7,column=0,sticky="w")
        ttk.Button(energia_box,text="Salvar e calcular energia",command=self.salvar_rateio_energia).grid(row=8,column=0,sticky="ew",pady=12)
        tk.Label(agua_box,text="Valor total da conta (R$)",bg=fundo_rateio,fg="#25313c",font=("Segoe UI",11)).grid(row=0,column=0,sticky="w")
        tk.Label(agua_box,text="Pessoas no terreno\n(soma automática dos inquilinos)",bg=fundo_rateio,fg="#25313c",font=("Segoe UI",11),justify="left").grid(row=2,column=0,sticky="w",pady=(18,0))
        tk.Label(agua_box,text="Valor por pessoa",bg=fundo_rateio,fg="#25313c",font=("Segoe UI",11)).grid(row=4,column=0,sticky="w",pady=(18,0))
        self.agua_total_var=tk.StringVar(value="0")
        self.agua_pessoas_var=tk.StringVar(value="0")
        self.agua_por_pessoa=tk.StringVar(value="Informe o valor e o total de pessoas")
        tk.Entry(agua_box,textvariable=self.agua_total_var,width=24,bg="#ffffff",fg="#18212b",insertbackground="#18212b",font=("Segoe UI",12),relief="solid",bd=1).grid(row=1,column=0,sticky="ew",pady=(6,0),ipady=4)
        tk.Entry(agua_box,textvariable=self.agua_pessoas_var,state="readonly",readonlybackground="#ffffff",width=24,bg="#ffffff",fg="#18212b",insertbackground="#18212b",font=("Segoe UI",12),relief="solid",bd=1).grid(row=3,column=0,sticky="ew",pady=(6,0),ipady=4)
        tk.Label(agua_box,textvariable=self.agua_por_pessoa,bg=fundo_rateio,fg="#17645e",font=("Segoe UI",11,"bold"),wraplength=310,justify="left").grid(row=5,column=0,sticky="w",pady=(6,0))
        tk.Label(agua_box,text="Água: valor total ÷ pessoas não isentas × pessoas do inquilino.\n\nIsentos não participam da divisão da água.\n\nInforme a quantidade na coluna Pessoas da aba Inquilinos.",bg=fundo_rateio,fg="#25313c",wraplength=310,justify="left").grid(row=6,column=0,sticky="w",pady=(18,0))
        ttk.Button(agua_box,text="Salvar rateio da água",command=self.salvar_rateio_agua).grid(row=7,column=0,sticky="ew",pady=(18,0))
        self.agua_total_var.trace_add("write",lambda *_:self.atualizar_previa_agua())
        self.lbl_mes_planilha=ttk.Label(
            planilha,text="",font=("Segoe UI",13,"bold")
        )
        self.lbl_mes_planilha.pack(anchor="w",pady=(0,8))
        tabela=tk.Frame(planilha,bg=FUNDO)
        tabela.pack(fill="both",expand=True)
        tabela.columnconfigure(0,weight=1)
        tabela.rowconfigure(0,weight=1)
        cols=("id","ocupante","energia","agua","aluguel","outras","ajuste","total","pago","saldo")
        self.lanc=ttk.Treeview(tabela,columns=cols,displaycolumns=cols[1:],show="headings",height=5)
        headers={"id":"ID","ocupante":"Ocupante","energia":"Energia (R$)","agua":"Água (R$)","aluguel":"Aluguel (R$)","outras":"Outras despesas (R$)","ajuste":"Ajuste (+/- R$)","total":"TOTAL (R$)","pago":"Pago (R$)","saldo":"Saldo (R$)"}
        widths={"id":0,"ocupante":190,"energia":105,"agua":105,"aluguel":95,"outras":150,"ajuste":90,"total":100,"pago":95,"saldo":95}
        for c in cols:
            self.lanc.heading(c,text=headers[c])
            self.lanc.column(c,width=widths[c],minwidth=widths[c],stretch=False,anchor="w" if c=="ocupante" else "e")
        self.lanc.tag_configure("pago",foreground="#145da0",font=("Segoe UI",10,"bold"))
        self.lanc.tag_configure("em_aberto",foreground="#b02020",font=("Segoe UI",10,"bold"))
        barra_vertical=ttk.Scrollbar(tabela,orient="vertical",command=self.lanc.yview)
        barra_horizontal=ttk.Scrollbar(tabela,orient="horizontal",command=self.lanc.xview)
        self.lanc.configure(yscrollcommand=barra_vertical.set,xscrollcommand=barra_horizontal.set)
        self.lanc.grid(row=0,column=0,sticky="nsew")
        barra_vertical.grid(row=0,column=1,sticky="ns")
        barra_horizontal.grid(row=1,column=0,sticky="ew")
        self.lanc.bind("<Double-1>",lambda e:self.editar_lancamento())
        legenda=ttk.Frame(planilha)
        legenda.pack(fill="x",pady=(6,0))
        tk.Label(legenda,text="  Quitado / sem saldo  ",bg="#ffffff",fg="#145da0",font=("Segoe UI",10,"bold")).pack(side="left",padx=(0,8))
        tk.Label(legenda,text="  Em aberto (inclusive parcial)  ",bg="#ffffff",fg="#b02020",font=("Segoe UI",10,"bold")).pack(side="left")
        self.lbl_total=ttk.Label(planilha,text="Selecione um mês para começar.",font=("Segoe UI",11,"bold"));self.lbl_total.pack(anchor="w",pady=8)
        despesas=ttk.Frame(planilha)
        despesas.pack(fill="x",pady=(4,0))
        ttk.Label(despesas,text="OUTRAS DESPESAS DO MÊS",font=("Segoe UI",11,"bold")).pack(anchor="w")
        acoes=ttk.Frame(despesas);acoes.pack(fill="x",pady=4)
        ttk.Button(acoes,text="Adicionar despesa",command=self.editar_despesa).pack(side="left")
        ttk.Button(acoes,text="Editar selecionada",command=lambda:self.editar_despesa(True)).pack(side="left",padx=6)
        ttk.Button(acoes,text="Excluir selecionada",command=self.excluir_despesa).pack(side="left")
        lista=ttk.Frame(despesas);lista.pack(fill="x")
        self.despesas_tree=ttk.Treeview(lista,columns=("descricao","valor","rateio"),show="headings",height=3)
        self.despesas_tree.heading("descricao",text="Descrição")
        self.despesas_tree.heading("valor",text="Valor total (R$)")
        self.despesas_tree.heading("rateio",text="Rateio")
        self.despesas_tree.column("descricao",width=300)
        self.despesas_tree.column("valor",width=140,anchor="e",stretch=False)
        self.despesas_tree.column("rateio",width=170,stretch=False)
        scroll=ttk.Scrollbar(lista,orient="vertical",command=self.despesas_tree.yview)
        self.despesas_tree.configure(yscrollcommand=scroll.set)
        self.despesas_tree.pack(side="left",fill="x",expand=True)
        scroll.pack(side="right",fill="y")
        self.despesas_tree.bind("<Double-1>",lambda e:self.editar_despesa(True))
        self.despesas_resumo=ttk.Label(despesas,text="",wraplength=650)
        self.despesas_resumo.pack(anchor="w",pady=4)

    def montar_ocupantes(self):
        self.oc_obs_editor=None
        self.oc_obs_editor_id=None
        self.oc_pessoas_editor=None
        self.oc_pessoas_editor_id=None
        f=ttk.Frame(self.tab_oc);f.pack(fill="x",pady=8)
        ttk.Label(f,text="Nome do inquilino:").pack(side="left")
        self.oc_nome=tk.StringVar();ttk.Entry(f,textvariable=self.oc_nome,width=36).pack(side="left",padx=8)
        ttk.Button(f,text="Adicionar inquilino",command=self.adicionar_ocupante).pack(side="left")
        ttk.Button(f,text="Excluir inquilino selecionado",command=self.excluir_ocupante).pack(side="left",padx=8)
        ttk.Button(f,text="Ativar/desativar selecionado",command=self.alternar_ocupante).pack(side="left")
        ttk.Label(
            self.tab_oc,
            text="Clique em uma cobrança para alternar Sim/Não. Clique na observação para editar. "
                 "As mudanças de cobrança valem do mês selecionado em diante. "
                 "Clique em Pessoas para alterar a quantidade em todos os meses, inclusive no histórico. "
                 "Clique em Aviso leitura para escolher quem deve receber o lembrete.",
            wraplength=1100,
        ).pack(anchor="w",pady=(0,4))
        tabela=tk.Frame(self.tab_oc,bg=FUNDO)
        tabela.pack(fill="both",expand=True,pady=10)
        colunas=("id","nome","observacoes","numero_pessoas")+tuple(
            f"cobrar_{chave}" for chave,_ in COBRANCAS
        )+("status","avisar_leitura")
        self.oc_tree=ttk.Treeview(
            tabela,columns=colunas,displaycolumns=colunas[1:],show="headings",height=16
        )
        cabecalhos={
            "id":"ID","nome":"Inquilino","observacoes":"Observações",
            "numero_pessoas":"Pessoas",
            "cobrar_energia":"Energia","cobrar_agua":"Água",
            "cobrar_aluguel":"Aluguel",
            "cobrar_outras":"Outras","cobrar_ajuste":"Ajuste","status":"Situação",
            "avisar_leitura":"Aviso leitura",
        }
        larguras={"id":0,"nome":210,"observacoes":250,"numero_pessoas":75,"cobrar_energia":85,
                  "cobrar_agua":75,"cobrar_aluguel":85,
                  "cobrar_outras":85,"cobrar_ajuste":75,"status":90,
                  "avisar_leitura":110}
        for c in colunas:
            self.oc_tree.heading(c,text=cabecalhos[c])
            self.oc_tree.column(
                c,width=larguras[c],minwidth=larguras[c],stretch=c=="observacoes",
                anchor="w" if c in ("nome","observacoes","status") else "center",
            )
        barra_vertical=ttk.Scrollbar(tabela,orient="vertical",command=self.oc_tree.yview)
        barra_horizontal=ttk.Scrollbar(tabela,orient="horizontal",command=self.oc_tree.xview)
        self.oc_tree.configure(
            yscrollcommand=barra_vertical.set,xscrollcommand=barra_horizontal.set
        )
        self.oc_tree.pack(side="left",fill="both",expand=True)
        barra_vertical.pack(side="right",fill="y")
        barra_horizontal.pack(side="bottom",fill="x")
        self.oc_tree.bind("<Button-1>",self.editar_celula_inquilino)

    def montar_relatorios(self):
        title = "Relatórios" if self.embutido else "Relatórios e segurança"
        ttk.Label(self.tab_rel,text=title,font=("Segoe UI",16,"bold")).pack(anchor="w",pady=(0,10))
        ttk.Label(self.tab_rel,text="Os dados ficam no seu computador, em um banco SQLite. O programa não importa os anos anteriores automaticamente.").pack(anchor="w",pady=4)
        f=ttk.Frame(self.tab_rel);f.pack(anchor="w",pady=10)
        ttk.Button(f,text="Gerar relatório em PDF",command=self.dialogo_relatorio_pdf).pack(side="left",padx=(0,8))
        if not self.embutido:
            ttk.Button(f,text="Criar backup do banco",command=self.backup_como).pack(side="left",padx=8)
            ttk.Button(f,text="Abrir pasta de dados",command=self.abrir_pasta).pack(side="left",padx=8)
            ttk.Button(f,text="Alterar senha",command=lambda:solicitar_acesso(self.root,alterar=True)).pack(side="left",padx=8)
        ttk.Label(self.tab_rel,text=f"Banco de dados atual: {DB_PATH}",wraplength=1000).pack(anchor="w",pady=15)

    def garantir_mes(self,ano,mes):
        self.conn.execute("INSERT OR IGNORE INTO meses(ano,mes,usar_rateio_despesas) VALUES(?,?,1)",(ano,mes));self.conn.commit()
        return self.conn.execute("SELECT id FROM meses WHERE ano=? AND mes=?",(ano,mes)).fetchone()["id"]

    def carregar_lancamentos(self):
        try: ano=int(self.m_ano.get());mes=int(self.m_mes.get())
        except ValueError:return
        if ano<2026:
            messagebox.showwarning("Período não permitido","Este sistema foi configurado para iniciar em 2026.");return
        mid=self.garantir_mes(ano,mes)
        campos=",".join(f"cobrar_{chave}" for chave,_ in COBRANCAS)
        pendentes=[]
        for ocupante in self.conn.execute("SELECT * FROM ocupantes WHERE ativo=1").fetchall():
            anterior=self.conn.execute(
                "SELECT l.*,m.ano,m.mes FROM lancamentos l JOIN meses m ON m.id=l.mes_id "
                "WHERE l.ocupante_id=? AND (m.ano*100+m.mes)<? "
                "ORDER BY m.ano DESC,m.mes DESC LIMIT 1",(ocupante["id"],ano*100+mes)
            ).fetchone()
            regra=self.conn.execute(
                "SELECT * FROM padroes_cobranca WHERE ocupante_id=? AND periodo<=? "
                "ORDER BY periodo DESC LIMIT 1",(ocupante["id"],ano*100+mes)
            ).fetchone()
            origem=regra if regra is not None else ocupante
            valores=[origem[f"cobrar_{chave}"] for chave,_ in COBRANCAS]
            parametros=",".join("?" for _ in valores)
            aluguel=anterior["aluguel"] if anterior else 0
            leitura=anterior["leitura_final"] if anterior else 0
            regra_pessoas=self.regra_pessoas_ocupante(ocupante["id"],ano,mes)
            pessoas=(
                regra_pessoas["numero_pessoas"] if regra_pessoas is not None
                else anterior["numero_pessoas"] if anterior else 0
            )
            resultado=self.conn.execute(
                f"INSERT OR IGNORE INTO lancamentos(mes_id,ocupante_id,aluguel,leitura_inicial,leitura_final,numero_pessoas,{campos}) "
                f"VALUES(?,?,?,?,?,?,{parametros})",
                (mid,ocupante["id"],aluguel,leitura,leitura,pessoas,*valores)
            )
            if resultado.rowcount==0 and anterior is not None:
                atual=self.conn.execute(
                    "SELECT * FROM lancamentos WHERE mes_id=? AND ocupante_id=?",(mid,ocupante["id"])
                ).fetchone()
                tem_pagamento=self.conn.execute(
                    "SELECT 1 FROM pagamentos WHERE lancamento_id=? LIMIT 1",(atual["id"],)
                ).fetchone()
                if regra_pessoas is not None and atual["numero_pessoas"]!=pessoas:
                    self.conn.execute(
                        "UPDATE lancamentos SET numero_pessoas=? WHERE id=?",
                        (pessoas,atual["id"]),
                    )
                elif regra_pessoas is None and atual["numero_pessoas"]==0 and pessoas>0 and not tem_pagamento:
                    self.conn.execute(
                        "UPDATE lancamentos SET numero_pessoas=? WHERE id=?",
                        (pessoas,atual["id"]),
                    )
                if tem_pagamento:
                    continue
                copiar_aluguel=atual["aluguel"]==0 and aluguel>0
                copiar_leitura=atual["leitura_inicial"]==0 and leitura>0 and (
                    atual["leitura_final"]==0 or atual["leitura_final"]>=leitura
                )
                if copiar_aluguel or copiar_leitura:
                    pendentes.append((atual,anterior,copiar_aluguel,copiar_leitura,ocupante["nome"]))
        self.conn.commit()
        if pendentes:
            detalhes=[]
            for atual,anterior,copiar_aluguel,copiar_leitura,nome in pendentes:
                campos_copiar=[]
                if copiar_aluguel:
                    campos_copiar.append(f"aluguel {moeda(anterior['aluguel'])}")
                if copiar_leitura:
                    campos_copiar.append(f"leitura anterior {anterior['leitura_final']:g}")
                detalhes.append(f"{nome} ({anterior['mes']:02d}/{anterior['ano']}): "+", ".join(campos_copiar))
            confirmar=messagebox.askyesno(
                "Preencher valores do mês anterior",
                f"Este mês ({mes:02d}/{ano}) já tem lançamentos com campos zerados.\n"
                "Preencher os campos abaixo com o último mês anterior de cada inquilino?\n\n"+
                "\n".join(detalhes)+
                "\n\nConfirme somente se os zeros não foram intencionais. Valores não zerados, "
                "isenções e lançamentos com histórico de pagamentos serão preservados.\n"
                "Se ambas as leituras estão zeradas, a leitura atual também começa no número anterior, sem consumo.",
                parent=self.root,
            )
            if confirmar:
                with self.conn:
                    for atual,anterior,copiar_aluguel,copiar_leitura,_ in pendentes:
                        self.conn.execute(
                            "UPDATE lancamentos SET aluguel=?,leitura_inicial=?,leitura_final=? WHERE id=?",
                            (anterior["aluguel"] if copiar_aluguel else atual["aluguel"],
                             anterior["leitura_final"] if copiar_leitura else atual["leitura_inicial"],
                             anterior["leitura_final"] if copiar_leitura and atual["leitura_final"]==0 else atual["leitura_final"],
                             atual["id"]),
                        )
        self.carregar_rateio_agua(mid)
        self.carregar_rateio_energia(mid)
        self.atualizar_lancamentos()
        if hasattr(self,"oc_tree"):
            self.atualizar_ocupantes()

    def contas_mes(self,mid):
        row=self.conn.execute("SELECT * FROM meses WHERE id=?",(mid,)).fetchone()
        if row is None:
            return None
        contas=dict(row)
        contas["total_pessoas_agua"]=self.pessoas_terreno(mid)
        return contas

    def pessoas_terreno(self,mid):
        return self.conn.execute(
            "SELECT COALESCE(SUM(numero_pessoas),0) FROM lancamentos WHERE mes_id=?",(mid,)
        ).fetchone()[0]

    def atualizar_despesas(self,mid):
        if not hasattr(self,"despesas_tree"):
            return
        self.despesas_tree.delete(*self.despesas_tree.get_children())
        for r in self.conn.execute(
            "SELECT d.*,o.nome nome_ocupante FROM despesas_mes d "
            "LEFT JOIN ocupantes o ON o.id=d.ocupante_id WHERE d.mes_id=? ORDER BY d.id",(mid,)
        ):
            forma=(f"Direto: {r['nome_ocupante']}" if r["ocupante_id"] is not None
                   else RATEIOS_DESPESAS[r["rateio"]])
            self.despesas_tree.insert("","end",iid=str(r["id"]),values=(r["descricao"],moeda(r["valor"]),forma))
        mes=self.contas_mes(mid)
        total=self.total_despesas(mid)
        divisor=mes["total_pessoas_agua"]
        rows=self.conn.execute("SELECT * FROM lancamentos WHERE mes_id=?",(mid,)).fetchall()
        if not mes["usar_rateio_despesas"]:
            total+=sum(
                (r["outras_despesas"] or 0) for r in rows if r["cobrar_outras"]
            )
        inquilinos=sum(bool(r["cobrar_outras"]) for r in rows)
        cobrado=sum(self.cobrancas_lancamento(r)["outras"] for r in rows)
        texto=f"Valor lançado: {moeda(total)} | Divisor por pessoas: {divisor} | Inquilinos não isentos: {inquilinos} | Total cobrado: {moeda(cobrado)}."
        if self.total_despesas(mid,"pessoas") and not divisor:
            texto+="\nPENDENTE: informe as pessoas nos lançamentos dos inquilinos para o rateio por pessoas."
        if self.total_despesas(mid,"inquilinos") and not inquilinos:
            texto+="\nPENDENTE: não há inquilinos não isentos para o rateio igual."
        if not mes["usar_rateio_despesas"]:
            texto=""
        self.despesas_resumo.config(text=texto)

    def gravar_despesa(self,mid,descricao,valor,ident=None,rateio="pessoas",ocupante_id=None):
        descricao=descricao.strip()
        if not descricao:
            raise ValueError("Informe a descrição da despesa.")
        if not math.isfinite(valor) or valor<=0:
            raise ValueError("Informe um valor de despesa maior que zero.")
        if ocupante_id is None and rateio not in RATEIOS_DESPESAS:
            raise ValueError("Selecione uma forma de rateio válida.")
        if ocupante_id is not None and not self.conn.execute(
            "SELECT 1 FROM lancamentos WHERE mes_id=? AND ocupante_id=?",(mid,ocupante_id)
        ).fetchone():
            raise ValueError("Selecione um inquilino com lançamento neste mês.")
        if ocupante_id is None and rateio=="pessoas" and self.contas_mes(mid)["total_pessoas_agua"]<=0:
            raise ValueError("Informe as pessoas nos lançamentos dos inquilinos antes de ratear por pessoas.")
        tipo="individual" if ocupante_id is not None else rateio
        with self.conn:
            if ident is None:
                self.conn.execute(
                    "INSERT INTO despesas_mes(mes_id,descricao,valor,rateio,ocupante_id) VALUES(?,?,?,?,?)",
                    (mid,descricao,valor,tipo,ocupante_id),
                )
            else:
                resultado=self.conn.execute(
                    "UPDATE despesas_mes SET descricao=?,valor=?,rateio=?,ocupante_id=? WHERE id=? AND mes_id=?",
                    (descricao,valor,tipo,ocupante_id,ident,mid),
                )
                if resultado.rowcount!=1:
                    raise ValueError("A despesa selecionada não pertence a este mês.")

    def gravar_despesa_multimes(self,periodos,descricao,valores,rateio="pessoas",ocupante_id=None,
                              ocupantes_ids=None,dividir_selecionados=True):
        descricao=descricao.strip()
        if not descricao:
            raise ValueError("Informe a descrição da despesa.")
        if len(periodos)!=len(valores) or not periodos:
            raise ValueError("Selecione ao menos um mês para a despesa.")
        if any(not math.isfinite(valor) or valor<=0 for valor in valores):
            raise ValueError("Cada valor mensal da despesa deve ser maior que zero.")
        if ocupante_id is None and rateio not in RATEIOS_DESPESAS:
            raise ValueError("Selecione uma forma de rateio válida.")
        if ocupante_id is not None and not self.conn.execute(
            "SELECT 1 FROM ocupantes WHERE id=?",(ocupante_id,)
        ).fetchone():
            raise ValueError("Selecione um inquilino válido.")
        if any(
            not isinstance(ano,int) or not isinstance(mes,int)
            or ano<ANO_INICIAL or ano>2040 or not 1<=mes<=12
            for ano,mes in periodos
        ):
            raise ValueError("Selecione meses entre 2026 e 2040.")
        if len(set(periodos))!=len(periodos):
            raise ValueError("Não selecione o mesmo mês mais de uma vez.")
        parcelas=None
        if ocupantes_ids is not None:
            if ocupante_id is not None or not ocupantes_ids or len(set(ocupantes_ids))!=len(ocupantes_ids):
                raise ValueError("Selecione ao menos um inquilino, sem repetir nomes.")
            for ident in ocupantes_ids:
                if not self.conn.execute("SELECT 1 FROM ocupantes WHERE id=?",(ident,)).fetchone():
                    raise ValueError("Um dos inquilinos selecionados não está cadastrado.")
                for ano,mes in periodos:
                    regra=self.conn.execute(
                        "SELECT l.cobrar_outras FROM lancamentos l JOIN meses m ON m.id=l.mes_id "
                        "WHERE l.ocupante_id=? AND m.ano=? AND m.mes=?",(ident,ano,mes),
                    ).fetchone()
                    if regra is None:
                        ocupante=self.conn.execute("SELECT * FROM ocupantes WHERE id=?",(ident,)).fetchone()
                        regra=self.regra_cobranca_ocupante(ocupante,ano,mes)
                    if not regra["cobrar_outras"]:
                        raise ValueError(
                            f"Há um inquilino selecionado isento de outras despesas em {mes:02d}/{ano}. "
                            "Remova-o da seleção ou ajuste a isenção antes de lançar."
                        )
            parcelas=[
                dividir_valor_por_meses(valor,len(ocupantes_ids)) if dividir_selecionados
                else [valor]*len(ocupantes_ids)
                for valor in valores
            ]
        tipo="individual" if ocupante_id is not None else rateio
        with self.conn:
            for indice,((ano,mes),valor) in enumerate(zip(periodos,valores)):
                self.conn.execute(
                    "INSERT OR IGNORE INTO meses(ano,mes,usar_rateio_despesas) VALUES(?,?,1)",
                    (ano,mes),
                )
                mid=self.conn.execute(
                    "SELECT id FROM meses WHERE ano=? AND mes=?",(ano,mes)
                ).fetchone()["id"]
                if parcelas is not None:
                    self.conn.executemany(
                        "INSERT INTO despesas_mes(mes_id,descricao,valor,rateio,ocupante_id) "
                        "VALUES(?,?,?,'individual',?)",
                        [(mid,descricao,parcela,ident)
                         for ident,parcela in zip(ocupantes_ids,parcelas[indice])],
                    )
                else:
                    self.conn.execute(
                        "INSERT INTO despesas_mes(mes_id,descricao,valor,rateio,ocupante_id) "
                        "VALUES(?,?,?,?,?)",
                        (mid,descricao,valor,tipo,ocupante_id),
                    )

    def editar_despesa(self,editar=False):
        mid=self.garantir_mes(int(self.m_ano.get()),int(self.m_mes.get()))
        row=None
        if editar:
            sel=self.despesas_tree.selection()
            if not sel:
                messagebox.showinfo("Selecione","Selecione uma despesa para editar.");return
            row=self.conn.execute("SELECT * FROM despesas_mes WHERE id=? AND mes_id=?",(sel[0],mid)).fetchone()
            if not row:
                messagebox.showerror("Despesa não encontrada","Carregue o mês e selecione a despesa novamente.");return
        win=tk.Toplevel(self.root);win.title("Outras despesas do mês");win.transient(self.root);win.grab_set()
        vincular_restauracao_modal(self.root,win)
        self.configurar_estilo_formulario(win)
        largura_tela=win.winfo_screenwidth()
        altura_tela=win.winfo_screenheight()
        largura_dialogo=min(800,max(280,largura_tela-24))
        altura_dialogo=min(760,max(240,altura_tela-48))
        colunas_lado_a_lado=largura_dialogo>=760
        win.geometry(f"{largura_dialogo}x{altura_dialogo}")
        win.minsize(min(360,largura_dialogo),min(320,altura_dialogo))
        win.columnconfigure(0,weight=1)
        win.rowconfigure(0,weight=1)
        conteudo=ttk.Frame(win,style="Form.TFrame")
        conteudo.grid(row=0,column=0,sticky="nsew")
        conteudo.columnconfigure(0,weight=1)
        conteudo.rowconfigure(0,weight=1)
        canvas=tk.Canvas(
            conteudo,bg=FUNDO,borderwidth=0,highlightthickness=0,
            width=largura_dialogo-24,height=max(180,altura_dialogo-120),
        )
        rolagem=ttk.Scrollbar(conteudo,orient="vertical",command=canvas.yview)
        canvas.configure(yscrollcommand=rolagem.set)
        canvas.grid(row=0,column=0,sticky="nsew")
        rolagem.grid(row=0,column=1,sticky="ns")
        formulario=ttk.Frame(canvas,style="Form.TFrame")
        formulario.columnconfigure(0,weight=1)
        if colunas_lado_a_lado:
            formulario.columnconfigure(1,weight=1)
        formulario_id=canvas.create_window(0,0,anchor="nw",window=formulario)
        formulario.bind(
            "<Configure>",
            lambda _evento:canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda evento:canvas.itemconfigure(formulario_id,width=evento.width),
        )
        dados=ttk.Frame(formulario,style="Form.TFrame",padding=12)
        dados.grid(row=0,column=0,columnspan=(2 if colunas_lado_a_lado else 1),sticky="ew")
        dados.columnconfigure(1,weight=1)
        quem=ttk.Frame(formulario,style="Form.TFrame",padding=12)
        quem.grid(row=1,column=0,sticky="nsew")
        quando=ttk.Frame(formulario,style="Form.TFrame",padding=12)
        quando.grid(
            row=1 if colunas_lado_a_lado else 2,
            column=1 if colunas_lado_a_lado else 0,
            sticky="nsew",
        )
        rodape=ttk.Frame(win,style="Form.TFrame",padding=12)
        rodape.grid(row=1,column=0,sticky="ew")
        rodape.columnconfigure(0,weight=1)
        win.rowconfigure(1,weight=0)
        descricao=tk.StringVar(value=row["descricao"] if row else "")
        valor=tk.StringVar(value=str(row["valor"]) if row else "")
        largura_entrada=max(12,min(48,(largura_dialogo-190)//8))
        wraplength_participantes=min(
            310,max(180,largura_dialogo-(480 if colunas_lado_a_lado else 56)),
        )
        ocupantes=self.conn.execute(
            "SELECT l.ocupante_id,o.nome FROM lancamentos l JOIN ocupantes o "
            "ON o.id=l.ocupante_id WHERE l.mes_id=? ORDER BY o.nome",(mid,)
        ).fetchall()
        ocupantes_por_nome={r["nome"]:r["ocupante_id"] for r in ocupantes}
        destino=tk.StringVar(value=next(
            (r["nome"] for r in ocupantes if row and r["ocupante_id"]==row["ocupante_id"]),
            "Todos",
        ))
        rateio=tk.StringVar(value=RATEIOS_DESPESAS.get(
            row["rateio"] if row and row["rateio"] in RATEIOS_DESPESAS else "pessoas"
        ))
        periodos={(int(self.m_ano.get()),int(self.m_mes.get()))}
        ttk.Label(dados,text="1. Qual é a despesa?",style="Form.TLabel").grid(row=0,column=0,columnspan=2,sticky="w",pady=(0,8))
        ttk.Label(dados,text="Descrição",style="Form.TLabel").grid(row=1,column=0,padx=(0,12),pady=4,sticky="w")
        descricao_entry=ttk.Entry(dados,textvariable=descricao,width=largura_entrada,style="Form.TEntry")
        descricao_entry.grid(row=1,column=1,pady=4,sticky="ew")
        ttk.Label(dados,text="Valor informado (R$)",style="Form.TLabel").grid(row=2,column=0,padx=(0,12),pady=4,sticky="w")
        ttk.Entry(dados,textvariable=valor,style="Form.TEntry").grid(row=2,column=1,pady=4,sticky="w")
        ttk.Label(quem,text="2. Quem participa?",style="Form.TLabel").pack(anchor="w",pady=(0,8))
        ttk.Label(quem,text="Cobrar de",style="Form.TLabel").pack(anchor="w")
        destino_combo=ttk.Combobox(
            quem,textvariable=destino,
            values=["Todos",*(["Escolher inquilinos"] if not row else []),*ocupantes_por_nome],
            state="readonly",width=28,
        )
        destino_combo.pack(fill="x",pady=(4,8))
        rateio_frame=ttk.Frame(quem,style="Form.TFrame")
        rateio_frame.pack(fill="x")
        ttk.Label(rateio_frame,text="Como cobrar de todos?",style="Form.TLabel").pack(anchor="w")
        rateio_combo=ttk.Combobox(
            rateio_frame,textvariable=rateio,values=list(RATEIOS_DESPESAS.values()),
            state="readonly",width=28,
        )
        rateio_combo.pack(fill="x",pady=4)
        participantes=ttk.Frame(quem,style="Form.TFrame")
        ttk.Label(
            participantes,text="Clique para incluir ou retirar cada participante.\nA REVISA também pode participar.",
            style="Form.TLabel",
        ).pack(anchor="w")
        nomes_frame=ttk.Frame(participantes,style="Form.TFrame")
        nomes_frame.pack(fill="both",expand=True,pady=6)
        lista_participantes=tk.Listbox(
            nomes_frame,height=6,selectmode="multiple",exportselection=False,
        )
        participantes_scroll=ttk.Scrollbar(nomes_frame,orient="vertical",command=lista_participantes.yview)
        participantes_scroll.pack(side="right",fill="y")
        lista_participantes.pack(side="left",fill="both",expand=True)
        lista_participantes.configure(yscrollcommand=participantes_scroll.set)
        for ocupante in ocupantes:
            lista_participantes.insert("end",ocupante["nome"])
        dividir_participantes=tk.BooleanVar(value=True)
        ttk.Checkbutton(
            participantes,text="Dividir igualmente entre os selecionados",
            variable=dividir_participantes,style="Form.TCheckbutton",
        ).pack(anchor="w")
        ttk.Label(
            participantes,text="Desmarcado: cada selecionado paga o valor integral do mês.",
            style="Form.TLabel",wraplength=wraplength_participantes,
        ).pack(anchor="w")
        def alternar_rateio(_evento=None):
            rateio_frame.pack_forget()
            participantes.pack_forget()
            if destino.get()=="Todos":
                rateio_frame.pack(fill="x")
            if destino.get()=="Escolher inquilinos":
                participantes.pack(fill="both",expand=True)
        destino_combo.bind("<<ComboboxSelected>>",alternar_rateio)
        alternar_rateio()
        ttk.Label(quando,text="3. Em quais meses?",style="Form.TLabel").pack(anchor="w",pady=(0,8))
        ttk.Label(quando,text="Meses escolhidos",style="Form.TLabel").pack(anchor="w")
        meses_frame=ttk.Frame(quando,style="Form.TFrame")
        meses_frame.pack(fill="x",pady=4)
        meses_lista=tk.Listbox(meses_frame,height=4,selectmode="extended",exportselection=False)
        meses_lista.pack(side="left",fill="both",expand=True)
        meses_scroll=ttk.Scrollbar(meses_frame,orient="vertical",command=meses_lista.yview)
        meses_scroll.pack(side="right",fill="y")
        meses_lista.configure(yscrollcommand=meses_scroll.set)
        seletor=ttk.Frame(quando,style="Form.TFrame")
        seletor.pack(anchor="w",pady=4)
        ano_mes=tk.StringVar(value=str(int(self.m_ano.get())))
        mes_mes=tk.StringVar(value=f"{int(self.m_mes.get()):02d}")
        ano_combo=ttk.Combobox(
            seletor,textvariable=ano_mes,values=[str(ano) for ano in range(ANO_INICIAL,2041)],
            state="readonly",width=7,
        )
        ano_combo.pack(side="left",padx=(0,6))
        mes_combo=ttk.Combobox(
            seletor,textvariable=mes_mes,values=[f"{mes:02d}" for mes in range(1,13)],
            state="readonly",width=4,
        )
        mes_combo.pack(side="left",padx=(0,6))
        def atualizar_meses():
            meses_lista.delete(0,"end")
            for ano,mes in sorted(periodos):
                meses_lista.insert("end",f"{mes:02d}/{ano}")
        def adicionar_mes():
            periodo=(int(ano_mes.get()),int(mes_mes.get()))
            if periodo in periodos:
                messagebox.showinfo("Mês já selecionado","Esse mês já está na lista.",parent=win)
                return
            periodos.add(periodo)
            atualizar_meses()
        def remover_meses():
            selecionados=meses_lista.curselection()
            meses_ordenados=sorted(periodos)
            for indice in selecionados:
                periodos.discard(meses_ordenados[indice])
            atualizar_meses()
        adicionar_botao=ttk.Button(seletor,text="Adicionar mês",command=adicionar_mes)
        adicionar_botao.pack(side="left",padx=(0,6))
        remover_botao=ttk.Button(quando,text="Retirar mês selecionado",command=remover_meses)
        remover_botao.pack(anchor="w",pady=(0,8))
        atualizar_meses()
        modo_mes=tk.StringVar(value="repetir")
        modo_label=ttk.Label(quando,text="Como usar o valor informado?",style="Form.TLabel")
        modo_label.pack(anchor="w",pady=(4,0))
        modo_frame=ttk.Frame(quando,style="Form.TFrame")
        modo_frame.pack(anchor="w",pady=4)
        ttk.Radiobutton(
            modo_frame,text="Repetir o valor em cada mês",
            variable=modo_mes,value="repetir",
        ).pack(anchor="w")
        ttk.Radiobutton(
            modo_frame,text="Parcelar o total entre os meses",
            variable=modo_mes,value="dividir",
        ).pack(anchor="w")
        if row:
            ano_combo.configure(state="disabled")
            mes_combo.configure(state="disabled")
            adicionar_botao.configure(state="disabled")
            remover_botao.configure(state="disabled")
            modo_label.pack_forget()
            modo_frame.pack_forget()
        ttk.Label(
            rodape,text="A despesa será somada às cobranças existentes. As isenções são mantidas.",
            style="Form.TLabel",wraplength=max(180,largura_dialogo-52),
        ).grid(row=0,column=0,columnspan=2,sticky="ew",pady=(0,8))
        def salvar():
            try:
                quantia=numero(valor.get(),"Valor total da despesa")
                tipo=next((chave for chave,label in RATEIOS_DESPESAS.items() if label==rateio.get()),"")
                ocupante_id=ocupantes_por_nome.get(destino.get())
                if row:
                    self.gravar_despesa(
                        mid,descricao.get(),quantia,row["id"],rateio=tipo,ocupante_id=ocupante_id,
                    )
                else:
                    lista_periodos=sorted(periodos)
                    if not lista_periodos:
                        raise ValueError("Selecione ao menos um mês para a despesa.")
                    if modo_mes.get()=="dividir":
                        valores=dividir_valor_por_meses(quantia,len(lista_periodos))
                    else:
                        valores=[quantia]*len(lista_periodos)
                    periodo_atual=(int(self.m_ano.get()),int(self.m_mes.get()))
                    if destino.get()=="Escolher inquilinos":
                        selecionados=[
                            ocupantes[indice]["ocupante_id"] for indice in lista_participantes.curselection()
                        ]
                        if not selecionados:
                            raise ValueError("Marque os inquilinos que participam da despesa.")
                        parcelas=[
                            dividir_valor_por_meses(v,len(selecionados))
                            if dividir_participantes.get() else [v]*len(selecionados)
                            for v in valores
                        ]
                        nomes={r["ocupante_id"]:r["nome"] for r in ocupantes}
                        detalhes="\n".join(
                            f"{mes:02d}/{ano}: "+", ".join(
                                f"{nomes[ident]}: {moeda(parcela)}"
                                for ident,parcela in zip(selecionados,mensais)
                            )
                            for (ano,mes),mensais in zip(lista_periodos,parcelas)
                        )
                        if not messagebox.askyesno(
                            "Confirmar despesa",
                            descricao.get()+"\n\n"+detalhes+
                            "\n\nCada parcela poderá ser editada ou excluída no respectivo mês.",
                            parent=win,
                        ):
                            return
                        self.gravar_despesa_multimes(
                            lista_periodos,descricao.get(),valores,rateio="inquilinos",
                            ocupantes_ids=selecionados,dividir_selecionados=dividir_participantes.get(),
                        )
                    elif lista_periodos==[periodo_atual]:
                        self.gravar_despesa(
                            mid,descricao.get(),valores[0],rateio=tipo,ocupante_id=ocupante_id,
                        )
                    else:
                        self.gravar_despesa_multimes(
                            lista_periodos,descricao.get(),valores,rateio=tipo,ocupante_id=ocupante_id,
                        )
            except (ValueError,sqlite3.Error) as e:
                messagebox.showerror("Verifique a despesa",str(e),parent=win);return
            win.destroy();self.atualizar_lancamentos()
        ttk.Button(rodape,text="Cancelar",command=win.destroy).grid(row=1,column=0,sticky="e",padx=8)
        ttk.Button(rodape,text="Salvar despesa",command=salvar).grid(row=1,column=1,sticky="e")
        win.update_idletasks()
        x=max(
            0,min(
                largura_tela-largura_dialogo,
                self.root.winfo_rootx()+(self.root.winfo_width()-largura_dialogo)//2,
            ),
        )
        y=max(
            0,min(
                altura_tela-altura_dialogo,
                self.root.winfo_rooty()+(self.root.winfo_height()-altura_dialogo)//2,
            ),
        )
        win.geometry(f"{largura_dialogo}x{altura_dialogo}+{x}+{y}")
        descricao_entry.focus_set()

    def excluir_despesa(self):
        sel=self.despesas_tree.selection()
        if not sel:
            messagebox.showinfo("Selecione","Selecione uma despesa para excluir.");return
        mid=self.garantir_mes(int(self.m_ano.get()),int(self.m_mes.get()))
        if not messagebox.askyesno("Excluir despesa","Excluir a despesa e recalcular as cobranças deste mês?",parent=self.root):
            return
        resultado=self.conn.execute("DELETE FROM despesas_mes WHERE id=? AND mes_id=?",(sel[0],mid))
        if resultado.rowcount!=1:
            messagebox.showerror("Despesa não encontrada","Carregue o mês e tente novamente.");return
        self.conn.commit();self.atualizar_lancamentos()

    def campos_cobranca(self,parent,row):
        variaveis={}
        ttk.Label(parent,text="Marque somente as cobranças que este inquilino deve pagar.\nDesmarcado = isento.",style="Form.TLabel").pack(anchor="w",pady=(0,8))
        for chave,label in COBRANCAS:
            variaveis[chave]=tk.BooleanVar(value=bool(row[f"cobrar_{chave}"]))
            ttk.Checkbutton(parent,text=label,variable=variaveis[chave],style="Form.TCheckbutton").pack(anchor="w",pady=4)
        return variaveis

    def salvar_cobrancas(self,tabela,ident,flags):
        if tabela not in ("ocupantes","lancamentos") or set(flags)!={chave for chave,_ in COBRANCAS}:
            raise ValueError("Configuração de cobranças inválida.")
        campos=",".join(f"cobrar_{chave}=?" for chave,_ in COBRANCAS)
        self.conn.execute(f"UPDATE {tabela} SET {campos} WHERE id=?",
                          (*[int(bool(flags[chave])) for chave,_ in COBRANCAS],ident))

    def regra_cobranca_ocupante(self,ocupante,ano,mes):
        return self.conn.execute(
            "SELECT * FROM padroes_cobranca WHERE ocupante_id=? AND periodo<=? "
            "ORDER BY periodo DESC LIMIT 1",
            (ocupante["id"],ano*100+mes),
        ).fetchone() or ocupante

    def regra_pessoas_ocupante(self,ocupante_id,ano,mes):
        return self.conn.execute(
            "SELECT numero_pessoas FROM padroes_pessoas WHERE ocupante_id=? AND periodo<=? "
            "ORDER BY periodo DESC LIMIT 1",
            (ocupante_id,ano*100+mes),
        ).fetchone()

    def pessoas_ocupante_no_periodo(self,ocupante_id,ano,mes):
        regra=self.regra_pessoas_ocupante(ocupante_id,ano,mes)
        if regra is not None:
            return regra["numero_pessoas"]
        row=self.conn.execute(
            "SELECT l.numero_pessoas FROM lancamentos l JOIN meses m ON m.id=l.mes_id "
            "WHERE l.ocupante_id=? AND m.ano*100+m.mes<=? "
            "ORDER BY m.ano DESC,m.mes DESC LIMIT 1",
            (ocupante_id,ano*100+mes),
        ).fetchone()
        return row["numero_pessoas"] if row is not None else 0

    def editar_celula_inquilino(self,event):
        regiao=self.oc_tree.identify_region(event.x,event.y)
        if regiao!="cell":
            return
        ident=self.oc_tree.identify_row(event.y)
        coluna=self.oc_tree.identify_column(event.x)
        if not ident:
            return
        self.oc_tree.selection_set(ident)
        self.oc_tree.focus(ident)
        if coluna=="#2":
            self.root.after_idle(lambda:self.iniciar_edicao_observacao(ident))
            return "break"
        if coluna=="#3":
            self.root.after_idle(lambda:self.iniciar_edicao_pessoas(ident))
            return "break"
        if coluna=="#10":
            try:
                row=self.conn.execute(
                    "SELECT avisar_leitura FROM ocupantes WHERE id=?",(ident,)
                ).fetchone()
                if row is None:
                    raise ValueError("Inquilino não encontrado.")
                self.conn.execute(
                    "UPDATE ocupantes SET avisar_leitura=? WHERE id=?",
                    (0 if row["avisar_leitura"] else 1,ident),
                )
                self.conn.commit()
            except (ValueError,sqlite3.Error) as erro:
                messagebox.showerror("Não foi possível atualizar o aviso de leitura",str(erro),parent=self.root)
                self.atualizar_ocupantes()
                return "break"
            self.atualizar_ocupantes()
            return "break"
        colunas_cobranca={
            f"#{indice+4}":chave for indice,(chave,_) in enumerate(COBRANCAS)
        }
        chave=colunas_cobranca.get(coluna)
        if chave is None:
            return
        flags={
            cobranca:self.oc_tree.set(ident,f"cobrar_{cobranca}")=="Sim"
            for cobranca,_ in COBRANCAS
        }
        flags[chave]=not flags[chave]
        try:
            ano=int(self.m_ano.get())
            mes=int(self.m_mes.get())
            self.aplicar_padrao_cobrancas(int(ident),flags,ano,mes)
        except (ValueError,sqlite3.Error) as erro:
            messagebox.showerror("Não foi possível atualizar a cobrança",str(erro),parent=self.root)
            self.atualizar_ocupantes()
            return "break"
        self.atualizar_ocupantes()
        self.atualizar_lancamentos()
        return "break"

    def iniciar_edicao_observacao(self,ident):
        if self.oc_obs_editor is not None:
            self.salvar_edicao_observacao()
        caixa=self.oc_tree.bbox(ident,"observacoes")
        if not caixa:
            return
        x,y,largura,altura=caixa
        valor=self.oc_tree.set(ident,"observacoes")
        editor=ttk.Entry(self.oc_tree)
        editor.insert(0,valor)
        editor.place(x=x,y=y,width=largura,height=altura)
        self.oc_obs_editor=editor
        self.oc_obs_editor_id=ident
        editor.bind("<Return>",self.salvar_edicao_observacao)
        editor.bind("<FocusOut>",self.salvar_edicao_observacao)
        editor.bind("<Escape>",self.cancelar_edicao_observacao)
        editor.focus_set()
        editor.selection_range(0,"end")

    def cancelar_edicao_observacao(self,event=None):
        editor=self.oc_obs_editor
        self.oc_obs_editor=None
        self.oc_obs_editor_id=None
        if editor is not None:
            editor.destroy()
        return "break"

    def salvar_edicao_observacao(self,event=None):
        editor=self.oc_obs_editor
        ident=self.oc_obs_editor_id
        if editor is None or ident is None:
            return "break"
        observacoes=editor.get().strip()
        self.oc_obs_editor=None
        self.oc_obs_editor_id=None
        editor.destroy()
        try:
            self.salvar_observacao_ocupante(ident,observacoes)
        except (sqlite3.Error,ValueError) as erro:
            messagebox.showerror("Não foi possível salvar a observação",str(erro),parent=self.root)
            self.atualizar_ocupantes()
            return "break"
        if self.oc_tree.exists(ident):
            self.oc_tree.set(ident,"observacoes",observacoes)
        return "break"

    def salvar_observacao_ocupante(self,ident,observacoes):
        with self.conn:
            resultado=self.conn.execute(
                "UPDATE ocupantes SET observacoes=? WHERE id=?",
                (observacoes.strip(),ident),
            )
            if resultado.rowcount!=1:
                raise ValueError("O inquilino selecionado não foi encontrado.")

    def iniciar_edicao_pessoas(self,ident):
        if self.oc_pessoas_editor is not None:
            self.salvar_edicao_pessoas()
        caixa=self.oc_tree.bbox(ident,"numero_pessoas")
        if not caixa:
            return
        x,y,largura,altura=caixa
        editor=ttk.Entry(self.oc_tree)
        editor.insert(0,self.oc_tree.set(ident,"numero_pessoas"))
        editor.place(x=x,y=y,width=largura,height=altura)
        self.oc_pessoas_editor=editor
        self.oc_pessoas_editor_id=ident
        editor.bind("<Return>",self.salvar_edicao_pessoas)
        editor.bind("<FocusOut>",self.salvar_edicao_pessoas)
        editor.bind("<Escape>",self.cancelar_edicao_pessoas)
        editor.focus_set()
        editor.selection_range(0,"end")

    def cancelar_edicao_pessoas(self,event=None):
        editor=self.oc_pessoas_editor
        self.oc_pessoas_editor=None
        self.oc_pessoas_editor_id=None
        if editor is not None:
            editor.destroy()
        return "break"

    def salvar_edicao_pessoas(self,event=None):
        editor=self.oc_pessoas_editor
        ident=self.oc_pessoas_editor_id
        if editor is None or ident is None:
            return "break"
        valor=editor.get().strip()
        self.oc_pessoas_editor=None
        self.oc_pessoas_editor_id=None
        editor.destroy()
        try:
            pessoas=int(valor)
        except ValueError:
            messagebox.showerror(
                "Não foi possível salvar as pessoas",
                "Informe um número inteiro de pessoas igual ou maior que zero.",
                parent=self.root,
            )
            self.atualizar_ocupantes()
            return "break"
        try:
            ano=int(self.m_ano.get())
            mes=int(self.m_mes.get())
            self.salvar_pessoas_ocupante(int(ident),ano,mes,pessoas)
        except (ValueError,sqlite3.Error) as erro:
            messagebox.showerror("Não foi possível salvar as pessoas",str(erro),parent=self.root)
            self.atualizar_ocupantes()
            return "break"
        self.atualizar_ocupantes()
        self.atualizar_lancamentos()
        return "break"

    def salvar_pessoas_ocupante(self,ident,ano,mes,pessoas):
        if ano<ANO_INICIAL or not 1<=mes<=12:
            raise ValueError("Período inválido para a quantidade de pessoas.")
        if isinstance(pessoas,bool) or not isinstance(pessoas,int) or pessoas<0:
            raise ValueError("Informe um número inteiro de pessoas igual ou maior que zero.")
        if self.conn.execute("SELECT 1 FROM ocupantes WHERE id=?",(ident,)).fetchone() is None:
            raise ValueError("Inquilino não encontrado.")
        with self.conn:
            self.conn.execute(
                "DELETE FROM padroes_pessoas WHERE ocupante_id=?",(ident,)
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO padroes_pessoas(ocupante_id,periodo,numero_pessoas) "
                "VALUES(?,?,?)",
                (ident,ANO_INICIAL*100+1,pessoas),
            )
            self.propagar_pessoas_ocupante(ident,pessoas)

    def aplicar_padrao_cobrancas(self,ident,flags,ano,mes):
        if ano<ANO_INICIAL or not 1<=mes<=12:
            raise ValueError("Período inválido para o padrão de cobrança.")
        if set(flags)!={chave for chave,_ in COBRANCAS}:
            raise ValueError("Configuração de cobranças inválida.")
        ocupante=self.conn.execute("SELECT * FROM ocupantes WHERE id=?",(ident,)).fetchone()
        if ocupante is None:
            raise ValueError("Inquilino não encontrado.")
        campos=",".join(f"cobrar_{chave}" for chave,_ in COBRANCAS)
        parametros=",".join("?" for _ in COBRANCAS)
        valores=[int(bool(flags[chave])) for chave,_ in COBRANCAS]
        periodo=ano*100+mes
        with self.conn:
            self.conn.execute(
                f"INSERT OR IGNORE INTO padroes_cobranca(ocupante_id,periodo,{campos}) VALUES(?,?,{parametros})",
                (ident,ANO_INICIAL*100+1,*[ocupante[f"cobrar_{chave}"] for chave,_ in COBRANCAS])
            )
            # Uma nova decisão substitui padrões futuros previamente programados.
            self.conn.execute("DELETE FROM padroes_cobranca WHERE ocupante_id=? AND periodo>=?",(ident,periodo))
            self.conn.execute(
                f"INSERT INTO padroes_cobranca(ocupante_id,periodo,{campos}) VALUES(?,?,{parametros})",
                (ident,periodo,*valores)
            )
            self.salvar_cobrancas("ocupantes",ident,flags)
            atribuicoes=",".join(f"cobrar_{chave}=?" for chave,_ in COBRANCAS)
            self.conn.execute(
                f"UPDATE lancamentos SET {atribuicoes} WHERE ocupante_id=? AND mes_id IN "
                "(SELECT id FROM meses WHERE ano*100+mes>=?)",(*valores,ident,periodo)
            )

    def carregar_rateio_agua(self,mid):
        mes=self.contas_mes(mid)
        self.agua_total_var.set(str(mes["conta_agua"] or 0))
        self.agua_pessoas_var.set(str(mes["total_pessoas_agua"] or 0))
        self.atualizar_previa_agua()

    def carregar_rateio_energia(self,mid):
        if not hasattr(self,"energia_total_var"):
            return
        mes=self.contas_mes(mid)
        self.energia_total_var.set(str(mes["conta_energia"]))
        self.energia_kwh_var.set(str(mes["total_kwh"]))
        self.energia_iluminacao_var.set(str(mes["iluminacao_publica"]))
        self.atualizar_previa_energia()

    def atualizar_previa_energia(self):
        try:
            valor=numero(self.energia_total_var.get(),"Valor da energia")
            kwh=numero(self.energia_kwh_var.get(),"Consumo total em kWh")
            iluminacao=numero(self.energia_iluminacao_var.get(),"Iluminação pública")
            if valor<0 or kwh<=0:
                self.energia_previa.set("Informe valor não negativo e kWh maiores que zero")
            elif iluminacao<0 or iluminacao>valor:
                self.energia_previa.set("Iluminação deve estar entre zero e o total da conta")
            else:
                base,adicional=self.tarifas_energia(valor,kwh,iluminacao)
                self.energia_previa.set(
                    f"Energia: R$ {base:.6f}/kWh\nIluminação: R$ {adicional:.6f}/kWh\nTotal: R$ {base+adicional:.6f}/kWh".replace(".",",")
                )
        except ValueError as e:
            self.energia_previa.set(str(e))

    def tarifas_energia(self,valor,kwh,iluminacao):
        return (valor-iluminacao)/kwh,iluminacao/kwh

    def gravar_rateio_energia(self,mid,valor,kwh,iluminacao=0):
        if not math.isfinite(valor) or not math.isfinite(kwh) or valor<0 or kwh<=0:
            raise ValueError("Informe valor não negativo e consumo total em kWh maior que zero.")
        if not math.isfinite(iluminacao) or iluminacao<0 or iluminacao>valor:
            raise ValueError("A iluminação pública deve ser igual ou maior que zero e não pode superar o total da conta.")
        revisa=self.conn.execute("SELECT id FROM ocupantes WHERE nome='REVISA'").fetchone()
        if revisa is None:
            raise ValueError("Cadastre a REVISA para receber o saldo da energia.")
        with self.conn:
            campos=",".join(f"cobrar_{chave}" for chave,_ in COBRANCAS)
            self.conn.execute(
                f"INSERT OR IGNORE INTO lancamentos(mes_id,ocupante_id,{campos}) "
                f"SELECT ?,id,{campos} FROM ocupantes WHERE id=?",(mid,revisa["id"])
            )
            self.conn.execute("UPDATE meses SET conta_energia=?,total_kwh=?,iluminacao_publica=?,usar_rateio_energia=1 WHERE id=?",
                              (valor,kwh,iluminacao,mid))

    def salvar_rateio_energia(self):
        try:
            valor=numero(self.energia_total_var.get(),"Valor da energia")
            kwh=numero(self.energia_kwh_var.get(),"Consumo total em kWh")
            iluminacao=numero(self.energia_iluminacao_var.get(),"Iluminação pública")
            mid=self.garantir_mes(int(self.m_ano.get()),int(self.m_mes.get()))
            self.gravar_rateio_energia(mid,valor,kwh,iluminacao)
        except ValueError as e:
            messagebox.showerror("Verifique a energia",str(e),parent=self.root);return
        self.atualizar_lancamentos()
        messagebox.showinfo("Energia salva","Tarifa mensal calculada. O saldo da conta fica para a REVISA.",parent=self.root)

    def atualizar_previa_agua(self):
        if not hasattr(self,"agua_por_pessoa"):
            return
        mid=self.conn.execute("SELECT id FROM meses WHERE ano=? AND mes=?",
                              (self.m_ano.get(),self.m_mes.get())).fetchone()
        self.agua_pessoas_var.set(str(self.pessoas_terreno(mid["id"]) if mid else 0))
        try:
            valor=numero(self.agua_total_var.get(),"Valor total da água")
            pessoas=self.pessoas_cobradas(mid["id"],"agua") if mid else 0
            if pessoas>0:
                self.agua_por_pessoa.set(f"{moeda(valor/pessoas)} por pessoa\n{pessoas} pessoas não isentas")
            elif valor>0:
                self.agua_por_pessoa.set("Pendente: informe pessoas nos inquilinos não isentos")
            else:
                self.agua_por_pessoa.set("R$ 0,00 por pessoa")
        except ValueError:
            self.agua_por_pessoa.set("Confira os valores informados")

    def salvar_rateio_agua(self):
        try:
            valor=numero(self.agua_total_var.get(),"Valor total da água")
            if valor<0:
                raise ValueError("O valor total da água não pode ser negativo.")
            ano=int(self.m_ano.get())
            mes=int(self.m_mes.get())
            mid=self.garantir_mes(ano,mes)
            pessoas=self.pessoas_terreno(mid)
        except ValueError as e:
            messagebox.showerror("Verifique os dados do rateio",str(e),parent=self.root)
            return
        self.conn.execute(
            "UPDATE meses SET conta_agua=?,total_pessoas_agua=? WHERE id=?",
            (valor,int(pessoas),mid),
        )
        self.conn.commit()
        self.atualizar_lancamentos()
        if valor and not self.pessoas_cobradas(mid,"agua"):
            messagebox.showwarning("Água salva, rateio pendente","Informe as pessoas nos lançamentos dos inquilinos não isentos. Sem elas, a água ainda não será cobrada.",parent=self.root)
        else:
            messagebox.showinfo("Rateio salvo","O valor da água foi atualizado para os inquilinos deste mês.",parent=self.root)

    def editar_contas_mes(self):
        ano=int(self.m_ano.get());mes=int(self.m_mes.get())
        if ano<2026:messagebox.showwarning("Período","O sistema começa em 2026.");return
        mid=self.garantir_mes(ano,mes); row=self.contas_mes(mid)
        win=tk.Toplevel(self.root);win.title(f"Contas gerais — {mes:02d}/{ano}");win.transient(self.root);win.grab_set()
        self.configurar_estilo_formulario(win)
        fields=[("Conta de energia (R$)","energia",row["conta_energia"]),("Consumo total de energia (kWh)","kwh",row["total_kwh"]),("Valor total da conta de água do mês (R$)","agua",row["conta_agua"]),("Pessoas no terreno (automático)","pessoas_agua",row["total_pessoas_agua"])]
        vars={}
        for i,(label,key,val) in enumerate(fields):
            ttk.Label(win,text=label,style="Form.TLabel").grid(row=i,column=0,padx=12,pady=8,sticky="w")
            vars[key]=tk.StringVar(value=str(val));ttk.Entry(win,textvariable=vars[key],width=20,style="Form.TEntry",state="readonly" if key=="pessoas_agua" else "normal").grid(row=i,column=1,padx=12,pady=8)
        ttk.Label(win,text="Iluminação pública incluída (R$)",style="Form.TLabel").grid(row=5,column=0,padx=12,pady=8,sticky="w")
        vars["iluminacao"]=tk.StringVar(value=str(row["iluminacao_publica"]))
        ttk.Entry(win,textvariable=vars["iluminacao"],width=20,style="Form.TEntry").grid(row=5,column=1,padx=12,pady=8)
        ttk.Label(win,text="Observações",style="Form.TLabel").grid(row=6,column=0,padx=12,pady=8,sticky="w")
        obs=tk.Text(win,width=38,height=3,bg="#ffffff",fg="#18212b",insertbackground="#18212b",relief="solid",bd=1);obs.grid(row=6,column=1,padx=12,pady=8);obs.insert("1.0",row["observacoes"] or "")
        ttk.Label(win,text="Energia: total já inclui iluminação pública; saldo para REVISA. Água: dividida somente entre não isentos.",style="Form.TLabel",wraplength=430).grid(row=7,column=0,columnspan=2,padx=12,pady=(0,8),sticky="w")
        def salvar():
            try:
                vals=[numero(vars[k].get(),k) for k in ("energia","agua","pessoas_agua")]
                vals[2]=self.pessoas_terreno(mid)
                if any(v<0 for v in vals):
                    raise ValueError("Os valores das contas e a quantidade de pessoas não podem ser negativos.")
            except ValueError as e:messagebox.showerror("Verifique os valores",str(e),parent=win);return
            try:
                kwh=numero(vars["kwh"].get(),"Consumo total em kWh")
                iluminacao=numero(vars["iluminacao"].get(),"Iluminação pública")
                if kwh<0:
                    raise ValueError("O consumo total não pode ser negativo.")
                with self.conn:
                    if kwh>0 or row["usar_rateio_energia"]:
                        self.gravar_rateio_energia(mid,vals[0],kwh,iluminacao)
                    elif vals[0]!=row["conta_energia"] or iluminacao!=row["iluminacao_publica"]:
                        raise ValueError("Informe os kWh totais para calcular a nova conta de energia.")
                    self.conn.execute("UPDATE meses SET conta_agua=?,total_pessoas_agua=?,observacoes=? WHERE id=?",
                                      (vals[1],int(vals[2]),obs.get("1.0","end").strip(),mid))
            except ValueError as e:
                messagebox.showerror("Verifique a energia",str(e),parent=win);return
            win.destroy();self.carregar_rateio_agua(mid);self.carregar_rateio_energia(mid);self.atualizar_lancamentos()
        ttk.Button(win,text="Salvar contas",command=salvar).grid(row=8,column=1,padx=12,pady=12,sticky="e")

    def obter_lancamento_selecionado(self):
        sel=self.lanc.selection()
        if not sel:messagebox.showinfo("Selecione","Selecione um lançamento na tabela.");return None
        return self.conn.execute("""SELECT l.*,o.nome,m.ano,m.mes FROM lancamentos l JOIN ocupantes o ON o.id=l.ocupante_id JOIN meses m ON m.id=l.mes_id WHERE l.id=?""",(self.lanc.item(sel[0],"values")[0],)).fetchone()

    def editar_lancamento(self):
        row=self.obter_lancamento_selecionado()
        if not row:return
        win=tk.Toplevel(self.root)
        win.title("Editar lançamento")
        win.transient(self.root)
        win.grab_set()
        win.resizable(False,False)
        self.configurar_estilo_formulario(win)

        moldura=ttk.Frame(win,padding=14,style="Form.TFrame")
        moldura.pack(fill="both",expand=True)
        ttk.Label(moldura,text=row["nome"],style="Form.Title.TLabel").pack(anchor="w")
        ttk.Label(moldura,text=f"Lançamento mensal • {row['mes']:02d}/{row['ano']}",style="Form.Subtitle.TLabel").pack(anchor="w",pady=(2,8))
        abas=ttk.Notebook(moldura);abas.pack(fill="both",expand=True)
        conteudo=ttk.Frame(abas,padding=10,style="Form.TFrame")
        extras=ttk.Frame(abas,padding=10,style="Form.TFrame")
        regras=ttk.Frame(abas,padding=14,style="Form.TFrame")
        abas.add(conteudo,text="Energia e rateios")
        abas.add(extras,text="Aluguel e ajustes")
        abas.add(regras,text="Cobranças / isenções")
        flags=self.campos_cobranca(regras,row)
        usar_padrao=tk.BooleanVar(value=False)
        ttk.Checkbutton(regras,text="Aplicar padrão deste mês em diante",variable=usar_padrao,
                        style="Form.TCheckbutton").pack(anchor="w",pady=(16,4))
        ttk.Label(regras,text="Para cobrar somente luz: marque apenas Energia.\nO padrão atualiza este mês e os seguintes; preserva os anteriores.",
                  style="Form.TLabel").pack(anchor="w",pady=8)

        vars={}
        leitura_editada={"valor":bool(row["leitura_informada"])}
        def criar_campo(parent,label,key,coluna):
            celula=ttk.Frame(parent,style="Form.TFrame")
            celula.grid(row=0,column=coluna,padx=(0 if coluna==0 else 10,0),sticky="ew")
            ttk.Label(celula,text=label,style="Form.TLabel").pack(anchor="w",pady=(0,4))
            vars[key]=tk.StringVar(value=str(row[key] or 0))
            ttk.Entry(celula,textvariable=vars[key],width=17,style="Form.TEntry").pack(fill="x")

        energia=ttk.LabelFrame(conteudo,text="  Energia  ",padding=12,style="Form.TLabelframe")
        energia.pack(fill="x",pady=(0,10))
        for coluna,(label,key) in enumerate((
            ("Leitura anterior","leitura_inicial"),
            ("Leitura atual","leitura_final"),
        )):
            criar_campo(energia,label,key,coluna)
        vars["leitura_final"].trace_add(
            "write",lambda *_:leitura_editada.update(valor=True)
        )
        conta=self.contas_mes(row["mes_id"])
        if conta["usar_rateio_energia"]:
            vars["tarifa_kwh"]=tk.StringVar(value=str(row["tarifa_kwh"] or 0))
            base,adicional=self.tarifas_energia(conta["conta_energia"],conta["total_kwh"],conta["iluminacao_publica"])
            info=f"Por kWh: energia R$ {base:.6f} + iluminação R$ {adicional:.6f}."
            if row["nome"]=="REVISA":
                info="REVISA recebe o saldo da conta; suas leituras não entram no cálculo."
        else:
            criar_campo(energia,"Tarifa antiga (R$/kWh)","tarifa_kwh",2)
            info="Mês antigo: tarifa individual. Salve a conta e kWh na lateral para usar tarifa mensal."
        ttk.Label(energia,text=info,style="Form.TLabel",wraplength=500).grid(
            row=1,column=0,columnspan=3,sticky="w",pady=(8,0)
        )
        ttk.Label(
            conteudo,text="A quantidade de pessoas e o rateio da água são gerenciados na aba Inquilinos.",
            style="Form.TLabel",wraplength=500,
        ).pack(anchor="w",pady=(0,10))

        adicionais=ttk.LabelFrame(extras,text="  Outros valores  ",padding=12,style="Form.TLabelframe")
        adicionais.pack(fill="x",pady=(0,10))
        for coluna,(label,key) in enumerate((
            ("Aluguel (R$)","aluguel"),
            ("Ajuste (+/- R$)","ajuste"),
        )):
            criar_campo(adicionais,label,key,coluna)
        ttk.Label(adicionais,text="Outras despesas: lançadas e rateadas na tabela abaixo do resumo mensal.",
                  style="Form.TLabel").grid(row=1,column=0,columnspan=2,sticky="w",pady=(8,0))

        observacoes=ttk.LabelFrame(extras,text="  Observações  ",padding=10,style="Form.TLabelframe")
        observacoes.pack(fill="x",pady=(0,12))
        obs=tk.Text(observacoes,width=62,height=3,wrap="word",bg="#ffffff",fg="#18212b",insertbackground="#18212b",relief="solid",bd=1)
        obs.pack(fill="x")
        obs.insert("1.0",row["observacoes"] or "")

        def salvar():
            try:
                d={k:numero(v.get(),k) for k,v in vars.items()}
                if d["leitura_final"]<d["leitura_inicial"]:raise ValueError("A leitura final não pode ser menor que a inicial.")
                if any(d[k]<0 for k in ("tarifa_kwh","aluguel")):raise ValueError("Tarifa e aluguel não podem ser negativos.")
            except ValueError as e:messagebox.showerror("Verifique os dados",str(e),parent=win);return
            escolhas={chave:v.get() for chave,v in flags.items()}
            with self.conn:
                self.conn.execute("""UPDATE lancamentos SET leitura_inicial=?,leitura_final=?,leitura_informada=?,tarifa_kwh=?,aluguel=?,ajuste=?,observacoes=? WHERE id=?""",
                    (d["leitura_inicial"],d["leitura_final"],
                     int(leitura_editada["valor"] or d["leitura_final"]!=d["leitura_inicial"]),
                     d["tarifa_kwh"],d["aluguel"],d["ajuste"],
                     obs.get("1.0","end").strip(),row["id"]))
                self.propagar_leitura_seguinte(
                    row["ocupante_id"],row["ano"],row["mes"],d["leitura_final"]
                )
                self.salvar_cobrancas("lancamentos",row["id"],escolhas)
                if usar_padrao.get():
                    self.aplicar_padrao_cobrancas(row["ocupante_id"],escolhas,row["ano"],row["mes"])
            win.destroy();self.atualizar_lancamentos()
        botoes=ttk.Frame(moldura,style="Form.TFrame")
        botoes.pack(fill="x")
        ttk.Button(botoes,text="Cancelar",command=win.destroy).pack(side="right")
        ttk.Button(botoes,text="Salvar lançamento",command=salvar).pack(side="right",padx=(0,8))

    def propagar_pessoas_ocupante(self,ocupante_id,pessoas):
        self.conn.execute(
            "UPDATE lancamentos SET numero_pessoas=? WHERE ocupante_id=?",
            (pessoas,ocupante_id),
        )

    def propagar_leitura_seguinte(self,ocupante_id,ano,mes,leitura):
        if mes==12:
            ano_seguinte,mes_seguinte=ano+1,1
        else:
            ano_seguinte,mes_seguinte=ano,mes+1
        seguinte=self.conn.execute(
            "SELECT l.id,l.leitura_inicial,l.leitura_final FROM lancamentos l "
            "JOIN meses m ON m.id=l.mes_id "
            "WHERE l.ocupante_id=? AND m.ano=? AND m.mes=?",
            (ocupante_id,ano_seguinte,mes_seguinte),
        ).fetchone()
        if seguinte is None:
            return
        leitura_final=(
            leitura
            if seguinte["leitura_final"]==seguinte["leitura_inicial"]
            else seguinte["leitura_final"]
        )
        self.conn.execute(
            "UPDATE lancamentos SET leitura_inicial=?,leitura_final=? WHERE id=?",
            (leitura,leitura_final,seguinte["id"]),
        )

    def pessoas_cobradas(self,mid,tipo):
        if tipo not in ("agua","outras"):
            raise ValueError("Tipo de rateio inválido.")
        return self.conn.execute(
            f"SELECT COALESCE(SUM(numero_pessoas),0) total FROM lancamentos "
            f"WHERE mes_id=? AND cobrar_{tipo}=1",(mid,)
        ).fetchone()["total"]

    def total_despesas(self,mid,rateio=None):
        return self.conn.execute(
            "SELECT COALESCE(SUM(valor),0) total FROM despesas_mes WHERE mes_id=? AND (? IS NULL OR rateio=?)",
            (mid,rateio,rateio),
        ).fetchone()["total"]

    def tarifa_energia(self,row):
        mes=self.contas_mes(row["mes_id"])
        if mes["usar_rateio_energia"]:
            return sum(self.tarifas_energia(mes["conta_energia"],mes["total_kwh"],mes["iluminacao_publica"]))
        return row["tarifa_kwh"] or 0

    def energia_lancamento(self,row):
        if not row["cobrar_energia"]:
            return 0
        mes=self.contas_mes(row["mes_id"])
        consumo=max(0,(row["leitura_final"] or 0)-(row["leitura_inicial"] or 0))
        if not mes["usar_rateio_energia"]:
            return consumo*(row["tarifa_kwh"] or 0)
        tarifa=self.tarifa_energia(row)
        nome=self.conn.execute("SELECT nome FROM ocupantes WHERE id=?",(row["ocupante_id"],)).fetchone()["nome"]
        if nome!="REVISA":
            return round(consumo*tarifa,2)
        outros=self.conn.execute(
            "SELECT l.* FROM lancamentos l JOIN ocupantes o ON o.id=l.ocupante_id "
            "WHERE l.mes_id=? AND o.nome!='REVISA' AND l.cobrar_energia=1",(row["mes_id"],)
        ).fetchall()
        return round(mes["conta_energia"]-sum(
            round(max(0,(r["leitura_final"] or 0)-(r["leitura_inicial"] or 0))*tarifa,2)
            for r in outros
        ),2)

    def cobrancas_lancamento(self,row):
        mid=row["mes_id"];mes=self.contas_mes(mid)
        pessoas_agua=self.pessoas_cobradas(mid,"agua")
        outras=(row["outras_despesas"] or 0) if not mes["usar_rateio_despesas"] else 0
        divisor=mes["total_pessoas_agua"]
        if divisor:
            outras+=self.total_despesas(mid,"pessoas")*(row["numero_pessoas"] or 0)/divisor
        inquilinos=self.conn.execute(
            "SELECT COUNT(*) FROM lancamentos WHERE mes_id=? AND cobrar_outras=1",(mid,)
        ).fetchone()[0]
        if inquilinos:
            outras+=self.total_despesas(mid,"inquilinos")
        outras+=self.conn.execute(
            "SELECT COALESCE(SUM(valor),0) FROM despesas_mes "
            "WHERE mes_id=? AND rateio='individual' AND ocupante_id=?",
            (mid,row["ocupante_id"]),
        ).fetchone()[0]
        valores={
            "energia":self.energia_lancamento(row),
            "agua":mes["conta_agua"]*(row["numero_pessoas"] or 0)/pessoas_agua if pessoas_agua else 0,
            "aluguel":row["aluguel"] or 0, "outras":outras, "ajuste":row["ajuste"] or 0,
        }
        return {chave:valor if row[f"cobrar_{chave}"] else 0 for chave,valor in valores.items()}

    def valores_lancamento(self,row):
        valores=self.cobrancas_lancamento(row)
        total=round(sum(valores.values()),2)
        pago=round(self.conn.execute(
            "SELECT COALESCE(SUM(valor),0) s FROM pagamentos "
            "WHERE lancamento_id=? AND revertido_em IS NULL",(row["id"],)
        ).fetchone()["s"],2)
        pago=round(pago+self.baixa_automatica(row,total,pago),2)
        saldo=round(max(0,total-pago),2)
        return valores["energia"],valores["agua"],total,pago,saldo

    def baixa_automatica(self,row,total,pago):
        ocupante=self.conn.execute("SELECT nome FROM ocupantes WHERE id=?",(row["ocupante_id"],)).fetchone()
        return max(0,total-pago) if ocupante["nome"]=="REVISA" else 0

    def atualizar_aviso_aberto(self):
        if not hasattr(self,"aviso_aberto"):
            return
        totais={}
        hoje=date.today()
        for row in self.conn.execute(
            "SELECT l.*,m.ano,m.mes,o.nome FROM lancamentos l "
            "JOIN meses m ON m.id=l.mes_id JOIN ocupantes o ON o.id=l.ocupante_id "
            "WHERE m.ano<? OR (m.ano=? AND m.mes<?)",
            (hoje.year,hoje.year,hoje.month),
        ).fetchall():
            if not lancamento_vencido(row["ano"],row["mes"],hoje):
                continue
            periodo=(row["ano"],row["mes"])
            saldo=round(self.valores_lancamento(row)[-1],2)
            if saldo>0:
                chave=(row["ano"],row["mes"],row["nome"])
                totais[chave]=totais.get(chave,0)+saldo
        if totais:
            periodos="\n".join(
                f"{NOMES_MESES[mes-1].upper()} DE {ano} — {nome}: {moeda(total)}"
                for (ano,mes,nome),total in sorted(totais.items())
            )
            total_aberto=sum(totais.values())
            if self.embutido:
                self.aviso_aberto.config(
                    text=f"ATENÇÃO: {len(totais)} em aberto • {moeda(total_aberto)}"
                )
                self.aviso_detalhes_aberto = f"Valores vencidos em aberto:\n\n{periodos}"
                self.aviso_aberto.pack(side="left", padx=(8, 0), pady=2)
            else:
                self.aviso_aberto.config(text=f"ATENÇÃO: em aberto\n{periodos}")
                self.aviso_aberto.pack(before=self.nb,fill="x",padx=16,pady=(0,6))
        else:
            self.aviso_aberto.pack_forget()
            if self.embutido:
                self.aviso_detalhes_aberto = ""

    def mostrar_detalhes_aberto(self,_evento=None):
        detalhes=getattr(self,"aviso_detalhes_aberto","")
        if detalhes:
            messagebox.showinfo("Valores em aberto",detalhes,parent=self.root)

    def atualizar_lancamentos(self):
        self.atualizar_aviso_aberto()
        if not hasattr(self,"lanc"):return
        self.lanc.delete(*self.lanc.get_children())
        try:ano=int(self.m_ano.get());mes=int(self.m_mes.get())
        except: return
        if hasattr(self,"lbl_mes_planilha") and 1<=mes<=12:
            nome_mes=NOMES_MESES[mes-1].upper()
            self.lbl_mes_planilha.config(text=f"RESUMO MENSAL POR INQUILINO - {nome_mes} DE {ano}")
        m=self.conn.execute("SELECT id FROM meses WHERE ano=? AND mes=?",(ano,mes)).fetchone()
        if not m:return
        rows=self.conn.execute("""SELECT l.*,o.nome FROM lancamentos l JOIN ocupantes o ON o.id=l.ocupante_id WHERE l.mes_id=? ORDER BY o.nome""",(m["id"],)).fetchall()
        soma_total=soma_pago=soma_saldo=0
        for r in rows:
            cobrancas=self.cobrancas_lancamento(r)
            en,agua,total,pago,saldo=self.valores_lancamento(r);soma_total+=total;soma_pago+=pago;soma_saldo+=saldo
            estilo="em_aberto" if saldo>0 else "pago"
            self.lanc.insert("","end",values=(r["id"],r["nome"],moeda(en),moeda(agua),moeda(cobrancas["aluguel"]),moeda(cobrancas["outras"]),moeda(cobrancas["ajuste"]),moeda(total),moeda(pago),moeda(saldo)),tags=(estilo,))
        texto=f"Total do mês: {moeda(soma_total)}     Recebido: {moeda(soma_pago)}     Em aberto: {moeda(soma_saldo)}\nREVISA: baixa automática incluída no valor pago."
        contas=self.contas_mes(m["id"])
        if contas["conta_agua"] and not self.pessoas_cobradas(m["id"],"agua"):
            texto+="\nÁGUA PENDENTE: não há pessoas informadas nos inquilinos não isentos."
        if contas["usar_rateio_energia"]:
            revisa=self.conn.execute(
                "SELECT l.* FROM lancamentos l JOIN ocupantes o ON o.id=l.ocupante_id WHERE l.mes_id=? AND o.nome='REVISA'",
                (m["id"],)
            ).fetchone()
            if revisa is None or not revisa["cobrar_energia"]:
                texto+="\nENERGIA: REVISA sem cobrança ativa; o saldo da conta não foi atribuído."
            elif self.energia_lancamento(revisa)<0:
                texto+=f"\nCrédito de energia para REVISA: {moeda(-self.energia_lancamento(revisa))}."
        self.lbl_total.config(text=texto,wraplength=650)
        self.atualizar_previa_agua()
        self.atualizar_despesas(m["id"])

    def reverter_pagamento(self,ident,lancamento_id):
        with self.conn:
            resultado=self.conn.execute(
                "UPDATE pagamentos SET revertido_em=? WHERE id=? AND lancamento_id=? AND revertido_em IS NULL",
                (datetime.now().isoformat(timespec="seconds"),ident,lancamento_id),
            )
            if resultado.rowcount!=1:
                raise ValueError("Pagamento não encontrado neste lançamento ou já revertido.")

    def registrar_pagamento(self):
        row=self.obter_lancamento_selecionado()
        if not row:return
        en,agua,total,pago,saldo=self.valores_lancamento(row)
        win=tk.Toplevel(self.root);win.title(f"Pagamento — {row['nome']}");win.transient(self.root);win.grab_set()
        self.configurar_estilo_formulario(win)
        vars={}
        for i,(lab,key,val) in enumerate([("Data do pagamento (DD/MM/AAAA)","data",date.today().strftime("%d/%m/%Y")),("Valor pago (R$)","valor",f"{saldo:.2f}".replace(".",",")),("Forma (PIX, dinheiro etc.)","forma","PIX")]):
            ttk.Label(win,text=lab,style="Form.TLabel").grid(row=i,column=0,padx=12,pady=7,sticky="w");vars[key]=tk.StringVar(value=str(val));ttk.Entry(win,textvariable=vars[key],width=28,style="Form.TEntry").grid(row=i,column=1,padx=12,pady=7)
        resumo=ttk.Label(win,text="",style="Form.TLabel")
        resumo.grid(row=3,column=0,columnspan=2,padx=12,pady=8)
        def salvar():
            try:
                d=data_iso(vars["data"].get());v=numero(vars["valor"].get(),"Valor pago")
                if not d:raise ValueError("Informe a data do pagamento.")
                if v<=0:raise ValueError("O valor pago deve ser maior que zero.")
            except ValueError as e:messagebox.showerror("Pagamento inválido",str(e),parent=win);return
            self.conn.execute("INSERT INTO pagamentos(lancamento_id,data_pagamento,valor,forma) VALUES(?,?,?,?)",(row["id"],d,v,vars["forma"].get().strip()));self.conn.commit()
            win.destroy();self.atualizar_lancamentos()
        ttk.Button(win,text="Salvar pagamento",command=salvar).grid(row=4,column=1,padx=12,pady=12,sticky="e")
        ttk.Label(win,text="Histórico de pagamentos deste lançamento",style="Form.TLabel").grid(row=5,column=0,columnspan=2,padx=12,pady=(8,4),sticky="w")
        frame=ttk.Frame(win,style="Form.TFrame")
        frame.grid(row=6,column=0,columnspan=2,padx=12,sticky="nsew")
        lista=ttk.Treeview(frame,columns=("data","valor","forma","situacao"),show="headings",height=5,selectmode="browse")
        for campo,titulo,largura in (("data","Data",100),("valor","Valor",110),("forma","Forma",130),("situacao","Situação",110)):
            lista.heading(campo,text=titulo)
            lista.column(campo,width=largura,anchor="e" if campo=="valor" else "w")
        scroll=ttk.Scrollbar(frame,orient="vertical",command=lista.yview)
        lista.configure(yscrollcommand=scroll.set)
        lista.pack(side="left",fill="both",expand=True);scroll.pack(side="right",fill="y")
        def atualizar_historico():
            lista.delete(*lista.get_children())
            for pagamento in self.conn.execute(
                "SELECT * FROM pagamentos WHERE lancamento_id=? ORDER BY data_pagamento,id",(row["id"],)
            ):
                data=datetime.strptime(pagamento["data_pagamento"],"%Y-%m-%d").strftime("%d/%m/%Y")
                lista.insert("","end",iid=str(pagamento["id"]),values=(
                    data,moeda(pagamento["valor"]),pagamento["forma"],
                    "Revertido" if pagamento["revertido_em"] else "Confirmado",
                ))
            _,_,t,p,s=self.valores_lancamento(row)
            resumo.config(text=f"Total: {moeda(t)}   Já pago: {moeda(p)}   Saldo: {moeda(s)}")
            vars["valor"].set(f"{s:.2f}".replace(".",","))
        def reverter():
            sel=lista.selection()
            if not sel:
                messagebox.showinfo("Selecione","Selecione o pagamento que deseja reverter.",parent=win);return
            pagamento=self.conn.execute(
                "SELECT * FROM pagamentos WHERE id=? AND lancamento_id=?",(sel[0],row["id"])
            ).fetchone()
            if pagamento is None or pagamento["revertido_em"]:
                messagebox.showerror("Pagamento indisponível","Este pagamento não existe ou já foi revertido.",parent=win);return
            if not messagebox.askyesno(
                "Reverter pagamento",f"Reverter o pagamento de {moeda(pagamento['valor'])} de {row['nome']}?\n"
                "O saldo será recalculado. O registro ficará no histórico como revertido.",parent=win
            ):
                return
            try:
                self.reverter_pagamento(pagamento["id"],row["id"])
            except ValueError as e:
                messagebox.showerror("Não foi possível reverter",str(e),parent=win);return
            atualizar_historico();self.atualizar_lancamentos()
        ttk.Button(win,text="Reverter pagamento selecionado",command=reverter).grid(row=7,column=0,columnspan=2,padx=12,pady=12,sticky="w")
        aviso="REVISA permanece quitada por baixa automática, mesmo após reverter registros manuais." if row["nome"]=="REVISA" else "Após reverter, registre um novo pagamento com os dados corretos."
        ttk.Label(win,text=aviso,style="Form.TLabel",wraplength=550).grid(row=8,column=0,columnspan=2,padx=12,pady=(0,12),sticky="w")
        atualizar_historico()

    def adicionar_ocupante(self):
        nome=self.oc_nome.get().strip()
        if not nome:messagebox.showwarning("Nome obrigatório","Digite o nome do ocupante.");return
        nome=nome.upper()
        chave=chave_nome_ocupante(nome)
        existentes=self.conn.execute("SELECT nome FROM ocupantes").fetchall()
        if any(chave_nome_ocupante(row["nome"])==chave for row in existentes):
            messagebox.showwarning("Já cadastrado","Esse ocupante já existe, mesmo com diferenças de acentuação ou símbolos.")
            return
        try:self.conn.execute("INSERT INTO ocupantes(nome) VALUES(?)",(nome,));self.conn.commit()
        except sqlite3.IntegrityError:messagebox.showwarning("Já cadastrado","Esse ocupante já existe.");return
        self.oc_nome.set("");self.atualizar_ocupantes()

    def excluir_ocupante(self):
        sel=self.oc_tree.selection()
        if not sel:
            messagebox.showinfo("Selecione","Selecione o inquilino que deseja excluir.")
            return
        ident=self.oc_tree.item(sel[0],"values")[0]
        row=self.conn.execute("SELECT nome,ativo FROM ocupantes WHERE id=?",(ident,)).fetchone()
        if not row:
            messagebox.showerror("Inquilino não encontrado","Atualize a lista e tente novamente.")
            return
        if not row["ativo"]:
            messagebox.showinfo("Inquilino já excluído",f"{row['nome']} já está inativo.")
            return
        confirmar=messagebox.askyesno(
            "Excluir inquilino",
            f"Desativar {row['nome']} para os próximos meses?\n\n"
            "Os lançamentos e pagamentos antigos serão preservados.",
            parent=self.root,
        )
        if not confirmar:
            return
        self.conn.execute("UPDATE ocupantes SET ativo=0 WHERE id=?",(ident,))
        self.conn.commit()
        self.atualizar_ocupantes()

    def alternar_ocupante(self):
        sel=self.oc_tree.selection()
        if not sel:messagebox.showinfo("Selecione","Selecione um ocupante.");return
        ident=self.oc_tree.item(sel[0],"values")[0]
        r=self.conn.execute("SELECT ativo FROM ocupantes WHERE id=?",(ident,)).fetchone()
        self.conn.execute("UPDATE ocupantes SET ativo=? WHERE id=?",(0 if r["ativo"] else 1,ident));self.conn.commit();self.atualizar_ocupantes()

    def atualizar_ocupantes(self):
        self.oc_tree.delete(*self.oc_tree.get_children())
        try:
            ano=int(self.m_ano.get())
            mes=int(self.m_mes.get())
        except ValueError:
            ano,mes=ANO_INICIAL,1
        for r in self.conn.execute("SELECT * FROM ocupantes ORDER BY nome"):
            regra=self.regra_cobranca_ocupante(r,ano,mes)
            valores=(
                r["id"],r["nome"],r["observacoes"] or "",
                self.pessoas_ocupante_no_periodo(r["id"],ano,mes),
                *("Sim" if regra[f"cobrar_{chave}"] else "Não" for chave,_ in COBRANCAS),
                "Ativo" if r["ativo"] else "Inativo",
                "Sim" if r["avisar_leitura"] else "Não",
            )
            self.oc_tree.insert("","end",iid=str(r["id"]),values=valores)

    def atualizar(self):
        self.atualizar_ocupantes()
        self.carregar_lancamentos()

    def dialogo_relatorio_pdf(self):
        win=tk.Toplevel(self.root)
        win.title("Gerar relatório em PDF")
        win.transient(self.root)
        win.resizable(False,False)
        moldura=ttk.Frame(win,padding=18)
        moldura.pack(fill="both",expand=True)

        ttk.Label(moldura,text="Período do relatório").grid(row=0,column=0,columnspan=2,sticky="w")
        ano=tk.StringVar(value=self.m_ano.get())
        mes=tk.StringVar(value=self.m_mes.get())
        ttk.Label(moldura,text="Ano").grid(row=1,column=0,sticky="w",pady=(8,0))
        ttk.Combobox(moldura,textvariable=ano,values=[str(y) for y in range(2026,2041)],
                     width=9,state="readonly").grid(row=1,column=1,sticky="w",pady=(8,0))
        ttk.Label(moldura,text="Mês").grid(row=2,column=0,sticky="w",pady=(8,0))
        ttk.Combobox(moldura,textvariable=mes,values=[f"{i:02d}" for i in range(1,13)],
                     width=9,state="readonly").grid(row=2,column=1,sticky="w",pady=(8,0))

        nomes=["Todos os ocupantes"]+[r["nome"] for r in self.conn.execute(
            "SELECT nome FROM ocupantes ORDER BY nome"
        )]
        ocupante=tk.StringVar(value=nomes[0])
        ttk.Label(moldura,text="Ocupante").grid(row=3,column=0,sticky="w",pady=(10,0))
        ocupante_combo=ttk.Combobox(
            moldura,textvariable=ocupante,values=nomes,width=28,state="readonly",
        )
        ocupante_combo.grid(row=3,column=1,sticky="w",pady=(10,0))
        ttk.Label(
            moldura,
            text="Ao selecionar um inquilino, o PDF mostra somente a conta, os pagamentos e o saldo dele.",
            wraplength=360,
        ).grid(row=4,column=0,columnspan=2,sticky="w",pady=(6,0))

        ttk.Label(moldura,text="Incluir no PDF").grid(row=5,column=0,columnspan=2,
                                                     sticky="w",pady=(14,4))
        opcoes={
            "resumo":tk.BooleanVar(value=True),
            "detalhado":tk.BooleanVar(value=True),
            "contas":tk.BooleanVar(value=True),
        }
        caixas_opcoes={}
        for linha,(chave,texto) in enumerate((
            ("resumo","Resumo dos totais"),
            ("detalhado","Detalhamento por ocupante, pagamentos e saldo"),
            ("contas","Contas do mês e despesas/rateios"),
        ),start=6):
            caixas_opcoes[chave]=ttk.Checkbutton(
                moldura,text=texto,variable=opcoes[chave],
            )
            caixas_opcoes[chave].grid(row=linha,column=0,columnspan=2,sticky="w")

        def alternar_tipo_relatorio(_evento=None):
            individual=ocupante.get()!="Todos os ocupantes"
            for chave,caixa in caixas_opcoes.items():
                if individual:
                    opcoes[chave].set(chave=="detalhado")
                    caixa.configure(state="disabled")
                else:
                    opcoes[chave].set(True)
                    caixa.configure(state="normal")

        ocupante_combo.bind("<<ComboboxSelected>>",alternar_tipo_relatorio)

        def gerar():
            individual=ocupante.get()!="Todos os ocupantes"
            selecionadas=(
                ["detalhado"] if individual else
                [chave for chave,var in opcoes.items() if var.get()]
            )
            if not selecionadas:
                messagebox.showwarning("Selecione o conteúdo","Marque ao menos uma seção do relatório.",parent=win)
                return
            try:
                periodo_ano=int(ano.get())
                periodo_mes=int(mes.get())
            except ValueError:
                messagebox.showerror("Período inválido","Selecione um ano e um mês válidos.",parent=win)
                return
            ocupante_id=None
            if ocupante.get()!="Todos os ocupantes":
                row=self.conn.execute("SELECT id FROM ocupantes WHERE nome=?",(ocupante.get(),)).fetchone()
                if row is None:
                    messagebox.showerror("Ocupante não encontrado","Selecione um ocupante válido.",parent=win)
                    return
                ocupante_id=row["id"]
            path=filedialog.asksaveasfilename(
                title="Salvar relatório em PDF",parent=win,defaultextension=".pdf",
                initialfile=f"relatorio_{periodo_ano}_{periodo_mes:02d}.pdf",
                filetypes=[("Documento PDF","*.pdf")],
            )
            if not path:
                return
            try:
                self.gerar_relatorio_pdf(path,periodo_ano,periodo_mes,ocupante_id,selecionadas)
            except (OSError,ValueError,ImportError) as erro:
                messagebox.showerror("Não foi possível gerar o relatório",str(erro),parent=win)
                return
            win.destroy()
            messagebox.showinfo("Relatório concluído",f"PDF salvo em:\n{path}",parent=self.root)

        botoes=ttk.Frame(moldura)
        botoes.grid(row=9,column=0,columnspan=2,sticky="e",pady=(16,0))
        ttk.Button(botoes,text="Cancelar",command=win.destroy).pack(side="right")
        ttk.Button(botoes,text="Salvar PDF",command=gerar).pack(side="right",padx=(0,8))
        win.grab_set()

    def gerar_relatorio_pdf(self,path,ano,mes,ocupante_id=None,opcoes=("resumo","detalhado","contas")):
        from xml.sax.saxutils import escape
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4,landscape
        from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,SimpleDocTemplate,Spacer,Table,TableStyle,
        )

        periodo=self.conn.execute(
            "SELECT * FROM meses WHERE ano=? AND mes=?",(ano,mes)
        ).fetchone()
        if periodo is None:
            raise ValueError(f"N\u00e3o h\u00e1 dados carregados para {mes:02d}/{ano}.")
        contas=self.contas_mes(periodo["id"])
        opcoes_relatorio=("detalhado",) if ocupante_id is not None else opcoes
        consulta=(
            "SELECT l.*,o.nome FROM lancamentos l JOIN ocupantes o ON o.id=l.ocupante_id "
            "WHERE l.mes_id=?"
        )
        parametros=[periodo["id"]]
        if ocupante_id is not None:
            consulta+=" AND o.id=?"
            parametros.append(ocupante_id)
        consulta+=" ORDER BY o.nome"
        lancamentos=self.conn.execute(consulta,parametros).fetchall()
        if ocupante_id is not None and not lancamentos:
            raise ValueError("Não há lançamento desse ocupante no mês selecionado.")

        styles=getSampleStyleSheet()
        styles.add(ParagraphStyle(name="ReportTitle",parent=styles["Title"],fontName="Helvetica-Bold",
                                  fontSize=17,leading=21,textColor=colors.HexColor("#18212b"),
                                  alignment=TA_CENTER,spaceAfter=5))
        styles.add(ParagraphStyle(name="SectionTitle",parent=styles["Heading2"],fontSize=12,
                                  leading=15,textColor=colors.HexColor("#245A9B"),spaceBefore=10,
                                  spaceAfter=6))
        styles.add(ParagraphStyle(name="Small",parent=styles["BodyText"],fontSize=8,leading=10))
        styles.add(ParagraphStyle(name="ReportNote",parent=styles["Small"],
                                  textColor=colors.HexColor("#596b7b"),spaceBefore=3))
        styles.add(ParagraphStyle(name="ReportStatus",parent=styles["Small"],
                                  fontName="Helvetica-Bold",fontSize=9,leading=12,
                                  textColor=colors.HexColor("#245A9B"),spaceBefore=4))
        styles.add(ParagraphStyle(name="FinancialValue",parent=styles["Small"],
                                  fontName="Helvetica-Bold"))
        styles.add(ParagraphStyle(name="FinancialLabel",parent=styles["Small"],
                                  fontName="Helvetica-Bold",
                                  textColor=colors.HexColor("#18212b")))
        def paragrafo(valor,estilo="Small"):
            return Paragraph(escape(str(valor)).replace("\n","<br/>"),styles[estilo])
        def tabela(dados,larguras,header=True,linhas_resumo=()):
            tabela_pdf=Table(dados,colWidths=larguras,repeatRows=1 if header else 0)
            estilos=[
                ("VALIGN",(0,0),(-1,-1),"TOP"),
                ("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#d5dde3")),
                ("ROWBACKGROUNDS",(0,1 if header else 0),(-1,-1),
                 [colors.white,colors.HexColor("#f5f8fa")]),
                ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#245A9B")) if header else
                ("BACKGROUND",(0,0),(-1,-1),colors.white),
                ("TEXTCOLOR",(0,0),(-1,0),colors.white) if header else
                ("TEXTCOLOR",(0,0),(-1,-1),colors.HexColor("#18212b")),
                ("ALIGN",(-1,0),(-1,-1),"RIGHT"),
                ("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),
                ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
            ]
            for linha,cor in linhas_resumo:
                estilos.extend([
                    ("BACKGROUND",(0,linha),(-1,linha),cor),
                    ("LINEABOVE",(0,linha),(-1,linha),0.8,colors.HexColor("#245A9B")),
                ])
            tabela_pdf.setStyle(TableStyle(estilos))
            return tabela_pdf
        styles.add(ParagraphStyle(name="TableHeader",parent=styles["Small"],
                                  fontName="Helvetica-Bold",textColor=colors.white))
        story=[
            Paragraph(
                f"{'Conta individual' if ocupante_id is not None else 'Relatório mensal'} — {mes:02d}/{ano}",
                styles["ReportTitle"],
            ),
            paragrafo("Gerado em "+datetime.now().strftime("%d/%m/%Y %H:%M")),
            Spacer(1,4*mm),
        ]
        if ocupante_id is not None:
            nome=self.conn.execute("SELECT nome FROM ocupantes WHERE id=?",(ocupante_id,)).fetchone()["nome"]
            story.insert(1,paragrafo(f"Ocupante: {nome}"))
        totais=[0.0,0.0,0.0]
        linhas_detalhe=[]
        for row in lancamentos:
            cobrancas=self.cobrancas_lancamento(row)
            _,_,total,pago,saldo=self.valores_lancamento(row)
            for chave in ("energia","agua","aluguel","outras","ajuste"):
                totais[0]+=cobrancas[chave]
            totais[1]+=pago
            totais[2]+=saldo
            linhas_detalhe.append((row,cobrancas,total,pago,saldo))

        if "resumo" in opcoes_relatorio or ocupante_id is not None:
            story.append(Paragraph(
                "Resumo da conta" if ocupante_id is not None else "Resumo financeiro",
                styles["SectionTitle"],
            ))
            story.append(paragrafo("Valores em reais (R$)."))
            dados=[
                [paragrafo("Total cobrado", "FinancialLabel"),
                 paragrafo("Recebido", "FinancialLabel"),
                 paragrafo("Saldo a pagar", "FinancialLabel")],
                [paragrafo(moeda(totais[0]),"FinancialValue"),
                 paragrafo(moeda(totais[1]),"FinancialValue"),
                 paragrafo(moeda(totais[2]),"FinancialValue")],
            ]
            story.append(tabela(
                dados,[85*mm,85*mm,85*mm],header=False,
                linhas_resumo=((1,colors.HexColor("#e7f0fb")),),
            ))
            situacao="Quitado" if totais[2]<=0 else "Em aberto"
            story.append(paragrafo(f"Situação: {situacao}","ReportStatus"))
            story.append(Spacer(1,2*mm))

        if "contas" in opcoes_relatorio:
            story.append(Paragraph("Contas e rateios do mês",styles["SectionTitle"]))
            contas_dados=[
                [paragrafo("Item","TableHeader"),paragrafo("Valor / quantidade","TableHeader")],
                [paragrafo("Conta de energia"),paragrafo(f"{moeda(contas['conta_energia'])} · {contas['total_kwh']:g} kWh")],
                [paragrafo("Iluminação pública incluída"),paragrafo(moeda(contas["iluminacao_publica"]))],
                [paragrafo("Conta de água"),paragrafo(f"{moeda(contas['conta_agua'])} · {contas['total_pessoas_agua']} pessoas")],
            ]
            story.append(tabela(contas_dados,[120*mm,120*mm]))
            despesas=self.conn.execute(
                "SELECT d.descricao,d.valor,d.rateio,o.nome nome_ocupante FROM despesas_mes d "
                "LEFT JOIN ocupantes o ON o.id=d.ocupante_id WHERE d.mes_id=? ORDER BY d.id",
                (periodo["id"],),
            ).fetchall()
            if despesas:
                story.append(Spacer(1,3*mm))
                dados=[[paragrafo("Despesa","TableHeader"),paragrafo("Rateio","TableHeader"),
                        paragrafo("Total","TableHeader")]]
                dados.extend([paragrafo(d["descricao"]),paragrafo(
                                  f"Direto: {d['nome_ocupante']}" if d["nome_ocupante"]
                                  else RATEIOS_DESPESAS[d["rateio"]]),
                              paragrafo(moeda(d["valor"]))] for d in despesas)
                story.append(tabela(dados,[80*mm,80*mm,80*mm]))

        if "detalhado" in opcoes_relatorio:
            story.append(Paragraph(
                "Conta individual" if ocupante_id is not None else "Detalhamento por ocupante",
                styles["SectionTitle"],
            ))
            if not lancamentos:
                story.append(paragrafo("Nenhum lançamento cadastrado neste mês."))
            for row,cobrancas,total,pago,saldo in linhas_detalhe:
                story.append(Paragraph(escape(row["nome"]),styles["Heading3"]))
                dados=[[paragrafo("Cobranças do mês","TableHeader"),paragrafo("Valor","TableHeader")]]
                for chave,label in COBRANCAS:
                    dados.append([paragrafo(label),paragrafo(moeda(cobrancas[chave]))])
                dados.extend([
                    [paragrafo("Total cobrado","FinancialLabel"),
                     paragrafo(moeda(total),"FinancialValue")],
                    [paragrafo("Recebido","FinancialLabel"),
                     paragrafo(moeda(pago),"FinancialValue")],
                    [paragrafo("Saldo a pagar","FinancialLabel"),
                     paragrafo(moeda(saldo),"FinancialValue")],
                ])
                linhas_resumo_inicio=len(COBRANCAS)+1
                story.append(tabela(
                    dados,[150*mm,90*mm],
                    linhas_resumo=(
                        (linhas_resumo_inicio,colors.HexColor("#e8eef2")),
                        (linhas_resumo_inicio+1,colors.HexColor("#e7f0fb")),
                        (linhas_resumo_inicio+2,colors.HexColor("#fff3dc")),
                    ),
                ))
                story.append(paragrafo(
                    "O valor recebido inclui pagamentos confirmados e, quando houver, a baixa automática.",
                    "ReportNote",
                ))
                pagamentos=self.conn.execute(
                    "SELECT data_pagamento,valor,forma,revertido_em FROM pagamentos "
                    "WHERE lancamento_id=? ORDER BY data_pagamento,id",(row["id"],)
                ).fetchall()
                if pagamentos:
                    story.append(Paragraph("Histórico de pagamentos",styles["Heading4"]))
                    dados=[[paragrafo("Data","TableHeader"),paragrafo("Valor","TableHeader"),
                            paragrafo("Forma","TableHeader"),paragrafo("Situação","TableHeader")]]
                    for pagamento in pagamentos:
                        situacao="Revertido em "+pagamento["revertido_em"] if pagamento["revertido_em"] else "Confirmado"
                        dados.append([paragrafo(pagamento["data_pagamento"]),paragrafo(moeda(pagamento["valor"])),
                                      paragrafo(pagamento["forma"] or "—"),paragrafo(situacao)])
                    story.append(Spacer(1,2*mm))
                    story.append(tabela(dados,[45*mm,45*mm,65*mm,85*mm]))
                story.append(Spacer(1,4*mm))

        def rodape(canvas,documento):
            canvas.saveState()
            canvas.setFont("Helvetica",8)
            canvas.setFillColor(colors.HexColor("#596b7b"))
            canvas.drawString(18*mm,10*mm,f"Controle de Energia e Água · {mes:02d}/{ano}")
            canvas.drawRightString(landscape(A4)[0]-18*mm,10*mm,f"Página {documento.page}")
            canvas.restoreState()

        documento=SimpleDocTemplate(
            str(path),pagesize=landscape(A4),rightMargin=18*mm,leftMargin=18*mm,
            topMargin=15*mm,bottomMargin=18*mm,title=f"Relatório mensal {mes:02d}/{ano}",
            author=APP_NAME,
        )
        documento.build(story,onFirstPage=rodape,onLaterPages=rodape)

    def backup_rapido(self):
        try:
            self.conn.commit();dest=PASTA/f"backup_controle_{datetime.now():%Y%m%d_%H%M%S}.db";shutil.copy2(DB_PATH,dest)
            messagebox.showinfo("Backup concluído",f"Cópia salva em:\n{dest}")
        except Exception as e:messagebox.showerror("Erro no backup",str(e))

    def backup_como(self):
        path=filedialog.asksaveasfilename(title="Salvar backup",defaultextension=".db",initialfile=f"backup_controle_{datetime.now():%Y%m%d_%H%M}.db",filetypes=[("Banco SQLite","*.db")])
        if not path:return
        try:self.conn.commit();shutil.copy2(DB_PATH,path);messagebox.showinfo("Backup concluído",f"Backup salvo em:\n{path}")
        except Exception as e:messagebox.showerror("Erro no backup",str(e))

    def abrir_pasta(self):
        try:os.startfile(str(PASTA))
        except Exception:messagebox.showinfo("Pasta de dados",str(PASTA))

    def encerrar(self):
        conn=getattr(self,"conn",None)
        if conn is None:return
        try:conn.commit()
        finally:
            conn.close()
            self.conn=None

    def fechar(self):
        try:self.encerrar()
        finally:self.root.destroy()

def main():
    if sys.platform=="win32":
        import ctypes
        resultado=ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Revisa.ControleEnergiaAgua")
        if resultado!=0:
            raise OSError(f"Não foi possível configurar o ícone da barra de tarefas: {resultado}")
    root=tk.Tk()
    root.withdraw()
    configurar_icone_aplicativo(root)
    if not solicitar_acesso(root):
        root.destroy()
        return
    app=App(root)
    root.protocol("WM_DELETE_WINDOW",app.fechar)
    root.deiconify()
    root.mainloop()

if __name__=="__main__": main()
