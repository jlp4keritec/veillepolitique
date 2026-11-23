"""Page Reglages (F11) : J modifie SES regles depuis le navigateur.

- Chaque section est validee entierement avant d'ecrire (tout ou rien).
- Chaque changement est historise (historique_reglages) et peut etre annule.
- Changer la ponderation recalcule les evenements recents (48 h) ; les photos du Journal ne bougent pas.
- L'apercu de ponderation recalcule le top avec les deux jeux de poids AU MEME INSTANT,
  pour que l'ecart ne vienne que des poids (donnees mesurees, rien d'invente).
"""

import json
import sqlite3
from datetime import datetime

from app import parametres
from app.analyse import analyser, evenements_recents, score, tendance
from app.util import from_iso, to_iso, utcnow

# (cle, libelle, type de champ, aide)  - type : nombre, heure, texte, oui_non, plage
SECTIONS: dict[str, dict] = {
    "seuils": {"titre": "Seuils et alertes", "champs": [
        ("seuil_critique", "Seuil d'alerte critique (/100)", "nombre", "Une alerte part à partir de ce score."),
        ("seuil_important", "Seuil « très important » (/100)", "nombre", "Mis en avant dans les synthèses."),
        ("alertes_actives", "Envoyer les alertes", "oui_non", ""),
        ("alerte_delta_score", "Nouvelle alerte si le score monte de", "nombre", "points (sinon : jamais deux fois)."),
        ("alerte_delta_sources", "… ou si autant de nouvelles sources", "nombre", ""),
        ("alerte_max_mises_a_jour", "Mises à jour max. par événement", "nombre", ""),
    ]},
    "horaires": {"titre": "Horaires (heure de Paris)", "champs": [
        ("heure_briefing", "Briefing du matin", "heure", ""),
        ("heure_synthese_soir", "Synthèse du soir", "heure", ""),
        ("plage_points", "Plage des points de veille", "plage", "ex. 08:00-22:00"),
        ("intervalle_point_heures", "Un point toutes les (heures)", "nombre", ""),
        ("point_si_rien", "Envoyer un point même sans nouveauté", "oui_non", ""),
        ("heure_journal", "Photo du top pour le Journal", "heure", ""),
        ("journal_taille_top", "Taille du top du Journal", "nombre", ""),
    ]},
    "collecte": {"titre": "Collecte et budget", "champs": [
        ("collecte_active", "Collecte automatique", "oui_non", "Non = pause."),
        ("intervalle_cycle_minutes", "Un cycle toutes les (minutes)", "nombre", ""),
        ("ia_active", "Utiliser l'IA (si disponible)", "oui_non", "Non = règles seules."),
        ("budget_mensuel_eur", "Budget IA en ligne mensuel (€)", "nombre", "Claude / OpenRouter. L'IA locale est gratuite."),
        ("budget_x_eur", "Budget veille X mensuel (€)", "nombre", "Réservé à la phase X (pas encore active)."),
        ("budget_alerte_pct", "Me prévenir à (% du budget)", "nombre", ""),
        ("nom_affiche", "Prénom affiché sur l'accueil", "texte", ""),
    ]},
}

LIMITES = {"intervalle_cycle_minutes": (5, 1440), "intervalle_point_heures": (1, 24), "journal_taille_top": (1, 50),
           "budget_alerte_pct": (1, 100), "alerte_max_mises_a_jour": (0, 20), "budget_mensuel_eur": (0, 1000),
           "budget_x_eur": (0, 1000), "ia_local_timeout_s": (10, 600)}

LIBELLES = {c[0]: c[1] for s in SECTIONS.values() for c in s["champs"]}
LIBELLES["poids_score"] = "Pondération du score"
for _cle, (_v, _desc) in parametres.DEFAUTS.items():
    LIBELLES.setdefault(_cle, _desc)


def lire_formulaire(section: str, form: dict) -> dict:
    """Convertit les champs du formulaire en valeurs (sans ecrire)."""
    vals = {}
    for cle, _lib, typ, _aide in SECTIONS[section]["champs"]:
        brut = form.get(cle)
        if typ == "oui_non":
            vals[cle] = brut in ("on", "1", "true", "oui")
        elif typ == "nombre":
            txt = (brut or "").strip().replace(",", ".")
            try:
                n = float(txt)
            except ValueError:
                raise ValueError(f"{LIBELLES[cle]} : nombre attendu") from None
            vals[cle] = int(n) if n.is_integer() else n
        else:
            vals[cle] = (brut or "").strip()
    return vals


def appliquer(conn: sqlite3.Connection, valeurs: dict, origine: str = "page") -> list[str]:
    """Valide TOUT puis ecrit. Retourne les cles changees ; leve ValueError (rien n'est ecrit)."""
    actuelles = parametres.tous(conn)
    controle = {}
    for cle, v in valeurs.items():
        try:
            controle[cle] = parametres._convertir(cle, v)  # noqa: SLF001 - meme validation que l'API
        except ValueError as e:
            raise ValueError(f"{LIBELLES.get(cle, cle)} : {e}") from None
        if cle in LIMITES and not LIMITES[cle][0] <= controle[cle] <= LIMITES[cle][1]:
            raise ValueError(f"{LIBELLES[cle]} : entre {LIMITES[cle][0]} et {LIMITES[cle][1]}")
    crit = controle.get("seuil_critique", actuelles["seuil_critique"])
    imp = controle.get("seuil_important", actuelles["seuil_important"])
    if imp >= crit:
        raise ValueError("Le seuil « très important » doit être inférieur au seuil critique")
    change = [c for c, v in controle.items() if actuelles.get(c) != v]
    for c in change:
        parametres.modifier(conn, c, controle[c], origine=origine)
    return change


# ------------------------------------------------------------------ ponderation
def lire_poids(form: dict) -> dict:
    poids = {}
    for k in parametres.DEFAUTS["poids_score"][0]:
        try:
            poids[k] = int(float((form.get(f"poids_{k}") or "").replace(",", ".")))
        except ValueError:
            raise ValueError("Chaque poids doit être un nombre entier") from None
        if poids[k] < 0:
            raise ValueError("Un poids ne peut pas être négatif")
    return poids


def apercu_poids(conn: sqlite3.Connection, nouveaux: dict, now: datetime, limite: int = 12) -> list[dict]:
    """Top des 24 h recalcule avec les poids actuels ET les nouveaux, au meme instant."""
    p = parametres.tous(conn)
    p_nouv = {**p, "poids_score": nouveaux}
    lignes = []
    for evt_id in evenements_recents(conn, now, 24):
        evt = conn.execute("SELECT * FROM evenements WHERE id = ?", (evt_id,)).fetchone()
        arts = conn.execute(
            "SELECT a.*, s.niveau, s.categorie, s.fiabilite, s.nom AS source_nom FROM articles a "
            "JOIN sources s ON s.id = a.source_id WHERE a.evenement_id = ?", (evt_id,)).fetchall()
        if not evt or not arts:
            continue
        etat, det = tendance([from_iso(a["publie_le"]) for a in arts], now, p)
        avant, _ = score(evt, arts, etat, det, now, p)
        apres, _ = score(evt, arts, etat, det, now, p_nouv)
        lignes.append({"id": evt_id, "titre": evt["titre"], "avant": avant, "apres": apres, "delta": apres - avant})
    rang_avant = {x["id"]: i for i, x in enumerate(sorted(lignes, key=lambda x: -x["avant"]), 1)}
    lignes.sort(key=lambda x: -x["apres"])
    for i, x in enumerate(lignes, 1):
        x["rang"], x["rang_avant"] = i, rang_avant[x["id"]]
        x["alerte_avant"] = x["avant"] >= p["seuil_critique"]
        x["alerte_apres"] = x["apres"] >= p["seuil_critique"]
    return lignes[:limite]


def enregistrer_poids(conn: sqlite3.Connection, poids: dict, now: datetime, origine: str = "page") -> int:
    """Enregistre la ponderation puis recalcule les evenements des 48 dernieres heures."""
    if parametres.tous(conn)["poids_score"] == poids:
        return 0
    parametres.modifier(conn, "poids_score", poids, origine=origine)  # valide : criteres et total = 100
    ids = evenements_recents(conn, now, 48)
    analyser(conn, ids, now)
    return len(ids)


# ------------------------------------------------------------------ historique
def historique(conn: sqlite3.Connection, limite: int = 40) -> list[dict]:
    out = []
    for r in conn.execute("SELECT * FROM historique_reglages ORDER BY id DESC LIMIT ?", (limite,)):
        lib = LIBELLES.get(r["cle"], r["cle"])
        if r["cle"].startswith("theme:"):
            lib = f"Thème « {r['cle'][6:]} »"
        elif r["cle"].startswith("source:"):
            s = conn.execute("SELECT nom FROM sources WHERE id = ?", (int(r["cle"][7:]),)).fetchone()
            lib = f"Source « {s['nom'] if s else r['cle'][7:]} »"
        out.append({"id": r["id"], "le": r["le"], "cle": r["cle"], "libelle": lib,
                    "ancienne": json.loads(r["ancienne"]) if r["ancienne"] else None,
                    "nouvelle": json.loads(r["nouvelle"]), "origine": r["origine"]})
    return out


def annuler(conn: sqlite3.Connection, hist_id: int, now: datetime) -> str:
    r = conn.execute("SELECT * FROM historique_reglages WHERE id = ?", (hist_id,)).fetchone()
    if r and r["cle"].startswith("theme:"):
        avant = json.loads(r["ancienne"]) if r["ancienne"] else None
        nom = r["cle"][6:]
        if avant is None:  # theme ajoute : on le desactive (jamais de suppression)
            conn.execute("UPDATE themes SET actif = 0 WHERE nom = ?", (nom,))
        else:
            enregistrer_theme(conn, nom, "\n".join(avant["mots"]), avant["actif"], origine="page (annulation)")
        return r["cle"]
    if r and r["cle"].startswith("source:"):
        sid = int(r["cle"][7:])
        avant = json.loads(r["ancienne"]) if r["ancienne"] else None
        if avant is None:  # source ajoutee : desactivee (l'historique de ses articles est conserve)
            conn.execute("UPDATE sources SET actif = 0 WHERE id = ?", (sid,))
        else:
            modifier_source(conn, sid, {k: ("on" if v else "") if k == "actif" else str(v) for k, v in avant.items()},
                            origine="page (annulation)")
        return r["cle"]
    if not r or r["cle"] not in parametres.DEFAUTS:
        raise ValueError("changement introuvable")
    ancienne = json.loads(r["ancienne"]) if r["ancienne"] else parametres.DEFAUTS[r["cle"]][0]
    if r["cle"] == "poids_score":
        enregistrer_poids(conn, ancienne, now, origine="page (annulation)")
    else:
        parametres.modifier(conn, r["cle"], ancienne, origine="page (annulation)")
    return r["cle"]


def remettre_defaut(conn: sqlite3.Connection, cle: str, now: datetime) -> None:
    if cle not in parametres.DEFAUTS:
        raise ValueError("réglage inconnu")
    if cle == "poids_score":
        enregistrer_poids(conn, parametres.DEFAUTS[cle][0], now, origine="page (défaut)")
    else:
        parametres.modifier(conn, cle, parametres.DEFAUTS[cle][0], origine="page (défaut)")


def valeur_lisible(v) -> str:
    if isinstance(v, bool):
        return "oui" if v else "non"
    if isinstance(v, dict) and "mots" in v:
        return ("actif" if v.get("actif") else "désactivé") + " · " + valeur_lisible(v["mots"])
    if isinstance(v, dict) and "ajout" in v:
        return f"ajout de {v['ajout']}"
    if isinstance(v, dict) and "frequence_minutes" in v:
        return (f"{'active' if v['actif'] else 'désactivée'} · fiabilité {v['fiabilite']}/5 · priorité {v['priorite']} · "
                f"toutes les {v['frequence_minutes']} min")
    if isinstance(v, dict):
        return " · ".join(f"{k} {x}" for k, x in v.items())
    if isinstance(v, list):
        return ", ".join(map(str, v[:8])) + (f" … (+{len(v) - 8})" if len(v) > 8 else "")
    return str(v)


# ------------------------------------------------------------------ listes, themes, sources (1b)
LISTES = [
    ("personnalites_suivies", "Personnalités suivies", "Noms de responsables publics : ils comptent comme acteurs."),
    ("mots_exclus", "Mots exclus", "Un article qui contient l'un de ces mots est écarté."),
    ("zone_regionale_mots", "Mots régionaux", "Un article qui en contient un passe en zone Lyon/AURA."),
    ("mots_impact", "Mots à fort impact", "Augmentent le critère « impact potentiel » du score."),
    ("acteurs_politiques", "Partis et acteurs locaux", "Comptent comme acteurs politiques."),
]
for _c, _l, _a in LISTES:
    LIBELLES[_c] = _l


def lire_liste(texte: str, max_elements: int = 300) -> list[str]:
    """Une entree par ligne (ou separee par des virgules), sans doublons ni vides."""
    morceaux = [m.strip() for ligne in (texte or "").splitlines() for m in ligne.split(",")]
    vus, out = set(), []
    for m in morceaux:
        if not m:
            continue
        if len(m) > 80:
            raise ValueError(f"« {m[:30]}… » : 80 caractères maximum par entrée")
        if m.lower() not in vus:
            vus.add(m.lower())
            out.append(m)
    if len(out) > max_elements:
        raise ValueError(f"{max_elements} entrées maximum")
    return out


def enregistrer_listes(conn: sqlite3.Connection, form: dict, origine: str = "page") -> list[str]:
    valeurs = {}
    for cle, lib, _aide in LISTES:
        try:
            valeurs[cle] = lire_liste(form.get(cle, ""))
        except ValueError as e:
            raise ValueError(f"{lib} : {e}") from None
    actuelles = parametres.tous(conn)
    change = [c for c, v in valeurs.items() if actuelles[c] != v]
    for c in change:
        parametres.modifier(conn, c, valeurs[c], origine=origine)
    return change


def _historiser(conn: sqlite3.Connection, cle: str, ancienne, nouvelle, origine: str) -> None:
    if ancienne != nouvelle:
        conn.execute("INSERT INTO historique_reglages (le, cle, ancienne, nouvelle, origine) VALUES (?,?,?,?,?)",
                     (to_iso(utcnow()), cle, json.dumps(ancienne, ensure_ascii=False) if ancienne is not None else None,
                      json.dumps(nouvelle, ensure_ascii=False), origine))


def themes(conn: sqlite3.Connection) -> list[dict]:
    return [{"nom": r["nom"], "mots": json.loads(r["mots_cles"]), "actif": bool(r["actif"]),
             "defaut": r["nom"] in parametres.THEMES_DEFAUT}
            for r in conn.execute("SELECT * FROM themes ORDER BY nom")]


def enregistrer_theme(conn: sqlite3.Connection, nom: str, mots_txt: str, actif: bool, nouveau: bool = False,
                      origine: str = "page") -> None:
    nom = (nom or "").strip()
    if not 2 <= len(nom) <= 40:
        raise ValueError("nom de thème : 2 à 40 caractères")
    mots = lire_liste(mots_txt, 200)
    if not mots:
        raise ValueError(f"thème « {nom} » : au moins un mot-clé")
    r = conn.execute("SELECT * FROM themes WHERE nom = ?", (nom,)).fetchone()
    if nouveau and r:
        raise ValueError(f"le thème « {nom} » existe déjà")
    if not nouveau and not r:
        raise ValueError("thème introuvable")
    avant = {"mots": json.loads(r["mots_cles"]), "actif": bool(r["actif"])} if r else None
    apres = {"mots": mots, "actif": bool(actif)}
    conn.execute("INSERT INTO themes (nom, mots_cles, actif) VALUES (?,?,?) ON CONFLICT(nom) DO UPDATE "
                 "SET mots_cles = excluded.mots_cles, actif = excluded.actif",
                 (nom, json.dumps(mots, ensure_ascii=False), int(bool(actif))))
    _historiser(conn, f"theme:{nom}", avant, apres, origine)


SOURCE_CHAMPS = ("actif", "fiabilite", "priorite", "frequence_minutes")


def modifier_source(conn: sqlite3.Connection, source_id: int, form: dict, origine: str = "page") -> bool:
    r = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    if not r:
        raise ValueError("source introuvable")
    try:
        apres = {"actif": form.get("actif") in ("on", "1"), "fiabilite": int(form.get("fiabilite", "")),
                 "priorite": int(form.get("priorite", "")), "frequence_minutes": int(form.get("frequence_minutes", ""))}
    except ValueError:
        raise ValueError(f"{r['nom']} : nombres attendus") from None
    if not (1 <= apres["fiabilite"] <= 5 and 1 <= apres["priorite"] <= 3 and 5 <= apres["frequence_minutes"] <= 1440):
        raise ValueError(f"{r['nom']} : fiabilité 1 à 5, priorité 1 à 3, fréquence 5 à 1440 min")
    avant = {"actif": bool(r["actif"]), "fiabilite": r["fiabilite"], "priorite": r["priorite"],
             "frequence_minutes": r["frequence_minutes"]}
    if avant == apres:
        return False
    conn.execute("UPDATE sources SET actif = ?, fiabilite = ?, priorite = ?, frequence_minutes = ?, maj_le = ? "
                 "WHERE id = ?", (int(apres["actif"]), apres["fiabilite"], apres["priorite"],
                                  apres["frequence_minutes"], to_iso(utcnow()), source_id))
    _historiser(conn, f"source:{source_id}", avant, apres, origine)
    return True


def adresse_publique(url: str, resoudre=None) -> None:
    """Refuse une adresse qui viserait le serveur lui-meme ou un reseau prive (VPN, maison...)."""
    import ipaddress
    import socket
    from urllib.parse import urlsplit

    u = urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password:
        raise ValueError("adresse http(s) complète attendue")
    resoudre = resoudre or (lambda h: {ai[4][0] for ai in socket.getaddrinfo(h, None)})
    try:
        ips = resoudre(u.hostname)
    except OSError:
        raise ValueError(f"adresse introuvable : {u.hostname}") from None
    for ip in ips:
        a = ipaddress.ip_address(ip.split("%")[0])
        if not a.is_global:
            raise ValueError("adresse privée ou locale refusée (protection du serveur)")


def ajouter_source(conn: sqlite3.Connection, form: dict, resoudre=None, origine: str = "page") -> int:
    from pydantic import ValidationError

    from app.sources import SourceIn

    try:
        s = SourceIn(nom=(form.get("nom") or "").strip(), url=(form.get("url") or "").strip(), type="rss",
                     categorie=form.get("categorie", ""), niveau=int(form.get("niveau") or 0),
                     zone=form.get("zone", ""), fiabilite=int(form.get("fiabilite") or 0), priorite=2,
                     frequence_minutes=int(form.get("frequence_minutes") or 0), actif=1,
                     note=f"ajoutée depuis la page Réglages le {utcnow():%d/%m/%Y}")
    except (ValidationError, ValueError):
        raise ValueError("nouvelle source : nom, adresse, catégorie, niveau 1-4, zone, fiabilité 1-5, "
                         "fréquence ≥ 5 min") from None
    adresse_publique(str(s.url), resoudre)
    cur = conn.execute(
        "INSERT OR IGNORE INTO sources (nom, url, type, categorie, niveau, zone, fiabilite, priorite, "
        "frequence_minutes, actif, note) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (s.nom, str(s.url), s.type, s.categorie, s.niveau, s.zone, s.fiabilite, s.priorite, s.frequence_minutes,
         s.actif, s.note))
    if not cur.rowcount:
        raise ValueError("cette adresse est déjà dans tes sources")
    _historiser(conn, f"source:{cur.lastrowid}", None, {"ajout": s.nom, "url": str(s.url)}, origine)
    return cur.lastrowid


# ------------------------------------------------------------------ IA (onglet Modele)
AGENTS_IA = {"classification": "Classement des articles", "synthese": "Résumés des synthèses",
             "question": "Réponses aux questions"}
for _c in ("ia_local_url", "ia_routage", "ia_local_timeout_s"):
    LIBELLES[_c] = {"ia_local_url": "Adresse de l'IA locale", "ia_routage": "Modèles par agent",
                    "ia_local_timeout_s": "Délai max. de l'IA locale"}[_c]


def enregistrer_ia(conn: sqlite3.Connection, form: dict, origine: str = "page") -> list[str]:
    routage = {}
    for agent in AGENTS_IA:
        entrees = [e.strip() for e in (form.get(f"routage_{agent}") or "").replace("\n", ",").split(",") if e.strip()]
        routage[agent] = entrees
    valeurs = {"ia_active": form.get("ia_active") in ("on", "1"), "ia_local_url": (form.get("ia_local_url") or "").strip(),
               "ia_routage": routage}
    try:
        valeurs["ia_local_timeout_s"] = int(float(form.get("ia_local_timeout_s") or "0"))
    except ValueError:
        raise ValueError("Délai : nombre de secondes attendu") from None
    return appliquer(conn, valeurs, origine)
