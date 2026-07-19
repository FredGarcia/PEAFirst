"""Tests des connecteurs HTTP : réseau simulé, parsing vérifié par source."""

import pytest

import peadvisor.config as config
import peadvisor.sources.http as http
import peadvisor.sources.stooq as stooq_module
from peadvisor.sources import REGISTRE
from peadvisor.sources.alphavantage import SourceAlphaVantage
from peadvisor.sources.eodhd import SourceEODHD
from peadvisor.sources.financialmodelingprep import SourceFinancialModelingPrep
from peadvisor.sources.http import univers_de_base
from peadvisor.sources.marketstack import SourceMarketstack
from peadvisor.sources.stooq import SourceStooq
from peadvisor.sources.twelvedata import SourceTwelveData


class FausseReponse:
    def __init__(self, json_data=None, texte=""):
        self._json = json_data
        self.text = texte

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


def _simuler(monkeypatch, reponses):
    """Remplace requests.get : `reponses` associe un fragment d'URL à un payload."""
    def faux_get(url, params=None, timeout=None):
        for fragment, payload in reponses.items():
            if fragment in url:
                return payload
        raise AssertionError(f"URL inattendue : {url}")
    monkeypatch.setattr(http.requests, "get", faux_get)
    monkeypatch.setattr(stooq_module.requests, "get", faux_get)


def test_toutes_les_sources_sont_enregistrees():
    assert {"seed", "stooq", "yahoo", "alphavantage", "twelvedata",
            "financialmodelingprep", "eodhd", "marketstack"} <= set(REGISTRE)


def test_univers_de_base_sans_historique_synthetique():
    univers = univers_de_base()
    assert univers and all("historique" not in a for a in univers)


def test_cle_env_prime_sur_fichier(monkeypatch):
    monkeypatch.setattr(config, "charger_cles", lambda: {"eodhd": "cle-fichier"})
    monkeypatch.delenv("EODHD_API_TOKEN", raising=False)
    assert config.cle_api("eodhd", "EODHD_API_TOKEN") == "cle-fichier"
    monkeypatch.setenv("EODHD_API_TOKEN", "cle-env")
    assert config.cle_api("eodhd", "EODHD_API_TOKEN") == "cle-env"


def test_cle_absente_bloque_l_import(monkeypatch):
    monkeypatch.setattr(config, "charger_cles", lambda: {})
    monkeypatch.delenv("EODHD_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="clé API"):
        SourceEODHD().recuperer()
    # Et le testeur renvoie une erreur explicite au lieu de lever.
    resultat = SourceEODHD().tester()
    assert not resultat["ok"] and "Clé absente" in resultat["erreur"]


def test_alphavantage_parse_et_suffixe(monkeypatch):
    src = SourceAlphaVantage()
    assert src.symbole("TTE") == "TTE.PAR"
    _simuler(monkeypatch, {"alphavantage.co": FausseReponse({
        "Global Quote": {"05. price": "62.50"},
        "Time Series (Daily)": {
            "2026-07-17": {"4. close": "62.50"},
            "2026-07-16": {"4. close": "62.10"},
        },
    })})
    assert src.cotation("TTE.PAR", "k") == {"cours": 62.5}
    serie = src.serie("TTE.PAR", "k")
    assert serie[0]["date"] == "2026-07-16" and serie[-1]["cours"] == 62.5


def test_twelvedata_parse(monkeypatch):
    src = SourceTwelveData()
    assert src.symbole("TTE") == "TTE"
    _simuler(monkeypatch, {
        "/quote": FausseReponse({"close": "62.5"}),
        "/time_series": FausseReponse({"values": [
            {"datetime": "2026-07-17", "close": "62.5"},
            {"datetime": "2026-07-16", "close": "62.1"},
        ]}),
    })
    assert src.cotation("TTE", "k") == {"cours": 62.5}
    assert [p["date"] for p in src.serie("TTE", "k")] == ["2026-07-16", "2026-07-17"]


def test_fmp_parse(monkeypatch):
    src = SourceFinancialModelingPrep()
    _simuler(monkeypatch, {
        "/quote": FausseReponse([{"price": 62.5, "marketCap": 148e9, "pe": 8.9,
                                  "dividendYield": 5.1, "priceTarget": 71.0}]),
        "/historical-price-eod": FausseReponse([
            {"date": "2026-07-17", "price": 62.5},
            {"date": "2026-07-16", "close": 62.1},
        ]),
    })
    cotation = src.cotation("TTE.PA", "k")
    assert cotation["cours"] == 62.5 and cotation["capitalisation"] == 148000.0
    assert cotation["objectif_cours"] == 71.0
    assert len(src.serie("TTE.PA", "k")) == 2


def test_eodhd_parse(monkeypatch):
    src = SourceEODHD()
    _simuler(monkeypatch, {
        "/real-time/": FausseReponse({"close": 62.5, "pe_ratio": 8.9}),
        "/eod/": FausseReponse([
            {"date": "2026-07-16", "close": 62.1, "adjusted_close": 62.0},
            {"date": "2026-07-17", "close": 62.5},
        ]),
    })
    assert src.cotation("TTE.PA", "k") == {"cours": 62.5, "per": 8.9}
    serie = src.serie("TTE.PA", "k")
    assert serie[0]["cours"] == 62.0  # cours ajusté prioritaire


def test_marketstack_parse_et_suffixe(monkeypatch):
    src = SourceMarketstack()
    assert src.symbole("TTE") == "TTE.XPAR"
    _simuler(monkeypatch, {
        "/eod/latest": FausseReponse({"data": [{"date": "2026-07-17T00:00:00+0000",
                                                "close": 62.5}]}),
        "/eod": FausseReponse({"data": [
            {"date": "2026-07-17T00:00:00+0000", "close": 62.5},
            {"date": "2026-07-16T00:00:00+0000", "close": 62.1},
        ]}),
    })
    assert src.cotation("TTE.XPAR", "k") == {"cours": 62.5}
    assert src.serie("TTE.XPAR", "k")[0]["date"] == "2026-07-16"


def test_stooq_sans_cle_et_parse_csv(monkeypatch):
    src = SourceStooq()
    assert not src.necessite_cle
    assert src.symbole("TTE") == "tte.fr"
    csv_texte = "Date,Open,High,Low,Close,Volume\n2026-07-16,61.9,62.3,61.5,62.1,100\n2026-07-17,62.1,62.8,62.0,62.5,120\n"
    _simuler(monkeypatch, {"stooq.com": FausseReponse(texte=csv_texte)})
    serie = src.serie("tte.fr")
    assert len(serie) == 2 and serie[-1]["cours"] == 62.5
    assert src.cotation("tte.fr") == {"cours": 62.5}


def test_import_complet_via_source_http(monkeypatch, session):
    """Une source HTTP alimente fiches + historiques jusque dans la base."""
    from peadvisor.services.importer import importer

    monkeypatch.setenv("EODHD_API_TOKEN", "cle-test")
    _simuler(monkeypatch, {
        "/real-time/": FausseReponse({"close": 100.0}),
        "/eod/": FausseReponse([
            {"date": f"2026-{mois:02d}-{jour:02d}", "close": 100.0 + jour}
            for mois in range(1, 5) for jour in range(1, 29)
        ]),
    })
    src = SourceEODHD()
    src.pause_s = 0  # pas d'attente en test
    monkeypatch.setitem(REGISTRE, "eodhd", lambda: src)
    journal = importer(session, "eodhd")
    assert journal.statut == "succes"
    assert "112 point(s)" in journal.detail or "point(s) d'historique" in journal.detail

    from peadvisor.models import Actif
    tte = session.query(Actif).filter(Actif.isin == "FR0000120271").one()
    assert tte.cours == 100.0
    assert tte.source == "eodhd"
