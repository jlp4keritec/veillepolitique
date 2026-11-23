"""Explications affichees dans les bulles d'aide et la page « Comment ca marche ».

Tout vient des donnees mesurees et des regles de J en vigueur : rien n'est invente.
"""

import json
import sqlite3

# Statuts de verification (cahier ch. 5.5) : sens en langage clair
VERIFICATION = {
    "confirmé par source primaire": "Publié par la source officielle elle-même (institution, ministère, assemblée…).",
    "corroboré par plusieurs sources": "Au moins deux médias indépendants rapportent la même information.",
    "une seule source disponible": "Un seul média l'a publié pour l'instant : à prendre avec prudence.",
    "déclaration rapportée": "Ce sont les propos d'une personne, rapportés par un média : pas un fait établi.",
    "non vérifié": "Pas encore assez d'éléments pour se prononcer.",
    "contradictoire": "Des sources disent des choses incompatibles.",
    "à confirmer": "Formulations au conditionnel ou non confirmées (« serait », « selon nos informations »…) : "
                   "jamais présenté comme un fait.",
}

TENDANCES = {
    "nouveau": "Sujet apparu récemment, pas encore d'historique à comparer.",
    "forte hausse": "Beaucoup plus d'articles que sur la période précédente (ratio ≥ réglage « forte hausse »).",
    "en hausse": "Plus d'articles que sur la période précédente (ratio ≥ réglage « hausse »).",
    "stable": "Autant d'articles que sur la période précédente.",
    "en baisse": "Moins d'articles que sur la période précédente (ratio ≤ réglage « baisse »).",
}


def echelle(p: dict) -> list[tuple[str, str, str]]:
    """(intervalle, niveau, classe CSS) selon les seuils de J."""
    c, i = p["seuil_critique"], p["seuil_important"]
    return [(f"≥ {c}", "critique : alerte immédiate", "crit"), (f"{i} – {c - 1}", "très important", "tres"),
            (f"50 – {i - 1}", "important", "imp"), ("30 – 49", "information", "info"), ("< 30", "faible", "faible")]


def score(details_json: str | dict | None) -> list[dict]:
    """Criteres du score, du plus fort au plus faible."""
    d = details_json if isinstance(details_json, dict) else json.loads(details_json or "{}")
    return sorted(({"cle": k, **v} for k, v in d.items() if isinstance(v, dict)), key=lambda x: -x.get("points", 0))


def classement(conn: sqlite3.Connection, evt_id: int, theme: str | None) -> dict:
    """Pourquoi ce theme / cette zone / ce type : mots trouves dans les articles de l'evenement."""
    rows = conn.execute("SELECT classif_details, classif_par, historique FROM articles WHERE evenement_id = ?",
                        (evt_id,)).fetchall()
    mots_titre, mots_resume, zones, types, notes = [], [], [], [], []
    ia = conserve = 0
    for r in rows:
        if r["classif_details"]:
            conserve += 1
            d = json.loads(r["classif_details"])
            t = (d.get("themes") or {}).get(theme or "") or {}
            mots_titre += t.get("titre", [])
            mots_resume += t.get("resume", [])
            if t.get("note"):
                notes.append(t["note"])
            if d.get("zone"):
                zones.append(d["zone"])
            if d.get("type"):
                types.append(d["type"])
        if r["classif_par"] == "regles+ia" and any("theme" in h.get("champs", []) for h in json.loads(r["historique"] or "[]")
                                                    if h.get("par") == "ia"):
            ia += 1
    uniq = lambda xs: list(dict.fromkeys(xs))[:6]  # noqa: E731
    return {"articles": len(rows), "conserves": conserve, "mots_titre": uniq(mots_titre),
            "mots_resume": uniq(mots_resume), "notes": uniq(notes), "zones": uniq(zones), "types": uniq(types),
            "ia": ia}
