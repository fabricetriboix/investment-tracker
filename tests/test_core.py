from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from investment_tracker.config import AppConfig, Bucket, Folder, from_dict, to_dict
from investment_tracker.csv_loader import (
    TYPE_ACCUMULATION,
    TYPE_DISTRIBUTION,
    CsvError,
    load_account,
    parse_filename,
    save_account,
)
from investment_tracker.interpolation import apply_opening_row, fill_missing_months
from investment_tracker.metrics import (
    INDEX_START,
    PERIODS,
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


def test_interpolate_gap():
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
    first = filled.loc[filled["yearmonth"] == 202401].iloc[0]
    mid = filled.loc[filled["yearmonth"] == 202402].iloc[0]
    assert first["contribution"] == pytest.approx(0.0)
    assert first["distribution"] == pytest.approx(0.0)
    assert mid["balance"] == pytest.approx(1100.0)
    assert mid["contribution"] == pytest.approx(150.0)
    assert mid["distribution"] == pytest.approx(15.0)


def test_apply_opening_row_zeros_cash_flows():
    frame = pd.DataFrame(
        {
            "yearmonth": [202402, 202401],
            "contribution": [10.0, 99.0],
            "withdrawal": [1.0, 5.0],
            "distribution": [2.0, 3.0],
            "balance": [1100.0, 1000.0],
        }
    )
    opened = apply_opening_row(frame)
    first = opened.iloc[0]
    assert int(first["yearmonth"]) == 202401
    assert first["contribution"] == 0.0
    assert first["withdrawal"] == 0.0
    assert first["distribution"] == 0.0
    assert first["balance"] == pytest.approx(1000.0)
    assert opened.iloc[1]["contribution"] == pytest.approx(10.0)


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
    assert pd.isna(returns.iloc[0])
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


def test_last_period_is_since_beginning():
    assert PERIODS[-1] == ("Since beginning", None)


def test_mean_yield_skips_opening_row():
    frame = pd.DataFrame(
        {
            "yearmonth": [202401, 202402, 202403],
            "contribution": [0.0, 0.0, 0.0],
            "withdrawal": [0.0, 0.0, 0.0],
            "distribution": [99.0, 10.0, 20.0],
            "balance": [1000.0, 1000.0, 1000.0],
        }
    )
    # Opening 99 is ignored; mean of 10/1000 and 20/1000.
    assert mean_yield_ratio(frame, None) == pytest.approx(0.015)


def test_config_roundtrip(tmp_path: Path):
    config = AppConfig(
        data_directory="/tmp/csvs",
        base_currency="USD",
        buckets=[Bucket(name="Equities", target_allocation=60.0, target_return=8.0)],
        folders=[Folder("Core", "Equities", 100.0, ["Brokerage"]), Folder("Loose", None, None, ["Spare"])],
    )
    payload = to_dict(config)
    restored = from_dict(yaml.safe_load(yaml.safe_dump(payload)))
    assert restored.data_directory == "/tmp/csvs"
    assert restored.buckets[0].name == "Equities"
    assert restored.folders[0] == Folder("Core", "Equities", 100.0, ["Brokerage"])
    assert restored.folders[1].bucket is None
    assert restored.folder_for_account("Brokerage").name == "Core"
    assert restored.bucket_for_account("Brokerage").name == "Equities"
    assert restored.bucket_for_account("Spare") is None
    assert "hidden_metric_pairs" not in payload


def test_old_bucket_accounts_key_is_ignored():
    restored = from_dict(
        {"buckets": [{"name": "Equities", "accounts": [{"name": "Brokerage", "target_allocation": 100}]}]}
    )
    assert restored.buckets[0].name == "Equities"
    assert restored.folders == []
    assert restored.bucket_for_account("Brokerage") is None


def test_set_account_folder_creates_moves_and_prunes():
    config = AppConfig(buckets=[Bucket("Equities")])
    config.set_account_folder("Brokerage", "Core")
    assert config.folder_for_account("Brokerage").name == "Core"
    config.folder_named("Core").bucket = "Equities"
    config.set_account_folder("ISA", "Core")
    assert config.bucket_accounts("Equities") == ["Brokerage", "ISA"]
    config.set_account_folder("Brokerage", "Other")
    assert config.folder_named("Core").accounts == ["ISA"]
    config.set_account_folder("ISA", "")
    assert config.folder_named("Core") is None
    assert [folder.name for folder in config.folders] == ["Other"]


def test_rename_and_remove_bucket_update_folders():
    config = AppConfig(buckets=[Bucket("A"), Bucket("B")], folders=[Folder("F", "A", 50.0, ["X"])])
    config.rename_bucket("A", "C")
    assert config.folders[0].bucket == "C"
    assert config.bucket_named("C") is not None
    config.remove_bucket("C")
    assert config.folders[0].bucket is None
    assert [bucket.name for bucket in config.buckets] == ["B"]


def test_distribution_csv_roundtrip(tmp_path: Path):
    path = tmp_path / "Test Account USD.csv"
    frame = pd.DataFrame(
        {
            "yearmonth": [202401, 202402],
            "contribution": [100.0, 25.0],
            "withdrawal": [0.0, 10.0],
            "distribution": [1.5, 1.5],
            "balance": [5000.0, 5100.0],
        }
    )
    save_account(path, frame, TYPE_DISTRIBUTION)
    header = path.read_text(encoding="utf-8").splitlines()[0]
    assert "distribution" in header
    account = load_account(path)
    assert account.name == "Test Account"
    assert account.currency == "USD"
    assert account.account_type == TYPE_DISTRIBUTION
    assert account.pays_income
    assert list(account.raw["yearmonth"]) == [202401, 202402]
    assert account.raw["contribution"].iloc[0] == pytest.approx(0.0)
    assert account.raw["distribution"].iloc[0] == pytest.approx(0.0)
    assert account.raw["contribution"].iloc[1] == pytest.approx(25.0)
    assert account.raw["balance"].iloc[-1] == pytest.approx(5100.0)


def test_accumulation_csv_omits_distribution_column(tmp_path: Path):
    path = tmp_path / "Workplace Pension GBP.csv"
    frame = pd.DataFrame(
        {
            "yearmonth": [202401, 202402],
            "contribution": [0.0, 50.0],
            "withdrawal": [0.0, 0.0],
            "balance": [1000.0, 1080.0],
        }
    )
    save_account(path, frame)
    header = path.read_text(encoding="utf-8").splitlines()[0]
    assert header == "yearmonth,contribution,withdrawal,balance"
    account = load_account(path)
    assert account.account_type == TYPE_ACCUMULATION
    assert not account.pays_income
    assert account.type_label == "Accumulation"
    assert list(account.raw["distribution"]) == [0.0, 0.0]
    assert account.raw["contribution"].iloc[1] == pytest.approx(50.0)
