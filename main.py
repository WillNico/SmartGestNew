# main.py - SmartGest (PySide6)
# Requisitos: pip install PySide6
# Dica: rode com "python main.py"

from __future__ import annotations
import sys
import importlib
import traceback
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QAction, QIcon, QPalette, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QGridLayout,
    QVBoxLayout, QHBoxLayout, QMessageBox, QInputDialog, QSizePolicy,
    QStatusBar, QGraphicsDropShadowEffect, QLineEdit
)

APP_TITLE = "SmartGest"
APP_SUBTITLE = "Gestor de Estoque"
CREDITOS = "Desenvolvido por Willian Nicoletti"
SENHA_ESTOQUE_ADM = "147258"


def resource_path(relative_path: str) -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return str(base / relative_path)

# ---------- helpers de tema ----------
def make_light_palette():
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#E8F1FB"))            # fundo geral
    pal.setColor(QPalette.WindowText, Qt.black)
    pal.setColor(QPalette.Base, QColor("#FFFFFF"))
    pal.setColor(QPalette.AlternateBase, QColor("#F6F9FE"))
    pal.setColor(QPalette.ToolTipBase, Qt.white)
    pal.setColor(QPalette.ToolTipText, Qt.black)
    pal.setColor(QPalette.Text, Qt.black)
    pal.setColor(QPalette.Button, QColor("#FFFFFF"))
    pal.setColor(QPalette.ButtonText, Qt.black)
    pal.setColor(QPalette.Highlight, QColor("#2D7FF9"))
    pal.setColor(QPalette.HighlightedText, Qt.white)
    return pal

def make_dark_palette():
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#101218"))
    pal.setColor(QPalette.WindowText, Qt.white)
    pal.setColor(QPalette.Base, QColor("#0B0D12"))
    pal.setColor(QPalette.AlternateBase, QColor("#121520"))
    pal.setColor(QPalette.ToolTipBase, QColor("#1B1F2A"))
    pal.setColor(QPalette.ToolTipText, Qt.white)
    pal.setColor(QPalette.Text, Qt.white)
    pal.setColor(QPalette.Button, QColor("#151A24"))
    pal.setColor(QPalette.ButtonText, Qt.white)
    pal.setColor(QPalette.Highlight, QColor("#4C8DFF"))
    pal.setColor(QPalette.HighlightedText, Qt.black)
    return pal

# ---------- botão tile bonito ----------
class TileButton(QPushButton):
    def __init__(self, label: str, emoji: str = "🧩", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setText(f"{emoji}\n{label}")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.setMinimumSize(210, 120)
        self.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.setCheckable(False)
        # estilo (QSS)
        self.setStyleSheet("""
            QPushButton {
                border: 0px;
                color: #0b2545;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                            stop:0 #ffffff, stop:1 #edf3ff);
                border-radius: 16px;
                padding: 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                            stop:0 #f6faff, stop:1 #e8f1ff);
            }
            QPushButton:pressed {
                background: #dfeaff;
            }
        """)

        # leve sombra “glass”
        shadow = QGraphicsDropShadowEffect(self, blurRadius=20, xOffset=0, yOffset=8)
        shadow.setColor(QColor(0, 0, 0, 50))
        self.setGraphicsEffect(shadow)

# ---------- janela principal ----------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_TITLE}")
        self.resize(1280, 800)
        self.setStyleSheet("QToolTip { color: white; background-color: #3A3F58; border: 0px; }")
        self._dark = False

        # Central card
        central = QWidget(self)
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(32, 24, 32, 24)
        outer.setSpacing(20)

        # Cabeçalho
        header = QWidget()
        hl = QVBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)

        titulo = QLabel(f"{APP_TITLE}")
        titulo.setFont(QFont("Segoe UI Variable", 28, QFont.Bold))
        subtitulo = QLabel(f"{APP_SUBTITLE}")
        subtitulo.setFont(QFont("Segoe UI", 14))
        subtitulo.setStyleSheet("color:#355070;")

        hl.addWidget(titulo)
        hl.addWidget(subtitulo)
        outer.addWidget(header)

        # grade de botões
        gridWrap = QWidget()
        grid = QGridLayout(gridWrap)
        grid.setSpacing(16)
        grid.setContentsMargins(0, 0, 0, 0)

        # mapa: label -> (emoji, handler)
        self.actions = {
            "Movimentação de Peças": ("🔁", self.abrir_movimentacao),
            "Entradas de Notas":      ("📥", self.abrir_entradas),
            "Cadastro de Peça":       ("🧾", self.abrir_cadastro),
            "Histórico de Movimentação": ("📜", self.abrir_historico),
            "Estoque":                ("📦", self.abrir_estoque),
            "Estoque Administrativo": ("🛡️", self.abrir_estoque_adm),
            "Editar Estoque Mínimo":  ("⚙️", self.abrir_estoque_baixo),
            "Sair":                   ("🚪", self.sair),
        }

        # cria tiles em grade 3xN
        cols = 3
        i = 0
        for label, (emoji, handler) in self.actions.items():
            btn = TileButton(label, emoji)
            btn.clicked.connect(handler)
            r, c = divmod(i, cols)
            grid.addWidget(btn, r, c)
            i += 1

        outer.addWidget(gridWrap, 1)

        # créditos
        creditos = QLabel(CREDITOS)
        creditos.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        creditos.setStyleSheet("color:#5a6a85;")
        creditos.setFont(QFont("Segoe UI", 10))
        outer.addWidget(creditos)

        # statusbar + menu/atalhos
        self._build_menu_and_status()

        # tema inicial (claro)
        QApplication.setPalette(make_light_palette())

        # maximiza
        self.showMaximized()

    # ---------- menu / atalhos ----------
    def _build_menu_and_status(self):
        mb = self.menuBar()
        menuArquivo = mb.addMenu("&Arquivo")
        menuExibir = mb.addMenu("&Exibir")
        menuAjuda = mb.addMenu("&Ajuda")

        # Atalhos úteis
        actMov = QAction("Movimentação (Ctrl+M)", self); actMov.setShortcut("Ctrl+M"); actMov.triggered.connect(self.abrir_movimentacao)
        actEnt = QAction("Entradas (Ctrl+E)", self); actEnt.setShortcut("Ctrl+E"); actEnt.triggered.connect(self.abrir_entradas)
        actCad = QAction("Cadastro (Ctrl+D)", self); actCad.setShortcut("Ctrl+D"); actCad.triggered.connect(self.abrir_cadastro)
        actHis = QAction("Histórico (Ctrl+H)", self); actHis.setShortcut("Ctrl+H"); actHis.triggered.connect(self.abrir_historico)
        actEst = QAction("Estoque (Ctrl+S)", self); actEst.setShortcut("Ctrl+S"); actEst.triggered.connect(self.abrir_estoque)
        actAdm = QAction("Estoque Adm (Ctrl+A)", self); actAdm.setShortcut("Ctrl+A"); actAdm.triggered.connect(self.abrir_estoque_adm)
        actMin = QAction("Estoque Mínimo (Ctrl+I)", self); actMin.setShortcut("Ctrl+I"); actMin.triggered.connect(self.abrir_estoque_baixo)
        actSair = QAction("Sair (Ctrl+Q)", self); actSair.setShortcut("Ctrl+Q"); actSair.triggered.connect(self.sair)

        for a in (actMov, actEnt, actCad, actHis, actEst, actAdm, actMin, actSair):
            menuArquivo.addAction(a)

        # Tema claro/escuro
        actTema = QAction("Alternar tema (F2)", self)
        actTema.setShortcut("F2")
        actTema.triggered.connect(self.toggle_theme)
        menuExibir.addAction(actTema)

        # Sobre
        actSobre = QAction("Sobre…", self)
        actSobre.triggered.connect(self._sobre)
        menuAjuda.addAction(actSobre)

        # Status bar
        sb = QStatusBar()
        sb.showMessage("Pronto. Dica: F2 alterna tema • Ctrl+M abre Movimentação.")
        self.setStatusBar(sb)

    def toggle_theme(self):
        self._dark = not self._dark
        QApplication.setPalette(make_dark_palette() if self._dark else make_light_palette())
        self.statusBar().showMessage("Tema escuro" if self._dark else "Tema claro", 2000)

    def _sobre(self):
        QMessageBox.information(self, "Sobre", f"{APP_TITLE}\nFeito por Willian Nicoletti Contato: (47) 9 9106-7550.\n{CREDITOS}")

    # ---------- util para abrir módulos ----------
    def _abrir_modulo(self, import_name: str, factory_names: tuple[str, ...] = ("abrir",), *, with_parent=True, maximize=True):
        """
        Tenta importar um módulo e chamar:
          - uma função 'abrir(parent?)'  OU
          - instanciar uma classe conhecida (ex.: MovimentacaoApp/Estoque/etc) e dar .show()

        Se o módulo/classe não existir, mostra erro bonitinho.
        """
        try:
            module = importlib.import_module(import_name)
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, "Erro ao importar",
                                 f"Não consegui importar o módulo '{import_name}'.\n\n{e}")
            return

        # 1) tenta função 'abrir'
        for fname in factory_names:
            func = getattr(module, fname, None)
            if callable(func):
                try:
                    self.hide()
                    if with_parent:
                        ret = func(self)
                    else:
                        ret = func()
                    # se retornar um QWidget/QMainWindow, conecta pra voltar quando fechar
                    if hasattr(ret, "destroyed"):
                        ret.destroyed.connect(self._voltar_main)
                    # se não retornou janela (padrão abrir modal?), garante que main volte depois
                    self.statusBar().showMessage(f"Abrindo {import_name}…", 1500)
                except Exception as e:
                    self.show()
                    traceback.print_exc()
                    QMessageBox.critical(self, "Erro ao abrir",
                                         f"Falhou ao abrir '{import_name}.{fname}()'.\n\n{e}")
                return  # sucesso ou tentativa feita

        # 2) tenta classes mais comuns
        candidate_classes = (
            "MovimentacaoApp", "EntradasApp", "CadastroPecaApp", "CadastroApp",
            "HistoricoApp", "EstoqueApp", "EstoqueAdmApp", "EstoqueBaixoApp",
            "InventarioApp", "ValorizacaoApp", "ComprasApp", "FormularioApp"
        )
        for cname in candidate_classes:
            cls = getattr(module, cname, None)
            if cls is not None:
                try:
                    self.hide()
                    try:
                        w = cls(self) if with_parent else cls()
                    except TypeError:
                        # caso a classe não aceite parent
                        w = cls()
                    if hasattr(w, "setAttribute"):
                        w.setAttribute(Qt.WA_DeleteOnClose, True)
                    if hasattr(w, "show"):
                        if maximize and hasattr(w, "showMaximized"):
                            w.showMaximized()
                        else:
                            w.show()
                    if hasattr(w, "destroyed"):
                        w.destroyed.connect(self._voltar_main)
                    self.statusBar().showMessage(f"Abrindo {import_name}.{cname}…", 1500)
                    return
                except Exception as e:
                    self.show()
                    traceback.print_exc()
                    QMessageBox.critical(self, "Erro ao abrir",
                                         f"Falhou ao instanciar '{import_name}.{cname}'.\n\n{e}")
                    return

        # nada deu certo
        self.show()
        QMessageBox.warning(self, "Não implementado",
                            f"O módulo '{import_name}' não tem função 'abrir' nem classe esperada.")

    def _voltar_main(self, *args):
        # volta pra janela principal quando a janela filha fechar
        self.show()
        self.raise_()
        self.activateWindow()

    # ---------- handlers dos botões ----------
    def abrir_movimentacao(self):
        self._abrir_modulo("movimentacao", factory_names=("abrir",), with_parent=True)

    def abrir_entradas(self):
        self._abrir_modulo("entradas", factory_names=("abrir",), with_parent=True)

    def abrir_cadastro(self):
        self._abrir_modulo("cadastro", factory_names=("abrir",), with_parent=True)

    def abrir_historico(self):
        self._abrir_modulo("historico", factory_names=("abrir",), with_parent=True)


    def abrir_estoque(self):
        self._abrir_modulo("estoque", factory_names=("abrir",), with_parent=True)

    def abrir_estoque_adm(self):
        senha, ok = QInputDialog.getText(
            self,
            "Senha",
            "Digite a senha para acessar:",
            echo=QLineEdit.Password
        )
        if ok and senha == SENHA_ESTOQUE_ADM:
            self._abrir_modulo("estoque_adm", factory_names=("abrir",), with_parent=True)
        elif ok:
            QMessageBox.critical(self, "Erro", "Senha incorreta")


    def abrir_estoque_baixo(self):
        self._abrir_modulo("estoque_baixo", factory_names=("abrir",), with_parent=True)

    def sair(self):
        self.close()

# ---------- main ----------
def main():
    app = QApplication(sys.argv)
    app.setApplicationDisplayName(APP_TITLE)
    app.setStyle("Fusion")
    app.setWindowIcon(QIcon(resource_path("assets/icon.ico")))  # define o ícone global aqui
    win = MainWindow()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
