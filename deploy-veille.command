#!/bin/bash
# ============================================================
# deploy-veille.command - Met VEILLE en ligne sur le VPS, depuis le Mac
#
#   1er deploiement : ~/veille/deploy-veille.command --init
#   mise a jour     : ~/veille/deploy-veille.command
# Options : --init          configure Nginx, HTTPS, mot de passe des pages
#           --copier-base   envoie la base du Mac (historique, reglages) - avec --init
#           --skip-nginx --skip-certbot   (depannage)
#
# Pre-requis : deploy-config.json (cle SSH, jamais de mot de passe SSH) dans ~/veille,
#              ~ ou ~/Agile ; enregistrement DNS veille -> IP du VPS (pour HTTPS).
# ============================================================
set -euo pipefail
RACINE="$(cd "$(dirname "$0")" && pwd)"
INIT=0; COPIER=0; SKIP_NGINX=0; SKIP_CERTBOT=0
for a in "$@"; do
    case "$a" in
        --init) INIT=1 ;; --copier-base) COPIER=1 ;;
        --skip-nginx) SKIP_NGINX=1 ;; --skip-certbot) SKIP_CERTBOT=1 ;;
        *) echo "Option inconnue : $a"; exit 1 ;;
    esac
done

etape() { echo; echo "[$(date +%H:%M:%S)] >> $*"; }
ok()    { echo "   [OK] $*"; }
die()   { echo "   [ERREUR] $*"; exit 1; }

echo "============================================"
echo "  VEILLE - deploiement sur le VPS"
echo "============================================"

# --- Configuration -------------------------------------------------------
CFG=""
for f in "$RACINE/deploy-config.json" "$HOME/deploy-config.json" "$HOME/Agile/deploy-config.json"; do
    [ -f "$f" ] && { CFG="$f"; break; }
done
[ -n "$CFG" ] || die "deploy-config.json introuvable. Copiez deploy/deploy-config.example.json en ~/veille/deploy-config.json et adaptez sshKeyPath."
lire() { /usr/bin/python3 -c "import json,os,sys; v=json.load(open(sys.argv[1])).get(sys.argv[2], sys.argv[3]); print(os.path.expanduser(str(v)))" "$CFG" "$1" "$2"; }
HOTE=$(lire host ""); UTIL=$(lire user ubuntu); PORT_SSH=$(lire port 22); CLE=$(lire sshKeyPath "")
FQDN=$(lire fqdn veille.mesoutilsagile.com); APP_PORT=$(lire appPort 5710)
[ -n "$HOTE" ] && [ -f "$CLE" ] || die "host ou sshKeyPath invalide dans $CFG"
SSH=(ssh -i "$CLE" -p "$PORT_SSH" -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new "$UTIL@$HOTE")
SCP=(scp -i "$CLE" -P "$PORT_SSH" -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new)
ok "config : $CFG -> $UTIL@$HOTE, https://$FQDN (port interne $APP_PORT)"

etape "Connexion SSH"
"${SSH[@]}" "echo connexion-ok" | grep -q connexion-ok || die "connexion SSH impossible"
ok "VPS joignable"

# --- Pre-vol : les tests doivent passer avant tout envoi -----------------
etape "Tests locaux (pre-vol obligatoire)"
"$RACINE/test-backend.command" nopause >/tmp/veille_prevol.log 2>&1 || { tail -15 /tmp/veille_prevol.log; die "tests en echec : rien n'est envoye"; }
ok "$(grep -E 'passed' /tmp/veille_prevol.log | tail -1)"

# --- Questions du premier deploiement ------------------------------------
MDP=""; EMAIL=""
if [ "$INIT" = "1" ]; then
    etape "Premier deploiement : informations"
    IP_DNS=$(/usr/bin/python3 -c "import socket,sys; print(socket.gethostbyname(sys.argv[1]))" "$FQDN" 2>/dev/null || true)
    if [ "$IP_DNS" != "$HOTE" ]; then
        echo "   [ATTENTION] $FQDN ne pointe pas encore vers $HOTE (DNS : ${IP_DNS:-aucun})."
        echo "               Creez chez OVH un enregistrement A : veille -> $HOTE. HTTPS sera saute."
        SKIP_CERTBOT=1
    fi
    if [ "$SKIP_CERTBOT" != "1" ]; then
        read -r -p "   E-mail pour le certificat HTTPS (Let's Encrypt) : " EMAIL
        if ! [[ "$EMAIL" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
            echo "   E-mail invalide : HTTPS saute (relancez --init plus tard)."; EMAIL=""; SKIP_CERTBOT=1
        fi
    fi
    while true; do
        read -r -s -p "   Mot de passe des pages (12 caracteres minimum) : " MDP; echo
        read -r -s -p "   Confirmez : " MDP2; echo
        [ "${#MDP}" -ge 12 ] && [ "$MDP" = "$MDP2" ] && break
        echo "   Trop court ou different, recommencez."
    done
fi

# --- Paquet (jamais .env, base, environnement Python, git) ---------------
etape "Paquet"
PAQUET=/tmp/veille_deploy.tgz
COPYFILE_DISABLE=1 tar -czf "$PAQUET" -C "$(dirname "$RACINE")" \
    --exclude='.git' --exclude='.venv' --exclude='__pycache__' --exclude='.pytest_cache' --exclude='.ruff_cache' \
    --exclude='.env' --exclude='*.db' --exclude='*.db-wal' --exclude='*.db-shm' --exclude='*.zip' \
    --exclude='.DS_Store' --exclude='deploy-config.json' --exclude='node_modules' "$(basename "$RACINE")"
if tar -tzf "$PAQUET" | grep -Eq '(^|/)\.env$|\.db$|deploy-config\.json'; then die "paquet contient un secret ou une base : arret"; fi
ok "$(du -h "$PAQUET" | cut -f1) - sans secret ni base"
"${SCP[@]}" "$PAQUET" "$RACINE/deploy/vps-installer.sh" "$UTIL@$HOTE:/tmp/" >/dev/null || die "envoi impossible"
trap 'rm -f "$PAQUET"' EXIT

if [ "$COPIER" = "1" ] && [ "$INIT" = "1" ]; then
    etape "Copie de la base du Mac"
    rm -rf /tmp/veille_base_mac && "$RACINE/backend/.venv/bin/python" "$RACINE/backend/scripts/sauvegarde_db.py" /tmp/veille_base_mac 1 >/dev/null
    "${SCP[@]}" /tmp/veille_base_mac/veille_*.db "$UTIL@$HOTE:/tmp/veille_base.db" >/dev/null || die "envoi de la base impossible"
    rm -rf /tmp/veille_base_mac
    ok "base envoyee"
fi

VARS="REMOTE_DIR=$(lire remoteDir /home/ubuntu/veille) FQDN=$FQDN APP_PORT=$APP_PORT INIT=$INIT SKIP_NGINX=$SKIP_NGINX SKIP_CERTBOT=$SKIP_CERTBOT EMAIL_CERTBOT='$EMAIL'"
etape "Installation sur le VPS"
"${SSH[@]}" "$VARS bash /tmp/vps-installer.sh preparer" || die "preparation echouee"

if [ -n "$MDP" ]; then
    # Le mot de passe passe par l'entree standard : jamais dans une commande ni un journal
    printf '%s' "$MDP" | "${SSH[@]}" "cd $(lire remoteDir /home/ubuntu/veille)/backend && .venv/bin/python scripts/definir_env.py MOT_DE_PASSE_PAGES" >/dev/null \
        || die "enregistrement du mot de passe impossible"
    MDP=""; MDP2=""
    ok "mot de passe des pages enregistre sur le VPS"
fi

etape "Demarrage sur le VPS"
"${SSH[@]}" "$VARS bash /tmp/vps-installer.sh demarrer" || die "demarrage echoue"

echo
echo "============================================"
echo "  VEILLE en ligne : https://$FQDN"
echo "============================================"
echo "  Pensez a arreter VEILLE sur le Mac (une seule instance a la fois)."
echo "  Journaux : ssh $UTIL@$HOTE 'pm2 logs veille --lines 30 --nostream'"
