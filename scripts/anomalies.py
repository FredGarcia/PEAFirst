#!/usr/bin/env python3
"""Détection d'anomalies dans les données de marché et les scores.

Produit data/anomalies.csv.

Un indicateur spectaculaire est plus souvent le symptôme d'une donnée douteuse
que d'une opportunité : un Sharpe de 5 sur un titre échangé trois fois par mois
traduit une série de cours plate, pas une performance exceptionnelle. Ces règles
signalent les cas à examiner avant toute décision — elles ne disqualifient pas
un instrument, elles demandent une vérification.

Chaque anomalie porte une gravité :
  alerte    la valeur est probablement inexploitable en l'état
  attention la valeur est plausible mais mérite un contrôle

Usage :
  python3 scripts/anomalies.py
  python3 scripts/anomalies.py --seuil-fraicheur 7 --resume
"""
import argparse
import csv
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

COLONNES = ["ISIN", "Nom", "Type", "Anomalie", "Gravite", "Detail"]

# Fenêtre de collecte par défaut (400 jours) ; en dessous de ce nombre de
# séances, la série comporte trop de trous pour des indicateurs fiables.
SEANCES_ATTENDUES = 200


def lire(chemin):
    if not chemin.exists():
        return []
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


def age_jours(iso):
    if not iso:
        return None
    try:
        return (date.today() - datetime.strptime(iso[:10], "%Y-%m-%d").date()).days
    except ValueError:
        return None


def detecter(marche, scores, seuil_fraicheur):
    scores_idx = {r["ISIN"]: r for r in scores}
    trouvees = []

    def ajouter(ligne, nom_anomalie, gravite, detail):
        trouvees.append({
            "ISIN": ligne["ISIN"], "Nom": ligne.get("Nom", ""),
            "Type": ligne.get("Type", ""), "Anomalie": nom_anomalie,
            "Gravite": gravite, "Detail": detail,
        })

    for l in marche:
        vol = nombre(l.get("Volatilite_annualisee_pct"))
        sharpe = nombre(l.get("Sharpe"))
        dd = nombre(l.get("Drawdown_max_pct"))
        perf = nombre(l.get("Perf_periode_pct"))
        seances = nombre(l.get("Nb_seances"))
        age = age_jours(l.get("Date_cours"))

        # Série trop courte : tous les indicateurs qui en découlent sont fragiles.
        if seances is not None and seances < SEANCES_ATTENDUES:
            ajouter(l, "serie_courte", "alerte",
                    f"{int(seances)} séances seulement : indicateurs peu fiables")

        # Volatilité de niveau SRI 7 : fréquente sur les titres peu liquides,
        # où un carnet d'ordres mince fait bouger le cours sans flux réel.
        if vol is not None and vol > 80:
            ajouter(l, "volatilite_extreme", "alerte",
                    f"volatilité {vol:.0f} % (SRI 7) : liquidité à vérifier")
        elif vol is not None and vol < 3:
            # Une volatilité quasi nulle sur une action signale plus souvent un
            # cours figé qu'un titre exceptionnellement calme.
            ajouter(l, "volatilite_nulle", "alerte",
                    f"volatilité {vol:.1f} % : cours probablement figé")

        # Un Sharpe très élevé sur un an tient rarement à la seule qualité de
        # l'actif ; il vient souvent d'une volatilité sous-estimée.
        if sharpe is not None and abs(sharpe) > 3:
            ajouter(l, "sharpe_aberrant", "attention",
                    f"Sharpe {sharpe:.2f} : vérifier la régularité de la série")

        # Incohérence interne : un actif volatil qui n'a jamais reculé.
        if vol is not None and dd is not None and vol > 20 and abs(dd) < vol / 5:
            ajouter(l, "drawdown_incoherent", "alerte",
                    f"volatilité {vol:.0f} % mais drawdown {dd:.1f} % : "
                    "série probablement lacunaire")

        if perf is not None and abs(perf) > 200:
            ajouter(l, "performance_extreme", "attention",
                    f"performance {perf:.0f} % : vérifier split ou regroupement")

        if age is not None and age > seuil_fraicheur:
            ajouter(l, "cours_perime", "attention",
                    f"dernier cours il y a {age} jours")

        # Un score adossé à une part faible du barème n'est pas comparable aux
        # autres, même si sa valeur paraît élevée.
        s = scores_idx.get(l["ISIN"])
        if s:
            couv = nombre(s.get("Couverture_pct"))
            if couv is not None and couv < 50:
                ajouter(l, "couverture_faible", "attention",
                        f"score établi sur {couv:.0f} % du barème seulement")

    return trouvees


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seuil-fraicheur", type=int, default=7)
    p.add_argument("--resume", action="store_true", help="afficher la synthèse")
    p.add_argument("--data-dir", default="data")
    args = p.parse_args()

    data = Path(args.data_dir)
    marche = lire(data / "base_isin_marche.csv")
    if not marche:
        print("Aucune donnée de marché : lancer d'abord scripts/enrich_marche.py")
        return 0

    trouvees = detecter(marche, lire(data / "base_isin_scores.csv"),
                        args.seuil_fraicheur)
    sortie = data / "anomalies.csv"
    with open(sortie, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES, delimiter=";")
        w.writeheader()
        w.writerows(trouvees)

    touches = len({a["ISIN"] for a in trouvees})
    print(f"{sortie} : {len(trouvees)} anomalie(s) sur {touches} instrument(s) "
          f"({len(marche)} analysés)")
    if args.resume and trouvees:
        for (nom, gravite), n in Counter(
                (a["Anomalie"], a["Gravite"]) for a in trouvees).most_common():
            print(f"  {gravite:<9} {nom:<24} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
