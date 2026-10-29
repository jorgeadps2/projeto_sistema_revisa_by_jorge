# -*- coding: utf-8 -*-
"""Relatório somente leitura da planilha de folha 2026. Não modifica a planilha original."""
import sys, os, openpyxl, csv
from datetime import datetime
from tkinter import Tk, filedialog, messagebox

def main():
    root=Tk();root.withdraw()
    path=filedialog.askopenfilename(title='Selecione a planilha original',filetypes=[('Excel','*.xlsx *.xlsm')])
    if not path: return
    try:
        wb=openpyxl.load_workbook(path,data_only=False,read_only=True)
        ws=wb['2026']
        months=['JANEIRO','FEVEREIRO','MARÇO','MARCO','ABRIL','MAIO','JUNHO','JULHO','AGOSTO','SETEMBRO','OUTUBRO','OUTRUBRO','NOVEMBRO','DEZEMBRO']
        rows=[]
        for r in range(1,ws.max_row+1):
            title=str(ws.cell(r,1).value or '').upper()
            if 'FOLHA PAGAMENTO' in title and '2026' in title:
                month=next((m for m in months if m in title), 'MÊS NÃO IDENTIFICADO')
                rows.append([r,month,title])
        out=os.path.join(os.path.dirname(path),f'relatorio_importacao_folha_2026_{datetime.now():%Y%m%d_%H%M%S}.csv')
        with open(out,'w',newline='',encoding='utf-8-sig') as f:
            w=csv.writer(f,delimiter=';');w.writerow(['Linha Excel','Mês detectado','Título original']);w.writerows(rows)
        wb.close();messagebox.showinfo('Relatório criado',f'Relatório de leitura criado em:\n{out}\n\nA planilha original não foi alterada.')
    except Exception as e: messagebox.showerror('Erro',str(e))
    finally: root.destroy()
if __name__=='__main__': main()
