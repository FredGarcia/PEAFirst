"""Endpoints de la couche de second ordre : auto-observation et auto-amélioration."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from peadvisor.database import get_session
from peadvisor.models import Anomalie, SuggestionPonderations
from peadvisor.services import amelioration, introspection

router = APIRouter(prefix="/api/meta", tags=["Système (second ordre)"])


@router.post("/observer")
def lancer_auto_diagnostic(session: Session = Depends(get_session)):
    """Exécute un cycle d'auto-observation et renvoie le rapport."""
    return introspection.observer(session)


@router.get("/sante")
def etat_de_sante(session: Session = Depends(get_session)):
    """Dernier rapport d'auto-diagnostic (ou null si aucun n'a encore été lancé)."""
    return introspection.dernier_rapport(session)


@router.get("/anomalies")
def lister_anomalies(statut: str = Query("ouverte", pattern="^(ouverte|ignoree|resolue|toutes)$"),
                     session: Session = Depends(get_session)):
    requete = session.query(Anomalie)
    if statut != "toutes":
        requete = requete.filter(Anomalie.statut == statut)
    anomalies = requete.order_by(Anomalie.date.desc()).limit(200).all()
    return [
        {"id": a.id, "date": a.date, "type": a.type, "gravite": a.gravite,
         "message": a.message, "statut": a.statut,
         "isin": a.actif.isin if a.actif else None}
        for a in anomalies
    ]


@router.post("/anomalies/{anomalie_id}/{action}")
def traiter_anomalie(anomalie_id: int, action: str, session: Session = Depends(get_session)):
    if action not in ("ignorer", "resoudre"):
        raise HTTPException(400, "Action attendue : ignorer ou resoudre")
    anomalie = session.get(Anomalie, anomalie_id)
    if anomalie is None:
        raise HTTPException(404, "Anomalie inconnue")
    anomalie.statut = "ignoree" if action == "ignorer" else "resolue"
    session.commit()
    return {"id": anomalie_id, "statut": anomalie.statut}


@router.get("/pouvoir-predictif")
def pouvoir_predictif(session: Session = Depends(get_session)):
    """Corrélation entre les scores passés et les rendements réalisés."""
    return introspection.pouvoir_predictif(session)


def _suggestion_dict(s: SuggestionPonderations) -> dict:
    return {"id": s.id, "date": s.date, "ponderations": json.loads(s.ponderations),
            "correlation_avant": s.correlation_avant, "correlation_apres": s.correlation_apres,
            "statut": s.statut, "commentaire": s.commentaire}


@router.get("/suggestions")
def lister_suggestions(session: Session = Depends(get_session)):
    suggestions = session.query(SuggestionPonderations).order_by(
        SuggestionPonderations.date.desc()).limit(50).all()
    return [_suggestion_dict(s) for s in suggestions]


@router.post("/optimiser")
def optimiser_ponderations(session: Session = Depends(get_session)):
    """Cherche des pondérations plus prédictives ; crée une suggestion si gain réel."""
    resultat = amelioration.proposer_ponderations(session)
    suggestion = resultat.get("suggestion")
    return {"detail": resultat.get("detail"),
            "correlation_actuelle": resultat.get("correlation_actuelle"),
            "suggestion": _suggestion_dict(suggestion) if suggestion else None}


@router.post("/suggestions/{suggestion_id}/appliquer")
def appliquer(suggestion_id: int, session: Session = Depends(get_session)):
    try:
        return amelioration.appliquer_suggestion(session, suggestion_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.post("/suggestions/{suggestion_id}/rejeter")
def rejeter(suggestion_id: int, session: Session = Depends(get_session)):
    try:
        amelioration.rejeter_suggestion(session, suggestion_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"id": suggestion_id, "statut": "rejetee"}
