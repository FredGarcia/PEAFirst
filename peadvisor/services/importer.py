"""Import et normalisation des données (niveaux L1/L2).

- lit la source active définie dans config/settings.yaml ;
- normalise les enregistrements (champ par champ, types contrôlés) ;
- dédoublonne par ISIN (clé métier) : un actif existant est mis à jour,
  jamais dupliqué ; les doublons intra-lot sont comptés et ignorés ;
- journalise le traitement (table journal_maj) ;
- déclenche le recalcul des scores après chaque import.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from peadvisor.config import charger_settings
from peadvisor.models import Actif, JournalMaj, TypeActif
from peadvisor.services import scoring

CHAMPS_MAJ = [
    "nom", "mnemonique", "marche", "devise", "pays", "secteur",
    "eligible_pea", "eligible_pea_pme", "societe_gestion", "capitalisation",
    "cours", "rendement", "per", "croissance", "volatilite", "niveau_risque",
    "score_esg", "objectif_cours", "consensus",
]


def _normaliser(brut: dict[str, Any]) -> dict[str, Any] | None:
    """Contrôle et normalise un enregistrement brut. Renvoie None s'il est invalide."""
    isin = (brut.get("isin") or "").strip().upper()
    nom = (brut.get("nom") or "").strip()
    type_brut = (brut.get("type") or "").strip().upper()
    if len(isin) != 12 or not nom or type_brut not in TypeActif.__members__:
        return None
    propre: dict[str, Any] = {"isin": isin, "nom": nom, "type": TypeActif[type_brut]}
    for champ in CHAMPS_MAJ:
        if champ in ("nom",):
            continue
        if champ in brut and brut[champ] is not None:
            propre[champ] = brut[champ]
    return propre


def importer(session: Session, nom_source: str | None = None) -> JournalMaj:
    """Importe la source demandée (ou la source active) et journalise le résultat."""
    from peadvisor.sources import REGISTRE

    settings = charger_settings()
    nom_source = nom_source or settings["donnees"]["source_active"]
    inclure_pea_pme = bool(settings["donnees"].get("inclure_pea_pme", False))

    journal = JournalMaj(traitement=f"import:{nom_source}", statut="succes",
                         nb_crees=0, nb_maj=0, nb_doublons=0, nb_erreurs=0)
    try:
        source = REGISTRE[nom_source]()
        bruts = source.recuperer()
    except Exception as exc:  # erreur réseau, source inconnue, quota...
        journal.statut = "erreur"
        journal.detail = f"Échec de la récupération : {exc}"
        journal.nb_erreurs = 1
        session.add(journal)
        session.commit()
        return journal

    vus: set[str] = set()
    for brut in bruts:
        propre = _normaliser(brut)
        if propre is None:
            journal.nb_erreurs += 1
            continue
        if propre["isin"] in vus:
            journal.nb_doublons += 1  # doublon intra-lot : ignoré
            continue
        vus.add(propre["isin"])
        if not inclure_pea_pme and propre.get("eligible_pea_pme") and not propre.get("eligible_pea", True):
            continue  # poche PEA-PME désactivée

        existant = session.query(Actif).filter(Actif.isin == propre["isin"]).one_or_none()
        if existant:
            for champ, valeur in propre.items():
                setattr(existant, champ, valeur)
            existant.source = nom_source
            existant.date_cours = datetime.utcnow()
            journal.nb_maj += 1
        else:
            session.add(Actif(**propre, source=nom_source, date_cours=datetime.utcnow()))
            journal.nb_crees += 1

    session.commit()

    nb_scores = scoring.scorer_tous(session)
    journal.detail = (
        f"{journal.nb_crees} créé(s), {journal.nb_maj} mis à jour, "
        f"{journal.nb_doublons} doublon(s) écarté(s), {journal.nb_erreurs} rejet(s). "
        f"Scores recalculés pour {nb_scores} actif(s)."
    )
    if journal.nb_erreurs:
        journal.statut = "avertissement"
    session.add(journal)
    session.commit()
    return journal
