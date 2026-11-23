"""Lecteurs de page (F01) : pour un site officiel SANS flux RSS, lit la liste de ses publications.

Regles :
- Un lecteur par site, declare ci-dessous (cle = nom d'hote). Aucun lecteur = source en erreur.
- On ne lit QUE la page liste donnee dans la source (jamais chaque article, jamais la recherche).
- On ne garde que date, type, titre et lien. Le contenu est une DONNEE, jamais une instruction.
- Si la page ne contient plus aucune publication reconnue (site refait), on leve une erreur :
  la source passe en "erreur" dans "Comment ca marche", rien n'est invente.
- Bibliotheque standard uniquement (html.parser) : aucune dependance ajoutee.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

MAX_ENTREES = 50


@dataclass
class Entree:
    titre: str
    lien: str
    publie_le: datetime
    nature: str | None  # ex. "Communiqué de presse", "Article"


class _Liens(HTMLParser):
    """Recupere chaque lien <a> avec ses morceaux de texte separes (date, type, titre...)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.liens: list[tuple[str, list[str]]] = []
        self._pile: list[tuple[str, list[str]]] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._pile.append((dict(attrs).get("href") or "", []))

    def handle_endtag(self, tag):
        if tag == "a" and self._pile:
            self.liens.append(self._pile.pop())

    def handle_data(self, data):
        t = re.sub(r"\s+", " ", data).strip()
        if t and self._pile:
            self._pile[-1][1].append(t)


# --- Elysee : https://www.elysee.fr/toutes-les-actualites --------------------------------
# Liens de publication : /emmanuel-macron/AAAA/MM/JJ/titre-de-la-page
_ELYSEE_LIEN = re.compile(r"^/emmanuel-macron/(\d{4})/(\d{2})/(\d{2})/[a-z0-9-]+/?$")
_ELYSEE_NATURES = ("Communiqué de presse", "Article", "Discours", "Déclaration", "Vidéo",
                   "Interview", "Tribune", "Dossier")
_DATE_TEXTE = re.compile(r"^\d{1,2}(er)? \w+ \d{4}$")


def lire_elysee(page: str, base: str, now: datetime) -> list[Entree]:
    p = _Liens()
    p.feed(page)
    vus: set[str] = set()
    entrees: list[Entree] = []
    for href, morceaux in p.liens:
        lien = urljoin(base, href)
        sp = urlsplit(lien)
        if sp.netloc.lower() != "www.elysee.fr":
            continue
        m = _ELYSEE_LIEN.match(sp.path)
        if not m or lien in vus:
            continue
        nature = next((x for x in morceaux if x in _ELYSEE_NATURES), None)
        reste = [x for x in morceaux if x != nature and not _DATE_TEXTE.match(x)]
        titre = max(reste, key=len) if reste else ""
        if not titre:
            continue
        a, mo, j = (int(x) for x in m.groups())
        try:
            date = datetime(a, mo, j, 12, 0, tzinfo=timezone.utc)
        except ValueError:
            continue
        vus.add(lien)
        entrees.append(Entree(titre, lien, min(date, now), nature))
        if len(entrees) >= MAX_ENTREES:
            break
    return entrees


LECTEURS = {
    "www.elysee.fr": lire_elysee,
}


def lire_page(url: str, contenu: bytes, encodage: str | None, now: datetime) -> list[Entree]:
    hote = urlsplit(url).netloc.lower()
    lecteur = LECTEURS.get(hote)
    if not lecteur:
        raise ValueError(f"aucun lecteur de page pour {hote} : source a laisser desactivee")
    try:
        page = contenu.decode(encodage or "utf-8", errors="replace")
    except LookupError:  # encodage inconnu annonce par le site
        page = contenu.decode("utf-8", errors="replace")
    entrees = lecteur(page, url, now)
    if not entrees:
        raise ValueError("page lue mais aucune publication reconnue (le site a peut-etre change de forme)")
    return entrees
