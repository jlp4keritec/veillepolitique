"""Reapplique les regles actuelles aux articles recents (idempotent).

Usage : python scripts/reclasser.py [jours]      (defaut : 3 jours)

- Ne touche JAMAIS un evenement qui a deja fait l'objet d'une alerte (historique conserve).
- Les autres articles recents sont reclasses et regroupes a nouveau ; les evenements
  devenus vides sont supprimes. Les propositions IA deja faites ne sont pas refaites.
"""

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.analyse import analyser, evenements_recents  # noqa: E402
from app.classification import classer_nouveaux  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import session  # noqa: E402
from app.initialisation import initialiser  # noqa: E402
from app.regroupement import regrouper_nouveaux  # noqa: E402
from app.util import to_iso, utcnow  # noqa: E402


def reclasser(db_path: Path, jours: int = 3) -> dict:
    initialiser(db_path, avec_sources=False)
    now = utcnow()
    with session(db_path) as conn:
        depuis = to_iso(now - timedelta(days=jours))
        proteges = {r[0] for r in conn.execute(
            "SELECT DISTINCT evenement_id FROM notifications WHERE type = 'alerte' AND evenement_id IS NOT NULL")}
        arts = [r["id"] for r in conn.execute(
            "SELECT id, evenement_id FROM articles WHERE publie_le >= ?", (depuis,))
            if r["evenement_id"] not in proteges]
        conn.executemany("UPDATE articles SET pertinent = NULL, evenement_id = NULL WHERE id = ?",
                         [(i,) for i in arts])
        supprimes = conn.execute(
            "DELETE FROM evenements WHERE notifie = 0 AND id NOT IN "
            "(SELECT DISTINCT evenement_id FROM articles WHERE evenement_id IS NOT NULL)").rowcount
        pert, ecart = classer_nouveaux(conn)
        touches = regrouper_nouveaux(conn)
        analyser(conn, set(evenements_recents(conn, now, 24 * jours)) | touches, now)
        nb_evt = conn.execute("SELECT COUNT(*) FROM evenements WHERE dernier_article_le >= ?", (depuis,)).fetchone()[0]
    return {"articles": len(arts), "pertinents": pert, "ecartes": ecart,
            "evenements_supprimes": supprimes, "evenements": nb_evt}


if __name__ == "__main__":
    j = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    r = reclasser(get_settings().db_path, j)
    print(f"[OK] {r['articles']} article(s) reclasse(s) : {r['pertinents']} pertinent(s), {r['ecartes']} ecarte(s) ; "
          f"{r['evenements']} evenement(s) sur {j} jour(s).")
