# movimentacao.py - PySide6
# Requisitos: pip install PySide6 psycopg2-binary
from __future__ import annotations
import sys
import psycopg2
from psycopg2 import OperationalError, DatabaseError

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QAction, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QLabel, QPushButton, QRadioButton, QButtonGroup, QSpinBox,
    QTableWidget, QTableWidgetItem, QCheckBox, QHeaderView, QDialog,
    QMessageBox, QSplitter, QSizePolicy, QAbstractItemView, QStatusBar
)

APP_TITLE = "Movimentação de Peças"

# ---------------- Helpers ----------------
def _err(self, title, msg):
    QMessageBox.critical(self, title, msg)

# ---------------- Diálogo de Pesquisa (genérico) ----------------
class SearchDialog(QDialog):
    def __init__(self, parent, titulo, cols, search_fn, on_select):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setModal(True)
        self.resize(900, 600)

        root = QVBoxLayout(self)
        header = QLabel(titulo)
        header.setFont(QFont("Segoe UI", 18, QFont.Bold))
        root.addWidget(header)

        self.ed = QLineEdit(self)
        self.ed.setPlaceholderText("Digite para pesquisar…")
        self.ed.returnPressed.connect(self._run_search)
        root.addWidget(self.ed)

        self.btn = QPushButton("Pesquisar", self)
        self.btn.clicked.connect(self._run_search)
        root.addWidget(self.btn)

        self.table = QTableWidget(self)
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.doubleClicked.connect(self._pick)
        root.addWidget(self.table, 1)

        self._search_fn = search_fn
        self._on_select = on_select

        # primeira busca vazia
        QTimer.singleShot(10, lambda: self._run_search())

    def _run_search(self):
        termo = self.ed.text().strip().upper()
        rows = self._search_fn(termo)
        self.table.setRowCount(0)
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for c, val in enumerate(r):
                item = QTableWidgetItem("" if val is None else str(val))
                # alinhamentos básicos
                if isinstance(val, (int, float)) or (isinstance(val, str) and val.isdigit()):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, c, item)

    def _pick(self):
        row = self.table.currentRow()
        if row < 0:
            return
        vals = [self.table.item(row, c).text() if self.table.item(row, c) else ""
                for c in range(self.table.columnCount())]
        self._on_select(vals)
        self.accept()

# ---------------- Janela Principal ----------------
class MovimentacaoApp(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 800)

        # Conexão persistente
        try:
            self.conn = psycopg2.connect(
                dbname="Almoxarifado",
                user="Ti", password="jj00tt",
                host="10.2.149.7"
            )
            self.cursor = self.conn.cursor()
        except OperationalError as e:
            _err(self, "Banco de Dados", f"Falha na conexão com PostgreSQL.\n\n{e}")
            self.close()
            return

        # ==== UI ====
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(10)

        # Menu/atalhos
        self._build_menu()

        # Splitter L|R
        split = QSplitter(Qt.Horizontal, self)
        root.addWidget(split, 1)

        # ---- Left (Form + Botões + Histórico) ----
        left = QWidget(self)
        leftL = QVBoxLayout(left)
        leftL.setSpacing(10)

        # Formulário
        formCard = QWidget(self)
        formLay  = QFormLayout(formCard)
        formLay.setLabelAlignment(Qt.AlignRight)
        formLay.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        formLay.setHorizontalSpacing(12)
        formLay.setVerticalSpacing(10)

        self.edCodigo = QLineEdit()
        self.edCodigo.setPlaceholderText("Ex.: ABC123")
        self.edCodigo.textChanged.connect(self._buscar_nome_peca)  # aceita *_
        formLay.addRow("Código da Peça:", self.edCodigo)

        self.edNome = QLineEdit()
        self.edNome.setReadOnly(True)
        formLay.addRow("Nome da Peça:", self.edNome)

        self.spQuantidade = QSpinBox()
        self.spQuantidade.setRange(1, 999999999)
        self.spQuantidade.setValue(1)
        formLay.addRow("Quantidade:", self.spQuantidade)

        self.edCodTec = QLineEdit()
        self.edCodTec.setPlaceholderText("Código do técnico")
        self.edCodTec.textChanged.connect(self._buscar_nome_tecnico)  # aceita *_
        formLay.addRow("Código Técnico:", self.edCodTec)

        self.edNomeTec = QLineEdit()
        self.edNomeTec.setReadOnly(True)
        formLay.addRow("Nome Técnico:", self.edNomeTec)

        self.edMaquina = QLineEdit()
        self.edMaquina.setPlaceholderText("Máquina/Local")
        formLay.addRow("Máquina/Local:", self.edMaquina)

        tipoRow = QWidget(self)
        trL = QHBoxLayout(tipoRow); trL.setContentsMargins(0,0,0,0)
        self.rbEntrada = QRadioButton("Entrada")
        self.rbSaida   = QRadioButton("Saída")
        self.grpTipo   = QButtonGroup(self)
        self.grpTipo.addButton(self.rbEntrada)
        self.grpTipo.addButton(self.rbSaida)
        self.rbEntrada.setChecked(True)
        trL.addWidget(self.rbEntrada); trL.addWidget(self.rbSaida); trL.addStretch()
        formLay.addRow("Tipo:", tipoRow)

        leftL.addWidget(formCard)

        # Botões
        btRow = QWidget(self)
        btL = QHBoxLayout(btRow); btL.setContentsMargins(0,0,0,0)
        self.btSalvar = QPushButton("Salvar")
        self.btSalvar.clicked.connect(self._realizar_movimentacao)
        self.btPesqPeca = QPushButton("Pesquisar Peça")
        self.btPesqPeca.clicked.connect(self._abrir_pesquisa_peca)
        self.btPesqTec = QPushButton("Pesquisar Técnico")
        self.btPesqTec.clicked.connect(self._abrir_pesquisa_tecnico)
        self.btVoltar = QPushButton("Voltar")
        self.btVoltar.clicked.connect(self.close)
        for b in (self.btSalvar, self.btPesqPeca, self.btPesqTec, self.btVoltar):
            b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            btL.addWidget(b)
        btL.addStretch()
        leftL.addWidget(btRow)

        # Histórico (Tabela)
        lblHist = QLabel("Últimas Movimentações")
        lblHist.setFont(QFont("Segoe UI", 16, QFont.Bold))
        leftL.addWidget(lblHist)

        self.tblHist = QTableWidget(self)
        self.tblHist.setColumnCount(9)
        self.tblHist.setHorizontalHeaderLabels([
            "Código","Peça","Data Mov.","Tipo","Quantidade","Saldo Atual","Local","Máquina","Funcionário"
        ])
        self._setup_table(self.tblHist, movable=True, sortable=True)
        self.tblHist.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tblHist.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tblHist.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tblHist.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tblHist.doubleClicked.connect(self._on_hist_double_click)
        leftL.addWidget(self.tblHist, 1)

        split.addWidget(left)

        # ---- Right (Estoque Crítico) ----
        right = QWidget(self)
        rightL = QVBoxLayout(right)
        rightL.setSpacing(10)

        lblMin = QLabel("Estoque Crítico")
        lblMin.setFont(QFont("Segoe UI", 16, QFont.Bold))
        rightL.addWidget(lblMin)

        self.chkZero = QCheckBox("Mostrar estoque = 0")
        self.chkZero.stateChanged.connect(self._carregar_estoque_minimo)
        rightL.addWidget(self.chkZero)

        self.tblMin = QTableWidget(self)
        self.tblMin.setColumnCount(5)
        self.tblMin.setHorizontalHeaderLabels(["Código","Descrição","Local","Saldo","Mínimo"])
        self._setup_table(self.tblMin, movable=True, sortable=True)
        rightL.addWidget(self.tblMin, 1)

        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)

        # Statusbar
        sb = QStatusBar()
        sb.showMessage("Pronto. Ctrl+S salva • Duplo clique no histórico preenche o formulário.")
        self.setStatusBar(sb)

        # Estilo leve
        self.setStyleSheet("""
            QMainWindow { background: #E8F1FB; }
            QPushButton { padding:8px 14px; background: white; border:1px solid #d7e3ff; border-radius:8px; }
            QPushButton:hover { background: #f6faff; }
            QLineEdit, QSpinBox { background:white; border:1px solid #cfdaf5; border-radius:6px; padding:5px 8px; }
            QTableWidget { background: white; border:1px solid #cfdaf5; border-radius:6px; gridline-color:#e3ecff; }
        """)

        # Carregamento inicial (após montar)
        QTimer.singleShot(120, self._load_initial_data)

    # ---------- Setup de tabela (reordenar, ordenar, zebra, etc.) ----------
    def _setup_table(self, table: QTableWidget, *, movable=True, sortable=True):
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        hdr = table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(QHeaderView.Interactive)  # usuário redimensiona
        if movable:
            hdr.setSectionsMovable(True)                    # arrastar colunas
        if sortable:
            table.setSortingEnabled(True)                   # clicar p/ ordenar

    # ---------- Menu e Atalhos ----------
    def _build_menu(self):
        mb = self.menuBar()
        menu = mb.addMenu("&Ações")
        actSave = QAction("Salvar (Ctrl+S)", self); actSave.setShortcut("Ctrl+S"); actSave.triggered.connect(self._realizar_movimentacao)
        actPeca = QAction("Pesquisar Peça (Ctrl+P)", self); actPeca.setShortcut("Ctrl+P"); actPeca.triggered.connect(self._abrir_pesquisa_peca)
        actTec  = QAction("Pesquisar Técnico (Ctrl+T)", self); actTec.setShortcut("Ctrl+T"); actTec.triggered.connect(self._abrir_pesquisa_tecnico)
        actVoltar = QAction("Voltar (Esc)", self); actVoltar.setShortcut("Esc"); actVoltar.triggered.connect(self.close)
        for a in (actSave, actPeca, actTec, actVoltar):
            menu.addAction(a)

    # ---------- Carregamentos ----------
    def _load_initial_data(self):
        self._carregar_historico()
        self._carregar_estoque_minimo()

    def _carregar_historico(self):
        sql = """
            SELECT
              h.codigo,
              h.nome,
              TO_CHAR(h.data_movimentacao,'DD/MM/YYYY HH24:MI:SS'),
              h.tipo_movimentacao,
              h.quantidade_movimentada,
              COALESCE(p.saldo,0),
              COALESCE(p.local,''),
              COALESCE(h.maquina,''),
              h.funcionario
            FROM historico_movimentacoes h
            LEFT JOIN produtos p ON h.codigo=p.codigo
            ORDER BY h.data_movimentacao DESC
            LIMIT 15
        """
        try:
            self.cursor.execute(sql)
            rows = self.cursor.fetchall()
        except DatabaseError as e:
            _err(self, "Histórico", f"Erro ao carregar histórico.\n\n{e}")
            return

        self.tblHist.setRowCount(0)
        for row in rows:
            r = self.tblHist.rowCount()
            self.tblHist.insertRow(r)
            for c, val in enumerate(row):
                item = QTableWidgetItem("" if val is None else str(val))
                # salienta saldo zerado
                if c == 5:
                    try:
                        if int(val) == 0:
                            item.setBackground(QColor("#F08080"))
                    except Exception:
                        pass
                # alinhamentos
                if c in (4, 5):  # Quantidade, Saldo
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                elif c in (2, 3):  # Data, Tipo
                    item.setTextAlignment(Qt.AlignCenter)
                else:
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.tblHist.setItem(r, c, item)

    def _carregar_estoque_minimo(self):
        if self.chkZero.isChecked():
            sql = "SELECT codigo,descricao,local,saldo,estoque_minimo FROM produtos WHERE estoque_minimo=0 ORDER BY codigo"
        else:
            sql = """
                SELECT codigo,descricao,local,saldo,estoque_minimo
                FROM produtos
                WHERE saldo<=estoque_minimo
                ORDER BY CASE WHEN saldo<estoque_minimo THEN 0 ELSE 1 END, codigo
            """
        try:
            self.cursor.execute(sql)
            rows = self.cursor.fetchall()
        except DatabaseError as e:
            _err(self, "Estoque Crítico", f"Erro ao carregar estoque mínimo.\n\n{e}")
            return

        self.tblMin.setRowCount(0)
        for cod, desc, local, saldo, minimo in rows:
            r = self.tblMin.rowCount()
            self.tblMin.insertRow(r)
            vals = [cod, desc, local, saldo, minimo]
            for c, val in enumerate(vals):
                item = QTableWidgetItem("" if val is None else str(val))
                # alinhamento numérico
                if c in (3, 4):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                # cores (pinta só a 1ª célula p/ economizar)
                if c == 0:
                    try:
                        s = float(saldo or 0); m = float(minimo or 0)
                        if s < m:
                            item.setBackground(QColor("#F0A7A7"))
                        elif s == m:
                            item.setBackground(QColor("#FCFCBD"))
                    except Exception:
                        pass
                self.tblMin.setItem(r, c, item)

    # ---------- Lookups ----------
    def _buscar_nome_peca(self, *_):
        cod = self.edCodigo.text().strip().upper()
        if not cod:
            self.edNome.setText("")
            return
        try:
            self.cursor.execute("SELECT descricao FROM produtos WHERE UPPER(codigo)=%s", (cod,))
            row = self.cursor.fetchone()
        except DatabaseError as e:
            _err(self, "Peça", f"Erro ao buscar peça.\n\n{e}")
            return
        self.edNome.setText("" if not row else (row[0] or "").upper())

    def _buscar_nome_tecnico(self, *_):
        cod = self.edCodTec.text().strip().upper()
        if not cod:
            self.edNomeTec.setText("")
            return
        try:
            self.cursor.execute("SELECT nome FROM tecnico WHERE UPPER(codigo)=%s", (cod,))
            row = self.cursor.fetchone()
        except DatabaseError as e:
            _err(self, "Técnico", f"Erro ao buscar técnico.\n\n{e}")
            return
        self.edNomeTec.setText("" if not row else (row[0] or "").upper())

    # ---------- Histórico -> Form ----------
    def _on_hist_double_click(self, _index):
        row = self.tblHist.currentRow()
        if row < 0:
            return
        vals = [self.tblHist.item(row, c).text() if self.tblHist.item(row, c) else "" for c in range(9)]
        cod, nome, data, tipo, qt, saldo, local, maquina, funcionario = vals

        self.edCodigo.setText(cod)
        self.edNome.setText(nome)
        try:
            self.spQuantidade.setValue(int(qt))
        except Exception:
            pass
        self.rbEntrada.setChecked(tipo.upper() == "ENTRADA")
        self.rbSaida.setChecked(tipo.upper() == "SAIDA")
        self.edMaquina.setText(maquina or local)
        self.edNomeTec.setText(funcionario)

    # ---------- Movimentação ----------
    def _realizar_movimentacao(self):
        cod = self.edCodigo.text().strip().upper()
        nome = self.edNome.text().strip()
        qt   = self.spQuantidade.value()
        nometec = self.edNomeTec.text().strip()
        maq  = self.edMaquina.text().strip()
        tipo = "ENTRADA" if self.rbEntrada.isChecked() else "SAIDA"

        if not all([cod, nome, qt, nometec, maq, tipo]):
            _err(self, "Validação", "Preencha todos os campos obrigatórios.")
            return

        try:
            self.cursor.execute("SELECT saldo FROM produtos WHERE UPPER(codigo)=%s", (cod,))
            r = self.cursor.fetchone()
            if not r:
                _err(self, "Validação", "Peça não existe.")
                return
            saldo = r[0] or 0
            if tipo == "ENTRADA":
                novo = saldo + qt
            else:
                if qt > saldo:
                    _err(self, "Validação", f"Saldo insuficiente ({saldo}).")
                    return
                novo = saldo - qt

            # UPDATE saldo
            self.cursor.execute("UPDATE produtos SET saldo=%s WHERE UPPER(codigo)=%s", (novo, cod))
            self.conn.commit()

            # INSERT histórico
            self.cursor.execute("""
                INSERT INTO historico_movimentacoes
                (codigo, nome, data_movimentacao, tipo_movimentacao,
                 quantidade_movimentada, funcionario, maquina)
                VALUES (%s, %s, CURRENT_TIMESTAMP, %s, %s, %s, %s)
            """, (cod, nome, tipo, qt, nometec, maq))
            self.conn.commit()

        except DatabaseError as e:
            self.conn.rollback()
            _err(self, "Movimentação", f"Erro ao salvar movimentação.\n\n{e}")
            return

        # nada de popup de sucesso — só um toque discreto na status bar
        self.statusBar().showMessage("Movimentação salva.", 2000)
        self._carregar_historico()
        self._carregar_estoque_minimo()
        QMessageBox.information(self, "Movimentação", "Movimentação realizada com sucesso!")

    # ---------- Pesquisas ----------
    def _abrir_pesquisa_peca(self):
        def search_fn(termo):
            like = f"%{termo}%"
            try:
                self.cursor.execute("""
                    SELECT codigo, descricao, saldo
                    FROM produtos
                    WHERE UPPER(codigo) LIKE %s OR UPPER(descricao) LIKE %s
                    ORDER BY descricao
                """, (like, like))
                return self.cursor.fetchall()
            except DatabaseError as e:
                _err(self, "Pesquisar Peças", f"Erro na consulta.\n\n{e}")
                return []

        def on_select(vals):
            cod = vals[0]
            self.edCodigo.setText(cod)
            self._buscar_nome_peca()

        dlg = SearchDialog(self, "Pesquisar Peças", ["Código","Descrição","Saldo"], search_fn, on_select)
        dlg.exec()

    def _abrir_pesquisa_tecnico(self):
        def search_fn(termo):
            like = f"%{termo}%"
            try:
                self.cursor.execute("""
                    SELECT codigo, nome
                    FROM tecnico
                    WHERE UPPER(codigo) LIKE %s OR UPPER(nome) LIKE %s
                    ORDER BY nome
                """, (like, like))
                return self.cursor.fetchall()
            except DatabaseError as e:
                _err(self, "Pesquisar Técnicos", f"Erro na consulta.\n\n{e}")
                return []

        def on_select(vals):
            cod = vals[0]
            self.edCodTec.setText(cod)
            self._buscar_nome_tecnico()

        dlg = SearchDialog(self, "Pesquisar Técnicos", ["Código","Nome"], search_fn, on_select)
        dlg.exec()

    # ---------- Fechamento ----------
    def closeEvent(self, event):
        try:
            if hasattr(self, "cursor") and self.cursor:
                self.cursor.close()
            if hasattr(self, "conn") and self.conn:
                self.conn.close()
        except Exception:
            pass
        super().closeEvent(event)

# --------- função que o launcher espera ---------
def abrir(parent=None):
    win = MovimentacaoApp(parent)
    win.showMaximized()
    return win

# --------- standalone ---------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MovimentacaoApp()
    w.showMaximized()
    sys.exit(app.exec())
