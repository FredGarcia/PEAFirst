"""Cohérence entre les colonnes déclarées et les champs réellement écrits.

Un `csv.DictWriter` lève `ValueError` dès qu'on lui passe une clé absente de
`fieldnames` — mais seulement à l'exécution, une fois la collecte terminée.
C'est exactement ce qui s'est produit : l'ajout de l'asymétrie et de
l'aplatissement avait modifié l'écriture sans modifier la liste `COLONNES`, et
le script échouait après avoir consommé son quota d'appels.

Ces tests lisent le code source plutôt que d'exécuter les scripts : ils n'ont
besoin ni de réseau, ni de clé, ni de données collectées.
"""

from __future__ import annotations

import ast
import csv
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
SCRIPTS = RACINE / "scripts"

# Script -> nom de la constante listant les colonnes du fichier produit.
DECLARATIONS = {
    "enrich_marche.py": "COLONNES",
    "scoring.py": "COLONNES",
    "anomalies.py": "COLONNES",
    "historique.py": "COLONNES",
    "sri.py": "COLONNES",
    "enrich_pea_actions.py": "COLONNES",
    "enrich_potentiel.py": "COLONNES",
}


def _colonnes_declarees(arbre, nom):
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Assign):
            for cible in noeud.targets:
                if isinstance(cible, ast.Name) and cible.id == nom:
                    try:
                        return list(ast.literal_eval(noeud.value))
                    except (ValueError, TypeError):
                        return None
    return None


def _cles_ecrites(arbre):
    """Clés littérales des dictionnaires passés à writerow/writerows."""
    cles = set()
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Call):
            continue
        fonction = noeud.func
        if not isinstance(fonction, ast.Attribute):
            continue
        if fonction.attr not in ("writerow", "writerows"):
            continue
        for argument in noeud.args:
            dictionnaires = ([argument] if isinstance(argument, ast.Dict)
                             else [e for e in ast.walk(argument)
                                   if isinstance(e, ast.Dict)])
            for d in dictionnaires:
                for cle in d.keys:
                    if isinstance(cle, ast.Constant) and isinstance(cle.value, str):
                        cles.add(cle.value)
    return cles


@pytest.mark.parametrize("script,constante", sorted(DECLARATIONS.items()))
def test_champs_ecrits_tous_declares(script, constante):
    chemin = SCRIPTS / script
    if not chemin.exists():
        pytest.skip(f"{script} absent")
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    colonnes = _colonnes_declarees(arbre, constante)
    if colonnes is None:
        pytest.skip(f"{script} : {constante} non littérale")
    manquants = sorted(_cles_ecrites(arbre) - set(colonnes))
    assert not manquants, (
        f"{script} écrit des champs absents de {constante} : {manquants}. "
        "csv.DictWriter lèverait ValueError à l'exécution."
    )


@pytest.mark.parametrize("script,constante", sorted(DECLARATIONS.items()))
def test_colonnes_sans_doublon(script, constante):
    chemin = SCRIPTS / script
    if not chemin.exists():
        pytest.skip(f"{script} absent")
    colonnes = _colonnes_declarees(ast.parse(chemin.read_text(encoding="utf-8")),
                                   constante)
    if colonnes is None:
        pytest.skip(f"{script} : {constante} non littérale")
    doublons = [c for c in set(colonnes) if colonnes.count(c) > 1]
    assert not doublons, f"{script} : colonnes en double {doublons}"


def test_fichiers_produits_conformes_a_leur_entete():
    """Chaque CSV de data/ a un nombre de colonnes constant.

    Une ligne plus courte ou plus longue que l'en-tête passe inaperçue à la
    lecture — les champs se décalent silencieusement.
    """
    for chemin in sorted((RACINE / "data").glob("*.csv")):
        with open(chemin, encoding="utf-8") as f:
            lignes = list(csv.reader(f, delimiter=";"))
        if not lignes:
            continue
        attendu = len(lignes[0])
        irregulieres = [n for n, l in enumerate(lignes[1:], 2)
                        if l and len(l) != attendu]
        assert not irregulieres, (
            f"{chemin.name} : {len(irregulieres)} ligne(s) au nombre de colonnes "
            f"inattendu (attendu {attendu}), d'abord la ligne {irregulieres[0]}"
        )
