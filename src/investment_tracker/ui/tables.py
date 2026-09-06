"""Size Qt tables to header and cell text so labels are not cropped."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont, QFontMetrics, QResizeEvent
from PySide6.QtWidgets import (
    QHeaderView,
    QSizePolicy,
    QStyle,
    QStyleOptionHeader,
    QTableWidget,
)

# Matches QHeaderView::section padding in styles.py (18px each side) plus slack
# for bold glyphs that overhang the font metrics box.
HEADER_PAD_X = 52
CELL_PAD_X = 36
HEADER_PAD_Y = 18
HEADER_PIXEL_SIZE = 14


def _header_font(header: QHeaderView) -> QFont:
    font = QFont(header.font())
    font.setBold(True)
    font.setPixelSize(max(font.pixelSize(), HEADER_PIXEL_SIZE) if font.pixelSize() > 0 else HEADER_PIXEL_SIZE)
    return font


def _text_width(metrics: QFontMetrics, text: str) -> int:
    return max(metrics.horizontalAdvance(text), metrics.boundingRect(text).width())


def header_section_width(header: QHeaderView, text: str) -> int:
    """Width Qt needs to paint a header label, including style padding."""
    header.ensurePolished()
    font = _header_font(header)
    header.setFont(font)
    metrics = QFontMetrics(font)
    option = QStyleOptionHeader()
    option.initFrom(header)
    option.text = text
    option.fontMetrics = metrics
    option.orientation = Qt.Orientation.Horizontal
    option.textAlignment = Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
    option.position = QStyleOptionHeader.SectionPosition.Middle
    content = QSize(_text_width(metrics, text), metrics.height())
    styled = header.style().sizeFromContents(
        QStyle.ContentsType.CT_HeaderSection, option, content, header
    )
    return max(styled.width(), _text_width(metrics, text) + HEADER_PAD_X, 56) + 12


class FittedTable(QTableWidget):
    """Table that keeps fitted column widths when the parent layout resizes it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._locked_widths: list[int] = []

    def lock_column_widths(self, widths: list[int]) -> None:
        self._locked_widths = [int(width) for width in widths]
        self._restore_widths()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._restore_widths()

    def _restore_widths(self) -> None:
        if not self._locked_widths:
            return
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        for col, width in enumerate(self._locked_widths):
            if col >= self.columnCount():
                break
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            if self.columnWidth(col) != width:
                self.setColumnWidth(col, width)


def fit_columns(table: QTableWidget) -> int:
    """Set each column width to the wider of its header or cells. Returns total width."""
    table.ensurePolished()
    header = table.horizontalHeader()
    header.ensurePolished()
    header.setFont(_header_font(header))
    header.setStretchLastSection(False)
    header.setTextElideMode(Qt.TextElideMode.ElideNone)
    header.setMinimumSectionSize(48)
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
    table.setWordWrap(False)
    table.setTextElideMode(Qt.TextElideMode.ElideNone)

    cell_fm = QFontMetrics(table.font())
    widths: list[int] = []
    for col in range(table.columnCount()):
        header_item = table.horizontalHeaderItem(col)
        if header_item is not None:
            text = header_item.text()
        else:
            model = header.model()
            text = model.headerData(col, Qt.Orientation.Horizontal) if model is not None else ""
        text = str(text or "")
        width = header_section_width(header, text)
        for row in range(table.rowCount()):
            cell = table.item(row, col)
            if cell is None or not cell.text():
                continue
            width = max(width, _text_width(cell_fm, cell.text()) + CELL_PAD_X)
            hint = table.sizeHintForColumn(col)
            if hint > 0:
                width = max(width, hint + 12)
        header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(col, width)
        widths.append(width)

    if isinstance(table, FittedTable):
        table.lock_column_widths(widths)
    return sum(widths)


def fit_height(table: QTableWidget, extra: int = 6) -> None:
    """Fix table height to the header plus every row, without clipping the header."""
    header = table.horizontalHeader()
    header.setFont(_header_font(header))
    header_h = max(header.sizeHint().height(), QFontMetrics(_header_font(header)).height() + HEADER_PAD_Y)
    header.setMinimumHeight(header_h)
    header.setFixedHeight(header_h)
    rows = table.rowCount()
    row_h = table.verticalHeader().defaultSectionSize() or 26
    if rows:
        hinted = table.sizeHintForRow(0)
        if hinted > 0:
            row_h = max(row_h, hinted)
        widget = table.cellWidget(0, 0) if table.columnCount() else None
        if widget is not None:
            row_h = max(row_h, widget.sizeHint().height() + 8)
    frame = table.frameWidth() * 2
    table.setFixedHeight(header_h + row_h * max(rows, 1) + frame + extra)


def shrink_wrap(table: QTableWidget) -> None:
    """Size the widget to its columns and rows so it does not stretch across the window."""
    total = fit_columns(table)
    widths = [table.columnWidth(col) for col in range(table.columnCount())]
    fit_height(table)
    vertical = table.verticalHeader()
    extra = table.frameWidth() * 2 + 8
    if vertical.isVisible():
        extra += max(vertical.width(), vertical.sizeHint().width())
    table.setFixedWidth(total + extra)
    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    for col, width in enumerate(widths):
        header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(col, width)
    if isinstance(table, FittedTable):
        table.lock_column_widths(widths)
    table.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


def fit_allocation_table(table: QTableWidget) -> None:
    """Include / Account / Target % of bucket: keep the % column readable."""
    table.ensurePolished()
    header = table.horizontalHeader()
    header.ensurePolished()
    header.setFont(_header_font(header))
    header.setStretchLastSection(False)
    header.setTextElideMode(Qt.TextElideMode.ElideNone)
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
    table.setWordWrap(False)
    table.setTextElideMode(Qt.TextElideMode.ElideNone)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    include_w = header_section_width(header, "Include")
    account_w = header_section_width(header, "Account")
    target_w = header_section_width(header, "Target % of bucket")
    cell_fm = QFontMetrics(table.font())
    for row in range(table.rowCount()):
        name = table.item(row, 1)
        if name is not None:
            account_w = max(account_w, _text_width(cell_fm, name.text()) + CELL_PAD_X)
        widget = table.cellWidget(row, 2)
        if widget is not None:
            target_w = max(target_w, widget.sizeHint().width() + 24)
            table.setRowHeight(row, max(table.rowHeight(row), widget.sizeHint().height() + 8))

    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
    extra = table.frameWidth() * 2 + 8
    table.setMinimumWidth(include_w + account_w + target_w + extra)
    fit_height(table, extra=8)
    header.setStretchLastSection(False)
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
    table.setColumnWidth(0, include_w)
    table.setColumnWidth(2, target_w)
