# entradas.py - PySide6
# Requisitos: pip install PySide6 psycopg2-binary
from __future__ import annotations
import sys
import psycopg2
from psycopg2 import OperationalError, DatabaseError

from PySide6.QtCore import Qt, QTimer, QLocale
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QLabel, QPushButton, QSpinBox, QDoubleSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QDialog, QStatusBar, QMessageBox
)

APP_TITLE = "Entradas de Notas"
SEARCH_LIMIT = 500

def _err(self, title, msg):
    QMessageBox.critical(self, title, msg)

# ---------- diálogo de pesquisa ----------
class SearchDialog(QDialog):
    def __init__(self, parent, conn):
        super().__init__(parent)
        self.setWindowTitle("Pesquisar Peças")
        self.setModal(True)
        self.resize(1000, 640)
        self.conn = conn
        self.cursor = conn.cursor()

        root = QVBoxLayout(self)

        header = QLabel("Pesquisar Peças")
        header.setFont(QFont("Segoe UI", 18, QFont.Bold))
        root.addWidget(header)

        self.ed = QLineEdit(self)
        self.ed.setPlaceholderText("Nome ou código…")
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._run_search)
        self.ed.textChanged.connect(lambda: self._debounce.start(250))
        self.ed.returnPressed.connect(self._run_search)
        root.addWidget(self.ed)

        self.table = QTableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Código", "Descrição", "Saldo"])
        self._setup_table(self.table)
        self.table.doubleClicked.connect(self._pick)
        root.addWidget(self.table, 1)

        btns = QWidget(self); hl = QHBoxLayout(btns); hl.setContentsMargins(0,0,0,0)
        btFechar = QPushButton("Fechar"); btFechar.clicked.connect(self.reject)
        hl.addStretch(); hl.addWidget(btFechar)
        root.addWidget(btns)

        QTimer.singleShot(10, self._run_search)

    def _setup_table(self, t: QTableWidget):
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.setAlternatingRowColors(True)
        t.verticalHeader().setVisible(False)
        hdr = t.horizontalHeader()
        hdr.setSectionsMovable(True)                    # arrastar colunas
        hdr.setSectionResizeMode(QHeaderView.Interactive)  # redimensionar
        t.setSortingEnabled(True)                       # ordenar

    def _run_search(self):
        termo = (self.ed.text() or "").strip().upper()
        try:
            if termo:
                self.cursor.execute("""
                    SELECT codigo, descricao, saldo
                    FROM produtos
                    WHERE UPPER(codigo) LIKE %s OR UPPER(descricao) LIKE %s
                    ORDER BY descricao
                    LIMIT %s
                """, (f"%{termo}%", f"%{termo}%", SEARCH_LIMIT))
            else:
                self.cursor.execute(
                    "SELECT codigo, descricao, saldo FROM produtos ORDER BY descricao LIMIT %s",
                    (SEARCH_LIMIT,)
                )
            rows = self.cursor.fetchall()
        except DatabaseError as e:
            _err(self, "Pesquisar Peças", f"Erro na consulta.\n\n{e}")
            rows = []

        sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for row, r in enumerate(rows):
            for c, val in enumerate(r):
                item = QTableWidgetItem("" if val is None else str(val))
                if c == 2:  # saldo
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.table.setItem(row, c, item)
        self.table.setSortingEnabled(sorting)

    def _pick(self, _index):
        row = self.table.currentRow()
        if row < 0:
            return
        cod = self.table.item(row, 0).text()
        self.selected_code = cod
        self.accept()

    def done(self, result):
        try:
            self.cursor.close()
        except Exception:
            pass
        super().done(result)

# ---------- janela principal ----------
class EntradasApp(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(APP_TITLE)
        self.resize(1100, 720)

        # DB persistente
        try:
            self.conn = psycopg2.connect(
                dbname="Almoxarifado", user="Ti", password="jj00tt", host="10.2.149.7"
            )
            self.cursor = self.conn.cursor()
        except OperationalError as e:
            _err(self, "Banco de Dados", f"Falha na conexão com PostgreSQL.\n\n{e}")
            self.close(); return

        # UI
        central = QWidget(self); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(14,10,14,10); root.setSpacing(10)

        title = QLabel(APP_TITLE); title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        root.addWidget(title)

        formCard = QWidget(self)
        form = QFormLayout(formCard)
        form.setLabelAlignment(Qt.AlignRight)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        # Campos
        self.edCodigo = QLineEdit(); self.edCodigo.setPlaceholderText("Ex.: ABC123")
        self.edCodigo.textChanged.connect(self._buscar_nome_peca)
        form.addRow("Código da Peça:", self.edCodigo)

        self.edNome = QLineEdit(); self.edNome.setReadOnly(True)
        form.addRow("Nome da Peça:", self.edNome)

        self.spQuantidade = QSpinBox(); self.spQuantidade.setRange(1, 999999999); self.spQuantidade.setValue(1)
        form.addRow("Quantidade:", self.spQuantidade)

        self.edCodTec = QLineEdit(); self.edCodTec.setPlaceholderText("Código do técnico")
        self.edCodTec.textChanged.connect(self._buscar_nome_tecnico)
        form.addRow("Código Técnico:", self.edCodTec)

        self.edNomeTec = QLineEdit(); self.edNomeTec.setReadOnly(True)
        form.addRow("Nome do Técnico:", self.edNomeTec)

        self.edMaquina = QLineEdit(); self.edMaquina.setPlaceholderText("Máquina/Local")
        form.addRow("Máquina/Local:", self.edMaquina)

        self.edNumNota = QLineEdit()
        form.addRow("Número da Nota:", self.edNumNota)

        # Valor Unitário com locale pt-BR (aceita vírgula)
        self.spValor = QDoubleSpinBox()
        self.spValor.setLocale(QLocale(QLocale.Portuguese, QLocale.Brazil))
        self.spValor.setDecimals(4)
        self.spValor.setRange(0.00, 999999999.0)
        self.spValor.setSingleStep(0.10)
        form.addRow("Valor Unitário:", self.spValor)

        self.edNcm = QLineEdit(); self.edNcm.setPlaceholderText("NCM")
        form.addRow("NCM:", self.edNcm)

        self.edFornecedor = QLineEdit(); self.edFornecedor.setPlaceholderText("Nome do fornecedor")
        form.addRow("Nome do Fornecedor:", self.edFornecedor)

        root.addWidget(formCard)

        # botões
        rowBtns = QWidget(self); h = QHBoxLayout(rowBtns); h.setContentsMargins(0,0,0,0)
        self.btSalvar = QPushButton("Registrar Entrada"); self.btSalvar.clicked.connect(self._registrar)
        self.btPesquisar = QPushButton("Pesquisar"); self.btPesquisar.clicked.connect(self._abrir_pesquisa)
        self.btVoltar = QPushButton("Voltar"); self.btVoltar.clicked.connect(self.close)
        for b in (self.btSalvar, self.btPesquisar):
            b.setMinimumWidth(180)
        h.addWidget(self.btSalvar); h.addWidget(self.btPesquisar); h.addStretch(); h.addWidget(self.btVoltar)
        root.addWidget(rowBtns)

        # status
        sb = QStatusBar(); self.setStatusBar(sb)

        # estilo
        self.setStyleSheet("""
            QMainWindow { background: #E8F1FB; }
            QPushButton { padding:8px 14px; background: white; border:1px solid #d7e3ff; border-radius:8px; }
            QPushButton:hover { background: #f6faff; }
            QLineEdit, QSpinBox, QDoubleSpinBox { background:white; border:1px solid #cfdaf5; border-radius:6px; padding:5px 8px; }
        """)

        # menu/atalhos
        self._build_menu()

    # ---------- menu ----------
    def _build_menu(self):
        mb = self.menuBar()
        mA = mb.addMenu("&Ações")
        actSave = QAction("Registrar (Ctrl+S)", self); actSave.setShortcut("Ctrl+S"); actSave.triggered.connect(self._registrar)
        actFind = QAction("Pesquisar (Ctrl+P)", self); actFind.setShortcut("Ctrl+P"); actFind.triggered.connect(self._abrir_pesquisa)
        actBack = QAction("Voltar (Esc)", self); actBack.setShortcut("Esc"); actBack.triggered.connect(self.close)
        for a in (actSave, actFind, actBack): mA.addAction(a)

    # ---------- lookups ----------
    def _buscar_nome_peca(self, *_):
        cod = self.edCodigo.text().strip().upper()
        if not cod:
            self.edNome.setText(""); return
        try:
            self.cursor.execute("SELECT descricao FROM produtos WHERE UPPER(codigo)=%s", (cod,))
            row = self.cursor.fetchone()
        except DatabaseError as e:
            _err(self, "Peça", f"Não foi possível buscar o nome da peça.\n\n{e}")
            return
        self.edNome.setText("" if not row else (row[0] or "").upper())

    def _buscar_nome_tecnico(self, *_):
        cod = self.edCodTec.text().strip().upper()
        if not cod:
            self.edNomeTec.setText(""); return
        try:
            self.cursor.execute("SELECT nome FROM tecnico WHERE UPPER(codigo)=%s", (cod,))
            row = self.cursor.fetchone()
        except DatabaseError as e:
            _err(self, "Técnico", f"Não foi possível buscar o nome do técnico.\n\n{e}")
            return
        self.edNomeTec.setText("" if not row else (row[0] or "").upper())

    # ---------- registrar entrada ----------
    def _registrar(self):
        # coleta e valida
        codigo = self.edCodigo.text().strip().upper()
        nome   = self.edNome.text().strip().upper()
        qt     = self.spQuantidade.value()
        codtec = self.edCodTec.text().strip().upper()
        nometc = self.edNomeTec.text().strip().upper()
        maq    = self.edMaquina.text().strip().upper()
        numnota= self.edNumNota.text().strip().upper()
        ncm    = self.edNcm.text().strip().upper()
        fornec = self.edFornecedor.text().strip().upper()
        valor  = float(self.spValor.value())

        if not all([codigo, nome, qt, codtec, nometc, maq, numnota, ncm, fornec]):
            _err(self, "Validação", "Todos os campos são obrigatórios.")
            return

        # se valor inteiro, deixa uma casa (compatível com seu comportamento anterior)
        if float(int(valor)) == valor:
            valor = float(f"{valor:.1f}")

        try:
            # saldo atual
            self.cursor.execute("""
                UPDATE produtos
                SET saldo=COALESCE(saldo,0)+%s, valor_un=%s
                WHERE UPPER(codigo)=%s
                RETURNING saldo
            """, (int(qt), valor, codigo))
            r = self.cursor.fetchone()
            if r is None:
                self.conn.rollback()
                _err(self, "Validação", "Código da peça não encontrado.")
                return

            # INSERT histórico
            self.cursor.execute("""
                INSERT INTO historico_movimentacoes
                (codigo, nome, data_movimentacao, tipo_movimentacao, quantidade_movimentada,
                 funcionario, maquina, numero_nota, nome_fornecedor, valor_unitario, ncm)
                VALUES (%s, %s, CURRENT_TIMESTAMP, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (codigo, nome, "ENTRADA", int(qt), nometc, maq, numnota, fornec, valor, ncm))
            self.conn.commit()

        except DatabaseError as e:
            self.conn.rollback()
            _err(self, "Entrada", f"Não foi possível registrar a entrada.\n\n{e}")
            return

        # sem popup de sucesso — só status bar
        self.statusBar().showMessage("Entrada registrada.", 2000)
        # foco volta na quantidade pra agilizar repetição
        self.spQuantidade.setValue(1)
        self.spQuantidade.setFocus()

    # ---------- pesquisa ----------
    def _abrir_pesquisa(self):
        dlg = SearchDialog(self, self.conn)
        if dlg.exec():
            self.edCodigo.setText(dlg.selected_code)
            self._buscar_nome_peca()
            self.spQuantidade.setFocus()

    # ---------- fechar ----------
    def closeEvent(self, e):
        try:
            if hasattr(self, "cursor") and self.cursor: self.cursor.close()
            if hasattr(self, "conn") and self.conn: self.conn.close()
        except Exception:
            pass
        # reexibe parent se existir
        p = self.parent()
        if p and hasattr(p, "show"):
            p.show(); p.raise_(); p.activateWindow()
        super().closeEvent(e)

# --------- função para o launcher (main.py) ---------
def abrir(parent=None):
    win = EntradasApp(parent)
    win.showMaximized()
    return win

# --------- standalone ---------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = EntradasApp()
    w.show()
    sys.exit(app.exec())
