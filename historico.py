# historico.py - PySide6
from __future__ import annotations
import sys
from datetime import datetime
import psycopg2
from psycopg2 import OperationalError, DatabaseError

from PySide6.QtCore import Qt, QTimer, QDate
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QSplitter, QStatusBar, QDialog, QFormLayout, QLineEdit, QCheckBox,
    QMessageBox, QInputDialog, QLineEdit as QLineEditEcho
)

from calendario import CampoData

APP_TITLE = "Histórico de Movimentação"
SENHA_HISTORICO = "609609"
MAX_HISTORY_ROWS = 2000

COLS = (
    "codigo", "nome", "data_movimentacao", "tipo_movimentacao", "quantidade_movimentada",
    "funcionario", "maquina", "prateleira", "numero_nota", "nome_fornecedor", "valor_unitario", "ncm"
)

def _err(self, title, msg):
    QMessageBox.critical(self, title, msg)

class HistoricoApp(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 800)

        self.last_filter = {"filters": {}, "start_date": None, "end_date": None}
        self.authorized = False

        # DB
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

        self._build_menu()

        title = QLabel(APP_TITLE); title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        root.addWidget(title)

        split = QSplitter(Qt.Vertical, self); root.addWidget(split, 1)

        # Tabela
        top = QWidget(self); topL = QVBoxLayout(top); topL.setContentsMargins(0,0,0,0)
        self.table = QTableWidget(self)
        self.table.setColumnCount(len(COLS))
        self.table.setHorizontalHeaderLabels([c.replace("_"," ").title() for c in COLS])
        self._setup_table(self.table)
        topL.addWidget(self.table)
        split.addWidget(top)

        # Barra de ações
        bottom = QWidget(self); botL = QHBoxLayout(bottom); botL.setContentsMargins(0,0,0,0)
        self.btnLoad   = QPushButton("Carregar Histórico"); self.btnLoad.clicked.connect(self._load_clicked)
        self.btnFilter = QPushButton("Filtrar Dados");       self.btnFilter.clicked.connect(self._open_filter)
        self.btnReset  = QPushButton("Redefinir Filtros");   self.btnReset.clicked.connect(self._reset_filters)
        self.btnVoltar = QPushButton("Voltar");              self.btnVoltar.clicked.connect(self.close)
        for b in (self.btnLoad, self.btnFilter, self.btnReset):
            b.setMinimumWidth(200)
        botL.addWidget(self.btnLoad); botL.addWidget(self.btnFilter); botL.addWidget(self.btnReset)
        botL.addStretch(); botL.addWidget(self.btnVoltar)
        split.addWidget(bottom)
        split.setStretchFactor(0, 10); split.setStretchFactor(1, 1)

        # Rodapé
        self.lblCount = QLabel("Registros exibidos: 0")
        sb = QStatusBar(); sb.addPermanentWidget(self.lblCount)
        self.setStatusBar(sb)

        # Estilo
        self.setStyleSheet("""
            QMainWindow { background: #E8F1FB; }
            QPushButton { padding:8px 14px; background: white; border:1px solid #d7e3ff; border-radius:8px; }
            QPushButton:hover { background: #f6faff; }
            QTableWidget { background: white; border:1px solid #cfdaf5; border-radius:6px; gridline-color:#e3ecff; }
        """)

        # Autenticação única ao abrir
        QTimer.singleShot(50, self._auth_then_load)

    # ---------- menu ----------
    def _build_menu(self):
        mb = self.menuBar()
        mA = mb.addMenu("&Ações")
        actLoad = QAction("Carregar (F5)", self); actLoad.setShortcut("F5"); actLoad.triggered.connect(self._load_clicked)
        actFilter = QAction("Filtrar (Ctrl+F)", self); actFilter.setShortcut("Ctrl+F"); actFilter.triggered.connect(self._open_filter)
        actReset = QAction("Redefinir (Ctrl+R)", self); actReset.setShortcut("Ctrl+R"); actReset.triggered.connect(self._reset_filters)
        actBack = QAction("Voltar (Esc)", self); actBack.setShortcut("Esc"); actBack.triggered.connect(self.close)
        for a in (actLoad, actFilter, actReset, actBack): mA.addAction(a)

    # ---------- tabela ----------
    def _setup_table(self, t: QTableWidget):
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.setAlternatingRowColors(True)
        t.verticalHeader().setVisible(False)
        hdr = t.horizontalHeader()
        hdr.setSectionsMovable(True)                 # arrastar colunas
        hdr.setSectionResizeMode(QHeaderView.Interactive)  # redimensionar
        t.setSortingEnabled(True)                    # ordenar por coluna
        # larguras mínimas amigáveis
        for i, c in enumerate(COLS):
            if c in ("codigo","tipo_movimentacao","ncm"): t.setColumnWidth(i, 120)
            elif c in ("quantidade_movimentada","valor_unitario","numero_nota"): t.setColumnWidth(i, 140)
            elif c in ("data_movimentacao",): t.setColumnWidth(i, 190)
            else: t.setColumnWidth(i, 180)

    # ---------- auth ----------
    def _auth_then_load(self):
        if self.authorized:
            self._load_data()
            return
        senha, ok = QInputDialog.getText(self, "Senha", "Digite a senha para acessar:", QLineEditEcho.Password)
        if not ok:
            self.close(); return
        if senha != SENHA_HISTORICO:
            _err(self, "Erro", "Senha incorreta.")
            self.close(); return
        self.authorized = True
        self._load_data()

    # ---------- ações ----------
    def _load_clicked(self):
        if not self.authorized:
            self._auth_then_load(); return
        self._load_data()

    def _reset_filters(self):
        self.last_filter = {"filters": {}, "start_date": None, "end_date": None}
        if not self.authorized:
            self._auth_then_load(); return
        self._load_data()

    # ---------- carga ----------
    def _load_data(self, where: str | None = None, params: tuple | None = None):
        self.table.setRowCount(0)
        sql = """
            SELECT
                h.codigo,
                h.nome,
                TO_CHAR(h.data_movimentacao, 'DD/MM/YYYY HH24:MI:SS') AS data_movimentacao,
                h.tipo_movimentacao,
                h.quantidade_movimentada,
                COALESCE(t.nome, h.funcionario) AS funcionario,
                h.maquina,
                p.local AS prateleira,
                h.numero_nota,
                h.nome_fornecedor,
                h.valor_unitario,
                h.ncm
            FROM historico_movimentacoes h
            LEFT JOIN tecnico  t ON h.funcionario = t.codigo
            LEFT JOIN produtos p ON h.codigo = p.codigo
        """
        if where:
            sql += " WHERE " + where
        sql += f" ORDER BY h.data_movimentacao DESC LIMIT {MAX_HISTORY_ROWS}"

        try:
            self.cursor.execute(sql, params or ())
            rows = self.cursor.fetchall()
        except DatabaseError as e:
            _err(self, "Histórico", f"Não foi possível carregar os dados.\n\n{e}")
            return

        sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))

        for row, r in enumerate(rows):
            for c, val in enumerate(r):
                item = QTableWidgetItem("" if val is None else str(val))
                # alinhamentos
                colname = COLS[c]
                if colname in ("quantidade_movimentada", "valor_unitario", "numero_nota"):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                elif colname in ("data_movimentacao", "tipo_movimentacao"):
                    item.setTextAlignment(Qt.AlignCenter)
                else:
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.table.setItem(row, c, item)

        self.table.setSortingEnabled(sorting)
        self.lblCount.setText(f"Registros exibidos: {len(rows)}")
        msg = "Histórico atualizado."
        if len(rows) == MAX_HISTORY_ROWS:
            msg = f"Histórico atualizado. Mostrando os {MAX_HISTORY_ROWS} registros mais recentes."
        self.statusBar().showMessage(msg, 2500)

    # ---------- filtro ----------
    def _open_filter(self):
        if not self.authorized:
            self._auth_then_load(); 
            if not self.authorized: return

        dlg = QDialog(self); dlg.setWindowTitle("Filtrar Histórico"); dlg.resize(540, 680)
        lay = QVBoxLayout(dlg)

        form = QWidget(dlg); fl = QFormLayout(form); fl.setLabelAlignment(Qt.AlignRight)
        edits: dict[str, QLineEdit] = {}

        # Campos de texto (todos menos data)
        for col in COLS:
            if col == "data_movimentacao": 
                continue
            lbl = col.replace("_", " ").title()
            ed = QLineEdit()
            ed.setPlaceholderText(f"Filtrar por {lbl}…")
            prev = self.last_filter["filters"].get(col)
            if prev: ed.setText(prev)
            fl.addRow(lbl + ":", ed)
            edits[col] = ed
        lay.addWidget(form)

        # Datas
        wDates = QWidget(dlg); hl = QHBoxLayout(wDates); hl.setContentsMargins(0,0,0,0)
        boxStart = QCheckBox("Data Inicial"); deStart = CampoData(dlg); deStart.setDisplayFormat("dd/MM/yyyy")
        boxEnd   = QCheckBox("Data Final");   deEnd   = CampoData(dlg); deEnd.setDisplayFormat("dd/MM/yyyy")
        if self.last_filter["start_date"]:
            try:
                d = datetime.strptime(self.last_filter["start_date"], "%d/%m/%Y")
                deStart.setDate(QDate(d.year, d.month, d.day)); boxStart.setChecked(True)
            except Exception: pass
        else:
            deStart.setDate(QDate.currentDate())
        if self.last_filter["end_date"]:
            try:
                d = datetime.strptime(self.last_filter["end_date"], "%d/%m/%Y")
                deEnd.setDate(QDate(d.year, d.month, d.day)); boxEnd.setChecked(True)
            except Exception: pass
        else:
            deEnd.setDate(QDate.currentDate())
        hl.addWidget(boxStart); hl.addWidget(deStart); hl.addSpacing(16)
        hl.addWidget(boxEnd);   hl.addWidget(deEnd);   hl.addStretch()
        lay.addWidget(wDates)

        # Botões
        rowBtns = QWidget(dlg); h2 = QHBoxLayout(rowBtns); h2.setContentsMargins(0,0,0,0)
        btApply = QPushButton("Aplicar Filtro"); btCancel = QPushButton("Cancelar")
        h2.addStretch(); h2.addWidget(btApply); h2.addWidget(btCancel)
        lay.addWidget(rowBtns)

        def apply():
            # Monta condições
            filled = {k: v.text().strip() for k, v in edits.items() if v.text().strip()}
            if not filled and not (boxStart.isChecked() or boxEnd.isChecked()):
                _err(self, "Filtro", "Preencha pelo menos um campo.")
                return

            conds = []
            params = []

            for col, value in filled.items():
                if col in ("quantidade_movimentada", "numero_nota", "valor_unitario", "ncm"):
                    conds.append(f"CAST(h.{col} AS TEXT) ILIKE %s")
                elif col == "prateleira":
                    conds.append("CAST(p.local AS TEXT) ILIKE %s")
                else:
                    conds.append(f"CAST(h.{col} AS TEXT) ILIKE %s")
                params.append(f"%{value}%")

            start_str = end_str = None
            start_dt = end_dt = None
            if boxStart.isChecked():
                d = deStart.date()
                start_dt = datetime(d.year(), d.month(), d.day())
                conds.append("h.data_movimentacao >= %s")
                params.append(start_dt)
                start_str = start_dt.strftime("%d/%m/%Y")
            if boxEnd.isChecked():
                d = deEnd.date()
                end_dt = datetime(d.year(), d.month(), d.day(), 23, 59, 59, 999999)
                conds.append("h.data_movimentacao <= %s")
                params.append(end_dt)
                end_str = end_dt.strftime("%d/%m/%Y")

            if start_dt and end_dt and start_dt > end_dt:
                _err(self, "Filtro", "Data inicial não pode ser maior que a data final.")
                return

            where = " AND ".join(conds) if conds else None
            self.last_filter = {"filters": filled, "start_date": start_str, "end_date": end_str}

            self._load_data(where, tuple(params))
            dlg.accept()

        btApply.clicked.connect(apply)
        btCancel.clicked.connect(dlg.reject)
        dlg.exec()

    # ---------- fechar ----------
    def closeEvent(self, e):
        try:
            if hasattr(self, "cursor") and self.cursor: self.cursor.close()
            if hasattr(self, "conn") and self.conn: self.conn.close()
        except Exception:
            pass
        # reabrir janela mãe se existir
        p = self.parent()
        if p and hasattr(p, "show"):
            p.show(); p.raise_(); p.activateWindow()
        super().closeEvent(e)

# Launcher p/ main.py
def abrir(parent=None):
    win = HistoricoApp(parent)
    win.showMaximized()
    return win

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = HistoricoApp()
    w.showMaximized()
    sys.exit(app.exec())
