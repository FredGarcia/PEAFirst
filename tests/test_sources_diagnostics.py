"""Tests des diagnostics et des corrections de connecteurs (réseau simulé)."""

import requests

import peadvisor.services.reference as reference
import peadvisor.sources.http as http
import peadvisor.sources.stooq as stooq_module
from peadvisor.sources.financialmodelingprep import SourceFinancialModelingPrep
from peadvisor.sources.stooq import SourceStooq


class FausseReponse:
    def __init__(self, json_data=None, texte="", statut=200):
        self._json = json_data
        self.text = texte
        self.status_code = statut

    def raise_for_status(self):
        if self.status_code >= 400:
            exc = requests.HTTPError(f"{self.status_code} Error")
            exc.response = self
            raise exc

    def json(self):
        if self._json is None:
            raise ValueError("pas de JSON")
        return self._json


def test_message_reponse_extrait_le_corps():
    # TwelveData / FMP renvoient la vraie raison dans le corps JSON.
    r = FausseReponse({"message": "symbol not found on your plan"}, statut=404)
    assert "not found" in http.SourceHTTPBase._message_reponse(r)
    r2 = FausseReponse({"Error Message": "Payment Required"}, statut=402)
    assert "Payment" in http.SourceHTTPBase._message_reponse(r2)


def test_tester_expose_le_message_api(monkeypatch):
    src = SourceFinancialModelingPrep()
    monkeypatch.setattr("peadvisor.config.charger_cles", lambda: {"financialmodelingprep": "k"})

    def faux_get(url, params=None, timeout=None, headers=None):
        return FausseReponse({"Error Message": "Exclusive Endpoint: upgrade your plan"},
                             statut=402)
    monkeypatch.setattr(http.requests, "get", faux_get)

    r = src.tester()
    assert not r["ok"]
    assert "HTTP 402" in r["erreur"] and "plan payant" in r["erreur"]
    assert "upgrade your plan" in r["erreur"]


def test_fmp_utilise_v3(monkeypatch):
    src = SourceFinancialModelingPrep()
    appels = []

    def faux_get(url, params=None, timeout=None, headers=None):
        appels.append(url)
        if "/quote/" in url:
            return FausseReponse([{"price": 70.5, "pe": 8.9}])
        return FausseReponse({"historical": [{"date": "2026-07-17", "close": 70.5}]})
    monkeypatch.setattr(http.requests, "get", faux_get)

    assert src.cotation("TTE.PA", "k")["cours"] == 70.5
    assert src.serie("TTE.PA", "k")[0]["cours"] == 70.5
    assert all("/api/v3/" in u for u in appels)  # plus de /stable/ (payant)


def test_stooq_entete_navigateur_et_no_data(monkeypatch):
    src = SourceStooq()
    entetes_vus = {}

    def faux_get(url, params=None, timeout=None, headers=None):
        entetes_vus.update(headers or {})
        # Symbole inconnu : stooq répond 200 « No data ».
        return FausseReponse(texte="No data")
    monkeypatch.setattr(stooq_module.requests, "get", faux_get)

    assert src.serie("inconnu.fr") == []
    assert "User-Agent" in entetes_vus and "Mozilla" in entetes_vus["User-Agent"]


def test_stooq_parse_csv(monkeypatch):
    src = SourceStooq()
    csv_texte = "Date,Open,High,Low,Close,Volume\n2026-07-16,61.9,62.3,61.5,62.1,100\n"
    monkeypatch.setattr(stooq_module.requests, "get",
                        lambda *a, **k: FausseReponse(texte=csv_texte))
    assert src.serie("tte.fr")[0]["cours"] == 62.1


def test_openfigi_resolution(monkeypatch):
    def faux_post(url, json=None, headers=None, timeout=None):
        return FausseReponse([{"data": [{"ticker": "TTE", "exchCode": "GR",
                                         "securityType": "Common Stock",
                                         "name": "TOTALENERGIES"}]}])
    monkeypatch.setattr(reference.requests, "post", faux_post)
    r = reference.resoudre_isin("FR0000120271")
    assert r["ticker"] == "TTE" and r["place"] == "GR"


def test_openfigi_sans_correspondance(monkeypatch):
    def faux_post(url, json=None, headers=None, timeout=None):
        return FausseReponse([{"warning": "No identifier found."}])
    monkeypatch.setattr(reference.requests, "post", faux_post)
    r = reference.resoudre_isin("XX0000000000")
    assert "erreur" in r and "No identifier" in r["erreur"]
