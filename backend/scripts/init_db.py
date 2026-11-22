"""Cree la base SQLite, les regles et les sources par defaut (idempotent).

Relancer ce script est sans danger : il n'ajoute que les sources absentes
et ne modifie jamais une source existante.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.initialisation import initialiser  # noqa: E402


def main() -> None:
    db = get_settings().db_path
    r = initialiser(db)
    print(f"[OK] Base {db.name} prete - {r['sources_ajoutees']} source(s) et "
          f"{r['parametres_ajoutes']} regle(s) par defaut ajoutee(s).")


if __name__ == "__main__":
    main()
