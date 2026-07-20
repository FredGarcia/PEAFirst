"""Moteur macro (niveau L1 — Collecte, données de contexte).

Récupère des données institutionnelles **gratuites et sans clé** auprès de la
Banque centrale européenne (portail SDMX, format CSV) :

- le **taux sans risque** de la zone euro (rendement des emprunts d'État notés
  AAA), qui alimente les ratios de Sharpe et de Sortino du moteur quantitatif
  — remplaçant le taux jusque-là codé en dur ;
- les **taux de change** face à l'euro (pour de futures conversions d'actifs
  libellés hors EUR).

Tout est optionnel et sûr hors-ligne : si la source distante échoue ou si
`macro.taux_sans_risque_source: fixe`, on retombe sur la valeur paramétrée
dans config/settings.yaml. Aucune dépendance nouvelle (requests, déjà présent).

Référence : ECB Data Portal, API SDMX 2.1 (https://data.ecb.europa.eu/help/api).
"""

from __future__ import annotations

import csv
import io
import logging

import requests

from peadvisor.config import charger_settings

logger = logging.getLogger("peadvisor.macro")

ECB_BASE = "https://data-api.ecb.europa.eu/service/data"

# Séries SDMX de la BCE.
SERIE_TAUX_10A = "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y"  # courbe AAA zone euro, 10 ans
FLUX_CHANGE = "EXR"  # taux de change quotidiens


def _derniere_observation_ecb(cle_serie: str) -> dict | None:
    """Dernière observation d'une série BCE (CSV SDMX). None si indisponible."""
    url = f"{ECB_BASE}/{cle_serie}"
    reponse = requests.get(url, params={"lastNObservations": 1, "format": "csvdata"},
                           timeout=20)
    reponse.raise_for_status()
    lignes = list(csv.DictReader(io.StringIO(reponse.text)))
    if not lignes:
        return None
    derniere = lignes[-1]
    valeur = derniere.get("OBS_VALUE")
    if valeur in (None, "", "NaN"):
        return None
    return {"date": derniere.get("TIME_PERIOD"), "valeur": float(valeur)}


def taux_sans_risque(settings: dict | None = None) -> dict:
    """Taux sans risque annuel (%) à utiliser pour Sharpe/Sortino.

    Renvoie {"taux": float, "source": str, "date": str | None}. La source est
    pilotée par macro.taux_sans_risque_source :
      - "fixe" (défaut) : valeur de quantitatif.taux_sans_risque_pct ;
      - "bce"           : rendement 10 ans des emprunts AAA de la zone euro,
                          avec repli sur la valeur fixe en cas d'échec.
    """
    settings = settings or charger_settings()
    fixe = float(settings.get("quantitatif", {}).get("taux_sans_risque_pct", 2.5))
    source = settings.get("macro", {}).get("taux_sans_risque_source", "fixe")

    if source == "bce":
        try:
            obs = _derniere_observation_ecb(SERIE_TAUX_10A)
            if obs is not None:
                return {"taux": round(obs["valeur"], 3), "source": "bce_10a_aaa",
                        "date": obs["date"]}
            logger.warning("Taux sans risque BCE indisponible : repli sur la valeur fixe.")
        except Exception as exc:
            logger.warning("Échec de récupération du taux BCE (%s) : repli sur la valeur fixe.", exc)
    return {"taux": fixe, "source": "fixe", "date": None}


def taux_change(devise: str, settings: dict | None = None) -> dict | None:
    """Taux de change 1 unité de `devise` → EUR (BCE, quotidien).

    La BCE cote EUR→devise (D.<devise>.EUR.SP00.A) ; on renvoie l'inverse pour
    convertir un montant exprimé dans la devise vers l'euro. None si indispo.
    """
    devise = devise.upper()
    if devise == "EUR":
        return {"devise": "EUR", "taux_vers_eur": 1.0, "date": None, "source": "identite"}
    try:
        obs = _derniere_observation_ecb(f"{FLUX_CHANGE}/D.{devise}.EUR.SP00.A")
        if obs and obs["valeur"]:
            return {"devise": devise, "taux_vers_eur": round(1 / obs["valeur"], 6),
                    "date": obs["date"], "source": "bce"}
    except Exception as exc:
        logger.warning("Taux de change %s indisponible : %s", devise, exc)
    return None
