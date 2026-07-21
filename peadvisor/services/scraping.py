"""Import à la demande d'une valeur scrapée (upsert + rescoring), partagé par
l'API et l'agent MCP."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from peadvisor.models import Actif, TypeActif
from peadvisor.services.scoring import scorer_tous
from peadvisor.sources.web import CHAMPS_FICHE, SCRAPERS


def importer_valeur(session: Session, source: str, requete: str) -> dict[str, Any]:
    """Scrape une valeur depuis `source` (par nom/ISIN/code), l'ajoute ou la met
    à jour dans le référentiel, recalcule les scores et renvoie un récapitulatif.
    Lève ValueError (source inconnue / valeur introuvable / rien d'exploitable)."""
    scraper = SCRAPERS.get(source)
    if scraper is None:
        raise ValueError(f"Source inconnue : {source}. Disponibles : {list(SCRAPERS)}")

    donnees = scraper.recuperer(requete)  # peut lever (réseau, parsing)
    isin = donnees.get("isin")
    if not isin:
        raise ValueError(f"ISIN introuvable sur la page {scraper.libelle} (structure modifiée ?)")

    # Type d'instrument déduit (ventilation Actions / ETF / OPCVM).
    type_detecte = donnees.get("type_detecte", "ACTION")
    type_actif = TypeActif[type_detecte] if type_detecte in TypeActif.__members__ else TypeActif.ACTION

    champs = {c: donnees[c] for c in CHAMPS_FICHE if c in donnees}
    actif = session.query(Actif).filter(Actif.isin == isin).one_or_none()
    cree = actif is None
    if cree:
        actif = Actif(isin=isin, type=type_actif, nom=donnees.get("nom") or requete)
        session.add(actif)
    else:
        actif.type = type_actif
    for champ, valeur in champs.items():
        setattr(actif, champ, valeur)
    if not actif.nom:
        actif.nom = donnees.get("nom") or requete
    actif.date_cours = datetime.utcnow()
    session.commit()

    scorer_tous(session)
    session.refresh(actif)

    eligible = actif.eligible_pea
    avertissement = None
    if eligible is False:
        avertissement = ("Éligibilité PEA non confirmée sur la page — vérifier "
                         "manuellement avant d'investir.")
    return {"cree": cree, "source": actif.source, "isin": isin, "nom": actif.nom,
            "type": actif.type.value, "onglet": actif.type.value.lower(),
            "eligible_pea": eligible, "avertissement": avertissement,
            "cours": actif.cours, "score_global": actif.score_global,
            "donnees_extraites": donnees}
