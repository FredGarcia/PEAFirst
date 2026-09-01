#!/usr/bin/env python3
"""Collecte persistante du potentiel et des données fondamentales.

Alimente data/base_isin_potentiel.csv avec les critères que l'historique de
cours ne permet pas de calculer : potentiel, objectif de cours, consensus
d'analystes, PER, rendement, note ESG et secteur.

Pourquoi passer par l'application
----------------------------------
La chaîne `scripts/` n'a aucune dépendance externe, et ce script ne fait pas
exception : il n'utilise que la bibliothèque standard. Le scraping lui-même est
réalisé par l'application PEAdvisor, dont le code est testé, plutôt que
réécrit ici. Ce script pilote son API et versionne le résultat.

L'application doit donc tourner :

    python run.py          # dans un autre terminal
    python3 scripts/enrich_potentiel.py --filtre pea --limite 50

Précautions
-----------
Chaque valeur demande une requête au site interrogé. Le script espace donc les
appels (`--pause`, 2 secondes par défaut), reprend où il s'est arrêté grâce au
fichier produit, et se limite par défaut à un petit lot. Interroger des
milliers de fiches d'affilée serait à la fois discourtois et fragile.

Le scraping de Boursorama se heurte à ses conditions d'utilisation, qui
interdisent l'extraction automatisée, et à la licence Euronext sur les cours.
C'est un choix qui vous appartient ; le script ne le dissimule pas.

Ce que la source ne fournit pas
-------------------------------
Aucune donnée de croissance : la colonne correspondante du barème reste vide,
et son poids continue d'être renormalisé plutôt qu'attribué par défaut.

Usage :
  python3 scripts/enrich_potentiel.py --etat
  python3 scripts/enrich_potentiel.py --filtre pea --limite 30
  python3 scripts/enrich_potentiel.py --isins FR0000120073,FR0000120966
"""
import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

COLONNES = ["ISIN", "Nom", "Potentiel_pct", "Objectif_cours", "Consensus",
            "PER", "Rendement_pct", "Score_ESG", "Secteur", "Capitalisation",
            "Source", "Date_MAJ"]

# Champ de la réponse -> colonne du fichier.
CHAMPS = {
    "potentiel": "Potentiel_pct",
    "objectif_cours": "Objectif_cours",
    "consensus": "Consensus",
    "per": "PER",
    "rendement": "Rendement_pct",
    "score_esg": "Score_ESG",
    "secteur": "Secteur",
    "capitalisation": "Capitalisation",
}


def lire(chemin):
    if not chemin.exists():
        return []
    with open(chemin, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def appel(url, methode="GET", delai=60):
    requete = urllib.request.Request(url, method=methode)
    try:
        with urllib.request.urlopen(requete, timeout=delai) as r:
            return json.load(r), None
    except urllib.error.HTTPError as e:
        corps = e.read().decode(errors="replace")[:160]
        return None, f"HTTP {e.code} {corps}"
    except urllib.error.URLError as e:
        return None, f"injoignable ({e.reason})"
    except Exception as e:  # JSON tronqué, délai dépassé…
        return None, type(e).__name__


def univers(data, filtre):
    base = lire(data / "base_isin.csv")
    if filtre == "tout":
        return base
    if filtre in ("actions", "etf"):
        vise = "Action" if filtre == "actions" else "ETF"
        return [r for r in base if r["Type"] == vise]

    # « pea » : uniquement les instruments dont l'éligibilité est confirmée.
    eligibles = set()
    for nom in ("base_isin_actions_pea.csv", "base_isin_fonds_pea.csv"):
        eligibles |= {r["ISIN"] for r in lire(data / nom)
                      if r.get("PEA_eligible") == "OUI"}
    return [r for r in base if r["ISIN"] in eligibles]


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--api", default="http://localhost:8000",
                   help="adresse de l'application (défaut http://localhost:8000)")
    p.add_argument("--source", default="boursorama",
                   help="site interrogé (défaut boursorama, seul validé)")
    p.add_argument("--filtre", choices=["pea", "actions", "etf", "tout"],
                   default="pea", help="univers visé (défaut pea)")
    p.add_argument("--isins", default="", help="liste d'ISIN séparés par des virgules")
    p.add_argument("--limite", type=int, default=25,
                   help="nombre maximal de valeurs par exécution (défaut 25)")
    p.add_argument("--pause", type=float, default=2.0,
                   help="délai entre deux appels, en secondes (défaut 2)")
    p.add_argument("--forcer", action="store_true",
                   help="réinterroger les valeurs déjà collectées")
    p.add_argument("--etat", action="store_true",
                   help="avancement, sans aucun appel")
    p.add_argument("--data-dir", default="data")
    args = p.parse_args()

    data = Path(args.data_dir)
    sortie = data / "base_isin_potentiel.csv"
    acquis = {r["ISIN"]: r for r in lire(sortie)}

    if args.isins:
        cibles_isin = [i.strip() for i in args.isins.split(",") if i.strip()]
        noms = {r["ISIN"]: r["Nom"] for r in lire(data / "base_isin.csv")}
        cibles = [{"ISIN": i, "Nom": noms.get(i, "")} for i in cibles_isin]
    else:
        cibles = univers(data, args.filtre)

    restants = [r for r in cibles if args.forcer or r["ISIN"] not in acquis]

    if args.etat or not cibles:
        avec_potentiel = sum(1 for r in acquis.values() if r.get("Potentiel_pct"))
        print(f"Univers « {args.filtre} » : {len(cibles)} instrument(s)")
        print(f"  déjà collectés     : {len(acquis)}")
        print(f"  dont avec potentiel: {avec_potentiel}")
        print(f"  restants           : {len(restants)}")
        if sortie.exists():
            print(f"  {sortie}")
        return 0

    lot = restants[:args.limite]
    if not lot:
        print("Rien à collecter : tout est déjà acquis (--forcer pour refaire).")
        return 0

    # L'application doit répondre avant d'entamer le lot : mieux vaut échouer
    # tout de suite qu'après une série d'erreurs identiques.
    base_api = args.api.rstrip("/")
    _, erreur = appel(f"{base_api}/api/meta/sante", delai=10)
    if erreur:
        print(f"Application injoignable sur {base_api} : {erreur}")
        print("La lancer dans un autre terminal : python run.py")
        return 1

    print(f"{len(lot)} valeur(s) à interroger via {args.source} "
          f"(pause {args.pause}s entre les appels)")
    ajouts = sans_potentiel = echecs = 0
    for n, r in enumerate(lot, 1):
        isin = r["ISIN"]
        url = (f"{base_api}/api/import/web/{args.source}/"
               f"{urllib.parse.quote(isin, safe='')}")
        reponse, erreur = appel(url, methode="POST")
        if erreur:
            echecs += 1
            print(f"  {n}/{len(lot)} {isin} : {erreur}")
        else:
            extrait = (reponse or {}).get("donnees_extraites") or {}
            ligne = {"ISIN": isin,
                     "Nom": reponse.get("nom") or r.get("Nom", ""),
                     "Source": args.source,
                     "Date_MAJ": date.today().isoformat()}
            for champ, colonne in CHAMPS.items():
                valeur = extrait.get(champ)
                ligne[colonne] = "" if valeur is None else valeur
            acquis[isin] = ligne
            if ligne.get("Potentiel_pct") not in ("", None):
                ajouts += 1
                print(f"  {n}/{len(lot)} {isin} : potentiel "
                      f"{ligne['Potentiel_pct']} %")
            else:
                sans_potentiel += 1
                # Fréquent sur les petites capitalisations : aucun analyste ne
                # les suit, il n'y a donc pas d'objectif de cours à relever.
                print(f"  {n}/{len(lot)} {isin} : aucun potentiel publié")

        # Écriture après chaque valeur : une interruption ne perd rien.
        with open(sortie, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLONNES, delimiter=";")
            w.writeheader()
            for cle in sorted(acquis):
                w.writerow({c: acquis[cle].get(c, "") for c in COLONNES})

        if n < len(lot):
            time.sleep(args.pause)

    print(f"\n{sortie} : {len(acquis)} instrument(s) au total")
    print(f"  {ajouts} potentiel(s) relevé(s), {sans_potentiel} sans potentiel "
          f"publié, {echecs} échec(s)")
    reste = len(restants) - len(lot)
    if reste > 0:
        print(f"Reste {reste} valeur(s) : relancer le script.")
    print("\nRelancer ensuite scripts/scoring.py pour que ces critères entrent "
          "dans le score.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
