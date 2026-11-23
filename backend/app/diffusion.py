"""Executeur de diffusion : envoie chaque notification sur les canaux configures.

Canaux : Telegram (si token + chat ID) et e-mail (si SMTP + destinataire).
- Un seul destinataire : J. Aucune liste d'abonnes, aucune publication.
- Messages courts : si URL_PUBLIQUE est renseignee, briefing / synthese / point partent
  en resume court avec un lien vers la page de lecture ; les alertes partent en entier
  avec un lien vers la fiche de l'evenement. L'archive garde toujours le texte complet.
"""

import html
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from app.telegram import Telegram, e, lien

TYPES_LONGS = ("briefing", "synthese", "point")


def texte_brut(contenu: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", contenu or ""))


def sujet_de(contenu: str) -> str:
    """Objet d'e-mail : premiere ligne du message, prefixee [VEILLE]."""
    premiere = next((x.strip() for x in texte_brut(contenu).split("\n") if x.strip()), "VEILLE")
    premiere = re.sub(r"[\r\n]+", " ", premiere)[:150]
    return f"[VEILLE] {premiere}"


class Email:
    """Envoi SMTP a J seul (Gmail : mot de passe d'application, port 587)."""

    def __init__(self, hote: str, port: int, utilisateur: str, mot_de_passe: str, destinataire: str,
                 expediteur: str = "", smtp_cls=None):
        self.hote, self.port = hote.strip(), int(port or 587)
        self.utilisateur, self.mot_de_passe = utilisateur.strip(), mot_de_passe
        self.destinataire = destinataire.strip()
        self.expediteur = (expediteur or utilisateur).strip()
        self.smtp_cls = smtp_cls  # injection pour les tests

    @property
    def actif(self) -> bool:
        return bool(self.hote and self.destinataire and self.expediteur)

    def construire(self, texte_html: str, sujet: str | None = None) -> EmailMessage:
        from app.pages import contenu_sur  # nettoyage identique aux pages
        m = EmailMessage()
        m["Subject"] = sujet or sujet_de(texte_html)
        m["From"] = self.expediteur
        m["To"] = self.destinataire
        m["Date"] = formatdate(localtime=True)
        m["Message-ID"] = make_msgid(domain="veille.local")
        m.set_content(texte_brut(texte_html))
        corps = (f'<div style="font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;color:#1b2430;'
                 f'max-width:680px">{contenu_sur(texte_html)}</div>')
        m.add_alternative(corps, subtype="html")
        return m

    def envoyer(self, texte: str, sujet: str | None = None) -> tuple[str, str | None]:
        if not self.actif:
            return "simule", None
        try:
            msg = self.construire(texte, sujet)
            if self.smtp_cls:
                cls = self.smtp_cls
            else:
                cls = smtplib.SMTP_SSL if self.port == 465 else smtplib.SMTP
            if cls is smtplib.SMTP_SSL:
                serveur = cls(self.hote, self.port, timeout=20, context=ssl.create_default_context())
            else:
                serveur = cls(self.hote, self.port, timeout=20)
            with serveur as s:
                if self.port != 465:
                    s.starttls(context=ssl.create_default_context())
                if self.utilisateur:
                    s.login(self.utilisateur, self.mot_de_passe)
                s.send_message(msg)
            return "envoye", None
        except Exception as exc:  # noqa: BLE001
            texte_err = f"{type(exc).__name__}: {exc}"
            if self.mot_de_passe:
                texte_err = texte_err.replace(self.mot_de_passe, "***")
            return "echec", texte_err[:500]


class Diffuseur:
    """Regroupe les canaux. Meme interface qu'un canal : .actif et .envoyer(texte)."""

    def __init__(self, canaux: list):
        self.canaux = [c for c in canaux if c is not None]

    @property
    def actif(self) -> bool:
        return any(c.actif for c in self.canaux)

    def envoyer(self, texte: str, sujet: str | None = None) -> tuple[str, str | None]:
        actifs = [c for c in self.canaux if c.actif]
        if not actifs:
            return "simule", None
        resultats = []
        for c in actifs:
            statut, err = c.envoyer(texte, sujet) if isinstance(c, Email) else c.envoyer(texte)
            resultats.append((type(c).__name__, statut, err))
        erreurs = "; ".join(f"{nom} : {err}" for nom, st, err in resultats if st == "echec")
        if any(st == "envoye" for _, st, _ in resultats):
            return "envoye", (f"partiel - {erreurs}" if erreurs else None)
        return "echec", erreurs or None


def message_court(type_: str, notif_id: int, contenu: str, url_publique: str,
                  evenement_id: int | None = None) -> str:
    """Version courte a envoyer ; le texte complet reste sur la page de lecture."""
    base = url_publique.rstrip("/")
    if type_ == "alerte":
        suite = f"\n\n{lien(f'{base}/evenement/{evenement_id}', 'Fiche complète (score détaillé, chronologie)')}" \
            if evenement_id else ""
        return contenu + suite
    if type_ not in TYPES_LONGS:
        return contenu
    lignes = [x for x in contenu.split("\n")]
    titre = lignes[0] if lignes else e(type_)
    # Les 3 premiers evenements cites (lignes "• <b>titre</b>")
    puces = [x for x in lignes if x.startswith("• <b>")][:3]
    resume = ""
    if "Résumé exécutif</b>" in contenu:
        i = next(k for k, x in enumerate(lignes) if "Résumé exécutif</b>" in x)
        resume = lignes[i + 1] if i + 1 < len(lignes) else ""
    morceaux = [titre]
    if resume:
        morceaux += ["", resume]
    if puces:
        morceaux += [""] + puces
    morceaux += ["", lien(f"{base}/lecture/{notif_id}", "Lire en entier")]
    return "\n".join(morceaux)


def diffuseur_depuis_config(tg: Telegram | None = None) -> Diffuseur:
    from app.config import get_settings
    s = get_settings()
    tg = tg or Telegram(s.telegram_bot_token.get_secret_value(), s.telegram_chat_id)
    mail = Email(s.smtp_hote, s.smtp_port, s.smtp_utilisateur, s.smtp_mot_de_passe.get_secret_value(),
                 s.email_destinataire, s.email_expediteur)
    return Diffuseur([tg, mail])
