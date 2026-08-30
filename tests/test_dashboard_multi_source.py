"""Le tableau de bord ne compte qu'une fois une valeur présente sous plusieurs
sources (dédoublonnage par ISIN)."""

import peadvisor.sources.web as web
from peadvisor.routers.dashboard import synthese
from peadvisor.services.importer import importer
from peadvisor.services.scraping import importer_valeur
from peadvisor.sources.boursorama import parser_page

PAGE = ('<title>TOTALENERGIES Cours Action TTE</title>'
        '<body class="eligible-pea"> FR0000120271 '
        '<span class="c-instrument c-instrument--last" data-ist-last="61.50">61,50</span></body>')


def test_synthese_dedoublonne_par_isin(session, monkeypatch):
    importer(session, "seed")
    n_avant = synthese(session=session)["nb_actifs"]

    # Ajoute une 2e ligne (source boursorama) pour un ISIN déjà présent (seed).
    monkeypatch.setattr(web.SCRAPERS["boursorama"], "recuperer_custom",
                        lambda requete: {**parser_page(PAGE), "source": "boursorama"})
    r = importer_valeur(session, "boursorama", "TotalEnergies")
    assert r["cree"] is True                       # nouvelle ligne (source différente)

    # Le nombre d'actifs du tableau de bord ne change pas (même ISIN).
    assert synthese(session=session)["nb_actifs"] == n_avant
