#!/usr/bin/env python3
"""Fiabilisation de l'éligibilité PEA des fonds (ETF + OPCVM).

Croise, par ordre de priorité décroissante :
  1. data/pea_emetteurs.csv — liste vérifiée issue des émetteurs
     (Amundi, iShares, BNP…) : fait autorité, OUI ou NON.
  2. Domicile hors EEE — inéligible par construction (art. L221-31 CMF).
  3. Nom commercial contenant « PEA » — les émetteurs réservent ce
     marquage aux fonds éligibles (gammes Amundi PEA, iShares Swap PEA…).
  4. Classe d'actifs incompatible (obligataire, monétaire, crypto,
     matières premières) sans marquage PEA — inéligible.
  5. Indice actions européen dans le nom + domicile EEE — très
     probablement éligible (quota 75 % d'actions UE respecté de fait).
  6. Reste (fonds EEE sur indices monde/US/émergents sans marquage
     PEA) — indéterminé, à vérifier via les listes émetteurs.

Produit data/base_isin_fonds_pea.csv : colonnes de la base + PEA_eligible
(OUI | PROBABLE | NON | A_VERIFIER), PEA_methode, PEA_source.

Usage : python3 scripts/enrich_pea.py [--data-dir data]
"""
import argparse
import csv
import re
from collections import Counter
from pathlib import Path

EEE = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE", "NO", "IS", "LI",
}

RE_PEA = re.compile(r"\bPEA\b", re.I)
# Indices actions européens (noms Euronext souvent tronqués : on matche large
# mais on exclut d'abord les classes d'actifs incompatibles).
RE_INDICE_EUROPE = re.compile(
    r"CAC ?40|CAC(?![A-Z])|SBF ?120|ESTOXX|EURO ?STOXX|STOXX ?(EUROPE )?[56]00?0?"
    r"|STOXX ?50|DAX(?![A-Z])|MDAX|TECDAX|SDAX|FTSE ?MIB|MIB(?![A-Z])|IBEX"
    r"|AEX(?![A-Z])|BEL ?20|PSI ?20|OMX|OBX"
    r"|MSCI (EMU|EUROPE|EUR|FRANCE|GERMANY|ITALY|SPAIN|NORDIC|NETHERLANDS)"
    r"|EMU(?![A-Z])|EUROZONE|EURONEXT|EUROPE(?![A-Z])|EUR(OPE)? ?SMALL",
    re.I,
)
# Classes d'actifs incompatibles avec le quota PEA (sauf montage swap dédié,
# toujours signalé par « PEA » dans le nom — testé avant cette règle).
RE_HORS_ACTIONS = re.compile(
    r"BOND|OBLIG|GOVT|GOVIES|GOV ?BD|TREASUR|CORP(?![A-Z])|AGGREGATE|AGG(?![A-Z])"
    r"|MONEY|MONETAIRE|CASH|OVERNIGHT|FLOATING ?RATE|HIGH ?YIELD|EONIA|ESTER|€STR"
    r"|BITCOIN|BITETN|ETHEREUM|CRYPTO|BLOCKCHAIN ?ETP|\bBTC\b|\bETH\b|\bXRP\b|SOLANA"
    r"|GOLD|\bOR\b|SILVER|ARGENT ?PHYS|PLATIN|PALLAD|COPPER|URANIUM|\bOIL\b"
    r"|\bWTI\b|BRENT|COMMOD|MATIERES ?PREM|NATURAL ?GAS|\bRENTE\b",
    re.I,
)
# Les fonds d'actions minières/aurifères sont des fonds actions, pas des ETC
# matières premières : ils échappent à la règle CLASSE_ACTIFS.
RE_MINES = re.compile(r"MIN(ING|ERS?)\b|GOLD ?MIN", re.I)


def lire_csv(chemin):
    with open(chemin, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def classifier(r, overlay, noms_figi):
    """Retourne (PEA_eligible, PEA_methode, PEA_source) pour un fonds.

    Le libellé Euronext étant souvent un code technique tronqué, le nom
    complet OpenFIGI (s'il a été récupéré) est concaténé au libellé pour
    donner prise aux règles lexicales."""
    isin = r["ISIN"]
    nom = r["Nom"]
    if noms_figi.get(isin):
        nom = f"{nom} {noms_figi[isin]}"
    if isin in overlay:
        o = overlay[isin]
        return o["PEA_eligible"], "LISTE_EMETTEUR", o["Source"]
    if isin[:2] not in EEE:
        return "NON", "HORS_EEE", "Domicile hors EEE (art. L221-31 CMF)"
    if RE_PEA.search(nom):
        return "OUI", "NOM_PEA", "Marquage « PEA » dans le nom émetteur"
    if RE_HORS_ACTIONS.search(nom) and not RE_MINES.search(nom):
        return "NON", "CLASSE_ACTIFS", "Obligataire/monétaire/crypto/matières premières sans montage PEA"
    if RE_INDICE_EUROPE.search(nom):
        return "PROBABLE", "INDICE_EUROPEEN", "Indice actions européen — quota 75 % actions UE respecté de fait"
    return "A_VERIFIER", "NON_DETERMINE", "Fonds EEE sur indice non européen : vérifier la liste émetteur"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    data = Path(args.data_dir)

    fonds = lire_csv(data / "base_isin_etf.csv") + lire_csv(data / "base_isin_opcvm.csv")
    fonds.sort(key=lambda r: r["ISIN"])

    chemin_overlay = data / "pea_emetteurs.csv"
    overlay = {}
    if chemin_overlay.exists():
        overlay = {r["ISIN"]: r for r in lire_csv(chemin_overlay)}
        inconnus = set(overlay) - {r["ISIN"] for r in fonds}
        if inconnus:
            print(f"ATTENTION : {len(inconnus)} ISIN de pea_emetteurs.csv absents "
                  f"de la base fonds : {sorted(inconnus)[:5]}")

    chemin_figi = data / "base_isin_figi.csv"
    noms_figi = {}
    if chemin_figi.exists():
        noms_figi = {r["ISIN"]: r.get("Nom_complet", "")
                     for r in lire_csv(chemin_figi) if r.get("Statut") == "OK"}
        print(f"Noms complets OpenFIGI chargés : {len(noms_figi)}")

    sortie = data / "base_isin_fonds_pea.csv"
    stats = Counter()
    with open(sortie, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=list(fonds[0].keys()) + ["PEA_eligible", "PEA_methode", "PEA_source"],
            delimiter=";",
        )
        w.writeheader()
        for r in fonds:
            eligible, methode, source = classifier(r, overlay, noms_figi)
            stats[(eligible, methode)] += 1
            w.writerow({**r, "PEA_eligible": eligible,
                        "PEA_methode": methode, "PEA_source": source})

    print(f"{sortie} : {len(fonds)} fonds classés")
    print(f"{'PEA_eligible':<12} {'méthode':<18} {'nb':>5}")
    for (eligible, methode), n in sorted(stats.items()):
        print(f"{eligible:<12} {methode:<18} {n:>5}")
    total = Counter()
    for (eligible, _), n in stats.items():
        total[eligible] += n
    print("\nBilan :", ", ".join(f"{k}={v}" for k, v in sorted(total.items())))


if __name__ == "__main__":
    main()
