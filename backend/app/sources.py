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


# Sources "a identifier" des versions precedentes dont le flux a ete trouve : mises a jour
# SEULEMENT si J ne les a pas modifiees (toujours inactives, type site, meme adresse).
SOURCES_MAJ: dict[str, str] = {
    "https://www.leprogres.fr/": "https://www.leprogres.fr/rss",
    "https://www.senat.fr/": "https://www.senat.fr/rss/presse.rss",
    # 23/11/2026 : flux officiels verifies par J et Claude
    "https://www.info.gouv.fr/": "https://www.info.gouv.fr/rss/actualites.xml",
    "https://www.assemblee-nationale.fr/": "https://www2.assemblee-nationale.fr/feeds/detail/crs",
    "https://www.grandlyon.com/": "https://www.grandlyon.com/actualites.xml",
    # 23/11/2026 : pas de flux, lecteur de page (app/lecteurs.py)
    "https://www.elysee.fr/": "https://www.elysee.fr/toutes-les-actualites",
}


def _maj_sources_trouvees(conn, sources: list[SourceIn]) -> None:
    par_url = {str(s.url): s for s in sources}
    for ancienne, nouvelle in SOURCES_MAJ.items():
        s = par_url.get(nouvelle)
        if not s or conn.execute("SELECT 1 FROM sources WHERE url = ?", (nouvelle,)).fetchone():
            continue
        conn.execute(
            "UPDATE sources SET nom = ?, url = ?, type = ?, actif = ?, note = ?, frequence_minutes = ? "
            "WHERE url = ? AND actif = 0 AND type = 'site'",
            (s.nom, nouvelle, s.type, s.actif, s.note, s.frequence_minutes, ancienne))


def seed_sources(db_path: Path, sources: list[SourceIn] | None = None) -> int:
    """Ajoute les sources absentes (cle = URL). N'ecrase jamais une source existante.

    Retourne le nombre de sources ajoutees.
    """
    sources = sources if sources is not None else charger_defaut()
    ajoutees = 0
    with session(db_path) as conn:
        _maj_sources_trouvees(conn, sources)
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
