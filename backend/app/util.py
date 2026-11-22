"""Outils communs : normalisation de texte, dates, URL."""

import hashlib
import html
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ISO = "%Y-%m-%dT%H:%M:%SZ"

STOPWORDS = set("""
a au aux avec ce ces cet cette dans de des du elle en et est il ils je la le les leur lui
ma mais me meme mes mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta
te tes toi ton tu un une vos votre vous y d l s c n j m t apres avant contre entre sans sous
selon vers chez plus moins tres tout tous toute toutes fait faire etre avoir ont a ete sont
""".split())


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime(ISO)


def from_iso(s: str) -> datetime:
    return datetime.strptime(s, ISO).replace(tzinfo=timezone.utc)


def normaliser(texte: str) -> str:
    """Minuscules, sans accents, ponctuation -> espace."""
    t = unicodedata.normalize("NFKD", texte or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = t.replace("’", " ").replace("'", " ")
    t = re.sub(r"[^a-z0-9.\- ]+", " ", t)
    t = re.sub(r"(?<![0-9])\.|\.(?![0-9])", " ", t)  # garde "49.3"
    return re.sub(r"\s+", " ", t).strip()


def mots_significatifs(texte_norm: str) -> list[str]:
    return [m for m in texte_norm.split() if len(m) > 2 and m not in STOPWORDS]


def contient(texte_norm: str, expression: str) -> bool:
    """Expression (normalisee) presente comme mot ou groupe de mots entiers."""
    e = normaliser(expression)
    if not e:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(e) + r"(?![a-z0-9])", texte_norm) is not None


def nettoyer_html(texte: str, max_len: int = 1000) -> str:
    t = re.sub(r"<[^>]+>", " ", texte or "")
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:max_len]


def url_canonique(url: str) -> str:
    """Retire fragments et parametres de suivi (utm_*, xtor...)."""
    p = urlsplit(url.strip())
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
         if not k.lower().startswith(("utm_", "xtor", "at_", "fbclid", "gclid"))]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path, urlencode(q), ""))


def empreinte(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]
