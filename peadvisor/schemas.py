"""Schémas Pydantic exposés par l'API REST."""

from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ActifOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nom: str
    isin: str
    mnemonique: str | None = None
    type: str
    marche: str | None = None
    devise: str | None = None
    pays: str | None = None
    secteur: str | None = None
    eligible_pea: bool = True
    eligible_pea_pme: bool = False
    societe_gestion: str | None = None
    capitalisation: float | None = None
    cours: float | None = None
    date_cours: datetime | None = None
    rendement: float | None = None
    per: float | None = None
    croissance: float | None = None
    volatilite: float | None = None
    niveau_risque: int | None = None
    score_esg: float | None = None
    objectif_cours: float | None = None
    potentiel: float | None = None
    consensus: float | None = None
    score_global: float | None = None
    indicateurs_quant: dict | None = None
    source: str | None = None
    maj_le: datetime | None = None

    @field_validator("indicateurs_quant", mode="before")
    @classmethod
    def _json_vers_dict(cls, valeur):
        return json.loads(valeur) if isinstance(valeur, str) else valeur


class DemandeAllocation(BaseModel):
    capital: float = Field(gt=0, description="Capital à investir en euros")
    niveau_risque: int = Field(ge=1, le=7, description="Profil de risque de 1 (prudent) à 7 (offensif)")
    horizon_annees: int = Field(ge=1, le=40, description="Horizon d'investissement en années")
    objectif: str = Field(pattern="^(croissance|dividendes|equilibre)$")


class LigneAllocation(BaseModel):
    isin: str
    nom: str
    type: str
    secteur: str | None
    poids: float          # part du capital (0-1)
    montant: float        # en euros
    score_global: float | None
    niveau_risque: int | None
    justification: str


class ReponseAllocation(BaseModel):
    capital: float
    niveau_risque: int
    horizon_annees: int
    objectif: str
    repartition_types: dict[str, float]
    lignes: list[LigneAllocation]
    commentaire: str


class LigneClassement(BaseModel):
    isin: str
    nom: str
    type: str
    rang: int
    valeur: float         # score pondéré ou coefficient TOPSIS


class ElementWatchlistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ajoute_le: datetime
    commentaire: str | None = None
    actif: ActifOut


class JournalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: datetime
    traitement: str
    statut: str
    detail: str | None
    nb_crees: int
    nb_maj: int
    nb_doublons: int
    nb_erreurs: int
