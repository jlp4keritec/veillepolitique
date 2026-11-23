"""Conservation et entretien de la base (regles de J).

Garde pour TOUJOURS : evenements, syntheses, alertes, photos du Journal, couts, avis IA, historique des reglages.
Allege apres N mois : le TEXTE des extraits d'articles (titre, lien, source, date, classement et resume IA gardes).
Purge apres N jours : le journal technique (messages de fonctionnement).
Compacte la base une fois par mois (VACUUM) pour rendre la place liberee.
Tache de nuit (heure_entretien), apres la sauvegarde de 03:15.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.db import get_etat, set_etat
from app.parametres import tous
from app.util import from_iso, to_iso

PARIS = ZoneInfo("Europe/Paris")


def alleger(conn: sqlite3.Connection, now: datetime) -> dict:
    p = tous(conn)
    res = {"extraits": 0, "journal": 0}
    mois = int(p["conservation_extraits_mois"])
    if mois > 0:
        limite = to_iso(now - timedelta(days=30 * mois))
        res["extraits"] = conn.execute(
            "UPDATE articles SET texte_extrait = '', texte_norm = '', allege = 1 "
            "WHERE allege = 0 AND collecte_le < ?", (limite,)).rowcount
    jours = int(p["conservation_journal_jours"])
    if jours > 0:
        res["journal"] = conn.execute("DELETE FROM journal WHERE horodatage < ?",
                                      (to_iso(now - timedelta(days=jours)),)).rowcount
    return res


def tache(conn: sqlite3.Connection, now: datetime) -> dict | None:
    """Une fois par nuit, a partir de heure_entretien (Paris). Retourne le bilan ou None."""
    p = tous(conn)
    local = now.astimezone(PARIS)
    h, m = (int(x) for x in p["heure_entretien"].split(":"))
    if local < local.replace(hour=h, minute=m, second=0, microsecond=0):
        return None
    der = get_etat(conn, "dernier_entretien_le")
    if der and from_iso(der).astimezone(PARIS).date() == local.date():
        return None
    bilan = alleger(conn, now)
    set_etat(conn, "dernier_entretien_le", to_iso(now))
    dernier_vacuum = get_etat(conn, "dernier_compactage_le")
    if not dernier_vacuum or from_iso(dernier_vacuum).astimezone(PARIS).strftime("%Y-%m") != local.strftime("%Y-%m"):
        bilan["compactage"] = True  # fait par l'appelant, hors transaction
    return bilan


def compacter(db_path: Path, now: datetime) -> None:
    """VACUUM : hors de toute transaction (connexion dediee, autocommit)."""
    c = sqlite3.connect(db_path, timeout=60, isolation_level=None)
    try:
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        c.execute("VACUUM")
        c.execute("INSERT INTO etat (cle, valeur) VALUES ('dernier_compactage_le', ?) "
                  "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur", (to_iso(now),))
    finally:
        c.close()


def taille(conn: sqlite3.Connection, db_path: Path, now: datetime) -> dict:
    """Taille mesuree de la base et projection a un an (au rythme observe)."""
    octets = sum(f.stat().st_size for f in (db_path, Path(str(db_path) + "-wal")) if f.exists())
    premier = conn.execute("SELECT MIN(collecte_le) FROM articles").fetchone()[0]
    age_j = max(1.0, (now - from_iso(premier)).total_seconds() / 86400) if premier else None
    sem = conn.execute("SELECT COUNT(*) FROM articles WHERE collecte_le >= ?",
                       (to_iso(now - timedelta(days=7)),)).fetchone()[0]
    return {
        "mo": round(octets / 1e6, 1),
        "articles": conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0],
        "alleges": conn.execute("SELECT COUNT(*) FROM articles WHERE allege = 1").fetchone()[0],
        "articles_jour": round(sem / min(7.0, age_j), 0) if age_j else 0,
        "age_jours": round(age_j, 1) if age_j else 0,
        # projection seulement apres 3 jours de mesure (sinon trop incertaine)
        "projection_an_mo": round(octets / 1e6 / age_j * 365) if age_j and age_j >= 3 else None,
        "dernier_entretien": get_etat(conn, "dernier_entretien_le"),
        "dernier_compactage": get_etat(conn, "dernier_compactage_le"),
    }
