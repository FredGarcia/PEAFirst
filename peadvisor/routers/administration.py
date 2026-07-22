"""Endpoints d'administration : import, journal, paramètres, sources, watchlist."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from peadvisor.config import (CRITERES_SCORE, charger_profil, charger_profils_scoring,
                              charger_scoring, charger_settings, sauvegarder_profil,
                              sauvegarder_profils_scoring, sauvegarder_scoring)
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


@router.get("/sources/scrapers")
def lister_scrapers():
    """Liste des sources de scraping (pour les boutons de l'onglet Actions)."""
    from peadvisor.sources.web import SCRAPERS

    return [{"nom": s.nom, "libelle": s.libelle, "valide": s.valide}
            for s in SCRAPERS.values()]


@router.post("/import/web/{source}/{requete:path}")
def importer_web(source: str, requete: str, session: Session = Depends(get_session)):
    """Ajoute/met à jour une valeur en la scrapant sur `source` (Boursorama,
    Boursier, Zonebourse…), par **nom, ISIN ou code**, puis recalcule les scores."""
    from peadvisor.services.scraping import importer_valeur

    try:
        return importer_valeur(session, source, requete)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Scraping {source} échoué : {exc}")


# Rétro-compatibilité : l'ancienne route Boursorama passe par le dispatcher.
@router.post("/import/boursorama/{requete:path}")
def importer_boursorama(requete: str, session: Session = Depends(get_session)):
    """Alias historique de /import/web/boursorama/{requête}."""
    return importer_web("boursorama", requete, session)


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
    urls_exemple = charger_profil().get("urls_exemple", {})
    sources = []
    for nom, classe in REGISTRE.items():
        # Une source est testable si elle expose une page exemple (URL dans les
        # paramètres) ou si c'est une source HTTP générique avec test dédié.
        info = {"nom": nom, "necessite_cle": False, "cle_configuree": None,
                "testable": nom in urls_exemple or issubclass(classe, SourceHTTPBase),
                "url_exemple": urls_exemple.get(nom)}
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


@router.get("/sources/etats")
def etats_des_sources():
    """État d'acquisition de chaque source (pour colorer les boutons de la barre
    de recherche) : « disponible » (bleu, des données arrivent), « vide »
    (orange, le test passe mais aucune donnée), « indisponible » (gris, échec).

    ⚠️ Interroge réellement chaque source : à déclencher à la demande."""
    from peadvisor.sources.http import SourceHTTPBase
    from peadvisor.sources.web import SCRAPERS

    TICKER_TEST = "TTE"          # TotalEnergies, largement coté
    etats = []
    noms = list(dict.fromkeys(list(SCRAPERS) + list(REGISTRE)))  # union, ordre stable
    for nom in noms:
        # Catégorie : recherche par valeur (scrapers) ou import global (sources HTTP).
        categorie = "recherche" if nom in SCRAPERS and nom != "seed" else "import"
        libelle = SCRAPERS[nom].libelle if nom in SCRAPERS else nom
        etat, detail = "indisponible", ""
        try:
            if nom == "seed":
                etat, categorie = "disponible", "import"
            elif nom in SCRAPERS:
                donnees = SCRAPERS[nom].recuperer(TICKER_TEST)
                etat = "disponible" if (donnees.get("isin") or donnees.get("cours")) else "vide"
            elif nom in REGISTRE and issubclass(REGISTRE[nom], SourceHTTPBase):
                r = REGISTRE[nom]().tester()
                if not r.get("ok"):
                    etat, detail = "indisponible", r.get("erreur", "")
                elif r.get("points_historique") or (r.get("cotation") or {}).get("cours"):
                    etat = "disponible"
                else:
                    etat, detail = "vide", "test OK mais aucune donnée"
            elif nom == "yahoo":
                r = _tester_exemple("yahoo")
                etat = "disponible" if r.get("ok") and r.get("exemple_json") else (
                    "vide" if r.get("ok") else "indisponible")
                detail = r.get("erreur", "")
        except Exception as exc:
            etat, detail = "indisponible", f"{type(exc).__name__} : {exc}"
        etats.append({"nom": nom, "libelle": libelle, "categorie": categorie,
                      "etat": etat, "detail": detail[:200]})
    return etats


@router.get("/reference/figi/{isin}")
def resoudre_figi(isin: str, place: str = "GR"):
    """Résout un ISIN en ticker/place via OpenFIGI (annuaire, pas des cours)."""
    from peadvisor.services.reference import resoudre_isin

    return resoudre_isin(isin, place)


@router.post("/sources/{nom}/tester")
def tester_source(nom: str):
    """Teste une source : récupère la page exemple (URL paramétrable) et renvoie
    un extrait en JSON ; en cas d'échec, la cause en texte. À défaut d'URL
    exemple, replie sur le test HTTP dédié (présence de clé, appel réel)."""
    from peadvisor.sources.http import SourceHTTPBase

    if nom not in REGISTRE:
        raise HTTPException(404, f"Source inconnue : {nom}. Disponibles : {list(REGISTRE)}")
    if charger_profil().get("urls_exemple", {}).get(nom):
        return _tester_exemple(nom)
    classe = REGISTRE[nom]
    if not issubclass(classe, SourceHTTPBase):
        return {"ok": False, "erreur": f"Aucune URL exemple définie pour « {nom} » "
                                       "(onglet Paramètres)."}
    return classe().tester()


def _tester_exemple(nom: str) -> dict:
    """Teste une source en récupérant sa page exemple (URL paramétrable) et en
    renvoyant un extrait JSON ; sinon un extrait texte (HTML/CSV) ; en cas
    d'échec, la cause en texte."""
    import requests

    url = charger_profil().get("urls_exemple", {}).get(nom, "")
    if not url:
        return {"ok": False, "erreur": f"Aucune URL exemple définie pour « {nom} » "
                                       "(onglet Paramètres)."}
    try:
        rep = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; PEAdvisor/1.0)"},
                           timeout=20)
        rep.raise_for_status()
    except Exception as exc:
        return {"ok": False, "url": url, "erreur": f"{type(exc).__name__} : {exc}"}

    # Réponse JSON → extrait résumé (métadonnées Yahoo si présentes, sinon brut).
    try:
        data = rep.json()
    except ValueError:
        data = None
    if data is not None:
        try:
            meta = data["chart"]["result"][0]["meta"]
            extrait = {k: meta[k] for k in ("symbol", "currency", "exchangeName",
                       "regularMarketPrice", "regularMarketTime") if k in meta}
        except (KeyError, IndexError, TypeError):
            extrait = data
        return {"ok": True, "url": url, "exemple_json": extrait}

    # Réponse non-JSON (HTML, CSV…) → extrait texte tronqué.
    texte = rep.text.strip()
    return {"ok": True, "url": url,
            "exemple_texte": texte[:2000] + ("…" if len(texte) > 2000 else "")}


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
    """Modifie les pondérations actives du score puis recalcule tous les scores."""
    cfg = charger_scoring()
    inconnues = set(ponderations) - set(CRITERES_SCORE)
    if inconnues:
        raise HTTPException(400, f"Critères inconnus : {sorted(inconnues)}")
    cfg["ponderations"].update({c: float(v) for c, v in ponderations.items()})
    sauvegarder_scoring(cfg)
    nb = scorer_tous(session)
    return {"ponderations": cfg["ponderations"], "actifs_recalcules": nb}


# --- Profils de pondération du score (CRUD) ------------------------------

def _valider_ponderations(ponderations: dict) -> dict[str, float]:
    inconnues = set(ponderations) - set(CRITERES_SCORE)
    if inconnues:
        raise HTTPException(400, f"Critères inconnus : {sorted(inconnues)}. "
                                 f"Attendus : {sorted(CRITERES_SCORE)}")
    try:
        valeurs = {c: float(v) for c, v in ponderations.items()}
    except (TypeError, ValueError):
        raise HTTPException(400, "Les pondérations doivent être numériques.")
    if any(v < 0 for v in valeurs.values()):
        raise HTTPException(400, "Les pondérations doivent être positives ou nulles.")
    if sum(valeurs.values()) <= 0:
        raise HTTPException(400, "Au moins une pondération doit être supérieure à 0.")
    return valeurs


@router.get("/scoring/criteres")
def criteres_du_score():
    """Familles de critères (libellés, variables) et pondérations actives."""
    return {"criteres": CRITERES_SCORE, "ponderations": charger_scoring()["ponderations"]}


@router.get("/scoring/profils")
def lister_profils_scoring():
    """Profils de pondération enregistrés (préenregistrés + créés par l'utilisateur)."""
    return charger_profils_scoring()


@router.post("/scoring/profils")
def creer_profil_scoring(corps: dict = Body(...)):
    nom = (corps.get("nom") or "").strip()
    if not nom:
        raise HTTPException(400, "Nom de profil requis.")
    profils = charger_profils_scoring()
    if nom in profils:
        raise HTTPException(409, f"Le profil « {nom} » existe déjà.")
    profils[nom] = _valider_ponderations(corps.get("ponderations") or {})
    sauvegarder_profils_scoring(profils)
    return {"nom": nom, "ponderations": profils[nom]}


@router.put("/scoring/profils/{nom}")
def modifier_profil_scoring(nom: str, ponderations: dict = Body(...)):
    profils = charger_profils_scoring()
    if nom not in profils:
        raise HTTPException(404, f"Profil inconnu : {nom}")
    profils[nom] = _valider_ponderations(ponderations)
    sauvegarder_profils_scoring(profils)
    return {"nom": nom, "ponderations": profils[nom]}


@router.delete("/scoring/profils/{nom}")
def supprimer_profil_scoring(nom: str):
    profils = charger_profils_scoring()
    if nom not in profils:
        raise HTTPException(404, f"Profil inconnu : {nom}")
    del profils[nom]
    sauvegarder_profils_scoring(profils)
    return {"supprime": nom}


@router.post("/scoring/profils/{nom}/appliquer")
def appliquer_profil_scoring(nom: str, session: Session = Depends(get_session)):
    """Applique un profil : ses pondérations deviennent actives, puis rescore."""
    profils = charger_profils_scoring()
    if nom not in profils:
        raise HTTPException(404, f"Profil inconnu : {nom}")
    cfg = charger_scoring()
    cfg["ponderations"] = {c: float(v) for c, v in profils[nom].items()}
    sauvegarder_scoring(cfg)
    nb = scorer_tous(session)
    return {"profil": nom, "ponderations": cfg["ponderations"], "actifs_recalcules": nb}


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
