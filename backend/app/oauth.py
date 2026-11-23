"""OAuth 2.1 pour le serveur MCP (connecteurs Claude.ai, Claude Code...) : seul J peut autoriser.

Parcours (spec MCP « Authorization ») :
1. /mcp sans jeton -> 401 + WWW-Authenticate: resource_metadata=.../.well-known/oauth-protected-resource
2. Le client lit les metadonnees (RFC 9728 / RFC 8414), s'enregistre (RFC 7591, /oauth/register).
3. /oauth/authorize : J se connecte avec le MOT DE PASSE DES PAGES puis clique « Autoriser » (PKCE S256 obligatoire).
4. /oauth/token : code -> jeton d'acces (1 h) + jeton de renouvellement (30 j, change a chaque usage).

Garde-fous :
- Actif seulement si MOT_DE_PASSE_PAGES est renseigne (VPS) : personne d'autre que J ne peut autoriser.
- Lecture seule : un jeton OAuth donne acces aux outils MCP, rien d'autre (ni pages, ni API, ni reglages).
- Jetons et codes stockes HACHES (SHA-256) : une copie de la base ne donne aucun acces.
- Redirections : https, ou http seulement vers localhost / 127.0.0.1 (Claude Code sur ton PC).
- J voit et revoque les acces dans Reglages > Acces.
"""

import base64
import hashlib
import json
import secrets
import sqlite3
from datetime import timedelta
from urllib.parse import parse_qs, urlencode, urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app import auth
from app.config import get_settings
from app.db import session
from app.util import from_iso, to_iso, utcnow

router = APIRouter(include_in_schema=False)

DUREE_CODE = timedelta(minutes=10)
DUREE_ACCES = timedelta(hours=1)
DUREE_RENOUV = timedelta(days=30)
MAX_CLIENTS = 50
CSRF = "veille_csrf_oauth"


def actif() -> bool:
    return auth.protection_active()


def _h(x: str) -> str:
    return hashlib.sha256(x.encode()).hexdigest()


def base_url(request: Request) -> str:
    pub = get_settings().url_publique.rstrip("/")
    if pub:
        return pub
    proto = "https" if auth.https(request) else request.url.scheme
    return f"{proto}://{request.headers.get('host', request.url.netloc)}"


def redirection_permise(uri: str) -> bool:
    try:
        u = urlsplit(uri)
    except ValueError:
        return False
    if u.username or u.password or u.fragment or not u.hostname:
        return False
    if u.scheme == "https":
        return True
    return u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1", "::1")


# ---------------------------------------------------------------- metadonnees
@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/mcp")
def meta_ressource(request: Request):
    if not actif():
        return JSONResponse({"detail": "OAuth inactif"}, status_code=404)
    b = base_url(request)
    return {"resource": f"{b}/mcp", "authorization_servers": [b], "bearer_methods_supported": ["header"],
            "scopes_supported": ["veille.lecture"], "resource_name": "VEILLE (lecture seule)"}


@router.get("/.well-known/oauth-authorization-server")
@router.get("/.well-known/openid-configuration")
def meta_serveur(request: Request):
    if not actif():
        return JSONResponse({"detail": "OAuth inactif"}, status_code=404)
    b = base_url(request)
    return {"issuer": b, "authorization_endpoint": f"{b}/oauth/authorize", "token_endpoint": f"{b}/oauth/token",
            "registration_endpoint": f"{b}/oauth/register", "revocation_endpoint": f"{b}/oauth/revoke",
            "response_types_supported": ["code"], "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"], "token_endpoint_auth_methods_supported": ["none"],
            "scopes_supported": ["veille.lecture"]}


# ---------------------------------------------------------------- enregistrement (RFC 7591)
@router.post("/oauth/register")
async def enregistrer(request: Request):
    if not actif():
        return JSONResponse({"error": "invalid_request", "error_description": "OAuth inactif"}, status_code=404)
    try:
        d = json.loads((await request.body())[:20000] or b"{}")
    except ValueError:
        return JSONResponse({"error": "invalid_client_metadata"}, status_code=400)
    uris = d.get("redirect_uris")
    if not isinstance(uris, list) or not uris or len(uris) > 5 or \
            not all(isinstance(u, str) and len(u) < 500 and redirection_permise(u) for u in uris):
        return JSONResponse({"error": "invalid_redirect_uri",
                             "error_description": "adresses https (ou http://localhost) attendues"}, status_code=400)
    nom = str(d.get("client_name") or "client MCP")[:80]
    with session(get_settings().db_path) as conn:
        # menage : clients jamais autorises de plus de 7 jours
        conn.execute("DELETE FROM oauth_clients WHERE autorise_le IS NULL AND cree_le < ?",
                     (to_iso(utcnow() - timedelta(days=7)),))
        if conn.execute("SELECT COUNT(*) FROM oauth_clients").fetchone()[0] >= MAX_CLIENTS:
            return JSONResponse({"error": "invalid_request", "error_description": "trop de clients"}, status_code=400)
        cid = "veille-" + secrets.token_urlsafe(18)
        conn.execute("INSERT INTO oauth_clients (client_id, nom, redirect_uris, cree_le) VALUES (?,?,?,?)",
                     (cid, nom, json.dumps(uris), to_iso(utcnow())))
    return JSONResponse({"client_id": cid, "client_name": nom, "redirect_uris": uris,
                         "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
                         "token_endpoint_auth_method": "none", "client_id_issued_at": int(utcnow().timestamp())},
                        status_code=201)


# ---------------------------------------------------------------- autorisation (J clique)
def _client(conn: sqlite3.Connection, cid: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM oauth_clients WHERE client_id = ?", (cid or "",)).fetchone()


def _valider(conn, p: dict) -> tuple[sqlite3.Row | None, str | None]:
    c = _client(conn, p.get("client_id", ""))
    if not c:
        return None, "client inconnu"
    if p.get("redirect_uri") not in json.loads(c["redirect_uris"]):
        return None, "adresse de retour non enregistrée"
    if p.get("response_type") != "code":
        return c, "unsupported_response_type"
    if p.get("code_challenge_method") != "S256" or not p.get("code_challenge"):
        return c, "PKCE S256 obligatoire"
    return c, None


def _page(titre: str, corps: str, code: int = 200) -> HTMLResponse:
    html = ("<!doctype html><html lang='fr'><head><meta charset='utf-8'><meta name='viewport' "
            "content='width=device-width,initial-scale=1'><meta name='robots' content='noindex'><title>VEILLE</title>"
            "<style>body{font:14px/1.45 system-ui,sans-serif;background:#0b1020;color:#eef1ff;display:flex;"
            "justify-content:center;padding:40px 12px}.c{max-width:440px;background:#141a33;border:1px solid "
            "rgba(255,255,255,.2);border-radius:14px;padding:16px}h1{font-size:17px;margin:0 0 8px}"
            ".d{color:rgba(238,241,255,.7);font-size:12px}button{font:inherit;height:34px;padding:0 14px;"
            "border-radius:9px;border:0;cursor:pointer;margin-right:6px}.ok{background:#fff;color:#0b1020;"
            "font-weight:600}.non{background:rgba(255,255,255,.12);color:#eef1ff}code{word-break:break-all}</style>"
            f"</head><body><div class='c'><h1>{titre}</h1>{corps}</div></body></html>")
    return HTMLResponse(html, status_code=code, headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY",
                                                         "Referrer-Policy": "no-referrer"})


def _e(s: str) -> str:
    import html
    return html.escape(s or "", quote=True)


@router.get("/oauth/authorize")
def autoriser_page(request: Request):
    if not actif():
        return _page("OAuth inactif", "<p class='d'>Le mot de passe des pages n'est pas réglé sur ce serveur.</p>", 404)
    p = {k: v for k, v in request.query_params.items()}
    with session(get_settings().db_path) as conn:
        c, err = _valider(conn, p)
    if err and not c:
        return _page("Demande refusée", f"<p class='d'>{_e(err)}</p>", 400)
    if err:
        return RedirectResponse(p["redirect_uri"] + ("&" if "?" in p["redirect_uri"] else "?") + urlencode(
            {"error": "invalid_request", "error_description": err, "state": p.get("state", "")}), status_code=303)
    if not auth.connecte(request):  # connexion avec le mot de passe des pages, puis retour ici
        suite = "/oauth/authorize?" + urlencode(p)
        return RedirectResponse("/connexion?" + urlencode({"suite": suite}), status_code=303)
    jeton = secrets.token_urlsafe(24)
    hote = urlsplit(p["redirect_uri"]).hostname
    champs = "".join(f"<input type='hidden' name='{_e(k)}' value='{_e(v)}'>" for k, v in p.items()
                     if k in ("client_id", "redirect_uri", "state", "code_challenge", "code_challenge_method",
                              "scope", "resource", "response_type"))
    corps = (f"<p><b>{_e(c['nom'])}</b> demande à <b>lire</b> ta veille (événements, synthèses, Journal, recherche).</p>"
             f"<p class='d'>Retour vers : <code>{_e(hote)}</code><br>Accès en lecture seule : aucune modification, "
             "aucun envoi, aucun réglage. Révocable à tout moment dans Réglages &gt; Accès.</p>"
             f"<form method='post' action='/oauth/authorize'>{champs}<input type='hidden' name='csrf' value='{jeton}'>"
             "<button class='ok' name='decision' value='oui'>Autoriser</button>"
             "<button class='non' name='decision' value='non'>Refuser</button></form>")
    r = _page("Autoriser l'accès à VEILLE ?", corps)
    r.set_cookie(CSRF, jeton, httponly=True, samesite="strict", secure=auth.https(request), path="/oauth")
    return r


@router.post("/oauth/authorize")
async def autoriser(request: Request):
    if not actif() or not auth.connecte(request):
        return _page("Connexion requise", "<p class='d'>Reconnecte-toi puis recommence depuis le client.</p>", 401)
    p = {k: v[-1] for k, v in parse_qs((await request.body()).decode("utf-8", "replace")[:10000]).items()}
    if not request.cookies.get(CSRF) or not secrets.compare_digest(request.cookies.get(CSRF, ""), p.get("csrf", "")):
        return _page("Formulaire expiré", "<p class='d'>Recommence depuis le client.</p>", 403)
    with session(get_settings().db_path) as conn:
        c, err = _valider(conn, p)
        if err:
            return _page("Demande refusée", f"<p class='d'>{_e(err)}</p>", 400)
        sep = "&" if "?" in p["redirect_uri"] else "?"
        if p.get("decision") != "oui":
            return RedirectResponse(p["redirect_uri"] + sep + urlencode(
                {"error": "access_denied", "state": p.get("state", "")}), status_code=303)
        code = secrets.token_urlsafe(32)
        conn.execute("INSERT INTO oauth_codes (code_hash, client_id, redirect_uri, code_challenge, expire_le) "
                     "VALUES (?,?,?,?,?)", (_h(code), c["client_id"], p["redirect_uri"], p["code_challenge"],
                                            to_iso(utcnow() + DUREE_CODE)))
        conn.execute("UPDATE oauth_clients SET autorise_le = ? WHERE client_id = ?", (to_iso(utcnow()), c["client_id"]))
    q = {"code": code, **({"state": p["state"]} if p.get("state") else {})}
    return RedirectResponse(p["redirect_uri"] + sep + urlencode(q), status_code=303)


# ---------------------------------------------------------------- jetons
def _erreur(code: str, desc: str = "", statut: int = 400) -> JSONResponse:
    return JSONResponse({"error": code, "error_description": desc}, status_code=statut,
                        headers={"Cache-Control": "no-store"})


def _emettre(conn, client_id: str) -> dict:
    acces, renouv = secrets.token_urlsafe(32), secrets.token_urlsafe(40)
    now = utcnow()
    conn.execute("INSERT INTO oauth_jetons (acces_hash, renouv_hash, client_id, acces_expire_le, renouv_expire_le, "
                 "cree_le) VALUES (?,?,?,?,?,?)", (_h(acces), _h(renouv), client_id, to_iso(now + DUREE_ACCES),
                                                   to_iso(now + DUREE_RENOUV), to_iso(now)))
    return {"access_token": acces, "token_type": "Bearer", "expires_in": int(DUREE_ACCES.total_seconds()),
            "refresh_token": renouv, "scope": "veille.lecture"}


@router.post("/oauth/token")
async def token(request: Request):
    if not actif():
        return _erreur("invalid_request", "OAuth inactif", 404)
    ip = auth.adresse(request)
    if auth.bloque(ip):
        return _erreur("invalid_request", "trop d'essais", 429)
    p = {k: v[-1] for k, v in parse_qs((await request.body()).decode("utf-8", "replace")[:10000]).items()}
    now = utcnow()
    with session(get_settings().db_path) as conn:
        if p.get("grant_type") == "authorization_code":
            r = conn.execute("SELECT * FROM oauth_codes WHERE code_hash = ?", (_h(p.get("code", "")),)).fetchone()
            if not r or r["utilise"] or from_iso(r["expire_le"]) < now or r["client_id"] != p.get("client_id") \
                    or r["redirect_uri"] != p.get("redirect_uri"):
                auth.noter_echec(ip)
                return _erreur("invalid_grant", "code invalide, expiré ou déjà utilisé")
            verif = base64.urlsafe_b64encode(hashlib.sha256(p.get("code_verifier", "").encode()).digest()).rstrip(b"=")
            if not secrets.compare_digest(verif.decode(), r["code_challenge"]):
                auth.noter_echec(ip)
                return _erreur("invalid_grant", "PKCE incorrect")
            conn.execute("UPDATE oauth_codes SET utilise = 1 WHERE code_hash = ?", (r["code_hash"],))
            return JSONResponse(_emettre(conn, r["client_id"]), headers={"Cache-Control": "no-store"})
        if p.get("grant_type") == "refresh_token":
            r = conn.execute("SELECT * FROM oauth_jetons WHERE renouv_hash = ?", (_h(p.get("refresh_token", "")),)).fetchone()
            if not r or r["revoque"] or from_iso(r["renouv_expire_le"]) < now or \
                    (p.get("client_id") and p["client_id"] != r["client_id"]):
                auth.noter_echec(ip)
                return _erreur("invalid_grant", "jeton de renouvellement invalide")
            conn.execute("UPDATE oauth_jetons SET revoque = 1 WHERE id = ?", (r["id"],))  # rotation
            return JSONResponse(_emettre(conn, r["client_id"]), headers={"Cache-Control": "no-store"})
    return _erreur("unsupported_grant_type")


@router.post("/oauth/revoke")
async def revoquer_jeton(request: Request):
    p = {k: v[-1] for k, v in parse_qs((await request.body()).decode("utf-8", "replace")[:10000]).items()}
    t = _h(p.get("token", ""))
    with session(get_settings().db_path) as conn:
        conn.execute("UPDATE oauth_jetons SET revoque = 1 WHERE acces_hash = ? OR renouv_hash = ?", (t, t))
    return JSONResponse({}, status_code=200)


def acces_valide(jeton: str) -> bool:
    """Jeton d'acces OAuth valide (non expire, non revoque) ?"""
    if not jeton or not actif():
        return False
    with session(get_settings().db_path) as conn:
        r = conn.execute("SELECT acces_expire_le, revoque FROM oauth_jetons WHERE acces_hash = ?", (_h(jeton),)).fetchone()
        if r and not r["revoque"] and from_iso(r["acces_expire_le"]) > utcnow():
            conn.execute("UPDATE oauth_jetons SET dernier_usage_le = ? WHERE acces_hash = ?", (to_iso(utcnow()), _h(jeton)))
            return True
    return False


# ---------------------------------------------------------------- pour la page Reglages > Acces
def acces_en_cours(conn: sqlite3.Connection) -> list[dict]:
    now = to_iso(utcnow())
    return [dict(r) for r in conn.execute(
        "SELECT c.client_id, c.nom, c.redirect_uris, c.autorise_le, MAX(j.dernier_usage_le) AS dernier_usage, "
        "COUNT(j.id) AS jetons FROM oauth_clients c JOIN oauth_jetons j ON j.client_id = c.client_id "
        "WHERE j.revoque = 0 AND j.renouv_expire_le > ? GROUP BY c.client_id ORDER BY c.autorise_le DESC", (now,))]


def revoquer_client(conn: sqlite3.Connection, client_id: str) -> int:
    n = conn.execute("UPDATE oauth_jetons SET revoque = 1 WHERE client_id = ? AND revoque = 0", (client_id,)).rowcount
    conn.execute("UPDATE oauth_codes SET utilise = 1 WHERE client_id = ?", (client_id,))
    return n
