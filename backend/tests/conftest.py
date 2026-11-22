"""Outils de test communs. Aucun test n'utilise le reseau ni la vraie base."""

from datetime import datetime, timezone
from email.utils import format_datetime

import httpx
import pytest

from app.config import get_settings
from app.db import connect
from app.initialisation import initialiser


@pytest.fixture
def base(tmp_path, monkeypatch):
    """Base temporaire initialisee (parametres + themes), sans les sources par defaut."""
    path = tmp_path / "veille_test.db"
    monkeypatch.setenv("VEILLE_DB_PATH", str(path))
    for k in ("ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.setenv(k, "")
    monkeypatch.setenv("SCHEDULER_ACTIF", "0")
    get_settings.cache_clear()
    initialiser(path, avec_sources=False)
    yield path
    get_settings.cache_clear()


@pytest.fixture
def conn(base):
    c = connect(base)
    yield c
    c.commit()
    c.close()


def ajouter_source(conn, nom="Media test", url="https://media.test/rss", zone="national",
                   categorie="media", niveau=2, fiabilite=4, frequence=15):
    cur = conn.execute(
        "INSERT INTO sources (nom, url, type, categorie, niveau, zone, fiabilite, priorite, "
        "frequence_minutes, actif) VALUES (?,?,?,?,?,?,?,1,?,1)",
        (nom, url, "rss", categorie, niveau, zone, fiabilite, frequence))
    conn.commit()
    return cur.lastrowid


def rss(items: list[tuple[str, str, datetime, str]]) -> bytes:
    """Construit un flux RSS 2.0 : items = (titre, lien, date, resume)."""
    corps = "".join(
        f"<item><title>{t}</title><link>{l}</link><guid>{l}</guid>"
        f"<pubDate>{format_datetime(d)}</pubDate><description>{r}</description></item>"
        for t, l, d, r in items)
    return (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
            f"<title>Test</title><link>https://media.test</link>{corps}</channel></rss>").encode()


def client_mock(routes: dict[str, bytes | int]) -> httpx.Client:
    """Client HTTP simule : url -> contenu RSS ou code d'erreur."""
    def handler(req: httpx.Request) -> httpx.Response:
        val = routes.get(str(req.url))
        if val is None:
            return httpx.Response(404)
        if isinstance(val, int):
            return httpx.Response(val)
        return httpx.Response(200, content=val, headers={"ETag": '"v1"'})
    return httpx.Client(transport=httpx.MockTransport(handler))


T0 = datetime(2026, 11, 22, 9, 0, tzinfo=timezone.utc)
