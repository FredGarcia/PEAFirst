#!/usr/bin/env python3
"""Simulateur d'investissement : versement initial, versements programmés,
horizons multiples et scénarios.

Répond au volet « Simulations » du cahier des charges : investissement unique,
versements programmés, réinvestissement des dividendes, fiscalité estimée,
horizons de 2 à 10 ans, scénarios prudent / médian / optimiste.

Ce que ce simulateur est, et ce qu'il n'est pas
-----------------------------------------------
Il projette des **hypothèses**, il ne prédit rien. Les taux de rendement sont
des paramètres, pas des prévisions : aucun modèle ne sait ce que fera un marché
sur dix ans. Trois trajectoires sont affichées côte à côte précisément pour que
l'écart entre elles reste visible — un chiffre unique donnerait une fausse
impression de certitude.

Les scénarios sont **déterministes** : un rendement annuel constant. C'est un
choix assumé. Une simulation de Monte-Carlo produirait des percentiles d'allure
scientifique reposant sur les mêmes hypothèses de départ, avec une précision
apparente que les données ne justifient pas. Le mode --sequence montre l'effet
de l'ordre des rendements, qui est l'essentiel de ce que la moyenne masque.

Fiscalité du PEA (au 1er janvier 2026, à vérifier avant tout usage)
-------------------------------------------------------------------
- Retrait **avant 5 ans** : impôt sur le revenu 12,8 % + prélèvements sociaux
  18,6 % = **31,4 %** sur les gains, et le plan est clôturé.
- Retrait **après 5 ans** : gains exonérés d'impôt sur le revenu, seuls les
  prélèvements sociaux de **18,6 %** s'appliquent.

Les prélèvements sociaux sont passés de 17,2 % à 18,6 % au 1er janvier 2026
(LFSS 2026, loi n° 2025-1403 du 30 décembre 2025). Le taux retenu est celui en
vigueur **au moment du retrait**, y compris sur des gains accumulés avant 2026.
Un simulateur resté à 17,2 % sous-estime donc l'impôt.

Cette règle rend les horizons de 2 et 3 ans structurellement défavorables en
PEA : le simulateur le chiffre au lieu de le passer sous silence.

Usage :
  python3 scripts/simulateur.py --capital 10000 --versement 500
  python3 scripts/simulateur.py --capital 5000 --versement 750 --horizons 5,10
  python3 scripts/simulateur.py --capital 20000 --enveloppe cto --sequence
"""
import argparse
import sys

# Horizons du cahier des charges.
HORIZONS = [2, 3, 5, 7, 8, 10]

# Rendements annuels moyens des scénarios, en pourcentage. Hypothèses de
# travail, à ajuster : ce ne sont ni des prévisions ni des engagements.
SCENARIOS = {
    "prudent": 2.0,
    "median": 5.0,
    "optimiste": 8.0,
}

# Prélèvements sociaux : portés de 17,2 % à 18,6 % au 1er janvier 2026 par la
# loi de financement de la Sécurité sociale (loi n° 2025-1403 du 30 décembre
# 2025, art. 12), la CSG passant de 9,2 % à 10,6 %. Le taux appliqué est celui
# en vigueur au moment du retrait, y compris sur des gains antérieurs.
# L'assurance-vie, elle, conserve 17,2 %.
PRELEVEMENTS_SOCIAUX = 18.6
# Impôt sur le revenu au prélèvement forfaitaire unique.
PFU_IR = 12.8


def capitalisation(capital, versement, mois_par_versement, annees, taux_annuel,
                   frais_gestion, frais_ordre):
    """Valeur du portefeuille après `annees`, versements inclus.

    Le calcul est mensuel : un versement trimestriel entré en année 1 ne
    travaille pas autant qu'un versement de la première année.
    """
    taux_mensuel = (1 + taux_annuel / 100) ** (1 / 12) - 1
    # Les frais de gestion des ETF sont prélevés en continu sur l'encours.
    frais_mensuel = (1 + frais_gestion / 100) ** (1 / 12) - 1

    valeur = capital * (1 - frais_ordre / 100) if capital else 0.0
    verse = capital
    mois = int(round(annees * 12))
    for m in range(1, mois + 1):
        valeur *= (1 + taux_mensuel)
        valeur *= (1 - frais_mensuel)
        if versement and mois_par_versement and m % mois_par_versement == 0:
            valeur += versement * (1 - frais_ordre / 100)
            verse += versement
    return valeur, verse


def fiscalite(valeur, verse, annees, enveloppe):
    """Impôt estimé au retrait total, et valeur nette."""
    gain = max(0.0, valeur - verse)
    if enveloppe == "pea":
        if annees < 5:
            taux = PFU_IR + PRELEVEMENTS_SOCIAUX
            motif = "retrait avant 5 ans : PFU 12,8 % + PS 18,6 %, plan clôturé"
        else:
            taux = PRELEVEMENTS_SOCIAUX
            motif = "après 5 ans : exonération d'IR, PS 18,6 % seuls"
    else:
        taux = PFU_IR + PRELEVEMENTS_SOCIAUX
        motif = "compte-titres : PFU 31,4 % quelle que soit la durée"
    impot = gain * taux / 100
    return gain, impot, valeur - impot, taux, motif


def sequence_tardive(capital, versement, mois_par_versement, annees,
                     taux_annuel, frais_gestion, frais_ordre):
    """Même rendement cumulé, mais concentré en fin de période.

    Illustre l'effet de séquence : deux trajectoires de rendement cumulé
    identique ne donnent pas le même résultat dès qu'on verse régulièrement.
    Contre l'intuition, des rendements faibles au début sont **favorables** à
    l'épargnant qui verse : ses versements achètent plus de parts tant que les
    cours sont bas. L'inverse — de bons rendements d'abord, une chute ensuite —
    est le cas défavorable, et c'est celui qui menace un retrait proche.
    """
    taux_mensuel = (1 + taux_annuel / 100) ** (1 / 12) - 1
    frais_mensuel = (1 + frais_gestion / 100) ** (1 / 12) - 1
    mois = int(round(annees * 12))
    valeur = capital * (1 - frais_ordre / 100) if capital else 0.0
    verse = capital
    # Première moitié à -30 % du rendement, seconde moitié compensée pour que
    # le rendement cumulé soit identique.
    total = (1 + taux_mensuel) ** mois
    bas = (1 + taux_mensuel * 0.3)
    reste = (total / bas ** (mois // 2)) ** (1 / (mois - mois // 2))
    for m in range(1, mois + 1):
        valeur *= bas if m <= mois // 2 else reste
        valeur *= (1 - frais_mensuel)
        if versement and mois_par_versement and m % mois_par_versement == 0:
            valeur += versement * (1 - frais_ordre / 100)
            verse += versement
    return valeur, verse


def euros(x):
    return f"{x:,.0f} €".replace(",", "\u202f")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--capital", type=float, default=10000.0,
                   help="versement initial en euros (défaut 10 000)")
    p.add_argument("--versement", type=float, default=0.0,
                   help="montant de chaque versement programmé (défaut 0)")
    p.add_argument("--periodicite", choices=["mensuel", "trimestriel", "annuel"],
                   default="trimestriel",
                   help="fréquence des versements (défaut trimestriel)")
    p.add_argument("--horizons", default=",".join(str(h) for h in HORIZONS),
                   help="horizons en années, séparés par des virgules")
    p.add_argument("--enveloppe", choices=["pea", "cto"], default="pea")
    p.add_argument("--frais-gestion", type=float, default=0.30,
                   help="frais annuels de gestion en %% de l'encours (défaut 0,30)")
    p.add_argument("--frais-ordre", type=float, default=0.50,
                   help="frais par versement en %% (défaut 0,50)")
    p.add_argument("--inflation", type=float, default=2.0,
                   help="inflation annuelle en %% pour le pouvoir d'achat (défaut 2,0)")
    p.add_argument("--sequence", action="store_true",
                   help="illustrer l'effet de l'ordre des rendements")
    args = p.parse_args()

    mois = {"mensuel": 1, "trimestriel": 3, "annuel": 12}[args.periodicite]
    try:
        horizons = [int(h) for h in args.horizons.split(",") if h.strip()]
    except ValueError:
        p.error("horizons invalides : attendu une liste d'entiers, ex. 5,10")
    if not horizons:
        p.error("aucun horizon fourni")

    print(f"Capital initial {euros(args.capital)}"
          + (f" · versement {euros(args.versement)} {args.periodicite}"
             if args.versement else " · aucun versement programmé"))
    print(f"Enveloppe {args.enveloppe.upper()} · frais {args.frais_gestion} %/an "
          f"sur l'encours et {args.frais_ordre} % par versement")
    print(f"Scénarios : " + ", ".join(f"{n} {t} %/an" for n, t in SCENARIOS.items()))
    print()

    entete = (f"{'Horizon':>8} {'Versé':>11} " +
              " ".join(f"{n.capitalize():>12}" for n in SCENARIOS) +
              f" {'Impôt (méd.)':>13} {'Net (méd.)':>12} {'Réel (méd.)':>12}")
    print(entete)
    print("-" * len(entete))

    for annees in horizons:
        valeurs = {}
        for nom, taux in SCENARIOS.items():
            valeurs[nom], verse = capitalisation(
                args.capital, args.versement, mois, annees, taux,
                args.frais_gestion, args.frais_ordre)
        med = valeurs["median"]
        gain, impot, net, taux_fisc, _ = fiscalite(med, verse, annees, args.enveloppe)
        # Pouvoir d'achat : ce que le net vaut en euros d'aujourd'hui.
        reel = net / ((1 + args.inflation / 100) ** annees)
        ligne = (f"{annees:>5} ans {euros(verse):>11} " +
                 " ".join(f"{euros(valeurs[n]):>12}" for n in SCENARIOS) +
                 f" {euros(impot):>13} {euros(net):>12} {euros(reel):>12}")
        print(ligne)

    print()
    # Rappel fiscal ciblé : c'est le point que les simulateurs escamotent.
    if args.enveloppe == "pea":
        courts = [a for a in horizons if a < 5]
        if courts:
            _, _, _, taux_court, motif_court = fiscalite(
                100, 0, min(courts), "pea")
            print(f"Horizons {', '.join(str(a) for a in courts)} ans : {motif_court}.")
            print("  Le gain est taxé à 31,4 % au lieu de 18,6 %, et le plan est")
            print("  clôturé — l'antériorité fiscale acquise est perdue.")
        longs = [a for a in horizons if a >= 5]
        if longs:
            print(f"Horizons {', '.join(str(a) for a in longs)} ans : "
                  "exonération d'IR, prélèvements sociaux de 18,6 % seuls.")
    else:
        print("Compte-titres : PFU de 31,4 % sur les gains quelle que soit la durée.")

    if args.sequence:
        annees = max(horizons)
        taux = SCENARIOS["median"]
        regulier, verse = capitalisation(
            args.capital, args.versement, mois, annees, taux,
            args.frais_gestion, args.frais_ordre)
        tardive, _ = sequence_tardive(
            args.capital, args.versement, mois, annees, taux,
            args.frais_gestion, args.frais_ordre)
        ecart = tardive - regulier
        print()
        print(f"Effet de l'ordre des rendements sur {annees} ans, à rendement "
              f"cumulé identique ({taux} %/an) :")
        print(f"  rendement régulier            {euros(regulier)}")
        print(f"  faible d'abord, fort ensuite  {euros(tardive)} "
              f"({'+' if ecart >= 0 else ''}{100 * ecart / regulier:.1f} %)")
        print("  Contre l'intuition, des rendements faibles au début favorisent")
        print("  celui qui verse régulièrement : ses versements achètent plus de")
        print("  parts tant que les cours sont bas. Le cas vraiment défavorable")
        print("  est l'inverse — une chute juste avant le retrait — que seul un")
        print("  horizon suffisamment long permet d'absorber.")

    print()
    print("Projection d'hypothèses, non une prévision. Les rendements passés ne")
    print("préjugent pas des rendements futurs, et aucun scénario n'est garanti.")
    print("Fiscalité au 1er janvier 2026 (LFSS 2026 : prélèvements sociaux portés")
    print("de 17,2 % à 18,6 %), à vérifier avant tout usage — elle change")
    print("régulièrement et dépend de votre situation personnelle.")
    print("Aide à la décision — ni conseil en investissement, ni conseil fiscal.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
