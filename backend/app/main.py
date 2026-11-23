"""API locale VEILLE (ecoute uniquement sur 127.0.0.1).

Sert a consulter et regler le systeme (F10, F11, F12) et au futur dashboard.
Pas d'authentification : ne JAMAIS l'exposer sur internet sans protection.
"""

import json
import logging
from urllib.parse import quote
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from app import __version__, auth, parametres, reglages
from app.config import get_settings
from app.db import get_etat, session
from app.ia import etat_budget
from app.initialisation import initialiser
from app.orchestrateur import Orchestrateur
from app.recherche import chercher_articles, chronologie
from app.sources import SourceIn, lister_sources
from app.util import from_iso, utcnow

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
ETAT: dict = {}
_FICHIER_DEPLOIEMENT = Path(__file__).resolve().parent.parent / "DEPLOIEMENT"
DEPLOIEMENT = _FICHIER_DEPLOIEMENT.read_text(encoding="utf-8").strip() if _FICHIER_DEPLOIEMENT.exists() else "local"


def verifier_production(s) -> None:
    """Sur le VPS (ENVIRONNEMENT=vps), refuse de demarrer sans mot de passe des pages solide."""
    if s.environnement.strip().lower() != "vps":
        return
    mdp = s.mot_de_passe_pages.get_secret_value()
    if len(mdp) < 12:
        raise RuntimeError("ENVIRONNEMENT=vps : MOT_DE_PASSE_PAGES obligatoire (12 caracteres minimum) "
                           "dans backend/.env. Demarrage refuse pour ne pas exposer la veille.")


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    verifier_production(s)
    initialiser(s.db_path)
    ETAT["orch"] = Orchestrateur(s.db_path)
    if s.scheduler_actif:
        from app.planificateur import demarrer
        ETAT["sched"] = demarrer(ETAT["orch"])
    yield
    if ETAT.get("sched"):
        ETAT["sched"].shutdown(wait=False)
    ETAT.clear()


app = FastAPI(title="VEILLE", version=__version__, lifespan=lifespan)


@app.middleware("http")
async def protection(request: Request, call_next):
    """Si un mot de passe est regle : tout est protege sauf /connexion et /api/v1/health."""
    chemin = request.url.path
    if (auth.protection_active() and chemin not in auth.PUBLIC and not chemin.startswith("/mcp")
            and not auth.connecte(request)):  # /mcp : protege par son propre jeton (mcp_serveur.py)
        if chemin.startswith("/api/") or chemin in ("/docs", "/openapi.json", "/redoc"):
            return JSONResponse({"detail": "connexion requise"}, status_code=401)
        suite = chemin + (f"?{request.url.query}" if request.url.query else "")
        return RedirectResponse(f"/connexion?suite={quote(suite)}", status_code=303)
    return await call_next(request)


from app.mcp_serveur import router as mcp_router  # noqa: E402
from app.pages import router as pages_router  # noqa: E402

app.include_router(pages_router)
app.include_router(mcp_router)


def db():
    return session(get_settings().db_path)


def _orch() -> Orchestrateur:
    return ETAT.get("orch") or Orchestrateur(get_settings().db_path)


def _decode(row, champs=("themes", "acteurs", "score_details", "tendance_details", "verification_details")):
    d = dict(row)
    for c in champs:
        if c in d and isinstance(d[c], str):
            d[c] = json.loads(d[c])
    return d


@app.get("/api/v1/health")
def health() -> dict:
    s = get_settings()
    with db() as conn:
        nb = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        nb_actives = conn.execute("SELECT COUNT(*) FROM sources WHERE actif = 1").fetchone()[0]
        p = parametres.tous(conn)
        dernier = get_etat(conn, "dernier_cycle")
        b = etat_budget(conn, utcnow())
    return {
        "status": "ok",
        "version": __version__,
        "deploiement": DEPLOIEMENT,
        "sources": nb,
        "sources_actives": nb_actives,
        "collecte_active": p["collecte_active"],
        "planificateur": bool(ETAT.get("sched")),
        "dernier_cycle": dernier,
        "budget": {"depense_eur": b["depense_eur"], "budget_eur": b["budget_eur"], "pct": b["pct"]},
        # On indique seulement SI les secrets sont renseignes, jamais leur valeur
        "config": {
            "anthropic_api_key": bool(s.anthropic_api_key.get_secret_value()),
            "telegram_bot_token": bool(s.telegram_bot_token.get_secret_value()),
            "telegram_chat_id": bool(s.telegram_chat_id),
            "budget_mensuel_eur": p["budget_mensuel_eur"],
        },
    }


# ---------------------------------------------------------------- sources (F11)
class SourcePatch(BaseModel):
    actif: Literal[0, 1] | None = None
    frequence_minutes: int | None = Field(default=None, ge=5)
    priorite: int | None = Field(default=None, ge=1, le=3)
    fiabilite: int | None = Field(default=None, ge=1, le=5)
    nom: str | None = Field(default=None, min_length=1, max_length=200)


@app.get("/api/v1/sources")
def sources() -> list[dict]:
    return lister_sources(get_settings().db_path)


@app.post("/api/v1/sources", status_code=201)
def ajouter_source(s: SourceIn) -> dict:
    try:
        reglages.adresse_publique(str(s.url))  # jamais une adresse privee (serveur, VPN, maison)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    with db() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO sources (nom, url, type, categorie, niveau, zone, fiabilite, priorite, "
            "frequence_minutes, actif, note) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (s.nom, str(s.url), s.type, s.categorie, s.niveau, s.zone, s.fiabilite, s.priorite,
             s.frequence_minutes, s.actif, s.note))
        if cur.rowcount == 0:
            raise HTTPException(409, "cette URL existe deja")
        return {"id": cur.lastrowid}


@app.patch("/api/v1/sources/{source_id}")
def modifier_source(source_id: int, patch: SourcePatch) -> dict:
    champs = patch.model_dump(exclude_none=True)
    if not champs:
        raise HTTPException(400, "rien a modifier")
    with db() as conn:
        n = conn.execute(f"UPDATE sources SET {', '.join(f'{k} = ?' for k in champs)} WHERE id = ?",
                         (*champs.values(), source_id)).rowcount
        if not n:
            raise HTTPException(404, "source introuvable")
    return {"id": source_id, **champs}


# ---------------------------------------------------------------- parametres (F11)
class Valeur(BaseModel):
    valeur: Any


@app.get("/api/v1/parametres")
def lire_parametres() -> dict:
    with db() as conn:
        vals = parametres.tous(conn)
    return {k: {"valeur": v, "description": parametres.DEFAUTS[k][1]} for k, v in vals.items()}


@app.put("/api/v1/parametres/{cle}")
def modifier_parametre(cle: str, corps: Valeur) -> dict:
    with db() as conn:
        try:
            return {"cle": cle, "valeur": parametres.modifier(conn, cle, corps.valeur, origine="api")}
        except KeyError:
            raise HTTPException(404, "parametre inconnu") from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None


@app.get("/api/v1/themes")
def themes() -> dict:
    with db() as conn:
        return {r["nom"]: {"mots_cles": json.loads(r["mots_cles"]), "actif": r["actif"]}
                for r in conn.execute("SELECT * FROM themes ORDER BY nom")}


class Theme(BaseModel):
    mots_cles: list[str] = Field(min_length=1)
    actif: Literal[0, 1] = 1


@app.put("/api/v1/themes/{nom}")
def modifier_theme(nom: str, t: Theme) -> dict:
    with db() as conn:
        conn.execute("INSERT INTO themes (nom, mots_cles, actif) VALUES (?,?,?) ON CONFLICT(nom) DO UPDATE "
                     "SET mots_cles = excluded.mots_cles, actif = excluded.actif",
                     (nom, json.dumps(t.mots_cles, ensure_ascii=False), t.actif))
    return {"nom": nom, **t.model_dump()}


# ---------------------------------------------------------------- historique (F10)
@app.get("/api/v1/evenements")
def evenements(depuis: str | None = None, score_min: int = 0, limite: int = Query(50, le=500)) -> list[dict]:
    sql, args = "SELECT * FROM evenements WHERE score >= ?", [score_min]
    if depuis:
        sql += " AND dernier_article_le >= ?"
        args.append(depuis)
    with db() as conn:
        return [_decode(r) for r in conn.execute(sql + " ORDER BY dernier_article_le DESC LIMIT ?", (*args, limite))]


@app.get("/api/v1/evenements/{evt_id}")
def evenement(evt_id: int) -> dict:
    with db() as conn:
        r = conn.execute("SELECT * FROM evenements WHERE id = ?", (evt_id,)).fetchone()
        if not r:
            raise HTTPException(404, "evenement introuvable")
        return {**_decode(r), "chronologie": [dict(a) for a in chronologie(conn, evt_id)]}


@app.get("/api/v1/articles")
def articles(q: str = "", theme: str | None = None, source_id: int | None = None, zone: str | None = None,
             acteur: str | None = None, du: str | None = None, au: str | None = None,
             limite: int = Query(50, le=500)) -> list[dict]:
    with db() as conn:
        rows = chercher_articles(conn, q.split()[:5], from_iso(du) if du else None, from_iso(au) if au else None,
                                 theme, source_id, zone, acteur, limite)
    return [dict(r) for r in rows]


@app.get("/api/v1/notifications")
def notifications(type: str | None = None, limite: int = Query(50, le=500)) -> list[dict]:
    with db() as conn:
        sql = "SELECT * FROM notifications" + (" WHERE type = ?" if type else "") + " ORDER BY id DESC LIMIT ?"
        return [dict(r) for r in conn.execute(sql, ((type, limite) if type else (limite,)))]


@app.get("/api/v1/journal")
def journal(niveau: str | None = None, limite: int = Query(100, le=1000)) -> list[dict]:
    with db() as conn:
        sql = "SELECT * FROM journal" + (" WHERE niveau = ?" if niveau else "") + " ORDER BY id DESC LIMIT ?"
        return [dict(r) for r in conn.execute(sql, ((niveau, limite) if niveau else (limite,)))]


@app.get("/api/v1/couts")
def couts() -> dict:
    with db() as conn:
        return etat_budget(conn, utcnow())


# ---------------------------------------------------------------- actions
class Question(BaseModel):
    texte: str = Field(min_length=2, max_length=500)


@app.post("/api/v1/question")
def poser_question(q: Question) -> dict:
    return {"reponse_html": _orch().question(q.texte)}


@app.post("/api/v1/cycle")
def lancer_cycle() -> dict:
    return _orch().cycle()


@app.post("/api/v1/syntheses/{type_}")
def lancer_synthese(type_: Literal["point", "briefing", "synthese"]) -> dict:
    return {"envoye": _orch().envoyer_synthese(type_)}


@app.post("/api/v1/pause")
def pause() -> dict:
    with db() as conn:
        parametres.modifier(conn, "collecte_active", False)
    return {"collecte_active": False}


@app.post("/api/v1/reprise")
def reprise() -> dict:
    with db() as conn:
        parametres.modifier(conn, "collecte_active", True)
    return {"collecte_active": True}
