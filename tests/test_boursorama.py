"""Tests du scraper Boursorama : analyse de page (pure) et import unitaire."""

import peadvisor.sources.boursorama as bourso
from peadvisor.sources.boursorama import (SourceBoursorama, _capitalisation_meur,
                                          _nombre, parser_page)

# Fragment représentatif d'une page « cours » Boursorama (structure réelle).
PAGE = """
<html><head><title>AIR LIQUIDE Cours Action AI</title></head><body>
  <h2 class="c-faceplate__company-title">Air Liquide</h2>
  <div class="c-faceplate__isin">FR0000120073 - Euronext Paris</div>
  <span class="c-instrument c-instrument--last" data-ist-last="184.52">184,52</span>
  <span class="c-instrument c-instrument--variation">+1,23%</span>
  <ul class="c-list-info">
    <li><p class="c-list-info__heading">Ouverture</p><p class="c-list-info__value">183,20 EUR</p></li>
    <li><p class="c-list-info__heading">+ Haut</p><p class="c-list-info__value">185,00</p></li>
    <li><p class="c-list-info__heading">+ Bas</p><p class="c-list-info__value">182,90</p></li>
    <li><p class="c-list-info__heading">Clôture veille</p><p class="c-list-info__value">182,28</p></li>
    <li><p class="c-list-info__heading">Volume</p><p class="c-list-info__value">1 234 567</p></li>
    <li><p class="c-list-info__heading">Capitalisation</p><p class="c-list-info__value">108,4 Md€</p></li>
    <li><p class="c-list-info__heading">PER</p><p class="c-list-info__value">27,1</p></li>
    <li><p class="c-list-info__heading">Rendement 2024</p><p class="c-list-info__value">1,80%</p></li>
    <li><p class="c-list-info__heading">Éligibilité PEA</p><p class="c-list-info__value">Oui</p></li>
  </ul>
</body></html>
"""


def test_nombre_format_francais():
    assert _nombre("1 234,56 EUR") == 1234.56
    assert _nombre("184,52") == 184.52
    assert _nombre("-0,50%") == -0.50
    assert _nombre("N/D") is None


def test_capitalisation_milliards():
    assert _capitalisation_meur("108,4 Md€") == 108400.0
    assert _capitalisation_meur("980 M€") == 980.0


def test_parser_page_complet():
    d = parser_page(PAGE)
    assert d["source"] == "boursorama"
    assert d["nom"] == "Air Liquide"
    assert d["isin"] == "FR0000120073"
    assert d["cours"] == 184.52
    assert d["variation_pct"] == 1.23
    assert d["devise"] == "EUR"
    assert d["ouverture"] == 183.20
    assert d["plus_haut"] == 185.00
    assert d["cloture_veille"] == 182.28
    assert d["volume"] == 1234567
    assert d["capitalisation"] == 108400.0
    assert d["per"] == 27.1
    assert d["rendement"] == 1.80
    assert d["eligible_pea"] is True


def test_parser_page_vide():
    d = parser_page("<html><body>rien</body></html>")
    assert d == {"source": "boursorama"}  # aucune donnée, pas d'exception


def test_symbole_code_boursorama():
    src = SourceBoursorama()
    assert src.symbole("AI") == "1rPAI"
    assert src.symbole("TTE") == "1rPTTE"
    assert not src.necessite_cle


def test_cotation_ne_garde_que_les_champs_utiles(monkeypatch):
    monkeypatch.setattr(bourso, "recuperer_un", lambda code: parser_page(PAGE))
    champs = SourceBoursorama().cotation("1rPAI")
    # Les champs de marché intermédiaires (ouverture, +haut…) ne polluent pas la fiche.
    assert "ouverture" not in champs and "plus_haut" not in champs
    assert champs["cours"] == 184.52 and champs["source"] == "boursorama"
    assert champs["capitalisation"] == 108400.0


def test_import_boursorama_met_a_jour(monkeypatch, session):
    """L'import d'Air Liquide (déjà en base via seed) met à jour la ligne + source."""
    from peadvisor.routers.administration import importer_boursorama
    from peadvisor.services.importer import importer

    importer(session, "seed")  # Air Liquide FR0000120073 présent, source=seed
    monkeypatch.setattr("peadvisor.sources.boursorama.recuperer_un",
                        lambda code: parser_page(PAGE))

    r = importer_boursorama("1rPAI", session=session)
    assert r["cree"] is False
    assert r["isin"] == "FR0000120073"
    assert r["source"] == "boursorama"

    from peadvisor.models import Actif
    al = session.query(Actif).filter(Actif.isin == "FR0000120073").one()
    assert al.cours == 184.52 and al.source == "boursorama"
    assert al.variation_pct == 1.23 and al.volume == 1234567
    assert al.score_global is not None  # rescoré


def test_import_boursorama_cree_nouvelle_valeur(monkeypatch, session):
    page = PAGE.replace("FR0000120073", "NL0000000001").replace("Air Liquide", "Nouvelle Valeur")
    monkeypatch.setattr("peadvisor.sources.boursorama.recuperer_un",
                        lambda code: parser_page(page))
    from peadvisor.routers.administration import importer_boursorama

    r = importer_boursorama("1rPXX", session=session)
    assert r["cree"] is True and r["isin"] == "NL0000000001"
