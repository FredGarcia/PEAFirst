"""Test du repli HTTP de Yahoo (API chart JSON, sans yfinance)."""

import peadvisor.sources.yahoo as yahoo
from peadvisor.sources.yahoo import SourceYahoo


class FausseReponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


CHART = {"chart": {"result": [{
    "meta": {"regularMarketPrice": 61.5, "currency": "EUR"},
    "timestamp": [1_700_000_000, 1_700_086_400],
    "indicators": {"quote": [{"close": [60.1, 61.5]}]},
}]}}


def test_symbole_suffixe_paris():
    assert SourceYahoo().symbole("TTE") == "TTE.PA"
    assert SourceYahoo().symbole("AAPL.US") == "AAPL.US"  # suffixe déjà présent


def test_cotation_http_parse_le_chart(monkeypatch):
    monkeypatch.setattr(yahoo.requests, "get", lambda *a, **k: FausseReponse(CHART))
    d = SourceYahoo().cotation_http("TTE.PA")
    assert d["cours"] == 61.5
    assert d["devise"] == "EUR"
    assert len(d["historique"]) == 2
    assert d["historique"][-1]["cours"] == 61.5
