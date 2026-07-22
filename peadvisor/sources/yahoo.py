"""Source Yahoo Finance.

Deux chemins d'accès, du plus riche au plus robuste :
1. la bibliothèque **yfinance** (si installée) : cours, capitalisation, PER,
   rendement, objectif de cours, consensus et historique ~3 ans ;
2. à défaut, un **repli HTTP direct** sur l'API *chart* publique de Yahoo
   (`query1.finance.yahoo.com/v8/finance/chart/<symbole>`) qui renvoie du JSON
   sans dépendance : cours courant, devise et historique de clôtures.

La liste des tickers interrogés est celle du jeu seed (champ `mnemonique`,
suffixé « .PA » pour Euronext Paris le cas échéant).
"""

from __future__ import annotations

from typing import Any

import requests

from peadvisor.sources.base import SourceDonnees

CHART = "https://query1.finance.yahoo.com/v8/finance/chart/"
ENTETES = {"User-Agent": "Mozilla/5.0 (compatible; PEAdvisor/1.0)"}


class SourceYahoo(SourceDonnees):
    nom = "yahoo"

    def symbole(self, ticker: str) -> str:
        return ticker if "." in ticker else f"{ticker}.PA"

    def recuperer(self) -> list[dict[str, Any]]:
        try:
            import yfinance as yf  # dépendance optionnelle
        except ImportError:
            # yfinance absent : repli HTTP direct (au moins cours + historique).
            return self._recuperer_http()

        from peadvisor.sources.http import univers_de_base

        # Univers de référence SANS l'historique synthétique : une source
        # réelle ne doit jamais importer des séries de démonstration.
        base = univers_de_base()
        resultats: list[dict[str, Any]] = []
        for actif in base:
            ticker = actif.get("mnemonique")
            if not ticker or actif.get("type") == "OPCVM":
                # Les OPCVM ne sont pas cotés sur Yahoo : on conserve la fiche telle quelle.
                resultats.append(actif)
                continue
            symbole = ticker if "." in ticker else f"{ticker}.PA"
            try:
                titre = yf.Ticker(symbole)
                info = titre.info or {}
                maj = dict(actif)
                # Historique réel (~3 ans de clôtures) pour le moteur quantitatif.
                try:
                    cloture = titre.history(period="3y", interval="1d")["Close"].dropna()
                    maj["historique"] = [
                        {"date": idx.date().isoformat(), "cours": round(float(v), 4)}
                        for idx, v in cloture.items()
                    ]
                except Exception:
                    pass  # sans historique, l'actif reste exploitable
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

    def cotation_http(self, symbole: str) -> dict[str, Any]:
        """Cours + historique via l'API chart de Yahoo (JSON, sans yfinance)."""
        rep = requests.get(f"{CHART}{symbole}", params={"range": "3y", "interval": "1d"},
                           headers=ENTETES, timeout=20)
        rep.raise_for_status()
        resultat = rep.json()["chart"]["result"][0]
        meta = resultat.get("meta", {})
        donnees: dict[str, Any] = {}
        if meta.get("regularMarketPrice") is not None:
            donnees["cours"] = round(float(meta["regularMarketPrice"]), 4)
        if meta.get("currency"):
            donnees["devise"] = meta["currency"]
        horodatages = resultat.get("timestamp") or []
        clotures = (resultat.get("indicators", {}).get("quote", [{}])[0].get("close") or [])
        from datetime import datetime, timezone
        historique = [
            {"date": datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat(),
             "cours": round(float(c), 4)}
            for t, c in zip(horodatages, clotures) if c is not None
        ]
        if historique:
            donnees["historique"] = historique
        return donnees

    def _recuperer_http(self) -> list[dict[str, Any]]:
        from peadvisor.sources.http import univers_de_base

        resultats: list[dict[str, Any]] = []
        for actif in univers_de_base():
            ticker = actif.get("mnemonique")
            if not ticker or actif.get("type") == "OPCVM":
                resultats.append(actif)
                continue
            maj = dict(actif)
            try:
                maj.update(self.cotation_http(self.symbole(ticker)))
            except Exception:
                pass  # réseau/quota : on conserve la fiche locale
            resultats.append(maj)
        return resultats
