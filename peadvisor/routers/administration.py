"""Endpoints d'administration : import, journal, paramètres, sources, watchlist."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from peadvisor.config import (charger_profil, charger_scoring, charger_settings,
                              sauvegarder_profil, sauvegarder_scoring)
from datetime import datetime

from peadvisor.database import get_session
from peadvisor.models import Actif, ElementWatchlist, JournalMaj, TypeActif
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


@router.post("/import/boursorama/{requete:path}")
def importer_boursorama(requete: str, session: Session = Depends(get_session)):
    """Ajoute/met à jour une valeur depuis Boursorama, par **nom, ISIN ou code**
    (ex. « Air Liquide », « FR0000120073 » ou « 1rPAI »), puis recalcule les
    scores. La recherche par nom/ISIN résout automatiquement le code."""
    from peadvisor.sources.boursorama import (CHAMPS_FICHE, code_ou_recherche,
                                              recuperer_un)

    try:
        code = code_ou_recherche(requete)
    except Exception as exc:
        raise HTTPException(502, f"Recherche Boursorama échouée : {exc}")
    if not code:
        raise HTTPException(404, f"Aucune valeur Boursorama trouvée pour « {requete} »")
    try:
        donnees = recuperer_un(code)
    except Exception as exc:
        raise HTTPException(502, f"Scraping Boursorama échoué ({code}) : {exc}")
    isin = donnees.get("isin")
    if not isin:
        raise HTTPException(422, "ISIN introuvable sur la page (structure Boursorama modifiée ?)")

    champs = {c: donnees[c] for c in CHAMPS_FICHE if c in donnees}
    actif = session.query(Actif).filter(Actif.isin == isin).one_or_none()
    cree = actif is None
    if cree:
        actif = Actif(isin=isin, type=TypeActif.ACTION, nom=donnees.get("nom") or code)
        session.add(actif)
    for champ, valeur in champs.items():
        setattr(actif, champ, valeur)
    if not actif.nom:
        actif.nom = donnees.get("nom") or code
    actif.date_cours = datetime.utcnow()
    session.commit()

    scorer_tous(session)
    session.refresh(actif)
    return {"cree": cree, "code_boursorama": code, "isin": isin, "nom": actif.nom,
            "cours": actif.cours, "source": actif.source,
            "score_global": actif.score_global, "donnees_extraites": donnees}


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
    from peadvisor.sources.http import SourceHTTPBase

    settings = charger_settings()
    sources = []
    for nom, classe in REGISTRE.items():
        info = {"nom": nom, "necessite_cle": False, "cle_configuree": None,
                "testable": issubclass(classe, SourceHTTPBase)}
        if issubclass(classe, SourceHTTPBase):
            instance = classe()
            info["necessite_cle"] = instance.necessite_cle
            if instance.necessite_cle:
                info["cle_configuree"] = instance._cle() is not None
                info["variable_env"] = instance.variable_env
        sources.append(info)
    return {
        "source_active": settings["donnees"]["source_active"],
        "sources": sources,
    }


@router.get("/reference/figi/{isin}")
def resoudre_figi(isin: str, place: str = "GR"):
    """Résout un ISIN en ticker/place via OpenFIGI (annuaire, pas des cours)."""
    from peadvisor.services.reference import resoudre_isin

    return resoudre_isin(isin, place)


@router.post("/sources/{nom}/tester")
def tester_source(nom: str):
    """Teste une source sur un titre : présence de la clé, appel réel,
    nombre de points d'historique reçus."""
    from peadvisor.sources.http import SourceHTTPBase

    if nom not in REGISTRE:
        raise HTTPException(404, f"Source inconnue : {nom}. Disponibles : {list(REGISTRE)}")
    classe = REGISTRE[nom]
    if not issubclass(classe, SourceHTTPBase):
        return {"ok": True, "info": f"La source '{nom}' ne se teste pas par requête HTTP "
                                    "(locale ou bibliothèque dédiée)."}
    return classe().tester()


@router.get("/parametres/profil")
def consulter_profil():
    """Profil investisseur : objectif, niveau de risque, horizon, algorithme."""
    return charger_profil()


@router.put("/parametres/profil")
def modifier_profil(maj: dict = Body(...)):
    """Modifie le profil investisseur (interrupteurs de l'écran Paramètres).

    Il pilote l'algorithme du classement du tableau de bord et pré-remplit
    le formulaire d'allocation.
    """
    if "objectif" in maj and maj["objectif"] not in ("croissance", "dividendes", "equilibre"):
        raise HTTPException(400, "objectif : croissance (capitalisation), dividendes (revenus) ou equilibre")
    if "algorithme_decision" in maj and maj["algorithme_decision"] not in ("weighted", "topsis"):
        raise HTTPException(400, "algorithme_decision : weighted ou topsis")
    if "niveau_risque" in maj and not (isinstance(maj["niveau_risque"], int)
                                       and 1 <= maj["niveau_risque"] <= 7):
        raise HTTPException(400, "niveau_risque : entier de 1 à 7")
    if "horizon_annees" in maj and not (isinstance(maj["horizon_annees"], int)
                                        and 1 <= maj["horizon_annees"] <= 40):
        raise HTTPException(400, "horizon_annees : entier de 1 à 40")
    return sauvegarder_profil(maj)


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
