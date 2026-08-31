from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from investment_tracker.config import AppConfig, Bucket, AccountAllocation, from_dict, to_dict
from investment_tracker.csv_loader import parse_filename, CsvError, load_account, save_account
from investment_tracker.interpolation import fill_missing_months
from investment_tracker.metrics import (
    INDEX_START,
    cagr,
    growth_of_index,
    max_drawdown,
    mean_yield_ratio,
    monthly_price_returns,
    volatility,
)


def test_parse_filename_with_spaces():
    name, ccy = parse_filename(Path("US Brokerage USD.csv"))
    assert name == "US Brokerage"
    assert ccy == "USD"


def test_parse_filename_rejects_bad():
    with pytest.raises(CsvError):
        parse_filename(Path("notes.txt"))
    with pytest.raises(CsvError):
        parse_filename(Path("NoCurrency.csv"))


def test_interpolate_gap(tmp_path: Path):
    frame = pd.DataFrame(
        {
            "yearmonth": [202401, 202403],
            "contribution": [100.0, 300.0],
            "withdrawal": [0.0, 0.0],
            "distribution": [10.0, 30.0],
            "balance": [1000.0, 1200.0],
        }
    )
    filled = fill_missing_months(frame)
    assert list(filled["yearmonth"]) == [202401, 202402, 202403]
    mid = filled.loc[filled["yearmonth"] == 202402].iloc[0]
    assert mid["balance"] == pytest.approx(1100.0)
    assert mid["contribution"] == pytest.approx(200.0)
    assert mid["distribution"] == pytest.approx(20.0)


def test_price_return_strips_cash_flows():
    frame = pd.DataFrame(
        {
            "yearmonth": [202401, 202402],
            "contribution": [0.0, 100.0],
            "withdrawal": [0.0, 20.0],
            "distribution": [0.0, 5.0],
            "balance": [1000.0, 1130.0],
        }
    )
    returns = monthly_price_returns(frame)
    # (1130 - 100 + 20) / 1000 - 1 = 0.05
    # distribution is not added back
    assert returns.iloc[1] == pytest.approx(0.05)


def test_growth_cagr_vol_drawdown():
    returns = pd.Series([float("nan"), 0.01, 0.01, 0.01, -0.2, 0.05], index=[1, 2, 3, 4, 5, 6])
    index = growth_of_index(returns)
    assert index.iloc[0] == INDEX_START
    assert index.iloc[3] == pytest.approx(INDEX_START * 1.01**3)
    overall = cagr(returns, None)
    assert overall is not None
    vol = volatility(returns.dropna(), None)
    assert vol is not None and vol > 0
    dd = max_drawdown(index, None)
    assert dd is not None and dd < 0


def test_mean_yield():
    frame = pd.DataFrame(
        {
            "yearmonth": [202401, 202402],
            "contribution": [0.0, 0.0],
            "withdrawal": [0.0, 0.0],
            "distribution": [10.0, 20.0],
            "balance": [1000.0, 1000.0],
        }
    )
    assert mean_yield_ratio(frame, None) == pytest.approx(0.015)


def test_config_roundtrip(tmp_path: Path):
    config = AppConfig(
        data_directory="/tmp/csvs",
        base_currency="USD",
        buckets=[
            Bucket(
                name="Equities",
                target_allocation=60.0,
                target_return=8.0,
                accounts=[AccountAllocation("Brokerage", 100.0)],
            )
        ],
    )
    payload = to_dict(config)
    restored = from_dict(payload)
    assert restored.data_directory == "/tmp/csvs"
    assert "dashboard" not in payload
    assert "hidden_metric_pairs" not in payload
    assert restored.buckets[0].name == "Equities"
    assert restored.buckets[0].accounts[0].name == "Brokerage"
    text = yaml.safe_dump(payload)
    assert "Equities" in text
    # Legacy files that still have the old dashboard block should load.
    legacy = from_dict(
        {
            "data_directory": "/tmp/csvs",
            "base_currency": "USD",
            "dashboard": {"hidden_metric_pairs": ["volatility"]},
            "buckets": [],
        }
    )
    assert legacy.data_directory == "/tmp/csvs"


def test_csv_roundtrip(tmp_path: Path):
    path = tmp_path / "Test Account USD.csv"
    frame = pd.DataFrame(
        {
            "yearmonth": [202401, 202402],
            "contribution": [100.0, 0.0],
            "withdrawal": [0.0, 25.0],
            "distribution": [1.5, 1.5],
            "balance": [5000.0, 5100.0],
        }
    )
    save_account(path, frame)
    account = load_account(path)
    assert account.name == "Test Account"
    assert account.currency == "USD"
    assert list(account.raw["yearmonth"]) == [202401, 202402]
    assert account.raw["balance"].iloc[-1] == pytest.approx(5100.0)
