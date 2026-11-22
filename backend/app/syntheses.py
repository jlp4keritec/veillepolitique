"""Agent de synthese : mise en forme des alertes (ch. 7.1), points de veille (7.2),
briefing matinal (F07, ch. 8) et synthese du soir (F08).

Tout part des donnees en base : chaque information porte sa source et son lien,
son statut de verification et son score. Le resume executif peut etre propose
par Claude (fonction `resumeur`) ; sinon un resume factuel par regles est utilise.
"""

import json
import sqlite3
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo

from app.analyse import niveau
from app.parametres import tous
from app.telegram import e, lien
from app.util import from_iso, to_iso

PARIS = ZoneInfo("Europe/Paris")
Resumeur = Callable[[list[dict], str], str | None]

EVOLUTION = {"nouveau": "nouveau sujet", "forte hausse": "en forte hausse", "en hausse": "en hausse",
             "stable": "stable", "en baisse": "en baisse"}


def heure_paris(dt: datetime) -> str:
    return dt.astimezone(PARIS).strftime("%H:%M")


def date_paris(dt: datetime) -> str:
    return dt.astimezone(PARIS).strftime("%d/%m/%Y")


def articles_de(conn: sqlite3.Connection, evt_id: int, limite: int = 5) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT a.titre, a.url, a.texte_extrait, a.publie_le, s.nom AS source, s.fiabilite "
        "FROM articles a JOIN sources s ON s.id = a.source_id WHERE a.evenement_id = ? "
        "ORDER BY s.fiabilite DESC, a.publie_le LIMIT ?", (evt_id, limite)).fetchall()


def evenements_depuis(conn: sqlite3.Connection, depuis: datetime, score_min: int = 0,
                      limite: int = 50) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM evenements WHERE dernier_article_le >= ? AND score >= ? "
        "ORDER BY score DESC, nb_sources DESC LIMIT ?", (to_iso(depuis), score_min, limite)).fetchall()


def _raisons(evt: sqlite3.Row, n: int = 3) -> str:
    d = json.loads(evt["score_details"] or "{}")
    top = sorted(d.values(), key=lambda x: -x["points"])[:n]
    return " ; ".join(f"{x['raison']} (+{x['points']})" for x in top if x["points"] > 0)


def _sources(conn, evt_id: int, n: int = 3) -> str:
    return " · ".join(lien(a["url"], a["source"]) for a in articles_de(conn, evt_id, n))


def ligne_evt(conn, evt: sqlite3.Row, p: dict) -> str:
    return (f"• <b>{e(evt['titre'])}</b>\n"
            f"  {evt['score']}/100 ({niveau(evt['score'], p)}) · {e(EVOLUTION.get(evt['tendance'], evt['tendance']))}"
            f" · {e(evt['verification'])}\n  {_sources(conn, evt['id'])}")


# ------------------------------------------------------------------ alerte
def format_alerte(conn: sqlite3.Connection, evt: sqlite3.Row, mise_a_jour: bool) -> str:
    arts = articles_de(conn, evt["id"], 5)
    if evt["resume_ia"]:
        resume = f"{e(evt['resume_ia'])}\n<i>(résumé proposé par l'IA à partir des sources ci-dessous)</i>"
    else:
        extraits = [f"« {e(a['texte_extrait'][:280])} » — {e(a['source'])}" for a in arts[:2] if a["texte_extrait"]]
        resume = "\n".join(extraits) or "Pas d'extrait disponible : voir les sources."
    acteurs = json.loads(evt["acteurs"] or "[]")
    evolution = "mise à jour (élément nouveau)" if mise_a_jour else EVOLUTION.get(evt["tendance"], evt["tendance"])
    return "\n".join([
        "🚨 <b>ALERTE POLITIQUE — CRITIQUE</b>" + (" (MISE À JOUR)" if mise_a_jour else ""),
        "",
        f"<b>{e(evt['titre'])}</b>",
        "",
        resume,
        "",
        f"<b>Pourquoi c'est important :</b> {e(_raisons(evt))}",
        f"<b>Acteurs :</b> {e(', '.join(acteurs) or 'non identifiés')}",
        f"<b>Évolution :</b> {e(evolution)} — {evt['nb_articles']} article(s), {evt['nb_sources']} source(s)",
        f"<b>Vérification :</b> {e(evt['verification'])}",
        "<b>Sources :</b> " + " · ".join(lien(a["url"], a["source"]) for a in arts),
        f"<b>Priorité :</b> {evt['score']}/100",
    ])


# ------------------------------------------------------------------ pied commun
def limites(conn: sqlite3.Connection) -> str:
    en_erreur = conn.execute("SELECT nom FROM sources WHERE actif = 1 AND derniere_erreur IS NOT NULL").fetchall()
    actives = conn.execute("SELECT COUNT(*) FROM sources WHERE actif = 1").fetchone()[0]
    txt = f"<i>Limites : {actives} source(s) active(s)"
    if en_erreur:
        txt += f", {len(en_erreur)} en erreur ({e(', '.join(r['nom'] for r in en_erreur[:5]))})"
    return txt + ". Réseaux sociaux non couverts (phase 2).</i>"


def _resume_executif(evts: list[sqlite3.Row], resumeur: Resumeur | None, conn, consigne: str) -> str:
    if not evts:
        return "Aucun événement suivi sur la période."
    if resumeur:
        donnees = [{"titre": v["titre"], "score": v["score"], "verification": v["verification"],
                    "tendance": v["tendance"], "sources": [a["source"] for a in articles_de(conn, v["id"], 3)]}
                   for v in evts[:10]]
        txt = resumeur(donnees, consigne)
        if txt:
            return e(txt) + "\n<i>(résumé proposé par l'IA à partir des événements listés)</i>"
    top = evts[0]
    n_crit = sum(1 for v in evts if v["score"] >= tous(conn)["seuil_critique"])
    return (f"{len(evts)} événement(s) suivis, dont {n_crit} critique(s). "
            f"Le plus important : « {e(top['titre'])} » ({top['score']}/100, {e(top['verification'])}).")


def _section(titre: str, lignes: list[str]) -> list[str]:
    return ["", f"<b>{titre}</b>"] + (lignes or ["Rien à signaler."])


# ------------------------------------------------------------------ point de veille
def point_veille(conn: sqlite3.Connection, now: datetime, depuis: datetime,
                 exclure: set[int] | None = None) -> str | None:
    p = tous(conn)
    exclure = exclure or set()
    evts = [v for v in evenements_depuis(conn, depuis) if v["id"] not in exclure]
    if not evts and not p["point_si_rien"]:
        return None
    hausse = [v for v in evts if v["tendance"] in ("forte hausse", "en hausse", "nouveau") and v["nb_articles"] >= 2]
    decl = [v for v in evts if v["type_evenement"] in ("déclaration", "réaction", "interview")]
    surv = [v for v in evts if v["verification"] in ("à confirmer", "une seule source disponible", "déclaration rapportée")
            and v["score"] >= 50]
    out = [f"🕑 <b>POINT DE VEILLE — {heure_paris(now)}</b>",
           f"<i>Depuis {heure_paris(depuis)}</i>"]
    out += _section("Les trois faits importants", [ligne_evt(conn, v, p) for v in evts[:3]])
    out += _section("Sujets en hausse", [
        f"• {e(v['titre'])} — {e(EVOLUTION[v['tendance']])} ({e(json.loads(v['tendance_details']).get('regle', ''))})"
        for v in hausse[:5]])
    out += _section("Nouvelles déclarations", [
        f"• {e(', '.join(json.loads(v['acteurs'])[:2]) or 'acteur non identifié')} : {e(v['titre'])} — {_sources(conn, v['id'], 1)}"
        for v in decl[:5]])
    out += _section("À surveiller (non confirmé)", [
        f"• {e(v['titre'])} — {e(v['verification'])}" for v in surv[:5]])
    out += ["", limites(conn)]
    return "\n".join(out)


# ------------------------------------------------------------------ briefing 08:00 / synthese 20:00
def _rapport(conn, now, depuis, titre: str, resumeur, consigne: str, matin: bool) -> str:
    p = tous(conn)
    evts = evenements_depuis(conn, depuis)
    out = [f"<b>{titre}</b>", ""]
    out += ["<b>Résumé exécutif</b>", _resume_executif(evts, resumeur, conn, consigne)]
    out += _section("Top 10" if matin else "Événements de la journée", [ligne_evt(conn, v, p) for v in evts[:10]])
    montent = sorted([v for v in evts if v["tendance"] in ("forte hausse", "en hausse")],
                     key=lambda v: (v["tendance"] != "forte hausse", -v["score"]))
    out += _section("Sujets qui montent" if matin else "Tendances émergentes", [
        f"• {e(v['titre'])} — {e(EVOLUTION[v['tendance']])}" for v in montent[:5]])
    nat = [v for v in evts if v["zone"] == "national"]
    out += _section("Politique nationale (gouvernement, Parlement, partis)", [ligne_evt(conn, v, p) for v in nat[:5]])
    reg = [v for v in evts if v["zone"] == "regional"]
    out += _section("Actualité régionale — Lyon / Auvergne-Rhône-Alpes", [ligne_evt(conn, v, p) for v in reg[:5]])
    contro = [v for v in evts if v["type_evenement"] in ("déclaration", "controverse", "réaction")]
    out += _section("Déclarations et controverses", [
        f"• {e(v['titre'])} ({e(v['type_evenement'])}, {e(v['verification'])}) — {_sources(conn, v['id'], 2)}"
        for v in contro[:5]])
    confirmes = [v for v in evts if v["verification"] in ("confirmé par source primaire", "corroboré par plusieurs sources")]
    if not matin:
        out += _section("Informations confirmées", [f"• {e(v['titre'])} — {e(v['verification'])}" for v in confirmes[:5]])
    if matin:
        out += _section("Agenda du jour", ["Aucune source d'agenda configurée pour l'instant."])
    faits = [v for v in evts if v["tendance"] in ("forte hausse", "en hausse")]
    hypo = [v for v in evts if v["verification"] == "à confirmer"]
    out += _section("À surveiller" if matin else "Susceptible de continuer demain",
                    [f"• Fait observé : {e(v['titre'])} ({e(EVOLUTION[v['tendance']])})" for v in faits[:3]]
                    + [f"• Hypothèse à confirmer : {e(v['titre'])}" for v in hypo[:3]])
    out += ["", limites(conn)]
    return "\n".join(out)


def briefing(conn, now: datetime, depuis: datetime, resumeur: Resumeur | None = None) -> str:
    return _rapport(conn, now, depuis, f"☀️ VEILLE POLITIQUE — {date_paris(now)} — 08:00", resumeur,
                    "Résumé exécutif du briefing matinal en 5 à 10 lignes.", matin=True)


def synthese_soir(conn, now: datetime, depuis: datetime, resumeur: Resumeur | None = None) -> str:
    return _rapport(conn, now, depuis, f"🌙 SYNTHÈSE DU SOIR — {date_paris(now)} — 20:00", resumeur,
                    "Récapitulatif factuel de la journée en 5 à 10 lignes.", matin=False)


def depuis_iso(s: str | None, defaut: datetime) -> datetime:
    return from_iso(s) if s else defaut
