#!/usr/bin/env python3
"""Croisement des listes d'éligibilité PEA publiées par les émetteurs.

Alimente data/pea_emetteurs.csv (la référence qui fait autorité pour
scripts/enrich_pea.py) à partir de fichiers téléchargés chez les émetteurs
ou distributeurs. Chaque entrée garde sa source et sa date de vérification.

Où trouver les listes (export CSV/Excel ou copier-coller des ISIN) :
  - Amundi ETF   : amundietf.fr → recherche produits → filtre « Éligible PEA »
  - iShares      : ishares.com/fr → screener → filtre PEA (gamme « Swap PEA »)
  - BNP Paribas  : easy.bnpparibas → liste des ETF, colonne éligibilité PEA
  - EasyBourse / justETF : listes consolidées d'ETF éligibles PEA

Formats acceptés en entrée : CSV (séparateur ; ou , — colonne ISIN détectée
par son intitulé ou son format) ou fichier texte avec un ISIN par ligne.

Usage :
  python3 scripts/maj_pea_emetteurs.py --merge amundi_pea.csv \\
      --emetteur "Amundi" --source "amundietf.fr filtre PEA 2026-08" \\
      [--eligible OUI] [--data-dir data]
  python3 scripts/maj_pea_emetteurs.py --check     # contrôle sans fusion

Les ISIN absents de la base fonds sont signalés et ignorés. Les entrées
existantes sont mises à jour (dernière source gagne). Relancer ensuite
scripts/enrich_pea.py puis scripts/validate_base.py.
"""
import argparse
import csv
import datetime
import re
import sys
from pathlib import Path

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")
COLONNES = ["ISIN", "Nom", "Emetteur", "PEA_eligible", "Source", "Date_verification"]


def lire_csv(chemin):
    with open(chemin, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def extraire_isins(chemin):
    """Extrait les couples (ISIN, nom éventuel) d'un fichier CSV ou texte."""
    texte = Path(chemin).read_text(encoding="utf-8-sig")
    lignes = [l for l in texte.splitlines() if l.strip()]
    resultat = []
    for ligne in lignes:
        champs = re.split(r"[;,\t]", ligne)
        isin, nom = "", ""
        for i, c in enumerate(champs):
            c = c.strip().strip('"')
            if ISIN_RE.match(c.upper()):
                isin = c.upper()
                autres = [x.strip().strip('"') for j, x in enumerate(champs) if j != i]
                nom = next((x for x in autres if x and not x.replace(".", "").isdigit()), "")
                break
        if isin:
            resultat.append((isin, nom))
    return resultat


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merge", help="fichier d'ISIN à fusionner")
    parser.add_argument("--emetteur", default="", help="nom de l'émetteur")
    parser.add_argument("--source", default="", help="provenance de la liste")
    parser.add_argument("--eligible", default="OUI", choices=["OUI", "NON"],
                        help="valeur d'éligibilité portée par la liste (défaut OUI)")
    parser.add_argument("--check", action="store_true",
                        help="contrôler pea_emetteurs.csv sans rien fusionner")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    data = Path(args.data_dir)

    fonds = {r["ISIN"]: r
             for r in lire_csv(data / "base_isin_etf.csv")
             + lire_csv(data / "base_isin_opcvm.csv")}
    chemin_ref = data / "pea_emetteurs.csv"
    reference = {r["ISIN"]: r for r in lire_csv(chemin_ref)} if chemin_ref.exists() else {}

    if args.check or not args.merge:
        absents = [i for i in reference if i not in fonds]
        print(f"pea_emetteurs.csv : {len(reference)} entrées, "
              f"{len(absents)} absentes de la base fonds")
        for i in absents:
            print(f"  absent : {i} ({reference[i]['Nom']})")
        return 1 if absents else 0

    if not args.source:
        parser.error("--source est obligatoire avec --merge (traçabilité)")

    entrees = extraire_isins(args.merge)
    if not entrees:
        print(f"Aucun ISIN reconnu dans {args.merge}")
        return 1
    aujourdhui = datetime.date.today().isoformat()
    ajouts, maj, ignores = 0, 0, []
    for isin, nom in entrees:
        if isin not in fonds:
            ignores.append(isin)
            continue
        existant = isin in reference
        reference[isin] = {
            "ISIN": isin,
            "Nom": nom or (reference.get(isin, {}).get("Nom") or fonds[isin]["Nom"]),
            "Emetteur": args.emetteur or reference.get(isin, {}).get("Emetteur", ""),
            "PEA_eligible": args.eligible,
            "Source": args.source,
            "Date_verification": aujourdhui,
        }
        maj += existant
        ajouts += not existant

    with open(chemin_ref, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES, delimiter=";")
        w.writeheader()
        for isin in sorted(reference):
            w.writerow(reference[isin])

    print(f"{chemin_ref} : {ajouts} ajout(s), {maj} mise(s) à jour, "
          f"{len(reference)} entrées au total")
    if ignores:
        print(f"{len(ignores)} ISIN hors base fonds ignorés : {ignores[:10]}"
              f"{'…' if len(ignores) > 10 else ''}")
    print("Relancer : python3 scripts/enrich_pea.py && python3 scripts/validate_base.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
