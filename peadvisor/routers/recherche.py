"""Service de recherche — API indépendante, partagée par les onglets Actions,
ETF et OPCVM.

Recherche une valeur par **nom, ISIN ou code** sur une source (Boursorama,
Boursier…), vérifie son **éligibilité PEA**, détecte son **type**
(ACTION / ETF / OPCVM) pour l'orienter vers le bon onglet, puis l'ajoute au
référentiel.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from peadvisor.database import get_session
from peadvisor.services.scraping import importer_valeur
from peadvisor.sources.web import SCRAPERS

router = APIRouter(prefix="/api/recherche", tags=["Recherche"])


@router.get("/sources")
def sources_de_recherche():
    """Liste des sources interrogeables (pour les boutons de la barre de recherche)."""
    return [{"nom": s.nom, "libelle": s.libelle, "valide": s.valide}
            for s in SCRAPERS.values()]


@router.post("/{source}/{requete:path}")
def rechercher(source: str, requete: str, session: Session = Depends(get_session)):
    """Recherche et ajoute une valeur. Renvoie le type détecté (onglet cible),
    l'éligibilité PEA et un éventuel avertissement."""
    try:
        return importer_valeur(session, source, requete)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Recherche {source} échouée : {exc}")
