import pytest

from peadvisor.schemas import DemandeAllocation
from peadvisor.services.allocation import proposer_allocation
from peadvisor.services.importer import importer


@pytest.mark.parametrize("risque,objectif", [(1, "equilibre"), (4, "dividendes"), (7, "croissance")])
def test_allocation_respecte_les_contraintes(session, risque, objectif):
    importer(session, "seed")
    demande = DemandeAllocation(capital=50000, niveau_risque=risque,
                                horizon_annees=10, objectif=objectif)
    reponse = proposer_allocation(session, demande)

    assert reponse.lignes, "au moins une ligne proposée"
    # Les poids somment à ~100 % et les montants au capital.
    assert abs(sum(l.poids for l in reponse.lignes) - 1.0) < 0.01
    assert abs(sum(l.montant for l in reponse.lignes) - 50000) < 50
    # Plafond par ligne (10 % + tolérance de renormalisation).
    assert all(l.poids <= 0.13 for l in reponse.lignes)


def test_profil_prudent_evite_les_actifs_dynamiques(session):
    importer(session, "seed")
    demande = DemandeAllocation(capital=10000, niveau_risque=1,
                                horizon_annees=5, objectif="equilibre")
    reponse = proposer_allocation(session, demande)
    assert all((l.niveau_risque or 4) <= 5 for l in reponse.lignes)
