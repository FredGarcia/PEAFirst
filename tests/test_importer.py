from peadvisor.models import Actif
from peadvisor.services.importer import _normaliser, importer


def test_normalisation_rejette_les_invalides():
    assert _normaliser({"isin": "FR0000120271", "nom": "Total", "type": "ACTION"}) is not None
    assert _normaliser({"isin": "TROPCOURT", "nom": "X", "type": "ACTION"}) is None
    assert _normaliser({"isin": "FR0000120271", "nom": "", "type": "ACTION"}) is None
    assert _normaliser({"isin": "FR0000120271", "nom": "X", "type": "INCONNU"}) is None


def test_import_seed_puis_reimport_sans_doublon(session):
    journal1 = importer(session, "seed")
    assert journal1.statut == "succes"
    assert journal1.nb_crees > 0
    total = session.query(Actif).count()
    assert total == journal1.nb_crees

    # Réimport : tout doit passer en mise à jour, aucun doublon créé.
    journal2 = importer(session, "seed")
    assert journal2.nb_crees == 0
    assert journal2.nb_maj == total
    assert session.query(Actif).count() == total

    # Les scores ont été calculés.
    actif = session.query(Actif).first()
    assert actif.score_global is not None
    assert 0 <= actif.score_global <= 100
