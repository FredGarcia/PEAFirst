"""Import à la demande d'une valeur scrapée (upsert + rescoring), partagé par
l'API et l'agent MCP."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from peadvisor.models import Actif, TypeActif
from peadvisor.services.scoring import scorer_tous
from peadvisor.sources.web import CHAMPS_FICHE, SCRAPERS


def importer_valeur(session: Session, source: str, requete: str,
                    confirmer: bool = False) -> dict[str, Any]:
    """Scrape une valeur depuis `source` (par nom/ISIN/code), l'ajoute ou la met
    à jour dans le référentiel, recalcule les scores et renvoie un récapitulatif.

    Si la valeur n'est **pas éligible au PEA** et que `confirmer` est faux, la
    valeur n'est **pas** enregistrée : on renvoie `confirmation_requise=True`
    avec la raison, pour que l'interface demande une confirmation d'ajout.

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

    # Éligibilité PEA : si non confirmée et ajout non forcé, demander confirmation
    # (sans rien enregistrer).
    eligible_scrape = donnees.get("eligible_pea")
    if eligible_scrape is False and not confirmer:
        return {"confirmation_requise": True, "cree": False, "isin": isin,
                "nom": donnees.get("nom") or requete, "type": type_actif.value,
                "onglet": type_actif.value.lower(), "eligible_pea": False,
                "source": donnees.get("source", source), "cours": donnees.get("cours"),
                "raison": ("Cette valeur n'apparaît pas éligible au PEA sur la page "
                           f"{scraper.libelle}. Confirmer l'ajout au référentiel ?"),
                "donnees_extraites": donnees}

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
    if donnees.get("source_url"):
        actif.source_url = donnees["source_url"]
    actif.date_cours = datetime.utcnow()
    session.commit()

    scorer_tous(session)
    session.refresh(actif)

    eligible = actif.eligible_pea
    avertissement = None
    if eligible is False:
        avertissement = ("Éligibilité PEA non confirmée sur la page — vérifier "
                         "manuellement avant d'investir.")
    return {"confirmation_requise": False, "cree": cree, "source": actif.source,
            "isin": isin, "nom": actif.nom,
            "type": actif.type.value, "onglet": actif.type.value.lower(),
            "eligible_pea": eligible, "avertissement": avertissement,
            "cours": actif.cours, "score_global": actif.score_global,
            "donnees_extraites": donnees}
