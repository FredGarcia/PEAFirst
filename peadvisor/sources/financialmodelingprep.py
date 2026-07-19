"""Financial Modeling Prep (https://financialmodelingprep.com) — cotations et
fondamentaux (PER, capitalisation, objectif de cours). Suffixe Paris : .PA."""

from __future__ import annotations

from typing import Any

from peadvisor.sources.http import SourceHTTPBase

URL = "https://financialmodelingprep.com/stable"


class SourceFinancialModelingPrep(SourceHTTPBase):
    nom = "financialmodelingprep"
    nom_cle = "financialmodelingprep"
    variable_env = "FMP_API_KEY"
    pause_s = 0.3

    def cotation(self, symbole: str, cle: str | None) -> dict[str, Any]:
        data = self._get_json(f"{URL}/quote", {"symbol": symbole, "apikey": cle})
        quote = data[0] if isinstance(data, list) and data else {}
        champs: dict[str, Any] = {}
        if quote.get("price"):
            champs["cours"] = float(quote["price"])
        if quote.get("marketCap"):
            champs["capitalisation"] = round(float(quote["marketCap"]) / 1e6, 1)
        if quote.get("pe"):
            champs["per"] = float(quote["pe"])
        if quote.get("dividendYield"):
            champs["rendement"] = round(float(quote["dividendYield"]), 2)
        if quote.get("priceTarget"):
            champs["objectif_cours"] = float(quote["priceTarget"])
        return champs

    def serie(self, symbole: str, cle: str | None) -> list[dict[str, Any]]:
        data = self._get_json(f"{URL}/historical-price-eod/light",
                              {"symbol": symbole, "apikey": cle})
        lignes = data if isinstance(data, list) else data.get("historical", [])
        points = []
        for ligne in lignes:
            cours = ligne.get("price") or ligne.get("close")
            if ligne.get("date") and cours:
                points.append({"date": str(ligne["date"])[:10], "cours": float(cours)})
        return sorted(points, key=lambda p: p["date"])
