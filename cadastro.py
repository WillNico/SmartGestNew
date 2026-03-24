# cadastro.py - PySide6
# Requisitos:
#   pip install PySide6 psycopg2-binary
from __future__ import annotations
import sys
from datetime import datetime

import psycopg2
from psycopg2 import OperationalError, DatabaseError

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QGroupBox, QStatusBar, QMessageBox,
    QDialog, QDialogButtonBox, QGridLayout, QInputDialog
)

APP_TITLE = "Cadastro de Peça"
DB = dict(dbname="Almoxarifado", user="Ti", password="jj00tt", host="10.2.149.7")

# senhas (iguais às usadas hoje)
PWD_EDICAO  = "147258"
PWD_FAMILIA = "147258"

def _err(self, title, msg): QMessageBox.critical(self, title, msg)
def _info(self, title, msg): QMessageBox.information(self, title, msg)
def _warn(self, title, msg): QMessageBox.warning(self, title, msg)


# ---------------- Diálogo: Cadastro de Família ----------------
class FamiliaDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Cadastro de Família")
        self.setModal(True)
        self.resize(520, 320)

        root = QVBoxLayout(self)

        form = QFormLayout()
        self.edCod  = QLineEdit()
        self.edCod.setPlaceholderText("Ex.: 001")
        self.edNome = QLineEdit()
        self.edNome.setPlaceholderText("Nome da família")
        form.addRow("Código da Família:", self.edCod)
        form.addRow("Nome da Família:",   self.edNome)

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btExcluir   = QPushButton("Excluir")
        btListarLivres = QPushButton("Números Disponíveis")
        bb.addButton(btExcluir, QDialogButtonBox.ActionRole)
        bb.addButton(btListarLivres, QDialogButtonBox.ActionRole)

        root.addLayout(form)
        root.addWidget(bb)

        bb.accepted.connect(self._salvar)
        bb.rejected.connect(self.reject)
        btExcluir.clicked.connect(self._excluir)
        btListarLivres.clicked.connect(self._listar_livres)

    # helpers DB
    def _conn(self):
        return psycopg2.connect(**DB)

    def _pedir_senha(self, titulo):
        txt, ok = QInputDialog.getText(self, titulo, "Senha:", QLineEdit.Password)
        return ok and (txt == PWD_FAMILIA)

    def _salvar(self):
        if not self._pedir_senha("Salvar Família"):
            _err(self, "Senha", "Senha incorreta."); return

        cod  = (self.edCod.text() or "").strip().upper()
        nome = (self.edNome.text() or "").strip().upper()
        if not cod or not nome:
            return _err(self, "Validação", "Preencha código e nome.")

        try:
            conn = self._conn(); cur = conn.cursor()
            # checa duplicidades
            cur.execute("SELECT 1 FROM familias WHERE nome=%s", (nome,)); ex_nome = cur.fetchone()
            if ex_nome: return _err(self, "Duplicado", "Já existe família com esse NOME.")
            cur.execute("SELECT 1 FROM familias WHERE codigo=%s", (cod,)); ex_cod = cur.fetchone()
            if ex_cod: return _err(self, "Duplicado", "Já existe família com esse CÓDIGO.")
            # insere
            cur.execute("INSERT INTO familias(codigo,nome) VALUES(%s,%s)", (cod, nome))
            # registra log opcional (mesma ideia do seu sistema)
            cur.execute("""
                INSERT INTO historico_movimentacoes
                (codigo, nome, data_movimentacao, tipo_movimentacao, quantidade_movimentada)
                VALUES (%s,%s,CURRENT_TIMESTAMP,%s,%s)
            """, (cod, nome, "NOVAFAMILIA", 0))
            conn.commit(); cur.close(); conn.close()
        except DatabaseError as e:
            _err(self, "Banco", f"Erro ao salvar família.\n\n{e}"); return

        _info(self, "OK", "Família salva.")
        self.accept()

    def _excluir(self):
        if not self._pedir_senha("Excluir Família"):
            _err(self, "Senha", "Senha incorreta."); return
        cod = (self.edCod.text() or "").strip().upper()
        if not cod:
            return _warn(self, "Dados", "Informe o código da família para excluir.")
        try:
            conn = self._conn(); cur = conn.cursor()
            cur.execute("DELETE FROM familias WHERE codigo=%s", (cod,))
            conn.commit(); cur.close(); conn.close()
        except DatabaseError as e:
            _err(self, "Banco", f"Erro ao excluir.\n\n{e}"); return
        _info(self, "OK", "Família excluída (se existia).")

    def _listar_livres(self):
        try:
            conn = self._conn(); cur = conn.cursor()
            cur.execute("SELECT codigo FROM familias")
            usados = {str(r[0]).zfill(3) for r in cur.fetchall()}
            cur.close(); conn.close()
        except DatabaseError as e:
            return _err(self, "Banco", f"Erro ao listar.\n\n{e}")
        livres = [f"{i:03d}" for i in range(1, 1000) if f"{i:03d}" not in usados]
        msg = "Códigos livres (ex.: 001..999):\n\n" + ", ".join(livres[:150])
        _info(self, "Números Disponíveis", msg)


# ---------------- Janela Principal ----------------
class CadastroPecaApp(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(APP_TITLE)
        self.resize(1080, 720)

        # Conexão persistente
        try:
            self.conn = psycopg2.connect(**DB)
            self.cursor = self.conn.cursor()
        except OperationalError as e:
            _err(self, "Banco de Dados", f"Falha na conexão com PostgreSQL.\n\n{e}")
            self.close(); return

        # ===== UI =====
        central = QWidget(self); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(14, 10, 14, 10); root.setSpacing(10)

        title = QLabel(APP_TITLE); title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        root.addWidget(title)

        # --------- Grupo Família ---------
        gFam = QGroupBox("Família")
        f = QFormLayout(gFam); f.setLabelAlignment(Qt.AlignRight)
        self.edFamilia = QLineEdit(); self.edFamilia.setPlaceholderText("Ex.: 001")
        self.edFamNome = QLineEdit(); self.edFamNome.setReadOnly(True)
        self.lblUltimo = QLabel("Último Código: —")

        self.edFamilia.textChanged.connect(self._on_familia_changed)

        f.addRow("Código da Família:", self.edFamilia)
        f.addRow("Nome da Família:",   self.edFamNome)
        f.addRow("", self.lblUltimo)

        # Ações da família
        famBtns = QWidget(); hb = QHBoxLayout(famBtns); hb.setContentsMargins(0,0,0,0)
        btNovaFam = QPushButton("Cadastrar/Editar Família")
        btNovaFam.clicked.connect(self._abrir_familia)
        hb.addWidget(btNovaFam); hb.addStretch()
        f.addRow("", famBtns)

        root.addWidget(gFam)

        # --------- Grupo Dados da Peça ---------
        gPeca = QGroupBox("Dados da Peça")
        p = QFormLayout(gPeca); p.setLabelAlignment(Qt.AlignRight)

        self.edCodigo = QLineEdit(); self.edCodigo.setPlaceholderText("Será sugerido pela família")
        self.edNome   = QLineEdit()
        self.spSaldo  = QSpinBox(); self.spSaldo.setRange(0, 999_999_999); self.spSaldo.setValue(0)
        self.edLocal  = QLineEdit(); self.edLocal.setPlaceholderText("Prateleira / Local")

        p.addRow("Código da Peça:", self.edCodigo)
        p.addRow("Nome:",           self.edNome)
        p.addRow("Saldo Inicial:",  self.spSaldo)
        p.addRow("Prateleira:",     self.edLocal)

        # Botões
        btns = QWidget(); hb2 = QHBoxLayout(btns); hb2.setContentsMargins(0,0,0,0)
        btSalvar  = QPushButton("Salvar");  btSalvar.clicked.connect(self._salvar)
        btEditar  = QPushButton("Editar");  btEditar.clicked.connect(self._editar)
        btValor   = QPushButton("Valorização de Estoque"); btValor.clicked.connect(self._abrir_valorizacao)
        btVoltar  = QPushButton("Voltar");  btVoltar.clicked.connect(self.close)
        for b in (btSalvar, btEditar, btValor): b.setMinimumWidth(160)
        hb2.addWidget(btSalvar); hb2.addWidget(btEditar); hb2.addWidget(btValor)
        hb2.addStretch(); hb2.addWidget(btVoltar)

        p.addRow("", btns)

        root.addWidget(gPeca)

        # StatusBar + estilo
        sb = QStatusBar(); self.setStatusBar(sb)
        self.setStyleSheet("""
            QMainWindow { background:#EAF2FC; }
            QGroupBox { background:white; border:1px solid #dbe5ff; border-radius:10px; margin-top:10px; }
            QGroupBox::title { subcontrol-origin: margin; left:12px; padding:0 6px; background:#EAF2FC; }
            QPushButton { padding:8px 14px; background:white; border:1px solid #d7e3ff; border-radius:8px; }
            QPushButton:hover { background:#f6faff; }
            QLineEdit, QSpinBox { background:white; border:1px solid #cfdaf5; border-radius:6px; padding:6px 10px; }
        """)

        # Menu/atalhos
        self._build_menu()

    # ---------- Menu ----------
    def _build_menu(self):
        mb = self.menuBar()
        mA = mb.addMenu("&Ações")
        aSave = QAction("Salvar (Ctrl+S)", self); aSave.setShortcut("Ctrl+S"); aSave.triggered.connect(self._salvar)
        aEdit = QAction("Editar (Ctrl+E)", self); aEdit.setShortcut("Ctrl+E"); aEdit.triggered.connect(self._editar)
        aBack = QAction("Voltar (Esc)", self); aBack.setShortcut("Esc"); aBack.triggered.connect(self.close)
        for a in (aSave, aEdit, aBack): mA.addAction(a)

    # ---------- Família ----------
    def _on_familia_changed(self):
        cod = (self.edFamilia.text() or "").strip().upper()
        if not cod:
            self.edFamNome.setText(""); self.lblUltimo.setText("Último Código: —"); return
        # nome da família
        try:
            self.cursor.execute("SELECT nome FROM familias WHERE codigo=%s", (cod,))
            row = self.cursor.fetchone()
            self.edFamNome.setText("" if not row else (row[0] or "").upper())
        except DatabaseError as e:
            _err(self, "Família", f"Erro ao buscar família.\n\n{e}"); return
        # sugere próximo código
        self._sugerir_proximo_codigo()

    def _sugerir_proximo_codigo(self):
        fam = (self.edFamilia.text() or "").strip().upper()
        if not fam: return
        try:
            # usa parte numérica após o ponto para achar o maior sequencial
            self.cursor.execute(
                "SELECT MAX(split_part(codigo,'.',2)::int) FROM produtos WHERE split_part(codigo,'.',1)=%s",
                (fam,)
            )
            r = self.cursor.fetchone()
            ult_num = int(r[0]) if r and r[0] is not None else 0
            proximo = f"{fam}.{ult_num+1:05d}"
            # último código “cheio” apenas informativo
            self.cursor.execute(
                "SELECT MAX(codigo) FROM produtos WHERE split_part(codigo,'.',1)=%s", (fam,)
            )
            r2 = self.cursor.fetchone()
            self.lblUltimo.setText(f"Último Código: {r2[0] or '—'}")
            self.edCodigo.setText(proximo)
        except DatabaseError as e:
            _err(self, "Sugestão de Código", f"Erro na consulta.\n\n{e}")

    # ---------- Salvar ----------
    def _salvar(self):
        codigo = (self.edCodigo.text() or "").strip().upper()
        nome   = (self.edNome.text()   or "").strip().upper()
        familia= (self.edFamilia.text()or "").strip().upper()
        saldo  = int(self.spSaldo.value())
        local  = (self.edLocal.text()  or "").strip().upper()

        if not all([codigo, nome, familia, local]):
            return _err(self, "Validação", "Preencha todos os campos.")

        try:
            # duplicidade por NOME
            self.cursor.execute("SELECT codigo FROM produtos WHERE UPPER(descricao)=%s", (nome,))
            r = self.cursor.fetchone()
            if r: return _err(self, "Duplicado", f"Nome já existe com o código: {r[0]}")

            # duplicidade por CÓDIGO
            self.cursor.execute("SELECT 1 FROM produtos WHERE UPPER(codigo)=%s", (codigo,))
            r = self.cursor.fetchone()
            if r: return _err(self, "Duplicado", f"Código já existe: {codigo}")

            # INSERT produto
            self.cursor.execute("""
                INSERT INTO produtos(codigo, descricao, saldo, estoque_minimo, local, valor_un)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (codigo, nome, saldo, 2, local, 0))
            self.conn.commit()

            # log histórico
            self.cursor.execute("""
                INSERT INTO historico_movimentacoes
                (codigo, nome, data_movimentacao, tipo_movimentacao, quantidade_movimentada)
                VALUES (%s,%s,CURRENT_TIMESTAMP,%s,%s)
            """, (codigo, nome, "CADASTRADO", saldo))
            self.conn.commit()
        except DatabaseError as e:
            self.conn.rollback()
            return _err(self, "Salvar", f"Erro ao salvar.\n\n{e}")

        self.statusBar().showMessage("Peça cadastrada.", 1800)
        # prepara próximo
        self.edNome.clear(); self.spSaldo.setValue(0); self.edLocal.clear()
        self._sugerir_proximo_codigo()
        self.edNome.setFocus()

    # ---------- Editar ----------
    def _editar(self):
        # pede senha
        txt, ok = QInputDialog.getText(self, "Editar", "Senha:", QLineEdit.Password)
        if not ok or txt != PWD_EDICAO:
            return _err(self, "Senha", "Senha incorreta.")

        codigo = (self.edCodigo.text() or "").strip().upper()
        if not codigo:
            return _warn(self, "Dados", "Informe o CÓDIGO da peça para editar.")

        try:
            self.cursor.execute("SELECT descricao FROM produtos WHERE UPPER(codigo)=%s", (codigo,))
            r = self.cursor.fetchone()
            if not r: return _err(self, "Editar", "Código não encontrado.")
            nome_atual = r[0] or ""
        except DatabaseError as e:
            return _err(self, "Editar", f"Erro na consulta.\n\n{e}")

        # diálogo simples para novo nome
        novo, ok = QInputDialog.getText(self, "Editar Peça",
                                        f"Código: {codigo}\nNovo Nome:",
                                        QLineEdit.Normal, nome_atual)
        if not ok: return
        novo = (novo or "").strip().upper()
        if not novo: return _warn(self, "Validação", "Nome não pode ficar vazio.")

        try:
            # checa duplicidade de nome
            self.cursor.execute("SELECT codigo FROM produtos WHERE UPPER(descricao)=%s AND UPPER(codigo)<>%s",
                                (novo, codigo))
            r = self.cursor.fetchone()
            if r: return _err(self, "Duplicado", f"Nome já existe com o código: {r[0]}")

            self.cursor.execute("UPDATE produtos SET descricao=%s WHERE UPPER(codigo)=%s",
                                (novo, codigo))
            self.conn.commit()

            self.cursor.execute("""
                INSERT INTO historico_movimentacoes
                (codigo, nome, data_movimentacao, tipo_movimentacao, quantidade_movimentada)
                VALUES (%s,%s,CURRENT_TIMESTAMP,%s,%s)
            """, (codigo, novo, "EDICAO", 0))
            self.conn.commit()
        except DatabaseError as e:
            self.conn.rollback()
            return _err(self, "Editar", f"Erro ao salvar edição.\n\n{e}")

        _info(self, "OK", "Dados atualizados com sucesso.")
        self.edNome.setText(novo)

    # ---------- Valorização ----------
    def _abrir_valorizacao(self):
        try:
            import valorizacao  # seu módulo
        except Exception:
            return _err(self, "Valorização", "Módulo 'valorizacao' não encontrado.")
        # se seu valorizacao ainda for Tk, tudo bem — apenas abre por conta própria
        try:
            # compat: algumas versões têm abrir(parent, parent_window)
            if hasattr(valorizacao, "abrir"):
                valorizacao.abrir(self, self)
            else:
                _warn(self, "Valorização", "Função abrir() não disponível no módulo.")
        except Exception as e:
            _err(self, "Valorização", f"Não foi possível abrir.\n\n{e}")

    # ---------- Família dialog ----------
    def _abrir_familia(self):
        dlg = FamiliaDialog(self)
        if dlg.exec():
            # se salvou/alterou, atualiza lookup e sugestão
            self._on_familia_changed()

    # ---------- Fechamento ----------
    def closeEvent(self, e):
        try:
            if hasattr(self, "cursor") and self.cursor: self.cursor.close()
            if hasattr(self, "conn") and self.conn: self.conn.close()
        except Exception:
            pass
        super().closeEvent(e)


# --------- função para o launcher ---------
def abrir(parent=None, parent_window=None):
    """Compatível com seu padrão: retorna a janela já maximizada."""
    win = CadastroPecaApp(parent)
    win.showMaximized()
    return win


# --------- standalone ---------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = CadastroPecaApp()
    w.showMaximized()
    sys.exit(app.exec())
