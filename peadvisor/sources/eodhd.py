"""EODHD (https://eodhd.com) — cotations temps réel différé et historiques
end-of-day, très bonne couverture européenne. Suffixe Paris : .PA."""

from __future__ import annotations

from typing import Any

from peadvisor.sources.http import SourceHTTPBase

URL = "https://eodhd.com/api"


class SourceEODHD(SourceHTTPBase):
    nom = "eodhd"
    nom_cle = "eodhd"
    variable_env = "EODHD_API_TOKEN"
    pause_s = 0.2

    def cotation(self, symbole: str, cle: str | None) -> dict[str, Any]:
        data = self._get_json(f"{URL}/real-time/{symbole}",
                              {"api_token": cle, "fmt": "json"})
        if not isinstance(data, dict):
            return {}
        champs: dict[str, Any] = {}
        prix = data.get("close") or data.get("last")
        if prix and prix != "NA":
            champs["cours"] = float(prix)
        if data.get("market_capitalization"):
            champs["capitalisation"] = round(float(data["market_capitalization"]) / 1e6, 1)
        if data.get("pe_ratio"):
            champs["per"] = float(data["pe_ratio"])
        if data.get("dividend_yield"):
            champs["rendement"] = float(data["dividend_yield"])
        return champs

    def serie(self, symbole: str, cle: str | None) -> list[dict[str, Any]]:
        data = self._get_json(f"{URL}/eod/{symbole}",
                              {"api_token": cle, "fmt": "json", "period": "d"})
        lignes = data if isinstance(data, list) else []
        return sorted(
            ({"date": str(l["date"])[:10],
              "cours": float(l.get("adjusted_close") or l["close"])}
             for l in lignes if l.get("date") and (l.get("adjusted_close") or l.get("close"))),
            key=lambda p: p["date"],
        )
