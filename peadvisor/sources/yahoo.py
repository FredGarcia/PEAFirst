"""Source Yahoo Finance (via la bibliothèque yfinance, optionnelle).

Met à jour cours, capitalisation, PER, rendement, objectif de cours et
consensus pour les actifs dont le mnémonique Yahoo est connu. La liste des
tickers interrogés est celle du jeu de données seed (champ `mnemonique`,
suffixé ".PA" pour Euronext Paris le cas échéant).

yfinance n'étant pas une API officielle, cette source est fournie comme
connecteur de départ : quotas et robustesse sont gérés au mieux (voir
docs/02-architecture.md pour brancher une source de données payante).
"""

from __future__ import annotations

from typing import Any

from peadvisor.sources.base import SourceDonnees
from peadvisor.sources.seed import SourceSeed


class SourceYahoo(SourceDonnees):
    nom = "yahoo"

    def recuperer(self) -> list[dict[str, Any]]:
        try:
            import yfinance as yf  # dépendance optionnelle
        except ImportError as exc:
            raise RuntimeError(
                "La source 'yahoo' nécessite la bibliothèque yfinance : pip install yfinance"
            ) from exc

        base = SourceSeed().recuperer()
        resultats: list[dict[str, Any]] = []
        for actif in base:
            ticker = actif.get("mnemonique")
            if not ticker or actif.get("type") == "OPCVM":
                # Les OPCVM ne sont pas cotés sur Yahoo : on conserve la fiche telle quelle.
                resultats.append(actif)
                continue
            symbole = ticker if "." in ticker else f"{ticker}.PA"
            try:
                info = yf.Ticker(symbole).info or {}
                maj = dict(actif)
                maj["cours"] = info.get("currentPrice") or info.get("regularMarketPrice") or actif.get("cours")
                if info.get("marketCap"):
                    maj["capitalisation"] = round(info["marketCap"] / 1e6, 1)
                maj["per"] = info.get("trailingPE") or actif.get("per")
                if info.get("dividendYield"):
                    maj["rendement"] = round(info["dividendYield"] * 100, 2)
                maj["objectif_cours"] = info.get("targetMeanPrice") or actif.get("objectif_cours")
                if info.get("recommendationMean"):
                    # Yahoo : 1 = achat fort ... 5 = vente → on inverse vers notre échelle 1-5.
                    maj["consensus"] = round(6 - info["recommendationMean"], 2)
                resultats.append(maj)
            except Exception:
                # Erreur réseau/quota sur un titre : on retombe sur la fiche locale.
                resultats.append(actif)
        return resultats
