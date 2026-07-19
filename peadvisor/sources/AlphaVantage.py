from __future__ import annotations

from typing import Any

from peadvisor.sources.base import SourceDonnees
from peadvisor.sources.seed import SourceSeed


class SourceAlphaVantage(SourceDonnees):
    nom = "alphavantage"

    def recuperer(self) -> list[dict[str, Any]]:
        try:
            import os
            import requests
        except ImportError as exc:
            raise RuntimeError(
                "La source 'alphavantage' nécessite requests : pip install requests"
            ) from exc

        api_key = os.getenv("ALPHAVANTAGE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "La source 'alphavantage' nécessite la variable d'environnement ALPHAVANTAGE_API_KEY"
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
                url = "https://www.alphavantage.co/query"
                params = {
                    "function": "GLOBAL_QUOTE",
                    "symbol": symbole,
                    "apikey": api_key,
                }
                data = requests.get(url, params=params, timeout=20).json()
                quote = data.get("Global Quote", {}) if isinstance(data, dict) else {}

                maj = dict(actif)
                prix = quote.get("05. price")
                if prix:
                    maj["cours"] = float(prix)

                volume = quote.get("06. volume")
                if volume:
                    maj["volume"] = int(volume)

                resultats.append(maj)
            except Exception:
                resultats.append(actif)

        return resultats
