from __future__ import annotations

from datetime import date
from pathlib import Path

import requests

from investment_tracker.currency import FxConverter


class _FakeResponse:
    def __init__(self, status: int, payload=None, url: str = ""):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.url = url

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error for url: {self.url}")

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self):
        self.urls: list[str] = []

    def get(self, url, params=None, **_kwargs):
        self.urls.append(url)
        params = params or {}
        if url.endswith("/currencies"):
            return _FakeResponse(200, {"USD": "US Dollar", "EUR": "Euro", "GBP": "Pound", "CAD": "Canadian Dollar"})
        if params.get("to") == "CHD" or params.get("from") == "CHD":
            full = f"{url}?from={params.get('from')}&to={params.get('to')}"
            return _FakeResponse(404, {}, full)
        to_ccy = params.get("to", "USD")
        return _FakeResponse(200, {"rates": {"2024-01-31": {to_ccy: 1.1}}})


def test_unknown_reporting_currency_does_not_call_timeseries(tmp_path: Path):
    session = _FakeSession()
    fx = FxConverter(cache_path=tmp_path / "fx.json", session=session)
    fx.prefetch(["USD", "EUR", "GBP", "CAD"], date(2019, 1, 21), date(2026, 8, 31), base="CHD")
    assert any("CHD" in warning and "not a reporting currency" in warning for warning in fx.warnings)
    timeseries_calls = [url for url in session.urls if ".." in url]
    assert timeseries_calls == []


def test_supported_pair_still_fetches(tmp_path: Path):
    session = _FakeSession()
    fx = FxConverter(cache_path=tmp_path / "fx.json", session=session)
    fx.prefetch(["EUR"], date(2024, 1, 1), date(2024, 1, 31), base="USD")
    assert fx.warnings == []
    assert any(".." in url for url in session.urls)
    assert fx.convert(10.0, "EUR", "USD", 202401) == 11.0
