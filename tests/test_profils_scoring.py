"""Tests du CRUD des profils de pondération du score et de leur application."""

import shutil

import pytest
from fastapi import HTTPException

import peadvisor.config as config
from peadvisor.routers.administration import (appliquer_profil_scoring, creer_profil_scoring,
                                              criteres_du_score, lister_profils_scoring,
                                              modifier_profil_scoring, supprimer_profil_scoring)
from peadvisor.services.importer import importer


@pytest.fixture()
def config_isolee(tmp_path, monkeypatch):
    """DOSSIER_CONFIG temporaire avec scoring.yaml/settings.yaml copiés."""
    for f in ("scoring.yaml", "settings.yaml"):
        shutil.copy(config.DOSSIER_CONFIG / f, tmp_path / f)
    monkeypatch.setattr(config, "DOSSIER_CONFIG", tmp_path)
    return tmp_path


def test_dix_familles_de_criteres(config_isolee):
    meta = criteres_du_score()
    assert len(meta["criteres"]) == 10
    assert {"potentiel", "valorisation", "croissance", "qualite", "solidite",
            "momentum", "dividende", "volatilite", "consensus", "esg"} == set(meta["criteres"])


def test_profils_preenregistres(config_isolee):
    profils = lister_profils_scoring()
    assert {"Value", "Growth", "Dividend", "Quality", "Momentum", "IA"} <= set(profils)
    assert profils["Value"]["valorisation"] == 30


def test_crud_profil(config_isolee):
    creer_profil_scoring({"nom": "Perso", "ponderations": {"momentum": 60, "qualite": 40}})
    assert "Perso" in lister_profils_scoring()
    # Doublon rejeté.
    with pytest.raises(HTTPException):
        creer_profil_scoring({"nom": "Perso", "ponderations": {"momentum": 1}})
    # Mise à jour.
    modifier_profil_scoring("Perso", {"momentum": 70, "esg": 30})
    assert lister_profils_scoring()["Perso"]["esg"] == 30
    # Suppression.
    supprimer_profil_scoring("Perso")
    assert "Perso" not in lister_profils_scoring()


def test_validation_criteres_inconnus(config_isolee):
    with pytest.raises(HTTPException):
        creer_profil_scoring({"nom": "X", "ponderations": {"inexistant": 10}})
    with pytest.raises(HTTPException):
        creer_profil_scoring({"nom": "Y", "ponderations": {"momentum": -5}})


def test_appliquer_profil_rescore(config_isolee, session):
    importer(session, "seed")
    r = appliquer_profil_scoring("Growth", session=session)
    assert r["profil"] == "Growth"
    assert r["actifs_recalcules"] > 0
    # Les pondérations actives valent désormais celles du profil Growth.
    assert config.charger_scoring()["ponderations"]["croissance"] == 30
