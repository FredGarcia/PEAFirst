#!/usr/bin/env python3
"""Enrichissement des données de marché et des indicateurs quantitatifs.

Alimente data/base_isin_marche.csv à partir des cours de clôture, puis calcule
les indicateurs du moteur quantitatif : volatilité annualisée, drawdown maximal,
ratio de Sharpe, ratio de Sortino et performance sur la période.

Deux modes, parce que les quotas gratuits ne permettent pas de tout faire :

  --cours      Dernier cours de chaque instrument (Marketstack, lots de 100).
               ~62 requêtes pour les 6188 ISIN de la base.
  --historique Historique quotidien + indicateurs calculés (1 requête par
               instrument). Réservé à un sous-ensemble : voir --filtre/--limite.

Quotas constatés (comptes gratuits, août 2026) :
  Marketstack   lots de 100 symboles, historique complet en 1 requête
  EODHD         20 requêtes/jour, bulk interdit — utilisé en repli
  Alpha Vantage 25 requêtes/jour — repli de dernier recours

Aucune de ces sources ne fournit l'éligibilité PEA : voir pea_emetteurs.csv.

Usage :
  export MARKETSTACK_API_KEY=...    # ou --cle
  python3 scripts/enrich_marche.py --cours --limite 500
  python3 scripts/enrich_marche.py --historique --filtre pea --limite 40
  python3 scripts/enrich_marche.py --etat        # avancement, sans appel API

Le cache data/marche_cache.json permet de reprendre après interruption : le
script ne réinterroge jamais un instrument déjà collecté (sauf --forcer).
"""
import argparse
import csv
import json
import math
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

MARKETSTACK = "https://api.marketstack.com/v1"
EODHD = "https://eodhd.com/api"

# MIC -> suffixe attendu par EODHD.
SUFFIXE_EODHD = {
    "XPAR": "PA", "XAMS": "AS", "XBRU": "BR", "XLIS": "LS",
    "XOSL": "OL", "XMIL": "MI", "XDUB": "IR",
}
LOT_SYMBOLES = 50
PAUSE = 1.1

# Places de cotation de la base -> code MIC utilisé par les fournisseurs.
MIC = {
    "Euronext Paris": "XPAR",
    "Euronext Paris - Multi-currency Trading": "XPAR",
    "Euronext Growth Paris": "XPAR",
    "Euronext Access Paris": "XPAR",
    "Euronext Amsterdam": "XAMS",
    "Euronext Amsterdam - Multi-currency Trading": "XAMS",
    "Euronext Amsterdam, Paris": "XAMS",
    "Euronext Amsterdam, Brussels": "XAMS",
    "Euronext Brussels": "XBRU",
    "Euronext Growth Brussels": "XBRU",
    "Euronext Lisbon": "XLIS",
    "Euronext Growth Lisbon": "XLIS",
    "Euronext Dublin": "XDUB",
    "Euronext Milan": "XMIL",
    "Euronext Growth Milan": "XMIL",
    "Oslo Børs": "XOSL",
    "Euronext Growth Oslo": "XOSL",
}

COLONNES = [
    "ISIN", "Nom", "Type", "Symbole_marche", "Devise", "Cours", "Date_cours",
    "Perf_periode_pct", "Volatilite_annualisee_pct", "Drawdown_max_pct",
    "Sharpe", "Sortino", "Nb_seances", "Source_cours", "Date_MAJ",
]


# ---------------------------------------------------------------- utilitaires

def lire_csv(chemin):
    with open(chemin, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def symbole_marche(ligne):
    """Construit le symbole SYMBOLE.MIC à partir de la place de cotation."""
    symbole = (ligne.get("Symbole") or "").strip()
    if not symbole:
        return ""
    for place in (ligne.get("Marché(s)") or "").split(" | "):
        mic = MIC.get(place.strip())
        if mic:
            return f"{symbole}.{mic}"
    return ""


def appel_json(url, essais=3):
    for tentative in range(essais):
        try:
            with urllib.request.urlopen(url, timeout=40) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            corps = e.read().decode(errors="replace")[:200]
            if e.code == 429:
                time.sleep(15)
                continue
            return {"_erreur": f"HTTP {e.code} {corps}"}
        except Exception as e:  # réseau, JSON tronqué…
            if tentative == essais - 1:
                return {"_erreur": f"{type(e).__name__}"}
            time.sleep(4)
    return {"_erreur": "epuise"}


# ------------------------------------------------------------- indicateurs

def indicateurs(closes, taux_sans_risque=0.0):
    """Indicateurs quantitatifs à partir d'une série de clôtures (ordre chrono).

    Renvoie un dict vide si la série est trop courte pour être significative.
    Les rendements nuls sont conservés : les exclure gonflerait la volatilité.
    """
    closes = [c for c in closes if c and c > 0]
    if len(closes) < 30:
        return {}

    rendements = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
    if not rendements:
        return {}

    # 252 séances de bourse par an : convention pour l'annualisation.
    vol_j = statistics.pstdev(rendements)
    vol_an = vol_j * math.sqrt(252)
    perf = closes[-1] / closes[0] - 1

    # Performance annualisée, pour comparer des séries de longueurs différentes.
    annees = len(rendements) / 252
    perf_an = (1 + perf) ** (1 / annees) - 1 if annees > 0 and perf > -1 else 0.0

    sharpe = (perf_an - taux_sans_risque) / vol_an if vol_an > 0 else 0.0

    # Sortino : seuls les rendements négatifs comptent dans le risque.
    negatifs = [r for r in rendements if r < 0]
    downside = statistics.pstdev(negatifs) * math.sqrt(252) if len(negatifs) > 1 else 0.0
    sortino = (perf_an - taux_sans_risque) / downside if downside > 0 else 0.0

    # Drawdown maximal : pire perte depuis un sommet précédent.
    sommet, dd_max = closes[0], 0.0
    for c in closes:
        sommet = max(sommet, c)
        dd_max = min(dd_max, c / sommet - 1)

    return {
        "Perf_periode_pct": round(perf * 100, 2),
        "Volatilite_annualisee_pct": round(vol_an * 100, 2),
        "Drawdown_max_pct": round(dd_max * 100, 2),
        "Sharpe": round(sharpe, 3),
        "Sortino": round(sortino, 3),
        "Nb_seances": len(closes),
    }


# ------------------------------------------------------------------ collecte

def collecter_historique_eodhd(symboles, cle, cache, jours, taux):
    """Historique via EODHD : 1 requête par instrument, 20/jour en gratuit.

    EODHD couvre les places Euronext que Marketstack ignore (Bruxelles, Oslo,
    Milan, Dublin). Le quota journalier se régénère, contrairement au quota
    mensuel de Marketstack : c'est la source à privilégier pour un
    sous-ensemble priorisé (watchlist, fonds éligibles PEA).
    """
    depuis = (date.today() - timedelta(days=jours)).isoformat()
    for n, sym in enumerate(symboles, 1):
        base_sym, _, mic = sym.partition(".")
        suffixe = SUFFIXE_EODHD.get(mic)
        if not suffixe:
            cache.setdefault(sym, {})["indisponible"] = True
            continue
        url = (f"{EODHD}/eod/{base_sym}.{suffixe}?api_token={cle}"
               f"&fmt=json&from={depuis}")
        rep = appel_json(url)
        if isinstance(rep, dict):
            erreur = rep.get("_erreur", "") or str(rep)[:120]
            if any(m in erreur.lower() for m in ("limit", "quota", "403", "429")):
                print(f"  {n}/{len(symboles)} {sym} : arrêt quota ({erreur[:90]})")
                return False
            cache.setdefault(sym, {})["indisponible"] = True
            print(f"  {n}/{len(symboles)} {sym} : indisponible")
            time.sleep(PAUSE)
            continue
        lignes = sorted(rep, key=lambda x: x.get("date", ""))
        closes = [x.get("adjusted_close") or x.get("close") for x in lignes]
        entree = cache.setdefault(sym, {})
        ind = indicateurs(closes, taux)
        if ind:
            entree.update(ind)
            entree["source"] = "EODHD"
            entree["cours"] = closes[-1]
            entree["date_cours"] = (lignes[-1].get("date") or "")[:10]
            print(f"  {n}/{len(symboles)} {sym} : {ind['Nb_seances']} séances, "
                  f"vol {ind['Volatilite_annualisee_pct']}%, "
                  f"Sharpe {ind['Sharpe']}")
        else:
            entree["historique_insuffisant"] = True
            print(f"  {n}/{len(symboles)} {sym} : historique insuffisant")
        time.sleep(PAUSE)
    return True


def charger_cache(chemin):
    if chemin.exists():
        try:
            return json.loads(chemin.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"cache illisible ({chemin}), redémarrage à vide")
    return {}


def sauver_cache(chemin, cache):
    temp = chemin.with_suffix(".tmp")
    temp.write_text(json.dumps(cache), encoding="utf-8")
    os.replace(temp, chemin)


def collecter_cours(symboles, cle, cache):
    """Dernier cours, par lots.

    Tous les symboles Euronext n'existent pas chez le fournisseur (les petites
    valeurs en sont souvent absentes). Un lot rejeté est donc redécoupé en deux
    plutôt qu'abandonné : on isole les symboles inconnus au lieu de perdre les
    bons qui les accompagnaient. Un symbole isolé qui échoue est marqué
    « indisponible » et ne sera plus réinterrogé.
    """
    lots = [symboles[i:i + LOT_SYMBOLES] for i in range(0, len(symboles), LOT_SYMBOLES)]
    total = len(lots)
    for n, lot in enumerate(lots, 1):
        if not _traiter_lot(lot, cle, cache, f"lot {n}/{total}"):
            return False
    return True


def _traiter_lot(lot, cle, cache, etiquette):
    """Traite un lot ; redécoupe en cas de rejet. False = arrêt demandé."""
    url = (f"{MARKETSTACK}/eod/latest?access_key={cle}"
           f"&symbols={','.join(lot)}&limit={LOT_SYMBOLES}")
    rep = appel_json(url)
    erreur = rep.get("_erreur") or (str(rep.get("error")) if "error" in rep else "")

    if erreur:
        # Quota épuisé ou clé refusée : inutile d'insister, on rend la main.
        if any(m in erreur.lower() for m in ("usage_limit", "quota", "inactive",
                                             "invalid_access_key", "401")):
            print(f"  {etiquette} : arrêt ({erreur[:120]})")
            return False
        if len(lot) == 1:
            cache.setdefault(lot[0], {})["indisponible"] = True
            print(f"  {etiquette} : {lot[0]} indisponible chez le fournisseur")
            return True
        milieu = len(lot) // 2
        time.sleep(PAUSE)
        return (_traiter_lot(lot[:milieu], cle, cache, etiquette + "a")
                and _traiter_lot(lot[milieu:], cle, cache, etiquette + "b"))

    recus = set()
    for x in rep.get("data", []):
        sym = x.get("symbol")
        if not sym:
            continue
        recus.add(sym)
        entree = cache.setdefault(sym, {})
        entree["cours"] = x.get("close")
        entree["date_cours"] = (x.get("date") or "")[:10]
        entree["source"] = "Marketstack"
    # Symboles acceptés par l'API mais sans donnée : à ne pas redemander.
    for sym in lot:
        if sym not in recus and not cache.get(sym, {}).get("cours"):
            cache.setdefault(sym, {})["indisponible"] = True
    print(f"  {etiquette} : {len(recus)}/{len(lot)} cours")
    time.sleep(PAUSE)
    return True


def collecter_historique(symboles, cle, cache, jours, taux):
    """Historique quotidien et indicateurs, une requête par instrument."""
    depuis = (date.today() - timedelta(days=jours)).isoformat()
    for n, sym in enumerate(symboles, 1):
        url = (f"{MARKETSTACK}/eod?access_key={cle}&symbols={sym}"
               f"&date_from={depuis}&date_to={date.today().isoformat()}&limit=1000")
        rep = appel_json(url)
        erreur = rep.get("_erreur") or (str(rep.get("error")) if "error" in rep else "")
        if erreur:
            if any(m in erreur.lower() for m in ("usage_limit", "quota", "inactive",
                                                 "invalid_access_key", "401")):
                print(f"  {n}/{len(symboles)} {sym} : arrêt ({erreur[:120]})")
                return False
            cache.setdefault(sym, {})["indisponible"] = True
            print(f"  {n}/{len(symboles)} {sym} : indisponible chez le fournisseur")
            time.sleep(PAUSE)
            continue
        lignes = rep.get("data") or []
        # L'API renvoie du plus récent au plus ancien : on rétablit l'ordre.
        lignes = sorted(lignes, key=lambda x: x.get("date", ""))
        closes = [x.get("close") for x in lignes]
        entree = cache.setdefault(sym, {})
        ind = indicateurs(closes, taux)
        if ind:
            entree.update(ind)
            entree["source"] = "Marketstack"
            if closes:
                entree["cours"] = closes[-1]
                entree["date_cours"] = (lignes[-1].get("date") or "")[:10]
            print(f"  {n}/{len(symboles)} {sym} : {ind['Nb_seances']} séances, "
                  f"vol {ind['Volatilite_annualisee_pct']}%")
        else:
            entree["historique_insuffisant"] = True
            print(f"  {n}/{len(symboles)} {sym} : historique insuffisant "
                  f"({len(closes)} séances)")
        time.sleep(PAUSE)
    return True


# --------------------------------------------------------------------- sortie

def ecrire_sortie(chemin, base, cache):
    aujourdhui = date.today().isoformat()
    ecrits = 0
    with open(chemin, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES, delimiter=";")
        w.writeheader()
        for ligne in base:
            sym = symbole_marche(ligne)
            info = cache.get(sym, {}) if sym else {}
            if not info or not info.get("cours"):
                continue
            w.writerow({
                "ISIN": ligne["ISIN"],
                "Nom": ligne["Nom"],
                "Type": ligne["Type"],
                "Symbole_marche": sym,
                "Devise": ligne["Devise"],
                "Cours": info.get("cours", ""),
                "Date_cours": info.get("date_cours", ""),
                "Perf_periode_pct": info.get("Perf_periode_pct", ""),
                "Volatilite_annualisee_pct": info.get("Volatilite_annualisee_pct", ""),
                "Drawdown_max_pct": info.get("Drawdown_max_pct", ""),
                "Sharpe": info.get("Sharpe", ""),
                "Sortino": info.get("Sortino", ""),
                "Nb_seances": info.get("Nb_seances", ""),
                "Source_cours": info.get("source", ""),
                "Date_MAJ": aujourdhui,
            })
            ecrits += 1
    return ecrits


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cours", action="store_true", help="dernier cours (lots de 100)")
    p.add_argument("--historique", action="store_true",
                   help="historique + indicateurs (1 requête par instrument)")
    p.add_argument("--etat", action="store_true", help="avancement, sans appel API")
    p.add_argument("--filtre", choices=["tout", "pea", "actions", "etf"], default="tout",
                   help="restreindre l'univers traité (défaut : tout)")
    p.add_argument("--limite", type=int, default=0,
                   help="nombre maximal d'instruments à interroger (0 = sans limite)")
    p.add_argument("--jours", type=int, default=400,
                   help="profondeur d'historique en jours (défaut 400)")
    p.add_argument("--taux-sans-risque", type=float, default=0.02,
                   help="taux sans risque annuel pour Sharpe/Sortino (défaut 0.02)")
    p.add_argument("--isins", default="",
                   help="liste d'ISIN séparés par des virgules, à traiter en "
                        "priorité (lot issu du tableau de bord)")
    p.add_argument("--file-attente", default="",
                   help="fichier contenant un ISIN par ligne (file d'attente "
                        "exportée depuis le tableau de bord)")
    p.add_argument("--forcer", action="store_true",
                   help="réinterroger même les instruments déjà en cache")
    p.add_argument("--source", choices=["eodhd", "marketstack"], default="eodhd",
                   help="fournisseur pour --historique (défaut eodhd : quota "
                        "journalier et meilleure couverture Euronext)")
    p.add_argument("--cle", default="")
    p.add_argument("--data-dir", default="data")
    args = p.parse_args()

    data = Path(args.data_dir)
    base = lire_csv(data / "base_isin.csv")
    chemin_cache = data / "marche_cache.json"
    chemin_sortie = data / "base_isin_marche.csv"
    cache = charger_cache(chemin_cache)

    # Univers de travail
    univers = base
    if args.filtre == "actions":
        univers = [r for r in base if r["Type"] == "Action"]
    elif args.filtre == "etf":
        univers = [r for r in base if r["Type"] == "ETF"]
    elif args.filtre == "pea":
        chemin_fonds = data / "base_isin_fonds_pea.csv"
        eligibles = set()
        if chemin_fonds.exists():
            eligibles = {r["ISIN"] for r in lire_csv(chemin_fonds)
                         if r.get("PEA_eligible") in ("OUI", "PROBABLE")}
        chemin_actions = data / "base_isin_actions_pea.csv"
        if chemin_actions.exists():
            eligibles |= {r["ISIN"] for r in lire_csv(chemin_actions)
                          if r.get("PEA_eligible") in ("OUI", "A_VERIFIER")}
        univers = [r for r in base if r["ISIN"] in eligibles]

    # Lot explicite : le tableau de bord permet de sélectionner des lignes et
    # d'exporter leurs ISIN. Il prime sur --filtre, et conserve l'ordre demandé.
    demandes = [i.strip() for i in args.isins.split(",") if i.strip()]
    if args.file_attente:
        chemin_file = Path(args.file_attente)
        if not chemin_file.exists():
            p.error(f"file d'attente introuvable : {chemin_file}")
        demandes += [l.strip() for l in chemin_file.read_text(encoding="utf-8").splitlines()
                     if l.strip() and not l.startswith("#")]
    if demandes:
        par_isin = {r["ISIN"]: r for r in base}
        inconnus = [i for i in demandes if i not in par_isin]
        if inconnus:
            print(f"{len(inconnus)} ISIN hors base ignoré(s) : {inconnus[:3]}")
        univers = [par_isin[i] for i in dict.fromkeys(demandes) if i in par_isin]
        print(f"Lot demandé : {len(univers)} instrument(s)")

    couples = [(r, symbole_marche(r)) for r in univers]
    resolus = [(r, s) for r, s in couples if s]
    non_resolus = len(couples) - len(resolus)

    if args.etat or not (args.cours or args.historique):
        avec_cours = sum(1 for _, s in resolus if cache.get(s, {}).get("cours"))
        avec_ind = sum(1 for _, s in resolus if cache.get(s, {}).get("Sharpe") is not None
                       and "Sharpe" in cache.get(s, {}))
        print(f"Univers « {args.filtre} » : {len(univers)} instruments")
        print(f"  symbole de marché résolu : {len(resolus)}"
              f" ({non_resolus} sans place reconnue)")
        indispo = sum(1 for _, s_ in resolus if cache.get(s_, {}).get("indisponible"))
        print(f"  cours en cache           : {avec_cours}")
        print(f"  indisponibles fournisseur: {indispo}")
        print(f"  indicateurs calculés     : {avec_ind}")
        if chemin_sortie.exists():
            print(f"  {chemin_sortie} : {len(lire_csv(chemin_sortie))} lignes")
        if not (args.cours or args.historique):
            print("\nRien à faire : préciser --cours ou --historique.")
        return 0

    if not args.cle:
        variable = ("EODHD_API_KEY" if (args.historique and args.source == "eodhd")
                    else "MARKETSTACK_API_KEY")
        args.cle = os.environ.get(variable, "")
    if not args.cle:
        p.error("clé absente : passer --cle, ou définir EODHD_API_KEY "
                "(--historique) ou MARKETSTACK_API_KEY (--cours)")

    cible = [s for _, s in resolus]
    if not args.forcer:
        cible = [s for s in cible if not cache.get(s, {}).get("indisponible")]
        if args.cours:
            cible = [s for s in cible if not cache.get(s, {}).get("cours")]
        else:
            cible = [s for s in cible
                     if "Sharpe" not in cache.get(s, {})
                     and not cache.get(s, {}).get("historique_insuffisant")]
    cible = list(dict.fromkeys(cible))  # dédoublonnage en conservant l'ordre
    if args.limite:
        cible = cible[:args.limite]

    if not cible:
        print("Rien à interroger : tout est déjà en cache (--forcer pour refaire).")
    else:
        print(f"{len(cible)} instrument(s) à interroger "
              f"({'cours' if args.cours else 'historique'})")
        try:
            if args.cours:
                collecter_cours(cible, args.cle, cache)
            elif args.source == "eodhd":
                collecter_historique_eodhd(cible, args.cle, cache, args.jours,
                                           args.taux_sans_risque)
            else:
                collecter_historique(cible, args.cle, cache, args.jours,
                                     args.taux_sans_risque)
        except KeyboardInterrupt:
            print("\nInterrompu — le cache est sauvegardé, relancer pour reprendre.")
        finally:
            sauver_cache(chemin_cache, cache)

    ecrits = ecrire_sortie(chemin_sortie, base, cache)
    print(f"{chemin_sortie} : {ecrits} lignes")
    restant = sum(1 for _, s in resolus if not cache.get(s, {}).get("cours"))
    if restant:
        print(f"Reste {restant} instrument(s) sans cours : relancer le script.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
