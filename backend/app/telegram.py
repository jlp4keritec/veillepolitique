"""Executeur Telegram : envoi des messages et lecture des commandes de J.

- Le bot ne parle qu'au TELEGRAM_CHAT_ID configure ; tout autre expediteur est ignore.
- Sans token ou sans chat ID : mode SIMULATION (le message est archive, pas envoye).
- Anti-doublon : la notification est enregistree AVANT l'envoi avec une cle unique ;
  une meme cle ne peut jamais repartir.
"""

import html
import sqlite3
from datetime import datetime

import httpx

from app.journal import ecrire
from app.util import to_iso, utcnow

LIMITE = 4000  # Telegram : 4096 caracteres maximum par message


def e(texte) -> str:
    """Echappement HTML de tout texte venant des donnees collectees."""
    return html.escape(str(texte if texte is not None else ""), quote=True)


def lien(url: str, libelle: str) -> str:
    return f'<a href="{e(url)}">{e(libelle)}</a>'


def decouper(texte: str, limite: int = LIMITE) -> list[str]:
    morceaux, courant = [], ""
    for ligne in texte.split("\n"):
        while len(ligne) > limite:
            morceaux.append(ligne[:limite])
            ligne = ligne[limite:]
        if len(courant) + len(ligne) + 1 > limite:
            morceaux.append(courant.rstrip("\n"))
            courant = ""
        courant += ligne + "\n"
    if courant.strip():
        morceaux.append(courant.rstrip("\n"))
    return morceaux


class Telegram:
    def __init__(self, token: str, chat_id: str, client: httpx.Client | None = None):
        self.token = token.strip()
        self.chat_id = str(chat_id).strip()
        self.client = client or httpx.Client(timeout=20)

    @property
    def actif(self) -> bool:
        return bool(self.token and self.chat_id)

    def _api(self, methode: str, **params) -> dict:
        r = self.client.post(f"https://api.telegram.org/bot{self.token}/{methode}", json=params)
        data = r.json()
        if not data.get("ok"):
            # on ne remonte jamais l'URL (elle contient le token)
            raise RuntimeError(f"Telegram {methode} : {data.get('description', r.status_code)}")
        return data

    def envoyer(self, texte: str) -> tuple[str, str | None]:
        if not self.actif:
            return "simule", None
        try:
            for morceau in decouper(texte):
                self._api("sendMessage", chat_id=self.chat_id, text=morceau, parse_mode="HTML",
                          disable_web_page_preview=True)
            return "envoye", None
        except Exception as exc:  # noqa: BLE001
            return "echec", self.masquer(f"{type(exc).__name__}: {exc}")[:500]

    def masquer(self, texte: str) -> str:
        """Le token ne doit jamais apparaitre dans un journal."""
        return texte.replace(self.token, "***") if self.token else texte

    def messages_recus(self, offset: int) -> list[dict]:
        """Messages texte de J uniquement. Les autres sont ignores (et signales)."""
        if not self.actif:
            return []
        data = self._api("getUpdates", offset=offset, timeout=0, allowed_updates=["message"])
        out = []
        for u in data.get("result", []):
            msg = u.get("message") or {}
            out.append({
                "update_id": u["update_id"],
                "autorise": str((msg.get("chat") or {}).get("id")) == self.chat_id,
                "texte": (msg.get("text") or "")[:2000],
            })
        return out


def notifier(conn: sqlite3.Connection, tg, type_: str, cle_unique: str, contenu: str,
             evenement_id: int | None = None, score: int | None = None,
             nb_sources: int | None = None, now: datetime | None = None) -> bool:
    """Enregistre puis envoie. Retourne False si cette cle a deja ete envoyee.

    `tg` : un canal ou un Diffuseur (interface .actif / .envoyer). L'archive garde le texte
    complet ; le message envoye peut etre la version courte avec lien (app/diffusion.py).
    """
    cur = conn.execute(
        "INSERT OR IGNORE INTO notifications (type, cle_unique, evenement_id, score_envoye, "
        "nb_sources_envoye, contenu, statut, envoye_le) VALUES (?,?,?,?,?,?,'en cours',?)",
        (type_, cle_unique, evenement_id, score, nb_sources, contenu, to_iso(now or utcnow())))
    if cur.rowcount == 0:
        return False
    notif_id = cur.lastrowid
    message = _message_a_envoyer(conn, type_, notif_id, contenu, evenement_id)
    conn.execute("UPDATE notifications SET message_envoye = ? WHERE id = ?", (message, notif_id))
    conn.commit()  # trace ecrite avant l'envoi : jamais de double envoi
    statut, erreur = _envoyer(tg, message, contenu)
    conn.execute("UPDATE notifications SET statut = ?, erreur = ? WHERE id = ?", (statut, erreur, notif_id))
    if statut == "echec" or (erreur and erreur.startswith("partiel")):
        ecrire(conn, "ERREUR", "diffusion", f"{type_} {cle_unique} : {erreur}")
    if evenement_id and type_ == "alerte":
        conn.execute("UPDATE evenements SET notifie = 1 WHERE id = ?", (evenement_id,))
    conn.commit()
    return True


def _message_a_envoyer(conn, type_: str, notif_id: int, contenu: str, evenement_id) -> str:
    from app.config import get_settings
    from app.diffusion import message_court
    from app.parametres import lire
    url = get_settings().url_publique.strip()
    if not url or not lire(conn, "messages_courts"):
        return contenu
    return message_court(type_, notif_id, contenu, url, evenement_id)


def _envoyer(tg, message: str, contenu: str):
    from app.diffusion import Diffuseur, sujet_de
    if isinstance(tg, Diffuseur):
        return tg.envoyer(message, sujet_de(contenu))
    return tg.envoyer(message)


def reessayer_echecs(conn: sqlite3.Connection, tg, max_tentatives: int = 3) -> int:
    """Renvoie les notifications en echec (jamais celles deja envoyees)."""
    if not tg.actif:
        return 0
    n = 0
    for r in conn.execute("SELECT * FROM notifications WHERE statut = 'echec' AND tentatives < ?",
                          (max_tentatives,)).fetchall():
        statut, erreur = _envoyer(tg, r["message_envoye"] or r["contenu"], r["contenu"])
        conn.execute("UPDATE notifications SET statut = ?, erreur = ?, tentatives = tentatives + 1 "
                     "WHERE id = ?", (statut, erreur, r["id"]))
        n += statut == "envoye"
    conn.commit()
    return n
