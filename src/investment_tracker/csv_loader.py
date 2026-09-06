"""Read and write account CSV files named ``ACCOUNT CURRENCY.csv``."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from investment_tracker.dates import to_period, to_yyyymm
from investment_tracker.interpolation import (
    NUMERIC_COLUMNS,
    apply_opening_row,
    fill_missing_months,
)

FILENAME_PATTERN = re.compile(r"^(?P<name>.+)\s+(?P<currency>[A-Za-z]{3})\.csv$", re.IGNORECASE)
CORE_COLUMNS = ("yearmonth", "contribution", "withdrawal", "balance")
COLUMNS = ("yearmonth", "contribution", "withdrawal", "distribution", "balance")
TYPE_ACCUMULATION = "accumulation"
TYPE_DISTRIBUTION = "distribution"


class CsvError(Exception):
    pass


@dataclass
class Account:
    name: str
    currency: str
    path: Path
    raw: pd.DataFrame
    filled: pd.DataFrame
    account_type: str = TYPE_DISTRIBUTION
    issues: list[str] = field(default_factory=list)

    @property
    def pays_income(self) -> bool:
        return self.account_type == TYPE_DISTRIBUTION

    @property
    def type_label(self) -> str:
        return "Distribution" if self.pays_income else "Accumulation"

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


def detect_account_type(columns: list[str]) -> str:
    incoming = {str(col).strip().lower() for col in columns}
    if "distribution" in incoming:
        return TYPE_DISTRIBUTION
    return TYPE_ACCUMULATION


def _normalise_frame(frame: pd.DataFrame, path: Path) -> tuple[pd.DataFrame, str]:
    incoming = {str(col).strip().lower(): col for col in frame.columns}
    account_type = detect_account_type(list(frame.columns))
    missing = [col for col in CORE_COLUMNS if col not in incoming]
    if missing:
        raise CsvError(f"{path.name}: missing columns {missing}")

    work = pd.DataFrame()
    for column in CORE_COLUMNS:
        work[column] = frame[incoming[column]]
    if account_type == TYPE_DISTRIBUTION:
        work["distribution"] = frame[incoming["distribution"]]
    else:
        work["distribution"] = 0.0

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
        return pd.DataFrame(columns=list(COLUMNS)), account_type

    work = pd.DataFrame(valid_rows).sort_values("yearmonth")
    work = work.drop_duplicates("yearmonth", keep="last").reset_index(drop=True)
    work["yearmonth"] = work["yearmonth"].astype(int)
    work = apply_opening_row(work)
    return work[list(COLUMNS)], account_type


def load_account(path: Path) -> Account:
    name, currency = parse_filename(path)
    try:
        frame = pd.read_csv(path)
    except Exception as exc:  # noqa: BLE001 — surface any parse failure to the UI
        raise CsvError(f"{path.name}: could not read file ({exc})") from exc
    raw, account_type = _normalise_frame(frame, path)
    filled = fill_missing_months(raw)
    return Account(
        name=name,
        currency=currency,
        path=path,
        raw=raw,
        filled=filled,
        account_type=account_type,
    )


def output_columns(account_type: str) -> list[str]:
    if account_type == TYPE_ACCUMULATION:
        return list(CORE_COLUMNS)
    return list(COLUMNS)


def save_account(path: Path, frame: pd.DataFrame, account_type: str | None = None) -> None:
    work, detected = _normalise_frame(frame, path)
    account_type = account_type or detected
    work = work.sort_values("yearmonth")
    formatted = work.copy()
    formatted["yearmonth"] = formatted["yearmonth"].map(lambda value: f"{int(value):06d}")
    formatted[output_columns(account_type)].to_csv(path, index=False, float_format="%.2f")


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
