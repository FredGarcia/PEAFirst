"""Endpoints de consultation des actifs (Actions, ETF, OPCVM)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from peadvisor.database import get_session
from peadvisor.models import Actif, TypeActif
from peadvisor.schemas import ActifOut

router = APIRouter(prefix="/api/actifs", tags=["Actifs"])


@router.get("", response_model=list[ActifOut])
def lister_actifs(
    type: TypeActif | None = None,
    secteur: str | None = None,
    pays: str | None = None,
    tri: str = Query("score_global", pattern="^(score_global|nom|rendement|potentiel|volatilite|per)$"),
    limite: int = Query(500, le=2000),
    session: Session = Depends(get_session),
):
    requete = session.query(Actif)
    if type:
        requete = requete.filter(Actif.type == type)
    if secteur:
        requete = requete.filter(Actif.secteur == secteur)
    if pays:
        requete = requete.filter(Actif.pays == pays)
    colonne = getattr(Actif, tri)
    if tri == "nom":
        requete = requete.order_by(colonne.asc())
    else:
        requete = requete.order_by(colonne.desc().nulls_last())
    return requete.limit(limite).all()


@router.post("/reactualiser")
def reactualiser_actifs(type: TypeActif | None = None, session: Session = Depends(get_session)):
    """Réactualise toutes les valeurs du tableau : re-scrape chaque valeur depuis
    sa source (repli Boursorama) par mnémonique/ISIN, met à jour la fiche, puis
    recalcule tous les scores. Best-effort : les échecs unitaires sont comptés."""
    from datetime import datetime

    from peadvisor.services.scoring import scorer_tous
    from peadvisor.sources.web import CHAMPS_FICHE, SCRAPERS

    requete = session.query(Actif)
    if type:
        requete = requete.filter(Actif.type == type)
    actifs = requete.all()

    maj, echecs, details = 0, 0, []
    sources_ko: dict[str, int] = {}
    for actif in actifs:
        source = actif.source if actif.source in SCRAPERS else "boursorama"
        scraper = SCRAPERS.get(source) or SCRAPERS["boursorama"]
        cle = actif.mnemonique or actif.isin
        try:
            donnees = scraper.recuperer(cle)
            for champ in CHAMPS_FICHE:
                if champ in donnees and champ != "source":
                    setattr(actif, champ, donnees[champ])
            if donnees.get("source_url"):
                actif.source_url = donnees["source_url"]
            actif.date_cours = datetime.utcnow()
            maj += 1
        except Exception as exc:                     # best-effort par valeur
            echecs += 1
            sources_ko[source] = sources_ko.get(source, 0) + 1
            details.append(f"{actif.nom or actif.isin} : {exc}")
    session.commit()
    nb_scores = scorer_tous(session)

    suggestions = _suggestions_reactualisation(actifs, echecs, sources_ko)
    return {"actifs_maj": maj, "echecs": echecs, "actifs_recalcules": nb_scores,
            "details": details[:20], "suggestions": suggestions}


def _suggestions_reactualisation(actifs, echecs, sources_ko) -> list[str]:
    """Rapport technique de fin de réactualisation (pistes d'amélioration)."""
    suggestions: list[str] = []
    if echecs:
        pires = sorted(sources_ko.items(), key=lambda kv: kv[1], reverse=True)
        detail = ", ".join(f"{s} ({n})" for s, n in pires)
        suggestions.append(
            f"{echecs} valeur(s) non réactualisée(s) — sources en échec : {detail}. "
            "Vérifier la connectivité et la structure des pages (onglet Sources → Tester).")
    # Champs critiques peu renseignés sur l'ensemble du tableau.
    if actifs:
        for champ, libelle in (("cours", "cours"), ("score_global", "score global"),
                               ("secteur", "secteur"), ("per", "PER"),
                               ("objectif_cours", "objectif de cours")):
            manquants = sum(1 for a in actifs if getattr(a, champ, None) is None)
            if manquants > len(actifs) * 0.4:
                suggestions.append(
                    f"Le champ « {libelle} » manque pour {manquants}/{len(actifs)} valeurs : "
                    "brancher une source plus riche ou compléter le scraping.")
    sans_url = [a for a in actifs if not a.source_url]
    if sans_url:
        suggestions.append(
            f"{len(sans_url)} valeur(s) sans lien d'acquisition (données de démonstration ou "
            "source non tracée) : ré-acquérir depuis une source pour renseigner la colonne Source.")
    if not suggestions:
        suggestions.append("Aucune anomalie détectée : toutes les valeurs sont à jour.")
    return suggestions


@router.get("/{isin}", response_model=ActifOut)
def detail_actif(isin: str, session: Session = Depends(get_session)):
    actif = session.query(Actif).filter(Actif.isin == isin.upper()).one_or_none()
    if not actif:
        raise HTTPException(404, f"Aucun actif avec l'ISIN {isin}")
    return actif


@router.delete("/{isin}")
def supprimer_actif(isin: str, session: Session = Depends(get_session)):
    """Retire une valeur du référentiel (bouton « supprimer » d'une ligne)."""
    from peadvisor.models import ElementWatchlist, HistoriqueCours, HistoriqueScore

    actif = session.query(Actif).filter(Actif.isin == isin.upper()).one_or_none()
    if not actif:
        raise HTTPException(404, f"Aucun actif avec l'ISIN {isin}")
    # Nettoyage des dépendances (pas de cascade déclarée).
    session.query(HistoriqueCours).filter(HistoriqueCours.actif_id == actif.id).delete()
    session.query(HistoriqueScore).filter(HistoriqueScore.actif_id == actif.id).delete()
    session.query(ElementWatchlist).filter(ElementWatchlist.actif_id == actif.id).delete()
    session.delete(actif)
    session.commit()
    return {"supprime": isin.upper(), "nom": actif.nom}


@router.get("/{isin}/sous-scores")
def sous_scores_actif(isin: str, session: Session = Depends(get_session)):
    actif = session.query(Actif).filter(Actif.isin == isin.upper()).one_or_none()
    if not actif:
        raise HTTPException(404, f"Aucun actif avec l'ISIN {isin}")
    return json.loads(actif.sous_scores) if actif.sous_scores else {}


@router.get("/{isin}/cours")
def serie_de_cours(isin: str, limite: int = Query(750, le=5000),
                   session: Session = Depends(get_session)):
    """Historique de cours quotidiens (du plus ancien au plus récent)."""
    from peadvisor.models import HistoriqueCours

    actif = session.query(Actif).filter(Actif.isin == isin.upper()).one_or_none()
    if not actif:
        raise HTTPException(404, f"Aucun actif avec l'ISIN {isin}")
    lignes = (session.query(HistoriqueCours)
              .filter(HistoriqueCours.actif_id == actif.id)
              .order_by(HistoriqueCours.date.desc()).limit(limite).all())
    return [{"date": l.date.isoformat(), "cours": l.cours} for l in reversed(lignes)]


@router.get("/{isin}/historique")
def historique_actif(isin: str, limite: int = Query(100, le=1000),
                     session: Session = Depends(get_session)):
    """Historique des scores et cours enregistrés à chaque mise à jour."""
    actif = session.query(Actif).filter(Actif.isin == isin.upper()).one_or_none()
    if not actif:
        raise HTTPException(404, f"Aucun actif avec l'ISIN {isin}")
    historique = sorted(actif.historique_scores, key=lambda h: h.date, reverse=True)[:limite]
    return [
        {"date": h.date, "score_global": h.score_global, "cours": h.cours}
        for h in historique
    ]
