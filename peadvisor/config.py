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
