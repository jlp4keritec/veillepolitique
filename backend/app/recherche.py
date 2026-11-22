"""Historique (F10) et recherche conversationnelle (F09).

La recherche se fait dans la base (jamais sur internet). Les reponses
citent les liens des articles trouves et signalent les donnees insuffisantes.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.parametres import themes_actifs
from app.util import contient, mots_significatifs, normaliser, to_iso

PARIS = ZoneInfo("Europe/Paris")

MOTS_OUTILS = {"quoi", "passe", "passee", "resume", "resumer", "fais", "fait", "chronologie", "compare",
               "comparer", "reactions", "sujets", "sujet", "aujourd", "hui", "hier", "semaine", "jour",
               "mois", "heures", "depuis", "quels", "quelles", "quel", "quelle", "cette", "derniere",
               "dernieres", "derniers", "dernier", "est", "ont", "hausse", "montent", "monte", "infos",
               "information", "informations", "actualite", "actu", "parle", "dit", "polemique"}


def periode(question_norm: str, now: datetime) -> datetime:
    local = now.astimezone(PARIS)
    minuit = local.replace(hour=0, minute=0, second=0, microsecond=0)
    if contient(question_norm, "hier"):
        return minuit - timedelta(days=1)
    if contient(question_norm, "aujourd hui") or contient(question_norm, "aujourd"):
        return minuit
    if contient(question_norm, "cette semaine") or contient(question_norm, "semaine"):
        return minuit - timedelta(days=local.weekday())
    if contient(question_norm, "mois"):
        return minuit - timedelta(days=30)
    return now - timedelta(hours=24 * 7)


def chercher_articles(conn: sqlite3.Connection, mots: list[str] = (), depuis: datetime | None = None,
                      jusqu: datetime | None = None, theme: str | None = None, source_id: int | None = None,
                      zone: str | None = None, acteur: str | None = None, limite: int = 30) -> list[sqlite3.Row]:
    sql = ("SELECT a.id, a.titre, a.url, a.publie_le, a.theme, a.zone, a.type_evenement, a.evenement_id, "
           "a.resume_ia, a.texte_extrait, s.nom AS source FROM articles a JOIN sources s ON s.id = a.source_id "
           "WHERE a.pertinent = 1")
    args: list = []
    for m in mots:
        sql += " AND (a.titre_norm LIKE ? OR a.texte_norm LIKE ?)"
        args += [f"%{normaliser(m)}%"] * 2
    if depuis:
        sql += " AND a.publie_le >= ?"
        args.append(to_iso(depuis))
    if jusqu:
        sql += " AND a.publie_le <= ?"
        args.append(to_iso(jusqu))
    if theme:
        sql += " AND a.themes LIKE ?"
        args.append(f'%"{theme}"%')
    if source_id:
        sql += " AND a.source_id = ?"
        args.append(source_id)
    if zone:
        sql += " AND a.zone = ?"
        args.append(zone)
    if acteur:
        sql += " AND a.acteurs LIKE ?"
        args.append(f"%{acteur}%")
    sql += " ORDER BY a.publie_le DESC LIMIT ?"
    args.append(limite)
    return conn.execute(sql, args).fetchall()


def chronologie(conn: sqlite3.Connection, evt_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT a.titre, a.url, a.publie_le, s.nom AS source FROM articles a JOIN sources s "
        "ON s.id = a.source_id WHERE a.evenement_id = ? ORDER BY a.publie_le, a.id", (evt_id,)).fetchall()


def analyser_question(conn: sqlite3.Connection, question: str, now: datetime) -> dict:
    q = normaliser(question)
    themes = themes_actifs(conn)
    theme = next((t for t, mots in themes.items()
                  if contient(q, t) or any(contient(q, m) for m in mots)), None)
    zone = "regional" if any(contient(q, m) for m in ("lyon", "region", "regional", "auvergne", "metropole")) else None
    mots = [m for m in mots_significatifs(q.replace("-", " ")) if m not in MOTS_OUTILS]
    if theme:
        mots_theme = {normaliser(x) for x in themes[theme]} | {normaliser(theme)}
        mots = [m for m in mots if m not in mots_theme]
    if zone:
        mots = [m for m in mots if m not in ("lyon", "region", "regional", "auvergne", "metropole")]
    tendances = contient(q, "hausse") or contient(q, "montent") or contient(q, "monte")
    return {"depuis": periode(q, now), "theme": theme, "zone": zone, "mots": mots[:5], "tendances": tendances}


def elements_pour_question(conn: sqlite3.Connection, question: str, now: datetime) -> tuple[dict, list[dict]]:
    c = analyser_question(conn, question, now)
    if c["tendances"]:
        rows = conn.execute(
            "SELECT e.id, e.titre, e.tendance, e.tendance_details, e.score, e.verification FROM evenements e "
            "WHERE e.dernier_article_le >= ? AND e.tendance IN ('forte hausse','en hausse','nouveau') "
            "ORDER BY (e.tendance = 'forte hausse') DESC, e.score DESC LIMIT 10", (to_iso(c["depuis"]),)).fetchall()
        elements = []
        for r in rows:
            a = conn.execute("SELECT a.url, s.nom AS source FROM articles a JOIN sources s ON s.id = a.source_id "
                             "WHERE a.evenement_id = ? LIMIT 1", (r["id"],)).fetchone()
            elements.append({"titre": r["titre"], "tendance": r["tendance"],
                             "mesure": json.loads(r["tendance_details"]).get("regle"), "score": r["score"],
                             "verification": r["verification"], "source": a["source"], "url": a["url"],
                             "date": None})
        return c, elements
    arts = chercher_articles(conn, c["mots"], c["depuis"], theme=c["theme"], zone=c["zone"], limite=15)
    if not arts and c["mots"]:  # elargit : un seul mot suffit
        vus = {}
        for m in c["mots"]:
            for a in chercher_articles(conn, [m], c["depuis"], theme=c["theme"], zone=c["zone"], limite=10):
                vus[a["id"]] = a
        arts = sorted(vus.values(), key=lambda a: a["publie_le"], reverse=True)[:15]
    elements = [{"titre": a["titre"], "date": a["publie_le"], "source": a["source"], "url": a["url"],
                 "type": a["type_evenement"], "resume": a["resume_ia"] or a["texte_extrait"][:300]}
                for a in arts]
    return c, elements
