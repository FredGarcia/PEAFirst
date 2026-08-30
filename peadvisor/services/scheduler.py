"""Automatisation des mises à jour (cahier des charges §7).

Utilise APScheduler : si `mise_a_jour.automatique` est activé dans
config/settings.yaml, un import complet est planifié chaque jour (ou chaque
lundi en mode hebdomadaire) à l'heure configurée. Chaque exécution est
journalisée dans la table journal_maj, y compris en cas d'erreur.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from peadvisor.config import charger_settings
from peadvisor.database import SessionLocal
from peadvisor.services.importer import importer

logger = logging.getLogger("peadvisor.scheduler")
_scheduler: BackgroundScheduler | None = None


def _tache_mise_a_jour() -> None:
    session = SessionLocal()
    try:
        journal = importer(session)
        logger.info("Mise à jour planifiée terminée : %s (%s)", journal.detail, journal.statut)
        # Couche de second ordre : le système s'observe (et s'optimise si configuré)
        # après chaque mise à jour planifiée.
        if charger_settings().get("meta", {}).get("observer_apres_maj", True):
            from peadvisor.services.amelioration import cycle_second_ordre

            resultat = cycle_second_ordre(session)
            logger.info("Auto-diagnostic : %s", resultat.get("optimisation"))
    finally:
        session.close()


def demarrer() -> BackgroundScheduler | None:
    """Démarre le planificateur si la mise à jour automatique est activée."""
    global _scheduler
    cfg = charger_settings()["mise_a_jour"]
    if not cfg.get("automatique", False):
        logger.info("Mise à jour automatique désactivée (config/settings.yaml).")
        return None

    heure, minute = (cfg.get("heure") or "07:30").split(":")
    if cfg.get("frequence", "quotidienne") == "hebdomadaire":
        declencheur = CronTrigger(day_of_week="mon", hour=int(heure), minute=int(minute))
    else:
        declencheur = CronTrigger(hour=int(heure), minute=int(minute))

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(_tache_mise_a_jour, declencheur, id="maj_donnees", replace_existing=True)
    _scheduler.start()
    logger.info("Planificateur démarré (%s à %s).", cfg.get("frequence"), cfg.get("heure"))
    return _scheduler


def arreter() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
