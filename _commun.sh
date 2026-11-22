#!/bin/bash
# ============================================================
# _commun.sh - fonctions partagees par les scripts .command (Mac)
# Ne pas lancer directement.
# ============================================================
RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACK="$RACINE/backend"
PORT=8710
VPY="$BACK/.venv/bin/python"

pause_fin() {
    if [ "$1" != "nopause" ]; then
        echo
        read -n 1 -s -r -p "Appuyez sur une touche pour fermer..."
        echo
    fi
}

trouver_python() {
    PY=""
    for cand in python3.14 python3.13 python3.12 \
                /opt/homebrew/bin/python3.14 /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 \
                /usr/local/bin/python3.14 /usr/local/bin/python3.13 /usr/local/bin/python3.12 python3; do
        if command -v "$cand" >/dev/null 2>&1 && \
           "$cand" -c "import sys; sys.exit(0 if (3,12) <= sys.version_info[:2] <= (3,14) else 1)" 2>/dev/null; then
            PY="$cand"
            return 0
        fi
    done
    return 1
}

preparer_env() {
    if [ -x "$VPY" ]; then
        return 0
    fi
    if ! trouver_python; then
        echo
        echo "[ERREUR] Aucune version compatible de Python : il faut 3.12, 3.13 ou 3.14."
        echo "         Version actuelle : $(python3 --version 2>&1)"
        echo "         Installez Python 3.13 depuis https://www.python.org/downloads/macos/"
        echo "         ou avec Homebrew : brew install python@3.13"
        return 1
    fi
    echo "[..] Python trouve : $PY ($("$PY" --version))"
    echo "[..] Creation de l'environnement Python - premiere fois, patientez..."
    rm -rf "$BACK/.venv"
    "$PY" -m venv "$BACK/.venv" || return 1
    "$VPY" -m pip install --upgrade pip -q || return 1
    "$VPY" -m pip install -r "$BACK/requirements.txt" || return 1
}

port_occupe() {
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1
}
