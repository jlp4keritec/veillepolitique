"""F01 : lecteur de page pour les sites officiels sans flux RSS (Elysee)."""

import sqlite3

from app.collecte import collecter, sources_dues
from app.lecteurs import lire_elysee, lire_page
from app.sources import lister_sources, seed_sources
from tests.conftest import T0, client_mock

URL = "https://www.elysee.fr/toutes-les-actualites"


def _carte(date_url: str, date_txt: str, nature: str, titre: str, slug: str) -> str:
    return (f'<li><h3><a href="https://www.elysee.fr/emmanuel-macron/{date_url}/{slug}">'
            f'<span>{date_txt}</span><span>{nature}</span><span>{titre}</span></a></h3>'
            f'<img alt="cover"></li>')


PAGE = ("<html><body><nav><a href='/'>Accueil</a><a href='/recherche'>Rechercher</a></nav><main><ul>"
        + _carte("2026/11/22", "22 novembre 2026", "Article", "Déplacement à Toulouse.", "deplacement-a-toulouse")
        + _carte("2026/11/19", "19 novembre 2026", "Communiqué de presse",
                 "Déclaration conjointe France &amp; Ukraine.", "declaration-conjointe")
        # meme publication affichee deux fois sur la page
        + _carte("2026/11/19", "19 novembre 2026", "Communiqué de presse",
                 "Déclaration conjointe France &amp; Ukraine.", "declaration-conjointe")
        + "</ul></main><footer><a href='/emmanuel-macron/objectif-plein-emploi'>Plein emploi</a>"
        "<a href='https://autre-site.test/emmanuel-macron/2026/11/19/piege'>Piege</a></footer>"
        "</body></html>").encode()


def test_lecteur_elysee_extrait_date_type_titre_lien():
    e = lire_elysee(PAGE.decode(), URL, T0)
    assert [x.titre for x in e] == ["Déplacement à Toulouse.", "Déclaration conjointe France & Ukraine."]
    assert e[1].nature == "Communiqué de presse" and e[0].nature == "Article"
    assert e[1].lien == "https://www.elysee.fr/emmanuel-macron/2026/11/19/declaration-conjointe"
    assert e[1].publie_le.isoformat() == "2026-11-19T12:00:00+00:00"
    assert e[0].publie_le == T0  # 22/11 12:00 est apres T0 (22/11 09:00) : jamais dans le futur


def test_page_changee_ou_site_inconnu_signale():
    for url, contenu in ((URL, b"<html><a href='/autre'>x</a></html>"), ("https://inconnu.test/", PAGE)):
        try:
            lire_page(url, contenu, None, T0)
        except ValueError:
            continue
        raise AssertionError("une erreur etait attendue")


def _source_elysee(conn):
    conn.execute(
        "INSERT INTO sources (nom,url,type,categorie,niveau,zone,fiabilite,priorite,frequence_minutes,actif)"
        " VALUES ('Elysee',?,'site','institutionnel',1,'national',5,1,60,1)", (URL,))
    conn.commit()


def test_collecte_d_un_site_sans_doublon(conn):
    _source_elysee(conn)
    res = collecter(conn, client_mock({URL: PAGE}), T0)
    assert res.articles_nouveaux == 2 and res.sources_en_erreur == 0
    a = conn.execute("SELECT * FROM articles WHERE url LIKE '%declaration-conjointe'").fetchone()
    assert a["texte_extrait"] == "Communiqué de presse" and a["publie_le"] == "2026-11-19T12:00:00Z"
    assert conn.execute("SELECT url_verifiee FROM sources").fetchone()[0] == 1
    # lecture suivante : rien de nouveau
    from datetime import timedelta
    assert collecter(conn, client_mock({URL: PAGE}), T0 + timedelta(minutes=61)).articles_nouveaux == 0


def test_site_change_de_forme_passe_en_erreur(conn):
    _source_elysee(conn)
    res = collecter(conn, client_mock({URL: b"<html><body>Nouveau site</body></html>"}), T0)
    assert res.sources_en_erreur == 1 and res.articles_nouveaux == 0
    s = conn.execute("SELECT * FROM sources").fetchone()
    assert "aucune publication reconnue" in s["derniere_erreur"]


def test_site_sans_lecteur_reste_ignore_s_il_est_desactive(conn):
    conn.execute(
        "INSERT INTO sources (nom,url,type,categorie,niveau,zone,frequence_minutes,actif)"
        " VALUES ('Region','https://www.auvergnerhonealpes.fr/','site','institutionnel',1,'regional',120,0)")
    assert sources_dues(conn, T0) == []


def test_base_existante_elysee_passe_sur_le_lecteur(tmp_path):
    db = tmp_path / "v.db"
    from app.db import init_schema
    init_schema(db)
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO sources (nom,url,type,categorie,niveau,zone,frequence_minutes,actif)"
                  " VALUES ('Elysee','https://www.elysee.fr/','site','institutionnel',1,'national',60,0)")
    seed_sources(db)
    par_url = {s["url"]: s for s in lister_sources(db)}
    assert "https://www.elysee.fr/" not in par_url
    assert par_url[URL]["actif"] == 1 and par_url[URL]["type"] == "site"
