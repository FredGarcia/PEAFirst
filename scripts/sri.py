#!/usr/bin/env python3
"""Estimation de l'indicateur de risque synthétique (SRI) des PRIIPS.

Attention : le SRI concerne les produits d'investissement packagés — fonds,
ETF, produits structurés. Une action détenue en direct n'a pas de SRI. Le
script lui applique néanmoins l'échelle, par analogie et pour permettre la
comparaison, en le signalant dans la colonne `Ecart_officiel`.

Produit data/base_isin_sri.csv.

Ce que ce script calcule
------------------------
Le SRI affiché sur les documents d'informations clés (DIC) combine deux
mesures : le risque de marché (MRM), déduit de la volatilité, et le risque de
crédit (CRM). Le règlement délégué (UE) 2017/653, révisé par le règlement
2021/2268, fixe les bornes du MRM pour les PRIIPS de catégorie 2 :

    classe 1 : VEV < 0,5 %        classe 5 : 20 – 30 %
    classe 2 : 0,5 – 5 %          classe 6 : 30 – 80 %
    classe 3 : 5 – 12 %           classe 7 : > 80 %
    classe 4 : 12 – 20 %

où VEV désigne la volatilité équivalente à une VaR à 97,5 % sur la période de
détention recommandée.

Pourquoi il s'agit d'une estimation, et non du SRI officiel
------------------------------------------------------------
La VEV réglementaire s'obtient par un développement de Cornish-Fisher qui
corrige la volatilité de l'asymétrie et de l'aplatissement des rendements.
**Sans ces corrections, la formule redonne exactement la volatilité
annualisée** : notre estimation est donc la méthode officielle sous hypothèse
de rendements normaux. L'écart avec le DIC vient de là, et de quatre autres
différences que ce script ne peut pas combler :

1. le règlement impose **cinq ans** d'historique en pas hebdomadaire ; nous
   disposons d'environ dix-huit mois en pas quotidien ;
2. l'asymétrie et l'aplatissement ne sont pas encore mesurés — la colonne
   `Methode` indique quelle formule a servi ;
3. le **risque de crédit** (CRM) n'est pas évalué : il peut relever le SRI
   d'un fonds au-dessus de son seul MRM ;
4. le MRM officiel est la valeur la plus fréquente sur quatre mois, alors que
   nous calculons une valeur instantanée.

Une classe 7 reste une classe 7 en toutes circonstances : le règlement dispense
alors d'évaluer le risque de crédit.

**Ce chiffre ne remplace pas le SRI du DIC.** Il sert à comparer des
instruments entre eux et à repérer ceux dont le risque dépasse un profil, pas à
se substituer au document réglementaire de l'émetteur.

Usage :
  python3 scripts/sri.py
  python3 scripts/sri.py --horizon 5 --resume
"""
import argparse
import csv
import math
import sys
from collections import Counter
from datetime import date
from pathlib import Path

# Bornes hautes de VEV (%) par classe MRM, catégorie 2 (RTS annexe II, point 2).
BORNES = [(1, 0.5), (2, 5.0), (3, 12.0), (4, 20.0), (5, 30.0), (6, 80.0)]

COLONNES = ["ISIN", "Nom", "Type", "Volatilite_annualisee_pct", "VEV_pct",
            "SRI_estime", "Bande", "Methode", "Fiabilite", "Nb_seances",
            "Ecart_officiel", "Date_MAJ"]

# Séances attendues pour cinq ans de cotation quotidienne.
SEANCES_CINQ_ANS = 5 * 252


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


def vev(volatilite_pct, asymetrie=None, aplatissement=None, horizon=5.0):
    """VaR-equivalent volatility, en pourcentage.

    Applique le développement de Cornish-Fisher quand l'asymétrie et
    l'aplatissement sont connus. Sinon renvoie la volatilité annualisée, qui
    est le résultat exact de la même formule pour une distribution normale.
    """
    if volatilite_pct is None or volatilite_pct <= 0:
        return None, "indisponible"
    if asymetrie is None or aplatissement is None:
        return volatilite_pct, "volatilite_annualisee"

    sigma = volatilite_pct / 100.0
    t = max(horizon, 0.25)
    racine = math.sqrt(t)
    # VaR en espace de rendement (RTS annexe II, point 12).
    correction = (-1.96
                  + 0.474 * asymetrie / racine
                  - 0.0687 * aplatissement / t
                  + 0.146 * asymetrie ** 2 / t)
    var = sigma * racine * correction - 0.5 * sigma ** 2 * t
    interieur = 3.842 - 2 * var
    if interieur <= 0:
        return volatilite_pct, "volatilite_annualisee"
    return ((math.sqrt(interieur) - 1.96) / racine) * 100.0, "cornish_fisher"


def classe(vev_pct):
    """Classe MRM et libellé de la bande."""
    if vev_pct is None:
        return None, ""
    precedent = None
    for niveau, borne in BORNES:
        if vev_pct < borne:
            libelle = (f"< {borne:g} %" if precedent is None
                       else f"{precedent:g} – {borne:g} %")
            return niveau, libelle
        precedent = borne
    return 7, "> 80 %"


def fiabilite(seances):
    """Qualifie la confiance accordée à l'estimation."""
    if seances is None:
        return "inconnue", "profondeur d'historique inconnue"
    part = seances / SEANCES_CINQ_ANS
    if part >= 0.9:
        return "bonne", "historique proche des cinq ans exigés"
    if part >= 0.4:
        return "moyenne", (f"{int(seances)} séances sur les {SEANCES_CINQ_ANS} "
                           "correspondant à cinq ans")
    return "faible", (f"{int(seances)} séances seulement : une période courte "
                      "peut masquer des phases de forte volatilité")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--horizon", type=float, default=5.0,
                   help="période de détention recommandée en années (défaut 5)")
    p.add_argument("--resume", action="store_true", help="afficher la synthèse")
    p.add_argument("--data-dir", default="data")
    args = p.parse_args()

    data = Path(args.data_dir)
    marche = lire(data / "base_isin_marche.csv")
    if not marche:
        print("Aucune donnée de marché : lancer d'abord scripts/enrich_marche.py")
        return 0

    aujourdhui = date.today().isoformat()
    lignes = []
    for r in marche:
        vol = nombre(r.get("Volatilite_annualisee_pct"))
        if vol is None:
            continue
        v, methode = vev(vol, nombre(r.get("Asymetrie")),
                         nombre(r.get("Aplatissement_exces")), args.horizon)
        niveau, bande = classe(v)
        seances = nombre(r.get("Nb_seances"))
        note, motif = fiabilite(seances)
        # Le SRI est un indicateur des PRIIPS : les fonds en ont un, les
        # actions détenues en direct n'en ont pas. L'échelle leur est appliquée
        # par analogie, ce qui doit être dit plutôt que laissé croire.
        if r.get("Type") == "Action":
            ecart = ("une action n'est pas un PRIIPS : aucun SRI officiel "
                     "n'existe, l'échelle est appliquée par analogie")
        else:
            ecart = ("estimation : CRM non évalué, historique plus court que "
                     "les cinq ans exigés")
            if methode == "volatilite_annualisee":
                ecart += ", asymétrie et aplatissement non corrigés"
        lignes.append({
            "ISIN": r["ISIN"], "Nom": r.get("Nom", ""), "Type": r.get("Type", ""),
            "Volatilite_annualisee_pct": f"{vol:.2f}",
            "VEV_pct": f"{v:.2f}" if v is not None else "",
            "SRI_estime": niveau or "", "Bande": bande, "Methode": methode,
            "Fiabilite": note, "Nb_seances": int(seances) if seances else "",
            "Ecart_officiel": ecart + f" ({motif})", "Date_MAJ": aujourdhui,
        })

    sortie = data / "base_isin_sri.csv"
    with open(sortie, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES, delimiter=";")
        w.writeheader()
        w.writerows(lignes)

    # Les instruments sans classe apparaissent sous une clé distincte plutôt
    # que mêlés aux niveaux numériques.
    repartition = Counter(l["SRI_estime"] if l["SRI_estime"] != "" else "n.d."
                          for l in lignes)
    niveaux = sorted(k for k in repartition if k != "n.d.")
    if "n.d." in repartition:
        niveaux.append("n.d.")
    print(f"{sortie} : {len(lignes)} instrument(s)")
    print("  Répartition SRI estimé : " +
          ", ".join(f"{k}={repartition[k]}" for k in niveaux))
    faibles = sum(1 for l in lignes if l["Fiabilite"] == "faible")
    if faibles:
        print(f"  {faibles} estimation(s) de fiabilité faible "
              "(historique trop court)")
    if args.resume:
        print()
        for niveau in niveaux:
            if niveau == "n.d.":
                continue
            exemples = [l["Nom"][:26] for l in lignes if l["SRI_estime"] == niveau][:3]
            bande = next(l["Bande"] for l in lignes if l["SRI_estime"] == niveau)
            print(f"  SRI {niveau} ({bande:<12}) : {repartition[niveau]:>4} — "
                  + ", ".join(exemples))

    print()
    print("Estimation, non le SRI officiel. Le document d'informations clés de")
    print("l'émetteur reste la seule référence : il s'appuie sur cinq ans")
    print("d'historique et intègre le risque de crédit, absent d'ici.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
