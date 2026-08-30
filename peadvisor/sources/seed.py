"""Source locale de démonstration.

Charge `peadvisor/data/seed_assets.json` : un échantillon représentatif
d'actions, d'ETF et d'OPCVM éligibles au PEA, avec des indicateurs
ILLUSTRATIFS (non temps réel) permettant de développer et de tester
l'application sans dépendance réseau.
"""

from __future__ import annotations

import json
import math
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from peadvisor.sources.base import SourceDonnees

CHEMIN_SEED = Path(__file__).resolve().parent.parent / "data" / "seed_assets.json"
NB_JOURS_HISTORIQUE = 750  # ~3 ans de séances


def _generer_historique(isin: str, cours_final: float, volatilite_pct: float,
                        croissance_pct: float) -> list[dict[str, Any]]:
    """Marche aléatoire géométrique déterministe (graine = ISIN), calibrée sur
    la volatilité déclarée de l'actif et ancrée sur son cours actuel.

    Illustratif : permet d'exercer le moteur quantitatif sans réseau. La série
    est re-générée à chaque import (l'ancrage au cours du jour déplace le
    chemin) ; les dates déjà en base ne sont pas réécrites par l'importeur.
    """
    rng = random.Random(isin)
    vol_jour = (volatilite_pct / 100) / math.sqrt(252)
    mu_jour = (croissance_pct / 100) / 252

    chemin = [1.0]
    for _ in range(NB_JOURS_HISTORIQUE - 1):
        rendement = mu_jour - 0.5 * vol_jour ** 2 + vol_jour * rng.gauss(0, 1)
        chemin.append(chemin[-1] * math.exp(rendement))
    facteur = cours_final / chemin[-1]

    # Jours ouvrés en remontant depuis aujourd'hui.
    dates: list[date] = []
    jour = date.today()
    while len(dates) < NB_JOURS_HISTORIQUE:
        if jour.weekday() < 5:
            dates.append(jour)
        jour -= timedelta(days=1)
    dates.reverse()

    return [{"date": d.isoformat(), "cours": round(p * facteur, 3)}
            for d, p in zip(dates, chemin)]


# Remplissage initial : plafond du nombre de VRAIES valeurs chargées par type
# (paramétrable dans config/settings.yaml → donnees.remplissage_initial). Aucune
# valeur n'est inventée : on charge le référentiel réel (seed_assets.json), au
# plus `cap` par type. Les indicateurs de marché du seed sont des points de
# départ indicatifs, remplacés par des données réelles via « Réactualiser ».
PLAFONDS_DEFAUT = {"ACTION": 300, "ETF": 30, "OPCVM": 30}


def cibles_remplissage() -> dict[str, int]:
    """Plafond par type pour le remplissage initial (settings.yaml)."""
    from peadvisor.config import charger_settings

    cfg = (charger_settings().get("donnees", {}) or {}).get("remplissage_initial") or {}
    return {
        "ACTION": int(cfg.get("actions", PLAFONDS_DEFAUT["ACTION"])),
        "ETF": int(cfg.get("etf", PLAFONDS_DEFAUT["ETF"])),
        "OPCVM": int(cfg.get("opcvm", PLAFONDS_DEFAUT["OPCVM"])),
    }


class SourceSeed(SourceDonnees):
    nom = "seed"

    def recuperer(self) -> list[dict[str, Any]]:
        with open(CHEMIN_SEED, encoding="utf-8") as f:
            reference = json.load(f)

        # Ne conserve que de vraies valeurs, au plus `cap` par type.
        plafonds = cibles_remplissage()
        comptes: dict[str, int] = {}
        actifs: list[dict[str, Any]] = []
        for actif in reference:
            type_actif = actif.get("type")
            plafond = plafonds.get(type_actif)
            if plafond is not None and comptes.get(type_actif, 0) >= plafond:
                continue
            comptes[type_actif] = comptes.get(type_actif, 0) + 1
            actifs.append(actif)

        for actif in actifs:
            if actif.get("cours"):
                actif["historique"] = _generer_historique(
                    actif["isin"], actif["cours"],
                    actif.get("volatilite") or 20.0,
                    actif.get("croissance") or 5.0,
                )
        return actifs
