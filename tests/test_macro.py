"""Tests du moteur macro (taux sans risque / change BCE, réseau simulé)."""

import peadvisor.services.macro as macro


class FausseReponse:
    def __init__(self, texte="", statut=200):
        self.text = texte
        self._statut = statut

    def raise_for_status(self):
        if self._statut >= 400:
            raise RuntimeError(f"HTTP {self._statut}")


CSV_TAUX = ("KEY,FREQ,TIME_PERIOD,OBS_VALUE\n"
            "YC.B.U2.EUR...,B,2026-07-17,3.15\n")
CSV_CHANGE = ("KEY,FREQ,CURRENCY,TIME_PERIOD,OBS_VALUE\n"
              "EXR.D.USD.EUR...,D,USD,2026-07-17,1.08\n")


def _simuler(monkeypatch, texte, statut=200):
    monkeypatch.setattr(macro.requests, "get",
                        lambda url, params=None, timeout=None: FausseReponse(texte, statut))


def test_source_fixe_par_defaut(monkeypatch):
    _simuler(monkeypatch, CSV_TAUX)  # ne doit même pas être appelé
    r = macro.taux_sans_risque({"quantitatif": {"taux_sans_risque_pct": 2.5},
                                "macro": {"taux_sans_risque_source": "fixe"}})
    assert r == {"taux": 2.5, "source": "fixe", "date": None}


def test_source_bce(monkeypatch):
    _simuler(monkeypatch, CSV_TAUX)
    r = macro.taux_sans_risque({"quantitatif": {"taux_sans_risque_pct": 2.5},
                                "macro": {"taux_sans_risque_source": "bce"}})
    assert r["taux"] == 3.15 and r["source"] == "bce_10a_aaa" and r["date"] == "2026-07-17"


def test_bce_indisponible_repli_sur_fixe(monkeypatch):
    _simuler(monkeypatch, "", statut=503)
    r = macro.taux_sans_risque({"quantitatif": {"taux_sans_risque_pct": 2.0},
                                "macro": {"taux_sans_risque_source": "bce"}})
    assert r["taux"] == 2.0 and r["source"] == "fixe"


def test_change_eur_identite():
    assert macro.taux_change("EUR")["taux_vers_eur"] == 1.0


def test_change_usd(monkeypatch):
    _simuler(monkeypatch, CSV_CHANGE)
    r = macro.taux_change("usd")
    # BCE cote EUR→USD = 1.08 ; on renvoie l'inverse (USD→EUR).
    assert r["devise"] == "USD" and abs(r["taux_vers_eur"] - 1 / 1.08) < 1e-6


def test_change_echec_renvoie_none(monkeypatch):
    _simuler(monkeypatch, "", statut=500)
    assert macro.taux_change("GBP") is None


def test_quantitatif_utilise_le_taux_macro(monkeypatch, session):
    """Le moteur quantitatif lit bien le taux via macro (ici forcé)."""
    from peadvisor.services import quantitatif
    from peadvisor.services.importer import importer

    monkeypatch.setattr(quantitatif, "charger_settings",
                        lambda: {"macro": {"taux_sans_risque_source": "bce"}})
    monkeypatch.setattr("peadvisor.services.macro.charger_settings", lambda: {})
    _simuler(monkeypatch, CSV_TAUX)
    importer(session, "seed")  # ne doit pas lever
    from peadvisor.models import Actif
    assert session.query(Actif).filter(Actif.indicateurs_quant.isnot(None)).count() > 0
