"""Exécution des scripts de la chaîne de données depuis l'interface.

Ce routeur n'exécute **jamais** une commande arbitraire. Chaque script et
chaque paramètre sont déclarés dans le catalogue ci-dessous ; une valeur qui ne
correspond pas au type ou à la liste de choix attendus est refusée avant tout
appel. Les arguments sont passés sous forme de liste à `subprocess`, sans
interpréteur de commandes : une valeur ne peut donc pas s'échapper en commande.

Protection contre les requêtes croisées
---------------------------------------
L'application écoute sur 127.0.0.1, mais un site visité dans le même navigateur
pourrait tout de même y adresser une requête. L'en-tête `X-PEAdvisor` est donc
exigé : un formulaire distant ne peut pas l'ajouter sans déclencher une requête
préalable de contrôle, que l'application refuse faute d'en-têtes CORS. Le
tableau de bord, servi depuis la même origine, l'envoie sans difficulté.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from peadvisor.config import charger_cles

router = APIRouter(prefix="/api/scripts", tags=["Scripts"])

RACINE = Path(__file__).resolve().parents[2]
DELAI_MAX = 900  # 15 minutes : une collecte complète peut être longue


def _p(nom: str, type_: str, defaut: Any = None, choix: list[str] | None = None,
       aide: str = "", drapeau: bool = False) -> dict[str, Any]:
    return {"nom": nom, "type": type_, "defaut": defaut, "choix": choix,
            "aide": aide, "drapeau": drapeau}


# Catalogue : seuls ces scripts et ces paramètres sont acceptés.
CATALOGUE: dict[str, dict[str, Any]] = {
    "validate_base": {
        "script": "validate_base.py",
        "titre": "Vérifier l'intégrité du référentiel",
        "aide": "Schéma, cohérence des sous-fichiers. Aucun appel réseau.",
        "cle": None,
        "parametres": [],
    },
    "enrich_marche": {
        "script": "enrich_marche.py",
        "titre": "Collecter cours et indicateurs",
        "aide": "Volatilité, drawdown, Sharpe, Sortino. Quota EODHD : 20/jour.",
        "cle": "eodhd",
        "parametres": [
            _p("etat", "bool", False, aide="avancement seul, sans appel", drapeau=True),
            _p("historique", "bool", True, aide="collecter l'historique", drapeau=True),
            _p("filtre", "choix", "pea", ["pea", "actions", "etf", "tout"]),
            _p("limite", "entier", 18, aide="0 = sans limite"),
            _p("rafraichir", "entier", 10, aide="réinterroger les cours de plus de N jours"),
            _p("source", "choix", "eodhd", ["eodhd", "marketstack"]),
            _p("isins", "texte", "", aide="ISIN séparés par des virgules"),
        ],
    },
    "scoring": {
        "script": "scoring.py",
        "titre": "Recalculer les scores",
        "aide": "Rang percentile par type, pondérations de scoring_params.json.",
        "cle": None,
        "parametres": [
            _p("top", "entier", 15, aide="afficher les N meilleurs"),
            _p("type", "choix", "", ["", "Action", "ETF", "OPCVM"]),
            _p("min-couverture", "entier", 30, aide="couverture minimale du barème"),
        ],
    },
    "sri": {
        "script": "sri.py",
        "titre": "Estimer l'indicateur de risque SRI",
        "aide": "Bornes PRIIPS. Un SRI officiel relevé sur DIC prime.",
        "cle": None,
        "parametres": [
            _p("resume", "bool", True, drapeau=True),
            _p("horizon", "entier", 5, aide="période de détention en années"),
        ],
    },
    "anomalies": {
        "script": "anomalies.py",
        "titre": "Détecter les anomalies",
        "aide": "Série courte, volatilité extrême, Sharpe aberrant, cours périmé.",
        "cle": None,
        "parametres": [
            _p("resume", "bool", True, drapeau=True),
            _p("seuil-fraicheur", "entier", 7, aide="âge au-delà duquel un cours est périmé"),
        ],
    },
    "historique": {
        "script": "historique.py",
        "titre": "Enregistrer la progression",
        "aide": "Un relevé par jour : notés, couverture, cours périmés.",
        "cle": None,
        "parametres": [
            _p("reconstruire", "bool", False, aide="amorcer depuis l'historique Git",
               drapeau=True),
        ],
    },
    "enrich_pea_actions": {
        "script": "enrich_pea_actions.py",
        "titre": "Recalculer l'éligibilité PEA des actions",
        "aide": "Régime foncier, nature, pays, corrections utilisateur.",
        "cle": None,
        "parametres": [
            _p("resume", "bool", True, drapeau=True),
            _p("a-verifier", "bool", False, aide="lister les titres à vérifier",
               drapeau=True),
        ],
    },
    "enrich_pea": {
        "script": "enrich_pea.py",
        "titre": "Recalculer l'éligibilité PEA des fonds",
        "aide": "Relevés émetteurs, nom, classe d'actifs, pays.",
        "cle": None,
        "parametres": [],
    },
    "enrich_potentiel": {
        "script": "enrich_potentiel.py",
        "titre": "Collecter potentiel et fondamentaux",
        "aide": "Potentiel, PER, consensus, ESG. Porte la couverture à 94 %.",
        "cle": None,
        "parametres": [
            _p("etat", "bool", False, aide="avancement seul", drapeau=True),
            _p("filtre", "choix", "pea", ["pea", "actions", "etf", "tout"]),
            _p("limite", "entier", 25),
            _p("pause", "entier", 2, aide="délai entre appels, en secondes"),
            _p("isins", "texte", "", aide="ISIN séparés par des virgules"),
        ],
    },
    "enrich_openfigi": {
        "script": "enrich_openfigi.py",
        "titre": "Enrichir les identifiants OpenFIGI",
        "aide": "FIGI, ticker, nom complet. Avec clé : lots de 100.",
        "cle": "openfigi",
        "parametres": [
            _p("tout", "bool", False, aide="toute la base, actions comprises",
               drapeau=True),
        ],
    },
    "dashboard": {
        "script": "dashboard.py",
        "titre": "Régénérer le tableau de bord",
        "aide": "Reconstruit data/dashboard.html. Recharger la page ensuite.",
        "cle": None,
        "parametres": [
            _p("top", "entier", 12),
            _p("seuil-fraicheur", "entier", 7),
        ],
    },
    "allocation": {
        "script": "allocation.py",
        "titre": "Proposer une allocation",
        "aide": "Bornes PRIIPS, horizon court resserrant le plafond.",
        "cle": None,
        "parametres": [
            _p("capital", "entier", 10000),
            _p("risque", "choix", "5", ["1", "2", "3", "4", "5", "6", "7"]),
            _p("horizon", "entier", 10),
            _p("objectif", "choix", "equilibre",
               ["croissance", "equilibre", "revenus"]),
            _p("lignes", "entier", 10),
            _p("pea-uniquement", "bool", True, drapeau=True),
        ],
    },
    "simulateur": {
        "script": "simulateur.py",
        "titre": "Simuler un plan d'investissement",
        "aide": "Versements programmés, six horizons, fiscalité 2026.",
        "cle": None,
        "parametres": [
            _p("capital", "entier", 10000),
            _p("versement", "entier", 500),
            _p("periodicite", "choix", "trimestriel",
               ["mensuel", "trimestriel", "annuel"]),
            _p("enveloppe", "choix", "pea", ["pea", "cto"]),
            _p("inflation", "entier", 2),
            _p("sequence", "bool", False, aide="effet de l'ordre des rendements",
               drapeau=True),
        ],
    },
}

# Variable d'environnement attendue par chaque script, par nom de clé.
VARIABLES = {
    "eodhd": "EODHD_API_KEY",
    "marketstack": "MARKETSTACK_API_KEY",
    "openfigi": "OPENFIGI_API_KEY",
}


class DemandeExecution(BaseModel):
    parametres: dict[str, Any] = {}


def _verifier_origine(entete: str | None) -> None:
    if entete is None:
        raise HTTPException(
            403,
            "En-tête X-PEAdvisor absent. Cette route n'est appelable que depuis "
            "le tableau de bord servi par l'application, ou en ligne de "
            "commande.",
        )


def _construire_arguments(definition: dict[str, Any],
                          fournis: dict[str, Any]) -> list[str]:
    """Traduit les paramètres reçus en arguments, en refusant tout le reste."""
    specs = {p["nom"]: p for p in definition["parametres"]}
    inconnus = sorted(set(fournis) - set(specs))
    if inconnus:
        raise HTTPException(400, f"Paramètre(s) inconnu(s) : {inconnus}")

    arguments: list[str] = []
    for nom, spec in specs.items():
        if nom not in fournis:
            continue
        valeur = fournis[nom]

        if spec["type"] == "bool":
            if not isinstance(valeur, bool):
                raise HTTPException(400, f"« {nom} » attend un booléen")
            if valeur:
                arguments.append(f"--{nom}")
            continue

        if valeur in ("", None):
            continue

        if spec["type"] == "entier":
            try:
                valeur = int(valeur)
            except (TypeError, ValueError):
                raise HTTPException(400, f"« {nom} » attend un entier")
            arguments += [f"--{nom}", str(valeur)]
            continue

        if spec["type"] == "choix":
            if str(valeur) not in (spec["choix"] or []):
                raise HTTPException(
                    400, f"« {nom} » : valeur refusée, attendu {spec['choix']}")
            arguments += [f"--{nom}", str(valeur)]
            continue

        # Texte libre : un seul usage, les listes d'ISIN. Le format est donc
        # contraint plutôt que laissé ouvert.
        texte = str(valeur).strip()
        if not all(c.isalnum() or c in ",-" for c in texte):
            raise HTTPException(
                400, f"« {nom} » : seuls les caractères alphanumériques, la "
                     "virgule et le tiret sont acceptés")
        if len(texte) > 2000:
            raise HTTPException(400, f"« {nom} » : valeur trop longue")
        arguments += [f"--{nom}", texte]
    return arguments


@router.get("")
def catalogue(x_peadvisor: str | None = Header(default=None)):
    """Scripts exécutables et leurs paramètres."""
    _verifier_origine(x_peadvisor)
    cles = charger_cles()
    sortie = []
    for identifiant, d in CATALOGUE.items():
        besoin = d["cle"]
        variable = VARIABLES.get(besoin) if besoin else None
        disponible = bool(cles.get(besoin) or (variable and os.environ.get(variable)))
        sortie.append({
            "id": identifiant,
            "titre": d["titre"],
            "aide": d["aide"],
            "script": d["script"],
            "cle_requise": besoin,
            "cle_disponible": disponible if besoin else True,
            "parametres": d["parametres"],
        })
    return sortie


@router.post("/{identifiant}/executer")
def executer(identifiant: str, demande: DemandeExecution,
             x_peadvisor: str | None = Header(default=None)):
    """Exécute un script du catalogue et renvoie sa sortie."""
    _verifier_origine(x_peadvisor)
    definition = CATALOGUE.get(identifiant)
    if definition is None:
        raise HTTPException(404, f"Script « {identifiant} » hors catalogue")

    chemin = RACINE / "scripts" / definition["script"]
    if not chemin.exists():
        raise HTTPException(404, f"{definition['script']} introuvable")

    arguments = _construire_arguments(definition, demande.parametres)

    # Les clés configurées dans l'application sont transmises aux scripts, qui
    # les lisent dans l'environnement. Elles ne transitent jamais par la page.
    environnement = dict(os.environ)
    for nom_cle, variable in VARIABLES.items():
        valeur = charger_cles().get(nom_cle)
        if valeur and not environnement.get(variable):
            environnement[variable] = valeur

    debut = time.monotonic()
    try:
        resultat = subprocess.run(
            [sys.executable, str(chemin), *arguments],
            cwd=RACINE, capture_output=True, text=True,
            timeout=DELAI_MAX, env=environnement,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(
            504, f"{definition['script']} interrompu après {DELAI_MAX} s")

    return {
        "script": definition["script"],
        "commande": " ".join(["python", f"scripts/{definition['script']}",
                              *arguments]),
        "code": resultat.returncode,
        "succes": resultat.returncode == 0,
        "duree_s": round(time.monotonic() - debut, 1),
        "sortie": resultat.stdout[-20000:],
        "erreurs": resultat.stderr[-4000:],
    }
