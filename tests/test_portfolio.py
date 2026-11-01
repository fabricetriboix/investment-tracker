from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from investment_tracker.config import (
    AppConfig,
    Bucket,
    Folder,
    default_first_run_config,
)
from investment_tracker.csv_loader import TYPE_ACCUMULATION, TYPE_DISTRIBUTION, Account, load_directory
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


def _account(name: str, currency: str, rows: list[dict], account_type: str = TYPE_DISTRIBUTION) -> Account:
    raw = pd.DataFrame(rows)
    if "distribution" not in raw.columns:
        raw["distribution"] = 0.0
    return Account(
        name=name,
        currency=currency,
        path=Path(f"{name} {currency}.csv"),
        raw=raw,
        filled=fill_missing_months(raw),
        account_type=account_type,
    )


def test_dashboard_from_examples():
    examples = Path(__file__).resolve().parents[1] / "examples"
    accounts, errors = load_directory(examples)
    assert not errors
    assert len(accounts) == 7
    by_name = {item.name: item for item in accounts}
    assert by_name["Workplace 401k"].account_type == TYPE_ACCUMULATION
    assert by_name["Canada TFSA"].account_type == TYPE_ACCUMULATION
    assert by_name["US Brokerage"].account_type == TYPE_DISTRIBUTION
    isa = by_name["UK Stocks ISA"]
    assert len(isa.filled) == len(isa.raw) + 2
    opening = by_name["Workplace 401k"].raw.iloc[0]
    assert opening["contribution"] == 0.0
    assert opening["withdrawal"] == 0.0
    assert opening["distribution"] == 0.0

    config = default_first_run_config()
    data = build_dashboard(accounts, config, _FakeFx())
    assert data.net_worth_usd > 0
    assert data.has_income
    assert data.income_12m_usd > 0
    assert not data.net_worth_series.empty
    assert set(data.bucket_series) == {"Equities", "Income", "Cash"}
    names = {bucket.name for bucket in data.buckets}
    assert names == {"Equities", "Income", "Cash"}
    equities = next(item for item in data.buckets if item.name == "Equities")
    assert equities.size_pct and equities.size_pct > 0.4
    assert equities.has_income
    assert equities.return_5y is not None
    assert equities.return_10y is not None
    income = next(item for item in data.buckets if item.name == "Income")
    assert income.has_yield_target
    assert income.has_income
    assert income.yield_12m is not None
    total_pct = sum(bucket.size_pct or 0.0 for bucket in data.buckets)
    assert total_pct == pytest.approx(1.0, abs=0.02)
    assert data.net_worth_usd == pytest.approx(
        sum(bucket.size_usd for bucket in data.buckets), rel=0.01
    )
    alloc_names = {block.name for block in data.allocations}
    assert alloc_names == {"Equities", "Income", "Cash"}
    equities_alloc = next(item for item in data.allocations if item.name == "Equities")
    by_asset = {asset.name: asset for asset in equities_alloc.assets}
    assert set(by_asset) == {"Global equity", "International"}
    assert by_asset["Global equity"].target_pct == pytest.approx(0.65)
    assert by_asset["International"].target_pct == pytest.approx(0.35)
    actual = sum(asset.size_pct or 0.0 for asset in equities_alloc.assets)
    assert actual == pytest.approx(1.0, abs=0.02)
    cash_alloc = next(item for item in data.allocations if item.name == "Cash")
    assert cash_alloc.assets[0].name == "Cash"
    assert cash_alloc.assets[0].target_pct == pytest.approx(1.0)


def test_accumulation_accounts_do_not_contribute_income():
    accum = _account(
        "Pension",
        "USD",
        [
            {"yearmonth": 202401, "contribution": 0, "withdrawal": 0, "distribution": 0, "balance": 1000},
            {"yearmonth": 202402, "contribution": 0, "withdrawal": 0, "distribution": 50, "balance": 1100},
        ],
        account_type=TYPE_ACCUMULATION,
    )
    paying = _account(
        "Brokerage",
        "USD",
        [
            {"yearmonth": 202401, "contribution": 0, "withdrawal": 0, "distribution": 0, "balance": 1000},
            {"yearmonth": 202402, "contribution": 0, "withdrawal": 0, "distribution": 20, "balance": 1100},
        ],
        account_type=TYPE_DISTRIBUTION,
    )
    config = AppConfig(
        buckets=[
            Bucket(name="Acc", target_allocation=50.0),
            Bucket(name="Dist", target_allocation=50.0, target_income_yield=4.0),
        ],
        folders=[
            Folder("Pensions", "Acc", 100.0, ["Pension"]),
            Folder("Brokerages", "Dist", 100.0, ["Brokerage"]),
        ],
    )
    data = build_dashboard([accum, paying], config, _FakeFx())
    assert data.has_income
    assert data.income_12m_usd == pytest.approx(20.0)
    acc_bucket = next(item for item in data.buckets if item.name == "Acc")
    dist_bucket = next(item for item in data.buckets if item.name == "Dist")
    assert not acc_bucket.has_income
    assert acc_bucket.income_12m_usd == 0.0
    assert acc_bucket.yield_12m is None
    assert dist_bucket.has_income
    assert dist_bucket.income_12m_usd == pytest.approx(20.0)


def test_portfolio_without_distributing_accounts_hides_income():
    accum = _account(
        "Pension",
        "USD",
        [
            {"yearmonth": 202401, "contribution": 0, "withdrawal": 0, "distribution": 0, "balance": 1000},
            {"yearmonth": 202402, "contribution": 50, "withdrawal": 0, "distribution": 0, "balance": 1100},
        ],
        account_type=TYPE_ACCUMULATION,
    )
    config = AppConfig(
        buckets=[Bucket(name="Retirement", target_allocation=100.0)],
        folders=[Folder("Pensions", "Retirement", 100.0, ["Pension"])],
    )
    data = build_dashboard([accum], config, _FakeFx())
    assert not data.has_income
    assert data.income_12m_usd == 0.0
    assert data.buckets[0].has_income is False


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
            Bucket(name="A", target_allocation=50.0),
            Bucket(name="B", target_allocation=50.0),
        ],
        folders=[
            Folder("Old", "A", 100.0, ["Older"]),
            Folder("New", "B", 100.0, ["Newer"]),
        ],
    )
    data = build_dashboard([older, newer], config, _FakeFx())
    assert data.as_of == 202403
    assert data.net_worth_usd == pytest.approx(2000.0)
    assert data.net_worth_series.loc[202403] == pytest.approx(2000.0)
    assert data.net_worth_series.loc[202401] == pytest.approx(2000.0)
    percents = {bucket.name: bucket.size_pct for bucket in data.buckets}
    assert percents["A"] == pytest.approx(0.5)
    assert percents["B"] == pytest.approx(0.5)


def test_unassigned_groups_by_folder_and_folders_in_bucket_aggregate():
    rows = [
        {"yearmonth": 202401, "contribution": 0, "withdrawal": 0, "distribution": 0, "balance": 1000},
        {"yearmonth": 202402, "contribution": 0, "withdrawal": 0, "distribution": 0, "balance": 1000},
    ]
    a = _account("A", "USD", rows)
    b = _account("B", "USD", rows)
    c = _account("C", "USD", rows)
    d = _account("D", "USD", rows)
    config = AppConfig(
        buckets=[Bucket(name="Growth", target_allocation=100.0)],
        folders=[
            Folder("Core", "Growth", 70.0, ["A", "B"]),
            Folder("Empty", "Growth", 30.0, ["Missing"]),
            Folder("Loose", None, None, ["C"]),
        ],
    )
    data = build_dashboard([a, b, c, d], config, _FakeFx())
    growth = next(item for item in data.allocations if item.name == "Growth")
    by_folder = {asset.name: asset for asset in growth.assets}
    assert set(by_folder) == {"Core", "Empty"}
    assert by_folder["Core"].size_usd == pytest.approx(2000.0)
    assert by_folder["Core"].size_pct == pytest.approx(1.0)
    assert by_folder["Core"].target_pct == pytest.approx(0.70)
    assert by_folder["Empty"].size_usd == 0.0
    unassigned = next(item for item in data.allocations if item.name == "Unassigned")
    assert {asset.name for asset in unassigned.assets} == {"Loose", "D"}
    sizes = {bucket.name: bucket.size_usd for bucket in data.buckets}
    assert sizes == {"Growth": pytest.approx(2000.0), "Unassigned": pytest.approx(2000.0)}
