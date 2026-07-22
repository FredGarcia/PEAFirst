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


# Remplissage initial : nombre de valeurs cible par type (paramétrable dans
# config/settings.yaml → donnees.remplissage_initial). Au-delà des valeurs
# réelles curées, des valeurs de démonstration sont générées (ISIN, indicateurs
# illustratifs cohérents) pour atteindre ces effectifs.
CIBLES_DEFAUT = {"ACTION": 300, "ETF": 30, "OPCVM": 30}

_SECTEURS = ["Énergie", "Banque & Assurance", "Santé", "Technologie", "Industrie",
             "Consommation", "Télécoms", "Services aux collectivités", "Immobilier",
             "Matériaux", "Automobile", "Luxe", "Agroalimentaire", "Chimie", "Média"]


def cibles_remplissage() -> dict[str, int]:
    """Effectifs cible par type pour le remplissage initial (settings.yaml)."""
    from peadvisor.config import charger_settings

    cfg = (charger_settings().get("donnees", {}) or {}).get("remplissage_initial") or {}
    return {
        "ACTION": int(cfg.get("actions", CIBLES_DEFAUT["ACTION"])),
        "ETF": int(cfg.get("etf", CIBLES_DEFAUT["ETF"])),
        "OPCVM": int(cfg.get("opcvm", CIBLES_DEFAUT["OPCVM"])),
    }


def _generer_valeur(type_actif: str, indice: int) -> dict[str, Any]:
    """Valeur de démonstration cohérente (indicateurs illustratifs déterministes)."""
    prefixe = {"ACTION": "FR90", "ETF": "FR80", "OPCVM": "LU80"}[type_actif]
    isin = f"{prefixe}{indice:08d}"
    rng = random.Random(isin)
    cours = round(rng.uniform(12, 320), 2)
    per = round(rng.uniform(6, 38), 1)
    volatilite = round(rng.uniform(10, 42), 1)
    croissance = round(rng.uniform(-6, 26), 1)
    capitalisation = round(rng.uniform(300, 90000), 0)          # M€
    nb_titres = round(capitalisation * 1e6 / cours, 0)
    bna = round(cours / per, 2)                                  # EPS = cours / PER
    marge = rng.uniform(3, 22) / 100                            # marge nette cible
    ca = round(bna * nb_titres / marge / 1e6, 0)                 # CA en M€
    dette_nette = round(rng.uniform(-0.3, 1.6) * capitalisation, 0)
    potentiel = rng.uniform(-15, 45)
    base = {
        "isin": isin, "type": type_actif, "devise": "EUR",
        "pays": "France" if prefixe.startswith("FR") else "Luxembourg",
        "secteur": rng.choice(_SECTEURS), "eligible_pea": True,
        "cours": cours, "capitalisation": capitalisation, "volatilite": volatilite,
        "croissance": croissance, "score_esg": round(rng.uniform(30, 92), 0),
        "consensus": round(rng.uniform(2.4, 4.6), 2),
    }
    if type_actif == "ACTION":
        base.update({
            "nom": f"Valeur Démo {indice:03d}", "mnemonique": f"DMA{indice:04d}",
            "marche": "Euronext Paris", "per": per, "bna": bna, "nb_titres": nb_titres,
            "ca": ca, "dette_nette": dette_nette, "rendement": round(rng.uniform(0, 6), 2),
            "objectif_cours": round(cours * (1 + potentiel / 100), 2),
            "taux_distribution": round(rng.uniform(0, 80), 1),
        })
    elif type_actif == "ETF":
        base.update({
            "nom": f"ETF Démo {indice:03d}", "mnemonique": f"DME{indice:04d}",
            "marche": "Euronext Paris", "societe_gestion": "Gestionnaire Démo",
            "rendement": round(rng.uniform(0, 4), 2),
        })
    else:  # OPCVM
        base.update({
            "nom": f"OPCVM Démo {indice:03d}", "societe_gestion": "Gestionnaire Démo",
            "rendement": round(rng.uniform(0, 4), 2),
        })
    return base


class SourceSeed(SourceDonnees):
    nom = "seed"

    def recuperer(self) -> list[dict[str, Any]]:
        with open(CHEMIN_SEED, encoding="utf-8") as f:
            actifs = json.load(f)

        # Complète chaque type jusqu'à l'effectif cible avec des valeurs générées.
        cibles = cibles_remplissage()
        par_type: dict[str, int] = {}
        for a in actifs:
            par_type[a["type"]] = par_type.get(a["type"], 0) + 1
        for type_actif, cible in cibles.items():
            for i in range(par_type.get(type_actif, 0) + 1, cible + 1):
                actifs.append(_generer_valeur(type_actif, i))

        for actif in actifs:
            if actif.get("cours"):
                actif["historique"] = _generer_historique(
                    actif["isin"], actif["cours"],
                    actif.get("volatilite") or 20.0,
                    actif.get("croissance") or 5.0,
                )
        return actifs
