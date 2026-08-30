"""Source PEAFirst : le référentiel réel produit par la chaîne `scripts/`.

Les autres sources interrogent une API externe. Celle-ci lit les fichiers que
la chaîne de données du dépôt a déjà constitués, vérifiés et versionnés :

    data/base_isin.csv              6 188 instruments Euronext dédoublonnés
    data/base_isin_figi.csv         identifiants et noms complets OpenFIGI
    data/base_isin_actions_pea.csv  éligibilité PEA des actions
    data/base_isin_fonds_pea.csv    éligibilité PEA des ETF et OPCVM
    data/base_isin_marche.csv       cours et indicateurs quantitatifs
    data/base_isin_sri.csv          indicateur de risque SRI

C'est la seule source dont l'éligibilité PEA repose sur des règles vérifiées
plutôt que sur une valeur déclarative : régime foncier, nature de l'instrument,
pays d'émission, relevés émetteurs, et les corrections saisies par
l'utilisateur, qui priment sur tout.

Aucune requête réseau, donc aucun quota : la collecte est faite en amont par
`scripts/enrich_marche.py`, quotidiennement via GitHub Actions.

Deux limites à connaître :

1. **Tous les instruments n'ont pas de données de marché.** Les quotas gratuits
   limitent la collecte à une vingtaine d'instruments par jour ; les autres
   n'ont ni cours, ni indicateurs, ni score. Le paramètre `avec_donnees`
   (défaut) ne remonte que les instruments réellement exploitables.
2. **Cinq critères du cahier des charges restent vides** — potentiel,
   valorisation (PER), croissance, dividende, consensus — faute de source
   européenne gratuite. Les champs correspondants sont laissés à `None` plutôt
   que remplis d'une valeur inventée : le score de PEAdvisor renormalise alors
   ses pondérations sur les critères réellement disponibles.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from peadvisor.sources.base import SourceDonnees

# Racine du dépôt, où vit le répertoire data/ alimenté par scripts/.
RACINE = Path(__file__).resolve().parents[2]

# Type PEAFirst -> type attendu par le modèle de PEAdvisor.
TYPES = {"Action": "ACTION", "ETF": "ETF", "OPCVM": "OPCVM"}


def _lire(nom: str) -> list[dict[str, str]]:
    chemin = RACINE / "data" / nom
    if not chemin.exists():
        return []
    with open(chemin, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def _nombre(valeur: Any) -> float | None:
    if valeur is None:
        return None
    texte = str(valeur).strip().replace(",", ".")
    if texte in ("", "-"):
        return None
    try:
        return float(texte)
    except ValueError:
        return None


class SourcePEAFirst(SourceDonnees):
    """Référentiel local produit par la chaîne de données du dépôt."""

    nom = "peafirst"

    def __init__(self, avec_donnees: bool = True, limite: int | None = None):
        # Par défaut on ne remonte que les instruments dotés de cours : peupler
        # la base de 6 188 lignes vides donnerait un tableau de bord trompeur.
        self.avec_donnees = avec_donnees
        self.limite = limite

    def recuperer(self) -> list[dict[str, Any]]:
        base = _lire("base_isin.csv")
        if not base:
            raise FileNotFoundError(
                "data/base_isin.csv introuvable : la source peafirst attend le "
                "référentiel produit par scripts/. Lancer la chaîne de données "
                "ou choisir une autre source dans config/settings.yaml."
            )

        figi = {r["ISIN"]: r for r in _lire("base_isin_figi.csv")}
        marche = {r["ISIN"]: r for r in _lire("base_isin_marche.csv")}
        sri = {r["ISIN"]: r for r in _lire("base_isin_sri.csv")}
        pea_actions = {r["ISIN"]: r for r in _lire("base_isin_actions_pea.csv")}
        pea_fonds = {r["ISIN"]: r for r in _lire("base_isin_fonds_pea.csv")}

        actifs: list[dict[str, Any]] = []
        for r in base:
            isin = r["ISIN"]
            m = marche.get(isin, {})
            if self.avec_donnees and not m.get("Cours"):
                continue

            type_actif = TYPES.get(r["Type"])
            if not type_actif:
                continue

            # L'éligibilité vient des fichiers dédiés. « PROBABLE » et
            # « A_VERIFIER » ne valent pas « éligible » : dans le doute, on ne
            # présente pas un titre comme logeable en PEA.
            statut = (pea_fonds.get(isin, {}).get("PEA_eligible")
                      or pea_actions.get(isin, {}).get("PEA_eligible")
                      or "A_VERIFIER")

            # Un nom OpenFIGI complet vaut mieux qu'un libellé technique
            # Euronext du genre « VANETFV3PLIMETFP ».
            nom_figi = (figi.get(isin, {}).get("Nom_complet") or "").strip()
            nom = nom_figi if len(nom_figi) > len(r["Nom"]) else r["Nom"]

            actifs.append({
                "isin": isin,
                "nom": nom,
                "type": type_actif,
                "mnemonique": (figi.get(isin, {}).get("Ticker")
                               or r.get("Symbole") or ""),
                "marche": (r.get("Marché(s)") or "").split(" | ")[0],
                "devise": r.get("Devise") or "",
                "pays": r.get("Pays_émission") or "",
                "eligible_pea": statut == "OUI",
                "cours": _nombre(m.get("Cours")),
                "volatilite": _nombre(m.get("Volatilite_annualisee_pct")),
                "niveau_risque": _nombre(sri.get(isin, {}).get("SRI_retenu")),
                # Champs sans source gratuite européenne : laissés vides plutôt
                # qu'inventés (voir la docstring du module). PEAdvisor
                # renormalise alors ses pondérations sur les critères présents.
                "score_esg": None,
                "rendement": None,
                "per": None,
                "croissance": None,
                "objectif_cours": None,
                "consensus": None,
            })
            if self.limite and len(actifs) >= self.limite:
                break

        return actifs
