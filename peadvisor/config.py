"""Chargement du paramétrage YAML (config/settings.yaml et config/scoring.yaml).

Le paramétrage est rechargé à la demande afin qu'une modification des
fichiers YAML soit prise en compte sans redémarrage ni modification du code.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_CONFIG = RACINE / "config"
CHEMIN_BDD = RACINE / "peadvisor.db"


def _charger(nom_fichier: str) -> dict[str, Any]:
    chemin = DOSSIER_CONFIG / nom_fichier
    with open(chemin, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def charger_settings() -> dict[str, Any]:
    return _charger("settings.yaml")


def charger_scoring() -> dict[str, Any]:
    return _charger("scoring.yaml")


def sauvegarder_scoring(config: dict[str, Any]) -> None:
    chemin = DOSSIER_CONFIG / "scoring.yaml"
    with open(chemin, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)


# Profil investisseur : valeurs par défaut si config/profil.yaml n'existe pas.
# objectif : "croissance" (capitalisation) | "dividendes" (revenus) | "equilibre"
PROFIL_DEFAUT: dict[str, Any] = {
    "objectif": "equilibre",
    "niveau_risque": 4,
    "horizon_annees": 10,
    "algorithme_decision": "topsis",   # "weighted" | "topsis"
    # Largeur de la barre latérale (px), paramétrable.
    "largeur_barre": 210,
    # Délai minimal (minutes) entre deux réactualisations du tableau.
    "reactualisation_minutes": 5,
    # Couleur d'en-tête de chaque tableau de valeurs (paramétrable).
    "couleur_actions": "#2a78d6",
    "couleur_etf": "#008300",
    "couleur_opcvm": "#e87ba4",
    # Colonnes visibles par onglet (liste de clés ; vide = jeu par défaut du front).
    "colonnes_actions": [],
    "colonnes_etf": [],
    "colonnes_opcvm": [],
    # URL d'une page exemple par source, renvoyée (en JSON) par le bouton « Tester ».
    "urls_exemple": {
        "yahoo": "https://query1.finance.yahoo.com/v8/finance/chart/AI.PA?range=5d&interval=1d",
        "stooq": "https://stooq.com/q/d/l/?s=tte.fr&i=d",
        "alphavantage": "https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=TTE.PAR&apikey=demo",
        "twelvedata": "https://api.twelvedata.com/quote?symbol=TTE&mic_code=XPAR&apikey=demo",
        "financialmodelingprep": "https://financialmodelingprep.com/api/v3/quote/TTE.PA?apikey=demo",
        "eodhd": "https://eodhd.com/api/real-time/TTE.PA?api_token=demo&fmt=json",
        "marketstack": "https://api.marketstack.com/v1/eod/latest?access_key=demo&symbols=TTE.XPAR",
        "boursorama": "https://www.boursorama.com/cours/1rPAI/",
    },
}


def charger_profil() -> dict[str, Any]:
    """Profil investisseur (config/profil.yaml, écrit par l'application)."""
    profil = dict(PROFIL_DEFAUT)
    chemin = DOSSIER_CONFIG / "profil.yaml"
    if chemin.exists():
        with open(chemin, encoding="utf-8") as f:
            contenu = yaml.safe_load(f) or {}
        profil.update({k: v for k, v in contenu.items() if k in PROFIL_DEFAUT})
    return profil


def sauvegarder_profil(maj: dict[str, Any]) -> dict[str, Any]:
    profil = charger_profil()
    profil.update({k: v for k, v in maj.items() if k in PROFIL_DEFAUT})
    with open(DOSSIER_CONFIG / "profil.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(profil, f, allow_unicode=True, sort_keys=False)
    return profil


# --- Profils de pondération du score (10 familles de critères) --------------

# Familles de critères : clé → (libellé, variables couvertes).
CRITERES_SCORE: dict[str, dict[str, str]] = {
    "potentiel":    {"libelle": "Potentiel", "variables": "Upside calculé (objectif / cours)"},
    "valorisation": {"libelle": "Valorisation", "variables": "PER (EV/EBITDA, P/B, PEG à venir)"},
    "croissance":   {"libelle": "Croissance", "variables": "CA, EPS, FCF"},
    "qualite":      {"libelle": "Qualité financière", "variables": "Marge nette (proxy ROE/ROIC)"},
    "solidite":     {"libelle": "Solidité", "variables": "Dette nette / capitalisation"},
    "momentum":     {"libelle": "Momentum", "variables": "Performance ~12 mois"},
    "dividende":    {"libelle": "Dividende", "variables": "Rendement (croissance, payout à venir)"},
    "volatilite":   {"libelle": "Volatilité / Risque", "variables": "Volatilité annualisée (bêta à venir)"},
    "consensus":    {"libelle": "Consensus", "variables": "Objectif et recommandations analystes"},
    "esg":          {"libelle": "ESG", "variables": "Note ESG globale"},
}

# Profils de pondération préenregistrés (modifiables via le CRUD).
PROFILS_SCORING_DEFAUT: dict[str, dict[str, float]] = {
    "Value":    {"potentiel": 15, "valorisation": 30, "croissance": 10, "qualite": 10,
                 "solidite": 10, "momentum": 5, "dividende": 5, "volatilite": 10,
                 "consensus": 3, "esg": 2},
    "Growth":   {"potentiel": 20, "valorisation": 10, "croissance": 30, "qualite": 10,
                 "solidite": 5, "momentum": 10, "dividende": 0, "volatilite": 5,
                 "consensus": 5, "esg": 5},
    "Dividend": {"potentiel": 10, "valorisation": 15, "croissance": 5, "qualite": 10,
                 "solidite": 15, "momentum": 5, "dividende": 30, "volatilite": 10,
                 "consensus": 5, "esg": 5},
    "Quality":  {"potentiel": 10, "valorisation": 15, "croissance": 15, "qualite": 25,
                 "solidite": 15, "momentum": 0, "dividende": 10, "volatilite": 5,
                 "consensus": 3, "esg": 2},
    "Momentum": {"potentiel": 15, "valorisation": 5, "croissance": 20, "qualite": 10,
                 "solidite": 5, "momentum": 30, "dividende": 0, "volatilite": 5,
                 "consensus": 5, "esg": 5},
    # IA : profil équilibré orienté facteurs empiriquement robustes (qualité,
    # momentum, valorisation) ; affinable par l'auto-amélioration (onglet Système).
    "IA":       {"potentiel": 10, "valorisation": 15, "croissance": 15, "qualite": 15,
                 "solidite": 10, "momentum": 12, "dividende": 5, "volatilite": 10,
                 "consensus": 4, "esg": 4},
}


def charger_profils_scoring() -> dict[str, dict[str, float]]:
    """Profils de pondération (config/profils_scoring.yaml). Initialisé avec les
    profils préenregistrés au premier accès."""
    chemin = DOSSIER_CONFIG / "profils_scoring.yaml"
    if not chemin.exists():
        sauvegarder_profils_scoring(PROFILS_SCORING_DEFAUT)
        return {k: dict(v) for k, v in PROFILS_SCORING_DEFAUT.items()}
    with open(chemin, encoding="utf-8") as f:
        contenu = yaml.safe_load(f) or {}
    return contenu.get("profils", {})


def sauvegarder_profils_scoring(profils: dict[str, dict[str, float]]) -> None:
    with open(DOSSIER_CONFIG / "profils_scoring.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump({"profils": profils}, f, allow_unicode=True, sort_keys=False)


def charger_cles() -> dict[str, str]:
    """Clés API des sources de données (config/cles_api.yaml, jamais versionné)."""
    chemin = DOSSIER_CONFIG / "cles_api.yaml"
    if not chemin.exists():
        return {}
    with open(chemin, encoding="utf-8") as f:
        return {k: str(v) for k, v in (yaml.safe_load(f) or {}).items() if v}


def cle_api(nom_source: str | None, variable_env: str | None = None) -> str | None:
    """Clé API d'une source : la variable d'environnement prime sur le fichier."""
    if variable_env and os.getenv(variable_env):
        return os.getenv(variable_env)
    if nom_source:
        return charger_cles().get(nom_source)
    return None
