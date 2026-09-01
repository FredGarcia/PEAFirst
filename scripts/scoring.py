#!/usr/bin/env python3
"""Moteur de score propriétaire, pondéré et paramétrable.

Calcule un score sur 100 par instrument à partir des critères disponibles,
selon l'architecture du cahier des charges. Les pondérations sont lues dans
data/scoring_params.json et modifiables sans toucher au code.

Principe directeur : **ne jamais inventer une note absente**. Un critère sans
donnée n'est pas remplacé par une valeur neutre — il est retiré du calcul et
les pondérations restantes sont renormalisées. La colonne `Couverture_pct`
indique quelle part du barème a réellement pu être évaluée : un score à 82
couvert à 30 % n'a pas la même valeur qu'un score à 82 couvert à 90 %, et le
tableau de bord doit pouvoir faire la différence.

Normalisation : rang percentile au sein de la population comparable (même
`Type`), ce qui évite qu'une valeur extrême écrase l'échelle, contrairement à
un min-max. Un critère est ignoré si sa population comparable est trop petite
pour que le rang ait un sens (< 5 instruments notés).

Critères actuellement alimentables (août 2026, sources gratuites) :
  performance, volatilité, Sharpe, Sortino, drawdown   -> scripts/enrich_marche.py
  ESG (classification SFDR art. 8/9, ETF seulement)    -> base Euronext
Critères prévus par le CDC mais sans source gratuite en Europe :
  potentiel, valorisation (PER), croissance, dividende, consensus analystes
Ils sont déjà déclarés dans les pondérations : le jour où une source les
alimente, ils entrent dans le score sans modification du code.

Usage :
  python3 scripts/scoring.py                    # score tout l'univers noté
  python3 scripts/scoring.py --type ETF         # restreindre à un type
  python3 scripts/scoring.py --min-couverture 50
  python3 scripts/scoring.py --top 20           # afficher le classement
"""
import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

# Critère -> (clé dans les données, sens). sens=+1 : plus c'est haut, mieux
# c'est ; sens=-1 : plus c'est bas, mieux c'est.
CRITERES = {
    "performance":  ("Perf_periode_pct", +1),
    "volatilite":   ("Volatilite_annualisee_pct", -1),
    "sharpe":       ("Sharpe", +1),
    "sortino":      ("Sortino", +1),
    "drawdown":     ("Drawdown_max_pct", +1),  # valeur négative : -5% > -40%
    "esg":          ("_esg", +1),
    # Alimentés par scripts/enrich_potentiel.py, quand ce fichier existe.
    "potentiel":    ("Potentiel_pct", +1),
    "valorisation": ("PER", -1),          # un PER bas est mieux noté
    "dividende":    ("Rendement_pct", +1),
    "consensus":    ("Consensus", +1),
    # Aucune source ne fournit de donnée de croissance : le critère reste
    # déclaré, son poids renormalisé plutôt qu'attribué par défaut.
    "croissance":   ("_croissance", +1),
}

PONDERATIONS_DEFAUT = {
    "_commentaire": ("Pondérations du score sur 100. Un critère sans donnée est "
                     "retiré et les autres sont renormalisés ; son poids n'est "
                     "jamais attribué par défaut."),
    "performance": 20,
    "sharpe": 15,
    "volatilite": 10,
    "drawdown": 10,
    "sortino": 5,
    "esg": 10,
    "potentiel": 10,
    "valorisation": 6,
    "croissance": 6,
    "dividende": 4,
    "consensus": 4,
}

# Classification SFDR : l'article 9 est plus exigeant que l'article 8.
ECHELLE_ESG = {"ESG ETF art. 9": 1.0, "ESG ETF art. 8": 0.6}

MIN_POPULATION = 5
# Un score global n'a de sens que s'il agrège plusieurs critères couvrant une
# part significative du barème. En deçà, on produirait un chiffre d'apparence
# globale reposant en fait sur un seul angle (un ETF noté sur le seul ESG
# ressortirait à 95/100). Ces instruments sont écartés, pas notés à zéro.
MIN_CRITERES = 2
MIN_COUVERTURE_DEFAUT = 30.0
COLONNES = ["ISIN", "Nom", "Type", "Score_global", "Couverture_pct",
            "Criteres_notes", "Rang", "Date_MAJ"]


def lire_csv(chemin):
    with open(chemin, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def nombre(valeur):
    """Convertit en float, ou None si la donnée est absente/illisible."""
    if valeur is None:
        return None
    texte = str(valeur).strip().replace(",", ".")
    if texte in ("", "-", "n/a", "N/A"):
        return None
    try:
        return float(texte)
    except ValueError:
        return None


def charger_ponderations(chemin):
    if chemin.exists():
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
        inconnus = [k for k in donnees
                    if not k.startswith("_") and k not in CRITERES]
        if inconnus:
            print(f"Pondérations ignorées (critères inconnus) : {inconnus}")
        return donnees
    chemin.write_text(json.dumps(PONDERATIONS_DEFAUT, indent=2, ensure_ascii=False),
                      encoding="utf-8")
    print(f"{chemin} créé avec les pondérations par défaut.")
    return PONDERATIONS_DEFAUT


def rangs_percentiles(valeurs):
    """Rang percentile dans [0, 1], moyenné sur les ex aequo.

    Le rang est préféré au min-max : une valeur aberrante (un Sharpe de 12 sur
    un titre illiquide) ne comprime pas l'échelle de tous les autres.
    """
    n = len(valeurs)
    if n < 2:
        return {v: 0.5 for v in valeurs}
    tries = sorted(valeurs)
    rangs = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and tries[j + 1] == tries[i]:
            j += 1
        # Rang moyen des ex aequo, ramené dans [0, 1].
        moyen = (i + j) / 2
        rangs[tries[i]] = moyen / (n - 1)
        i = j + 1
    return rangs


def collecter_donnees(base, marche, fondamentaux=()):
    """Fusionne base, données de marché et fondamentaux en ISIN -> valeurs."""
    par_isin = {}
    for r in base:
        par_isin[r["ISIN"]] = {
            "Nom": r["Nom"], "Type": r["Type"],
            "_esg": ECHELLE_ESG.get((r.get("ESG_classification") or "").strip()),
        }
    # Note ESG des fondamentaux. Deux échelles coexistent : la classification
    # SFDR (article 8/9, propre aux fonds) et la note du fournisseur (0-100,
    # relevée sur les actions). Les mélanger dans un même classement serait
    # faux — une échelle écraserait l'autre. Ce n'est pas le cas ici parce que
    # le rang percentile est calculé **par Type** et que les deux populations
    # sont disjointes : SFDR pour les ETF, note fournisseur pour les actions.
    # Si une même population venait à porter les deux, il faudrait trancher.
    for r in fondamentaux:
        note = nombre(r.get("Score_ESG"))
        if note is None:
            continue
        entree = par_isin.setdefault(r["ISIN"], {"Nom": r.get("Nom", ""),
                                                 "Type": r.get("Type", "")})
        if entree.get("_esg") is None:
            entree["_esg"] = note

    for source in (marche, fondamentaux):
        for r in source:
            entree = par_isin.setdefault(r["ISIN"], {"Nom": r.get("Nom", ""),
                                                     "Type": r.get("Type", "")})
            for critere, (cle, _) in CRITERES.items():
                if cle.startswith("_"):
                    continue
                valeur = nombre(r.get(cle))
                if valeur is not None:
                    entree[cle] = valeur
    return par_isin


def calculer(par_isin, ponderations):
    """Calcule les sous-notes puis le score global, par population comparable."""
    poids = {k: float(v) for k, v in ponderations.items()
             if not k.startswith("_") and k in CRITERES and float(v) > 0}

    # Les rangs se calculent au sein d'un même Type : comparer la volatilité
    # d'un ETF à celle d'une small cap n'aurait pas de sens.
    types = {}
    for isin, d in par_isin.items():
        types.setdefault(d.get("Type", ""), []).append(isin)

    notes = {isin: {} for isin in par_isin}
    for _type, isins in types.items():
        for critere, (cle, sens) in CRITERES.items():
            if critere not in poids:
                continue
            valeurs = {i: par_isin[i][cle] for i in isins
                       if par_isin[i].get(cle) is not None}
            if len(valeurs) < MIN_POPULATION:
                continue  # population trop mince : le rang ne signifie rien
            rangs = rangs_percentiles(list(valeurs.values()))
            for isin, v in valeurs.items():
                r = rangs[v]
                notes[isin][critere] = (r if sens > 0 else 1 - r) * 100

    resultats = []
    for isin, d in par_isin.items():
        note = notes[isin]
        if not note:
            continue
        if len(note) < MIN_CRITERES:
            continue
        poids_dispo = sum(poids[c] for c in note)
        poids_total = sum(poids.values())
        score = sum(note[c] * poids[c] for c in note) / poids_dispo
        resultats.append({
            "ISIN": isin,
            "Nom": d.get("Nom", ""),
            "Type": d.get("Type", ""),
            "Score_global": round(score, 1),
            "Couverture_pct": round(100 * poids_dispo / poids_total, 1),
            "Criteres_notes": "|".join(sorted(note)),
        })
    return resultats


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--type", help="restreindre à un type (Action, ETF, OPCVM)")
    p.add_argument("--min-couverture", type=float, default=MIN_COUVERTURE_DEFAUT,
                   help=f"couverture minimale du barème en %% (défaut "
                        f"{MIN_COUVERTURE_DEFAUT:.0f} ; 0 pour tout conserver)")
    p.add_argument("--top", type=int, default=0, help="afficher les N meilleurs")
    p.add_argument("--data-dir", default="data")
    args = p.parse_args()

    data = Path(args.data_dir)
    chemin_marche = data / "base_isin_marche.csv"
    if not chemin_marche.exists():
        print(f"{chemin_marche} absent : lancer d'abord scripts/enrich_marche.py")
        return 1

    base = lire_csv(data / "base_isin.csv")
    marche = lire_csv(chemin_marche)
    chemin_fonda = data / "base_isin_potentiel.csv"
    fondamentaux = lire_csv(chemin_fonda) if chemin_fonda.exists() else []
    ponderations = charger_ponderations(data / "scoring_params.json")

    par_isin = collecter_donnees(base, marche, fondamentaux)
    if fondamentaux:
        print(f"{chemin_fonda.name} : {len(fondamentaux)} instrument(s) "
              "avec fondamentaux")
    if args.type:
        par_isin = {i: d for i, d in par_isin.items() if d.get("Type") == args.type}

    resultats = calculer(par_isin, ponderations)
    resultats = [r for r in resultats if r["Couverture_pct"] >= args.min_couverture]
    resultats.sort(key=lambda r: -r["Score_global"])
    for rang, r in enumerate(resultats, 1):
        r["Rang"] = rang
        r["Date_MAJ"] = date.today().isoformat()

    sortie = data / "base_isin_scores.csv"
    with open(sortie, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES, delimiter=";")
        w.writeheader()
        w.writerows(resultats)
    print(f"{sortie} : {len(resultats)} instrument(s) notés "
          f"(seuils : >= {MIN_CRITERES} critères, couverture >= "
          f"{args.min_couverture:.0f} %)")
    ecartes = len(par_isin) - len(resultats)
    if ecartes > 0:
        print(f"{ecartes} instrument(s) écartés faute de données suffisantes.")

    if resultats:
        couverture = sum(r["Couverture_pct"] for r in resultats) / len(resultats)
        print(f"Couverture moyenne du barème : {couverture:.1f} %")
        if couverture < 60:
            print("Attention : la majorité du barème n'est pas alimentée. "
                  "Ces scores classent sur le risque et la performance passée, "
                  "pas sur la valorisation ni les perspectives.")
    if args.top:
        print(f"\n{'Rg':>3} {'Score':>6} {'Couv.':>6}  {'Type':<7} Nom")
        for r in resultats[:args.top]:
            print(f"{r['Rang']:>3} {r['Score_global']:>6} "
                  f"{r['Couverture_pct']:>5}%  {r['Type']:<7} {r['Nom'][:38]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
