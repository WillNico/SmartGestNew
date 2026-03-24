# estoque_adm.py - PySide6
# Requisitos:
#   pip install PySide6 psycopg2-binary reportlab pandas openpyxl
from __future__ import annotations
import sys
import importlib
import random
from datetime import datetime

import psycopg2
from psycopg2 import OperationalError, DatabaseError

from PySide6.QtCore import Qt, QTimer, QObject, Signal, QThread
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QFileDialog, QStatusBar, QMessageBox, QDialog, QFormLayout,
    QDoubleSpinBox
)

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

APP_TITLE = "Visão Geral do Estoque (Adm)"
COLS = ("Código", "Descrição", "Saldo", "Valor Unit.", "Local")

DB_KW = dict(dbname="Almoxarifado", user="Ti", password="jj00tt", host="10.2.149.7")

def _err(self, title, msg):
    QMessageBox.critical(self, title, msg)
class NumericTableWidgetItem(QTableWidgetItem):
    def __init__(self, value):
        super().__init__(self._format_value(value))
        try:
            self.numeric_value = float(value)
        except Exception:
            self.numeric_value = 0.0

    def __lt__(self, other):
        if isinstance(other, NumericTableWidgetItem):
            return self.numeric_value < other.numeric_value
        try:
            return self.numeric_value < float(other.text().replace(",", "."))
        except Exception:
            return super().__lt__(other)

    @staticmethod
    def _format_value(value):
        if value is None:
            return ""
        return str(value)
# ---------------- Worker p/ busca assíncrona ----------------
class FetchWorker(QObject):
    finished = Signal(int, list)
    failed = Signal(int, str)

    def __init__(self, req_id: int, term: str):
        super().__init__()
        self.req_id = req_id
        self.term = term


    def run(self):
        conn = None
        cur = None
        try:
            conn = psycopg2.connect(**DB_KW)
            cur = conn.cursor()

            sql = """
                SELECT UPPER(codigo), UPPER(descricao), COALESCE(saldo,0),
                       COALESCE(valor_un,0), UPPER(COALESCE(local,''))
                FROM produtos
                WHERE 1=1
            """
            params = []
            t = (self.term or "").strip().upper()

            if t:
                sql += " AND (UPPER(codigo) LIKE %s OR UPPER(descricao) LIKE %s)"
                params.extend([f"%{t}%", f"%{t}%"])

            sql += " ORDER BY descricao LIMIT 500"

            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
            self.finished.emit(self.req_id, rows)

        except Exception as e:
            self.failed.emit(self.req_id, str(e))

        finally:
            try:
                if cur:
                    cur.close()
            except Exception:
                pass
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

# ---------------- Diálogo de edição ----------------
class EditDialog(QDialog):
    def __init__(self, parent, codigo: str, descricao: str, valor_un: float, local: str):
        super().__init__(parent)
        self.setWindowTitle("Editar Prateleira e Preço")
        self.resize(420, 220)
        lay = QVBoxLayout(self)

        formW = QWidget(self); form = QFormLayout(formW)
        self.edCod  = QLineEdit(codigo);   self.edCod.setReadOnly(True)
        self.edDesc = QLineEdit(descricao);self.edDesc.setReadOnly(True)
        self.spVal  = QDoubleSpinBox(); self.spVal.setRange(0.0, 999999999.0); self.spVal.setDecimals(4); self.spVal.setValue(float(valor_un or 0.0))
        self.edLoc  = QLineEdit(local)

        form.addRow("Código:", self.edCod)
        form.addRow("Descrição:", self.edDesc)
        form.addRow("Valor Unitário:", self.spVal)
        form.addRow("Local:", self.edLoc)
        lay.addWidget(formW)

        rowB = QWidget(self); hb = QHBoxLayout(rowB); hb.setContentsMargins(0,0,0,0)
        btOk = QPushButton("Salvar"); btOk.clicked.connect(self.accept)
        btCancel = QPushButton("Cancelar"); btCancel.clicked.connect(self.reject)
        hb.addStretch(); hb.addWidget(btOk); hb.addWidget(btCancel)
        lay.addWidget(rowB)

    def values(self):
        return self.edCod.text(), self.edDesc.text(), float(self.spVal.value()), self.edLoc.text().strip().upper()
from shiboken6 import isValid
# ---------------- Janela principal ----------------
class EstoqueAdmApp(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 800)

        # DB persistente
        try:
            self.conn = psycopg2.connect(**DB_KW)
            self.cursor = self.conn.cursor()
        except OperationalError as e:
            _err(self, "Banco de Dados", f"Falha na conexão com PostgreSQL.\n\n{e}")
            self.close(); return

        # UI
        central = QWidget(self); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(14,10,14,10); root.setSpacing(10)

        title = QLabel(APP_TITLE); title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        root.addWidget(title)

        # barra superior
        bar = QWidget(self); hb = QHBoxLayout(bar); hb.setContentsMargins(0,0,0,0)
        lb = QLabel("Nome ou Código:"); self.edBusca = QLineEdit(); self.edBusca.setPlaceholderText("Digite e solte — busca automática")
        self.edBusca.textChanged.connect(self._debounce_search)
        self.edBusca.returnPressed.connect(self._run_search)
        btCad = QPushButton("Cadastro de Peça"); btCad.clicked.connect(self._open_cadastro)
        btInv = QPushButton("Inventário"); btInv.clicked.connect(self._open_inventario)
        btPDF = QPushButton("Exportar PDF"); btPDF.clicked.connect(lambda: self._export_pdf(selected=False))
        btPDFSel = QPushButton("PDF Selecionados"); btPDFSel.clicked.connect(lambda: self._export_pdf(selected=True))
        btXLS = QPushButton("Exportar Excel"); btXLS.clicked.connect(lambda: self._export_excel(selected=False))
        btXLSSel = QPushButton("Excel Selecionados"); btXLSSel.clicked.connect(lambda: self._export_excel(selected=True))
        btPick = QPushButton("10 Aleatórios"); btPick.clicked.connect(self._selecionar_10_aleatorios)
        btEdit = QPushButton("Editar Prateleira e Preço"); btEdit.clicked.connect(self._editar_prateleira_preco)
        btVoltar = QPushButton("Voltar"); btVoltar.clicked.connect(self.close)

        for b in (btCad, btInv, btPDF, btPDFSel, btXLS, btXLSSel, btPick, btEdit):
            b.setMinimumWidth(150)

        hb.addWidget(lb); hb.addWidget(self.edBusca, 1); hb.addSpacing(8)
        hb.addWidget(btCad); hb.addWidget(btInv); hb.addWidget(btPDF); hb.addWidget(btPDFSel)
        hb.addWidget(btXLS); hb.addWidget(btXLSSel); hb.addWidget(btPick); hb.addWidget(btEdit)
        hb.addStretch(); hb.addWidget(btVoltar)
        root.addWidget(bar)

        # tabela
        self.table = QTableWidget(self)
        self.table.setColumnCount(len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self._setup_table(self.table)
        root.addWidget(self.table, 1)

        # stats
        self.lblStats = QLabel("Saldo Total: –  |  Itens: –")
        self.lblValor = QLabel("Valor Total: –")
        root.addWidget(self.lblStats); root.addWidget(self.lblValor)

        # status
        sb = QStatusBar(); self.setStatusBar(sb)

        # estilo
        self.setStyleSheet("""
            QMainWindow { background: #E8F1FB; }
            QPushButton { padding:8px 14px; background: white; border:1px solid #d7e3ff; border-radius:8px; }
            QPushButton:hover { background: #f6faff; }
            QLineEdit { background:white; border:1px solid #cfdaf5; border-radius:6px; padding:6px 10px; }
            QTableWidget { background: white; border:1px solid #cfdaf5; border-radius:6px; gridline-color:#e3ecff; }
        """)

        # menu/atalhos
        self._build_menu()

        # debounce e worker control
        self._debounce = QTimer(self); self._debounce.setSingleShot(True); self._debounce.timeout.connect(self._run_search)
        self._req_id = 0
        self._fetch_thread: QThread | None = None
        self._fetch_worker: FetchWorker | None = None

        # primeira carga
        QTimer.singleShot(100, self._run_search)

    # ---------- menu ----------
    def _build_menu(self):
        mb = self.menuBar()
        mA = mb.addMenu("&Ações")
        actSearch = QAction("Buscar (Enter)", self); actSearch.triggered.connect(self._run_search)
        actPDF    = QAction("Exportar PDF (Ctrl+P)", self); actPDF.setShortcut("Ctrl+P"); actPDF.triggered.connect(lambda: self._export_pdf(False))
        actXLS    = QAction("Exportar Excel (Ctrl+E)", self); actXLS.setShortcut("Ctrl+E"); actXLS.triggered.connect(lambda: self._export_excel(False))
        actCad    = QAction("Cadastro (Ctrl+D)", self); actCad.setShortcut("Ctrl+D"); actCad.triggered.connect(self._open_cadastro)
        actInv    = QAction("Inventário (Ctrl+I)", self); actInv.setShortcut("Ctrl+I"); actInv.triggered.connect(self._open_inventario)
        actEdit   = QAction("Editar (Ctrl+Shift+E)", self); actEdit.setShortcut("Ctrl+Shift+E"); actEdit.triggered.connect(self._editar_prateleira_preco)
        actPick   = QAction("Selecionar 10 (Ctrl+L)", self); actPick.setShortcut("Ctrl+L"); actPick.triggered.connect(self._selecionar_10_aleatorios)
        actBack   = QAction("Voltar (Esc)", self); actBack.setShortcut("Esc"); actBack.triggered.connect(self.close)
        for a in (actSearch, actPDF, actXLS, actCad, actInv, actEdit, actPick, actBack): mA.addAction(a)

    # ---------- tabela ----------
    def _setup_table(self, t: QTableWidget):
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.ExtendedSelection)
        t.setAlternatingRowColors(True)
        t.verticalHeader().setVisible(False)
        hdr = t.horizontalHeader()
        hdr.setSectionsMovable(True)
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        t.setSortingEnabled(True)
        widths = [150, 520, 120, 120, 160]
        for i, w in enumerate(widths): t.setColumnWidth(i, w)

    # ---------- debounce ----------
    def _debounce_search(self):
        self._debounce.start(250)

    # ---------- helper: SQL do filtro atual ----------
    def _sql_for_filter(self, *, full: bool):
        """
        full=False -> mesma query da UI (rápida, com LIMIT)
        full=True  -> mesma query porém SEM LIMIT (p/ exportar tudo)
        """
        term = (self.edBusca.text() or "").strip().upper()
        sql = """
            SELECT UPPER(codigo), UPPER(descricao), COALESCE(saldo,0), COALESCE(valor_un,0), UPPER(COALESCE(local,''))
            FROM produtos
            WHERE 1=1
        """
        params = []
        if term:
            sql += " AND (UPPER(codigo) LIKE %s OR UPPER(descricao) LIKE %s)"
            params.extend([f"%{term}%", f"%{term}%"])
        sql += " ORDER BY descricao"
        if not full:
            sql += " LIMIT 500"
        return sql, tuple(params)

    # ---------- busca ----------
    def _run_search(self):
        self.statusBar().showMessage("Carregando…", 1000)
        self._req_id += 1
        req_id = self._req_id

        # encerra thread anterior com segurança
        if self._fetch_thread is not None:
            try:
                if isValid(self._fetch_thread) and self._fetch_thread.isRunning():
                    self._fetch_thread.quit()
                    self._fetch_thread.wait(300)
            except RuntimeError:
                pass
            finally:
                self._fetch_thread = None
                self._fetch_worker = None

        # limpa tabela antes da nova carga
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        # cria nova thread
        thread = QThread(self)
        worker = FetchWorker(req_id, self.edBusca.text())

        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_fetch_ok)
        worker.failed.connect(self._on_fetch_fail)

        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)

        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)

        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_fetch_refs)

        self._fetch_thread = thread
        self._fetch_worker = worker

        thread.start()

    def _on_fetch_ok(self, req_id: int, rows: list):
        if req_id != self._req_id:
            return
    
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
    
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
    
            for c, val in enumerate(r):
                if c in (2, 3):  # saldo e valor unitário
                    item = NumericTableWidgetItem(val)
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                else:
                    txt = "" if val is None else str(val)
                    item = QTableWidgetItem(txt)
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    
                self.table.setItem(row, c, item)
    
        self.table.setSortingEnabled(True)
        self._update_stats()
        self.statusBar().showMessage(f"{len(rows)} registros carregados.", 1500)

    def _on_fetch_fail(self, req_id: int, err: str):
        if req_id != self._req_id: return
        _err(self, "Busca", f"Erro ao carregar dados.\n\n{err}")

    # ---------- stats ----------
    def _update_stats(self):
        try:
            self.cursor.execute("SELECT COALESCE(SUM(saldo),0), COUNT(*), COALESCE(SUM(saldo*COALESCE(valor_un,0)),0) FROM produtos")
            total, cnt, valor = self.cursor.fetchone()
        except DatabaseError as e:
            _err(self, "Estatísticas", f"Não foi possível obter as estatísticas.\n\n{e}")
            return
        self.lblStats.setText(f"Saldo Total: {int(total):,}  |  Itens: {cnt}".replace(",", "."))
        self.lblValor.setText(f"Valor Total: R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))


    def _clear_fetch_refs(self):
        self._fetch_thread = None
        self._fetch_worker = None

    # ---------- exportações (agora puxam TUDO do banco quando não for 'selecionados') ----------
    def _export_pdf(self, selected: bool):
        if not _HAS_REPORTLAB:
            _err(self, "Exportar PDF", "Biblioteca 'reportlab' não encontrada.\nInstale: pip install reportlab")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Salvar PDF", "estoque_adm.pdf", "PDF (*.pdf)")
        if not path: return

        # coleta dados
        if selected:
            rows = []
            idxs = self.table.selectionModel().selectedRows()
            for i in idxs:
                rows.append([self.table.item(i.row(), c).text() if self.table.item(i.row(), c) else "" for c in range(5)])
        else:
            # pega do banco com MESMO filtro e SEM LIMIT
            sql, params = self._sql_for_filter(full=True)
            try:
                self.cursor.execute(sql, params)
                rows = self.cursor.fetchall()
            except DatabaseError as e:
                _err(self, "Exportar PDF", f"Erro na consulta para exportação.\n\n{e}")
                return

        if not rows:
            _err(self, "Exportar PDF", "Nada para exportar.")
            return

        try:
            c = canvas.Canvas(path, pagesize=landscape(letter))
            width, height = landscape(letter)
            c.setFont("Helvetica", 10)
            x0, y = 40, height - 40
            row_h = 18
            w_cod, w_desc, w_saldo, w_val, w_loc = 120, 360, 80, 90, 140

            def hdr():
                c.drawString(x0, y, "Código")
                c.drawString(x0 + w_cod, y, "Descrição")
                c.drawString(x0 + w_cod + w_desc, y, "Saldo")
                c.drawString(x0 + w_cod + w_desc + w_saldo, y, "Valor Unit.")
                c.drawString(x0 + w_cod + w_desc + w_saldo + w_val, y, "Local")

            hdr(); y -= row_h
            n = 0
            for r in rows:
                if n and n % 28 == 0:
                    c.showPage(); c.setFont("Helvetica", 10)
                    y = height - 40; hdr(); y -= row_h
                # r pode vir como tupla do DB ou lista da tabela
                r = list(r)
                desc = str(r[1])
                maxw = w_desc - 10
                while c.stringWidth(desc, "Helvetica", 10) > maxw and len(desc) > 0:
                    desc = desc[:-1]
                if desc != str(r[1]): desc += "…"
                c.drawString(x0, y, str(r[0]))
                c.drawString(x0 + w_cod, y, desc)
                c.drawRightString(x0 + w_cod + w_desc + w_saldo - 6, y, str(r[2]))
                c.drawRightString(x0 + w_cod + w_desc + w_saldo + w_val - 6, y, str(r[3]))
                c.drawString(x0 + w_cod + w_desc + w_saldo + w_val, y, str(r[4]))
                y -= row_h; n += 1
            c.save()
        except Exception as e:
            _err(self, "Exportar PDF", f"Falhou ao exportar.\n\n{e}")
            return

        self.statusBar().showMessage("PDF exportado (completo).", 2000)

    def _export_excel(self, selected: bool):
        if not _HAS_PANDAS:
            _err(self, "Exportar Excel", "Biblioteca 'pandas' não encontrada.\nInstale: pip install pandas openpyxl")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Salvar Excel", "estoque_adm.xlsx", "Excel (*.xlsx)")
        if not path: return

        if selected:
            rows = []
            idxs = self.table.selectionModel().selectedRows()
            for i in idxs:
                rows.append([self.table.item(i.row(), c).text() if self.table.item(i.row(), c) else "" for c in range(5)])
        else:
            sql, params = self._sql_for_filter(full=True)
            try:
                self.cursor.execute(sql, params)
                rows = self.cursor.fetchall()
            except DatabaseError as e:
                _err(self, "Exportar Excel", f"Erro na consulta para exportação.\n\n{e}")
                return

        if not rows:
            _err(self, "Exportar Excel", "Nada para exportar.")
            return

        try:
            df = pd.DataFrame(rows, columns=list(COLS))
            df.to_excel(path, index=False)
        except Exception as e:
            _err(self, "Exportar Excel", f"Falhou ao exportar.\n\n{e}")
            return

        self.statusBar().showMessage("Excel exportado (completo).", 2000)

    # ---------- seleção aleatória ----------
    def _selecionar_10_aleatorios(self):
        total = self.table.rowCount()
        if total < 10:
            _err(self, "Selecionar 10", "Menos de 10 peças na lista.")
            return
        rows = list(range(total))
        pick = random.sample(rows, 10)
        self.table.clearSelection()
        for r in pick: self.table.selectRow(r)
        self.statusBar().showMessage("10 itens selecionados.", 1500)

    # ---------- edição ----------
    def _editar_prateleira_preco(self):
        row = self.table.currentRow()
        if row < 0:
            _err(self, "Editar", "Selecione uma linha.")
            return
        codigo = self.table.item(row, 0).text()
        descricao = self.table.item(row, 1).text()
        try:
            valor_un = float(self.table.item(row, 3).text().replace(",", "."))
        except Exception:
            valor_un = 0.0
        local = self.table.item(row, 4).text()

        dlg = EditDialog(self, codigo, descricao, valor_un, local)
        if not dlg.exec(): return
        codigo, descricao, novo_valor, novo_local = dlg.values()

        try:
            self.cursor.execute(
                "UPDATE produtos SET valor_un=%s, local=%s WHERE UPPER(codigo)=%s",
                (novo_valor, novo_local, codigo.upper())
            )
            self.conn.commit()
            self.cursor.execute("""
                INSERT INTO historico_movimentacoes
                (codigo, nome, data_movimentacao, tipo_movimentacao, quantidade_movimentada, maquina, valor_unitario)
                VALUES (%s, %s, CURRENT_TIMESTAMP, %s, %s, %s, %s)
            """, (codigo.upper(), descricao, "ALTERACAO", 0, None, novo_valor))
            self.conn.commit()
        except DatabaseError as e:
            self.conn.rollback()
            _err(self, "Editar", f"Falha ao atualizar.\n\n{e}")
            return

        self.statusBar().showMessage("Atualizado.", 1500)
        self._run_search()

    # ---------- integrações ----------
    def _open_cadastro(self):
        self._open_module("cadastro")

    def _open_inventario(self):
        self._open_module("inventario")

    def _open_module(self, modname: str):
        try:
            mod = importlib.import_module(modname)
        except Exception as e:
            _err(self, "Abrir módulo", f"Não consegui importar '{modname}'.\n\n{e}")
            return
        abrir = getattr(mod, "abrir", None)
        if not callable(abrir):
            _err(self, "Abrir módulo", f"O módulo '{modname}' não expõe função abrir(parent).")
            return
        try:
            self.hide()
            child = abrir(self)
            if hasattr(child, "destroyed"):
                child.destroyed.connect(self._back_to_me)
        except Exception as e:
            self.show()
            _err(self, "Abrir módulo", f"Erro ao abrir '{modname}'.\n\n{e}")

    def _back_to_me(self, *_):
        self.show(); self.raise_(); self.activateWindow()

    # ---------- fechar ----------
    def closeEvent(self, e):
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
    win = EstoqueAdmApp(parent)
    win.showMaximized()
    return win

# --------- standalone ---------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = EstoqueAdmApp()
    w.showMaximized()
    sys.exit(app.exec())
