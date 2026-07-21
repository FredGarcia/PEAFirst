"""Modèle de données (SQLAlchemy).

Tables :
- actifs            : référentiel des valeurs éligibles au PEA (clé métier : ISIN)
- historique_scores : trace des scores calculés à chaque mise à jour
- journal_maj       : journal des traitements (import, scoring, erreurs)
- watchlist         : valeurs suivies par l'utilisateur
"""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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
    variation_pct: Mapped[float | None] = mapped_column(Float)    # variation du jour, en %
    volume: Mapped[float | None] = mapped_column(Float)           # volume échangé du jour
    per: Mapped[float | None] = mapped_column(Float)

    # Fondamentaux et technique étendus (scraping Boursorama)
    ouverture: Mapped[float | None] = mapped_column(Float)
    plus_haut: Mapped[float | None] = mapped_column(Float)
    plus_bas: Mapped[float | None] = mapped_column(Float)
    cloture_veille: Mapped[float | None] = mapped_column(Float)
    haut_52s: Mapped[float | None] = mapped_column(Float)
    bas_52s: Mapped[float | None] = mapped_column(Float)
    quantite_echangee: Mapped[float | None] = mapped_column(Float)
    nb_titres: Mapped[float | None] = mapped_column(Float)
    bna: Mapped[float | None] = mapped_column(Float)
    dividende: Mapped[float | None] = mapped_column(Float)
    taux_distribution: Mapped[float | None] = mapped_column(Float)
    dette_nette: Mapped[float | None] = mapped_column(Float)      # M€
    ca: Mapped[float | None] = mapped_column(Float)              # M€
    nb_analystes: Mapped[float | None] = mapped_column(Float)
    date_cotation: Mapped[str | None] = mapped_column(String(20))
    heure_cotation: Mapped[str | None] = mapped_column(String(20))
    croissance: Mapped[float | None] = mapped_column(Float)       # en %
    volatilite: Mapped[float | None] = mapped_column(Float)       # annualisée, en %
    niveau_risque: Mapped[int | None] = mapped_column(Integer)    # 1 à 7 (SRI)
    score_esg: Mapped[float | None] = mapped_column(Float)        # 0 à 100 (haut = mieux)
    risque_esg: Mapped[float | None] = mapped_column(Float)       # 0 à 100 (bas = mieux, ESG Sustainalytics)
    objectif_cours: Mapped[float | None] = mapped_column(Float)
    potentiel: Mapped[float | None] = mapped_column(Float)        # en %, calculé
    consensus: Mapped[float | None] = mapped_column(Float)        # 1 (vente) à 5 (achat fort)

    # Scores calculés (0 à 100)
    score_global: Mapped[float | None] = mapped_column(Float, index=True)
    sous_scores: Mapped[str | None] = mapped_column(Text)  # JSON des sous-notes

    # Indicateurs du moteur quantitatif (JSON : perf_1an, drawdown_max,
    # sharpe, sortino, var_95, volatilite calculée...), issus de l'historique.
    indicateurs_quant: Mapped[str | None] = mapped_column(Text)

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


class HistoriqueCours(Base):
    """Série de cours quotidiens d'un actif (alimente le moteur quantitatif)."""

    __tablename__ = "historique_cours"
    __table_args__ = (UniqueConstraint("actif_id", "date", name="uq_cours_actif_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actif_id: Mapped[int] = mapped_column(ForeignKey("actifs.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    cours: Mapped[float] = mapped_column(Float)


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


class RapportSysteme(Base):
    """Instantané d'auto-diagnostic (couche de second ordre)."""

    __tablename__ = "rapports_systeme"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    contenu: Mapped[str] = mapped_column(Text)  # rapport complet en JSON


class Anomalie(Base):
    """Anomalie détectée par l'auto-observation (donnée incohérente, dérive...)."""

    __tablename__ = "anomalies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    actif_id: Mapped[int | None] = mapped_column(ForeignKey("actifs.id"), index=True)
    type: Mapped[str] = mapped_column(String(40), index=True)
    gravite: Mapped[str] = mapped_column(String(15))  # "info" | "avertissement" | "critique"
    message: Mapped[str] = mapped_column(Text)
    statut: Mapped[str] = mapped_column(String(15), default="ouverte")  # "ouverte" | "ignoree" | "resolue"

    actif: Mapped[Actif | None] = relationship()


class SuggestionPonderations(Base):
    """Pondérations optimisées proposées par l'auto-amélioration."""

    __tablename__ = "suggestions_ponderations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    ponderations: Mapped[str] = mapped_column(Text)  # JSON critère → poids
    correlation_avant: Mapped[float | None] = mapped_column(Float)
    correlation_apres: Mapped[float | None] = mapped_column(Float)
    statut: Mapped[str] = mapped_column(String(15), default="proposee")  # "proposee" | "appliquee" | "rejetee"
    commentaire: Mapped[str | None] = mapped_column(Text)


class ElementWatchlist(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actif_id: Mapped[int] = mapped_column(ForeignKey("actifs.id"), unique=True)
    ajoute_le: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    commentaire: Mapped[str | None] = mapped_column(Text)

    actif: Mapped[Actif] = relationship()
