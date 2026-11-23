"""F05 alertes sans doublon, F06-F08 syntheses, envoi Telegram simule."""

from datetime import timedelta

import httpx

from app.alertes import traiter_alertes
from app.analyse import analyser
from app.classification import classer_nouveaux
from app.collecte import collecter
from app.regroupement import regrouper_nouveaux
from app.syntheses import briefing, point_veille, synthese_soir
from app.telegram import Telegram, decouper, notifier
from tests.conftest import T0, ajouter_source, client_mock, rss

TITRE = "Motion de censure : le gouvernement renversé, dissolution de l'Assemblée nationale"


class FauxTelegram(Telegram):
    def __init__(self, echoue=False):
        super().__init__("token", "42")
        self.envoyes, self.echoue = [], echoue

    def envoyer(self, texte):
        if self.echoue:
            return "echec", "panne"
        self.envoyes.append(texte)
        return "envoye", None


def _evt_critique(conn, n=4, decalage=0):
    routes = {}
    for i in range(n):
        url = f"https://s{i}.test/rss"
        if not conn.execute("SELECT 1 FROM sources WHERE url = ?", (url,)).fetchone():
            ajouter_source(conn, nom=f"S{i}", url=url)
        routes[url] = rss([(f"{TITRE} {'!' * i}", f"https://s{i}.test/a{decalage}", T0 - timedelta(minutes=10 + i), "<script>alert(1)</script>Texte")])
    collecter(conn, client_mock(routes), T0 + timedelta(minutes=decalage))
    classer_nouveaux(conn)
    analyser(conn, regrouper_nouveaux(conn), T0)


def test_alerte_envoyee_une_seule_fois(conn):
    _evt_critique(conn)
    tg = FauxTelegram()
    assert len(traiter_alertes(conn, tg, T0)) == 1
    assert traiter_alertes(conn, tg, T0) == []
    assert len(tg.envoyes) == 1
    msg = tg.envoyes[0]
    assert "ALERTE POLITIQUE — CRITIQUE" in msg and "Priorité" in msg and "https://s0.test/a0" in msg
    assert "<script>" not in msg  # contenu collecte echappe


def test_mise_a_jour_si_element_nouveau(conn):
    _evt_critique(conn, n=3)
    tg = FauxTelegram()
    traiter_alertes(conn, tg, T0)
    n_avant = len(tg.envoyes)
    assert n_avant == 1
    # 2 nouvelles sources sur le meme evenement -> mise a jour
    for i in (3, 4):
        ajouter_source(conn, nom=f"S{i}", url=f"https://s{i}.test/rss")
    collecter(conn, client_mock({f"https://s{i}.test/rss": rss([(f"{TITRE} {'!' * i}", f"https://s{i}.test/b", T0, "")])
                                for i in (3, 4)}), T0)
    classer_nouveaux(conn)
    analyser(conn, regrouper_nouveaux(conn), T0)
    traiter_alertes(conn, tg, T0)
    assert len(tg.envoyes) == n_avant + 1 and "MISE À JOUR" in tg.envoyes[-1]
    assert traiter_alertes(conn, tg, T0) == []


def test_notifier_cle_unique_meme_si_echec(conn):
    tg = FauxTelegram(echoue=True)
    assert notifier(conn, tg, "point", "point:x", "texte")
    assert not notifier(conn, tg, "point", "point:x", "texte")
    r = conn.execute("SELECT * FROM notifications").fetchone()
    assert r["statut"] == "echec"
    assert conn.execute("SELECT COUNT(*) FROM journal WHERE composant='diffusion'").fetchone()[0] == 1


def test_mode_simulation_sans_token(conn):
    tg = Telegram("", "")
    assert notifier(conn, tg, "point", "point:y", "texte")
    assert conn.execute("SELECT statut FROM notifications").fetchone()[0] == "simule"


def test_bot_ignore_autres_utilisateurs():
    def handler(req):
        return httpx.Response(200, json={"ok": True, "result": [
            {"update_id": 1, "message": {"chat": {"id": 42}, "text": "/etat"}},
            {"update_id": 2, "message": {"chat": {"id": 666}, "text": "/pause"}},
        ]})
    tg = Telegram("t", "42", httpx.Client(transport=httpx.MockTransport(handler)))
    msgs = tg.messages_recus(0)
    assert [m["autorise"] for m in msgs] == [True, False]


def test_decoupage_messages_longs():
    morceaux = decouper("\n".join(["x" * 100] * 100), 1000)
    assert all(len(m) <= 1000 for m in morceaux) and len(morceaux) >= 10


def test_point_briefing_synthese(conn):
    _evt_critique(conn)
    pv = point_veille(conn, T0, T0 - timedelta(hours=2))
    assert pv.startswith("🕑 <b>POINT DE VEILLE") and "Les trois faits importants" in pv
    b = briefing(conn, T0, T0 - timedelta(hours=24))
    for section in ("Résumé exécutif", "Top 10", "Sujets qui montent", "Politique nationale",
                    "Actualité régionale", "Déclarations et controverses", "Agenda du jour", "À surveiller", "Limites"):
        assert section in b, section
    s = synthese_soir(conn, T0, T0 - timedelta(hours=12))
    assert "SYNTHÈSE DU SOIR" in s and "Informations confirmées" in s


def test_point_vide_non_envoye(conn):
    assert point_veille(conn, T0, T0 - timedelta(hours=2)) is None


def test_resumeur_ia_signale(conn):
    _evt_critique(conn)
    b = briefing(conn, T0, T0 - timedelta(hours=24), resumeur=lambda d, c: "Résumé IA.")
    assert "Résumé IA." in b and "proposé par l'IA" in b


def test_token_jamais_dans_les_erreurs():
    def handler(req):
        raise httpx.ConnectError(f"echec vers {req.url}")
    tg = Telegram("123:SECRET", "42", httpx.Client(transport=httpx.MockTransport(handler)))
    statut, erreur = tg.envoyer("x")
    assert statut == "echec" and "SECRET" not in erreur
