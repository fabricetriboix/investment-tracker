"""Dashboard: portfolio net worth, bucket KPIs, net-worth and bucket charts."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from investment_tracker.config import AppConfig
from investment_tracker.portfolio import DashboardData
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
from investment_tracker.ui.styles import AMBER, MUTED, NAVY, NEGATIVE, TEAL

_BUCKET_CHART_COLORS = (TEAL, NAVY, AMBER, "#6c3483", "#1a5276")


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


class DashboardTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._config = AppConfig()
        self._data: DashboardData | None = None
        self._bucket_charts: list[LineChart] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        root = QVBoxLayout(inner)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

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

        self.table = QTableWidget(0, 0)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.table)

        self.chart = LineChart("Net worth", height=5.6)
        self.chart.setMinimumHeight(440)
        root.addWidget(self.chart)

        self._bucket_charts_box = QVBoxLayout()
        self._bucket_charts_box.setSpacing(8)
        root.addLayout(self._bucket_charts_box)
        root.addStretch()

    def render(self, data: DashboardData, config: AppConfig) -> None:
        self._data = data
        self._config = config
        base = config.base_currency
        as_of = yearmonth_label(data.as_of)
        self.net_worth_card.set_values(
            fmt_money(data.net_worth_usd, base),
            f"As of {as_of}" if data.as_of else "No account data loaded",
        )
        self.income_card.set_values(
            fmt_money(data.income_12m_usd, base),
            "Income paid out of accounts (distributions)",
        )

        warnings = data.load_errors + data.fx_warnings
        if warnings:
            self._banner.setText(" • ".join(warnings))
            self._banner.show()
        else:
            self._banner.hide()

        self._rebuild_table(data, config)
        self.chart.plot_series(data.net_worth_series, f"Net worth ({base})", color=TEAL)
        self._rebuild_bucket_charts(data, base)

    def _rebuild_table(self, data: DashboardData, config: AppConfig) -> None:
        columns: list[tuple[str, str]] = [
            ("bucket", "Bucket"),
            ("size", "Size"),
            ("size_tgt", "Target size"),
            ("ret", "Return 12m"),
            ("ret_tgt", "Target return"),
            ("yield", "Yield 12m"),
            ("yield_tgt", "Target yield"),
            ("income", "Income 12m"),
            ("vol", "Volatility 5y"),
            ("vol_tgt", "Target vol"),
            ("dd", "Max DD 5y"),
            ("dd_tgt", "Target max DD"),
        ]
        keys = [key for key, _ in columns]
        headers = [label for _, label in columns]
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(data.buckets))

        base = config.base_currency
        for row, bucket in enumerate(data.buckets):
            for col, key in enumerate(keys):
                item: QTableWidgetItem
                if key == "bucket":
                    item = QTableWidgetItem(bucket.name)
                elif key == "size":
                    text = f"{fmt_pct(bucket.size_pct)}  ({fmt_money(bucket.size_usd, base)})"
                    item = colored_item(text, allocation_color(bucket.size_pct, bucket.target_allocation))
                elif key == "size_tgt":
                    item = colored_item(fmt_pct(bucket.target_allocation), MUTED)
                elif key == "ret":
                    item = colored_item(
                        fmt_pct(bucket.return_12m, signed=True),
                        comparison_color(bucket.return_12m, bucket.target_return, True),
                    )
                elif key == "ret_tgt":
                    item = colored_item(fmt_pct(bucket.target_return), MUTED)
                elif key == "yield":
                    if not bucket.has_yield_target:
                        item = colored_item("—", MUTED)
                    else:
                        item = colored_item(
                            fmt_pct(bucket.yield_12m),
                            comparison_color(bucket.yield_12m, bucket.target_income_yield, True),
                        )
                elif key == "yield_tgt":
                    item = colored_item(fmt_pct(bucket.target_income_yield), MUTED)
                elif key == "income":
                    item = colored_item(fmt_money(bucket.income_12m_usd, base))
                elif key == "vol":
                    item = colored_item(
                        fmt_pct(bucket.volatility_5y),
                        comparison_color(bucket.volatility_5y, bucket.target_volatility, False),
                    )
                elif key == "vol_tgt":
                    item = colored_item(fmt_pct(bucket.target_volatility), MUTED)
                elif key == "dd":
                    item = colored_item(
                        fmt_drawdown(bucket.max_drawdown_5y),
                        comparison_color(bucket.max_drawdown_5y, bucket.target_max_drawdown, False),
                    )
                elif key == "dd_tgt":
                    item = colored_item(fmt_drawdown(bucket.target_max_drawdown), MUTED)
                else:
                    item = QTableWidgetItem("")
                self.table.setItem(row, col, item)
            self.table.setRowHeight(row, 28)

        self._fit_table_to_contents()

    def _fit_table_to_contents(self) -> None:
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()
        for column in range(self.table.columnCount()):
            width = self.table.columnWidth(column)
            self.table.setColumnWidth(column, width + 12)
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(column, self.table.columnWidth(column))
        header_h = self.table.horizontalHeader().height()
        rows_h = sum(self.table.rowHeight(row) for row in range(self.table.rowCount()))
        frame = self.table.frameWidth() * 2
        self.table.setFixedHeight(header_h + rows_h + frame + 4)
        total_w = sum(self.table.columnWidth(column) for column in range(self.table.columnCount()))
        self.table.setMinimumWidth(total_w + 24)

    def _rebuild_bucket_charts(self, data: DashboardData, base: str) -> None:
        while self._bucket_charts:
            widget = self._bucket_charts.pop()
            self._bucket_charts_box.removeWidget(widget)
            widget.deleteLater()

        for index, bucket in enumerate(data.buckets):
            title = f"{bucket.name} — total balance ({base})"
            chart = LineChart(title, height=4.8)
            chart.setMinimumHeight(400)
            series = data.bucket_series.get(bucket.name)
            color = _BUCKET_CHART_COLORS[index % len(_BUCKET_CHART_COLORS)]
            chart.plot_series(series, f"Balance ({base})", color=color)
            self._bucket_charts_box.addWidget(chart)
            self._bucket_charts.append(chart)
