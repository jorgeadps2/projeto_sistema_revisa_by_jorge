import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import controle_energia_agua as sistema


class RateiosTest(unittest.TestCase):
    def setUp(self):
        self.app = sistema.App.__new__(sistema.App)
        self.app.embutido = False
        self.app.conn = sqlite3.connect(":memory:")
        self.app.conn.row_factory = sqlite3.Row
        self.addCleanup(self.app.conn.close)
        self.app.criar_banco()
        self.mid = self.app.garantir_mes(2026, 1)
        self.app.conn.execute(
            "UPDATE meses SET conta_agua=240,total_pessoas_agua=12,limpeza_calha=60 WHERE id=?",
            (self.mid,),
        )
        self.ids = []
        for nome, pessoas, partes in (("TESTE A", 3, 2), ("TESTE B", 2, 1)):
            oid = self.app.conn.execute("INSERT INTO ocupantes(nome) VALUES(?)", (nome,)).lastrowid
            lid = self.app.conn.execute(
                """INSERT INTO lancamentos(mes_id,ocupante_id,numero_pessoas,agua_partes,
                   leitura_inicial,leitura_final,tarifa_kwh,aluguel,outras_despesas,ajuste)
                   VALUES(?,?,?,?,10,12,5,100,999,5)""",
                (self.mid, oid, pessoas, partes),
            ).lastrowid
            self.ids.append(lid)
        self.app.conn.commit()

    def row(self, lid):
        return self.app.conn.execute("SELECT * FROM lancamentos WHERE id=?", (lid,)).fetchone()

    def flags(self, **mudancas):
        flags = {chave: True for chave, _ in sistema.COBRANCAS}
        flags.update(mudancas)
        return flags

    def test_chave_nome_ocupante_ignora_acentos_e_simbolo_corrompido(self):
        correto="MARCOS - MM FULG\u00d5ES"
        corrompido="MARCOS - MM FULG\u00c3\u2022ES"
        self.assertEqual(sistema.chave_nome_ocupante(correto),
                         sistema.chave_nome_ocupante(corrompido))

    def test_nao_cadastra_ocupante_com_nome_corrompido_duplicado(self):
        self.app.oc_nome=SimpleNamespace(get=lambda:"MARCOS - MM FULG\u00c3\u2022ES")
        self.app.atualizar_ocupantes=Mock()
        with patch.object(sistema.messagebox,"showwarning") as aviso:
            self.app.adicionar_ocupante()
        aviso.assert_called_once()
        self.app.atualizar_ocupantes.assert_not_called()
        self.assertEqual(
            self.app.conn.execute(
                "SELECT COUNT(*) FROM ocupantes WHERE nome='MARCOS - MM FULG\u00c3\u2022ES'"
            ).fetchone()[0],
            0,
        )

    def test_observacao_do_inquilino_e_salva_e_migrada(self):
        oid=self.row(self.ids[0])["ocupante_id"]
        self.app.salvar_observacao_ocupante(oid,"Portão lateral")
        self.assertEqual(
            self.app.conn.execute(
                "SELECT observacoes FROM ocupantes WHERE id=?",(oid,)
            ).fetchone()["observacoes"],
            "Portão lateral",
        )
        self.assertIn(
            "observacoes",
            {r["name"] for r in self.app.conn.execute("PRAGMA table_info(ocupantes)")},
        )

    def test_cobranca_padrao_exibida_corresponde_ao_mes_selecionado(self):
        ocupante=self.app.conn.execute(
            "SELECT * FROM ocupantes WHERE id=?",(self.row(self.ids[0])["ocupante_id"],)
        ).fetchone()
        janeiro=self.app.regra_cobranca_ocupante(ocupante,2026,1)
        self.assertEqual(janeiro["cobrar_agua"],1)
        self.app.aplicar_padrao_cobrancas(
            ocupante["id"],self.flags(agua=False),2026,3
        )
        atualizado=self.app.conn.execute(
            "SELECT * FROM ocupantes WHERE id=?",(ocupante["id"],)
        ).fetchone()
        self.assertEqual(self.app.regra_cobranca_ocupante(atualizado,2026,2)["cobrar_agua"],1)
        self.assertEqual(self.app.regra_cobranca_ocupante(atualizado,2026,3)["cobrar_agua"],0)
        self.assertEqual(self.app.regra_cobranca_ocupante(atualizado,2026,4)["cobrar_agua"],0)

    def test_um_clique_na_cobranca_salva_padrao_do_mes_selecionado_em_diante(self):
        ocupante_id=self.row(self.ids[0])["ocupante_id"]
        self.app.oc_tree=Mock()
        self.app.oc_tree.identify_region.return_value="cell"
        self.app.oc_tree.identify_row.return_value=str(ocupante_id)
        self.app.oc_tree.identify_column.return_value="#4"
        self.app.oc_tree.set.side_effect=lambda ident,col: (
            "Sim" if col!="cobrar_agua" else "Não"
        )
        self.app.m_ano=SimpleNamespace(get=lambda:"2026")
        self.app.m_mes=SimpleNamespace(get=lambda:"03")
        self.app.aplicar_padrao_cobrancas=Mock()
        self.app.atualizar_ocupantes=Mock()
        self.app.atualizar_lancamentos=Mock()
        self.app.editar_celula_inquilino(SimpleNamespace(x=20,y=10))
        flags={chave:True for chave,_ in sistema.COBRANCAS}
        flags["agua"]=True
        self.app.aplicar_padrao_cobrancas.assert_called_once_with(
            ocupante_id,flags,2026,3
        )
        self.app.atualizar_ocupantes.assert_called_once()
        self.app.atualizar_lancamentos.assert_called_once()

    def test_titulo_dos_lancamentos_mostra_mes_e_ano_selecionados(self):
        self.app.atualizar_aviso_aberto=Mock()
        self.app.lanc=Mock()
        self.app.lanc.get_children.return_value=()
        self.app.m_ano=SimpleNamespace(get=lambda:"2026")
        self.app.m_mes=SimpleNamespace(get=lambda:"02")
        self.app.lbl_mes_planilha=Mock()
        self.app.atualizar_lancamentos()
        self.app.lbl_mes_planilha.config.assert_called_once_with(
            text="RESUMO MENSAL POR INQUILINO - FEVEREIRO DE 2026"
        )

    def test_pessoas_terreno_soma_todos_e_atualiza_por_mes(self):
        self.assertEqual(self.app.contas_mes(self.mid)["total_pessoas_agua"],5)
        self.app.salvar_cobrancas("lancamentos",self.ids[0],self.flags(agua=False,outras=False))
        oid=self.row(self.ids[0])["ocupante_id"]
        self.app.conn.execute("UPDATE ocupantes SET ativo=0 WHERE id=?",(oid,))
        self.assertEqual(self.app.pessoas_terreno(self.mid),5)
        self.assertEqual(self.app.pessoas_cobradas(self.mid,"agua"),2)
        outro=self.app.garantir_mes(2026,2)
        self.app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id,numero_pessoas) VALUES(?,?,8)",(outro,oid)
        )
        self.assertEqual(self.app.pessoas_terreno(outro),8)
        self.app.conn.execute("UPDATE lancamentos SET numero_pessoas=4 WHERE id=?",(self.ids[1],))
        self.assertEqual(self.app.contas_mes(self.mid)["total_pessoas_agua"],7)
        self.app.m_ano=SimpleNamespace(get=lambda:"2026")
        self.app.m_mes=SimpleNamespace(get=lambda:"01")
        self.app.agua_total_var=Mock(get=lambda:"valor inválido")
        self.app.agua_pessoas_var=Mock()
        self.app.agua_por_pessoa=Mock()
        self.app.atualizar_previa_agua()
        self.app.agua_pessoas_var.set.assert_called_with("7")
        self.app.conn.execute("DELETE FROM lancamentos WHERE mes_id=?",(outro,))
        self.assertEqual(self.app.contas_mes(outro)["total_pessoas_agua"],0)

    def test_leitura_atual_atualiza_mes_seguinte_e_preserva_leitura_digitada(self):
        ocupante_id=self.row(self.ids[0])["ocupante_id"]
        fevereiro=self.app.garantir_mes(2026,2)
        fevereiro_id=self.app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id,leitura_inicial,leitura_final) "
            "VALUES(?,?,10,10)",
            (fevereiro,ocupante_id),
        ).lastrowid
        marco=self.app.garantir_mes(2026,3)
        marco_id=self.app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id,leitura_inicial,leitura_final) "
            "VALUES(?,?,10,25)",
            (marco,ocupante_id),
        ).lastrowid

        self.app.propagar_leitura_seguinte(ocupante_id,2026,1,20)

        fevereiro_lancamento=self.row(fevereiro_id)
        self.assertEqual(fevereiro_lancamento["leitura_inicial"],20)
        self.assertEqual(fevereiro_lancamento["leitura_final"],20)
        marco_lancamento=self.row(marco_id)
        self.assertEqual(marco_lancamento["leitura_inicial"],10)
        self.assertEqual(marco_lancamento["leitura_final"],25)

    def test_leitura_atual_atualiza_mes_seguinte_na_virada_do_ano(self):
        ocupante_id=self.row(self.ids[0])["ocupante_id"]
        dezembro=self.app.garantir_mes(2026,12)
        dezembro_id=self.app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id,leitura_inicial,leitura_final) "
            "VALUES(?,?,10,20)",
            (dezembro,ocupante_id),
        ).lastrowid
        janeiro=self.app.garantir_mes(2027,1)
        janeiro_id=self.app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id,leitura_inicial,leitura_final) "
            "VALUES(?,?,20,23)",
            (janeiro,ocupante_id),
        ).lastrowid

        self.app.propagar_leitura_seguinte(ocupante_id,2026,12,22)

        self.assertEqual(self.row(janeiro_id)["leitura_inicial"],22)
        self.assertEqual(self.row(janeiro_id)["leitura_final"],23)
        self.assertEqual(self.row(dezembro_id)["leitura_final"],20)

    def test_aviso_aberto_mostra_mes_e_valor_sem_detalhes_extras(self):
        self.app.aviso_aberto=Mock()
        self.app.nb=Mock()
        self.app.m_ano=SimpleNamespace(get=lambda:"2027")
        self.app.m_mes=SimpleNamespace(get=lambda:"12")
        for lid in self.ids:
            self.app.salvar_cobrancas("lancamentos",lid,self.flags(
                energia=False,agua=False,outras=False,ajuste=False
            ))
        oid=self.row(self.ids[0])["ocupante_id"]
        outro=self.app.garantir_mes(2026,2)
        self.app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id,aluguel) VALUES(?,?,50)",(outro,oid)
        )
        self.app.conn.execute("UPDATE ocupantes SET ativo=0 WHERE id=?",(oid,))
        revisa=self.app.conn.execute("SELECT id FROM ocupantes WHERE nome='REVISA'").fetchone()[0]
        self.app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id,aluguel) VALUES(?,?,900)",(self.mid,revisa)
        )
        self.app.conn.commit()
        with patch.object(sistema,"date",SimpleNamespace(today=lambda:date(2026,3,1))):
            self.app.atualizar_aviso_aberto()
        texto=self.app.aviso_aberto.config.call_args.kwargs["text"]
        self.assertEqual(
            texto,
            "ATEN\u00c7\u00c3O: em aberto\nJANEIRO DE 2026 — TESTE A: "+sistema.moeda(100)+
            "\nJANEIRO DE 2026 — TESTE B: "+sistema.moeda(100)+
            "\nFEVEREIRO DE 2026 — TESTE A: "+sistema.moeda(50),
        )
        self.assertNotIn("lançamento",texto)
        self.assertNotIn("considerando todos os meses",texto)
        self.app.aviso_aberto.pack.assert_called_with(before=self.app.nb,fill="x",padx=16,pady=(0,6))
        self.app.aviso_aberto.pack_forget.assert_not_called()
        for row in self.app.conn.execute("SELECT * FROM lancamentos").fetchall():
            saldo=self.app.valores_lancamento(row)[-1]
            if saldo:
                self.app.conn.execute(
                    "INSERT INTO pagamentos(lancamento_id,data_pagamento,valor) VALUES(?,'2026-02-20',?)",
                    (row["id"],saldo),
                )
        self.app.conn.commit()
        with patch.object(sistema,"date",SimpleNamespace(today=lambda:date(2026,3,1))):
            self.app.atualizar_aviso_aberto()
        self.app.aviso_aberto.pack_forget.assert_called_once()
        pid=self.app.conn.execute(
            "SELECT id FROM pagamentos WHERE lancamento_id=?",(self.ids[0],)
        ).fetchone()[0]
        self.app.reverter_pagamento(pid,self.ids[0])
        with patch.object(sistema,"date",SimpleNamespace(today=lambda:date(2026,3,1))):
            self.app.atualizar_aviso_aberto()
        texto=self.app.aviso_aberto.config.call_args.kwargs["text"]
        self.assertIn("JANEIRO DE 2026 — TESTE A: "+sistema.moeda(100),texto)
        self.assertEqual(self.app.aviso_aberto.pack.call_count,2)

    def test_aviso_aberto_so_mostra_mes_depois_da_virada(self):
        self.app.aviso_aberto=Mock()
        self.app.nb=Mock()
        for lid in self.ids:
            self.app.salvar_cobrancas("lancamentos",lid,self.flags(
                energia=False,agua=False,aluguel=False,outras=False,ajuste=False
            ))
        oid=self.row(self.ids[0])["ocupante_id"]
        outubro=self.app.garantir_mes(2026,10)
        lid=self.app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id,aluguel) VALUES(?,?,100)",
            (outubro,oid),
        ).lastrowid
        self.app.conn.commit()

        with patch.object(sistema,"date",SimpleNamespace(today=lambda:date(2026,10,31))):
            self.app.atualizar_aviso_aberto()
        self.app.aviso_aberto.pack_forget.assert_called_once()

        with patch.object(sistema,"date",SimpleNamespace(today=lambda:date(2026,11,1))):
            self.app.atualizar_aviso_aberto()
        texto=self.app.aviso_aberto.config.call_args.kwargs["text"]
        self.assertEqual(
            texto,
            "ATEN\u00c7\u00c3O: em aberto\nOUTUBRO DE 2026 — TESTE A: "+sistema.moeda(100),
        )
        self.app.aviso_aberto.pack.assert_called_once()

    def carregar_mes_teste(self,ano,mes):
        self.app.m_ano=SimpleNamespace(get=lambda:str(ano))
        self.app.m_mes=SimpleNamespace(get=lambda:f"{mes:02d}")
        self.app.root=None
        self.app.carregar_rateio_agua=Mock()
        self.app.carregar_rateio_energia=Mock()
        self.app.atualizar_lancamentos=Mock()
        self.app.carregar_lancamentos()
        return self.app.conn.execute(
            "SELECT l.* FROM lancamentos l JOIN meses m ON m.id=l.mes_id "
            "WHERE m.ano=? AND m.mes=? AND l.ocupante_id=?",
            (ano,mes,self.row(self.ids[0])["ocupante_id"]),
        ).fetchone()

    def test_novo_mes_copia_aluguel_e_leitura_sem_consumo(self):
        self.app.conn.execute("UPDATE lancamentos SET numero_pessoas=3 WHERE id=?",(self.ids[0],))
        with patch.object(sistema.messagebox,"askyesno") as confirmar:
            novo=self.carregar_mes_teste(2026,2)
            confirmar.assert_not_called()
        self.assertEqual((novo["aluguel"],novo["leitura_inicial"],novo["leitura_final"]),(100,12,12))
        self.assertEqual(novo["numero_pessoas"],3)
        self.assertEqual(self.app.energia_lancamento(novo),0)
        self.assertEqual(novo["ajuste"],0)
        self.assertEqual(novo["outras_despesas"],0)
        self.app.conn.execute(
            "UPDATE lancamentos SET aluguel=150,leitura_final=42 WHERE id=?",(novo["id"],)
        )
        futuro=self.carregar_mes_teste(2027,1)
        self.assertEqual((futuro["aluguel"],futuro["leitura_inicial"],futuro["leitura_final"]),(150,42,42))
        self.assertEqual(futuro["numero_pessoas"],3)
        self.assertEqual(self.row(self.ids[0])["leitura_final"],12)

    def test_mes_existente_com_pessoas_zeradas_herda_mes_anterior(self):
        oid=self.row(self.ids[0])["ocupante_id"]
        outro_oid=self.row(self.ids[1])["ocupante_id"]
        self.app.conn.execute("UPDATE lancamentos SET numero_pessoas=4 WHERE id=?",(self.ids[0],))
        fevereiro=self.app.garantir_mes(2026,2)
        self.app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id,numero_pessoas) VALUES(?,?,0)",
            (fevereiro,oid),
        )
        self.app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id,numero_pessoas) VALUES(?,?,7)",
            (fevereiro,outro_oid),
        )
        self.app.conn.commit()

        with patch.object(sistema.messagebox,"askyesno",return_value=True):
            self.carregar_mes_teste(2026,2)

        herdado=self.app.conn.execute(
            "SELECT numero_pessoas FROM lancamentos WHERE mes_id=? AND ocupante_id=?",
            (fevereiro,oid),
        ).fetchone()["numero_pessoas"]
        preservado=self.app.conn.execute(
            "SELECT numero_pessoas FROM lancamentos WHERE mes_id=? AND ocupante_id=?",
            (fevereiro,outro_oid),
        ).fetchone()["numero_pessoas"]
        self.assertEqual(herdado,4)
        self.assertEqual(preservado,7)

    def test_alterar_pessoas_propaga_do_mes_selecionado_para_frente(self):
        oid=self.row(self.ids[0])["ocupante_id"]
        outro_oid=self.row(self.ids[1])["ocupante_id"]
        fevereiro=self.app.garantir_mes(2026,2)
        marco=self.app.garantir_mes(2026,3)
        outro_fevereiro=self.app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id,numero_pessoas) VALUES(?,?,8)",
            (fevereiro,outro_oid),
        ).lastrowid
        id_fevereiro=self.app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id,numero_pessoas) VALUES(?,?,1)",
            (fevereiro,oid),
        ).lastrowid
        id_marco=self.app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id,numero_pessoas) VALUES(?,?,2)",
            (marco,oid),
        ).lastrowid
        self.app.propagar_pessoas_futuras(oid,2026,2,4)
        self.assertEqual(self.row(self.ids[0])["numero_pessoas"],3)
        self.assertEqual(self.row(id_fevereiro)["numero_pessoas"],4)
        self.assertEqual(self.row(id_marco)["numero_pessoas"],4)
        self.assertEqual(self.row(outro_fevereiro)["numero_pessoas"],8)

    def test_pessoas_propaga_atualiza_total_do_terreno_e_rateio_da_agua(self):
        oid=self.row(self.ids[0])["ocupante_id"]
        outro_oid=self.row(self.ids[1])["ocupante_id"]
        fevereiro=self.app.garantir_mes(2026,2)
        marco=self.app.garantir_mes(2026,3)
        self.app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id,numero_pessoas) VALUES(?,?,1)",
            (fevereiro,oid),
        )
        self.app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id,numero_pessoas) VALUES(?,?,2)",
            (fevereiro,outro_oid),
        )
        id_marco=self.app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id,numero_pessoas) VALUES(?,?,1)",
            (marco,oid),
        ).lastrowid
        self.app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id,numero_pessoas) VALUES(?,?,2)",
            (marco,outro_oid),
        )
        self.app.conn.execute("UPDATE meses SET conta_agua=600 WHERE id=?",(fevereiro,))
        self.app.conn.execute("UPDATE meses SET conta_agua=300 WHERE id=?",(marco,))

        self.app.propagar_pessoas_futuras(oid,2026,2,4)

        self.assertEqual(self.app.pessoas_terreno(fevereiro),6)
        self.assertEqual(self.app.pessoas_cobradas(fevereiro,"agua"),6)
        self.assertAlmostEqual(self.app.cobrancas_lancamento(self.row(
            self.app.conn.execute(
                "SELECT id FROM lancamentos WHERE mes_id=? AND ocupante_id=?",(fevereiro,oid)
            ).fetchone()["id"]
        ))["agua"],400)
        self.assertEqual(self.app.pessoas_terreno(marco),6)
        self.assertEqual(self.row(id_marco)["numero_pessoas"],4)
        self.assertAlmostEqual(self.app.cobrancas_lancamento(self.row(id_marco))["agua"],200)

    def test_mes_sem_anterior_nao_copia_futuro(self):
        novo=self.carregar_mes_teste(2026,3)
        self.app.conn.execute("UPDATE lancamentos SET aluguel=200,leitura_final=90 WHERE id=?",(novo["id"],))
        anterior=self.carregar_mes_teste(2026,2)
        self.assertEqual((anterior["aluguel"],anterior["leitura_inicial"]),(100,12))
        oid=self.app.conn.execute("INSERT INTO ocupantes(nome) VALUES('SEM HISTORICO')").lastrowid
        self.app.conn.commit()
        with patch.object(sistema.messagebox,"askyesno",return_value=False):
            self.carregar_mes_teste(2026,1)
        primeiro=self.app.conn.execute(
            "SELECT * FROM lancamentos WHERE mes_id=? AND ocupante_id=?",(self.mid,oid)
        ).fetchone()
        self.assertEqual((primeiro["aluguel"],primeiro["leitura_inicial"],primeiro["leitura_final"]),(0,0,0))

    def test_mes_existente_exige_confirmacao_e_preserva_digitados(self):
        novo=self.carregar_mes_teste(2026,2)
        self.app.conn.execute(
            "UPDATE lancamentos SET aluguel=0,leitura_inicial=0,leitura_final=30,cobrar_aluguel=0 WHERE id=?",
            (novo["id"],),
        )
        self.app.conn.commit()
        with patch.object(sistema.messagebox,"askyesno",return_value=False) as confirmar:
            mantido=self.carregar_mes_teste(2026,2)
            confirmar.assert_called_once()
        self.assertEqual((mantido["aluguel"],mantido["leitura_inicial"],mantido["leitura_final"]),(0,0,30))
        with patch.object(sistema.messagebox,"askyesno",return_value=True):
            corrigido=self.carregar_mes_teste(2026,2)
        self.assertEqual((corrigido["aluguel"],corrigido["leitura_inicial"],corrigido["leitura_final"]),(100,12,30))
        self.assertEqual(corrigido["cobrar_aluguel"],0)
        self.assertEqual(self.app.cobrancas_lancamento(corrigido)["aluguel"],0)
        self.app.conn.execute("UPDATE lancamentos SET aluguel=200,leitura_inicial=20 WHERE id=?",(novo["id"],))
        with patch.object(sistema.messagebox,"askyesno") as confirmar:
            mantido=self.carregar_mes_teste(2026,2)
            confirmar.assert_not_called()
        self.assertEqual((mantido["aluguel"],mantido["leitura_inicial"],mantido["leitura_final"]),(200,20,30))

    def test_corrigir_mes_zerado_sem_sobrescrever_pagamentos_ou_leitura_menor(self):
        novo=self.carregar_mes_teste(2026,2)
        self.app.conn.execute(
            "UPDATE lancamentos SET aluguel=0,leitura_inicial=0,leitura_final=0 WHERE id=?",(novo["id"],)
        )
        with patch.object(sistema.messagebox,"askyesno",return_value=True):
            corrigido=self.carregar_mes_teste(2026,2)
        self.assertEqual((corrigido["aluguel"],corrigido["leitura_inicial"],corrigido["leitura_final"]),(100,12,12))
        self.app.conn.execute("UPDATE lancamentos SET leitura_inicial=0,leitura_final=5 WHERE id=?",(novo["id"],))
        with patch.object(sistema.messagebox,"askyesno") as confirmar:
            mantido=self.carregar_mes_teste(2026,2)
            confirmar.assert_not_called()
        self.assertEqual((mantido["leitura_inicial"],mantido["leitura_final"]),(0,5))
        self.app.conn.execute("UPDATE lancamentos SET aluguel=0,leitura_inicial=0,leitura_final=0 WHERE id=?",(novo["id"],))
        self.app.conn.execute(
            "INSERT INTO pagamentos(lancamento_id,data_pagamento,valor) VALUES(?,'2026-02-15',10)",(novo["id"],)
        )
        self.app.conn.commit()
        with patch.object(sistema.messagebox,"askyesno") as confirmar:
            mantido=self.carregar_mes_teste(2026,2)
            confirmar.assert_not_called()
        self.assertEqual((mantido["aluguel"],mantido["leitura_inicial"],mantido["leitura_final"]),(0,0,0))

    def test_somente_luz_e_pagamento(self):
        lid = self.ids[0]
        flags = {chave: chave == "energia" for chave, _ in sistema.COBRANCAS}
        self.app.salvar_cobrancas("lancamentos", lid, flags)
        self.app.conn.execute(
            "INSERT INTO pagamentos(lancamento_id,data_pagamento,valor) VALUES(?, '2026-01-15', 4)",
            (lid,),
        )
        self.assertEqual(self.app.valores_lancamento(self.row(lid)), (10, 0, 10, 4, 6))
        valores = self.app.cobrancas_lancamento(self.row(lid))
        self.assertEqual(valores, dict(energia=10, agua=0, aluguel=0, outras=0, ajuste=0))

    def test_agua_redistribuida_sem_isentos(self):
        self.app.salvar_cobrancas("lancamentos", self.ids[0], self.flags(agua=False))
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[0]))["agua"], 0)
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[1]))["agua"], 240)
        self.assertEqual(self.app.pessoas_cobradas(self.mid, "agua"), 2)

    def test_letras_pagamento_sem_fundo_colorido_e_sem_frases_removidas(self):
        root=sistema.tk.Tk()
        self.addCleanup(root.destroy)
        root.withdraw()
        self.app.root=root
        self.app.configurar_estilo()
        self.app.tab_mes=sistema.ttk.Frame(root)
        self.app.montar_mes()
        from tkinter import font
        for tag,cor,peso in (("pago","#145da0","bold"),("em_aberto","#b02020","bold")):
            estilo=self.app.lanc.tag_configure(tag)
            self.assertEqual(estilo["foreground"],cor)
            self.assertFalse(estilo["background"])
            self.assertEqual(font.Font(root=root,font=estilo["font"]).actual("weight"),peso)
        self.app.conn.execute("UPDATE meses SET usar_rateio_despesas=0 WHERE id=?",(self.mid,))
        self.app.atualizar_despesas(self.mid)
        self.assertEqual(self.app.despesas_resumo["text"],"")
        def textos(widget):
            for filho in widget.winfo_children():
                if isinstance(filho,sistema.ttk.Label):
                    yield filho["text"]
                yield from textos(filho)
        self.assertFalse(any("Energia =" in texto for texto in textos(self.app.tab_mes)))

    def test_tema_escuro_em_todas_as_abas_preserva_destaques(self):
        root=sistema.tk.Tk()
        self.addCleanup(root.destroy)
        root.withdraw()
        self.app.root=root
        self.app.configurar_estilo()
        self.app.montar()
        estilo=sistema.ttk.Style(root)
        self.assertEqual(root["background"].lower(),sistema.FUNDO.lower())
        for nome in ("TFrame","TLabel","TLabelframe","TLabelframe.Label","TNotebook"):
            self.assertEqual(estilo.lookup(nome,"background").lower(),sistema.FUNDO.lower())
        self.assertEqual(estilo.lookup("TLabel","foreground").lower(),sistema.TEXTO_CLARO.lower())
        self.assertEqual(estilo.lookup("Treeview","fieldbackground"),"#ffffff")
        self.assertEqual(estilo.lookup("Treeview","background",("selected",)),"#dce7f0")
        self.assertEqual(estilo.lookup("TCombobox","fieldbackground",("readonly",)),"#ffffff")
        self.assertEqual(estilo.lookup("TNotebook.Tab","background",("selected",)).lower(),sistema.AZUL.lower())
        self.assertEqual(str(self.app.botao_alterar_senha["text"]),"Alterar senha")
        self.assertEqual((self.app.icone_senha.width(),self.app.icone_senha.height()),(24,24))
        self.assertEqual(self.app.lanc.tag_configure("pago")["foreground"],"#145da0")
        self.assertEqual(self.app.lanc.tag_configure("em_aberto")["foreground"],"#b02020")
        def verificar(widget):
            if "background" in widget.keys():
                self.assertNotIn(widget["background"],("#101820","#0b1118"))
            for filho in widget.winfo_children():
                verificar(filho)
        verificar(root)
        self.assertEqual(self.app.nb["style"],"Navigation.TNotebook")
        self.assertEqual(len(self.app.icones_navegacao),5)
        for icone in self.app.icones_navegacao:
            self.assertEqual((icone.width(),icone.height()),(24,24))
        self.assertEqual(estilo.lookup("ToolbarSelected.TButton","background").lower(),sistema.AZUL.lower())
        self.assertEqual(estilo.lookup("ToolbarSelected.TButton","background",("active",)).lower(),sistema.AZUL_ESCURO.lower())
        self.assertEqual(estilo.lookup("ToolbarSelected.TButton","background",("pressed",)).lower(),sistema.AZUL_ESCURO.lower())
        for indice,titulo in enumerate(("Lançamentos mensais","Inquilinos","Relatórios e backup")):
            self.assertEqual(str(self.app.botoes_navegacao[indice]["compound"]),"top")
            self.assertTrue(self.app.botoes_navegacao[indice]["image"])
            self.app.botoes_navegacao[indice].invoke()
            root.update()
            self.assertEqual(self.app.nb.index(self.app.nb.select()),indice)
            self.assertEqual(self.app.titulo_pagina["text"],titulo)
            for outro,botao in self.app.botoes_navegacao.items():
                self.assertEqual(botao["style"],"ToolbarSelected.TButton" if outro==indice else "Toolbar.TButton")
        self.app.nb.select(0)
        root.update()
        self.assertEqual(self.app.titulo_pagina["text"],"Lançamentos mensais")

    def test_linhas_acompanham_saldo_pagamento_e_reversao(self):
        self.app.m_ano=SimpleNamespace(get=lambda:"2026")
        self.app.m_mes=SimpleNamespace(get=lambda:"01")
        self.app.lanc=Mock()
        self.app.lanc.get_children.return_value=()
        self.app.lbl_total=Mock()
        self.app.atualizar_previa_agua=Mock()
        self.app.atualizar_despesas=Mock()
        oid=self.app.conn.execute("SELECT id FROM ocupantes WHERE nome='REVISA'").fetchone()[0]
        self.app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id,aluguel) VALUES(?,?,100)",(self.mid,oid)
        )
        def estilos():
            self.app.lanc.insert.reset_mock()
            self.app.atualizar_lancamentos()
            return {call.kwargs["values"][1]:call.kwargs["tags"] for call in self.app.lanc.insert.call_args_list}
        self.assertEqual(estilos(),{"REVISA":("pago",),"TESTE A":("em_aberto",),"TESTE B":("em_aberto",)})
        lid=self.ids[0]
        total=self.app.valores_lancamento(self.row(lid))[2]
        self.app.conn.execute(
            "INSERT INTO pagamentos(lancamento_id,data_pagamento,valor) VALUES(?,'2026-01-15',1)",(lid,)
        )
        self.assertEqual(estilos()["TESTE A"],("em_aberto",))
        pid=self.app.conn.execute(
            "INSERT INTO pagamentos(lancamento_id,data_pagamento,valor) VALUES(?,'2026-01-15',?)",(lid,total-1)
        ).lastrowid
        self.assertEqual(estilos()["TESTE A"],("pago",))
        self.app.reverter_pagamento(pid,lid)
        self.assertEqual(estilos()["TESTE A"],("em_aberto",))
        self.app.salvar_cobrancas("lancamentos",self.ids[1],{chave:False for chave,_ in sistema.COBRANCAS})
        self.assertEqual(estilos()["TESTE B"],("pago",))

    def test_revisa_quitada_em_meses_antigos_e_futuros(self):
        oid=self.app.conn.execute("SELECT id FROM ocupantes WHERE nome='REVISA'").fetchone()[0]
        for ano,mes in ((2025,12),(2026,1),(2027,2)):
            mid=self.app.garantir_mes(ano,mes)
            lid=self.app.conn.execute(
                "INSERT INTO lancamentos(mes_id,ocupante_id,aluguel,outras_despesas,ajuste) VALUES(?,?,100,20,5)",
                (mid,oid),
            ).lastrowid
            self.app.conn.execute("UPDATE meses SET usar_rateio_despesas=0 WHERE id=?",(mid,))
            valores=self.app.valores_lancamento(self.row(lid))
            self.assertEqual(valores[2:],(125,125,0))
            self.app.conn.execute("UPDATE lancamentos SET aluguel=150 WHERE id=?",(lid,))
            self.assertEqual(self.app.valores_lancamento(self.row(lid))[2:],(175,175,0))
        self.assertEqual(self.app.conn.execute("SELECT COUNT(*) FROM pagamentos").fetchone()[0],0)
        self.assertGreater(self.app.valores_lancamento(self.row(self.ids[0]))[-1],0)

    def test_revisa_baixa_complementa_manual_sem_duplicar(self):
        oid=self.app.conn.execute("SELECT id FROM ocupantes WHERE nome='REVISA'").fetchone()[0]
        lid=self.app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id,aluguel) VALUES(?,?,100)",(self.mid,oid)
        ).lastrowid
        pid=self.app.conn.execute(
            "INSERT INTO pagamentos(lancamento_id,data_pagamento,valor) VALUES(?,'2026-01-15',30)",(lid,)
        ).lastrowid
        self.assertEqual(self.app.valores_lancamento(self.row(lid))[2:],(100,100,0))
        self.assertEqual(self.app.baixa_automatica(self.row(lid),100,30),70)
        self.app.reverter_pagamento(pid,lid)
        self.assertEqual(self.app.valores_lancamento(self.row(lid))[2:],(100,100,0))
        self.app.conn.execute("UPDATE lancamentos SET aluguel=-10 WHERE id=?",(lid,))
        self.assertEqual(self.app.valores_lancamento(self.row(lid))[2:],(-10,0,0))

    def test_reverter_pagamento_recalcula_e_preserva_outros(self):
        lid=self.ids[0]
        self.app.salvar_cobrancas("lancamentos",lid,self.flags(
            energia=True,agua=False,aluguel=False,outras=False,ajuste=False
        ))
        ids=[]
        for alvo,valor in ((lid,4),(lid,6),(self.ids[1],20)):
            ids.append(self.app.conn.execute(
                "INSERT INTO pagamentos(lancamento_id,data_pagamento,valor) VALUES(?,'2026-01-15',?)",
                (alvo,valor),
            ).lastrowid)
        self.app.conn.commit()
        self.assertEqual(self.app.valores_lancamento(self.row(lid))[-2:],(10,0))
        with self.assertRaises(ValueError):
            self.app.reverter_pagamento(ids[0],self.ids[1])
        self.assertIsNone(self.app.conn.execute("SELECT revertido_em FROM pagamentos WHERE id=?",(ids[0],)).fetchone()[0])
        self.app.reverter_pagamento(ids[0],lid)
        self.assertEqual(self.app.valores_lancamento(self.row(lid))[-2:],(6,4))
        with self.assertRaises(ValueError):
            self.app.reverter_pagamento(ids[0],lid)
        self.app.reverter_pagamento(ids[1],lid)
        self.assertEqual(self.app.valores_lancamento(self.row(lid))[-2:],(0,10))
        self.assertEqual(self.app.valores_lancamento(self.row(self.ids[1]))[-2],20)
        self.assertEqual(self.app.conn.execute("SELECT COUNT(*) FROM pagamentos").fetchone()[0],3)
        self.app.criar_banco()
        self.assertEqual(self.app.valores_lancamento(self.row(lid))[-2:],(0,10))

    def test_limpeza_calha_legada_nao_e_cobrada(self):
        cobrancas=self.app.cobrancas_lancamento(self.row(self.ids[1]))
        self.assertNotIn("calha",cobrancas)
        self.assertEqual(
            self.app.valores_lancamento(self.row(self.ids[1]))[2],
            sum(cobrancas.values()),
        )

    def test_despesas_substituem_valores_individuais(self):
        self.app.gravar_despesa(self.mid, "Manutencao", 120)
        self.app.gravar_despesa(self.mid, "Material", 60)
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[0]))["outras"], 108)
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[1]))["outras"], 72)
        self.app.salvar_cobrancas("lancamentos", self.ids[0], self.flags(outras=False))
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[0]))["outras"], 0)
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[1]))["outras"], 72)
        self.assertEqual(self.row(self.ids[0])["outras_despesas"], 999)

    def test_despesas_mistas_por_pessoas_e_igual_por_inquilino(self):
        self.app.gravar_despesa(self.mid,"Por pessoas",120)
        self.app.gravar_despesa(self.mid,"Igual",60,rateio="inquilinos")
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[0]))["outras"],132)
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[1]))["outras"],108)
        self.assertEqual(self.app.total_despesas(self.mid),180)
        self.app.salvar_cobrancas("lancamentos",self.ids[0],self.flags(outras=False))
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[0]))["outras"],0)
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[1]))["outras"],108)
        self.app.conn.execute("UPDATE lancamentos SET numero_pessoas=0 WHERE id=?",(self.ids[1],))
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[1]))["outras"],60)

    def test_despesa_direcionada_e_rateio_somam_aos_valores_existentes(self):
        self.app.conn.execute(
            "UPDATE meses SET usar_rateio_despesas=0 WHERE id=?",(self.mid,)
        )
        self.app.conn.execute(
            "UPDATE lancamentos SET outras_despesas=25 WHERE id=?",(self.ids[0],)
        )
        self.app.conn.execute(
            "UPDATE lancamentos SET outras_despesas=10 WHERE id=?",(self.ids[1],)
        )
        self.app.gravar_despesa(
            self.mid,"Reparo individual",100,ocupante_id=self.row(self.ids[0])["ocupante_id"]
        )
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[0]))["outras"],125)
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[1]))["outras"],10)
        self.app.gravar_despesa(self.mid,"Material comum",100,rateio="inquilinos")
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[0]))["outras"],225)
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[1]))["outras"],110)
        self.assertEqual(
            self.app.conn.execute("SELECT usar_rateio_despesas FROM meses WHERE id=?",(self.mid,)).fetchone()[0],
            0,
        )
        ident=self.app.conn.execute(
            "SELECT id FROM despesas_mes WHERE descricao='Reparo individual'"
        ).fetchone()[0]
        self.app.gravar_despesa(
            self.mid,"Reparo alterado",30,ident,ocupante_id=self.row(self.ids[1])["ocupante_id"]
        )
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[0]))["outras"],125)
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[1]))["outras"],140)

    def test_rateio_igual_sem_pessoas_edicao_exclusao_e_isencoes(self):
        self.app.conn.execute("UPDATE meses SET total_pessoas_agua=0 WHERE id=?",(self.mid,))
        self.app.conn.execute("UPDATE lancamentos SET numero_pessoas=0 WHERE mes_id=?",(self.mid,))
        self.app.gravar_despesa(self.mid,"Igual",100,rateio="inquilinos")
        ident=self.app.conn.execute("SELECT id FROM despesas_mes WHERE mes_id=?",(self.mid,)).fetchone()[0]
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[0]))["outras"],100)
        with self.assertRaises(ValueError):
            self.app.gravar_despesa(self.mid,"Invalido",10,rateio="invalido")
        with self.assertRaises(ValueError):
            self.app.gravar_despesa(self.mid,"Por pessoas",100,ident,rateio="pessoas")
        self.assertEqual(self.app.total_despesas(self.mid,"inquilinos"),100)
        self.app.conn.execute("UPDATE meses SET total_pessoas_agua=10 WHERE id=?",(self.mid,))
        self.app.conn.execute("UPDATE lancamentos SET numero_pessoas=3 WHERE id=?",(self.ids[0],))
        self.app.conn.execute("UPDATE lancamentos SET numero_pessoas=7 WHERE id=?",(self.ids[1],))
        self.app.gravar_despesa(self.mid,"Por pessoas",100,ident,rateio="pessoas")
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[0]))["outras"],30)
        self.app.gravar_despesa(self.mid,"Igual novamente",100,ident,rateio="inquilinos")
        for lid in self.ids:
            self.app.salvar_cobrancas("lancamentos",lid,self.flags(outras=False))
            self.assertEqual(self.app.cobrancas_lancamento(self.row(lid))["outras"],0)
        self.app.conn.execute("DELETE FROM despesas_mes WHERE id=?",(ident,))
        self.assertEqual(self.app.total_despesas(self.mid),0)

    def test_despesa_pode_ser_lancada_em_meses_individuais(self):
        periodos=[(2026,1),(2026,3),(2027,2)]
        self.app.gravar_despesa_multimes(
            periodos,"Manutenção", [100,100,100],rateio="inquilinos",
        )
        valores=self.app.conn.execute(
            "SELECT m.ano,m.mes,d.valor FROM despesas_mes d "
            "JOIN meses m ON m.id=d.mes_id WHERE d.descricao=? ORDER BY m.ano,m.mes",
            ("Manutenção",),
        ).fetchall()
        self.assertEqual(
            [(row["ano"],row["mes"],row["valor"]) for row in valores],
            [(2026,1,100),(2026,3,100),(2027,2,100)],
        )

    def test_dividir_valor_total_em_meses_distribui_centavos(self):
        valores=sistema.dividir_valor_por_meses(10,3)
        self.assertEqual(valores,[3.34,3.33,3.33])
        self.assertEqual(round(sum(valores),2),10)
        with self.assertRaisesRegex(ValueError,"R\\$ 0,01"):
            sistema.dividir_valor_por_meses(0.02,3)

    def test_portao_89550_para_tres_inquilinos_em_setembro_e_outubro(self):
        terceiros=self.app.conn.execute("INSERT INTO ocupantes(nome) VALUES('TESTE C')").lastrowid
        selecionados=[self.row(lid)["ocupante_id"] for lid in self.ids]+[terceiros]
        periodos=[(2026,9),(2026,10)]
        valores=sistema.dividir_valor_por_meses(895.50,len(periodos))
        self.app.gravar_despesa_multimes(
            periodos,"Conserto de portão",valores,
            ocupantes_ids=selecionados,
        )
        despesas=self.app.conn.execute(
            "SELECT d.*,m.ano,m.mes FROM despesas_mes d JOIN meses m ON m.id=d.mes_id"
        ).fetchall()
        self.assertEqual(len(despesas),6)
        self.assertEqual(sum(d["valor"] for d in despesas),895.50)
        self.assertEqual({d["ocupante_id"] for d in despesas},set(selecionados))
        self.assertEqual({d["mes"] for d in despesas},{9,10})
        for despesa in despesas:
            self.assertEqual(despesa["valor"],149.25)
            self.assertEqual(despesa["rateio"],"individual")
            self.app.conn.execute(
                "INSERT INTO lancamentos(mes_id,ocupante_id) VALUES(?,?)",
                (despesa["mes_id"],despesa["ocupante_id"]),
            )
        for lancamento in self.app.conn.execute(
            "SELECT * FROM lancamentos WHERE mes_id!=?",(self.mid,),
        ).fetchall():
            self.assertEqual(self.app.cobrancas_lancamento(lancamento)["outras"],149.25)
        excluido=self.app.conn.execute("SELECT id FROM ocupantes WHERE nome='REVISA'").fetchone()["id"]
        for mid in {d["mes_id"] for d in despesas}:
            self.app.conn.execute(
                "INSERT INTO lancamentos(mes_id,ocupante_id) VALUES(?,?)",(mid,excluido),
            )
            lancamento=self.app.conn.execute(
                "SELECT * FROM lancamentos WHERE mes_id=? AND ocupante_id=?",(mid,excluido),
            ).fetchone()
            self.assertEqual(self.app.cobrancas_lancamento(lancamento)["outras"],0)
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[0]))["outras"],0)

    def test_selecao_preserva_centavos_e_nao_cobra_outros_inquilinos(self):
        selecionado=self.row(self.ids[0])["ocupante_id"]
        outro=self.row(self.ids[1])["ocupante_id"]
        self.app.gravar_despesa_multimes(
            [(2026,1)],"Parcela",[10],ocupantes_ids=[selecionado,outro],
        )
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[0]))["outras"],5)
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[1]))["outras"],5)
        self.app.gravar_despesa_multimes(
            [(2026,1)],"Somente um",[12.34],ocupantes_ids=[selecionado],
        )
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[0]))["outras"],17.34)
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[1]))["outras"],5)

    def test_tela_despesa_mostra_revisa_e_parcela_entre_selecionados(self):
        root=sistema.tk.Tk()
        self.addCleanup(root.destroy)
        root.update()
        self.app.root=root
        self.app.m_ano=SimpleNamespace(get=lambda:"2026")
        self.app.m_mes=SimpleNamespace(get=lambda:"01")
        self.app.atualizar_lancamentos=Mock()
        revisa=self.app.conn.execute("SELECT id FROM ocupantes WHERE nome='REVISA'").fetchone()[0]
        lid=self.app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id) VALUES(?,?)",(self.mid,revisa),
        ).lastrowid
        self.app.editar_despesa()
        win=next(w for w in root.winfo_children() if isinstance(w,sistema.tk.Toplevel))
        def descendentes(widget):
            for filho in widget.winfo_children():
                yield filho
                yield from descendentes(filho)
        widgets=list(descendentes(win))
        entries=[w for w in widgets if isinstance(w,sistema.ttk.Entry) and not isinstance(w,sistema.ttk.Combobox)]
        entries[0].insert(0,"Portão com REVISA")
        entries[1].insert(0,"895,50")
        destino=next(w for w in widgets if isinstance(w,sistema.ttk.Combobox) and "Escolher inquilinos" in w["values"])
        self.assertIn("REVISA",destino["values"])
        destino.set("Escolher inquilinos")
        destino.event_generate("<<ComboboxSelected>>")
        root.update()
        lista=next(w for w in widgets if isinstance(w,sistema.tk.Listbox) and "REVISA" in w.get(0,"end"))
        nomes=lista.get(0,"end")
        self.assertTrue(lista.winfo_ismapped())
        self.assertGreaterEqual(int(lista["height"]),6)
        self.assertTrue(lista["yscrollcommand"])
        for nome in ("REVISA","TESTE A","TESTE B"):
            lista.selection_set(nomes.index(nome))
        combos=[w for w in widgets if isinstance(w,sistema.ttk.Combobox)]
        mes=next(w for w in combos if "02" in w["values"])
        mes.set("02")
        next(w for w in widgets if isinstance(w,sistema.ttk.Button) and w["text"]=="Adicionar mês").invoke()
        next(w for w in widgets if isinstance(w,sistema.ttk.Radiobutton) and w["value"]=="dividir").invoke()
        root.update()
        self.assertLessEqual(win.winfo_reqheight(),root.winfo_screenheight())
        self.assertLessEqual(win.winfo_reqwidth(),root.winfo_screenwidth())
        with patch.object(sistema.messagebox,"askyesno",return_value=True) as confirmar, \
             patch.object(sistema.messagebox,"showerror") as erro:
            next(w for w in widgets if isinstance(w,sistema.ttk.Button) and w["text"]=="Salvar despesa").invoke()
        erro.assert_not_called()
        self.assertIn("REVISA: R$ 149,25",confirmar.call_args.args[1])
        despesas=self.app.conn.execute("SELECT * FROM despesas_mes").fetchall()
        self.assertEqual(len(despesas),6)
        self.assertEqual({d["valor"] for d in despesas},{149.25})
        self.assertEqual(sum(d["valor"] for d in despesas),895.50)
        self.assertEqual(sum(d["ocupante_id"]==revisa for d in despesas),2)
        self.assertEqual(self.app.cobrancas_lancamento(self.row(lid))["outras"],149.25)
        self.app.atualizar_lancamentos.assert_called_once()

    def test_selecionados_podem_receber_valor_integral_sem_dividir(self):
        ids=[self.row(lid)["ocupante_id"] for lid in self.ids]
        self.app.gravar_despesa_multimes(
            [(2026,1)],"Individual",[100],ocupantes_ids=ids,dividir_selecionados=False,
        )
        for lid in self.ids:
            self.assertEqual(self.app.cobrancas_lancamento(self.row(lid))["outras"],100)

    def test_selecao_invalida_ou_isenta_nao_grava_despesas(self):
        ident=self.row(self.ids[0])["ocupante_id"]
        for selecionados in ([],[ident,ident],[99999]):
            with self.assertRaises(ValueError):
                self.app.gravar_despesa_multimes(
                    [(2026,1)],"Inválida",[100],ocupantes_ids=selecionados,
                )
        self.app.salvar_cobrancas("lancamentos",self.ids[0],self.flags(outras=False))
        with self.assertRaisesRegex(ValueError,"isento"):
            self.app.gravar_despesa_multimes(
                [(2026,1)],"Isento",[100],ocupantes_ids=[ident],
            )
        self.assertEqual(self.app.conn.execute("SELECT COUNT(*) FROM despesas_mes").fetchone()[0],0)

    def test_selecao_distribui_centavos_e_reverte_tudo_em_falha(self):
        ids=[self.row(lid)["ocupante_id"] for lid in self.ids]
        self.app.gravar_despesa_multimes(
            [(2026,1)],"Centavos",[0.03],ocupantes_ids=ids,
        )
        self.assertEqual(
            [r["valor"] for r in self.app.conn.execute("SELECT valor FROM despesas_mes ORDER BY id")],
            [0.02,0.01],
        )
        self.app.conn.executescript(
            "CREATE TRIGGER falha_despesa BEFORE INSERT ON despesas_mes "
            "WHEN NEW.descricao='Falha' AND NEW.ocupante_id="+str(ids[1])+
            " BEGIN SELECT RAISE(ABORT,'falha de teste'); END;"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.app.gravar_despesa_multimes(
                [(2027,1)],"Falha",[100],ocupantes_ids=ids,
            )
        self.assertEqual(self.app.conn.execute(
            "SELECT COUNT(*) FROM despesas_mes WHERE descricao='Falha'",
        ).fetchone()[0],0)
        self.assertEqual(self.app.conn.execute(
            "SELECT COUNT(*) FROM meses WHERE ano=2027",
        ).fetchone()[0],0)

    def test_icone_imovel_tem_versoes_png_e_ico(self):
        from PIL import Image
        with Image.open(sistema.caminho_recurso("assets/imovel.png")) as imagem:
            self.assertEqual(imagem.format,"PNG")
            self.assertEqual(imagem.size,(256,256))
        with Image.open(sistema.caminho_recurso("assets/imovel.ico")) as imagem:
            self.assertEqual(imagem.format,"ICO")
            self.assertIn((16,16),imagem.ico.sizes())
            self.assertIn((256,256),imagem.ico.sizes())

    def test_janela_modal_minimizada_e_restaurada_com_a_janela_principal(self):
        root=Mock()
        root.bind.return_value="map_binding"
        win=Mock()
        win.winfo_exists.return_value=True
        win.state.return_value="iconic"
        sistema.vincular_restauracao_modal(root,win)
        ao_mapear=root.bind.call_args.args[1]
        ao_mapear(None)
        restaurar=win.after_idle.call_args.args[0]
        restaurar()
        win.deiconify.assert_called_once_with()
        win.lift.assert_called_once_with()
        win.grab_set.assert_called_once_with()
        ao_destruir=win.bind.call_args.args[1]
        ao_destruir(SimpleNamespace(widget=win))
        root.unbind.assert_called_once_with("<Map>","map_binding")

    def test_editar_excluir_despesa_e_isolar_mes(self):
        self.app.gravar_despesa(self.mid, "Material", 120)
        primeira = self.app.conn.execute("SELECT id FROM despesas_mes").fetchone()["id"]
        self.app.gravar_despesa(self.mid,"Reparo",60)
        segunda = self.app.conn.execute(
            "SELECT id FROM despesas_mes WHERE descricao='Reparo'"
        ).fetchone()["id"]
        self.assertEqual(self.app.total_despesas(self.mid),180)
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[0]))["outras"],108)
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[1]))["outras"],72)
        outro = self.app.garantir_mes(2026, 2)
        self.app.conn.execute("UPDATE meses SET total_pessoas_agua=12 WHERE id=?", (outro,))
        with self.assertRaises(ValueError):
            self.app.gravar_despesa(outro, "Incorreta", 10, primeira)
        self.app.gravar_despesa(self.mid, "Material corrigido", 240, primeira)
        self.assertEqual(self.app.total_despesas(self.mid),300)
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[0]))["outras"],180)
        self.app.conn.execute("DELETE FROM despesas_mes WHERE id=?", (segunda,))
        self.assertEqual(self.app.total_despesas(self.mid),240)
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[0]))["outras"],144)
        self.assertEqual(self.app.cobrancas_lancamento(self.row(self.ids[1]))["outras"],96)
        self.assertEqual(self.app.total_despesas(outro), 0)

    def test_despesa_invalida_e_divisor_zero(self):
        for descricao, valor in (("", 10), ("X", 0), ("X", -5), ("X", float("nan"))):
            with self.assertRaises(ValueError):
                self.app.gravar_despesa(self.mid, descricao, valor)
        self.app.conn.execute("UPDATE meses SET total_pessoas_agua=0 WHERE id=?", (self.mid,))
        self.app.conn.execute("UPDATE lancamentos SET numero_pessoas=0 WHERE mes_id=?",(self.mid,))
        with self.assertRaises(ValueError):
            self.app.gravar_despesa(self.mid, "Material", 20)
        self.assertEqual(self.app.total_despesas(self.mid), 0)

    def test_todos_isentos_sem_divisao_por_zero(self):
        flags = {chave: False for chave, _ in sistema.COBRANCAS}
        for lid in self.ids:
            self.app.salvar_cobrancas("lancamentos", lid, flags)
            self.assertEqual(self.app.valores_lancamento(self.row(lid)), (0, 0, 0, 0, 0))

    def test_padrao_apenas_para_novos_lancamentos(self):
        row = self.row(self.ids[0])
        flags = {chave: chave == "energia" for chave, _ in sistema.COBRANCAS}
        self.app.salvar_cobrancas("ocupantes", row["ocupante_id"], flags)
        self.app.m_ano = SimpleNamespace(get=lambda: "2026")
        self.app.m_mes = SimpleNamespace(get=lambda: "02")
        self.app.carregar_rateio_agua = Mock()
        self.app.atualizar_lancamentos = Mock()
        self.app.carregar_lancamentos()
        novo = self.app.conn.execute(
            "SELECT l.* FROM lancamentos l JOIN meses m ON m.id=l.mes_id "
            "WHERE m.mes=2 AND l.ocupante_id=?", (row["ocupante_id"],)
        ).fetchone()
        self.assertEqual(novo["cobrar_energia"], 1)
        self.assertEqual(novo["cobrar_agua"], 0)
        self.assertEqual(self.row(self.ids[0])["cobrar_agua"], 1)
        self.app.salvar_cobrancas("lancamentos", novo["id"], self.flags())
        self.app.carregar_lancamentos()
        self.assertEqual(self.row(novo["id"])["cobrar_agua"], 1)

    def test_gera_relatorio_pdf_com_secoes_e_filtro_de_ocupante(self):
        self.app.gravar_despesa(self.mid, "Material", 120)
        self.app.gravar_despesa(self.mid, "Igual por inquilino", 60, rateio="inquilinos")
        self.app.salvar_cobrancas("lancamentos", self.ids[0], self.flags(aluguel=False))
        oid=self.row(self.ids[0])["ocupante_id"]
        with tempfile.TemporaryDirectory() as pasta:
            caminho=Path(pasta)/"relatorio.pdf"
            self.app.gerar_relatorio_pdf(caminho,2026,1,ocupante_id=oid,
                                         opcoes=("resumo","detalhado","contas"))
            conteudo=caminho.read_bytes()
        self.assertTrue(conteudo.startswith(b"%PDF-"))
        self.assertIn(b"%%EOF",conteudo[-1024:])

    def test_relatorio_pdf_inclui_historico_revertido_e_baixa_automatica(self):
        oid=self.app.conn.execute("SELECT id FROM ocupantes WHERE nome='REVISA'").fetchone()[0]
        self.app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id,aluguel) VALUES(?,?,100)",(self.mid,oid)
        )
        pid=self.app.conn.execute(
            "INSERT INTO pagamentos(lancamento_id,data_pagamento,valor) VALUES(?,'2026-01-15',10)",
            (self.ids[0],),
        ).lastrowid
        self.app.reverter_pagamento(pid,self.ids[0])
        with tempfile.TemporaryDirectory() as pasta:
            caminho=Path(pasta)/"relatorio.pdf"
            self.app.gerar_relatorio_pdf(caminho,2026,1,opcoes=("resumo","detalhado"))
            conteudo=caminho.read_bytes()
        self.assertTrue(conteudo.startswith(b"%PDF-"))
        self.assertIn(b"%%EOF",conteudo[-1024:])

    def test_relatorio_pdf_informa_mes_sem_dados(self):
        with tempfile.TemporaryDirectory() as pasta:
            with self.assertRaisesRegex(ValueError,"N\u00e3o h\u00e1 dados carregados"):
                self.app.gerar_relatorio_pdf(Path(pasta)/"relatorio.pdf",2026,2)

    def test_padrao_atual_futuros_preserva_anteriores_e_outros(self):
        oid=self.row(self.ids[0])["ocupante_id"]
        futuro=self.app.garantir_mes(2027,1)
        lid=self.app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id) VALUES(?,?)",(futuro,oid)
        ).lastrowid
        flags={chave:chave=="energia" for chave,_ in sistema.COBRANCAS}
        self.app.aplicar_padrao_cobrancas(oid,flags,2026,2)
        self.assertEqual(self.row(self.ids[0])["cobrar_agua"],1)
        self.assertEqual(self.row(self.ids[1])["cobrar_agua"],1)
        self.assertEqual(self.row(lid)["cobrar_agua"],0)
        self.app.m_ano=SimpleNamespace(get=lambda:"2026")
        self.app.m_mes=SimpleNamespace(get=lambda:"03")
        self.app.carregar_rateio_agua=Mock()
        self.app.atualizar_lancamentos=Mock()
        self.app.carregar_lancamentos()
        marco=self.app.conn.execute(
            "SELECT l.* FROM lancamentos l JOIN meses m ON m.id=l.mes_id WHERE m.mes=3 AND l.ocupante_id=?",(oid,)
        ).fetchone()
        self.assertEqual(marco["cobrar_agua"],0)
        self.app.aplicar_padrao_cobrancas(oid,self.flags(),2026,4)
        self.assertEqual(self.row(marco["id"])["cobrar_agua"],0)
        self.assertEqual(self.row(lid)["cobrar_agua"],1)
        self.app.m_mes=SimpleNamespace(get=lambda:"02")
        self.app.carregar_lancamentos()
        fevereiro=self.app.conn.execute(
            "SELECT l.* FROM lancamentos l JOIN meses m ON m.id=l.mes_id WHERE m.mes=2 AND l.ocupante_id=?",(oid,)
        ).fetchone()
        self.assertEqual(fevereiro["cobrar_agua"],0)

    def test_energia_tarifa_mensal_e_saldo_revisa(self):
        self.app.gravar_rateio_energia(self.mid,600,300)
        self.app.conn.execute("UPDATE lancamentos SET leitura_inicial=100,leitura_final=150 WHERE id=?",(self.ids[0],))
        self.app.conn.execute("UPDATE lancamentos SET leitura_inicial=200,leitura_final=280 WHERE id=?",(self.ids[1],))
        revisa=self.app.conn.execute(
            "SELECT l.* FROM lancamentos l JOIN ocupantes o ON o.id=l.ocupante_id WHERE l.mes_id=? AND o.nome='REVISA'",(self.mid,)
        ).fetchone()
        self.assertEqual(self.app.energia_lancamento(self.row(self.ids[0])),100)
        self.assertEqual(self.app.energia_lancamento(self.row(self.ids[1])),160)
        self.assertEqual(self.app.energia_lancamento(revisa),340)
        self.app.conn.execute("UPDATE lancamentos SET leitura_final=9999 WHERE id=?",(revisa["id"],))
        self.assertEqual(self.app.energia_lancamento(self.row(revisa["id"])),340)
        self.app.salvar_cobrancas("lancamentos",self.ids[0],self.flags(energia=False))
        self.assertEqual(self.app.energia_lancamento(self.row(revisa["id"])),440)
        self.assertEqual(self.app.tarifa_energia(self.row(self.ids[0])),2)

    def test_energia_credito_e_validacao(self):
        self.app.gravar_rateio_energia(self.mid,10,2)
        self.app.conn.execute("UPDATE lancamentos SET leitura_inicial=0,leitura_final=3 WHERE id=?",(self.ids[0],))
        self.app.conn.execute("UPDATE lancamentos SET leitura_inicial=0,leitura_final=0 WHERE id=?",(self.ids[1],))
        revisa=self.app.conn.execute(
            "SELECT l.* FROM lancamentos l JOIN ocupantes o ON o.id=l.ocupante_id WHERE l.mes_id=? AND o.nome='REVISA'",(self.mid,)
        ).fetchone()
        self.assertEqual(self.app.energia_lancamento(revisa),-5)
        self.assertEqual(self.app.valores_lancamento(revisa)[2],-5)
        for valor,kwh in ((10,0),(-1,5),(10,-1),(float("nan"),10)):
            with self.assertRaises(ValueError):
                self.app.gravar_rateio_energia(self.mid,valor,kwh)
        self.assertEqual(self.app.contas_mes(self.mid)["conta_energia"],10)

    def test_energia_arredondamento_fecha_conta(self):
        self.app.gravar_rateio_energia(self.mid,100,3)
        for lid in self.ids:
            self.app.conn.execute("UPDATE lancamentos SET leitura_inicial=0,leitura_final=1 WHERE id=?",(lid,))
        rows=self.app.conn.execute("SELECT * FROM lancamentos WHERE mes_id=?",(self.mid,)).fetchall()
        self.assertAlmostEqual(sum(self.app.energia_lancamento(r) for r in rows),100)

    def test_iluminacao_incluida_sem_duplicar_conta(self):
        self.app.gravar_rateio_energia(self.mid,600,300,60)
        self.assertEqual(self.app.tarifas_energia(600,300,60),(1.8,0.2))
        self.assertEqual(self.app.contas_mes(self.mid)["iluminacao_publica"],60)
        for lid in self.ids:
            self.app.conn.execute("UPDATE lancamentos SET leitura_inicial=0,leitura_final=50 WHERE id=?",(lid,))
        self.assertEqual(self.app.energia_lancamento(self.row(self.ids[0])),100)
        rows=self.app.conn.execute("SELECT * FROM lancamentos WHERE mes_id=?",(self.mid,)).fetchall()
        self.assertAlmostEqual(sum(self.app.energia_lancamento(r) for r in rows),600)
        for valor in (-1,601,float("nan"),float("inf")):
            with self.assertRaises(ValueError):
                self.app.gravar_rateio_energia(self.mid,600,300,valor)
        self.assertEqual(self.app.contas_mes(self.mid)["iluminacao_publica"],60)

    def test_migracao_preserva_historico_e_e_idempotente(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE meses(id INTEGER PRIMARY KEY,ano INTEGER,mes INTEGER,
              conta_energia REAL DEFAULT 0,conta_agua REAL DEFAULT 0,limpeza_calha REAL DEFAULT 0,
              observacoes TEXT DEFAULT '', UNIQUE(ano,mes));
            CREATE TABLE ocupantes(id INTEGER PRIMARY KEY,nome TEXT UNIQUE,ativo INTEGER DEFAULT 1);
            CREATE TABLE lancamentos(id INTEGER PRIMARY KEY,mes_id INTEGER,ocupante_id INTEGER,
              leitura_inicial REAL DEFAULT 0,leitura_final REAL DEFAULT 0,tarifa_kwh REAL DEFAULT 0,
              agua_partes REAL DEFAULT 0,aluguel REAL DEFAULT 0,portao REAL DEFAULT 0,
              ajuste REAL DEFAULT 0,observacoes TEXT DEFAULT '',UNIQUE(mes_id,ocupante_id));
            INSERT INTO meses(id,ano,mes) VALUES(1,2026,1);
            INSERT INTO ocupantes(id,nome) VALUES(1,'LEGADO');
            INSERT INTO lancamentos(id,mes_id,ocupante_id,portao) VALUES(1,1,1,35);
            CREATE TABLE pagamentos(id INTEGER PRIMARY KEY,lancamento_id INTEGER NOT NULL,
              data_pagamento TEXT NOT NULL,valor REAL NOT NULL,forma TEXT DEFAULT '',observacoes TEXT DEFAULT '');
            INSERT INTO pagamentos(lancamento_id,data_pagamento,valor) VALUES(1,'2026-01-15',10);
            CREATE TABLE despesas_mes(id INTEGER PRIMARY KEY,mes_id INTEGER NOT NULL,
              descricao TEXT NOT NULL,valor REAL NOT NULL);
            INSERT INTO despesas_mes(mes_id,descricao,valor) VALUES(1,'Legado por pessoas',100);
        """)
        app = sistema.App.__new__(sistema.App)
        app.conn = conn
        app.criar_banco()
        row = conn.execute("SELECT * FROM lancamentos").fetchone()
        indices = {
            row["name"] for row in conn.execute("PRAGMA index_list(pagamentos)")
        }
        self.assertIn("idx_pagamentos_lancamento_revertido", indices)
        indices = {
            row["name"] for row in conn.execute("PRAGMA index_list(lancamentos)")
        }
        self.assertIn("idx_lancamentos_ocupante_mes", indices)
        indices = {
            row["name"] for row in conn.execute("PRAGMA index_list(despesas_mes)")
        }
        self.assertIn("idx_despesas_mes_rateio_ocupante", indices)
        self.assertEqual(app.contas_mes(1)["iluminacao_publica"],0)
        self.assertEqual(row["outras_despesas"], 35)
        self.assertEqual(app.cobrancas_lancamento(row)["outras"], 35)
        self.assertEqual(app.valores_lancamento(row)[-2:],(10,25))
        self.assertIsNone(conn.execute("SELECT revertido_em FROM pagamentos").fetchone()[0])
        self.assertEqual(conn.execute("SELECT rateio FROM despesas_mes").fetchone()[0],"pessoas")
        conn.execute("UPDATE lancamentos SET cobrar_agua=0 WHERE id=1")
        app.criar_banco()
        self.assertEqual(conn.execute("SELECT cobrar_agua FROM lancamentos").fetchone()[0], 0)
        conn.execute("UPDATE meses SET total_pessoas_agua=1 WHERE id=1")
        conn.execute("UPDATE lancamentos SET numero_pessoas=1 WHERE id=1")
        app.gravar_despesa(1, "Nova despesa", 10)
        self.assertEqual(app.cobrancas_lancamento(conn.execute("SELECT * FROM lancamentos").fetchone())["outras"], 145)
        self.assertEqual(conn.execute("SELECT outras_despesas FROM lancamentos").fetchone()[0], 35)
        self.assertIn(
            "ocupante_id",
            {row["name"] for row in conn.execute("PRAGMA table_info(despesas_mes)")},
        )

    def test_aviso_aberto_nao_calcula_lancamentos_futuros(self):
        ocupante_id = self.row(self.ids[0])["ocupante_id"]
        mes_futuro = self.app.garantir_mes(2099, 1)
        self.app.conn.execute(
            "INSERT INTO lancamentos(mes_id,ocupante_id) VALUES(?,?)",
            (mes_futuro, ocupante_id),
        )
        self.app.conn.commit()
        self.app.aviso_aberto = Mock()
        self.app.nb = Mock()
        with patch.object(
            self.app, "valores_lancamento", return_value=(0, 0, 0, 10, 0, 10)
        ) as calcular:
            self.app.atualizar_aviso_aberto()
        self.assertEqual(calcular.call_count, 2)


class AcessoTest(unittest.TestCase):
    def setUp(self):
        pasta=tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.path=Path(pasta.name) / "acesso.json"
        alteracao=patch.object(sistema,"ACESSO_PATH",self.path)
        alteracao.start()
        self.addCleanup(alteracao.stop)

    def test_logo_da_tela_de_acesso_esta_disponivel(self):
        logo=sistema.caminho_recurso("assets/revisa_logo.jpeg")
        self.assertTrue(logo.is_file())
        from PIL import Image
        with Image.open(logo) as imagem:
            self.assertEqual(imagem.format,"JPEG")
            self.assertEqual(imagem.size,(768,768))

    def test_senha_e_codigo_nao_sao_salvos_em_texto(self):
        self.assertIsNone(sistema.ler_acesso())
        codigo=sistema.salvar_acesso("SenhaTeste123","SenhaTeste123")
        dados=sistema.ler_acesso()
        texto=self.path.read_text(encoding="utf-8")
        self.assertNotIn("SenhaTeste123",texto)
        self.assertNotIn(codigo,texto)
        self.assertTrue(sistema.conferir_acesso(dados,"SenhaTeste123"))
        self.assertFalse(sistema.conferir_acesso(dados,"errada"))
        self.assertTrue(sistema.conferir_acesso(dados,codigo.lower(),recuperacao=True))
        self.assertFalse(sistema.conferir_acesso(dados,"invalido",recuperacao=True))

    def test_troca_senha_e_invalida_codigo_anterior(self):
        codigo=sistema.salvar_acesso("SenhaAntiga123","SenhaAntiga123")
        novo=sistema.salvar_acesso("SenhaNova123","SenhaNova123")
        dados=sistema.ler_acesso()
        self.assertFalse(sistema.conferir_acesso(dados,"SenhaAntiga123"))
        self.assertTrue(sistema.conferir_acesso(dados,"SenhaNova123"))
        self.assertFalse(sistema.conferir_acesso(dados,codigo,recuperacao=True))
        self.assertTrue(sistema.conferir_acesso(dados,novo,recuperacao=True))
        self.assertNotEqual(codigo,novo)

    def test_erros_de_validacao_preservam_arquivo(self):
        sistema.salvar_acesso("SenhaTeste123","SenhaTeste123")
        original=self.path.read_bytes()
        for senha,confirmacao in (("curta","curta"),("SenhaTeste123","diferente")):
            with self.assertRaises(ValueError):
                sistema.salvar_acesso(senha,confirmacao)
        with patch.object(sistema.os,"replace",side_effect=OSError("falha de gravação")):
            with self.assertRaises(OSError):
                sistema.salvar_acesso("OutraSenha123","OutraSenha123")
        self.assertEqual(self.path.read_bytes(),original)
        self.assertEqual(list(self.path.parent.glob("*.tmp")),[])

    def test_arquivo_corrompido_bloqueia_acesso(self):
        for texto in ("{","[]",'{"versao":2}','{"versao":1,"sal":"zz"}'):
            self.path.write_text(texto,encoding="utf-8")
            with self.assertRaises(ValueError):
                sistema.ler_acesso()

    def test_cancelar_ou_falhar_login_nao_abre_aplicacao(self):
        root=Mock()
        with patch.object(sistema.tk,"Tk",return_value=root), \
             patch.object(sistema.sys,"platform","test"), \
             patch.object(sistema.sys,"argv",[
                 "app","--central-authenticated","--revisa-auth-pipe=untrusted"
             ]), \
             patch.object(sistema,"configurar_icone_aplicativo") as configurar_icone, \
             patch.object(sistema,"solicitar_acesso",return_value=False) as solicitar_acesso, \
             patch.object(sistema,"App") as app:
            sistema.main()
        root.withdraw.assert_called_once()
        configurar_icone.assert_called_once_with(root)
        solicitar_acesso.assert_called_once_with(root)
        root.destroy.assert_called_once()
        root.deiconify.assert_not_called()
        root.mainloop.assert_not_called()
        app.assert_not_called()


if __name__ == "__main__":
    unittest.main()
