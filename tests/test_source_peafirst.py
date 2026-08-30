"""Tests de la source peafirst : le référentiel local produit par scripts/."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from peadvisor.sources import REGISTRE
from peadvisor.sources.peafirst import SourcePEAFirst

RACINE = Path(__file__).resolve().parents[1]
BASE = RACINE / "data" / "base_isin.csv"

besoin_donnees = pytest.mark.skipif(
    not BASE.exists(),
    reason="référentiel data/ absent : lancer la chaîne scripts/",
)


def test_source_enregistree():
    assert REGISTRE["peafirst"] is SourcePEAFirst


@besoin_donnees
def test_recuperer_renvoie_des_actifs_exploitables():
    actifs = SourcePEAFirst().recuperer()
    assert actifs, "aucun actif : la collecte n'a produit aucun cours"
    for a in actifs:
        assert len(a["isin"]) == 12
        assert a["nom"]
        assert a["type"] in ("ACTION", "ETF", "OPCVM")
        # avec_donnees=True par défaut : un actif sans cours n'a rien à faire ici
        assert a["cours"] is not None


@besoin_donnees
def test_champs_sans_source_restent_vides():
    """Un champ sans source ne doit jamais être rempli d'une valeur inventée.

    C'est ce qui permet à PEAdvisor de renormaliser ses pondérations sur les
    seuls critères disponibles, au lieu de noter un actif sur des zéros.
    """
    actifs = SourcePEAFirst(limite=25).recuperer()
    for champ in ("rendement", "per", "croissance", "objectif_cours", "consensus"):
        assert all(a[champ] is None for a in actifs), champ


@besoin_donnees
def test_eligibilite_suit_les_fichiers_dedies():
    """Seul « OUI » vaut éligible : « PROBABLE » et « A_VERIFIER » ne suffisent pas."""
    actifs = {a["isin"]: a for a in SourcePEAFirst().recuperer()}
    for nom_fichier in ("base_isin_actions_pea.csv", "base_isin_fonds_pea.csv"):
        chemin = RACINE / "data" / nom_fichier
        if not chemin.exists():
            continue
        with open(chemin, encoding="utf-8") as f:
            for ligne in csv.DictReader(f, delimiter=";"):
                actif = actifs.get(ligne["ISIN"])
                if actif is None:
                    continue
                assert actif["eligible_pea"] is (ligne["PEA_eligible"] == "OUI")


@besoin_donnees
def test_foncieres_non_eligibles():
    """Les foncières à régime transparent ne doivent jamais ressortir éligibles.

    C'est l'erreur la plus coûteuse du domaine : loger un titre inéligible dans
    un PEA entraîne la clôture du plan.
    """
    chemin = RACINE / "data" / "base_isin_actions_pea.csv"
    if not chemin.exists():
        pytest.skip("éligibilité des actions non calculée")
    with open(chemin, encoding="utf-8") as f:
        foncieres = {r["ISIN"] for r in csv.DictReader(f, delimiter=";")
                     if r["PEA_methode"] in ("REGIME_FONCIER", "REGIME_DECLARE")}
    actifs = {a["isin"]: a for a in SourcePEAFirst().recuperer()}
    for isin in foncieres & set(actifs):
        assert actifs[isin]["eligible_pea"] is False, isin


@besoin_donnees
def test_limite_et_filtre():
    assert len(SourcePEAFirst(limite=5).recuperer()) <= 5
    # Sans filtre, la base entière remonte, y compris les instruments non collectés.
    assert len(SourcePEAFirst(avec_donnees=False).recuperer()) > \
        len(SourcePEAFirst(avec_donnees=True).recuperer())


def test_message_explicite_si_referentiel_absent(tmp_path, monkeypatch):
    """Une source qui échoue doit dire quoi faire, pas seulement qu'elle échoue."""
    monkeypatch.setattr("peadvisor.sources.peafirst.RACINE", tmp_path)
    with pytest.raises(FileNotFoundError, match="scripts/"):
        SourcePEAFirst().recuperer()
