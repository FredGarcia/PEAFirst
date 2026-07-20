"""Scraping Boursorama (https://www.boursorama.com/cours/<code>/).

⚠️ Le *scraping* dépend de la structure HTML du site et de ses conditions
d'utilisation : plus fragile qu'une API (une refonte de page peut le casser)
et à réserver à un usage personnel. L'analyse de page est isolée dans la
fonction pure `parser_page(html)`, entièrement testée et facile à ajuster si
la mise en page évolue.

Code Boursorama d'une valeur = préfixe de place + mnémonique. Euronext Paris
utilise `1rP` : Air Liquide (AI) → `1rPAI`, TotalEnergies (TTE) → `1rPTTE`.
Quelques exceptions sont listées dans CODES.

Champs extraits : nom, ISIN, cours, devise, variation du jour, ouverture,
+haut, +bas, clôture veille, volume, capitalisation, PER, rendement du
dividende, éligibilité PEA.
"""

from __future__ import annotations

import re
from typing import Any

import requests

from peadvisor.sources.http import SourceHTTPBase, univers_de_base

BASE = "https://www.boursorama.com/cours/"
ENTETES = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
           "Accept-Language": "fr-FR,fr;q=0.9"}

# Exceptions au schéma « 1rP + mnémonique » (place ou code particulier).
CODES: dict[str, str] = {
    # "MNEMO": "code_boursorama",
}

# Étiquettes Boursorama (accents/casse ignorés) → champ PEAdvisor.
ETIQUETTES = {
    "ouverture": "ouverture",
    "+ haut": "plus_haut", "+haut": "plus_haut", "plus haut": "plus_haut",
    "+ bas": "plus_bas", "+bas": "plus_bas", "plus bas": "plus_bas",
    "cloture veille": "cloture_veille", "veille": "cloture_veille",
    "volume": "volume",
    "capitalisation": "capitalisation", "capi": "capitalisation",
    "per": "per", "per (2024)": "per", "per estime": "per",
    "rendement": "rendement", "rendement 2024": "rendement",
    "eligibilite pea": "eligible_pea", "eligibilite sr": "_ignore",
}


def _sans_accents(txt: str) -> str:
    for a, b in (("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a"), ("â", "a"),
                 ("î", "i"), ("ô", "o"), ("û", "u"), ("ç", "c")):
        txt = txt.replace(a, b).replace(a.upper(), b.upper())
    return txt


def _texte(html_fragment: str) -> str:
    """Retire les balises et normalise les espaces (y compris insécables)."""
    sans_balises = re.sub(r"<[^>]+>", " ", html_fragment)
    return re.sub(r"\s+", " ", sans_balises.replace("\xa0", " ")).strip()


def _nombre(txt: str) -> float | None:
    """Nombre robuste : virgule décimale (texte « 1 234,56 EUR ») ou point
    décimal (attributs machine « 184.52 »). Espaces = séparateurs de milliers."""
    t = txt.replace("\xa0", " ").replace(" ", "")
    m = re.search(r"-?\d[\d.,]*", t)
    if not m:
        return None
    s = m.group()
    if "," in s:  # virgule = décimale ; un éventuel point serait un millier
        s = s.replace(".", "").replace(",", ".")
    return float(s)


def _capitalisation_meur(txt: str) -> float | None:
    """« 45,2 Md€ » → 45200 (M€) ; « 980 M€ » → 980 ; « 1,2 B » → 1200."""
    valeur = _nombre(txt)
    if valeur is None:
        return None
    t = _sans_accents(txt).lower()
    if "md" in t or "b" in t or "mrd" in t:  # milliards
        return round(valeur * 1000, 1)
    return round(valeur, 1)  # déjà en millions


def parser_page(html: str) -> dict[str, Any]:
    """Extrait les données d'une page « cours » Boursorama (fonction pure)."""
    resultat: dict[str, Any] = {"source": "boursorama"}

    # Nom de la société.
    m = re.search(r'c-faceplate__company-title[^>]*>(.*?)</', html, re.S)
    if m:
        resultat["nom"] = _texte(m.group(1))

    # ISIN (motif normalisé : 2 lettres + 9 alphanum + 1 chiffre).
    m = re.search(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b", html)
    if m:
        resultat["isin"] = m.group(1)

    # Dernier cours : attribut data-ist-last, sinon élément c-instrument--last.
    m = (re.search(r'data-ist-last="([\d.,]+)"', html)
         or re.search(r'c-instrument--last[^>]*>(.*?)</', html, re.S))
    if m:
        cours = _nombre(_texte(m.group(1)))
        if cours is not None:
            resultat["cours"] = cours

    # Variation du jour (%).
    m = re.search(r'c-instrument--variation[^>]*>(.*?)</', html, re.S)
    if m:
        resultat["variation_pct"] = _nombre(_texte(m.group(1)))

    if "EUR" in html or "€" in html:
        resultat.setdefault("devise", "EUR")

    # Paires étiquette → valeur des listes d'indicateurs Boursorama.
    paires = re.findall(
        r'c-list-info__heading[^>]*>(.*?)</[^>]*>\s*<[^>]*c-list-info__value[^>]*>(.*?)</',
        html, re.S)
    for etiquette_html, valeur_html in paires:
        cle = _sans_accents(_texte(etiquette_html)).lower().strip()
        champ = ETIQUETTES.get(cle)
        if not champ or champ == "_ignore":
            continue
        valeur_txt = _texte(valeur_html)
        if champ == "eligible_pea":
            resultat["eligible_pea"] = "oui" in valeur_txt.lower()
        elif champ == "capitalisation":
            resultat["capitalisation"] = _capitalisation_meur(valeur_txt)
        else:
            valeur = _nombre(valeur_txt)
            if valeur is not None:
                resultat[champ] = valeur
    return resultat


def recuperer_un(code: str) -> dict[str, Any]:
    """Récupère et analyse la page d'une valeur Boursorama (par son code)."""
    reponse = requests.get(f"{BASE}{code}/", headers=ENTETES, timeout=20)
    reponse.raise_for_status()
    return parser_page(reponse.text)


class SourceBoursorama(SourceHTTPBase):
    nom = "boursorama"
    necessite_cle = False
    pause_s = 1.0  # scraping : rester courtois
    TICKER_TEST = "AI"  # Air Liquide → 1rPAI

    def symbole(self, ticker: str) -> str:
        return CODES.get(ticker, f"1rP{ticker}")

    def cotation(self, symbole: str, cle: str | None = None) -> dict[str, Any]:
        donnees = recuperer_un(symbole)
        # On ne garde que les champs exploitables par le référentiel.
        champs = ("cours", "devise", "variation_pct", "volume", "capitalisation",
                  "per", "rendement", "eligible_pea", "source")
        return {c: donnees[c] for c in champs if c in donnees}

    def serie(self, symbole: str, cle: str | None = None) -> list[dict[str, Any]]:
        return []  # cette page ne fournit pas l'historique quotidien

    def recuperer(self) -> list[dict[str, Any]]:
        resultats = []
        for actif in univers_de_base():
            ticker = actif.get("mnemonique")
            if not ticker or actif.get("type") == "OPCVM":
                resultats.append(actif)
                continue
            maj = dict(actif)
            try:
                maj.update(self.cotation(self.symbole(ticker)))
            except Exception:
                pass
            resultats.append(maj)
            import time
            time.sleep(self.pause_s)
        return resultats
