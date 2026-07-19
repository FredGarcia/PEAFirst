"""Modèle de données (SQLAlchemy).

Tables :
- actifs            : référentiel des valeurs éligibles au PEA (clé métier : ISIN)
- historique_scores : trace des scores calculés à chaque mise à jour
- journal_maj       : journal des traitements (import, scoring, erreurs)
- watchlist         : valeurs suivies par l'utilisateur
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from peadvisor.database import Base


class TypeActif(str, enum.Enum):
    ACTION = "ACTION"
    ETF = "ETF"
    OPCVM = "OPCVM"


class Actif(Base):
    __tablename__ = "actifs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Identité
    nom: Mapped[str] = mapped_column(String(120))
    isin: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    mnemonique: Mapped[str | None] = mapped_column(String(20), index=True)
    type: Mapped[TypeActif] = mapped_column(Enum(TypeActif), index=True)
    marche: Mapped[str | None] = mapped_column(String(60))
    devise: Mapped[str | None] = mapped_column(String(3), default="EUR")
    pays: Mapped[str | None] = mapped_column(String(40))
    secteur: Mapped[str | None] = mapped_column(String(60))
    eligible_pea: Mapped[bool] = mapped_column(default=True)
    eligible_pea_pme: Mapped[bool] = mapped_column(default=False)
    societe_gestion: Mapped[str | None] = mapped_column(String(80))

    # Données de marché
    capitalisation: Mapped[float | None] = mapped_column(Float)  # en M€
    cours: Mapped[float | None] = mapped_column(Float)
    date_cours: Mapped[datetime | None] = mapped_column(DateTime)

    # Indicateurs
    rendement: Mapped[float | None] = mapped_column(Float)        # dividende, en %
    per: Mapped[float | None] = mapped_column(Float)
    croissance: Mapped[float | None] = mapped_column(Float)       # en %
    volatilite: Mapped[float | None] = mapped_column(Float)       # annualisée, en %
    niveau_risque: Mapped[int | None] = mapped_column(Integer)    # 1 à 7 (SRI)
    score_esg: Mapped[float | None] = mapped_column(Float)        # 0 à 100
    objectif_cours: Mapped[float | None] = mapped_column(Float)
    potentiel: Mapped[float | None] = mapped_column(Float)        # en %, calculé
    consensus: Mapped[float | None] = mapped_column(Float)        # 1 (vente) à 5 (achat fort)

    # Scores calculés (0 à 100)
    score_global: Mapped[float | None] = mapped_column(Float, index=True)
    sous_scores: Mapped[str | None] = mapped_column(Text)  # JSON des sous-notes

    # Traçabilité
    source: Mapped[str | None] = mapped_column(String(40))
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    maj_le: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    historique_scores: Mapped[list["HistoriqueScore"]] = relationship(back_populates="actif")


class HistoriqueScore(Base):
    __tablename__ = "historique_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actif_id: Mapped[int] = mapped_column(ForeignKey("actifs.id"), index=True)
    date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    score_global: Mapped[float] = mapped_column(Float)
    cours: Mapped[float | None] = mapped_column(Float)

    actif: Mapped[Actif] = relationship(back_populates="historique_scores")


class JournalMaj(Base):
    __tablename__ = "journal_maj"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    traitement: Mapped[str] = mapped_column(String(60))   # ex : "import", "scoring"
    statut: Mapped[str] = mapped_column(String(20))       # "succes" | "erreur" | "avertissement"
    detail: Mapped[str | None] = mapped_column(Text)
    nb_crees: Mapped[int] = mapped_column(Integer, default=0)
    nb_maj: Mapped[int] = mapped_column(Integer, default=0)
    nb_doublons: Mapped[int] = mapped_column(Integer, default=0)
    nb_erreurs: Mapped[int] = mapped_column(Integer, default=0)


class ElementWatchlist(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actif_id: Mapped[int] = mapped_column(ForeignKey("actifs.id"), unique=True)
    ajoute_le: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    commentaire: Mapped[str | None] = mapped_column(Text)

    actif: Mapped[Actif] = relationship()
