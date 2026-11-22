"""Filtrage (F02) et classification par regles (agent de classification, cahier 5.3).

Les regles de J (mots-cles, exclusions, sources) DECIDENT. L'IA peut ensuite
PROPOSER une classification plus fine (voir app/ia.py), validee contre les
listes autorisees ici.
"""

import json
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


def classer(titre_norm: str, texte_norm: str, source_zone: str, params: dict,
            themes: dict[str, list[str]]) -> Classement:
    texte = f"{titre_norm} {texte_norm}"
    if len(titre_norm.split()) < params["titre_mots_min"]:
        return Classement(False, "titre trop court (page sujet d'un media)")
    for mot in params["mots_exclus"]:
        if contient(texte, mot):
            return Classement(False, f"mot exclu : {mot}")

    # Themes : le titre compte double
    scores: dict[str, int] = {}
    for nom, mots in themes.items():
        s = sum(2 if contient(titre_norm, m) else 1 if contient(texte_norm, m) else 0 for m in mots)
        if s:
            scores[nom] = s
    themes_trouves = sorted(scores, key=lambda n: (-scores[n], n))

    regional = source_zone == "regional" or any(contient(texte, m) for m in params["zone_regionale_mots"])
    tous_acteurs = params["acteurs_institutionnels"] + params["acteurs_politiques"] + params["personnalites_suivies"]
    acteurs = [a for a in tous_acteurs if contient(texte, a)]
    acteurs_titre = [a for a in tous_acteurs if contient(titre_norm, a)]
    type_evt = None
    for t, mots in params["types_evenement_mots"].items():
        if any(contient(titre_norm, m) for m in mots):
            type_evt = t
            break
    if type_evt is None and params["type_depuis_resume"]:
        for t, mots in params["types_evenement_mots"].items():
            if any(contient(texte_norm, m) for m in mots):
                type_evt = t
                break

    if not themes_trouves and any(a in params["acteurs_institutionnels"] for a in acteurs):
        themes_trouves = ["Institutions"]  # acteur institutionnel sans theme precis
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
    )


def classer_nouveaux(conn: sqlite3.Connection) -> tuple[int, int]:
    """Classe les articles pas encore filtres. Retourne (pertinents, ecartes)."""
    params = tous(conn)
    themes = themes_actifs(conn)
    ok = ko = 0
    rows = conn.execute(
        "SELECT a.id, a.titre_norm, a.texte_norm, s.zone AS szone FROM articles a "
        "JOIN sources s ON s.id = a.source_id WHERE a.pertinent IS NULL").fetchall()
    for r in rows:
        c = classer(r["titre_norm"], r["texte_norm"], r["szone"], params, themes)
        conn.execute(
            """UPDATE articles SET pertinent = ?, raison_filtre = ?, theme = ?, themes = ?, zone = ?,
               acteurs = ?, acteurs_titre = ?, type_evenement = ?, classif_par = 'regles' WHERE id = ?""",
            (int(c.pertinent), c.raison, c.theme, json.dumps(c.themes, ensure_ascii=False), c.zone,
             json.dumps(c.acteurs, ensure_ascii=False), json.dumps(c.acteurs_titre, ensure_ascii=False),
             c.type_evenement, r["id"]))
        ok += c.pertinent
        ko += not c.pertinent
    return ok, ko
