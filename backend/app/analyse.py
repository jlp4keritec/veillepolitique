"""Tendances (cahier 5.4), score d'importance (F04) et statut de verification (5.5).

Tout est calcule a partir de donnees mesurees (nombre d'articles, sources
distinctes, dates, mots-cles, niveau des sources). Chaque resultat porte ses
raisons, pour que le score soit explicable. L'IA n'intervient pas ici.
"""

import json
import sqlite3
from datetime import datetime, timedelta

from app.parametres import tous
from app.util import contient, from_iso, to_iso

STATUTS = [
    "confirmé par source primaire", "corroboré par plusieurs sources", "une seule source disponible",
    "déclaration rapportée", "non vérifié", "contradictoire", "à confirmer",
]
TENDANCES = ["nouveau", "forte hausse", "en hausse", "stable", "en baisse"]
TYPES_FORTS = {"décision", "vote", "réforme", "nomination", "démission", "crise"}
ACTEURS_MAJEURS = {"president de la republique", "elysee", "premier ministre", "matignon",
                   "gouvernement", "assemblee nationale", "senat", "conseil constitutionnel"}


# ---------------------------------------------------------------- tendances
def compter(dates: list[datetime], now: datetime, minutes: int) -> tuple[int, int]:
    d = timedelta(minutes=minutes)
    cur = sum(1 for x in dates if now - d < x <= now)
    prev = sum(1 for x in dates if now - 2 * d < x <= now - d)
    return cur, prev


def tendance(dates: list[datetime], now: datetime, p: dict) -> tuple[str, dict]:
    fen = p["tendance_fenetre_minutes"]
    details = {}
    for m in p["tendance_fenetres_minutes"]:
        c, pr = compter(dates, now, m)
        details[f"{m}min"] = {"courant": c, "precedent": pr}
    cur, prev = compter(dates, now, fen)
    avant = sum(1 for x in dates if x <= now - timedelta(minutes=fen))
    base = max(prev, 1)
    if cur >= 1 and avant == 0:
        etat = "nouveau"
    elif cur >= 3 and cur >= p["tendance_ratio_forte_hausse"] * base:
        etat = "forte hausse"
    elif cur >= 2 and cur >= p["tendance_ratio_hausse"] * base:
        etat = "en hausse"
    elif prev >= 2 and cur <= p["tendance_ratio_baisse"] * prev:
        etat = "en baisse"
    else:
        etat = "stable"
    details["regle"] = f"fenetre {fen} min : {cur} article(s) contre {prev} avant ({avant} plus anciens)"
    return etat, details


# ---------------------------------------------------------------- verification
def verification(arts: list[sqlite3.Row], p: dict) -> tuple[str, dict]:
    sources = {a["source_id"] for a in arts}
    primaires = [a["source_nom"] for a in arts if a["categorie"] == "institutionnel"]
    if primaires:
        return STATUTS[0], {"raison": f"publie par une source institutionnelle : {primaires[0]}"}
    rumeurs = [a for a in arts
               if any(contient(a["titre_norm"], m) for m in p["marqueurs_rumeur"])
               or any(contient(a["texte_norm"], m) for m in p["marqueurs_rumeur_texte"])]
    if rumeurs and len(rumeurs) * 2 >= len(arts):
        return STATUTS[6], {"raison": "formulations conditionnelles ou non confirmees dans la majorite des articles"}
    if len(sources) >= 2:
        return STATUTS[1], {"raison": f"{len(sources)} sources distinctes"}
    if any(contient(a["titre_norm"], m) for a in arts for m in p["marqueurs_declaration"]):
        return STATUTS[3], {"raison": "propos rapportes par une seule source"}
    return STATUTS[2], {"raison": "un seul media a publie cette information"}


# ---------------------------------------------------------------- score
def score(evt: sqlite3.Row, arts: list[sqlite3.Row], etat_tendance: str, details_tendance: dict,
          now: datetime, p: dict) -> tuple[int, dict]:
    w = p["poids_score"]
    acteurs = set(json.loads(evt["acteurs"]))
    titre = set(json.loads(evt["acteurs_titre"]))
    texte = " ".join(f"{a['titre_norm']} {a['texte_norm']}" for a in arts)
    d: dict[str, dict] = {}

    # 1. Importance institutionnelle / politique
    if any(a["niveau"] == 1 for a in arts):
        v, r = 1.0, "source institutionnelle (niveau 1)"
    elif titre & ACTEURS_MAJEURS:
        v, r = 0.8, "acteur institutionnel majeur dans le titre : " + ", ".join(sorted(titre & ACTEURS_MAJEURS))
    elif titre:
        v, r = 0.4, "acteur politique dans le titre : " + ", ".join(sorted(titre)[:3])
    elif acteurs & ACTEURS_MAJEURS:
        v, r = 0.4, "acteur institutionnel cite dans le resume : " + ", ".join(sorted(acteurs & ACTEURS_MAJEURS))
    elif acteurs:
        v, r = 0.2, "acteur politique cite dans le resume : " + ", ".join(sorted(acteurs)[:3])
    else:
        v, r = 0.0, "aucun acteur public identifie"
    if evt["type_evenement"] in TYPES_FORTS:
        v, r = min(1.0, v + 0.2), r + f" + type « {evt['type_evenement']} »"
    d["institutionnel"] = {"points": round(v * w["institutionnel"]), "raison": r}

    # 2. Nouveaute : age du premier article
    age_h = (now - from_iso(evt["premier_article_le"])).total_seconds() / 3600
    v = 1.0 if age_h < 1 else 0.75 if age_h < 3 else 0.5 if age_h < 6 else 0.25 if age_h < 24 else 0.0
    d["nouveaute"] = {"points": round(v * w["nouveaute"]), "raison": f"premier article il y a {age_h:.1f} h"}

    # 3. Acceleration du volume (tendance mesuree)
    fen = details_tendance.get(f"{p['tendance_fenetre_minutes']}min", {"courant": 0})
    v = {"forte hausse": 1.0, "en hausse": 0.6, "stable": 0.2, "en baisse": 0.0}.get(etat_tendance)
    if etat_tendance == "nouveau":
        v = min(1.0, 0.25 + 0.25 * (fen["courant"] - 1))
    d["acceleration"] = {"points": round(v * w["acceleration"]),
                         "raison": f"tendance « {etat_tendance} » - {details_tendance.get('regle', '')}"}

    # 4. Nombre de sources independantes
    n = evt["nb_sources"]
    v = {0: 0, 1: 0.2, 2: 0.47, 3: 0.73}.get(n, 1.0)
    d["sources"] = {"points": round(v * w["sources"]), "raison": f"{n} source(s) distincte(s)"}

    # 5. Impact potentiel
    mots = [m for m in p["mots_impact"] if contient(texte, m)]
    v = min(1.0, len(mots) / 3)
    if evt["type_evenement"] in ("crise", "démission"):
        v = min(1.0, v + 0.34)
    d["impact"] = {"points": round(v * w["impact"]),
                   "raison": ("mots a fort impact : " + ", ".join(mots)) if mots else
                   f"type « {evt['type_evenement'] or 'non determine'} »"}

    # 6. Pertinence avec les themes suivis
    etranger = evt["theme"] == "International" and not acteurs
    v = (0.2 if etranger else 0.6 if evt["theme"] else 0) + (0.4 if evt["zone"] == "regional" else 0)
    d["pertinence"] = {"points": round(v * w["pertinence"]),
                       "raison": f"theme {evt['theme'] or 'aucun'}, zone {evt['zone']}"
                                 + (" (actualite etrangere sans acteur francais)" if etranger else "")}

    total = min(100, sum(x["points"] for x in d.values()))
    return total, d


def niveau(s: int, p: dict | None = None) -> str:
    crit = p["seuil_critique"] if p else 85
    imp = p["seuil_important"] if p else 70
    return ("critique" if s >= crit else "très important" if s >= imp else "important" if s >= 50
            else "information" if s >= 30 else "faible")


def analyser(conn: sqlite3.Connection, evt_ids, now: datetime) -> None:
    p = tous(conn)
    for evt_id in evt_ids:
        evt = conn.execute("SELECT * FROM evenements WHERE id = ?", (evt_id,)).fetchone()
        arts = conn.execute(
            "SELECT a.*, s.niveau, s.categorie, s.fiabilite, s.nom AS source_nom FROM articles a "
            "JOIN sources s ON s.id = a.source_id WHERE a.evenement_id = ?", (evt_id,)).fetchall()
        if not evt or not arts:
            continue
        dates = [from_iso(a["publie_le"]) for a in arts]
        etat, det_t = tendance(dates, now, p)
        statut, det_v = verification(arts, p)
        sc, det_s = score(evt, arts, etat, det_t, now, p)
        conn.execute(
            "UPDATE evenements SET tendance = ?, tendance_details = ?, verification = ?, "
            "verification_details = ?, score = ?, score_details = ?, maj_le = ? WHERE id = ?",
            (etat, json.dumps(det_t, ensure_ascii=False), statut, json.dumps(det_v, ensure_ascii=False),
             sc, json.dumps(det_s, ensure_ascii=False), to_iso(now), evt_id))


def evenements_recents(conn: sqlite3.Connection, now: datetime, heures: int = 24) -> list[int]:
    return [r["id"] for r in conn.execute(
        "SELECT id FROM evenements WHERE dernier_article_le >= ?", (to_iso(now - timedelta(hours=heures)),))]
