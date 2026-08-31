"""Fill missing monthly rows by linear interpolation between known months."""

from __future__ import annotations

import pandas as pd

from investment_tracker.dates import period_range, to_period, to_yyyymm

NUMERIC_COLUMNS = ("contribution", "withdrawal", "distribution", "balance")


def fill_missing_months(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with every month between the first and last row filled.

    Known rows are kept as-is. Missing months are linearly interpolated
    from the nearest surrounding known months (the request's "extrapolate
    from the closest filled-in months" for gaps inside the series).
    """
    if frame.empty:
        return frame.copy()

    work = frame.copy()
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
    return work[["yearmonth", *NUMERIC_COLUMNS]]
