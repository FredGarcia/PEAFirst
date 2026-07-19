from __future__ import annotations

from typing import Any

from peadvisor.sources.base import SourceDonnees
from peadvisor.sources.seed import SourceSeed

class SourceEODHD(SourceDonnees):
    nom = "eodhd"

    def recuperer(self) -> list[dict[str, Any]]:
        try:
            import os
            import requests
        except ImportError as exc:
            raise RuntimeError(
                "La source 'eodhd' nécessite requests : pip install requests"
            ) from exc

        api_key = os.getenv("EODHD_API_TOKEN")
        if not api_key:
            raise RuntimeError(
                "La source 'eodhd' nécessite la variable d'environnement EODHD_API_TOKEN"
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
                url = f"https://eodhd.com/api/real-time/{symbole}"
                params = {
                    "api_token": api_key,
                    "fmt": "json",
                }
                data = requests.get(url, params=params, timeout=20).json()

                maj = dict(actif)
                if isinstance(data, dict):
                    prix = data.get("close") or data.get("last")
                    if prix:
                        maj["cours"] = float(prix)

                    if data.get("market_capitalization"):
                        maj["capitalisation"] = round(float(data["market_capitalization"]) / 1e6, 1)

                    if data.get("pe_ratio"):
                        maj["per"] = float(data["pe_ratio"])

                    if data.get("dividend_yield"):
                        maj["rendement"] = float(data["dividend_yield"])

                resultats.append(maj)
            except Exception:
                resultats.append(actif)

        return resultats
