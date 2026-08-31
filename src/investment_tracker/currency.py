"""Currency conversion via Frankfurter (ECB rates, free, no API key)."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import requests

from investment_tracker.config import CONFIG_DIR
from investment_tracker.dates import month_end, to_period

FRANKFURTER_BASE = "https://api.frankfurter.dev/v1"
CACHE_PATH = CONFIG_DIR / "fx_cache.json"
TIMEOUT = 20

# Used when the currencies endpoint is unreachable.
FALLBACK_CURRENCIES = {
    "AUD", "BGN", "BRL", "CAD", "CHF", "CNY", "CZK", "DKK", "EUR", "GBP",
    "HKD", "HUF", "IDR", "ILS", "INR", "ISK", "JPY", "KRW", "MXN", "MYR",
    "NOK", "NZD", "PHP", "PLN", "RON", "SEK", "SGD", "THB", "TRY", "USD",
    "ZAR",
}


class FxError(Exception):
    pass


class FxConverter:
    """Convert amounts using month-end ECB rates from Frankfurter.

    Rates are cached under ~/.config/investment-tracker/fx_cache.json so the
    app still works offline after a successful fetch.
    """

    def __init__(self, cache_path: Path | None = None, session: requests.Session | None = None):
        self.cache_path = cache_path or CACHE_PATH
        self.session = session or requests.Session()
        # pair -> {ISO date -> rate} meaning 1 FROM = rate TO
        self._rates: dict[str, dict[str, float]] = {}
        self._supported: set[str] | None = None
        self.warnings: list[str] = []
        self._load_cache()

    def _pair_key(self, from_ccy: str, to_ccy: str) -> str:
        return f"{from_ccy.upper()}_{to_ccy.upper()}"

    def _load_cache(self) -> None:
        if not self.cache_path.exists():
            return
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        rates = payload.get("rates") if isinstance(payload, dict) else None
        if isinstance(rates, dict):
            self._rates = {
                str(pair): {str(day): float(rate) for day, rate in mapping.items()}
                for pair, mapping in rates.items()
                if isinstance(mapping, dict)
            }
        cached_codes = payload.get("currencies") if isinstance(payload, dict) else None
        if isinstance(cached_codes, list) and cached_codes:
            self._supported = {str(code).upper() for code in cached_codes}

    def _save_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "source": "frankfurter.dev",
            "rates": self._rates,
            "currencies": sorted(self._supported or []),
        }
        tmp = self.cache_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.cache_path)

    def supported_currencies(self) -> set[str]:
        if self._supported:
            return self._supported
        try:
            response = self.session.get(
                f"{FRANKFURTER_BASE}/currencies",
                timeout=TIMEOUT,
                allow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException:
            self._supported = set(FALLBACK_CURRENCIES)
            self.warnings.append(
                "Could not refresh Frankfurter's currency list; using a built-in set of major codes."
            )
            return self._supported
        if isinstance(payload, dict) and payload:
            self._supported = {str(code).upper() for code in payload}
        else:
            self._supported = set(FALLBACK_CURRENCIES)
        return self._supported

    def prefetch(self, currencies: list[str], start: date, end: date, base: str = "USD") -> None:
        """Download timeseries for every currency that is not the base."""
        self.warnings.clear()
        base = (base or "USD").upper()
        supported = self.supported_currencies()

        if base not in supported:
            self.warnings.append(
                f"{base} is not a reporting currency Frankfurter supports. "
                "Use a three-letter code such as USD, EUR, GBP, CAD or CHF."
            )
            try:
                self._save_cache()
            except OSError:
                pass
            return

        today = date.today()
        if end > today:
            end = today
        if start > end:
            start = end

        unique = sorted({ccy.upper() for ccy in currencies if ccy})
        skipped: list[str] = []
        for currency in unique:
            if currency == base:
                continue
            if currency not in supported:
                skipped.append(currency)
                continue
            try:
                self._fetch_pair(currency, base, start, end)
            except FxError as exc:
                self.warnings.append(str(exc))
        if skipped:
            self.warnings.append(
                "Unsupported account currencies (skipped): " + ", ".join(skipped) + "."
            )
        try:
            self._save_cache()
        except OSError as exc:
            self.warnings.append(f"Could not save FX cache: {exc}")

    def _fetch_pair(self, from_ccy: str, to_ccy: str, start: date, end: date) -> None:
        key = self._pair_key(from_ccy, to_ccy)
        padded_start = start - timedelta(days=10)
        url = f"{FRANKFURTER_BASE}/{padded_start.isoformat()}..{end.isoformat()}"
        try:
            response = self.session.get(
                url,
                params={"from": from_ccy, "to": to_ccy},
                timeout=TIMEOUT,
                allow_redirects=True,
            )
            if response.status_code == 404:
                raise FxError(
                    f"Frankfurter has no rates for {from_ccy}->{to_ccy}. "
                    "Check that both codes are valid three-letter currencies."
                )
            response.raise_for_status()
            payload = response.json()
        except FxError:
            raise
        except requests.RequestException as exc:
            if key in self._rates:
                self.warnings.append(
                    f"Using cached {from_ccy}/{to_ccy} rates (Frankfurter unreachable: {exc})"
                )
                return
            raise FxError(f"Frankfurter request failed for {from_ccy}->{to_ccy}: {exc}") from exc

        series = payload.get("rates") or {}
        stored = self._rates.setdefault(key, {})
        for day, mapping in series.items():
            if isinstance(mapping, dict) and to_ccy in mapping:
                stored[day] = float(mapping[to_ccy])
        if not stored:
            raise FxError(f"Frankfurter returned no rates for {from_ccy}->{to_ccy}")

    def rate_on(self, from_ccy: str, to_ccy: str, on: date) -> float | None:
        from_ccy, to_ccy = from_ccy.upper(), to_ccy.upper()
        if from_ccy == to_ccy:
            return 1.0
        key = self._pair_key(from_ccy, to_ccy)
        series = self._rates.get(key) or {}
        if not series:
            inverse = self._rates.get(self._pair_key(to_ccy, from_ccy)) or {}
            if inverse:
                day = self._on_or_before(inverse, on)
                if day is not None:
                    value = inverse[day]
                    return None if value == 0 else 1.0 / value
            return None
        day = self._on_or_before(series, on)
        if day is None:
            return None
        return series[day]

    @staticmethod
    def _on_or_before(series: dict[str, float], on: date) -> str | None:
        target = on.isoformat()
        candidates = [day for day in series if day <= target]
        if not candidates:
            return None
        return max(candidates)

    def convert(self, amount: float, from_ccy: str, to_ccy: str, yearmonth: int) -> float | None:
        period = to_period(yearmonth)
        rate = self.rate_on(from_ccy, to_ccy, month_end(period))
        if rate is None:
            return None
        return float(amount) * rate
