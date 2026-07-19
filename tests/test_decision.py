from peadvisor.services.decision import classer
from peadvisor.services.importer import importer
from peadvisor.models import Actif


def test_topsis_classe_tous_les_actifs(session):
    importer(session, "seed")
    actifs = session.query(Actif).all()
    classement = classer(actifs, "topsis")
    assert len(classement) == len(actifs)
    coefficients = [c for _, c in classement]
    assert all(0.0 <= c <= 1.0 for c in coefficients)
    assert coefficients == sorted(coefficients, reverse=True)


def test_classement_pondere_suit_le_score(session):
    importer(session, "seed")
    actifs = session.query(Actif).all()
    classement = classer(actifs, "weighted")
    scores = [s for _, s in classement]
    assert scores == sorted(scores, reverse=True)
