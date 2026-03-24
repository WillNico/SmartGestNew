# inventario.py - PySide6 (versão estável)
# Requisitos:
#   pip install PySide6 psycopg2-binary reportlab pandas openpyxl shiboken6

from __future__ import annotations
import sys
from datetime import datetime

import psycopg2
from psycopg2 import OperationalError, DatabaseError

from PySide6.QtCore import (
    Qt, QTimer, QDate, QObject, Signal, QThread, QSettings, QByteArray
)
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QDateEdit, QCheckBox, QFileDialog, QStatusBar,
    QMessageBox, QGroupBox
)

import shiboken6

# Export opcional
try:
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.pdfgen import canvas
    _HAS_REPORTLAB = True
except Exception:
    _HAS_REPORTLAB = False

try:
    import pandas as pd
    _HAS_PANDAS = True
except Exception:
    _HAS_PANDAS = False

APP_TITLE = "Inventário"
COLS_BASE = ("Código", "Descrição", "Saldo", "Prateleira", "Última Mov.", "Funcionário")
COLS_VIEW = ("✓",) + COLS_BASE

DB = dict(dbname="Almoxarifado", user="Ti", password="jj00tt", host="10.2.149.7")


def _err(self, title, msg):
    QMessageBox.critical(self, title, msg)


# ---------- Worker seguro ----------
class FetchWorker(QObject):
    finished = Signal(int, list)   # (req_id, rows)
    failed   = Signal(int, str)

    def __init__(self, req_id: int, sql: str, params: tuple):
        super().__init__()
        self.req_id = req_id
        self.sql = sql
        self.params = params
        self._conn = None
        self._cur = None
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        try:
            if self._conn is not None:
                self._conn.cancel()
        except Exception:
            pass

    def run(self):
        try:
            if QThread.currentThread().isInterruptionRequested():
                return

            self._conn = psycopg2.connect(**DB)
            self._cur = self._conn.cursor()

            self._cur.execute(self.sql, self.params)

            if QThread.currentThread().isInterruptionRequested() or self._cancelled:
                return

            rows = self._cur.fetchall()

            if QThread.currentThread().isInterruptionRequested() or self._cancelled:
                return

            self.finished.emit(self.req_id, rows)

        except Exception as e:
            msg = str(e).lower()
            if self._cancelled or QThread.currentThread().isInterruptionRequested():
                return
            if "canceling statement due to user request" in msg:
                return
            self.failed.emit(self.req_id, str(e))

        finally:
            try:
                if self._cur:
                    self._cur.close()
            except Exception:
                pass
            try:
                if self._conn:
                    self._conn.close()
            except Exception:
                pass
            self._cur = None
            self._conn = None


class InventarioApp(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(APP_TITLE)
        self.resize(1360, 860)

        # estado interno
        self._filling = False
        self._changing_checks = False
        self._closing = False
        self._pending_search = False
        self._cursor_wait_on = False

        # infra async
        self._req_id = 0
        self._fetch_thread: QThread | None = None
        self._fetch_worker: FetchWorker | None = None

        # Conexão persistente da UI principal
        try:
            self.conn = psycopg2.connect(**DB)
            self.cursor = self.conn.cursor()
        except OperationalError as e:
            _err(self, "Banco de Dados", f"Falha na conexão com PostgreSQL.\n\n{e}")
            self.close()
            return

        # ===== UI =====
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(10)

        title = QLabel(APP_TITLE)
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        root.addWidget(title)

        # --------- Grupo Filtros ---------
        grpFiltros = QGroupBox("Filtros")
        layF = QFormLayout(grpFiltros)
        layF.setLabelAlignment(Qt.AlignRight)
        layF.setHorizontalSpacing(12)
        layF.setVerticalSpacing(8)

        self.edFamilia = QLineEdit()
        self.edFamilia.setPlaceholderText("Prefixo da família (ex.: ABC)")

        self.edFamiliaNome = QLineEdit()
        self.edFamiliaNome.setReadOnly(True)

        self.edPeca = QLineEdit()
        self.edPeca.setPlaceholderText("Código da peça")

        self.edPecaNome = QLineEdit()
        self.edPecaNome.setReadOnly(True)

        self.edBusca = QLineEdit()
        self.edBusca.setPlaceholderText("Busca rápida (código/descrição)")

        self.dtCorte = QDateEdit()
        self.dtCorte.setCalendarPopup(True)
        self.dtCorte.setDisplayFormat("dd/MM/yyyy")
        self.dtCorte.setDate(QDate.currentDate())

        self.chkTodas = QCheckBox("Mostrar todas")
        self.chkCorteOuSem = QCheckBox("Somente sem prateleira ou ≤ data de corte")
        self.chkCorteOuSem.setChecked(True)

        # debounce único
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._run_search)

        # ligações
        self.edFamilia.textChanged.connect(self._lookup_familia)
        self.edPeca.textChanged.connect(self._lookup_peca)
        self.edBusca.textChanged.connect(lambda: self._debounce.start(300))
        self.dtCorte.dateChanged.connect(lambda *_: self._debounce.start(150))
        self.chkTodas.stateChanged.connect(lambda *_: self._debounce.start(150))
        self.chkCorteOuSem.stateChanged.connect(lambda *_: self._debounce.start(150))

        layF.addRow("Família:", self.edFamilia)
        layF.addRow("Nome da Família:", self.edFamiliaNome)
        layF.addRow("Código da Peça:", self.edPeca)
        layF.addRow("Nome da Peça:", self.edPecaNome)
        layF.addRow("Busca rápida:", self.edBusca)

        rowFiltros = QWidget()
        hf = QHBoxLayout(rowFiltros)
        hf.setContentsMargins(0, 0, 0, 0)
        hf.addWidget(QLabel("Data de corte:"))
        hf.addWidget(self.dtCorte)
        hf.addSpacing(12)
        hf.addWidget(self.chkTodas)
        hf.addWidget(self.chkCorteOuSem)
        hf.addStretch()
        layF.addRow("", rowFiltros)

        root.addWidget(grpFiltros)

        # --------- Grupo Contagem ---------
        grpContagem = QGroupBox("Contagem (INVENTÁRIO)")
        layC = QFormLayout(grpContagem)
        layC.setLabelAlignment(Qt.AlignRight)
        layC.setHorizontalSpacing(12)
        layC.setVerticalSpacing(8)

        self.spQtd = QSpinBox()
        self.spQtd.setRange(0, 999_999_999)

        self.edLocal = QLineEdit()
        self.edLocal.setPlaceholderText("Prateleira / Local")

        self.edFunc = QLineEdit()
        self.edFunc.setPlaceholderText("Código do funcionário")

        self.edFuncNome = QLineEdit()
        self.edFuncNome.setReadOnly(True)

        self.edFunc.textChanged.connect(self._lookup_func)
        self.edLocal.returnPressed.connect(self._salvar)

        layC.addRow("Quantidade:", self.spQtd)
        layC.addRow("Prateleira:", self.edLocal)
        layC.addRow("Cód. Funcionário:", self.edFunc)
        layC.addRow("Nome do Funcionário:", self.edFuncNome)

        rowBtns = QWidget()
        hb = QHBoxLayout(rowBtns)
        hb.setContentsMargins(0, 0, 0, 0)

        btSalvar = QPushButton("Salvar")
        btSalvar.clicked.connect(self._salvar)

        btPDF = QPushButton("Exportar PDF")
        btPDF.clicked.connect(self._export_pdf)

        btXLS = QPushButton("Exportar Excel")
        btXLS.clicked.connect(self._export_excel)

        btLimpar = QPushButton("Limpar")
        btLimpar.clicked.connect(self._limpar_form)

        btAtual = QPushButton("Atualizar")
        btAtual.clicked.connect(self._run_search)

        btVoltar = QPushButton("Voltar")
        btVoltar.clicked.connect(self.close)

        for b in (btSalvar, btPDF, btXLS, btLimpar, btAtual):
            b.setMinimumWidth(120)

        hb.addWidget(btSalvar)
        hb.addWidget(btPDF)
        hb.addWidget(btXLS)
        hb.addWidget(btLimpar)
        hb.addWidget(btAtual)
        hb.addStretch()
        hb.addWidget(btVoltar)
        layC.addRow("", rowBtns)

        root.addWidget(grpContagem)

        # --------- Toolbar seleção ---------
        bar = QWidget()
        hb2 = QHBoxLayout(bar)
        hb2.setContentsMargins(0, 0, 0, 0)

        self.chkMarcarTodos = QCheckBox("Marcar todos (visíveis)")
        self.chkMarcarTodos.stateChanged.connect(self._toggle_all_visible)

        btnInvert = QPushButton("Inverter")
        btnInvert.clicked.connect(self._invert_checks)

        btnZero = QPushButton("Marcar saldo = 0")
        btnZero.clicked.connect(self._mark_saldo_zero)

        btnSemLoc = QPushButton("Marcar sem prateleira")
        btnSemLoc.clicked.connect(self._mark_sem_prateleira)

        self.lblSel = QLabel("Selecionados: 0  |  Saldo selecionado: 0")

        hb2.addWidget(self.chkMarcarTodos)
        hb2.addSpacing(8)
        hb2.addWidget(btnInvert)
        hb2.addSpacing(8)
        hb2.addWidget(btnZero)
        hb2.addWidget(btnSemLoc)
        hb2.addStretch()
        hb2.addWidget(self.lblSel)

        root.addWidget(bar)

        # --------- Tabela ---------
        self.table = QTableWidget(self)
        self.table.setColumnCount(len(COLS_VIEW))
        self.table.setHorizontalHeaderLabels(COLS_VIEW)
        self._setup_table(self.table)
        root.addWidget(self.table, 1)

        self.lblTotais = QLabel("Total de peças: –  |  Itens exibidos: –")
        root.addWidget(self.lblTotais)

        sb = QStatusBar()
        self.setStatusBar(sb)

        self.setStyleSheet("""
            QMainWindow { background:#EAF2FC; }
            QGroupBox { background:white; border:1px solid #dbe5ff; border-radius:10px; margin-top:10px; }
            QGroupBox::title { subcontrol-origin: margin; left:12px; padding:0 6px; background:#EAF2FC; }
            QPushButton { padding:8px 14px; background:white; border:1px solid #d7e3ff; border-radius:8px; }
            QPushButton:hover { background:#f6faff; }
            QLineEdit, QSpinBox, QDateEdit { background:white; border:1px solid #cfdaf5; border-radius:6px; padding:6px 10px; }
            QTableWidget { background:white; border:1px solid #cfdaf5; border-radius:6px; gridline-color:#e3ecff; }
        """)

        self._build_menu()

        # Layout
        self.settings = QSettings("SmartGest", "Inventario")
        self._restore_layout()

        # carga inicial
        QTimer.singleShot(150, self._run_search)

    # ---------- Cursor ----------
    def _set_busy(self, busy: bool):
        if busy and not self._cursor_wait_on:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self._cursor_wait_on = True
        elif not busy and self._cursor_wait_on:
            QApplication.restoreOverrideCursor()
            self._cursor_wait_on = False

    # ---------- Menu ----------
    def _build_menu(self):
        mb = self.menuBar()
        mA = mb.addMenu("&Ações")

        aSave = QAction("Salvar (Ctrl+S)", self)
        aSave.setShortcut("Ctrl+S")
        aSave.triggered.connect(self._salvar)

        aPDF = QAction("Exportar PDF (Ctrl+P)", self)
        aPDF.setShortcut("Ctrl+P")
        aPDF.triggered.connect(self._export_pdf)

        aXLS = QAction("Exportar Excel (Ctrl+E)", self)
        aXLS.setShortcut("Ctrl+E")
        aXLS.triggered.connect(self._export_excel)

        aBack = QAction("Voltar (Esc)", self)
        aBack.setShortcut("Esc")
        aBack.triggered.connect(self.close)

        for a in (aSave, aPDF, aXLS, aBack):
            mA.addAction(a)

    # ---------- Tabela ----------
    def _setup_table(self, t: QTableWidget):
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.setAlternatingRowColors(True)
        t.verticalHeader().setVisible(False)

        hdr = t.horizontalHeader()
        hdr.setSectionsMovable(True)
        hdr.setSectionResizeMode(QHeaderView.Interactive)

        t.setSortingEnabled(True)

        widths = [38, 150, 520, 110, 160, 140, 200]
        for i, w in enumerate(widths):
            t.setColumnWidth(i, w)

        t.doubleClicked.connect(self._pick_to_form)
        t.itemChanged.connect(self._on_item_changed)

        t.setContextMenuPolicy(Qt.CustomContextMenu)
        t.customContextMenuRequested.connect(self._context_menu)

    def _context_menu(self, pos):
        r = self.table.rowAt(pos.y())
        if r < 0:
            return
        item_chk = self.table.item(r, 0)
        if not item_chk:
            return
        new_state = Qt.Unchecked if item_chk.checkState() == Qt.Checked else Qt.Checked
        self._set_row_checked(r, new_state)

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._filling or self._changing_checks:
            return
        if item.column() != 0:
            return
        self._update_selection_stats()

    # ---------- Lookups ----------
    def _lookup_familia(self):
        cod = self.edFamilia.text().strip().upper()
        if not cod:
            self.edFamiliaNome.setText("")
            self._debounce.start(200)
            return
        try:
            self.cursor.execute("SELECT nome FROM familias WHERE codigo=%s", (cod,))
            row = self.cursor.fetchone()
            self.edFamiliaNome.setText("" if not row else (row[0] or "").upper())
        except DatabaseError as e:
            _err(self, "Família", f"Erro ao buscar família.\n\n{e}")
            return
        self._debounce.start(250)

    def _lookup_peca(self):
        cod = self.edPeca.text().strip().upper()
        if not cod:
            self.edPecaNome.setText("")
            self._debounce.start(200)
            return
        try:
            self.cursor.execute("SELECT descricao FROM produtos WHERE UPPER(codigo)=%s", (cod,))
            row = self.cursor.fetchone()
            self.edPecaNome.setText("" if not row else (row[0] or "").upper())
        except DatabaseError as e:
            _err(self, "Peça", f"Erro ao buscar peça.\n\n{e}")
            return
        self._debounce.start(250)

    def _lookup_func(self):
        cod = self.edFunc.text().strip().upper()
        if not cod:
            self.edFuncNome.setText("")
            return
        try:
            self.cursor.execute("SELECT nome FROM tecnico WHERE UPPER(codigo)=%s", (cod,))
            row = self.cursor.fetchone()
            self.edFuncNome.setText("" if not row else (row[0] or "").upper())
        except DatabaseError as e:
            _err(self, "Funcionário", f"Erro ao buscar funcionário.\n\n{e}")

    # ---------- SQL ----------
    def _sql_for_list(self):
        fam = self.edFamilia.text().strip().upper()
        peca = self.edPeca.text().strip().upper()
        quick = self.edBusca.text().strip().upper()

        qdate = self.dtCorte.date()
        data_corte = datetime(qdate.year(), qdate.month(), qdate.day())

        sub = """
            SELECT codigo, MAX(data_movimentacao) AS ultima_movimentacao, MAX(funcionario) AS funcionario
            FROM historico_movimentacoes
            GROUP BY codigo
        """

        sql = f"""
            SELECT
                p.codigo,
                p.descricao,
                COALESCE(p.saldo,0),
                COALESCE(p.local,''),
                h.ultima_movimentacao,
                h.funcionario
            FROM produtos p
            LEFT JOIN ({sub}) h ON p.codigo = h.codigo
            WHERE 1=1
        """
        params = []

        if fam:
            sql += " AND UPPER(p.codigo) LIKE %s"
            params.append(fam + "%")

        if peca:
            sql += " AND UPPER(p.codigo) LIKE %s"
            params.append(f"%{peca}%")

        if quick:
            sql += " AND (UPPER(p.codigo) LIKE %s OR UPPER(p.descricao) LIKE %s)"
            params.extend([f"%{quick}%", f"%{quick}%"])

        if (not self.chkTodas.isChecked()) and self.chkCorteOuSem.isChecked():
            sql += " AND (p.local IS NULL OR p.local='' OR h.ultima_movimentacao <= %s)"
            params.append(data_corte)

        sql += " ORDER BY p.descricao"
        return sql, tuple(params)

    # ---------- Infra thread ----------
    def _thread_running(self):
        return (
            self._fetch_thread is not None
            and shiboken6.isValid(self._fetch_thread)
            and self._fetch_thread.isRunning()
        )

    def _cancel_running_fetch(self):
        if self._fetch_worker and shiboken6.isValid(self._fetch_worker):
            try:
                self._fetch_worker.cancel()
            except Exception:
                pass

        if self._fetch_thread and shiboken6.isValid(self._fetch_thread):
            try:
                self._fetch_thread.requestInterruption()
                self._fetch_thread.quit()
            except Exception:
                pass

    # ---------- Busca assíncrona segura ----------
    def _run_search(self):
        if self._closing:
            return

        # se já existe uma consulta em andamento, marca pendente e cancela a atual
        if self._thread_running():
            self._pending_search = True
            self.statusBar().showMessage("Atualizando consulta…")
            self._cancel_running_fetch()
            return

        sql, params = self._sql_for_list()
        self._req_id += 1
        req_id = self._req_id

        self._pending_search = False
        self._set_busy(True)
        self.statusBar().showMessage("Carregando…")

        thread = QThread(self)
        worker = FetchWorker(req_id, sql, params)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_fetch_ok)
        worker.failed.connect(self._on_fetch_fail)

        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)

        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_fetch_thread_finished)

        self._fetch_thread = thread
        self._fetch_worker = worker

        thread.start()

    def _on_fetch_thread_finished(self):
        self._fetch_thread = None
        self._fetch_worker = None
        self._set_busy(False)

        if self._closing:
            return

        if self._pending_search:
            self._pending_search = False
            QTimer.singleShot(0, self._run_search)

    def _on_fetch_ok(self, req_id: int, rows: list):
        if self._closing:
            return

        if req_id != self._req_id:
            return

        self._filling = True
        sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        total_pecas = 0

        qd = self.dtCorte.date()
        data_corte = datetime(qd.year(), qd.month(), qd.day())

        for (codigo, desc, saldo, local, ult, func) in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)

            chk = QTableWidgetItem("")
            chk.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
            chk.setCheckState(Qt.Unchecked)
            chk.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 0, chk)

            vals = [
                str(codigo).upper(),
                str(desc or "").upper(),
                str(saldo),
                str(local or "").upper(),
                (ult.strftime("%d/%m/%Y") if ult else "N/A"),
                str(func or "")
            ]

            for c, v in enumerate(vals, start=1):
                it = QTableWidgetItem(v)

                if c == 3:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                else:
                    it.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

                if c == 1 and ult and ult > data_corte:
                    it.setBackground(Qt.lightGray)

                if c == 3:
                    try:
                        if int(v) == 0:
                            it.setBackground(Qt.yellow)
                    except Exception:
                        pass

                self.table.setItem(r, c, it)

            try:
                total_pecas += int(saldo or 0)
            except Exception:
                pass

        self.table.setSortingEnabled(sorting)
        self._filling = False

        self._update_selection_stats()
        self.lblTotais.setText(f"Total de peças: {total_pecas}  |  Itens exibidos: {len(rows)}")
        self.statusBar().showMessage(f"{len(rows)} linhas.", 1500)

    def _on_fetch_fail(self, req_id: int, err: str):
        if self._closing:
            return
        if req_id != self._req_id:
            return
        _err(self, "Consulta", f"Erro ao carregar lista.\n\n{err}")

    # ---------- Seleção ----------
    def _set_row_checked(self, row: int, state: Qt.CheckState):
        item = self.table.item(row, 0)
        if not item:
            return
        self._changing_checks = True
        item.setCheckState(state)
        self._changing_checks = False
        self._update_selection_stats()

    def _toggle_all_visible(self, state: int):
        self._changing_checks = True
        chk = Qt.Checked if state == Qt.Checked else Qt.Unchecked
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it:
                it.setCheckState(chk)
        self._changing_checks = False
        self._update_selection_stats()

    def _invert_checks(self):
        self._changing_checks = True
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it:
                it.setCheckState(Qt.Unchecked if it.checkState() == Qt.Checked else Qt.Checked)
        self._changing_checks = False
        self._update_selection_stats()

    def _mark_saldo_zero(self):
        self._changing_checks = True
        for r in range(self.table.rowCount()):
            saldo_item = self.table.item(r, 3)
            chk = self.table.item(r, 0)
            if saldo_item and chk:
                try:
                    if int(saldo_item.text()) == 0:
                        chk.setCheckState(Qt.Checked)
                except Exception:
                    pass
        self._changing_checks = False
        self._update_selection_stats()

    def _mark_sem_prateleira(self):
        self._changing_checks = True
        for r in range(self.table.rowCount()):
            loc_item = self.table.item(r, 4)
            chk = self.table.item(r, 0)
            if loc_item and chk:
                if not loc_item.text().strip():
                    chk.setCheckState(Qt.Checked)
        self._changing_checks = False
        self._update_selection_stats()

    def _checked_rows(self):
        out = []
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it and it.checkState() == Qt.Checked:
                vals = [
                    self.table.item(r, c).text() if self.table.item(r, c) else ""
                    for c in range(1, len(COLS_VIEW))
                ]
                out.append(tuple(vals))
        return out

    def _update_selection_stats(self):
        rows = self._checked_rows()
        total_sel = 0
        for tup in rows:
            try:
                total_sel += int(tup[2])
            except Exception:
                pass

        self.lblSel.setText(f"Selecionados: {len(rows)}  |  Saldo selecionado: {total_sel}")

        if self.table.rowCount() == 0:
            st = Qt.Unchecked
        else:
            checked = sum(
                1 for r in range(self.table.rowCount())
                if self.table.item(r, 0) and self.table.item(r, 0).checkState() == Qt.Checked
            )
            st = Qt.Checked if checked == self.table.rowCount() else (
                Qt.Unchecked if checked == 0 else Qt.PartiallyChecked
            )

        self.chkMarcarTodos.blockSignals(True)
        self.chkMarcarTodos.setCheckState(st)
        self.chkMarcarTodos.blockSignals(False)

    # ---------- Salvar ----------
    def _salvar(self):
        codigo = self.edPeca.text().strip().upper()
        nome = self.edPecaNome.text().strip().upper()
        func = self.edFunc.text().strip().upper()
        funcnm = self.edFuncNome.text().strip().upper()
        qtd = int(self.spQtd.value())
        local = self.edLocal.text().strip().upper()

        if not codigo or not func:
            _err(self, "Validação", "Informe Código da Peça e Código do Funcionário.")
            return

        try:
            self.cursor.execute(
                "UPDATE produtos SET saldo=%s, local=%s WHERE UPPER(codigo)=%s",
                (qtd, local, codigo)
            )
            self.conn.commit()

            self.cursor.execute("""
                INSERT INTO historico_movimentacoes
                (codigo, nome, data_movimentacao, tipo_movimentacao, quantidade_movimentada, maquina, funcionario)
                VALUES (%s, %s, CURRENT_TIMESTAMP, %s, %s, %s, %s)
            """, (codigo, nome, "INVENTARIO", qtd, local, (funcnm or func)))
            self.conn.commit()

        except DatabaseError as e:
            self.conn.rollback()
            _err(self, "Inventário", f"Não foi possível salvar.\n\n{e}")
            return

        self.statusBar().showMessage("Inventário salvo.", 1500)
        self._run_search()

    # ---------- Export PDF ----------
    def _export_pdf(self):
        if not _HAS_REPORTLAB:
            _err(self, "Exportar PDF", "Biblioteca 'reportlab' não encontrada.\nInstale: pip install reportlab")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Salvar PDF", "inventario.pdf", "PDF (*.pdf)")
        if not path:
            return

        rows = self._checked_rows()
        if not rows:
            sql, params = self._sql_for_list()
            try:
                self.cursor.execute(sql, params)
                rows = [
                    (
                        str(c).upper(),
                        str(d or "").upper(),
                        str(s),
                        str(l or "").upper(),
                        (u.strftime("%d/%m/%Y") if u else "N/A"),
                        str(f or "")
                    )
                    for (c, d, s, l, u, f) in self.cursor.fetchall()
                ]
            except DatabaseError as e:
                _err(self, "Exportar PDF", f"Erro na consulta para exportação.\n\n{e}")
                return

            if not rows:
                _err(self, "Exportar PDF", "Nada para exportar.")
                return

        try:
            c = canvas.Canvas(path, pagesize=landscape(letter))
            W, H = landscape(letter)
            c.setFont("Helvetica", 10)
            x0, y = 40, H - 40
            row_h = 18
            w = dict(cod=120, desc=360, saldo=70, loc=140, ult=100, func=180)

            def hdr():
                c.drawString(x0, y, "Código")
                c.drawString(x0 + w["cod"], y, "Descrição")
                c.drawString(x0 + w["cod"] + w["desc"], y, "Saldo")
                c.drawString(x0 + w["cod"] + w["desc"] + w["saldo"], y, "Prateleira")
                c.drawString(x0 + w["cod"] + w["desc"] + w["saldo"] + w["loc"], y, "Última Mov.")
                c.drawString(x0 + w["cod"] + w["desc"] + w["saldo"] + w["loc"] + w["ult"], y, "Funcionário")

            hdr()
            y -= row_h
            n = 0

            for (codigo, desc, saldo, local, ult, func) in rows:
                if n and n % 28 == 0:
                    c.showPage()
                    c.setFont("Helvetica", 10)
                    y = H - 40
                    hdr()
                    y -= row_h

                txt = str(desc or "")
                while c.stringWidth(txt, "Helvetica", 10) > (w["desc"] - 10) and len(txt) > 0:
                    txt = txt[:-1]
                if txt != str(desc or ""):
                    txt += "…"

                c.drawString(x0, y, str(codigo))
                c.drawString(x0 + w["cod"], y, txt)
                c.drawRightString(x0 + w["cod"] + w["desc"] + w["saldo"] - 6, y, str(saldo))
                c.drawString(x0 + w["cod"] + w["desc"] + w["saldo"], y, str(local))
                c.drawString(x0 + w["cod"] + w["desc"] + w["saldo"] + w["loc"], y, str(ult))
                c.drawString(x0 + w["cod"] + w["desc"] + w["saldo"] + w["loc"] + w["ult"], y, str(func))

                y -= row_h
                n += 1

            c.save()

        except Exception as e:
            _err(self, "Exportar PDF", f"Falhou ao exportar.\n\n{e}")
            return

        self.statusBar().showMessage("PDF exportado.", 2000)

    # ---------- Export Excel ----------
    def _export_excel(self):
        if not _HAS_PANDAS:
            _err(self, "Exportar Excel", "Biblioteca 'pandas' não encontrada.\nInstale: pip install pandas openpyxl")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Salvar Excel", "inventario.xlsx", "Excel (*.xlsx)")
        if not path:
            return

        rows = self._checked_rows()
        if not rows:
            sql, params = self._sql_for_list()
            try:
                self.cursor.execute(sql, params)
                rows = [
                    (
                        str(c).upper(),
                        str(d or "").upper(),
                        str(s),
                        str(l or "").upper(),
                        (u.strftime("%d/%m/%Y") if u else "N/A"),
                        str(f or "")
                    )
                    for (c, d, s, l, u, f) in self.cursor.fetchall()
                ]
            except DatabaseError as e:
                _err(self, "Exportar Excel", f"Erro na consulta para exportação.\n\n{e}")
                return

            if not rows:
                _err(self, "Exportar Excel", "Nada para exportar.")
                return

        try:
            df = pd.DataFrame(rows, columns=list(COLS_BASE))
            df.to_excel(path, index=False)
        except Exception as e:
            _err(self, "Exportar Excel", f"Falhou ao exportar.\n\n{e}")
            return

        self.statusBar().showMessage("Excel exportado.", 2000)

    # ---------- Helpers ----------
    def _pick_to_form(self, *_args):
        r = self.table.currentRow()
        if r < 0:
            return

        codigo_item = self.table.item(r, 1)
        saldo_item = self.table.item(r, 3)
        local_item = self.table.item(r, 4)

        codigo = codigo_item.text() if codigo_item else ""
        saldo = saldo_item.text() if saldo_item else "0"
        local = local_item.text() if local_item else ""

        self.edPeca.setText(codigo)
        self._lookup_peca()

        try:
            self.spQtd.setValue(int(saldo))
        except Exception:
            self.spQtd.setValue(0)

        self.edLocal.setText(local)
        self.spQtd.setFocus()

    def _limpar_form(self):
        for w in (self.edPeca, self.edPecaNome, self.edFunc, self.edFuncNome, self.edLocal):
            w.setText("")
        self.spQtd.setValue(0)
        self.statusBar().clearMessage()

    # ---------- Layout ----------
    def _restore_layout(self):
        g = self.settings.value("window/geometry", None)
        if isinstance(g, QByteArray):
            self.restoreGeometry(g)

        hs = self.settings.value("table/header", None)
        if isinstance(hs, QByteArray):
            self.table.horizontalHeader().restoreState(hs)

    def _save_layout(self):
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("table/header", self.table.horizontalHeader().saveState())

    # ---------- Fechamento ----------
    def closeEvent(self, e):
        self._closing = True
        self._save_layout()

        try:
            self._cancel_running_fetch()
        except Exception:
            pass

        try:
            if hasattr(self, "cursor") and self.cursor:
                self.cursor.close()
        except Exception:
            pass

        try:
            if hasattr(self, "conn") and self.conn:
                self.conn.close()
        except Exception:
            pass

        self._set_busy(False)

        p = self.parent()
        if p and hasattr(p, "show"):
            try:
                p.show()
                p.raise_()
                p.activateWindow()
            except Exception:
                pass

        super().closeEvent(e)


# --------- função para o launcher ----------
def abrir(parent=None):
    win = InventarioApp(parent)
    win.showMaximized()
    return win


# --------- standalone ----------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = InventarioApp()
    w.showMaximized()
    sys.exit(app.exec())