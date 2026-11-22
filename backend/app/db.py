"""Base SQLite : schema, migrations douces et acces.

Les migrations n'effacent jamais de donnees : CREATE TABLE IF NOT EXISTS
et ajout de colonnes manquantes uniquement.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    nom               TEXT    NOT NULL,
    url               TEXT    NOT NULL UNIQUE,
    type              TEXT    NOT NULL CHECK (type IN ('rss','api','site','x')),
    categorie         TEXT    NOT NULL CHECK (categorie IN ('institutionnel','media','reseau_social','complement')),
    niveau            INTEGER NOT NULL CHECK (niveau BETWEEN 1 AND 4),
    zone              TEXT    NOT NULL CHECK (zone IN ('national','regional')),
    fiabilite         INTEGER NOT NULL DEFAULT 3 CHECK (fiabilite BETWEEN 1 AND 5),
    priorite          INTEGER NOT NULL DEFAULT 2 CHECK (priorite BETWEEN 1 AND 3),
    frequence_minutes INTEGER NOT NULL CHECK (frequence_minutes >= 5),
    actif             INTEGER NOT NULL DEFAULT 1 CHECK (actif IN (0,1)),
    url_verifiee      INTEGER NOT NULL DEFAULT 0 CHECK (url_verifiee IN (0,1)),
    note              TEXT,
    derniere_collecte TEXT,
    derniere_erreur   TEXT,
    cree_le           TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    maj_le            TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS parametres (
    cle         TEXT PRIMARY KEY,
    valeur      TEXT NOT NULL,          -- JSON
    description TEXT NOT NULL,
    maj_le      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS themes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    nom       TEXT NOT NULL UNIQUE,
    mots_cles TEXT NOT NULL,            -- JSON liste
    actif     INTEGER NOT NULL DEFAULT 1 CHECK (actif IN (0,1))
);

CREATE TABLE IF NOT EXISTS evenements (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    titre                TEXT NOT NULL,
    titre_norm           TEXT NOT NULL,
    premier_article_le   TEXT NOT NULL,
    dernier_article_le   TEXT NOT NULL,
    nb_articles          INTEGER NOT NULL DEFAULT 0,
    nb_sources           INTEGER NOT NULL DEFAULT 0,
    theme                TEXT,
    themes               TEXT NOT NULL DEFAULT '[]',
    zone                 TEXT,
    acteurs              TEXT NOT NULL DEFAULT '[]',
    type_evenement       TEXT,
    score                INTEGER NOT NULL DEFAULT 0,
    score_details        TEXT NOT NULL DEFAULT '{}',
    tendance             TEXT NOT NULL DEFAULT 'nouveau',
    tendance_details     TEXT NOT NULL DEFAULT '{}',
    verification         TEXT NOT NULL DEFAULT 'non vérifié',
    verification_details TEXT NOT NULL DEFAULT '{}',
    resume_ia            TEXT,
    notifie              INTEGER NOT NULL DEFAULT 0,
    cree_le              TEXT NOT NULL,
    maj_le               TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_evt_dernier ON evenements(dernier_article_le);

CREATE TABLE IF NOT EXISTS articles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       INTEGER NOT NULL REFERENCES sources(id),
    url             TEXT NOT NULL UNIQUE,
    guid            TEXT,
    titre           TEXT NOT NULL,
    titre_norm      TEXT NOT NULL,
    texte_extrait   TEXT NOT NULL DEFAULT '',
    texte_norm      TEXT NOT NULL DEFAULT '',
    auteur          TEXT,
    publie_le       TEXT NOT NULL,
    collecte_le     TEXT NOT NULL,
    pertinent       INTEGER,            -- NULL = pas encore filtre
    raison_filtre   TEXT,
    theme           TEXT,
    themes          TEXT NOT NULL DEFAULT '[]',
    zone            TEXT,
    acteurs         TEXT NOT NULL DEFAULT '[]',
    type_evenement  TEXT,
    classif_par     TEXT,               -- 'regles' ou 'regles+ia'
    resume_ia       TEXT,
    ia_traite       INTEGER NOT NULL DEFAULT 0,
    evenement_id    INTEGER REFERENCES evenements(id),
    historique      TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS ix_art_publie ON articles(publie_le);
CREATE INDEX IF NOT EXISTS ix_art_evt ON articles(evenement_id);
CREATE INDEX IF NOT EXISTS ix_art_guid ON articles(source_id, guid);

CREATE TABLE IF NOT EXISTS notifications (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    type             TEXT NOT NULL,     -- alerte, point, briefing, synthese, reponse, systeme
    cle_unique       TEXT NOT NULL UNIQUE,
    evenement_id     INTEGER REFERENCES evenements(id),
    score_envoye     INTEGER,
    nb_sources_envoye INTEGER,
    contenu          TEXT NOT NULL,
    statut           TEXT NOT NULL,     -- envoye, simule, echec
    erreur           TEXT,
    tentatives       INTEGER NOT NULL DEFAULT 1,
    envoye_le        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS couts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    horodatage TEXT NOT NULL,
    agent      TEXT NOT NULL,
    modele     TEXT NOT NULL,
    tokens_in  INTEGER NOT NULL,
    tokens_out INTEGER NOT NULL,
    cout_eur   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS journal (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    horodatage TEXT NOT NULL,
    niveau     TEXT NOT NULL,
    composant  TEXT NOT NULL,
    message    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS etat (
    cle    TEXT PRIMARY KEY,
    valeur TEXT NOT NULL
);
"""

# Colonnes ajoutees apres la v0.1.0 (table, colonne, definition)
COLONNES_AJOUTEES = [
    ("sources", "etag", "TEXT"),
    ("sources", "last_modified", "TEXT"),
    ("sources", "erreurs_consecutives", "INTEGER NOT NULL DEFAULT 0"),
    ("articles", "acteurs_titre", "TEXT NOT NULL DEFAULT '[]'"),
    ("evenements", "acteurs_titre", "TEXT NOT NULL DEFAULT '[]'"),
]


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def session(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema(db_path: Path) -> None:
    with session(db_path) as conn:
        conn.executescript(SCHEMA)
        for table, col, definition in COLONNES_AJOUTEES:
            existantes = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            if col not in existantes:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")


def get_etat(conn: sqlite3.Connection, cle: str, defaut: str | None = None) -> str | None:
    r = conn.execute("SELECT valeur FROM etat WHERE cle = ?", (cle,)).fetchone()
    return r["valeur"] if r else defaut


def set_etat(conn: sqlite3.Connection, cle: str, valeur: str) -> None:
    conn.execute(
        "INSERT INTO etat (cle, valeur) VALUES (?, ?) "
        "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur",
        (cle, valeur),
    )
