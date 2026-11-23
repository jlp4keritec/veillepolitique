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
    assert len(sources) >= 15
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


def test_sources_trouvees_mises_a_jour_si_non_modifiees(db):
    import sqlite3 as sq
    with sq.connect(db) as c:  # etat d'une base v0.1 : Senat et Progres "a identifier"
        for nom, url in (("Senat", "https://www.senat.fr/"), ("Le Progres - Lyon", "https://www.leprogres.fr/")):
            c.execute("INSERT INTO sources (nom,url,type,categorie,niveau,zone,frequence_minutes,actif) "
                      "VALUES (?,?,'site','media',2,'national',30,0)", (nom, url))
        c.execute("UPDATE sources SET actif = 1 WHERE url = 'https://www.leprogres.fr/'")  # modifiee par J
    seed_sources(db)
    urls = {s["url"]: s for s in lister_sources(db)}
    assert "https://www.senat.fr/rss/presse.rss" in urls and urls["https://www.senat.fr/rss/presse.rss"]["actif"] == 1
    assert "https://www.senat.fr/" not in urls
    assert "https://www.leprogres.fr/" in urls  # J l'avait modifiee : jamais touchee
    assert seed_sources(db) == 0  # idempotent


def test_flux_officiels_trouves_mis_a_jour(db):
    """Base existante : les 3 sources 'site' desactivees passent sur leur flux RSS (23/11/2026),
    sans doublon ; une source modifiee par J (ici reactivee) n'est pas touchee."""
    anciennes = {
        "https://www.info.gouv.fr/": "Gouvernement - info.gouv.fr",
        "https://www.assemblee-nationale.fr/": "Assemblee nationale",
        "https://www.grandlyon.com/": "Metropole de Lyon",
    }
    with sqlite3.connect(db) as c:
        for url, nom in anciennes.items():
            actif = 1 if "grandlyon" in url else 0  # J a touche a celle-ci
            c.execute(
                "INSERT INTO sources (nom,url,type,categorie,niveau,zone,frequence_minutes,actif)"
                " VALUES (?,?,'site','institutionnel',1,'national',60,?)", (nom, url, actif))
    seed_sources(db)
    par_url = {s["url"]: s for s in lister_sources(db)}
    for url in ("https://www.info.gouv.fr/rss/actualites.xml",
                "https://www2.assemblee-nationale.fr/feeds/detail/crs"):
        assert par_url[url]["type"] == "rss" and par_url[url]["actif"] == 1
    assert "https://www.info.gouv.fr/" not in par_url
    assert "https://www.assemblee-nationale.fr/" not in par_url
    # modifiee par J : conservee telle quelle ; le nouveau flux est ajoute a cote
    assert par_url["https://www.grandlyon.com/"]["type"] == "site"
    assert "https://www.grandlyon.com/actualites.xml" in par_url
    assert len(par_url) == len(charger_defaut()) + 1
