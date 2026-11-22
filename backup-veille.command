#!/bin/bash
# ============================================================
# backup-veille.command - Sauvegarde ZIP de VEILLE (Mac)
# Sortie : ~/veille-backups/veille_AAAAMMJJ-HHMMSS.zip
# Toujours exclus : .venv, caches, .env (secrets), .DS_Store
# ============================================================
source "$(dirname "$0")/_commun.sh"
DEST="$HOME/veille-backups"
mkdir -p "$DEST"

echo "============================================"
echo "  Backup VEILLE  ->  $DEST"
echo "============================================"
echo "  1. Complet                (avec .git et la base)"
echo "  2. Sans base              (recommande avant deploiement)"
echo "  3. Sans base ni .git      (leger)"
echo "  0. Quitter"
echo
read -r -p "Votre choix [0-3] : " CHOIX

EXCL=(-x "*/.venv/*" -x "*/__pycache__/*" -x "*/.pytest_cache/*" -x "*/.ruff_cache/*" \
      -x "*/.env" -x "*.DS_Store" -x "*/node_modules/*")
case "$CHOIX" in
    1) ;;
    2) EXCL+=(-x "*/data/*.db" -x "*/data/*.db-wal" -x "*/data/*.db-shm") ;;
    3) EXCL+=(-x "*/data/*.db" -x "*/data/*.db-wal" -x "*/data/*.db-shm" -x "*/.git/*") ;;
    0) exit 0 ;;
    *) echo "Choix invalide."; pause_fin; exit 1 ;;
esac

ZIP="$DEST/veille_$(date +%Y%m%d-%H%M%S).zip"
cd "$(dirname "$RACINE")" || exit 1
NOM="$(basename "$RACINE")"
if zip -r -q "$ZIP" "$NOM" "${EXCL[@]}"; then
    echo "[OK] Sauvegarde creee : $ZIP ($(du -h "$ZIP" | cut -f1))"
else
    echo "[ERREUR] La sauvegarde a echoue."
fi
pause_fin
