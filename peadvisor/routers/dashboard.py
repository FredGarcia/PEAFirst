"""Endpoints du tableau de bord (KPI, répartitions, tops, matrice de décision)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from peadvisor.database import get_session
from peadvisor.models import Actif
from peadvisor.schemas import LigneClassement
from peadvisor.services.decision import classer

router = APIRouter(prefix="/api/dashboard", tags=["Tableau de bord"])


def _moyenne(valeurs: list[float | None]) -> float | None:
    presentes = [v for v in valeurs if v is not None]
    return round(sum(presentes) / len(presentes), 2) if presentes else None


def _repartition(actifs: list[Actif], attribut: str) -> dict[str, int]:
    comptes: dict[str, int] = {}
    for a in actifs:
        valeur = getattr(a, attribut)
        cle = valeur.value if hasattr(valeur, "value") else (valeur or "Non renseigné")
        comptes[cle] = comptes.get(cle, 0) + 1
    return dict(sorted(comptes.items(), key=lambda kv: kv[1], reverse=True))


def _top(actifs: list[Actif], attribut: str, n: int = 5) -> list[dict]:
    tries = sorted((a for a in actifs if getattr(a, attribut) is not None),
                   key=lambda a: getattr(a, attribut), reverse=True)[:n]
    return [
        {"nom": a.nom, "isin": a.isin, "type": a.type.value, "valeur": getattr(a, attribut),
         "score_global": a.score_global}
        for a in tries
    ]


@router.get("/synthese")
def synthese(session: Session = Depends(get_session)):
    actifs = session.query(Actif).all()
    secteurs = _repartition(actifs, "secteur")
    # Diversification : part du secteur le plus représenté (plus c'est bas, mieux c'est).
    concentration = round(max(secteurs.values()) / len(actifs) * 100, 1) if actifs else None
    return {
        "nb_actifs": len(actifs),
        "repartition_types": _repartition(actifs, "type"),
        "repartition_pays": _repartition(actifs, "pays"),
        "repartition_secteurs": secteurs,
        "rendement_moyen": _moyenne([a.rendement for a in actifs]),
        "potentiel_moyen": _moyenne([a.potentiel for a in actifs]),
        "score_moyen": _moyenne([a.score_global for a in actifs]),
        "score_esg_moyen": _moyenne([a.score_esg for a in actifs]),
        "niveau_risque_moyen": _moyenne([float(a.niveau_risque) for a in actifs if a.niveau_risque]),
        "concentration_secteur_max_pct": concentration,
        "top_opportunites": _top(actifs, "potentiel"),
        "top_dividendes": _top(actifs, "rendement"),
        "top_croissance": _top(actifs, "croissance"),
        "top_scores": _top(actifs, "score_global"),
    }


@router.get("/correlations")
def matrice_correlations(isins: str | None = Query(None, description="ISIN séparés par des virgules ; omis = top 10 par score"),
                         session: Session = Depends(get_session)):
    """Matrice de corrélation des rendements quotidiens (moteur quantitatif)."""
    from peadvisor.services.quantitatif import correlations

    if isins:
        liste = [i.strip() for i in isins.split(",") if i.strip()]
    else:
        tops = (session.query(Actif).order_by(Actif.score_global.desc().nulls_last())
                .limit(10).all())
        liste = [a.isin for a in tops]
    return correlations(session, liste)


@router.get("/classement", response_model=list[LigneClassement])
def matrice_decision(
    methode: str = Query("weighted", pattern="^(weighted|topsis)$"),
    limite: int = Query(20, le=200),
    session: Session = Depends(get_session),
):
    """Matrice de décision multicritère : classement des actifs (score pondéré ou TOPSIS)."""
    actifs = session.query(Actif).all()
    classement = classer(actifs, methode)[:limite]
    return [
        LigneClassement(isin=a.isin, nom=a.nom, type=a.type.value, rang=i + 1, valeur=v)
        for i, (a, v) in enumerate(classement)
    ]
