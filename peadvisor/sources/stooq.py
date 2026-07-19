"""Stooq (https://stooq.com) — historiques quotidiens au format CSV,
**gratuit et sans clé API**. Suffixe des valeurs françaises : .fr (minuscules).

C'est la source réelle la plus simple à activer : `donnees.source_active: stooq`
dans config/settings.yaml, sans aucune configuration supplémentaire.
"""

from __future__ import annotations

import csv
import io
from typing import Any

import requests

from peadvisor.sources.http import SourceHTTPBase

URL = "https://stooq.com/q/d/l/"


class SourceStooq(SourceHTTPBase):
    nom = "stooq"
    necessite_cle = False
    pause_s = 0.5

    def symbole(self, ticker: str) -> str:
        return ticker.lower() if "." in ticker else f"{ticker.lower()}.fr"

    def serie(self, symbole: str, cle: str | None = None) -> list[dict[str, Any]]:
        reponse = requests.get(URL, params={"s": symbole, "i": "d"}, timeout=20)
        reponse.raise_for_status()
        points = []
        for ligne in csv.DictReader(io.StringIO(reponse.text)):
            if ligne.get("Date") and ligne.get("Close"):
                try:
                    points.append({"date": ligne["Date"], "cours": float(ligne["Close"])})
                except ValueError:
                    continue
        return sorted(points, key=lambda p: p["date"])

    def cotation(self, symbole: str, cle: str | None = None) -> dict[str, Any]:
        # Pas d'endpoint de cotation dédié : le dernier point de la série fait foi.
        points = self.serie(symbole, cle)
        return {"cours": points[-1]["cours"]} if points else {}
