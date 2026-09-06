"""Fill missing monthly rows by linear interpolation between known months."""

from __future__ import annotations

import pandas as pd

from investment_tracker.dates import period_range, to_period, to_yyyymm

NUMERIC_COLUMNS = ("contribution", "withdrawal", "distribution", "balance")
CASH_FLOW_COLUMNS = ("contribution", "withdrawal", "distribution")


def apply_opening_row(frame: pd.DataFrame) -> pd.DataFrame:
    """The earliest row is the opening balance: cash-flow columns are zero."""
    if frame.empty:
        return frame.copy()
    work = frame.sort_values("yearmonth").reset_index(drop=True)
    for column in CASH_FLOW_COLUMNS:
        if column in work.columns:
            work.loc[work.index[0], column] = 0.0
    return work


def fill_missing_months(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with every month between the first and last row filled.

    Known rows are kept as-is. Missing months are linearly interpolated
    from the nearest surrounding known months (the request's "extrapolate
    from the closest filled-in months" for gaps inside the series).
    """
    if frame.empty:
        empty = frame.copy()
        for column in NUMERIC_COLUMNS:
            if column not in empty.columns:
                empty[column] = []
        return empty

    work = frame.copy()
    if "distribution" not in work.columns:
        work["distribution"] = 0.0
    work = apply_opening_row(work)
    work["_period"] = work["yearmonth"].map(to_period)
    work = work.sort_values("_period").drop_duplicates("_period", keep="last")
    work = work.set_index("_period")

    full_index = period_range(work.index.min(), work.index.max())
    work = work.reindex(full_index)

    for column in NUMERIC_COLUMNS:
        if column in work.columns:
            work[column] = pd.to_numeric(work[column], errors="coerce")
            work[column] = work[column].interpolate(method="linear")

    work["yearmonth"] = [to_yyyymm(period) for period in work.index]
    work = work.reset_index(drop=True)
    work = apply_opening_row(work)
    return work[["yearmonth", *NUMERIC_COLUMNS]]
