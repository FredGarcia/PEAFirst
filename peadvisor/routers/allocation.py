"""Endpoint du moteur d'allocation automatique."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from peadvisor.database import get_session
from peadvisor.schemas import DemandeAllocation, ReponseAllocation
from peadvisor.services.allocation import proposer_allocation

router = APIRouter(prefix="/api/allocation", tags=["Allocation"])


@router.post("", response_model=ReponseAllocation)
def generer_allocation(demande: DemandeAllocation, session: Session = Depends(get_session)):
    """Propose une allocation de portefeuille selon capital, risque, horizon et objectif."""
    return proposer_allocation(session, demande)
