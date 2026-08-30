"""Point d'entrée FastAPI de PEAdvisor.

- crée les tables SQLite au démarrage ;
- charge automatiquement le jeu de données si la base est vide ;
- démarre le planificateur de mises à jour si activé ;
- sert l'API REST (/api/...) et le tableau de bord web (/).

Lancement : `python run.py` puis http://localhost:8000
Documentation interactive de l'API : http://localhost:8000/docs
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from peadvisor import __version__
from peadvisor.database import SessionLocal, creer_tables
from peadvisor.models import Actif
from peadvisor.routers import (actifs, administration, allocation, dashboard, meta,
                               recherche, simulation)
from peadvisor.services import scheduler
from peadvisor.services.importer import importer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

DOSSIER_STATIC = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def cycle_de_vie(app: FastAPI):
    creer_tables()
    session = SessionLocal()
    try:
        if session.query(Actif).count() == 0:
            journal = importer(session)
            logging.getLogger("peadvisor").info("Base initialisée : %s", journal.detail)
    finally:
        session.close()
    scheduler.demarrer()
    yield
    scheduler.arreter()


app = FastAPI(
    title="PEAdvisor",
    version=__version__,
    description="Aide à la décision pour l'investissement via un Plan d'Épargne en Actions.",
    lifespan=cycle_de_vie,
)

@app.middleware("http")
async def revalidation_des_assets(request, call_next):
    """Force la revalidation des fichiers statiques (JS/CSS/HTML) pour éviter que
    le navigateur ne serve une ancienne version en cache après une mise à jour."""
    reponse = await call_next(request)
    chemin = request.url.path
    if chemin == "/" or chemin.endswith((".js", ".css", ".html")):
        reponse.headers["Cache-Control"] = "no-cache, must-revalidate"
    return reponse


app.include_router(dashboard.router)
app.include_router(actifs.router)
app.include_router(allocation.router)
app.include_router(simulation.router)
app.include_router(recherche.router)
app.include_router(administration.router)
app.include_router(meta.router)

# Le tableau de bord web est servi à la racine.
app.mount("/", StaticFiles(directory=DOSSIER_STATIC, html=True), name="static")
