"""Shared formatting helpers for the UI."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QTableWidgetItem

from investment_tracker.ui.styles import AMBER, MUTED, NEGATIVE, POSITIVE


def fmt_money(value: float | None, currency: str = "USD", decimals: int = 0) -> str:
    if value is None:
        return "—"
    if decimals == 0:
        return f"{currency} {value:,.0f}"
    return f"{currency} {value:,.{decimals}f}"


def fmt_pct(value: float | None, digits: int = 1, signed: bool = False) -> str:
    if value is None:
        return "—"
    percent = value * 100.0
    if signed:
        return f"{percent:+.{digits}f}%"
    return f"{percent:.{digits}f}%"


def fmt_drawdown(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{abs(value) * 100.0:.1f}%"


def yearmonth_label(value: int | None) -> str:
    if not value:
        return "—"
    text = f"{int(value):06d}"
    return f"{text[:4]}-{text[4:]}"


def comparison_color(actual: float | None, target: float | None, higher_is_better: bool) -> str:
    if actual is None or target is None:
        return MUTED
    if higher_is_better:
        if actual >= target:
            return POSITIVE
        if actual >= target * 0.85:
            return AMBER
        return NEGATIVE
    # lower is better (volatility, drawdown magnitude)
    actual_mag = abs(actual)
    target_mag = abs(target)
    if actual_mag <= target_mag:
        return POSITIVE
    if actual_mag <= target_mag * 1.15:
        return AMBER
    return NEGATIVE


def allocation_color(actual: float | None, target: float | None) -> str:
    if actual is None or target is None:
        return MUTED
    gap = abs(actual - target)
    if gap <= 0.02:
        return POSITIVE
    if gap <= 0.05:
        return AMBER
    return NEGATIVE


def colored_item(text: str, color: str | None = None, align_right: bool = True) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    if align_right:
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if color:
        item.setForeground(QBrush(QColor(color)))
    return item
