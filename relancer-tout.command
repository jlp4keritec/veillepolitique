#!/bin/bash
# ============================================================
# relancer-tout.command - Redemarre VEILLE en local (Mac)
# 1. Ferme le backend - port 8710 uniquement
# 2. Lance les tests - s'arrete s'ils echouent
# 3. Relance le backend dans une nouvelle fenetre Terminal
# 4. Attend qu'il reponde puis ouvre la page de sante
# ============================================================
source "$(dirname "$0")/_commun.sh"

echo "[..] Fermeture du backend precedent..."
PIDS=$(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null)
if [ -n "$PIDS" ]; then
    kill $PIDS 2>/dev/null
    sleep 2
    PIDS=$(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null)
    [ -n "$PIDS" ] && kill -9 $PIDS 2>/dev/null && sleep 1
fi
if port_occupe; then
    echo "[ERREUR] Le port $PORT est encore occupe :"
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN
    pause_fin
    exit 1
fi
echo "[OK] Backend arrete."

echo
echo "[..] Tests du backend..."
if ! "$RACINE/test-backend.command" nopause; then
    echo
    echo "[ECHEC] Des tests ont echoue : l'application n'est PAS relancee."
    pause_fin
    exit 1
fi

echo
echo "[..] Demarrage du backend dans une nouvelle fenetre..."
open -a Terminal "$RACINE/start-backend.command"
for i in $(seq 1 90); do
    if curl -s -o /dev/null "http://127.0.0.1:$PORT/api/v1/health"; then
        echo "[OK] Backend pret sur http://127.0.0.1:$PORT"
        open "http://127.0.0.1:$PORT/api/v1/health"
        echo "La fenetre du backend reste ouverte. Pour arreter : Ctrl+C dans cette fenetre."
        sleep 2
        exit 0
    fi
    sleep 2
done
echo "[ERREUR] Le backend ne repond pas apres 3 minutes. Regardez sa fenetre."
pause_fin
exit 1
