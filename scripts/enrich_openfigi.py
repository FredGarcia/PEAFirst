#!/usr/bin/env python3
"""Enrichissement OpenFIGI : FIGI, ticker exact, nom complet, type d'instrument.

Interroge l'API de mapping OpenFIGI v3 (https://www.openfigi.com/api) pour
chaque ISIN de la base et alimente un cache incrémental
(data/openfigi_cache.csv) puis un fichier fusionné (data/base_isin_figi.csv).

Le nom complet OpenFIGI est précieux pour les fonds dont le libellé Euronext
est un code technique (« VANETFV3PLIMETFP ») : il permet ensuite à
scripts/enrich_pea.py de classer sur un vrai nom.

Limites de débit (gérées automatiquement) :
  - sans clé   : 25 requêtes/min, 10 ISIN par requête  (~14 min pour 3 390 fonds)
  - avec clé   : 25 requêtes/6 s, 100 ISIN par requête (~1 min)
    → clé gratuite sur openfigi.com, à passer via la variable
      d'environnement OPENFIGI_API_KEY.

Le cache permet d'interrompre et de reprendre sans re-consommer de quota.

Usage :
  python3 scripts/enrich_openfigi.py                # fonds seulement (défaut)
  python3 scripts/enrich_openfigi.py --tout         # toute la base
  OPENFIGI_API_KEY=xxx python3 scripts/enrich_openfigi.py

Nécessite un accès réseau à api.openfigi.com (bloqué dans certains
environnements sandboxés : exécuter en local le cas échéant).
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

URL = "https://api.openfigi.com/v3/mapping"
COLONNES_CACHE = ["ISIN", "FIGI", "Ticker", "Nom_complet", "Type_instrument",
                  "Bourse", "Statut"]


def lire_csv(chemin):
    with open(chemin, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def charger_cache(chemin):
    if not chemin.exists():
        return {}
    return {r["ISIN"]: r for r in lire_csv(chemin)}


def ecrire_cache(chemin, cache):
    with open(chemin, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES_CACHE, delimiter=";")
        w.writeheader()
        for isin in sorted(cache):
            w.writerow(cache[isin])


def interroger(lot, cle):
    """Interroge OpenFIGI pour un lot d'ISIN, avec retries sur 429/erreur réseau."""
    corps = json.dumps([
        {"idType": "ID_ISIN", "idValue": isin} for isin in lot
    ]).encode()
    entetes = {"Content-Type": "application/json"}
    if cle:
        entetes["X-OPENFIGI-APIKEY"] = cle
    for attente in (0, 15, 30, 60):
        if attente:
            print(f"  nouvelle tentative dans {attente} s…")
            time.sleep(attente)
        req = urllib.request.Request(URL, data=corps, headers=entetes)
        try:
            with urllib.request.urlopen(req, timeout=30) as rep:
                return json.loads(rep.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                continue
            raise
        except urllib.error.URLError as e:
            print(f"  erreur réseau : {e.reason}")
            continue
    raise RuntimeError("OpenFIGI inaccessible après 4 tentatives")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--tout", action="store_true",
                        help="enrichir toute la base (défaut : ETF + OPCVM)")
    args = parser.parse_args()
    data = Path(args.data_dir)
    cle = os.environ.get("OPENFIGI_API_KEY", "")

    if args.tout:
        lignes = lire_csv(data / "base_isin.csv")
    else:
        lignes = (lire_csv(data / "base_isin_etf.csv")
                  + lire_csv(data / "base_isin_opcvm.csv"))
    lignes.sort(key=lambda r: r["ISIN"])

    chemin_cache = data / "openfigi_cache.csv"
    cache = charger_cache(chemin_cache)
    restants = [r["ISIN"] for r in lignes if r["ISIN"] not in cache]
    taille_lot = 100 if cle else 10
    pause = 6 / 25 if cle else 60 / 25
    print(f"{len(lignes)} ISIN, {len(cache)} déjà en cache, {len(restants)} à interroger "
          f"(lots de {taille_lot}, {'avec' if cle else 'sans'} clé API)")

    try:
        for debut in range(0, len(restants), taille_lot):
            lot = restants[debut:debut + taille_lot]
            resultats = interroger(lot, cle)
            for isin, res in zip(lot, resultats):
                donnees = (res.get("data") or [{}])[0]
                cache[isin] = {
                    "ISIN": isin,
                    "FIGI": donnees.get("figi", ""),
                    "Ticker": donnees.get("ticker", ""),
                    "Nom_complet": donnees.get("name", ""),
                    "Type_instrument": donnees.get("securityType", ""),
                    "Bourse": donnees.get("exchCode", ""),
                    "Statut": "OK" if donnees.get("figi") else "INTROUVABLE",
                }
            if (debut // taille_lot) % 10 == 0:
                ecrire_cache(chemin_cache, cache)
                print(f"  {debut + len(lot)}/{len(restants)} interrogés")
            time.sleep(pause)
    except KeyboardInterrupt:
        print("\nInterrompu — le cache est sauvegardé, relancer pour reprendre.")
    finally:
        ecrire_cache(chemin_cache, cache)

    sortie = data / "base_isin_figi.csv"
    with open(sortie, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=list(lignes[0].keys()) + COLONNES_CACHE[1:],
            delimiter=";",
        )
        w.writeheader()
        for r in lignes:
            extra = cache.get(r["ISIN"], {})
            w.writerow({**r, **{k: extra.get(k, "") for k in COLONNES_CACHE[1:]}})
    trouves = sum(1 for r in lignes
                  if cache.get(r["ISIN"], {}).get("Statut") == "OK")
    print(f"{sortie} : {len(lignes)} lignes, {trouves} FIGI trouvés")
    if len(cache) < len(lignes):
        print(f"Reste {len(lignes) - len(cache)} ISIN à interroger : relancer le script.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
