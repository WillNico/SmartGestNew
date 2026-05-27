# estoque.py - PySide6
# Requisitos:
#   pip install PySide6 psycopg2-binary reportlab pandas openpyxl
from __future__ import annotations
import sys
import importlib
import psycopg2
from psycopg2 import OperationalError, DatabaseError

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QFileDialog, QStatusBar, QMessageBox
)

# --- try imports para exportações (avisar bonito se faltar) ---
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

APP_TITLE = "Visão Geral do Estoque"
COLS = ("Código", "Descrição", "Saldo", "Local")
LIST_LIMIT = 1000

def _err(self, title, msg):
    QMessageBox.critical(self, title, msg)

class EstoqueApp(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 800)

        # --- DB persistente ---
        try:
            self.conn = psycopg2.connect(
                dbname="Almoxarifado", user="Ti", password="jj00tt", host="10.2.149.7"
            )
            self.cursor = self.conn.cursor()
        except OperationalError as e:
            _err(self, "Banco de Dados", f"Falha na conexão com PostgreSQL.\n\n{e}")
            self.close(); return

        # --- UI ---
        central = QWidget(self); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(14,10,14,10); root.setSpacing(10)

        title = QLabel(APP_TITLE); title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        root.addWidget(title)

        # barra de busca + botões
        rowTop = QWidget(self); ht = QHBoxLayout(rowTop); ht.setContentsMargins(0,0,0,0)
        lb = QLabel("Nome ou Código:"); self.edBusca = QLineEdit(); self.edBusca.setPlaceholderText("Digite e pressione Enter…")
        self.edBusca.returnPressed.connect(self._run_search)
        self.edBusca.textChanged.connect(self._search_debounced)
        btCad = QPushButton("Cadastro de Peça"); btCad.clicked.connect(self._open_cadastro)
        btInv = QPushButton("Inventário"); btInv.clicked.connect(self._open_inventario)
        btPDF = QPushButton("Exportar PDF"); btPDF.clicked.connect(self._export_pdf)
        btXLS = QPushButton("Exportar Excel"); btXLS.clicked.connect(self._export_excel)
        btVoltar = QPushButton("Voltar"); btVoltar.clicked.connect(self.close)
        for b in (btCad, btInv, btPDF, btXLS): b.setMinimumWidth(160)
        ht.addWidget(lb); ht.addWidget(self.edBusca, 1); ht.addSpacing(8)
        ht.addWidget(btCad); ht.addWidget(btInv); ht.addWidget(btPDF); ht.addWidget(btXLS)
        ht.addStretch(); ht.addWidget(btVoltar)
        root.addWidget(rowTop)

        # tabela
        self.table = QTableWidget(self)
        self.table.setColumnCount(len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self._setup_table(self.table)
        root.addWidget(self.table, 1)

        # stats
        self.lblStats = QLabel("Saldo Total: – , Total de Itens: –")
        root.addWidget(self.lblStats)

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

        # primeira carga (depois que tudo montou)
        QTimer.singleShot(120, self._initial_load)

        # debounce timer
        self._debounce = QTimer(self); self._debounce.setSingleShot(True); self._debounce.timeout.connect(self._run_search)

    # ---------- menu / atalhos ----------
    def _build_menu(self):
        mb = self.menuBar()
        mA = mb.addMenu("&Ações")
        actSearch = QAction("Buscar (Enter)", self); actSearch.triggered.connect(self._run_search)
        actPDF    = QAction("Exportar PDF (Ctrl+P)", self); actPDF.setShortcut("Ctrl+P"); actPDF.triggered.connect(self._export_pdf)
        actXLS    = QAction("Exportar Excel (Ctrl+E)", self); actXLS.setShortcut("Ctrl+E"); actXLS.triggered.connect(self._export_excel)
        actCad    = QAction("Cadastro (Ctrl+D)", self); actCad.setShortcut("Ctrl+D"); actCad.triggered.connect(self._open_cadastro)
        actInv    = QAction("Inventário (Ctrl+I)", self); actInv.setShortcut("Ctrl+I"); actInv.triggered.connect(self._open_inventario)
        actBack   = QAction("Voltar (Esc)", self); actBack.setShortcut("Esc"); actBack.triggered.connect(self.close)
        for a in (actSearch, actPDF, actXLS, actCad, actInv, actBack): mA.addAction(a)

    # ---------- tabela ----------
    def _setup_table(self, t: QTableWidget):
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.setAlternatingRowColors(True)
        t.verticalHeader().setVisible(False)
        hdr = t.horizontalHeader()
        hdr.setSectionsMovable(True)                      # arrastar colunas
        hdr.setSectionResizeMode(QHeaderView.Interactive) # redimensionar
        t.setSortingEnabled(True)                         # ordenar
        # larguras
        widths = [150, 500, 120, 160]
        for i, w in enumerate(widths):
            t.setColumnWidth(i, w)

    # ---------- carregamento ----------
    def _initial_load(self):
        self._run_search()

    def _search_debounced(self):
        # 250ms após parar de digitar
        self._debounce.start(250)

    def _sql_for_filter(self, *, full: bool):
        termo = (self.edBusca.text() or "").strip().upper()
        sql = """
            SELECT UPPER(codigo), UPPER(descricao), COALESCE(saldo,0), UPPER(COALESCE(local,''))
            FROM produtos
            WHERE 1=1
        """
        params = []
        if termo:
            sql += " AND (UPPER(codigo) LIKE %s OR UPPER(descricao) LIKE %s)"
            params.extend([f"%{termo}%", f"%{termo}%"])
        sql += " ORDER BY descricao"
        if not full:
            sql += " LIMIT %s"
            params.append(LIST_LIMIT)
        return sql, tuple(params)

    def _run_search(self):
        sql, params = self._sql_for_filter(full=False)
    
        try:
            self.cursor.execute(sql, params)
            rows = self.cursor.fetchall()
        except DatabaseError as e:
            _err(self, "Busca", f"Não foi possível realizar a pesquisa.\n\n{e}")
            return
    
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
    
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
    
            for c, val in enumerate(r):
                item = QTableWidgetItem()
    
                if c == 2:  # SALDO NUMÉRICO
                    numero = 0 if val is None else float(val)
                    item.setData(Qt.DisplayRole, numero)
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                else:
                    txt = "" if val is None else str(val)
                    item.setText(txt)
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    
                self.table.setItem(row, c, item)
    
        self.table.setSortingEnabled(True)
        self._update_stats()
        msg = f"{len(rows)} registros carregados."
        if len(rows) == LIST_LIMIT:
            msg = f"{LIST_LIMIT} registros carregados. Use a busca para filtrar melhor."
        self.statusBar().showMessage(msg, 2500)

    def _update_stats(self):
        try:
            self.cursor.execute("SELECT COALESCE(SUM(saldo),0), COUNT(*) FROM produtos")
            total_saldo, total_itens = self.cursor.fetchone()
        except DatabaseError as e:
            _err(self, "Estatísticas", f"Não foi possível obter as estatísticas.\n\n{e}")
            return
        self.lblStats.setText(f"Saldo Total: {total_saldo} • Total de Itens: {total_itens}")

    # ---------- exportações ----------
    def _export_pdf(self):
        if not _HAS_REPORTLAB:
            _err(self, "Exportar PDF", "Biblioteca 'reportlab' não encontrada.\nInstale com: pip install reportlab")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Salvar PDF", "estoque.pdf", "PDF (*.pdf)")
        if not path: return

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
            from reportlab.lib.pagesizes import letter, landscape
            from reportlab.pdfgen import canvas
            c = canvas.Canvas(path, pagesize=landscape(letter))
            width, height = landscape(letter)
            c.setFont("Helvetica", 10)

            x0, y = 40, height - 40
            row_h = 18
            w_cod, w_desc, w_saldo, w_loc = 140, 360, 80, 140

            # cabeçalhos
            c.drawString(x0, y, "Código")
            c.drawString(x0 + w_cod, y, "Descrição")
            c.drawString(x0 + w_cod + w_desc, y, "Saldo")
            c.drawString(x0 + w_cod + w_desc + w_saldo, y, "Local")
            y -= row_h

            def draw_row(vals):
                nonlocal y
                # quebra leve na descrição
                desc = vals[1]
                maxw = w_desc - 10
                if c.stringWidth(desc, "Helvetica", 10) > maxw:
                    # corta “no amor”
                    while c.stringWidth(desc + "…", "Helvetica", 10) > maxw and len(desc) > 0:
                        desc = desc[:-1]
                    desc += "…"
                c.drawString(x0, y, vals[0])
                c.drawString(x0 + w_cod, y, desc)
                c.drawRightString(x0 + w_cod + w_desc + w_saldo - 6, y, vals[2])
                c.drawString(x0 + w_cod + w_desc + w_saldo, y, vals[3])
                y -= row_h

            rows_on_page = 0
            for raw in rows:
                vals = ["" if v is None else str(v) for v in raw]
                if rows_on_page and rows_on_page % 28 == 0:
                    c.showPage(); c.setFont("Helvetica", 10)
                    y = height - 40
                    c.drawString(x0, y, "Código")
                    c.drawString(x0 + w_cod, y, "Descrição")
                    c.drawString(x0 + w_cod + w_desc, y, "Saldo")
                    c.drawString(x0 + w_cod + w_desc + w_saldo, y, "Local")
                    y -= row_h
                draw_row(vals); rows_on_page += 1

            c.save()
        except Exception as e:
            _err(self, "Exportar PDF", f"Falhou ao exportar.\n\n{e}")
            return

        self.statusBar().showMessage("PDF exportado.", 2000)

    def _export_excel(self):
        if not _HAS_PANDAS:
            _err(self, "Exportar Excel", "Biblioteca 'pandas' não encontrada.\nInstale com: pip install pandas openpyxl")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Salvar Excel", "estoque.xlsx", "Excel (*.xlsx)")
        if not path: return

        try:
            sql, params = self._sql_for_filter(full=True)
            self.cursor.execute(sql, params)
            data = self.cursor.fetchall()
            if not data:
                _err(self, "Exportar Excel", "Nada para exportar.")
                return
            df = pd.DataFrame(data, columns=list(COLS))
            df.to_excel(path, index=False)
        except DatabaseError as e:
            _err(self, "Exportar Excel", f"Erro na consulta para exportação.\n\n{e}")
            return
        except Exception as e:
            _err(self, "Exportar Excel", f"Falhou ao exportar.\n\n{e}")
            return

        self.statusBar().showMessage("Excel exportado.", 2000)

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
        if callable(abrir):
            try:
                self.hide()
                child = abrir(self)  # passar self como parent
                # se o módulo retornar uma janela, reexibe ao fechar
                if hasattr(child, "destroyed"):
                    child.destroyed.connect(self._back_to_me)
            except Exception as e:
                self.show()
                _err(self, "Abrir módulo", f"Erro ao abrir '{modname}'.\n\n{e}")
        else:
            _err(self, "Abrir módulo", f"O módulo '{modname}' não expõe função abrir(parent).")

    def _back_to_me(self, *_):
        self.show(); self.raise_(); self.activateWindow()

    # ---------- fechamento ----------
    def closeEvent(self, e):
        try:
            if hasattr(self, "cursor") and self.cursor: self.cursor.close()
            if hasattr(self, "conn") and self.conn: self.conn.close()
        except Exception:
            pass
        # reabre parent (main) se existir
        p = self.parent()
        if p and hasattr(p, "show"):
            p.show(); p.raise_(); p.activateWindow()
        super().closeEvent(e)

# --------- função para o launcher (main.py) ---------
def abrir(parent=None):
    win = EstoqueApp(parent)
    win.showMaximized()
    return win

# --------- standalone ---------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = EstoqueApp()
    w.showMaximized()
    sys.exit(app.exec())
