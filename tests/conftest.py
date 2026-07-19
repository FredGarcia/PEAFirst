"""Fixtures de test : base SQLite en mémoire, isolée de la base applicative."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import peadvisor.database as database
from peadvisor.database import Base


@pytest.fixture()
def session(monkeypatch):
    engine = create_engine("sqlite://")
    fabrique = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", fabrique)
    from peadvisor import models  # noqa: F401

    Base.metadata.create_all(engine)
    s = fabrique()
    yield s
    s.close()
