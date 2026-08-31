from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from investment_tracker.config import (
    AccountAllocation,
    AppConfig,
    Bucket,
    default_first_run_config,
)
from investment_tracker.csv_loader import Account, load_directory
from investment_tracker.interpolation import fill_missing_months
from investment_tracker.portfolio import build_dashboard


class _FakeFx:
    def __init__(self):
        self.warnings: list[str] = []

    def prefetch(self, currencies, start, end, base="USD"):
        self.warnings = []

    def convert(self, amount, from_ccy, to_ccy, yearmonth):
        if from_ccy == to_ccy:
            return float(amount)
        rates = {"GBP": 1.30, "CAD": 0.74, "EUR": 1.10}
        return float(amount) * rates.get(from_ccy, 1.0)


def _account(name: str, currency: str, rows: list[dict]) -> Account:
    raw = pd.DataFrame(rows)
    return Account(
        name=name,
        currency=currency,
        path=Path(f"{name} {currency}.csv"),
        raw=raw,
        filled=fill_missing_months(raw),
    )


def test_dashboard_from_examples():
    examples = Path(__file__).resolve().parents[1] / "examples"
    accounts, errors = load_directory(examples)
    assert not errors
    assert len(accounts) == 7
    isa = next(item for item in accounts if item.name == "UK Stocks ISA")
    assert len(isa.filled) == len(isa.raw) + 2

    config = default_first_run_config()
    data = build_dashboard(accounts, config, _FakeFx())
    assert data.net_worth_usd > 0
    assert data.income_12m_usd > 0
    assert not data.net_worth_series.empty
    names = {bucket.name for bucket in data.buckets}
    assert names == {"Equities", "Income", "Cash"}
    equities = next(item for item in data.buckets if item.name == "Equities")
    assert equities.size_pct and equities.size_pct > 0.4
    income = next(item for item in data.buckets if item.name == "Income")
    assert income.has_yield_target
    assert income.yield_12m is not None
    total_pct = sum(bucket.size_pct or 0.0 for bucket in data.buckets)
    assert total_pct == pytest.approx(1.0, abs=0.02)
    assert data.net_worth_usd == pytest.approx(
        sum(bucket.size_usd for bucket in data.buckets), rel=0.01
    )
    assert set(data.bucket_series) == names
    for name, series in data.bucket_series.items():
        assert not series.empty


def test_staggered_end_dates_do_not_drop_accounts():
    """A newer month on one account must not zero out the rest of the portfolio."""
    older = _account(
        "Older",
        "USD",
        [
            {
                "yearmonth": 202401,
                "contribution": 0,
                "withdrawal": 0,
                "distribution": 0,
                "balance": 1000,
            },
            {
                "yearmonth": 202402,
                "contribution": 0,
                "withdrawal": 0,
                "distribution": 0,
                "balance": 1000,
            },
        ],
    )
    newer = _account(
        "Newer",
        "USD",
        [
            {
                "yearmonth": 202401,
                "contribution": 0,
                "withdrawal": 0,
                "distribution": 0,
                "balance": 1000,
            },
            {
                "yearmonth": 202402,
                "contribution": 0,
                "withdrawal": 0,
                "distribution": 0,
                "balance": 1000,
            },
            {
                "yearmonth": 202403,
                "contribution": 0,
                "withdrawal": 0,
                "distribution": 0,
                "balance": 1000,
            },
        ],
    )
    config = AppConfig(
        buckets=[
            Bucket(
                name="A",
                target_allocation=50.0,
                accounts=[AccountAllocation("Older", 100.0)],
            ),
            Bucket(
                name="B",
                target_allocation=50.0,
                accounts=[AccountAllocation("Newer", 100.0)],
            ),
        ]
    )
    data = build_dashboard([older, newer], config, _FakeFx())
    assert data.as_of == 202403
    assert data.net_worth_usd == pytest.approx(2000.0)
    assert data.net_worth_series.loc[202403] == pytest.approx(2000.0)
    assert data.net_worth_series.loc[202401] == pytest.approx(2000.0)
    percents = {bucket.name: bucket.size_pct for bucket in data.buckets}
    assert percents["A"] == pytest.approx(0.5)
    assert percents["B"] == pytest.approx(0.5)
