"""Tests du framework multi-sources (registre, parseur générique, dispatch)."""

import pytest

import peadvisor.sources.web as web
from peadvisor.sources.web import SCRAPERS, Scraper, parser_generique


class FausseReponse:
    def __init__(self, texte="", statut=200):
        self.text = texte
        self.status_code = statut

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_registre_contient_les_sources_demandees():
    assert {"boursorama", "boursier", "zonebourse", "boursedirect",
            "ouestfrance", "euronext"} <= set(SCRAPERS)
    # Boursorama est la seule source validée pour l'instant.
    assert SCRAPERS["boursorama"].valide is True
    assert SCRAPERS["boursier"].valide is False


def test_parser_generique_extrait_nom_isin_cours():
    html = ('<title>Air Liquide - Cours de l\'action | Boursier</title>'
            'ISIN FR0000120073 '
            '<span itemprop="price" content="176.46">176,46 EUR</span>')
    d = parser_generique(html, "boursier")
    assert d["source"] == "boursier"
    assert d["isin"] == "FR0000120073"
    assert d["nom"] == "Air Liquide"
    assert d["cours"] == 176.46
    assert d["devise"] == "EUR"


def test_scraper_config_resout_et_parse(monkeypatch):
    # Recherche → lien de fiche → page → parseur générique.
    src = Scraper("demo", "Démo", recherche_url="https://x/recherche",
                  motif_lien=r'(/cours/[^"]+)', base="https://x")

    def faux_get(url, params=None, headers=None, timeout=None):
        if "recherche" in url:
            return FausseReponse('<a href="/cours/air-liquide">AL</a>')
        return FausseReponse('<title>Air Liquide</title> FR0000120073 '
                             'data-last="176.46"')
    monkeypatch.setattr(web.requests, "get", faux_get)

    d = src.recuperer("air liquide")
    assert d["isin"] == "FR0000120073" and d["cours"] == 176.46


def test_scraper_page_pauvre_leve_message_actionnable(monkeypatch):
    src = Scraper("demo", "Démo", cours_direct="https://x/{req}")

    monkeypatch.setattr(web.requests, "get",
                        lambda *a, **k: FausseReponse("<html>rien d'utile</html>"))
    with pytest.raises(ValueError, match="fiabiliser"):
        src.recuperer("FR0000120073")


def test_dispatch_boursorama_via_service(monkeypatch, session):
    from peadvisor.services.importer import importer
    from peadvisor.services.scraping import importer_valeur
    from tests.fixtures_boursorama import PAGE_REELLE

    importer(session, "seed")
    monkeypatch.setattr("peadvisor.sources.boursorama.recuperer_un",
                        lambda code: web.parser_page(PAGE_REELLE))
    monkeypatch.setattr("peadvisor.sources.boursorama.code_ou_recherche",
                        lambda q: "1rPAI")

    r = importer_valeur(session, "boursorama", "Air Liquide")
    assert r["source"] == "boursorama" and r["isin"] == "FR0000120073"
    assert r["donnees_extraites"]["risque_esg"] == 12.7


def test_dispatch_source_inconnue(session):
    from peadvisor.services.scraping import importer_valeur
    with pytest.raises(ValueError, match="inconnue"):
        importer_valeur(session, "inexistante", "x")
