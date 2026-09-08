"""Tests du routeur d'exécution des scripts.

L'enjeu est la sécurité : cette route lance des processus. Elle ne doit accepter
que les scripts et les paramètres du catalogue, et refuser tout le reste — en
particulier ce qui ressemble à une tentative d'injection.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from peadvisor.main import app
from peadvisor.routers.scripts import CATALOGUE, VARIABLES

client = TestClient(app)
ENTETE = {"X-PEAdvisor": "1"}


def test_entete_requis_sur_le_catalogue():
    """Sans l'en-tête, un site tiers pourrait appeler l'API locale."""
    assert client.get("/api/scripts").status_code == 403


def test_entete_requis_sur_l_execution():
    reponse = client.post("/api/scripts/validate_base/executer",
                          json={"parametres": {}})
    assert reponse.status_code == 403


def test_catalogue_liste_les_scripts():
    reponse = client.get("/api/scripts", headers=ENTETE)
    assert reponse.status_code == 200
    donnees = reponse.json()
    assert {x["id"] for x in donnees} == set(CATALOGUE)
    for x in donnees:
        assert x["titre"] and x["script"].endswith(".py")


def test_script_hors_catalogue_refuse():
    reponse = client.post("/api/scripts/inconnu/executer",
                          json={"parametres": {}}, headers=ENTETE)
    assert reponse.status_code == 404


def test_parametre_inconnu_refuse():
    reponse = client.post("/api/scripts/scoring/executer",
                          json={"parametres": {"pirate": "x"}}, headers=ENTETE)
    assert reponse.status_code == 400
    assert "inconnu" in reponse.json()["detail"].lower()


def test_choix_hors_liste_refuse():
    reponse = client.post("/api/scripts/enrich_marche/executer",
                          json={"parametres": {"filtre": "../../etc"}},
                          headers=ENTETE)
    assert reponse.status_code == 400


def test_entier_invalide_refuse():
    reponse = client.post("/api/scripts/scoring/executer",
                          json={"parametres": {"top": "abc"}}, headers=ENTETE)
    assert reponse.status_code == 400


def test_injection_dans_un_champ_texte_refusee():
    """Le seul champ libre n'accepte que des ISIN : ni espace, ni séparateur."""
    for tentative in ("FR000; rm -rf /", "FR000 && curl x", "$(whoami)",
                      "`id`", "FR000|cat /etc/passwd", "../../secret"):
        reponse = client.post("/api/scripts/enrich_marche/executer",
                              json={"parametres": {"isins": tentative}},
                              headers=ENTETE)
        assert reponse.status_code == 400, tentative


def test_champ_texte_trop_long_refuse():
    reponse = client.post("/api/scripts/enrich_marche/executer",
                          json={"parametres": {"isins": "A" * 3000}},
                          headers=ENTETE)
    assert reponse.status_code == 400


def test_execution_reelle_sans_reseau():
    """validate_base n'appelle aucune source : sûr à exécuter en test."""
    reponse = client.post("/api/scripts/validate_base/executer",
                          json={"parametres": {}}, headers=ENTETE)
    assert reponse.status_code == 200
    resultat = reponse.json()
    assert resultat["succes"] is True
    assert resultat["code"] == 0
    assert "OK" in resultat["sortie"]
    # La commande affichée doit refléter ce qui a réellement tourné.
    assert resultat["commande"].startswith("python scripts/validate_base.py")


def test_catalogue_coherent_avec_les_scripts_reels():
    """Un script du catalogue doit exister, et ses clés être connues."""
    from peadvisor.routers.scripts import RACINE

    for identifiant, definition in CATALOGUE.items():
        chemin = RACINE / "scripts" / definition["script"]
        assert chemin.exists(), f"{identifiant} : {definition['script']} absent"
        if definition["cle"]:
            assert definition["cle"] in VARIABLES, identifiant
        for parametre in definition["parametres"]:
            assert parametre["type"] in ("bool", "entier", "choix", "texte")
            if parametre["type"] == "choix":
                assert parametre["choix"], parametre["nom"]
