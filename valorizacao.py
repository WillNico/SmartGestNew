# valorizacao.py - PySide6
# Requisitos:
#   pip install PySide6 psycopg2-binary
from __future__ import annotations
import sys
from datetime import datetime

import psycopg2
from psycopg2 import OperationalError, DatabaseError

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton, QButtonGroup, QStatusBar,
    QDialog, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QCheckBox, QMessageBox
)

APP_TITLE = "Valorização de Estoque"
DB = dict(dbname="Almoxarifado", user="Ti", password="jj00tt", host="10.2.149.7")
SEARCH_LIMIT = 500

def _err(self, title, msg): QMessageBox.critical(self, title, msg)

# ---------- Diálogo de Pesquisa ----------
class BuscaValorDialog(QDialog):
    def __init__(self, parent, cursor):
        super().__init__(parent)
        self.setWindowTitle("Pesquisar Peças (valor zerado opcional)")
        self.resize(1000, 620)
        self.cursor = cursor

        root = QVBoxLayout(self)

        head = QLabel("Pesquisar Peças")
        head.setFont(QFont("Segoe UI", 18, QFont.Bold))
        root.addWidget(head)

        row = QWidget(self)
        hb = QHBoxLayout(row); hb.setContentsMargins(0,0,0,0)
        self.ed = QLineEdit(); self.ed.setPlaceholderText("Nome ou código…")
        self.chkZero = QCheckBox("Somente valor zerado")
        self.chkZero.setChecked(True)
        bt = QPushButton("Buscar")
        hb.addWidget(self.ed, 1); hb.addWidget(self.chkZero); hb.addWidget(bt)
        root.addWidget(row)

        self.tbl = QTableWidget(self)
        self.tbl.setColumnCount(3)
        self.tbl.setHorizontalHeaderLabels(["Código","Descrição","Saldo"])
        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Stretch)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl.doubleClicked.connect(self.accept)
        root.addWidget(self.tbl, 1)

        # ligações
        bt.clicked.connect(self._buscar)
        self.ed.returnPressed.connect(self._buscar)
        self.chkZero.stateChanged.connect(self._buscar)

        QTimer.singleShot(50, self._buscar)

    def _buscar(self):
        termo = (self.ed.text() or "").strip().upper()
        only_zero = self.chkZero.isChecked()
        try:
            if only_zero:
                if termo:
                    self.cursor.execute("""
                        SELECT codigo, descricao, saldo
                        FROM produtos
                        WHERE valor_un = 0
                          AND (UPPER(codigo) LIKE %s OR UPPER(descricao) LIKE %s)
                        ORDER BY descricao
                        LIMIT %s
                    """, (f"%{termo}%", f"%{termo}%", SEARCH_LIMIT))
                else:
                    self.cursor.execute("""
                        SELECT codigo, descricao, saldo
                        FROM produtos
                        WHERE valor_un = 0
                        ORDER BY descricao
                        LIMIT %s
                    """, (SEARCH_LIMIT,))
            else:
                if termo:
                    self.cursor.execute("""
                        SELECT codigo, descricao, saldo
                        FROM produtos
                        WHERE UPPER(codigo) LIKE %s OR UPPER(descricao) LIKE %s
                        ORDER BY descricao
                        LIMIT %s
                    """, (f"%{termo}%", f"%{termo}%", SEARCH_LIMIT))
                else:
                    self.cursor.execute("""
                        SELECT codigo, descricao, saldo
                        FROM produtos
                        ORDER BY descricao
                        LIMIT %s
                    """, (SEARCH_LIMIT,))
            rows = self.cursor.fetchall()
        except DatabaseError as e:
            _err(self, "Pesquisar", f"Erro na consulta.\n\n{e}")
            return

        sorting = self.tbl.isSortingEnabled()
        self.tbl.setSortingEnabled(False)
        self.tbl.setRowCount(len(rows))
        for r, (c,d,s) in enumerate(rows):
            self.tbl.setItem(r, 0, QTableWidgetItem(str(c).upper()))
            self.tbl.setItem(r, 1, QTableWidgetItem(str(d or "").upper()))
            it_s = QTableWidgetItem(str(s))
            it_s.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tbl.setItem(r, 2, it_s)
        self.tbl.setSortingEnabled(sorting)

    def selected_code(self) -> str | None:
        r = self.tbl.currentRow()
        if r < 0: return None
        it = self.tbl.item(r, 0)
        return it.text() if it else None

# ---------- Janela Principal ----------
class ValorizacaoApp(QMainWindow):
    def __init__(self, parent=None, parent_window=None):
        super().__init__(parent)
        self.parent_window = parent_window
        self.setWindowTitle(APP_TITLE)
        self.resize(1024, 720)

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

        # Formulário
        card = QWidget(); form = QFormLayout(card)
        form.setLabelAlignment(Qt.AlignRight)
        form.setHorizontalSpacing(12); form.setVerticalSpacing(10)

        rowCodigo = QWidget(); hb1 = QHBoxLayout(rowCodigo); hb1.setContentsMargins(0,0,0,0)
        self.edCodigo = QLineEdit(); self.edCodigo.setPlaceholderText("Código da peça")
        btBuscar = QPushButton("Pesquisar (Ctrl+F)")
        hb1.addWidget(self.edCodigo, 1); hb1.addWidget(btBuscar)
        form.addRow("Código:", rowCodigo)

        self.edNome = QLineEdit(); self.edNome.setReadOnly(True)
        form.addRow("Nome da Peça:", self.edNome)

        self.edValorAtual = QLineEdit(); self.edValorAtual.setReadOnly(True)
        form.addRow("Valor Atual:", self.edValorAtual)

        # Tipo: Estimativa / Real (exclusivos)
        rowTipo = QWidget(); hb2 = QHBoxLayout(rowTipo); hb2.setContentsMargins(0,0,0,0)
        self.rbEstim = QRadioButton("Estimativa")
        self.rbReal  = QRadioButton("Real")
        self.grpTipo = QButtonGroup(self); self.grpTipo.setExclusive(True)
        self.grpTipo.addButton(self.rbEstim); self.grpTipo.addButton(self.rbReal)
        self.rbReal.setChecked(True)
        hb2.addWidget(self.rbEstim); hb2.addWidget(self.rbReal); hb2.addStretch()
        form.addRow("Tipo:", rowTipo)

        self.edNovoValor = QLineEdit(); self.edNovoValor.setPlaceholderText("Ex.: 12,34 ou 12.34")
        form.addRow("Novo Valor:", self.edNovoValor)

        # Botões
        rowBtns = QWidget(); hb3 = QHBoxLayout(rowBtns); hb3.setContentsMargins(0,0,0,0)
        btSalvar = QPushButton("Salvar (Ctrl+S)")
        btZero   = QPushButton("Itens com valor zerado")
        btVoltar = QPushButton("Voltar (Esc)")
        for b in (btSalvar, btZero): b.setMinimumWidth(160)
        hb3.addWidget(btSalvar); hb3.addWidget(btZero); hb3.addStretch(); hb3.addWidget(btVoltar)
        root.addWidget(card); root.addWidget(rowBtns)

        # Statusbar
        sb = QStatusBar(); self.setStatusBar(sb)

        # Estilo
        self.setStyleSheet("""
            QMainWindow { background:#EAF2FC; }
            QWidget#card, QGroupBox { background:white; border:1px solid #dbe5ff; border-radius:10px; }
            QPushButton { padding:8px 14px; background:white; border:1px solid #d7e3ff; border-radius:8px; }
            QPushButton:hover { background:#f6faff; }
            QLineEdit { background:white; border:1px solid #cfdaf5; border-radius:6px; padding:6px 10px; }
        """)
        card.setObjectName("card")

        # Ligações
        self.edCodigo.textChanged.connect(self._buscar_nome_valor_peca)
        btBuscar.clicked.connect(self._abrir_busca)
        btSalvar.clicked.connect(self._salvar)
        btZero.clicked.connect(self._abrir_busca_zero)
        btVoltar.clicked.connect(self.close)

        # Menu / atalhos
        self._build_menu()

        # Foco inicial
        QTimer.singleShot(100, self.edCodigo.setFocus)

    # ---------- Menu ----------
    def _build_menu(self):
        mb = self.menuBar()
        mA = mb.addMenu("&Ações")
        aFind = QAction("Pesquisar (Ctrl+F)", self); aFind.setShortcut("Ctrl+F"); aFind.triggered.connect(self._abrir_busca)
        aSave = QAction("Salvar (Ctrl+S)", self);   aSave.setShortcut("Ctrl+S"); aSave.triggered.connect(self._salvar)
        aBack = QAction("Voltar (Esc)", self);      aBack.setShortcut("Esc");    aBack.triggered.connect(self.close)
        for a in (aFind, aSave, aBack): mA.addAction(a)

    # ---------- Lookups ----------
    def _buscar_nome_valor_peca(self):
        cod = self.edCodigo.text().strip().upper()
        if not cod:
            self.edNome.setText(""); self.edValorAtual.setText(""); return
        try:
            self.cursor.execute("SELECT descricao, valor_un FROM produtos WHERE UPPER(codigo)=%s", (cod,))
            row = self.cursor.fetchone()
        except DatabaseError as e:
            _err(self, "Peça", f"Erro ao buscar peça.\n\n{e}")
            return
        if not row:
            self.edNome.setText(""); self.edValorAtual.setText("")
            return
        nome, val = row[0], row[1]
        self.edNome.setText(str(nome or "").upper())
        self.edValorAtual.setText("" if val is None else f"{float(val):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    # ---------- Busca / Seletores ----------
    def _abrir_busca(self):
        dlg = BuscaValorDialog(self, self.cursor)
        if dlg.exec() == QDialog.Accepted:
            codigo = dlg.selected_code()
            if codigo:
                self.edCodigo.setText(codigo)
                self._buscar_nome_valor_peca()
                self.edNovoValor.setFocus()

    def _abrir_busca_zero(self):
        self._abrir_busca()  # o diálogo já vem com “somente valor zerado” marcado por padrão

    # ---------- Salvar ----------
    def _salvar(self):
        codigo = self.edCodigo.text().strip().upper()
        nome   = self.edNome.text().strip().upper()
        novo   = self.edNovoValor.text().strip().replace(",", ".")
        tipo   = "ESTIMATIVA" if self.rbEstim.isChecked() else "REAL"

        if not codigo or not novo or not tipo:
            _err(self, "Validação", "Preencha Código, Novo Valor e Tipo.")
            return

        try:
            novo_valor = float(novo)
        except ValueError:
            _err(self, "Validação", "Novo Valor deve ser um número (ex.: 12,34).")
            return

        try:
            # confirma que a peça existe
            self.cursor.execute("SELECT 1 FROM produtos WHERE UPPER(codigo)=%s", (codigo,))
            if not self.cursor.fetchone():
                _err(self, "Validação", "Código da peça não encontrado.")
                return

            # atualiza valor
            self.cursor.execute("UPDATE produtos SET valor_un=%s WHERE UPPER(codigo)=%s", (novo_valor, codigo))

            # histórico
            self.cursor.execute("""
                INSERT INTO historico_movimentacoes
                (codigo, nome, data_movimentacao, tipo_movimentacao, quantidade_movimentada,
                 funcionario, maquina, numero_nota, nome_fornecedor, valor_unitario, ncm)
                VALUES (%s, %s, CURRENT_TIMESTAMP, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (codigo, nome, tipo, 0, None, None, None, None, novo_valor, None))
            self.conn.commit()

        except DatabaseError as e:
            self.conn.rollback()
            _err(self, "Salvar", f"Não foi possível salvar.\n\n{e}")
            return

        # sem pop-up de sucesso; feedback suave
        self.statusBar().showMessage("Valor atualizado e histórico registrado.", 2000)
        self._buscar_nome_valor_peca()
        self.edNovoValor.clear()
        self.edNovoValor.setFocus()

    # ---------- Fechamento ----------
    def closeEvent(self, e):
        try:
            if hasattr(self, "cursor") and self.cursor: self.cursor.close()
            if hasattr(self, "conn") and self.conn: self.conn.close()
        except Exception:
            pass
        p = self.parent_window or self.parent()
        if p and hasattr(p, "show"):
            p.show(); p.raise_(); p.activateWindow()
        super().closeEvent(e)

# --------- função que o launcher espera ---------
def abrir(parent=None, parent_window=None):
    win = ValorizacaoApp(parent, parent_window)
    win.showMaximized()
    return win

# --------- standalone ---------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ValorizacaoApp()
    w.showMaximized()
    sys.exit(app.exec())
