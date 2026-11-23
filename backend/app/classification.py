"""Filtrage (F02) et classification par regles (agent de classification, cahier 5.3).

Les regles de J (mots-cles, exclusions, sources) DECIDENT. L'IA peut ensuite
PROPOSER une classification plus fine (voir app/ia.py), validee contre les
listes autorisees ici.
"""

import json
import re
import sqlite3
from dataclasses import dataclass, field

from app.parametres import themes_actifs, tous
from app.util import contient


@dataclass
class Classement:
    pertinent: bool
    raison: str
    theme: str | None = None
    themes: list[str] = field(default_factory=list)
    zone: str = "national"
    acteurs: list[str] = field(default_factory=list)
    acteurs_titre: list[str] = field(default_factory=list)
    type_evenement: str | None = None
    explication: dict = field(default_factory=dict)  # mots trouves : rend le classement explicable


PARTICULES = {"de", "du", "d", "le", "la", "les", "von", "van"}


def page_sujet(titre: str, max_mots: int = 4) -> bool:
    """Titre fait uniquement de noms propres ("Marine Le Pen") : page sujet d'un media."""
    mots = re.findall(r"[\w’'-]+", titre or "")
    if not mots or len(mots) > max_mots:
        return False
    return all(m[:1].isupper() or m.lower() in PARTICULES for m in mots) and any(m[:1].isupper() for m in mots)


def classer(titre_norm: str, texte_norm: str, source_zone: str, params: dict,
            themes: dict[str, list[str]], titre: str = "") -> Classement:
    texte = f"{titre_norm} {texte_norm}"
    if len(titre_norm.split()) < params["titre_mots_min"] or page_sujet(titre):
        return Classement(False, "titre trop court (page sujet d'un media)")
    for mot in params["mots_exclus"]:
        if contient(texte, mot):
            return Classement(False, f"mot exclu : {mot}")

    # Themes : 1 mot-cle dans le titre suffit ; dans le resume seul, il en faut
    # theme_resume_mots_min DIFFERENTS (evite les themes "au hasard"). Le titre compte double.
    scores: dict[str, int] = {}
    mots_themes: dict[str, dict] = {}
    for nom, mots in themes.items():
        dans_titre = [m for m in mots if contient(titre_norm, m)]
        dans_resume = [m for m in mots if m not in dans_titre and contient(texte_norm, m)]
        if dans_titre or len(dans_resume) >= params["theme_resume_mots_min"]:
            scores[nom] = 2 * len(dans_titre) + len(dans_resume)
            mots_themes[nom] = {"titre": dans_titre[:6], "resume": dans_resume[:6]}
    themes_trouves = sorted(scores, key=lambda n: (-scores[n], n))

    mot_regional = next((m for m in params["zone_regionale_mots"] if contient(texte, m)), None)
    regional = source_zone == "regional" or mot_regional is not None
    if source_zone == "regional":
        zone_raison = "source régionale"
    elif mot_regional:
        zone_raison = f"mot régional « {mot_regional} »"
    else:
        zone_raison = "aucun mot régional : national"
    type_raison = None
    tous_acteurs = params["acteurs_institutionnels"] + params["acteurs_politiques"] + params["personnalites_suivies"]
    acteurs = [a for a in tous_acteurs if contient(texte, a)]
    acteurs_titre = [a for a in tous_acteurs if contient(titre_norm, a)]
    type_evt = None
    for t, mots in params["types_evenement_mots"].items():
        m = next((m for m in mots if contient(titre_norm, m)), None)
        if m:
            type_evt, type_raison = t, f"« {m} » dans le titre"
            break
    if type_evt is None and params["type_depuis_resume"]:
        for t, mots in params["types_evenement_mots"].items():
            m = next((m for m in mots if contient(texte_norm, m)), None)
            if m:
                type_evt, type_raison = t, f"« {m} » dans le résumé"
                break

    if not themes_trouves and any(a in params["acteurs_institutionnels"] for a in acteurs):
        themes_trouves = ["Institutions"]  # acteur institutionnel sans theme precis
        mots_themes["Institutions"] = {"titre": [], "resume": [], "note": "acteur institutionnel sans thème précis"}
    pertinent = bool(themes_trouves or acteurs)
    if pertinent:
        raison = "themes/acteurs reconnus"
    elif regional:
        # Article regional sans theme politique : garde uniquement s'il est politique
        raison = "regional sans theme ni acteur politique"
    else:
        raison = "aucun theme ni acteur suivi"
    return Classement(
        pertinent=pertinent, raison=raison,
        theme=themes_trouves[0] if themes_trouves else None, themes=themes_trouves,
        zone="regional" if regional else "national",
        acteurs=list(dict.fromkeys(acteurs)), acteurs_titre=list(dict.fromkeys(acteurs_titre)),
        type_evenement=type_evt,
        explication={"themes": mots_themes, "zone": zone_raison, "type": type_raison,
                     "acteurs": list(dict.fromkeys(acteurs))[:6]},
    )


def classer_nouveaux(conn: sqlite3.Connection) -> tuple[int, int]:
    """Classe les articles pas encore filtres. Retourne (pertinents, ecartes)."""
    params = tous(conn)
    themes = themes_actifs(conn)
    ok = ko = 0
    rows = conn.execute(
        "SELECT a.id, a.titre, a.titre_norm, a.texte_norm, s.zone AS szone FROM articles a "
        "JOIN sources s ON s.id = a.source_id WHERE a.pertinent IS NULL").fetchall()
    for r in rows:
        c = classer(r["titre_norm"], r["texte_norm"], r["szone"], params, themes, r["titre"])
        conn.execute(
            """UPDATE articles SET pertinent = ?, raison_filtre = ?, theme = ?, themes = ?, zone = ?,
               acteurs = ?, acteurs_titre = ?, type_evenement = ?, classif_par = 'regles',
               classif_details = ? WHERE id = ?""",
            (int(c.pertinent), c.raison, c.theme, json.dumps(c.themes, ensure_ascii=False), c.zone,
             json.dumps(c.acteurs, ensure_ascii=False), json.dumps(c.acteurs_titre, ensure_ascii=False),
             c.type_evenement, json.dumps(c.explication, ensure_ascii=False), r["id"]))
        ok += c.pertinent
        ko += not c.pertinent
    return ok, ko
