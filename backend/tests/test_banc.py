"""Banc d'essai : mesure IA / regles et entre deux modeles, sans modifier les articles."""

import json

import pytest

from app import banc
from app.ia import ClientIA
from tests.test_ia_fournisseurs import LOCAL, claude, panne, transport
from tests.test_ia_recherche import _articles


def _repondre_par_lot(theme):
    """Ollama simule : renvoie un classement pour chaque article du lot recu."""
    import re

    import httpx

    def handler(req):
        corps = json.loads(req.content)
        ids = [int(x) for x in re.findall(r'<donnees id="(\d+)"', corps["messages"][1]["content"])]
        return httpx.Response(200, json={"message": {"content": json.dumps([{"id": i, "theme": theme} for i in ids])},
                                         "prompt_eval_count": 10, "eval_count": 10})
    return handler


def test_banc_un_modele(base, conn):
    _articles(conn, ["Le gouvernement annonce une réforme des retraites", "Le Sénat vote le budget de la défense"])
    conn.commit()
    avant = conn.execute("SELECT id, theme, themes FROM articles ORDER BY id").fetchall()
    ia = ClientIA("", transport({"10.10.0.2": _repondre_par_lot("Retraites")}, []), local_url=LOCAL)
    bid = banc.lancer(base, ia, ["local:ministral-3:3b"], 10, en_fond=False)
    r = banc.derniers(conn)[0]
    assert r["id"] == bid and r["statut"] == "termine"
    m = r["resultats"]["modeles"]["local:ministral-3:3b"]
    assert m["articles"] == 2 and m["pct_valides"] == 100 and m["n_theme"] == 2 and m["accord_theme"] == 50
    assert [tuple(x) for x in conn.execute("SELECT id, theme, themes FROM articles ORDER BY id")] == \
        [tuple(x) for x in avant]                                                       # rien n'est modifie
    assert conn.execute("SELECT COUNT(*) FROM avis_ia WHERE origine = 'banc'").fetchone()[0] == 2


def test_banc_deux_modeles_et_panne(base, conn):
    _articles(conn, ["Le gouvernement annonce une réforme des retraites"])
    conn.commit()
    ids = [r[0] for r in conn.execute("SELECT id FROM articles WHERE pertinent = 1")]
    ia = ClientIA("cle-test", transport({"10.10.0.2": panne,
                                         "api.anthropic.com": claude(json.dumps([{"id": ids[0], "theme": "Retraites"}]))},
                                        []), local_url=LOCAL)
    banc.lancer(base, ia, ["local:ministral-3:3b", "anthropic:"], 10, en_fond=False)
    r = banc.derniers(conn)[0]["resultats"]
    assert r["modeles"]["local:ministral-3:3b"]["valides"] == 0                       # en panne : mesure a 0
    assert r["modeles"]["anthropic:"]["accord_theme"] == 100
    assert r["entre_modeles"]["n"] == 0


def test_banc_controles(base, conn):
    ia = ClientIA("", local_url=LOCAL)
    for mauvais in ([], ["a", "b", "c"], ["pirate:x"], ["local:"]):
        with pytest.raises(ValueError):
            banc.lancer(base, ia, mauvais, 10, en_fond=False)
    conn.execute("INSERT INTO banc_essai (lance_le, statut, n, modeles) VALUES (?, 'en cours', 5, '[]')",
                 ("2099-01-01T00:00:00Z",))
    conn.commit()
    with pytest.raises(ValueError, match="déjà en cours"):
        banc.lancer(base, ia, ["local:ministral-3:3b"], 10, en_fond=False)


def test_page_banc(base, conn):
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as c:
        r = c.get("/reglages?onglet=modele")
        import re
        j = re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)
        assert "Banc d'essai" in r.text
        r = c.post("/reglages/ia/banc", data={"csrf": j, "modele_a": "pirate:x", "n": "10"})
        assert "commence par local" in r.text
