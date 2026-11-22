"""Tests du socle : base, sources par defaut, API, protection des secrets."""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import init_schema
from app.sources import charger_defaut, lister_sources, seed_sources

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Base temporaire : les tests ne touchent jamais la vraie base."""
    path = tmp_path / "test.db"
    monkeypatch.setenv("VEILLE_DB_PATH", str(path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-de-test-123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    monkeypatch.setenv("SCHEDULER_ACTIF", "0")
    get_settings.cache_clear()
    init_schema(path)
    yield path
    get_settings.cache_clear()


def test_sources_defaut_valides():
    sources = charger_defaut()
    assert len(sources) >= 10
    urls = [str(s.url) for s in sources]
    assert len(urls) == len(set(urls)), "URL en double dans sources_defaut.json"
    assert any(s.zone == "regional" for s in sources)
    assert any(s.categorie == "institutionnel" for s in sources)


def test_seed_idempotent(db):
    n1 = seed_sources(db)
    n2 = seed_sources(db)
    assert n1 == len(charger_defaut())
    assert n2 == 0
    assert len(lister_sources(db)) == n1


def test_seed_n_ecrase_pas_les_modifs(db):
    seed_sources(db)
    with sqlite3.connect(db) as c:
        c.execute("UPDATE sources SET actif = 0, frequence_minutes = 240 WHERE id = 1")
    seed_sources(db)
    s = next(x for x in lister_sources(db) if x["id"] == 1)
    assert s["actif"] == 0 and s["frequence_minutes"] == 240


def test_sources_non_verifiees_par_defaut(db):
    seed_sources(db)
    assert all(s["url_verifiee"] == 0 for s in lister_sources(db))


def test_schema_refuse_valeur_invalide(db):
    with sqlite3.connect(db) as c, pytest.raises(sqlite3.IntegrityError):
        c.execute(
            "INSERT INTO sources (nom,url,type,categorie,niveau,zone,frequence_minutes)"
            " VALUES ('x','http://x','pigeon','media',2,'national',15)"
        )


def test_api_health_et_sources(db):
    seed_sources(db)
    from app.main import app

    with TestClient(app) as client:
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["sources"] == len(charger_defaut())
        assert body["config"]["telegram_bot_token"] is True
        assert "secret-de-test-123" not in r.text, "un secret fuit dans l'API"

        r = client.get("/api/v1/sources")
        assert r.status_code == 200 and len(r.json()) == body["sources"]


def test_env_exclu_de_git():
    lignes = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in lignes
    assert "backend/data/*.db" in lignes
