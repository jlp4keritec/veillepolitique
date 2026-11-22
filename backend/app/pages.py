"""Pages de lecture (lecture seule) : accueil, archives, lecture, evenement, recherche, connexion.

Tout le contenu est echappe automatiquement (Jinja2). Le texte des syntheses, deja
mis en forme pour Telegram, est NETTOYE avant affichage : seules les balises
<b>, <i> et les liens http(s) sont conservees.
"""

import html
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, quote
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from app import __version__, auth, parametres
from app.analyse import niveau
from app.config import get_settings
from app.db import get_etat, session
from app.recherche import chercher_articles, chronologie
from app.util import from_iso, to_iso, utcnow

PARIS = ZoneInfo("Europe/Paris")
TYPES_LISIBLES = {"briefing": "Briefing 08:00", "synthese": "Synthèse 20:00", "point": "Point de veille",
                  "alerte": "Alerte", "systeme": "Système", "reponse": "Réponse"}
CRITERES = {"institutionnel": "Importance institutionnelle", "nouveaute": "Nouveauté",
            "acceleration": "Accélération", "sources": "Sources indépendantes",
            "impact": "Impact potentiel", "pertinence": "Pertinence thèmes"}

_BALISE = re.compile(r'(<b>|</b>|<i>|</i>|</a>|<a href="[^"<>]*">)')
_HREF = re.compile(r'<a href="([^"<>]*)">')

env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"),
                  autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)


def contenu_sur(texte: str) -> Markup:
    """Garde seulement <b>, <i> et les liens http(s) ; tout le reste est echappe."""
    sortie = []
    ouverts_a = 0
    for morceau in _BALISE.split(texte or ""):
        if morceau in ("<b>", "</b>", "<i>", "</i>"):
            sortie.append(morceau)
        elif morceau == "</a>":
            if ouverts_a:
                sortie.append("</a>")
                ouverts_a -= 1
        elif m := _HREF.fullmatch(morceau):
            url = html.unescape(m.group(1))
            if url.startswith(("https://", "http://")):
                sortie.append(f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">')
                ouverts_a += 1
        else:
            sortie.append(html.escape(html.unescape(morceau), quote=False))
    sortie.append("</a>" * ouverts_a)
    # equilibre les <b>/<i> eventuellement non fermes
    rendu = "".join(sortie)
    for t in ("b", "i"):
        rendu += f"</{t}>" * max(0, rendu.count(f"<{t}>") - rendu.count(f"</{t}>"))
    return Markup(rendu.replace("\n", "<br>\n"))


def _paris(iso: str | None, fmt: str = "%d/%m %H:%M") -> str:
    return from_iso(iso).astimezone(PARIS).strftime(fmt) if iso else "—"


def _classe_score(score: int, p: dict) -> str:
    return ("crit" if score >= p["seuil_critique"] else "tres" if score >= p["seuil_important"]
            else "imp" if score >= 50 else "info" if score >= 30 else "faible")


env.filters["paris"] = _paris
env.filters["jour"] = lambda iso: _paris(iso, "%a %d/%m/%Y").capitalize()
env.globals.update(version=__version__, TYPES=TYPES_LISIBLES, CRITERES=CRITERES)

router = APIRouter(include_in_schema=False)


def page(nom: str, request: Request, **ctx) -> HTMLResponse:
    with session(get_settings().db_path) as conn:
        p = parametres.tous(conn)
    ctx.setdefault("titre_page", "VEILLE")
    rendu = env.get_template(nom).render(
        request=request, p=p, protege=auth.protection_active(),
        score_classe=lambda s: _classe_score(s, p), niveau=lambda s: niveau(s, p), **ctx)
    return HTMLResponse(rendu, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                        "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY"})


def _evts(conn, depuis: datetime, limite: int = 10):
    return conn.execute("SELECT * FROM evenements WHERE dernier_article_le >= ? ORDER BY score DESC, nb_sources DESC "
                        "LIMIT ?", (to_iso(depuis), limite)).fetchall()


# ------------------------------------------------------------------ accueil
@router.get("/", response_class=HTMLResponse)
def accueil(request: Request):
    now = utcnow()
    minuit = now.astimezone(PARIS).replace(hour=0, minute=0, second=0, microsecond=0)
    with session(get_settings().db_path) as conn:
        dernier = conn.execute("SELECT * FROM notifications WHERE type IN ('briefing','synthese') "
                               "ORDER BY id DESC LIMIT 1").fetchone()
        alertes = conn.execute("SELECT * FROM notifications WHERE type = 'alerte' AND envoye_le >= ? "
                               "ORDER BY id DESC", (to_iso(minuit),)).fetchall()
        top = _evts(conn, now - timedelta(hours=24))
        etat = {
            "dernier_cycle": get_etat(conn, "dernier_cycle"),
            "sources": conn.execute("SELECT COUNT(*) FROM sources WHERE actif = 1").fetchone()[0],
            "erreurs": conn.execute("SELECT COUNT(*) FROM sources WHERE actif = 1 AND derniere_erreur IS NOT NULL").fetchone()[0],
            "articles_24h": conn.execute("SELECT COUNT(*) FROM articles WHERE collecte_le >= ?",
                                         (to_iso(now - timedelta(hours=24)),)).fetchone()[0],
        }
    return page("accueil.html", request, dernier=dernier, contenu=contenu_sur(dernier["contenu"]) if dernier else None,
                alertes=alertes, top=top, etat=etat)


def _apercu(debut: str) -> str:
    """Premiere ligne utile d'un message (titre d'alerte, debut du resume...)."""
    lignes = [html.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in (debut or "").split("\n")]
    lignes = [x for x in lignes[1:] if x and x not in ("Résumé exécutif",) and not x.startswith("Depuis ")]
    if not lignes:
        return "Lire"
    return lignes[0] if len(lignes[0]) <= 140 else lignes[0][:139].rsplit(" ", 1)[0] + "…"


# ------------------------------------------------------------------ archives
@router.get("/archives", response_class=HTMLResponse)
def archives(request: Request, type: str = "", page_n: int = 1):
    types = [type] if type in ("briefing", "synthese", "point", "alerte") else ["briefing", "synthese", "point", "alerte"]
    page_n = max(1, page_n)
    with session(get_settings().db_path) as conn:
        q = f"FROM notifications WHERE type IN ({','.join('?' * len(types))})"
        total = conn.execute("SELECT COUNT(*) " + q, types).fetchone()[0]
        rows = conn.execute("SELECT id, type, envoye_le, statut, evenement_id, score_envoye, "
                            "substr(contenu, 1, 600) AS debut " + q + " ORDER BY id DESC LIMIT 50 OFFSET ?",
                            (*types, (page_n - 1) * 50)).fetchall()
    apercus = [(r, _apercu(r["debut"])) for r in rows]
    return page("archives.html", request, titre_page="Archives", lignes=apercus, type_choisi=type,
                page_n=page_n, pages=max(1, (total + 49) // 50), total=total)


# ------------------------------------------------------------------ lecture
@router.get("/lecture/{notif_id}", response_class=HTMLResponse)
def lecture(request: Request, notif_id: int):
    with session(get_settings().db_path) as conn:
        n = conn.execute("SELECT * FROM notifications WHERE id = ?", (notif_id,)).fetchone()
        if not n:
            raise HTTPException(404, "introuvable")
        prec = conn.execute("SELECT id FROM notifications WHERE id < ? AND type = ? ORDER BY id DESC LIMIT 1",
                            (notif_id, n["type"])).fetchone()
        suiv = conn.execute("SELECT id FROM notifications WHERE id > ? AND type = ? ORDER BY id LIMIT 1",
                            (notif_id, n["type"])).fetchone()
    return page("lecture.html", request, titre_page=TYPES_LISIBLES.get(n["type"], n["type"]), n=n,
                contenu=contenu_sur(n["contenu"]), prec=prec, suiv=suiv)


# ------------------------------------------------------------------ evenement
@router.get("/evenement/{evt_id}", response_class=HTMLResponse)
def evenement(request: Request, evt_id: int):
    with session(get_settings().db_path) as conn:
        e = conn.execute("SELECT * FROM evenements WHERE id = ?", (evt_id,)).fetchone()
        if not e:
            raise HTTPException(404, "introuvable")
        chrono = chronologie(conn, evt_id)
        notifs = conn.execute("SELECT id, type, envoye_le FROM notifications WHERE evenement_id = ? ORDER BY id",
                              (evt_id,)).fetchall()
    return page("evenement.html", request, titre_page="Événement", e=e, chrono=chrono, notifs=notifs,
                details=json.loads(e["score_details"] or "{}"), tendance=json.loads(e["tendance_details"] or "{}"),
                verif=json.loads(e["verification_details"] or "{}"), acteurs=json.loads(e["acteurs"] or "[]"),
                themes=json.loads(e["themes"] or "[]"))


# ------------------------------------------------------------------ recherche (F10)
def _date(s: str, fin: bool = False) -> datetime | None:
    try:
        d = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=PARIS)
    except ValueError:
        return None
    return d + timedelta(days=1) - timedelta(seconds=1) if fin else d


@router.get("/recherche", response_class=HTMLResponse)
def recherche(request: Request, q: str = "", theme: str = "", zone: str = "", du: str = "", au: str = ""):
    with session(get_settings().db_path) as conn:
        themes = [r["nom"] for r in conn.execute("SELECT nom FROM themes WHERE actif = 1 ORDER BY nom")]
        lance = bool(q or theme or zone or du or au)
        rows = chercher_articles(conn, q.split()[:5], _date(du), _date(au, fin=True), theme or None, None,
                                 zone if zone in ("national", "regional") else None, None, 100) if lance else []
    return page("recherche.html", request, titre_page="Recherche", rows=rows, lance=lance, themes=themes,
                f={"q": q, "theme": theme, "zone": zone, "du": du, "au": au})


# ------------------------------------------------------------------ connexion
@router.get("/connexion", response_class=HTMLResponse)
def connexion_page(request: Request, suite: str = "/", erreur: str = ""):
    if not auth.protection_active():
        return RedirectResponse("/", status_code=303)
    return page("connexion.html", request, titre_page="Connexion", suite=_suite_sure(suite), erreur=erreur)


def _suite_sure(suite: str) -> str:
    """Redirection uniquement vers une page de ce site (pas de redirection ouverte)."""
    return suite if suite.startswith("/") and not suite.startswith("//") else "/"


@router.post("/connexion")
async def connexion(request: Request):
    ip = auth.adresse(request)
    corps = parse_qs((await request.body()).decode("utf-8", "replace")[:2000])
    suite = _suite_sure((corps.get("suite") or ["/"])[0])
    if auth.bloque(ip):
        return RedirectResponse(f"/connexion?erreur=bloque&suite={quote(suite)}", status_code=303)
    if not auth.verifier_mot_de_passe((corps.get("mot_de_passe") or [""])[0]):
        auth.noter_echec(ip)
        return RedirectResponse(f"/connexion?erreur=faux&suite={quote(suite)}", status_code=303)
    auth.oublier_echecs(ip)
    r = RedirectResponse(suite, status_code=303)
    r.set_cookie(auth.COOKIE, auth.creer_jeton(), max_age=auth.DUREE_SESSION, httponly=True,
                 samesite="lax", secure=auth.https(request), path="/")
    return r


@router.get("/deconnexion")
def deconnexion():
    r = RedirectResponse("/connexion", status_code=303)
    r.delete_cookie(auth.COOKIE, path="/")
    return r
