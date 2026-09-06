"""Dashboard: portfolio net worth, bucket KPIs, net-worth and bucket charts."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from investment_tracker.config import AppConfig
from investment_tracker.portfolio import BucketSnapshot, DashboardData
from investment_tracker.ui.charts import LineChart
from investment_tracker.ui.formatters import (
    allocation_color,
    colored_item,
    comparison_color,
    fmt_drawdown,
    fmt_money,
    fmt_pct,
    yearmonth_label,
)
from investment_tracker.ui.styles import MUTED, NAVY, NEGATIVE, TEAL
from investment_tracker.ui.tables import FittedTable, fit_columns, fit_height


class _KpiCard(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("kpiCard")
        self.setStyleSheet(
            """
            QFrame#kpiCard {
                background: #ffffff;
                border: 1px solid #d5dbdb;
                border-radius: 8px;
            }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(2)
        self._kicker = QLabel(title)
        self._kicker.setStyleSheet(f"color: {MUTED}; font-size: 13px; font-weight: 600;")
        self._value = QLabel("—")
        self._value.setStyleSheet(f"color: {NAVY}; font-size: 24px; font-weight: 700;")
        self._hint = QLabel("")
        self._hint.setStyleSheet(f"color: {MUTED}; font-size: 13px;")
        layout.addWidget(self._kicker)
        layout.addWidget(self._value)
        layout.addWidget(self._hint)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_values(self, value: str, hint: str = "") -> None:
        self._value.setText(value)
        self._hint.setText(hint)


def _metric_table() -> FittedTable:
    table = FittedTable()
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return table


def _bucket_item(table: QTableWidget, name: str) -> QTableWidgetItem:
    item = QTableWidgetItem(name)
    item.setForeground(table.palette().text())
    return item


def _cell(bucket: BucketSnapshot, key: str, base: str, table: QTableWidget) -> QTableWidgetItem:
    if key == "bucket":
        return _bucket_item(table, bucket.name)
    if key == "size":
        text = f"{fmt_pct(bucket.size_pct)}  ({fmt_money(bucket.size_usd, base)})"
        return colored_item(text, allocation_color(bucket.size_pct, bucket.target_allocation))
    if key == "size_tgt":
        return colored_item(fmt_pct(bucket.target_allocation), MUTED)
    if key == "ret":
        return colored_item(
            fmt_pct(bucket.return_12m, signed=True),
            comparison_color(bucket.return_12m, bucket.target_return, True),
        )
    if key == "ret_tgt":
        return colored_item(fmt_pct(bucket.target_return), MUTED)
    if key == "ret_5y":
        return colored_item(
            fmt_pct(bucket.return_5y, signed=True),
            comparison_color(bucket.return_5y, bucket.target_return, True),
        )
    if key == "ret_10y":
        return colored_item(
            fmt_pct(bucket.return_10y, signed=True),
            comparison_color(bucket.return_10y, bucket.target_return, True),
        )
    if key == "yield":
        if not bucket.has_income:
            return colored_item("—", MUTED)
        if not bucket.has_yield_target:
            return colored_item(fmt_pct(bucket.yield_12m), MUTED)
        return colored_item(
            fmt_pct(bucket.yield_12m),
            comparison_color(bucket.yield_12m, bucket.target_income_yield, True),
        )
    if key == "yield_tgt":
        return colored_item(fmt_pct(bucket.target_income_yield) if bucket.has_income else "—", MUTED)
    if key == "income":
        if bucket.has_income:
            return colored_item(fmt_money(bucket.income_12m_usd, base))
        return colored_item("—", MUTED)
    if key == "vol":
        return colored_item(
            fmt_pct(bucket.volatility_5y),
            comparison_color(bucket.volatility_5y, bucket.target_volatility, False),
        )
    if key == "vol_tgt":
        return colored_item(fmt_pct(bucket.target_volatility), MUTED)
    if key == "dd":
        return colored_item(
            fmt_drawdown(bucket.max_drawdown_5y),
            comparison_color(bucket.max_drawdown_5y, bucket.target_max_drawdown, False),
        )
    if key == "dd_tgt":
        return colored_item(fmt_drawdown(bucket.target_max_drawdown), MUTED)
    return QTableWidgetItem("")


class DashboardTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._config = AppConfig()
        self._data: DashboardData | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        root = QVBoxLayout(inner)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)
        self.net_worth_card = _KpiCard("Portfolio net worth")
        self.income_card = _KpiCard("Distributions · past 12 months")
        kpi_row.addWidget(self.net_worth_card)
        kpi_row.addWidget(self.income_card)
        root.addLayout(kpi_row)

        self._banner = QLabel("")
        self._banner.setWordWrap(True)
        self._banner.setStyleSheet(f"color: {NEGATIVE}; font-size: 13px;")
        self._banner.hide()
        root.addWidget(self._banner)

        self.table = _metric_table()
        root.addWidget(self.table)

        self.risk_table = _metric_table()
        root.addWidget(self.risk_table)

        self.chart = LineChart("Net worth", height=5.6)
        self.chart.setMinimumHeight(440)
        root.addWidget(self.chart)

        self.bucket_chart = LineChart("Bucket balances", height=4.8)
        self.bucket_chart.setMinimumHeight(400)
        root.addWidget(self.bucket_chart)

    def render(self, data: DashboardData, config: AppConfig) -> None:
        self._data = data
        self._config = config
        base = config.base_currency
        as_of = yearmonth_label(data.as_of)
        self.net_worth_card.set_values(
            fmt_money(data.net_worth_usd, base),
            f"As of {as_of}" if data.as_of else "No account data loaded",
        )
        self.income_card.setVisible(data.has_income)
        if data.has_income:
            self.income_card.set_values(
                fmt_money(data.income_12m_usd, base),
                "Income paid out of distribution accounts",
            )

        warnings = data.load_errors + data.fx_warnings
        if warnings:
            self._banner.setText(" • ".join(warnings))
            self._banner.show()
        else:
            self._banner.hide()

        self._rebuild_tables(data, config)
        self.chart.plot_series(data.net_worth_series, f"Net worth ({base})", color=TEAL)
        self.bucket_chart.plot_many(data.bucket_series, f"Balance ({base})")

    def _rebuild_tables(self, data: DashboardData, config: AppConfig) -> None:
        summary: list[tuple[str, str]] = [
            ("bucket", "Bucket"),
            ("size", "Size"),
            ("size_tgt", "Target size"),
            ("ret", "Return 12m"),
            ("ret_tgt", "Target return"),
            ("ret_5y", "Return 5y"),
            ("ret_10y", "Return 10y"),
        ]
        risk: list[tuple[str, str]] = [("bucket", "Bucket")]
        if data.has_income:
            risk += [
                ("yield", "Yield 12m"),
                ("yield_tgt", "Target yield"),
                ("income", "Income 12m"),
            ]
        risk += [
            ("vol", "Volatility 5y"),
            ("vol_tgt", "Target volatility"),
            ("dd", "Max DD 5y"),
            ("dd_tgt", "Target max DD"),
        ]
        self._fill_table(self.table, summary, data, config)
        self._fill_table(self.risk_table, risk, data, config)

    def _fill_table(
        self,
        table: FittedTable,
        columns: list[tuple[str, str]],
        data: DashboardData,
        config: AppConfig,
    ) -> None:
        keys = [key for key, _ in columns]
        headers = [label for _, label in columns]
        table.clear()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(data.buckets))
        base = config.base_currency
        for row, bucket in enumerate(data.buckets):
            for col, key in enumerate(keys):
                table.setItem(row, col, _cell(bucket, key, base, table))
        total = fit_columns(table)
        fit_height(table, extra=18)
        table.setMinimumWidth(total + table.frameWidth() * 2 + 4)
