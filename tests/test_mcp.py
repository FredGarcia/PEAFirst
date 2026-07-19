"""Tests du serveur MCP : outils appelés directement sur une base de test."""

import mcp_server
from peadvisor.services.importer import importer


def test_les_outils_sont_enregistres():
    import anyio

    async def lister():
        return await mcp_server.mcp.list_tools()

    outils = {t.name for t in anyio.run(lister)}
    attendus = {"lister_actifs", "fiche_actif", "synthese_dashboard",
                "classement_multicritere", "proposer_allocation",
                "consulter_watchlist", "gerer_watchlist", "lancer_mise_a_jour",
                "journal_traitements", "rapport_systeme", "lister_anomalies",
                "ponderations_score", "optimiser_ponderations"}
    assert attendus <= outils


def test_outils_consultation(session):
    importer(session, "seed")

    actifs = mcp_server.lister_actifs(type="ETF", limite=5)
    assert actifs and all(a["type"] == "ETF" for a in actifs)

    fiche = mcp_server.fiche_actif(actifs[0]["isin"])
    assert fiche["sous_scores"] is not None

    classement = mcp_server.classement_multicritere("topsis", limite=5)
    assert len(classement) == 5 and classement[0]["rang"] == 1

    synthese = mcp_server.synthese_dashboard()
    assert synthese["nb_actifs"] > 0


def test_outils_action(session):
    importer(session, "seed")
    isin = mcp_server.lister_actifs(limite=1)[0]["isin"]

    assert "ajouté" in mcp_server.gerer_watchlist("ajouter", isin)["resultat"]
    assert len(mcp_server.consulter_watchlist()) == 1
    assert "retiré" in mcp_server.gerer_watchlist("retirer", isin)["resultat"]

    allocation = mcp_server.proposer_allocation(10000, 4, 10, "equilibre")
    assert allocation["lignes"] and abs(sum(l["poids"] for l in allocation["lignes"]) - 1) < 0.01

    rapport = mcp_server.rapport_systeme(lancer_nouveau=True)
    assert "recommandations" in rapport
    assert isinstance(mcp_server.lister_anomalies("toutes"), list)
    assert "ponderations" in mcp_server.ponderations_score()
