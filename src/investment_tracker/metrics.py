"""Performance statistics that strip contributions, withdrawals and distributions.

Monthly price return
--------------------
The ending ``balance`` is treated as the account value *after* deposits,
withdrawals and paid-out distributions for that month. Deposits inflate
the ending balance; withdrawals and distributions have already left.

    r_t = (balance_t - contribution_t + withdrawal_t) / balance_{t-1} - 1

Distributions are **not** added back, so the 10,000 growth series is a
price-return (capital appreciation) path, not a total-return path.

If income is reinvested it never appears in ``distribution`` and instead
moves ``balance``, which is then reflected in r_t.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

INDEX_START = 10_000.0


def monthly_price_returns(frame: pd.DataFrame) -> pd.Series:
    """Return monthly price returns indexed by yearmonth (first month is NaN)."""
    if frame.empty:
        return pd.Series(dtype=float)

    work = frame.sort_values("yearmonth").reset_index(drop=True)
    prev_balance = work["balance"].shift(1)
    end_ex_cash = work["balance"] - work["contribution"] + work["withdrawal"]
    returns = end_ex_cash / prev_balance - 1.0
    returns = returns.where(prev_balance > 0)
    returns.index = work["yearmonth"]
    returns.name = "return"
    return returns


def growth_of_index(returns: pd.Series, start: float = INDEX_START) -> pd.Series:
    """Compound monthly returns into a growth-of-10,000 series."""
    if returns.empty:
        return pd.Series(dtype=float)
    growth = pd.Series(index=returns.index, dtype=float)
    value = start
    for yearmonth, ret in returns.items():
        if pd.isna(ret):
            growth.loc[yearmonth] = value
        else:
            value = value * (1.0 + float(ret))
            growth.loc[yearmonth] = value
    growth.name = "index"
    return growth


def _window_slice(series: pd.Series, months: int | None) -> pd.Series:
    series = series.dropna()
    if months is None or len(series) <= months:
        return series
    return series.iloc[-months:]


def cagr(returns: pd.Series, months: int | None = None) -> float | None:
    """Compounded annual growth rate from monthly price returns."""
    window = _window_slice(returns, months)
    if window.empty:
        return None
    total = float((1.0 + window).prod())
    n = len(window)
    if n <= 0 or total <= 0:
        return None
    return total ** (12.0 / n) - 1.0


def volatility(returns: pd.Series, months: int | None = None) -> float | None:
    """Annualised standard deviation of monthly returns (* sqrt(12)).

    Target volatilities in the config are annual figures (for example 15%),
    so the displayed statistic is annualised. The underlying series is the
    sample standard deviation of monthly price returns.
    """
    window = _window_slice(returns, months)
    if len(window) < 2:
        return None
    monthly_std = float(window.std(ddof=1))
    if np.isnan(monthly_std):
        return None
    return monthly_std * np.sqrt(12.0)


def max_drawdown(index: pd.Series, months: int | None = None) -> float | None:
    """Maximum peak-to-trough decline, as a negative fraction (e.g. -0.23)."""
    if index.empty:
        return None
    work = index.dropna()
    if months is not None and len(work) > months + 1:
        # Keep one extra point so a drawdown can start at the window edge.
        work = work.iloc[-(months + 1) :]
    if work.empty:
        return None
    running_peak = work.cummax()
    drawdown = work / running_peak - 1.0
    value = float(drawdown.min())
    if np.isnan(value):
        return None
    return value


def skip_opening_row(frame: pd.DataFrame) -> pd.DataFrame:
    """Drop the opening-balance row (earliest yearmonth) from income stats."""
    if frame.empty or len(frame) < 2:
        return frame.iloc[0:0].copy() if not frame.empty else frame.copy()
    return frame.sort_values("yearmonth").iloc[1:]


def mean_yield_ratio(frame: pd.DataFrame, months: int | None = None) -> float | None:
    """Simple average of distribution / balance over the window."""
    if frame.empty:
        return None
    work = skip_opening_row(frame)
    if work.empty:
        return None
    if months is not None:
        work = work.tail(months)
    balances = work["balance"].replace(0, np.nan)
    ratios = work["distribution"] / balances
    ratios = ratios.dropna()
    if ratios.empty:
        return None
    return float(ratios.mean())


def mean_distribution_amount(frame: pd.DataFrame, months: int | None = None) -> float | None:
    if frame.empty:
        return None
    work = skip_opening_row(frame)
    if work.empty:
        return None
    if months is not None:
        work = work.tail(months)
    if work.empty:
        return None
    return float(work["distribution"].mean())


def trailing_income(frame: pd.DataFrame, months: int = 12) -> float:
    if frame.empty:
        return 0.0
    work = skip_opening_row(frame)
    if work.empty:
        return 0.0
    work = work.sort_values("yearmonth").tail(months)
    return float(work["distribution"].sum())


@dataclass(frozen=True)
class PeriodStats:
    label: str
    months: int | None
    cagr: float | None
    volatility: float | None
    max_drawdown: float | None
    mean_yield_pct: float | None
    mean_yield_amount: float | None


PERIODS: tuple[tuple[str, int | None], ...] = (
    ("3 months", 3),
    ("6 months", 6),
    ("12 months", 12),
    ("Since beginning", None),
)


def account_stats(frame: pd.DataFrame, include_yield: bool = True) -> list[PeriodStats]:
    returns = monthly_price_returns(frame)
    index = growth_of_index(returns)
    stats: list[PeriodStats] = []
    for label, months in PERIODS:
        stats.append(
            PeriodStats(
                label=label,
                months=months,
                cagr=cagr(returns, months),
                volatility=volatility(returns, months),
                max_drawdown=max_drawdown(index, months),
                mean_yield_pct=mean_yield_ratio(frame, months) if include_yield else None,
                mean_yield_amount=mean_distribution_amount(frame, months) if include_yield else None,
            )
        )
    return stats
