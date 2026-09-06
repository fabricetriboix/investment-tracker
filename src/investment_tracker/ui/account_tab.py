"""Per-account tab: CSV view, 10,000 growth chart, statistics."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from investment_tracker.csv_loader import Account
from investment_tracker.metrics import INDEX_START, account_stats, growth_of_index, monthly_price_returns
from investment_tracker.ui.charts import LineChart
from investment_tracker.ui.formatters import fmt_drawdown, fmt_money, fmt_pct
from investment_tracker.ui.styles import MUTED, NAVY
from investment_tracker.ui.tables import shrink_wrap

DIST_HEADERS = ["Year-month", "Contribution", "Withdrawal", "Distribution", "Balance"]
ACCUM_HEADERS = ["Year-month", "Contribution", "Withdrawal", "Balance"]


def _csv_headers(pays_income: bool) -> list[str]:
    return DIST_HEADERS if pays_income else ACCUM_HEADERS


def _row_values(row, pays_income: bool) -> list[str]:
    values = [
        f"{int(row['yearmonth']):06d}",
        f"{float(row['contribution']):.2f}",
        f"{float(row['withdrawal']):.2f}",
    ]
    if pays_income:
        values.append(f"{float(row['distribution']):.2f}")
    values.append(f"{float(row['balance']):.2f}")
    return values


class AccountTab(QWidget):
    def __init__(self, account: Account, bucket_name: str | None = None, parent=None):
        super().__init__(parent)
        self.account = account

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
        currency_label = QLabel(f"Currency: {account.currency}")
        currency_label.setStyleSheet(f"color: {MUTED}; font-weight: 600;")
        type_label = QLabel(f"Type: {account.type_label}")
        type_label.setStyleSheet(f"color: {NAVY}; font-weight: 600;")
        bucket_label = QLabel(f"Bucket: {bucket_name}" if bucket_name else "Bucket: Unassigned")
        bucket_label.setStyleSheet(f"color: {NAVY}; font-weight: 600;")
        header.addWidget(title)
        header.addSpacing(12)
        header.addWidget(currency_label)
        header.addSpacing(12)
        header.addWidget(type_label)
        header.addSpacing(12)
        header.addWidget(bucket_label)
        header.addStretch()
        layout.addLayout(header)

        if account.pays_income:
            note = QLabel(
                "The first row is the opening balance. "
                "Distribution is income paid out of the account. "
                "Edit the CSV file on disk and press F5 to reload."
            )
            stat_headers = [
                "Period",
                "CAGR",
                "Volatility (ann.)",
                "Max drawdown",
                "Mean yield (monthly)",
                "Mean yield (amount)",
            ]
            self._stat_columns = 6
        else:
            note = QLabel(
                "The first row is the opening balance. "
                "This is an accumulation account: income is reinvested and is not recorded separately. "
                "Edit the CSV file on disk and press F5 to reload."
            )
            stat_headers = ["Period", "CAGR", "Volatility (ann.)", "Max drawdown"]
            self._stat_columns = 4
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {MUTED};")
        layout.addWidget(note)

        self.stats_table = QTableWidget(4, self._stat_columns)
        self.stats_table.setHorizontalHeaderLabels(stat_headers)
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.stats_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.stats_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.stats_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.stats_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.stats_table, alignment=Qt.AlignmentFlag.AlignLeft)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.chart = LineChart(f"Growth of {INDEX_START:,.0f} {account.currency}")
        self.chart.setMinimumHeight(180)
        splitter.addWidget(self.chart)

        self.table = QTableWidget(0, len(_csv_headers(account.pays_income)))
        self.table.setHorizontalHeaderLabels(_csv_headers(account.pays_income))
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setTextElideMode(Qt.TextElideMode.ElideNone)
        splitter.addWidget(self.table)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, stretch=1)

        self._fill_csv_table()
        self._fill_stats()

    def _fill_csv_table(self) -> None:
        frame = self.account.raw
        pays = self.account.pays_income
        if frame is None or frame.empty:
            self.table.setRowCount(0)
            return
        ordered = frame.sort_values("yearmonth")
        self.table.setRowCount(len(ordered))
        labels: list[str] = []
        for row_index, (_, row) in enumerate(ordered.iterrows()):
            values = _row_values(row, pays)
            labels.append("Open" if row_index == 0 else str(row_index + 1))
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if col > 0:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_index, col, cell)
        self.table.setVerticalHeaderLabels(labels)

    def _fill_stats(self) -> None:
        filled = self.account.filled
        returns = monthly_price_returns(filled)
        index = growth_of_index(returns)
        self.chart.plot_series(index, self.account.currency)
        stats = account_stats(filled, include_yield=self.account.pays_income)
        for row, item in enumerate(stats):
            values = [
                item.label,
                fmt_pct(item.cagr, signed=True),
                fmt_pct(item.volatility),
                fmt_drawdown(item.max_drawdown),
            ]
            if self.account.pays_income:
                values.extend(
                    [
                        fmt_pct(item.mean_yield_pct, digits=2),
                        fmt_money(item.mean_yield_amount, self.account.currency, decimals=2),
                    ]
                )
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if col > 0:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.stats_table.setItem(row, col, cell)
        shrink_wrap(self.stats_table)
