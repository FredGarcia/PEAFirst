"""Financial Modeling Prep (https://financialmodelingprep.com).

⚠️ L'offre **gratuite est essentiellement limitée aux valeurs américaines** ;
les endpoints `/stable/` et de nombreuses données européennes exigent un plan
payant (HTTP 402). On cible ici l'API historique v3 (compatible clés
anciennes) ; sur une clé gratuite récente, les valeurs Euronext peuvent
renvoyer 402/403 — voir docs/09-sources-donnees.md.
"""

from __future__ import annotations

from typing import Any

from peadvisor.sources.http import SourceHTTPBase

URL = "https://financialmodelingprep.com/api/v3"


class SourceFinancialModelingPrep(SourceHTTPBase):
    nom = "financialmodelingprep"
    nom_cle = "financialmodelingprep"
    variable_env = "FMP_API_KEY"
    pause_s = 0.3

    def cotation(self, symbole: str, cle: str | None) -> dict[str, Any]:
        data = self._get_json(f"{URL}/quote/{symbole}", {"apikey": cle})
        quote = data[0] if isinstance(data, list) and data else {}
        champs: dict[str, Any] = {}
        if quote.get("price"):
            champs["cours"] = float(quote["price"])
        if quote.get("marketCap"):
            champs["capitalisation"] = round(float(quote["marketCap"]) / 1e6, 1)
        if quote.get("pe"):
            champs["per"] = float(quote["pe"])
        return champs

    def serie(self, symbole: str, cle: str | None) -> list[dict[str, Any]]:
        data = self._get_json(f"{URL}/historical-price-full/{symbole}",
                              {"apikey": cle, "serietype": "line"})
        lignes = data.get("historical", []) if isinstance(data, dict) else []
        return sorted(
            ({"date": str(l["date"])[:10], "cours": float(l["close"])}
             for l in lignes if l.get("date") and l.get("close")),
            key=lambda p: p["date"],
        )
