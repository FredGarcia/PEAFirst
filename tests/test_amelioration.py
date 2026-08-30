import json

import peadvisor.services.amelioration as amelioration
from peadvisor.models import SuggestionPonderations
from peadvisor.services.importer import importer
from tests.test_introspection import _fabriquer_historique


def test_optimisation_sans_historique(session):
    importer(session, "seed")
    resultat = amelioration.proposer_ponderations(session)
    assert resultat["suggestion"] is None
    assert "insuffisant" in resultat["detail"].lower()


def test_optimisation_trouve_des_ponderations_plus_predictives(session):
    importer(session, "seed")
    _fabriquer_historique(session)  # rendements corrélés à la sous-note dividende
    resultat = amelioration.proposer_ponderations(session)
    suggestion = resultat["suggestion"]
    assert suggestion is not None
    assert suggestion.correlation_apres > suggestion.correlation_avant
    poids = json.loads(suggestion.ponderations)
    # L'optimiseur doit augmenter le poids du critère réellement prédictif.
    assert poids["dividende"] > 10
    assert abs(sum(poids.values()) - 100) < 1


def test_application_suggestion(session, monkeypatch):
    importer(session, "seed")
    _fabriquer_historique(session)
    amelioration.proposer_ponderations(session)
    suggestion = session.query(SuggestionPonderations).first()

    sauvegardes = {}
    monkeypatch.setattr(amelioration, "sauvegarder_scoring",
                        lambda cfg: sauvegardes.update(cfg))
    resultat = amelioration.appliquer_suggestion(session, suggestion.id)
    assert suggestion.statut == "appliquee"
    assert sauvegardes["ponderations"] == resultat["ponderations"]
    assert resultat["actifs_recalcules"] > 0
