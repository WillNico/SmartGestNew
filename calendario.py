from __future__ import annotations

from PySide6.QtCore import QDate, QLocale, Signal
from PySide6.QtWidgets import (
    QCalendarWidget,
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class CalendarioDialog(QDialog):
    def __init__(self, parent=None, selected_date: QDate | None = None):
        super().__init__(parent)
        self.setWindowTitle("Calendário")
        self.resize(420, 340)

        root = QVBoxLayout(self)

        self.calendar = QCalendarWidget(self)
        self.calendar.setGridVisible(True)
        self.calendar.setLocale(QLocale(QLocale.Portuguese, QLocale.Brazil))
        self.calendar.setSelectedDate(selected_date or QDate.currentDate())
        self.calendar.activated.connect(self.accept)
        root.addWidget(self.calendar, 1)

        buttons = QWidget(self)
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)

        bt_today = QPushButton("Hoje", self)
        bt_ok = QPushButton("OK", self)
        bt_cancel = QPushButton("Cancelar", self)

        bt_today.clicked.connect(lambda: self.calendar.setSelectedDate(QDate.currentDate()))
        bt_ok.clicked.connect(self.accept)
        bt_cancel.clicked.connect(self.reject)

        row.addWidget(bt_today)
        row.addStretch()
        row.addWidget(bt_ok)
        row.addWidget(bt_cancel)
        root.addWidget(buttons)

    def selected_date(self) -> QDate:
        return self.calendar.selectedDate()


class CampoData(QWidget):
    dateChanged = Signal(QDate)

    def __init__(self, parent=None, date: QDate | None = None, display_format: str = "dd/MM/yyyy"):
        super().__init__(parent)

        self._edit = QDateEdit(self)
        self._edit.setDisplayFormat(display_format)
        self._edit.setLocale(QLocale(QLocale.Portuguese, QLocale.Brazil))
        self._edit.setCalendarPopup(False)
        self._edit.setDate(date or QDate.currentDate())

        self._button = QToolButton(self)
        self._button.setText("...")
        self._button.setToolTip("Abrir calendário")
        self._button.setFixedWidth(34)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._edit, 1)
        layout.addWidget(self._button)

        self._edit.dateChanged.connect(self.dateChanged.emit)
        self._button.clicked.connect(self.abrir_calendario)
        self.setFocusProxy(self._edit)

    def abrir_calendario(self):
        dlg = CalendarioDialog(self, self._edit.date())
        if dlg.exec() == QDialog.Accepted:
            self._edit.setDate(dlg.selected_date())

    def date(self) -> QDate:
        return self._edit.date()

    def setDate(self, date: QDate):
        self._edit.setDate(date)

    def setDisplayFormat(self, display_format: str):
        self._edit.setDisplayFormat(display_format)

    def displayFormat(self) -> str:
        return self._edit.displayFormat()

    def setMinimumDate(self, date: QDate):
        self._edit.setMinimumDate(date)

    def setMaximumDate(self, date: QDate):
        self._edit.setMaximumDate(date)

    def setDateRange(self, minimum: QDate, maximum: QDate):
        self._edit.setDateRange(minimum, maximum)

    def setCalendarPopup(self, _enabled: bool):
        self._edit.setCalendarPopup(False)


def criar_campo_data(parent=None, date: QDate | None = None) -> CampoData:
    return CampoData(parent=parent, date=date)
