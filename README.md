# Investment Tracker

This is my first project entirely vibe-coded. Please feel free to use it to track your own investments.

Desktop app that reads monthly account CSV files and shows portfolio, bucket and per-account performance. It is a native PySide6 (Qt 6) application — it does not use a browser.

Python is the right stack here. The files you already keep are tabular time series; pandas is the natural way to interpolate gaps, compute returns and roll windows. Qt gives a real desktop window on Ubuntu, with the same code running on macOS and Windows.

## CSV format

Put one file per account in a directory. The file name is `ACCOUNT CURRENCY.csv`, where `CURRENCY` is the three-letter code:

- `US Brokerage USD.csv`
- `UK Stocks ISA GBP.csv`

The first data row is always the **opening balance**. Cash-flow columns on that row are stored as zero; only `balance` is the starting AUM. Later rows are monthly activity.

There are two file types, detected from the header:

| Type | Header | Meaning |
| --- | --- | --- |
| **Distribution** | includes `distribution` | Income is paid out of the account and recorded each month |
| **Accumulation** | no `distribution` column | Income is reinvested; it is not recorded separately |

Common columns:

| Column | Meaning |
| --- | --- |
| `yearmonth` | Month as `YYYYMM` (for example `202403`) |
| `contribution` | Cash paid **into** the account that month |
| `withdrawal` | Cash taken **out** of the account that month |
| `distribution` | Interest, dividends and other income **paid out** (distribution files only) |
| `balance` | End-of-month value, or opening AUM on the first row |

Conventions used by the metrics:

- Ending `balance` includes that month’s contributions and is already after withdrawals and paid-out distributions.
- Income that is reinvested must **not** be listed under `distribution`; use an accumulation file instead. It simply shows up in `balance`.
- Missing months between the first and last row are filled by linear interpolation for charts and statistics. The table on each account tab shows the CSV as stored.
- The app forces cash-flow columns on the earliest row to zero when you load a file.

## What the app shows

1. **Dashboard** — portfolio net worth in the reporting currency (USD by default), a table of bucket size and returns (12 months, 5 years, 10 years) next to their targets, a second table of yield/income (when any account pays distributions), volatility and maximum drawdown, a **Net worth** chart, per-bucket tables of each account’s actual vs target weight, and a **Bucket balances** chart. Accumulation-only portfolios omit the income KPI and the yield/income columns.
2. **Configuration** — CSV directory, reporting currency, buckets, portfolio-level bucket weights, account weights inside each bucket, and optional bucket targets (return, income yield, volatility, maximum drawdown).
3. **One tab per account** — type label (Accumulation or Distribution), the bucket it belongs to, a read-only view of the CSV, currency, growth of 10,000 in that currency, and a statistics table for 3 / 6 / 12 months and since beginning. Distribution tabs include a Distribution column and income-yield statistics. Accumulation tabs do not. Change figures in the CSV on disk and press `F5` to reload.

The 10,000 chart is a **price-return** path: contributions, withdrawals and distributions are stripped out so it answers “how would a lump sum have moved?” The first plotted point is the opening balance (index = 10,000); returns start the following month.

Volatility is the sample standard deviation of monthly price returns, annualised with √12 so it is comparable to typical annual targets (for example 15%). Maximum drawdown is the worst peak-to-trough decline of that same 10,000 series.

Bucket volatility and drawdown on the dashboard are computed from USD-converted, cash-flow-stripped values, so they include foreign-exchange movement. Each account tab charts and scores the account in its own currency.

## Currency conversion

Spot and historical month-end rates come from **[Frankfurter](https://frankfurter.dev/)** (`https://api.frankfurter.dev/v1`), a free API of European Central Bank reference rates. No API key is required. Rates are cached in `~/.config/investment-tracker/fx_cache.json` so the app still works offline after a successful fetch.

Frankfurter covers the major currencies (USD, EUR, GBP, CAD, JPY, AUD, CHF, and the other ECB-quoted currencies). Codes it does not know (for example a mistyped `CHD`) produce a single warning; the app does not fire a request per month. If a rate is missing, the dashboard explains that in a banner.

Alternatives if you later need broader coverage: the ECB SDW itself, or [Open Exchange Rates](https://openexchangerates.org/) (free tier, API key).

## Configuration file

Saved at `~/.config/investment-tracker/config.yaml` on Linux, macOS and Windows (`Path.home() / ".config" / "investment-tracker"`). It stores the CSV directory, reporting currency and buckets.

## Run locally

Ubuntu 24.04 (and any current Linux, macOS or Windows with Python 3.11+):

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
python -m investment_tracker
```

`pip install -e .` is optional. From the repo root you can also run:

```bash
PYTHONPATH=src python -m investment_tracker
```

On Ubuntu 24.04, Qt also needs a few system libraries if they are not already installed:

```bash
sudo apt install libegl1 libgl1 libxcb-cursor0 libxkbcommon-x11-0 libxcb-xkb1
```

On first launch the app points at the `examples/` folder in this repo (sample accounts in USD, GBP, CAD and EUR) and writes a starter config with Equities / Income / Cash buckets. Workplace 401k and Canada TFSA are accumulation files; the others pay distributions. Change the directory on the Configuration tab to use your own files.

Keyboard: `F5` reloads the CSV directory.

## Tests

```bash
pip install pytest
python -m pytest
```

## Cash-flow example

Opening balance 10,000 at the end of January. In February you contributed 500, withdrew 100, received 20 of dividends paid out, and the ending balance is 10,480:

price return = (10,480 − 500 + 100) / 10,000 − 1 = 0.8%.

The 20 of dividends is **not** added back, so it does not lift the 10,000 chart; it does lift mean income yield on a distribution account.
