"""Test du bouton « Tester » d'une source : récupère la page exemple (URL
paramétrable) et renvoie un extrait JSON, un extrait texte, ou la cause d'échec."""

import pytest

import peadvisor.routers.administration as administration

# Alias local pour éviter que pytest ne collecte la fonction importée (préfixe « test »).
appeler_test = administration.tester_source


class FausseReponse:
    def __init__(self, json_data=None, texte="", statut=200):
        self._json = json_data
        self.text = texte
        self.status_code = statut

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        if self._json is None:
            raise ValueError("pas de JSON")
        return self._json


@pytest.fixture()
def urls(monkeypatch):
    """Force un jeu d'URL exemple connu (indépendant du profil réel)."""
    monkeypatch.setattr(administration, "charger_profil",
                        lambda: {"urls_exemple": {"yahoo": "http://exemple/yahoo",
                                                  "boursorama": "http://exemple/bourso"}})


def test_tester_source_json(urls, monkeypatch):
    donnees = {"chart": {"result": [{"meta": {"symbol": "AI.PA", "currency": "EUR",
                                              "regularMarketPrice": 177.7}}]}}
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: FausseReponse(json_data=donnees))

    r = appeler_test("yahoo")
    assert r["ok"] is True
    assert r["exemple_json"]["symbol"] == "AI.PA"          # extrait des métadonnées
    assert r["exemple_json"]["regularMarketPrice"] == 177.7


def test_tester_source_texte(urls, monkeypatch):
    import requests
    monkeypatch.setattr(requests, "get",
                        lambda *a, **k: FausseReponse(texte="<html>page boursorama</html>"))

    r = appeler_test("boursorama")
    assert r["ok"] is True
    assert "exemple_json" not in r
    assert "page boursorama" in r["exemple_texte"]         # extrait texte (non-JSON)


def test_tester_source_echec_cause_texte(urls, monkeypatch):
    import requests

    def get_ko(*a, **k):
        raise ConnectionError("connexion refusée")
    monkeypatch.setattr(requests, "get", get_ko)

    r = appeler_test("yahoo")
    assert r["ok"] is False
    assert "connexion refusée" in r["erreur"]              # cause en texte
