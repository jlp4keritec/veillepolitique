"""F01 collecte, F02 filtrage/classification, F03 regroupement."""

from datetime import timedelta

from app.classification import classer, classer_nouveaux
from app.collecte import collecter, sources_dues
from app.parametres import themes_actifs, tous
from app.regroupement import meme_evenement, regrouper_nouveaux
from app.util import normaliser
from tests.conftest import T0, ajouter_source, client_mock, rss

URL = "https://media.test/rss"


def test_collecte_stocke_articles_et_horodate(conn):
    ajouter_source(conn)
    flux = rss([
        ("Le Sénat adopte la réforme des retraites", "https://media.test/a1?utm_source=x", T0, "<p>Vote <b>serré</b></p>"),
        ("Météo : grand soleil", "https://media.test/a2", T0, "beau temps"),
    ])
    res = collecter(conn, client_mock({URL: flux}), T0)
    assert res.articles_nouveaux == 2 and res.sources_en_erreur == 0
    a = conn.execute("SELECT * FROM articles WHERE url LIKE '%a1%'").fetchone()
    assert a["url"] == "https://media.test/a1"  # parametre de suivi retire
    assert a["texte_extrait"] == "Vote serré"   # HTML nettoye
    assert a["publie_le"] == "2026-11-22T09:00:00Z"
    s = conn.execute("SELECT * FROM sources").fetchone()
    assert s["url_verifiee"] == 1 and s["etag"] == '"v1"'


def test_collecte_sans_doublon(conn):
    ajouter_source(conn)
    flux = rss([("Titre A", "https://media.test/a1", T0, "x")])
    collecter(conn, client_mock({URL: flux}), T0)
    res = collecter(conn, client_mock({URL: flux}), T0 + timedelta(minutes=20))
    assert res.articles_nouveaux == 0
    assert conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 1


def test_collecte_respecte_frequence(conn):
    ajouter_source(conn, frequence=15)
    collecter(conn, client_mock({URL: rss([])}), T0)
    assert sources_dues(conn, T0 + timedelta(minutes=10)) == []
    assert len(sources_dues(conn, T0 + timedelta(minutes=16))) == 1


def test_source_en_erreur_ne_bloque_pas_les_autres(conn):
    ajouter_source(conn, nom="Panne", url="https://panne.test/rss")
    ajouter_source(conn, nom="OK", url=URL)
    res = collecter(conn, client_mock({"https://panne.test/rss": 500,
                                       URL: rss([("Titre", "https://media.test/x", T0, "")])}), T0)
    assert res.sources_en_erreur == 1 and res.articles_nouveaux == 1
    panne = conn.execute("SELECT * FROM sources WHERE nom = 'Panne'").fetchone()
    assert panne["erreurs_consecutives"] == 1 and "500" in panne["derniere_erreur"]
    # Nouvelle tentative retardee (delai double) : pas due a +20 min, due a +31 min
    assert all(s["nom"] != "Panne" for s in sources_dues(conn, T0 + timedelta(minutes=20)))
    assert any(s["nom"] == "Panne" for s in sources_dues(conn, T0 + timedelta(minutes=31)))
    assert conn.execute("SELECT COUNT(*) FROM journal WHERE niveau = 'ERREUR'").fetchone()[0] == 1


def test_flux_illisible_signale(conn):
    ajouter_source(conn)
    res = collecter(conn, client_mock({URL: b"<html>pas un flux"}), T0)
    assert res.sources_en_erreur == 1


def test_classification_regles(conn):
    p, th = tous(conn), themes_actifs(conn)
    c = classer(normaliser("Retraites : le Sénat adopte la réforme"), "", "national", p, th)
    assert c.pertinent and c.theme == "Retraites" and "senat" in c.acteurs and c.type_evenement == "vote"
    c = classer(normaliser("La Métropole de Lyon vote son budget"), "", "national", p, th)
    assert c.zone == "regional" and c.pertinent
    c = classer(normaliser("Recette de la tarte aux pommes"), "", "national", p, th)
    assert not c.pertinent


def test_rassemblement_national_n_est_pas_une_manifestation(conn):
    p, th = tous(conn), themes_actifs(conn)
    c = classer(normaliser("Le Rassemblement national présente son candidat"), "", "national", p, th)
    assert c.type_evenement != "manifestation" and "rassemblement national" in c.acteurs


def test_mots_exclus(conn):
    from app.parametres import modifier
    modifier(conn, "mots_exclus", ["football"])
    c = classer(normaliser("Le ministre des Sports et le football"), "", "national", tous(conn), themes_actifs(conn))
    assert not c.pertinent and "football" in c.raison


def test_regroupement_meme_evenement(conn):
    ajouter_source(conn, nom="A", url="https://a.test/rss")
    ajouter_source(conn, nom="B", url="https://b.test/rss")
    collecter(conn, client_mock({
        "https://a.test/rss": rss([("Le Sénat adopte la réforme des retraites", "https://a.test/1", T0, "")]),
        "https://b.test/rss": rss([
            ("Réforme des retraites : le Sénat adopte le texte", "https://b.test/1", T0 + timedelta(minutes=5), ""),
            ("Immigration : le gouvernement présente un projet de loi", "https://b.test/2", T0, ""),
        ]),
    }), T0 + timedelta(minutes=10))
    classer_nouveaux(conn)
    regrouper_nouveaux(conn)
    evts = conn.execute("SELECT * FROM evenements ORDER BY nb_articles DESC").fetchall()
    assert len(evts) == 2
    assert evts[0]["nb_articles"] == 2 and evts[0]["nb_sources"] == 2


def test_similarite_titres():
    s, m = 83, 2
    assert meme_evenement(normaliser("Dissolution : Emmanuel Macron s'adresse aux Français"),
                          normaliser("Macron s'adresse aux Français après la dissolution"), s, m)
    assert not meme_evenement(normaliser("Le Sénat adopte la réforme des retraites"),
                              normaliser("Le Sénat rejette le budget de la sécurité sociale"), s, m)
