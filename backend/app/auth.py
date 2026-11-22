"""Protection par mot de passe des pages et de l'API (si MOT_DE_PASSE_PAGES est renseigne).

- Mot de passe vide (Mac, usage local) : aucune protection.
- Mot de passe renseigne (VPS) : tout est protege sauf /connexion et /api/v1/health.
- Session : cookie signe (HMAC), valable 30 jours, HttpOnly, SameSite=Lax, Secure en HTTPS.
  Changer le mot de passe deconnecte toutes les sessions.
- Plus de 5 essais rates en 15 minutes depuis une meme adresse : blocage temporaire.
"""

import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.config import get_settings
from app.db import get_etat, session, set_etat

COOKIE = "veille_session"
DUREE_SESSION = 30 * 24 * 3600
ESSAIS_MAX = 5
FENETRE_ESSAIS = 15 * 60
PUBLIC = {"/connexion", "/api/v1/health"}

_echecs: dict[str, deque] = defaultdict(deque)
_verrou = threading.Lock()


def mot_de_passe() -> str:
    return get_settings().mot_de_passe_pages.get_secret_value()


def protection_active() -> bool:
    return bool(mot_de_passe())


def _cle() -> bytes:
    """Cle de signature : secret aleatoire stocke en base + empreinte du mot de passe."""
    s = get_settings()
    with session(s.db_path) as conn:
        secret = get_etat(conn, "session_secret")
        if not secret:
            secret = secrets.token_hex(32)
            set_etat(conn, "session_secret", secret)
    return hashlib.sha256((secret + "|" + mot_de_passe()).encode()).digest()


def creer_jeton(maintenant: float | None = None) -> str:
    expire = int((maintenant or time.time()) + DUREE_SESSION)
    sig = hmac.new(_cle(), str(expire).encode(), hashlib.sha256).hexdigest()
    return f"{expire}.{sig}"


def jeton_valide(jeton: str | None, maintenant: float | None = None) -> bool:
    if not jeton or "." not in jeton:
        return False
    expire, _, sig = jeton.partition(".")
    if not expire.isdigit() or int(expire) < (maintenant or time.time()):
        return False
    attendu = hmac.new(_cle(), expire.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, attendu)


def adresse(request: Request) -> str:
    """Adresse du visiteur ; derriere Nginx (local), on lit X-Real-IP."""
    hote = request.client.host if request.client else "?"
    if hote in ("127.0.0.1", "::1"):
        return request.headers.get("x-real-ip", hote)
    return hote


def bloque(ip: str, maintenant: float | None = None) -> bool:
    t = maintenant or time.time()
    with _verrou:
        q = _echecs[ip]
        while q and q[0] < t - FENETRE_ESSAIS:
            q.popleft()
        return len(q) >= ESSAIS_MAX


def noter_echec(ip: str, maintenant: float | None = None) -> None:
    with _verrou:
        _echecs[ip].append(maintenant or time.time())


def oublier_echecs(ip: str) -> None:
    with _verrou:
        _echecs.pop(ip, None)


def verifier_mot_de_passe(propose: str) -> bool:
    return hmac.compare_digest(propose.encode(), mot_de_passe().encode())


def connecte(request: Request) -> bool:
    return not protection_active() or jeton_valide(request.cookies.get(COOKIE))


def https(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
