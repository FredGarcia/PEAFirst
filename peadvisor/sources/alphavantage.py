"""AlphaVantage (https://www.alphavantage.co) — clé gratuite très limitée
(~25 requêtes/jour) : à réserver aux tests. Suffixe Euronext Paris : .PAR."""

from __future__ import annotations

from typing import Any

from peadvisor.sources.http import SourceHTTPBase

URL = "https://www.alphavantage.co/query"


class SourceAlphaVantage(SourceHTTPBase):
    nom = "alphavantage"
    nom_cle = "alphavantage"
    variable_env = "ALPHAVANTAGE_API_KEY"
    pause_s = 12.0  # quota gratuit : ~5 requêtes/minute

    def symbole(self, ticker: str) -> str:
        return ticker if "." in ticker else f"{ticker}.PAR"

    def cotation(self, symbole: str, cle: str | None) -> dict[str, Any]:
        data = self._get_json(URL, {"function": "GLOBAL_QUOTE", "symbol": symbole,
                                    "apikey": cle})
        quote = data.get("Global Quote", {}) if isinstance(data, dict) else {}
        prix = quote.get("05. price")
        return {"cours": float(prix)} if prix else {}

    def serie(self, symbole: str, cle: str | None) -> list[dict[str, Any]]:
        data = self._get_json(URL, {"function": "TIME_SERIES_DAILY", "symbol": symbole,
                                    "outputsize": "compact", "apikey": cle})
        series = data.get("Time Series (Daily)", {}) if isinstance(data, dict) else {}
        return sorted(
            ({"date": jour, "cours": float(valeurs["4. close"])}
             for jour, valeurs in series.items() if valeurs.get("4. close")),
            key=lambda p: p["date"],
        )
