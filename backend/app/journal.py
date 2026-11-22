"""Journal des traitements et erreurs (table journal + console)."""

import logging
import sqlite3

from app.util import to_iso, utcnow

log = logging.getLogger("veille")


def ecrire(conn: sqlite3.Connection, niveau: str, composant: str, message: str) -> None:
    message = message[:2000]
    getattr(log, {"ERREUR": "error", "ALERTE": "warning"}.get(niveau, "info"))(
        "[%s] %s", composant, message)
    conn.execute(
        "INSERT INTO journal (horodatage, niveau, composant, message) VALUES (?,?,?,?)",
        (to_iso(utcnow()), niveau, composant, message),
    )
