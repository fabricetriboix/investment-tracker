"""Load and save ~/.config/investment-tracker/config.yaml."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path.home() / ".config" / "investment-tracker"
CONFIG_PATH = CONFIG_DIR / "config.yaml"


@dataclass
class AccountAllocation:
    name: str
    target_allocation: float | None = None


@dataclass
class Bucket:
    name: str
    target_allocation: float | None = None
    target_return: float | None = None
    target_income_yield: float | None = None
    target_volatility: float | None = None
    target_max_drawdown: float | None = None
    accounts: list[AccountAllocation] = field(default_factory=list)

    def account_names(self) -> list[str]:
        return [item.name for item in self.accounts]


@dataclass
class AppConfig:
    data_directory: str = ""
    base_currency: str = "USD"
    buckets: list[Bucket] = field(default_factory=list)

    def bucket_for_account(self, account_name: str) -> Bucket | None:
        for bucket in self.buckets:
            if account_name in bucket.account_names():
                return bucket
        return None


def _as_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _bucket_from_dict(raw: dict[str, Any]) -> Bucket:
    accounts = [
        AccountAllocation(
            name=str(item["name"]),
            target_allocation=_as_optional_float(item.get("target_allocation")),
        )
        for item in raw.get("accounts") or []
        if item.get("name")
    ]
    return Bucket(
        name=str(raw.get("name") or "Untitled"),
        target_allocation=_as_optional_float(raw.get("target_allocation")),
        target_return=_as_optional_float(raw.get("target_return")),
        target_income_yield=_as_optional_float(raw.get("target_income_yield")),
        target_volatility=_as_optional_float(raw.get("target_volatility")),
        target_max_drawdown=_as_optional_float(raw.get("target_max_drawdown")),
        accounts=accounts,
    )


def from_dict(raw: dict[str, Any] | None) -> AppConfig:
    raw = raw or {}
    return AppConfig(
        data_directory=str(raw.get("data_directory") or ""),
        base_currency=str(raw.get("base_currency") or "USD").upper(),
        buckets=[_bucket_from_dict(item) for item in raw.get("buckets") or []],
    )


def to_dict(config: AppConfig) -> dict[str, Any]:
    buckets = []
    for bucket in config.buckets:
        buckets.append(asdict(bucket))
    return {
        "data_directory": config.data_directory,
        "base_currency": config.base_currency,
        "buckets": buckets,
    }


def load(path: Path | None = None) -> AppConfig:
    path = path or CONFIG_PATH
    if not path.exists():
        return AppConfig()
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        return AppConfig()
    return from_dict(raw)


def save(config: AppConfig, path: Path | None = None) -> Path:
    path = path or CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = to_dict(config)
    tmp = path.with_suffix(".yaml.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=True)
    tmp.replace(path)
    return path


def default_first_run_config(examples_dir: str = "") -> AppConfig:
    return AppConfig(
        data_directory=examples_dir,
        base_currency="USD",
        buckets=[
            Bucket(
                name="Equities",
                target_allocation=65.0,
                target_return=8.0,
                target_volatility=16.0,
                target_max_drawdown=35.0,
                accounts=[
                    AccountAllocation("US Brokerage", 25.0),
                    AccountAllocation("Workplace 401k", 40.0),
                    AccountAllocation("UK Stocks ISA", 20.0),
                    AccountAllocation("Canada TFSA", 15.0),
                ],
            ),
            Bucket(
                name="Income",
                target_allocation=25.0,
                target_return=4.0,
                target_income_yield=5.0,
                target_volatility=10.0,
                target_max_drawdown=18.0,
                accounts=[
                    AccountAllocation("Bond Ladder", 45.0),
                    AccountAllocation("REIT Portfolio", 55.0),
                ],
            ),
            Bucket(
                name="Cash",
                target_allocation=10.0,
                target_return=2.0,
                target_income_yield=3.0,
                target_volatility=1.5,
                target_max_drawdown=1.0,
                accounts=[AccountAllocation("Euro Savings", 100.0)],
            ),
        ],
    )


def copy_config(config: AppConfig) -> AppConfig:
    return from_dict(deepcopy(to_dict(config)))
