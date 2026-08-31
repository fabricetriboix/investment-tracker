"""Per-account tab: editable CSV, 10,000 growth chart, statistics."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from investment_tracker.csv_loader import COLUMNS, Account, next_yearmonth, save_account
from investment_tracker.interpolation import fill_missing_months
from investment_tracker.metrics import INDEX_START, account_stats, growth_of_index, monthly_price_returns
from investment_tracker.ui.charts import LineChart
from investment_tracker.ui.formatters import fmt_drawdown, fmt_money, fmt_pct
from investment_tracker.ui.styles import MUTED, NAVY, TEAL

HEADERS = ["Year-month", "Contribution", "Withdrawal", "Distribution", "Balance"]


class AccountTableModel(QAbstractTableModel):
    rows_changed = Signal()

    def __init__(self, account: Account, parent=None):
        super().__init__(parent)
        self.account = account
        self._rows: list[list[str]] = self._from_frame(account.raw)

    @staticmethod
    def _from_frame(frame) -> list[list[str]]:
        rows: list[list[str]] = []
        if frame is None or frame.empty:
            return rows
        ordered = frame.sort_values("yearmonth")
        for _, row in ordered.iterrows():
            rows.append(
                [
                    f"{int(row['yearmonth']):06d}",
                    f"{float(row['contribution']):.2f}",
                    f"{float(row['withdrawal']):.2f}",
                    f"{float(row['distribution']):.2f}",
                    f"{float(row['balance']):.2f}",
                ]
            )
        return rows

    def frame(self):
        import pandas as pd

        if not self._rows:
            return pd.DataFrame(columns=list(COLUMNS))
        records = []
        for row in self._rows:
            try:
                records.append(
                    {
                        "yearmonth": int(str(row[0]).replace("-", "")),
                        "contribution": float(row[1] or 0),
                        "withdrawal": float(row[2] or 0),
                        "distribution": float(row[3] or 0),
                        "balance": float(row[4] or 0),
                    }
                )
            except (TypeError, ValueError):
                continue
        return pd.DataFrame(records, columns=list(COLUMNS))

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return 5

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return HEADERS[section]
        return str(section + 1)

    def flags(self, index):  # noqa: N802
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if not index.isValid():
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return self._rows[index.row()][index.column()]
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() > 0:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):  # noqa: N802
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        text = str(value).strip()
        column = index.column()
        if column == 0:
            compact = text.replace("-", "")
            if not compact.isdigit() or len(compact) != 6:
                return False
            month = int(compact[4:])
            if month < 1 or month > 12:
                return False
            text = f"{int(compact):06d}"
        else:
            try:
                text = f"{float(text.replace(',', '')):.2f}"
            except ValueError:
                return False
        self._rows[index.row()][column] = text
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole])
        self.rows_changed.emit()
        return True

    def add_row(self) -> None:
        frame = self.frame()
        nxt = next_yearmonth(frame)
        last_balance = "0.00"
        if self._rows:
            last_balance = self._rows[-1][4]
        self.beginInsertRows(QModelIndex(), len(self._rows), len(self._rows))
        self._rows.append([f"{nxt:06d}", "0.00", "0.00", "0.00", last_balance])
        self.endInsertRows()
        self.rows_changed.emit()

    def remove_rows(self, rows: list[int]) -> None:
        for row in sorted(set(rows), reverse=True):
            if 0 <= row < len(self._rows):
                self.beginRemoveRows(QModelIndex(), row, row)
                del self._rows[row]
                self.endRemoveRows()
        self.rows_changed.emit()


class AccountTab(QWidget):
    saved = Signal()
    save_failed = Signal(str)

    def __init__(self, account: Account, parent=None):
        super().__init__(parent)
        self.account = account
        self.model = AccountTableModel(account)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._flush_save)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel(account.name)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {NAVY};")
        self.currency_label = QLabel(f"Currency: {account.currency}")
        self.currency_label.setStyleSheet(f"color: {MUTED}; font-weight: 600;")
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {TEAL};")
        header.addWidget(title)
        header.addSpacing(12)
        header.addWidget(self.currency_label)
        header.addStretch()
        header.addWidget(self.status_label)
        layout.addLayout(header)

        self.stats_table = QTableWidget(4, 6)
        self.stats_table.setHorizontalHeaderLabels(
            [
                "Period",
                "CAGR",
                "Volatility (ann.)",
                "Max drawdown",
                "Mean yield (monthly)",
                "Mean yield (amount)",
            ]
        )
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.stats_table.setMaximumHeight(160)
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.stats_table)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.chart = LineChart(f"Growth of {INDEX_START:,.0f} {account.currency}")
        self.chart.setMinimumHeight(180)
        splitter.addWidget(self.chart)

        table_wrap = QWidget()
        table_layout = QVBoxLayout(table_wrap)
        table_layout.setContentsMargins(0, 0, 0, 0)
        buttons = QHBoxLayout()
        add_btn = QPushButton("Add month")
        add_btn.clicked.connect(self._add_row)
        del_btn = QPushButton("Delete selected")
        del_btn.setProperty("secondary", True)
        del_btn.clicked.connect(self._delete_selected)
        hint = QLabel("Edits are saved automatically to the CSV file.")
        hint.setStyleSheet(f"color: {MUTED};")
        buttons.addWidget(add_btn)
        buttons.addWidget(del_btn)
        buttons.addStretch()
        buttons.addWidget(hint)
        table_layout.addLayout(buttons)

        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        table_layout.addWidget(self.table)
        splitter.addWidget(table_wrap)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, stretch=1)

        self.model.rows_changed.connect(self._on_rows_changed)
        self._refresh_derived()

    def _on_rows_changed(self) -> None:
        self.status_label.setText("Saving…")
        self._save_timer.start()
        self._refresh_derived()

    def _flush_save(self) -> None:
        frame = self.model.frame()
        try:
            save_account(self.account.path, frame)
        except Exception as exc:  # noqa: BLE001
            self.status_label.setText("Save failed")
            self.save_failed.emit(str(exc))
            return
        self.account.raw = frame
        self.account.filled = fill_missing_months(frame)
        self.status_label.setText("Saved")
        self.saved.emit()

    def _refresh_derived(self) -> None:
        frame = self.model.frame()
        filled = fill_missing_months(frame)
        returns = monthly_price_returns(filled)
        index = growth_of_index(returns)
        self.chart.plot_series(index, self.account.currency)
        stats = account_stats(filled)
        for row, item in enumerate(stats):
            values = [
                item.label,
                fmt_pct(item.cagr, signed=True),
                fmt_pct(item.volatility),
                fmt_drawdown(item.max_drawdown),
                fmt_pct(item.mean_yield_pct, digits=2),
                fmt_money(item.mean_yield_amount, self.account.currency, decimals=2),
            ]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if col > 0:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.stats_table.setItem(row, col, cell)

    def _add_row(self) -> None:
        self.model.add_row()
        self.table.scrollToBottom()

    def _delete_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        if not rows:
            return
        confirm = QMessageBox.question(
            self,
            "Delete rows",
            f"Delete {len(rows)} selected month(s)? This is saved immediately.",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.model.remove_rows(rows)
