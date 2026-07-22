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

    # Reprise d'une migration interrompue : restaure « actifs » depuis
    # « actifs_old » si le renommage a réussi sans que la table ait été recréée.
    with engine.begin() as conn:
        tables = {r[0] for r in conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "actifs_old" in tables and "actifs" not in tables:
            conn.exec_driver_sql("ALTER TABLE actifs_old RENAME TO actifs")

    Base.metadata.create_all(engine)

    # Migration : identité métier (ISIN, source). Si l'ancien index unique sur
    # ISIN seul subsiste (bases créées avant), reconstruire la table pour le
    # remplacer par la contrainte composite (ISIN, source).
    with engine.begin() as conn:
        index = conn.exec_driver_sql("PRAGMA index_list(actifs)").fetchall()

        def _colonnes_index(nom_index: str) -> list[str]:
            return [r[2] for r in conn.exec_driver_sql(
                f"PRAGMA index_info('{nom_index}')").fetchall()]

        uniques = [_colonnes_index(r[1]) for r in index if r[2]]
        if ["isin"] in uniques and ["isin", "source"] not in uniques:
            colonnes = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(actifs)")]
            liste = ", ".join(colonnes)
            # Libère les noms d'index explicites (ix_actifs_*) avant de recréer la
            # table : ils seraient sinon en conflit lors du CREATE INDEX.
            for r in index:
                if not str(r[1]).startswith("sqlite_autoindex"):
                    conn.exec_driver_sql(f'DROP INDEX IF EXISTS "{r[1]}"')
            # legacy_alter_table=ON : le renommage ne réécrit pas les clés
            # étrangères des tables enfant (elles continuent de viser « actifs »).
            conn.exec_driver_sql("PRAGMA legacy_alter_table=ON")
            conn.exec_driver_sql("ALTER TABLE actifs RENAME TO actifs_old")
            conn.exec_driver_sql("PRAGMA legacy_alter_table=OFF")
            models.Actif.__table__.create(conn)
            conn.exec_driver_sql(f"INSERT INTO actifs ({liste}) SELECT {liste} FROM actifs_old")
            conn.exec_driver_sql("DROP TABLE actifs_old")

    # Mini-migration : create_all ne modifie pas les tables existantes ;
    # on ajoute les colonnes apparues depuis la création de la base.
    with engine.begin() as conn:
        colonnes = [ligne[1] for ligne in conn.exec_driver_sql("PRAGMA table_info(actifs)")]
        nouvelles = [
            ("indicateurs_quant", "TEXT"), ("variation_pct", "FLOAT"),
            ("volume", "FLOAT"), ("risque_esg", "FLOAT"),
            ("ouverture", "FLOAT"), ("plus_haut", "FLOAT"), ("plus_bas", "FLOAT"),
            ("cloture_veille", "FLOAT"), ("haut_52s", "FLOAT"), ("bas_52s", "FLOAT"),
            ("quantite_echangee", "FLOAT"), ("nb_titres", "FLOAT"), ("bna", "FLOAT"),
            ("dividende", "FLOAT"), ("taux_distribution", "FLOAT"),
            ("dette_nette", "FLOAT"), ("ca", "FLOAT"), ("nb_analystes", "FLOAT"),
            ("date_cotation", "VARCHAR(20)"), ("heure_cotation", "VARCHAR(20)"),
            ("source_url", "VARCHAR(400)"),
        ]
        for nom, type_sql in nouvelles:
            if nom not in colonnes:
                conn.exec_driver_sql(f"ALTER TABLE actifs ADD COLUMN {nom} {type_sql}")
