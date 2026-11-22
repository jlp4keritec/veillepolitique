"""Regles de J (F11) : valeurs par defaut, lecture, modification validee.

Toutes ces valeurs sont des DEFAUTS. J les modifie (API ou Telegram /param).
Le seed n'ecrase jamais une valeur deja modifiee.
"""

import json
import sqlite3
from typing import Any

from app.util import to_iso, utcnow

# cle -> (valeur par defaut, description)
DEFAUTS: dict[str, tuple[Any, str]] = {
    # --- Collecte (F01) ---
    "collecte_active": (True, "Collecte automatique active (false = pause)"),
    "intervalle_cycle_minutes": (5, "Frequence du cycle de traitement (minutes)"),
    "taille_max_flux_ko": (5000, "Taille maximale d'un flux telecharge (Ko)"),
    "extrait_max_caracteres": (1000, "Longueur maximale de l'extrait stocke par article"),
    # --- Filtrage (F02) ---
    "mots_exclus": ([], "Mots-cles : un article qui les contient est ecarte"),
    "titre_mots_min": (3, "Titre plus court = page sujet d'un media, ecartee"),
    "type_depuis_resume": (False, "Deduire le type d'evenement aussi depuis le resume (sinon titre seul)"),
    "zone_regionale_mots": ([
        "lyon", "lyonnais", "lyonnaise", "villeurbanne", "metropole de lyon", "grand lyon",
        "rhone", "auvergne-rhone-alpes", "auvergne rhone alpes", "grenoble",
        "saint-etienne", "clermont-ferrand", "annecy", "isere", "savoie", "haute-savoie",
        "drome", "ardeche", "puy-de-dome", "cantal", "haute-loire", "bron", "venissieux", "vaulx-en-velin", "caluire",
    ], "Mots qui classent un article en zone regionale"),
    "acteurs_institutionnels": ([
        "president de la republique", "elysee", "premier ministre", "matignon",
        "gouvernement", "assemblee nationale", "senat", "conseil constitutionnel",
        "conseil d etat", "ministre", "ministere", "depute", "deputes", "senateur", "senateurs",
    ], "Acteurs institutionnels nationaux (poids fort)"),
    "acteurs_politiques": ([
        "renaissance", "rassemblement national", "la france insoumise", "lfi",
        "les republicains", "parti socialiste", "les ecologistes", "eelv", "modem",
        "horizons", "parti communiste", "reconquete",
        "metropole de lyon", "ville de lyon", "maire de lyon", "region auvergne-rhone-alpes",
        "conseil regional", "conseil municipal", "prefet", "prefecture",
    ], "Partis et acteurs publics locaux"),
    "personnalites_suivies": ([], "Noms de responsables publics a suivre (a remplir par J)"),
    # --- Classification ---
    "types_evenement_mots": ({
        "démission": ["demission", "demissionne", "quitte ses fonctions"],
        "nomination": ["nomme", "nommee", "nomination"],
        "vote": ["vote", "adopte", "adoptee", "rejete", "rejetee", "scrutin"],
        "réforme": ["reforme"],
        "décision": ["decide", "decision", "decret", "arrete prefectoral", "tranche"],
        "crise": ["crise", "motion de censure", "dissolution", "49.3", "censure"],
        "controverse": ["polemique", "controverse", "tolle", "scandale"],
        "enquête": ["enquete", "perquisition", "mis en examen", "garde a vue"],
        "manifestation": ["manifestation", "manifestants", "greve", "mobilisation"],
        "proposition": ["proposition de loi", "propose", "projet de loi"],
        "annonce": ["annonce", "annoncent"],
        "publication de rapport": ["rapport"],
        "interview": ["interview", "entretien"],
        "débat": ["debat"],
        "réaction": ["reagit", "reaction", "repond", "denonce"],
        "déclaration": ["declare", "affirme", "estime", "assure", "declaration"],
    }, "Mots-cles par type d'evenement (ordre = priorite)"),
    "mots_impact": ([
        "dissolution", "motion de censure", "49.3", "remaniement", "referendum",
        "etat d urgence", "attentat", "loi de finances", "budget", "demission du gouvernement",
        "conseil constitutionnel", "elections", "cohabitation",
    ], "Mots signalant un impact potentiel fort"),
    "marqueurs_declaration": (["selon", "affirme", "declare", "estime", "assure", "a dit"],
                              "Marqueurs d'une declaration rapportee"),
    "marqueurs_rumeur": (["rumeur", "rumeurs", "serait", "aurait", "pourrait", "selon nos informations",
                          "non confirme", "pas confirme", "selon des sources"],
                         "Marqueurs d'une information a confirmer, cherches dans le TITRE"),
    "marqueurs_rumeur_texte": (["rumeur", "rumeurs", "non confirme", "non confirmee", "pas confirme",
                                "pas encore confirme", "selon nos informations"],
                               "Marqueurs explicites cherches dans le RESUME"),
    # --- Deduplication / regroupement (F03) ---
    "fenetre_regroupement_heures": (48, "Fenetre de recherche d'un evenement existant (heures)"),
    "seuil_similarite_titre": (83, "Similarite minimale des titres pour regrouper (0-100)"),
    "mots_communs_min": (2, "Nombre minimal de mots significatifs communs pour regrouper"),
    "mot_rare_frequence_max": (10, "Un nom propre cite dans au plus N titres (48 h) est 'rare'"),
    "mot_rare_similarite_min": (35, "Similarite minimale si deux titres partagent un nom propre rare"),
    "mot_rare_mots_communs_min": (3, "Mots importants communs requis en plus du nom propre rare"),
    # --- Tendances ---
    "tendance_fenetre_minutes": (60, "Fenetre principale de calcul de tendance (minutes)"),
    "tendance_fenetres_minutes": ([15, 60, 1440], "Fenetres comparees (cahier 5.4)"),
    "tendance_ratio_hausse": (1.5, "Ratio courant/precedent pour 'en hausse'"),
    "tendance_ratio_forte_hausse": (3.0, "Ratio courant/precedent pour 'forte hausse'"),
    "tendance_ratio_baisse": (0.5, "Ratio courant/precedent pour 'en baisse'"),
    # --- Scoring (F04) ---
    "poids_score": ({
        "institutionnel": 25, "nouveaute": 20, "acceleration": 20,
        "sources": 15, "impact": 15, "pertinence": 5,
    }, "Ponderation du score sur 100 (cahier F04)"),
    "seuil_critique": (85, "Score a partir duquel une alerte critique part"),
    "seuil_important": (70, "Score 'tres important'"),
    # --- Alertes (F05) ---
    "alertes_actives": (True, "Envoi des alertes critiques"),
    "alerte_delta_score": (10, "Hausse de score qui justifie une mise a jour d'alerte"),
    "alerte_delta_sources": (2, "Nouvelles sources qui justifient une mise a jour d'alerte"),
    "alerte_max_mises_a_jour": (3, "Nombre maximal de mises a jour par evenement"),
    "alerte_fiabilite_min": (4, "Fiabilite min. d'une source unique pour alerter"),
    # --- Syntheses (F06-F08) ---
    "heure_briefing": ("08:00", "Heure du briefing matinal (Paris)"),
    "heure_synthese_soir": ("20:00", "Heure de la synthese du soir (Paris)"),
    "intervalle_point_heures": (2, "Intervalle entre deux points de veille (heures)"),
    "plage_points": ("08:00-22:00", "Plage horaire des points de veille (Paris)"),
    "point_si_rien": (False, "Envoyer un point meme sans nouveaute"),
    # --- IA et couts (F12) ---
    "ia_active": (True, "Utiliser Claude (si cle API presente et budget disponible)"),
    "modele_ia": ("claude-haiku-5-5", "Modele Claude utilise"),
    "prix_entree_usd_mtok": (0.10, "Prix entree USD / million de tokens (a verifier)"),
    "prix_sortie_usd_mtok": (0.50, "Prix sortie USD / million de tokens (a verifier)"),
    "taux_usd_eur": (0.87, "Taux de conversion USD -> EUR (a ajuster)"),
    "budget_mensuel_eur": (50.0, "Plafond mensuel d'appels IA (EUR)"),
    "budget_alerte_pct": (80, "Alerte Telegram a ce pourcentage du budget"),
    "ia_max_articles_par_cycle": (20, "Articles envoyes a Claude par cycle (maximum)"),
}

THEMES_DEFAUT: dict[str, list[str]] = {
    "Institutions": ["constitution", "constitutionnel", "institutions", "motion de censure",
                     "dissolution", "49.3", "remaniement", "referendum", "cohabitation"],
    "Élections": ["election", "elections", "municipales", "legislatives", "presidentielle",
                  "regionales", "europeennes", "sondage", "candidat", "candidate", "scrutin"],
    "Économie": ["economie", "croissance", "inflation", "entreprises", "industrie", "deficit", "dette"],
    "Fiscalité": ["impot", "impots", "fiscalite", "taxe", "tva", "loi de finances", "budget"],
    "Pouvoir d'achat": ["pouvoir d achat", "prix", "salaires", "smic", "carburant"],
    "Emploi": ["emploi", "chomage", "travail", "france travail"],
    "Immigration": ["immigration", "migrants", "asile", "titre de sejour", "frontieres"],
    "Sécurité": ["securite", "police", "gendarmerie", "delinquance", "violences", "attentat"],
    "Justice": ["justice", "tribunal", "proces", "magistrat", "condamne", "mis en examen"],
    "Éducation": ["education", "ecole", "college", "lycee", "enseignants", "universite"],
    "Santé": ["sante", "hopital", "medecins", "securite sociale", "assurance maladie"],
    "Retraites": ["retraite", "retraites", "pension", "pensions"],
    "Environnement": ["environnement", "climat", "ecologie", "pollution", "biodiversite"],
    "Énergie": ["energie", "electricite", "nucleaire", "gaz", "renouvelables"],
    "Agriculture": ["agriculture", "agriculteurs", "agricole", "pac", "eleveurs"],
    "Défense": ["defense", "armee", "militaire", "armees"],
    "Europe": ["europe", "europeen", "europeenne", "union europeenne", "bruxelles", "commission europeenne"],
    "Laïcité": ["laicite", "religion", "voile", "culte"],
    "Transports": ["transports", "sncf", "tcl", "metro", "tramway", "train", "autoroute", "zfe"],
    "Logement": ["logement", "loyers", "hlm", "immobilier", "logements"],
    "International": ["international", "diplomatie", "ukraine", "russie", "etats-unis", "chine",
                      "israel", "gaza", "otan", "onu", "bresil", "argentine", "mexique", "canada",
                      "royaume-uni", "allemagne", "italie", "espagne", "belgique", "pologne", "hongrie",
                      "turquie", "iran", "inde", "japon", "coree", "syrie", "liban", "venezuela",
                      "algerie", "maroc", "tunisie", "senegal", "mali", "maison blanche", "kremlin"],
}


# Mises a jour de themes par defaut : appliquees SEULEMENT si J n'a pas modifie le theme.
THEMES_MAJ: dict[str, list[list[str]]] = {
    "International": [["international", "diplomatie", "ukraine", "russie", "etats-unis", "chine",
                       "israel", "gaza", "otan", "onu"]],
}


# Nouvelles valeurs par defaut : appliquees SEULEMENT si J a garde l'ancienne valeur.
PARAMS_MAJ: dict[str, list] = {
    "seuil_similarite_titre": [68],  # v0.2.2 : changement de methode de comparaison
}


def seed_parametres(conn: sqlite3.Connection) -> int:
    n = 0
    for cle, anciennes in PARAMS_MAJ.items():
        r = conn.execute("SELECT valeur FROM parametres WHERE cle = ?", (cle,)).fetchone()
        if r and json.loads(r["valeur"]) in anciennes:
            conn.execute("UPDATE parametres SET valeur = ? WHERE cle = ?", (json.dumps(DEFAUTS[cle][0]), cle))
    for cle, (val, desc) in DEFAUTS.items():
        cur = conn.execute(
            "INSERT OR IGNORE INTO parametres (cle, valeur, description) VALUES (?,?,?)",
            (cle, json.dumps(val, ensure_ascii=False), desc),
        )
        n += cur.rowcount
    for nom, mots in THEMES_DEFAUT.items():
        conn.execute("INSERT OR IGNORE INTO themes (nom, mots_cles) VALUES (?,?)",
                     (nom, json.dumps(mots, ensure_ascii=False)))
    for nom, anciennes in THEMES_MAJ.items():
        r = conn.execute("SELECT mots_cles FROM themes WHERE nom = ?", (nom,)).fetchone()
        if r and json.loads(r["mots_cles"]) in anciennes:
            conn.execute("UPDATE themes SET mots_cles = ? WHERE nom = ?",
                         (json.dumps(THEMES_DEFAUT[nom], ensure_ascii=False), nom))
    return n


def tous(conn: sqlite3.Connection) -> dict[str, Any]:
    vals = {k: v for k, (v, _) in DEFAUTS.items()}
    for r in conn.execute("SELECT cle, valeur FROM parametres"):
        if r["cle"] in vals:
            vals[r["cle"]] = json.loads(r["valeur"])
    return vals


def lire(conn: sqlite3.Connection, cle: str) -> Any:
    if cle not in DEFAUTS:
        raise KeyError(cle)
    r = conn.execute("SELECT valeur FROM parametres WHERE cle = ?", (cle,)).fetchone()
    return json.loads(r["valeur"]) if r else DEFAUTS[cle][0]


def _convertir(cle: str, valeur: Any) -> Any:
    """Valide la nouvelle valeur selon le type de la valeur par defaut."""
    defaut = DEFAUTS[cle][0]
    if isinstance(valeur, str) and not isinstance(defaut, str):
        txt = valeur.strip()
        if isinstance(defaut, bool):
            if txt.lower() in ("true", "vrai", "oui", "on", "1"):
                return True
            if txt.lower() in ("false", "faux", "non", "off", "0"):
                return False
            raise ValueError("valeur attendue : oui / non")
        try:
            valeur = json.loads(txt)
        except json.JSONDecodeError as e:
            raise ValueError(f"valeur illisible : {txt}") from e
    if isinstance(defaut, bool):
        if not isinstance(valeur, bool):
            raise ValueError("valeur attendue : oui / non")
    elif isinstance(defaut, (int, float)):
        if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
            raise ValueError("valeur numerique attendue")
        if valeur < 0:
            raise ValueError("valeur positive attendue")
        valeur = int(valeur) if isinstance(defaut, int) and float(valeur).is_integer() else valeur
    elif isinstance(defaut, str):
        if not isinstance(valeur, str):
            raise ValueError("texte attendu")
    elif isinstance(defaut, list):
        if not isinstance(valeur, list):
            raise ValueError("liste attendue, ex. [\"a\", \"b\"]")
    elif isinstance(defaut, dict):
        if not isinstance(valeur, dict):
            raise ValueError("objet attendu")
    if cle.startswith("heure_"):
        _verifier_heure(valeur)
    if cle == "plage_points":
        debut, _, fin = valeur.partition("-")
        _verifier_heure(debut)
        _verifier_heure(fin)
    if cle in ("seuil_critique", "seuil_important", "seuil_similarite_titre") and valeur > 100:
        raise ValueError("valeur entre 0 et 100")
    if cle == "poids_score":
        attendues = set(DEFAUTS["poids_score"][0])
        if set(valeur) != attendues or sum(valeur.values()) != 100:
            raise ValueError(f"criteres {sorted(attendues)} et total = 100")
    return valeur


def _verifier_heure(h: str) -> None:
    hh, _, mm = h.partition(":")
    if not (hh.isdigit() and mm.isdigit() and 0 <= int(hh) < 24 and 0 <= int(mm) < 60):
        raise ValueError("heure attendue au format HH:MM")


def modifier(conn: sqlite3.Connection, cle: str, valeur: Any) -> Any:
    if cle not in DEFAUTS:
        raise KeyError(cle)
    v = _convertir(cle, valeur)
    conn.execute(
        "INSERT INTO parametres (cle, valeur, description, maj_le) VALUES (?,?,?,?) "
        "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur, maj_le = excluded.maj_le",
        (cle, json.dumps(v, ensure_ascii=False), DEFAUTS[cle][1], to_iso(utcnow())),
    )
    return v


def themes_actifs(conn: sqlite3.Connection) -> dict[str, list[str]]:
    return {r["nom"]: json.loads(r["mots_cles"])
            for r in conn.execute("SELECT nom, mots_cles FROM themes WHERE actif = 1")}
