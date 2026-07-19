"""Endpoints d'administration : import, journal, paramètres, sources, watchlist."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from peadvisor.config import charger_scoring, charger_settings, sauvegarder_scoring
from peadvisor.database import get_session
from peadvisor.models import Actif, ElementWatchlist, JournalMaj
from peadvisor.schemas import ElementWatchlistOut, JournalOut
from peadvisor.services.importer import importer
from peadvisor.services.scoring import scorer_tous
from peadvisor.sources import REGISTRE

router = APIRouter(prefix="/api", tags=["Administration"])


# --- Import & journal (M1/M12) -------------------------------------------

@router.post("/import", response_model=JournalOut)
def lancer_import(source: str | None = None, session: Session = Depends(get_session)):
    """Lance un import manuel depuis la source active (ou la source indiquée)."""
    if source and source not in REGISTRE:
        raise HTTPException(400, f"Source inconnue : {source}. Disponibles : {list(REGISTRE)}")
    return importer(session, source)


@router.post("/scores/recalculer")
def recalculer_scores(session: Session = Depends(get_session)):
    """Recalcule tous les scores (après modification des pondérations par exemple)."""
    nb = scorer_tous(session)
    return {"actifs_recalcules": nb}


@router.get("/journal", response_model=list[JournalOut])
def consulter_journal(limite: int = Query(50, le=500), session: Session = Depends(get_session)):
    return session.query(JournalMaj).order_by(JournalMaj.date.desc()).limit(limite).all()


# --- Sources & paramètres (M11) ------------------------------------------

@router.get("/sources")
def lister_sources():
    settings = charger_settings()
    return {
        "source_active": settings["donnees"]["source_active"],
        "sources_disponibles": list(REGISTRE),
    }


@router.get("/parametres/scoring")
def consulter_ponderations():
    return charger_scoring()


@router.put("/parametres/scoring")
def modifier_ponderations(ponderations: dict[str, float] = Body(...),
                          session: Session = Depends(get_session)):
    """Modifie les pondérations du score puis recalcule tous les scores."""
    cfg = charger_scoring()
    inconnues = set(ponderations) - set(cfg["ponderations"])
    if inconnues:
        raise HTTPException(400, f"Critères inconnus : {sorted(inconnues)}")
    cfg["ponderations"].update({c: float(v) for c, v in ponderations.items()})
    sauvegarder_scoring(cfg)
    nb = scorer_tous(session)
    return {"ponderations": cfg["ponderations"], "actifs_recalcules": nb}


# --- Watchlist (M9) -------------------------------------------------------

@router.get("/watchlist", response_model=list[ElementWatchlistOut])
def consulter_watchlist(session: Session = Depends(get_session)):
    return session.query(ElementWatchlist).order_by(ElementWatchlist.ajoute_le.desc()).all()


@router.post("/watchlist/{isin}", response_model=ElementWatchlistOut)
def ajouter_watchlist(isin: str, commentaire: str | None = None,
                      session: Session = Depends(get_session)):
    actif = session.query(Actif).filter(Actif.isin == isin.upper()).one_or_none()
    if not actif:
        raise HTTPException(404, f"Aucun actif avec l'ISIN {isin}")
    existant = session.query(ElementWatchlist).filter(ElementWatchlist.actif_id == actif.id).one_or_none()
    if existant:
        return existant
    element = ElementWatchlist(actif_id=actif.id, commentaire=commentaire)
    session.add(element)
    session.commit()
    session.refresh(element)
    return element


@router.delete("/watchlist/{isin}")
def retirer_watchlist(isin: str, session: Session = Depends(get_session)):
    actif = session.query(Actif).filter(Actif.isin == isin.upper()).one_or_none()
    element = actif and session.query(ElementWatchlist).filter(
        ElementWatchlist.actif_id == actif.id).one_or_none()
    if not element:
        raise HTTPException(404, f"{isin} n'est pas dans la watchlist")
    session.delete(element)
    session.commit()
    return {"supprime": isin.upper()}
