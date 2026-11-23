"""Journal quotidien (F10) : photo du top de chaque journee, prise chaque soir.

Le top d'une journee = les evenements qui ont recu au moins un article publie ce jour-la
(heure de Paris), classes par score. Les scores evoluent ensuite : la photo fige le
classement TEL QU'IL ETAIT (score, raisons, verification, sources et liens). Une photo
n'est jamais modifiee. Sans photo, la page recalcule avec les scores actuels et le dit.
Donnees mesurees uniquement : aucun appel a l'IA.
"""

import json
import sqlite3
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.parametres import tous
from app.util import from_iso, to_iso

PARIS = ZoneInfo("Europe/Paris")

def bornes(jour: date) -> tuple[str, str]:
    """Debut et fin d'une journee de Paris, en UTC ISO (fin exclue)."""
    debut = datetime(jour.year, jour.month, jour.day, tzinfo=PARIS)
    fin = debut + timedelta(days=1)
    return to_iso(debut), to_iso(fin)


def jour_paris(dt: datetime) -> date:
    return dt.astimezone(PARIS).date()


def _lien_sur(url: str | None) -> str | None:
    return url if url and url.startswith(("https://", "http://")) else None


def calculer(conn: sqlite3.Connection, jour: date, taille: int | None = None) -> dict:
    """Top et chiffres d'une journee, a partir des donnees actuelles de la base."""
    p = tous(conn)
    taille = int(taille or p["journal_taille_top"])
    d, f = bornes(jour)
    evts = conn.execute(
        "SELECT * FROM evenements WHERE id IN (SELECT evenement_id FROM articles "
        "WHERE evenement_id IS NOT NULL AND publie_le >= ? AND publie_le < ?) "
        "ORDER BY score DESC, nb_sources DESC, id LIMIT ?", (d, f, taille)).fetchall()
    top = []
    for rang, e in enumerate(evts, 1):
        details = json.loads(e["score_details"] or "{}")
        raisons = [f"{x['raison']} (+{x['points']})" for x in
                   sorted(details.values(), key=lambda x: -x.get("points", 0))[:3] if x.get("points", 0) > 0]
        sources = []
        for a in conn.execute(
                "SELECT a.url, s.nom AS source FROM articles a JOIN sources s ON s.id = a.source_id "
                "WHERE a.evenement_id = ? AND a.publie_le >= ? AND a.publie_le < ? "
                "ORDER BY s.fiabilite DESC, a.publie_le LIMIT 3", (e["id"], d, f)):
            if _lien_sur(a["url"]):
                sources.append({"nom": a["source"], "url": a["url"]})
        top.append({"rang": rang, "id": e["id"], "titre": e["titre"], "score": e["score"], "raisons": raisons,
                    "tendance": e["tendance"], "verification": e["verification"], "nb_sources": e["nb_sources"],
                    "theme": e["theme"], "zone": e["zone"], "sources": sources})

    def compte(sql: str, *args) -> int:
        return conn.execute(sql, args).fetchone()[0]

    cout = conn.execute("SELECT COALESCE(SUM(cout_eur), 0) FROM couts WHERE horodatage >= ? AND horodatage < ?",
                        (d, f)).fetchone()[0]
    chiffres = {
        "articles": compte("SELECT COUNT(*) FROM articles WHERE collecte_le >= ? AND collecte_le < ?", d, f),
        "pertinents": compte("SELECT COUNT(*) FROM articles WHERE pertinent = 1 AND collecte_le >= ? AND collecte_le < ?", d, f),
        "nouveaux_evenements": compte("SELECT COUNT(*) FROM evenements WHERE cree_le >= ? AND cree_le < ?", d, f),
        "alertes": compte("SELECT COUNT(*) FROM notifications WHERE type = 'alerte' AND envoye_le >= ? AND envoye_le < ?", d, f),
        "cout_ia_eur": round(float(cout), 4),
    }
    return {"top": top, "chiffres": chiffres}


def lire(conn: sqlite3.Connection, jour: date) -> dict | None:
    r = conn.execute("SELECT * FROM journal_quotidien WHERE jour = ?", (jour.isoformat(),)).fetchone()
    if not r:
        return None
    return {"jour": r["jour"], "photo_le": r["photo_le"], "rattrape": bool(r["rattrape"]),
            "top": json.loads(r["top"]), "chiffres": json.loads(r["chiffres"])}


def photographier(conn: sqlite3.Connection, jour: date, now: datetime, rattrape: bool = False) -> bool:
    """Enregistre la photo du jour. Retourne False si elle existe deja (jamais ecrasee)."""
    data = calculer(conn, jour)
    cur = conn.execute(
        "INSERT OR IGNORE INTO journal_quotidien (jour, photo_le, rattrape, top, chiffres) VALUES (?,?,?,?,?)",
        (jour.isoformat(), to_iso(now), int(rattrape), json.dumps(data["top"], ensure_ascii=False),
         json.dumps(data["chiffres"], ensure_ascii=False)))
    return cur.rowcount == 1


def tache(conn: sqlite3.Connection, now: datetime) -> list[str]:
    """Appelee chaque minute par l'orchestrateur. Retourne les jours photographies."""
    p = tous(conn)
    local = now.astimezone(PARIS)
    h, m = (int(x) for x in p["heure_journal"].split(":"))
    faits = []
    aujourdhui = local.date()
    if local >= local.replace(hour=h, minute=m, second=0, microsecond=0) and photographier(conn, aujourdhui, now):
        faits.append(aujourdhui.isoformat())
    # Rattrapage de la veille (serveur arrete a l'heure prevue), seulement si elle a des donnees
    hier = aujourdhui - timedelta(days=1)
    if not lire(conn, hier):
        d, f = bornes(hier)
        if conn.execute("SELECT 1 FROM articles WHERE collecte_le >= ? AND collecte_le < ? LIMIT 1", (d, f)).fetchone():
            if photographier(conn, hier, now, rattrape=True):
                faits.append(hier.isoformat())
    return faits


def messages_du_jour(conn: sqlite3.Connection, jour: date) -> list[sqlite3.Row]:
    d, f = bornes(jour)
    return conn.execute(
        "SELECT id, type, envoye_le, statut, score_envoye, substr(contenu, 1, 600) AS debut FROM notifications "
        "WHERE type IN ('briefing','synthese','point','alerte') AND envoye_le >= ? AND envoye_le < ? "
        "ORDER BY envoye_le", (d, f)).fetchall()


def premier_jour(conn: sqlite3.Connection) -> date | None:
    r = conn.execute("SELECT MIN(collecte_le) FROM articles").fetchone()[0]
    return jour_paris(from_iso(r)) if r else None
