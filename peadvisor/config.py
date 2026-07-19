"""Chargement du paramétrage YAML (config/settings.yaml et config/scoring.yaml).

Le paramétrage est rechargé à la demande afin qu'une modification des
fichiers YAML soit prise en compte sans redémarrage ni modification du code.
"""

from __future__ import annotations

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
