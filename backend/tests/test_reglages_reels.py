"""Reglages v0.2.2, verifies sur de VRAIS titres collectes le 21/11/2026."""

import json
from datetime import timedelta

from app.analyse import analyser
from app.classification import classer, classer_nouveaux
from app.collecte import collecter
from app.parametres import seed_parametres, themes_actifs, tous
from app.regroupement import regrouper_nouveaux
from app.util import normaliser, utcnow
from tests.conftest import ajouter_source, client_mock, rss

MOUTOUH = [
    "Fuites au ministère de l’Intérieur : Hugues Moutouh, le «préfet bulldozer» soupçonné d’avoir tuyauté le RN",
    "Suspecté d’être une taupe du RN, le préfet Hugues Moutouh demande à être relevé de ses fonctions",
    "Fuites de Beauvau vers le RN : d’un email trouvé au domicile d’un ami de Marine Le Pen aux suspicions "
    "visant le préfet Hugues Moutouh, itinéraire d’une enquête sensible",
]


def _charger(conn, articles_par_source):
    now = utcnow()
    routes = {}
    for i, articles in enumerate(articles_par_source):
        url = f"https://r{i}.test/rss"
        ajouter_source(conn, nom=f"R{i}", url=url)
        routes[url] = rss([(t, f"https://r{i}.test/{k}", now - timedelta(minutes=30 + k), r)
                           for k, (t, r) in enumerate(articles)])
    collecter(conn, client_mock(routes), now)
    classer_nouveaux(conn)
    analyser(conn, regrouper_nouveaux(conn), now)
    return now


def test_1_affaire_moutouh_regroupee(conn):
    bruit = [(f"Le RN et la réforme numéro {i} au Sénat", "") for i in range(5)]
    _charger(conn, [[(MOUTOUH[0], "")] + bruit[:2], [(MOUTOUH[1], "")], [(MOUTOUH[2], "")] + bruit[2:]])
    evts = conn.execute("SELECT * FROM evenements WHERE titre_norm LIKE '%moutouh%'").fetchall()
    assert len(evts) == 1 and evts[0]["nb_articles"] == 3 and evts[0]["nb_sources"] == 3


def test_1_nom_frequent_ne_fusionne_pas(conn):
    # "Macron" cite dans 12 titres de sujets differents : pas rare, donc pas de fusion abusive
    titres = [
        "Emmanuel Macron reçoit les syndicats agricoles à l'Élysée",
        "Dette publique : Emmanuel Macron appelle à un effort national",
        "Ukraine : Macron annonce une nouvelle aide militaire de la France",
        "Macron en visite à Marseille pour parler de sécurité",
        "Retraites : Macron défend sa réforme devant les députés de la majorité",
        "Le président Macron recevra le chancelier allemand jeudi",
        "Nucléaire : Emmanuel Macron confirme la construction de six réacteurs",
        "École : Macron veut généraliser l'uniforme dès la rentrée",
        "Macron et la Chine : un déplacement à Pékin en préparation",
        "Logement : les annonces d'Emmanuel Macron jugées insuffisantes",
        "Impôts : Macron exclut toute hausse avant 2027",
        "Santé : Emmanuel Macron promet des médecins dans chaque département",
    ]
    _charger(conn, [[(x, "") for x in titres]])
    pertinents = conn.execute("SELECT COUNT(*) FROM articles WHERE pertinent = 1").fetchone()[0]
    assert pertinents >= 10
    assert conn.execute("SELECT COUNT(*) FROM evenements").fetchone()[0] == pertinents  # aucune fusion


def test_2_type_depuis_le_titre(conn):
    p, th = tous(conn), themes_actifs(conn)
    titre = ("\"Le 2 mai est le pire scénario possible\": la secrétaire générale de la CFDT Marylise Léon "
             "demande à \"avancer d'une semaine\" la présidentielle")
    c = classer(normaliser(titre), normaliser("Le gouvernement a fixé la date du vote."), "national", p, th)
    assert c.type_evenement is None
    assert c.acteurs == ["gouvernement"] and c.acteurs_titre == []


def test_3_acteur_du_resume_vaut_moitie(conn):
    titre = "La secrétaire générale de la CFDT demande d'avancer la présidentielle"
    _charger(conn, [[(titre, "Le gouvernement a fixé le calendrier.")]])
    d = json.loads(conn.execute("SELECT score_details FROM evenements").fetchone()[0])
    assert d["institutionnel"]["points"] == 10 and "resume" in d["institutionnel"]["raison"]


def test_4_conditionnel_du_resume_ne_suffit_plus(conn):
    _charger(conn, [[("Les Républicains : Bruno Retailleau prépare sa campagne présidentielle",
                      "Il pourrait annoncer sa candidature, qui serait prévue en janvier.")]])
    assert conn.execute("SELECT verification FROM evenements").fetchone()[0] == "une seule source disponible"


def test_4_conditionnel_du_titre(conn):
    _charger(conn, [[("Le ministre de l'Intérieur serait sur le départ", "")]])
    assert conn.execute("SELECT verification FROM evenements").fetchone()[0] == "à confirmer"


def test_5_page_sujet_ecartee(conn):
    c = classer(normaliser("Bruno Retailleau"), normaliser("gouvernement senat ministre"), "national",
                tous(conn), themes_actifs(conn))
    assert not c.pertinent and "trop court" in c.raison


def test_6_actualite_etrangere(conn):
    _charger(conn, [[("Jair Bolsonaro, ancien président du Brésil, à nouveau hospitalisé en soins intensifs "
                      "pour une occlusion intestinale", "")]])
    e = conn.execute("SELECT * FROM evenements").fetchone()
    assert e["theme"] == "International"
    assert json.loads(e["score_details"])["pertinence"]["points"] == 1


def test_6_mise_a_jour_theme_respecte_les_modifs_de_j(conn):
    anciens = ["international", "diplomatie", "ukraine", "russie", "etats-unis", "chine", "israel", "gaza", "otan", "onu"]
    conn.execute("UPDATE themes SET mots_cles = ? WHERE nom = 'International'", (json.dumps(anciens),))
    seed_parametres(conn)
    assert "bresil" in themes_actifs(conn)["International"]  # valeur par defaut d'origine : mise a jour
    conn.execute("UPDATE themes SET mots_cles = '[\"ukraine\"]' WHERE nom = 'International'")
    seed_parametres(conn)
    assert themes_actifs(conn)["International"] == ["ukraine"]  # modifie par J : jamais ecrase


def test_reclasser_ne_touche_pas_les_alertes(base, conn):
    from scripts.reclasser import reclasser
    _charger(conn, [[(MOUTOUH[0], "")], [(MOUTOUH[1], "")]])
    evt = conn.execute("SELECT id FROM evenements").fetchone()[0]
    conn.execute("INSERT INTO notifications (type, cle_unique, evenement_id, contenu, statut, envoye_le) "
                 "VALUES ('alerte', 'alerte:x:1', ?, 'x', 'envoye', '2026-11-22T00:00:00Z')", (evt,))
    conn.commit()
    r = reclasser(base, 3)
    assert r["articles"] == 0
    assert conn.execute("SELECT COUNT(*) FROM articles WHERE evenement_id = ?", (evt,)).fetchone()[0] == 2
