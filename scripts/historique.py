#!/usr/bin/env python3
"""Suivi de la progression de la collecte dans le temps.

Alimente data/historique_couverture.csv, une ligne par jour :
combien d'instruments sont collectés, notés, et sur quelle part du barème.

C'est l'indicateur de santé du projet : les scores ne valent que par l'étendue
et la fraîcheur des données qui les nourrissent. Une courbe qui stagne signale
un quota épuisé ou un workflow en échec, ce qu'aucun score ne montrerait.

Le mode --reconstruire relit l'historique Git des fichiers de données pour
amorcer la courbe avec des points réels plutôt que de la faire commencer
aujourd'hui. Il ne crée aucune donnée : il relit des états déjà commités.

Usage :
  python3 scripts/historique.py                 # ajoute le point du jour
  python3 scripts/historique.py --reconstruire  # amorce depuis l'historique Git
"""
import argparse
import csv
import io
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

COLONNES = ["Date", "Instruments", "Collectes", "Notes", "Couverture_moy_pct",
            "Score_moy", "Cours_perimes"]


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


def lire_texte_csv(texte):
    if not texte:
        return []
    return list(csv.DictReader(io.StringIO(texte), delimiter=";"))


def age_jours(iso, reference):
    if not iso:
        return None
    try:
        return (reference - datetime.strptime(iso[:10], "%Y-%m-%d").date()).days
    except ValueError:
        return None


def mesurer(base, marche, scores, jour, seuil):
    couvs = [nombre(r.get("Couverture_pct")) for r in scores]
    couvs = [c for c in couvs if c is not None]
    notes = [nombre(r.get("Score_global")) for r in scores]
    notes = [n for n in notes if n is not None]
    ages = [age_jours(r.get("Date_cours"), jour) for r in marche]
    perimes = sum(1 for a in ages if a is not None and a > seuil)
    return {
        "Date": jour.isoformat(),
        "Instruments": len(base),
        "Collectes": len(marche),
        "Notes": len(scores),
        "Couverture_moy_pct": round(sum(couvs) / len(couvs), 1) if couvs else 0,
        "Score_moy": round(sum(notes) / len(notes), 1) if notes else 0,
        "Cours_perimes": perimes,
    }


def git(args):
    try:
        r = subprocess.run(["git"] + args, capture_output=True, text=True, timeout=30)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def reconstruire(data, seuil):
    """Relit l'état des fichiers de données à chaque commit qui les a touchés."""
    chemins = [f"{data}/base_isin_marche.csv", f"{data}/base_isin_scores.csv"]
    sortie = git(["log", "--format=%H %ad", "--date=short", "--reverse", "--"] + chemins)
    points = {}
    for ligne in sortie.strip().splitlines():
        if not ligne.strip():
            continue
        sha, _, jour_txt = ligne.partition(" ")
        try:
            jour = datetime.strptime(jour_txt.strip(), "%Y-%m-%d").date()
        except ValueError:
            continue
        base = lire_texte_csv(git(["show", f"{sha}:{data}/base_isin.csv"]))
        marche = lire_texte_csv(git(["show", f"{sha}:{data}/base_isin_marche.csv"]))
        scores = lire_texte_csv(git(["show", f"{sha}:{data}/base_isin_scores.csv"]))
        if not base:
            continue
        # Un seul point par jour : le dernier état commité fait foi.
        points[jour.isoformat()] = mesurer(base, marche, scores, jour, seuil)
    return [points[k] for k in sorted(points)]


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reconstruire", action="store_true",
                   help="amorcer la courbe depuis l'historique Git")
    p.add_argument("--seuil-fraicheur", type=int, default=7)
    p.add_argument("--data-dir", default="data")
    args = p.parse_args()

    data = Path(args.data_dir)
    chemin = data / "historique_couverture.csv"

    existant = {}
    if chemin.exists():
        with open(chemin, encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter=";"):
                existant[r["Date"]] = r

    ajoutes = 0
    if args.reconstruire:
        for point in reconstruire(data, args.seuil_fraicheur):
            if point["Date"] not in existant:
                existant[point["Date"]] = point
                ajoutes += 1

    def lire_fichier(nom):
        chemin_f = data / nom
        if not chemin_f.exists():
            return []
        with open(chemin_f, encoding="utf-8") as f:
            return list(csv.DictReader(f, delimiter=";"))

    aujourdhui = mesurer(lire_fichier("base_isin.csv"),
                         lire_fichier("base_isin_marche.csv"),
                         lire_fichier("base_isin_scores.csv"),
                         date.today(), args.seuil_fraicheur)
    # Le point du jour est réécrit à chaque exécution : plusieurs collectes
    # peuvent avoir lieu dans la même journée.
    nouveau = aujourdhui["Date"] not in existant
    existant[aujourdhui["Date"]] = aujourdhui
    if nouveau:
        ajoutes += 1

    with open(chemin, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES, delimiter=";")
        w.writeheader()
        for cle in sorted(existant):
            w.writerow({c: existant[cle].get(c, "") for c in COLONNES})

    print(f"{chemin} : {len(existant)} point(s), {ajoutes} ajouté(s)")
    print(f"  aujourd'hui : {aujourdhui['Notes']} noté(s), "
          f"{aujourdhui['Collectes']} collecté(s), "
          f"couverture {aujourdhui['Couverture_moy_pct']} %")
    return 0


if __name__ == "__main__":
    sys.exit(main())
