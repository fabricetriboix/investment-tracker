"""Matplotlib canvases embedded in Qt."""

from __future__ import annotations

import matplotlib

matplotlib.use("QtAgg")

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter
import pandas as pd

from investment_tracker.dates import to_period
from investment_tracker.ui.styles import NAVY


def _yearmonth_to_timestamp(yearmonth: int) -> pd.Timestamp:
    return to_period(int(yearmonth)).to_timestamp()


class LineChart(FigureCanvasQTAgg):
    def __init__(self, title: str, parent=None, height: float = 2.8):
        self.figure = Figure(figsize=(7.2, height), dpi=100, facecolor="white")
        super().__init__(self.figure)
        self.setParent(parent)
        self.axes = self.figure.add_subplot(111)
        self._title = title
        self.figure.subplots_adjust(left=0.10, right=0.98, top=0.86, bottom=0.18)

    def plot_series(
        self,
        series: pd.Series,
        ylabel: str,
        color: str = NAVY,
    ) -> None:
        self.axes.clear()
        self.axes.set_title(
            self._title, loc="left", fontsize=13, color=NAVY, pad=8, fontweight="bold"
        )
        if series is None or series.empty:
            self.axes.text(
                0.5,
                0.5,
                "No data to chart",
                ha="center",
                va="center",
                transform=self.axes.transAxes,
                color="#7f8c8d",
            )
            self.axes.set_xticks([])
            self.axes.set_yticks([])
            self.draw()
            return

        xs = [_yearmonth_to_timestamp(int(idx)) for idx in series.index]
        ys = [float(value) for value in series.values]
        self.axes.plot(xs, ys, color=color, linewidth=1.8)
        self.axes.fill_between(xs, ys, color=color, alpha=0.08)
        self.axes.set_ylabel(ylabel, fontsize=11)
        self.axes.grid(True, axis="y", linestyle="--", alpha=0.35)
        self.axes.spines["top"].set_visible(False)
        self.axes.spines["right"].set_visible(False)
        self.axes.yaxis.set_major_formatter(FuncFormatter(lambda value, _pos: f"{value:,.0f}"))
        self.figure.autofmt_xdate(rotation=30, ha="right")
        self.draw()
