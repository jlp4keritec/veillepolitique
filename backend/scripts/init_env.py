"""Cree backend/.env depuis .env.example, ou le complete (idempotent).

- .env absent  : copie complete du modele.
- .env present : ajoute seulement les cles manquantes, ne modifie JAMAIS
  une valeur deja presente (vos secrets restent intacts).
"""

from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
EXAMPLE = BACKEND / ".env.example"
ENV = BACKEND / ".env"


def cles(lignes: list[str]) -> set[str]:
    out = set()
    for l in lignes:
        l = l.strip()
        if l and not l.startswith("#") and "=" in l:
            out.add(l.split("=", 1)[0].strip())
    return out


def main() -> None:
    modele = EXAMPLE.read_text(encoding="utf-8").splitlines()
    if not ENV.exists():
        ENV.write_text("\n".join(modele) + "\n", encoding="utf-8")
        print("[OK] backend/.env cree. Renseignez vos cles dedans (jamais dans le chat).")
        return
    actuel = ENV.read_text(encoding="utf-8").splitlines()
    presentes = cles(actuel)
    manquantes = [l for l in modele if "=" in l and not l.lstrip().startswith("#")
                  and l.split("=", 1)[0].strip() not in presentes]
    if manquantes:
        with ENV.open("a", encoding="utf-8") as f:
            f.write("\n# Ajoute automatiquement\n" + "\n".join(manquantes) + "\n")
        print(f"[OK] backend/.env complete : {len(manquantes)} cle(s) ajoutee(s).")


if __name__ == "__main__":
    main()
