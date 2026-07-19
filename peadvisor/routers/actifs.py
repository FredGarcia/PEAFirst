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


@router.get("/{isin}/sous-scores")
def sous_scores_actif(isin: str, session: Session = Depends(get_session)):
    actif = session.query(Actif).filter(Actif.isin == isin.upper()).one_or_none()
    if not actif:
        raise HTTPException(404, f"Aucun actif avec l'ISIN {isin}")
    return json.loads(actif.sous_scores) if actif.sous_scores else {}


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
