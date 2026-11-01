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
class Bucket:
    name: str
    target_allocation: float | None = None
    target_return: float | None = None
    target_income_yield: float | None = None
    target_volatility: float | None = None
    target_max_drawdown: float | None = None


@dataclass
class Folder:
    name: str
    bucket: str | None = None
    target_allocation: float | None = None  # % of its bucket
    accounts: list[str] = field(default_factory=list)


@dataclass
class AppConfig:
    data_directory: str = ""
    base_currency: str = "USD"
    buckets: list[Bucket] = field(default_factory=list)
    folders: list[Folder] = field(default_factory=list)

    def bucket_named(self, name: str | None) -> Bucket | None:
        for bucket in self.buckets:
            if bucket.name == name:
                return bucket
        return None

    def folder_named(self, name: str | None) -> Folder | None:
        for folder in self.folders:
            if folder.name == name:
                return folder
        return None

    def folder_for_account(self, account_name: str) -> Folder | None:
        for folder in self.folders:
            if account_name in folder.accounts:
                return folder
        return None

    def folders_in_bucket(self, bucket_name: str) -> list[Folder]:
        return [folder for folder in self.folders if folder.bucket == bucket_name]

    def bucket_accounts(self, bucket_name: str) -> list[str]:
        names: list[str] = []
        for folder in self.folders_in_bucket(bucket_name):
            names.extend(name for name in folder.accounts if name not in names)
        return names

    def bucket_for_account(self, account_name: str) -> Bucket | None:
        folder = self.folder_for_account(account_name)
        return self.bucket_named(folder.bucket) if folder else None

    def set_account_folder(self, account_name: str, folder_name: str | None) -> None:
        """Move an account into a folder (created if new); None or "" removes it from any folder."""
        folder_name = (folder_name or "").strip()
        for folder in self.folders:
            if account_name in folder.accounts and folder.name != folder_name:
                folder.accounts.remove(account_name)
        if folder_name:
            target = self.folder_named(folder_name)
            if target is None:
                target = Folder(name=folder_name)
                self.folders.append(target)
            if account_name not in target.accounts:
                target.accounts.append(account_name)
        self.folders = [folder for folder in self.folders if folder.accounts]

    def rename_bucket(self, old: str, new: str) -> None:
        bucket = self.bucket_named(old)
        if bucket is not None:
            bucket.name = new
        for folder in self.folders:
            if folder.bucket == old:
                folder.bucket = new

    def remove_bucket(self, name: str) -> None:
        self.buckets = [bucket for bucket in self.buckets if bucket.name != name]
        for folder in self.folders:
            if folder.bucket == name:
                folder.bucket = None


def _as_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _bucket_from_dict(raw: dict[str, Any]) -> Bucket:
    return Bucket(
        name=str(raw.get("name") or "Untitled"),
        target_allocation=_as_optional_float(raw.get("target_allocation")),
        target_return=_as_optional_float(raw.get("target_return")),
        target_income_yield=_as_optional_float(raw.get("target_income_yield")),
        target_volatility=_as_optional_float(raw.get("target_volatility")),
        target_max_drawdown=_as_optional_float(raw.get("target_max_drawdown")),
    )


def _folder_from_dict(raw: dict[str, Any]) -> Folder:
    bucket = raw.get("bucket")
    return Folder(
        name=str(raw["name"]),
        bucket=str(bucket) if bucket else None,
        target_allocation=_as_optional_float(raw.get("target_allocation")),
        accounts=[str(name) for name in raw.get("accounts") or [] if name],
    )


def from_dict(raw: dict[str, Any] | None) -> AppConfig:
    raw = raw or {}
    return AppConfig(
        data_directory=str(raw.get("data_directory") or ""),
        base_currency=str(raw.get("base_currency") or "USD").upper(),
        buckets=[_bucket_from_dict(item) for item in raw.get("buckets") or []],
        folders=[
            _folder_from_dict(item)
            for item in raw.get("folders") or []
            if isinstance(item, dict) and item.get("name")
        ],
    )


def to_dict(config: AppConfig) -> dict[str, Any]:
    return {
        "data_directory": config.data_directory,
        "base_currency": config.base_currency,
        "buckets": [asdict(bucket) for bucket in config.buckets],
        "folders": [asdict(folder) for folder in config.folders],
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
            ),
            Bucket(
                name="Income",
                target_allocation=25.0,
                target_return=4.0,
                target_income_yield=5.0,
                target_volatility=10.0,
                target_max_drawdown=18.0,
            ),
            Bucket(
                name="Cash",
                target_allocation=10.0,
                target_return=2.0,
                target_income_yield=3.0,
                target_volatility=1.5,
                target_max_drawdown=1.0,
            ),
        ],
        folders=[
            Folder("Global equity", "Equities", 65.0, ["US Brokerage", "Workplace 401k"]),
            Folder("International", "Equities", 35.0, ["UK Stocks ISA", "Canada TFSA"]),
            Folder("Fixed income", "Income", 45.0, ["Bond Ladder"]),
            Folder("Property", "Income", 55.0, ["REIT Portfolio"]),
            Folder("Cash", "Cash", 100.0, ["Euro Savings"]),
        ],
    )


def copy_config(config: AppConfig) -> AppConfig:
    return from_dict(deepcopy(to_dict(config)))
