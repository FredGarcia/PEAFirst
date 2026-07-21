"""Test de la réactualisation en masse du tableau (re-scrape + rescoring)."""

import peadvisor.sources.boursorama as bourso
from peadvisor.models import Actif
from peadvisor.routers.actifs import reactualiser_actifs
from peadvisor.services.importer import importer
from peadvisor.sources.boursorama import parser_page

PAGE = ('<html><head><title>TOTALENERGIES Cours Action TTE</title></head>'
        '<body class="eligible-pea"> FR0000120271 '
        '<span class="c-instrument c-instrument--last" data-ist-last="61.50">61,50</span>'
        '<span class="c-instrument c-instrument--variation">+0,80%</span></body></html>')


def test_reactualiser_met_a_jour_les_valeurs(monkeypatch, session):
    importer(session, "seed")
    # Toutes les valeurs re-scrapées renvoient la même page de test.
    monkeypatch.setattr(bourso, "code_ou_recherche", lambda requete: "1rPTTE")
    monkeypatch.setattr(bourso, "recuperer_un", lambda code: parser_page(PAGE))

    r = reactualiser_actifs(session=session)
    assert r["actifs_maj"] > 0
    assert r["echecs"] == 0
    assert r["actifs_recalcules"] >= r["actifs_maj"]

    # La fiche TotalEnergies porte le nouveau cours issu du scrape.
    tte = session.query(Actif).filter(Actif.isin == "FR0000120271").one()
    assert tte.cours == 61.50 and tte.variation_pct == 0.80
