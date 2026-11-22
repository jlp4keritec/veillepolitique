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


PARTICULES = {"de", "du", "d", "le", "la", "von", "van", "ben", "el"}
PONCTUATION_FIN = {":", ".", "!", "?", "«", "»", '"'}


def noms_propres(titre: str) -> set[str]:
    return _analyse_noms(titre)[0]


def prenoms(titre: str) -> set[str]:
    """Mots d'un nom compose sauf le dernier ("Marine", "Jean-Luc") : partages, peu distinctifs."""
    return _analyse_noms(titre)[1]


def _analyse_noms(titre: str) -> tuple[set[str], set[str]]:
    """Noms propres distinctifs d'un titre, normalises.

    - Une suite de mots a majuscule est UN nom : seul son dernier mot compte
      ("Marine Tondelier" -> tondelier, "Marine Le Pen" -> pen), car les prenoms sont partages.
    - Un mot a majuscule seul en debut de phrase est ignore (majuscule grammaticale).
    - Les sigles (RN, LFI) comptent.
    """
    noms: set[str] = set()
    autres: set[str] = set()
    jetons = re.findall(r"[\w’'-]+|[:.!?«»\",;()]", titre)
    etat = {"suite": [], "au_debut": False}

    def fermer():
        suite = etat["suite"]
        if suite and not (etat["au_debut"] and len(suite) == 1):
            n = normaliser(suite[-1])
            if len(n) >= 3 and n not in NON_NOMS:
                noms.add(n)
            autres.update(normaliser(x) for x in suite[:-1])
        etat["suite"] = []

    debut = True
    for mot in jetons:
        if not re.match(r"\w", mot):
            fermer()
            debut = mot in PONCTUATION_FIN
            continue
        brut = re.split(r"[’']", mot)[-1]  # l'Elysee -> Elysee
        if brut.isupper() and len(brut) >= 2 and normaliser(brut) not in NON_NOMS:  # sigle
            fermer()
            noms.add(normaliser(brut))
        elif brut[:1].isupper():
            if not etat["suite"]:
                etat["au_debut"] = debut
            etat["suite"].append(brut)
        elif etat["suite"] and normaliser(brut) in PARTICULES and not (etat["au_debut"] and len(etat["suite"]) == 1):
            pass  # "Dominique de Villepin" : la suite continue (mais pas "Fuites de Beauvau" en debut de titre)
        else:
            fermer()
        debut = False
    fermer()
    return noms, autres


def frequences_noms(conn: sqlite3.Connection, centre, fenetre) -> Counter:
    c: Counter = Counter()
    for r in conn.execute("SELECT titre FROM articles WHERE pertinent = 1 AND publie_le BETWEEN ? AND ?",
                          (to_iso(centre - fenetre), to_iso(centre + fenetre))):
        c.update(noms_propres(r["titre"]))
    return c


def _mots(titre_norm: str) -> list[str]:
    # Les nombres (2027, 49.3...) ne distinguent pas un evenement
    return [m for m in mots_significatifs(titre_norm) if not m.replace(".", "").replace("-", "").isdigit()]


def similarite(titre_a: str, titre_b: str) -> tuple[float, int]:
    a, b = _mots(titre_a), _mots(titre_b)
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
    sim, _ = similarite(normaliser(titre_a), normaliser(titre_b))
    exclus = prenoms(titre_a) | prenoms(titre_b)
    partages = (set(_mots(normaliser(titre_a))) & set(_mots(normaliser(titre_b)))) | \
        (noms_propres(titre_a) & noms_propres(titre_b))  # inclut les sigles courts (RN)
    communs = len(partages - exclus)
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
