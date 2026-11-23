"""Diffusion : e-mail, plusieurs canaux, messages courts avec lien, garde-fou production."""

import pytest

from app.diffusion import Diffuseur, Email, message_court, sujet_de
from app.telegram import notifier, reessayer_echecs
from tests.test_alertes_syntheses import FauxTelegram


class FauxSMTP:
    envoyes: list = []

    def __init__(self, hote, port, timeout=None, context=None):
        self.hote, self.port = hote, port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        self.tls = True

    def login(self, u, p):
        if p != "bon-mdp":
            raise RuntimeError(f"auth refusee pour {p}")

    def send_message(self, m):
        FauxSMTP.envoyes.append(m)


def email(mdp="bon-mdp"):
    FauxSMTP.envoyes = []
    return Email("smtp.test", 587, "j@test.fr", mdp, "j@test.fr", smtp_cls=FauxSMTP)


def test_email_construit_et_envoye():
    m = email()
    statut, err = m.envoyer("🚨 <b>ALERTE POLITIQUE — CRITIQUE</b>\n<b>Titre &lt;script&gt;</b>\n"
                            '<a href="https://s.test/a">Source</a>')
    assert statut == "envoye" and err is None
    msg = FauxSMTP.envoyes[0]
    assert msg["Subject"] == "[VEILLE] 🚨 ALERTE POLITIQUE — CRITIQUE" and msg["To"] == "j@test.fr"
    corps_html = msg.get_body(("html",)).get_content()
    assert 'href="https://s.test/a"' in corps_html and "<script>" not in corps_html
    assert "Titre <script>" in msg.get_body(("plain",)).get_content()  # texte brut lisible


def test_email_mot_de_passe_jamais_dans_l_erreur():
    statut, err = email("mauvais-secret").envoyer("x")
    assert statut == "echec" and "mauvais-secret" not in err


def test_email_inactif_sans_config():
    assert Email("", 587, "", "", "").envoyer("x") == ("simule", None)


def test_diffuseur_plusieurs_canaux():
    tg_ok, mail = FauxTelegram(), email()
    assert Diffuseur([tg_ok, mail]).envoyer("<b>Point</b>") == ("envoye", None)
    assert len(tg_ok.envoyes) == 1 and len(FauxSMTP.envoyes) == 1
    statut, err = Diffuseur([FauxTelegram(echoue=True), email()]).envoyer("x")
    assert statut == "envoye" and err.startswith("partiel")  # un canal suffit
    assert Diffuseur([FauxTelegram(echoue=True)]).envoyer("x")[0] == "echec"
    assert Diffuseur([Email("", 0, "", "", "")]).envoyer("x") == ("simule", None)


BRIEFING = ("☀️ <b>VEILLE POLITIQUE — 22/11/2026 — 08:00</b>\n\n<b>Résumé exécutif</b>\n6 événements suivis.\n\n"
            "<b>Top 10</b>\n• <b>Motion de censure</b>\n  98/100\n• <b>Budget Lyon</b>\n  53/100\n"
            "• <b>Moutouh</b>\n• <b>Quatrième</b>")


def test_message_court_avec_lien():
    m = message_court("briefing", 12, BRIEFING, "https://veille.test/")
    assert "VEILLE POLITIQUE" in m and "6 événements suivis." in m
    assert "Motion de censure" in m and "Moutouh" in m and "Quatrième" not in m  # 3 premiers
    assert 'href="https://veille.test/lecture/12"' in m and len(m) < len(BRIEFING) + 120
    a = message_court("alerte", 3, "🚨 <b>ALERTE</b>", "https://veille.test", evenement_id=7)
    assert a.startswith("🚨 <b>ALERTE</b>") and 'href="https://veille.test/evenement/7"' in a


def test_notifier_archive_complet_envoie_court(conn, monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("URL_PUBLIQUE", "https://veille.test")
    get_settings.cache_clear()
    tg = FauxTelegram()
    assert notifier(conn, tg, "briefing", "briefing:x", BRIEFING)
    r = conn.execute("SELECT * FROM notifications").fetchone()
    assert r["contenu"] == BRIEFING  # archive complete
    assert f"/lecture/{r['id']}" in tg.envoyes[0] and "Quatrième" not in tg.envoyes[0]
    get_settings.cache_clear()


def test_sans_url_message_complet(conn):
    tg = FauxTelegram()
    notifier(conn, tg, "briefing", "briefing:y", BRIEFING)
    assert tg.envoyes[0] == BRIEFING


def test_reessai_renvoie_le_message_court(conn, monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("URL_PUBLIQUE", "https://veille.test")
    get_settings.cache_clear()
    notifier(conn, FauxTelegram(echoue=True), "briefing", "briefing:z", BRIEFING)
    tg = FauxTelegram()
    assert reessayer_echecs(conn, tg) == 1 and "/lecture/" in tg.envoyes[0]
    get_settings.cache_clear()


def test_sujet():
    assert sujet_de("\n🕑 <b>POINT DE VEILLE — 14:00</b>\nx") == "[VEILLE] 🕑 POINT DE VEILLE — 14:00"


def test_production_exige_mot_de_passe(monkeypatch):
    from app.config import get_settings
    from app.main import verifier_production
    monkeypatch.setenv("ENVIRONNEMENT", "vps")
    monkeypatch.setenv("MOT_DE_PASSE_PAGES", "court")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="MOT_DE_PASSE_PAGES"):
        verifier_production(get_settings())
    monkeypatch.setenv("MOT_DE_PASSE_PAGES", "un-mot-de-passe-solide")
    get_settings.cache_clear()
    verifier_production(get_settings())  # ne leve pas
    get_settings.cache_clear()
