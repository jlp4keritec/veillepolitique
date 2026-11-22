"""Pages de lecture et protection par mot de passe."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.config import get_settings
from app.ia import ClientIA
from app.orchestrateur import Orchestrateur
from app.pages import contenu_sur
from tests.conftest import ajouter_source, client_mock, rss
from tests.test_alertes_syntheses import TITRE, FauxTelegram

PIEGE = 'Le Sénat et la réforme <script>alert(1)</script><img src=x onerror="alert(2)">'


@pytest.fixture
def donnees(base, conn):
    from app.util import utcnow
    now = utcnow()
    routes = {}
    for i in range(4):
        url = f"https://s{i}.test/rss"
        ajouter_source(conn, nom=f"S{i}", url=url)
        routes[url] = rss([(f"{TITRE} {'!' * i}", f"https://s{i}.test/a", now - timedelta(minutes=5 + i), "x"),
                           (PIEGE.replace("<", "&lt;").replace(">", "&gt;") if i == 0 else "Recette du gratin",
                            f"https://s{i}.test/p", now - timedelta(minutes=3), "")])
    orch = Orchestrateur(base, http=client_mock(routes), tg=FauxTelegram(), ia=ClientIA(""))
    orch.cycle(now)
    orch.envoyer_synthese("briefing", now)
    return base


@pytest.fixture
def client(donnees, monkeypatch):
    from app.main import app
    auth._echecs.clear()
    with TestClient(app) as c:
        yield c


def test_pages_sans_mot_de_passe(client, conn):
    r = client.get("/")
    assert r.status_code == 200 and "Top 24 h" in r.text and "Motion de censure" in r.text
    assert "VEILLE POLITIQUE" in r.text  # dernier briefing affiche
    assert client.get("/connexion", follow_redirects=False).status_code == 303  # inutile sans mot de passe
    r = client.get("/archives")
    assert r.status_code == 200 and "Briefing 08:00" in r.text and "Alerte" in r.text
    assert client.get("/archives?type=alerte").status_code == 200
    alerte = conn.execute("SELECT id, evenement_id FROM notifications WHERE type = 'alerte'").fetchone()
    r = client.get(f"/lecture/{alerte['id']}")
    assert r.status_code == 200 and "ALERTE POLITIQUE" in r.text and 'href="https://s0.test/a"' in r.text
    r = client.get(f"/evenement/{alerte['evenement_id']}")
    assert r.status_code == 200 and "Pourquoi ce score" in r.text and "Importance institutionnelle" in r.text
    assert "https://s3.test/a" in r.text
    r = client.get("/recherche?q=censure")
    assert r.status_code == 200 and "https://s0.test/a" in r.text
    assert "Données insuffisantes" in client.get("/recherche?q=introuvablexyz").text
    assert client.get("/lecture/99999").status_code == 404
    assert client.get("/evenement/99999").status_code == 404


def test_titre_piege_echappe_partout(client, conn):
    # 1re protection : la collecte retire deja les balises
    assert conn.execute("SELECT COUNT(*) FROM articles WHERE titre LIKE '%<script>%'").fetchone()[0] == 0
    # 2e protection : meme un titre dangereux en base est echappe par les pages
    conn.execute("INSERT INTO articles (source_id, url, titre, titre_norm, publie_le, collecte_le, pertinent) "
                 "VALUES (1, 'https://s0.test/piege', ?, 'senat piege', '2026-11-22T00:00:00Z', "
                 "'2026-11-22T00:00:00Z', 1)", (PIEGE,))
    conn.commit()
    for url in ("/", "/recherche?q=senat", "/archives"):
        r = client.get(url)
        assert "<script>alert(1)" not in r.text and 'onerror="alert(2)"' not in r.text, url
    assert "&lt;script&gt;" in client.get("/recherche?q=senat").text


def test_nettoyage_contenu():
    s = str(contenu_sur('<b>Titre</b> <a href="javascript:alert(1)">x</a> <a href="https://ok.test/a?b=1&amp;c=2">src</a>'
                        '\n<script>mal()</script><i>fin'))
    assert "<b>Titre</b>" in s and "javascript" not in s and "<script>" not in s
    assert 'href="https://ok.test/a?b=1&amp;c=2"' in s and 'rel="noopener noreferrer"' in s
    assert s.count("<i>") == s.count("</i>") and "<br>" in s


@pytest.fixture
def client_protege(donnees, monkeypatch):
    monkeypatch.setenv("MOT_DE_PASSE_PAGES", "un-mot-de-passe-long-2026")
    get_settings.cache_clear()
    auth._echecs.clear()
    from app.main import app
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_tout_est_protege(client_protege):
    c = client_protege
    r = c.get("/archives?type=alerte", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/connexion?suite=/archives")
    assert c.get("/api/v1/sources").status_code == 401
    assert c.get("/docs").status_code == 401
    assert c.get("/api/v1/health").status_code == 200  # surveillance
    assert c.get("/connexion").status_code == 200


def test_connexion_et_session_30_jours(client_protege):
    c = client_protege
    r = c.post("/connexion", data={"mot_de_passe": "faux", "suite": "/archives"}, follow_redirects=False)
    assert "erreur=faux" in r.headers["location"]
    r = c.post("/connexion", data={"mot_de_passe": "un-mot-de-passe-long-2026", "suite": "/archives"},
               follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/archives"
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Max-Age=2592000" in cookie and "SameSite=lax" in cookie
    assert c.get("/").status_code == 200
    assert c.get("/api/v1/sources").status_code == 200
    c.get("/deconnexion")
    assert c.get("/", follow_redirects=False).status_code == 303


def test_blocage_apres_5_essais(client_protege):
    c = client_protege
    for _ in range(5):
        c.post("/connexion", data={"mot_de_passe": "faux"}, follow_redirects=False)
    r = c.post("/connexion", data={"mot_de_passe": "un-mot-de-passe-long-2026"}, follow_redirects=False)
    assert "erreur=bloque" in r.headers["location"]
    assert c.get("/", follow_redirects=False).status_code == 303


def test_jeton_falsifie_ou_expire(client_protege):
    import time
    j = auth.creer_jeton()
    assert auth.jeton_valide(j)
    assert not auth.jeton_valide(j[:-1] + ("0" if j[-1] != "0" else "1"))
    assert not auth.jeton_valide(j, maintenant=time.time() + auth.DUREE_SESSION + 10)
    client_protege.cookies.set(auth.COOKIE, "9999999999.faux")
    assert client_protege.get("/", follow_redirects=False).status_code == 303


def test_changer_mot_de_passe_deconnecte(client_protege, monkeypatch):
    j = auth.creer_jeton()
    monkeypatch.setenv("MOT_DE_PASSE_PAGES", "un-autre-mot-de-passe")
    get_settings.cache_clear()
    assert not auth.jeton_valide(j)


def test_pas_de_redirection_vers_un_autre_site(client_protege):
    r = client_protege.post("/connexion", data={"mot_de_passe": "un-mot-de-passe-long-2026",
                                                "suite": "//site-pirate.test/"}, follow_redirects=False)
    assert r.headers["location"] == "/"
