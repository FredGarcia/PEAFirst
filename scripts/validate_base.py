#!/usr/bin/env python3
"""Validation automatique de la base ISIN PEAFirst.

Contrôles :
  1. Format et checksum (Luhn) de chaque ISIN.
  2. Absence de doublons dans la base consolidée.
  3. Cohérence des sous-fichiers (actions/ETF/OPCVM) avec la base.
  4. Cohérence de PEA_indicatif avec la règle du préfixe pays EEE.
  5. Champs obligatoires non vides, colonnes attendues.
  6. Si présents : cohérence de data/pea_emetteurs.csv et du fichier enrichi
     data/base_isin_fonds_pea.csv avec la base.

Sortie : rapport sur stdout, code retour 0 si tout est valide, 1 sinon.

Usage : python3 scripts/validate_base.py [--data-dir data]
"""
import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

COLONNES = [
    "ISIN", "Nom", "Symbole", "Type", "Marché(s)", "Devise",
    "Pays_émission", "PEA_indicatif", "ESG_classification", "Source", "Date_MAJ",
]
TYPES_VALIDES = {"Action", "ETF", "OPCVM"}
# UE/EEE incluant NO, IS, LI (règle du README)
EEE = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE", "NO", "IS", "LI",
}
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")

erreurs = []


def erreur(msg):
    erreurs.append(msg)
    print(f"  ERREUR : {msg}")


def checksum_isin_valide(isin):
    """Contrôle Luhn de l'ISIN (lettres converties en base 36, le chiffre de
    contrôle n'est pas doublé)."""
    chiffres = "".join(str(int(c, 36)) for c in isin)
    total, doubler = 0, False
    for c in reversed(chiffres):
        d = int(c)
        if doubler:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        doubler = not doubler
    return total % 10 == 0


def lire_csv(chemin):
    with open(chemin, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def valider_lignes(nom_fichier, lignes):
    for r in lignes:
        isin = r.get("ISIN", "")
        if not ISIN_RE.match(isin):
            erreur(f"{nom_fichier} : format ISIN invalide « {isin} »")
        elif not checksum_isin_valide(isin):
            erreur(f"{nom_fichier} : checksum ISIN invalide « {isin} »")
        if r.get("Type") not in TYPES_VALIDES:
            erreur(f"{nom_fichier} : {isin} type inconnu « {r.get('Type')} »")
        for col in ("Nom", "Symbole", "Devise", "Pays_émission", "Source", "Date_MAJ"):
            if not (r.get(col) or "").strip():
                erreur(f"{nom_fichier} : {isin} champ « {col} » vide")
        if isin and r.get("Pays_émission") != isin[:2]:
            erreur(f"{nom_fichier} : {isin} Pays_émission « {r.get('Pays_émission')} » "
                   f"≠ préfixe ISIN « {isin[:2]} »")
        attendu = "OUI" if isin[:2] in EEE else "NON"
        if r.get("PEA_indicatif") != attendu:
            erreur(f"{nom_fichier} : {isin} PEA_indicatif « {r.get('PEA_indicatif')} » "
                   f"≠ règle EEE ({attendu})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data", help="répertoire des CSV")
    args = parser.parse_args()
    data = Path(args.data_dir)

    print("== Validation de la base consolidée ==")
    base = lire_csv(data / "base_isin.csv")
    entetes = list(base[0].keys()) if base else []
    if entetes != COLONNES:
        erreur(f"base_isin.csv : colonnes {entetes} ≠ attendues {COLONNES}")
    doublons = {k: v for k, v in Counter(r["ISIN"] for r in base).items() if v > 1}
    for isin, n in doublons.items():
        erreur(f"base_isin.csv : ISIN en double « {isin} » ({n} occurrences)")
    valider_lignes("base_isin.csv", base)
    print(f"  {len(base)} lignes contrôlées")

    print("== Cohérence des sous-fichiers ==")
    index_base = {r["ISIN"]: r for r in base}
    compte_types = Counter(r["Type"] for r in base)
    for fichier, type_attendu in [
        ("base_isin_actions.csv", "Action"),
        ("base_isin_etf.csv", "ETF"),
        ("base_isin_opcvm.csv", "OPCVM"),
    ]:
        lignes = lire_csv(data / fichier)
        for r in lignes:
            ref = index_base.get(r["ISIN"])
            if ref is None:
                erreur(f"{fichier} : {r['ISIN']} absent de base_isin.csv")
            elif r != ref:
                erreur(f"{fichier} : {r['ISIN']} diffère de la ligne de base_isin.csv")
            if r.get("Type") != type_attendu:
                erreur(f"{fichier} : {r['ISIN']} type « {r.get('Type')} » ≠ {type_attendu}")
        if len(lignes) != compte_types[type_attendu]:
            erreur(f"{fichier} : {len(lignes)} lignes ≠ {compte_types[type_attendu]} "
                   f"« {type_attendu} » dans la base")
        print(f"  {fichier} : {len(lignes)} lignes contrôlées")

    overlay = data / "pea_emetteurs.csv"
    if overlay.exists():
        print("== Cohérence de pea_emetteurs.csv ==")
        lignes = lire_csv(overlay)
        for r in lignes:
            if r["ISIN"] not in index_base:
                erreur(f"pea_emetteurs.csv : {r['ISIN']} absent de base_isin.csv")
            elif index_base[r["ISIN"]]["Type"] not in ("ETF", "OPCVM"):
                erreur(f"pea_emetteurs.csv : {r['ISIN']} n'est pas un fonds "
                       f"({index_base[r['ISIN']]['Type']})")
            if r.get("PEA_eligible") not in ("OUI", "NON"):
                erreur(f"pea_emetteurs.csv : {r['ISIN']} PEA_eligible "
                       f"« {r.get('PEA_eligible')} » (attendu OUI ou NON)")
            if not (r.get("Source") or "").strip():
                erreur(f"pea_emetteurs.csv : {r['ISIN']} sans Source")
        dbl = {k: v for k, v in Counter(r["ISIN"] for r in lignes).items() if v > 1}
        for isin in dbl:
            erreur(f"pea_emetteurs.csv : ISIN en double « {isin} »")
        print(f"  {len(lignes)} lignes contrôlées")

    enrichi = data / "base_isin_fonds_pea.csv"
    if enrichi.exists():
        print("== Cohérence de base_isin_fonds_pea.csv ==")
        lignes = lire_csv(enrichi)
        fonds_base = {i for i, r in index_base.items() if r["Type"] in ("ETF", "OPCVM")}
        vus = set()
        for r in lignes:
            vus.add(r["ISIN"])
            if r["ISIN"] not in fonds_base:
                erreur(f"base_isin_fonds_pea.csv : {r['ISIN']} n'est pas un fonds de la base")
            if r.get("PEA_eligible") not in ("OUI", "PROBABLE", "NON", "A_VERIFIER"):
                erreur(f"base_isin_fonds_pea.csv : {r['ISIN']} PEA_eligible "
                       f"« {r.get('PEA_eligible')} » invalide")
        manquants = fonds_base - vus
        if manquants:
            erreur(f"base_isin_fonds_pea.csv : {len(manquants)} fonds de la base absents "
                   f"(ex. {sorted(manquants)[:3]})")
        print(f"  {len(lignes)} lignes contrôlées")

    print()
    if erreurs:
        print(f"ÉCHEC : {len(erreurs)} erreur(s).")
        return 1
    print("OK : tous les contrôles passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
