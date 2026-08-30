"""Interface commune des sources de données."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SourceDonnees(ABC):
    """Une source renvoie des actifs normalisés sous forme de dictionnaires.

    Champs attendus (les champs manquants sont tolérés) :
    nom, isin, mnemonique, type, marche, devise, pays, secteur,
    eligible_pea, eligible_pea_pme, societe_gestion, capitalisation,
    cours, rendement, per, croissance, volatilite, niveau_risque,
    score_esg, objectif_cours, consensus.
    """

    nom: str = "abstraite"

    @abstractmethod
    def recuperer(self) -> list[dict[str, Any]]:
        """Récupère la liste des actifs. Peut lever une exception réseau."""
