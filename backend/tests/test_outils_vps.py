"""Outils de deploiement : sauvegarde de la base, ecriture de secrets dans .env."""

import os
import sqlite3
import stat

import pytest

from scripts.definir_env import definir
from scripts.sauvegarde_db import sauvegarder


def test_sauvegarde_coherente_et_rotation(base, tmp_path):
    dossier = tmp_path / "sauv"
    for i in range(4):
        (dossier / f"veille_2026010{i}-000000.db").parent.mkdir(exist_ok=True)
        (dossier / f"veille_2026010{i}-000000.db").write_bytes(b"")
    c = sauvegarder(base, dossier, garder=3)
    assert c.exists()
    with sqlite3.connect(c) as db:
        assert db.execute("SELECT COUNT(*) FROM parametres").fetchone()[0] > 30
    assert len(list(dossier.glob("veille_*.db"))) == 3 and c in dossier.glob("veille_*.db")


def test_definir_env(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# commentaire\nMOT_DE_PASSE_PAGES=\nAUTRE=1\n")
    definir("MOT_DE_PASSE_PAGES", "secret long 123", f)
    definir("NOUVELLE", "x", f)
    contenu = f.read_text()
    assert "MOT_DE_PASSE_PAGES=secret long 123\n" in contenu and "AUTRE=1" in contenu and "NOUVELLE=x" in contenu
    if os.name != "nt":  # droits Unix (VPS, Mac) ; Windows ne gere pas ces droits
        assert stat.S_IMODE(f.stat().st_mode) == 0o600
    with pytest.raises(ValueError):
        definir("cle; rm", "x", f)
    with pytest.raises(ValueError):
        definir("CLE", "a\nINJECTION=1", f)
