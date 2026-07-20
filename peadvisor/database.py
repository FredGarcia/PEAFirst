"""Connexion SQLite et session SQLAlchemy."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from peadvisor.config import CHEMIN_BDD

engine = create_engine(f"sqlite:///{CHEMIN_BDD}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_session():
    """Dépendance FastAPI : fournit une session par requête."""
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def creer_tables() -> None:
    from peadvisor import models  # noqa: F401 — enregistre les modèles

    Base.metadata.create_all(engine)

    # Mini-migration : create_all ne modifie pas les tables existantes ;
    # on ajoute les colonnes apparues depuis la création de la base.
    with engine.begin() as conn:
        colonnes = [ligne[1] for ligne in conn.exec_driver_sql("PRAGMA table_info(actifs)")]
        for nom, type_sql in (("indicateurs_quant", "TEXT"),
                              ("variation_pct", "FLOAT"),
                              ("volume", "FLOAT")):
            if nom not in colonnes:
                conn.exec_driver_sql(f"ALTER TABLE actifs ADD COLUMN {nom} {type_sql}")
