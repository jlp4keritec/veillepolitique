"""Commandes Telegram de J (F09, F10, F11, F12).

Seul le chat de J est traite (filtre dans app/telegram.py + orchestrateur).
Les modifications de regles passent par app/parametres.modifier (validation).
"""

import json
import sqlite3
from datetime import datetime

from app import parametres
from app.analyse import niveau
from app.ia import ClientIA, etat_budget, repondre
from app.recherche import chercher_articles, chronologie, elements_pour_question
from app.syntheses import heure_paris
from app.telegram import e, lien
from app.util import from_iso

AIDE = """<b>Commandes VEILLE</b>
/etat — état du système
/sources — liste des sources
/source_on N · /source_off N — activer / désactiver la source N
/pause · /reprise — suspendre / relancer la collecte
/params — règles modifiables
/param cle valeur — modifier une règle (ex. /param seuil_critique 80)
/couts — budget et dépenses du mois
/top — événements les plus importants (24 h)
/evenement N — chronologie de l'événement N
/cherche mots — recherche dans l'historique
/point · /briefing · /soir — envoyer une synthèse maintenant
Sinon : posez votre question en français (ex. « Que s'est-il passé à Lyon cette semaine ? »)."""


def _etat(conn: sqlite3.Connection, now: datetime) -> str:
    p = parametres.tous(conn)
    nb = conn.execute("SELECT COUNT(*) FROM sources WHERE actif = 1").fetchone()[0]
    err = conn.execute("SELECT COUNT(*) FROM sources WHERE actif = 1 AND derniere_erreur IS NOT NULL").fetchone()[0]
    arts = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    evts = conn.execute("SELECT COUNT(*) FROM evenements").fetchone()[0]
    b = etat_budget(conn, now)
    der = conn.execute("SELECT MAX(derniere_collecte) FROM sources").fetchone()[0]
    return "\n".join([
        "<b>État VEILLE</b>",
        f"Collecte : {'ACTIVE' if p['collecte_active'] else 'EN PAUSE'} · dernière : {heure_paris(from_iso(der)) if der else 'jamais'}",
        f"Sources actives : {nb} (dont {err} en erreur)",
        f"Articles : {arts} · Événements : {evts}",
        f"Alertes : {'actives' if p['alertes_actives'] else 'désactivées'} (seuil {p['seuil_critique']})",
        f"IA : {'active' if p['ia_active'] else 'désactivée'} · budget {b['depense_eur']:.2f} / {b['budget_eur']:.2f} € ({b['pct']} %)",
    ])


def _sources(conn) -> str:
    lignes = ["<b>Sources</b> (N · état · nom)"]
    for s in conn.execute("SELECT * FROM sources ORDER BY actif DESC, niveau, nom"):
        etat = "✅" if s["actif"] else "⏸"
        if s["actif"] and s["derniere_erreur"]:
            etat = "⚠️"
        lignes.append(f"{s['id']} · {etat} · {e(s['nom'])}" + (" (non vérifiée)" if not s["url_verifiee"] else ""))
    return "\n".join(lignes)


def _top(conn, now) -> str:
    from datetime import timedelta
    from app.util import to_iso
    p = parametres.tous(conn)
    rows = conn.execute("SELECT * FROM evenements WHERE dernier_article_le >= ? ORDER BY score DESC LIMIT 10",
                        (to_iso(now - timedelta(hours=24)),)).fetchall()
    if not rows:
        return "Aucun événement sur les dernières 24 h."
    return "\n".join(["<b>Top 24 h</b>"] + [
        f"{r['id']} · {r['score']}/100 ({niveau(r['score'], p)}) · {e(r['titre'])} — {e(r['verification'])}"
        for r in rows])


def traiter(conn: sqlite3.Connection, texte: str, now: datetime, ia: ClientIA | None = None,
            declencher=None) -> str:
    """Retourne la reponse a envoyer a J. `declencher(type)` envoie une synthese a la demande."""
    t = texte.strip()
    cmd, _, arg = t.partition(" ")
    cmd = cmd.lower().split("@")[0]
    arg = arg.strip()
    try:
        if cmd in ("/start", "/aide", "/help"):
            return AIDE
        if cmd == "/etat":
            return _etat(conn, now)
        if cmd == "/sources":
            return _sources(conn)
        if cmd in ("/source_on", "/source_off"):
            if not arg.isdigit():
                return "Usage : /source_on N (numéro dans /sources)"
            actif = int(cmd == "/source_on")
            n = conn.execute("UPDATE sources SET actif = ? WHERE id = ?", (actif, int(arg))).rowcount
            return f"Source {arg} {'activée' if actif else 'désactivée'}." if n else f"Source {arg} introuvable."
        if cmd in ("/pause", "/reprise"):
            parametres.modifier(conn, "collecte_active", cmd == "/reprise", origine="telegram")
            return "Collecte relancée." if cmd == "/reprise" else "Collecte suspendue. /reprise pour relancer."
        if cmd == "/params":
            vals = parametres.tous(conn)
            simples = [f"{k} = {e(json.dumps(v, ensure_ascii=False))}" for k, v in vals.items()
                       if not isinstance(v, (list, dict))]
            listes = [k for k, v in vals.items() if isinstance(v, (list, dict))]
            return "<b>Règles</b>\n" + "\n".join(simples) + "\n\n<i>Listes (via l'API) : " + e(", ".join(listes)) + "</i>"
        if cmd == "/param":
            cle, _, val = arg.partition(" ")
            if not cle or not val:
                return "Usage : /param cle valeur (voir /params)"
            v = parametres.modifier(conn, cle, val, origine="telegram")
            return f"Règle modifiée : {e(cle)} = {e(json.dumps(v, ensure_ascii=False))}"
        if cmd == "/couts":
            b = etat_budget(conn, now)
            lignes = [f"<b>Coûts {b['mois']}</b>", f"{b['depense_eur']:.4f} € / {b['budget_eur']:.2f} € ({b['pct']} %)"]
            lignes += [f"• {e(a)} : {v['appels']} appel(s), {v['eur']:.4f} €, {v['tokens_in']}+{v['tokens_out']} tokens"
                       for a, v in b["par_agent"].items()]
            return "\n".join(lignes)
        if cmd == "/top":
            return _top(conn, now)
        if cmd == "/evenement":
            if not arg.isdigit():
                return "Usage : /evenement N (numéro dans /top)"
            rows = chronologie(conn, int(arg))
            if not rows:
                return f"Événement {arg} introuvable."
            return "\n".join([f"<b>Chronologie de l'événement {arg}</b>"] + [
                f"{heure_paris(from_iso(r['publie_le']))} {from_iso(r['publie_le']).strftime('%d/%m')} · "
                f"{lien(r['url'], r['source'])} : {e(r['titre'])}" for r in rows])
        if cmd == "/cherche":
            if not arg:
                return "Usage : /cherche mots"
            rows = chercher_articles(conn, arg.split()[:5], limite=10)
            if not rows:
                return "Aucun article trouvé dans l'historique."
            return "\n".join([f"<b>Recherche : {e(arg)}</b>"] + [
                f"• {from_iso(r['publie_le']).strftime('%d/%m %H:%M')} {lien(r['url'], r['source'])} : {e(r['titre'])}"
                for r in rows])
        if cmd in ("/point", "/briefing", "/soir"):
            if declencher:
                declencher({"/point": "point", "/briefing": "briefing", "/soir": "synthese"}[cmd])
                return "Synthèse envoyée."
            return "Indisponible."
        if cmd.startswith("/"):
            return "Commande inconnue. /aide pour la liste."
        return question(conn, t, now, ia)
    except (KeyError, ValueError) as exc:
        return f"Refusé : {e(exc)}"


def question(conn: sqlite3.Connection, texte: str, now: datetime, ia: ClientIA | None) -> str:
    """F09 : reponse a partir des donnees collectees, avec les liens."""
    critere, elements = elements_pour_question(conn, texte, now)
    if not elements:
        return ("Données insuffisantes : aucun article correspondant dans l'historique "
                f"depuis le {critere['depuis'].strftime('%d/%m')}.")
    sources = "\n".join(f"[{i + 1}] {lien(el['url'], el['source'])} : {e(el['titre'])}"
                        for i, el in enumerate(elements))
    texte_ia = repondre(conn, ia, texte, elements) if ia and ia.disponible(conn, now, "question")[0] else None
    if texte_ia:
        return f"{e(texte_ia)}\n<i>(réponse proposée par l'IA à partir des éléments ci-dessous)</i>\n\n{sources}"
    entete = f"{len(elements)} élément(s) trouvé(s) dans l'historique"
    if critere["theme"]:
        entete += f" · thème {e(critere['theme'])}"
    if critere["zone"]:
        entete += " · Lyon / région"
    return f"<b>{entete}</b>\n{sources}"
