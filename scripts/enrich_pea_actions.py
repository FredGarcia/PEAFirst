#!/usr/bin/env python3
"""Éligibilité PEA des actions.

Produit data/base_isin_actions_pea.csv, pendant de base_isin_fonds_pea.csv
pour les actions.

Pourquoi ce fichier existe
--------------------------
La colonne `PEA_indicatif` de la base repose sur le seul préfixe pays de l'ISIN.
C'est une approximation grossière : elle classe « OUI » des titres qui ne sont
pas éligibles, notamment les foncières cotées et les bons de souscription. Un
tel faux positif n'est pas anodin — loger un titre inéligible dans un PEA
expose à la clôture du plan.

Règles appliquées, par priorité décroissante
--------------------------------------------
1. **Correction utilisateur** (`data/corrections_pea.csv`) — fait toujours foi.
2. **Régime foncier** : les SIIC ne sont plus éligibles au PEA depuis le
   21 octobre 2011, et il en va de même des régimes européens équivalents
   (Sicafi/SIR belge, SOCIMI espagnol, FBI néerlandais, SIIQ italien, G-REIT
   allemand, UK-REIT). OpenFIGI les identifie par `Type_instrument = REIT`.
3. **Nature de l'instrument** : les bons et droits de souscription ne sont pas
   éligibles.
4. **Pays d'émission hors EEE**.
5. **Nature incertaine** : certificats néerlandais, actions d'épargne
   italiennes, actions de préférence, parts et certificats divers sont classés
   `A_VERIFIER` plutôt que supposés éligibles — leur traitement dépend du titre.
6. Action ordinaire émise dans l'EEE : `OUI`.

Le classement par `Type_instrument` dépend de la couverture OpenFIGI : une
action sans identifiant reste `A_VERIFIER` faute d'information sur sa nature.

Usage :
  python3 scripts/enrich_pea_actions.py
  python3 scripts/enrich_pea_actions.py --resume
"""
import argparse
import csv
import sys
from collections import Counter
from datetime import date
from pathlib import Path

EEE = {"FR", "DE", "IT", "ES", "NL", "BE", "PT", "LU", "IE", "AT", "FI", "GR",
       "SE", "DK", "PL", "CZ", "HU", "SK", "SI", "EE", "LV", "LT", "RO", "BG",
       "HR", "CY", "MT", "NO", "IS", "LI"}

# Types OpenFIGI exclus, avec le motif retenu.
EXCLUS = {
    "REIT": ("REGIME_FONCIER",
             "foncière cotée (SIIC ou régime européen équivalent) : "
             "exclue du PEA depuis le 21 octobre 2011"),
    "Equity WRT": ("TYPE_INSTRUMENT",
                   "bon ou droit de souscription : non éligible au PEA"),
    "Right": ("TYPE_INSTRUMENT",
              "droit d'attribution ou de souscription : non éligible au PEA"),
}

# Types dont l'éligibilité dépend du titre : ne rien supposer.
INCERTAINS = {
    "Preference": "action de préférence : vérifier le prospectus",
    "Dutch Cert": "certificat néerlandais : vérifier le titre sous-jacent",
    "Savings Share": "action d'épargne italienne : vérifier le statut",
    "Receipt": "certificat représentatif : vérifier le titre sous-jacent",
    "Closed-End Fund": "fonds fermé coté : vérifier la politique d'investissement",
    "Unit": "part composite : vérifier la composition",
}

COLONNES = ["ISIN", "Nom", "Symbole", "Marché(s)", "Devise", "Pays_émission",
            "Type_instrument", "PEA_eligible", "PEA_methode", "PEA_source",
            "Date_MAJ"]

CORRECTIONS_ENTETE = ["ISIN", "PEA_eligible", "Motif", "Source", "Date"]


def lire(chemin):
    if not chemin.exists():
        return []
    with open(chemin, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def charger_corrections(chemin):
    """Corrections saisies par l'utilisateur. Elles priment sur toute règle."""
    corrections = {}
    for r in lire(chemin):
        isin = (r.get("ISIN") or "").strip()
        valeur = (r.get("PEA_eligible") or "").strip().upper()
        if not isin or valeur not in ("OUI", "NON", "A_VERIFIER"):
            continue
        corrections[isin] = {
            "valeur": valeur,
            "motif": (r.get("Motif") or "").strip() or "correction manuelle",
            "source": (r.get("Source") or "").strip() or "saisie utilisateur",
        }
    return corrections


def classer(action, type_figi, corrections):
    isin = action["ISIN"]
    if isin in corrections:
        c = corrections[isin]
        return c["valeur"], "CORRECTION_UTILISATEUR", f"{c['motif']} — {c['source']}"

    if type_figi in EXCLUS:
        methode, motif = EXCLUS[type_figi]
        return "NON", methode, motif

    if action.get("Pays_émission") not in EEE:
        return "NON", "HORS_EEE", (
            f"émetteur hors EEE ({action.get('Pays_émission')}) : "
            "hors du champ du PEA")

    if type_figi in INCERTAINS:
        return "A_VERIFIER", "TYPE_INCERTAIN", INCERTAINS[type_figi]

    if not type_figi:
        return "A_VERIFIER", "NATURE_INCONNUE", (
            "nature de l'instrument non identifiée par OpenFIGI")

    return "OUI", "ACTION_EEE", (
        f"action ordinaire ({type_figi}) émise dans l'EEE")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--resume", action="store_true", help="afficher la synthèse")
    p.add_argument("--data-dir", default="data")
    args = p.parse_args()

    data = Path(args.data_dir)
    base = lire(data / "base_isin.csv")
    if not base:
        print(f"{data}/base_isin.csv absent.")
        return 1
    figi = {r["ISIN"]: (r.get("Type_instrument") or "").strip()
            for r in lire(data / "base_isin_figi.csv")}
    chemin_corr = data / "corrections_pea.csv"
    corrections = charger_corrections(chemin_corr)

    # Un fichier de corrections vide sert de gabarit à l'utilisateur.
    if not chemin_corr.exists():
        with open(chemin_corr, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(CORRECTIONS_ENTETE)
        print(f"{chemin_corr} créé (vide) : y déposer les corrections.")

    actions = [r for r in base if r["Type"] == "Action"]
    aujourdhui = date.today().isoformat()
    lignes = []
    for a in actions:
        type_figi = figi.get(a["ISIN"], "")
        valeur, methode, motif = classer(a, type_figi, corrections)
        lignes.append({
            "ISIN": a["ISIN"], "Nom": a["Nom"], "Symbole": a["Symbole"],
            "Marché(s)": a["Marché(s)"], "Devise": a["Devise"],
            "Pays_émission": a["Pays_émission"], "Type_instrument": type_figi,
            "PEA_eligible": valeur, "PEA_methode": methode,
            "PEA_source": motif, "Date_MAJ": aujourdhui,
        })

    sortie = data / "base_isin_actions_pea.csv"
    with open(sortie, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES, delimiter=";")
        w.writeheader()
        w.writerows(lignes)

    compte = Counter(l["PEA_eligible"] for l in lignes)
    print(f"{sortie} : {len(lignes)} action(s)")
    print(f"  Bilan : " + ", ".join(f"{k}={v}" for k, v in sorted(compte.items())))
    appliquees = sum(1 for l in lignes if l["PEA_methode"] == "CORRECTION_UTILISATEUR")
    inconnues = [i for i in corrections if i not in {l["ISIN"] for l in lignes}]
    if appliquees:
        print(f"  {appliquees} correction(s) utilisateur appliquée(s)")
    if inconnues:
        print(f"  {len(inconnues)} correction(s) sur un ISIN hors actions, ignorée(s)")
    if args.resume:
        print()
        for (v, m), n in Counter(
                (l["PEA_eligible"], l["PEA_methode"]) for l in lignes).most_common():
            print(f"  {v:<12} {m:<24} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
