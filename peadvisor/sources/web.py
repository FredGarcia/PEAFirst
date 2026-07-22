"""Scrapers web multi-sources — ajout d'une valeur à la demande (nom/ISIN/code).

Chaque source est un `Scraper` : soit un connecteur **validé** avec son propre
parseur (Boursorama), soit un connecteur **best-effort** piloté par
configuration (URL de recherche + motif de lien + parseur générique), à
fiabiliser dès qu'une page exemple est disponible — le même chemin que celui
suivi pour Boursorama.

⚠️ Le scraping dépend de la structure des sites et de leurs conditions
d'utilisation (usage personnel). Le champ `valide` indique si le parseur a été
vérifié contre une vraie page.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

import requests

from peadvisor.sources.boursorama import (CHAMPS_FICHE, ENTETES, _nombre, _texte,
                                          parser_page)

__all__ = ["SCRAPERS", "CHAMPS_FICHE", "parser_generique"]


def parser_generique(html: str, source: str) -> dict[str, Any]:
    """Extraction best-effort commune : nom (<title>), ISIN, cours et devise.

    Suffisant pour créer/mettre à jour une ligne ; les indicateurs riches
    (PER, objectif, ESG…) nécessitent un parseur dédié par source, ajouté
    après examen d'une page réelle.
    """
    d: dict[str, Any] = {"source": source}
    if m := re.search(r"<title>(.*?)</title>", html, re.S):
        nom = re.split(r"\s*[|:–-]\s*|\bCours\b|\bAction\b|,", _texte(m.group(1)))[0]
        if nom:
            d["nom"] = nom.strip().title()
    if m := re.search(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b", html):
        d["isin"] = m.group(1)
    if "EUR" in html or "€" in html:
        d["devise"] = "EUR"
    # Cours : plusieurs conventions rencontrées sur les sites financiers.
    for motif in (r'itemprop="price"[^>]*content="([\d.,]+)"',
                  r'data-(?:last|price|cours)="([\d.,]+)"',
                  r'"last(?:Price)?"\s*:\s*"?([\d.,]+)"?',
                  r'class="[^"]*(?:last|cotation|c-instrument--last)[^"]*"[^>]*>\s*([\d.,]+)'):
        if m := re.search(motif, html):
            if (v := _nombre(m.group(1))) is not None:
                d["cours"] = v
                break
    return d


@dataclass
class Scraper:
    nom: str
    libelle: str
    valide: bool = False
    # Connecteur validé : fonction complète requête -> dict.
    recuperer_custom: Callable[[str], dict] | None = None
    # Connecteur best-effort piloté par configuration :
    recherche_url: str | None = None   # ?query=... renvoyant des liens de fiches
    motif_lien: str | None = None      # regex capturant le chemin/URL de la fiche
    base: str = ""                     # préfixe pour reconstruire l'URL absolue
    cours_direct: str | None = None    # URL de fiche directe (ISIN), {req} = requête

    def _resoudre_url(self, requete: str) -> str | None:
        requete = requete.strip()
        if self.cours_direct and re.match(r"^[A-Z]{2}[A-Z0-9]{9}\d$", requete):
            return self.cours_direct.format(req=requete)
        if self.recherche_url is None:
            return None
        rep = requests.get(self.recherche_url, params={"query": requete},
                           headers=ENTETES, timeout=20)
        rep.raise_for_status()
        m = re.search(self.motif_lien, rep.text) if self.motif_lien else None
        if not m:
            return None
        lien = m.group(1)
        return lien if lien.startswith("http") else self.base + lien

    def recuperer(self, requete: str) -> dict[str, Any]:
        if self.recuperer_custom is not None:
            return self.recuperer_custom(requete)
        url = self._resoudre_url(requete)
        if not url:
            raise ValueError(f"Aucune fiche trouvée sur {self.libelle} pour « {requete} »")
        rep = requests.get(url, headers=ENTETES, timeout=20)
        rep.raise_for_status()
        donnees = parser_generique(rep.text, self.nom)
        donnees.setdefault("source_url", url)   # lien d'acquisition
        if not donnees.get("isin") and not donnees.get("cours"):
            raise ValueError(
                f"{self.libelle} : rien d'exploitable extrait — parseur à fiabiliser "
                "(envoyer une page exemple, comme pour Boursorama)")
        return donnees


def _boursorama(requete: str) -> dict[str, Any]:
    # Accès via le module (et non les noms importés) pour rester patchable.
    from peadvisor.sources import boursorama
    code = boursorama.code_ou_recherche(requete)
    if not code:
        raise ValueError(f"Aucune valeur Boursorama pour « {requete} »")
    donnees = boursorama.recuperer_un(code)
    donnees.setdefault("source_url", f"{boursorama.BASE}{code}/")  # lien d'acquisition
    return donnees


# Registre des sources. Boursorama = validé ; les autres sont best-effort
# (parseur générique) en attendant une page exemple pour un parseur dédié.
SCRAPERS: dict[str, Scraper] = {
    "boursorama": Scraper("boursorama", "Boursorama", valide=True,
                          recuperer_custom=_boursorama),
    "boursier": Scraper("boursier", "Boursier",
                        recherche_url="https://www.boursier.com/recherche/rapide",
                        motif_lien=r'(/actions/cours/[^"\'>]+\.html)',
                        base="https://www.boursier.com"),
    "zonebourse": Scraper("zonebourse", "Zonebourse",
                          recherche_url="https://www.zonebourse.com/recherche/instruments/",
                          motif_lien=r'(/cours/action/[^"\'>]+)',
                          base="https://www.zonebourse.com"),
    "boursedirect": Scraper("boursedirect", "Bourse Direct",
                            recherche_url="https://www.boursedirect.fr/api/search",
                            motif_lien=r'(/fr/marches/[^"\'>]+)',
                            base="https://www.boursedirect.fr"),
    "ouestfrance": Scraper("ouestfrance", "Ouest-France",
                           recherche_url="https://bourse.ouest-france.fr/recherche/",
                           motif_lien=r'(/cours/[^"\'>]+)',
                           base="https://bourse.ouest-france.fr"),
    "euronext": Scraper("euronext", "Euronext Paris",
                        cours_direct="https://live.euronext.com/en/product/equities/{req}-XPAR",
                        recherche_url="https://live.euronext.com/en/instrumentSearch/searchJSON",
                        motif_lien=r'"(https://live\.euronext\.com/en/product/equities/[^"]+)"'),
}
