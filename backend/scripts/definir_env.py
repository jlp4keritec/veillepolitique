"""Ecrit une valeur dans backend/.env, lue sur l'ENTREE STANDARD (jamais en argument).

Usage : printf '%s' "valeur" | python scripts/definir_env.py CLE
Ainsi un secret n'apparait ni dans l'historique du terminal ni dans la liste des processus.
Remplace la ligne CLE=... si elle existe, sinon l'ajoute. Fichier .env en droits 600.
"""

import os
import re
import sys
from pathlib import Path

ENV = Path(__file__).resolve().parent.parent / ".env"


def definir(cle: str, valeur: str, fichier: Path = ENV) -> None:
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", cle):
        raise ValueError("nom de cle invalide")
    if "\n" in valeur or "\r" in valeur:
        raise ValueError("la valeur ne doit pas contenir de retour a la ligne")
    lignes = fichier.read_text(encoding="utf-8").splitlines() if fichier.exists() else []
    nouvelle = f"{cle}={valeur}"
    for i, l in enumerate(lignes):
        if l.split("=", 1)[0].strip() == cle and not l.lstrip().startswith("#"):
            lignes[i] = nouvelle
            break
    else:
        lignes.append(nouvelle)
    fichier.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    os.chmod(fichier, 0o600)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage : printf '%s' valeur | python scripts/definir_env.py CLE")
    definir(sys.argv[1], sys.stdin.read().rstrip("\n"))
    print(f"[OK] {sys.argv[1]} enregistre dans backend/.env")
