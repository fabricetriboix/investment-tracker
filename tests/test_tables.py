from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem

from investment_tracker.ui.styles import APP_STYLESHEET
from investment_tracker.ui.tables import (
    FittedTable,
    fit_allocation_table,
    fit_columns,
    header_section_width,
    shrink_wrap,
)


def _app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        existing.setStyleSheet(APP_STYLESHEET)
        return existing
    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)
    return app


def test_fit_columns_covers_styled_header():
    _app()
    table = FittedTable()
    table.setColumnCount(3)
    table.setRowCount(2)
    headers = ["Income 12m", "Volatility 5y", "Target max DD"]
    table.setHorizontalHeaderLabels(headers)
    table.setItem(0, 0, QTableWidgetItem("USD 2,131"))
    table.setItem(0, 1, QTableWidgetItem("12.1%"))
    table.setItem(0, 2, QTableWidgetItem("35.0%"))
    table.setItem(1, 0, QTableWidgetItem("USD 1,000"))
    table.setItem(1, 1, QTableWidgetItem("7.3%"))
    table.setItem(1, 2, QTableWidgetItem("18.0%"))
    table.resize(400, 120)
    fit_columns(table)
    table.resize(360, 120)
    header = table.horizontalHeader()
    for col, title in enumerate(headers):
        needed = header_section_width(header, title)
        assert table.columnWidth(col) >= needed, f"{title}: {table.columnWidth(col)} < {needed}"
        assert table.columnWidth(col) == table._locked_widths[col]


def test_shrink_wrap_stats_table_is_not_window_wide():
    _app()
    table = QTableWidget(4, 4)
    table.setHorizontalHeaderLabels(["Period", "CAGR", "Volatility (ann.)", "Max drawdown"])
    table.setItem(0, 0, QTableWidgetItem("3 months"))
    table.setItem(1, 0, QTableWidgetItem("6 months"))
    table.setItem(2, 0, QTableWidgetItem("12 months"))
    table.setItem(3, 0, QTableWidgetItem("Since beginning"))
    for row in range(4):
        for col in range(1, 4):
            table.setItem(row, col, QTableWidgetItem("+1.2%"))
    shrink_wrap(table)
    assert table.width() < 900
    header = table.horizontalHeader()
    assert table.columnWidth(0) >= header_section_width(header, "Period")
    assert table.columnWidth(3) >= header_section_width(header, "Max drawdown")
    cell_w = table.fontMetrics().horizontalAdvance("Since beginning")
    assert table.columnWidth(0) >= cell_w + 8


def test_folder_table_keeps_target_and_bucket_columns_readable():
    _app()
    table = QTableWidget(3, 3)
    table.setHorizontalHeaderLabels(["Folder", "Bucket", "Target % of bucket"])
    table.verticalHeader().setVisible(False)
    for row, name in enumerate(["Cash", "International", "Global equity"]):
        table.setItem(row, 0, QTableWidgetItem(name))
        combo = QComboBox()
        combo.addItems(["Unassigned", "Equities", "Income"])
        table.setCellWidget(row, 1, combo)
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 100.0)
        spin.setSuffix(" %")
        spin.setMinimumWidth(120)
        table.setCellWidget(row, 2, spin)
    table.resize(900, 200)
    fit_allocation_table(table, stretch_column=None)
    header = table.horizontalHeader()
    assert table.width() < 700
    cell_w = table.fontMetrics().horizontalAdvance("Global equity")
    assert cell_w <= table.columnWidth(0) <= cell_w + header_section_width(header, "Folder")
    assert table.columnWidth(2) >= header_section_width(header, "Target % of bucket")
    assert table.columnWidth(2) >= 120
    assert table.columnWidth(1) >= header_section_width(header, "Bucket")
    assert table.columnWidth(0) >= header_section_width(header, "Folder")
    rows_h = sum(table.rowHeight(row) for row in range(table.rowCount()))
    assert table.height() >= header.height() + rows_h
