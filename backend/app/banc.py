"""Banc d'essai IA (mesure) : sur N articles recents deja classes par les regles de J,
on demande a 1 ou 2 modeles leur classement et on MESURE :
- la part de reponses valides (JSON lisible, theme dans la liste de J),
- l'accord avec les regles (theme, type),
- l'accord entre les deux modeles (si deux),
- le temps de reponse.
Rien n'est modifie dans les articles : c'est une mesure, pas une classification.
"""

import json
import sqlite3
import threading
import time
from datetime import timedelta
from pathlib import Path

from app.db import session
from app.ia import ClientIA, FOURNISSEURS, _json, _noter_avis, prompt_classification
from app.parametres import themes_actifs, tous
from app.util import to_iso, utcnow

LOT = 8  # articles par appel (petits lots : un modele local de 3B s'y perd moins)
_verrou = threading.Lock()

def lire_modele(txt: str) -> tuple[str, str]:
    f, _, m = (txt or "").strip().partition(":")
    if f not in FOURNISSEURS:
        raise ValueError(f"modèle « {txt} » : commence par local:, anthropic: ou openrouter:")
    if f != "anthropic" and not m.strip():
        raise ValueError(f"modèle « {txt} » : préciser le nom après « {f}: »")
    return f, m.strip()


def lancer(db_path: Path, ia: ClientIA, modeles: list[str], n: int = 40, en_fond: bool = True) -> int:
    """Cree le banc et le lance (en tache de fond par defaut). Retourne son identifiant."""
    if not 1 <= len(modeles) <= 2:
        raise ValueError("1 ou 2 modèles")
    for m in modeles:
        lire_modele(m)
    n = max(5, min(int(n), 100))
    with session(db_path) as conn:
        # un banc reste "en cours" si le serveur a redemarre pendant la mesure : on le clot apres 1 h
        conn.execute("UPDATE banc_essai SET statut = 'echec', resultats = ? WHERE statut = 'en cours' AND lance_le < ?",
                     (json.dumps({"erreur": "interrompu (redémarrage)"}), to_iso(utcnow() - timedelta(hours=1))))
        if conn.execute("SELECT 1 FROM banc_essai WHERE statut = 'en cours'").fetchone():
            raise ValueError("un banc d'essai est déjà en cours")
        cur = conn.execute("INSERT INTO banc_essai (lance_le, statut, n, modeles) VALUES (?, 'en cours', ?, ?)",
                           (to_iso(utcnow()), n, json.dumps(modeles)))
        banc_id = cur.lastrowid
    if en_fond:
        threading.Thread(target=executer, args=(db_path, ia, banc_id), daemon=True).start()
    else:
        executer(db_path, ia, banc_id)
    return banc_id


def executer(db_path: Path, ia: ClientIA, banc_id: int) -> None:
    with _verrou, session(db_path) as conn:
        b = conn.execute("SELECT * FROM banc_essai WHERE id = ?", (banc_id,)).fetchone()
        try:
            res = _mesurer(conn, ia, json.loads(b["modeles"]), b["n"])
            conn.execute("UPDATE banc_essai SET statut = 'termine', fini_le = ?, resultats = ? WHERE id = ?",
                         (to_iso(utcnow()), json.dumps(res, ensure_ascii=False), banc_id))
        except Exception as exc:  # noqa: BLE001
            conn.execute("UPDATE banc_essai SET statut = 'echec', fini_le = ?, resultats = ? WHERE id = ?",
                         (to_iso(utcnow()), json.dumps({"erreur": type(exc).__name__}), banc_id))


def _mesurer(conn: sqlite3.Connection, ia: ClientIA, modeles: list[str], n: int) -> dict:
    p = tous(conn)
    themes = sorted(themes_actifs(conn))
    types = list(p["types_evenement_mots"])
    arts = conn.execute(
        "SELECT a.id, a.titre, a.texte_extrait, a.theme, a.themes, a.type_evenement, s.nom AS source FROM articles a "
        "JOIN sources s ON s.id = a.source_id WHERE a.pertinent = 1 ORDER BY a.collecte_le DESC LIMIT ?", (n,)).fetchall()
    par_modele, reponses = {}, {}
    for nom in modeles:
        f, m = lire_modele(nom)
        props, duree, appels_ok = {}, 0.0, 0
        for i in range(0, len(arts), LOT):
            lot = arts[i:i + LOT]
            systeme, donnees = prompt_classification(themes, types, lot)
            debut = time.monotonic()
            texte = ia.appeler_modele(conn, "banc", f, m, systeme, donnees, max_tokens=150 * len(lot) + 100)
            duree += time.monotonic() - debut
            data = _json(texte)
            if isinstance(data, list):
                appels_ok += 1
                for x in data:
                    if isinstance(x, dict) and x.get("id") in {a["id"] for a in lot}:
                        props[x["id"]] = x
        valides = accord_th = n_th = accord_ty = n_ty = 0
        for a in arts:
            x = props.get(a["id"])
            if not x or x.get("theme") not in themes:
                continue
            valides += 1
            regles = json.loads(a["themes"] or "[]")
            if regles:
                n_th += 1
                ok = x["theme"] in regles
                accord_th += ok
                _noter_avis(conn, a["id"], "theme", a["theme"], x["theme"], ok, nom, origine="banc")
            if a["type_evenement"] and x.get("type_evenement") in types:
                n_ty += 1
                ok = x["type_evenement"] == a["type_evenement"]
                accord_ty += ok
                _noter_avis(conn, a["id"], "type_evenement", a["type_evenement"], x["type_evenement"], ok, nom,
                            origine="banc")
        nb_appels = max(1, (len(arts) + LOT - 1) // LOT)
        par_modele[nom] = {
            "articles": len(arts), "valides": valides, "pct_valides": _pct(valides, len(arts)),
            "accord_theme": _pct(accord_th, n_th), "n_theme": n_th, "accord_type": _pct(accord_ty, n_ty), "n_type": n_ty,
            "duree_moy_s": round(duree / nb_appels, 1), "appels_reussis": f"{appels_ok}/{nb_appels}"}
        reponses[nom] = props
    entre = None
    if len(modeles) == 2:
        a_, b_ = reponses[modeles[0]], reponses[modeles[1]]
        communs = [i for i in a_ if i in b_ and a_[i].get("theme") in themes and b_[i].get("theme") in themes]
        entre = {"n": len(communs), "accord": _pct(sum(a_[i]["theme"] == b_[i]["theme"] for i in communs), len(communs))}
    return {"modeles": par_modele, "entre_modeles": entre, "articles": len(arts)}


def _pct(a: int, b: int) -> int | None:
    return round(100 * a / b) if b else None


def derniers(conn: sqlite3.Connection, limite: int = 6) -> list[dict]:
    return [{**dict(r), "modeles": json.loads(r["modeles"]), "resultats": json.loads(r["resultats"] or "null")}
            for r in conn.execute("SELECT * FROM banc_essai ORDER BY id DESC LIMIT ?", (limite,))]
