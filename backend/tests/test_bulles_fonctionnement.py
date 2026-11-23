"""Bulles d'aide (scores, verification, tendance, classement) et page « Comment ca marche »."""

import json

from app.classification import classer
from app.parametres import DEFAUTS, modifier
from tests.test_pages import PIEGE, client, donnees  # noqa: F401  (fixtures)

P = {k: v for k, (v, _) in DEFAUTS.items()}


def test_classement_explique_les_mots():
    c = classer("le senat vote la reforme des retraites a lyon", "", "national", P,
                {"Retraites": ["retraites", "pension"], "Emploi": ["emploi"]}, "Le Sénat vote la réforme des retraites à Lyon")
    assert c.explication["themes"]["Retraites"]["titre"] == ["retraites"]
    assert "lyon" in c.explication["zone"] and c.zone == "regional"
    assert c.explication["type"].startswith("« vote »")
    c2 = classer("le maire parle aux habitants ce matin", "", "regional", P, {}, "Le maire parle aux habitants ce matin")
    assert c2.explication["zone"] == "source régionale"


def test_bulles_accueil_et_evenement(client, conn):  # noqa: F811
    r = client.get("/")
    assert r.status_code == 200 and 'class="bulle"' in r.text and 'role="tooltip"' in r.text
    assert "Importance institutionnelle" in r.text          # detail du score dans la bulle
    assert "Mots-clés dans le titre" in r.text               # pourquoi ce theme
    assert "Alerte à partir de 85" in r.text                 # seuil = reglage de J
    evt = conn.execute("SELECT id FROM evenements ORDER BY score DESC LIMIT 1").fetchone()["id"]
    r = client.get(f"/evenement/{evt}")
    assert r.status_code == 200 and "Calcul :" in r.text and "Au moins deux médias" in r.text
    r = client.get("/journal")
    assert "Rang 1" in r.text and "Classés par score" in r.text


def test_seuils_affiches_suivent_les_reglages(client, conn):  # noqa: F811
    modifier(conn, "seuil_critique", 90)
    conn.commit()
    assert "Alerte à partir de 90" in client.get("/").text
    assert "≥ 90" in client.get("/fonctionnement").text


def test_anciens_articles_sans_mots(client, conn):  # noqa: F811
    conn.execute("UPDATE articles SET classif_details = NULL")
    conn.commit()
    assert "Mots non conservés" in client.get("/").text


def test_page_fonctionnement(client, conn):  # noqa: F811
    r = client.get("/fonctionnement")
    assert r.status_code == 200
    for txt in ("Les agents proposent, tes règles décident", "Orchestrateur", "Collecte (F01)", "Regroupement (F03)",
                "Score (F04)", "Exécuteur", "jamais deux fois", "Statuts de vérification", "Ta revue de presse",
                "inactive", "S0", 'href="/fonctionnement"', "Double avis"):
        assert txt in r.text, txt


def test_bulles_echappent_le_contenu(client, conn):  # noqa: F811
    conn.execute("UPDATE evenements SET score_details = ?, verification_details = ?",
                 (json.dumps({"impact": {"points": 5, "raison": PIEGE}}), json.dumps({"raison": PIEGE})))
    conn.execute("UPDATE articles SET classif_details = ?",
                 (json.dumps({"themes": {"Institutions": {"titre": [PIEGE], "resume": []}}, "zone": PIEGE}),))
    conn.commit()
    for url in ("/", "/journal"):
        r = client.get(url)
        assert "<script>alert(1)" not in r.text and 'onerror="alert(2)"' not in r.text, url


def test_bulle_avis_divergents(client, conn):  # noqa: F811
    conn.execute("UPDATE articles SET classif_details = ? WHERE evenement_id IS NOT NULL",
                 (json.dumps({"themes": {}, "zone": "x", "ia": {"modele": "local:ministral-3:3b", "theme": "Défense",
                                                                 "theme_avis": "divergent"}}),))
    conn.commit()
    r = client.get("/")
    assert "avis divergents" in r.text and "tes règles ont tranché" in r.text and "Défense" in r.text
