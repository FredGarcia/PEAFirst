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
