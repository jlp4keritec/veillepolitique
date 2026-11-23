"""Cycle complet, horloge 08:00 / 20:00 / points, commandes Telegram entrantes, API."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from fastapi.testclient import TestClient

from app.db import connect
from app.ia import ClientIA
from app.orchestrateur import Orchestrateur
from tests.conftest import ajouter_source, client_mock, rss
from tests.test_alertes_syntheses import TITRE, FauxTelegram

PARIS = ZoneInfo("Europe/Paris")


def paris(h, m=0, jour=23):
    return datetime(2026, 11, jour, h, m, tzinfo=PARIS).astimezone(ZoneInfo("UTC"))


def _orch(base, conn, now, n=4):
    routes = {}
    for i in range(n):
        url = f"https://s{i}.test/rss"
        ajouter_source(conn, nom=f"S{i}", url=url)
        routes[url] = rss([(f"{TITRE} {'!' * i}", f"https://s{i}.test/a", now - timedelta(minutes=5 + i), "x"),
                           ("Recette du gratin dauphinois", f"https://s{i}.test/g", now, "")])
    tg = FauxTelegram()
    return Orchestrateur(base, http=client_mock(routes), tg=tg, ia=ClientIA("")), tg


def test_cycle_complet(base, conn):
    now = paris(10)
    orch, tg = _orch(base, conn, now)
    r = orch.cycle(now)
    assert r["collecte"] == {"sources": 4, "erreurs": 0, "nouveaux": 8}
    assert r["pertinents"] == 4 and r["ecartes"] == 4
    assert len(r["alertes"]) == 1 and len(tg.envoyes) == 1
    r2 = orch.cycle(now + timedelta(minutes=20))
    assert r2["alertes"] == [] and len(tg.envoyes) == 1  # jamais deux fois


def test_pause_suspend_la_collecte(base, conn):
    now = paris(10)
    orch, tg = _orch(base, conn, now)
    orch.question("/pause")
    assert orch.cycle(now)["collecte"] is None


def test_horloge_briefing_une_fois(base, conn):
    orch, tg = _orch(base, conn, paris(7, 50))
    orch.cycle(paris(7, 50))
    n = len(tg.envoyes)
    assert orch.horloge(paris(7, 59)) == []
    assert orch.horloge(paris(8, 0)) == ["briefing"]
    assert orch.horloge(paris(8, 1)) == []
    assert "VEILLE POLITIQUE" in tg.envoyes[n]
    assert orch.horloge(paris(8, 0, jour=24)) == ["briefing"]  # lendemain


def test_horloge_rattrapage_limite(base, conn):
    orch, tg = _orch(base, conn, paris(7))
    assert "briefing" in orch.horloge(paris(10, 30))      # PC rallume a 10:30 : rattrape
    orch2, _ = Orchestrateur(base, tg=FauxTelegram(), ia=ClientIA("")), None
    assert "synthese" not in orch2.horloge(paris(23, 30))  # trop tard pour 20:00


def test_horloge_synthese_et_points(base, conn):
    # 2 sources : evenement sous le seuil d'alerte, donc "nouveau" pour le point de 09:00
    # (un evenement deja alerte n'est pas repete dans le point qui suit)
    orch, tg = _orch(base, conn, paris(9), n=2)
    orch.cycle(paris(9))
    assert orch.horloge(paris(8, 0)) == ["briefing"]
    assert orch.horloge(paris(9, 0)) == ["point"]          # 1er point de la journee
    assert orch.horloge(paris(10, 0)) == []                 # < 2 h
    orch.cycle(paris(10, 30))
    envoyes = orch.horloge(paris(11, 5))
    assert envoyes in ([], ["point"])                       # point seulement s'il y a du nouveau
    assert orch.horloge(paris(20, 0)) == ["synthese"]
    assert orch.horloge(paris(23, 0)) == []                 # hors plage 08:00-22:00


def test_ecoute_telegram(base, conn):
    reponses = []

    def handler(req):
        if req.url.path.endswith("/getUpdates"):
            return httpx.Response(200, json={"ok": True, "result": [
                {"update_id": 10, "message": {"chat": {"id": 42}, "text": "/etat"}},
                {"update_id": 11, "message": {"chat": {"id": 7}, "text": "/pause"}},
            ]})
        reponses.append(req.content)
        return httpx.Response(200, json={"ok": True, "result": {}})

    from app.telegram import Telegram
    tg = Telegram("t", "42", httpx.Client(transport=httpx.MockTransport(handler)))
    orch = Orchestrateur(base, http=client_mock({}), tg=tg, ia=ClientIA(""))
    assert orch.ecouter() == 1
    assert len(reponses) == 1 and "VEILLE" in reponses[0].decode()
    c = connect(base)
    assert c.execute("SELECT valeur FROM parametres WHERE cle='collecte_active'").fetchone()[0] == "true"
    assert c.execute("SELECT valeur FROM etat WHERE cle='telegram_offset'").fetchone()[0] == "12"
    c.close()


def test_api(base, monkeypatch):
    from app import reglages
    from app.main import app
    vrai = reglages.adresse_publique
    monkeypatch.setattr(reglages, "adresse_publique", lambda url, resoudre=None: vrai(url, lambda h: {"93.184.216.34"}))
    with TestClient(app) as client:
        assert client.get("/api/v1/health").json()["planificateur"] is False
        r = client.post("/api/v1/sources", json={"nom": "Nouvelle", "url": "https://n.test/rss", "type": "rss",
                                                 "categorie": "media", "niveau": 2, "zone": "national",
                                                 "frequence_minutes": 15})
        assert r.status_code == 201
        sid = r.json()["id"]
        assert client.post("/api/v1/sources", json={"nom": "Nouvelle", "url": "https://n.test/rss", "type": "rss",
                                                    "categorie": "media", "niveau": 2, "zone": "national",
                                                    "frequence_minutes": 15}).status_code == 409
        monkeypatch.setattr(reglages, "adresse_publique", lambda url, resoudre=None: vrai(url, lambda h: {"127.0.0.1"}))
        assert client.post("/api/v1/sources", json={"nom": "Piege", "url": "https://interne.test/rss", "type": "rss",
                                                    "categorie": "media", "niveau": 2, "zone": "national",
                                                    "frequence_minutes": 15}).status_code == 422
        assert client.patch(f"/api/v1/sources/{sid}", json={"actif": 0}).status_code == 200
        assert client.put("/api/v1/parametres/seuil_critique", json={"valeur": 80}).json()["valeur"] == 80
        assert client.put("/api/v1/parametres/seuil_critique", json={"valeur": "abc"}).status_code == 422
        assert client.put("/api/v1/parametres/poids_score", json={"valeur": {"institutionnel": 50}}).status_code == 422
        assert "Retraites" in client.get("/api/v1/themes").json()
        assert client.put("/api/v1/themes/Sport", json={"mots_cles": ["sport"]}).status_code == 200
        for url in ("/api/v1/evenements", "/api/v1/articles?q=x", "/api/v1/notifications", "/api/v1/journal",
                    "/api/v1/couts", "/api/v1/parametres"):
            assert client.get(url).status_code == 200, url
        assert client.post("/api/v1/pause").json() == {"collecte_active": False}
        assert client.post("/api/v1/question", json={"texte": "Quoi de neuf à Lyon ?"}).status_code == 200
