# -*- coding: utf-8 -*-
"""Folha de Pagamento - Revisa | Python + Tkinter + SQLite (Windows)"""
import os, sys, json, sqlite3, shutil, subprocess, tempfile, math, hashlib, hmac, secrets, re
import urllib.parse
from datetime import datetime, timedelta
from xml.sax.saxutils import escape as xml_escape
from importar_pdf_folha import read_payroll_pdf
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk, messagebox, filedialog, simpledialog
from PIL import Image, ImageDraw, ImageTk
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, LongTable, KeepTogether, PageBreak
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.styles import ParagraphStyle as _ParagraphStyle
from reportlab.platypus import TableStyle as _TableStyle

REPORT_FONT_SCALE = 0.85


class NumberedReportCanvas(Canvas):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._report_pages=[]

    def showPage(self):
        self._report_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total=len(self._report_pages)
        for state in self._report_pages:
            self.__dict__.update(state)
            width,height=self._pagesize
            self.saveState()
            self.setFillColor(colors.HexColor('#64748b'))
            self.setFont('Helvetica',8)
            self.drawRightString(
                width-12*mm,height-15.5*mm,
                f'Página {self._pageNumber} de {total}')
            self.restoreState()
            super().showPage()
        super().save()


def _scaled_font(size):
    return round(max(size * REPORT_FONT_SCALE, min(size, 7)), 2)


def ParagraphStyle(name, parent=None, **kwargs):
    if 'fontSize' in kwargs:
        old = kwargs['fontSize']
        kwargs['fontSize'] = _scaled_font(old)
        if 'leading' in kwargs:
            kwargs['leading'] = round(kwargs['leading'] * kwargs['fontSize'] / old, 2)
    elif 'leading' in kwargs:
        kwargs['leading'] = round(kwargs['leading'] * REPORT_FONT_SCALE, 2)
    return _ParagraphStyle(name, parent=parent, **kwargs)


def TableStyle(commands):
    commands = [('FONTSIZE', c[1], c[2], _scaled_font(c[3])) if c[0] == 'FONTSIZE' else c for c in commands]
    if not any(c[0] == 'FONTSIZE' for c in commands):
        commands.insert(0, ('FONTSIZE', (0, 0), (-1, -1), 7.5))
    return _TableStyle(commands)

APP_NAME = 'Folha de Pagamento - Revisa'
APP_VERSION = '3.9'
LOAN_KIND = 'Empréstimo'
ADVANCE_KIND = 'Adiantamento Salarial'
LOAN_KINDS = (LOAN_KIND, ADVANCE_KIND)
AUTHOR = 'Revisa Injeção Diesel'
MONTHS = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']
BG = '#0B1220'; NAVY = '#142b4a'; BLUE = '#2563eb'; TEXT = '#172b4d'; MUTED = '#64748b'; WHITE = '#ffffff'; GREEN = '#15803d'; ORANGE = '#b45309'
DARK_SURFACE = '#111C2E'; DARK_SURFACE_ALT = '#16243A'; DARK_BORDER = '#24344D'; DARK_SIDEBAR = '#0E1726'
ON_DARK = '#E6EDF7'; ON_DARK_MUTED = '#8FA3BF'; ACCENT_HOVER = '#1d4ed8'
PDF_ROW_ALT = '#f3f6fb'
SIDEBAR = '#10243e'; SIDEBAR_SURFACE = '#183450'; SIDEBAR_HOVER = '#21415f'
SIDEBAR_TEXT = '#dbe7f3'; SIDEBAR_MUTED = '#91a5bc'; SIDEBAR_ACCENT = '#60a5fa'
DARK_HOVER = '#22324D'; DARK_SCROLL_ACTIVE = '#2A3B57'; DARK_DISABLED = '#5B6B82'
ON_HOVER = WHITE; PRESSED_BG = BLUE; HEADING = ON_DARK
LIGHT_THEME = False


def use_light_theme():
    """Tema claro usado somente pelo Sistemas Revisa integrado; o programa autônomo não chama esta função."""
    global BG, NAVY, BLUE, TEXT, MUTED, ACCENT_HOVER, DARK_SURFACE, DARK_SURFACE_ALT, DARK_BORDER
    global DARK_SIDEBAR, ON_DARK, ON_DARK_MUTED, DARK_HOVER, DARK_SCROLL_ACTIVE, DARK_DISABLED
    global ON_HOVER, PRESSED_BG, HEADING, LIGHT_THEME
    BG = '#F2F4F8'; NAVY = '#064B82'; BLUE = '#0875C9'; TEXT = '#20252B'; MUTED = '#667085'
    ACCENT_HOVER = '#064B82'; DARK_SURFACE = '#FFFFFF'; DARK_SURFACE_ALT = '#E9EEF5'
    DARK_BORDER = '#D5DCE5'; DARK_SIDEBAR = '#FFFFFF'; ON_DARK = '#20252B'; ON_DARK_MUTED = '#667085'
    DARK_HOVER = '#DCEBFA'; DARK_SCROLL_ACTIVE = '#B9C3D0'; DARK_DISABLED = '#98A2B3'
    ON_HOVER = '#064B82'; PRESSED_BG = '#B9D7F2'; HEADING = '#064B82'; LIGHT_THEME = True


def temporary_pdf_path(prefix):
    file_descriptor,path=tempfile.mkstemp(prefix=prefix,suffix='.pdf')
    os.close(file_descriptor)
    return path


def central_geometry_from_args():
    argument=next(
        (value for value in sys.argv if value.startswith('--central-geometry=')),
        None)
    if argument is None:
        return None
    match=re.fullmatch(
        r'--central-geometry=(\d+)x(\d+)\+(-?\d+)\+(-?\d+)',
        argument)
    if match is None:
        raise ValueError('Geometria da janela da Central inválida.')
    width,height,x,y=map(int,match.groups())
    if width<320 or height<240:
        raise ValueError('A área da Central é pequena demais para abrir a Folha.')
    return width,height,x,y


def show_file_in_folder(path):
    path=os.path.abspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f'O PDF não foi encontrado:\n{path}')
    if sys.platform.startswith('win'):
        subprocess.Popen(f'explorer.exe /select,"{path}"')
    elif sys.platform=='darwin':
        subprocess.Popen(['open','-R',path])
    else:
        subprocess.Popen(['xdg-open',os.path.dirname(path)])


_SIGN_PASSWORD={'value':None,'failed':False}
SIGN_CONFIG_NAME='assinatura_digital.json'
SIGN_DEFAULT_PFX=os.path.join(
    os.path.expanduser('~'),'Documents','CONTROLE FINANCEIRO','CERTIFICADO DIGITAL','2026')


def signing_pfx_path():
    # O certificado fica fora do programa; o caminho pode ser trocado em assinatura_digital.json.
    configured=signing_config().get('certificado')
    for candidate in (configured,SIGN_DEFAULT_PFX):
        if not candidate:
            continue
        if os.path.isfile(candidate):
            return candidate
        if os.path.isdir(candidate):
            for name in sorted(os.listdir(candidate)):
                if name.lower().endswith(('.pfx','.p12')):
                    return os.path.join(candidate,name)
    return None


def signing_config():
    try:
        with open(os.path.join(DATA_DIR,SIGN_CONFIG_NAME),encoding='utf-8') as handle:
            return json.load(handle)
    except (OSError,ValueError):
        return {}


def save_signing_config(**values):
    config=signing_config()
    config.update(values)
    os.makedirs(DATA_DIR,exist_ok=True)
    with open(os.path.join(DATA_DIR,SIGN_CONFIG_NAME),'w',encoding='utf-8') as handle:
        json.dump(config,handle)


def remember_signing_expiry(pfx,signer):
    # A validade só pode ser lida com a senha; fica guardada (sem a senha) para o aviso do painel.
    try:
        expires=signer.signing_cert['tbs_certificate']['validity']['not_after'].native
        save_signing_config(
            validade=expires.strftime('%Y-%m-%d'),validade_certificado=pfx)
    except Exception:
        pass


def signing_expiry_warning(warn_days=30,include_ok=False):
    """Retorna a mensagem de aviso se o certificado vence em breve ou já venceu."""
    pfx=signing_pfx_path()
    if pfx is None:
        return None
    config=signing_config()
    if config.get('validade_certificado')!=pfx or not config.get('validade'):
        try:
            from pyhanko.sign import signers
            remember_signing_expiry(pfx,signers.SimpleSigner.load_pkcs12(pfx,passphrase=None))
            config=signing_config()
        except Exception:
            return None
    try:
        expires=datetime.strptime(config['validade'],'%Y-%m-%d').date()
    except (KeyError,ValueError):
        return None
    days=(expires-datetime.now().date()).days
    date_text=expires.strftime('%d/%m/%Y')
    if days<0:
        return f'A assinatura digital VENCEU em {date_text}. Renove o certificado para continuar assinando os relatórios.'
    if days<=warn_days:
        when='hoje' if days==0 else f'em {days} dia(s)'
        return f'A assinatura digital vence {when} ({date_text}). Providencie a renovação do certificado.'
    if include_ok:
        return f'OK:Assinatura digital ativa — válida até {date_text} ({days} dias restantes).'
    return None


def sign_pdf_file(path):
    """Assina o PDF com o certificado digital, com carimbo visível na última página."""
    pfx=signing_pfx_path()
    if pfx is None:
        return False
    from pyhanko.sign import signers, fields
    from pyhanko.stamp import TextStampStyle
    from pyhanko.pdf_utils.images import PdfImage
    from pyhanko.pdf_utils.layout import SimpleBoxLayoutRule, AxisAlignment, Margins, InnerScaling
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.pdf_utils.reader import PdfFileReader
    signer=None
    for attempt in range(3):
        password=_SIGN_PASSWORD['value']
        if password is None:
            password=simpledialog.askstring(
                'Assinatura digital',
                'Senha do certificado digital (usada só nesta sessão):',show='*',
                parent=tk._default_root)
            if not password:
                return False
        try:
            signer=signers.SimpleSigner.load_pkcs12(pfx,passphrase=password.encode('utf-8'))
        except Exception:
            signer=None
        if signer is not None:
            _SIGN_PASSWORD['value']=password
            remember_signing_expiry(pfx,signer)
            break
        _SIGN_PASSWORD['value']=None
        messagebox.showerror('Assinatura digital','Senha do certificado incorreta.',parent=tk._default_root)
    if signer is None:
        return False
    signed_path=path+'.assinado'
    with open(path,'rb') as source:
        reader=PdfFileReader(source)
        media=reader.root['/Pages']['/Kids'][0].get_object()['/MediaBox']
        page_width=float(media[2])
        writer=IncrementalPdfFileWriter(source)
        metadata=signers.PdfSignatureMetadata(field_name='AssinaturaRevisa')
        field=fields.SigFieldSpec(
            'AssinaturaRevisa',on_page=-1,
            box=(page_width-330,10,page_width-34,62))
        style=TextStampStyle(
            stamp_text='Assinado digitalmente\n%(signer)s\n%(ts)s',border_width=0.5,
            background=PdfImage(resource_path('assinatura_logo.png')),
            background_opacity=1.0,
            background_layout=SimpleBoxLayoutRule(
                x_align=AxisAlignment.ALIGN_MIN,y_align=AxisAlignment.ALIGN_MID,
                margins=Margins(left=4,right=0,top=3,bottom=3),
                inner_content_scaling=InnerScaling.SHRINK_TO_FIT),
            inner_content_layout=SimpleBoxLayoutRule(
                x_align=AxisAlignment.ALIGN_MAX,y_align=AxisAlignment.ALIGN_MID,
                margins=Margins(left=60,right=4,top=3,bottom=3)))
        pdf_signer=signers.PdfSigner(metadata,signer=signer,stamp_style=style,new_field_spec=field)
        with open(signed_path,'wb') as output:
            pdf_signer.sign_pdf(writer,output=output)
    os.replace(signed_path,path)
    return True


def choose_signing_pfx():
    chosen=filedialog.askopenfilename(
        title='Selecione o certificado digital (.pfx)',
        filetypes=[('Certificado digital','*.pfx *.p12'),('Todos os arquivos','*.*')],
        parent=tk._default_root)
    if not chosen:
        return None
    os.makedirs(DATA_DIR,exist_ok=True)
    save_signing_config(certificado=chosen)
    return chosen


def open_pdf(path):
    if messagebox.askyesno(
            'Assinatura digital',
            'Deseja assinar digitalmente este relatório?\n\n'
            'Sim: o PDF é assinado e recebe o carimbo com a logo.\n'
            'Não: o relatório abre normalmente, sem assinatura.',
            parent=tk._default_root):
        try:
            if signing_pfx_path() is None and choose_signing_pfx() is None:
                raise RuntimeError('certificado digital não selecionado')
            if not sign_pdf_file(path):
                raise RuntimeError('assinatura cancelada')
        except Exception as ex:
            messagebox.showwarning(
                'Assinatura digital',
                f'O relatório foi aberto sem assinatura digital.\n\nMotivo: {ex}',
                parent=tk._default_root)
    if sys.platform.startswith('win'):
        os.startfile(path)
    elif sys.platform=='darwin':
        subprocess.Popen(['open',path])
    else:
        subprocess.Popen(['xdg-open',path])


def app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(name):
    bundle_dir=getattr(sys,'_MEIPASS',app_dir())
    return os.path.join(bundle_dir,name)


def set_window_icon(window):
    try:
        window.iconbitmap(resource_path('folha_pagamento.ico'))
    except tk.TclError:
        pass


DATA_DIR = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'FolhaPagamentoRevisa')
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, 'folha_pagamento.db')
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')
ZAP_REPORTS_DIR = os.path.join(DATA_DIR, 'Relatorios ZAP')
ACCOUNTING_PDF_DIR = r'C:\Users\Revisa\Documents\CONTROLE FINANCEIRO\RECURSOS HUMANOS\FOLHA DE PGTO'
os.makedirs(BACKUP_DIR, exist_ok=True)
def _find_mega_backup_dir():
    # Usa a pasta do projeto onde o programa está (funciona em qualquer computador).
    base=os.path.dirname(sys.executable) if getattr(sys,'frozen',False) else os.path.dirname(os.path.abspath(__file__))
    for folder in (base,os.path.dirname(base)):
        candidate=os.path.join(folder,'Backup Folha Revisa')
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(base, 'Backup Folha Revisa')


AUTO_BACKUP_DIR = _find_mega_backup_dir()
SYNC_MARKER = os.path.join(DATA_DIR, 'ultima_sincronizacao.txt')


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    return con


def init_db():
    # If the pre-populated database ships next to the program, copy it once to the user data folder.
    bundled = resource_path('folha_pagamento.db')
    if not os.path.exists(DB_PATH) and os.path.exists(bundled) and os.path.abspath(bundled) != os.path.abspath(DB_PATH):
        shutil.copy2(bundled, DB_PATH)
    with connect() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS employees(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL UNIQUE,email TEXT DEFAULT '',phone TEXT DEFAULT '',pix TEXT DEFAULT '',role TEXT DEFAULT '',sector TEXT DEFAULT '',active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS employee_salary_history(id INTEGER PRIMARY KEY AUTOINCREMENT,employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,salary REAL NOT NULL CHECK(salary>=0),effective_year INTEGER NOT NULL,effective_month INTEGER NOT NULL CHECK(effective_month BETWEEN 1 AND 12),created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,UNIQUE(employee_id,effective_year,effective_month));
        CREATE TABLE IF NOT EXISTS employee_previous_salary_controls(employee_id INTEGER PRIMARY KEY REFERENCES employees(id) ON DELETE CASCADE,amount REAL NOT NULL CHECK(amount>=0),updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS employee_salary_register_updates(employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,updated_on TEXT NOT NULL,amount REAL NOT NULL CHECK(amount>=0),notes TEXT NOT NULL DEFAULT '',PRIMARY KEY(employee_id,updated_on));
        CREATE INDEX IF NOT EXISTS idx_salary_history_period ON employee_salary_history(employee_id,effective_year DESC,effective_month DESC);
        CREATE TABLE IF NOT EXISTS annual_employees(id INTEGER PRIMARY KEY AUTOINCREMENT,year INTEGER NOT NULL,employee_id INTEGER NOT NULL REFERENCES employees(id),salary_base REAL NOT NULL DEFAULT 0,role TEXT DEFAULT '',sector TEXT DEFAULT '',active INTEGER NOT NULL DEFAULT 1,notes TEXT DEFAULT '',UNIQUE(year,employee_id));
        CREATE TABLE IF NOT EXISTS payrolls(id INTEGER PRIMARY KEY AUTOINCREMENT,year INTEGER NOT NULL,month INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'Em revisão',notes TEXT DEFAULT '',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,UNIQUE(year,month));
        CREATE TABLE IF NOT EXISTS payroll_items(id INTEGER PRIMARY KEY AUTOINCREMENT,payroll_id INTEGER NOT NULL REFERENCES payrolls(id) ON DELETE CASCADE,employee_id INTEGER NOT NULL REFERENCES employees(id),salary REAL NOT NULL DEFAULT 0,pf REAL NOT NULL DEFAULT 0,overtime REAL NOT NULL DEFAULT 0,vacation REAL NOT NULL DEFAULT 0,meta REAL NOT NULL DEFAULT 0,marmitex REAL NOT NULL DEFAULT 0,advances REAL NOT NULL DEFAULT 0,pharmacy REAL NOT NULL DEFAULT 0,other_deductions REAL NOT NULL DEFAULT 0,loan REAL NOT NULL DEFAULT 0,total REAL NOT NULL DEFAULT 0,original_total REAL,source TEXT NOT NULL DEFAULT 'Manual',notes TEXT DEFAULT '',UNIQUE(payroll_id,employee_id));
        CREATE TABLE IF NOT EXISTS employee_loans(id INTEGER PRIMARY KEY AUTOINCREMENT,employee_id INTEGER NOT NULL REFERENCES employees(id),principal REAL NOT NULL,installment_count INTEGER NOT NULL,start_year INTEGER NOT NULL,start_month INTEGER NOT NULL,notes TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS employee_loan_adjustments(id INTEGER PRIMARY KEY AUTOINCREMENT,loan_id INTEGER NOT NULL REFERENCES employee_loans(id) ON DELETE CASCADE,principal REAL NOT NULL,installment_count INTEGER NOT NULL,start_year INTEGER NOT NULL,start_month INTEGER NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,UNIQUE(loan_id,start_year,start_month));
        CREATE TABLE IF NOT EXISTS employee_meta_entries(id INTEGER PRIMARY KEY AUTOINCREMENT,employee_id INTEGER NOT NULL REFERENCES employees(id),entry_date TEXT NOT NULL,amount REAL NOT NULL CHECK(amount>0),notes TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS idx_meta_entry_date ON employee_meta_entries(entry_date,employee_id);
        CREATE TABLE IF NOT EXISTS app_auth(id INTEGER PRIMARY KEY CHECK(id=1),salt BLOB NOT NULL,password_hash BLOB NOT NULL);
        CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT,happened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,action TEXT NOT NULL,details TEXT DEFAULT '');
        CREATE INDEX IF NOT EXISTS idx_payroll_year_month ON payrolls(year,month);
        CREATE INDEX IF NOT EXISTS idx_items_employee ON payroll_items(employee_id);
        CREATE TRIGGER IF NOT EXISTS prevent_closed_payroll_item_insert
        BEFORE INSERT ON payroll_items
        WHEN EXISTS (SELECT 1 FROM payrolls WHERE id=NEW.payroll_id AND status='Fechada')
        BEGIN
            SELECT RAISE(ABORT,'Folha fechada: reabra antes de alterar os lançamentos.');
        END;
        CREATE TRIGGER IF NOT EXISTS prevent_closed_payroll_item_update
        BEFORE UPDATE ON payroll_items
        WHEN EXISTS (SELECT 1 FROM payrolls WHERE id=OLD.payroll_id AND status='Fechada')
          OR EXISTS (SELECT 1 FROM payrolls WHERE id=NEW.payroll_id AND status='Fechada')
        BEGIN
            SELECT RAISE(ABORT,'Folha fechada: reabra antes de alterar os lançamentos.');
        END;
        CREATE TRIGGER IF NOT EXISTS prevent_closed_payroll_item_delete
        BEFORE DELETE ON payroll_items
        WHEN EXISTS (SELECT 1 FROM payrolls WHERE id=OLD.payroll_id AND status='Fechada')
        BEGIN
            SELECT RAISE(ABORT,'Folha fechada: reabra antes de alterar os lançamentos.');
        END;
        ''')
        con.execute("UPDATE payrolls SET status='Em revisão' WHERE status!='Fechada'")
        employee_columns=[r['name'] for r in con.execute('PRAGMA table_info(employees)').fetchall()]
        if 'pix' not in employee_columns:
            con.execute("ALTER TABLE employees ADD COLUMN pix TEXT DEFAULT ''")
        if 'code' not in employee_columns:
            con.execute("ALTER TABLE employees ADD COLUMN code TEXT NOT NULL DEFAULT ''")
        for column in (
                'address','address_number','bairro','cep','city','state','ctps',
                'birth_date','cpf','admission_date','dismissal_date','inactive_since',
                'bank','bank_agency','bank_account'):
            if column not in employee_columns:
                con.execute(f'ALTER TABLE employees ADD COLUMN {column} TEXT NOT NULL DEFAULT \'\'')
        con.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_employees_code
            ON employees(code) WHERE code IS NOT NULL AND TRIM(code) <> ''""")
        columns=[r['name'] for r in con.execute('PRAGMA table_info(payroll_items)').fetchall()]
        if 'loan' not in columns:
            con.execute('ALTER TABLE payroll_items ADD COLUMN loan REAL NOT NULL DEFAULT 0')
        if 'loan_manual' not in columns:
            con.execute('ALTER TABLE payroll_items ADD COLUMN loan_manual REAL NOT NULL DEFAULT 0')
            if 'loan' in columns:
                con.execute('UPDATE payroll_items SET loan_manual=loan')
        if 'loan_override' not in columns:
            con.execute('ALTER TABLE payroll_items ADD COLUMN loan_override REAL')
        if 'thirteenth' not in columns:
            con.execute('ALTER TABLE payroll_items ADD COLUMN thirteenth REAL NOT NULL DEFAULT 0')
        # NULL em advances_manual = valor de "advances" ainda é todo manual (folhas antigas/fechadas).
        if 'advances_manual' not in columns:
            con.execute('ALTER TABLE payroll_items ADD COLUMN advances_manual REAL')
        if 'advances_override' not in columns:
            con.execute('ALTER TABLE payroll_items ADD COLUMN advances_override REAL')
        payroll_columns=[r['name'] for r in con.execute('PRAGMA table_info(payrolls)').fetchall()]
        if 'loan_only' not in payroll_columns:
            con.execute('ALTER TABLE payrolls ADD COLUMN loan_only INTEGER NOT NULL DEFAULT 0')
            # Folhas criadas só para parcelas, em versões anteriores, tinham observação automática.
            con.execute("UPDATE payrolls SET loan_only=1,notes='' WHERE notes LIKE 'Criada automaticamente%'")
            con.execute("""DELETE FROM payroll_items WHERE source='Automático' AND loan=0 AND advances=0
                AND payroll_id IN (SELECT id FROM payrolls WHERE loan_only=1 AND status!='Fechada')""")
            con.execute("""UPDATE payroll_items SET salary=0,notes='',
                total=ROUND(pf+overtime+vacation+meta+thirteenth-marmitex-advances-pharmacy-other_deductions-loan,2)
                WHERE (source='Automático' OR notes LIKE 'Lançamento criado automaticamente%')
                AND payroll_id IN (SELECT id FROM payrolls WHERE loan_only=1 AND status!='Fechada')""")
        salary_columns=[r['name'] for r in con.execute('PRAGMA table_info(employee_salary_history)').fetchall()]
        if 'old_salary' not in salary_columns:
            con.execute('ALTER TABLE employee_salary_history ADD COLUMN old_salary REAL')
        salary_update_columns=[r['name'] for r in con.execute(
            'PRAGMA table_info(employee_salary_register_updates)').fetchall()]
        if 'notes' not in salary_update_columns:
            con.execute(
                "ALTER TABLE employee_salary_register_updates ADD COLUMN notes TEXT NOT NULL DEFAULT ''")
        if 'kind' not in salary_update_columns:
            con.execute(
                "ALTER TABLE employee_salary_register_updates ADD COLUMN kind TEXT NOT NULL DEFAULT ''")
        loan_columns=[r['name'] for r in con.execute('PRAGMA table_info(employee_loans)').fetchall()]
        if 'notes' not in loan_columns:
            con.execute("ALTER TABLE employee_loans ADD COLUMN notes TEXT NOT NULL DEFAULT ''")
        if 'kind' not in loan_columns:
            con.execute("ALTER TABLE employee_loans ADD COLUMN kind TEXT NOT NULL DEFAULT 'Empréstimo'")
        for column,definition in (
            ('settled_year','INTEGER'),
            ('settled_month','INTEGER'),
            ('settlement_amount','REAL'),
        ):
            if column not in loan_columns:
                con.execute(f'ALTER TABLE employee_loans ADD COLUMN {column} {definition}')
        con.execute("""UPDATE payrolls SET notes=''
            WHERE notes LIKE 'Criada automaticamente%'
                OR notes='Criada manualmente; revisar salário e variáveis antes do fechamento.'""")
        closed_note_payrolls=con.execute("""SELECT DISTINCT p.id FROM payrolls p
            JOIN payroll_items i ON i.payroll_id=p.id
            WHERE p.status='Fechada' AND (
                i.notes LIKE 'Lançamento criado automaticamente%'
                OR i.notes='Salário-base informado manualmente; conferir antes de fechar.')""").fetchall()
        for payroll in closed_note_payrolls:
            con.execute("UPDATE payrolls SET status='Em revisão' WHERE id=?",(payroll['id'],))
        con.execute("""UPDATE payroll_items SET notes=''
            WHERE notes LIKE 'Lançamento criado automaticamente%'
                OR notes='Salário-base informado manualmente; conferir antes de fechar.'""")
        for payroll in closed_note_payrolls:
            con.execute("UPDATE payrolls SET status='Fechada' WHERE id=?",(payroll['id'],))


def money(v):
    try:
        if v is None or str(v).strip() == '': return 0.0
        if isinstance(v, (int, float)): return float(v)
        s = str(v).strip().replace('R$', '').replace(' ', '')
        if ',' in s: s = s.replace('.', '').replace(',', '.')
        return float(s)
    except (ValueError, TypeError):
        raise ValueError(f'Valor inválido: {v!r}')


def brl(v):
    return ('R$ {:,.2f}'.format(float(v or 0))).replace(',', 'X').replace('.', ',').replace('X', '.')


def require_active_employee(con,employee_id):
    employee=con.execute('SELECT name FROM employees WHERE id=? AND active=1',(employee_id,)).fetchone()
    if employee is None:
        raise ValueError('Selecione um colaborador ativo. Atualize a lista antes de incluir lançamentos.')
    return employee


def meta_entry_values(entry_date,amount):
    entry_date=normalize_employee_date(entry_date)
    if not entry_date:
        raise ValueError('Informe a data da Meta (DD/MM/AAAA).')
    amount=money(amount)
    if not math.isfinite(amount) or amount<=0 or round(amount,2)<=0:
        raise ValueError('Informe um valor maior que zero.')
    return entry_date,round(amount,2)


def phone_parts(value):
    digits=re.sub(r'\D','',value or '')
    if len(digits) in (12,13) and digits.startswith('55'):
        digits=digits[2:]
    if len(digits) in (10,11):
        return digits[:2],digits[2:]
    return '',digits


def format_phone(value):
    ddd,number=phone_parts(value)
    if len(ddd)!=2 or len(number) not in (8,9):
        return value or ''
    split=len(number)-4
    return f'({ddd}) {number[:split]}-{number[split:]}'


def whatsapp_chat_url(phone,name,year,month):
    ddd,number=phone_parts(phone)
    if len(ddd)!=2 or len(number) not in (8,9):
        raise ValueError('O telefone cadastrado não tem DDD e número válidos.')
    if not 1<=month<=12:
        raise ValueError('O mês selecionado é inválido.')
    message='Segue seu Holerite Adminstrativo'
    return f'whatsapp://send?phone=55{ddd}{number}&text={urllib.parse.quote(message,safe="")}'


def open_whatsapp_desktop(url):
    if not sys.platform.startswith('win'):
        raise RuntimeError('A abertura do aplicativo WhatsApp está disponível no Windows.')
    try:
        os.startfile(url)
    except OSError as ex:
        raise RuntimeError(
            'Não foi possível abrir o aplicativo WhatsApp. Confira se ele está instalado '
            'e associado aos links whatsapp:// nas configurações do Windows.') from ex


def employee_date_for_form(value):
    if not value:
        return ''
    try:
        return datetime.strptime(value,'%Y-%m-%d').strftime('%d/%m/%Y')
    except ValueError:
        return value


def normalize_employee_date(value):
    value=value.strip()
    if not value:
        return ''
    for date_format in ('%d/%m/%Y','%Y-%m-%d'):
        try:
            return datetime.strptime(value,date_format).strftime('%Y-%m-%d')
        except ValueError:
            continue
    raise ValueError('Use o formato DD/MM/AAAA para as datas.')


def normalize_salary_register_period(value):
    value=value.strip()
    for period_format in ('%m/%Y','%m-%Y'):
        try:
            return datetime.strptime(value,period_format).replace(day=1).strftime('%Y-%m-%d')
        except ValueError:
            continue
    raise ValueError('Use o formato MM/AAAA para a data do reajuste.')


def salary_register_period_label(value):
    return datetime.strptime(value,'%Y-%m-%d').strftime('%m/%Y')


def calc_total(d):
    # PF, hora extra, férias, meta e 13º são proventos; marmitex, vales, farmácia, empréstimo e outros são descontos.
    return round(d['salary'] + d['pf'] + d['overtime'] + d['vacation'] + (d.get('meta') or 0) + (d.get('thirteenth') or 0) - d['marmitex'] - d['advances'] - d['pharmacy'] - d['other_deductions'] - d['loan'], 2)


def employee_salary_for_period(con,employee_id,year,month):
    salary=con.execute('''SELECT salary FROM employee_salary_history
        WHERE employee_id=? AND (effective_year<? OR (effective_year=? AND effective_month<=?))
        ORDER BY effective_year DESC,effective_month DESC LIMIT 1''',
        (employee_id,year,year,month)).fetchone()
    if salary:
        return float(salary['salary'])
    annual=con.execute(
        'SELECT salary_base FROM annual_employees WHERE employee_id=? AND year=?',
        (employee_id,year)).fetchone()
    if annual:
        return float(annual['salary_base'])
    previous=con.execute('''SELECT i.salary FROM payroll_items i
        JOIN payrolls p ON p.id=i.payroll_id
        WHERE i.employee_id=? AND (p.year<? OR (p.year=? AND p.month<?))
        ORDER BY p.year DESC,p.month DESC LIMIT 1''',
        (employee_id,year,year,month)).fetchone()
    return float(previous['salary']) if previous else 0.0


def sync_payroll_employees(con,payroll):
    if payroll['status']=='Fechada' or payroll['loan_only']:
        return
    period=payroll['year']*12+payroll['month']

    def month_index(value):
        try:
            date=datetime.strptime((value or '')[:10],'%Y-%m-%d')
        except ValueError:
            return None
        return date.year*12+date.month

    existing={row['employee_id'] for row in con.execute(
        'SELECT employee_id FROM payroll_items WHERE payroll_id=?',(payroll['id'],))}
    for employee in con.execute(
            'SELECT id,active,admission_date,dismissal_date,inactive_since FROM employees').fetchall():
        if employee['active']:
            admitted=month_index(employee['admission_date'])
            if employee['id'] in existing or (admitted and period<admitted):
                continue
            salary=employee_salary_for_period(con,employee['id'],payroll['year'],payroll['month'])
            con.execute('''INSERT INTO payroll_items(payroll_id,employee_id,salary,total,source,notes)
                VALUES(?,?,?,?,?,?)''',(payroll['id'],employee['id'],salary,salary,'Automático',''))
        elif employee['id'] in existing:
            left=month_index(employee['inactive_since']) or month_index(employee['dismissal_date'])
            if left and period>left:
                con.execute('DELETE FROM payroll_items WHERE payroll_id=? AND employee_id=?',
                    (payroll['id'],employee['id']))


def employee_salary_before_period(con,employee_id,year,month):
    previous=con.execute('''SELECT salary FROM employee_salary_history
        WHERE employee_id=? AND (effective_year<? OR (effective_year=? AND effective_month<?))
        ORDER BY effective_year DESC,effective_month DESC LIMIT 1''',
        (employee_id,year,year,month)).fetchone()
    if previous:
        return float(previous['salary'])
    same_period=con.execute('''SELECT i.salary FROM payroll_items i
        JOIN payrolls p ON p.id=i.payroll_id
        WHERE i.employee_id=? AND p.year=? AND p.month=? LIMIT 1''',
        (employee_id,year,month)).fetchone()
    if same_period:
        return float(same_period['salary'])
    annual=con.execute(
        'SELECT salary_base FROM annual_employees WHERE employee_id=? AND year=?',
        (employee_id,year)).fetchone()
    if annual:
        return float(annual['salary_base'])
    prior_payroll=con.execute('''SELECT i.salary FROM payroll_items i
        JOIN payrolls p ON p.id=i.payroll_id
        WHERE i.employee_id=? AND (p.year<? OR (p.year=? AND p.month<?))
        ORDER BY p.year DESC,p.month DESC LIMIT 1''',
        (employee_id,year,year,month)).fetchone()
    return float(prior_payroll['salary']) if prior_payroll else None


def loan_installment(principal, count, number):
    regular = round(principal / count, 2)
    return round(principal - regular * (count - 1), 2) if number == count else regular


def loan_terms_for_month(con, loan, year, month):
    adjustment=con.execute('''SELECT principal,installment_count,start_year,start_month
        FROM employee_loan_adjustments
        WHERE loan_id=? AND (start_year<? OR (start_year=? AND start_month<=?))
        ORDER BY start_year DESC,start_month DESC LIMIT 1''',
        (loan['id'],year,year,month)).fetchone()
    if adjustment:
        principal=adjustment['principal']
        count=adjustment['installment_count']
        start_year=adjustment['start_year']
        start_month=adjustment['start_month']
    else:
        principal=loan['principal']
        count=loan['installment_count']
        start_year=loan['start_year']
        start_month=loan['start_month']
    elapsed=(year-start_year)*12+month-start_month
    return principal,count,elapsed,start_year,start_month


def loan_installment_details(con,employee_id,year,month,kind=None):
    loans=con.execute('SELECT * FROM employee_loans WHERE employee_id=? ORDER BY id',(employee_id,)).fetchall()
    details=[]
    for loan in loans:
        if kind is not None and loan['kind']!=kind:
            continue
        if loan['settled_year'] is not None and (
                year*12+month >= loan['settled_year']*12+loan['settled_month']):
            continue
        principal,count,elapsed,_,_=loan_terms_for_month(con,loan,year,month)
        if 0<=elapsed<count:
            details.append((elapsed+1,count,loan_installment(principal,count,elapsed+1)))
    return details


def loan_remaining_for_month(con,loan,year,month):
    if loan['settled_year'] is not None:
        return 0.0
    principal,count,elapsed,_,_=loan_terms_for_month(con,loan,year,month)
    if elapsed<0:
        return round(float(principal),2)
    if elapsed>=count:
        return 0.0
    return round(sum(
        loan_installment(principal,count,number)
        for number in range(elapsed+1,count+1)),2)


def scheduled_amounts(con,employee_id,year,month):
    loan=round(sum(a for _,_,a in loan_installment_details(con,employee_id,year,month,LOAN_KIND)),2)
    advance=round(sum(a for _,_,a in loan_installment_details(con,employee_id,year,month,ADVANCE_KIND)),2)
    return loan,advance


def loan_installment_label(con,employee_id,year,month,loan_amount,loan_override=None,loan_manual=0):
    loan_details=loan_installment_details(con,employee_id,year,month,LOAN_KIND)
    advance_details=loan_installment_details(con,employee_id,year,month,ADVANCE_KIND)
    settlements=con.execute('''SELECT kind FROM employee_loans
        WHERE employee_id=? AND settled_year=? AND settled_month=? AND settlement_amount>0
        ORDER BY id''',(employee_id,year,month)).fetchall()
    if not loan_details and not advance_details and not settlements:
        return 'Manual' if float(loan_amount or 0)>0 else '—'
    parts=['Q Empréstimo' if row['kind']==LOAN_KIND else 'Vale quitado' for row in settlements]
    parts.extend(f'Emp {number}/{count}' for number,count,_ in loan_details)
    if advance_details:
        parts.append('Vale')
    label=' + '.join(parts)
    scheduled_total=round(sum(amount for _,_,amount in loan_details)+float(loan_manual or 0),2)
    if loan_override is not None and round(float(loan_amount or 0),2)!=scheduled_total:
        label+=' (zerada)' if float(loan_amount or 0)==0 else ' (ajustada)'
    return label


def loan_terms_for_loan(con,loan):
    terms=[{
        'principal':loan['principal'],
        'installment_count':loan['installment_count'],
        'start_year':loan['start_year'],
        'start_month':loan['start_month'],
    }]
    adjustments=con.execute('''SELECT principal,installment_count,start_year,start_month
        FROM employee_loan_adjustments WHERE loan_id=?
        ORDER BY start_year,start_month''',(loan['id'],)).fetchall()
    terms.extend(dict(adjustment) for adjustment in adjustments)
    return terms


def log_action(action, details=''):
    with connect() as con:
        con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)', (action, details))


PASSWORD_ITERATIONS = 600_000
PASSWORD_MIN_LENGTH = 8


def hash_password(password, salt=None):
    salt=salt or secrets.token_bytes(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),salt,PASSWORD_ITERATIONS)
    return salt,digest


def password_is_configured():
    with connect() as con:
        return con.execute('SELECT 1 FROM app_auth WHERE id=1').fetchone() is not None


def verify_password(password):
    with connect() as con:
        row=con.execute('SELECT salt,password_hash FROM app_auth WHERE id=1').fetchone()
    if row is None:
        return False
    _,digest=hash_password(password,row['salt'])
    return hmac.compare_digest(digest,row['password_hash'])


def save_password(password):
    salt,digest=hash_password(password)
    with connect() as con:
        con.execute('INSERT OR REPLACE INTO app_auth(id,salt,password_hash) VALUES(1,?,?)',(salt,digest))


def authenticate():
    root=tk.Tk()
    root.title('Acesso - '+APP_NAME)
    set_window_icon(root)
    root.configure(bg=BG)
    root.resizable(False,False)
    root.protocol('WM_DELETE_WINDOW',root.destroy)
    configured=password_is_configured()
    state={'authenticated':False}
    style=ttk.Style(root)
    try: style.theme_use('clam')
    except tk.TclError: pass
    style.configure('LoginTitle.TLabel',font=('Segoe UI Semibold',17),foreground=ON_DARK,background=DARK_SURFACE)
    style.configure('LoginSub.TLabel',font=('Segoe UI',9),foreground=ON_DARK_MUTED,background=DARK_SURFACE)
    style.configure('LoginField.TLabel',font=('Segoe UI Semibold',9),foreground=ON_DARK_MUTED,background=DARK_SURFACE)
    style.configure('LoginError.TLabel',font=('Segoe UI',9),foreground='#F87171',background=DARK_SURFACE)
    style.configure('Login.TEntry',padding=(10,7),fieldbackground=DARK_SURFACE_ALT,foreground=ON_DARK,
                    insertcolor=ON_DARK,bordercolor=DARK_BORDER,lightcolor=DARK_BORDER,darkcolor=DARK_BORDER)
    style.map('Login.TEntry',bordercolor=[('focus',BLUE)],lightcolor=[('focus',BLUE)])
    style.configure('Login.TCheckbutton',background=DARK_SURFACE,foreground=ON_DARK_MUTED,
                    indicatorbackground=DARK_SURFACE_ALT,indicatorforeground=ON_DARK,focuscolor=DARK_SURFACE)
    style.map('Login.TCheckbutton',background=[('active',DARK_SURFACE)],foreground=[('active',ON_DARK)],
              indicatorbackground=[('selected',BLUE),('active',DARK_SURFACE_ALT)])
    style.configure('Accent.TButton',padding=(12,9),background=BLUE,foreground=WHITE,
                    font=('Segoe UI Semibold',10),relief='flat',borderwidth=0,focuscolor=BLUE)
    style.map('Accent.TButton',background=[('active',ACCENT_HOVER)],foreground=[('active',WHITE)])

    tk.Frame(root,bg=BLUE,height=4).pack(fill='x')
    card=tk.Frame(root,bg=DARK_SURFACE,highlightbackground=DARK_BORDER,highlightthickness=1,padx=28,pady=20)
    card.pack(fill='both',expand=True,padx=18,pady=18)
    header=tk.Frame(card,bg=DARK_SURFACE)
    header.pack(fill='x')
    with Image.open(resource_path('logo_revisa.png')) as logo_source:
        logo_source=logo_source.convert('RGBA')
        logo_source.thumbnail((140,64),Image.Resampling.LANCZOS)
        logo_card=Image.new('RGBA',(logo_source.width+16,logo_source.height+12),WHITE)
        logo_card.paste(logo_source,(8,6),logo_source)
    root.logo_image=ImageTk.PhotoImage(logo_card,master=root)
    tk.Label(header,image=root.logo_image,bg=DARK_SURFACE).pack(side='left',padx=(0,14))
    titles=tk.Frame(header,bg=DARK_SURFACE)
    titles.pack(side='left',fill='x')
    tk.Label(titles,text='ACESSO AO SISTEMA',bg=DARK_SURFACE,fg='#60A5FA',font=('Segoe UI Semibold',8)).pack(anchor='w')
    ttk.Label(titles,text='Folha de Pagamento',style='LoginTitle.TLabel').pack(anchor='w')
    ttk.Label(titles,text='Entre com sua senha para continuar.',style='LoginSub.TLabel').pack(anchor='w')
    tk.Frame(card,bg=DARK_BORDER,height=1).pack(fill='x',pady=(16,10))

    form=tk.Frame(card,bg=DARK_SURFACE)
    form.pack(fill='x')
    form.columnconfigure(0,weight=1)
    password_var=tk.StringVar()
    confirm_var=tk.StringVar()
    ttk.Label(form,text='Crie uma senha' if not configured else 'Senha de acesso',style='LoginField.TLabel').grid(row=0,column=0,sticky='w',pady=(0,5))
    password_entry=ttk.Entry(form,textvariable=password_var,show='*',width=40,style='Login.TEntry')
    password_entry.grid(row=1,column=0,sticky='ew',pady=(0,8))
    password_entries=[password_entry]
    if not configured:
        ttk.Label(form,text=f'Use pelo menos {PASSWORD_MIN_LENGTH} caracteres.',style='LoginSub.TLabel').grid(row=2,column=0,sticky='w',pady=(0,8))
        ttk.Label(form,text='Confirme a senha',style='LoginField.TLabel').grid(row=3,column=0,sticky='w',pady=(0,5))
        confirm_entry=ttk.Entry(form,textvariable=confirm_var,show='*',width=40,style='Login.TEntry')
        confirm_entry.grid(row=4,column=0,sticky='ew',pady=(0,8))
        password_entries.append(confirm_entry)
    show_var=tk.BooleanVar(value=False)

    def toggle_password_visibility():
        for entry in password_entries:
            entry.configure(show='' if show_var.get() else '*')

    ttk.Checkbutton(card,text='Mostrar senha',variable=show_var,command=toggle_password_visibility,style='Login.TCheckbutton').pack(anchor='w')
    message_var=tk.StringVar()
    ttk.Label(card,textvariable=message_var,style='LoginError.TLabel',wraplength=340,anchor='w').pack(fill='x',pady=(6,4))

    def submit(event=None):
        password=password_var.get()
        if not configured:
            if len(password)<PASSWORD_MIN_LENGTH:
                message_var.set(f'A senha precisa ter pelo menos {PASSWORD_MIN_LENGTH} caracteres.')
                return
            if password!=confirm_var.get():
                message_var.set('As senhas não conferem.')
                return
            save_password(password)
            state['authenticated']=True
        elif verify_password(password):
            state['authenticated']=True
        else:
            message_var.set('Senha incorreta.')
            password_var.set('')
            password_entry.focus_set()
            return
        root.destroy()

    ttk.Button(card,text='Criar senha e entrar' if not configured else 'Entrar com segurança',style='Accent.TButton',command=submit).pack(fill='x',pady=(4,0))
    tk.Label(card,text='Desenvolvido por Jorge Alberto de Paula  •  Versão '+APP_VERSION,
             bg=DARK_SURFACE,fg=ON_DARK_MUTED,font=('Segoe UI',8)).pack(pady=(14,0))
    password_entry.bind('<Return>',submit)
    if not configured:
        confirm_entry.bind('<Return>',submit)
    root.bind('<Escape>',lambda event:root.destroy())
    root.update_idletasks()
    root.geometry(f'+{max(0,(root.winfo_screenwidth()-root.winfo_reqwidth())//2)}+{max(0,(root.winfo_screenheight()-root.winfo_reqheight())//2)}')
    password_entry.focus_set()
    root.mainloop()
    return state['authenticated']


class ScrollableHost(ttk.Frame):
    """Área que preenche o espaço disponível e ganha barras de rolagem quando o conteúdo não cabe."""
    SELF_SCROLLING=('Treeview','Listbox','Text','TCombobox','Combobox')

    def __init__(self,master):
        super().__init__(master)
        self.canvas=tk.Canvas(self,highlightthickness=0,borderwidth=0,bg=BG)
        self.vbar=ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview)
        self.hbar=ttk.Scrollbar(self,orient='horizontal',command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vbar.set,xscrollcommand=self.hbar.set)
        self.canvas.pack(side='left',fill='both',expand=True)
        self.inner=ttk.Frame(self.canvas)
        self.window_id=self.canvas.create_window(0,0,window=self.inner,anchor='nw')
        self.canvas.bind('<Configure>',self._layout)
        self.inner.bind('<Configure>',self._layout)
        self.bind('<Configure>',self._layout)
        self.bind_all('<MouseWheel>',self._on_wheel,add='+')
        self.bind_all('<Shift-MouseWheel>',self._on_shift_wheel,add='+')

    def _layout(self,event=None):
        bar_w=self.vbar.winfo_reqwidth()
        bar_h=self.hbar.winfo_reqheight()
        total_w=self.winfo_width()
        total_h=self.winfo_height()
        need_w=self.inner.winfo_reqwidth()
        need_h=self.inner.winfo_reqheight()
        show_v=need_h>total_h
        show_h=need_w>total_w-(bar_w if show_v else 0)
        if show_h and not show_v:
            show_v=need_h>total_h-bar_h
        if show_v!=bool(self.vbar.winfo_manager()):
            self.vbar.pack(side='right',fill='y',before=self.canvas) if show_v else self.vbar.pack_forget()
        if show_h!=bool(self.hbar.winfo_manager()):
            self.hbar.pack(side='bottom',fill='x',before=self.canvas) if show_h else self.hbar.pack_forget()
        view_w=total_w-(bar_w if show_v else 0)
        view_h=total_h-(bar_h if show_h else 0)
        width=max(view_w,need_w)
        height=max(view_h,need_h)
        self.canvas.itemconfigure(self.window_id,width=width,height=height)
        self.canvas.configure(scrollregion=(0,0,width,height))
        if not show_v:
            self.canvas.yview_moveto(0)
        if not show_h:
            self.canvas.xview_moveto(0)

    def _scroll_target(self,event):
        try:
            if not self.winfo_ismapped():
                return None
            widget=self.winfo_containing(event.x_root,event.y_root)
        except (KeyError,tk.TclError):
            return None
        if widget is None or widget.winfo_toplevel()!=self.winfo_toplevel():
            return None
        if widget.winfo_class() in self.SELF_SCROLLING:
            return None
        return widget

    def _on_wheel(self,event):
        if self._scroll_target(event) is not None and self.vbar.winfo_manager():
            self.canvas.yview_scroll(int(-event.delta/120),'units')

    def _on_shift_wheel(self,event):
        if self._scroll_target(event) is not None and self.hbar.winfo_manager():
            self.canvas.xview_scroll(int(-event.delta/120),'units')


class FolhaBase:
    """Conteúdo da Folha; usado pela janela própria (FolhaApp) e pelo painel embutido (FolhaPanel)."""

    def _init_folha(self):
        self.configure(bg=BG)
        today = datetime.now()
        self.current_payroll_year = today.year
        self.current_payroll_month = today.month
        self.search_var = tk.StringVar()
        self.load_newer_mega_backup()
        self._style()
        self._build()
        self.bind_all('<Map>',self._apply_dialog_branding,add='+')
        self.refresh_all()

    def mega_backup_path(self):
        return os.path.join(AUTO_BACKUP_DIR,'backup_saida.db')

    def record_mega_sync(self):
        try:
            stamp=os.path.getmtime(self.mega_backup_path())
            with open(SYNC_MARKER,'w') as marker:
                marker.write(repr(stamp))
        except OSError:
            pass

    def load_newer_mega_backup(self):
        # Se o backup do Mega foi gravado por outro computador, oferece carregá-lo.
        source=self.mega_backup_path()
        try:
            if not os.path.exists(source) or not os.path.exists(DB_PATH):
                return
            source_time=os.path.getmtime(source)
            try:
                with open(SYNC_MARKER) as marker:
                    known=float(marker.read().strip())
                newer=source_time>known+1
            except (OSError,ValueError):
                # Sem registro: primeira vez neste computador, oferece a cópia do Mega.
                newer=True
            if not newer:
                return
            when=datetime.fromtimestamp(source_time).strftime('%d/%m/%Y %H:%M')
            if not messagebox.askyesno(
                'Dados mais recentes no Mega',
                f'Foi encontrada uma cópia do banco salva em {when} na pasta do Mega, '
                'mais nova que a deste computador.\n\n'
                'Carregar essa cópia? (Os dados atuais deste computador serão guardados '
                'antes em "antes_de_carregar.db".)',
                parent=self):
                return
            shutil.copy2(DB_PATH,os.path.join(BACKUP_DIR,'antes_de_carregar.db'))
            origin=sqlite3.connect(f'file:{source}?mode=ro',uri=True)
            target=sqlite3.connect(DB_PATH)
            try:
                origin.backup(target)
            finally:
                target.close()
                origin.close()
            init_db()
            self.record_mega_sync()
        except (OSError,sqlite3.Error) as ex:
            messagebox.showerror(
                'Falha ao carregar o banco do Mega',
                f'Não foi possível carregar a cópia do Mega:\n{ex}',parent=self)

    def save_exit_backups(self):
        for directory in (BACKUP_DIR,AUTO_BACKUP_DIR):
            try:
                os.makedirs(directory,exist_ok=True)
                final=os.path.join(directory,'backup_saida.db')
                temp=final+'.tmp'
                if self.create_backup(temp,show_success=False):
                    os.replace(temp,final)
                    for name in os.listdir(directory):
                        if name.startswith('backup_saida_') and name.endswith('.db'):
                            os.remove(os.path.join(directory,name))
            except OSError:
                pass
        self.record_mega_sync()

    def on_close(self):
        self.save_exit_backups()
        self.destroy()

    def _style(self):
        st = ttk.Style(self)
        try: st.theme_use('clam')
        except tk.TclError: pass
        st.configure('.', font=('Segoe UI', 10))
        st.configure('TFrame', background=BG)
        st.configure('Toolbar.TFrame',background='#004b97')
        st.configure('TLabel', background=BG, foreground=TEXT)
        st.configure('Title.TLabel', font=('Segoe UI Semibold', 20), foreground=NAVY, background=BG)
        st.configure('Sub.TLabel', font=('Segoe UI', 10), foreground=MUTED, background=BG)
        st.configure('TButton', padding=(11, 7), background='#e2e8f0', foreground=TEXT)
        st.map('TButton', background=[('active','#cbd5e1')])
        st.configure('Accent.TButton', padding=(12, 8), background=BLUE, foreground='white')
        st.map('Accent.TButton', background=[('active','#1d4ed8')], foreground=[('active','white')])
        st.configure('Toolbar.TButton',padding=(11,7),background='#eff6ff',foreground=NAVY)
        st.map('Toolbar.TButton',background=[('pressed','#c5dcf5'),('active','#dbeafe')],
               foreground=[('active',NAVY)])
        st.configure('ToolbarSelected.TButton',padding=(11,7),background='#ff4500',foreground=NAVY)
        st.map('ToolbarSelected.TButton',background=[('pressed','#e63e00'),('active','#ff642b')],
               foreground=[('active',NAVY)])
        st.configure('Secondary.TButton',padding=(11,7),background='#eff6ff',foreground=NAVY)
        st.configure('Highlight.TButton',padding=(12,8),background='#0f766e',foreground='white',font=('Segoe UI Semibold',9))
        st.configure('ImportPdf.TButton',padding=(12,8),background='#ea580c',foreground='white',font=('Segoe UI Semibold',9))
        st.configure('Report.TButton',padding=(12,8),background='#7c3aed',foreground='white',font=('Segoe UI Semibold',9))
        st.configure('WhatsApp.TButton',padding=(12,8),background='#128C7E',foreground='white',font=('Segoe UI Semibold',9))
        st.map('Report.TButton',background=[('active','#6d28d9')],foreground=[('active','white')])
        st.map('WhatsApp.TButton',background=[('active','#0f766e')],foreground=[('active','white')])
        st.map('Highlight.TButton',background=[('active','#115e59')],foreground=[('active','white')])
        st.map('ImportPdf.TButton',background=[('active','#c2410c')],foreground=[('active','white')])
        st.map('Secondary.TButton',background=[('active','#dbeafe')],foreground=[('active',NAVY)])
        st.configure('Orange.TMenubutton',padding=(11,8,10,8),background='#ea580c',foreground='white',arrowcolor='white')
        st.map('Orange.TMenubutton',background=[('active','#c2410c')],foreground=[('active','white')],arrowcolor=[('active','white')])
        st.configure('MonthNav.TButton',padding=(3,2),background='#eff6ff',foreground=NAVY)
        st.map('MonthNav.TButton',background=[('active','#dbeafe')],foreground=[('active',NAVY)])
        st.configure('Danger.TButton',padding=(11,7),background='#fee2e2',foreground='#991b1b')
        st.map('Danger.TButton',background=[('active','#fecaca')],foreground=[('active','#7f1d1d')])
        st.configure('EditLaunch.TButton',padding=(12,7),background='#dc2626',foreground='white')
        st.map('EditLaunch.TButton',background=[('active','#b91c1c')],foreground=[('active','white')])
        st.configure('ClosePayroll.TButton',padding=(12,7),background='#15803d',foreground='white')
        st.map('ClosePayroll.TButton',background=[('active','#166534')],foreground=[('active','white')])
        st.configure('ReopenPayroll.TButton',padding=(12,7),background='#dc2626',foreground='white')
        st.map('ReopenPayroll.TButton',background=[('active','#b91c1c')],foreground=[('active','white')])
        for name in (
                'TButton','Accent.TButton','Toolbar.TButton','ToolbarSelected.TButton','Secondary.TButton','Highlight.TButton',
                'ImportPdf.TButton','Report.TButton','WhatsApp.TButton',
                'Danger.TButton','EditLaunch.TButton','ClosePayroll.TButton',
                'ReopenPayroll.TButton'):
            st.configure(name,padding=(7,3),font=('Segoe UI Semibold',9),
                         relief='flat',borderwidth=0,focuscolor=BG)
        for name in ('Report.TButton','ImportPdf.TButton','Secondary.TButton'):
            st.configure(name,background='#e8eef6',foreground='#334b68')
            st.map(name,background=[('pressed','#cbd8e9'),('active','#dbe6f3')],
                   foreground=[('disabled',MUTED),('active',NAVY)])
        for name in ('EditLaunch.TButton','Highlight.TButton'):
            st.configure(name,background=BLUE,foreground=WHITE)
            st.map(name,background=[('active','#1d4ed8')],
                   foreground=[('disabled',MUTED),('active',WHITE)])
        st.configure('ImportPdf.TButton',background='#fecaca',foreground='#991b1b')
        st.map('ImportPdf.TButton',
               background=[('pressed','#f87171'),('active','#fca5a5')],
               foreground=[('disabled',MUTED),('active','#7f1d1d')])
        st.configure('CompactReport.TButton',font=('Segoe UI Semibold',8))
        st.configure('CompactReport.TButton',background='#e8eef6',foreground='#334b68')
        st.map('CompactReport.TButton',
               background=[('pressed','#cbd8e9'),('active','#dbe6f3')],
               foreground=[('disabled',MUTED),('active',NAVY)])
        st.configure('Orange.TMenubutton',padding=(7,3),font=('Segoe UI Semibold',9),
                     background='#e8eef6',foreground=NAVY,arrowcolor=NAVY,
                     relief='flat',borderwidth=0)
        st.map('Orange.TMenubutton',background=[('active','#d6e1ef')],
               foreground=[('active',NAVY)],arrowcolor=[('active',NAVY)])
        st.configure('ReopenPayroll.TButton',background='#fff1dc',foreground='#92400e')
        st.map('ReopenPayroll.TButton',background=[('active','#fde5bd')],
               foreground=[('active','#92400e')])
        st.configure('Treeview', rowheight=30, background=WHITE, fieldbackground=WHITE, foreground=TEXT, borderwidth=0)
        st.configure('Treeview.Heading', font=('Segoe UI Semibold', 9), background='#e7edf5', foreground=NAVY, padding=8)
        st.map('Treeview', background=[('selected','#dbeafe')], foreground=[('selected',TEXT)])
        st.configure('CardTitle.TLabel',font=('Segoe UI',9),foreground=MUTED,background=WHITE)
        st.configure('CardValue.TLabel',font=('Segoe UI Semibold',21),foreground=NAVY,background=WHITE)
        st.configure('PageHeading.TLabel',font=('Segoe UI Semibold',14),foreground=NAVY,background=BG)
        self._apply_dark_theme(st)

    def _apply_dark_theme(self,st):
        # Estrutura escura; tabelas, campos e cartões continuam claros para leitura dos dados.
        st.configure('.',background=BG,foreground=ON_DARK,bordercolor=DARK_BORDER,
                     lightcolor=DARK_BORDER,darkcolor=DARK_BORDER,troughcolor=DARK_SURFACE)
        st.configure('TFrame',background=BG)
        st.configure('TLabel',background=BG,foreground=ON_DARK)
        st.configure('Title.TLabel',foreground=HEADING,background=BG)
        st.configure('Sub.TLabel',foreground=ON_DARK_MUTED,background=BG)
        st.configure('PageHeading.TLabel',foreground=HEADING,background=BG)
        st.configure('TLabelframe',background=BG,bordercolor=DARK_BORDER,lightcolor=DARK_BORDER,darkcolor=DARK_BORDER)
        st.configure('TLabelframe.Label',background=BG,foreground=ON_DARK,font=('Segoe UI Semibold',10))
        for name in ('TCheckbutton','TRadiobutton'):
            st.configure(name,background=BG,foreground=ON_DARK,indicatorbackground=WHITE,
                         indicatorforeground=TEXT,focuscolor=BG)
            st.map(name,background=[('active',DARK_SURFACE_ALT)],foreground=[('disabled',ON_DARK_MUTED),('active',ON_DARK)],
                   indicatorbackground=[('selected',WHITE),('active',WHITE)])
        st.configure('TEntry',fieldbackground=WHITE,foreground=TEXT,insertcolor=TEXT)
        st.configure('TSpinbox',fieldbackground=WHITE,foreground=TEXT,insertcolor=TEXT,arrowcolor=ON_DARK,background=DARK_SURFACE_ALT)
        st.configure('TCombobox',fieldbackground=WHITE,foreground=TEXT,arrowcolor=ON_DARK,background=DARK_SURFACE_ALT,
                     selectbackground='#dbeafe',selectforeground=TEXT)
        st.map('TCombobox',fieldbackground=[('readonly',WHITE),('disabled','#e2e8f0')],
               foreground=[('readonly',TEXT),('disabled',MUTED)],
               selectbackground=[('readonly','#dbeafe')],selectforeground=[('readonly',TEXT)])
        st.configure('TScrollbar',background=DARK_SURFACE_ALT,troughcolor=DARK_SURFACE,arrowcolor=ON_DARK,bordercolor=DARK_BORDER)
        st.map('TScrollbar',background=[('active',DARK_SCROLL_ACTIVE)])
        st.configure('TNotebook',background=BG,bordercolor=DARK_BORDER)
        st.configure('TNotebook.Tab',background=DARK_SURFACE,foreground=ON_DARK_MUTED,padding=(12,6))
        st.map('TNotebook.Tab',background=[('selected',BLUE),('active',DARK_SURFACE_ALT)],
               foreground=[('selected',WHITE),('active',ON_DARK)])
        st.configure('TSeparator',background=DARK_BORDER)
        st.configure('Toolbar.TFrame',background=DARK_SIDEBAR)
        st.configure('Toolbar.TButton',background=DARK_SIDEBAR,foreground=ON_DARK,padding=(8,5))
        st.map('Toolbar.TButton',background=[('pressed',PRESSED_BG),('active',DARK_SURFACE_ALT)],
               foreground=[('active',ON_HOVER)])
        st.configure('ToolbarSelected.TButton',background=BLUE,foreground=WHITE,padding=(8,5))
        st.map('ToolbarSelected.TButton',background=[('pressed',ACCENT_HOVER),('active',ACCENT_HOVER)],
               foreground=[('active',WHITE)])
        for name in ('TButton','Secondary.TButton','Report.TButton','CompactReport.TButton','MonthNav.TButton'):
            st.configure(name,background=DARK_SURFACE_ALT,foreground=ON_DARK,focuscolor=DARK_SURFACE_ALT)
            st.map(name,background=[('pressed',PRESSED_BG),('active',DARK_HOVER)],
                   foreground=[('disabled',DARK_DISABLED),('active',ON_HOVER)])
        st.configure('Orange.TMenubutton',background=DARK_SURFACE_ALT,foreground=ON_DARK,arrowcolor=ON_DARK)
        st.map('Orange.TMenubutton',background=[('active',DARK_HOVER)],
               foreground=[('active',ON_HOVER)],arrowcolor=[('active',ON_HOVER)])
        st.configure('Accent.TButton',background=BLUE,foreground=WHITE)
        st.map('Accent.TButton',background=[('active',ACCENT_HOVER)],foreground=[('active',WHITE)])
        self.option_add('*TCombobox*Listbox.background',WHITE)
        self.option_add('*TCombobox*Listbox.foreground',TEXT)
        self.option_add('*TCombobox*Listbox.selectBackground','#dbeafe')
        self.option_add('*TCombobox*Listbox.selectForeground',TEXT)

    def _build(self):
        toolbar=ttk.Frame(self,style='Toolbar.TFrame',padding=(8,6))
        toolbar.pack(fill='x')
        self.navigation_buttons={}
        navigation=[
            ('dashboard','Painel'),('payroll','Folha mensal'),
            ('employees','Colaboradores'),('salaries','Salários'),
            ('loans','Proventos / Descontos'),
        ]
        if not getattr(self,'centralized_actions',False):
            navigation.append(('about','Sobre'))
        for section,label in navigation:
            button=ttk.Button(
                toolbar,text=label,style='Toolbar.TButton',
                command=lambda name=section:self.navigate(name))
            button.pack(side='left',padx=2)
            self.navigation_buttons[section]=button
        if not getattr(self,'centralized_actions',False):
            self.backup_button=ttk.Button(
                toolbar,text='Backup',style='Toolbar.TButton',
                command=lambda:self.show_backup_options(self.backup_button))
            self.backup_button.pack(side='left',padx=2)
            self.change_password_button=ttk.Button(
                toolbar,text='Alterar senha',style='Toolbar.TButton',
                command=self.change_password_dialog)
            self.change_password_button.pack(side='left',padx=2)
        self._add_tab_action_icons(toolbar)
        for button in toolbar.winfo_children():
            button.configure(compound='top',width=14)
        self.navigation_buttons['loans'].configure(width=22)
        if 'about' in self.navigation_buttons:
            self.navigation_buttons['about'].configure(width=8)
        if getattr(self,'centralized_actions',False):
            self.signing_expiry_label=tk.Label(
                toolbar,text="",bg="#FFF7ED",fg="#9A3412",
                font=("Segoe UI Semibold",9),anchor="w",justify="left",
                padx=9,pady=5,relief="solid",bd=1,cursor="hand2")
            self.signing_expiry_label.pack(side='left',padx=(8,0),pady=2)
            self.signing_expiry_label.bind(
                '<Button-1>',lambda _event:self.show_signing_expiry_details())
            self.update_signing_expiry_notice()
        tk.Frame(self,bg=DARK_BORDER,height=1).pack(fill='x')
        content=ttk.Frame(self,padding=(8,6))
        content.pack(fill='both',expand=True)
        titlebar=ttk.Frame(content)
        titlebar.pack(fill='x',pady=(0,8))
        logo_card=tk.Frame(
            titlebar,bg=WHITE,highlightbackground='#dbe3ee',
            highlightthickness=1,padx=6,pady=3)
        with Image.open(resource_path('logo_revisa.png')) as logo_source:
            logo_source.thumbnail((96,52),Image.Resampling.LANCZOS)
            self.dashboard_logo_image=ImageTk.PhotoImage(
                logo_source.copy(),master=self)
        tk.Label(logo_card,image=self.dashboard_logo_image,bg=WHITE).pack()
        self.dashboard_logo_card=logo_card
        self.dashboard_logo_card.pack(side='left',padx=(0,12))
        self.page_title=ttk.Label(titlebar,text='Painel de controle',style='Title.TLabel')
        self.page_title.pack(side='left',pady=8)
        scroll_host=ScrollableHost(content)
        scroll_host.pack(fill='both',expand=True)
        self.scroll_host=scroll_host
        self.page_host=scroll_host.inner
        self.dashboard_tab=ttk.Frame(self.page_host,padding=14)
        self.payroll_tab=ttk.Frame(self.page_host,padding=12)
        self.employees_tab=ttk.Frame(self.page_host,padding=12)
        self.salaries_tab=ttk.Frame(self.page_host,padding=12)
        self.loans_tab=ttk.Frame(self.page_host,padding=12)
        self.about_tab=ttk.Frame(self.page_host,padding=12)
        self._build_dashboard(); self._build_payroll(); self._build_employees(); self._build_salaries(); self._build_loans()
        self._build_about()
        self.navigate('dashboard')

    def _apply_dialog_branding(self,event):
        window=event.widget
        scope=str(self)
        if scope!='.' and not str(window).startswith(scope+'.'):
            return
        if isinstance(window,tk.Toplevel):
            try:
                window.iconbitmap(resource_path('folha_pagamento.ico'))
                window.configure(bg=BG)
            except tk.TclError:
                return

    def navigate(self,section):
        pages={
            'dashboard':(self.dashboard_tab,'Painel de controle'),
            'payroll':(self.payroll_tab,'Folha mensal'),
            'employees':(self.employees_tab,'Colaboradores'),
            'salaries':(self.salaries_tab,'Salários e reajustes'),
            'loans':(self.loans_tab,'Proventos / Descontos'),
            'about':(self.about_tab,'Sobre o sistema'),
        }
        if section not in pages:
            raise ValueError(f'Seção de navegação desconhecida: {section}')
        if getattr(self,'current_section',None):
            self.current_page.pack_forget()
        self.current_section=section
        self.current_page,self_title=pages[section]
        self.current_page.pack(fill='both',expand=True)
        if section!='dashboard':
            self.dashboard_logo_card.pack_forget()
        self.page_title.configure(text=self_title)
        # O conteúdo da seção anterior pode ter deixado a área maior; recalcula as barras de rolagem.
        self.scroll_host.after_idle(self.scroll_host._layout)
        if section=='loans':
            self.refresh_loans()
        for key,button in self.navigation_buttons.items():
            selected=key==section
            button.configure(style='ToolbarSelected.TButton' if selected else 'Toolbar.TButton')

    def update_signing_expiry_notice(self):
        if not getattr(self,'centralized_actions',False):
            return
        notice,status,_when=self.signing_status_callback()
        if status=='ok':
            text=f'Assinatura válida até {_when}'
            background,foreground='#ECFDF3','#067647'
        elif status=='expired':
            text=f'ATENÇÃO: assinatura venceu em {_when}'
            background,foreground='#FEF3F2','#B42318'
        elif status=='warning':
            text=f'ATENÇÃO: assinatura vence em {notice.split(" em ",1)[1].split(" (",1)[0]}'
            background,foreground='#FFF7ED','#9A3412'
        else:
            text='Assinatura: validade indisponível'
            background,foreground='#F3F4F6','#667085'
        self.signing_expiry_label.configure(
            text=text,bg=background,fg=foreground)
        self.signing_expiry_details=notice

    def show_signing_expiry_details(self):
        messagebox.showinfo(
            'Validade da assinatura digital',
            self.signing_expiry_details,
            parent=self.winfo_toplevel())

    def _build_about(self):
        ttk.Label(self.about_tab,text=APP_NAME,style='PageHeading.TLabel').pack(anchor='w',pady=(0,12))
        details=(
            ('Versão',APP_VERSION),
            ('Desenvolvedor','Jorge Alberto de Paula'),
            ('Sistema','REVISA | Folha de Pagamento'),
            ('Finalidade','Gestão de colaboradores, salários, folha mensal, proventos, descontos e relatórios.'),
            ('Armazenamento','Dados locais em banco SQLite. Faça backups regularmente.'),
            ('Banco de dados',DB_PATH),
        )
        for heading,value in details:
            ttk.Label(self.about_tab,text=heading,font=('Segoe UI Semibold',10)).pack(anchor='w',pady=(8,2))
            ttk.Label(self.about_tab,text=value,wraplength=620,justify='left').pack(anchor='w')

    def _build_dashboard(self):
        wrap=self.dashboard_tab
        topbar=ttk.Frame(wrap)
        topbar.pack(fill='x',pady=(0,10))
        ttk.Label(topbar,text='Visão geral da folha',style='PageHeading.TLabel').pack(side='left')
        self.dashboard_period=ttk.Label(topbar,text='',style='Sub.TLabel')
        self.dashboard_period.pack(side='right',padx=(8,0))
        quick=ttk.Frame(wrap)
        quick.pack(fill='x',pady=(0,12))
        ttk.Button(quick,text='Abrir folha mensal',style='Accent.TButton',command=lambda:self.navigate('payroll')).pack(side='left',padx=(0,8))
        ttk.Button(quick,text='Colaboradores',style='Secondary.TButton',command=lambda:self.navigate('employees')).pack(side='left',padx=(0,8))
        cards=ttk.Frame(wrap); cards.pack(fill='x',pady=(0,14))
        self.dashboard_cards=cards
        self.card_values=[]
        self.card_titles=[]
        self.card_hints=[]
        card_data=[
            ('♙','Colaboradores ativos'),
            ('R$','Total líquido da competência'),
            ('▤','Colaboradores lançados'),
            ('◷','Folhas em revisão no ano'),
        ]
        for index,(icon,title) in enumerate(card_data):
            f=tk.Frame(cards,bg=WHITE,highlightbackground='#dbe3ee',highlightthickness=1)
            f.pack(side='left',fill='both',expand=True,padx=(0,10 if index<len(card_data)-1 else 0))
            accent=BLUE if index in (0,1) else GREEN
            tk.Frame(f,bg=accent,height=3).pack(fill='x')
            tk.Label(
                f,text=icon,bg='#eff6ff' if index in (0,1) else '#ecfdf5',
                fg=accent,font=('Segoe UI Semibold',11),width=4
            ).pack(anchor='w',padx=12,pady=(9,4))
            title_label=tk.Label(f,text=title,bg=WHITE,fg=MUTED,font=('Segoe UI Semibold',9))
            title_label.pack(anchor='w',padx=14,pady=(0,1))
            v=ttk.Label(f,text='—',style='CardValue.TLabel')
            v.pack(anchor='w',padx=14,pady=(0,0))
            hint=tk.Label(f,text='',bg=WHITE,fg=MUTED,font=('Segoe UI',8))
            hint.pack(anchor='w',padx=14,pady=(0,9))
            self.card_titles.append(title_label)
            self.card_values.append(v)
            self.card_hints.append(hint)
        summary=ttk.Frame(wrap); summary.pack(fill='x',pady=(0,14))
        closed_card=tk.Frame(summary,bg=WHITE,highlightbackground='#dbe3ee',highlightthickness=1)
        closed_card.pack(side='left',fill='y',padx=(0,12))
        tk.Frame(closed_card,bg=GREEN,height=3).pack(fill='x')
        self.closed_title=tk.Label(closed_card,text='Total anual das folhas fechadas',bg=WHITE,fg=MUTED,font=('Segoe UI Semibold',9))
        self.closed_title.pack(anchor='w',padx=14,pady=(10,1))
        self.closed_total=ttk.Label(closed_card,text='—',style='CardValue.TLabel')
        self.closed_total.pack(anchor='w',padx=14)
        self.closed_hint=tk.Label(closed_card,text='',bg=WHITE,fg=MUTED,font=('Segoe UI',8),justify='left')
        self.closed_hint.pack(anchor='w',padx=14,pady=(0,10))
        review_card=tk.Frame(summary,bg=WHITE,highlightbackground='#dbe3ee',highlightthickness=1)
        review_card.pack(side='left',fill='both',expand=True)
        tk.Frame(review_card,bg='#f59e0b',height=3).pack(fill='x')
        review_head=tk.Frame(review_card,bg=WHITE)
        review_head.pack(fill='x',padx=14,pady=(8,2))
        self.review_title=tk.Label(review_head,text='Folhas em revisão (falta fechar)',bg=WHITE,fg=MUTED,font=('Segoe UI Semibold',9))
        self.review_title.pack(side='left')
        self.review_total=tk.Label(review_head,text='',bg=WHITE,fg=NAVY,font=('Segoe UI Semibold',9))
        self.review_total.pack(side='right')
        review_body=tk.Frame(review_card,bg=WHITE)
        review_body.pack(fill='both',expand=True,padx=10,pady=(0,8))
        self.review_tree=ttk.Treeview(review_body,columns=('period','status','net'),show='headings',height=3)
        for column,heading,width,anchor in (('period','Competência',160,'w'),('status','Situação',120,'w'),('net','Valor líquido',140,'e')):
            self.review_tree.heading(column,text=heading)
            self.review_tree.column(column,width=width,anchor=anchor)
        review_scroll=ttk.Scrollbar(review_body,orient='vertical',command=self.review_tree.yview)
        self.review_tree.configure(yscrollcommand=review_scroll.set)
        self.review_tree.pack(side='left',fill='both',expand=True)
        review_scroll.pack(side='right',fill='y')
        charts=ttk.Frame(wrap)
        charts.pack(fill='both',expand=True)
        self.dashboard_chart_data=[]
        self.dashboard_charts=[]
        self.dashboard_chart_titles=[]
        self.dashboard_chart_subtitles=[]
        for index,(title,kind) in enumerate((
            ('Total líquido por mês','net'),
            ('Colaboradores lançados por mês','people'),
        )):
            chart_card=tk.Frame(charts,bg=WHITE,highlightbackground='#dbe3ee',highlightthickness=1)
            chart_card.pack(side='left',fill='both',expand=True,padx=(0,12 if index==0 else 0))
            tk.Frame(chart_card,bg='#e7edf5',height=1).pack(side='bottom',fill='x')
            title_label=tk.Label(chart_card,text=title,bg=WHITE,fg=NAVY,font=('Segoe UI Semibold',11))
            title_label.pack(anchor='w',padx=16,pady=(13,1))
            subtitle_label=tk.Label(
                chart_card,text='Acompanhamento das 12 competências do ano',
                bg=WHITE,fg=MUTED,font=('Segoe UI',8))
            subtitle_label.pack(anchor='w',padx=16)
            canvas=tk.Canvas(chart_card,bg=WHITE,highlightthickness=0,height=200)
            canvas.pack(fill='both',expand=True,padx=10,pady=(4,8))
            canvas.bind('<Configure>',lambda event,c=canvas,k=kind:self._draw_dashboard_chart(c,k))
            self.dashboard_charts.append((canvas,kind))
            self.dashboard_chart_titles.append(title_label)
            self.dashboard_chart_subtitles.append(subtitle_label)

    def _tab_action_layout(self,parent):
        parent.configure(padding=(8,0,8,8))
        actions=ttk.Frame(parent,width=184,padding=(0,0,8,0))
        actions.pack(side='left',fill='y',anchor='n')
        actions.pack_propagate(False)
        content=ttk.Frame(parent)
        content.pack(side='left',fill='both',expand=True)
        return actions,content

    def _align_tab_actions(self,actions,table):
        spacer=ttk.Frame(actions,height=0)
        children=actions.pack_slaves()
        if children:
            spacer.pack(fill='x',before=children[0])
        else:
            spacer.pack(fill='x')

        def align(event=None):
            offset=max(0,table.winfo_rooty()-actions.winfo_rooty())
            if spacer.winfo_reqheight()!=offset:
                spacer.configure(height=offset)

        table.bind('<Configure>',align,add='+')
        table.bind('<Map>',align,add='+')

    def _tab_reports(self,parent,entries,style='Report.TButton'):
        group=ttk.LabelFrame(parent,text='Relatórios',padding=(4,6))
        group.pack(side='bottom',fill='x',pady=(14,6))
        for label,command in entries:
            ttk.Button(
                group,text=label,style=style,
                command=command).pack(fill='x',pady=(0,4))
        self._add_tab_action_icons(group)

    def _add_tab_action_icons(self,actions):
        for button in actions.winfo_children():
            if button.winfo_class() not in ('TButton','TMenubutton'):
                continue
            if button.cget('image'):
                continue
            text=button.cget('text').lower()
            image=Image.new('RGBA',(64,64),(0,0,0,0))
            draw=ImageDraw.Draw(image)
            if button.cget('style')!='Report.TButton':
                draw.ellipse((9,52,58,61),fill='#b4c1d3')
            if text=='sobre':
                draw.ellipse((9,6,56,53),fill='#2563eb',outline='#174176',width=2)
                draw.ellipse((29,15,35,21),fill='white')
                draw.line((32,28,32,43),fill='white',width=5)
            elif 'excluir' in text:
                draw.rounded_rectangle((17,17,49,55),radius=4,fill='#dce5ef',outline='#596d87',width=2)
                draw.rectangle((14,13,52,20),fill='#e65b4f',outline='#9e302c',width=2)
                draw.rectangle((25,8,41,13),fill='#f58a72',outline='#9e302c',width=2)
                for x in (25,33,41):
                    draw.line((x,26,x,48),fill='#8295ad',width=3)
            elif 'novo' in text or 'cadastrar' in text:
                draw.rounded_rectangle((8,34,43,56),radius=8,fill='#286cc2',outline='#174176',width=2)
                draw.ellipse((15,8,36,34),fill='#efb56d',outline='#986335',width=2)
                draw.pieslice((15,5,36,24),180,360,fill='#9b6037')
                draw.ellipse((36,32,61,57),fill='#60b94c',outline='#287534',width=2)
                draw.line((42,45,55,45),fill='white',width=4)
                draw.line((49,38,49,52),fill='white',width=4)
            elif 'fechar' in text or 'reabrir' in text:
                draw.arc((18,6,46,39),180,360,fill='#6c7d91',width=7)
                draw.rounded_rectangle((12,27,53,56),radius=5,fill='#efb841',outline='#a67520',width=2)
                draw.rectangle((16,30,49,35),fill='#ffdb78')
                draw.ellipse((29,38,37,46),fill='#73511e')
                draw.line((33,43,33,49),fill='#73511e',width=3)
            elif button.cget('style')=='ImportPdf.TButton' or 'importar' in text:
                draw.polygon([(13,4),(40,4),(52,16),(52,58),(13,58)],
                             fill='white',outline='#496686',width=3)
                draw.line((40,5,40,17,51,17),fill='#496686',width=3)
                draw.line((21,25,43,25),fill='#a8b8ca',width=3)
                draw.line((21,31,34,31),fill='#a8b8ca',width=3)
                draw.line((33,30,33,45),fill='#dc2626',width=5)
                draw.polygon([(25,40),(33,49),(41,40)],fill='#dc2626')
                draw.line((23,53,43,53),fill='#496686',width=3)
            elif 'pdf' in text:
                draw.polygon([(13,4),(40,4),(52,16),(52,58),(13,58)],
                             fill='white',outline='#496686',width=3)
                draw.line((40,5,40,17,51,17),fill='#496686',width=3)
                for y in (25,32,39,46):
                    draw.line((21,y,44,y),fill='#718da9',width=3)
                draw.rounded_rectangle((6,31,59,53),radius=3,fill='#d93636')
                draw.line((16,48,16,36,24,36,24,42,16,42),fill='white',width=2)
                draw.line((30,48,30,36,36,36,40,40,40,44,36,48,30,48),fill='white',width=2)
                draw.line((46,48,46,36,54,36),fill='white',width=2)
                draw.line((46,42,52,42),fill='white',width=2)
            elif 'senha' in text:
                draw.arc((18,6,46,38),180,360,fill='#93a4bb',width=7)
                draw.line((18,22,18,30),fill='#93a4bb',width=7)
                draw.line((46,22,46,30),fill='#93a4bb',width=7)
                draw.rounded_rectangle((10,28,54,58),radius=7,fill='#2563eb',outline='#1e3a8a',width=2)
                draw.ellipse((27,36,37,46),fill='white')
                draw.line((32,44,32,52),fill='white',width=4)
            elif 'salvar' in text:
                draw.rounded_rectangle((8,7,56,56),radius=4,fill='#4777ce',outline='#233f7b',width=2)
                draw.rectangle((12,10,51,14),fill='#85aff1')
                draw.rectangle((20,8,44,27),fill='#c5d4e9',outline='#233f7b',width=2)
                draw.rectangle((35,11,40,23),fill='#527299')
                draw.rectangle((17,35,48,55),fill='#f8fbff',outline='#233f7b',width=2)
                draw.line((23,42,42,42),fill='#9bb6d9',width=2)
                draw.line((23,48,42,48),fill='#9bb6d9',width=2)
            elif text=='painel':
                for x0,y0 in ((8,6),(34,6),(8,30),(34,30)):
                    draw.rounded_rectangle((x0,y0,x0+22,y0+20),radius=4,fill='#3b82f6' if (x0,y0)==(8,6) else '#93c5fd',outline='#1e40af',width=2)
            elif text=='folha mensal':
                draw.rounded_rectangle((8,10,56,56),radius=5,fill='#f8fbff',outline='#1e40af',width=2)
                draw.rectangle((8,10,56,22),fill='#3b82f6')
                draw.line((20,5,20,15),fill='#1e40af',width=4)
                draw.line((44,5,44,15),fill='#1e40af',width=4)
                for y in (29,38,47):
                    for x in (15,27,39):
                        draw.rectangle((x,y,x+7,y+5),fill='#93a4bb')
            elif text=='colaboradores':
                draw.ellipse((6,10,26,30),fill='#93c5fd',outline='#1e40af',width=2)
                draw.pieslice((2,30,30,62),180,360,fill='#93c5fd',outline='#1e40af',width=2)
                draw.ellipse((26,4,50,28),fill='#3b82f6',outline='#1e40af',width=2)
                draw.pieslice((20,28,56,64),180,360,fill='#3b82f6',outline='#1e40af',width=2)
            elif text=='salários':
                draw.ellipse((8,8,56,56),fill='#22c55e',outline='#166534',width=3)
                draw.arc((22,16,42,32),90,330,fill='white',width=4)
                draw.arc((22,30,42,46),270,150,fill='white',width=4)
                draw.line((32,11,32,51),fill='white',width=3)
            elif text=='proventos / descontos':
                draw.ellipse((4,8,32,36),fill='#22c55e',outline='#166534',width=2)
                draw.line((11,22,25,22),fill='white',width=4)
                draw.line((18,15,18,29),fill='white',width=4)
                draw.ellipse((30,26,58,54),fill='#ef4444',outline='#991b1b',width=2)
                draw.line((37,40,51,40),fill='white',width=4)
            elif text=='backup':
                draw.rounded_rectangle((8,7,56,56),radius=4,fill='#4777ce',outline='#233f7b',width=2)
                draw.rectangle((20,8,44,27),fill='#c5d4e9',outline='#233f7b',width=2)
                draw.rectangle((35,11,40,23),fill='#527299')
                draw.rectangle((17,35,48,55),fill='#f8fbff',outline='#233f7b',width=2)
            else:
                draw.rounded_rectangle((8,8,45,54),radius=3,fill='#fff8dd',outline='#b49450',width=2)
                for y in (18,27,36,45):
                    draw.line((15,y,36,y),fill='#c9b57d',width=2)
                draw.polygon([(20,45),(47,13),(56,21),(29,53),(17,57)],fill='#f4be43',outline='#8f6622',width=2)
                draw.polygon([(17,57),(20,45),(29,53)],fill='#f1d7aa')
                draw.polygon([(17,57),(19,51),(23,55)],fill='#3e4857')
                draw.polygon([(47,13),(51,9),(60,17),(56,21)],fill='#ef827c',outline='#9a4f53')
            button.action_icon=ImageTk.PhotoImage(
                image.resize((18,18),Image.Resampling.LANCZOS),master=button)
            button.configure(image=button.action_icon,compound='left')

    def _build_payroll(self):
        actions,content=self._tab_action_layout(self.payroll_tab)
        bar=ttk.Frame(content);bar.pack(fill='x',pady=(0,10))
        ttk.Label(bar,text='Ano:').pack(side='left')
        self.pay_year=ttk.Combobox(bar,width=9,state='readonly',values=[]);self.pay_year.pack(side='left',padx=(6,14));self.pay_year.set(str(self.current_payroll_year))
        self.pay_year.bind('<<ComboboxSelected>>',self.on_year_selected)
        ttk.Label(bar,text='Mês:').pack(side='left')
        ttk.Button(bar,text='◀',width=3,style='MonthNav.TButton',command=lambda:self.navigate_payroll_month(-1)).pack(side='left',padx=(6,0))
        self.pay_month=ttk.Combobox(bar,width=14,state='readonly',values=MONTHS);self.pay_month.pack(side='left',padx=6);self.pay_month.set(MONTHS[self.current_payroll_month-1])
        self.pay_month.bind('<<ComboboxSelected>>',self.on_month_selected)
        ttk.Button(bar,text='▶',width=3,style='MonthNav.TButton',command=lambda:self.navigate_payroll_month(1)).pack(side='left',padx=(0,8))
        self.payroll_edit_buttons=[]
        self.payroll_edit_buttons.append(ttk.Button(
            actions,text='Editar lançamento',style='EditLaunch.TButton',
            command=self.edit_selected_item))
        self.payroll_edit_buttons[-1].pack(fill='x',pady=(0,6))
        ttk.Button(
            actions,text='DP - Antares',style='ImportPdf.TButton',
            command=self.import_accounting_pdf_dialog).pack(fill='x',pady=(0,6))
        self.payroll_status_button=ttk.Button(actions,text='Fechar folha',style='ClosePayroll.TButton',command=self.toggle_status)
        self.payroll_status_button.pack(fill='x',pady=(0,6))
        share_row=actions
        icon=Image.new('RGBA',(112,112),(0,0,0,0))
        draw=ImageDraw.Draw(icon)
        draw.ellipse((4,4,108,108),fill='#25D366')
        draw.ellipse((21,18,91,88),outline='white',width=6)
        draw.polygon([(26,70),(20,94),(46,85)],fill='white')
        draw.polygon([(31,73),(28,85),(43,81)],fill='#25D366')
        draw.arc((38,32,80,74),start=85,end=190,fill='white',width=10)
        draw.polygon(
            [(37,35),(42,31),(48,32),(54,44),(49,50),(41,46)],
            fill='white')
        draw.polygon(
            [(61,65),(67,58),(79,63),(81,69),(76,75),(67,73)],
            fill='white')
        icon=icon.resize((15,15),Image.Resampling.LANCZOS)
        self.whatsapp_icon=ImageTk.PhotoImage(icon,master=self)
        ttk.Button(
            share_row,text='WhatsApp',image=self.whatsapp_icon,
            compound='left',style='WhatsApp.TButton',
            command=self.send_payslips_whatsapp_batch_dialog).pack(fill='x',pady=(0,6))
        columns=('name','note_marker','salary','pf','overtime','vacation','thirteenth','marmitex','advances','pharmacy','loan','loan_installment','total')
        payroll_table=ttk.Frame(content)
        payroll_table.pack(fill='both',expand=True)
        self._align_tab_actions(actions,payroll_table)
        payroll_style=ttk.Style(self)
        payroll_style.configure('Payroll.Treeview',foreground='#000000')
        payroll_style.map(
            'Payroll.Treeview',foreground=[('selected','#000000')],
            background=[('selected','#dbeafe')])
        self.pay_tree=ttk.Treeview(payroll_table,columns=columns,show='headings',selectmode='browse',style='Payroll.Treeview')
        heads={'name':'Colaborador','note_marker':'','salary':'Salário','pf':'PF / adicional','overtime':'Hora extra','vacation':'Férias','thirteenth':'13º salário','marmitex':'Marmitex','advances':'Adiantamento Salarial','pharmacy':'Farmácia','loan':'Empréstimo','loan_installment':'Empréstimo / Vale','total':'Total líquido'}
        widths={'name':175,'note_marker':26,'salary':100,'pf':95,'overtime':95,'vacation':95,'thirteenth':100,'marmitex':95,'advances':150,'pharmacy':95,'loan':100,'loan_installment':125,'total':115}
        for c in columns:
            self.pay_tree.heading(c,text=heads[c]);self.pay_tree.column(c,width=widths[c],anchor='w' if c=='name' else 'center')
        self.pay_tree.column('note_marker',anchor='e',minwidth=26,stretch=False)
        payroll_scroll=ttk.Scrollbar(payroll_table,orient='horizontal',command=self.pay_tree.xview)
        self.payroll_cell_labels={}
        self.payroll_note_marker_refresh=None

        def on_horizontal_scroll(first,last):
            payroll_scroll.set(first,last)
            self._schedule_payroll_note_markers()

        self.pay_tree.configure(
            xscrollcommand=on_horizontal_scroll,
            yscrollcommand=lambda *_:self._schedule_payroll_note_markers())
        for event in ('<Configure>','<Map>','<<TreeviewSelect>>','<B1-Motion>','<ButtonRelease-1>'):
            self.pay_tree.bind(event,lambda _:self._schedule_payroll_note_markers(),add='+')
        self.pay_tree.bind('<Destroy>',self._cancel_payroll_note_markers,add='+')
        self.pay_tree.pack(fill='both',expand=True)
        payroll_scroll.pack(fill='x')
        self.pay_tree.bind('<Double-1>',lambda e:self.edit_selected_item())
        row_font=('Segoe UI',9,'bold')
        self.pay_tree.tag_configure('launch_full',background='#e6f6ec',foreground='#000000',font=row_font)
        self.pay_tree.tag_configure('launch_partial',background='#fdf6d0',foreground='#000000',font=row_font)
        self.pay_tree.tag_configure(
            'launch_full_note',background='#ffedd5',foreground='#000000',font=row_font)
        self.pay_tree.tag_configure(
            'launch_partial_note',background='#ffedd5',foreground='#000000',font=row_font)
        observations_frame=ttk.LabelFrame(
            content,text='Observações dos colaboradores',padding=(8,4))
        observations_frame.pack(fill='x',pady=(6,0))
        self.payroll_observations=tk.Text(
            observations_frame,height=8,wrap='word',font=('Segoe UI',10),
            bg=WHITE,fg=TEXT,relief='flat',bd=0,padx=8,pady=6)
        self.payroll_observations.tag_configure(
            'employee_name',font=('Segoe UI Semibold',10),foreground='#000000',
            spacing1=4,background='#ffedd5')
        self.payroll_observations.tag_configure(
            'employee_note',lmargin1=12,lmargin2=12,spacing3=5,
            foreground='#000000',background='#ffedd5')
        self.payroll_observations.tag_configure(
            'employee_marker',foreground='#dc2626')
        self.payroll_observations.tag_configure(
            'empty_notes',foreground=MUTED)
        observations_scroll=ttk.Scrollbar(
            observations_frame,orient='vertical',command=self.payroll_observations.yview)
        self.payroll_observations.configure(
            yscrollcommand=observations_scroll.set,state='disabled')
        self.payroll_observations.pack(side='left',fill='x',expand=True)
        observations_scroll.pack(side='right',fill='y')
        self.pay_summary=ttk.Label(content,text='Selecione o mês.',font=('Segoe UI Semibold',11));self.pay_summary.pack(anchor='e',pady=(10,0))
        self.pay_note=ttk.Label(content,text='Os valores são calculados no sistema; itens importados mantêm também o total original da planilha.',style='Sub.TLabel');self.pay_note.pack(anchor='w',pady=(6,0))
        self._add_tab_action_icons(actions)
        self._tab_reports(actions,[
            ('Folha (PDF)',self.generate_payroll_pdf_dialog),
            ('Holerites (PDF)',self.generate_payslips_dialog)])

    def _schedule_payroll_note_markers(self):
        if self.payroll_note_marker_refresh is None:
            self.payroll_note_marker_refresh=self.after_idle(self._refresh_payroll_note_markers)

    def _cancel_payroll_note_markers(self,event):
        if event.widget is self.pay_tree and self.payroll_note_marker_refresh is not None:
            self.after_cancel(self.payroll_note_marker_refresh)
            self.payroll_note_marker_refresh=None

    def _refresh_payroll_note_markers(self):
        self.payroll_note_marker_refresh=None
        tree=self.pay_tree
        visible=set()
        selected=set(tree.selection())
        credit_columns=('salary','pf','overtime','vacation','thirteenth','total')
        debit_columns=('marmitex','advances','pharmacy','loan','loan_installment')
        for item in tree.get_children():
            if not tree.bbox(item):
                continue
            background=(
                ttk.Style(tree).lookup(tree['style'],'background',('selected',))
                if item in selected else
                tree.tag_configure(tree.item(item,'tags')[0],'background'))
            for column in ('note_marker',)+credit_columns+debit_columns:
                text=tree.set(item,column)
                bounds=tree.bbox(item,column)
                if not text or not bounds:
                    continue
                x,y,width,height=bounds
                if x+width<=0 or x>=tree.winfo_width():
                    continue
                key=(item,column)
                visible.add(key)
                if key not in self.payroll_cell_labels:
                    # Treeview tags color whole rows; overlay only colored cells.
                    color=('#dc2626' if column=='note_marker' else
                           '#15803d' if column in credit_columns else '#b91c1c')
                    label=tk.Label(
                        tree,fg=color,font=('Segoe UI',9,'bold'),
                        anchor='e' if column=='note_marker' else 'center',
                        bd=0,padx=0,pady=0,takefocus=False)
                    label.bind('<Button-1>',lambda event,i=item:self._select_payroll_note_marker(i))
                    label.bind('<Double-1>',lambda event,i=item:self._select_payroll_note_marker(i,edit=True))
                    label.bind('<MouseWheel>',lambda event:tree.event_generate(
                        '<MouseWheel>',delta=event.delta,state=event.state))
                    self.payroll_cell_labels[key]=label
                label=self.payroll_cell_labels[key]
                label.configure(text=text,bg=background)
                label.place(
                    x=x,y=y,width=max(1,width-(4 if column=='note_marker' else 0)),
                    height=height)
        for key in list(self.payroll_cell_labels):
            if key not in visible:
                self.payroll_cell_labels.pop(key).destroy()

    def _select_payroll_note_marker(self,item,edit=False):
        self.pay_tree.selection_set(item)
        self.pay_tree.focus(item)
        self.pay_tree.focus_set()
        if edit:
            self.edit_selected_item()

    def _show_payroll_item_notes(self,rows):
        self.payroll_observations.configure(state='normal')
        self.payroll_observations.delete('1.0','end')
        notes=[row for row in rows if row['notes'] and row['notes'].strip()]
        if notes:
            for row in notes:
                self.payroll_observations.insert(
                    'end','● ',('employee_name','employee_marker'))
                self.payroll_observations.insert(
                    'end',f'{row["name"]}\n','employee_name')
                self.payroll_observations.insert(
                    'end',f'{row["notes"].strip()}\n','employee_note')
        else:
            self.payroll_observations.insert(
                '1.0','Nenhuma observação de colaborador nesta folha.',
                'empty_notes')
        self.payroll_observations.configure(state='disabled')

    def _build_employees(self):
        actions,content=self._tab_action_layout(self.employees_tab)
        bar=ttk.Frame(content);bar.pack(fill='x',pady=(0,10))
        ttk.Label(bar,text='Cadastro geral de colaboradores',font=('Segoe UI Semibold',13)).pack(side='left')
        bar=actions
        ttk.Button(bar,text='Novo colaborador',style='Accent.TButton',command=self.add_employee_dialog).pack(fill='x',pady=(0,6))
        self.employee_actions_menu=tk.Menu(self,tearoff=0)
        for label,command in (
            ('Editar cadastro',self.edit_selected_employee),
            ('Salário / reajustes',self.employee_salary_dialog),
            ('Ativar / inativar',self.toggle_employee),
            (None,None),
            ('Excluir colaborador',self.delete_selected_employee),
        ):
            if label is None:
                self.employee_actions_menu.add_separator()
            else:
                self.employee_actions_menu.add_command(label=label,command=command)
        actions_button=ttk.Menubutton(bar,text='Ações do cadastro',style='Orange.TMenubutton',menu=self.employee_actions_menu)
        actions_button.pack(fill='x',pady=(0,6))
        cols=('code','name','role','salary','sector','email','phone','pix','bank','bank_agency','bank_account','address','bairro','cep','city','state','ctps','birth_date','cpf','admission_date','dismissal_date','active')
        employee_columns=[
            ('code','Código',90),('name','Nome',190),('role','Cargo',140),('salary','Salário atual',115),('sector','Setor',120),
            ('email','E-mail',170),('phone','Telefone',125),('pix','PIX',160),
            ('bank','Banco',160),('bank_agency','Agência',100),('bank_account','Conta',140),
            ('address','Endereço',240),
            ('bairro','Bairro',150),
            ('cep','CEP',100),('city','Cidade',150),('state','Estado',100),
            ('ctps','CTPS',130),('birth_date','Nascimento',115),('cpf','CPF',130),
            ('admission_date','Admissão',115),('dismissal_date','Demissão',115),('active','Situação',90),
        ]
        self.employee_tree_notebook=ttk.Notebook(content)
        active_tab=ttk.Frame(self.employee_tree_notebook)
        inactive_tab=ttk.Frame(self.employee_tree_notebook)
        self.employee_tree_notebook.add(active_tab,text='Ativos')
        self.employee_tree_notebook.add(inactive_tab,text='Inativos')
        self.employee_tree_notebook.pack(fill='both',expand=True)
        self._align_tab_actions(actions,self.employee_tree_notebook)
        self.emp_tree=self._create_employee_tree(active_tab,cols,employee_columns)
        self.inactive_emp_tree=self._create_employee_tree(inactive_tab,cols,employee_columns)
        self.emp_tree.bind('<Double-1>',lambda e:self.edit_selected_employee())
        self.inactive_emp_tree.bind('<Double-1>',lambda e:self.edit_selected_employee())
        for tree in (self.emp_tree,self.inactive_emp_tree):
            tree.bind('<Button-3>',self.show_employee_context_menu)
        ttk.Label(content,text='Dê dois cliques ou clique com o botão direito em um colaborador para ver as ações. Os nomes importados de 2026 são mantidos separados quando aparecem com identificações diferentes na planilha.',style='Sub.TLabel').pack(anchor='w',pady=(8,0))
        self._add_tab_action_icons(actions)
        self._tab_reports(actions,[
            ('Dados Cadastrais (PDF)',self.generate_employee_report_dialog)])

    def _build_salaries(self):
        actions,content=self._tab_action_layout(self.salaries_tab)
        bar=ttk.Frame(content)
        bar.pack(fill='x',pady=(0,8))
        ttk.Label(bar,text='Histórico de salários',font=('Segoe UI Semibold',13)).pack(side='left')
        bar=actions
        ttk.Button(
            bar,text='Salário anterior',style='Secondary.TButton',
            command=self.edit_previous_salary).pack(fill='x',pady=(0,6))
        ttk.Button(
            bar,text='Salário / reajustes',style='Highlight.TButton',
            command=self.open_selected_employee_salary_dialog).pack(fill='x',pady=(0,6))
        ttk.Label(
            content,
            text='O salário anterior é digitado manualmente. Cada reajuste salvo cria uma coluna identificada como “Reajuste” e o mês/ano; se já existir reajuste do colaborador nesse mês, o valor é atualizado.',
            style='Sub.TLabel').pack(anchor='w',pady=(0,10))
        columns=('code','name','previous_salary')
        table=ttk.Frame(content)
        table.pack(fill='x')
        self._align_tab_actions(actions,table)
        self.salary_tree=ttk.Treeview(table,columns=columns,show='headings',selectmode='browse',height=8)
        for column,title,width,anchor in (
            ('code','Matrícula',130,'center'),
            ('name','Nome do colaborador',260,'w'),
            ('previous_salary','Salário anterior (R$)',190,'e'),
        ):
            self.salary_tree.heading(column,text=title)
            self.salary_tree.column(column,width=width,anchor=anchor)
        vertical_scroll=ttk.Scrollbar(table,orient='vertical',command=self.salary_tree.yview)
        horizontal_scroll=ttk.Scrollbar(table,orient='horizontal',command=self.salary_tree.xview)
        self.salary_tree.configure(
            yscrollcommand=vertical_scroll.set,
            xscrollcommand=horizontal_scroll.set)
        self.salary_tree.grid(row=0,column=0,sticky='nsew')
        vertical_scroll.grid(row=0,column=1,sticky='ns')
        horizontal_scroll.grid(row=1,column=0,sticky='ew')
        table.rowconfigure(0,weight=1)
        table.columnconfigure(0,weight=1)
        self.salary_tree.bind('<Double-1>',self.on_salary_register_double_click)
        self.salary_tree.bind('<<TreeviewSelect>>',self.on_salary_register_selection)
        self.salary_column_dates={}
        observations=ttk.Frame(content,padding=(0,4))
        observations.pack(fill='x',pady=(8,0))
        observation_controls=ttk.Frame(observations)
        observation_controls.pack(fill='x',pady=(0,8))
        observation_controls.columnconfigure(1,weight=1)
        self.salary_note_employee_label=ttk.Label(
            observation_controls,text='Selecione um colaborador na tabela.')
        self.salary_note_employee_label.grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,6))
        ttk.Label(observation_controls,text='Reajuste:').grid(
            row=1,column=0,sticky='w',padx=(0,6))
        self.salary_note_record_var=tk.StringVar()
        self.salary_note_record_combo=ttk.Combobox(
            observation_controls,textvariable=self.salary_note_record_var,
            state='disabled',width=12)
        self.salary_note_record_combo.grid(row=1,column=1,sticky='ew',padx=(0,12))
        self.salary_note_record_combo.bind(
            '<<ComboboxSelected>>',self.on_salary_note_record_selected)
        ttk.Label(observation_controls,text='Mês/ano (MM/AAAA):').grid(
            row=2,column=0,sticky='w',padx=(0,6),pady=(6,0))
        self.salary_note_date_var=tk.StringVar()
        self.salary_note_date_entry=ttk.Entry(
            observation_controls,textvariable=self.salary_note_date_var,
            state='disabled',width=9)
        self.salary_note_date_entry.grid(row=2,column=1,sticky='ew',padx=(0,12),pady=(6,0))
        self.salary_note_save_button=ttk.Button(
            actions,text='Salvar data do reajuste',
            command=self.save_salary_observation,state='disabled')
        self.salary_note_save_button.pack(fill='x',pady=(0,6))
        ttk.Button(
            actions,text='Excluir coluna',
            command=self.delete_salary_adjustment_column).pack(fill='x',pady=(0,6))

        self._add_tab_action_icons(actions)
        self._tab_reports(actions,[
            ('Salários atualizados (PDF)',self.generate_current_salaries_report)],
            style='CompactReport.TButton')

    def _create_employee_tree(self,parent,columns,headings):
        table=ttk.Frame(parent)
        table.pack(fill='both',expand=True)
        tree=ttk.Treeview(table,columns=columns,show='headings',selectmode='browse')
        for column,title,width in headings:
            tree.heading(column,text=title,anchor='w' if column=='name' else 'center')
            tree.column(column,width=width,anchor='w' if column=='name' else 'center')
        scroll=ttk.Scrollbar(table,orient='horizontal',command=tree.xview)
        tree.configure(xscrollcommand=scroll.set)
        tree.pack(fill='both',expand=True)
        scroll.pack(fill='x')
        tree.tag_configure('inactive',foreground='#64748b')
        return tree

    def show_employee_context_menu(self,event):
        row=event.widget.identify_row(event.y)
        if not row:
            return
        event.widget.selection_set(row)
        self.employee_actions_menu.tk_popup(event.x_root,event.y_root)
        self.employee_actions_menu.grab_release()

    def selected_employee_tree(self):
        if self.employee_tree_notebook.index(self.employee_tree_notebook.select())==1:
            return self.inactive_emp_tree
        return self.emp_tree

    def autosize_treeview_columns(self,tree,min_width=70,max_width=420,padding=24,bold=False):
        style=ttk.Style(tree)
        heading_font=tkfont.Font(font=style.lookup('Treeview.Heading','font'))
        cell_font=tkfont.Font(font=style.lookup('Treeview','font'))
        if bold:
            cell_font.configure(weight='bold')
        for column in tree['columns']:
            heading=tree.heading(column,'text')
            width=max(min_width,heading_font.measure(heading)+padding)
            for item in tree.get_children(''):
                value=tree.set(item,column)
                width=max(width,cell_font.measure(str(value))+padding)
                if width>=max_width:
                    width=max_width
                    break
            tree.column(column,width=min(max_width,width),stretch=False)

    def sync_all_loans(self):
        with connect() as con:
            months=set()
            for loan in con.execute('SELECT * FROM employee_loans').fetchall():
                months|=self.loan_months(con,loan)
            self.sync_loan_payrolls(con,months)

    def refresh_all(self):
        self.sync_all_loans()
        self.load_dashboard();self.load_employees();self.load_salary_register();self.update_years();self.load_payroll()

    def update_years(self):
        with connect() as con: years=[str(r[0]) for r in con.execute('SELECT DISTINCT year FROM payrolls ORDER BY year DESC')]
        current_year=str(self.current_payroll_year)
        if current_year not in years:
            years.append(current_year)
        years.sort(key=int,reverse=True)
        self.pay_year['values']=years
        if self.pay_year.get() not in years: self.pay_year.set(current_year)
        self.update_months()

    def update_months(self):
        months=MONTHS
        selected=self.pay_month.get()
        self.pay_month['values']=months
        if selected not in months:
            self.pay_month.set(MONTHS[self.current_payroll_month-1])

    def on_year_selected(self,event=None):
        self.update_months()
        self.load_payroll()

    def on_month_selected(self,event=None):
        self.load_payroll()

    def navigate_payroll_month(self,offset):
        try:
            year=int(self.pay_year.get())
            month=MONTHS.index(self.pay_month.get())
        except (ValueError,tk.TclError):
            messagebox.showerror('Competência inválida','Selecione um ano e um mês válidos.',parent=self)
            return
        target_year=year
        target_month=month+offset
        if target_month<0:
            target_year-=1
            target_month=len(MONTHS)-1
        elif target_month>=len(MONTHS):
            target_year+=1
            target_month=0
        if str(target_year) not in self.pay_year['values']:
            messagebox.showinfo(
                'Sem folha nesse ano',
                f'Não há folhas cadastradas para {target_year}.',
                parent=self)
            return
        self.pay_year.set(str(target_year))
        self.pay_month.set(MONTHS[target_month])
        self.load_payroll()

    def load_dashboard(self):
        try:
            year=int(self.pay_year.get())
            month=MONTHS.index(self.pay_month.get())+1
        except (AttributeError,ValueError,tk.TclError):
            year=self.current_payroll_year
            month=self.current_payroll_month
        with connect() as con:
            active=con.execute('''SELECT COUNT(DISTINCT ae.employee_id)
                FROM annual_employees ae JOIN employees e ON e.id=ae.employee_id
                WHERE ae.year=? AND ae.active=1 AND e.active=1''',(year,)).fetchone()[0]
            review=con.execute(
                "SELECT COUNT(*) FROM payrolls WHERE year=? AND status='Em revisão'",(year,)).fetchone()[0]
            monthly=con.execute('''SELECT p.month,COALESCE(SUM(i.total),0) net,
                COUNT(DISTINCT i.employee_id) people
                FROM payrolls p LEFT JOIN payroll_items i ON i.payroll_id=p.id
                WHERE p.year=? GROUP BY p.month ORDER BY p.month''',(year,)).fetchall()
            status_rows=con.execute('''SELECT p.month,p.status,COALESCE(SUM(i.total),0) net
                FROM payrolls p LEFT JOIN payroll_items i ON i.payroll_id=p.id
                WHERE p.year=? GROUP BY p.id ORDER BY p.month''',(year,)).fetchall()
            selected=con.execute('''SELECT p.status,COALESCE(SUM(i.total),0) net,
                    COUNT(DISTINCT i.employee_id) people
                FROM payrolls p LEFT JOIN payroll_items i ON i.payroll_id=p.id
                WHERE p.year=? AND p.month=? GROUP BY p.id,p.status''',(year,month)).fetchone()
        monthly_by_month={
            row['month']:{'net':float(row['net'] or 0),'people':int(row['people'] or 0)}
            for row in monthly
        }
        self.dashboard_chart_data=[
            {'month':m,'net':monthly_by_month.get(m,{}).get('net',0.0),
             'people':monthly_by_month.get(m,{}).get('people',0)}
            for m in range(1,13)
        ]
        self.dashboard_selected_month=month
        selected_net=float(selected['net'] or 0) if selected else None
        selected_people=int(selected['people'] or 0) if selected else 0
        self.dashboard_period.configure(text=f'{MONTHS[month-1]} / {year}')
        card_values=[
            str(active),
            brl(selected_net) if selected_net is not None else '—',
            str(selected_people),
            str(review),
        ]
        card_hints=[
            f'Ativos no cadastro anual de {year}',
            f'{MONTHS[month-1]} / {year} • {selected["status"] if selected else "sem folha criada"}',
            'Com lançamento na competência selecionada',
            f'Competências em revisão no ano de {year}',
        ]
        for label,value in zip(self.card_values,card_values):
            label.configure(text=value,font=('Segoe UI Semibold',16 if value.startswith('R$') else 21))
        for label,hint in zip(self.card_hints,card_hints):
            label.configure(text=hint)
        closed_rows=[r for r in status_rows if r['status']=='Fechada']
        pending_rows=[r for r in status_rows if r['status']!='Fechada']
        self.closed_title.configure(text=f'Total anual das folhas fechadas — {year}')
        self.closed_total.configure(text=brl(sum(float(r['net'] or 0) for r in closed_rows)),font=('Segoe UI Semibold',16))
        self.closed_hint.configure(text=f'{len(closed_rows)} de {len(status_rows)} folhas fechadas no ano')
        self.review_title.configure(text=f'Folhas em revisão — falta fechar ({year})')
        self.review_total.configure(text=f'{len(pending_rows)} folha(s) • {brl(sum(float(r["net"] or 0) for r in pending_rows))}' if pending_rows else 'Todas as folhas estão fechadas')
        for item in self.review_tree.get_children():
            self.review_tree.delete(item)
        for r in pending_rows:
            self.review_tree.insert('','end',values=(f'{MONTHS[r["month"]-1]} / {year}','Em revisão',brl(r['net'])))
        for label,title in zip(self.dashboard_chart_titles,(
            f'Total líquido por mês — {year}',
            f'Colaboradores lançados por mês — {year}',
        )):
            label.configure(text=title)
        for label in self.dashboard_chart_subtitles:
            label.configure(text=f'Comparativo mensal • {year}')
        for canvas,kind in self.dashboard_charts:
            self._draw_dashboard_chart(canvas,kind)

    def _draw_dashboard_chart(self,canvas,kind):
        canvas.delete('all')
        width=canvas.winfo_width()
        height=canvas.winfo_height()
        if width<180 or height<150:
            return
        data=self.dashboard_chart_data
        if not data:
            canvas.create_text(width/2,height/2,text='Sem dados para exibir',fill=MUTED,font=('Segoe UI',9))
            return
        left,right,top,bottom=68,width-18,22,height-43
        plot_width=right-left
        plot_height=bottom-top
        values=[float(row[kind] or 0) for row in data]
        slot=plot_width/12
        selected_month=getattr(self,'dashboard_selected_month',0)
        if kind=='net':
            min_value=min(0,min(values))
            max_value=max(0,max(values))
            if min_value==max_value==0:
                max_value=1
            max_value+=max(1,(max_value-min_value)*0.08)
            span=max_value-min_value
            for step in range(5):
                value=max_value-(max_value-min_value)*step/4
                y=top+plot_height*step/4
                canvas.create_line(left,y,right,y,fill='#e8eef5',dash=(2,3))
                canvas.create_text(
                    left-8,y,text=self._dashboard_money_axis_label(value),
                    anchor='e',fill=MUTED,font=('Segoe UI',8))
            zero_y=top+plot_height*(max_value/span)
            canvas.create_line(left,zero_y,right,zero_y,fill='#9aa9ba',width=1)
            bar_width=max(5,min(32,slot*0.58))
            for index,(row,value) in enumerate(zip(data,values)):
                x=left+slot*(index+0.5)
                y=top+plot_height*(max_value-value)/span
                color=BLUE if row['month']==selected_month else ('#dbe5ef' if value==0 else '#60a5fa')
                canvas.create_rectangle(
                    x-bar_width/2,min(y,zero_y),x+bar_width/2,max(y,zero_y),
                    fill=color,outline='')
                if value and slot>=33:
                    canvas.create_text(
                        x,max(top+8,min(y,zero_y)-9),
                        text=self._dashboard_compact_number(value),
                        fill=NAVY,font=('Segoe UI Semibold',7))
                canvas.create_text(
                    x,bottom+19,text=MONTHS[row['month']-1][:3],
                    fill=BLUE if row['month']==selected_month else MUTED,
                    font=('Segoe UI Semibold' if row['month']==selected_month else 'Segoe UI',8))
        else:
            maximum=max(0,max(values))
            tick=max(1,math.ceil(maximum/4))
            scale_top=max(tick*4,1)
            points=[]
            for index,(row,value) in enumerate(zip(data,values)):
                x=left+slot*(index+0.5)
                y=bottom-plot_height*value/scale_top
                points.append((x,y,row['month'],int(value)))
            if points:
                area=[left,bottom]
                for x,y,_,_ in points:
                    area.extend((x,y))
                area.extend((right,bottom))
                canvas.create_polygon(*area,fill='#eff6ff',outline='')
            for step in range(5):
                value=scale_top-step*tick
                y=top+plot_height*step/4
                canvas.create_line(left,y,right,y,fill='#e8eef5',dash=(2,3))
                canvas.create_text(left-8,y,text=f'{value:d}',anchor='e',fill=MUTED,font=('Segoe UI',8))
            for x,_,point_month,_ in points:
                canvas.create_text(
                    x,bottom+19,text=MONTHS[point_month-1][:3],
                    fill=BLUE if point_month==selected_month else MUTED,
                    font=('Segoe UI Semibold' if point_month==selected_month else 'Segoe UI',8))
            if len(points)>=2:
                line_points=[coordinate for x,y,_,_ in points for coordinate in (x,y)]
                canvas.create_line(*line_points,fill='#0f766e',width=3,smooth=True)
            for x,y,point_month,value in points:
                dot_color=BLUE if point_month==selected_month else '#0f766e'
                canvas.create_oval(x-5,y-5,x+5,y+5,fill=WHITE,outline=dot_color,width=2)
                if value:
                    canvas.create_text(
                        x,max(top+9,y-13),text=str(value),
                        fill=NAVY,font=('Segoe UI Semibold',8))

    @staticmethod
    def _dashboard_compact_number(value):
        value=float(value or 0)
        absolute=abs(value)
        if absolute>=1_000_000:
            return f'{value/1_000_000:.1f}mi'.replace('.',',')
        if absolute>=10_000:
            return f'{value/1_000:.0f}k'
        if absolute>=1_000:
            return f'{value/1_000:.1f}k'.replace('.',',')
        return f'{value:.0f}'

    def _dashboard_money_axis_label(self,value):
        return f'R$ {self._dashboard_compact_number(value)}'

    def load_employees(self):
        for tree in (self.emp_tree,self.inactive_emp_tree):
            for item in tree.get_children():
                tree.delete(item)
        with connect() as con:
            rows=con.execute('SELECT * FROM employees ORDER BY active DESC,name COLLATE NOCASE').fetchall()
            salaries={
                row['id']:employee_salary_for_period(con,row['id'],datetime.now().year,datetime.now().month)
                for row in rows
            }
        counts={1:0,0:0}
        for r in rows:
            active=bool(r['active'])
            tree=self.emp_tree if active else self.inactive_emp_tree
            counts[int(active)]+=1
            tree.insert(
                '','end',iid=str(r['id']),
                values=(
                    r['code'] or '',r['name'],r['role'],brl(salaries[r['id']]),r['sector'],r['email'],
                    format_phone(r['phone']),r['pix'] or '',
                    r['bank'] or '',r['bank_agency'] or '',r['bank_account'] or '',
                    ' '.join(part for part in (r['address'] or '',r['address_number'] or '') if part),
                    r['bairro'] or '',r['cep'] or '',
                    r['city'] or '',r['state'] or '',r['ctps'] or '',
                    employee_date_for_form(r['birth_date']),r['cpf'] or '',
                    employee_date_for_form(r['admission_date']),employee_date_for_form(r['dismissal_date']),
                    'Ativo' if active else 'Inativo'),
                tags=() if active else ('inactive',))
        self.employee_tree_notebook.tab(0,text=f'Ativos ({counts[1]})')
        self.employee_tree_notebook.tab(1,text=f'Inativos ({counts[0]})')
        self.autosize_treeview_columns(self.emp_tree)
        self.autosize_treeview_columns(self.inactive_emp_tree)

    def load_salary_register(self):
        if not hasattr(self,'salary_tree'):
            return
        for item in self.salary_tree.get_children():
            self.salary_tree.delete(item)
        with connect() as con:
            employees=con.execute(
                '''SELECT e.id,e.code,e.name,p.amount previous_salary
                FROM employees e
                LEFT JOIN employee_previous_salary_controls p ON p.employee_id=e.id
                WHERE e.active=1 ORDER BY e.name COLLATE NOCASE''').fetchall()
            updates=con.execute('''SELECT u.employee_id,u.updated_on,u.amount
                FROM employee_salary_register_updates u
                JOIN employees e ON e.id=u.employee_id
                WHERE e.active=1 ORDER BY u.updated_on,u.employee_id''').fetchall()
        dates=sorted({row['updated_on'] for row in updates})
        update_amounts={
            (row['employee_id'],row['updated_on']):row['amount'] for row in updates}
        self.salary_update_dates={}
        for row in updates:
            self.salary_update_dates.setdefault(row['employee_id'],[]).append(
                row['updated_on'])
        update_columns=[f'update_{date.replace("-","")}' for date in dates]
        pct_columns=[f'pct_{date.replace("-","")}' for date in dates]
        columns=('code','name','previous_salary')+tuple(
            column for pair in zip(update_columns,pct_columns) for column in pair)
        self.salary_column_dates=dict(zip(update_columns,dates))
        self.salary_tree['columns']=columns
        for column,title,width,anchor in (
            ('code','Matrícula',130,'center'),
            ('name','Nome do colaborador',260,'w'),
            ('previous_salary','Salário anterior (R$)',190,'e'),
        ):
            self.salary_tree.heading(column,text=title)
            self.salary_tree.column(column,width=width,anchor=anchor)
        for date,column,pct_column in zip(dates,update_columns,pct_columns):
            date_label=salary_register_period_label(date)
            self.salary_tree.heading(column,text=f'Reajuste - {date_label}')
            self.salary_tree.column(column,width=150,anchor='e')
            self.salary_tree.heading(pct_column,text='%')
            self.salary_tree.column(pct_column,width=90,anchor='center')
        for employee in employees:
            values=[
                employee['code'] or '—',
                employee['name'],
                brl(employee['previous_salary'])
                if employee['previous_salary'] is not None else '',
            ]
            base=employee['previous_salary']
            for date in dates:
                amount=update_amounts.get((employee['id'],date))
                if amount is None:
                    values.extend(['',''])
                    continue
                pct=(f'{(amount-base)/base*100:+.2f}%'.replace('.',',')
                     if base else '')
                values.extend([brl(amount),pct])
                base=amount
            self.salary_tree.insert(
                '','end',iid=str(employee['id']),values=tuple(values))
        self.salary_tree.configure(height=max(8,min(len(employees),22)))
        self.autosize_treeview_columns(self.salary_tree,max_width=220)
        self.refresh_salary_observations()

    def delete_salary_adjustment_column(self):
        dates=sorted(self.salary_column_dates.values())
        if not dates:
            messagebox.showinfo('Sem reajustes','Não há colunas de reajuste para excluir.',parent=self)
            return
        dialog=tk.Toplevel(self)
        dialog.title('Excluir coluna de reajuste')
        dialog.configure(bg=BG)
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False,False)
        body=ttk.Frame(dialog,padding=20)
        body.pack(fill='both',expand=True)
        ttk.Label(body,text='Escolha a coluna de reajuste a excluir:').pack(anchor='w')
        labels={salary_register_period_label(date)+(
            f' ({sum(d[:7]==date[:7] for d in dates[:i+1])})'
            if sum(d[:7]==date[:7] for d in dates)>1 else ''):date
            for i,date in enumerate(dates)}
        choice=tk.StringVar(value=list(labels)[-1])
        ttk.Combobox(body,textvariable=choice,values=list(labels),state='readonly',
                     width=20).pack(anchor='w',pady=8)
        ttk.Label(body,text='O reajuste será removido de todos os colaboradores nessa coluna.',
                  style='Sub.TLabel').pack(anchor='w')

        def confirm():
            date=labels[choice.get()]
            if not messagebox.askyesno(
                'Confirmar exclusão',
                f'Excluir a coluna {choice.get()} de todos os colaboradores?',parent=dialog):
                return
            with connect() as con:
                con.execute('DELETE FROM employee_salary_register_updates WHERE updated_on=?',(date,))
                con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',(
                    'Exclusão de coluna de reajuste',f'Coluna {choice.get()} removida'))
            dialog.destroy()
            self.load_salary_register()

        buttons=ttk.Frame(body)
        buttons.pack(fill='x',pady=(12,0))
        ttk.Button(buttons,text='Cancelar',command=dialog.destroy).pack(side='right')
        ttk.Button(buttons,text='Excluir coluna',style='Accent.TButton',
                   command=confirm).pack(side='right',padx=(0,8))

    def delete_selected_salary_adjustment(self):
        selection=self.salary_tree.selection()
        updated_on=getattr(self,'salary_selected_update_date',None)
        if not selection or updated_on not in getattr(self,'salary_note_dates',()):
            messagebox.showinfo('Selecione','Selecione um colaborador e um reajuste.',parent=self)
            return
        employee_id=int(selection[0])
        name=self.salary_tree.set(selection[0],'name')
        label=salary_register_period_label(updated_on)
        if not messagebox.askyesno(
            'Excluir reajuste',f'Excluir o reajuste de {label} de {name}?',parent=self):
            return
        with connect() as con:
            con.execute('DELETE FROM employee_salary_register_updates WHERE employee_id=? AND updated_on=?',
                        (employee_id,updated_on))
            con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',(
                'Exclusão de reajuste da tabela',f'{name}: {label}'))
        self.load_salary_register()
        if self.salary_tree.exists(str(employee_id)):
            self.salary_tree.selection_set(str(employee_id))

    def on_salary_register_selection(self,event=None):
        self.refresh_salary_observations()

    def refresh_salary_observations(self):
        self.salary_note_date_var.set('')
        self.salary_note_record_var.set('')
        self.salary_note_record_combo['values']=()
        self.salary_note_date_entry.configure(state='disabled')
        self.salary_note_record_combo.configure(state='disabled')
        self.salary_note_save_button.configure(state='disabled')
        selection=self.salary_tree.selection()
        if not selection:
            self.salary_note_employee_label.configure(
                text='Selecione um colaborador na tabela.')
            return
        employee_id=int(selection[0])
        employee_name=self.salary_tree.set(selection[0],'name')
        dates=self.salary_update_dates.get(employee_id,[])
        self.salary_note_dates=set(dates)
        self.salary_note_employee_label.configure(text=employee_name)
        if not dates:
            self.salary_note_employee_label.configure(
                text=f'{employee_name} — nenhum reajuste registrado.')
            return
        updated_on=dates[-1]
        labels=[]
        self.salary_note_record_dates={}
        period_counts={}
        for date in reversed(dates):
            label=salary_register_period_label(date)
            period_counts[label]=period_counts.get(label,0)+1
            if period_counts[label]>1:
                label=f'{label} ({period_counts[label]})'
            labels.append(label)
            self.salary_note_record_dates[label]=date
        self.salary_note_record_combo['values']=labels
        self.salary_note_record_combo.configure(state='readonly')
        self.salary_note_record_var.set(
            next(label for label,date in self.salary_note_record_dates.items()
                 if date==updated_on))
        self.salary_note_date_var.set(
            salary_register_period_label(updated_on))
        self.salary_note_date_entry.configure(state='normal')
        self.load_salary_observation(updated_on)

    def on_salary_note_record_selected(self,event=None):
        updated_on=self.salary_note_record_dates.get(
            self.salary_note_record_var.get())
        if updated_on:
            self.load_salary_observation(updated_on)

    def load_salary_observation(self,updated_on=None):
        selection=self.salary_tree.selection()
        if updated_on is None:
            updated_on=self.salary_note_record_dates.get(
                self.salary_note_record_var.get())
        if not selection or updated_on not in self.salary_note_dates:
            return
        self.salary_selected_update_date=updated_on
        self.salary_note_date_var.set(
            salary_register_period_label(updated_on))
        self.salary_note_save_button.configure(state='normal')

    def save_salary_observation(self):
        selection=self.salary_tree.selection()
        if not selection:
            return
        try:
            new_updated_on=normalize_salary_register_period(
                self.salary_note_date_var.get())
        except ValueError as ex:
            messagebox.showerror('Data inválida',str(ex),parent=self)
            return
        employee_id=int(selection[0])
        selected_date=self.salary_selected_update_date
        if new_updated_on[:7]!=selected_date[:7]:
            with connect() as con:
                collisions=con.execute('''SELECT updated_on
                    FROM employee_salary_register_updates
                    WHERE employee_id=? AND updated_on LIKE ? AND updated_on<>?''',
                    (employee_id,f'{new_updated_on[:7]}-%',selected_date)).fetchall()
            if collisions:
                messagebox.showerror(
                    'Data já cadastrada',
                    'Este colaborador já possui um reajuste nesse mês/ano. '
                    'Escolha outro período para evitar substituir o registro.',
                    parent=self)
                return
        if new_updated_on[:7]==selected_date[:7]:
            new_updated_on=selected_date
        try:
            with connect() as con:
                if new_updated_on!=selected_date:
                    con.execute('''UPDATE employee_salary_register_updates
                        SET updated_on=?
                        WHERE employee_id=? AND updated_on=?''',
                        (new_updated_on,employee_id,selected_date))
        except sqlite3.Error as ex:
            messagebox.showerror(
                'Erro ao salvar data do reajuste',str(ex),parent=self)
            return
        self.load_salary_register()
        self.salary_tree.selection_set(str(employee_id))
        self.salary_tree.focus(str(employee_id))
        self.salary_note_employee_label.configure(
            text=f'{self.salary_tree.set(str(employee_id),"name")} — data salva.')

    def on_salary_register_double_click(self,event):
        if event.widget.identify_column(event.x)=='#3':
            self.edit_previous_salary()

    def edit_previous_salary(self):
        selection=self.salary_tree.selection()
        if not selection:
            messagebox.showinfo(
                'Selecione','Selecione um colaborador para digitar o valor de controle.',
                parent=self)
            return
        employee_id=int(selection[0])
        employee=self.salary_tree.item(selection[0],'values')
        initial_previous_salary=employee[2]
        dialog=tk.Toplevel(self)
        dialog.title('Salário anterior')
        dialog.configure(bg=BG)
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False,False)
        body=ttk.Frame(dialog,padding=20)
        body.pack(fill='both',expand=True)
        ttk.Label(
            body,text=f'Salário anterior — {employee[1]}',
            font=('Segoe UI Semibold',13)).pack(anchor='w',pady=(0,10))
        ttk.Label(body,text='Salário anterior (R$)').pack(anchor='w')
        previous_salary_var=tk.StringVar(value=initial_previous_salary)
        previous_salary_entry=ttk.Entry(
            body,textvariable=previous_salary_var,width=24)
        previous_salary_entry.pack(fill='x',pady=(5,10))
        buttons=ttk.Frame(body)
        buttons.pack(fill='x')
        ttk.Button(buttons,text='Cancelar',command=dialog.destroy).pack(side='right')

        def save_control():
            raw_previous_salary=previous_salary_var.get().strip()
            try:
                previous_salary=(
                    round(money(raw_previous_salary),2)
                    if raw_previous_salary else None)
            except ValueError as ex:
                messagebox.showerror('Valor inválido',str(ex),parent=dialog)
                return
            if previous_salary is not None and (
                not math.isfinite(previous_salary) or previous_salary<0):
                messagebox.showerror(
                    'Valor inválido','O salário anterior não pode ser negativo.',
                    parent=dialog)
                return
            try:
                with connect() as con:
                    changed_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    if previous_salary is None:
                        con.execute(
                            'DELETE FROM employee_previous_salary_controls WHERE employee_id=?',
                            (employee_id,))
                    else:
                        con.execute('''INSERT INTO employee_previous_salary_controls(
                            employee_id,amount,updated_at) VALUES(?,?,?)
                            ON CONFLICT(employee_id) DO UPDATE SET
                            amount=excluded.amount,updated_at=excluded.updated_at''',
                            (employee_id,previous_salary,changed_at))
                    con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',(
                        'Atualização do salário anterior para controle',
                        f'{employee[1]}: salário anterior '
                        f'{brl(previous_salary) if previous_salary is not None else "vazio"}'))
            except sqlite3.Error as ex:
                messagebox.showerror(
                    'Erro ao salvar controle',str(ex),parent=dialog)
                return
            dialog.destroy()
            self.load_salary_register()

        ttk.Button(
            buttons,text='Salvar salário anterior',style='Accent.TButton',
            command=save_control).pack(side='right',padx=(0,8))
        previous_salary_entry.bind('<Return>',lambda event:save_control())
        previous_salary_entry.bind('<Escape>',lambda event:dialog.destroy())
        previous_salary_entry.focus_set()

    def open_selected_employee_salary_dialog(self):
        selection=self.salary_tree.selection()
        if not selection:
            messagebox.showinfo(
                'Selecione',
                'Selecione um colaborador para abrir salário e reajustes da folha.',
                parent=self)
            return
        self.employee_salary_dialog(int(selection[0]))

    def save_accounting_pdf_values(self,year,month,entries):
        if not entries:
            raise ValueError('Selecione pelo menos um funcionário.')
        with connect() as con:
            payroll=con.execute(
                'SELECT * FROM payrolls WHERE year=? AND month=?',(year,month)).fetchone()
            if payroll is None or payroll['status']=='Fechada':
                raise ValueError('Selecione uma folha existente e aberta antes de importar.')
            seen=set()
            for entry in entries:
                employee_id=entry['employee_id']
                amount=entry['amount']
                if employee_id in seen or not math.isfinite(amount) or amount<0:
                    raise ValueError('A seleção contém valores inválidos ou funcionários repetidos.')
                seen.add(employee_id)
                item=con.execute('''SELECT i.*,e.name FROM payroll_items i
                    JOIN employees e ON e.id=i.employee_id
                    WHERE i.payroll_id=? AND i.employee_id=?''',(payroll['id'],employee_id)).fetchone()
                if item is None:
                    raise ValueError('Funcionário sem lançamento nesta folha.')
                if item['salary']!=entry['previous_salary']:
                    raise ValueError('O salário foi alterado após a conferência. Reabra a importação.')
                values=dict(item)
                values['salary']=round(amount,2)
                con.execute('UPDATE payroll_items SET salary=?,total=?,source=? WHERE id=?',(
                    values['salary'],calc_total(values),'PDF contábil',item['id']))
                con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',(
                    'Importação local de PDF contábil',
                    f'{item["name"]} - {month:02d}/{year}: salário {brl(item["salary"])} para {brl(amount)}'))
        return len(entries)

    def import_accounting_pdf_dialog(self):
        period=self.selected_payroll_period()
        if period is None:
            return
        year,month=period
        with connect() as con:
            payroll=con.execute(
                'SELECT * FROM payrolls WHERE year=? AND month=?',period).fetchone()
            if payroll is None or payroll['status']=='Fechada':
                messagebox.showwarning('Folha indisponível','Selecione uma folha existente e aberta.',parent=self)
                return
            items=con.execute('''SELECT i.*,e.name FROM payroll_items i
                JOIN employees e ON e.id=i.employee_id WHERE i.payroll_id=?''',(payroll['id'],)).fetchall()
        path=filedialog.askopenfilename(
            parent=self,title='Selecionar PDF da contabilidade',
            initialdir=ACCOUNTING_PDF_DIR,filetypes=[('PDF','*.pdf')])
        if not path:
            return
        try:
            entries,problems=read_payroll_pdf(
                path,[dict(id=item['employee_id'],name=item['name']) for item in items],year,month)
        except Exception as ex:
            messagebox.showerror('Não foi possível ler o PDF',str(ex),parent=self)
            return
        by_employee={item['employee_id']:item for item in items}
        form=tk.Toplevel(self)
        form.title(f'Conferir importação — {MONTHS[month-1]}/{year}')
        form.transient(self)
        form.grab_set()
        form.geometry('900x550')
        body=ttk.Frame(form,padding=16)
        body.pack(fill='both',expand=True)
        ttk.Label(body,text='Todos estão incluídos. Clique na coluna Importar para deixar alguém de fora.',
            font=('Segoe UI Semibold',11)).pack(anchor='w')
        ttk.Label(body,text='O líquido do PDF substituirá SALÁRIO. Os demais valores e descontos serão mantidos '
            'e aplicados novamente no cálculo. Nenhum desconto é importado do PDF. '
            'Confira para evitar descontos em duplicidade.',
            wraplength=840,style='Sub.TLabel').pack(anchor='w',pady=8)
        table_frame=ttk.Frame(body)
        table_frame.pack(fill='both',expand=True)
        table=ttk.Treeview(table_frame,columns=('include','name','new'),show='headings',selectmode='none')
        table.tag_configure('included',background='#e6f6ec',foreground='#14532d')
        table.tag_configure('excluded',background='#fee2e2',foreground='#991b1b')
        for key,title,width in (('include','Importar',90),('name','Funcionário',440),
                ('new','Líquido do PDF → Salário',260)):
            table.heading(key,text=title)
            table.column(key,width=width,anchor='w' if key=='name' else 'center')
        scroll=ttk.Scrollbar(table_frame,orient='vertical',command=table.yview)
        table.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y')
        table.pack(fill='both',expand=True)
        choices={}
        for entry in entries:
            item=by_employee[entry['employee_id']]
            entry['previous_salary']=item['salary']
            key=str(entry['employee_id'])
            choices[key]=entry
            table.insert('','end',iid=key,values=(
                'Sim',entry['name'],brl(entry['amount'])),tags=('included',))

        def toggle_import(event):
            key=table.identify_row(event.y)
            if key and table.identify_column(event.x)=='#1':
                include=table.set(key,'include')!='Sim'
                table.set(key,'include','Sim' if include else 'Não')
                table.item(key,tags=('included' if include else 'excluded',))

        table.bind('<Button-1>',toggle_import)
        if problems:
            ttk.Label(body,text='\n'.join(problems),wraplength=840,style='Sub.TLabel').pack(anchor='w',pady=6)
        buttons=ttk.Frame(body)
        buttons.pack(fill='x',pady=(8,0))

        def save():
            selected=[entry for key,entry in choices.items() if table.set(key,'include')=='Sim']
            if not selected:
                messagebox.showwarning('Sem seleção','Selecione os funcionários que deseja importar.',parent=form)
                return
            if not messagebox.askyesno('Confirmar importação',
                    f'Alterar a coluna Salário de {len(selected)} funcionários em {MONTHS[month-1]}/{year}?\n\n'
                    'Os descontos existentes continuarão sendo aplicados. Confirme somente após conferir os valores.',
                    parent=form):
                return
            try:
                saved=self.save_accounting_pdf_values(year,month,selected)
            except (ValueError,sqlite3.Error) as ex:
                messagebox.showerror('Importação não realizada',str(ex),parent=form)
                return
            form.destroy()
            self.load_payroll()
            messagebox.showinfo('Importação concluída',f'{saved} salários atualizados.',parent=self)

        ttk.Button(buttons,text='Cancelar',command=form.destroy).pack(side='right')
        ttk.Button(buttons,text='Importar incluídos',command=save,style='Accent.TButton').pack(side='right',padx=8)
        self.wait_window(form)

    def load_payroll(self):
        if not hasattr(self,'pay_tree'): return
        for i in self.pay_tree.get_children(): self.pay_tree.delete(i)
        self._schedule_payroll_note_markers()
        try: year=int(self.pay_year.get())
        except (ValueError,tk.TclError): year=self.current_payroll_year
        month=MONTHS.index(self.pay_month.get())+1 if self.pay_month.get() in MONTHS else self.current_payroll_month
        all_columns=self.pay_tree['columns']
        self.pay_tree['displaycolumns']=list(all_columns)
        with connect() as con:
            current=con.execute('SELECT * FROM payrolls WHERE year=? AND month=?',(year,month)).fetchone()
            if current:
                sync_payroll_employees(con,current)
            self.apply_loan_installments(con,year,month)
            p=con.execute('SELECT * FROM payrolls WHERE year=? AND month=?',(year,month)).fetchone()
            if not p:
                self.autosize_treeview_columns(self.pay_tree)
                self.pay_tree.column('note_marker',width=26)
                self.update_payroll_lock_controls(None)
                self.pay_summary.config(text=f'{MONTHS[month-1]} de {year}: não há folha criada.')
                self.pay_note.config(text='Não há folha cadastrada para esta competência.')
                self._show_payroll_item_notes([])
                self.load_dashboard()
                return
            rows=con.execute('''SELECT i.*,e.name FROM payroll_items i JOIN employees e ON e.id=i.employee_id WHERE i.payroll_id=? ORDER BY e.name COLLATE NOCASE''',(p['id'],)).fetchall()
            installment_labels={
                r['id']:loan_installment_label(
                    con,r['employee_id'],year,month,r['loan'],r['loan_override'],r['loan_manual'])
                for r in rows
            }
        self.update_payroll_lock_controls(p['status'])
        self.load_dashboard()
        total=0
        is_closed=p['status']=='Fechada'
        for r in rows:
            total+=r['total']
            has_note=bool(r['notes'] and r['notes'].strip())
            tag=('launch_full' if is_closed else 'launch_partial')
            if has_note:
                tag += '_note'
            self.pay_tree.insert('','end',iid=str(r['id']),values=(
                r['name'],'●' if has_note else '',
                *[brl(v) if v else '–' for v in (
                    r['salary'],r['pf'],r['overtime'],r['vacation'],
                    r['thirteenth'],r['marmitex'],r['advances'],
                    r['pharmacy'],r['loan'] or 0)],
                installment_labels[r['id']],
                brl(r['total']) if r['total'] else '–'),tags=(tag,))
        self._show_payroll_item_notes(rows)
        self.autosize_treeview_columns(self.pay_tree,bold=True)
        self.pay_tree.column('note_marker',width=26)
        self.pay_summary.config(text=f'{MONTHS[month-1]} / {year}  •  {len(rows)} colaboradores  •  Total líquido: {brl(total)}  •  {p["status"]}')
        self.pay_note.config(text=f'Observações da folha: {p["notes"] or "—"} | Valores: créditos em verde, débitos em vermelho. Fundo: amarelo = revisão, verde = fechada, laranja / ● vermelha = observações.')

    def update_payroll_lock_controls(self,status):
        closed=status=='Fechada'
        state='disabled' if closed or status is None else 'normal'
        for button in self.payroll_edit_buttons:
            button.configure(state=state)
        if status is not None:
            self.payroll_status_button.configure(
                text='Reabrir folha' if closed else 'Fechar folha',
                style='ReopenPayroll.TButton' if closed else 'ClosePayroll.TButton')
        else:
            self.payroll_status_button.configure(text='Fechar folha',style='ClosePayroll.TButton')
            self.payroll_status_button.configure(state='disabled')
            return
        self.payroll_status_button.configure(state='normal')

    def payroll_is_closed(self,year,month):
        with connect() as con:
            row=con.execute('SELECT status FROM payrolls WHERE year=? AND month=?',(year,month)).fetchone()
        return row is not None and row['status']=='Fechada'

    def save_payroll_deductions_batch(self,year,month,entries):
        if not 1900<=year<=9999 or not 1<=month<=12:
            raise ValueError('Informe uma competência válida.')
        values=[]
        seen=set()
        fields=('marmitex','pharmacy')
        with connect() as con:
            employees={row['id']:row['name'] for row in con.execute(
                'SELECT id,name FROM employees WHERE active=1').fetchall()}
            for employee_id,marmitex,pharmacy in entries:
                if employee_id not in employees or employee_id in seen:
                    raise ValueError('A lista contém colaborador inativo, inexistente ou repetido.')
                seen.add(employee_id)
                employee_values={}
                for field,value in zip(fields,(marmitex,pharmacy)):
                    if value is None or str(value).strip()=='':
                        continue
                    try:
                        amount=money(value)
                    except ValueError as ex:
                        label='Marmitex' if field=='marmitex' else 'Farmácia'
                        raise ValueError(f'{employees[employee_id]} — {label}: informe um valor válido.') from ex
                    if not math.isfinite(amount) or amount<0:
                        label='Marmitex' if field=='marmitex' else 'Farmácia'
                        raise ValueError(f'{employees[employee_id]} — {label}: o valor não pode ser negativo.')
                    employee_values[field]=round(amount,2)
                if employee_values:
                    values.append((employee_id,employees[employee_id],employee_values))
            if not values:
                raise ValueError('Informe Marmitex ou Farmácia para pelo menos um colaborador.')

            self.apply_loan_installments(con,year,month)
            payroll=con.execute(
                'SELECT * FROM payrolls WHERE year=? AND month=?',(year,month)).fetchone()
            if payroll and payroll['status']=='Fechada':
                raise ValueError(
                    f'A folha de {MONTHS[month-1]}/{year} está fechada. Reabra-a antes de lançar o lote.')
            if not payroll:
                payroll_id=con.execute(
                    "INSERT INTO payrolls(year,month,status,notes) VALUES(?,?,'Em revisão','')",
                    (year,month)).lastrowid
                payroll=con.execute('SELECT * FROM payrolls WHERE id=?',(payroll_id,)).fetchone()
            if payroll['loan_only']:
                con.execute(
                    "UPDATE payrolls SET loan_only=0 WHERE id=?",(payroll['id'],))
                payroll=dict(payroll)
                payroll['loan_only']=0
            sync_payroll_employees(con,payroll)

            total_marmitex=0.0
            total_pharmacy=0.0
            for employee_id,name,employee_values in values:
                item=con.execute(
                    'SELECT * FROM payroll_items WHERE payroll_id=? AND employee_id=?',
                    (payroll['id'],employee_id)).fetchone()
                if not item:
                    raise ValueError(
                        f'{name} não possui lançamento nesta competência. Confira a data de admissão.')
                updated=dict(item)
                for field,amount in employee_values.items():
                    updated[field]=amount
                total=calc_total(updated)
                assignments=','.join(f'{field}=?' for field in employee_values)
                con.execute(
                    f"UPDATE payroll_items SET {assignments},total=?,source='Manual' WHERE id=?",
                    (*employee_values.values(),total,item['id']))
                total_marmitex+=employee_values.get('marmitex',0)
                total_pharmacy+=employee_values.get('pharmacy',0)
                con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',(
                    'Lançamento de descontos em lote',
                    f'{name} - {MONTHS[month-1]}/{year}: '
                    +', '.join(
                        f'{"Marmitex" if field=="marmitex" else "Farmácia"} {brl(amount)}'
                        for field,amount in employee_values.items())))
            con.execute(
                "UPDATE payrolls SET status='Em revisão',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (payroll['id'],))
        return len(values),round(total_marmitex,2),round(total_pharmacy,2)

    def add_payroll_deduction_batch_dialog(self,field):
        labels={'marmitex':'Marmitex','pharmacy':'Farmácia'}
        if field not in labels:
            raise ValueError('Tipo de desconto em lote inválido.')
        label=labels[field]
        period=self.selected_payroll_period()
        if period is None:
            return
        year,month=period
        with connect() as con:
            employees=con.execute(
                'SELECT id,name FROM employees WHERE active=1 ORDER BY name COLLATE NOCASE').fetchall()
            payroll=con.execute(
                'SELECT status FROM payrolls WHERE year=? AND month=?',(year,month)).fetchone()
        if payroll and payroll['status']=='Fechada':
            messagebox.showwarning(
                'Folha fechada',
                f'Reabra a folha de {MONTHS[month-1]}/{year} antes de lançar o lote.',
                parent=self)
            return
        if not employees:
            messagebox.showwarning(
                'Sem colaboradores ativos','Cadastre ou ative colaboradores antes de lançar o lote.',
                parent=self)
            return
        form=tk.Toplevel(self)
        form.title(f'{label} em lote')
        form.configure(bg=BG)
        form.transient(self)
        form.grab_set()
        form.geometry(f'{min(820,self.winfo_screenwidth()-80)}x{min(650,self.winfo_screenheight()-100)}')
        fields=ttk.Frame(form,padding=18)
        fields.pack(fill='both',expand=True)
        ttk.Label(fields,text=f'{label} em lote',font=('Segoe UI Semibold',15)).pack(anchor='w')
        ttk.Label(
            fields,
            text=f'Competência: {MONTHS[month-1]}/{year}. Deixe em branco para manter o valor atual; '
                 'informe 0,00 para zerar o desconto.',
            style='Sub.TLabel',wraplength=700).pack(anchor='w',pady=(4,12))
        headings=ttk.Frame(fields)
        headings.pack(fill='x')
        ttk.Label(headings,text='Colaborador',font=('Segoe UI Semibold',10)).grid(
            row=0,column=0,sticky='w')
        ttk.Label(headings,text=f'{label} (R$)',font=('Segoe UI Semibold',10)).grid(
            row=0,column=1,padx=8)
        host=ScrollableHost(fields)
        host.pack(fill='both',expand=True,pady=(5,10))
        host.inner.columnconfigure(0,weight=1)
        variables=[]
        inputs=[]
        for index,employee in enumerate(employees):
            ttk.Label(host.inner,text=employee['name']).grid(
                row=index,column=0,sticky='w',padx=4,pady=5)
            amount_var=tk.StringVar()
            entry=ttk.Entry(host.inner,textvariable=amount_var,width=18,justify='right')
            entry.grid(row=index,column=1,padx=8,pady=5)
            variables.append((employee['id'],amount_var))
            inputs.append(entry)

            def reveal(event,widget):
                form.update_idletasks()
                height=host.inner.winfo_height()
                top=host.canvas.canvasy(0)
                bottom=top+host.canvas.winfo_height()
                if widget.winfo_y()<top:
                    host.canvas.yview_moveto(widget.winfo_y()/max(height,1))
                elif widget.winfo_y()+widget.winfo_height()>bottom:
                    host.canvas.yview_moveto(
                        (widget.winfo_y()+widget.winfo_height()-host.canvas.winfo_height())/max(height,1))

            entry.bind('<FocusIn>',lambda event,widget=entry:reveal(event,widget))

        buttons=ttk.Frame(fields)
        buttons.pack(fill='x')

        def save():
            try:
                saved,total_marmitex,total_pharmacy=self.save_payroll_deductions_batch(
                    year,month,
                    [(employee_id,amount.get() if field=='marmitex' else '',
                      amount.get() if field=='pharmacy' else '')
                     for employee_id,amount in variables])
            except (ValueError,sqlite3.Error) as ex:
                messagebox.showerror('Não foi possível salvar o lote',str(ex),parent=form)
                return
            form.destroy()
            self.load_payroll()
            self.load_dashboard()
            messagebox.showinfo(
                f'{label} registrado',
                f'{saved} colaborador(es) atualizado(s).\nTotal de {label}: '
                f'{brl(total_marmitex if field=="marmitex" else total_pharmacy)}',
                parent=self)

        ttk.Button(buttons,text='Cancelar',command=form.destroy).pack(side='right')
        ttk.Button(buttons,text='Salvar lote',style='Accent.TButton',command=save).pack(
            side='right',padx=8)
        inputs[0].focus_set()
        self.wait_window(form)

    def apply_loan_installments(self, con, year, month):
        loans=con.execute('SELECT * FROM employee_loans ORDER BY id').fetchall()
        scheduled={}
        for loan in loans:
            if loan['settled_year'] is not None and (
                    year*12+month >= loan['settled_year']*12+loan['settled_month']):
                continue
            principal,count,elapsed,_,_=loan_terms_for_month(con,loan,year,month)
            if 0<=elapsed<count:
                amount=loan_installment(principal,count,elapsed+1)
                slot=scheduled.setdefault(loan['employee_id'],{LOAN_KIND:0.0,ADVANCE_KIND:0.0})
                kind=loan['kind'] if loan['kind'] in LOAN_KINDS else LOAN_KIND
                slot[kind]=round(slot[kind]+amount,2)
        payroll=con.execute('SELECT * FROM payrolls WHERE year=? AND month=?',(year,month)).fetchone()
        if not payroll and scheduled:
            payroll_id=con.execute(
                "INSERT INTO payrolls(year,month,status,notes,loan_only) VALUES(?,?,?,?,1)",
                (year,month,'Em revisão','')
            ).lastrowid
            payroll=con.execute('SELECT * FROM payrolls WHERE id=?',(payroll_id,)).fetchone()
        if not payroll or payroll['status']=='Fechada':
            return
        items=con.execute('SELECT * FROM payroll_items WHERE payroll_id=?',(payroll['id'],)).fetchall()
        item_by_employee={item['employee_id']:item for item in items}
        for employee_id,slot in scheduled.items():
            if employee_id in item_by_employee:
                continue
            salary=0
            total=round(salary-slot[LOAN_KIND]-slot[ADVANCE_KIND],2)
            con.execute('''INSERT INTO payroll_items(payroll_id,employee_id,salary,loan,loan_manual,advances,advances_manual,total,source,notes)
                VALUES(?,?,?,?,?,?,?,?,?,?)''',(payroll['id'],employee_id,salary,slot[LOAN_KIND],0,slot[ADVANCE_KIND],0,total,'Manual',''))
        items=con.execute('SELECT * FROM payroll_items WHERE payroll_id=?',(payroll['id'],)).fetchall()
        for item in items:
            slot=scheduled.get(item['employee_id'],{LOAN_KIND:0.0,ADVANCE_KIND:0.0})
            loan_amount=(item['loan_override'] if item['loan_override'] is not None
                else round((item['loan_manual'] or 0)+slot[LOAN_KIND],2))
            advances_manual=item['advances_manual'] if item['advances_manual'] is not None else item['advances']
            advances_amount=(item['advances_override'] if item['advances_override'] is not None
                else round((advances_manual or 0)+slot[ADVANCE_KIND],2))
            values=dict(item)
            values['loan']=loan_amount
            values['advances']=advances_amount
            total=calc_total(values)
            if (item['loan']!=loan_amount or item['advances']!=advances_amount or item['total']!=total
                    or item['advances_manual'] is None):
                con.execute('UPDATE payroll_items SET loan=?,advances=?,advances_manual=?,total=? WHERE id=?',
                    (loan_amount,advances_amount,advances_manual,total,item['id']))

    def loan_months(self,con,loan):
        months=set()
        for term in loan_terms_for_loan(con,loan):
            index=term['start_year']*12+term['start_month']-1
            for n in range(index,index+int(term['installment_count'])):
                months.add((n//12,n%12+1))
        return months

    def sync_loan_payrolls(self,con,months):
        # Cronológico, para que as folhas criadas herdem o salário do mês anterior.
        for year,month in sorted(months):
            self.apply_loan_installments(con,year,month)

    def loan_schedule_by_month(self,con,loan):
        kind=loan['kind'] if loan['kind'] in LOAN_KINDS else LOAN_KIND
        field='loan_override' if kind==LOAN_KIND else 'advances_override'
        schedule={}
        for year,month in self.loan_months(con,loan):
            if loan['settled_year'] is not None and (
                    year*12+month >= loan['settled_year']*12+loan['settled_month']):
                continue
            principal,count,elapsed,_,_=loan_terms_for_month(con,loan,year,month)
            if 0<=elapsed<count:
                schedule[(year,month)]=(field,loan_installment(principal,count,elapsed+1))
        return schedule

    def reconcile_loan_payroll_overrides(self,con,employee_id,old_schedule,new_schedule):
        changes={}
        for (year,month),(field,amount) in old_schedule.items():
            changes[(year,month,field)]=changes.get((year,month,field),0.0)-amount
        for (year,month),(field,amount) in new_schedule.items():
            changes[(year,month,field)]=changes.get((year,month,field),0.0)+amount

        for (year,month,field),delta in changes.items():
            if not delta:
                continue
            payroll=con.execute(
                'SELECT id,status FROM payrolls WHERE year=? AND month=?',(year,month)).fetchone()
            if not payroll or payroll['status']=='Fechada':
                continue
            con.execute(f'''UPDATE payroll_items SET {field}=MAX(0,ROUND({field}+?,2))
                WHERE payroll_id=? AND employee_id=? AND {field} IS NOT NULL''',
                (delta,payroll['id'],employee_id))

    def settle_employee_loan(self,loan_id,year,month):
        with connect() as con:
            loan=con.execute('''SELECT l.*,e.name FROM employee_loans l
                JOIN employees e ON e.id=l.employee_id WHERE l.id=?''',(loan_id,)).fetchone()
            if not loan:
                raise ValueError('O empréstimo ou adiantamento não foi encontrado.')
            if loan['settled_year'] is not None:
                raise ValueError('Este empréstimo ou adiantamento já foi quitado.')
            amount=loan_remaining_for_month(con,loan,year,month)
            if amount<=0:
                raise ValueError('Não há saldo restante para quitar neste contrato.')

            payroll=con.execute(
                'SELECT * FROM payrolls WHERE year=? AND month=?',(year,month)).fetchone()
            if not payroll:
                payroll_id=con.execute(
                    "INSERT INTO payrolls(year,month,status,notes,loan_only) VALUES(?,?,?,?,1)",
                    (year,month,'Em revisão','')).lastrowid
                payroll=con.execute('SELECT * FROM payrolls WHERE id=?',(payroll_id,)).fetchone()

            was_closed=payroll['status']=='Fechada'
            if was_closed:
                con.execute(
                    "UPDATE payrolls SET status='Em revisão',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (payroll['id'],))

            item=con.execute('''SELECT * FROM payroll_items
                WHERE payroll_id=? AND employee_id=?''',
                (payroll['id'],loan['employee_id'])).fetchone()
            field='loan' if loan['kind']==LOAN_KIND else 'advances'
            manual_field='loan_manual' if field=='loan' else 'advances_manual'
            override_field='loan_override' if field=='loan' else 'advances_override'
            if item:
                manual_amount=item[manual_field]
                if manual_amount is None:
                    manual_amount=item[field]
                manual_amount=max(0.0,float(manual_amount or 0))
            else:
                manual_amount=0.0

            con.execute('''UPDATE employee_loans
                SET settled_year=?,settled_month=?,settlement_amount=? WHERE id=?''',
                (year,month,amount,loan_id))
            self.sync_loan_payrolls(con,self.loan_months(con,loan))

            item=con.execute('''SELECT * FROM payroll_items
                WHERE payroll_id=? AND employee_id=?''',
                (payroll['id'],loan['employee_id'])).fetchone()
            if not item:
                con.execute('''INSERT INTO payroll_items(
                    payroll_id,employee_id,salary,total,source,notes)
                    VALUES(?,?,0,0,'Manual','')''',
                    (payroll['id'],loan['employee_id']))
                item=con.execute('''SELECT * FROM payroll_items
                    WHERE payroll_id=? AND employee_id=?''',
                    (payroll['id'],loan['employee_id'])).fetchone()

            current_scheduled=scheduled_amounts(con,loan['employee_id'],year,month)
            scheduled=current_scheduled[0] if field=='loan' else current_scheduled[1]
            manual_amount=round(manual_amount+amount,2)
            deduction=round(manual_amount+scheduled,2)
            values=dict(item)
            values[field]=deduction
            total=calc_total(values)
            con.execute(f'''UPDATE payroll_items
                SET {field}=?,{manual_field}=?,{override_field}=NULL,total=? WHERE id=?''',
                (deduction,manual_amount,total,item['id']))

            if was_closed:
                con.execute(
                    "UPDATE payrolls SET status='Fechada',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (payroll['id'],))
            con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',(
                'Quitação de empréstimo ou adiantamento',
                f'{loan["name"]} - {loan["kind"]}: {brl(amount)} em {MONTHS[month-1]}/{year}'))
        return loan['name'],loan['kind'],amount,was_closed

    def _build_loans(self):
        win=self
        actions,body=self._tab_action_layout(self.loans_tab)
        header=ttk.Frame(body)
        header.pack(fill='x')
        ttk.Label(header,text='Empréstimos, adiantamentos salariais e Meta',font=('Segoe UI Semibold',15)).pack(side='left')
        ttk.Label(body,text='Empréstimos e adiantamentos entram na folha. Meta é um controle separado, sem efeito na folha ou no holerite.',style='Sub.TLabel').pack(anchor='w',pady=(4,12))
        self.loan_period_label=ttk.Label(body,style='Sub.TLabel')
        self.loan_period_label.pack(anchor='w',pady=(0,8))
        columns=('employee','kind','total_amount','principal','installments','monthly','start','current','notes')
        self.loan_notebook=ttk.Notebook(body)
        self.loan_notebook.pack(fill='both',expand=True)
        self._align_tab_actions(actions,self.loan_notebook)
        self.loan_trees={}
        for key,title in (('advances','Adiantamentos'),('loans','Empréstimos')):
            loan_table=ttk.Frame(self.loan_notebook)
            self.loan_notebook.add(loan_table,text=title)
            if key=='advances':
                filters=ttk.Frame(loan_table)
                filters.pack(fill='x',pady=(8,10))
                ttk.Label(filters,text='Situação:').pack(side='left',padx=(4,6))
                self.advance_filter=ttk.Combobox(
                    filters,state='readonly',width=16,values=('Pendentes','Quitados'))
                self.advance_filter.current(0)
                self.advance_filter.pack(side='left')
                ttk.Label(
                    filters,text='Descontos confirmados em folhas fechadas e quitações até a competência selecionada.',
                    style='Sub.TLabel').pack(side='left',padx=12)
                table_columns=('employee','total_amount','paid','principal','status','start','notes')
                headings=[('employee','Colaborador',180),('total_amount','Valor total',120),
                    ('paid','Já descontado',120),('principal','Falta descontar',120),
                    ('status','Situação',110),('start','Primeiro desconto',140),('notes','Observações',180)]
            else:
                table_columns=columns
                headings=[('employee','Colaborador',160),('kind','Tipo',150),('total_amount','Valor total',150),('principal','Saldo restante',110),('installments','Parcelas',80),('monthly','Parcela mensal',105),('start','Vigência',90),('current','Parcela do mês',125),('notes','Observações',180)]
            loan_tree=ttk.Treeview(loan_table,columns=table_columns,show='headings',selectmode='browse')
            self.loan_trees[key]=loan_tree
            for column,label,width in headings:
                loan_tree.heading(column,text=label,anchor='center')
                loan_tree.column(column,width=width,anchor='w' if column in ('employee','notes') else 'center')
            loan_vertical_scroll=ttk.Scrollbar(loan_table,orient='vertical',command=loan_tree.yview)
            loan_scroll=ttk.Scrollbar(loan_table,orient='horizontal',command=loan_tree.xview)
            loan_tree.configure(xscrollcommand=loan_scroll.set,yscrollcommand=loan_vertical_scroll.set)
            loan_scroll.pack(side='bottom',fill='x')
            loan_vertical_scroll.pack(side='right',fill='y')
            loan_tree.pack(side='left',fill='both',expand=True)
            loan_tree.bind('<Double-1>',lambda event:edit_loan_dialog())
        tree=self.loan_trees['advances']
        self.loans_tree=tree
        meta_page=ttk.Frame(self.loan_notebook)
        self.loan_notebook.add(meta_page,text='Meta')
        loan_actions=ttk.Frame(actions)
        loan_actions.pack(fill='both',expand=True)
        meta_actions=ttk.Frame(actions)
        self._build_meta(meta_page,meta_actions)

        def select_tab(event=None):
            nonlocal tree
            is_meta=self.loan_notebook.index('current')==2
            if is_meta:
                loan_actions.pack_forget()
                meta_actions.pack(fill='both',expand=True)
                self.loan_period_label.configure(text='Meta: consulte os lançamentos pelo período e colaborador abaixo.')
            else:
                meta_actions.pack_forget()
                loan_actions.pack(fill='both',expand=True)
                tree=self.loan_trees[('advances','loans')[self.loan_notebook.index('current')]]
                self.loans_tree=tree
                self.loan_period_label.configure(
                    text=f'Exibindo lançamentos com parcela ou quitação em '
                         f'{MONTHS[selected_month-1]}/{selected_year}.')

        self.loan_notebook.bind('<<NotebookTabChanged>>',select_tab)
        try:
            selected_year=int(self.pay_year.get())
            selected_month=MONTHS.index(self.pay_month.get())+1
        except (ValueError, tk.TclError):
            selected_year=datetime.now().year
            selected_month=datetime.now().month

        def refresh():
            nonlocal selected_year,selected_month
            try:
                selected_year=int(self.pay_year.get())
                selected_month=MONTHS.index(self.pay_month.get())+1
            except (ValueError,tk.TclError):
                selected_year=datetime.now().year
                selected_month=datetime.now().month
            self.loan_period_label.configure(
                text=('Meta: consulte os lançamentos pelo período e colaborador abaixo.'
                      if self.loan_notebook.index('current')==2 else
                      f'Exibindo lançamentos com parcela ou quitação em '
                      f'{MONTHS[selected_month-1]}/{selected_year}.'))
            for loan_tree in self.loan_trees.values():
                for row in loan_tree.get_children():
                    loan_tree.delete(row)
            reports={
                kind:{row['loan_id']:row for row in
                      self.loan_report_data(selected_year,selected_month,kind)}
                for kind in LOAN_KINDS}
            advance_status=reports[ADVANCE_KIND]
            monthly_loan_ids={
                loan_id
                for kind_rows in reports.values()
                for loan_id,row in kind_rows.items()
                if any((item['year'],item['month'])==(selected_year,selected_month)
                       for item in row['monthly_details'])
            }
            with connect() as con:
                loans=con.execute('''SELECT l.*,e.name FROM employee_loans l
                    JOIN employees e ON e.id=l.employee_id
                    ORDER BY l.start_year DESC,l.start_month DESC,e.name COLLATE NOCASE''').fetchall()
                for loan in loans:
                    if loan['id'] not in monthly_loan_ids:
                        continue
                    count=loan['installment_count']
                    start_year,start_month=loan['start_year'],loan['start_month']
                    if loan['settled_year'] is not None:
                        progress=f'Quitado em {loan["settled_month"]:02d}/{loan["settled_year"]}'
                        monthly=0
                        remaining=0
                    else:
                        principal,count,elapsed,start_year,start_month=loan_terms_for_month(con,loan,selected_year,selected_month)
                        if elapsed<0:
                            progress='A iniciar'
                            monthly=loan_installment(principal,count,1)
                        elif elapsed>=count:
                            progress='Concluído'
                            monthly=0
                        else:
                            progress=f'{elapsed+1}/{count}'
                            monthly=loan_installment(principal,count,elapsed+1)
                        remaining=loan_remaining_for_month(con,loan,selected_year,selected_month)
                    if loan['kind']==ADVANCE_KIND:
                        status=advance_status[loan['id']]
                        remaining=status['balance']
                        paid=remaining<=0.005
                        selected_filter=self.advance_filter.get()
                        if (selected_filter=='Pendentes' and paid
                                or selected_filter=='Quitados' and not paid):
                            continue
                        situation='Quitado' if paid else 'Parcial' if status['paid']>0.005 else 'Pendente'
                        self.loan_trees['advances'].insert(
                            '','end',iid=str(loan['id']),
                            values=(loan['name'],brl(status['principal']),brl(status['paid']),
                                brl(remaining),situation,f'{MONTHS[start_month-1]}/{start_year}',loan['notes'] or ''))
                    else:
                        target=self.loan_trees['loans']
                        target.insert('','end',iid=str(loan['id']),values=(loan['name'],loan['kind'],brl(loan['principal']),brl(remaining),count,brl(monthly),f'{MONTHS[start_month-1]}/{start_year}',progress,loan['notes'] or ''))
            for loan_tree in self.loan_trees.values():
                self.autosize_treeview_columns(loan_tree,max_width=180)
                loan_tree.column('notes',stretch=True)
            self.refresh_meta()

        self.advance_filter.bind('<<ComboboxSelected>>',lambda event:refresh())

        def settle_loan():
            selection=tree.selection()
            if not selection:
                messagebox.showinfo('Selecione um lançamento','Selecione um empréstimo ou adiantamento para quitar.',parent=win)
                return
            loan_id=int(selection[0])
            with connect() as con:
                loan=con.execute('''SELECT l.*,e.name FROM employee_loans l
                    JOIN employees e ON e.id=l.employee_id WHERE l.id=?''',(loan_id,)).fetchone()
                if not loan or loan['settled_year'] is not None:
                    messagebox.showinfo('Lançamento já quitado','Este lançamento já foi quitado.',parent=win)
                    return
                amount=loan_remaining_for_month(con,loan,selected_year,selected_month)
                if amount<=0:
                    messagebox.showinfo('Sem saldo restante','Este contrato não possui saldo restante para quitar.',parent=win)
                    return
            destination='empréstimo' if loan['kind']==LOAN_KIND else 'adiantamento'
            if not messagebox.askyesno(
                    'Confirmar quitação',
                    f'Quitar {loan["kind"].lower()} de {loan["name"]} pelo saldo restante de {brl(amount)}?\n\n'
                    f'O valor será lançado em {MONTHS[selected_month-1]}/{selected_year} no desconto de {destination}; '
                    'as parcelas futuras serão encerradas. Os demais valores da folha serão mantidos.',
                    parent=win):
                return
            try:
                name,kind,settled_amount,was_closed=self.settle_employee_loan(
                    loan_id,selected_year,selected_month)
            except (sqlite3.Error,ValueError) as ex:
                messagebox.showerror('Erro ao quitar lançamento',str(ex),parent=win)
                return
            refresh()
            self.load_payroll()
            self.load_dashboard()
            closed_message=' A folha permaneceu fechada após a atualização.' if was_closed else ''
            messagebox.showinfo(
                'Quitação registrada',
                f'{kind} de {name} quitado por {brl(settled_amount)} em '
                f'{MONTHS[selected_month-1]}/{selected_year}.{closed_message}',
                parent=win)

        def delete_selected_loan(parent=None):
            parent=parent if parent is not None else win
            selection=tree.selection()
            if not selection:
                messagebox.showinfo('Selecione um lançamento','Selecione um lançamento para excluir.',parent=parent)
                return False
            loan_id=int(selection[0])
            with connect() as con:
                loan=con.execute(
                    'SELECT l.*,e.name FROM employee_loans l JOIN employees e ON e.id=l.employee_id WHERE l.id=?',
                    (loan_id,)).fetchone()
            if loan['settled_year'] is not None:
                messagebox.showwarning(
                    'Lançamento quitado',
                    'Um contrato quitado não pode ser excluído para preservar o registro da quitação.',
                    parent=parent)
                return False
            if not messagebox.askyesno(
                    'Excluir lançamento',
                    f'Excluir {loan["kind"].lower()} de {loan["name"]}?\n\n'
                    'As parcelas serão removidas das folhas abertas. Folhas fechadas não são alteradas.',
                    parent=parent):
                return False
            with connect() as con:
                months=self.loan_months(con,loan)
                old_schedule=self.loan_schedule_by_month(con,loan)
                con.execute('DELETE FROM employee_loan_adjustments WHERE loan_id=?',(loan_id,))
                con.execute('DELETE FROM employee_loans WHERE id=?',(loan_id,))
                con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',(
                    'Exclusão de lançamento',
                    f'{loan["kind"]}: {loan["name"]} - {brl(loan["principal"])} em {loan["installment_count"]} parcelas'))
                self.reconcile_loan_payroll_overrides(con,loan['employee_id'],old_schedule,{})
                self.sync_loan_payrolls(con,months)
            refresh()
            self.load_payroll();self.load_dashboard()
            return True

        def edit_loan_dialog():
            selection=tree.selection()
            if not selection:
                messagebox.showinfo('Selecione um empréstimo','Selecione um empréstimo para editar ou excluir.',parent=win)
                return
            loan_id=int(selection[0])
            with connect() as con:
                loan=con.execute('SELECT l.*,e.name FROM employee_loans l JOIN employees e ON e.id=l.employee_id WHERE l.id=?',(loan_id,)).fetchone()
            settled=loan['settled_year'] is not None
            form=tk.Toplevel(win);form.title('Editar lançamento');form.configure(bg=BG);form.transient(win);form.grab_set();form.resizable(False,False)
            fields=ttk.Frame(form,padding=20);fields.pack(fill='both',expand=True)
            ttk.Label(fields,text=f'Editar {loan["kind"].lower()} - {loan["name"]}',font=('Segoe UI Semibold',15)).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,8))
            hint=('Contrato quitado. Somente as observações podem ser alteradas.' if settled else
                'Altere o valor, a quantidade de parcelas ou o primeiro desconto. As folhas abertas são atualizadas automaticamente e as folhas dos meses que faltarem são criadas. Folhas fechadas não são alteradas.')
            ttk.Label(fields,text=hint,style='Sub.TLabel',wraplength=460).grid(row=1,column=0,columnspan=2,sticky='w',pady=(0,12))
            notes_var=tk.StringVar(value=loan['notes'] or '')
            principal_var=tk.StringVar(value=f'{loan["principal"]:.2f}'.replace('.',','))
            count_var=tk.StringVar(value=str(loan['installment_count']))
            year_var=tk.StringVar(value=str(loan['start_year']))
            month_var=tk.StringVar(value=MONTHS[loan['start_month']-1])
            ttk.Label(fields,text='Valor total emprestado (R$)').grid(row=2,column=0,sticky='w',pady=5,padx=(0,14))
            ttk.Entry(fields,textvariable=principal_var,width=20,state='disabled' if settled else 'normal').grid(row=2,column=1,sticky='ew',pady=5)
            ttk.Label(fields,text='Quantidade de parcelas').grid(row=3,column=0,sticky='w',pady=5,padx=(0,14))
            ttk.Entry(fields,textvariable=count_var,width=20,state='disabled' if settled else 'normal').grid(row=3,column=1,sticky='ew',pady=5)
            ttk.Label(fields,text='Primeiro desconto - mês/ano').grid(row=4,column=0,sticky='w',pady=5,padx=(0,14))
            start=ttk.Frame(fields);start.grid(row=4,column=1,sticky='w',pady=5)
            ttk.Combobox(start,textvariable=month_var,state='disabled' if settled else 'readonly',width=15,values=MONTHS).pack(side='left')
            ttk.Entry(start,textvariable=year_var,width=8,state='disabled' if settled else 'normal').pack(side='left',padx=(8,0))
            ttk.Label(fields,text='Observações').grid(row=5,column=0,sticky='w',pady=5,padx=(0,14))
            ttk.Entry(fields,textvariable=notes_var,width=48).grid(row=5,column=1,sticky='ew',pady=5)
            kind_var=tk.StringVar(value=loan['kind'] if loan['kind'] in LOAN_KINDS else LOAN_KIND)
            ttk.Label(fields,text='Tipo').grid(row=6,column=0,sticky='w',pady=5,padx=(0,14))
            ttk.Combobox(fields,textvariable=kind_var,state='disabled' if settled else 'readonly',width=22,values=LOAN_KINDS).grid(row=6,column=1,sticky='w',pady=5)

            def save_adjustment():
                if settled:
                    with connect() as con:
                        con.execute('UPDATE employee_loans SET notes=? WHERE id=?',
                            (notes_var.get().strip(),loan_id))
                    form.destroy()
                    refresh()
                    return
                try:
                    new_principal=money(principal_var.get())
                    new_count=int(count_var.get())
                    start_year=int(year_var.get())
                    start_month=MONTHS.index(month_var.get())+1
                except (ValueError,TypeError):
                    messagebox.showerror('Dados inválidos','Confira o valor, a quantidade de parcelas e a data de início.',parent=form)
                    return
                if not math.isfinite(new_principal) or new_principal<=0 or not 0<new_count<=600 or not 1900<=start_year<=9999:
                    messagebox.showerror('Dados inválidos','Informe valor, parcelas (1 a 600) e ano válidos.',parent=form)
                    return
                with connect() as con:
                    old_months=self.loan_months(con,loan)
                    old_schedule=self.loan_schedule_by_month(con,loan)
                    con.execute('DELETE FROM employee_loan_adjustments WHERE loan_id=?',(loan_id,))
                    con.execute('''UPDATE employee_loans SET principal=?,installment_count=?,start_year=?,start_month=?,notes=?,kind=? WHERE id=?''',
                        (new_principal,new_count,start_year,start_month,notes_var.get().strip(),kind_var.get(),loan_id))
                    con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',('Alteração de empréstimo',f'{loan["name"]} - {brl(new_principal)} em {new_count} parcelas a partir de {MONTHS[start_month-1]}/{start_year}'))
                    updated=con.execute('SELECT * FROM employee_loans WHERE id=?',(loan_id,)).fetchone()
                    new_months=self.loan_months(con,updated)
                    new_schedule=self.loan_schedule_by_month(con,updated)
                    self.reconcile_loan_payroll_overrides(con,loan['employee_id'],old_schedule,new_schedule)
                    self.sync_loan_payrolls(con,old_months|new_months)
                form.destroy()
                refresh()
                self.load_payroll();self.load_dashboard()

            def delete_loan():
                if delete_selected_loan(parent=form):
                    form.destroy()

            buttons=ttk.Frame(fields);buttons.grid(row=7,column=0,columnspan=2,sticky='e',pady=(12,0))
            ttk.Button(buttons,text='Cancelar',command=form.destroy).pack(side='right',padx=(8,0))
            ttk.Button(buttons,text='Salvar alterações',style='Accent.TButton',command=save_adjustment).pack(side='right')
            ttk.Button(buttons,text='Excluir lançamento',command=delete_loan).pack(side='right',padx=(0,8))

        def add_loan_dialog(kind=LOAN_KIND):
            with connect() as con:
                employees=con.execute('SELECT id,name FROM employees WHERE active=1 ORDER BY name COLLATE NOCASE').fetchall()
            if not employees:
                messagebox.showwarning('Sem colaboradores ativos','Cadastre ou ative um colaborador antes de registrar um empréstimo.',parent=win)
                return
            form=tk.Toplevel(win);form.title(f'Cadastrar {kind.lower()}');form.configure(bg=BG);form.transient(win);form.grab_set();form.resizable(False,False)
            fields=ttk.Frame(form,padding=18);fields.pack(fill='both',expand=True)
            ttk.Label(fields,text='Novo lançamento',font=('Segoe UI Semibold',15)).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,10))
            employee_var=tk.StringVar(value=employees[0]['name'])
            amount_var=tk.StringVar()
            count_var=tk.StringVar(value='1' if kind==ADVANCE_KIND else '36')
            notes_var=tk.StringVar()
            year_var=tk.StringVar(value=str(selected_year))
            month_var=tk.StringVar(value=MONTHS[selected_month-1])
            ttk.Label(fields,text='Colaborador').grid(row=1,column=0,sticky='w',pady=5)
            ttk.Combobox(fields,textvariable=employee_var,state='readonly',width=32,values=[employee['name'] for employee in employees]).grid(row=1,column=1,sticky='ew',pady=5)
            ttk.Label(fields,text='Valor total (R$)').grid(row=2,column=0,sticky='w',pady=5)
            ttk.Entry(fields,textvariable=amount_var,width=20).grid(row=2,column=1,sticky='ew',pady=5)
            ttk.Label(fields,text='Número de parcelas').grid(row=3,column=0,sticky='w',pady=5)
            ttk.Entry(fields,textvariable=count_var,width=20).grid(row=3,column=1,sticky='ew',pady=5)
            ttk.Label(fields,text='Primeira parcela - mês/ano').grid(row=4,column=0,sticky='w',pady=5)
            start=ttk.Frame(fields);start.grid(row=4,column=1,sticky='w',pady=5)
            ttk.Combobox(start,textvariable=month_var,state='readonly',width=15,values=MONTHS).pack(side='left')
            ttk.Entry(start,textvariable=year_var,width=8).pack(side='left',padx=(8,0))
            ttk.Label(fields,text='Observações').grid(row=5,column=0,sticky='w',pady=5)
            ttk.Entry(fields,textvariable=notes_var,width=42).grid(row=5,column=1,sticky='ew',pady=5)
            kind_var=tk.StringVar(value=kind)
            ttk.Label(fields,text='Tipo').grid(row=6,column=0,sticky='w',pady=5)
            ttk.Combobox(fields,textvariable=kind_var,state='disabled',width=22,values=LOAN_KINDS).grid(row=6,column=1,sticky='w',pady=5)
            installment_preview=ttk.Label(fields,text='Informe o valor e a quantidade de parcelas.',style='Sub.TLabel')
            installment_preview.grid(row=7,column=0,columnspan=2,sticky='w',pady=(8,12))

            def update_preview(*_):
                try:
                    principal=money(amount_var.get())
                    count=int(count_var.get())
                    if principal>0 and count>0:
                        installment_preview.config(text=f'{count} parcelas: {brl(loan_installment(principal,count,1))} por mês; a última parcela será ajustada pelos centavos.')
                    else:
                        installment_preview.config(text='Informe um valor e uma quantidade de parcelas maiores que zero.')
                except ValueError:
                    installment_preview.config(text='Informe um valor e uma quantidade de parcelas válidos.')

            amount_var.trace_add('write',update_preview)
            count_var.trace_add('write',update_preview)
            update_preview()

            def save_loan():
                try:
                    principal=money(amount_var.get())
                    count=int(count_var.get())
                    start_year=int(year_var.get())
                    start_month=MONTHS.index(month_var.get())+1
                except (ValueError, TypeError):
                    messagebox.showerror('Dados inválidos','Confira o valor, a quantidade de parcelas e a data de início.',parent=form)
                    return
                if not math.isfinite(principal) or principal<=0 or not 0<count<=600 or not 1900<=start_year<=9999:
                    messagebox.showerror('Dados inválidos','O valor, a quantidade de parcelas (1 a 600) e o ano devem ser válidos.',parent=form)
                    return
                employee_id=next((employee['id'] for employee in employees if employee['name']==employee_var.get()),None)
                if employee_id is None:
                    messagebox.showerror('Colaborador','Selecione um colaborador.',parent=form)
                    return
                with connect() as con:
                    try:
                        require_active_employee(con,employee_id)
                    except ValueError as ex:
                        messagebox.showerror('Colaborador inativo',str(ex),parent=form)
                        return
                    payroll=con.execute('SELECT status FROM payrolls WHERE year=? AND month=?',(start_year,start_month)).fetchone()
                    if payroll and payroll['status']=='Fechada':
                        messagebox.showwarning('Folha fechada','Reabra a folha do mês de início antes de cadastrar a primeira parcela.',parent=form)
                        return
                    new_id=con.execute('''INSERT INTO employee_loans(employee_id,principal,installment_count,start_year,start_month,notes,kind)
                        VALUES(?,?,?,?,?,?,?)''',(employee_id,principal,count,start_year,start_month,notes_var.get().strip(),kind_var.get())).lastrowid
                    con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',(f'Cadastro de {kind_var.get().lower()}',f'{employee_var.get()} - {brl(principal)} em {count} parcelas a partir de {MONTHS[start_month-1]}/{start_year}'))
                    new_loan=con.execute('SELECT * FROM employee_loans WHERE id=?',(new_id,)).fetchone()
                    self.reconcile_loan_payroll_overrides(
                        con,employee_id,{},self.loan_schedule_by_month(con,new_loan))
                    self.sync_loan_payrolls(con,self.loan_months(con,new_loan))
                form.destroy()
                refresh()
                self.load_payroll();self.load_dashboard()

            buttons=ttk.Frame(fields);buttons.grid(row=8,column=0,columnspan=2,sticky='e',pady=(4,0))
            ttk.Button(buttons,text='Cancelar',command=form.destroy).pack(side='right',padx=(8,0))
            ttk.Button(buttons,text='Salvar',style='Accent.TButton',command=save_loan).pack(side='right')

        ttk.Button(
            loan_actions,text='Marmitex em lote',
            command=lambda:self.add_payroll_deduction_batch_dialog('marmitex')
        ).pack(fill='x',pady=(0,6))
        ttk.Button(
            loan_actions,text='Farmácia em lote',
            command=lambda:self.add_payroll_deduction_batch_dialog('pharmacy')
        ).pack(fill='x',pady=(0,6))
        self.loan_actions_menu=tk.Menu(self,tearoff=0)
        for label,command in (
                ('Cadastrar empréstimo',lambda:add_loan_dialog(LOAN_KIND)),
                ('Cadastrar adiantamento',lambda:add_loan_dialog(ADVANCE_KIND)),
                ('Cadastrar adiantamento em lote',self.add_salary_advances_batch_dialog),
                (None,None),
                ('Editar',edit_loan_dialog),
                ('Excluir',delete_selected_loan),
                ('Quitar saldo',settle_loan)):
            if label is None:
                self.loan_actions_menu.add_separator()
            else:
                self.loan_actions_menu.add_command(label=label,command=command)
        ttk.Menubutton(
            loan_actions,text='Cadastrar / ações',style='Orange.TMenubutton',
            menu=self.loan_actions_menu).pack(fill='x',pady=(0,6))
        self.refresh_loans=refresh
        self._add_tab_action_icons(loan_actions)
        self._tab_reports(loan_actions,[
            ('Por colaborador (PDF)',self.generate_advance_report_dialog)])

    def _build_meta(self,parent,actions):
        filters=ttk.Frame(parent,padding=(4,8))
        filters.pack(fill='x')
        today=datetime.now()
        self.meta_start_var=tk.StringVar(value=today.replace(day=1).strftime('%d/%m/%Y'))
        self.meta_end_var=tk.StringVar(value=today.strftime('%d/%m/%Y'))
        ttk.Label(filters,text='De (DD/MM/AAAA):').grid(row=0,column=0,sticky='w')
        ttk.Entry(filters,textvariable=self.meta_start_var,width=12).grid(row=0,column=1,padx=(4,10))
        ttk.Label(filters,text='Até:').grid(row=0,column=2)
        ttk.Entry(filters,textvariable=self.meta_end_var,width=12).grid(row=0,column=3,padx=(4,10))
        ttk.Label(filters,text='Colaborador:').grid(row=1,column=0,sticky='w',pady=(8,0))
        self.meta_employee_box=ttk.Combobox(filters,state='readonly',width=38)
        self.meta_employee_box.grid(row=1,column=1,columnspan=3,sticky='ew',pady=(8,0))
        self.meta_employee_ids=[None]
        self.meta_employee_box.configure(values=['Todos os colaboradores'])
        self.meta_employee_box.current(0)
        ttk.Button(filters,text='Filtrar',command=self.refresh_meta).grid(row=1,column=4,padx=8,pady=(8,0))
        holder=ttk.Frame(parent)
        holder.pack(fill='both',expand=True)
        self.meta_tree=ttk.Treeview(
            holder,columns=('employee','date','amount','notes'),show='headings',selectmode='browse')
        for column,label,width in (
                ('employee','Colaborador',180),('date','Data',100),
                ('amount','Valor total',120),('notes','Observações',180)):
            self.meta_tree.heading(column,text=label,anchor='center')
            self.meta_tree.column(column,width=width,anchor='w' if column in ('employee','notes') else 'center')
        vertical=ttk.Scrollbar(holder,orient='vertical',command=self.meta_tree.yview)
        horizontal=ttk.Scrollbar(holder,orient='horizontal',command=self.meta_tree.xview)
        self.meta_tree.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        horizontal.pack(side='bottom',fill='x')
        vertical.pack(side='right',fill='y')
        self.meta_tree.pack(fill='both',expand=True)
        self.meta_tree.bind('<Double-1>',lambda event:self.edit_selected_meta())
        self.meta_summary=ttk.Label(parent,text='Use Filtrar para consultar os lançamentos.',style='Sub.TLabel')
        self.meta_summary.pack(anchor='w',pady=8)
        self.meta_actions_menu=tk.Menu(self,tearoff=0)
        for label,command in (
                ('Cadastrar Meta',self.meta_entry_dialog),
                ('Cadastrar Meta em lote',self.add_meta_batch_dialog),
                (None,None),
                ('Editar',self.edit_selected_meta),
                ('Excluir',self.delete_selected_meta)):
            if label is None:
                self.meta_actions_menu.add_separator()
            else:
                self.meta_actions_menu.add_command(label=label,command=command)
        ttk.Menubutton(
            actions,text='Cadastrar / ações',style='Orange.TMenubutton',
            menu=self.meta_actions_menu).pack(fill='x',pady=(0,6))
        self._add_tab_action_icons(actions)
        self._tab_reports(actions,[('Meta (PDF)',self.generate_meta_report)])

    def meta_filter_values(self):
        start=normalize_employee_date(self.meta_start_var.get())
        end=normalize_employee_date(self.meta_end_var.get())
        if not start or not end or start>end:
            raise ValueError('Informe a data inicial e final em ordem válida (DD/MM/AAAA).')
        index=self.meta_employee_box.current()
        if not 0<=index<len(self.meta_employee_ids):
            raise ValueError('Selecione um colaborador ou todos os colaboradores.')
        return start,end,self.meta_employee_ids[index]

    def meta_report_data(self,start,end,employee_id=None):
        start=normalize_employee_date(start)
        end=normalize_employee_date(end)
        if not start or not end or start>end:
            raise ValueError('Informe um período válido para consultar a Meta.')
        sql='''SELECT m.*,e.name FROM employee_meta_entries m
            JOIN employees e ON e.id=m.employee_id WHERE m.entry_date BETWEEN ? AND ?'''
        parameters=[start,end]
        if employee_id is not None:
            sql+=' AND m.employee_id=?'
            parameters.append(employee_id)
        with connect() as con:
            return con.execute(
                sql+' ORDER BY m.entry_date,e.name COLLATE NOCASE,m.id',parameters).fetchall()

    def refresh_meta(self):
        index=self.meta_employee_box.current()
        selected=self.meta_employee_ids[index] if 0<=index<len(self.meta_employee_ids) else None
        with connect() as con:
            employees=con.execute('SELECT id,name FROM employees ORDER BY name COLLATE NOCASE').fetchall()
        self.meta_employee_ids=[None]+[employee['id'] for employee in employees]
        self.meta_employee_box.configure(values=['Todos os colaboradores']+[
            f'{employee["name"]} (#{employee["id"]})' for employee in employees])
        self.meta_employee_box.current(
            self.meta_employee_ids.index(selected) if selected in self.meta_employee_ids else 0)
        try:
            rows=self.meta_report_data(*self.meta_filter_values())
        except (ValueError,sqlite3.Error) as ex:
            messagebox.showerror('Erro ao consultar Meta',str(ex),parent=self)
            return
        self.meta_tree.delete(*self.meta_tree.get_children())
        for row in rows:
            self.meta_tree.insert('','end',iid=str(row['id']),values=(
                row['name'],employee_date_for_form(row['entry_date']),brl(row['amount']),row['notes']))
        self.autosize_treeview_columns(self.meta_tree,max_width=180)
        self.meta_tree.column('notes',stretch=True)
        self.meta_summary.configure(
            text=f'{len(rows)} lançamento(s) • Total: {brl(sum(row["amount"] for row in rows))} • Não integra a folha.')

    def save_meta_entry(self,employee_id,entry_date,amount,notes='',entry_id=None):
        entry_date,amount=meta_entry_values(entry_date,amount)
        with connect() as con:
            return self._save_meta_entry_in_connection(con,employee_id,entry_date,amount,notes,entry_id)

    def _save_meta_entry_in_connection(self,con,employee_id,entry_date,amount,notes,entry_id=None):
        previous=None
        if entry_id is not None:
            previous=con.execute('SELECT * FROM employee_meta_entries WHERE id=?',(entry_id,)).fetchone()
            if previous is None:
                raise ValueError('O lançamento de Meta não existe mais. Atualize a lista.')
        employee=con.execute('SELECT name,active FROM employees WHERE id=?',(employee_id,)).fetchone()
        if employee is None or (not employee['active'] and
                (previous is None or previous['employee_id']!=employee_id)):
            raise ValueError('Selecione um colaborador ativo para lançar a Meta.')
        values=(employee_id,entry_date,amount,notes.strip())
        if previous is None:
            entry_id=con.execute('''INSERT INTO employee_meta_entries(employee_id,entry_date,amount,notes)
                VALUES(?,?,?,?)''',values).lastrowid
        else:
            con.execute('''UPDATE employee_meta_entries SET employee_id=?,entry_date=?,amount=?,notes=?
                WHERE id=?''',(*values,entry_id))
        con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',(
            'Edição de Meta' if previous is not None else 'Cadastro de Meta',
            f'#{entry_id} - {employee["name"]} - {employee_date_for_form(entry_date)} - {brl(amount)}'))
        return entry_id

    def save_meta_batch(self,employee_ids,entry_date,amount,notes=''):
        entry_date,amount=meta_entry_values(entry_date,amount)
        if not employee_ids:
            raise ValueError('Marque pelo menos um colaborador ativo para lançar a Meta.')
        if len(set(employee_ids))!=len(employee_ids):
            raise ValueError('Há colaboradores repetidos na seleção.')
        with connect() as con:
            for employee_id in employee_ids:
                self._save_meta_entry_in_connection(con,employee_id,entry_date,amount,notes)
        return len(employee_ids),round(amount*len(employee_ids),2)

    def add_meta_batch_dialog(self):
        with connect() as con:
            employees=con.execute(
                'SELECT id,name FROM employees WHERE active=1 ORDER BY name COLLATE NOCASE').fetchall()
        if not employees:
            messagebox.showwarning('Sem colaboradores ativos','Cadastre ou ative colaboradores antes de lançar a Meta.',parent=self)
            return
        form=tk.Toplevel(self)
        form.title('Meta em lote')
        form.configure(bg=BG)
        form.transient(self)
        form.grab_set()
        form.geometry(f'{min(700,self.winfo_screenwidth()-80)}x{min(650,self.winfo_screenheight()-100)}')
        fields=ttk.Frame(form,padding=18)
        fields.pack(fill='both',expand=True)
        ttk.Label(fields,text='Meta em lote',font=('Segoe UI Semibold',15)).pack(anchor='w')
        ttk.Label(fields,text='Um único valor para os ativos marcados. Desmarque quem não deve receber. Não integra a folha.',
                  style='Sub.TLabel',wraplength=600).pack(anchor='w',pady=(4,12))
        settings=ttk.Frame(fields)
        settings.pack(fill='x',pady=(0,10))
        date_var=tk.StringVar(value=datetime.now().strftime('%d/%m/%Y'))
        amount_var=tk.StringVar()
        ttk.Label(settings,text='Data (DD/MM/AAAA):').grid(row=0,column=0,sticky='w')
        ttk.Entry(settings,textvariable=date_var,width=12).grid(row=0,column=1,padx=6)
        ttk.Label(settings,text='Valor por colaborador (R$):').grid(row=1,column=0,sticky='w',pady=(8,0))
        amount_entry=ttk.Entry(settings,textvariable=amount_var,width=20)
        amount_entry.grid(row=1,column=1,padx=6,pady=(8,0),sticky='w')
        notes_var=tk.StringVar()
        ttk.Label(settings,text='Observação do lote:').grid(row=2,column=0,sticky='w',pady=(8,0))
        ttk.Entry(settings,textvariable=notes_var,width=38).grid(row=2,column=1,padx=6,pady=(8,0),sticky='ew')
        choices=ttk.Frame(fields)
        choices.pack(fill='x',pady=(0,8))
        host=ScrollableHost(fields)
        host.pack(fill='both',expand=True)
        variables=[]
        for employee in employees:
            variable=tk.BooleanVar(value=True)
            ttk.Checkbutton(host.inner,text=employee['name'],variable=variable).pack(anchor='w',padx=4,pady=4)
            variables.append((employee['id'],variable))
        summary=ttk.Label(fields,style='Sub.TLabel')
        summary.pack(anchor='w',pady=8)

        def update_summary(*_):
            count=sum(variable.get() for employee_id,variable in variables)
            try:
                _,amount=meta_entry_values(date_var.get(),amount_var.get())
                summary.configure(text=f'{count} selecionado(s) • Total: {brl(amount*count)}')
            except ValueError:
                summary.configure(text=f'{count} selecionado(s) • Informe data e valor válidos.')

        def select_all(value):
            for employee_id,variable in variables:
                variable.set(value)

        ttk.Button(choices,text='Selecionar todos',command=lambda:select_all(True)).pack(side='left')
        ttk.Button(choices,text='Desmarcar todos',command=lambda:select_all(False)).pack(side='left',padx=8)
        for employee_id,variable in variables:
            variable.trace_add('write',update_summary)
        date_var.trace_add('write',update_summary)
        amount_var.trace_add('write',update_summary)
        update_summary()

        def save():
            try:
                count,total=self.save_meta_batch(
                    [employee_id for employee_id,variable in variables if variable.get()],
                    date_var.get(),amount_var.get(),notes_var.get())
            except (ValueError,sqlite3.Error) as ex:
                messagebox.showerror('Não foi possível salvar o lote',str(ex),parent=form)
                return
            form.destroy()
            self.refresh_meta()
            messagebox.showinfo('Metas registradas',f'{count} metas salvas. Total: {brl(total)}.\n'
                                'Os valores não foram incluídos na folha.',parent=self)

        buttons=ttk.Frame(fields)
        buttons.pack(fill='x')
        ttk.Button(buttons,text='Cancelar',command=form.destroy).pack(side='right')
        ttk.Button(buttons,text='Salvar lote',style='Accent.TButton',command=save).pack(side='right',padx=8)
        amount_entry.focus_set()

    def delete_meta_entry(self,entry_id):
        with connect() as con:
            row=con.execute('''SELECT m.*,e.name FROM employee_meta_entries m
                JOIN employees e ON e.id=m.employee_id WHERE m.id=?''',(entry_id,)).fetchone()
            if row is None:
                raise ValueError('O lançamento de Meta não existe mais. Atualize a lista.')
            con.execute('DELETE FROM employee_meta_entries WHERE id=?',(entry_id,))
            con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',(
                'Exclusão de Meta',
                f'#{entry_id} - {row["name"]} - {employee_date_for_form(row["entry_date"])} - {brl(row["amount"])}'))

    def edit_selected_meta(self):
        selection=self.meta_tree.selection()
        if not selection:
            messagebox.showinfo('Selecione uma Meta','Selecione um lançamento de Meta para editar.',parent=self)
            return
        self.meta_entry_dialog(int(selection[0]))

    def delete_selected_meta(self):
        selection=self.meta_tree.selection()
        if not selection:
            messagebox.showinfo('Selecione uma Meta','Selecione um lançamento de Meta para excluir.',parent=self)
            return
        if not messagebox.askyesno('Excluir Meta','Excluir permanentemente o lançamento de Meta selecionado?',parent=self):
            return
        try:
            self.delete_meta_entry(int(selection[0]))
        except (ValueError,sqlite3.Error) as ex:
            messagebox.showerror('Erro ao excluir Meta',str(ex),parent=self)
            return
        self.refresh_meta()

    def meta_entry_dialog(self,entry_id=None):
        with connect() as con:
            entry=con.execute('''SELECT m.*,e.name,e.active FROM employee_meta_entries m
                JOIN employees e ON e.id=m.employee_id WHERE m.id=?''',(entry_id,)).fetchone()
            if entry_id is not None and entry is None:
                messagebox.showerror('Meta não encontrada','Atualize a lista e tente novamente.',parent=self)
                return
            employees=con.execute('SELECT id,name FROM employees WHERE active=1 ORDER BY name COLLATE NOCASE').fetchall()
        inactive_history=entry is not None and not entry['active']
        if not employees and not inactive_history:
            messagebox.showwarning('Sem colaboradores ativos','Cadastre ou ative um colaborador antes de lançar a Meta.',parent=self)
            return
        form=tk.Toplevel(self)
        form.title('Editar Meta' if entry else 'Cadastrar Meta')
        form.configure(bg=BG)
        form.transient(self)
        form.grab_set()
        fields=ttk.Frame(form,padding=18)
        fields.pack(fill='both',expand=True)
        fields.columnconfigure(1,weight=1)
        ttk.Label(fields,text='Meta • Não integra a folha',font=('Segoe UI Semibold',14)).grid(
            row=0,column=0,columnspan=2,sticky='w',pady=(0,12))
        ttk.Label(fields,text='Colaborador').grid(row=1,column=0,sticky='w',pady=5)
        if inactive_history:
            ttk.Label(fields,text=f'{entry["name"]} (inativo • registro histórico)').grid(row=1,column=1,sticky='w',pady=5)
        else:
            employee_box=ttk.Combobox(fields,state='readonly',width=38,values=[e['name'] for e in employees])
            employee_box.current(next((i for i,e in enumerate(employees) if entry and e['id']==entry['employee_id']),0))
            employee_box.grid(row=1,column=1,sticky='ew',pady=5)
        date_var=tk.StringVar(value=employee_date_for_form(entry['entry_date']) if entry else datetime.now().strftime('%d/%m/%Y'))
        amount_var=tk.StringVar(value=brl(entry['amount']) if entry else '')
        for row,label,variable in ((2,'Data (DD/MM/AAAA)',date_var),(3,'Valor (R$)',amount_var)):
            ttk.Label(fields,text=label).grid(row=row,column=0,sticky='w',pady=5)
            ttk.Entry(fields,textvariable=variable).grid(row=row,column=1,sticky='ew',pady=5)
        ttk.Label(fields,text='Observações').grid(row=4,column=0,sticky='nw',pady=5)
        notes=tk.Text(fields,width=38,height=5,wrap='word',font=('Segoe UI',10))
        notes.grid(row=4,column=1,sticky='nsew',pady=5)
        notes.insert('1.0',entry['notes'] if entry else '')
        fields.rowconfigure(4,weight=1)

        def save():
            if inactive_history:
                employee_id=entry['employee_id']
            else:
                index=employee_box.current()
                if not 0<=index<len(employees):
                    messagebox.showerror('Colaborador inválido','Selecione um colaborador.',parent=form)
                    return
                employee_id=employees[index]['id']
            try:
                self.save_meta_entry(
                    employee_id,date_var.get(),amount_var.get(),
                    notes.get('1.0','end-1c'),entry_id)
            except (ValueError,sqlite3.Error) as ex:
                messagebox.showerror('Erro ao salvar Meta',str(ex),parent=form)
                return
            form.destroy()
            self.refresh_meta()
            messagebox.showinfo('Meta salva','Lançamento salvo no controle Meta. Não foi incluído na folha.\n'
                                'Use os filtros de período e colaborador para consultá-lo.',parent=self)

        buttons=ttk.Frame(fields)
        buttons.grid(row=5,column=0,columnspan=2,sticky='e',pady=(12,0))
        ttk.Button(buttons,text='Cancelar',command=form.destroy).pack(side='right',padx=(8,0))
        ttk.Button(buttons,text='Salvar',style='Accent.TButton',command=save).pack(side='right')

    def write_meta_report_pdf(self,start,end,path,employee_id=None):
        rows=self.meta_report_data(start,end,employee_id)
        total=round(sum(row['amount'] for row in rows),2)
        employee_name='Todos os colaboradores'
        if employee_id is not None:
            with connect() as con:
                employee=con.execute('SELECT name FROM employees WHERE id=?',(employee_id,)).fetchone()
            if employee is None:
                raise ValueError('O colaborador selecionado não existe mais.')
            employee_name=employee['name']
        styles=getSampleStyleSheet()
        cell=ParagraphStyle(
            'MetaCell',parent=styles['Normal'],fontName='Helvetica',
            fontSize=5.5,leading=6.5,wordWrap='CJK')
        centered=ParagraphStyle('MetaCenteredCell',parent=cell,alignment=1)
        total_cell=ParagraphStyle('MetaTotalCell',parent=cell,fontName='Helvetica-Bold')
        centered_total=ParagraphStyle('MetaCenteredTotal',parent=total_cell,alignment=1)
        heading=ParagraphStyle(
            'MetaHeading',parent=styles['Normal'],fontName='Helvetica-Bold',
            fontSize=5,leading=6,textColor=colors.white,alignment=1)
        title=ParagraphStyle(
            'MetaTitle',parent=styles['Title'],fontName='Helvetica-Bold',
            fontSize=9,leading=11,textColor=colors.HexColor(NAVY),alignment=1,spaceAfter=2)
        subtitle=ParagraphStyle(
            'MetaSubtitle',parent=cell,alignment=1,textColor=colors.HexColor(MUTED))
        generated=datetime.now().strftime('%d/%m/%Y %H:%M')
        page_size=portrait(A4)
        usable_width=page_size[0]-24*mm-12
        document=SimpleDocTemplate(
            path,pagesize=page_size,leftMargin=12*mm,rightMargin=12*mm,
            topMargin=24*mm,bottomMargin=18*mm,title='Relatório de Meta',author=AUTHOR)
        story=[
            Paragraph('Relatório de Meta',title),
            Paragraph(f'Período: {employee_date_for_form(normalize_employee_date(start))} a '
                      f'{employee_date_for_form(normalize_employee_date(end))}',subtitle),
            Paragraph(xml_escape(employee_name),subtitle),
            Paragraph('Controle separado: estes valores não integram a folha nem o holerite.',subtitle),
            Spacer(1,3*mm),
        ]
        data=[[Paragraph(label,heading) for label in ('Colaborador','Data','Valor total','Observações')]]
        for row in rows:
            data.append([
                Paragraph(xml_escape(row['name']),cell),
                Paragraph(employee_date_for_form(row['entry_date']),centered),
                Paragraph(brl(row['amount']),centered),
                Paragraph(xml_escape(row['notes']).replace('\n','<br/>'),cell),
            ])
        if not rows:
            story.append(Paragraph('Nenhum lançamento de Meta no período selecionado.',cell))
        data.append([
            Paragraph('TOTAL GERAL',total_cell),
            Paragraph(f'{len(rows)} lançamento(s)',centered_total),
            Paragraph(brl(total),centered_total),
            '',
        ])
        table=LongTable(
            data,colWidths=[usable_width*ratio for ratio in (0.30,0.14,0.17,0.39)],
            repeatRows=1,hAlign='LEFT',spaceAfter=8*mm)
        table.setStyle(TableStyle([
            ('FONTSIZE',(0,0),(-1,-1),6.5),
            ('BACKGROUND',(0,0),(-1,0),colors.HexColor(NAVY)),
            ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('GRID',(0,0),(-1,-1),0.3,colors.HexColor('#dbe3ee')),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor(PDF_ROW_ALT)]),
            ('LEFTPADDING',(0,0),(-1,-1),3),
            ('RIGHTPADDING',(0,0),(-1,-1),3),
            ('TOPPADDING',(0,0),(-1,-1),1.5),
            ('BOTTOMPADDING',(0,0),(-1,-1),1.5),
            ('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#eff6ff')),
            ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),
        ]))
        story.append(table)

        def draw_page(canvas,document):
            self.pdf_page_header(canvas,page_size,generated,document.page)

        document.build(story,onFirstPage=draw_page,onLaterPages=draw_page,canvasmaker=NumberedReportCanvas)
        return len(rows),total

    def generate_meta_report(self):
        try:
            start,end,employee_id=self.meta_filter_values()
        except ValueError as ex:
            messagebox.showerror('Filtros inválidos',str(ex),parent=self)
            return
        path=temporary_pdf_path('relatorio_meta_')
        try:
            self.write_meta_report_pdf(start,end,path,employee_id)
            open_pdf(path)
        except Exception as ex:
            messagebox.showerror(
                'Erro no relatório de Meta',
                f'Não foi possível gerar ou abrir o PDF: {ex}\n\nArquivo temporário: {path}',parent=self)

    def save_salary_advances_batch(self,entries,start_year,start_month,count,notes=''):
        if not 1900<=start_year<=9999 or not 1<=start_month<=12 or not 1<=count<=600:
            raise ValueError('Informe mês, ano (1900 a 9999) e parcelas (1 a 600) válidos.')
        start_index=start_year*12+start_month-1
        months={(index//12,index%12+1) for index in range(start_index,start_index+count)}
        if max(year for year,month in months)>9999:
            raise ValueError('A última parcela deve ocorrer até dezembro de 9999.')
        values=[]
        seen=set()
        with connect() as con:
            employees={row['id']:row['name'] for row in con.execute(
                'SELECT id,name FROM employees WHERE active=1').fetchall()}
            for employee_id,value in entries:
                if employee_id not in employees or employee_id in seen:
                    raise ValueError('A lista contém colaborador inativo, inexistente ou repetido.')
                seen.add(employee_id)
                name=employees[employee_id]
                try:
                    principal=money(value)
                except ValueError as ex:
                    raise ValueError(f'{name}: informe um valor válido.') from ex
                if not math.isfinite(principal) or principal<0:
                    raise ValueError(f'{name}: informe um valor positivo ou deixe em branco.')
                if principal==0:
                    continue
                principal=round(principal,2)
                if principal<=0:
                    raise ValueError(f'{name}: o valor mínimo é R$ 0,01.')
                values.append((employee_id,name,principal))
            if not values:
                raise ValueError('Informe o valor de pelo menos um colaborador.')
            for payroll in con.execute(
                    "SELECT year,month FROM payrolls WHERE status='Fechada'").fetchall():
                if (payroll['year'],payroll['month']) in months:
                    raise ValueError(
                        f'A folha de {MONTHS[payroll["month"]-1]}/{payroll["year"]} está fechada. '
                        'Reabra essa folha antes de lançar o lote.')
            for employee_id,name,principal in values:
                loan_id=con.execute('''INSERT INTO employee_loans(
                    employee_id,principal,installment_count,start_year,start_month,notes,kind)
                    VALUES(?,?,?,?,?,?,?)''',
                    (employee_id,principal,count,start_year,start_month,notes.strip(),ADVANCE_KIND)).lastrowid
                loan=con.execute('SELECT * FROM employee_loans WHERE id=?',(loan_id,)).fetchone()
                self.reconcile_loan_payroll_overrides(
                    con,employee_id,{},self.loan_schedule_by_month(con,loan))
                con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',(
                    'Cadastro de adiantamento salarial em lote',
                    f'{name} - {brl(principal)} em {count} parcelas a partir de {MONTHS[start_month-1]}/{start_year}'))
            self.sync_loan_payrolls(con,months)
        return len(values),round(sum(principal for employee_id,name,principal in values),2)

    def add_salary_advances_batch_dialog(self):
        period=self.selected_payroll_period()
        if period is None:
            return
        with connect() as con:
            employees=con.execute(
                'SELECT id,name FROM employees WHERE active=1 ORDER BY name COLLATE NOCASE').fetchall()
        if not employees:
            messagebox.showwarning(
                'Sem colaboradores ativos','Cadastre ou ative colaboradores antes de lançar adiantamentos.',parent=self)
            return
        year,month=period
        form=tk.Toplevel(self)
        form.title('Adiantamentos salariais em lote')
        form.configure(bg=BG)
        form.transient(self)
        form.grab_set()
        form.geometry(f'{min(780,self.winfo_screenwidth()-80)}x{min(650,self.winfo_screenheight()-100)}')
        fields=ttk.Frame(form,padding=18)
        fields.pack(fill='both',expand=True)
        ttk.Label(fields,text='Adiantamentos salariais em lote',font=('Segoe UI Semibold',15)).pack(anchor='w')
        ttk.Label(
            fields,text='Preencha um valor por colaborador. Desconto integral no mês escolhido. Em branco ou zero: não lançar. Use Tab para avançar.',
            style='Sub.TLabel',wraplength=600).pack(anchor='w',pady=(4,12))
        settings=ttk.Frame(fields)
        settings.pack(fill='x',pady=(0,10))
        ttk.Label(settings,text='Mês do desconto:').pack(side='left')
        month_box=ttk.Combobox(settings,state='readonly',width=14,values=MONTHS)
        month_box.current(month-1)
        month_box.pack(side='left',padx=6)
        year_var=tk.StringVar(value=str(year))
        ttk.Entry(settings,textvariable=year_var,width=6).pack(side='left')
        notes_var=tk.StringVar()
        note_row=ttk.Frame(fields)
        note_row.pack(fill='x',pady=(0,10))
        ttk.Label(note_row,text='Observação do lote:').pack(side='left',padx=(0,6))
        ttk.Entry(note_row,textvariable=notes_var).pack(side='left',fill='x',expand=True)
        headings=ttk.Frame(fields)
        headings.pack(fill='x')
        ttk.Label(headings,text='Colaborador',font=('Segoe UI Semibold',10)).pack(side='left')
        ttk.Label(headings,text='Valor total do adiantamento (R$)',font=('Segoe UI Semibold',10)).pack(side='right')
        host=ScrollableHost(fields)
        host.pack(fill='both',expand=True,pady=(5,10))
        host.inner.columnconfigure(0,weight=1)
        variables=[]
        inputs=[]
        for index,employee in enumerate(employees):
            ttk.Label(host.inner,text=employee['name']).grid(row=index,column=0,sticky='w',padx=4,pady=5)
            variable=tk.StringVar()
            entry=ttk.Entry(host.inner,textvariable=variable,width=20,justify='right')
            entry.grid(row=index,column=1,sticky='e',padx=4,pady=5)
            variables.append((employee['id'],variable))
            inputs.append(entry)

            def reveal(event,widget=entry):
                form.update_idletasks()
                height=host.inner.winfo_height()
                top=host.canvas.canvasy(0)
                bottom=top+host.canvas.winfo_height()
                if widget.winfo_y()<top:
                    host.canvas.yview_moveto(widget.winfo_y()/max(height,1))
                elif widget.winfo_y()+widget.winfo_height()>bottom:
                    host.canvas.yview_moveto(
                        (widget.winfo_y()+widget.winfo_height()-host.canvas.winfo_height())/max(height,1))

            entry.bind('<FocusIn>',reveal)
        buttons=ttk.Frame(fields)
        buttons.pack(fill='x')

        def save():
            try:
                start_year=int(year_var.get())
            except ValueError:
                messagebox.showerror('Dados inválidos','Informe um ano válido.',parent=form)
                return
            try:
                saved,total=self.save_salary_advances_batch(
                    [(employee_id,variable.get()) for employee_id,variable in variables],
                    start_year,month_box.current()+1,1,notes_var.get())
            except (ValueError,sqlite3.Error) as ex:
                messagebox.showerror('Não foi possível salvar o lote',str(ex),parent=form)
                return
            form.destroy()
            self.refresh_loans()
            self.load_payroll()
            self.load_dashboard()
            messagebox.showinfo('Adiantamentos registrados',f'{saved} adiantamentos salvos. Total: {brl(total)}.',parent=self)

        ttk.Button(buttons,text='Cancelar',command=form.destroy).pack(side='right')
        ttk.Button(buttons,text='Salvar lote',style='Accent.TButton',command=save).pack(side='right',padx=8)
        inputs[0].focus_set()
        self.wait_window(form)

    def add_employee_loan_dialog(self):
        with connect() as con:
            employees=con.execute('SELECT id,name FROM employees WHERE active=1 ORDER BY name COLLATE NOCASE').fetchall()
        if not employees:
            messagebox.showwarning('Sem colaboradores ativos','Cadastre ou ative um colaborador antes de registrar um empréstimo.',parent=self)
            return
        try:
            selected_year=int(self.pay_year.get())
            selected_month=MONTHS.index(self.pay_month.get())+1
        except (ValueError, tk.TclError):
            selected_year=datetime.now().year
            selected_month=datetime.now().month

        form=tk.Toplevel(self)
        form.title('Cadastrar empréstimo parcelado')
        form.configure(bg=BG)
        form.transient(self)
        form.grab_set()
        form.resizable(False,False)
        fields=ttk.Frame(form,padding=22)
        fields.pack(fill='both',expand=True)
        ttk.Label(fields,text='Cadastrar empréstimo parcelado',font=('Segoe UI Semibold',16)).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,8))
        ttk.Label(fields,text='Informe o valor total, as parcelas e quando começa o desconto.',style='Sub.TLabel').grid(row=1,column=0,columnspan=2,sticky='w',pady=(0,12))
        employee_var=tk.StringVar(value=employees[0]['name'])
        amount_var=tk.StringVar()
        count_var=tk.StringVar(value='36')
        notes_var=tk.StringVar()
        year_var=tk.StringVar(value=str(selected_year))
        month_var=tk.StringVar(value=MONTHS[selected_month-1])
        ttk.Label(fields,text='Colaborador').grid(row=2,column=0,sticky='w',pady=6,padx=(0,16))
        ttk.Combobox(fields,textvariable=employee_var,state='readonly',width=34,values=[employee['name'] for employee in employees]).grid(row=2,column=1,sticky='ew',pady=6)
        ttk.Label(fields,text='Valor total emprestado (R$)').grid(row=3,column=0,sticky='w',pady=6,padx=(0,16))
        ttk.Entry(fields,textvariable=amount_var,width=20).grid(row=3,column=1,sticky='ew',pady=6)
        ttk.Label(fields,text='Quantidade de parcelas').grid(row=4,column=0,sticky='w',pady=6,padx=(0,16))
        ttk.Entry(fields,textvariable=count_var,width=20).grid(row=4,column=1,sticky='ew',pady=6)
        ttk.Label(fields,text='Primeiro desconto - mês/ano').grid(row=5,column=0,sticky='w',pady=6,padx=(0,16))
        start=ttk.Frame(fields)
        start.grid(row=5,column=1,sticky='w',pady=6)
        ttk.Combobox(start,textvariable=month_var,state='readonly',width=15,values=MONTHS).pack(side='left')
        ttk.Entry(start,textvariable=year_var,width=8).pack(side='left',padx=(8,0))
        ttk.Label(fields,text='Observações').grid(row=6,column=0,sticky='w',pady=6,padx=(0,16))
        ttk.Entry(fields,textvariable=notes_var,width=40).grid(row=6,column=1,sticky='ew',pady=6)
        preview=ttk.Label(fields,text='Exemplo: R$ 30.000 em 36 parcelas.',style='Sub.TLabel')
        preview.grid(row=7,column=0,columnspan=2,sticky='w',pady=(10,14))

        def update_preview(*_):
            try:
                principal=money(amount_var.get())
                count=int(count_var.get())
                if principal>0 and count>0:
                    preview.config(text=f'{count} parcelas de aproximadamente {brl(loan_installment(principal,count,1))}; a última é ajustada pelos centavos.')
            except (ValueError,TypeError):
                preview.config(text='Informe um valor e uma quantidade de parcelas válidos.')

        amount_var.trace_add('write',update_preview)
        count_var.trace_add('write',update_preview)

        def save_loan():
            try:
                principal=money(amount_var.get())
                count=int(count_var.get())
                start_year=int(year_var.get())
                start_month=MONTHS.index(month_var.get())+1
            except (ValueError,TypeError):
                messagebox.showerror('Dados inválidos','Confira o valor, a quantidade de parcelas e o mês/ano de início.',parent=form)
                return
            if not math.isfinite(principal) or principal<=0 or count<=0 or not 1900<=start_year<=9999:
                messagebox.showerror('Dados inválidos','Informe valor, quantidade de parcelas e ano válidos.',parent=form)
                return
            employee_id=next((employee['id'] for employee in employees if employee['name']==employee_var.get()),None)
            if employee_id is None:
                messagebox.showerror('Colaborador','Selecione um colaborador.',parent=form)
                return
            with connect() as con:
                try:
                    require_active_employee(con,employee_id)
                except ValueError as ex:
                    messagebox.showerror('Colaborador inativo',str(ex),parent=form)
                    return
                payroll=con.execute('SELECT status FROM payrolls WHERE year=? AND month=?',(start_year,start_month)).fetchone()
                if payroll and payroll['status']=='Fechada':
                    messagebox.showwarning('Folha fechada','Reabra a folha do mês de início antes de cadastrar a primeira parcela.',parent=form)
                    return
                new_id=con.execute('INSERT INTO employee_loans(employee_id,principal,installment_count,start_year,start_month,notes) VALUES(?,?,?,?,?,?)',(employee_id,principal,count,start_year,start_month,notes_var.get().strip())).lastrowid
                con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',('Cadastro de empréstimo',f'{employee_var.get()} - {brl(principal)} em {count} parcelas a partir de {MONTHS[start_month-1]}/{start_year}'))
                new_loan=con.execute('SELECT * FROM employee_loans WHERE id=?',(new_id,)).fetchone()
                self.reconcile_loan_payroll_overrides(
                    con,employee_id,{},self.loan_schedule_by_month(con,new_loan))
                self.sync_loan_payrolls(con,self.loan_months(con,new_loan))
            form.destroy()
            self.load_payroll()
            self.load_dashboard()

        buttons=ttk.Frame(fields)
        buttons.grid(row=8,column=0,columnspan=2,sticky='e')
        ttk.Button(buttons,text='Cancelar',command=form.destroy).pack(side='right',padx=(8,0))
        ttk.Button(buttons,text='Salvar empréstimo',style='Accent.TButton',command=save_loan).pack(side='right')
        form.update_idletasks()
        form.geometry(f'+{self.winfo_rootx()+100}+{self.winfo_rooty()+80}')

    def selected_item(self):
        sel=self.pay_tree.selection()
        if not sel: messagebox.showinfo('Selecione','Selecione um lançamento na tabela.'); return None
        return int(sel[0])

    def item_dialog(self, row=None, default_employee=None):
        year=int(self.pay_year.get()); month=MONTHS.index(self.pay_month.get())+1
        with connect() as con:
            p=con.execute('SELECT * FROM payrolls WHERE year=? AND month=?',(year,month)).fetchone()
            if not p:
                messagebox.showwarning('Folha inexistente','Não há folha cadastrada para esta competência; não é possível lançar dados neste período.'); return
            if p['status']=='Fechada':
                messagebox.showwarning('Folha fechada','Esta folha está fechada. Reabra o mês antes de incluir ou editar lançamentos.',parent=self)
                self.load_payroll()
                return
            self.apply_loan_installments(con,year,month)
            if row:
                item=con.execute('SELECT i.*,e.name,e.active FROM payroll_items i JOIN employees e ON e.id=i.employee_id WHERE i.id=?',(row,)).fetchone()
            else: item=None
            employees=con.execute('SELECT id,name FROM employees WHERE active=1 ORDER BY name COLLATE NOCASE').fetchall()
            existing={r['employee_id'] for r in con.execute('SELECT employee_id FROM payroll_items WHERE payroll_id=?',(p['id'],)).fetchall()}
            default_choice=next((e for e in employees if e['name']==default_employee),None)
            if not item:
                available=[e for e in employees if e['id'] not in existing]
                default_choice=next((e for e in available if e['name']==default_employee),available[0] if available else None)
                default_salary=employee_salary_for_period(con,default_choice['id'],year,month) if default_choice else 0
        win=tk.Toplevel(self);win.title('Editar lançamento' if item else 'Incluir colaborador na folha');win.configure(bg=BG);win.transient(self);win.grab_set();win.resizable(True,True)
        body=ttk.Frame(win,padding=20);body.pack(fill='both',expand=True)
        body.columnconfigure(1,weight=1);body.columnconfigure(3,weight=1)
        ttk.Label(body,text='Dados do lançamento',font=('Segoe UI Semibold',15)).grid(row=0,column=0,columnspan=4,sticky='w',pady=(0,12))
        vars={}
        if item:
            employee_choices=[(item['employee_id'],item['name'])]
            emp_var=tk.StringVar(value=item['name'])
        else:
            employee_choices=[(e['id'],e['name']) for e in employees if e['id'] not in existing]
            if not employee_choices:
                messagebox.showinfo('Folha completa','Todos os colaboradores ativos já estão nesta folha.');win.destroy();return
            emp_var=tk.StringVar(value=default_choice['name'])
        ttk.Label(body,text='Colaborador').grid(row=1,column=0,sticky='w',pady=5)
        if item and not item['active']:
            ttk.Label(body,text=f'{item["name"]} (inativo • registro histórico)').grid(row=1,column=1,columnspan=3,sticky='w',pady=5)
        else:
            combo=ttk.Combobox(body,textvariable=emp_var,state='readonly',width=28,values=[x[1] for x in employee_choices])
            combo.grid(row=1,column=1,columnspan=3,sticky='ew',pady=5)
            combo.bind('<<ComboboxSelected>>',lambda event:update_installment_description(event))
        fields=[('salary','Salário'),('pf','PF / adicional'),('overtime','Hora extra'),('vacation','Férias')]
        fields.append(('thirteenth','13º salário'))
        fields+=[('marmitex','Marmitex'),('advances','Adiantamento Salarial (0 para zerar)'),('pharmacy','Farmácia'),('other_deductions','Outros descontos'),('loan','Parcela empréstimo neste mês (0 para zerar)')]
        vals=item if item else {'salary':default_salary,'pf':0,'overtime':0,'vacation':0,'meta':0,'thirteenth':0,'marmitex':0,'advances':0,'pharmacy':0,'other_deductions':0,'loan':0}
        for idx,(key,label) in enumerate(fields):
            r=2+idx//2;c=(idx%2)*2
            ttk.Label(body,text=label).grid(row=r,column=c,sticky='w',pady=5,padx=(0,8))
            v=tk.StringVar(value=f'{float(vals[key] or 0):.2f}'.replace('.',','));vars[key]=v
            ttk.Entry(body,textvariable=v,width=16).grid(row=r,column=c+1,sticky='ew',pady=5,padx=(0,14))
        schedule_var=tk.StringVar()
        schedule_label=ttk.Label(body,textvariable=schedule_var,style='Sub.TLabel')
        schedule_label.grid(row=2+(len(fields)+1)//2,column=0,columnspan=4,sticky='w',pady=(4,2))

        def update_installment_description(event=None):
            employee_id=next((employee_id for employee_id,name in employee_choices if name==emp_var.get()),None)
            if employee_id is None:
                schedule_var.set('Selecione um colaborador para ver a parcela.')
                return
            with connect() as con:
                loan_details=loan_installment_details(con,employee_id,year,month,LOAN_KIND)
                advance_details=loan_installment_details(con,employee_id,year,month,ADVANCE_KIND)
                if not item:
                    vars['salary'].set(f'{employee_salary_for_period(con,employee_id,year,month):.2f}'.replace('.',','))
                    sched_loan,sched_adv=scheduled_amounts(con,employee_id,year,month)
                    vars['loan'].set(f'{sched_loan:.2f}'.replace('.',','))
                    vars['advances'].set(f'{sched_adv:.2f}'.replace('.',','))
            parts=' + '.join([f'Empréstimo {number}/{count} ({brl(amount)})' for number,count,amount in loan_details]
                +[f'Adiantamento {number}/{count} ({brl(amount)})' for number,count,amount in advance_details])
            if parts:
                schedule_var.set(f'Parcela(s) prevista(s) neste mês: {parts}')
            else:
                schedule_var.set('Sem parcela automática programada para este colaborador neste mês.')

        update_installment_description()
        rr=3+(len(fields)+1)//2
        ttk.Label(body,text='Observações').grid(row=rr,column=0,sticky='w',pady=(8,2))
        ttk.Label(
            body,text='Escreva uma observação por linha.',
            style='Sub.TLabel').grid(row=rr,column=1,columnspan=3,sticky='w',pady=(8,2))
        note_frame=ttk.Frame(body)
        note_frame.grid(row=rr+1,column=0,columnspan=4,sticky='nsew')
        body.rowconfigure(rr+1,weight=1)
        note_text=tk.Text(
            note_frame,height=8,width=52,wrap='word',font=('Segoe UI',10),
            bg=WHITE,fg=TEXT,relief='solid',bd=1,padx=8,pady=6)
        note_scroll=ttk.Scrollbar(
            note_frame,orient='vertical',command=note_text.yview)
        note_text.configure(yscrollcommand=note_scroll.set)
        note_text.pack(side='left',fill='both',expand=True)
        note_scroll.pack(side='right',fill='y')
        if item and item['notes']:
            note_text.insert('1.0',item['notes'])
        total_lbl=ttk.Label(body,text='Total líquido: R$ 0,00',font=('Segoe UI Semibold',11));total_lbl.grid(row=rr+2,column=0,columnspan=4,sticky='w',pady=(8,12))
        def getvals(): return {k:money(v.get()) for k,v in vars.items()}
        def preview(*_):
            try: total_lbl.config(text='Total líquido: '+brl(calc_total(getvals())))
            except ValueError: total_lbl.config(text='Confira os valores digitados.')
        for v in vars.values(): v.trace_add('write',preview)
        preview()
        def save():
            try: d=getvals()
            except ValueError as ex: messagebox.showerror('Valor inválido',str(ex),parent=win);return
            d.setdefault('thirteenth',float(item['thirteenth'] or 0) if item else 0.0)
            d.setdefault('meta',0.0)
            slip_keys=('salary','pf','overtime','vacation','meta','thirteenth','marmitex','advances','pharmacy','other_deductions','loan')
            name=emp_var.get()
            eid=next((x[0] for x in employee_choices if x[1]==name),None)
            if eid is None: messagebox.showerror('Colaborador','Selecione um colaborador.',parent=win);return
            total=calc_total(d)
            try:
                with connect() as con:
                    if not item:
                        require_active_employee(con,eid)
                    sched_loan,sched_adv=scheduled_amounts(con,eid,year,month)
                    # Valor digitado acima do programado vira acréscimo manual; abaixo vira ajuste fixo.
                    loan_manual=round(max(0.0,d['loan']-sched_loan),2)
                    loan_override=d['loan'] if d['loan']<sched_loan else None
                    adv_manual=round(max(0.0,d['advances']-sched_adv),2)
                    adv_override=d['advances'] if d['advances']<sched_adv else None
                    current=con.execute('SELECT status FROM payrolls WHERE id=?',(p['id'],)).fetchone()
                    if not current or current['status']=='Fechada':
                        messagebox.showwarning('Folha fechada','A folha foi fechada antes de salvar. Reabra o mês e tente novamente.',parent=win)
                        win.destroy()
                        self.load_payroll()
                        return
                    if item:
                        con.execute('''UPDATE payroll_items SET salary=?,pf=?,overtime=?,vacation=?,meta=?,thirteenth=?,marmitex=?,advances=?,pharmacy=?,other_deductions=?,loan=?,loan_manual=?,loan_override=?,advances_manual=?,advances_override=?,total=?,source='Manual',notes=? WHERE id=?''',(*[d[k] for k in slip_keys],loan_manual,loan_override,adv_manual,adv_override,total,note_text.get('1.0','end-1c').strip(),row))
                        con.execute("UPDATE payrolls SET status='Em revisão',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status!='Fechada'",(p['id'],))
                        con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',('Edição de lançamento',f'{name} - {MONTHS[month-1]}/{year}'))
                    else:
                        con.execute('''INSERT INTO payroll_items(payroll_id,employee_id,salary,pf,overtime,vacation,meta,thirteenth,marmitex,advances,pharmacy,other_deductions,loan,loan_manual,loan_override,advances_manual,advances_override,total,source,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(p['id'],eid,*[d[k] for k in slip_keys],loan_manual,loan_override,adv_manual,adv_override,total,'Manual',note_text.get('1.0','end-1c').strip()))
                        con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',('Novo lançamento',f'{name} - {MONTHS[month-1]}/{year}'))
            except ValueError as ex:
                messagebox.showerror('Colaborador inativo',str(ex),parent=win)
                return
            except sqlite3.IntegrityError as ex:
                messagebox.showwarning('Folha fechada',str(ex),parent=win)
                win.destroy()
                self.load_payroll()
                return
            win.destroy();self.load_payroll();self.load_dashboard()
        buttons=ttk.Frame(body);buttons.grid(row=rr+3,column=0,columnspan=4,sticky='e',pady=(8,0))
        ttk.Button(buttons,text='Cancelar',command=win.destroy).pack(side='right',padx=(8,0));ttk.Button(buttons,text='Salvar lançamento',style='Accent.TButton',command=save).pack(side='right')
        win.update_idletasks();win.geometry(f'+{self.winfo_rootx()+120}+{self.winfo_rooty()+90}')

    def add_item_dialog(self): self.item_dialog()
    def edit_selected_item(self):
        iid=self.selected_item()
        if iid is not None: self.item_dialog(row=iid)
    def remove_selected_item(self):
        iid=self.selected_item()
        if iid is None:return
        year=int(self.pay_year.get());month=MONTHS.index(self.pay_month.get())+1
        if self.payroll_is_closed(year,month):
            messagebox.showwarning('Folha fechada','Esta folha está fechada. Reabra o mês antes de remover lançamentos.',parent=self)
            self.load_payroll()
            return
        if not messagebox.askyesno('Confirmar remoção','Remover este lançamento da folha? Esta ação fica registrada no histórico de auditoria.'):return
        with connect() as con:
            r=con.execute('SELECT e.name,p.year,p.month,p.status FROM payroll_items i JOIN employees e ON e.id=i.employee_id JOIN payrolls p ON p.id=i.payroll_id WHERE i.id=?',(iid,)).fetchone()
            if not r:
                self.load_payroll()
                return
            if r['status']=='Fechada':
                messagebox.showwarning('Folha fechada','A folha foi fechada antes da remoção. Reabra o mês antes de alterar lançamentos.',parent=self)
                self.load_payroll()
                return
            try:
                con.execute('DELETE FROM payroll_items WHERE id=?',(iid,))
                con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',('Remoção de lançamento',f'{r["name"]} - {r["month"]}/{r["year"]}'))
            except sqlite3.IntegrityError as ex:
                messagebox.showwarning('Folha fechada',str(ex),parent=self)
                self.load_payroll()
                return
        self.load_payroll();self.load_dashboard()

    def toggle_status(self):
        year=int(self.pay_year.get());month=MONTHS.index(self.pay_month.get())+1
        with connect() as con:
            p=con.execute('SELECT * FROM payrolls WHERE year=? AND month=?',(year,month)).fetchone()
            if not p: messagebox.showinfo('Sem folha','Não há folha para este mês.');return
            is_reopening=p['status']=='Fechada'
            new='Em revisão' if is_reopening else 'Fechada'
            action='reabrir' if is_reopening else 'fechar'
            if not messagebox.askyesno(
                'Reabrir folha' if is_reopening else 'Fechar folha',
                f'Confirma {action} a folha de {MONTHS[month-1]} de {year}? '
                +('Os lançamentos voltarão a poder ser alterados.' if is_reopening else 'Depois disso, inclusão, edição e remoção de lançamentos ficarão bloqueadas.')
            ):return
            reason=''
            if is_reopening:
                while not reason:
                    reason=simpledialog.askstring('Motivo da reabertura',f'Informe o motivo para reabrir a folha de {MONTHS[month-1]} de {year}:',parent=self)
                    if reason is None:return
                    reason=reason.strip()
                    if not reason:
                        messagebox.showwarning('Motivo obrigatório','Informe o motivo para reabrir a folha.',parent=self)
            con.execute('UPDATE payrolls SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(new,p['id']))
            con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',('Reabertura de folha' if reason else 'Status da folha',f'{MONTHS[month-1]}/{year}: {new}'+(f' | Motivo: {reason}' if reason else '')))
        self.load_payroll()
        messagebox.showinfo('Folha reaberta' if is_reopening else 'Folha fechada',
            f'A folha de {MONTHS[month-1]} de {year} foi {action} com sucesso.'
            +(' Os lançamentos estão liberados para edição.' if is_reopening else ' Os lançamentos estão bloqueados para edição.'),
            parent=self)

    def add_employee_dialog(self):
        self.employee_dialog()

    def edit_selected_employee(self):
        selection=self.selected_employee_tree().selection()
        if not selection:
            messagebox.showinfo('Selecione','Selecione um colaborador para editar.',parent=self)
            return
        self.employee_dialog(int(selection[0]))

    def employee_salary_dialog(self,employee_id=None):
        if employee_id is None:
            selection=self.selected_employee_tree().selection()
            if not selection:
                messagebox.showinfo('Selecione','Selecione um colaborador para consultar ou alterar o salário.',parent=self)
                return
            employee_id=int(selection[0])
        if not employee_id:
            messagebox.showinfo('Selecione','Selecione um colaborador para consultar ou alterar o salário.',parent=self)
            return
        try:
            selected_year=int(self.pay_year.get())
            selected_month=MONTHS.index(self.pay_month.get())+1
        except (ValueError,tk.TclError):
            selected_year=datetime.now().year
            selected_month=datetime.now().month
        with connect() as con:
            employee=con.execute('SELECT id,name FROM employees WHERE id=?',(employee_id,)).fetchone()
            current_salary=employee_salary_for_period(con,employee_id,selected_year,selected_month)
        if not employee:
            messagebox.showerror('Colaborador não encontrado','Atualize a lista e tente novamente.',parent=self)
            self.load_employees()
            return

        win=tk.Toplevel(self)
        win.title(f'Salário e reajustes — {employee["name"]}')
        win.configure(bg=BG)
        win.transient(self)
        win.grab_set()
        win.geometry('640x520')
        win.minsize(600,480)
        body=ttk.Frame(win,padding=18)
        body.pack(fill='both',expand=True)
        body.columnconfigure(0,weight=1)
        body.rowconfigure(3,weight=1)
        ttk.Label(body,text=f'Salário e reajustes — {employee["name"]}',font=('Segoe UI Semibold',15)).grid(row=0,column=0,sticky='w')
        ttk.Label(
            body,text=f'Salário na competência selecionada: {brl(current_salary)}',
            style='Sub.TLabel').grid(row=1,column=0,sticky='w',pady=(4,10))
        ttk.Label(body,text='Histórico: salário anterior, novo salário e datas',font=('Segoe UI Semibold',10)).grid(
            row=2,column=0,sticky='w',pady=(0,5))
        salary_history_table=ttk.Frame(body)
        salary_history_table.grid(row=3,column=0,sticky='nsew')
        salary_history_table.columnconfigure(0,weight=1)
        salary_history_table.rowconfigure(0,weight=1)
        history_tree=ttk.Treeview(
            salary_history_table,columns=('old_salary','new_salary','period','changed'),show='headings',height=4)
        for column,title,width in (
            ('old_salary','Salário anterior',145),('new_salary','Novo salário',145),
            ('period','Mês do reajuste',150),('changed','Alterado em',165)):
            history_tree.heading(column,text=title)
            history_tree.column(column,width=width,anchor='center')
        history_scroll=ttk.Scrollbar(salary_history_table,orient='vertical',command=history_tree.yview)
        history_tree.configure(yscrollcommand=history_scroll.set)
        history_tree.grid(row=0,column=0,sticky='nsew')
        history_scroll.grid(row=0,column=1,sticky='ns')

        def display_changed_at(value):
            if not value:
                return '—'
            try:
                return datetime.strptime(value,'%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y %H:%M')
            except ValueError:
                return value

        def refresh_history():
            for item in history_tree.get_children():
                history_tree.delete(item)
            with connect() as con:
                rows=con.execute('''SELECT id,salary,old_salary,effective_year,effective_month,created_at
                    FROM employee_salary_history WHERE employee_id=?
                    ORDER BY effective_year DESC,effective_month DESC,id DESC''',(employee_id,)).fetchall()
                for row in rows:
                    old_salary=row['old_salary']
                    if old_salary is None:
                        old_salary=employee_salary_before_period(
                            con,employee_id,row['effective_year'],row['effective_month'])
                    history_tree.insert(
                        '','end',iid=str(row['id']),
                        values=(
                            brl(old_salary) if old_salary is not None else '—',
                            brl(row['salary']),
                            f'{MONTHS[row["effective_month"]-1]}/{row["effective_year"]}',
                            display_changed_at(row['created_at'])))

        refresh_history()
        self.autosize_treeview_columns(history_tree)
        ttk.Label(body,text='Registrar salário inicial ou reajuste',font=('Segoe UI Semibold',11)).grid(
            row=4,column=0,sticky='w',pady=(12,5))
        fields=ttk.Frame(body)
        fields.grid(row=5,column=0,sticky='ew')
        salary_var=tk.StringVar()
        year_var=tk.StringVar(value=str(selected_year))
        month_var=tk.StringVar(value=MONTHS[selected_month-1])
        ttk.Label(fields,text='Novo salário base (R$)').grid(row=0,column=0,sticky='w',pady=5,padx=(0,12))
        ttk.Entry(fields,textvariable=salary_var,width=20).grid(row=0,column=1,sticky='w',pady=5)
        adjustment_period_var=tk.StringVar(
            value=datetime.now().strftime('%m/%Y'))
        ttk.Label(fields,text='Mês/ano do reajuste (MM/AAAA)').grid(
            row=1,column=0,sticky='w',pady=5,padx=(0,12))
        ttk.Entry(fields,textvariable=adjustment_period_var,width=20).grid(
            row=1,column=1,sticky='w',pady=5)

        def save_salary():
            try:
                salary=round(money(salary_var.get()),2)
                updated_on=normalize_salary_register_period(
                    adjustment_period_var.get())
                effective_year=int(updated_on[:4])
                effective_month=int(updated_on[5:7])
            except (ValueError,TypeError):
                messagebox.showerror(
                    'Dados inválidos',
                    'Informe um salário e um mês/ano de reajuste válidos no formato MM/AAAA.',
                    parent=win)
                return
            if not math.isfinite(salary) or salary<0 or not 1900<=effective_year<=9999:
                messagebox.showerror('Dados inválidos','O salário não pode ser negativo e o ano deve ser válido.',parent=win)
                return
            period_label=f'{MONTHS[effective_month-1]}/{effective_year}'
            if not messagebox.askyesno(
                'Confirmar alteração salarial',
                f'O salário de {employee["name"]} passará a {brl(salary)} a partir de {period_label}.\n\nDeseja continuar?',
                parent=win):
                return
            try:
                with connect() as con:
                    previous=con.execute('''SELECT old_salary FROM employee_salary_history
                        WHERE employee_id=? AND effective_year=? AND effective_month=?''',
                        (employee_id,effective_year,effective_month)).fetchone()
                    old_salary=(
                        float(previous['old_salary']) if previous and previous['old_salary'] is not None
                        else employee_salary_before_period(con,employee_id,effective_year,effective_month))
                    changed_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    con.execute('''INSERT INTO employee_salary_history(
                        employee_id,salary,old_salary,effective_year,effective_month,created_at)
                        VALUES(?,?,?,?,?,?)
                        ON CONFLICT(employee_id,effective_year,effective_month)
                        DO UPDATE SET salary=excluded.salary,
                            old_salary=COALESCE(employee_salary_history.old_salary,excluded.old_salary),
                            created_at=excluded.created_at''',
                        (employee_id,salary,old_salary,effective_year,effective_month,changed_at))
                    existing_register_update=con.execute('''SELECT updated_on
                        FROM employee_salary_register_updates
                        WHERE employee_id=? AND updated_on LIKE ?
                        ORDER BY updated_on DESC LIMIT 1''',
                        (employee_id,f'{updated_on[:7]}-%')).fetchone()
                    if existing_register_update:
                        updated_on=existing_register_update['updated_on']
                    con.execute('''INSERT INTO employee_salary_register_updates(
                        employee_id,updated_on,amount) VALUES(?,?,?)
                        ON CONFLICT(employee_id,updated_on)
                        DO UPDATE SET amount=excluded.amount''',
                        (employee_id,updated_on,salary))
                    con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',(
                        'Alteração de salário',
                        f'{employee["name"]}: '
                        f'{brl(old_salary) if old_salary is not None else "salário anterior não identificado"} '
                        f'para {brl(salary)} a partir de {period_label}; '
                        f'coluna de {salary_register_period_label(updated_on)} atualizada; '
                        'folhas existentes preservadas'))
            except (sqlite3.Error,ValueError) as ex:
                messagebox.showerror('Erro ao atualizar salário',str(ex),parent=win)
                return
            refresh_history()
            salary_var.set('')
            self.load_employees()
            self.load_salary_register()
            messagebox.showinfo(
                'Salário atualizado',
                f'O salário de {employee["name"]} foi registrado a partir de {period_label}. '
                'As folhas existentes não foram alteradas.',
                parent=win)

        def delete_salary():
            selected=history_tree.selection()
            if not selected:
                messagebox.showinfo('Selecione','Selecione um reajuste do histórico para excluir.',parent=win)
                return
            record_id=int(selected[0])
            values=history_tree.item(selected[0],'values')
            if not messagebox.askyesno(
                'Excluir reajuste',
                f'Excluir o reajuste de {values[2]} para {employee["name"]}?\n\n'
                'As folhas já lançadas não serão alteradas.',
                parent=win):
                return
            try:
                with connect() as con:
                    salary_record=con.execute(
                        'SELECT salary,effective_year,effective_month FROM employee_salary_history WHERE id=? AND employee_id=?',
                        (record_id,employee_id)).fetchone()
                    if not salary_record:
                        messagebox.showerror('Registro não encontrado','Atualize o histórico e tente novamente.',parent=win)
                        refresh_history()
                        return
                    con.execute('DELETE FROM employee_salary_history WHERE id=? AND employee_id=?',(record_id,employee_id))
                    con.execute('''DELETE FROM employee_salary_register_updates
                        WHERE employee_id=? AND ABS(amount-?)<0.005''',
                        (employee_id,salary_record['salary']))
                    con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',(
                        'Exclusão de reajuste salarial',
                        f'{employee["name"]}: {brl(salary_record["salary"])} a partir de '
                        f'{MONTHS[salary_record["effective_month"]-1]}/{salary_record["effective_year"]}; '
                        'folhas existentes preservadas'))
            except sqlite3.Error as ex:
                messagebox.showerror('Erro ao excluir reajuste',str(ex),parent=win)
                return
            refresh_history()
            self.load_employees()
            self.load_salary_register()

        buttons=ttk.Frame(body)
        buttons.grid(row=7,column=0,sticky='ew',pady=(12,0))
        ttk.Button(buttons,text='Excluir reajuste',style='Secondary.TButton',command=delete_salary).pack(side='left')
        ttk.Button(buttons,text='Fechar',command=win.destroy).pack(side='right',padx=(8,0))
        ttk.Button(buttons,text='Salvar salário / reajuste',style='Accent.TButton',command=save_salary).pack(side='right')

    def employee_dialog(self,employee_id=None):
        with connect() as con:
            employee=con.execute('SELECT * FROM employees WHERE id=?',(employee_id,)).fetchone() if employee_id else None
        if employee_id and not employee:
            messagebox.showerror('Colaborador não encontrado','Atualize a lista e selecione um colaborador válido.',parent=self)
            self.load_employees()
            return
        win=tk.Toplevel(self)
        win.title('Editar colaborador' if employee else 'Cadastrar colaborador')
        win.configure(bg=BG)
        win.transient(self)
        win.grab_set()
        win.geometry('960x760')
        win.minsize(800,600)
        style=ttk.Style(win)
        style.configure(
            'EmployeeSection.TLabel',background=WHITE,foreground=NAVY,
            font=('Segoe UI Semibold',11))
        style.configure(
            'EmployeeHint.TLabel',background=WHITE,foreground=MUTED,
            font=('Segoe UI',9))
        style.configure(
            'EmployeeField.TLabel',background=WHITE,foreground='#475569',
            font=('Segoe UI Semibold',9))
        style.configure('EmployeeForm.TFrame',background=WHITE)
        body=ttk.Frame(win,padding=(20,16,20,14))
        body.pack(fill='both',expand=True)
        header=ttk.Frame(body)
        header.pack(fill='x',pady=(0,12))
        ttk.Label(
            header,text='Editar colaborador' if employee else 'Novo colaborador',
            style='Title.TLabel').pack(anchor='w')
        ttk.Label(
            header,
            text='Dados pessoais, contato e informações para folha de pagamento.',
            style='Sub.TLabel').pack(anchor='w',pady=(3,0))
        holder=ttk.Frame(body)
        holder.pack(fill='both',expand=True)
        canvas=tk.Canvas(holder,bg=BG,highlightthickness=0)
        scroll=ttk.Scrollbar(holder,orient='vertical',command=canvas.yview)
        form=ttk.Frame(canvas,padding=(2,2,12,8))
        form.columnconfigure(0,weight=1)
        form.columnconfigure(1,weight=1)
        form.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        form_window=canvas.create_window((0,0),window=form,anchor='nw')
        canvas.configure(yscrollcommand=scroll.set)
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(form_window,width=e.width))
        canvas.pack(side='left',fill='both',expand=True)
        scroll.pack(side='right',fill='y')
        canvas.bind('<MouseWheel>',lambda e:canvas.yview_scroll(
            -1 if e.delta>0 else 1,'units'))

        vs={}
        def create_section(title,hint,row,column,columnspan=1):
            card=tk.Frame(
                form,bg=WHITE,highlightbackground='#dbe3ee',
                highlightthickness=1,borderwidth=0)
            card.grid(
                row=row,column=column,columnspan=columnspan,sticky='nsew',
                padx=(0,10) if column==0 else (6,0),pady=(0,12))
            card.columnconfigure(0,weight=1)
            content=tk.Frame(card,bg=WHITE,padx=15,pady=13)
            content.pack(fill='both',expand=True)
            ttk.Label(content,text=title,style='EmployeeSection.TLabel').pack(anchor='w')
            ttk.Label(content,text=hint,style='EmployeeHint.TLabel').pack(
                anchor='w',pady=(2,10))
            fields_frame=ttk.Frame(content,style='EmployeeForm.TFrame')
            fields_frame.pack(fill='x')
            fields_frame.columnconfigure(0,weight=1)
            fields_frame.columnconfigure(1,weight=1)
            return fields_frame

        def add_field(parent,key,label,row,column=0,columnspan=1):
            field=ttk.Frame(parent,style='EmployeeForm.TFrame')
            field.grid(
                row=row,column=column,columnspan=columnspan,sticky='ew',
                padx=(0,10) if column==0 and columnspan==1 else 0,
                pady=(0,9))
            field.columnconfigure(0,weight=1)
            ttk.Label(field,text=label,style='EmployeeField.TLabel').pack(
                anchor='w',pady=(0,4))
            initial=(employee[key] or '') if employee else ''
            if key in ('birth_date','admission_date','dismissal_date'):
                initial=employee_date_for_form(initial)
            vs[key]=tk.StringVar(value=initial)
            entry=ttk.Entry(field,textvariable=vs[key])
            entry.pack(fill='x')
            return field

        identity=create_section(
            'Identificação','Informações principais do colaborador.',0,0,2)
        add_field(identity,'name','Nome completo *',0,columnspan=2)
        add_field(identity,'code','Código do colaborador',1,0)
        add_field(identity,'role','Cargo',1,1)
        add_field(identity,'sector','Setor',2,0)

        contact=create_section(
            'Contato','Canais para contato e comunicação.',1,0)
        add_field(contact,'email','E-mail',0,columnspan=2)
        phone_field=ttk.Frame(contact,style='EmployeeForm.TFrame')
        phone_field.grid(row=1,column=0,columnspan=2,sticky='ew',pady=(0,9))
        ttk.Label(
            phone_field,text='Telefone',style='EmployeeField.TLabel').pack(
                anchor='w',pady=(0,4))
        phone_ddd_var=tk.StringVar()
        phone_number_var=tk.StringVar()
        if employee:
            ddd,number=phone_parts(employee['phone'])
            phone_ddd_var.set(ddd)
            phone_number_var.set(number)
        phone_row=ttk.Frame(phone_field,style='EmployeeForm.TFrame')
        phone_row.pack(fill='x')
        ttk.Label(phone_row,text='DDD',style='EmployeeHint.TLabel').pack(
            side='left',padx=(0,6))
        ttk.Entry(phone_row,textvariable=phone_ddd_var,width=6).pack(side='left')
        ttk.Label(phone_row,text='Número',style='EmployeeHint.TLabel').pack(
            side='left',padx=(12,6))
        ttk.Entry(phone_row,textvariable=phone_number_var,width=20).pack(
            side='left',fill='x',expand=True)
        vs['pix']=tk.StringVar(value=(employee['pix'] or '') if employee else '')
        pix_field=ttk.Frame(contact,style='EmployeeForm.TFrame')
        pix_field.grid(row=2,column=0,columnspan=2,sticky='ew',pady=(0,9))
        ttk.Label(pix_field,text='Chave PIX',style='EmployeeField.TLabel').pack(
            anchor='w',pady=(0,4))
        ttk.Entry(pix_field,textvariable=vs['pix']).pack(fill='x')

        address=create_section(
            'Endereço','Localização residencial para cadastro.',1,1)
        add_field(address,'address','Endereço',0,columnspan=2)
        add_field(address,'address_number','Número',1,0)
        add_field(address,'bairro','Bairro',1,1)
        add_field(address,'cep','CEP',2,0)
        add_field(address,'city','Cidade',2,1)
        add_field(address,'state','Estado (UF)',3,0)

        documents=create_section(
            'Documentos e vínculo','Identificação civil e datas do vínculo.',2,0)
        add_field(documents,'cpf','CPF',0,0)
        add_field(documents,'ctps','CTPS',0,1)
        add_field(documents,'birth_date','Data de nascimento (DD/MM/AAAA)',1,0)
        add_field(documents,'admission_date','Data de admissão (DD/MM/AAAA)',1,1)
        add_field(documents,'dismissal_date','Data de demissão (DD/MM/AAAA)',2,0)

        bank=create_section(
            'Dados bancários','Informações de pagamento do colaborador.',2,1)
        add_field(bank,'bank','Banco',0,0)
        add_field(bank,'bank_agency','Agência',0,1)
        add_field(bank,'bank_account','Conta',1,0)

        buttons=ttk.Frame(body)
        buttons.pack(fill='x',pady=(12,0))
        ttk.Separator(body,orient='horizontal').pack(
            fill='x',before=buttons,pady=(8,0))
        ttk.Button(buttons,text='Cancelar',command=win.destroy).pack(side='left')
        def save():
            code=vs['code'].get().strip()
            name=vs['name'].get().strip()
            if not name: messagebox.showwarning('Campo obrigatório','Informe o nome.',parent=win);return
            try:
                dates={key:normalize_employee_date(vs[key].get()) for key in ('birth_date','admission_date','dismissal_date')}
            except ValueError as ex:
                messagebox.showwarning('Data inválida',str(ex),parent=win)
                return
            cep_digits=re.sub(r'\D','',vs['cep'].get())
            if cep_digits and len(cep_digits)!=8:
                messagebox.showwarning('CEP inválido','Informe o CEP com 8 dígitos.',parent=win)
                return
            cep=f'{cep_digits[:5]}-{cep_digits[5:]}' if cep_digits else ''
            cpf_digits=re.sub(r'\D','',vs['cpf'].get())
            if cpf_digits and len(cpf_digits)!=11:
                messagebox.showwarning('CPF inválido','Informe o CPF com 11 dígitos.',parent=win)
                return
            cpf=f'{cpf_digits[:3]}.{cpf_digits[3:6]}.{cpf_digits[6:9]}-{cpf_digits[9:]}' if cpf_digits else ''
            ddd=re.sub(r'\D','',phone_ddd_var.get())
            number=re.sub(r'\D','',phone_number_var.get())
            if bool(ddd)!=bool(number):
                messagebox.showwarning('Telefone incompleto','Informe o DDD e o número do telefone.',parent=win)
                return
            if ddd and (len(ddd)!=2 or not 10<=int(ddd)<=99 or len(number) not in (8,9)):
                messagebox.showwarning('Telefone inválido','Informe o DDD com 2 dígitos e o telefone com 8 ou 9 dígitos.',parent=win)
                return
            phone=format_phone(ddd+number) if ddd else ''
            try:
                with connect() as con:
                    values=(
                        name,vs['role'].get().strip(),vs['sector'].get().strip(),
                        vs['email'].get().strip(),phone,vs['pix'].get().strip(),code,
                        vs['address'].get().strip(),vs['address_number'].get().strip(),
                        vs['bairro'].get().strip(),cep,vs['city'].get().strip(),
                        vs['state'].get().strip(),vs['ctps'].get().strip(),
                        dates['birth_date'],cpf,dates['admission_date'],dates['dismissal_date'],
                        vs['bank'].get().strip(),vs['bank_agency'].get().strip(),
                        vs['bank_account'].get().strip())
                    if employee:
                        con.execute('''UPDATE employees SET
                            name=?,role=?,sector=?,email=?,phone=?,pix=?,code=?,address=?,address_number=?,bairro=?,cep=?,city=?,state=?,ctps=?,
                            birth_date=?,cpf=?,admission_date=?,dismissal_date=?,
                            bank=?,bank_agency=?,bank_account=? WHERE id=?''',(*values,employee_id))
                        con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',('Edição de colaborador',name))
                    else:
                        con.execute('''INSERT INTO employees(
                            name,role,sector,email,phone,pix,code,address,address_number,bairro,cep,city,state,ctps,
                            birth_date,cpf,admission_date,dismissal_date,bank,bank_agency,bank_account
                            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',values)
                        con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',('Cadastro de colaborador',name))
            except sqlite3.IntegrityError as ex:
                if 'employees.code' in str(ex):
                    messagebox.showerror('Código já cadastrado','Já existe um colaborador com esse código.',parent=win)
                    return
                messagebox.showerror('Nome já cadastrado','Já existe um colaborador com esse nome.',parent=win)
                return
            win.destroy();self.load_employees();self.load_salary_register();self.update_years()
        ttk.Button(buttons,text='Salvar alterações' if employee else 'Salvar',style='Accent.TButton',command=save).pack(side='right')

    def toggle_employee(self):
        tree=self.selected_employee_tree()
        sel=tree.selection()
        if not sel: messagebox.showinfo('Selecione','Selecione um colaborador.');return
        eid=int(sel[0])
        with connect() as con:
            r=con.execute('SELECT name,active FROM employees WHERE id=?',(eid,)).fetchone();new=0 if r['active'] else 1
            inactive_since='' if new else datetime.now().strftime('%Y-%m-01')
            con.execute('UPDATE employees SET active=?,inactive_since=? WHERE id=?',(new,inactive_since,eid));con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',('Situação de colaborador',f'{r["name"]}: {"Ativo" if new else "Inativo"}'))
        self.load_employees()
        self.load_salary_register()
        self.load_payroll()
        self.employee_tree_notebook.select(0 if new else 1)

    def delete_selected_employee(self):
        selection=self.selected_employee_tree().selection()
        if not selection:
            messagebox.showinfo('Selecione','Selecione um colaborador para excluir.',parent=self)
            return
        employee_id=int(selection[0])
        with connect() as con:
            employee=con.execute('SELECT id,name FROM employees WHERE id=?',(employee_id,)).fetchone()
        if not employee:
            messagebox.showerror('Colaborador não encontrado','Atualize a lista e tente novamente.',parent=self)
            self.load_employees()
            return
        if not messagebox.askyesno(
            'Confirmar exclusão',
            f'Deseja excluir permanentemente o cadastro de {employee["name"]}?\n\n'
            'A exclusão não pode ser desfeita. Colaboradores com histórico de folha, ano cadastrado '
            'ou empréstimo ou Meta não podem ser excluídos; nesse caso, use “Ativar / inativar selecionado”.',
            parent=self):
            return
        try:
            with connect() as con:
                current=con.execute('SELECT name FROM employees WHERE id=?',(employee_id,)).fetchone()
                if not current:
                    raise ValueError('O cadastro não existe mais. Atualize a lista e tente novamente.')
                dependencies=(
                    ('folhas',con.execute('SELECT COUNT(*) FROM payroll_items WHERE employee_id=?',(employee_id,)).fetchone()[0]),
                    ('anos cadastrados',con.execute('SELECT COUNT(*) FROM annual_employees WHERE employee_id=?',(employee_id,)).fetchone()[0]),
                    ('empréstimos',con.execute('SELECT COUNT(*) FROM employee_loans WHERE employee_id=?',(employee_id,)).fetchone()[0]),
                    ('lançamentos de Meta',con.execute('SELECT COUNT(*) FROM employee_meta_entries WHERE employee_id=?',(employee_id,)).fetchone()[0]),
                )
                linked=[f'{count} {label}' for label,count in dependencies if count]
                if linked:
                    raise ValueError(
                        f'{current["name"]} possui vínculo com {", ".join(linked)}. '
                        'Para preservar o histórico, esse cadastro não pode ser excluído; use “Ativar / inativar selecionado”.')
                con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',(
                    'Exclusão de colaborador',current['name']))
                con.execute('DELETE FROM employees WHERE id=?',(employee_id,))
        except (sqlite3.IntegrityError,ValueError) as ex:
            messagebox.showwarning('Não foi possível excluir',str(ex),parent=self)
            return
        self.load_employees()
        self.load_dashboard()
        messagebox.showinfo('Colaborador excluído',f'O cadastro de {employee["name"]} foi excluído.',parent=self)

    def new_year_dialog(self):
        win=tk.Toplevel(self);win.title('Configurar novo ano — manual');win.configure(bg=BG);win.transient(self);win.grab_set();win.geometry('850x650');win.minsize(760,520)
        outer=ttk.Frame(win,padding=18);outer.pack(fill='both',expand=True)
        ttk.Label(outer,text='Configurar um novo ano',font=('Segoe UI Semibold',17)).pack(anchor='w')
        ttk.Label(outer,text='Marque somente os colaboradores que entrarão no ano e informe o salário-base de cada um. Os 12 meses serão criados sem lançar variáveis/descontos.',style='Sub.TLabel').pack(anchor='w',pady=(4,12))
        line=ttk.Frame(outer);line.pack(fill='x',pady=(0,10));ttk.Label(line,text='Ano:').pack(side='left')
        year_var=tk.StringVar(value=str(max(2027,datetime.now().year)))
        ttk.Entry(line,textvariable=year_var,width=10).pack(side='left',padx=8)
        ttk.Label(line,text='Seleção manual e salários não serão copiados automaticamente de anos anteriores.',style='Sub.TLabel').pack(side='left',padx=8)
        holder=ttk.Frame(outer);holder.pack(fill='both',expand=True)
        canvas=tk.Canvas(holder,bg=BG,highlightthickness=0);scroll=ttk.Scrollbar(holder,orient='vertical',command=canvas.yview);inner=ttk.Frame(canvas)
        inner.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0,0),window=inner,anchor='nw');canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        ttk.Label(inner,text='Incluir',width=10).grid(row=0,column=0,sticky='w',padx=5,pady=5);ttk.Label(inner,text='Colaborador',width=30).grid(row=0,column=1,sticky='w',padx=5);ttk.Label(inner,text='Salário-base (R$)').grid(row=0,column=2,sticky='w',padx=5)
        with connect() as con: emps=con.execute('SELECT id,name,role,sector FROM employees WHERE active=1 ORDER BY name COLLATE NOCASE').fetchall()
        choices=[]
        for idx,e in enumerate(emps,1):
            bv=tk.BooleanVar(value=False);sv=tk.StringVar(value='0,00');choices.append((e,bv,sv))
            ttk.Checkbutton(inner,variable=bv).grid(row=idx,column=0,sticky='w',padx=10,pady=3)
            ttk.Label(inner,text=e['name']).grid(row=idx,column=1,sticky='w',padx=5,pady=3)
            ttk.Entry(inner,textvariable=sv,width=18).grid(row=idx,column=2,sticky='w',padx=5,pady=3)
        def save_year():
            try: year=int(year_var.get())
            except: messagebox.showerror('Ano inválido','Digite um ano válido.',parent=win);return
            selected=[]
            for e,bv,sv in choices:
                if bv.get():
                    try: salary=money(sv.get())
                    except ValueError: messagebox.showerror('Salário inválido',f'Confira o salário de {e["name"]}.',parent=win);return
                    if salary<0: messagebox.showerror('Salário inválido','O salário não pode ser negativo.',parent=win);return
                    selected.append((e,salary))
            if not selected: messagebox.showwarning('Seleção vazia','Marque pelo menos um colaborador.',parent=win);return
            with connect() as con:
                if con.execute('SELECT 1 FROM payrolls WHERE year=? LIMIT 1',(year,)).fetchone():
                    messagebox.showerror('Ano já existe',f'Já existe histórico de folha para {year}. Para preservar os registros, não é possível recriar esse ano por aqui.',parent=win);return
                for employee,salary in selected:
                    con.execute('''INSERT INTO employee_salary_history(
                        employee_id,salary,effective_year,effective_month)
                        VALUES(?,?,?,1)
                        ON CONFLICT(employee_id,effective_year,effective_month)
                        DO UPDATE SET salary=excluded.salary''',(employee['id'],salary,year))
                for month in range(1,13):
                    pid=con.execute('INSERT INTO payrolls(year,month,status) VALUES(?,?,?)',(year,month,'Em revisão')).lastrowid
                    for e,salary in selected:
                        con.execute('INSERT OR REPLACE INTO annual_employees(year,employee_id,salary_base,role,sector,active) VALUES(?,?,?,?,?,1)',(year,e['id'],salary,e['role'],e['sector']))
                        con.execute('INSERT INTO payroll_items(payroll_id,employee_id,salary,total,source) VALUES(?,?,?,?,?)',(pid,e['id'],salary,salary,'Ano novo'))
                con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',('Criação de novo ano',f'{year}: {len(selected)} colaboradores selecionados manualmente'))
            win.destroy();self.update_years();self.pay_year.set(str(year));self.update_months();self.pay_month.set(MONTHS[0]);self.load_payroll();self.load_dashboard()
            messagebox.showinfo('Ano criado',f'O ano {year} foi criado com 12 folhas em revisão e {len(selected)} colaborador(s). Os dados dos anos anteriores foram preservados.')
        buttons=ttk.Frame(outer);buttons.pack(fill='x',pady=(12,0));ttk.Button(buttons,text='Cancelar',command=win.destroy).pack(side='right',padx=(8,0));ttk.Button(buttons,text='Criar ano e 12 folhas',style='Accent.TButton',command=save_year).pack(side='right')

    def backup_db(self):
        stamp=datetime.now().strftime('%Y%m%d_%H%M%S');dest=os.path.join(BACKUP_DIR,f'folha_pagamento_{stamp}.db')
        self.create_backup(dest)

    def run_automatic_backup_if_due(self,now=None):
        now=now or datetime.now()
        temporary=None
        try:
            with connect() as con:
                row=con.execute(
                    "SELECT value FROM app_settings WHERE key='last_automatic_backup'"
                ).fetchone()
            if row:
                try:
                    last_backup=datetime.strptime(row['value'],'%Y-%m-%d %H:%M:%S')
                except ValueError as ex:
                    messagebox.showerror(
                        'Data de backup inválida',
                        f'Não foi possível verificar a data do último backup automático: {ex}',
                        parent=self)
                    return
                if now-last_backup<timedelta(days=30):
                    return
            os.makedirs(AUTO_BACKUP_DIR,exist_ok=True)
            destination=os.path.join(AUTO_BACKUP_DIR,'backup_folha.db')
            temporary=destination+'.tmp'
            if not self.create_backup(temporary,show_success=False):
                if os.path.exists(temporary):
                    os.remove(temporary)
                return
            os.replace(temporary,destination)
            temporary=None
            for name in os.listdir(AUTO_BACKUP_DIR):
                if name.startswith('backup_folha_') and name.endswith('.db'):
                    os.remove(os.path.join(AUTO_BACKUP_DIR,name))
            backup_time=now.strftime('%Y-%m-%d %H:%M:%S')
            with connect() as con:
                con.execute('''INSERT INTO app_settings(key,value)
                    VALUES('last_automatic_backup',?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value''',
                    (backup_time,))
                con.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',(
                    'Backup automático',
                    f'Backup criado em {destination}'))
        except (OSError,sqlite3.Error) as ex:
            cleanup_error=''
            if temporary and os.path.exists(temporary):
                try:
                    os.remove(temporary)
                except OSError as cleanup_ex:
                    cleanup_error=f'\nTambém não foi possível remover o arquivo temporário:\n{cleanup_ex}'
            messagebox.showerror(
                'Falha no backup automático',
                f'Não foi possível concluir ou registrar o backup automático:\n{ex}{cleanup_error}',
                parent=self)
            return
        messagebox.showinfo(
            'Backup automático concluído',
            f'Backup criado em:\n{destination}',
            parent=self)

    def show_backup_options(self,button):
        menu=tk.Menu(self,tearoff=False)
        menu.add_command(label='Criar backup agora',command=self.backup_db)
        menu.add_command(label='Salvar backup em outro local...',command=self.save_backup_as)
        menu.add_separator()
        menu.add_command(label='Abrir pasta de backups',command=self.open_backup_folder)
        menu.tk_popup(button.winfo_rootx(),button.winfo_rooty())

    def save_backup_as(self):
        stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
        destination=filedialog.asksaveasfilename(
            parent=self,title='Salvar cópia de segurança',
            initialdir=BACKUP_DIR,
            initialfile=f'folha_pagamento_{stamp}.db',
            defaultextension='.db',
            filetypes=[('Banco de dados SQLite','*.db')])
        if destination:
            self.create_backup(destination)

    def create_backup(self,destination,show_success=True):
        source=None
        target=None
        try:
            source=connect()
            target=sqlite3.connect(destination)
            source.backup(target)
            target.close()
            target=None
            source.close()
            source=None
            if show_success:
                messagebox.showinfo(
                    'Backup concluído',
                    f'Cópia de segurança criada em:\n{destination}',
                    parent=self)
            return True
        except (OSError,sqlite3.Error) as ex:
            messagebox.showerror('Falha no backup',str(ex),parent=self)
            return False
        finally:
            if target is not None:
                target.close()
            if source is not None:
                source.close()

    def open_backup_folder(self):
        try:
            if sys.platform.startswith('win'):
                os.startfile(BACKUP_DIR)
            elif sys.platform=='darwin':
                subprocess.Popen(['open',BACKUP_DIR])
            else:
                subprocess.Popen(['xdg-open',BACKUP_DIR])
        except (OSError,subprocess.SubprocessError) as ex:
            messagebox.showerror('Não foi possível abrir a pasta de backups',str(ex),parent=self)

    def change_password_dialog(self):
        win=tk.Toplevel(self);win.title('Alterar senha de acesso');win.configure(bg=BG);win.transient(self);win.grab_set();win.resizable(False,False)
        set_window_icon(win)
        body=ttk.Frame(win,padding=24);body.pack(fill='both',expand=True)
        ttk.Label(body,text='Alterar senha',font=('Segoe UI Semibold',15)).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,4))
        ttk.Label(
            body,text='Esta senha também é usada para entrar no Gerenciador Administrativo.',
            style='Sub.TLabel',wraplength=330,justify='left').grid(row=1,column=0,columnspan=2,sticky='w',pady=(0,10))
        current_var=tk.StringVar()
        new_var=tk.StringVar()
        confirm_var=tk.StringVar()
        entries=[]
        fields=(('Senha atual',current_var),(f'Nova senha (mínimo {PASSWORD_MIN_LENGTH} caracteres)',new_var),('Confirme a nova senha',confirm_var))
        for row,(label,var) in enumerate(fields,1):
            ttk.Label(body,text=label).grid(row=row*2,column=0,sticky='w',pady=(6,3),padx=(0,12))
            entry=ttk.Entry(body,textvariable=var,show='*',width=36)
            entry.grid(row=row*2+1,column=0,columnspan=2,sticky='ew',pady=(0,4),ipady=3)
            entries.append(entry)

        def save(event=None):
            if not verify_password(current_var.get()):
                messagebox.showerror('Senha incorreta','A senha atual não confere.',parent=win)
                current_var.set('')
                entries[0].focus_set()
                return
            if len(new_var.get())<PASSWORD_MIN_LENGTH:
                messagebox.showerror('Senha curta',f'A nova senha precisa ter pelo menos {PASSWORD_MIN_LENGTH} caracteres.',parent=win)
                return
            if new_var.get()!=confirm_var.get():
                messagebox.showerror('Senhas diferentes','A confirmação não confere com a nova senha.',parent=win)
                return
            save_password(new_var.get())
            win.destroy()
            messagebox.showinfo('Senha alterada','A senha de acesso foi atualizada.',parent=self)

        for entry in entries:
            entry.bind('<Return>',save)
        win.bind('<Escape>',lambda event:win.destroy())
        buttons=ttk.Frame(body);buttons.grid(row=8,column=0,columnspan=2,sticky='e',pady=(14,0))
        ttk.Button(buttons,text='Cancelar',command=win.destroy).pack(side='right',padx=(8,0))
        ttk.Button(buttons,text='Salvar senha',style='Accent.TButton',command=save).pack(side='right')
        win.update_idletasks()
        x=self.winfo_rootx()+max(0,(self.winfo_width()-win.winfo_reqwidth())//2)
        y=self.winfo_rooty()+max(0,(self.winfo_height()-win.winfo_reqheight())//3)
        win.geometry(f'+{x}+{y}')
        entries[0].focus_set()

    def selected_payroll_period(self):
        try:
            year=int(self.pay_year.get())
            month=MONTHS.index(self.pay_month.get())+1
        except (ValueError,tk.TclError):
            messagebox.showerror('Período inválido','Selecione um ano e um mês válidos.',parent=self)
            return None
        return year,month

    def payroll_report_rows(self,year,month):
        with connect() as con:
            self.apply_loan_installments(con,year,month)
            payroll=con.execute('SELECT * FROM payrolls WHERE year=? AND month=?',(year,month)).fetchone()
            if payroll is None:
                return None,None
            rows=con.execute('''SELECT e.name,i.employee_id,i.loan_override,i.loan_manual,
                i.salary,i.pf,i.overtime,i.vacation,i.meta,i.thirteenth,i.marmitex,
                i.advances,i.pharmacy,i.loan,i.other_deductions,i.total,i.notes
                FROM payroll_items i JOIN employees e ON e.id=i.employee_id
                WHERE i.payroll_id=? ORDER BY e.name COLLATE NOCASE''',(payroll['id'],)).fetchall()
            report_rows=[
                {**{key:row[key] for key in row.keys()},
                 'loan_installment':loan_installment_label(
                    con,row['employee_id'],year,month,row['loan'],row['loan_override'],row['loan_manual'])}
                for row in rows
            ]
        return payroll,report_rows

    def write_payroll_pdf(self,year,month,path):
        payroll,rows=self.payroll_report_rows(year,month)
        if payroll is None:
            raise ValueError(f'Não há folha criada para {MONTHS[month-1]} de {year}.')

        styles=getSampleStyleSheet()
        title_style=ParagraphStyle('PayrollTitle',parent=styles['Title'],fontName='Helvetica-Bold',fontSize=16,leading=20,textColor=colors.HexColor(NAVY),alignment=1,spaceAfter=4)
        subtitle_style=ParagraphStyle('PayrollSubtitle',parent=styles['Normal'],fontName='Helvetica',fontSize=9,textColor=colors.HexColor('#64748b'),alignment=1,spaceAfter=10)
        legend_style=ParagraphStyle('PayrollLegend',parent=subtitle_style,alignment=0,leading=20,spaceAfter=6)
        employee_style=ParagraphStyle('PayrollEmployee',parent=styles['Normal'],fontName='Helvetica',fontSize=7,leading=8)
        credit_color=colors.HexColor('#15803d')
        debit_color=colors.HexColor('#b91c1c')
        note_marker='<font color="#dc2626">&#8226;</font>'
        installment_style=ParagraphStyle('PayrollInstallment',parent=styles['Normal'],fontName='Helvetica',fontSize=6.5,leading=7,alignment=1,textColor=debit_color)
        header_style=ParagraphStyle('PayrollHeader',parent=styles['Normal'],fontName='Helvetica-Bold',fontSize=6.5,leading=7,textColor=colors.white,alignment=1)
        summary_style=ParagraphStyle('PayrollSummary',parent=styles['Normal'],fontName='Helvetica-Bold',fontSize=10,leading=14,textColor=colors.HexColor(NAVY))
        amount_font_size=6
        summary_value_style=ParagraphStyle('PayrollSummaryValue',parent=summary_style,fontSize=amount_font_size,leading=8)
        credit_summary_style=ParagraphStyle('PayrollCreditSummary',parent=summary_value_style,textColor=credit_color)
        debit_summary_style=ParagraphStyle('PayrollDebitSummary',parent=summary_value_style,textColor=debit_color)
        observation_name_font_size=7
        observation_text_font_size=15
        observation_style=ParagraphStyle('PayrollObservation',parent=employee_style,fontSize=9,leading=18,spaceAfter=8)
        total_value_style=ParagraphStyle('PayrollTotalValue',parent=credit_summary_style,alignment=1)
        generated=datetime.now().strftime('%d/%m/%Y %H:%M')
        page_size=landscape(A4)

        def draw_page(canvas,document):
            self.pdf_page_header(canvas,page_size,generated,document.page)

        document=SimpleDocTemplate(path,pagesize=page_size,rightMargin=12*mm,leftMargin=12*mm,topMargin=24*mm,bottomMargin=18*mm,title=f'Folha a pagar - {MONTHS[month-1]} {year}',author=AUTHOR)
        story=[
            Paragraph(
                '<font color="#15803d" size="20">&#8226;</font> Crédito'
                ' &nbsp;&nbsp; <font color="#b91c1c" size="20">&#8226;</font> Débito',
                legend_style),
            Paragraph(f'Folha a pagar - {MONTHS[month-1]} de {year}',title_style),
            Paragraph(f'Situação: {payroll["status"]} &nbsp;&nbsp; | &nbsp;&nbsp; Colaboradores: {len(rows)}',subtitle_style),
        ]
        has13=month in (11,12)
        earnings_keys=('salary','pf','overtime','vacation','meta')+(('thirteenth',) if has13 else ())
        deduction_keys=('marmitex','advances','pharmacy','loan','loan_installment','other_deductions','total')
        earnings_headers=['Salário','PF / adicional','Hora extra','Férias','Meta']+(['13º salário'] if has13 else [])
        deduction_headers=['Marmitex','Adiant. salarial','Farmácia','Empréstimo','Parcela / vale','Outros descontos','Líquido']
        payroll_headers=earnings_headers+deduction_headers
        payroll_keys=earnings_keys+deduction_keys
        payroll_data=[[Paragraph('Colaborador',header_style)]+[
            Paragraph(xml_escape(header),header_style) for header in payroll_headers
        ]]
        totals={key:0.0 for key in ('salary','pf','overtime','vacation','meta','thirteenth','marmitex','advances','pharmacy','loan','other_deductions','total')}
        for row in rows:
            marker=f' {note_marker}' if (row['notes'] or '').strip() else ''
            employee_data=[Paragraph(xml_escape(str(row['name']))+marker,employee_style)]
            employee_data.extend(
                Paragraph(xml_escape(str(row['loan_installment'])),installment_style)
                if key=='loan_installment'
                else brl(row[key]).replace('R$ ','')
                for key in payroll_keys
            )
            payroll_data.append(employee_data)
            for key in totals:
                totals[key]+=float(row[key] or 0)
        usable_width=page_size[0]-24*mm
        name_width=43*mm
        amount_width=(usable_width-name_width)/len(payroll_keys)
        payroll_table=LongTable(
            payroll_data,
            colWidths=[name_width]+[amount_width]*len(payroll_keys),
            repeatRows=1,
            hAlign='LEFT',
        )
        payroll_table.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#eff6ff')),
            ('BACKGROUND',(0,0),(-1,0),colors.HexColor(NAVY)),
            ('BACKGROUND',(1,0),(len(earnings_keys),0),credit_color),
            ('BACKGROUND',(len(earnings_keys)+1,0),(-2,0),debit_color),
            ('TEXTCOLOR',(0,0),(-1,0),colors.white),
            ('TEXTCOLOR',(1,1),(len(earnings_keys),-1),credit_color),
            ('TEXTCOLOR',(len(earnings_keys)+1,1),(-2,-1),debit_color),
            ('TEXTCOLOR',(-1,1),(-1,-1),credit_color),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
            ('FONTSIZE',(0,0),(-1,-1),amount_font_size),
            ('ALIGN',(1,1),(-1,-1),'CENTER'),
            ('FONTNAME',(-1,1),(-1,-1),'Helvetica-Bold'),
            ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('GRID',(0,0),(-1,-1),0.3,colors.HexColor('#dbe3ee')),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f3f6fb')]),
            ('LEFTPADDING',(0,0),(-1,-1),2),
            ('RIGHTPADDING',(0,0),(-1,-1),2),
            ('TOPPADDING',(0,0),(-1,-1),1.5),
            ('BOTTOMPADDING',(0,0),(-1,-1),1.5),
        ]))
        gross=sum(totals[key] for key in ('salary','pf','overtime','vacation','meta','thirteenth'))
        deductions=sum(totals[key] for key in ('marmitex','advances','pharmacy','loan','other_deductions'))
        summary=Table([
            [Paragraph(f'Total de proventos: {brl(gross)}',credit_summary_style),
             Paragraph(f'Total de descontos: {brl(deductions)}',debit_summary_style)],
            [Paragraph('TOTAL GERAL A PAGAR',summary_value_style),
             Paragraph(brl(totals['total']),total_value_style)],
        ],colWidths=[usable_width/2,usable_width/2])
        summary.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eff6ff')),
            ('BACKGROUND',(0,1),(-1,1),colors.HexColor('#dcfce7')),
            ('BOX',(0,0),(-1,-1),0.8,colors.HexColor('#86efac')),
            ('INNERGRID',(0,0),(-1,-1),0.35,colors.HexColor('#bbf7d0')),
            ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('ALIGN',(0,0),(-1,-1),'CENTER'),
            ('LEFTPADDING',(0,0),(-1,-1),8),
            ('RIGHTPADDING',(0,0),(-1,-1),8),
            ('TOPPADDING',(0,0),(-1,-1),3),
            ('BOTTOMPADDING',(0,0),(-1,-1),3),
        ]))
        story.extend([
            payroll_table,
            Spacer(1,8*mm),
            summary,
        ])
        noted_rows=[row for row in rows if (row['notes'] or '').strip()]
        if noted_rows:
            story.extend([
                Spacer(1,6*mm),
                Paragraph('Observações dos colaboradores',summary_style),
                Spacer(1,2*mm),
            ])
            for row in noted_rows:
                notes=xml_escape(row['notes'].strip()).replace('\n','<br/>')
                story.append(Paragraph(
                    f'{note_marker} <font size="{observation_name_font_size}"><b>'
                    f'{xml_escape(str(row["name"]))}</b></font><br/>'
                    f'<font size="{observation_text_font_size}">{notes}</font>',
                    observation_style))
        document.build(story,onFirstPage=draw_page,onLaterPages=draw_page,canvasmaker=NumberedReportCanvas)
        return totals['total']

    def generate_payroll_pdf_dialog(self):
        period=self.selected_payroll_period()
        if period is None:
            return
        year,month=period
        path=temporary_pdf_path(f'folha_a_pagar_{year}_{month:02d}_')
        try:
            total=self.write_payroll_pdf(year,month,path)
            open_pdf(path)
        except Exception as ex:
            messagebox.showerror(
                'Erro ao abrir relatório',
                f'Não foi possível gerar ou abrir o PDF: {ex}\n\nArquivo temporário: {path}',
                parent=self)
            return

    def pdf_page_header(self,canvas,page_size,generated,page=None,margin=12*mm):
        width,height=page_size
        navy=colors.HexColor(NAVY)
        canvas.saveState()
        canvas.drawImage(resource_path('logo_revisa.png'),margin,height-19*mm,width=36*mm,height=14*mm,preserveAspectRatio=True,anchor='sw',mask='auto')
        canvas.setFillColor(navy)
        canvas.setFont('Helvetica-Bold',11)
        canvas.drawString(margin+40*mm,height-11*mm,AUTHOR.upper())
        canvas.setFont('Helvetica',8)
        canvas.setFillColor(colors.HexColor('#64748b'))
        canvas.drawString(margin+40*mm,height-15.5*mm,'Departamento Pessoal  |  Folha de Pagamento')
        canvas.drawRightString(width-margin,height-11*mm,f'Impresso em {generated}')
        canvas.setStrokeColor(navy)
        canvas.setLineWidth(1.4)
        canvas.line(margin,height-21*mm,width-margin,height-21*mm)
        canvas.setLineWidth(0.4)
        canvas.line(margin,height-22.2*mm,width-margin,height-22.2*mm)
        canvas.setStrokeColor(colors.HexColor('#cbd5e1'))
        canvas.line(margin,12*mm,width-margin,12*mm)
        canvas.setFont('Helvetica',7)
        canvas.drawString(margin,8*mm,'Documento confidencial - uso administrativo')
        canvas.restoreState()

    def write_payslips_pdf(self,year,month,path,employee_id=None):
        payroll,rows=self.payroll_report_rows(year,month)
        if payroll is None:
            raise ValueError(f'Não há folha criada para {MONTHS[month-1]} de {year}.')
        if employee_id is not None:
            rows=[r for r in rows if r['employee_id']==employee_id]
        if not rows:
            raise ValueError('Nenhum lançamento encontrado para gerar o holerite.')
        with connect() as con:
            info={r['id']:r for r in con.execute('SELECT id,role,code,admission_date FROM employees')}
        styles=getSampleStyleSheet()
        title_style=ParagraphStyle('SlipTitle',parent=styles['Title'],fontName='Helvetica-Bold',fontSize=11,leading=13,textColor=colors.HexColor(NAVY),alignment=1,spaceAfter=2)
        subtitle_style=ParagraphStyle('SlipSubtitle',parent=styles['Normal'],fontName='Helvetica',fontSize=7.5,textColor=colors.HexColor('#64748b'),alignment=1,spaceAfter=5)
        small=ParagraphStyle('SlipSmall',parent=styles['Normal'],fontName='Helvetica',fontSize=6.5,leading=7)
        observation_style=ParagraphStyle('SlipObservation',parent=small,leading=8)
        generated=datetime.now().strftime('%d/%m/%Y %H:%M')
        page_size=portrait(A4)
        earnings=[('Salário','salary'),('PF / adicional','pf'),('Hora extra','overtime'),('Férias','vacation'),('13º salário','thirteenth')]
        deductions=[('Marmitex','marmitex'),('Adiantamento Salarial','advances'),('Farmácia','pharmacy'),('Empréstimo','loan'),('Outros descontos','other_deductions')]
        document=SimpleDocTemplate(path,pagesize=page_size,rightMargin=12*mm,leftMargin=12*mm,topMargin=24*mm,bottomMargin=18*mm,title=f'Holerite - {MONTHS[month-1]} {year}',author=AUTHOR)
        story=[]
        for index,row in enumerate(rows):
            emp=info.get(row['employee_id'])
            installment_descriptions={LOAN_KIND:[],ADVANCE_KIND:[]}
            with connect() as con:
                for kind in LOAN_KINDS:
                    installment_descriptions[kind]=[
                        f'{number}/{count}: {brl(amount)}'
                        for number,count,amount in loan_installment_details(
                            con,row['employee_id'],year,month,kind)]
                settlements=con.execute(
                    '''SELECT kind,settlement_amount FROM employee_loans
                    WHERE employee_id=? AND settled_year=? AND settled_month=?
                    AND settlement_amount>0 ORDER BY id''',
                    (row['employee_id'],year,month)).fetchall()
                for settlement in settlements:
                    installment_descriptions[settlement['kind']].append(
                        f'Quitação: {brl(settlement["settlement_amount"])}')
            lines=[['Descrição','Proventos','Descontos']]
            for label,key in earnings:
                if float(row[key] or 0) or key=='salary':
                    lines.append([label,brl(row[key]),''])
            for label,key in deductions:
                if float(row[key] or 0):
                    text=label
                    if key in ('loan','advances'):
                        kind=LOAN_KIND if key=='loan' else ADVANCE_KIND
                        details=installment_descriptions[kind]
                        if details:
                            text=Paragraph(
                                f'{xml_escape(label)}<br/>'
                                +f'<font size="{small.fontSize-1}">'
                                +' | '.join(xml_escape(detail) for detail in details)
                                +'</font>',
                                small)
                    lines.append([text,'',brl(row[key])])
            total_earnings=sum(float(row[k] or 0) for _,k in earnings)
            total_deductions=sum(float(row[k] or 0) for _,k in deductions)
            lines.append(['Totais',brl(total_earnings),brl(total_deductions)])
            head=Table([[
                Paragraph(f'<b>Colaborador</b><br/>{xml_escape(str(row["name"]))}',small),
                Paragraph(f'<b>Cargo</b><br/>{xml_escape(str((emp["role"] if emp else "") or "—"))}',small),
                Paragraph(f'<b>Matrícula</b><br/>{xml_escape(str((emp["code"] if emp else "") or "—"))}',small),
                Paragraph(f'<b>Admissão</b><br/>{xml_escape(str((emp["admission_date"] if emp else "") or "—"))}',small),
            ]],colWidths=[74*mm,50*mm,28*mm,34*mm])
            head.setStyle(TableStyle([
                ('BOX',(0,0),(-1,-1),0.6,colors.HexColor('#cbd5e1')),
                ('INNERGRID',(0,0),(-1,-1),0.3,colors.HexColor('#dbe3ee')),
                ('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#eff6ff')),
                ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                ('TOPPADDING',(0,0),(-1,-1),1.5),('BOTTOMPADDING',(0,0),(-1,-1),1.5),
            ]))
            table=Table(lines,colWidths=[100*mm,43*mm,43*mm])
            table.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,0),colors.HexColor(NAVY)),
                ('TEXTCOLOR',(0,0),(-1,0),colors.white),
                ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
                ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),
                ('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#eff6ff')),
                ('FONTSIZE',(0,0),(-1,-1),6.5),
                ('ALIGN',(1,0),(-1,-1),'CENTER'),
                ('GRID',(0,0),(-1,-1),0.3,colors.HexColor('#dbe3ee')),
                ('TOPPADDING',(0,0),(-1,-1),1),('BOTTOMPADDING',(0,0),(-1,-1),1),
                ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                ('LEADING',(0,0),(-1,-1),7.5),
            ]))
            net=Table([[Paragraph('LÍQUIDO A RECEBER',ParagraphStyle('SlipNetLabel',parent=small,fontName='Helvetica-Bold',fontSize=6.5)),
                        Paragraph(brl(row['total']),ParagraphStyle('SlipNet',parent=small,fontName='Helvetica-Bold',fontSize=8.5,textColor=colors.HexColor('#15803d'),alignment=1))]],
                      colWidths=[100*mm,86*mm])
            net.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#dcfce7')),
                ('BOX',(0,0),(-1,-1),0.8,colors.HexColor('#86efac')),
                ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                ('LEFTPADDING',(0,0),(-1,-1),6),
                ('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3),
            ]))
            story.extend([
                Paragraph('Cálculo Folha de Pagamento',title_style),
                Paragraph(f'Competência: {MONTHS[month-1]} de {year}',subtitle_style),
                head,Spacer(1,2*mm),table,Spacer(1,2*mm),net,
            ])
            notes=(row['notes'] or '').strip()
            if notes:
                observation=Table([[
                    Paragraph(
                        f'<b>Observações do colaborador</b><br/>'
                        f'{xml_escape(notes).replace(chr(10), "<br/>")}',
                        observation_style)
                ]],colWidths=[186*mm])
                observation.setStyle(TableStyle([
                    ('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#fff7ed')),
                    ('BOX',(0,0),(-1,-1),0.5,colors.HexColor('#fed7aa')),
                    ('LEFTPADDING',(0,0),(-1,-1),4),
                    ('RIGHTPADDING',(0,0),(-1,-1),4),
                    ('TOPPADDING',(0,0),(-1,-1),2),
                    ('BOTTOMPADDING',(0,0),(-1,-1),2),
                ]))
                story.extend([Spacer(1,2*mm),observation])
            loan_lines=[['Valor emprestado','Qtd. parcelas','Parcela atual','Valor da parcela','Parcelas restantes','Saldo restante']]
            with connect() as con:
                for loan in con.execute('SELECT * FROM employee_loans WHERE employee_id=? ORDER BY id',(row['employee_id'],)).fetchall():
                    if loan['settled_year'] is not None:
                        settled_period=(loan['settled_year'],loan['settled_month'])
                        if (year,month)==settled_period:
                            loan_lines.append([
                                brl(loan['principal']),str(loan['installment_count']),
                                f'Quitado {loan["settled_month"]:02d}/{loan["settled_year"]}',
                                brl(loan['settlement_amount']), '0', brl(0)])
                        if (year,month)>=settled_period:
                            continue
                    principal,count,elapsed,_,_=loan_terms_for_month(con,loan,year,month)
                    if 0<=elapsed<count:
                        number=elapsed+1
                        balance=sum(loan_installment(principal,count,n) for n in range(number+1,count+1))
                        loan_lines.append([brl(principal),str(count),f'{number}/{count}',brl(loan_installment(principal,count,number)),str(count-number),brl(balance)])
            if len(loan_lines)>1:
                loan_table=Table(loan_lines,colWidths=[31*mm,26*mm,28*mm,34*mm,34*mm,33*mm])
                loan_table.setStyle(TableStyle([
                    ('BACKGROUND',(0,0),(-1,0),colors.HexColor(NAVY)),
                    ('TEXTCOLOR',(0,0),(-1,0),colors.white),
                    ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
                    ('FONTSIZE',(0,0),(-1,-1),6.5),
                    ('ALIGN',(0,0),(-1,-1),'CENTER'),
                    ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                    ('GRID',(0,0),(-1,-1),0.3,colors.HexColor('#dbe3ee')),
                    ('TOPPADDING',(0,0),(-1,-1),1),('BOTTOMPADDING',(0,0),(-1,-1),1),
                ]))
                story.extend([Spacer(1,2.5*mm),Paragraph('Empréstimos e adiantamentos',ParagraphStyle('SlipLoanTitle',parent=small,fontName='Helvetica-Bold',fontSize=7.5,textColor=colors.HexColor(NAVY))),Spacer(1,0.5*mm),loan_table])
            if index<len(rows)-1:
                story.append(PageBreak())
        document.build(story,onFirstPage=lambda c,d:self.pdf_page_header(c,page_size,generated,d.page),onLaterPages=lambda c,d:self.pdf_page_header(c,page_size,generated,d.page),canvasmaker=NumberedReportCanvas)
        return len(rows)

    def generate_payslips_dialog(self):
        period=self.selected_payroll_period()
        if period is None:
            return
        year,month=period
        with connect() as con:
            employees=con.execute(
                '''SELECT e.id,e.name FROM payroll_items i
                JOIN employees e ON e.id=i.employee_id
                JOIN payrolls p ON p.id=i.payroll_id
                WHERE p.year=? AND p.month=?
                ORDER BY e.name COLLATE NOCASE''',(year,month)).fetchall()
        if not employees:
            messagebox.showinfo(
                'Sem lançamentos','Não há colaboradores lançados nesta competência.',
                parent=self)
            return
        win=tk.Toplevel(self)
        win.title('Holerites (PDF)')
        win.transient(self)
        win.grab_set()
        body=ttk.Frame(win,padding=20)
        body.pack(fill='both',expand=True)
        ttk.Label(
            body,text=f'Holerites — {MONTHS[month-1]} de {year}',
            font=('Segoe UI Semibold',12)).pack(anchor='w',pady=(0,12))
        ttk.Label(body,text='Colaborador:').pack(anchor='w',pady=(0,4))
        choice=ttk.Combobox(
            body,state='readonly',width=48,
            values=['Todos os colaboradores']+[e['name'] for e in employees])
        choice.current(0)
        choice.pack(fill='x')

        def generate():
            index=choice.current()
            if not 0<=index<=len(employees):
                messagebox.showwarning(
                    'Selecione','Selecione um colaborador ou todos.',parent=win)
                return
            employee_id=None if index==0 else employees[index-1]['id']
            try:
                path=temporary_pdf_path(f'holerites_{year}_{month:02d}_')
                self.write_payslips_pdf(year,month,path,employee_id)
                open_pdf(path)
            except Exception as ex:
                messagebox.showerror(
                    'Erro ao gerar holerite',
                    f'Não foi possível gerar ou abrir o PDF: {ex}',parent=win)
                return
            win.destroy()

        controls=ttk.Frame(body)
        controls.pack(fill='x',pady=(16,0))
        ttk.Button(
            controls,text='Cancelar',command=win.destroy).pack(side='right',padx=(8,0))
        ttk.Button(
            controls,text='Gerar PDF',style='Report.TButton',
            command=generate).pack(side='right')

    def send_payslip_whatsapp_dialog(self):
        period=self.selected_payroll_period()
        if period is None:
            return
        selection=self.pay_tree.selection()
        if not selection:
            messagebox.showinfo(
                'Selecione um colaborador',
                'Selecione o colaborador na folha para preparar o holerite.',
                parent=self)
            return
        year,month=period
        with connect() as con:
            employee=con.execute(
                '''SELECT i.employee_id,e.name,e.phone
                FROM payroll_items i
                JOIN payrolls p ON p.id=i.payroll_id
                JOIN employees e ON e.id=i.employee_id
                WHERE i.id=? AND p.year=? AND p.month=?''',
                (int(selection[0]),year,month)).fetchone()
        if not employee:
            messagebox.showwarning(
                'Lançamento não encontrado',
                'O lançamento selecionado não pertence à competência atual. Atualize a folha e tente novamente.',
                parent=self)
            return
        try:
            chat_url=whatsapp_chat_url(
                employee['phone'],employee['name'],year,month)
        except ValueError as ex:
            messagebox.showwarning(
                'Telefone inválido',
                f'{ex}\n\nConfira o telefone do colaborador no cadastro.',
                parent=self)
            return
        safe_name=re.sub(r'[<>:"/\\|?*]+','_',employee['name']).strip(' .')
        path=filedialog.asksaveasfilename(
            parent=self,
            title='Salvar holerite para enviar pelo WhatsApp',
            initialfile=f'Holerite_{safe_name}_{month:02d}_{year}.pdf',
            defaultextension='.pdf',
            filetypes=[('Arquivo PDF','*.pdf')])
        if not path:
            return
        try:
            self.write_payslips_pdf(
                year,month,path,employee['employee_id'])
            open_pdf(path)
            open_whatsapp_desktop(chat_url)
            show_file_in_folder(path)
        except Exception as ex:
            messagebox.showerror(
                'Erro ao preparar envio',
                f'Não foi possível preparar o holerite ou abrir o WhatsApp: {ex}\n\n'
                f'O arquivo, se já foi gerado, está em:\n{path}',
                parent=self)
            return
        messagebox.showinfo(
            'Holerite pronto',
            'A conversa do colaborador foi aberta no WhatsApp e o PDF foi salvo.\n\n'
            'O PDF está selecionado na pasta. Arraste-o para a conversa, confira o destinatário e confirme o envio. '
            'O programa não envia a mensagem sem sua confirmação.',
            parent=self)

    def send_payslips_whatsapp_batch_dialog(self):
        period=self.selected_payroll_period()
        if period is None:
            return
        year,month=period
        with connect() as con:
            payroll=con.execute(
                'SELECT id FROM payrolls WHERE year=? AND month=?',
                (year,month)).fetchone()
            if not payroll:
                messagebox.showinfo(
                    'Sem folha',
                    'Não há folha cadastrada para esta competência.',
                    parent=self)
                return
            employees=con.execute(
                '''SELECT e.id,e.name,e.phone
                FROM payroll_items i JOIN employees e ON e.id=i.employee_id
                WHERE i.payroll_id=?
                ORDER BY e.name COLLATE NOCASE''',
                (payroll['id'],)).fetchall()
        if not employees:
            messagebox.showinfo(
                'Folha sem lançamentos',
                'Não há colaboradores lançados nesta folha.',
                parent=self)
            return

        win=tk.Toplevel(self)
        win.title('Salvar holerites em massa')
        win.configure(bg=BG)
        win.transient(self)
        win.grab_set()
        win.geometry('620x480')
        win.minsize(520,360)
        body=ttk.Frame(win,padding=16)
        body.pack(fill='both',expand=True)
        body.columnconfigure(0,weight=1)
        body.rowconfigure(2,weight=1)
        ttk.Label(
            body,
            text=f'Selecione os colaboradores — {MONTHS[month-1]} de {year}',
            font=('Segoe UI Semibold',12)).grid(row=0,column=0,sticky='w',pady=(0,4))
        ttk.Label(
            body,
            text='Um PDF por pessoa na pasta Relatorios ZAP.\n'
            'Use Ctrl ou Shift para selecionar vários colaboradores.',
            wraplength=460,style='Sub.TLabel').grid(row=1,column=0,sticky='ew',pady=(0,10))

        table_frame=ttk.Frame(body)
        table_frame.grid(row=2,column=0,sticky='nsew')
        tree=ttk.Treeview(
            table_frame,columns=('name','phone'),show='headings',
            selectmode='extended')
        tree.heading('name',text='Colaborador')
        tree.heading('phone',text='WhatsApp / telefone')
        tree.column('name',width=330,anchor='w')
        tree.column('phone',width=180,anchor='w')
        scrollbar=ttk.Scrollbar(
            table_frame,orient='vertical',command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side='left',fill='both',expand=True)
        scrollbar.pack(side='right',fill='y')
        for employee in employees:
            tree.insert(
                '', 'end', iid=str(employee['id']),
                values=(employee['name'],format_phone(employee['phone'])))

        def select_all_employees():
            tree.selection_set(tree.get_children())

        controls=ttk.Frame(body)
        controls.grid(row=3,column=0,sticky='ew',pady=(10,0))
        ttk.Button(
            controls,text='Selecionar todos',
            command=select_all_employees).pack(side='left')

        def prepare_batch():
            selected_ids=set(tree.selection())
            selected=[employee for employee in employees
                      if str(employee['id']) in selected_ids]
            if not selected:
                messagebox.showinfo(
                    'Selecione colaboradores',
                    'Marque pelo menos um colaborador.',
                    parent=win)
                return
            try:
                os.makedirs(ZAP_REPORTS_DIR,exist_ok=True)
                folder=tempfile.mkdtemp(
                    prefix=f'Holerites_{year}_{month:02d}_',dir=ZAP_REPORTS_DIR)
            except OSError as ex:
                messagebox.showerror(
                    'Erro ao criar pasta',str(ex),parent=win)
                return
            generated=[]
            errors=[]
            for employee in selected:
                safe_name=re.sub(
                    r'[<>:"/\\|?*]+','_',employee['name']).strip(' .')
                path=os.path.join(
                    folder,
                    f'Holerite_{safe_name}_{employee["id"]}_{month:02d}_{year}.pdf')
                try:
                    self.write_payslips_pdf(
                        year,month,path,employee['id'])
                except Exception as ex:
                    errors.append(f'{employee["name"]}: {ex}')
                else:
                    generated.append((employee,path))
            if errors:
                messagebox.showwarning(
                    'Alguns holerites não foram gerados',
                    'Não foi possível gerar:\n'+'\n'.join(errors),
                    parent=win)
            if not generated:
                return
            win.destroy()
            self.saved_payslips_whatsapp_dialog(year,month,generated)

        ttk.Button(
            controls,text='Cancelar',command=win.destroy).pack(side='right',padx=(8,0))
        ttk.Button(
            controls,text='Salvar PDFs',style='Accent.TButton',
            command=prepare_batch).pack(side='right')

    def saved_payslips_whatsapp_dialog(self,year,month,generated):
        win=tk.Toplevel(self)
        win.title(f'Holerites salvos — {month:02d}/{year}')
        win.transient(self)
        win.geometry('860x480')
        win.minsize(680,360)
        body=ttk.Frame(win,padding=16)
        body.pack(fill='both',expand=True)
        body.columnconfigure(0,weight=1)
        body.rowconfigure(3,weight=1)
        ttk.Label(
            body,text=f'{len(generated)} holerite(s) salvo(s)',
            font=('Segoe UI Semibold',14)).grid(row=0,column=0,sticky='w')
        instructions=ttk.Label(
            body,text='Selecione o colaborador e clique em Abrir WhatsApp do selecionado.\n'
            'Anexe e envie o PDF no WhatsApp; depois clique em Próximo colaborador para continuar.',
            wraplength=620,style='Sub.TLabel')
        instructions.grid(row=1,column=0,sticky='ew',pady=(6,12))
        body.bind(
            '<Configure>',
            lambda event:instructions.configure(wraplength=max(200,event.width-32)))
        table=ttk.Frame(body)
        table.grid(row=3,column=0,sticky='nsew',pady=(10,0))
        tree=ttk.Treeview(
            table,columns=('name','phone','file'),show='headings',selectmode='browse')
        tree.heading('name',text='Colaborador')
        tree.heading('phone',text='WhatsApp cadastrado')
        tree.heading('file',text='PDF individual')
        tree.column('name',width=230)
        tree.column('phone',width=160)
        tree.column('file',width=370)
        scroll=ttk.Scrollbar(table,orient='vertical',command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side='left',fill='both',expand=True)
        scroll.pack(side='right',fill='y')
        for index,(employee,path) in enumerate(generated):
            tree.insert(
                '','end',iid=str(index),
                values=(employee['name'],format_phone(employee['phone']),
                        os.path.basename(path)))
        tree.selection_set('0')
        folder=os.path.dirname(generated[0][1])
        folder_row=ttk.Frame(body)
        folder_row.grid(row=4,column=0,sticky='ew',pady=(8,0))
        ttk.Label(folder_row,text='Pasta:').pack(side='left',padx=(0,6))
        folder_var=tk.StringVar(master=win,value=folder)
        ttk.Entry(
            folder_row,textvariable=folder_var,state='readonly'
        ).pack(side='left',fill='x',expand=True)

        last_opened_index=None

        def open_selected(with_whatsapp):
            nonlocal last_opened_index
            selection=tree.selection()
            if not selection:
                messagebox.showinfo(
                    'Selecione','Selecione um colaborador na lista.',parent=win)
                return
            index=int(selection[0])
            employee,path=generated[index]
            try:
                if not os.path.isfile(path):
                    raise FileNotFoundError(f'O PDF não foi encontrado:\n{path}')
                if with_whatsapp:
                    chat_url=whatsapp_chat_url(
                        employee['phone'],employee['name'],year,month)
                    open_whatsapp_desktop(chat_url)
                show_file_in_folder(path)
                if with_whatsapp:
                    last_opened_index=index
            except (OSError,ValueError,RuntimeError) as ex:
                messagebox.showerror(
                    'Não foi possível preparar o envio',str(ex),parent=win)

        def open_next():
            index=0 if last_opened_index is None else last_opened_index+1
            if index>=len(generated):
                messagebox.showinfo(
                    'Fim da lista',
                    'Você chegou ao último colaborador. Confira os envios no WhatsApp; '
                    'o programa não confirma se as mensagens foram enviadas.',
                    parent=win)
                return
            tree.selection_set(str(index))
            tree.see(str(index))
            open_selected(True)

        controls=ttk.Frame(body)
        controls.grid(row=2,column=0,sticky='ew')
        ttk.Button(
            controls,text='Localizar PDF',
            command=lambda:open_selected(False)).grid(row=0,column=0,sticky='w')
        ttk.Button(
            controls,text='Abrir WhatsApp do selecionado',
            style='WhatsApp.TButton',
            command=lambda:open_selected(True)).grid(row=0,column=1,sticky='w',padx=8)
        ttk.Button(
            controls,text='Próximo colaborador',
            style='WhatsApp.TButton',
            command=open_next).grid(row=1,column=1,sticky='w',padx=8,pady=(6,0))
        ttk.Button(
            controls,text='Fechar',command=win.destroy).grid(row=1,column=0,sticky='w',pady=(6,0))

    def write_annual_report_pdf(self,year,path,employee_id=None):
        fields=[('Salário','salary'),('PF / adicional','pf'),('Hora extra','overtime'),('Férias','vacation'),('13º salário','thirteenth'),
                ('Marmitex','marmitex'),('Adiantamento Salarial','advances'),('Farmácia','pharmacy'),('Empréstimo','loan'),
                ('Outros descontos','other_deductions'),('Líquido','total')]
        with connect() as con:
            query='''SELECT DISTINCT e.id,e.name,e.role,e.code FROM employees e
                JOIN payroll_items i ON i.employee_id=e.id JOIN payrolls p ON p.id=i.payroll_id
                WHERE p.year=?'''
            args=[year]
            if employee_id is not None:
                query+=' AND e.id=?';args.append(employee_id)
            employees=con.execute(query+' ORDER BY e.name COLLATE NOCASE',args).fetchall()
            items={(r['employee_id'],r['month']):r for r in con.execute(
                '''SELECT p.month,i.* FROM payroll_items i JOIN payrolls p ON p.id=i.payroll_id
                WHERE p.year=?''',(year,))}
        if not employees:
            raise ValueError(f'Não há lançamentos em {year} para gerar o relatório.')
        styles=getSampleStyleSheet()
        title_style=ParagraphStyle('AnnualTitle',parent=styles['Title'],fontName='Helvetica-Bold',fontSize=16,leading=20,textColor=colors.HexColor(NAVY),alignment=1,spaceAfter=4)
        subtitle_style=ParagraphStyle('AnnualSubtitle',parent=styles['Normal'],fontName='Helvetica',fontSize=9,textColor=colors.HexColor('#64748b'),alignment=1,spaceAfter=10)
        summary_style=ParagraphStyle('AnnualSummary',parent=styles['Normal'],fontName='Helvetica-Bold',fontSize=10,leading=14,textColor=colors.HexColor(NAVY),alignment=1)
        generated=datetime.now().strftime('%d/%m/%Y %H:%M')
        page_size=landscape(A4) if employee_id is None else portrait(A4)
        fmt=lambda v:brl(v).replace('R$ ','') if v else '–'
        document=SimpleDocTemplate(path,pagesize=page_size,rightMargin=12*mm,leftMargin=12*mm,topMargin=24*mm,bottomMargin=18*mm,title=f'Relatório anual {year}',author=AUTHOR)
        story=[]
        if employee_id is None:
            head_style=ParagraphStyle('AnnualAllHead',parent=styles['Normal'],fontName='Helvetica-Bold',fontSize=7,leading=8,textColor=colors.white,alignment=1)
            name_style=ParagraphStyle('AnnualAllName',parent=styles['Normal'],fontName='Helvetica',fontSize=7.5,leading=9)
            data=[[Paragraph('Colaborador',head_style)]+[Paragraph(label,head_style) for label,_ in fields]]
            sums={key:0.0 for _,key in fields}
            for emp in employees:
                line=[Paragraph(xml_escape(str(emp['name'])),name_style)]
                for _,key in fields:
                    value=sum(float(items[(emp['id'],m)][key] or 0) for m in range(1,13) if (emp['id'],m) in items)
                    sums[key]+=value
                    line.append(fmt(value))
                data.append(line)
            data.append(['TOTAL']+[fmt(sums[key]) for _,key in fields])
            table=Table(data,colWidths=[48*mm]+[18.6*mm]*len(fields),repeatRows=1,hAlign='LEFT')
            table.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,0),colors.HexColor(NAVY)),
                ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),
                ('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#dcfce7')),
                ('ROWBACKGROUNDS',(0,1),(-1,-2),[colors.white,colors.HexColor('#f3f6fb')]),
                ('FONTSIZE',(0,0),(-1,-1),7.5),
                ('ALIGN',(1,0),(-1,-1),'CENTER'),
                ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                ('GRID',(0,0),(-1,-1),0.3,colors.HexColor('#dbe3ee')),
                ('LEFTPADDING',(0,0),(-1,-1),2),('RIGHTPADDING',(0,0),(-1,-1),2),
                ('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3),
            ]))
            story.extend([
                Paragraph(f'Relatório anual - {year}',title_style),
                Paragraph(f'Soma do ano todo &nbsp;|&nbsp; Colaboradores: {len(employees)}',subtitle_style),
                table,
            ])
            document.build(story,onFirstPage=lambda c,d:self.pdf_page_header(c,page_size,generated,d.page),onLaterPages=lambda c,d:self.pdf_page_header(c,page_size,generated,d.page),canvasmaker=NumberedReportCanvas)
            return len(employees)
        for index,emp in enumerate(employees):
            header=['']+[m[:3] for m in MONTHS]+['Total']
            data=[header]
            thirteenth=sum(float(items[(emp['id'],m)]['thirteenth'] or 0) for m in range(1,13) if (emp['id'],m) in items)
            year_net=0.0
            for label,key in fields:
                values=[float(items[(emp['id'],m)][key] or 0) if (emp['id'],m) in items else 0.0 for m in range(1,13)]
                total=sum(values)
                if key=='total':
                    year_net=total
                data.append([label]+[fmt(v) for v in values]+[fmt(total)])
            table=Table(data,colWidths=[24*mm]+[11.8*mm]*12+[20*mm],repeatRows=1)
            table.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,0),colors.HexColor(NAVY)),
                ('TEXTCOLOR',(0,0),(-1,0),colors.white),
                ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
                ('FONTNAME',(0,1),(0,-1),'Helvetica-Bold'),
                ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),
                ('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#dcfce7')),
                ('ROWBACKGROUNDS',(0,1),(-1,-2),[colors.white,colors.HexColor('#f3f6fb')]),
                ('FONTSIZE',(0,0),(-1,-1),5.8),
                ('ALIGN',(1,0),(-1,-1),'CENTER'),
                ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                ('GRID',(0,0),(-1,-1),0.3,colors.HexColor('#dbe3ee')),
                ('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3),
                ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
            ]))
            summary=Table([[Paragraph(
                f'Líquido do ano: {brl(year_net)} &nbsp;&nbsp;|&nbsp;&nbsp; 13º salário no ano: {brl(thirteenth)}',
                summary_style)]],colWidths=[186*mm])
            summary.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#eff6ff')),
                ('BOX',(0,0),(-1,-1),0.8,colors.HexColor('#bfdbfe')),
                ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),
            ]))
            detail=' | '.join(x for x in (str(emp['role'] or ''),f'Matrícula {emp["code"]}' if emp['code'] else '') if x)
            story.extend([
                Paragraph(f'Relatório anual - {xml_escape(str(emp["name"]))}',title_style),
                Paragraph(f'Ano {year}'+(f' &nbsp;|&nbsp; {xml_escape(detail)}' if detail else ''),subtitle_style),
                table,Spacer(1,8*mm),summary,
            ])
            if index<len(employees)-1:
                story.append(PageBreak())
        document.build(story,onFirstPage=lambda c,d:self.pdf_page_header(c,page_size,generated,d.page),onLaterPages=lambda c,d:self.pdf_page_header(c,page_size,generated,d.page),canvasmaker=NumberedReportCanvas)
        return len(employees)

    def generate_annual_report_dialog(self):
        with connect() as con:
            years=[str(r['year']) for r in con.execute('SELECT DISTINCT year FROM payrolls ORDER BY year DESC')]
            employees=con.execute('SELECT id,name FROM employees ORDER BY active DESC,name COLLATE NOCASE').fetchall()
        if not years:
            messagebox.showinfo('Sem dados','Não há folhas criadas.',parent=self)
            return
        win=tk.Toplevel(self);win.title('R$  Relatório anual (PDF)');win.transient(self);win.resizable(False,False);set_window_icon(win)
        body=ttk.Frame(win,padding=18);body.pack(fill='both',expand=True)
        ttk.Label(body,text='Ano').pack(anchor='w')
        year_box=ttk.Combobox(body,values=years,state='readonly',width=32);year_box.pack(anchor='w',pady=(4,10))
        year_box.set(self.pay_year.get() if self.pay_year.get() in years else years[0])
        ttk.Label(body,text='Colaborador').pack(anchor='w')
        names=['Todos os colaboradores']+[e['name'] for e in employees]
        employee_box=ttk.Combobox(body,values=names,state='readonly',width=32);employee_box.pack(anchor='w',pady=(4,14))
        employee_box.set(names[0])
        def generate():
            index=employee_box.current()
            employee_id=None if index<=0 else employees[index-1]['id']
            path=temporary_pdf_path(f'relatorio_anual_{year_box.get()}_')
            try:
                self.write_annual_report_pdf(int(year_box.get()),path,employee_id)
                open_pdf(path)
            except Exception as ex:
                messagebox.showerror('Erro ao gerar relatório',f'Não foi possível gerar ou abrir o PDF: {ex}',parent=win)
                return
            win.destroy()
        buttons=ttk.Frame(body);buttons.pack(fill='x')
        ttk.Button(buttons,text='Cancelar',command=win.destroy).pack(side='right',padx=(8,0))
        ttk.Button(buttons,text='Gerar PDF',style='Report.TButton',command=generate).pack(side='right')
        win.grab_set()

    def write_employee_report_pdf(self,path,report_type,employee_id=None):
        report_columns={
            'pix':(
                'Relatório de PIX',
                ('Código','Colaborador','Chave PIX'),
                ('code','name','pix'),
                (22*mm,48*mm,116*mm),
                portrait(A4),
            ),
            'bank':(
                'Relatório de contas bancárias',
                ('Código','Colaborador','Banco','Agência','Conta'),
                ('code','name','bank','bank_agency','bank_account'),
                (18*mm,42*mm,36*mm,28*mm,62*mm),
                portrait(A4),
            ),
            'phone':(
                'Relatório de telefones',
                ('Código','Colaborador','Telefone'),
                ('code','name','phone'),
                (22*mm,48*mm,116*mm),
                portrait(A4),
            ),
            'email':(
                'Relatório de e-mails',
                ('Código','Colaborador','E-mail'),
                ('code','name','email'),
                (22*mm,48*mm,116*mm),
                portrait(A4),
            ),
            'address':(
                'Relatório de endereços',
                ('Código','Colaborador','Endereço completo'),
                ('code','name'),
                (22*mm,48*mm,116*mm),
                portrait(A4),
            ),
        }
        if report_type not in report_columns:
            raise ValueError('Tipo de relatório de colaborador inválido.')
        title,headers,fields,column_widths,page_size=report_columns[report_type]
        selected_fields=(
            ('code','name','address','address_number','bairro','cep','city','state')
            if report_type=='address' else fields)
        columns=','.join(selected_fields)
        query='SELECT '+columns+' FROM employees'
        query+=' WHERE active=1'
        params=[]
        if employee_id is not None:
            query+=' AND id=?'
            params.append(employee_id)
        query+=' ORDER BY active DESC,name COLLATE NOCASE'
        with connect() as con:
            rows=con.execute(query,params).fetchall()
        generated=datetime.now().strftime('%d/%m/%Y %H:%M')
        generated=datetime.now().strftime('%d/%m/%Y %H:%M')
        styles=getSampleStyleSheet()
        title_style=ParagraphStyle(
            'EmployeeReportTitle',parent=styles['Title'],fontName='Helvetica-Bold',
            fontSize=16,leading=20,textColor=colors.HexColor(NAVY),alignment=1,spaceAfter=4)
        subtitle_style=ParagraphStyle(
            'EmployeeReportSubtitle',parent=styles['Normal'],fontName='Helvetica',
            fontSize=9,textColor=colors.HexColor('#64748b'),alignment=1,spaceAfter=10)
        header_style=ParagraphStyle(
            'EmployeeReportHeader',parent=styles['Normal'],fontName='Helvetica-Bold',
            fontSize=8,leading=9,textColor=colors.white)
        value_style=ParagraphStyle(
            'EmployeeReportValue',parent=styles['Normal'],fontName='Helvetica',
            fontSize=8,leading=10,wordWrap='CJK')

        def paragraph(value,style):
            return Paragraph(xml_escape(str(value or '—')),style)

        def draw_page(canvas,document):
            self.pdf_page_header(canvas,page_size,generated,document.page)

        employee_label=(
            rows[0]['name'] if employee_id is not None and rows
            else 'Todos os colaboradores')
        document=SimpleDocTemplate(
            path,pagesize=page_size,rightMargin=12*mm,leftMargin=12*mm,
            topMargin=24*mm,bottomMargin=18*mm,title=title,author=AUTHOR)
        data=[[paragraph(value,header_style) for value in headers]]
        for row in rows:
            if report_type=='address':
                address_parts=(
                    (row['address'] or '').strip(),
                    (row['address_number'] or '').strip(),
                    (row['bairro'] or '').strip(),
                    f'CEP {row["cep"].strip()}' if row['cep'] else '',
                    ' / '.join(
                        value.strip() for value in (row['city'],row['state']) if value
                    ),
                )
                values=(row['code'],row['name'],', '.join(part for part in address_parts if part))
            else:
                values=[row[field] for field in fields]
            data.append([paragraph(value,value_style) for value in values])
        report_table=LongTable(
            data,colWidths=column_widths,repeatRows=1,hAlign='LEFT')
        report_table.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),colors.HexColor(NAVY)),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f3f6fb')]),
            ('GRID',(0,0),(-1,-1),0.35,colors.HexColor('#dbe3ee')),
            ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('LEFTPADDING',(0,0),(-1,-1),5),
            ('RIGHTPADDING',(0,0),(-1,-1),5),
            ('TOPPADDING',(0,0),(-1,-1),5),
            ('BOTTOMPADDING',(0,0),(-1,-1),5),
        ]))
        story=[
            Paragraph(xml_escape(title),title_style),
            Paragraph(
                f'{xml_escape(employee_label)} • {len(rows)} colaborador(es) • Gerado em {generated}',
                subtitle_style),
            report_table,
        ]
        document.build(
            story,onFirstPage=draw_page,onLaterPages=draw_page,
            canvasmaker=NumberedReportCanvas)
        return len(rows)

    def generate_employee_report_dialog(self):
        with connect() as con:
            employees=con.execute(
                'SELECT id,name,code FROM employees WHERE active=1 ORDER BY name COLLATE NOCASE').fetchall()
        if not employees:
            messagebox.showwarning(
                'Sem colaboradores ativos',
                'Cadastre ou ative um colaborador antes de gerar o relatório.',
                parent=self)
            return

        dialog=tk.Toplevel(self)
        dialog.title('Relatórios de dados cadastrais')
        dialog.configure(bg=BG)
        dialog.transient(self)
        dialog.resizable(False,False)
        fields=ttk.Frame(dialog,padding=20)
        fields.pack(fill='both',expand=True)
        ttk.Label(
            fields,text='Escolha o relatório e os colaboradores',
            font=('Segoe UI Semibold',14)).pack(anchor='w',pady=(0,14))

        employee_choices={'Todos os colaboradores':None}
        employee_choices.update({
            f'{employee["name"]} (código {employee["code"]})'
            if employee['code'] else employee['name']:employee['id']
            for employee in employees
        })
        employee_var=tk.StringVar(value='Todos os colaboradores')
        ttk.Label(fields,text='Colaborador').pack(anchor='w')
        ttk.Combobox(
            fields,textvariable=employee_var,state='readonly',width=48,
            values=list(employee_choices)).pack(fill='x',pady=(5,12))

        report_choices={
            'Relatório de PIX':'pix',
            'Relatório de conta bancária':'bank',
            'Relatório de telefone':'phone',
            'Relatório de e-mail':'email',
            'Relatório de endereço':'address',
        }
        report_var=tk.StringVar(value='Relatório de PIX')
        ttk.Label(fields,text='Tipo de relatório').pack(anchor='w')
        ttk.Combobox(
            fields,textvariable=report_var,state='readonly',width=48,
            values=list(report_choices)).pack(fill='x',pady=(5,14))
        buttons=ttk.Frame(fields)
        buttons.pack(fill='x')
        ttk.Button(buttons,text='Cancelar',command=dialog.destroy).pack(side='right')

        def generate_report():
            employee_label=employee_var.get()
            report_label=report_var.get()
            if employee_label not in employee_choices or report_label not in report_choices:
                messagebox.showwarning(
                    'Seleção inválida','Escolha um colaborador e um tipo de relatório.',
                    parent=dialog)
                return
            employee_id=employee_choices[employee_label]
            report_type=report_choices[report_label]
            dialog.destroy()
            suffix=f'_{employee_id}' if employee_id is not None else '_todos'
            path=temporary_pdf_path(
                f'relatorio_{report_type}_colaboradores_{datetime.now():%Y_%m_%d}{suffix}_')
            try:
                self.write_employee_report_pdf(path,report_type,employee_id)
                open_pdf(path)
            except Exception as ex:
                messagebox.showerror(
                    'Erro ao abrir relatório',
                    f'Não foi possível gerar ou abrir o PDF: {ex}\n\nArquivo temporário: {path}',
                    parent=self)
                return

        ttk.Button(
            buttons,text='Gerar PDF',style='Accent.TButton',
            command=generate_report).pack(side='right',padx=(0,8))
        dialog.bind('<Escape>',lambda event:dialog.destroy())
        dialog.grab_set()
        self.wait_window(dialog)

    def loan_report_data(self,year,month,kind=LOAN_KIND,employee_id=None):
        cutoff=(year,month)
        amount_column='advances' if kind==ADVANCE_KIND else 'loan'
        with connect() as con:
            loans=con.execute('''SELECT l.*,e.name FROM employee_loans l
                JOIN employees e ON e.id=l.employee_id
                WHERE l.kind=? AND (? IS NULL OR l.employee_id=?)
                ORDER BY l.employee_id,l.id''',(kind,employee_id,employee_id)).fetchall()
            actual_rows=con.execute(f'''SELECT i.employee_id,p.year,p.month,i.{amount_column} AS amount
                FROM payroll_items i JOIN payrolls p ON p.id=i.payroll_id
                WHERE p.status='Fechada' AND (p.year<? OR (p.year=? AND p.month<=?))
                AND (? IS NULL OR i.employee_id=?)
                ORDER BY p.year,p.month,i.employee_id''',(year,year,month,employee_id,employee_id)).fetchall()

            actual_by_employee_month={}
            for row in actual_rows:
                key=(row['employee_id'],row['year'],row['month'])
                actual_by_employee_month[key]=actual_by_employee_month.get(key,0)+float(row['amount'] or 0)

            settlement_by_loan={}
            settlement_by_employee_month={}
            for loan in loans:
                if (loan['settled_year'] is None
                        or (loan['settled_year'],loan['settled_month'])>cutoff):
                    continue
                amount=float(loan['settlement_amount'] or 0)
                settlement_by_loan[loan['id']]=amount
                key=(loan['employee_id'],loan['settled_year'],loan['settled_month'])
                settlement_by_employee_month[key]=settlement_by_employee_month.get(key,0)+amount
            for key,amount in settlement_by_employee_month.items():
                actual_by_employee_month[key]=round(
                    max(0,actual_by_employee_month.get(key,0)-amount),2)

            schedules={}
            schedule_months_by_loan={}
            terms_by_loan={}
            for loan in loans:
                terms=loan_terms_for_loan(con,loan)
                terms_by_loan[loan['id']]=terms
                periods=[]
                for index,term in enumerate(terms):
                    start_year=term['start_year']
                    start_month=term['start_month']
                    principal=term['principal']
                    count=term['installment_count']
                    start_index=start_year*12+start_month-1
                    end_index=start_index+count-1
                    if index+1<len(terms):
                        next_start=terms[index+1]['start_year']*12+terms[index+1]['start_month']-1
                        end_index=min(end_index,next_start-1)
                    for period_index in range(start_index,end_index+1):
                        period_year,zero_month=divmod(period_index,12)
                        period_month=zero_month+1
                        if (loan['settled_year'] is not None
                                and (period_year,period_month)>=(loan['settled_year'],loan['settled_month'])):
                            continue
                        elapsed=(period_year-start_year)*12+period_month-start_month
                        if elapsed>=0 and elapsed<count:
                            amount=loan_installment(principal,count,elapsed+1)
                            periods.append((period_year,period_month,amount,elapsed+1,count))
                            schedules.setdefault((loan['employee_id'],period_year,period_month),[]).append((loan['id'],amount))
                schedule_months_by_loan[loan['id']]=periods

            paid_by_loan_period={}
            paid_total_by_loan={}
            for (employee_id,pay_year,pay_month),loan_schedules in sorted(schedules.items(),key=lambda entry:(entry[0][1],entry[0][2],entry[0][0])):
                available=actual_by_employee_month.get((employee_id,pay_year,pay_month),0)
                for loan_id,expected in sorted(loan_schedules,key=lambda entry:entry[0]):
                    paid=min(expected,max(0,available))
                    paid_by_loan_period[(loan_id,pay_year,pay_month)]=paid
                    paid_total_by_loan[loan_id]=paid_total_by_loan.get(loan_id,0)+paid
                    available=round(max(0,available-paid),2)
                if available>0 and loan_schedules:
                    loan_id=min(entry[0] for entry in loan_schedules)
                    current_terms=[term for term in terms_by_loan[loan_id] if (term['start_year'],term['start_month'])<=(pay_year,pay_month)]
                    if current_terms:
                        current_term=current_terms[-1]
                        term_start=(current_term['start_year'],current_term['start_month'])
                        paid_before=sum(
                            amount for (paid_loan_id,paid_year,paid_month),amount in paid_by_loan_period.items()
                            if paid_loan_id==loan_id and term_start<=(paid_year,paid_month)<(pay_year,pay_month)
                        )
                        paid_this_month=paid_by_loan_period.get((loan_id,pay_year,pay_month),0)
                        extra=min(available,max(0,float(current_term['principal'])-paid_before-paid_this_month))
                        if extra:
                            paid_by_loan_period[(loan_id,pay_year,pay_month)]=paid_this_month+extra
                            paid_total_by_loan[loan_id]=paid_total_by_loan.get(loan_id,0)+extra

            report=[]
            for loan in loans:
                applicable=terms_by_loan[loan['id']]
                settlement_period=(
                    (loan['settled_year'],loan['settled_month'])
                    if loan['id'] in settlement_by_loan else None)
                recorded_settlement=(
                    (loan['settled_year'],loan['settled_month'])
                    if loan['settled_year'] is not None else None)
                effective_cutoff=min(cutoff,settlement_period) if settlement_period else cutoff
                effective=[term for term in applicable if (term['start_year'],term['start_month'])<=effective_cutoff]
                if effective:
                    current=effective[-1]
                else:
                    current={'principal':loan['principal'],'installment_count':loan['installment_count'],'start_year':loan['start_year'],'start_month':loan['start_month']}
                current_start=(current['start_year'],current['start_month'])
                paid_current=0
                for (loan_id,pay_year,pay_month),paid in paid_by_loan_period.items():
                    if loan_id==loan['id'] and current_start<=(pay_year,pay_month)<=cutoff:
                        paid_current+=paid
                balance=round(max(0,float(current['principal'])-paid_current),2)
                paid_installments=0
                pending=[]
                monthly_details=[]
                for pay_year,pay_month,expected,installment_number,installment_count in schedule_months_by_loan[loan['id']]:
                    actual=paid_by_loan_period.get((loan['id'],pay_year,pay_month),0)
                    paid_amount=round(min(expected,actual),2)
                    pending_amount=round(max(0,expected-paid_amount),2)
                    monthly_details.append({
                        'installment_number':installment_number,
                        'installment_count':installment_count,
                        'year':pay_year,
                        'month':pay_month,
                        'scheduled':expected,
                        'paid':paid_amount,
                        'pending':pending_amount,
                        'settlement':False,
                    })
                    if actual>=expected-0.005:
                        paid_installments+=1
                    else:
                        pending.append((
                            installment_number,installment_count,pay_year,pay_month,
                            pending_amount))
                if settlement_period:
                    balance=0
                    paid_installments=int(current['installment_count'])
                    pending=[]
                    due_label=f'Quitado em {settlement_period[1]:02d}/{settlement_period[0]}'
                    paid=round(min(
                        float(current['principal']),
                        paid_total_by_loan.get(loan['id'],0)+settlement_by_loan[loan['id']]),2)
                elif pending:
                    _,_,next_year,next_month,next_amount=pending[0]
                    due_label=f'{MONTHS[next_month-1]}/{next_year} - {brl(next_amount)}'
                else:
                    due_label='Sem parcelas programadas'
                if not settlement_period:
                    paid=round(paid_total_by_loan.get(loan['id'],0),2)
                if recorded_settlement:
                    monthly_details.append({
                        'installment_number':0,
                        'installment_count':0,
                        'year':recorded_settlement[0],
                        'month':recorded_settlement[1],
                        'scheduled':float(loan['settlement_amount'] or 0),
                        'paid':float(loan['settlement_amount'] or 0),
                        'pending':0.0,
                        'settlement':True,
                    })
                current_count=int(current['installment_count'])
                report.append({
                    'name':loan['name'],
                    'employee_id':loan['employee_id'],
                    'kind':loan['kind'],
                    'notes':loan['notes'] or '',
                    'created_at':loan['created_at'],
                    'installment_count':current_count,
                    'installment_amount':(
                        loan_installment(float(current['principal']),current_count,1)
                        if current_count>0 else 0.0),
                    'loan_id':loan['id'],
                    'principal':float(current['principal']),
                    'paid':paid,
                    'paid_installments':paid_installments,
                    'pending_installments':len(pending),
                    'next_due':due_label,
                    'balance':balance,
                    'pending_details':pending,
                    'monthly_details':monthly_details,
                })
        return report

    def write_employee_general_report_pdf(self,year,month,path,employee_id=None,only_month=None):
        if only_month is not None:
            year,month=only_month
        cutoff=(year,month)
        rows=[]
        for report_kind in LOAN_KINDS:
            rows.extend(self.loan_report_data(year,month,report_kind,employee_id))
        with connect() as con:
            employees={row['id']:row for row in con.execute(
                'SELECT id,code,name,active FROM employees').fetchall()}
        by_employee={}
        for row in rows:
            by_employee.setdefault(row['employee_id'],[]).append(row)
        if employee_id is not None and employee_id not in by_employee and employee_id in employees:
            by_employee[employee_id]=[]

        def employee_name(key):
            if by_employee[key]:
                return by_employee[key][0]['name']
            return employees[key]['name'] if key in employees else '—'

        order=sorted(by_employee,key=lambda key:employee_name(key).casefold())

        styles=getSampleStyleSheet()
        title_style=ParagraphStyle(
            'EmployeeGeneralTitle',parent=styles['Title'],fontName='Helvetica-Bold',
            fontSize=9,leading=11,textColor=colors.HexColor(NAVY),alignment=1,spaceAfter=2)
        cell_style=ParagraphStyle(
            'EmployeeGeneralCell',parent=styles['Normal'],fontName='Helvetica',
            fontSize=5.5,leading=6.5,wordWrap='CJK')
        centered_cell_style=ParagraphStyle(
            'EmployeeGeneralCenteredCell',parent=cell_style,alignment=1)
        total_cell_style=ParagraphStyle(
            'EmployeeGeneralTotalCell',parent=cell_style,fontName='Helvetica-Bold')
        centered_total_style=ParagraphStyle(
            'EmployeeGeneralCenteredTotal',parent=total_cell_style,alignment=1)
        header_style=ParagraphStyle(
            'EmployeeGeneralHeader',parent=styles['Normal'],fontName='Helvetica-Bold',
            fontSize=5,leading=6,textColor=colors.white,alignment=1)
        employee_style=ParagraphStyle(
            'EmployeeGeneralName',parent=styles['Normal'],fontName='Helvetica-Bold',
            fontSize=5.5,leading=6.5,textColor=colors.white)
        section_style=ParagraphStyle(
            'EmployeeGeneralSection',parent=styles['Heading2'],fontName='Helvetica-Bold',
            fontSize=6,leading=7,textColor=colors.HexColor(NAVY),spaceBefore=2.5*mm,spaceAfter=1.5*mm,keepWithNext=True)
        page_size=portrait(A4)
        usable_width=page_size[0]-24*mm-12
        generated=datetime.now().strftime('%d/%m/%Y %H:%M')

        def draw_page(canvas,document):
            self.pdf_page_header(canvas,page_size,generated,document.page)

        def period_label(period_year,period_month):
            return f'{MONTHS[period_month-1][:3]}/{period_year}'

        def month_status(period,pending,paid,settlement):
            if settlement or pending<=0.005:
                return 'Quitado'
            if period>cutoff:
                return 'A vencer'
            return 'Parcial' if paid>0 else 'Em aberto'

        def make_table(data,widths,total_row=False):
            data=[
                [
                    value if isinstance(value,Paragraph) else Paragraph(
                        xml_escape(str(value)),
                        (total_cell_style if column==0 else centered_total_style)
                        if total_row and row_index==len(data)-1 else
                        (cell_style if column==0 else centered_cell_style))
                    for column,value in enumerate(row)
                ]
                for row_index,row in enumerate(data)
            ]
            scale=usable_width/sum(widths)
            table=LongTable(
                data,colWidths=[width*scale for width in widths],
                repeatRows=1,hAlign='LEFT',spaceAfter=8*mm)
            commands=[
                ('FONTSIZE',(0,0),(-1,-1),6.5),
                ('BACKGROUND',(0,0),(-1,0),colors.HexColor(NAVY)),
                ('ALIGN',(1,1),(-1,-1),'CENTER'),
                ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                ('GRID',(0,0),(-1,-1),0.3,colors.HexColor('#dbe3ee')),
                ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f3f6fb')]),
                ('LEFTPADDING',(0,0),(-1,-1),3),
                ('RIGHTPADDING',(0,0),(-1,-1),3),
                ('TOPPADDING',(0,0),(-1,-1),1.5),
                ('BOTTOMPADDING',(0,0),(-1,-1),1.5),
            ]
            if total_row:
                commands.extend([
                    ('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#eff6ff')),
                    ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),
                ])
            table.setStyle(TableStyle(commands))
            return table

        def headers(*labels):
            return [Paragraph(label,header_style) for label in labels]

        report_name='Relatório Geral por Colaborador'
        document=SimpleDocTemplate(
            path,pagesize=page_size,rightMargin=12*mm,leftMargin=12*mm,
            topMargin=24*mm,bottomMargin=18*mm,title=report_name,author=AUTHOR)
        story=[Paragraph(report_name,title_style)]

        total_balance=0.0
        summaries=[]
        sections=[]
        for position,key in enumerate(order):
            employee_rows=sorted(
                by_employee[key],key=lambda row:(row['kind']!=LOAN_KIND,row['loan_id']))
            name=employee_name(key)
            info=employees.get(key)
            code=((info['code'] or '').strip() if info else '') or '—'
            status='Ativo' if info is None or info['active'] else 'Inativo'
            loans=[row for row in employee_rows if row['kind']==LOAN_KIND]
            advances=[row for row in employee_rows if row['kind']==ADVANCE_KIND]

            def total(items,field):
                return round(sum(row[field] for row in items),2)

            balance=total(employee_rows,'balance')
            total_balance+=balance
            paid_installments=sum(row['paid_installments'] for row in employee_rows)
            pending_installments=sum(row['pending_installments'] for row in employee_rows)
            summaries.append([
                Paragraph(xml_escape(name),cell_style),
                brl(total(employee_rows,'principal')),brl(total(employee_rows,'paid')),
                brl(balance),
            ])

            block=[Spacer(1,4*mm)] if position>0 else []
            header=Table(
                [[Paragraph(xml_escape(f'Código: {code} • {name} • {status}'),employee_style)]],
                colWidths=[usable_width],hAlign='LEFT')
            header.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,-1),colors.HexColor(NAVY)),
                ('LEFTPADDING',(0,0),(-1,-1),4),
                ('TOPPADDING',(0,0),(-1,-1),2),
                ('BOTTOMPADDING',(0,0),(-1,-1),2),
            ]))
            header.keepWithNext=True
            block.append(header)
            if not employee_rows:
                block.extend([
                    Spacer(1,3*mm),
                    Paragraph('Este colaborador não possui empréstimos ou adiantamentos cadastrados.',cell_style),
                ])
                sections.append(block)
                continue

            if only_month is not None:
                month_items=sorted(
                    ((row,item) for row in employee_rows for item in row['monthly_details']
                     if (item['year'],item['month'])==only_month),
                    key=lambda entry:(entry[0]['kind']!=LOAN_KIND,entry[0]['loan_id']))
                if not month_items:
                    if employee_id is None:
                        continue
                    block.extend([
                        Spacer(1,2*mm),
                        Paragraph('Nenhuma parcela neste mês.',cell_style),
                    ])
                    sections.append(block)
                    continue
                month_name=f'{MONTHS[only_month[1]-1]} de {only_month[0]}'
                for kind_name,kind_title,item_word in (
                        (LOAN_KIND,'EMPRÉSTIMO',f'Parcela do empréstimo'),
                        (ADVANCE_KIND,'ADIANTAMENTO SALARIAL','Desconto do adiantamento')):
                    kind_items=[entry for entry in month_items if entry[0]['kind']==kind_name]
                    if not kind_items:
                        continue
                    month_data=[headers(
                        item_word,'Valor a pagar no mês','Já pago','Falta pagar','Situação')]
                    for row,item in kind_items:
                        installment=(
                            'Quitação antecipada' if item['settlement'] else
                            f'Parcela {item["installment_number"]} de {item["installment_count"]}')
                        month_data.append([
                            installment,brl(item['scheduled']),
                            brl(item['paid']),brl(item['pending']),
                            month_status(only_month,item['pending'],item['paid'],item['settlement']),
                        ])
                    month_data.append([
                        f'TOTAL DO MÊS ({kind_title.title()})',
                        brl(sum(item['scheduled'] for _,item in kind_items)),
                        brl(sum(item['paid'] for _,item in kind_items)),
                        brl(sum(item['pending'] for _,item in kind_items)),''])
                    block.extend([
                        Paragraph(f'{kind_title} — o que vence em {month_name}',section_style),
                        make_table(month_data,[60*mm,34*mm,28*mm,28*mm,30*mm],total_row=True),
                    ])
                sections.append(block)
                continue

            highlight_label=ParagraphStyle(
                'EmployeeGeneralHighlightLabel',parent=styles['Normal'],fontName='Helvetica-Bold',
                fontSize=5.5,leading=6.5,textColor=colors.HexColor('#475569'),alignment=1)
            highlight_value=ParagraphStyle(
                'EmployeeGeneralHighlightValue',parent=styles['Normal'],fontName='Helvetica-Bold',
                fontSize=6.5,leading=8,textColor=colors.HexColor(NAVY),alignment=1)
            highlight_total=ParagraphStyle(
                'EmployeeGeneralHighlightTotal',parent=highlight_value,
                fontSize=7,leading=9,textColor=colors.HexColor('#b91c1c'))
            overview=Table([
                [Paragraph('Empréstimos: falta pagar',highlight_label),
                 Paragraph('Adiantamentos: falta pagar',highlight_label),
                 Paragraph('TOTAL QUE AINDA FALTA PAGAR',highlight_label),
                 Paragraph('Total já pago (empréstimos + adiantamentos)',highlight_label)],
                [Paragraph(brl(total(loans,'balance')),highlight_value),
                 Paragraph(brl(total(advances,'balance')),highlight_value),
                 Paragraph(brl(balance),highlight_total),
                 Paragraph(brl(total(employee_rows,'paid')),highlight_value)],
            ],colWidths=[usable_width/4]*4,hAlign='LEFT')
            overview.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#eaf1fb')),
                ('BOX',(0,0),(-1,-1),1.2,colors.HexColor(NAVY)),
                ('BACKGROUND',(2,0),(2,-1),colors.HexColor('#fff1f1')),
                ('LINEAFTER',(0,0),(-2,-1),0.4,colors.HexColor('#b6c6dd')),
                ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                ('TOPPADDING',(0,0),(-1,0),5),
                ('BOTTOMPADDING',(0,0),(-1,0),1),
                ('TOPPADDING',(0,1),(-1,1),1),
                ('BOTTOMPADDING',(0,1),(-1,1),6),
            ]))
            block.extend([
                Spacer(1,1.5*mm),Paragraph('Resumo geral do colaborador',section_style),overview,
                Spacer(1,7*mm)])

            for kind_name,kind_rows,table_title,list_title,money_word in (
                    (LOAN_KIND,loans,'EMPRÉSTIMOS do colaborador',
                     'Parcelas de empréstimo que ainda faltam pagar','Valor'),
                    (ADVANCE_KIND,advances,'ADIANTAMENTOS SALARIAIS do colaborador',
                     'Descontos de adiantamento que ainda faltam pagar','Valor')):
                if not kind_rows:
                    continue
                kind_data=[headers(
                    money_word,'Parcelas já pagas','Valor de cada parcela','Já pago',
                    'Falta pagar','Último desconto previsto','Situação')]
                for row in kind_rows:
                    scheduled=[item for item in row['monthly_details'] if not item['settlement']]
                    last_due=period_label(scheduled[-1]['year'],scheduled[-1]['month']) if scheduled else '—'
                    settled=next((item for item in row['monthly_details'] if item['settlement']),None)
                    if settled:
                        situation=f'Quitado em {settled["month"]:02d}/{settled["year"]}'
                    elif row['balance']<=0.005:
                        situation='Todo pago'
                    else:
                        situation='Em andamento'
                    kind_data.append([
                        brl(row['principal']),
                        f'{row["paid_installments"]} de {row["installment_count"]}',
                        brl(row['installment_amount']),brl(row['paid']),
                        brl(row['balance']),last_due,situation,
                    ])
                block.extend([
                    Paragraph(table_title,section_style),
                    make_table(kind_data,[30*mm,28*mm,32*mm,28*mm,28*mm,34*mm,34*mm]),
                ])

                pending_items=sorted(
                    ((row,item) for row in kind_rows for item in row['monthly_details']
                     if item['pending']>0.005),
                    key=lambda entry:(entry[1]['year'],entry[1]['month'],entry[0]['loan_id']))
                if pending_items:
                    pending_data=[headers('Mês do desconto','Parcela','Falta pagar')]
                    for row,item in pending_items:
                        pending_data.append([
                            period_label(item['year'],item['month']),
                            f'{item["installment_number"]} de {item["installment_count"]}',
                            brl(item['pending']),
                        ])
                    pending_data.append([
                        'TOTAL QUE FALTA','',brl(sum(item['pending'] for _,item in pending_items))])
                    block.extend([
                        Paragraph(list_title,section_style),
                        make_table(pending_data,[40*mm,34*mm,40*mm],total_row=True),
                    ])
                else:
                    block.append(Paragraph('Nada pendente: tudo pago.',cell_style))
            sections.append(block)
            continue

        if len(order)>1 and only_month is None:
            summaries.append([
                Paragraph('TOTAL GERAL',cell_style),'','',brl(total_balance)])
            story.extend([
                Paragraph('Resumo por colaborador',section_style),
                make_table(
                    [headers('Colaborador','Total contratado','Já pago','Falta pagar')]
                    +summaries,
                    [80*mm,36*mm,36*mm,36*mm],total_row=True),
                PageBreak(),
            ])
        if not order:
            story.append(Paragraph('Não há empréstimos ou adiantamentos cadastrados para a seleção.',cell_style))
        for block in sections:
            story.extend(block)
        document.build(story,onFirstPage=draw_page,onLaterPages=draw_page,canvasmaker=NumberedReportCanvas)
        return len(order),total_balance

    def generate_advance_report_dialog(self):
        period=self.selected_payroll_period()
        if period is None:
            return
        year,month=period
        with connect() as con:
            employees=con.execute(
                'SELECT id,name FROM employees ORDER BY active DESC,name COLLATE NOCASE').fetchall()
        choices=['Todos os colaboradores']+[f'{employee["name"]} (#{employee["id"]})' for employee in employees]
        employee_ids=[None]+[employee['id'] for employee in employees]
        dialog=tk.Toplevel(self)
        report_title='Relatório Geral por Colaborador'
        dialog.title(report_title)
        dialog.configure(bg=BG)
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False,False)
        fields=ttk.Frame(dialog,padding=20)
        fields.pack(fill='both',expand=True)
        ttk.Label(
            fields,text=f'Empréstimos e adiantamentos • Saldo em {MONTHS[month-1]} de {year}',
            font=('Segoe UI Semibold',14)).pack(anchor='w',pady=(0,12))
        ttk.Label(fields,text='Funcionário / colaborador').pack(anchor='w')
        employee_var=tk.StringVar(value=choices[0])
        employee_box=ttk.Combobox(
            fields,textvariable=employee_var,state='readonly',width=38,values=choices)
        employee_box.current(0)
        employee_box.pack(fill='x',pady=(5,14))
        period_fields=ttk.Frame(fields)
        period_fields.pack(fill='x')
        ttk.Label(period_fields,text='Período').pack(anchor='w')
        period_choices=['Todos os meses (o que falta pagar)','Somente um mês']
        period_box=ttk.Combobox(
            period_fields,state='readonly',width=38,values=period_choices)
        period_box.current(0)
        period_box.pack(fill='x',pady=(5,8))
        month_row=ttk.Frame(period_fields)
        month_row.pack(fill='x',pady=(0,14))
        month_box=ttk.Combobox(
            month_row,state='disabled',width=16,values=list(MONTHS))
        month_box.current(month-1)
        month_box.pack(side='left')
        year_var=tk.StringVar(value=str(year))
        year_box=ttk.Spinbox(
            month_row,from_=2000,to=2100,width=7,textvariable=year_var,state='disabled')
        year_box.pack(side='left',padx=(8,0))

        def toggle_month(event=None):
            state='readonly' if period_box.current()==1 else 'disabled'
            month_box.configure(state=state)
            year_box.configure(state='normal' if period_box.current()==1 else 'disabled')

        period_box.bind('<<ComboboxSelected>>',toggle_month)
        buttons=ttk.Frame(fields)
        buttons.pack(fill='x')
        ttk.Button(buttons,text='Cancelar',command=dialog.destroy).pack(side='right')

        def generate_report():
            employee_index=employee_box.current()
            if not 0<=employee_index<len(employee_ids):
                messagebox.showerror('Funcionário inválido','Selecione um funcionário ou todos os colaboradores.',parent=dialog)
                return
            employee_id=employee_ids[employee_index]
            only_month=None
            if period_box.current()==1:
                try:
                    only_month=(int(year_var.get()),month_box.current()+1)
                except ValueError:
                    messagebox.showerror('Ano inválido','Informe um ano válido.',parent=dialog)
                    return
            suffix=f'_{employee_id}' if employee_id is not None else '_todos'
            path=temporary_pdf_path(
                f'relatorio_geral_colaborador_{year}_{month:02d}{suffix}_')
            try:
                self.write_employee_general_report_pdf(
                    year,month,path,employee_id=employee_id,only_month=only_month)
                open_pdf(path)
            except Exception as ex:
                messagebox.showerror(
                    'Erro ao abrir relatório',
                    f'Não foi possível gerar ou abrir o {report_title.lower()}: {ex}\n\n'
                    f'Arquivo temporário: {path}',
                    parent=dialog)
                return
            dialog.destroy()

        ttk.Button(
            buttons,text='Gerar PDF',style='Report.TButton',
            command=generate_report).pack(side='right',padx=(0,8))
        dialog.bind('<Escape>',lambda event:dialog.destroy())
        self.wait_window(dialog)

    def write_current_salaries_report(self,path):
        period=datetime.now()
        year=period.year
        month=period.month
        with connect() as con:
            employees=con.execute('''SELECT id,code,name FROM employees
                WHERE active=1 ORDER BY name COLLATE NOCASE''').fetchall()
            salaries=[
                (employee,employee_salary_for_period(
                    con,employee['id'],year,month))
                for employee in employees
            ]
        styles=getSampleStyleSheet()
        title_style=ParagraphStyle(
            'CurrentSalariesTitle',parent=styles['Title'],
            fontName='Helvetica-Bold',fontSize=16,leading=20,
            textColor=colors.HexColor(NAVY),alignment=1,spaceAfter=4)
        subtitle_style=ParagraphStyle(
            'CurrentSalariesSubtitle',parent=styles['Normal'],
            fontName='Helvetica',fontSize=9,
            textColor=colors.HexColor('#64748b'),alignment=1,spaceAfter=12)
        header_style=ParagraphStyle(
            'CurrentSalariesHeader',parent=styles['Normal'],
            fontName='Helvetica-Bold',fontSize=8,leading=9,
            textColor=colors.white,alignment=1)
        cell_style=ParagraphStyle(
            'CurrentSalariesCell',parent=styles['Normal'],
            fontName='Helvetica',fontSize=8,leading=10,wordWrap='CJK')
        page_size=portrait(A4)
        generated=period.strftime('%d/%m/%Y %H:%M')

        def draw_page(canvas,document):
            self.pdf_page_header(canvas,page_size,generated,document.page)

        document=SimpleDocTemplate(
            path,pagesize=page_size,rightMargin=12*mm,leftMargin=12*mm,
            topMargin=24*mm,bottomMargin=18*mm,
            title='Relatório de salários atualizados',author=AUTHOR)
        story=[
            Paragraph('Relatório de salários atualizados',title_style),
            Paragraph(
                f'Salários vigentes em {month:02d}/{year} • Gerado em {generated}',
                subtitle_style),
        ]
        headers=['Matrícula','Colaborador','Salário atualizado']
        data=[[Paragraph(xml_escape(header),header_style) for header in headers]]
        for employee,salary in salaries:
            data.append([
                employee['code'] or '—',
                Paragraph(xml_escape(employee['name']),cell_style),
                brl(salary),
            ])
        if not employees:
            data.append([Paragraph('Nenhum colaborador ativo.',cell_style)]+['']*(len(headers)-1))
        table=LongTable(
            data,colWidths=[30*mm,100*mm,45*mm],
            repeatRows=1,hAlign='LEFT')
        table_style=[
            ('BACKGROUND',(0,0),(-1,0),colors.HexColor(NAVY)),
            ('TEXTCOLOR',(0,0),(-1,0),colors.white),
            ('ALIGN',(0,1),(0,-1),'CENTER'),
            ('ALIGN',(2,1),(2,-1),'RIGHT'),
            ('FONTSIZE',(0,1),(-1,-1),8),
            ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('GRID',(0,0),(-1,-1),0.35,colors.HexColor('#dbe3ee')),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[
                colors.white,colors.HexColor('#f3f6fb')]),
            ('LEFTPADDING',(0,0),(-1,-1),5),
            ('RIGHTPADDING',(0,0),(-1,-1),5),
            ('TOPPADDING',(0,0),(-1,-1),6),
            ('BOTTOMPADDING',(0,0),(-1,-1),6),
        ]
        if not employees:
            table_style.append(('SPAN',(0,1),(-1,1)))
        table.setStyle(TableStyle(table_style))
        story.append(table)
        document.build(story,onFirstPage=draw_page,onLaterPages=draw_page,canvasmaker=NumberedReportCanvas)
        return len(salaries)

    def generate_current_salaries_report(self):
        path=temporary_pdf_path('relatorio_salarios_atualizados_')
        try:
            self.write_current_salaries_report(path)
            open_pdf(path)
        except Exception as ex:
            messagebox.showerror(
                'Erro ao abrir relatório',
                f'Não foi possível gerar ou abrir o relatório de salários atualizados: {ex}\n\n'
                f'Arquivo temporário: {path}',
                parent=self)
            return

class FolhaApp(FolhaBase,tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        set_window_icon(self)
        central_geometry=central_geometry_from_args()
        screen_width=self.winfo_screenwidth()
        screen_height=self.winfo_screenheight()
        if central_geometry is None:
            minimum_width=min(760,max(320,screen_width-40))
            minimum_height=min(480,max(240,screen_height-80))
            window_width=min(1320,max(minimum_width,screen_width-80))
            window_height=min(790,max(minimum_height,screen_height-120))
            self.geometry(f'{window_width}x{window_height}')
        else:
            window_width,window_height,x,y=central_geometry
            minimum_width=320
            minimum_height=240
            self.geometry(f'{window_width}x{window_height}+{x}+{y}')
        self.minsize(minimum_width,minimum_height)
        self._init_folha()
        self.protocol('WM_DELETE_WINDOW',self.on_close)
        if central_geometry is None:
            self.state('zoomed')


class FolhaPanel(FolhaBase,tk.Frame):
    """Folha embutida em outra janela (Sistemas Revisa integrado)."""

    def __init__(self,master,centralized_actions=False,signing_status_callback=None):
        tk.Frame.__init__(self,master,bg=BG)
        self.centralized_actions=centralized_actions
        self.signing_status_callback=signing_status_callback
        self._init_folha()

    def reapply_style(self):
        self._style()

    def close_module(self):
        self.save_exit_backups()
        self.destroy()

def main():
    if sys.platform=='win32':
        import ctypes
        result=ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            'Revisa.FolhaPagamento')
        if result!=0:
            raise OSError(f'Não foi possível configurar o ícone da barra de tarefas: {result}')
    init_db()
    if authenticate():
        FolhaApp().mainloop()


if __name__=='__main__':
    main()
