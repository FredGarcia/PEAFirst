"""Référentiel des instruments (niveau L1) — résolution d'identifiants.

OpenFIGI (https://www.openfigi.com) n'est **pas une source de cours** mais un
annuaire : il fait correspondre un **ISIN** à son (ses) ticker(s) et place(s)
de cotation. C'est la brique qui, le jour du référentiel complet, permettra de
résoudre automatiquement le bon symbole pour chaque source de cours (chacune a
son format : .PA, .PAR, .XPAR…).

API v3 (POST /v3/mapping) : clé facultative (quota plus élevé avec clé).
⚠️ La v2 ferme le 1er juillet 2026 — on cible directement la v3.
"""

from __future__ import annotations

from typing import Any

import requests

from peadvisor.config import cle_api

URL = "https://api.openfigi.com/v3/mapping"


def resoudre_isin(isin: str, code_place: str = "GR") -> dict[str, Any]:
    """Résout un ISIN en ticker/place via OpenFIGI.

    Args:
        isin: Code ISIN (12 caractères).
        code_place: Code place OpenFIGI (ex. "GR" = Euronext Paris, "GY" = Xetra).

    Renvoie {"isin", "ticker", "place", "type", "nom"} ou {"isin", "erreur"}.
    """
    isin = isin.strip().upper()
    entetes = {"Content-Type": "application/json"}
    cle = cle_api("openfigi", "OPENFIGI_API_KEY")
    if cle:
        entetes["X-OPENFIGI-APIKEY"] = cle

    requete = {"idType": "ID_ISIN", "idValue": isin}
    if code_place:
        requete["exchCode"] = code_place
    try:
        reponse = requests.post(URL, json=[requete], headers=entetes, timeout=20)
        reponse.raise_for_status()
        bloc = reponse.json()[0]
    except Exception as exc:
        return {"isin": isin, "erreur": f"{type(exc).__name__} : {exc}"}

    if bloc.get("warning") or not bloc.get("data"):
        return {"isin": isin, "erreur": bloc.get("warning", "aucune correspondance")}
    premier = bloc["data"][0]
    return {
        "isin": isin,
        "ticker": premier.get("ticker"),
        "place": premier.get("exchCode"),
        "type": premier.get("securityType"),
        "nom": premier.get("name"),
    }
