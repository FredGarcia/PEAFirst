"""Tests du simulateur d'investissement."""

import math

import pytest
from pydantic import ValidationError

from peadvisor.schemas import DemandeSimulation
from peadvisor.services.simulation import simuler


def test_versement_obligatoire():
    with pytest.raises(ValidationError):
        DemandeSimulation(capital_initial=0, versement_mensuel=0, horizon_annees=10)


def test_capitalisation_versement_unique():
    # 10 000 € à 5 %/an sur 10 ans, sans versement ni dividende, dividendes réinvestis.
    d = DemandeSimulation(capital_initial=10000, horizon_annees=10,
                          rendement_prix_pct=5, rendement_dividende_pct=0)
    r = simuler(d)
    med = r.scenarios["median"]
    assert med.versements_cumules == 10000
    # ≈ 10000 × 1,05^10 = 16289 (mensualisé, très proche)
    assert abs(med.valeur_finale_brute - 10000 * 1.05 ** 10) < 20
    assert med.trajectoire[-1]["annee"] == 10


def test_ordre_des_scenarios():
    d = DemandeSimulation(capital_initial=10000, horizon_annees=10,
                          rendement_prix_pct=5, volatilite_pct=15)
    r = simuler(d)
    assert (r.scenarios["prudent"].valeur_finale_brute
            < r.scenarios["median"].valeur_finale_brute
            < r.scenarios["optimiste"].valeur_finale_brute)
    # L'écart annualisé = volatilité / racine(horizon).
    assert abs(r.ecart_scenario_pct - 15 / math.sqrt(10)) < 0.05


def test_ecart_se_resserre_avec_horizon():
    court = simuler(DemandeSimulation(capital_initial=10000, horizon_annees=4,
                                      rendement_prix_pct=5, volatilite_pct=20))
    long = simuler(DemandeSimulation(capital_initial=10000, horizon_annees=25,
                                     rendement_prix_pct=5, volatilite_pct=20))
    assert court.ecart_scenario_pct > long.ecart_scenario_pct


def test_fiscalite_pea_avant_et_apres_seuil():
    # Après 5 ans : exonéré d'IR, seuls les prélèvements sociaux (17,2 %).
    apres = simuler(DemandeSimulation(capital_initial=10000, horizon_annees=8,
                                      rendement_prix_pct=6)).scenarios["median"]
    assert apres.exonere_ir
    assert abs(apres.impot_estime - apres.plus_value_brute * 0.172) < 0.5

    # Avant 5 ans : PFU 30 %.
    avant = simuler(DemandeSimulation(capital_initial=10000, horizon_annees=3,
                                      rendement_prix_pct=6)).scenarios["median"]
    assert not avant.exonere_ir
    assert abs(avant.impot_estime - avant.plus_value_brute * 0.30) < 0.5


def test_reinvestissement_dividendes():
    base = dict(capital_initial=10000, horizon_annees=10, rendement_prix_pct=4,
                rendement_dividende_pct=3)
    avec = simuler(DemandeSimulation(**base, reinvestir_dividendes=True)).scenarios["median"]
    sans = simuler(DemandeSimulation(**base, reinvestir_dividendes=False)).scenarios["median"]
    # Réinvestir capitalise les dividendes : valeur finale plus élevée.
    assert avec.valeur_finale_brute > sans.valeur_finale_brute
    assert avec.dividendes_percus == 0  # tout est capitalisé
    assert sans.dividendes_percus > 0   # versés en numéraire


def test_versements_programmes_cumules():
    d = DemandeSimulation(capital_initial=1000, versement_mensuel=100, horizon_annees=5,
                          rendement_prix_pct=0, rendement_dividende_pct=0)
    med = simuler(d).scenarios["median"]
    # 1000 + 100 × 60 = 7000 versés ; sans rendement, valeur ≈ versements.
    assert med.versements_cumules == 7000
    assert abs(med.valeur_finale_brute - 7000) < 1
    assert med.impot_estime == 0  # pas de plus-value
