"""Tendances mesurees, score explicable, statuts de verification."""

from datetime import timedelta

from app.analyse import analyser, niveau, tendance
from app.classification import classer_nouveaux
from app.collecte import collecter
from app.parametres import tous
from app.regroupement import regrouper_nouveaux
from tests.conftest import T0, ajouter_source, client_mock, rss


def test_tendances(conn):
    p = tous(conn)
    now = T0
    assert tendance([now - timedelta(minutes=5)], now, p)[0] == "nouveau"
    vieux = [now - timedelta(hours=5)]
    hausse = vieux + [now - timedelta(minutes=m) for m in (5, 10, 15, 20)]
    assert tendance(hausse, now, p)[0] == "forte hausse"
    stable = vieux + [now - timedelta(minutes=70), now - timedelta(minutes=10)]
    assert tendance(stable, now, p)[0] == "stable"
    baisse = vieux + [now - timedelta(minutes=m) for m in (70, 80, 90, 100)]
    assert tendance(baisse, now, p)[0] == "en baisse"


def _scenario(conn, n_sources, titre, categorie="media"):
    routes = {}
    for i in range(n_sources):
        url = f"https://s{i}.test/rss"
        ajouter_source(conn, nom=f"S{i}", url=url, categorie=categorie if i == 0 else "media",
                       niveau=1 if (categorie == "institutionnel" and i == 0) else 2)
        routes[url] = rss([(titre if i == 0 else f"{titre} ({i})", f"https://s{i}.test/a", T0 - timedelta(minutes=10 + i), "")])
    collecter(conn, client_mock(routes), T0)
    classer_nouveaux(conn)
    ids = regrouper_nouveaux(conn)
    analyser(conn, ids, T0)
    return conn.execute("SELECT * FROM evenements ORDER BY score DESC").fetchone()


def test_score_critique_explicable(conn):
    e = _scenario(conn, 4, "Motion de censure : le gouvernement renversé, dissolution de l'Assemblée nationale")
    import json
    d = json.loads(e["score_details"])
    assert set(d) == {"institutionnel", "nouveaute", "acceleration", "sources", "impact", "pertinence"}
    assert all("raison" in v and "points" in v for v in d.values())
    assert e["score"] == sum(v["points"] for v in d.values())
    assert e["nb_sources"] == 4 and e["score"] >= 85, d
    assert e["verification"] == "corroboré par plusieurs sources"


def test_source_unique_score_modere(conn):
    e = _scenario(conn, 1, "Le maire de Lyon inaugure une piste cyclable")
    assert e["score"] < 70
    assert e["verification"] == "une seule source disponible"


def test_source_primaire(conn):
    e = _scenario(conn, 1, "Le gouvernement publie le décret sur les retraites", categorie="institutionnel")
    assert e["verification"] == "confirmé par source primaire"


def test_rumeur_jamais_presentee_comme_fait(conn):
    e = _scenario(conn, 2, "Le ministre de l'Intérieur serait sur le départ selon des sources")
    assert e["verification"] == "à confirmer"


def test_niveaux(conn):
    p = tous(conn)
    assert niveau(90, p) == "critique" and niveau(72, p) == "très important" and niveau(10, p) == "faible"
