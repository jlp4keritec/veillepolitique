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

env_valide() {
    # Environnement present ET cree avec Python 3.12 a 3.14 ?
    [ -x "$VPY" ] && "$VPY" -c "import sys; sys.exit(0 if (3,12) <= sys.version_info[:2] <= (3,14) else 1)" 2>/dev/null
}

trouver_uv() {
    UV=""
    for cand in uv /opt/homebrew/bin/uv /usr/local/bin/uv "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
        if command -v "$cand" >/dev/null 2>&1; then
            UV="$cand"
            return 0
        fi
    done
    return 1
}

empreinte_req() {
    if command -v shasum >/dev/null 2>&1; then
        shasum "$BACK/requirements.txt" | cut -d' ' -f1
    else
        cksum "$BACK/requirements.txt" | cut -d' ' -f1
    fi
}

installer_paquets() {
    echo "[..] Installation des bibliotheques (requirements.txt)..."
    if trouver_uv; then
        "$UV" pip install --python "$VPY" -r "$BACK/requirements.txt" || return 1
    else
        "$VPY" -m pip install -r "$BACK/requirements.txt" || return 1
    fi
    empreinte_req > "$BACK/.venv/.requirements.sha"
}

preparer_env() {
    if env_valide; then
        # Liste des bibliotheques modifiee depuis la derniere installation ?
        if [ "$(cat "$BACK/.venv/.requirements.sha" 2>/dev/null)" != "$(empreinte_req)" ]; then
            installer_paquets || return 1
        fi
        return 0
    fi
    if [ -d "$BACK/.venv" ]; then
        echo "[..] Environnement Python absent, abime ou trop ancien : il est recree."
    fi
    if ! trouver_python; then
        echo
        echo "[ERREUR] Aucune version compatible de Python : il faut 3.12, 3.13 ou 3.14."
        echo "         Version actuelle : $(python3 --version 2>&1)"
        echo "         Installez Python 3.13 avec Homebrew : brew install python@3.13"
        return 1
    fi
    echo "[..] Python trouve : $PY ($("$PY" --version))"
    echo "[..] Creation de l'environnement Python - premiere fois, patientez..."
    rm -rf "$BACK/.venv"
    if trouver_uv; then
        echo "[..] Installateur : uv"
        "$UV" venv --python "$PY" "$BACK/.venv" || return 1
    else
        "$PY" -m venv "$BACK/.venv" || {
            echo "[AIDE] Si l'erreur parle de 'ensurepip' : installez uv (brew install uv) puis relancez."
            return 1
        }
        "$VPY" -m pip install --upgrade pip -q || return 1
    fi
    installer_paquets
}

port_occupe() {
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1
}
