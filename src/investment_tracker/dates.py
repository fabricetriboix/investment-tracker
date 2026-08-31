"""Year-month helpers. CSV yearmonth values are integers like 202403."""

from __future__ import annotations

from datetime import date

import pandas as pd


def to_period(yearmonth: int | str | float) -> pd.Period:
    text = str(int(float(yearmonth)))
    if len(text) != 6:
        raise ValueError(f"yearmonth must be YYYYMM, got {yearmonth!r}")
    year, month = int(text[:4]), int(text[4:])
    if month < 1 or month > 12:
        raise ValueError(f"invalid month in yearmonth {yearmonth!r}")
    return pd.Period(year=year, month=month, freq="M")


def to_yyyymm(period: pd.Period) -> int:
    return int(period.strftime("%Y%m"))


def month_end(period: pd.Period) -> date:
    return period.to_timestamp(how="end").date()


def period_range(start: pd.Period, end: pd.Period) -> pd.PeriodIndex:
    return pd.period_range(start=start, end=end, freq="M")
