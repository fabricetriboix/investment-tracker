from __future__ import annotations

from datetime import date
from pathlib import Path

import requests

from investment_tracker.currency import FALLBACK_CURRENCIES, FxConverter


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, currencies=None):
        self.currencies = currencies or {"USD": "US Dollar", "EUR": "Euro", "GBP": "Pound"}
        self.calls: list[str] = []

    def get(self, url, params=None, timeout=None, allow_redirects=True):
        self.calls.append(url)
        if url.endswith("/currencies"):
            return _FakeResponse(self.currencies)
        raise requests.HTTPError("404")


def test_unsupported_currency_is_reported_once(tmp_path: Path):
    session = _FakeSession()
    fx = FxConverter(cache_path=tmp_path / "fx.json", session=session)
    fx.prefetch(["USD", "CHD", "XYZ"], start=date(2024, 1, 31), end=date(2024, 3, 31), base="USD")
    assert len(fx.warnings) == 1
    assert "CHD" in fx.warnings[0]
    assert "XYZ" in fx.warnings[0]
    assert not any("timeseries" in call or ".." in call for call in session.calls)


def test_fallback_currency_list_includes_majors():
    assert {"USD", "EUR", "GBP", "CAD", "CHF"} <= FALLBACK_CURRENCIES
    assert "CHD" not in FALLBACK_CURRENCIES
