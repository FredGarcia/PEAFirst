import math

from peadvisor.models import Actif, HistoriqueCours
from peadvisor.services.importer import importer
from peadvisor.services.quantitatif import MIN_POINTS, calculer_indicateurs, correlations


def test_serie_constante():
    indicateurs = calculer_indicateurs([100.0] * 100)
    assert indicateurs["volatilite_pct"] == 0.0
    assert indicateurs["perf_1an_pct"] == 0.0
    assert indicateurs["drawdown_max_pct"] == 0.0
    assert indicateurs["sharpe"] is None  # écart-type nul


def test_serie_trop_courte():
    assert calculer_indicateurs([100.0] * (MIN_POINTS - 1)) is None


def test_drawdown_et_perf():
    # 100 → 120 → 60 → 90 : pire baisse = -50 % depuis le plus-haut de 120.
    cours = ([100 + i for i in range(21)]      # monte à 120
             + [120 - 3 * i for i in range(1, 21)]  # chute à 60
             + [60 + i for i in range(1, 31)])      # remonte à 90
    indicateurs = calculer_indicateurs(cours)
    assert indicateurs["drawdown_max_pct"] == -50.0
    assert indicateurs["var_95_jour_pct"] > 0


def test_volatilite_annualisee_coherente():
    # Alternance +1 % / -1 % : écart-type quotidien ≈ 1 % → vol ≈ 15,9 %.
    cours = [100.0]
    for i in range(300):
        cours.append(cours[-1] * (1.01 if i % 2 == 0 else 0.99))
    indicateurs = calculer_indicateurs(cours)
    attendu = 0.01 * math.sqrt(252) * 100
    assert abs(indicateurs["volatilite_pct"] - attendu) < 1.0


def test_import_alimente_historique_et_indicateurs(session):
    journal = importer(session, "seed")
    assert "historique" in journal.detail

    actif = session.query(Actif).filter(Actif.isin == "FR0000120271").one()
    nb_points = session.query(HistoriqueCours).filter(
        HistoriqueCours.actif_id == actif.id).count()
    assert nb_points >= 700
    assert actif.indicateurs_quant is not None
    # La volatilité réalisée (calibrée sur la volatilité déclarée de 22 %)
    # a remplacé la valeur déclarative, à la précision statistique près.
    assert 12 < actif.volatilite < 35

    # Réimport : l'historique est append-only, aucun doublon de date.
    importer(session, "seed")
    assert session.query(HistoriqueCours).filter(
        HistoriqueCours.actif_id == actif.id).count() == nb_points


def test_correlations(session):
    importer(session, "seed")
    resultat = correlations(session, ["FR0000120271", "FR0000121014", "INCONNU00000"])
    assert set(resultat["isins"]) == {"FR0000120271", "FR0000121014"}
    matrice = resultat["matrice"]
    assert matrice["FR0000120271"]["FR0000120271"] == 1.0
    croisee = matrice["FR0000120271"]["FR0000121014"]
    assert croisee is not None and -1.0 <= croisee <= 1.0
    # Symétrie
    assert croisee == matrice["FR0000121014"]["FR0000120271"]
