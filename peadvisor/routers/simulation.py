"""Endpoint du simulateur d'investissement."""

from __future__ import annotations

from fastapi import APIRouter

from peadvisor.schemas import DemandeSimulation, ReponseSimulation
from peadvisor.services.simulation import simuler

router = APIRouter(prefix="/api/simulation", tags=["Simulation"])


@router.post("", response_model=ReponseSimulation)
def lancer_simulation(demande: DemandeSimulation):
    """Projette un investissement PEA : versements, dividendes, 3 scénarios,
    fiscalité estimée."""
    return simuler(demande)
