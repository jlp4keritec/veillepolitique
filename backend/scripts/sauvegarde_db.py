"""Sauvegarde coherente de la base SQLite (idempotent, sans arreter VEILLE).

Usage : python scripts/sauvegarde_db.py [dossier] [nombre_a_garder]
  defaut : ~/backups/veille, 30 sauvegardes gardees (les plus anciennes sont supprimees).
Utilise l'API de sauvegarde SQLite : copie coherente meme pendant l'ecriture.
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402


def sauvegarder(source: Path, dossier: Path, garder: int = 30) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / f"veille_{datetime.now():%Y%m%d-%H%M%S}.db"
    with sqlite3.connect(source) as src, sqlite3.connect(cible) as dst:
        src.backup(dst)
    with sqlite3.connect(cible) as verif:
        if verif.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError(f"sauvegarde corrompue : {cible}")
    for vieux in sorted(dossier.glob("veille_*.db"))[:-garder]:
        vieux.unlink()
    return cible


if __name__ == "__main__":
    dossier = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else Path.home() / "backups" / "veille"
    garder = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    c = sauvegarder(get_settings().db_path, dossier, garder)
    print(f"[OK] {c} ({c.stat().st_size // 1024} Ko)")
