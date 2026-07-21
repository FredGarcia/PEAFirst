"""Scraping Boursorama (https://www.boursorama.com/cours/<code>/).

Version enrichie (fusion de la correction utilisateur + intégration PEAdvisor) :
extraction étendue des fondamentaux et de la donnée technique, détection du
**type d'instrument** (Action / ETF / OPCVM, depuis le <title>) pour ventiler
la valeur dans le bon onglet, et détection de l'**éligibilité PEA**.

⚠️ Le scraping dépend de la structure du site et de ses conditions
d'utilisation (usage personnel). L'analyse est isolée dans `parser_page(html)`
(fonction pure, testée contre une page réelle).
"""

from __future__ import annotations

import re
import time
from typing import Any

import requests

from peadvisor.sources.http import SourceHTTPBase, univers_de_base

BASE = "https://www.boursorama.com/cours/"
RECHERCHE = "https://www.boursorama.com/recherche/ajax"
ENTETES = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
           "Accept-Language": "fr-FR,fr;q=0.9"}

# Champs conservés pour la fiche (colonnes du modèle Actif). Noms SQL valides :
# les 52 semaines deviennent haut_52s / bas_52s.
CHAMPS_FICHE = (
    "nom", "secteur", "cours", "devise", "date_cotation", "heure_cotation",
    "variation_pct", "ouverture", "plus_haut", "plus_bas", "cloture_veille",
    "haut_52s", "bas_52s", "volume", "quantite_echangee",
    "capitalisation", "nb_titres", "per", "rendement", "bna", "dividende",
    "taux_distribution", "dette_nette", "ca",
    "objectif_cours", "potentiel", "consensus", "nb_analystes",
    "score_esg", "risque_esg", "eligible_pea", "source",
)

# Exceptions au schéma « 1rP + mnémonique ».
CODES: dict[str, str] = {}

# Étiquette Boursorama (sans accents, minuscule) → champ. Ordre important :
# tester les termes longs avant les courts (« 52 semaines + haut » avant « + haut »).
PREFIXES = [
    ("52 semaines + haut", "haut_52s"),
    ("52 semaines + bas", "bas_52s"),
    ("nombre de titres", "nb_titres"),
    ("benefice net par action", "bna"), ("bna", "bna"),
    ("taux de distribution", "taux_distribution"),
    ("chiffre d'affaires", "ca"),
    ("dette nette", "dette_nette"),
    ("ouverture", "ouverture"),
    ("+ haut", "plus_haut"), ("+haut", "plus_haut"), ("plus haut", "plus_haut"),
    ("+ bas", "plus_bas"), ("+bas", "plus_bas"), ("plus bas", "plus_bas"),
    ("cloture veille", "cloture_veille"),
    ("dernier dividende", "dividende"),
    ("volume", "volume"),
    ("quantite", "quantite_echangee"),
    ("valorisation", "capitalisation"), ("capitalisation", "capitalisation"),
    ("per", "per"),
    ("rendement", "rendement"),
    ("dividende", "dividende"),
    ("secteur", "secteur"),
    ("date ", "date_cotation"),
    ("heure", "heure_cotation"),
]


def _sans_accents(txt: str) -> str:
    for a, b in (("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a"), ("â", "a"),
                 ("î", "i"), ("ô", "o"), ("û", "u"), ("ç", "c")):
        txt = txt.replace(a, b).replace(a.upper(), b.upper())
    return txt


def _texte(html_fragment: str) -> str:
    sans_balises = re.sub(r"<[^>]+>", " ", html_fragment)
    return re.sub(r"\s+", " ", sans_balises.replace("\xa0", " ")).strip()


def _nombre(txt: str) -> float | None:
    t = txt.replace("\xa0", " ").replace(" ", "")
    m = re.search(r"-?\d[\d.,]*", t)
    if not m:
        return None
    s = m.group()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return float(s)


def _valeur_avec_unite(txt: str) -> float | None:
    """« 45,2 Md€ » → 45200 (M€) ; « 980 M€ » → 980 ; « 1,2 B » → 1200."""
    valeur = _nombre(txt)
    if valeur is None:
        return None
    t = _sans_accents(txt).lower()
    if "md" in t or "mrd" in t or " b" in t:  # milliards (Md€, Mrd, « B »)
        return round(valeur * 1000, 2)
    if "k" in t:
        return round(valeur / 1000, 4)
    return round(valeur, 2)


# Rétro-compatibilité (nom historique utilisé ailleurs / dans les tests).
_capitalisation_meur = _valeur_avec_unite


def _champ_pour(etiquette: str) -> str | None:
    cle = _sans_accents(etiquette).lower().strip()
    for prefixe, champ in PREFIXES:
        if cle.startswith(prefixe):
            return champ
    return None


def _type_depuis_titre(html: str) -> str:
    """Type d'instrument déduit du <title> : « … Cours Action … » → ACTION."""
    m = re.search(r"<title>\s*.+?\s+Cours\s+([A-Za-zÉÈéè]+)", html)
    mot = _sans_accents(m.group(1)).lower() if m else ""
    if mot.startswith("tracker") or mot == "etf" or mot == "etn":
        return "ETF"
    if mot in ("opcvm", "sicav", "fcp", "fonds"):
        return "OPCVM"
    return "ACTION"


def parser_page(html: str) -> dict[str, Any]:
    """Extrait les données d'une page « cours » Boursorama (fonction pure)."""
    resultat: dict[str, Any] = {"source": "boursorama"}

    if t := re.search(r"<title>\s*(.+?)\s+(?:Cours|Action|,|-)", html, re.S):
        resultat["nom"] = _texte(t.group(1)).title()
    resultat["type_detecte"] = _type_depuis_titre(html)

    if m := re.search(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b", html):
        resultat["isin"] = m.group(1)
    if "EUR" in html or "€" in html:
        resultat["devise"] = "EUR"

    # Éligibilité PEA : marqueur analytics « eligible-pea » présent sur la fiche.
    resultat["eligible_pea"] = bool(re.search(r"eligible-pea", html))

    # Dernier cours : attribut data-ist-last, sinon texte de l'élément (l'attribut
    # est souvent vide en HTML statique, le cours étant dans le texte).
    m = re.search(r'data-ist-last="([\d.,]+)"', html)
    if m and _nombre(m.group(1)) is not None:
        resultat["cours"] = _nombre(m.group(1))
    else:
        m = re.search(r'c-instrument--last[^>]*>\s*([\d.,]+)\s*<', html)
        if m and _nombre(m.group(1)) is not None:
            resultat["cours"] = _nombre(m.group(1))

    m = re.search(r'c-instrument--variation[^>]*>([^<]*)<', html)
    if m and _nombre(m.group(1)) is not None:
        resultat["variation_pct"] = _nombre(m.group(1))

    paires = re.findall(
        r'c-list-info__heading[^>]*>(.*?)</p>(?:(?!c-list-info__heading).)*?'
        r'c-list-info__value[^>]*>(.*?)</p>', html, re.S)
    for etiquette_html, valeur_html in paires:
        champ = _champ_pour(_texte(etiquette_html))
        if not champ:
            continue
        valeur_txt = _texte(valeur_html)
        if champ == "secteur":
            resultat["secteur"] = valeur_txt or None
        elif champ in ("date_cotation", "heure_cotation"):
            resultat.setdefault(champ, valeur_txt or None)
        elif champ in ("capitalisation", "dette_nette", "ca"):
            resultat[champ] = _valeur_avec_unite(valeur_txt)
        elif (v := _nombre(valeur_txt)) is not None:
            resultat.setdefault(champ, v)

    if "cours" not in resultat and "cloture_veille" in resultat:
        resultat["cours"] = resultat["cloture_veille"]

    if m := re.search(r"Objectif de cours[^<]*<span[^>]*>\s*([\d.,]+)", html):
        resultat["objectif_cours"] = _nombre(m.group(1))
    if m := re.search(r"Potentiel\s*:?\s*<span[^>]*>\s*(-?[\d.,]+)\s*%", html):
        resultat["potentiel"] = _nombre(m.group(1))
    if m := re.search(r"Nombre d'analystes[^<]*<span[^>]*>\s*(\d+)", html):
        resultat["nb_analystes"] = int(m.group(1))

    # Risque ESG (Sustainalytics, bas = mieux) → score ESG PEAdvisor (100 − risque).
    if m := re.search(r"Risque ESG.*?c-list-info__value[^>]*>\s*([\d.,]+)\s*/\s*100", html, re.S):
        risque = _nombre(m.group(1))
        if risque is not None:
            resultat["risque_esg"] = risque
            resultat["score_esg"] = round(100 - risque, 1)

    # Consensus (échelle Boursorama 1 = achat … 5 = vente) → PEAdvisor (5 = achat fort).
    if m := re.search(r"c-median-gauge__tooltip[^>]*>\s*(-?\d[\d.,]*)\s*<", html):
        brut = _nombre(m.group(1))
        if brut is not None:
            resultat["consensus_bourso"] = brut
            resultat["consensus"] = round(min(5.0, max(1.0, 6 - brut)), 2)

    return resultat


def recuperer_un(code: str) -> dict[str, Any]:
    reponse = requests.get(f"{BASE}{code}/", headers=ENTETES, timeout=20)
    reponse.raise_for_status()
    return parser_page(reponse.text)


def resoudre_code(requete: str) -> str | None:
    reponse = requests.get(RECHERCHE, params={"query": requete}, headers=ENTETES, timeout=20)
    reponse.raise_for_status()
    m = re.search(r"/cours/([0-9][0-9a-zA-Z]+)/", reponse.text)
    return m.group(1) if m else None


def code_ou_recherche(requete: str) -> str | None:
    requete = requete.strip()
    if re.match(r"^\d[a-zA-Z]", requete):
        return requete
    return resoudre_code(requete)


class SourceBoursorama(SourceHTTPBase):
    nom = "boursorama"
    necessite_cle = False
    pause_s = 1.0
    TICKER_TEST = "AI"

    def symbole(self, ticker: str) -> str:
        return CODES.get(ticker, f"1rP{ticker}")

    def cotation(self, symbole: str, cle: str | None = None) -> dict[str, Any]:
        donnees = recuperer_un(symbole)
        return {c: donnees[c] for c in CHAMPS_FICHE if c in donnees and c != "nom"}

    def serie(self, symbole: str, cle: str | None = None) -> list[dict[str, Any]]:
        return []

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
            time.sleep(self.pause_s)
        return resultats
