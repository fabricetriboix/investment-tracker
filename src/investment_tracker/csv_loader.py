"""Read and write account CSV files named ``ACCOUNT CURRENCY.csv``."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from investment_tracker.dates import to_period, to_yyyymm
from investment_tracker.interpolation import NUMERIC_COLUMNS, fill_missing_months

FILENAME_PATTERN = re.compile(r"^(?P<name>.+)\s+(?P<currency>[A-Za-z]{3})\.csv$", re.IGNORECASE)
COLUMNS = ("yearmonth", "contribution", "withdrawal", "distribution", "balance")


class CsvError(Exception):
    pass


@dataclass
class Account:
    name: str
    currency: str
    path: Path
    raw: pd.DataFrame
    filled: pd.DataFrame
    issues: list[str] = field(default_factory=list)

    @property
    def latest_balance(self) -> float:
        if self.filled.empty:
            return 0.0
        return float(self.filled.sort_values("yearmonth")["balance"].iloc[-1])


def parse_filename(path: Path) -> tuple[str, str]:
    match = FILENAME_PATTERN.match(path.name)
    if not match:
        raise CsvError(
            f"{path.name}: expected 'ACCOUNT CURRENCY.csv' (currency is a 3-letter code)"
        )
    return match.group("name").strip(), match.group("currency").upper()


def _normalise_frame(frame: pd.DataFrame, path: Path) -> pd.DataFrame:
    incoming = {str(col).strip().lower(): col for col in frame.columns}
    missing = [col for col in COLUMNS if col not in incoming]
    if missing:
        raise CsvError(f"{path.name}: missing columns {missing}")

    work = pd.DataFrame()
    for column in COLUMNS:
        work[column] = frame[incoming[column]]

    work["yearmonth"] = pd.to_numeric(work["yearmonth"], errors="coerce")
    for column in NUMERIC_COLUMNS:
        work[column] = pd.to_numeric(work[column], errors="coerce")

    work = work.dropna(subset=["yearmonth"])
    work["yearmonth"] = work["yearmonth"].astype(int)
    for column in NUMERIC_COLUMNS:
        work[column] = work[column].fillna(0.0)

    valid_rows = []
    for _, row in work.iterrows():
        try:
            to_period(int(row["yearmonth"]))
        except ValueError:
            continue
        valid_rows.append(row)
    if not valid_rows:
        return pd.DataFrame(columns=list(COLUMNS))

    work = pd.DataFrame(valid_rows).sort_values("yearmonth")
    work = work.drop_duplicates("yearmonth", keep="last").reset_index(drop=True)
    work["yearmonth"] = work["yearmonth"].astype(int)
    return work[list(COLUMNS)]


def load_account(path: Path) -> Account:
    name, currency = parse_filename(path)
    try:
        frame = pd.read_csv(path)
    except Exception as exc:  # noqa: BLE001 — surface any parse failure to the UI
        raise CsvError(f"{path.name}: could not read file ({exc})") from exc
    raw = _normalise_frame(frame, path)
    filled = fill_missing_months(raw)
    return Account(name=name, currency=currency, path=path, raw=raw, filled=filled)


def save_account(path: Path, frame: pd.DataFrame) -> None:
    work = _normalise_frame(frame, path)
    work = work.sort_values("yearmonth")
    formatted = work.copy()
    formatted["yearmonth"] = formatted["yearmonth"].map(lambda value: f"{int(value):06d}")
    formatted.to_csv(path, index=False, float_format="%.2f")


def load_directory(directory: Path) -> tuple[list[Account], list[str]]:
    accounts: list[Account] = []
    errors: list[str] = []
    if not directory.is_dir():
        return accounts, [f"Data directory does not exist: {directory}"]

    paths = sorted(directory.glob("*.csv"), key=lambda item: item.name.lower())
    for path in paths:
        if path.name.startswith("."):
            continue
        try:
            accounts.append(load_account(path))
        except CsvError as exc:
            errors.append(str(exc))
    return accounts, errors


def empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=list(COLUMNS))


def next_yearmonth(frame: pd.DataFrame) -> int:
    if frame.empty:
        today = pd.Timestamp.today()
        return int(today.strftime("%Y%m"))
    last = to_period(int(frame["yearmonth"].max()))
    return to_yyyymm(last + 1)
