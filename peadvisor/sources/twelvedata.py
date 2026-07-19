from __future__ import annotations

from typing import Any

from peadvisor.sources.base import SourceDonnees
from peadvisor.sources.seed import SourceSeed

class SourceTwelveData(SourceDonnees):
    nom = "twelvedata"

    def recuperer(self) -> list[dict[str, Any]]:
        try:
            import os
            import requests
        except ImportError as exc:
            raise RuntimeError(
                "La source 'twelvedata' nécessite requests : pip install requests"
            ) from exc

        api_key = os.getenv("TWELVEDATA_API_KEY")
        if not api_key:
            raise RuntimeError(
                "La source 'twelvedata' nécessite la variable d'environnement TWELVEDATA_API_KEY"
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
                url = "https://api.twelvedata.com/quote"
                params = {
                    "symbol": symbole,
                    "apikey": api_key,
                }
                data = requests.get(url, params=params, timeout=20).json()

                maj = dict(actif)
                if isinstance(data, dict):
                    prix = data.get("close")
                    if prix:
                        maj["cours"] = float(prix)

                    cap = data.get("market_cap")
                    if cap:
                        maj["capitalisation"] = round(float(cap) / 1e6, 1)

                    pe = data.get("pe_ratio")
                    if pe:
                        maj["per"] = float(pe)

                    div = data.get("dividend_yield")
                    if div:
                        maj["rendement"] = round(float(div), 2)

                resultats.append(maj)
            except Exception:
                resultats.append(actif)

        return resultats