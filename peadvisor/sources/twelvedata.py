"""Twelve Data (https://twelvedata.com) — bonne couverture Euronext (code MIC
XPAR), offre gratuite ~8 requêtes/minute et 800/jour."""

from __future__ import annotations

from typing import Any

from peadvisor.sources.http import SourceHTTPBase

URL = "https://api.twelvedata.com"


class SourceTwelveData(SourceHTTPBase):
    nom = "twelvedata"
    nom_cle = "twelvedata"
    variable_env = "TWELVEDATA_API_KEY"
    pause_s = 8.0  # quota gratuit : 8 requêtes/minute (2 requêtes par titre)

    def symbole(self, ticker: str) -> str:
        return ticker  # symbole nu, la place est passée via mic_code=XPAR

    def cotation(self, symbole: str, cle: str | None) -> dict[str, Any]:
        data = self._get_json(f"{URL}/quote", {"symbol": symbole, "mic_code": "XPAR",
                                               "apikey": cle})
        if not isinstance(data, dict) or data.get("status") == "error":
            return {}
        return {"cours": float(data["close"])} if data.get("close") else {}

    def serie(self, symbole: str, cle: str | None) -> list[dict[str, Any]]:
        data = self._get_json(f"{URL}/time_series",
                              {"symbol": symbole, "mic_code": "XPAR", "interval": "1day",
                               "outputsize": 750, "apikey": cle})
        valeurs = data.get("values", []) if isinstance(data, dict) else []
        return sorted(
            ({"date": v["datetime"][:10], "cours": float(v["close"])}
             for v in valeurs if v.get("close")),
            key=lambda p: p["date"],
        )
