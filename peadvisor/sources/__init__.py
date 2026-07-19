"""Connecteurs de données (niveau L1 — Collecte).

Chaque source implémente `SourceDonnees.recuperer()` et renvoie une liste
de dictionnaires normalisés. Pour ajouter une source (Boursorama, EOD, etc.),
créer un module qui hérite de `SourceDonnees` et l'enregistrer dans REGISTRE.
"""

from peadvisor.sources.base import SourceDonnees
from peadvisor.sources.seed import SourceSeed
from peadvisor.sources.yahoo import SourceYahoo

REGISTRE: dict[str, type[SourceDonnees]] = {
    "seed": SourceSeed,
    "yahoo": SourceYahoo,
}
