"""Decision d'alerte (F05) : les REGLES de J decident, l'executeur envoie.

- Seuil : score >= seuil_critique.
- Qualite des sources : au moins 2 sources, OU une source institutionnelle,
  OU une source unique de fiabilite >= alerte_fiabilite_min.
- Jamais deux fois : 1re alerte, puis mise a jour seulement si le score monte
  d'au moins alerte_delta_score OU si alerte_delta_sources nouvelles sources
  apparaissent, dans la limite de alerte_max_mises_a_jour.
"""

import sqlite3
from datetime import datetime, timedelta

from app.parametres import tous
from app.syntheses import format_alerte
from app.telegram import notifier
from app.util import to_iso


def qualite_ok(conn: sqlite3.Connection, evt: sqlite3.Row, p: dict) -> tuple[bool, str]:
    if evt["verification"] == "contradictoire":
        return False, "informations contradictoires"
    if evt["nb_sources"] >= 2:
        return True, "plusieurs sources"
    r = conn.execute(
        "SELECT MIN(s.niveau) AS niv, MAX(s.fiabilite) AS fiab FROM articles a "
        "JOIN sources s ON s.id = a.source_id WHERE a.evenement_id = ?", (evt["id"],)).fetchone()
    if r["niv"] == 1:
        return True, "source institutionnelle"
    if (r["fiab"] or 0) >= p["alerte_fiabilite_min"]:
        return True, "source unique fiable"
    return False, "source unique peu fiable"


def decision(conn: sqlite3.Connection, evt: sqlite3.Row, p: dict) -> tuple[str | None, str]:
    """Retourne (cle_unique a envoyer ou None, explication)."""
    if evt["score"] < p["seuil_critique"]:
        return None, "sous le seuil"
    ok, pourquoi = qualite_ok(conn, evt, p)
    if not ok:
        return None, pourquoi
    precedentes = conn.execute(
        "SELECT score_envoye, nb_sources_envoye FROM notifications WHERE type = 'alerte' "
        "AND evenement_id = ? ORDER BY id", (evt["id"],)).fetchall()
    if not precedentes:
        return f"alerte:{evt['id']}:1", "premiere alerte"
    if len(precedentes) - 1 >= p["alerte_max_mises_a_jour"]:
        return None, "nombre maximal de mises a jour atteint"
    der = precedentes[-1]
    if (evt["score"] - (der["score_envoye"] or 0) >= p["alerte_delta_score"]
            or evt["nb_sources"] - (der["nb_sources_envoye"] or 0) >= p["alerte_delta_sources"]):
        return f"alerte:{evt['id']}:{len(precedentes) + 1}", "element nouveau significatif"
    return None, "deja alerte, pas d'element nouveau significatif"


def traiter_alertes(conn: sqlite3.Connection, tg, now: datetime) -> list[int]:
    p = tous(conn)
    if not p["alertes_actives"]:
        return []
    envoyees = []
    evts = conn.execute("SELECT * FROM evenements WHERE score >= ? AND dernier_article_le >= ? "
                        "ORDER BY score DESC", (p["seuil_critique"], to_iso(now - timedelta(hours=24)))).fetchall()
    for evt in evts:
        cle, _ = decision(conn, evt, p)
        if not cle:
            continue
        maj = not cle.endswith(":1")
        if notifier(conn, tg, "alerte", cle, format_alerte(conn, evt, maj), evt["id"], evt["score"], evt["nb_sources"], now=now):
            envoyees.append(evt["id"])
    return envoyees
