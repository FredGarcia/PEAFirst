"""Source locale de démonstration.

Charge `peadvisor/data/seed_assets.json` : un échantillon représentatif
d'actions, d'ETF et d'OPCVM éligibles au PEA, avec des indicateurs
ILLUSTRATIFS (non temps réel) permettant de développer et de tester
l'application sans dépendance réseau.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from peadvisor.sources.base import SourceDonnees

CHEMIN_SEED = Path(__file__).resolve().parent.parent / "data" / "seed_assets.json"


class SourceSeed(SourceDonnees):
    nom = "seed"

    def recuperer(self) -> list[dict[str, Any]]:
        with open(CHEMIN_SEED, encoding="utf-8") as f:
            return json.load(f)
