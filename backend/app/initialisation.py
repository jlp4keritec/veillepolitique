"""Initialisation idempotente : schema, parametres, themes, sources."""

import json
from pathlib import Path

from app.config import get_settings
from app.db import init_schema, session
from app.parametres import seed_parametres
from app.sources import seed_sources


def initialiser(db_path: Path | None = None, avec_sources: bool = True) -> dict:
    s = get_settings()
    db_path = db_path or s.db_path
    init_schema(db_path)
    with session(db_path) as conn:
        nouveau_budget = conn.execute(
            "SELECT 1 FROM parametres WHERE cle = 'budget_mensuel_eur'").fetchone() is None
        n_params = seed_parametres(conn)
        if nouveau_budget:  # premier lancement : budget repris du .env
            conn.execute("UPDATE parametres SET valeur = ? WHERE cle = 'budget_mensuel_eur'",
                         (json.dumps(s.budget_mensuel_eur),))
    n_sources = seed_sources(db_path) if avec_sources else 0
    return {"parametres_ajoutes": n_params, "sources_ajoutees": n_sources}
