"""OAuth du serveur MCP : seul J autorise (mot de passe des pages), PKCE, renouvellement, revocation,
et le jeton fixe de LILY continue de fonctionner."""

import base64
import hashlib
import re
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from tests.test_pages import donnees  # noqa: F401  (fixture)

MDP = "mot-de-passe-des-pages-123"
JETON_LILY = "jeton-fixe-de-lily-0123456789abcdef"
RETOUR = "https://claude.ai/api/mcp/auth_callback"
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}}}


@pytest.fixture
def c(donnees, monkeypatch):  # noqa: F811
    monkeypatch.setenv("MOT_DE_PASSE_PAGES", MDP)
    monkeypatch.setenv("MCP_TOKEN", JETON_LILY)
    get_settings.cache_clear()
    from app import auth
    from app.main import app
    auth._echecs.clear()
    with TestClient(app, base_url="https://veille.test") as client:
        yield client
    get_settings.cache_clear()


def pkce():
    v = "verificateur-" + "x" * 50
    return v, base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()


def enregistrer(c, uris=(RETOUR,)):
    return c.post("/oauth/register", json={"client_name": "Claude", "redirect_uris": list(uris)})


def parcours(c, verif=None):
    """Enregistrement -> connexion de J -> Autoriser -> code -> jetons."""
    cid = enregistrer(c).json()["client_id"]
    v, chal = pkce()
    q = {"response_type": "code", "client_id": cid, "redirect_uri": RETOUR, "code_challenge": chal,
         "code_challenge_method": "S256", "state": "etat123", "resource": "https://veille.test/mcp"}
    r = c.get("/oauth/authorize", params=q, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/connexion")     # pas connecte : connexion
    suite = parse_qs(urlsplit(r.headers["location"]).query)["suite"][0]
    r = c.post("/connexion", data={"mot_de_passe": MDP, "suite": suite}, follow_redirects=False)
    assert r.headers["location"] == suite
    r = c.get(suite)
    assert "Autoriser l" in r.text and "Claude" in r.text and "claude.ai" in r.text
    form = dict(re.findall(r"name='([^']+)' value='([^']*)'", r.text))
    r = c.post("/oauth/authorize", data={**form, "decision": "oui"}, follow_redirects=False)
    loc = urlsplit(r.headers["location"])
    assert f"{loc.scheme}://{loc.netloc}{loc.path}" == RETOUR
    qs = parse_qs(loc.query)
    assert qs["state"] == ["etat123"]
    r = c.post("/oauth/token", data={"grant_type": "authorization_code", "code": qs["code"][0], "client_id": cid,
                                     "redirect_uri": RETOUR, "code_verifier": verif or v})
    return cid, qs["code"][0], v, r


def test_metadonnees_et_401(c):
    r = c.post("/mcp", json=INIT)
    assert r.status_code == 401
    assert 'resource_metadata="https://veille.test/.well-known/oauth-protected-resource"' in r.headers["www-authenticate"]
    m = c.get("/.well-known/oauth-protected-resource").json()
    assert m["authorization_servers"] == ["https://veille.test"] and m["resource"] == "https://veille.test/mcp"
    s = c.get("/.well-known/oauth-authorization-server").json()
    assert s["code_challenge_methods_supported"] == ["S256"] and s["registration_endpoint"].endswith("/oauth/register")
    from app import auth
    assert not any(auth._echecs.values())           # une demande SANS jeton ne compte pas comme essai rate


def test_parcours_complet_puis_mcp(c, conn):
    cid, code, v, r = parcours(c)
    j = r.json()
    assert r.status_code == 200 and j["token_type"] == "Bearer" and j["refresh_token"]
    h = {"Authorization": f"Bearer {j['access_token']}"}
    assert c.post("/mcp", json=INIT, headers=h).status_code == 200
    r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                             "params": {"name": "veille_lister_evenements", "arguments": {}}}, headers=h)
    assert "Motion de censure" in r.text
    # code a usage unique
    r2 = c.post("/oauth/token", data={"grant_type": "authorization_code", "code": code, "client_id": cid,
                                      "redirect_uri": RETOUR, "code_verifier": v})
    assert r2.status_code == 400
    # rien n'est stocke en clair
    assert not conn.execute("SELECT 1 FROM oauth_jetons WHERE acces_hash = ?", (j["access_token"],)).fetchone()
    # un jeton OAuth n'ouvre PAS les pages ni l'API
    c.cookies.clear()
    assert c.get("/api/v1/sources", headers=h).status_code == 401


def test_pkce_faux_refuse(c):
    _cid, _code, _v, r = parcours(c, verif="mauvais-verificateur-" + "y" * 40)
    assert r.status_code == 400 and r.json()["error"] == "invalid_grant"


def test_renouvellement_avec_rotation_et_revocation(c):
    cid, _code, _v, r = parcours(c)
    j = r.json()
    r = c.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": j["refresh_token"], "client_id": cid})
    assert r.status_code == 200
    j2 = r.json()
    assert c.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": j["refresh_token"]}).status_code == 400
    h2 = {"Authorization": f"Bearer {j2['access_token']}"}
    assert c.post("/mcp", json=INIT, headers=h2).status_code == 200
    # J revoque dans Reglages > Acces
    page = c.get("/reglages?onglet=acces")
    assert "Clients autorisés" in page.text and "Claude" in page.text
    jeton = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    r = c.post("/reglages/acces/revoquer", data={"csrf": jeton, "client_id": cid}, follow_redirects=True)
    assert "Accès révoqué" in r.text
    assert c.post("/mcp", json=INIT, headers=h2).status_code == 401


def test_refus_et_controles(c):
    assert enregistrer(c, ["http://pirate.exemple/cb"]).status_code == 400          # http hors localhost
    assert enregistrer(c, ["http://localhost:33418/callback"]).status_code == 201     # Claude Code
    cid = enregistrer(c).json()["client_id"]
    _v, chal = pkce()
    base = {"response_type": "code", "client_id": cid, "code_challenge": chal, "code_challenge_method": "S256"}
    r = c.get("/oauth/authorize", params={**base, "redirect_uri": "https://autre.exemple/cb"})
    assert r.status_code == 400                                                       # retour non enregistre
    r = c.get("/oauth/authorize", params={**base, "redirect_uri": RETOUR, "code_challenge_method": "plain"},
              follow_redirects=False)
    assert "error=invalid_request" in r.headers["location"]                           # PKCE S256 obligatoire
    assert c.post("/oauth/token", data={"grant_type": "password"}).status_code == 400


def test_j_peut_refuser(c):
    cid = enregistrer(c).json()["client_id"]
    _v, chal = pkce()
    c.post("/connexion", data={"mot_de_passe": MDP, "suite": "/"})
    r = c.get("/oauth/authorize", params={"response_type": "code", "client_id": cid, "redirect_uri": RETOUR,
                                          "code_challenge": chal, "code_challenge_method": "S256", "state": "s"})
    form = dict(re.findall(r"name='([^']+)' value='([^']*)'", r.text))
    r = c.post("/oauth/authorize", data={**form, "decision": "non"}, follow_redirects=False)
    assert "error=access_denied" in r.headers["location"]
    assert c.post("/oauth/authorize", data={**form, "csrf": "faux", "decision": "oui"}).status_code == 403


def test_lily_jeton_fixe_inchange(c):
    """OAuth actif : le jeton fixe de LILY marche exactement comme avant."""
    h = {"Authorization": f"Bearer {JETON_LILY}"}
    assert c.post("/mcp", json=INIT, headers=h).status_code == 200
    r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=h)
    assert len(r.json()["result"]["tools"]) == 8
    assert c.post("/mcp", json=INIT, headers={"Authorization": "Bearer faux"}).status_code == 401


def test_oauth_inactif_sans_mot_de_passe(base, monkeypatch):
    monkeypatch.setenv("MOT_DE_PASSE_PAGES", "")
    monkeypatch.setenv("MCP_TOKEN", "")
    get_settings.cache_clear()
    from app.main import app
    with TestClient(app) as client:
        assert client.get("/.well-known/oauth-authorization-server").status_code == 404
        assert client.post("/oauth/register", json={"redirect_uris": [RETOUR]}).status_code == 404
        assert client.post("/mcp", json=INIT).status_code == 404
    get_settings.cache_clear()
