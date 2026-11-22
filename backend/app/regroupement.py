"""Deduplication et regroupement en dossiers d'information (F03).

Doublons exacts (URL, guid, meme titre meme source) : ecartes a la collecte.
Ici : les articles qui traitent du meme evenement sont rattaches au meme
`evenement`, par similarite des titres + mots communs + proximite temporelle.
"""

import json
import re
import sqlite3
from collections import Counter
from datetime import timedelta

from rapidfuzz import fuzz

from app.parametres import tous
from app.util import from_iso, mots_significatifs, normaliser, to_iso, utcnow

# Mots a majuscule trop courants pour distinguer un evenement
NON_NOMS = {"le", "la", "les", "un", "une", "des", "du", "de", "en", "au", "aux", "ce", "cette", "il", "elle",
            "et", "a", "l", "d", "qui", "que", "pour", "avec", "sur", "dans", "par", "est", "son", "sa", "ses",
            "on", "nous", "vous", "je", "ils", "elles", "mais", "ou", "pourquoi", "comment", "quand", "apres",
            "avant", "video", "direct", "info", "infos", "exclusif", "replay", "interview", "edito", "tribune"}


def noms_propres(titre: str) -> set[str]:
    """Mots a majuscule hors debut de phrase (ex. Moutouh, Beauvau), sigles (RN, LFI), normalises."""
    noms = set()
    debut = True
    for mot in re.findall(r"[\w’'-]+|[:.!?«»\"]", titre):
        if mot in (":", ".", "!", "?", "«", "»", '"'):
            debut = True
            continue
        brut = re.split(r"[’']", mot)[-1]  # l'Elysee -> Elysee
        n = normaliser(brut)
        if (not debut and brut[:1].isupper() and len(n) >= 3 and n not in NON_NOMS) or \
                (brut.isupper() and len(brut) >= 2 and n not in NON_NOMS):
            noms.add(n)
        debut = False
    return noms


def frequences_noms(conn: sqlite3.Connection, centre, fenetre) -> Counter:
    c: Counter = Counter()
    for r in conn.execute("SELECT titre FROM articles WHERE pertinent = 1 AND publie_le BETWEEN ? AND ?",
                          (to_iso(centre - fenetre), to_iso(centre + fenetre))):
        c.update(noms_propres(r["titre"]))
    return c


def similarite(titre_a: str, titre_b: str) -> tuple[float, int]:
    a, b = mots_significatifs(titre_a), mots_significatifs(titre_b)
    communs = len(set(a) & set(b))
    # token_sort : compare tous les mots (token_set rapprochait trop "Macron sur X" et "Macron sur Y")
    return fuzz.token_sort_ratio(" ".join(a), " ".join(b)), communs


def meme_evenement(titre_a: str, titre_b: str, seuil: float, mots_min: int) -> bool:
    sim, communs = similarite(titre_a, titre_b)
    return sim >= seuil and communs >= mots_min


def meme_evenement_rare(titre_a: str, titre_b: str, freq: Counter, p: dict) -> tuple[bool, float]:
    """Deux titres qui partagent un nom propre RARE (mesure sur 48 h) et restent un peu proches."""
    rares = {n for n in noms_propres(titre_a) & noms_propres(titre_b) if freq.get(n, 0) <= p["mot_rare_frequence_max"]}
    if not rares:
        return False, 0.0
    sim, communs = similarite(normaliser(titre_a), normaliser(titre_b))
    return sim >= p["mot_rare_similarite_min"] and communs >= p["mot_rare_mots_communs_min"], sim


def regrouper_nouveaux(conn: sqlite3.Connection) -> set[int]:
    """Rattache les articles pertinents non groupes. Retourne les evenements touches."""
    p = tous(conn)
    fenetre = timedelta(hours=p["fenetre_regroupement_heures"])
    touches: set[int] = set()
    arts = conn.execute(
        "SELECT * FROM articles WHERE pertinent = 1 AND evenement_id IS NULL ORDER BY publie_le, id"
    ).fetchall()
    freq = frequences_noms(conn, utcnow(), fenetre) if arts else Counter()
    for a in arts:
        quand = from_iso(a["publie_le"])
        candidats = conn.execute(
            "SELECT e.id, e.titre_norm FROM evenements e WHERE e.dernier_article_le >= ? "
            "AND e.premier_article_le <= ? ORDER BY e.dernier_article_le DESC LIMIT 300",
            (to_iso(quand - fenetre), to_iso(quand + fenetre))).fetchall()
        meilleur, meilleur_sim = None, -1.0
        for c in candidats:
            # compare aussi aux titres des articles deja dans l'evenement
            titres = conn.execute(
                "SELECT titre, titre_norm FROM articles WHERE evenement_id = ? ORDER BY id DESC LIMIT 10",
                (c["id"],)).fetchall()
            for t in titres:
                sim, communs = similarite(a["titre_norm"], t["titre_norm"])
                ok = sim >= p["seuil_similarite_titre"] and communs >= p["mots_communs_min"]
                if not ok:
                    ok, sim = meme_evenement_rare(a["titre"], t["titre"], freq, p)
                    sim -= 50  # priorite aux correspondances classiques
                if ok and sim > meilleur_sim:
                    meilleur, meilleur_sim = c["id"], sim
        if meilleur is None:
            now = to_iso(utcnow())
            cur = conn.execute(
                "INSERT INTO evenements (titre, titre_norm, premier_article_le, dernier_article_le, "
                "cree_le, maj_le) VALUES (?,?,?,?,?,?)",
                (a["titre"], a["titre_norm"], a["publie_le"], a["publie_le"], now, now))
            meilleur = cur.lastrowid
        conn.execute("UPDATE articles SET evenement_id = ? WHERE id = ?", (meilleur, a["id"]))
        touches.add(meilleur)
    for evt_id in touches:
        agreger(conn, evt_id)
    return touches


def agreger(conn: sqlite3.Connection, evt_id: int) -> None:
    """Recalcule les champs d'un evenement a partir de ses articles."""
    arts = conn.execute(
        "SELECT a.*, s.fiabilite, s.niveau FROM articles a JOIN sources s ON s.id = a.source_id "
        "WHERE a.evenement_id = ? ORDER BY a.publie_le, a.id", (evt_id,)).fetchall()
    if not arts:
        return
    themes = Counter(t for a in arts for t in json.loads(a["themes"]))
    types = Counter(a["type_evenement"] for a in arts if a["type_evenement"])
    acteurs = list(dict.fromkeys(x for a in arts for x in json.loads(a["acteurs"])))
    acteurs_titre = list(dict.fromkeys(x for a in arts for x in json.loads(a["acteurs_titre"])))
    # Titre de reference : article de la source la plus fiable, puis le plus ancien
    ref = sorted(arts, key=lambda a: (-a["fiabilite"], a["niveau"], a["publie_le"]))[0]
    conn.execute(
        """UPDATE evenements SET titre = ?, titre_norm = ?, premier_article_le = ?,
           dernier_article_le = ?, nb_articles = ?, nb_sources = ?, theme = ?, themes = ?, zone = ?,
           acteurs = ?, acteurs_titre = ?, type_evenement = ?, maj_le = ? WHERE id = ?""",
        (ref["titre"], ref["titre_norm"], arts[0]["publie_le"], max(a["publie_le"] for a in arts),
         len(arts), len({a["source_id"] for a in arts}),
         themes.most_common(1)[0][0] if themes else None,
         json.dumps([t for t, _ in themes.most_common()], ensure_ascii=False),
         "regional" if any(a["zone"] == "regional" for a in arts) else "national",
         json.dumps(acteurs, ensure_ascii=False), json.dumps(acteurs_titre, ensure_ascii=False),
         types.most_common(1)[0][0] if types else None, to_iso(utcnow()), evt_id))
