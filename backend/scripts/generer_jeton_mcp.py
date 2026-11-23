"""Cree (ou remplace avec --nouveau) le jeton du serveur MCP dans backend/.env et l'affiche UNE fois.

Usage : python scripts/generer_jeton_mcp.py [--nouveau]
- Sans --nouveau : si un jeton existe deja, il n'est pas change (rien n'est affiche).
- Le jeton s'affiche dans TON terminal seulement : ne le colle jamais dans un chat.
- Redemarrer VEILLE ensuite pour qu'il soit pris en compte.
"""

import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.definir_env import ENV, definir  # noqa: E402


def jeton_actuel() -> str:
    if not ENV.exists():
        return ""
    for ligne in ENV.read_text(encoding="utf-8").splitlines():
        if ligne.startswith("MCP_TOKEN="):
            return ligne.split("=", 1)[1].strip()
    return ""


if __name__ == "__main__":
    if jeton_actuel() and "--nouveau" not in sys.argv:
        print("[OK] Un jeton MCP existe deja (non affiche). Pour le remplacer : --nouveau")
        sys.exit(0)
    jeton = secrets.token_urlsafe(32)
    definir("MCP_TOKEN", jeton)
    print("[OK] Jeton MCP enregistre dans backend/.env. A recopier dans Claude / LILY (jamais dans un chat) :")
    print(jeton)
