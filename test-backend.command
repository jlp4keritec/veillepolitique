#!/bin/bash
# ============================================================
# test-backend.command - Lance tous les tests du backend VEILLE (Mac)
# Les tests utilisent une base temporaire - jamais la vraie base.
# Option : test-backend.command nopause - sans pause finale
# ============================================================
source "$(dirname "$0")/_commun.sh"
cd "$BACK" || exit 1

preparer_env || { echo "[ERREUR] Environnement Python impossible a creer."; pause_fin "$1"; exit 1; }
"$VPY" scripts/init_env.py >/dev/null
"$VPY" -m pytest
RC=$?
echo
if [ "$RC" = "0" ]; then
    echo "[OK] Tous les tests passent."
else
    echo "[ECHEC] Des tests ont echoue - code $RC. Envoyez une capture de cette fenetre."
fi
pause_fin "$1"
exit $RC
