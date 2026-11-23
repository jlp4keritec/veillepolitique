"""Agent orchestrateur (cahier 5.1, workflow ch. 10).

Cycle standard : collecte -> normalisation/dedoublonnage -> filtrage/classification
-> propositions IA (validees) -> regroupement -> tendances/score/verification
-> decision d'alerte -> envoi -> archivage et indicateurs.

Horloge : point de veille (toutes les N h dans la plage), briefing 08:00,
synthese 20:00 (heure de Paris). Rattrapage apres interruption dans les 3 h.
Un verrou unique evite deux traitements simultanes.
"""

import threading
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from app.alertes import traiter_alertes
from app.analyse import analyser, evenements_recents
from app.classification import classer_nouveaux
from app.collecte import client_http, collecter
from app.commandes import traiter
from app.config import get_settings
from app.db import get_etat, session, set_etat
from app.diffusion import diffuseur_depuis_config
from app.ia import ClientIA, client_ia_depuis_config, etat_budget, proposer_classification, resumes_vers_evenements, resumeur
from app.journal import ecrire
from app import maintenance
from app.quotidien import tache as journal_quotidien
from app.parametres import tous
from app.regroupement import regrouper_nouveaux
from app.syntheses import briefing, point_veille, synthese_soir
from app.telegram import Telegram, notifier, reessayer_echecs
from app.util import from_iso, to_iso, utcnow

PARIS = ZoneInfo("Europe/Paris")
RATTRAPAGE = timedelta(hours=3)


def _heure(local: datetime, hhmm: str) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return local.replace(hour=h, minute=m, second=0, microsecond=0)


class Orchestrateur:
    def __init__(self, db_path: Path | None = None, http: httpx.Client | None = None,
                 tg: Telegram | None = None, ia: ClientIA | None = None):
        s = get_settings()
        self.db_path = db_path or s.db_path
        self.http = http or client_http()
        self.tg = tg or Telegram(s.telegram_bot_token.get_secret_value(), s.telegram_chat_id)
        self.diff = diffuseur_depuis_config(self.tg)  # Telegram + e-mail selon .env
        self.ia = ia or client_ia_depuis_config()
        self.verrou = threading.Lock()

    # ------------------------------------------------------------ cycle
    def cycle(self, now: datetime | None = None) -> dict:
        now = now or utcnow()
        with self.verrou, session(self.db_path) as conn:
            p = tous(conn)
            res = {"collecte": None}
            if p["collecte_active"]:
                c = collecter(conn, self.http, now)
                res["collecte"] = {"sources": c.sources_traitees, "erreurs": c.sources_en_erreur,
                                   "nouveaux": c.articles_nouveaux}
            pert, ecart = classer_nouveaux(conn)
            res["pertinents"], res["ecartes"] = pert, ecart
            res["ia_classifies"] = proposer_classification(conn, self.ia)
            touches = regrouper_nouveaux(conn)
            resumes_vers_evenements(conn, touches)
            recents = set(evenements_recents(conn, now)) | touches
            analyser(conn, recents, now)
            res["evenements_analyses"] = len(recents)
            conn.commit()
            res["alertes"] = traiter_alertes(conn, self.diff, now)
            self._controle_budget(conn, now)
            reessayer_echecs(conn, self.diff)
            set_etat(conn, "dernier_cycle", to_iso(now))
            ecrire(conn, "INFO", "orchestrateur", f"cycle : {res}")
            return res

    def _controle_budget(self, conn, now: datetime) -> None:
        b = etat_budget(conn, now)
        p = tous(conn)
        for seuil in (p["budget_alerte_pct"], 100):
            if b["pct"] >= seuil:
                notifier(conn, self.diff, "systeme", f"budget:{b['mois']}:{seuil}",
                         f"💶 <b>Budget IA</b> : {b['depense_eur']:.2f} € / {b['budget_eur']:.2f} € "
                         f"({b['pct']} %)." + (" Appels IA suspendus, repli sur les règles." if seuil >= 100 else ""), now=now)

    # ------------------------------------------------------------ syntheses
    def envoyer_synthese(self, type_: str, now: datetime | None = None, a_la_demande: bool = True) -> bool:
        now = now or utcnow()
        with self.verrou, session(self.db_path) as conn:
            return self._synthese(conn, type_, now, a_la_demande)

    def _synthese(self, conn, type_: str, now: datetime, a_la_demande: bool) -> bool:
        res = resumeur(conn, self.ia) if self.ia.disponible(conn, now, "synthese")[0] else None
        local = now.astimezone(PARIS)
        if type_ == "briefing":
            prec = get_etat(conn, "dernier_briefing_le")
            depuis = min(from_iso(prec), now - timedelta(hours=24)) if prec else now - timedelta(hours=24)
            texte = briefing(conn, now, depuis, res)
        elif type_ == "synthese":
            debut_jour = local.replace(hour=0, minute=0, second=0, microsecond=0)
            texte = synthese_soir(conn, now, debut_jour, res)
        else:
            prec = get_etat(conn, "dernier_point_le")
            depuis = from_iso(prec) if prec else now - timedelta(hours=tous(conn)["intervalle_point_heures"])
            deja = {r["evenement_id"] for r in conn.execute(
                "SELECT evenement_id FROM notifications WHERE type = 'alerte' AND envoye_le >= ?", (to_iso(depuis),))}
            texte = point_veille(conn, now, depuis, exclure=deja)
            if texte is None:
                if a_la_demande:
                    texte = "🕑 Point de veille : rien de nouveau depuis le dernier point."
                else:
                    set_etat(conn, "dernier_point_le", to_iso(now))
                    return False
        suffixe = f":demande:{to_iso(now)}" if a_la_demande else ""
        cle = {"briefing": f"briefing:{local.date()}", "synthese": f"synthese:{local.date()}",
               "point": f"point:{to_iso(now)}"}[type_] + suffixe
        envoye = notifier(conn, self.diff, type_, cle, texte, now=now)
        if not a_la_demande:
            set_etat(conn, {"briefing": "dernier_briefing_le", "synthese": "derniere_synthese_le",
                            "point": "dernier_point_le"}[type_], to_iso(now))
        return envoye

    def horloge(self, now: datetime | None = None) -> list[str]:
        """Appelee chaque minute : envoie ce qui est du (une seule fois par jour pour 08:00 / 20:00)."""
        now = now or utcnow()
        local = now.astimezone(PARIS)
        envoyes = []
        with self.verrou, session(self.db_path) as conn:
            p = tous(conn)
            for type_, cle_heure, cle_etat in (("briefing", "heure_briefing", "dernier_briefing_le"),
                                               ("synthese", "heure_synthese_soir", "derniere_synthese_le")):
                prevu = _heure(local, p[cle_heure])
                der = get_etat(conn, cle_etat)
                deja = der and from_iso(der).astimezone(PARIS).date() == local.date()
                if prevu <= local < prevu + RATTRAPAGE and not deja:
                    self._synthese(conn, type_, now, a_la_demande=False)
                    envoyes.append(type_)
            debut, _, fin = p["plage_points"].partition("-")
            if _heure(local, debut) <= local <= _heure(local, fin) and not envoyes:
                der = get_etat(conn, "dernier_point_le")
                # pas de point juste apres un briefing / une synthese
                autres = [get_etat(conn, k) for k in ("dernier_briefing_le", "derniere_synthese_le")]
                recent = any(a and now - from_iso(a) < timedelta(minutes=30) for a in autres)
                if not recent and (not der or now - from_iso(der) >= timedelta(hours=p["intervalle_point_heures"])):
                    if self._synthese(conn, "point", now, a_la_demande=False):
                        envoyes.append("point")
            try:  # photo quotidienne du top (F10) : n'empeche jamais le reste
                for j in journal_quotidien(conn, now):
                    ecrire(conn, "INFO", "journal", f"photo du top enregistree pour le {j}")
            except Exception as exc:  # noqa: BLE001
                ecrire(conn, "ERREUR", "journal", f"photo quotidienne : {type(exc).__name__}")
            compacter = False
            try:  # entretien de nuit : conservation (regles de J)
                bilan = maintenance.tache(conn, now)
                if bilan:
                    ecrire(conn, "INFO", "entretien", f"extraits alleges : {bilan['extraits']}, "
                                                      f"messages techniques purges : {bilan['journal']}")
                    compacter = bool(bilan.get("compactage"))
            except Exception as exc:  # noqa: BLE001
                ecrire(conn, "ERREUR", "entretien", f"{type(exc).__name__}")
        if compacter:  # hors transaction : VACUUM mensuel (verrou : aucun cycle en meme temps)
            try:
                with self.verrou:
                    maintenance.compacter(self.db_path, now)
            except Exception as exc:  # noqa: BLE001
                with session(self.db_path) as conn:
                    ecrire(conn, "ERREUR", "entretien", f"compactage : {type(exc).__name__}")
        return envoyes

    # ------------------------------------------------------------ Telegram entrant
    def ecouter(self, now: datetime | None = None) -> int:
        if not self.tg.actif:
            return 0
        with session(self.db_path) as conn:
            offset = int(get_etat(conn, "telegram_offset", "0"))
        try:
            msgs = self.tg.messages_recus(offset)
        except Exception as exc:  # noqa: BLE001
            with session(self.db_path) as conn:
                ecrire(conn, "ERREUR", "telegram", f"lecture : {type(exc).__name__}")
            return 0
        traites = 0
        for m in msgs:
            with session(self.db_path) as conn:
                set_etat(conn, "telegram_offset", str(m["update_id"] + 1))
                if not m["autorise"]:
                    ecrire(conn, "ALERTE", "telegram", "message ignore : expediteur non autorise")
                    continue
                if not m["texte"]:
                    continue
            with self.verrou, session(self.db_path) as conn:
                reponse = traiter(conn, m["texte"], now or utcnow(), self.ia,
                                  declencher=lambda t: self._synthese(conn, t, now or utcnow(), True))
                notifier(conn, self.tg, "reponse", f"reponse:{m['update_id']}", reponse)
                traites += 1
        return traites

    def question(self, texte: str, now: datetime | None = None) -> str:
        with self.verrou, session(self.db_path) as conn:
            return traiter(conn, texte, now or utcnow(), self.ia)

