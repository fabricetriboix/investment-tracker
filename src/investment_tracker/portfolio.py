"""Combine accounts, FX conversion and bucket-level KPIs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from investment_tracker.config import AppConfig, Bucket
from investment_tracker.csv_loader import Account
from investment_tracker.currency import FxConverter
from investment_tracker.dates import month_end, period_range, to_period, to_yyyymm
from investment_tracker.interpolation import NUMERIC_COLUMNS
from investment_tracker.metrics import (
    cagr,
    growth_of_index,
    max_drawdown,
    monthly_price_returns,
    skip_opening_row,
    volatility,
)


@dataclass
class BucketSnapshot:
    name: str
    size_usd: float
    size_pct: float | None
    target_allocation: float | None
    income_12m_usd: float
    yield_12m: float | None
    target_income_yield: float | None
    return_12m: float | None
    return_5y: float | None
    return_10y: float | None
    target_return: float | None
    volatility_5y: float | None
    target_volatility: float | None
    max_drawdown_5y: float | None
    target_max_drawdown: float | None
    has_yield_target: bool
    has_income: bool
    account_names: list[str] = field(default_factory=list)


@dataclass
class AssetAllocation:
    name: str
    size_usd: float
    size_pct: float | None
    target_pct: float | None


@dataclass
class BucketAllocation:
    name: str
    assets: list[AssetAllocation]


@dataclass
class DashboardData:
    net_worth_usd: float
    income_12m_usd: float
    as_of: int | None
    net_worth_series: pd.Series
    bucket_series: dict[str, pd.Series]
    buckets: list[BucketSnapshot]
    allocations: list[BucketAllocation]
    has_income: bool
    fx_warnings: list[str]
    load_errors: list[str]


def _all_yearmonths(accounts: list[Account]) -> list[int]:
    """Contiguous months from the earliest to the latest CSV row across accounts."""
    periods: list = []
    for account in accounts:
        if account.filled.empty:
            continue
        periods.extend(to_period(int(value)) for value in account.filled["yearmonth"])
    if not periods:
        return []
    return [to_yyyymm(period) for period in period_range(min(periods), max(periods))]


def convert_frame(frame: pd.DataFrame, currency: str, fx: FxConverter, base: str) -> pd.DataFrame:
    """Add reporting-currency columns to a native-currency monthly frame."""
    work = frame.copy()
    if work.empty:
        for column in ("balance_base", "distribution_base", "contribution_base", "withdrawal_base"):
            work[column] = []
        return work

    balance_base: list[float | None] = []
    dist_base: list[float | None] = []
    contrib_base: list[float | None] = []
    wd_base: list[float | None] = []
    for _, row in work.iterrows():
        ym = int(row["yearmonth"])
        balance_base.append(fx.convert(float(row["balance"] or 0.0), currency, base, ym))
        dist_base.append(fx.convert(float(row["distribution"] or 0.0), currency, base, ym))
        contrib_base.append(fx.convert(float(row["contribution"] or 0.0), currency, base, ym))
        wd_base.append(fx.convert(float(row["withdrawal"] or 0.0), currency, base, ym))
    work["balance_base"] = balance_base
    work["distribution_base"] = dist_base
    work["contribution_base"] = contrib_base
    work["withdrawal_base"] = wd_base
    return work


def convert_filled(account: Account, fx: FxConverter, base: str) -> pd.DataFrame:
    """Filled monthly series with USD (base) columns added."""
    return convert_frame(account.filled, account.currency, fx, base)


def align_native(account: Account, months: list[int]) -> pd.DataFrame:
    """Place an account on a shared calendar.

    Balance is carried forward after the account's first month so a newer
    row in another CSV does not drop this account from net worth. Cash flows
    are zero in months the account did not record.
    """
    columns = ["yearmonth", *NUMERIC_COLUMNS]
    if not months:
        return pd.DataFrame(columns=columns)
    if account.filled.empty:
        zeros = pd.DataFrame({"yearmonth": months})
        for column in NUMERIC_COLUMNS:
            zeros[column] = 0.0
        return zeros[columns]

    work = account.filled.copy()
    work["yearmonth"] = work["yearmonth"].astype(int)
    work = work.drop_duplicates("yearmonth", keep="last").set_index("yearmonth").sort_index()
    native_months = [int(index) for index in work.index]
    combined = sorted(set(months) | set(native_months))
    aligned = work.reindex(combined)
    aligned.index.name = "yearmonth"
    first = int(work.index.min())
    started = aligned.index >= first
    aligned.loc[started, "balance"] = aligned.loc[started, "balance"].ffill()
    for column in ("contribution", "withdrawal", "distribution"):
        aligned[column] = aligned[column].fillna(0.0)
    aligned["balance"] = aligned["balance"].fillna(0.0)
    aligned = aligned.loc[months]
    return aligned.reset_index()[columns]


def convert_aligned(account: Account, months: list[int], fx: FxConverter, base: str) -> pd.DataFrame:
    return convert_frame(align_native(account, months), account.currency, fx, base)


def net_worth_series(accounts: list[Account], fx: FxConverter, base: str) -> pd.Series:
    months = _all_yearmonths(accounts)
    if not months:
        return pd.Series(dtype=float)
    converted = [convert_aligned(account, months, fx, base) for account in accounts]
    values: dict[int, float] = {}
    for ym in months:
        total = 0.0
        for frame in converted:
            row = frame.loc[frame["yearmonth"] == ym]
            if row.empty:
                continue
            amount = row["balance_base"].iloc[0]
            if pd.notna(amount):
                total += float(amount)
        values[ym] = total
    series = pd.Series(values, dtype=float)
    series.index.name = "yearmonth"
    series.name = "net_worth"
    return series


def _latest_yearmonth(accounts: list[Account]) -> int | None:
    months = _all_yearmonths(accounts)
    return months[-1] if months else None


def _accounts_by_name(accounts: list[Account]) -> dict[str, Account]:
    return {account.name: account for account in accounts}


def _assigned_names(config: AppConfig) -> set[str]:
    names: set[str] = set()
    for bucket in config.buckets:
        names.update(config.bucket_accounts(bucket.name))
    return names


def _bucket_accounts(config: AppConfig, bucket: Bucket, by_name: dict[str, Account]) -> list[Account]:
    found: list[Account] = []
    for name in config.bucket_accounts(bucket.name):
        account = by_name.get(name)
        if account is not None:
            found.append(account)
    return found


def _income_accounts(members: list[Account]) -> list[Account]:
    return [account for account in members if account.pays_income]


def _combined_base_frame(members: list[Account], fx: FxConverter, base: str) -> pd.DataFrame:
    """Sum converted balances and cash flows across member accounts."""
    months = _all_yearmonths(members)
    if not months:
        return pd.DataFrame(
            columns=[
                "yearmonth",
                "contribution",
                "withdrawal",
                "distribution",
                "balance",
            ]
        )
    converted = [convert_aligned(account, months, fx, base) for account in members]
    rows = []
    for ym in months:
        contrib = wd = dist = bal = 0.0
        for frame in converted:
            row = frame.loc[frame["yearmonth"] == ym]
            if row.empty:
                continue
            for src, dest_name in (
                ("contribution_base", "contrib"),
                ("withdrawal_base", "wd"),
                ("distribution_base", "dist"),
                ("balance_base", "bal"),
            ):
                value = row[src].iloc[0]
                if pd.isna(value):
                    continue
                if dest_name == "contrib":
                    contrib += float(value)
                elif dest_name == "wd":
                    wd += float(value)
                elif dest_name == "dist":
                    dist += float(value)
                else:
                    bal += float(value)
        rows.append(
            {
                "yearmonth": ym,
                "contribution": contrib,
                "withdrawal": wd,
                "distribution": dist,
                "balance": bal,
            }
        )
    return pd.DataFrame(rows)


def _balance_series(members: list[Account], fx: FxConverter, base: str) -> pd.Series:
    combined = _combined_base_frame(members, fx, base)
    if combined.empty:
        return pd.Series(dtype=float)
    series = combined.set_index("yearmonth")["balance"].astype(float)
    series.index = series.index.astype(int)
    series.index.name = "yearmonth"
    series.name = "balance"
    return series


def _size_usd(members: list[Account], fx: FxConverter, base: str, as_of: int | None) -> float:
    if as_of is None:
        return 0.0
    months = [as_of]
    total = 0.0
    for account in members:
        converted = convert_aligned(account, months, fx, base)
        if converted.empty:
            continue
        value = converted["balance_base"].iloc[-1]
        if pd.notna(value):
            total += float(value)
    return total


def _income_12m_usd(members: list[Account], fx: FxConverter, base: str) -> float:
    total = 0.0
    for account in _income_accounts(members):
        converted = convert_filled(account, fx, base)
        if converted.empty:
            continue
        work = skip_opening_row(converted)
        if work.empty:
            continue
        values = work.sort_values("yearmonth").tail(12)["distribution_base"].dropna()
        total += float(values.sum()) if not values.empty else 0.0
    return total


def _bucket_yield_12m(members: list[Account], fx: FxConverter, base: str) -> float | None:
    if not _income_accounts(members):
        return None
    combined = _combined_base_frame(members, fx, base)
    work = skip_opening_row(combined)
    if work.empty:
        return None
    tail = work.sort_values("yearmonth").tail(12)
    ratios = []
    for _, row in tail.iterrows():
        if row["balance"]:
            ratios.append(float(row["distribution"]) / float(row["balance"]))
    if not ratios:
        return None
    return (sum(ratios) / len(ratios)) * 12.0


def build_bucket_snapshot(
    name: str,
    members: list[Account],
    bucket: Bucket | None,
    fx: FxConverter,
    base: str,
    as_of: int | None,
    portfolio_usd: float,
) -> BucketSnapshot:
    combined = _combined_base_frame(members, fx, base)
    returns = monthly_price_returns(combined)
    index = growth_of_index(returns)
    size = _size_usd(members, fx, base, as_of)
    size_pct = (size / portfolio_usd) if portfolio_usd else None
    has_income = bool(_income_accounts(members))
    target_yield = bucket.target_income_yield if bucket else None
    return BucketSnapshot(
        name=name,
        size_usd=size,
        size_pct=size_pct,
        target_allocation=(bucket.target_allocation / 100.0) if bucket and bucket.target_allocation is not None else None,
        income_12m_usd=_income_12m_usd(members, fx, base) if has_income else 0.0,
        yield_12m=_bucket_yield_12m(members, fx, base),
        target_income_yield=(target_yield / 100.0) if target_yield is not None else None,
        return_12m=cagr(returns, 12),
        return_5y=cagr(returns, 60),
        return_10y=cagr(returns, 120),
        target_return=(bucket.target_return / 100.0) if bucket and bucket.target_return is not None else None,
        volatility_5y=volatility(returns, 60),
        target_volatility=(bucket.target_volatility / 100.0) if bucket and bucket.target_volatility is not None else None,
        max_drawdown_5y=max_drawdown(index, 60),
        target_max_drawdown=(
            -abs(bucket.target_max_drawdown) / 100.0
            if bucket and bucket.target_max_drawdown is not None
            else None
        ),
        has_yield_target=target_yield is not None,
        has_income=has_income,
        account_names=[account.name for account in members],
    )


def _asset_allocations(
    members: list[Account],
    config: AppConfig,
    bucket: Bucket | None,
    fx: FxConverter,
    base: str,
    as_of: int | None,
) -> list[AssetAllocation]:
    """Actual and target weights of each folder inside a bucket.

    Without a bucket (the Unassigned group) members are grouped by folder,
    and accounts without a folder appear under their own name.
    """
    bucket_total = _size_usd(members, fx, base, as_of)
    groups: dict[str, list[Account]] = {}
    targets: dict[str, float | None] = {}
    if bucket is not None:
        for folder in config.folders_in_bucket(bucket.name):
            groups.setdefault(folder.name, [])
            targets[folder.name] = (
                folder.target_allocation / 100.0 if folder.target_allocation is not None else None
            )
    for account in members:
        folder = config.folder_for_account(account.name)
        groups.setdefault(folder.name if folder else account.name, []).append(account)
    rows: list[AssetAllocation] = []
    for name, accounts in groups.items():
        size = _size_usd(accounts, fx, base, as_of)
        pct = (size / bucket_total) if bucket_total else None
        rows.append(
            AssetAllocation(
                name=name,
                size_usd=size,
                size_pct=pct,
                target_pct=targets.get(name),
            )
        )
    return rows


def build_dashboard(
    accounts: list[Account],
    config: AppConfig,
    fx: FxConverter,
    load_errors: list[str] | None = None,
) -> DashboardData:
    base = config.base_currency or "USD"
    months = _all_yearmonths(accounts)
    if months:
        start = month_end(to_period(months[0]))
        end = month_end(to_period(months[-1]))
    else:
        start = end = date.today()
    currencies = [account.currency for account in accounts]
    fx.prefetch(currencies, start, end, base=base)

    series = net_worth_series(accounts, fx, base)
    as_of = _latest_yearmonth(accounts)
    net_worth = float(series.iloc[-1]) if not series.empty else 0.0
    has_income = any(account.pays_income for account in accounts)
    income_12m = _income_12m_usd(accounts, fx, base) if has_income else 0.0

    by_name = _accounts_by_name(accounts)
    snapshots: list[BucketSnapshot] = []
    series_by_bucket: dict[str, pd.Series] = {}
    allocations: list[BucketAllocation] = []
    for bucket in config.buckets:
        members = _bucket_accounts(config, bucket, by_name)
        snapshots.append(
            build_bucket_snapshot(bucket.name, members, bucket, fx, base, as_of, net_worth)
        )
        series_by_bucket[bucket.name] = _balance_series(members, fx, base)
        allocations.append(
            BucketAllocation(
                name=bucket.name,
                assets=_asset_allocations(members, config, bucket, fx, base, as_of),
            )
        )

    unassigned = [account for account in accounts if account.name not in _assigned_names(config)]
    if unassigned:
        snapshots.append(
            build_bucket_snapshot("Unassigned", unassigned, None, fx, base, as_of, net_worth)
        )
        series_by_bucket["Unassigned"] = _balance_series(unassigned, fx, base)
        allocations.append(
            BucketAllocation(
                name="Unassigned",
                assets=_asset_allocations(unassigned, config, None, fx, base, as_of),
            )
        )

    return DashboardData(
        net_worth_usd=net_worth,
        income_12m_usd=income_12m,
        as_of=as_of,
        net_worth_series=series,
        bucket_series=series_by_bucket,
        buckets=snapshots,
        allocations=allocations,
        has_income=has_income,
        fx_warnings=list(fx.warnings),
        load_errors=list(load_errors or []),
    )
