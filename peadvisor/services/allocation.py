"""Moteur d'allocation automatique (niveau L3 — Décision).

Principe :
1. Le profil de risque (1 à 7) et l'horizon déterminent une répartition
   cible entre trois poches : défensive (actifs de niveau de risque 1-3),
   cœur de portefeuille (4-5) et dynamique (6-7).
2. L'objectif (croissance / dividendes / équilibré) détermine le critère de
   sélection des valeurs à l'intérieur de chaque poche.
3. Les contraintes de diversification de config/settings.yaml sont
   appliquées : poids maximal par ligne, poids maximal par secteur,
   nombre de lignes minimal/maximal.
"""

from __future__ import annotations

import json
import math

from sqlalchemy.orm import Session

from peadvisor.config import charger_settings
from peadvisor.models import Actif, TypeActif
from peadvisor.schemas import DemandeAllocation, LigneAllocation, ReponseAllocation

# Répartition (défensive, cœur, dynamique) en % pour chaque profil 1-7.
MIX_PROFILS: dict[int, tuple[int, int, int]] = {
    1: (70, 30, 0),
    2: (55, 40, 5),
    3: (40, 50, 10),
    4: (25, 55, 20),
    5: (15, 55, 30),
    6: (5, 50, 45),
    7: (0, 40, 60),
}

LIBELLES_POCHES = ("défensive", "cœur", "dynamique")


def _poche(actif: Actif) -> int:
    niveau = actif.niveau_risque or 4
    if niveau <= 3:
        return 0
    if niveau <= 5:
        return 1
    return 2


def _metrique(actif: Actif, objectif: str) -> float:
    """Note de sélection selon l'objectif, à partir des sous-scores."""
    sous = json.loads(actif.sous_scores) if actif.sous_scores else {}
    score = actif.score_global or 0.0
    if objectif == "dividendes":
        return 0.5 * (sous.get("dividende") or 0) + 0.2 * (sous.get("volatilite") or 0) + 0.3 * score
    if objectif == "croissance":
        return 0.35 * (sous.get("croissance") or 0) + 0.25 * (sous.get("potentiel") or 0) + 0.4 * score
    return score  # équilibré : score global


def _ajuster_horizon(mix: tuple[int, int, int], horizon: int) -> tuple[int, int, int]:
    """Horizon court → plus défensif ; horizon long → plus dynamique (±10 pts)."""
    defensif, coeur, dynamique = mix
    if horizon < 5:
        transfert = min(10, dynamique)
        return (defensif + transfert, coeur, dynamique - transfert)
    if horizon >= 15:
        transfert = min(10, defensif)
        return (defensif - transfert, coeur, dynamique + transfert)
    return mix


def proposer_allocation(session: Session, demande: DemandeAllocation) -> ReponseAllocation:
    params = charger_settings()["allocation"]
    poids_max_ligne = float(params.get("poids_max_par_ligne", 0.10))
    poids_max_secteur = float(params.get("poids_max_par_secteur", 0.30))
    lignes_min = int(params.get("lignes_min", 8))
    lignes_max = int(params.get("lignes_max", 25))
    part_min_fonds = float(params.get("part_min_etf_opcvm", 0.30))

    actifs = session.query(Actif).filter(Actif.eligible_pea.is_(True)).all()
    mix = _ajuster_horizon(MIX_PROFILS[demande.niveau_risque], demande.horizon_annees)

    # Poches triées par la métrique liée à l'objectif.
    poches: list[list[Actif]] = [[], [], []]
    for a in actifs:
        poches[_poche(a)].append(a)
    for p in poches:
        p.sort(key=lambda a: _metrique(a, demande.objectif), reverse=True)

    # Une poche cible vide voit son poids reversé à la poche cœur.
    poids_poches = [m / 100 for m in mix]
    for i in (0, 2):
        if poids_poches[i] > 0 and not poches[i]:
            poids_poches[1] += poids_poches[i]
            poids_poches[i] = 0.0

    # Nombre de lignes cible, proportionnel au capital.
    nb_lignes = max(lignes_min, min(lignes_max, int(demande.capital // 1500) or 1))
    nb_lignes = min(nb_lignes, sum(len(p) for p, w in zip(poches, poids_poches) if w > 0))

    lignes: list[LigneAllocation] = []
    poids_secteurs: dict[str, float] = {}

    for i, (poche, poids_poche) in enumerate(zip(poches, poids_poches)):
        if poids_poche <= 0 or not poche:
            continue
        # Assez de lignes pour que le plafond par ligne reste tenable
        # (ex. : poche à 80 % avec plafond 10 % → au moins 8 lignes).
        nb = max(1, round(nb_lignes * poids_poche), math.ceil(poids_poche / poids_max_ligne))
        nb = min(nb, len(poche))

        # Diversification par type : la poche cœur réserve une part minimale
        # aux fonds (ETF/OPCVM), classiquement le socle d'un portefeuille PEA.
        candidats = poche
        if i == 1 and part_min_fonds > 0:
            fonds = [a for a in poche if a.type != TypeActif.ACTION]
            actions_seules = [a for a in poche if a.type == TypeActif.ACTION]
            nb_fonds = min(len(fonds), math.ceil(nb * part_min_fonds))
            candidats = fonds[:nb_fonds] + actions_seules + fonds[nb_fonds:]

        selection: list[Actif] = []
        for a in candidats:
            secteur = a.secteur or "Divers"
            if poids_secteurs.get(secteur, 0.0) + poids_poche / max(nb, 1) > poids_max_secteur:
                continue  # contrainte sectorielle : on passe au candidat suivant
            selection.append(a)
            poids_secteurs[secteur] = poids_secteurs.get(secteur, 0.0) + poids_poche / max(nb, 1)
            if len(selection) >= nb:
                break

        if not selection:
            selection = poche[:nb]

        # Poids intra-poche proportionnels à la métrique, plafonnés par ligne.
        metriques = [max(_metrique(a, demande.objectif), 1.0) for a in selection]
        total_m = sum(metriques)
        poids_bruts = [poids_poche * m / total_m for m in metriques]
        exces = sum(max(0.0, p - poids_max_ligne) for p in poids_bruts)
        poids_final = [min(p, poids_max_ligne) for p in poids_bruts]
        # L'excédent au-delà du plafond est réparti uniformément sur les lignes non plafonnées.
        non_plafonnees = [j for j, p in enumerate(poids_bruts) if p < poids_max_ligne]
        for j in non_plafonnees:
            poids_final[j] += exces / len(non_plafonnees) if non_plafonnees else 0.0

        for a, p in zip(selection, poids_final):
            lignes.append(LigneAllocation(
                isin=a.isin,
                nom=a.nom,
                type=a.type.value if hasattr(a.type, "value") else str(a.type),
                secteur=a.secteur,
                poids=round(p, 4),
                montant=round(p * demande.capital, 2),
                score_global=a.score_global,
                niveau_risque=a.niveau_risque,
                justification=f"Poche {LIBELLES_POCHES[i]} — objectif {demande.objectif}, "
                              f"score {a.score_global or 0:.0f}/100",
            ))

    # Renormalisation finale (les arrondis et plafonds peuvent dévier de 100 %).
    total = sum(l.poids for l in lignes) or 1.0
    for l in lignes:
        l.poids = round(l.poids / total, 4)
        l.montant = round(l.poids * demande.capital, 2)

    repartition_types: dict[str, float] = {}
    for l in lignes:
        repartition_types[l.type] = round(repartition_types.get(l.type, 0.0) + l.poids, 4)

    commentaire = (
        f"Profil {demande.niveau_risque}/7, horizon {demande.horizon_annees} ans, objectif "
        f"« {demande.objectif} » : répartition cible défensive/cœur/dynamique = "
        f"{mix[0]}/{mix[1]}/{mix[2]} %. {len(lignes)} lignes proposées, plafond "
        f"{poids_max_ligne:.0%} par ligne et {poids_max_secteur:.0%} par secteur. "
        "Proposition indicative : ceci n'est pas un conseil en investissement."
    )

    return ReponseAllocation(
        capital=demande.capital,
        niveau_risque=demande.niveau_risque,
        horizon_annees=demande.horizon_annees,
        objectif=demande.objectif,
        repartition_types=repartition_types,
        lignes=sorted(lignes, key=lambda l: l.poids, reverse=True),
        commentaire=commentaire,
    )
