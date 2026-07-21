"""Tests du profil investisseur (interrupteurs de l'écran Paramètres)."""

import pytest
from fastapi import HTTPException

import peadvisor.config as config
from peadvisor.routers.administration import consulter_profil, modifier_profil


@pytest.fixture()
def config_isolee(tmp_path, monkeypatch):
    """Écrit profil.yaml dans un dossier temporaire, pas dans le dépôt."""
    monkeypatch.setattr(config, "DOSSIER_CONFIG", tmp_path)
    return tmp_path


def test_profil_par_defaut(config_isolee):
    profil = consulter_profil()
    # Cœur du profil (d'autres clés d'apparence existent aussi).
    for cle, val in {"objectif": "equilibre", "niveau_risque": 4,
                     "horizon_annees": 10, "algorithme_decision": "topsis"}.items():
        assert profil[cle] == val
    assert "couleur_actions" in profil and "largeur_barre" in profil
    assert "yahoo" in profil["urls_exemple"]        # URL exemple par source
    assert profil["colonnes_actions"] == []          # jeu par défaut du front


def test_modification_et_persistance(config_isolee):
    resultat = modifier_profil({"objectif": "dividendes", "niveau_risque": 6,
                                "algorithme_decision": "weighted"})
    assert resultat["objectif"] == "dividendes"
    # Relecture depuis le fichier : la modification persiste, l'horizon garde sa valeur.
    profil = consulter_profil()
    assert profil["niveau_risque"] == 6
    assert profil["algorithme_decision"] == "weighted"
    assert profil["horizon_annees"] == 10


def test_champs_inconnus_ignores(config_isolee):
    resultat = modifier_profil({"objectif": "croissance", "piratage": "oui"})
    assert "piratage" not in resultat


@pytest.mark.parametrize("maj", [
    {"objectif": "yolo"},
    {"algorithme_decision": "ahp"},          # pas encore implémenté
    {"niveau_risque": 8},
    {"niveau_risque": "4"},                  # type strict
    {"horizon_annees": 0},
])
def test_validations(config_isolee, maj):
    with pytest.raises(HTTPException):
        modifier_profil(maj)
