from __future__ import annotations

from typing import Any

from peadvisor.sources.base import SourceDonnees
from peadvisor.sources.seed import SourceSeed


class SourceFinancialModelingPrep(SourceDonnees):
    nom = "financialmodelingprep"

    def recuperer(self) -> list[dict[str, Any]]:
        try:
            import os
            import requests
        except ImportError as exc:
            raise RuntimeError(
                "La source 'financialmodelingprep' nécessite requests : pip install requests"
            ) from exc

        api_key = os.getenv("FMP_API_KEY")
        if not api_key:
            raise RuntimeError(
                "La source 'financialmodelingprep' nécessite la variable d'environnement FMP_API_KEY"
            )

        base = SourceSeed().recuperer()
        resultats: list[dict[str, Any]] = []

        for actif in base:
            ticker = actif.get("mnemonique")
            if not ticker or actif.get("type") == "OPCVM":
                resultats.append(actif)
                continue

            symbole = ticker if "." in ticker else f"{ticker}.PA"
            try:
                url = "https://financialmodelingprep.com/stable/quote"
                params = {
                    "symbol": symbole,
                    "apikey": api_key,
                }
                data = requests.get(url, params=params, timeout=20).json()
                quote = data[0] if isinstance(data, list) and data else {}

                maj = dict(actif)
                prix = quote.get("price")
                if prix:
                    maj["cours"] = float(prix)

                cap = quote.get("marketCap")
                if cap:
                    maj["capitalisation"] = round(float(cap) / 1e6, 1)

                pe = quote.get("pe")
                if pe:
                    maj["per"] = float(pe)

                div = quote.get("dividendYield")
                if div:
                    maj["rendement"] = round(float(div), 2)

                target = quote.get("priceTarget")
                if target:
                    maj["objectif_cours"] = float(target)

                resultats.append(maj)
            except Exception:
                resultats.append(actif)

        return resultats
