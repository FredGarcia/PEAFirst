"""Moteur de scoring (niveau L2 — Analyse).

Chaque actif reçoit des sous-notes de 0 à 100 (potentiel, valorisation,
croissance, ESG, dividende, volatilité, consensus), puis un score global
pondéré selon config/scoring.yaml. Si une donnée est absente, la pondération
est redistribuée sur les critères disponibles afin de ne pas pénaliser
artificiellement l'actif.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from peadvisor.config import charger_scoring
from peadvisor.models import Actif, HistoriqueScore


def _normaliser(valeur: float | None, borne_min: float, borne_max: float, inverser: bool = False) -> float | None:
    """Projette une valeur brute sur l'échelle 0-100 entre [borne_min, borne_max]."""
    if valeur is None:
        return None
    ratio = (valeur - borne_min) / (borne_max - borne_min)
    ratio = min(1.0, max(0.0, ratio))
    if inverser:
        ratio = 1.0 - ratio
    return round(ratio * 100, 1)


def calculer_sous_scores(actif: dict[str, Any] | Actif, config: dict | None = None) -> dict[str, float | None]:
    """Calcule les sous-notes 0-100 d'un actif (dict ou modèle ORM), pour les
    10 familles de critères (valorisation, croissance, qualité, solidité,
    momentum, dividende, volatilité, consensus, ESG, potentiel)."""
    cfg = config or charger_scoring()
    bornes = cfg["bornes"]

    def val(champ: str):
        return actif.get(champ) if isinstance(actif, dict) else getattr(actif, champ, None)

    def borne(nom: str, valeur, inverser=False):
        b = bornes.get(nom)
        return _normaliser(valeur, b["min"], b["max"], inverser) if b else None

    # Potentiel : recalculé depuis l'objectif de cours si disponible.
    potentiel = val("potentiel")
    if potentiel is None and val("objectif_cours") and val("cours"):
        potentiel = round((val("objectif_cours") / val("cours") - 1) * 100, 2)

    # Qualité financière : marge nette = (BNA × nb titres) / CA, proxy de ROE/ROIC.
    marge = None
    if val("bna") and val("nb_titres") and val("ca"):
        chiffre_affaires = val("ca") * 1e6            # CA stocké en M€
        if chiffre_affaires:
            marge = val("bna") * val("nb_titres") / chiffre_affaires * 100

    # Solidité : dette nette rapportée à la capitalisation (négatif = trésorerie nette).
    levier = None
    if val("dette_nette") is not None and val("capitalisation"):
        levier = val("dette_nette") / val("capitalisation")

    # Momentum : performance ~12 mois issue du moteur quantitatif.
    quant = val("indicateurs_quant")
    if isinstance(quant, str):
        try:
            quant = json.loads(quant)
        except (ValueError, TypeError):
            quant = None
    momentum = quant.get("perf_1an_pct") if isinstance(quant, dict) else None

    return {
        "potentiel": borne("potentiel", potentiel),
        "valorisation": _normaliser(val("per"), bornes["per"]["min"], bornes["per"]["max"], inverser=True),
        "croissance": borne("croissance", val("croissance")),
        "qualite": borne("qualite", marge),
        "solidite": borne("solidite", levier, inverser=True),
        "momentum": borne("momentum", momentum),
        "dividende": _normaliser(val("rendement"), bornes["dividende"]["min"], bornes["dividende"]["max"]),
        "volatilite": _normaliser(val("volatilite"), bornes["volatilite"]["min"], bornes["volatilite"]["max"], inverser=True),
        "consensus": _normaliser(val("consensus"), bornes["consensus"]["min"], bornes["consensus"]["max"]),
        "esg": val("score_esg"),
    }


def calculer_score_global(sous_scores: dict[str, float | None], config: dict | None = None) -> float:
    """Score pondéré 0-100, avec redistribution des poids sur les critères renseignés."""
    cfg = config or charger_scoring()
    poids = cfg["ponderations"]
    disponibles = {c: n for c, n in sous_scores.items() if n is not None and poids.get(c, 0) > 0}
    if not disponibles:
        return float(cfg.get("note_donnee_manquante", 50))
    total_poids = sum(poids[c] for c in disponibles)
    score = sum(note * poids[c] for c, note in disponibles.items()) / total_poids
    return round(score, 1)


def deriver_niveau_risque(volatilite: float | None) -> int | None:
    """Échelle 1-7 (type SRI) dérivée de la volatilité annualisée, si non fournie."""
    if volatilite is None:
        return None
    seuils = [(0.5, 1), (5, 2), (12, 3), (20, 4), (25, 5), (30, 6)]
    for seuil, niveau in seuils:
        if volatilite < seuil:
            return niveau
    return 7


def scorer_tous(session: Session) -> int:
    """Recalcule sous-notes, score global et niveau de risque de tous les actifs.

    Alimente aussi l'historique des scores. Renvoie le nombre d'actifs traités.
    """
    cfg = charger_scoring()
    actifs = session.query(Actif).all()
    for actif in actifs:
        if actif.objectif_cours and actif.cours:
            actif.potentiel = round((actif.objectif_cours / actif.cours - 1) * 100, 2)
        sous = calculer_sous_scores(actif, cfg)
        actif.sous_scores = json.dumps(sous)
        actif.score_global = calculer_score_global(sous, cfg)
        if actif.niveau_risque is None:
            actif.niveau_risque = deriver_niveau_risque(actif.volatilite)
        session.add(HistoriqueScore(
            actif_id=actif.id,
            date=datetime.utcnow(),
            score_global=actif.score_global,
            cours=actif.cours,
        ))
    session.commit()
    return len(actifs)
