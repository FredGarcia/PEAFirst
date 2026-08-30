#!/usr/bin/env python3
"""Moteur d'allocation de portefeuille.

Propose une répartition du capital selon les quatre entrées du cahier des
charges : capital, horizon, profil de risque (1 à 7) et objectif
(croissance, revenus, équilibré).

Le profil de risque suit les bornes de volatilité annualisée de la
réglementation PRIIPS (indicateur SRI), ce qui rend le niveau choisi
comparable à celui affiché sur les documents d'information des fonds :

  SRI 1 : < 0,5 %      SRI 5 : 20 – 30 %
  SRI 2 : 0,5 – 5 %    SRI 6 : 30 – 80 %
  SRI 3 : 5 – 12 %     SRI 7 : > 80 %
  SRI 4 : 12 – 20 %

Deux limites à connaître avant d'utiliser une allocation produite ici :

1. **Les corrélations ne sont pas modélisées.** La volatilité annoncée pour le
   portefeuille est la moyenne pondérée des volatilités individuelles. C'est
   une majoration : un portefeuille réellement diversifié aura une volatilité
   inférieure. Le chiffre sert à comparer des allocations entre elles, pas à
   prédire le risque réel.
2. **L'objectif « revenus » ne peut pas être servi correctement** faute de
   source gratuite sur les dividendes européens. Il est traité comme
   « équilibré » avec une préférence pour la faible volatilité, et le script
   le signale explicitement plutôt que de faire semblant.

Usage :
  python3 scripts/allocation.py --capital 10000 --risque 4 --horizon 8 \
      --objectif croissance
"""
import argparse
import csv
import sys
from pathlib import Path

# Bornes de volatilité annualisée (%) par niveau SRI, d'après PRIIPS.
BANDES_SRI = {
    1: (0.0, 0.5), 2: (0.5, 5.0), 3: (5.0, 12.0), 4: (12.0, 20.0),
    5: (20.0, 30.0), 6: (30.0, 80.0), 7: (80.0, 1000.0),
}

# Poids maximal d'une ligne, par niveau de risque : un profil prudent doit
# être plus dispersé qu'un profil offensif assumé.
PLAFOND_LIGNE = {1: 0.15, 2: 0.15, 3: 0.20, 4: 0.20, 5: 0.25, 6: 0.30, 7: 0.35}

# Nombre de lignes visé, pour éviter une concentration excessive.
MIN_LIGNES = 5


def lire_csv(chemin):
    with open(chemin, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def nombre(valeur):
    if valeur is None:
        return None
    texte = str(valeur).strip().replace(",", ".")
    if texte in ("", "-"):
        return None
    try:
        return float(texte)
    except ValueError:
        return None


def plafond_volatilite(risque, horizon):
    """Volatilité maximale admise, resserrée si l'horizon est court.

    Un horizon court laisse moins de temps pour absorber une baisse : on
    n'autorise pas le plein niveau de risque demandé si l'argent est engagé
    sur quelques années seulement.
    """
    haut = BANDES_SRI[risque][1]
    if horizon < 3:
        return min(haut, BANDES_SRI[max(1, risque - 2)][1])
    if horizon < 5:
        return min(haut, BANDES_SRI[max(1, risque - 1)][1])
    return haut


def selectionner(candidats, vol_max, objectif):
    """Filtre par volatilité, puis ordonne selon l'objectif."""
    retenus = [c for c in candidats
               if c["vol"] is not None and c["vol"] <= vol_max]

    if objectif == "croissance":
        # Priorité au score, qui intègre déjà performance et risque.
        retenus.sort(key=lambda c: -c["score"])
    elif objectif == "revenus":
        # Sans données de dividendes : à défaut, régularité (faible
        # volatilité, faible drawdown) à score correct.
        retenus.sort(key=lambda c: (c["vol"], -c["score"]))
    else:  # équilibré
        retenus.sort(key=lambda c: -(c["score"] - c["vol"] / 4))
    return retenus


def repartir(retenus, risque):
    """Poids proportionnels au score, plafonnés puis renormalisés.

    Le plafonnement est réappliqué en boucle : redistribuer l'excédent d'une
    ligne écrêtée peut faire dépasser le plafond à une autre.
    """
    plafond = PLAFOND_LIGNE[risque]
    poids = {}
    total_score = sum(max(c["score"], 1.0) for c in retenus)
    for c in retenus:
        poids[c["isin"]] = max(c["score"], 1.0) / total_score

    for _ in range(20):
        excedent = 0.0
        libres = []
        for isin, p in poids.items():
            if p > plafond:
                excedent += p - plafond
                poids[isin] = plafond
            else:
                libres.append(isin)
        if excedent <= 1e-9 or not libres:
            break
        base = sum(poids[i] for i in libres)
        if base <= 0:
            for i in libres:
                poids[i] += excedent / len(libres)
            break
        for i in libres:
            poids[i] += excedent * poids[i] / base
    return poids


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--capital", type=float, required=True, help="capital en euros")
    p.add_argument("--risque", type=int, required=True, choices=range(1, 8),
                   help="profil de risque, 1 (prudent) à 7 (offensif)")
    p.add_argument("--horizon", type=int, default=8, help="horizon en années")
    p.add_argument("--objectif", choices=["croissance", "revenus", "equilibre"],
                   default="equilibre")
    p.add_argument("--lignes", type=int, default=10,
                   help="nombre de lignes visé (défaut 10)")
    p.add_argument("--pea-uniquement", action="store_true",
                   help="ne retenir que les instruments éligibles PEA")
    p.add_argument("--data-dir", default="data")
    args = p.parse_args()

    data = Path(args.data_dir)
    chemin_scores = data / "base_isin_scores.csv"
    if not chemin_scores.exists():
        print(f"{chemin_scores} absent : lancer d'abord scripts/scoring.py")
        return 1

    scores = {r["ISIN"]: r for r in lire_csv(chemin_scores)}
    marche = {r["ISIN"]: r for r in lire_csv(data / "base_isin_marche.csv")}

    eligibles = None
    if args.pea_uniquement:
        eligibles = set()
        chemin_fonds = data / "base_isin_fonds_pea.csv"
        if chemin_fonds.exists():
            eligibles = {r["ISIN"] for r in lire_csv(chemin_fonds)
                         if r.get("PEA_eligible") == "OUI"}
        # Les actions passent par base_isin_actions_pea.csv : PEA_indicatif
        # repose sur le seul préfixe pays et retient des foncières et des bons
        # qui ne sont pas éligibles.
        chemin_actions = data / "base_isin_actions_pea.csv"
        if chemin_actions.exists():
            eligibles |= {r["ISIN"] for r in lire_csv(chemin_actions)
                          if r.get("PEA_eligible") == "OUI"}
        else:
            print("base_isin_actions_pea.csv absent : lancer "
                  "scripts/enrich_pea_actions.py pour une éligibilité fiable.")

    candidats = []
    for isin, s in scores.items():
        if eligibles is not None and isin not in eligibles:
            continue
        m = marche.get(isin, {})
        candidats.append({
            "isin": isin, "nom": s["Nom"], "type": s["Type"],
            "score": nombre(s["Score_global"]) or 0.0,
            "couverture": nombre(s["Couverture_pct"]) or 0.0,
            "vol": nombre(m.get("Volatilite_annualisee_pct")),
            "dd": nombre(m.get("Drawdown_max_pct")),
        })

    vol_max = plafond_volatilite(args.risque, args.horizon)
    retenus = selectionner(candidats, vol_max, args.objectif)[:args.lignes]

    print(f"Capital {args.capital:,.0f} € | risque {args.risque}/7 | "
          f"horizon {args.horizon} ans | objectif {args.objectif}".replace(",", " "))
    print(f"Volatilité maximale retenue : {vol_max:.1f} %"
          + (f" (resserrée pour un horizon de {args.horizon} ans)"
             if vol_max < BANDES_SRI[args.risque][1] else ""))
    print(f"Univers noté disponible : {len(candidats)} instrument(s), "
          f"{len(retenus)} retenu(s)\n")

    if not retenus:
        print("Aucun instrument ne respecte cette contrainte de volatilité.")
        print("Élargir l'univers noté (scripts/enrich_marche.py) ou relever "
              "le profil de risque.")
        return 0

    if args.objectif == "revenus":
        print("Objectif « revenus » : aucune source gratuite ne fournit les")
        print("dividendes européens. La sélection privilégie donc la régularité")
        print("(faible volatilité) et non le rendement distribué.\n")

    poids = repartir(retenus, args.risque)
    print(f"{'Poids':>7} {'Montant':>11}  {'Score':>6} {'Vol':>6}  Nom")
    vol_ponderee = 0.0
    for c in sorted(retenus, key=lambda x: -poids[x["isin"]]):
        w = poids[c["isin"]]
        vol_ponderee += w * (c["vol"] or 0.0)
        montant = f"{args.capital * w:,.0f} €".replace(",", " ")
        print(f"{w * 100:>6.1f}% {montant:>11}  {c['score']:>6.1f} "
              f"{c['vol']:>5.1f}%  {c['nom'][:34]}")

    print(f"\nVolatilité moyenne pondérée : {vol_ponderee:.1f} % "
          f"(majorant : la diversification n'est pas modélisée)")
    couverture = sum(c["couverture"] for c in retenus) / len(retenus)
    print(f"Couverture moyenne du barème de score : {couverture:.0f} %")
    if len(retenus) < MIN_LIGNES:
        print(f"Attention : {len(retenus)} ligne(s) seulement, la "
              f"diversification est insuffisante pour un portefeuille réel.")
    print("\nAide à la décision — ni conseil en investissement, ni conseil fiscal.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
