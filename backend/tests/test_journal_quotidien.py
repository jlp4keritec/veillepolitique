"""Journal quotidien (F10) : photo du top, jamais modifiee, page /journal."""

import json
from datetime import timedelta

from app import quotidien
from app.ia import ClientIA
from app.orchestrateur import Orchestrateur
from app.parametres import modifier
from tests.conftest import client_mock
from tests.test_alertes_syntheses import FauxTelegram
from tests.test_orchestrateur import _orch, paris
from tests.test_pages import PIEGE, client, donnees  # noqa: F401  (fixtures)


def test_photo_a_l_heure_une_seule_fois(base, conn):
    orch, _ = _orch(base, conn, paris(9))
    orch.cycle(paris(9))
    jour = paris(9).astimezone(quotidien.PARIS).date()
    orch.horloge(paris(23, 54))
    assert quotidien.lire(conn, jour) is None                 # pas avant 23:55
    orch.horloge(paris(23, 55))
    photo = quotidien.lire(conn, jour)
    assert photo and not photo["rattrape"] and photo["top"]
    t = photo["top"][0]
    assert t["rang"] == 1 and t["score"] > 0 and t["raisons"] and t["sources"]
    assert all(s["url"].startswith("https://") for s in t["sources"])
    assert photo["chiffres"]["articles"] == 8 and photo["chiffres"]["pertinents"] == 4
    # le score evolue ensuite : la photo reste celle du soir
    conn.execute("UPDATE evenements SET score = 1, titre = 'change'")
    conn.commit()
    orch.horloge(paris(23, 58))
    assert quotidien.lire(conn, jour)["top"][0]["score"] == t["score"]
    assert conn.execute("SELECT COUNT(*) FROM journal_quotidien").fetchone()[0] == 1


def test_rattrapage_de_la_veille(base, conn):
    orch, _ = _orch(base, conn, paris(9))
    orch.cycle(paris(9))
    hier = paris(9).astimezone(quotidien.PARIS).date()
    orch.horloge(paris(7, 0, jour=24))                      # serveur arrete a 23:55 la veille
    photo = quotidien.lire(conn, hier)
    assert photo and photo["rattrape"]
    assert quotidien.lire(conn, hier + timedelta(days=1)) is None


def test_veille_sans_donnees_pas_de_photo(base, conn):
    orch = Orchestrateur(base, http=client_mock({}), tg=FauxTelegram(), ia=ClientIA(""))
    orch.horloge(paris(7, 0, jour=24))
    assert conn.execute("SELECT COUNT(*) FROM journal_quotidien").fetchone()[0] == 0


def test_reglages_de_j(base, conn):
    modifier(conn, "journal_taille_top", 1)
    modifier(conn, "heure_journal", "21:00")
    conn.commit()
    orch, _ = _orch(base, conn, paris(9))
    orch.cycle(paris(9))
    orch.horloge(paris(21, 0))
    photo = quotidien.lire(conn, paris(9).astimezone(quotidien.PARIS).date())
    assert photo and len(photo["top"]) == 1


def test_lien_non_http_ecarte(base, conn):
    orch, _ = _orch(base, conn, paris(9))
    orch.cycle(paris(9))
    conn.execute("UPDATE articles SET url = 'javascript:alert(1)' WHERE id = (SELECT MIN(id) FROM articles "
                 "WHERE evenement_id IS NOT NULL)")
    conn.commit()
    data = quotidien.calculer(conn, paris(9).astimezone(quotidien.PARIS).date())
    assert all(s["url"].startswith("http") for e in data["top"] for s in e["sources"])


def test_page_journal(client, conn):  # noqa: F811
    from app.util import utcnow
    aujourdhui = quotidien.jour_paris(utcnow())
    r = client.get("/journal")
    assert r.status_code == 200 and "journée en cours" in r.text and "Motion de censure" in r.text
    assert "Messages du jour" in r.text and "Briefing 08:00" in r.text and 'href="/journal"' in r.text
    # photo : on affiche la photo, pas les scores actuels
    quotidien.photographier(conn, aujourdhui, utcnow())
    conn.execute("UPDATE evenements SET titre = 'titre modifie apres la photo'")
    conn.commit()
    r = client.get("/journal")
    assert "photo du" in r.text and "Motion de censure" in r.text and "titre modifie" not in r.text
    # jour passe sans photo : reconstitue et annonce comme tel
    hier = (aujourdhui - timedelta(days=1)).isoformat()
    assert "reconstitué" in client.get(f"/journal?jour={hier}").text
    # dates invalides ou futures : retour a aujourd'hui
    for j in ("2026-13-45", "abc", (aujourdhui + timedelta(days=1)).isoformat()):
        assert client.get(f"/journal?jour={j}", follow_redirects=False).status_code == 303


def test_page_journal_echappe(client, conn):  # noqa: F811
    from app.util import utcnow
    evt = conn.execute("SELECT id FROM evenements LIMIT 1").fetchone()["id"]
    conn.execute("UPDATE evenements SET titre = ?, score_details = ? WHERE id = ?",
                 (PIEGE, json.dumps({"impact": {"points": 5, "raison": PIEGE}}), evt))
    conn.commit()
    quotidien.photographier(conn, quotidien.jour_paris(utcnow()), utcnow())
    conn.commit()
    r = client.get("/journal")
    assert "<script>alert(1)" not in r.text and 'onerror="alert(2)"' not in r.text
    assert "&lt;script&gt;" in r.text
