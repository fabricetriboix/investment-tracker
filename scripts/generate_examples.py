"""Deterministic example CSVs so the app can be tried immediately."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from investment_tracker.dates import to_period, to_yyyymm
from investment_tracker.csv_loader import COLUMNS, save_account

START = 201901
END = 202608


def _months(start: int, end: int) -> list[int]:
    period = to_period(start)
    last = to_period(end)
    values: list[int] = []
    while period <= last:
        values.append(to_yyyymm(period))
        period += 1
    return values


def _equity_return(ym: int, rng: np.random.Generator, tilt: float = 0.0) -> float:
    """Roughly 8% annual with known crash months."""
    shocks = {
        202002: -0.085,
        202003: -0.125,
        202004: 0.128,
        202011: 0.11,
        202201: -0.055,
        202202: -0.032,
        202203: -0.038,
        202204: -0.09,
        202205: 0.002,
        202206: -0.085,
        202209: -0.095,
        202210: 0.08,
        202211: 0.055,
        202303: -0.045,
        202310: -0.03,
        202311: 0.09,
        202402: 0.052,
        202408: -0.045,
        202504: -0.06,
        202511: 0.04,
    }
    if ym in shocks:
        return shocks[ym] + tilt
    # ~0.65% monthly plus noise
    return float(0.0065 + tilt + rng.normal(0, 0.018))


def _simulate(
    start: int,
    end: int,
    opening_balance: float,
    contrib_fn,
    return_fn,
    dist_rate_fn,
    withdraw_fn=None,
    skip: set[int] | None = None,
) -> pd.DataFrame:
    skip = skip or set()
    withdraw_fn = withdraw_fn or (lambda _ym: 0.0)
    balance = opening_balance
    rows = []
    first = True
    for ym in _months(start, end):
        contrib = float(contrib_fn(ym))
        withdrawal = float(withdraw_fn(ym))
        invested = max(0.0, balance + contrib - withdrawal)
        after_market = invested * (1.0 + float(return_fn(ym)))
        dist = max(0.0, after_market * float(dist_rate_fn(ym)))
        balance = max(0.0, after_market - dist)
        if first and opening_balance > 0 and contrib == 0:
            # Opening balance is pre-existing capital; still record the month.
            pass
        first = False
        if ym in skip:
            continue
        rows.append(
            {
                "yearmonth": ym,
                "contribution": round(contrib, 2),
                "withdrawal": round(withdrawal, 2),
                "distribution": round(dist, 2),
                "balance": round(balance, 2),
            }
        )
    return pd.DataFrame(rows, columns=list(COLUMNS))


def generate(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)

    us_brokerage = _simulate(
        START,
        END,
        opening_balance=42_500.0,
        contrib_fn=lambda ym: 400.0 if ym % 100 != 12 else 1200.0,
        return_fn=lambda ym: _equity_return(ym, rng, tilt=0.0005),
        dist_rate_fn=lambda _ym: 0.0012,
        withdraw_fn=lambda ym: 5000.0 if ym == 202307 else 0.0,
    )
    save_account(directory / "US Brokerage USD.csv", us_brokerage)

    rng401k = np.random.default_rng(7)
    workplace = _simulate(
        START,
        END,
        opening_balance=88_000.0,
        contrib_fn=lambda ym: 850.0,
        return_fn=lambda ym: _equity_return(ym, rng401k, tilt=-0.0003),
        dist_rate_fn=lambda _ym: 0.0,  # dividends reinvested
    )
    save_account(directory / "Workplace 401k USD.csv", workplace)

    rng_isa = np.random.default_rng(11)
    isa = _simulate(
        202003,
        END,
        opening_balance=15_200.0,
        contrib_fn=lambda ym: 250.0,
        return_fn=lambda ym: _equity_return(ym, rng_isa, tilt=-0.0008),
        dist_rate_fn=lambda _ym: 0.0018,
        skip={202206, 202207},
    )
    save_account(directory / "UK Stocks ISA GBP.csv", isa)

    rng_tfsa = np.random.default_rng(19)
    tfsa = _simulate(
        202101,
        END,
        opening_balance=12_000.0,
        contrib_fn=lambda ym: 500.0 if ym < 202501 else 650.0,
        return_fn=lambda ym: _equity_return(ym, rng_tfsa, tilt=0.0),
        dist_rate_fn=lambda _ym: 0.0008,
    )
    save_account(directory / "Canada TFSA CAD.csv", tfsa)

    rng_bond = np.random.default_rng(23)

    def bond_return(ym: int) -> float:
        if ym <= 202112:
            return float(0.0015 + rng_bond.normal(0, 0.004))
        if ym <= 202310:
            return float(-0.004 + rng_bond.normal(0, 0.008))
        return float(0.003 + rng_bond.normal(0, 0.005))

    bonds = _simulate(
        201906,
        END,
        opening_balance=28_000.0,
        contrib_fn=lambda ym: 150.0,
        return_fn=bond_return,
        dist_rate_fn=lambda _ym: 0.0034,
        withdraw_fn=lambda ym: 2000.0 if ym == 202412 else 0.0,
    )
    save_account(directory / "Bond Ladder GBP.csv", bonds)

    rng_reit = np.random.default_rng(29)

    def reit_return(ym: int) -> float:
        shocks = {202003: -0.22, 202004: 0.08, 202202: -0.04, 202209: -0.12, 202310: -0.06}
        if ym in shocks:
            return shocks[ym]
        return float(0.004 + rng_reit.normal(0, 0.022))

    reits = _simulate(
        201903,
        END,
        opening_balance=18_500.0,
        contrib_fn=lambda ym: 200.0,
        return_fn=reit_return,
        dist_rate_fn=lambda _ym: 0.0045,
    )
    save_account(directory / "REIT Portfolio USD.csv", reits)

    def cash_return(ym: int) -> float:
        if ym < 202207:
            return 0.0002
        if ym < 202307:
            return 0.0025
        return 0.0032

    def cash_yield(ym: int) -> float:
        if ym < 202207:
            return 0.0002
        if ym < 202307:
            return 0.0028
        return 0.0035

    cash = _simulate(
        201901,
        END,
        opening_balance=22_000.0,
        contrib_fn=lambda ym: 300.0 if ym % 100 == 1 else 0.0,
        return_fn=cash_return,
        dist_rate_fn=cash_yield,
    )
    save_account(directory / "Euro Savings EUR.csv", cash)


if __name__ == "__main__":
    generate(Path(__file__).resolve().parents[1] / "examples")
