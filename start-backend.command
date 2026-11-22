#!/bin/bash
# ============================================================
# start-backend.command - Lance le backend VEILLE en local (Mac)
# 1. Cherche Python 3.14, puis 3.13, puis 3.12
# 2. Cree l'environnement backend/.venv si absent
# 3. Cree ou complete backend/.env - vos cles ne sont jamais ecrasees
# 4. Cree la base, les regles et les sources par defaut - idempotent
# 5. Verifie que le port 8710 est libre
# 6. Demarre l'API et les taches automatiques sur http://127.0.0.1:8710
# ============================================================
source "$(dirname "$0")/_commun.sh"
cd "$BACK" || exit 1

preparer_env || { echo "[ERREUR] Une etape a echoue. Lisez le message ci-dessus."; pause_fin; exit 1; }

echo "[..] Configuration backend/.env..."
"$VPY" scripts/init_env.py || { pause_fin; exit 1; }
echo "[..] Base de donnees et sources par defaut..."
"$VPY" scripts/init_db.py || { pause_fin; exit 1; }

if port_occupe; then
    echo
    echo "[ERREUR] Le port $PORT est deja utilise par un autre programme :"
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN
    echo "         Fermez-le, ou lancez relancer-tout.command."
    pause_fin
    exit 1
fi

echo
echo "[OK] Backend sur http://127.0.0.1:$PORT  - sante : /api/v1/health  - doc : /docs"
echo "     Ctrl+C pour arreter."
echo
exec "$VPY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --reload
