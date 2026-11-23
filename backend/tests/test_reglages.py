"""Page Reglages (F11) : validation tout-ou-rien, apercu de ponderation, historique, annulation, anti-falsification."""

import re

from app import parametres
from tests.test_pages import client, donnees  # noqa: F401  (fixtures)


def _csrf(client):  # noqa: F811
    r = client.get("/reglages")
    assert r.status_code == 200
    return re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)


POIDS = {"institutionnel": 25, "nouveaute": 20, "acceleration": 20, "sources": 15, "impact": 15, "pertinence": 5}


def _form_poids(jeton, action, **chg):
    d = {f"poids_{k}": str(chg.get(k, v)) for k, v in POIDS.items()}
    d.update(csrf=jeton, action=action)
    return d


def test_page_et_sans_jeton_refuse(client, conn):  # noqa: F811
    r = client.get("/reglages")
    assert "Pondération du score" in r.text and "Seuils et alertes" in r.text and 'href="/reglages"' in r.text
    assert client.post("/reglages/section/seuils", data={"seuil_critique": "90"}).status_code == 403
    assert client.post("/reglages/section/seuils", data={"seuil_critique": "90", "csrf": "faux"}).status_code == 403
    assert parametres.lire(conn, "seuil_critique") == 85


def test_section_tout_ou_rien(client, conn):  # noqa: F811
    j = _csrf(client)
    base = {"csrf": j, "seuil_critique": "90", "seuil_important": "70", "alertes_actives": "on",
            "alerte_delta_score": "10", "alerte_delta_sources": "2", "alerte_max_mises_a_jour": "3"}
    r = client.post("/reglages/section/seuils", data={**base, "seuil_important": "95"})
    assert "Rien n'a été enregistré" in r.text and parametres.lire(conn, "seuil_critique") == 85
    r = client.post("/reglages/section/seuils", data={**base, "seuil_critique": "abc"})
    assert "nombre attendu" in r.text
    r = client.post("/reglages/section/seuils", data=base, follow_redirects=True)
    assert "Réglages enregistrés" in r.text
    conn.commit()
    assert parametres.lire(conn, "seuil_critique") == 90
    assert "Alerte à partir de 90" in client.get("/").text            # bulles a jour
    h = conn.execute("SELECT * FROM historique_reglages").fetchall()
    assert len(h) == 1 and h[0]["cle"] == "seuil_critique" and h[0]["origine"] == "page"


def test_horaire_invalide(client, conn):  # noqa: F811
    j = _csrf(client)
    d = {"csrf": j, "heure_briefing": "25:00", "heure_synthese_soir": "20:00", "plage_points": "08:00-22:00",
         "intervalle_point_heures": "2", "heure_journal": "23:55", "journal_taille_top": "10"}
    assert "HH:MM" in client.post("/reglages/section/horaires", data=d).text
    d["heure_briefing"] = "07:30"
    client.post("/reglages/section/horaires", data=d)
    conn.commit()
    assert parametres.lire(conn, "heure_briefing") == "07:30" and parametres.lire(conn, "point_si_rien") is False


def test_apercu_ne_change_rien_puis_enregistrement(client, conn):  # noqa: F811
    j = _csrf(client)
    avant = conn.execute("SELECT id, score FROM evenements ORDER BY id").fetchall()
    r = client.post("/reglages/poids", data=_form_poids(j, "apercu", institutionnel=5, sources=35))
    assert "Aperçu : top 24 h avec ces poids" in r.text and "Avec ces poids" in r.text
    assert parametres.lire(conn, "poids_score") == POIDS
    assert [tuple(x) for x in conn.execute("SELECT id, score FROM evenements ORDER BY id")] == [tuple(x) for x in avant]
    r = client.post("/reglages/poids", data=_form_poids(j, "enregistrer", institutionnel=5))
    assert "Le total doit faire 100" in r.text and parametres.lire(conn, "poids_score") == POIDS
    r = client.post("/reglages/poids", data=_form_poids(j, "enregistrer", institutionnel=5, sources=35),
                    follow_redirects=True)
    assert "Pondération enregistrée" in r.text
    conn.commit()
    assert parametres.lire(conn, "poids_score")["sources"] == 35
    d = conn.execute("SELECT score_details FROM evenements ORDER BY score DESC LIMIT 1").fetchone()[0]
    assert '"sources": {"points": 35' in d                                        # recalcule avec les nouveaux poids


def test_annuler_et_defaut(client, conn):  # noqa: F811
    j = _csrf(client)
    client.post("/reglages/poids", data=_form_poids(j, "enregistrer", institutionnel=5, sources=35))
    conn.commit()
    hid = conn.execute("SELECT id FROM historique_reglages WHERE cle = 'poids_score'").fetchone()[0]
    r = client.post(f"/reglages/annuler/{hid}", data={"csrf": j}, follow_redirects=True)
    assert "Changement annulé" in r.text
    conn.commit()
    assert parametres.lire(conn, "poids_score") == POIDS
    parametres.modifier(conn, "nom_affiche", "J")
    conn.commit()
    client.post("/reglages/defaut/nom_affiche", data={"csrf": j})
    conn.commit()
    assert parametres.lire(conn, "nom_affiche") == "Jean-Luc"
    assert client.post("/reglages/defaut/inconnu", data={"csrf": j}).status_code == 200  # message d'erreur, rien casse
    assert client.post("/reglages/section/inconnue", data={"csrf": j}).status_code == 404


def test_historique_api(client, conn):  # noqa: F811
    r = client.put("/api/v1/parametres/seuil_important", json={"valeur": 72})
    assert r.status_code == 200
    conn.commit()
    h = conn.execute("SELECT origine FROM historique_reglages").fetchone()
    assert h["origine"] == "api"
    assert "Historique des changements" in client.get("/reglages?onglet=historique").text


def test_listes(client, conn):  # noqa: F811
    j = _csrf(client)
    r = client.post("/reglages/listes", data={"csrf": j, "personnalites_suivies": "Grégory Doucet\nLaurent Wauquiez, grégory doucet",
                                              "mots_exclus": "horoscope", "zone_regionale_mots": "lyon",
                                              "mots_impact": "dissolution", "acteurs_politiques": "renaissance"},
                    follow_redirects=True)
    assert "Réglages enregistrés" in r.text
    conn.commit()
    assert parametres.lire(conn, "personnalites_suivies") == ["Grégory Doucet", "Laurent Wauquiez"]   # sans doublon
    r = client.post("/reglages/listes", data={"csrf": j, "mots_exclus": "x" * 90})
    assert "80 caractères maximum" in r.text and parametres.lire(conn, "mots_exclus") == ["horoscope"]


def test_themes_ajout_modif_annulation(client, conn):  # noqa: F811
    j = _csrf(client)
    r = client.post("/reglages/theme", data={"csrf": j, "nouveau": "1", "nom": "Culture", "actif": "on",
                                             "mots": "culture, musée, festival"}, follow_redirects=True)
    assert "Réglages enregistrés" in r.text and "Culture" in r.text
    assert "existe déjà" in client.post("/reglages/theme", data={"csrf": j, "nouveau": "1", "nom": "Culture",
                                                                   "mots": "x"}).text
    client.post("/reglages/theme", data={"csrf": j, "nom": "Culture", "mots": "culture"})   # decoche actif
    conn.commit()
    r = conn.execute("SELECT mots_cles, actif FROM themes WHERE nom = 'Culture'").fetchone()
    assert r["actif"] == 0 and r["mots_cles"] == '["culture"]'
    hid = conn.execute("SELECT MAX(id) FROM historique_reglages WHERE cle = 'theme:Culture'").fetchone()[0]
    client.post(f"/reglages/annuler/{hid}", data={"csrf": j})
    conn.commit()
    r = conn.execute("SELECT mots_cles, actif FROM themes WHERE nom = 'Culture'").fetchone()
    assert r["actif"] == 1 and "festival" in r["mots_cles"]
    assert "au moins un mot-clé" in client.post("/reglages/theme", data={"csrf": j, "nom": "Culture", "mots": " "}).text
    assert "Thème « Culture »" in client.get("/reglages?onglet=historique").text


def test_sources_modif(client, conn):  # noqa: F811
    j = _csrf(client)
    sid = conn.execute("SELECT id FROM sources ORDER BY id LIMIT 1").fetchone()[0]
    r = client.post(f"/reglages/source/{sid}", data={"csrf": j, "fiabilite": "2", "priorite": "3", "frequence_minutes": "60"},
                    follow_redirects=True)
    assert "Réglages enregistrés" in r.text
    conn.commit()
    s = conn.execute("SELECT * FROM sources WHERE id = ?", (sid,)).fetchone()
    assert (s["actif"], s["fiabilite"], s["frequence_minutes"]) == (0, 2, 60)
    assert "fréquence 5 à 1440" in client.post(f"/reglages/source/{sid}", data={"csrf": j, "fiabilite": "9",
                                                                                "priorite": "1", "frequence_minutes": "1"}).text


def test_adresse_publique():
    import pytest

    from app.reglages import adresse_publique
    for ip in ("127.0.0.1", "10.10.0.2", "192.168.1.10", "::1", "169.254.169.254"):
        with pytest.raises(ValueError, match="privée"):
            adresse_publique("https://piege.exemple/rss", lambda h, ip=ip: {ip})
    with pytest.raises(ValueError, match="http"):
        adresse_publique("file:///etc/passwd", lambda h: {"1.1.1.1"})
    with pytest.raises(ValueError, match="http"):
        adresse_publique("https://user:mdp@exemple.fr/rss", lambda h: {"1.1.1.1"})
    adresse_publique("https://exemple.fr/rss", lambda h: {"93.184.216.34"})   # publique : acceptee


def test_ajout_source(client, conn, monkeypatch):  # noqa: F811
    import app.reglages as R
    vrai = R.adresse_publique
    j = _csrf(client)
    ajout = {"csrf": j, "nom": "Nouveau média", "url": "https://media.exemple.fr/rss", "categorie": "media", "niveau": "2",
             "zone": "national", "fiabilite": "3", "frequence_minutes": "30"}
    monkeypatch.setattr(R, "adresse_publique", lambda url, resoudre=None: vrai(url, lambda h: {"10.10.0.2"}))
    assert "adresse privée" in client.post("/reglages/source-ajout", data=ajout).text
    monkeypatch.setattr(R, "adresse_publique", lambda url, resoudre=None: vrai(url, lambda h: {"93.184.216.34"}))
    r = client.post("/reglages/source-ajout", data=ajout, follow_redirects=True)
    assert "Source ajoutée" in r.text
    assert "déjà dans tes sources" in client.post("/reglages/source-ajout", data=ajout).text
    assert "fréquence ≥ 5" in client.post("/reglages/source-ajout", data={**ajout, "url": "https://autre.fr/rss",
                                                                           "frequence_minutes": "1"}).text
    conn.commit()
    hid = conn.execute("SELECT id FROM historique_reglages WHERE cle LIKE 'source:%' AND ancienne IS NULL").fetchone()[0]
    client.post(f"/reglages/annuler/{hid}", data={"csrf": j})
    conn.commit()
    assert conn.execute("SELECT actif FROM sources WHERE nom = 'Nouveau média'").fetchone()[0] == 0


def test_reclasser(client, conn):  # noqa: F811
    j = _csrf(client)
    r = client.post("/reglages/reclasser", data={"csrf": j}, follow_redirects=True)
    assert "Règles réappliquées" in r.text


def test_onglet_modele(client, conn):  # noqa: F811
    j = _csrf(client)
    r = client.get("/reglages?onglet=modele")
    assert r.status_code == 200 and "Quel modèle pour quel travail" in r.text and "règles seules" in r.text
    form = {"csrf": j, "routage_classification": "local:ministral-3:3b, anthropic:", "routage_synthese": "anthropic:",
            "routage_question": "anthropic:", "ia_local_url": "http://10.10.0.2:11434", "ia_local_timeout_s": "90",
            "ia_active": "on"}
    r = client.post("/reglages/ia", data=form, follow_redirects=True)
    assert "Réglages enregistrés" in r.text and "http://10.10.0.2:11434" in r.text
    conn.commit()
    assert parametres.lire(conn, "ia_routage")["synthese"] == ["anthropic:"]
    assert "invalide" in client.post("/reglages/ia", data={**form, "routage_synthese": "pirate:x"}).text
    assert "préciser le modele" in client.post("/reglages/ia", data={**form, "routage_synthese": "local:"}).text \
        or "preciser le modele" in client.post("/reglages/ia", data={**form, "routage_synthese": "local:"}).text
    assert "adresse attendue" in client.post("/reglages/ia", data={**form, "ia_local_url": "ftp://x"}).text
    r = client.post("/reglages/ia/essai", data={"csrf": j, "fournisseur": "anthropic", "modele": "", "action": "tester"})
    assert "non configuré" in r.text                                    # pas de cle : rien n'est appele
    assert client.post("/reglages/ia/essai", data={"csrf": j, "fournisseur": "x"}).status_code == 400
