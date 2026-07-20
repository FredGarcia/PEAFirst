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
RECHERCHE = "https://www.boursorama.com/recherche/ajax"
ENTETES = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
           "Accept-Language": "fr-FR,fr;q=0.9"}

# Champs conservés pour la fiche du référentiel (colonnes du modèle Actif).
# potentiel et consensus_bourso restent hors modèle : le potentiel est
# recalculé par le scoring (objectif/cours), consensus_bourso est la valeur
# brute conservée pour transparence dans la réponse d'import.
CHAMPS_FICHE = ("nom", "secteur", "cours", "devise", "variation_pct", "volume",
                "capitalisation", "per", "rendement", "objectif_cours",
                "consensus", "score_esg", "risque_esg", "eligible_pea", "source")

# Exceptions au schéma « 1rP + mnémonique » (place ou code particulier).
CODES: dict[str, str] = {
    # "MNEMO": "code_boursorama",
}

# Correspondance étiquette Boursorama (sans accents, minuscule) → champ.
# Testée par préfixe : « rendement estimé 2026 » → commence par « rendement ».
PREFIXES = [
    ("ouverture", "ouverture"),
    ("+ haut", "plus_haut"), ("+haut", "plus_haut"), ("plus haut", "plus_haut"),
    ("+ bas", "plus_bas"), ("+bas", "plus_bas"), ("plus bas", "plus_bas"),
    ("cloture veille", "cloture_veille"),
    ("volume", "volume"),
    ("valorisation", "capitalisation"), ("capitalisation", "capitalisation"),
    ("per", "per"),
    ("rendement", "rendement"),
    ("secteur", "secteur"),
]


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


def _champ_pour(etiquette: str) -> str | None:
    """Champ PEAdvisor correspondant à une étiquette Boursorama (par préfixe)."""
    cle = _sans_accents(etiquette).lower().strip()
    for prefixe, champ in PREFIXES:
        if cle.startswith(prefixe):
            return champ
    return None


def parser_page(html: str) -> dict[str, Any]:
    """Extrait les données d'une page « cours » Boursorama (fonction pure).

    Couvre les indicateurs rendus côté serveur : identité, cours (dernier ou,
    à défaut, clôture veille), variation, secteur, valorisation, PER et
    rendement estimés, objectif de cours 3 mois + potentiel, risque ESG,
    consensus analystes. Les valeurs ESG et consensus sont converties vers les
    conventions PEAdvisor (voir plus bas).
    """
    resultat: dict[str, Any] = {"source": "boursorama"}

    # Nom : la balise <title> (« AIR LIQUIDE Cours Action … ») est la plus
    # fiable ; on prend le texte avant « Cours ».
    if t := re.search(r"<title>\s*(.+?)\s+(?:Cours|Action|,|-)", html, re.S):
        resultat["nom"] = _texte(t.group(1)).title()

    # ISIN.
    if m := re.search(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b", html):
        resultat["isin"] = m.group(1)

    if "EUR" in html or "€" in html:
        resultat["devise"] = "EUR"

    # Dernier cours : data-ist-last (souvent vide en HTML statique, rempli en JS).
    m = re.search(r'data-ist-last="([\d.,]+)"', html)
    if m and _nombre(m.group(1)) is not None:
        resultat["cours"] = _nombre(m.group(1))

    m = re.search(r'c-instrument--variation[^>]*>([^<]*)<', html)
    if m and _nombre(m.group(1)) is not None:
        resultat["variation_pct"] = _nombre(m.group(1))

    # Listes d'indicateurs (heading → value), tolérantes au contenu intercalé
    # (icônes, boutons) et sans franchir l'étiquette suivante.
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
        elif champ == "capitalisation":
            resultat["capitalisation"] = _capitalisation_meur(valeur_txt)
        elif (v := _nombre(valeur_txt)) is not None:
            resultat.setdefault(champ, v)

    # Clôture veille comme repli du dernier cours (HTML statique sans live).
    if "cours" not in resultat and "cloture_veille" in resultat:
        resultat["cours"] = resultat["cloture_veille"]

    # Objectif de cours 3 mois et potentiel (bloc consensus).
    if m := re.search(r"Objectif de cours[^<]*<span[^>]*>\s*([\d.,]+)", html):
        resultat["objectif_cours"] = _nombre(m.group(1))
    if m := re.search(r"Potentiel\s*:?\s*<span[^>]*>\s*(-?[\d.,]+)\s*%", html):
        resultat["potentiel"] = _nombre(m.group(1))

    # Risque ESG (Sustainalytics) : « 12,7/100 (faible) ». Plus bas = mieux.
    if m := re.search(r"Risque ESG.*?c-list-info__value[^>]*>\s*([\d.,]+)\s*/\s*100", html, re.S):
        risque = _nombre(m.group(1))
        if risque is not None:
            resultat["risque_esg"] = risque
            # Conversion vers le score ESG PEAdvisor (0-100, haut = mieux).
            resultat["score_esg"] = round(100 - risque, 1)

    # Consensus analystes : jauge (échelle Boursorama 1 = achat ... 5 = vente).
    if m := re.search(r"c-median-gauge__tooltip[^>]*>\s*(-?\d[\d.,]*)\s*<", html):
        brut = _nombre(m.group(1))
        if brut is not None:
            resultat["consensus_bourso"] = brut
            # Vers l'échelle PEAdvisor (1 = vente ... 5 = achat fort).
            resultat["consensus"] = round(min(5.0, max(1.0, 6 - brut)), 2)

    return resultat


def recuperer_un(code: str) -> dict[str, Any]:
    """Récupère et analyse la page d'une valeur Boursorama (par son code)."""
    reponse = requests.get(f"{BASE}{code}/", headers=ENTETES, timeout=20)
    reponse.raise_for_status()
    return parser_page(reponse.text)


def resoudre_code(requete: str) -> str | None:
    """Résout un nom ou un ISIN en code Boursorama via la recherche du site.

    La recherche accepte aussi bien un nom (« air liquide ») qu'un ISIN
    (« FR0000120073 ») et renvoie des liens /cours/<code>/ — on prend le
    premier résultat action.
    """
    reponse = requests.get(RECHERCHE, params={"query": requete}, headers=ENTETES, timeout=20)
    reponse.raise_for_status()
    m = re.search(r"/cours/([0-9][0-9a-zA-Z]+)/", reponse.text)
    return m.group(1) if m else None


def code_ou_recherche(requete: str) -> str | None:
    """Renvoie un code Boursorama : la requête telle quelle si elle en est
    déjà un (ex. « 1rPAI »), sinon résolution par nom/ISIN."""
    requete = requete.strip()
    if re.match(r"^\d[a-zA-Z]", requete):  # ex. 1rPAI, 1rACA…
        return requete
    return resoudre_code(requete)


class SourceBoursorama(SourceHTTPBase):
    nom = "boursorama"
    necessite_cle = False
    pause_s = 1.0  # scraping : rester courtois
    TICKER_TEST = "AI"  # Air Liquide → 1rPAI

    def symbole(self, ticker: str) -> str:
        return CODES.get(ticker, f"1rP{ticker}")

    def cotation(self, symbole: str, cle: str | None = None) -> dict[str, Any]:
        donnees = recuperer_un(symbole)
        return {c: donnees[c] for c in CHAMPS_FICHE if c in donnees and c != "nom"}

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
