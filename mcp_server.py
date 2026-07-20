"""Serveur MCP de PEAdvisor — pilotage par un agent (option B du Moteur IA).

Expose les fonctions de PEAdvisor comme outils MCP (Model Context Protocol),
utilisables depuis Claude Desktop ou claude.ai : consultation des actifs,
tableau de bord, classement multicritère, allocation, watchlist, mises à
jour, auto-diagnostic et optimisation des pondérations.

Principe d'architecture : les moteurs déterministes de PEAdvisor restent les
seuls responsables des calculs (scores, TOPSIS, allocations) ; l'agent
consomme leurs résultats pour les expliquer, les comparer et les synthétiser.

Accès direct à la base SQLite via les services applicatifs : il n'est pas
nécessaire que le serveur web (run.py) tourne. Au premier lancement, la base
est créée et alimentée depuis la source active si elle est vide.

Lancement (fait par Claude Desktop, cf. docs/08-agent-mcp.md) :
    python mcp_server.py
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager

from mcp.server.fastmcp import FastMCP

import peadvisor.database as database
from peadvisor.models import Actif, Anomalie, ElementWatchlist, JournalMaj, TypeActif
from peadvisor.schemas import DemandeAllocation

# Important : ne jamais écrire sur stdout (canal du protocole MCP) — les
# journaux partent sur stderr.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

mcp = FastMCP(
    "peadvisor",
    instructions=(
        "Outils d'aide à la décision PEA (actions, ETF, OPCVM éligibles). "
        "Les scores, classements et allocations sont calculés par les moteurs "
        "déterministes de PEAdvisor : utilise ces outils pour consulter, "
        "expliquer et comparer leurs résultats, jamais pour recalculer "
        "toi-même un score. Toute recommandation est indicative et ne "
        "constitue pas un conseil en investissement — le rappeler quand c'est "
        "pertinent."
    ),
)


@contextmanager
def _session():
    s = database.SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _actif_vers_dict(a: Actif, complet: bool = False) -> dict:
    base = {
        "nom": a.nom,
        "isin": a.isin,
        "type": a.type.value if hasattr(a.type, "value") else str(a.type),
        "secteur": a.secteur,
        "cours": a.cours,
        "rendement_pct": a.rendement,
        "per": a.per,
        "potentiel_pct": a.potentiel,
        "score_esg": a.score_esg,
        "niveau_risque_1_7": a.niveau_risque,
        "score_global": a.score_global,
    }
    if complet:
        base.update({
            "mnemonique": a.mnemonique,
            "marche": a.marche,
            "devise": a.devise,
            "pays": a.pays,
            "eligible_pea": a.eligible_pea,
            "eligible_pea_pme": a.eligible_pea_pme,
            "societe_gestion": a.societe_gestion,
            "capitalisation_meur": a.capitalisation,
            "croissance_pct": a.croissance,
            "volatilite_pct": a.volatilite,
            "objectif_cours": a.objectif_cours,
            "consensus_1_5": a.consensus,
            "sous_scores": json.loads(a.sous_scores) if a.sous_scores else None,
            "indicateurs_quantitatifs": json.loads(a.indicateurs_quant) if a.indicateurs_quant else None,
            "source": a.source,
            "maj_le": a.maj_le.isoformat() if a.maj_le else None,
        })
    return base


# --------------------------------------------------------------------------
# Consultation des actifs
# --------------------------------------------------------------------------

@mcp.tool()
def lister_actifs(type: str | None = None, limite: int = 50) -> list[dict]:
    """Liste les actifs éligibles PEA, triés par score global décroissant.

    Args:
        type: Filtre optionnel : "ACTION", "ETF" ou "OPCVM". Omis = tous.
        limite: Nombre maximal d'actifs renvoyés (défaut 50).
    """
    with _session() as s:
        requete = s.query(Actif)
        if type:
            requete = requete.filter(Actif.type == TypeActif[type.upper()])
        actifs = requete.order_by(Actif.score_global.desc().nulls_last()).limit(limite).all()
        return [_actif_vers_dict(a) for a in actifs]


@mcp.tool()
def fiche_actif(isin: str) -> dict:
    """Fiche complète d'un actif : indicateurs, sous-scores 0-100 du score
    propriétaire (potentiel, valorisation, croissance, ESG, dividende,
    volatilité, consensus) et traçabilité.

    Args:
        isin: Code ISIN de l'actif (12 caractères).
    """
    with _session() as s:
        actif = s.query(Actif).filter(Actif.isin == isin.upper()).one_or_none()
        if actif is None:
            return {"erreur": f"Aucun actif avec l'ISIN {isin}"}
        return _actif_vers_dict(actif, complet=True)


@mcp.tool()
def synthese_dashboard() -> dict:
    """Synthèse du tableau de bord : KPI (scores moyens, rendement, risque),
    répartitions par type/secteur/pays et tops (opportunités, dividendes,
    croissance)."""
    from peadvisor.routers.dashboard import synthese

    with _session() as s:
        return synthese(session=s)


@mcp.tool()
def classement_multicritere(methode: str = "topsis", limite: int = 15) -> list[dict]:
    """Matrice de décision multicritère : classement des actifs.

    Args:
        methode: "topsis" (proximité à la solution idéale, récompense les
            profils équilibrés) ou "weighted" (score pondéré global).
        limite: Nombre de lignes du classement (défaut 15).
    """
    from peadvisor.services.decision import classer

    with _session() as s:
        actifs = s.query(Actif).all()
        return [
            {"rang": i + 1, "nom": a.nom, "isin": a.isin, "type": a.type.value,
             "valeur": v, "score_global": a.score_global}
            for i, (a, v) in enumerate(classer(actifs, methode)[:limite])
        ]


@mcp.tool()
def correlations(isins: list[str] | None = None) -> dict:
    """Matrice de corrélation des rendements quotidiens entre actifs
    (moteur quantitatif, à partir des historiques de cours). Utile pour
    évaluer la diversification réelle d'une sélection ou d'une allocation.

    Args:
        isins: Liste de codes ISIN à comparer ; omise = top 10 par score.
    """
    from peadvisor.services.quantitatif import correlations as moteur

    with _session() as s:
        if not isins:
            tops = (s.query(Actif).order_by(Actif.score_global.desc().nulls_last())
                    .limit(10).all())
            isins = [a.isin for a in tops]
        return moteur(s, isins)


# --------------------------------------------------------------------------
# Allocation
# --------------------------------------------------------------------------

@mcp.tool()
def proposer_allocation(capital: float, niveau_risque: int, horizon_annees: int,
                        objectif: str = "equilibre") -> dict:
    """Propose une allocation de portefeuille PEA (moteur par règles :
    poches de risque, contraintes de diversification paramétrables).

    Args:
        capital: Capital à investir en euros (> 0).
        niveau_risque: Profil de risque de 1 (prudent) à 7 (offensif).
        horizon_annees: Horizon d'investissement en années (1 à 40).
        objectif: "croissance", "dividendes" ou "equilibre".
    """
    from peadvisor.services.allocation import proposer_allocation as moteur

    demande = DemandeAllocation(capital=capital, niveau_risque=niveau_risque,
                                horizon_annees=horizon_annees, objectif=objectif)
    with _session() as s:
        return moteur(s, demande).model_dump()


@mcp.tool()
def simuler_investissement(horizon_annees: int, capital_initial: float = 0,
                           versement_mensuel: float = 0, rendement_prix_pct: float = 5.0,
                           rendement_dividende_pct: float = 2.5,
                           reinvestir_dividendes: bool = True,
                           volatilite_pct: float | None = None) -> dict:
    """Projette un investissement PEA dans le temps : versement initial et
    versements programmés, réinvestissement des dividendes, trois scénarios
    (prudent / médian / optimiste) et fiscalité PEA estimée (exonération d'IR
    après 5 ans, prélèvements sociaux).

    Args:
        horizon_annees: Durée de projection (1 à 40).
        capital_initial: Versement initial en euros.
        versement_mensuel: Versement mensuel programmé en euros.
        rendement_prix_pct: Appréciation annuelle attendue du cours (%).
        rendement_dividende_pct: Rendement annuel du dividende (%).
        reinvestir_dividendes: Réinvestir les dividendes (capitalisation).
        volatilite_pct: Volatilité pour l'écart des scénarios (défaut config).
    """
    from peadvisor.schemas import DemandeSimulation
    from peadvisor.services.simulation import simuler

    demande = DemandeSimulation(
        capital_initial=capital_initial, versement_mensuel=versement_mensuel,
        horizon_annees=horizon_annees, rendement_prix_pct=rendement_prix_pct,
        rendement_dividende_pct=rendement_dividende_pct,
        reinvestir_dividendes=reinvestir_dividendes, volatilite_pct=volatilite_pct)
    reponse = simuler(demande).model_dump()
    # Allège la sortie : on retire les trajectoires détaillées (résumé par scénario).
    for s in reponse["scenarios"].values():
        s.pop("trajectoire", None)
    return reponse


# --------------------------------------------------------------------------
# Watchlist
# --------------------------------------------------------------------------

@mcp.tool()
def consulter_watchlist() -> list[dict]:
    """Liste les valeurs de la watchlist avec leurs indicateurs actuels."""
    with _session() as s:
        elements = s.query(ElementWatchlist).all()
        return [
            {"ajoute_le": e.ajoute_le.isoformat(), "commentaire": e.commentaire,
             **_actif_vers_dict(e.actif)}
            for e in elements
        ]


@mcp.tool()
def gerer_watchlist(action: str, isin: str, commentaire: str | None = None) -> dict:
    """Ajoute ou retire une valeur de la watchlist.

    Args:
        action: "ajouter" ou "retirer".
        isin: Code ISIN de l'actif.
        commentaire: Note optionnelle lors de l'ajout.
    """
    with _session() as s:
        actif = s.query(Actif).filter(Actif.isin == isin.upper()).one_or_none()
        if actif is None:
            return {"erreur": f"Aucun actif avec l'ISIN {isin}"}
        existant = s.query(ElementWatchlist).filter(
            ElementWatchlist.actif_id == actif.id).one_or_none()
        if action == "ajouter":
            if existant:
                return {"resultat": f"{actif.nom} est déjà dans la watchlist"}
            s.add(ElementWatchlist(actif_id=actif.id, commentaire=commentaire))
            s.commit()
            return {"resultat": f"{actif.nom} ajouté à la watchlist"}
        if action == "retirer":
            if not existant:
                return {"erreur": f"{actif.nom} n'est pas dans la watchlist"}
            s.delete(existant)
            s.commit()
            return {"resultat": f"{actif.nom} retiré de la watchlist"}
        return {"erreur": "Action attendue : ajouter ou retirer"}


# --------------------------------------------------------------------------
# Mises à jour et journal (L1 / M12)
# --------------------------------------------------------------------------

@mcp.tool()
def lancer_mise_a_jour(source: str | None = None) -> dict:
    """Lance un import des données depuis la source active (ou celle
    indiquée : "seed" ou "yahoo"), avec dédoublonnage par ISIN, recalcul des
    scores et journalisation.

    Args:
        source: Source à utiliser ; omis = source active de settings.yaml.
    """
    from peadvisor.services.importer import importer

    with _session() as s:
        journal = importer(s, source)
        return {"statut": journal.statut, "detail": journal.detail}


@mcp.tool()
def importer_boursorama(code: str) -> dict:
    """Scrape une valeur sur Boursorama (par son code, ex. 1rPAI = Air Liquide)
    et l'ajoute ou la met à jour dans le référentiel, avec recalcul des scores.
    La source de la ligne devient « boursorama ».

    Args:
        code: Code Boursorama de la valeur (préfixe de place + mnémonique).
    """
    from datetime import datetime

    from peadvisor.models import Actif, TypeActif
    from peadvisor.services.scoring import scorer_tous
    from peadvisor.sources.boursorama import recuperer_un

    with _session() as s:
        try:
            donnees = recuperer_un(code)
        except Exception as exc:
            return {"erreur": f"Scraping échoué : {exc}"}
        isin = donnees.get("isin")
        if not isin:
            return {"erreur": "ISIN introuvable sur la page"}
        champs = {c: donnees[c] for c in ("nom", "cours", "devise", "variation_pct",
                  "volume", "capitalisation", "per", "rendement", "eligible_pea",
                  "source") if c in donnees}
        actif = s.query(Actif).filter(Actif.isin == isin).one_or_none()
        cree = actif is None
        if cree:
            actif = Actif(isin=isin, type=TypeActif.ACTION, nom=donnees.get("nom") or code)
            s.add(actif)
        for champ, valeur in champs.items():
            setattr(actif, champ, valeur)
        actif.date_cours = datetime.utcnow()
        s.commit()
        scorer_tous(s)
        return {"cree": cree, "isin": isin, "nom": actif.nom, "cours": actif.cours,
                "source": actif.source}


@mcp.tool()
def journal_traitements(limite: int = 20) -> list[dict]:
    """Journal des traitements (imports, scoring, auto-diagnostics,
    optimisations), du plus récent au plus ancien.

    Args:
        limite: Nombre d'entrées renvoyées (défaut 20).
    """
    with _session() as s:
        lignes = s.query(JournalMaj).order_by(JournalMaj.date.desc()).limit(limite).all()
        return [
            {"date": j.date.isoformat(), "traitement": j.traitement, "statut": j.statut,
             "detail": j.detail, "crees": j.nb_crees, "maj": j.nb_maj,
             "doublons": j.nb_doublons, "rejets": j.nb_erreurs}
            for j in lignes
        ]


# --------------------------------------------------------------------------
# Couche de second ordre (auto-observation / auto-amélioration)
# --------------------------------------------------------------------------

@mcp.tool()
def rapport_systeme(lancer_nouveau: bool = False) -> dict:
    """Rapport d'auto-diagnostic du système : complétude des données,
    fraîcheur, discrimination des critères, anomalies, pouvoir prédictif du
    score et recommandations d'amélioration.

    Args:
        lancer_nouveau: True pour exécuter un nouveau diagnostic ; False
            (défaut) pour renvoyer le dernier rapport enregistré.
    """
    from peadvisor.services.introspection import dernier_rapport, observer

    with _session() as s:
        if lancer_nouveau:
            return observer(s)
        rapport = dernier_rapport(s)
        return rapport or {"info": "Aucun diagnostic encore : relancer avec lancer_nouveau=true."}


@mcp.tool()
def lister_anomalies(statut: str = "ouverte") -> list[dict]:
    """Anomalies détectées par l'auto-observation (données incohérentes,
    valeurs atypiques, dérives de score).

    Args:
        statut: "ouverte" (défaut), "ignoree", "resolue" ou "toutes".
    """
    with _session() as s:
        requete = s.query(Anomalie)
        if statut != "toutes":
            requete = requete.filter(Anomalie.statut == statut)
        return [
            {"id": a.id, "date": a.date.isoformat(), "type": a.type,
             "gravite": a.gravite, "message": a.message, "statut": a.statut}
            for a in requete.order_by(Anomalie.date.desc()).limit(100).all()
        ]


@mcp.tool()
def taux_sans_risque() -> dict:
    """Taux sans risque annuel (%) utilisé pour Sharpe/Sortino, et son origine
    (valeur fixe paramétrée ou rendement 10 ans zone euro récupéré à la BCE)."""
    from peadvisor.services.macro import taux_sans_risque as calcul

    return calcul()


@mcp.tool()
def resoudre_isin(isin: str, code_place: str = "GR") -> dict:
    """Résout un ISIN en ticker et place de cotation via OpenFIGI (annuaire
    d'instruments, pas une source de cours). Utile pour trouver le bon symbole
    d'une valeur avant de l'ajouter au référentiel.

    Args:
        isin: Code ISIN (12 caractères).
        code_place: Code place OpenFIGI (défaut "GR" = Euronext Paris).
    """
    from peadvisor.services.reference import resoudre_isin as resoudre

    return resoudre(isin, code_place)


@mcp.tool()
def ponderations_score() -> dict:
    """Pondérations et bornes de normalisation actuelles du score
    propriétaire (config/scoring.yaml)."""
    from peadvisor.config import charger_scoring

    return charger_scoring()


@mcp.tool()
def optimiser_ponderations() -> dict:
    """Recherche des pondérations plus prédictives (corrélation entre scores
    passés et rendements réalisés, montée de coordonnées bornée). Crée une
    suggestion à valider dans l'écran Système — n'applique rien
    automatiquement."""
    from peadvisor.services.amelioration import proposer_ponderations

    with _session() as s:
        resultat = proposer_ponderations(s)
        suggestion = resultat.get("suggestion")
        reponse = {"detail": resultat.get("detail")}
        if suggestion is not None:
            reponse["suggestion"] = {
                "id": suggestion.id,
                "ponderations": json.loads(suggestion.ponderations),
                "correlation_avant": suggestion.correlation_avant,
                "correlation_apres": suggestion.correlation_apres,
                "a_valider_dans": "écran Système de PEAdvisor",
            }
        return reponse


# --------------------------------------------------------------------------
# Démarrage
# --------------------------------------------------------------------------

def initialiser() -> None:
    """Crée les tables et alimente la base si elle est vide."""
    from peadvisor.services.importer import importer

    database.creer_tables()
    with _session() as s:
        if s.query(Actif).count() == 0:
            journal = importer(s)
            logging.getLogger("peadvisor.mcp").info("Base initialisée : %s", journal.detail)


if __name__ == "__main__":
    initialiser()
    mcp.run()  # transport stdio, pour Claude Desktop
