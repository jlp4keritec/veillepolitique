"""Registre des sources (cahier 4.2) : modele, seed idempotent, lecture."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

from app.db import session

DEFAUT_PATH = Path(__file__).resolve().parent / "data" / "sources_defaut.json"


class SourceIn(BaseModel):
    nom: str = Field(min_length=1, max_length=200)
    url: HttpUrl
    type: Literal["rss", "api", "site", "x"]
    categorie: Literal["institutionnel", "media", "reseau_social", "complement"]
    niveau: int = Field(ge=1, le=4)
    zone: Literal["national", "regional"]
    fiabilite: int = Field(default=3, ge=1, le=5)
    priorite: int = Field(default=2, ge=1, le=3)
    frequence_minutes: int = Field(ge=5)
    actif: int = Field(default=1, ge=0, le=1)
    note: str | None = None


def charger_defaut(path: Path = DEFAUT_PATH) -> list[SourceIn]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [SourceIn.model_validate(s) for s in data["sources"]]


def seed_sources(db_path: Path, sources: list[SourceIn] | None = None) -> int:
    """Ajoute les sources absentes (cle = URL). N'ecrase jamais une source existante.

    Retourne le nombre de sources ajoutees.
    """
    sources = sources if sources is not None else charger_defaut()
    ajoutees = 0
    with session(db_path) as conn:
        for s in sources:
            cur = conn.execute(
                """INSERT OR IGNORE INTO sources
                   (nom, url, type, categorie, niveau, zone, fiabilite, priorite,
                    frequence_minutes, actif, note)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (s.nom, str(s.url), s.type, s.categorie, s.niveau, s.zone,
                 s.fiabilite, s.priorite, s.frequence_minutes, s.actif, s.note),
            )
            ajoutees += cur.rowcount
    return ajoutees


def lister_sources(db_path: Path) -> list[dict]:
    with session(db_path) as conn:
        rows = conn.execute("SELECT * FROM sources ORDER BY niveau, zone, nom").fetchall()
    return [dict(r) for r in rows]
