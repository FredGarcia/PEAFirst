from peadvisor.services.scoring import (
    _normaliser,
    calculer_score_global,
    calculer_sous_scores,
    deriver_niveau_risque,
)


def test_normalisation_bornes():
    assert _normaliser(50.0, -20, 50) == 100.0
    assert _normaliser(-20.0, -20, 50) == 0.0
    assert _normaliser(999.0, -20, 50) == 100.0   # plafonné
    assert _normaliser(5.0, 5, 40, inverser=True) == 100.0  # PER bas = bonne note
    assert _normaliser(None, 0, 1) is None


def test_sous_scores_et_potentiel_calcule():
    actif = {"cours": 100.0, "objectif_cours": 120.0, "per": 10.0, "rendement": 4.0,
             "croissance": 10.0, "volatilite": 20.0, "score_esg": 70, "consensus": 4.0}
    sous = calculer_sous_scores(actif)
    # potentiel = +20 % → (20 - (-20)) / 70 = 57.1
    assert sous["potentiel"] == 57.1
    assert sous["esg"] == 70
    assert 0 <= sous["valorisation"] <= 100


def test_score_global_redistribue_les_poids_manquants():
    complet = calculer_score_global({"potentiel": 80, "valorisation": 80, "croissance": 80,
                                     "esg": 80, "dividende": 80, "volatilite": 80, "consensus": 80})
    assert complet == 80.0
    partiel = calculer_score_global({"potentiel": 80, "valorisation": None, "croissance": None,
                                     "esg": None, "dividende": None, "volatilite": None,
                                     "consensus": None})
    assert partiel == 80.0  # seul critère disponible → 100 % du poids
    vide = calculer_score_global({c: None for c in ["potentiel", "esg"]})
    assert vide == 50.0  # note neutre


def test_niveau_risque_derive():
    assert deriver_niveau_risque(3.0) == 2
    assert deriver_niveau_risque(15.0) == 4
    assert deriver_niveau_risque(50.0) == 7
    assert deriver_niveau_risque(None) is None
