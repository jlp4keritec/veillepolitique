"""Planificateur interne (APScheduler, dans le meme programme que l'API).

Pas d'outil externe : les taches tournent tant que le backend est lance.
"""

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from app.db import session
from app.orchestrateur import Orchestrateur
from app.parametres import lire

log = logging.getLogger("veille")


def _protege(nom, fn):
    def run():
        try:
            fn()
        except Exception:  # une tache en erreur ne doit pas arreter les autres
            log.exception("tache %s en erreur", nom)
    return run


def demarrer(orch: Orchestrateur) -> BackgroundScheduler:
    with session(orch.db_path) as conn:
        minutes = max(1, int(lire(conn, "intervalle_cycle_minutes")))
    sched = BackgroundScheduler(timezone="Europe/Paris", job_defaults={"coalesce": True, "max_instances": 1})
    sched.add_job(_protege("cycle", orch.cycle), "interval", minutes=minutes, id="cycle",
                  next_run_time=datetime.now())
    sched.add_job(_protege("horloge", orch.horloge), "interval", minutes=1, id="horloge")
    sched.add_job(_protege("telegram", orch.ecouter), "interval", seconds=5, id="telegram")
    sched.start()
    log.info("planificateur demarre : cycle toutes les %s min", minutes)
    return sched
