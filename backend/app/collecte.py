"""Agent de collecte (F01) : recupere les flux RSS des sources actives et dues.

- Respecte la frequence de chaque source et les en-tetes ETag / Last-Modified.
- Taille de flux limitee, delai d'attente court.
- Une source en erreur n'arrete pas les autres ; nouvelle tentative avec
  delai croissant (frequence x 2^erreurs, plafond 4 h).
- Stocke seulement titre, lien, date, auteur et un extrait court (droits des medias).
"""

import calendar
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import feedparser
import httpx

from app import __version__
from app.journal import ecrire
from app.parametres import lire
from app.util import empreinte, from_iso, nettoyer_html, normaliser, to_iso, url_canonique

USER_AGENT = f"VEILLE/{__version__} (veille personnelle, lecture RSS)"
DELAI_MAX_MINUTES = 240


@dataclass
class ResultatCollecte:
    sources_traitees: int = 0
    sources_en_erreur: int = 0
    articles_nouveaux: int = 0
    erreurs: list[str] = field(default_factory=list)


def sources_dues(conn: sqlite3.Connection, now: datetime) -> list[sqlite3.Row]:
    dues = []
    for s in conn.execute("SELECT * FROM sources WHERE actif = 1 AND type = 'rss' ORDER BY priorite"):
        if not s["derniere_collecte"]:
            dues.append(s)
            continue
        attente = s["frequence_minutes"] * (2 ** min(s["erreurs_consecutives"], 6))
        attente = min(attente, max(DELAI_MAX_MINUTES, s["frequence_minutes"]))
        if now - from_iso(s["derniere_collecte"]) >= timedelta(minutes=attente):
            dues.append(s)
    return dues


def _date_entree(e, now: datetime) -> datetime:
    for k in ("published_parsed", "updated_parsed"):
        t = e.get(k)
        if t:
            dt = datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
            # Date future ou absurde : on garde l'heure de collecte
            if dt > now + timedelta(hours=1) or dt.year < 2000:
                return now
            return dt
    return now


def _telecharger(client: httpx.Client, source: sqlite3.Row, max_octets: int):
    """Retourne (code HTTP, en-tetes, contenu). Contenu vide si 304."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml, */*"}
    if source["etag"]:
        headers["If-None-Match"] = source["etag"]
    if source["last_modified"]:
        headers["If-Modified-Since"] = source["last_modified"]
    with client.stream("GET", source["url"], headers=headers) as r:
        if r.status_code == 304:
            return 304, r.headers, b""
        r.raise_for_status()
        corps = bytearray()
        for bloc in r.iter_bytes():
            corps.extend(bloc)
            if len(corps) > max_octets:
                raise ValueError(f"flux trop volumineux (> {max_octets // 1024} Ko)")
        return r.status_code, r.headers, bytes(corps)


def collecter_source(conn: sqlite3.Connection, client: httpx.Client, source: sqlite3.Row,
                     now: datetime) -> int:
    """Collecte une source. Retourne le nombre d'articles nouveaux. Leve en cas d'erreur."""
    max_octets = int(lire(conn, "taille_max_flux_ko")) * 1024
    max_extrait = int(lire(conn, "extrait_max_caracteres"))
    code, entetes, contenu = _telecharger(client, source, max_octets)
    maj = {"derniere_collecte": to_iso(now), "derniere_erreur": None, "erreurs_consecutives": 0,
           "url_verifiee": 1}
    if code == 304:
        _maj_source(conn, source["id"], maj)
        return 0
    flux = feedparser.parse(contenu)
    if flux.bozo and not flux.entries:
        raise ValueError(f"flux illisible : {type(flux.bozo_exception).__name__}")
    maj["etag"] = entetes.get("ETag")
    maj["last_modified"] = entetes.get("Last-Modified")

    nouveaux = 0
    for e in flux.entries:
        lien = (e.get("link") or "").strip()
        titre = nettoyer_html(e.get("title") or "", 500)
        if not lien.startswith(("http://", "https://")) or not titre:
            continue  # contenu incomplet : ignore
        url = url_canonique(lien)
        guid = (e.get("id") or "")[:500] or None
        if guid and conn.execute("SELECT 1 FROM articles WHERE source_id = ? AND guid = ?",
                                 (source["id"], guid)).fetchone():
            continue
        extrait = nettoyer_html(e.get("summary") or e.get("description") or "", max_extrait)
        titre_norm = normaliser(titre)
        # Meme titre, meme source, derniere 48 h : republication -> doublon
        limite = to_iso(now - timedelta(hours=48))
        if conn.execute("SELECT 1 FROM articles WHERE source_id = ? AND titre_norm = ? AND collecte_le >= ?",
                        (source["id"], titre_norm, limite)).fetchone():
            continue
        cur = conn.execute(
            """INSERT OR IGNORE INTO articles
               (source_id, url, guid, titre, titre_norm, texte_extrait, texte_norm, auteur,
                publie_le, collecte_le)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (source["id"], url, guid or empreinte(url), titre, titre_norm, extrait,
             normaliser(extrait), (e.get("author") or None), to_iso(_date_entree(e, now)), to_iso(now)),
        )
        nouveaux += cur.rowcount
    _maj_source(conn, source["id"], maj)
    return nouveaux


def _maj_source(conn: sqlite3.Connection, source_id: int, champs: dict) -> None:
    champs = dict(champs, maj_le=champs.get("derniere_collecte"))
    cols = ", ".join(f"{k} = ?" for k in champs)
    conn.execute(f"UPDATE sources SET {cols} WHERE id = ?", (*champs.values(), source_id))


def collecter(conn: sqlite3.Connection, client: httpx.Client, now: datetime) -> ResultatCollecte:
    res = ResultatCollecte()
    for s in sources_dues(conn, now):
        res.sources_traitees += 1
        try:
            res.articles_nouveaux += collecter_source(conn, client, s, now)
        except Exception as exc:  # une source en panne ne bloque pas les autres
            msg = f"{type(exc).__name__}: {exc}"[:500]
            res.sources_en_erreur += 1
            res.erreurs.append(f"{s['nom']} : {msg}")
            conn.execute(
                "UPDATE sources SET derniere_collecte = ?, derniere_erreur = ?, "
                "erreurs_consecutives = erreurs_consecutives + 1 WHERE id = ?",
                (to_iso(now), msg, s["id"]))
            ecrire(conn, "ERREUR", "collecte", f"source {s['id']} {s['nom']} : {msg}")
        conn.commit()
    return res


def client_http() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(15.0, connect=10.0), follow_redirects=True,
                        max_redirects=5)
