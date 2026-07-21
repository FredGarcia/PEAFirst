"""Tests du service de recherche : type d'instrument, éligibilité, ventilation,
suppression de ligne."""

from peadvisor.models import Actif, TypeActif
from peadvisor.services.importer import importer
from peadvisor.sources.boursorama import parser_page

PAGE_ACTION = ('<title>AIR LIQUIDE Cours Action AI, Cotation Bourse - Boursorama</title>'
               'FR0000120073 eligible-pea data-ist-last="177.70"')
PAGE_ETF = ('<title>LYXOR CAC 40 Cours Tracker ETF, Cotation - Boursorama</title>'
            'FR0007052782 data-ist-last="60.10"')


def test_detection_type_depuis_titre():
    assert parser_page(PAGE_ACTION)["type_detecte"] == "ACTION"
    assert parser_page(PAGE_ETF)["type_detecte"] == "ETF"


def test_detection_eligibilite_pea():
    assert parser_page(PAGE_ACTION)["eligible_pea"] is True   # marqueur présent
    assert parser_page(PAGE_ETF)["eligible_pea"] is False      # marqueur absent


def test_recherche_ventile_selon_le_type(monkeypatch, session):
    import peadvisor.sources.web as web
    from peadvisor.services.scraping import importer_valeur

    # Un ETF scrapé (non éligible PEA ici) doit être créé avec le type ETF si
    # l'ajout est confirmé (confirmer=True).
    monkeypatch.setattr(web.SCRAPERS["boursorama"], "recuperer_custom",
                        lambda requete: parser_page(PAGE_ETF))
    r = importer_valeur(session, "boursorama", "Lyxor CAC 40", confirmer=True)
    assert r["type"] == "ETF" and r["onglet"] == "etf"
    etf = session.query(Actif).filter(Actif.isin == "FR0007052782").one()
    assert etf.type == TypeActif.ETF


def test_recherche_demande_confirmation_si_non_eligible(monkeypatch, session):
    import peadvisor.sources.web as web
    from peadvisor.services.scraping import importer_valeur

    monkeypatch.setattr(web.SCRAPERS["boursorama"], "recuperer_custom",
                        lambda requete: parser_page(PAGE_ETF))  # eligible_pea False

    # Sans confirmation : rien n'est enregistré, une confirmation est demandée.
    r = importer_valeur(session, "boursorama", "x")
    assert r["confirmation_requise"] is True
    assert r["eligible_pea"] is False and r["raison"]
    assert session.query(Actif).filter(Actif.isin == "FR0007052782").count() == 0

    # Avec confirmation : la valeur est ajoutée et signalée par un avertissement.
    r2 = importer_valeur(session, "boursorama", "x", confirmer=True)
    assert r2["confirmation_requise"] is False and r2["avertissement"]
    assert session.query(Actif).filter(Actif.isin == "FR0007052782").count() == 1


def test_suppression_actif(session):
    from peadvisor.routers.actifs import supprimer_actif

    importer(session, "seed")
    isin = "FR0000120271"  # TotalEnergies
    assert session.query(Actif).filter(Actif.isin == isin).count() == 1
    r = supprimer_actif(isin, session=session)
    assert r["supprime"] == isin
    assert session.query(Actif).filter(Actif.isin == isin).count() == 0
