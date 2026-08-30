"""Marketstack (https://marketstack.com) — historiques end-of-day, symboles
suffixés par le code MIC de la place (Euronext Paris : .XPAR)."""

from __future__ import annotations

from typing import Any

from peadvisor.sources.http import SourceHTTPBase

URL = "https://api.marketstack.com/v1"


class SourceMarketstack(SourceHTTPBase):
    nom = "marketstack"
    nom_cle = "marketstack"
    variable_env = "MARKETSTACK_API_KEY"
    pause_s = 0.5

    def symbole(self, ticker: str) -> str:
        return ticker if "." in ticker else f"{ticker}.XPAR"

    def cotation(self, symbole: str, cle: str | None) -> dict[str, Any]:
        data = self._get_json(f"{URL}/eod/latest",
                              {"access_key": cle, "symbols": symbole})
        lignes = data.get("data", []) if isinstance(data, dict) else []
        if lignes and lignes[0].get("close"):
            return {"cours": float(lignes[0]["close"])}
        return {}

    def serie(self, symbole: str, cle: str | None) -> list[dict[str, Any]]:
        data = self._get_json(f"{URL}/eod",
                              {"access_key": cle, "symbols": symbole, "limit": 1000})
        lignes = data.get("data", []) if isinstance(data, dict) else []
        return sorted(
            ({"date": str(l["date"])[:10], "cours": float(l["close"])}
             for l in lignes if l.get("date") and l.get("close")),
            key=lambda p: p["date"],
        )
