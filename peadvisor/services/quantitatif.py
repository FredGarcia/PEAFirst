"""Moteur quantitatif (niveau L2 — Analyse).

Calcule, à partir des historiques de cours quotidiens :

- volatilité annualisée réalisée (remplace la volatilité déclarative dans le
  scoring et la dérivation du niveau de risque) ;
- performance sur 1 an ;
- drawdown maximal (pire baisse depuis un plus-haut) ;
- ratios de Sharpe et de Sortino (annualisés, taux sans risque paramétrable) ;
- VaR historique à 95 % (perte quotidienne dépassée 5 % du temps) ;
- corrélations entre actifs (rendements quotidiens alignés par date).

Sans dépendance externe (statistiques calculées à la main) : le module reste
exact et testable, et pourra passer à numpy/pandas quand la volumétrie
l'exigera.
"""

from __future__ import annotations

import json
import math
import statistics
from datetime import date

from sqlalchemy.orm import Session

from peadvisor.config import charger_settings
from peadvisor.models import Actif, HistoriqueCours

JOURS_BOURSE_PAR_AN = 252
MIN_POINTS = 60  # en dessous, les indicateurs ne sont pas significatifs


def _rendements(cours: list[float]) -> list[float]:
    return [cours[i] / cours[i - 1] - 1 for i in range(1, len(cours)) if cours[i - 1] > 0]


def calculer_indicateurs(cours: list[float], taux_sans_risque_pct: float = 2.5) -> dict | None:
    """Indicateurs quantitatifs d'une série de clôtures quotidiennes (ordonnée)."""
    if len(cours) < MIN_POINTS:
        return None
    rendements = _rendements(cours)
    moyenne = statistics.fmean(rendements)
    ecart_type = statistics.pstdev(rendements)

    volatilite = ecart_type * math.sqrt(JOURS_BOURSE_PAR_AN) * 100

    # Performance sur ~1 an de séances (ou toute la série si plus courte).
    recul = min(JOURS_BOURSE_PAR_AN, len(cours) - 1)
    perf_1an = (cours[-1] / cours[-1 - recul] - 1) * 100

    # Drawdown maximal.
    plus_haut = cours[0]
    drawdown_max = 0.0
    for c in cours:
        plus_haut = max(plus_haut, c)
        drawdown_max = min(drawdown_max, c / plus_haut - 1)

    # Sharpe et Sortino annualisés.
    rendement_annuel = moyenne * JOURS_BOURSE_PAR_AN
    excedent = rendement_annuel - taux_sans_risque_pct / 100
    sharpe = excedent / (ecart_type * math.sqrt(JOURS_BOURSE_PAR_AN)) if ecart_type > 0 else None
    negatifs = [r for r in rendements if r < 0]
    ecart_baisse = statistics.pstdev(negatifs) if len(negatifs) >= 2 else None
    sortino = (excedent / (ecart_baisse * math.sqrt(JOURS_BOURSE_PAR_AN))
               if ecart_baisse else None)

    # VaR historique 95 % (perte quotidienne, en % positif).
    tries = sorted(rendements)
    var_95 = -tries[max(0, int(0.05 * len(tries)) - 1)] * 100

    arrondi = lambda v: round(v, 2) if v is not None else None  # noqa: E731
    return {
        "volatilite_pct": arrondi(volatilite),
        "perf_1an_pct": arrondi(perf_1an),
        "drawdown_max_pct": arrondi(drawdown_max * 100),
        "sharpe": arrondi(sharpe),
        "sortino": arrondi(sortino),
        "var_95_jour_pct": arrondi(var_95),
        "nb_points": len(cours),
    }


def _serie(session: Session, actif_id: int) -> list[tuple[date, float]]:
    lignes = (session.query(HistoriqueCours.date, HistoriqueCours.cours)
              .filter(HistoriqueCours.actif_id == actif_id)
              .order_by(HistoriqueCours.date).all())
    return [(d, c) for d, c in lignes]


def calculer_tous(session: Session) -> int:
    """Calcule et stocke les indicateurs quantitatifs de tous les actifs
    disposant d'un historique suffisant. La volatilité réalisée remplace la
    volatilité déclarative (elle alimentera le scoring et le niveau de
    risque). Renvoie le nombre d'actifs traités."""
    settings = charger_settings()
    taux = float(settings.get("quantitatif", {}).get("taux_sans_risque_pct", 2.5))
    nb = 0
    for actif in session.query(Actif).all():
        serie = _serie(session, actif.id)
        indicateurs = calculer_indicateurs([c for _, c in serie], taux)
        if indicateurs is None:
            continue
        actif.indicateurs_quant = json.dumps(indicateurs)
        actif.volatilite = indicateurs["volatilite_pct"]
        nb += 1
    session.commit()
    return nb


def correlations(session: Session, isins: list[str]) -> dict:
    """Matrice de corrélation de Pearson des rendements quotidiens,
    alignés sur les dates communes aux séries."""
    series: dict[str, dict[date, float]] = {}
    for isin in isins:
        actif = session.query(Actif).filter(Actif.isin == isin.upper()).one_or_none()
        if actif is None:
            continue
        serie = _serie(session, actif.id)
        if len(serie) >= MIN_POINTS:
            series[actif.isin] = dict(serie)
    retenus = list(series)

    def correlation(a: str, b: str) -> float | None:
        communes = sorted(set(series[a]) & set(series[b]))
        if len(communes) < MIN_POINTS:
            return None
        ra = _rendements([series[a][d] for d in communes])
        rb = _rendements([series[b][d] for d in communes])
        ma, mb = statistics.fmean(ra), statistics.fmean(rb)
        num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
        den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
        return round(num / den, 3) if den else None

    matrice = {a: {b: (1.0 if a == b else correlation(a, b)) for b in retenus} for a in retenus}
    return {"isins": retenus, "matrice": matrice}
