"""Une même valeur acquise depuis des sources différentes = une ligne par source ;
ré-acquérir depuis la même source met à jour la ligne existante (pas de doublon)."""

import peadvisor.sources.web as web
from peadvisor.models import Actif
from peadvisor.services.importer import importer
from peadvisor.services.scraping import importer_valeur
from peadvisor.sources.boursorama import parser_page

PAGE = ('<title>TOTALENERGIES Cours Action TTE</title>'
        '<body class="eligible-pea"> FR0000120271 '
        '<span class="c-instrument c-instrument--last" data-ist-last="61.50">61,50</span></body>')


def test_meme_source_ne_duplique_pas(session):
    importer(session, "seed")
    n1 = session.query(Actif).count()
    importer(session, "seed")            # ré-import même source → mise à jour
    assert session.query(Actif).count() == n1


def test_source_differente_ajoute_une_ligne(session, monkeypatch):
    def page(source):
        return lambda requete: {**parser_page(PAGE), "source": source}

    monkeypatch.setattr(web.SCRAPERS["boursorama"], "recuperer_custom", page("boursorama"))
    r1 = importer_valeur(session, "boursorama", "TotalEnergies")
    monkeypatch.setattr(web.SCRAPERS["zonebourse"], "recuperer_custom", page("zonebourse"))
    r2 = importer_valeur(session, "zonebourse", "TotalEnergies")

    assert r1["cree"] is True and r2["cree"] is True     # deux lignes distinctes
    lignes = session.query(Actif).filter(Actif.isin == "FR0000120271").all()
    assert {a.source for a in lignes} == {"boursorama", "zonebourse"}

    # Ré-acquérir depuis boursorama met à jour la ligne boursorama (pas de 3e ligne).
    r3 = importer_valeur(session, "boursorama", "TotalEnergies")
    assert r3["cree"] is False
    assert session.query(Actif).filter(Actif.isin == "FR0000120271").count() == 2


def test_suppression_ligne_unique_par_id(session, monkeypatch):
    from peadvisor.routers.actifs import supprimer_ligne

    monkeypatch.setattr(web.SCRAPERS["boursorama"], "recuperer_custom",
                        lambda requete: {**parser_page(PAGE), "source": "boursorama"})
    importer_valeur(session, "boursorama", "TotalEnergies")
    ligne = session.query(Actif).filter(Actif.isin == "FR0000120271").one()
    r = supprimer_ligne(ligne.id, session=session)
    assert r["id"] == ligne.id
    assert session.query(Actif).filter(Actif.isin == "FR0000120271").count() == 0
