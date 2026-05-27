# estoque_baixo.py - PySide6
# Requisitos:
#   pip install PySide6 psycopg2-binary
from __future__ import annotations
import sys

import psycopg2
from psycopg2 import OperationalError, DatabaseError

from PySide6.QtCore import Qt, QTimer, QObject, Signal, QThread
from PySide6.QtGui import QAction, QFont, QColor, QBrush

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QInputDialog, QMessageBox, QStatusBar, QGroupBox, QSpinBox
)

APP_TITLE = "Editar Estoque Mínimo"
DB = dict(dbname="Almoxarifado", user="Ti", password="jj00tt", host="10.2.149.7")

COLS = ("Código","Descrição","Local","Saldo","Mínimo")

def _err(self, title, msg): QMessageBox.critical(self, title, msg)
def _warn(self, title, msg): QMessageBox.warning(self, title, msg)

# ---------- Worker para busca assíncrona ----------
class FetchWorker(QObject):
    finished = Signal(int, list)   # (req_id, rows)
    failed   = Signal(int, str)

    def __init__(self, req_id: int, sql: str, params: tuple):
        super().__init__()
        self.req_id = req_id
        self.sql = sql
        self.params = params

    def run(self):
        conn = None
        cur = None
        try:
            conn = psycopg2.connect(**DB)
            cur  = conn.cursor()
            cur.execute(self.sql, self.params)
            rows = cur.fetchall()
            self.finished.emit(self.req_id, rows)
        except Exception as e:
            self.failed.emit(self.req_id, str(e))
        finally:
            try:
                if cur: cur.close()
                if conn: conn.close()
            except Exception:
                pass

# ---------- App ----------
class EstoqueBaixoApp(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 800)

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

        # --------- Filtros ---------
        grpFiltros = QGroupBox("Filtros")
        layF = QFormLayout(grpFiltros)
        layF.setLabelAlignment(Qt.AlignRight)
        layF.setHorizontalSpacing(12); layF.setVerticalSpacing(8)

        self.edTexto = QLineEdit(); self.edTexto.setPlaceholderText("Código ou Descrição (ILIKE)")
        self.edMinEq = QLineEdit(); self.edMinEq.setPlaceholderText("= Mínimo exato (opcional)")
        self.edFam   = QLineEdit(); self.edFam.setPlaceholderText("Família (split_part(codigo,'.',1))")

        rowBtns = QWidget(); hb = QHBoxLayout(rowBtns); hb.setContentsMargins(0,0,0,0)
        btFiltrar = QPushButton("Filtrar (Enter)")
        btLimpar  = QPushButton("Limpar")
        btAtual   = QPushButton("Atualizar (F5)")
        hb.addWidget(btFiltrar); hb.addWidget(btLimpar); hb.addStretch(); hb.addWidget(btAtual)

        layF.addRow("Código/Peça:", self.edTexto)
        layF.addRow("Estoque Mínimo:", self.edMinEq)
        layF.addRow("Família:", self.edFam)
        layF.addRow("", rowBtns)

        root.addWidget(grpFiltros)

        # --------- Ações em Grupo ---------
        grpAcao = QGroupBox("Ações em Grupo")
        layG = QHBoxLayout(grpAcao); layG.setContentsMargins(10,10,10,10)
        self.spNovoMin = QSpinBox(); self.spNovoMin.setRange(0, 999_999_999); self.spNovoMin.setValue(0)
        btAplicar = QPushButton("Aplicar aos Selecionados (Ctrl+Enter)")
        self.lblSel = QLabel("Selecionados: 0")
        layG.addWidget(QLabel("Novo Estoque Mínimo:"))
        layG.addWidget(self.spNovoMin)
        layG.addSpacing(12)
        layG.addWidget(btAplicar)
        layG.addStretch()
        layG.addWidget(self.lblSel)
        root.addWidget(grpAcao)

        # --------- Tabela ---------
        self.table = QTableWidget(self)
        self.table.setColumnCount(len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self._setup_table(self.table)
        root.addWidget(self.table, 1)

        # Status
        self.lblInfo = QLabel("0 itens.")
        root.addWidget(self.lblInfo)
        sb = QStatusBar(); self.setStatusBar(sb)

        # Estilo
        self.setStyleSheet("""
            QMainWindow { background:#EAF2FC; }
            QGroupBox { background:white; border:1px solid #dbe5ff; border-radius:10px; margin-top:10px; }
            QGroupBox::title { subcontrol-origin: margin; left:12px; padding:0 6px; background:#EAF2FC; }
            QPushButton { padding:8px 14px; background:white; border:1px solid #d7e3ff; border-radius:8px; }
            QPushButton:hover { background:#f6faff; }
            QLineEdit, QSpinBox { background:white; border:1px solid #cfdaf5; border-radius:6px; padding:6px 10px; }
            QTableWidget { background:white; border:1px solid #cfdaf5; border-radius:6px; gridline-color:#e3ecff; }
        """)

        # Menu / Atalhos
        self._build_menu()

        # Infra de busca assíncrona
        self._debounce = QTimer(self); self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._run_search)
        self._req_id = 0
        self._fetch_thread: QThread | None = None
        self._fetch_worker: FetchWorker | None = None
        self._active_fetches: list[tuple[QThread, FetchWorker]] = []
        self._closing = False

        # Ligações
        btFiltrar.clicked.connect(self._run_search)
        btLimpar.clicked.connect(self._limpar_filtros)
        btAtual.clicked.connect(self._run_search)

        self.edTexto.returnPressed.connect(self._run_search)
        self.edMinEq.returnPressed.connect(self._run_search)
        self.edFam.returnPressed.connect(self._run_search)

        btAplicar.clicked.connect(self._apply_group)
        self.table.itemSelectionChanged.connect(self._update_sel_label)
        self.table.doubleClicked.connect(self._edit_min_on_double)

        # Carga inicial
        QTimer.singleShot(120, self._run_search)

    # ---------- Menu ----------
    def _build_menu(self):
        mb = self.menuBar()
        mA = mb.addMenu("&Ações")
        aFilter = QAction("Filtrar (Enter)", self); aFilter.setShortcut("Return"); aFilter.triggered.connect(self._run_search)
        aApply  = QAction("Aplicar em Grupo (Ctrl+Enter)", self); aApply.setShortcut("Ctrl+Return"); aApply.triggered.connect(self._apply_group)
        aRef    = QAction("Atualizar (F5)", self); aRef.setShortcut("F5"); aRef.triggered.connect(self._run_search)
        aBack   = QAction("Voltar (Esc)", self); aBack.setShortcut("Esc"); aBack.triggered.connect(self.close)
        for a in (aFilter, aApply, aRef, aBack): mA.addAction(a)

    # ---------- Tabela ----------
    def _setup_table(self, t: QTableWidget):
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.ExtendedSelection)
        t.setAlternatingRowColors(True)
        t.verticalHeader().setVisible(False)
        hdr = t.horizontalHeader()
        hdr.setSectionsMovable(True)                      # arrastar colunas
        hdr.setSectionResizeMode(QHeaderView.Interactive) # redimensionar
        t.setSortingEnabled(True)
        widths = [160, 520, 180, 110, 110]
        for i, w in enumerate(widths): t.setColumnWidth(i, w)

    # ---------- SQL dinâmico dos filtros ----------
    def _sql_for_list(self):
        text = (self.edTexto.text() or "").strip()
        minf = (self.edMinEq.text() or "").strip()
        fam  = (self.edFam.text() or "").strip()

        sql = """
            SELECT
              codigo,
              descricao,
              COALESCE(local,'') AS local,
              COALESCE(saldo,0)  AS saldo,
              COALESCE(estoque_minimo,0) AS minimo
            FROM produtos
        """
        params = []
        where_clauses = []

        if text:
            where_clauses.append("(codigo ILIKE %s OR descricao ILIKE %s)")
            params.extend([f"%{text}%", f"%{text}%"])

        if minf.isdigit():
            where_clauses.append("estoque_minimo = %s")
            params.append(int(minf))

        if fam:
            where_clauses.append("split_part(codigo,'.',1) = %s")
            params.append(fam)

        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)

        sql += " ORDER BY codigo"
        return sql, tuple(params)


    # ---------- Busca assíncrona ----------
    def _run_search(self):
        if self._closing:
            return
        self.statusBar().showMessage("Carregando…", 800)
        sql, params = self._sql_for_list()
        self._req_id += 1
        req_id = self._req_id

        # Mantem referencias das buscas antigas ate terminarem; respostas velhas sao ignoradas por req_id.
        thread = QThread(self)
        worker = FetchWorker(req_id, sql, params)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_fetch_ok)
        worker.failed.connect(self._on_fetch_fail)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda thread=thread, worker=worker: self._cleanup_fetch(thread, worker))

        self._fetch_thread = thread
        self._fetch_worker = worker
        self._active_fetches.append((thread, worker))
        thread.start()

    def _cleanup_fetch(self, thread: QThread, worker: FetchWorker):
        self._active_fetches = [
            pair for pair in self._active_fetches
            if pair[0] is not thread and pair[1] is not worker
        ]
        if self._fetch_thread is thread:
            self._fetch_thread = None
            self._fetch_worker = None

    def _on_fetch_ok(self, req_id: int, rows: list):
        if self._closing:
            return
        if req_id != self._req_id:  # resposta antiga
            return
        t = self.table
        t.setRowCount(0)
        total = 0
        for (codigo, desc, local, saldo, minimo) in rows:
            r = t.rowCount(); t.insertRow(r)
            vals = [str(codigo).upper(),
                    str(desc or "").upper(),
                    str(local or "").upper(),
                    str(int(saldo or 0)),
                    str(int(minimo or 0))]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c in (3,4):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                t.setItem(r, c, it)

            # cores por critério
            s = int(saldo or 0)
            m = int(minimo or 0)
            if s < m:
                self._paint_row(r, "#F0A7A7")  # crítico
            elif s == m:
                self._paint_row(r, "#FCFCBD")  # igual

            total += 1

        self.lblInfo.setText(f"{total} itens exibidos.")
        self.statusBar().showMessage(f"{total} linhas.", 1200)
        self._update_sel_label()

    def _on_fetch_fail(self, req_id: int, err: str):
        if self._closing:
            return
        if req_id != self._req_id: return
        _err(self, "Consulta", f"Erro ao carregar.\n\n{err}")

    def _paint_row(self, row: int, color):
        # aceita "#RRGGBB" ou QColor
        brush = QBrush(QColor(color) if isinstance(color, str) else color)
        for c in range(self.table.columnCount()):
            it = self.table.item(row, c)
            if it:
                it.setBackground(brush)
    

    # ---------- Edição individual (duplo clique na coluna "Mínimo") ----------
    def _edit_min_on_double(self, idx):
        if idx.column() != 4:  # somente coluna "Mínimo"
            return
        r = idx.row()
        cod = self.table.item(r, 0).text()
        atual = int(self.table.item(r, 4).text() or "0")
        novo, ok = QInputDialog.getInt(self, "Editar Mínimo",
                                       f"Novo mínimo para {cod}:", atual, 0, 999_999_999, 1)
        if not ok: return
        self._update_db_min([(cod, novo)])
        self._run_search()

    # ---------- Aplicar em grupo ----------
    def _apply_group(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return _warn(self, "Selecionar", "Selecione ao menos um item.")
        novo = int(self.spNovoMin.value())
        pairs = []
        for mi in sel:
            r = mi.row()
            cod = self.table.item(r, 0).text()
            pairs.append((cod, novo))
        self._update_db_min(pairs)
        self._run_search()
        self.statusBar().showMessage(f"Ajustado mínimo em {len(pairs)} itens.", 1500)

    def _update_db_min(self, pairs: list[tuple[str,int]]):
        try:
            # Uma transação só
            for cod, minimo in pairs:
                self.cursor.execute("UPDATE produtos SET estoque_minimo=%s WHERE codigo=%s",
                                    (int(minimo), cod))
            self.conn.commit()
        except DatabaseError as e:
            self.conn.rollback()
            _err(self, "Atualização", f"Falhou ao salvar.\n\n{e}")

    # ---------- Auxiliares ----------
    def _update_sel_label(self):
        n = len(self.table.selectionModel().selectedRows()) if self.table.selectionModel() else 0
        self.lblSel.setText(f"Selecionados: {n}")

    def _limpar_filtros(self):
        self.edTexto.clear(); self.edMinEq.clear(); self.edFam.clear()
        self._run_search()

    # ---------- Fechamento ----------
    def closeEvent(self, e):
        self._closing = True
        for thread, _worker in list(getattr(self, "_active_fetches", [])):
            try:
                if thread.isRunning():
                    thread.quit()
                    thread.wait(1000)
            except Exception:
                pass
        try:
            if hasattr(self, "cursor") and self.cursor: self.cursor.close()
            if hasattr(self, "conn") and self.conn: self.conn.close()
        except Exception:
            pass
        p = self.parent()
        if p and hasattr(p, "show"):
            p.show(); p.raise_(); p.activateWindow()
        super().closeEvent(e)

# --------- função para o launcher (main.py) ---------
def abrir(parent=None):
    win = EstoqueBaixoApp(parent)
    win.showMaximized()
    return win

# --------- standalone ---------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = EstoqueBaixoApp()
    w.showMaximized()
    sys.exit(app.exec())
