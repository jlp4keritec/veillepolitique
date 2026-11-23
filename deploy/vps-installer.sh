#!/usr/bin/env bash
# ============================================================
# vps-installer.sh - execute SUR LE VPS par deploy-veille.command
#   bash vps-installer.sh preparer   : code, environnement Python, .env, base, tests
#   bash vps-installer.sh demarrer   : PM2, controle de sante (retour arriere si KO),
#                                      Nginx, Certbot, sauvegarde quotidienne
# Variables : FQDN, APP_PORT, INIT (0/1), SKIP_NGINX, SKIP_CERTBOT, EMAIL_CERTBOT
# Idempotent : relancable sans danger.
# ============================================================
set -euo pipefail

ETAPE="${1:-}"
REMOTE="${REMOTE_DIR:-$HOME/veille}"
FQDN="${FQDN:-veille.mesoutilsagile.com}"
APP_PORT="${APP_PORT:-5710}"
INIT="${INIT:-0}"
SAUV_CODE="$HOME/backups/veille-code"
PAQUET="${PAQUET:-/tmp/veille_deploy.tgz}"
BASE_IMPORT="/tmp/veille_base.db"
PY="$REMOTE/backend/.venv/bin/python"

ok()   { echo "   [OK] $*"; }
info() { echo "   ...  $*"; }
die()  { echo "   [ERREUR] $*" >&2; exit 1; }

restaurer_code() {
    local dernier
    dernier=$(ls -1t "$SAUV_CODE"/veille-code-*.tgz 2>/dev/null | head -1 || true)
    if [ -n "$dernier" ]; then
        echo "   ... remise en place de $dernier"
        tar -xzf "$dernier" -C "$(dirname "$REMOTE")"
    fi
}

preparer() {
    echo "==> Preparation sur le VPS ($REMOTE)"
    [ -f "$PAQUET" ] || die "paquet absent : $PAQUET"
    python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" \
        || die "Python 3.12+ requis sur le VPS (python3 --version)"
    command -v rsync >/dev/null 2>&1 || { info "installation de rsync"; sudo apt-get install -y -qq rsync >/dev/null; }
    if ! python3 -c "import ensurepip" 2>/dev/null; then
        info "installation de python3-venv"
        sudo apt-get update -qq && sudo apt-get install -y -qq python3-venv >/dev/null
    fi

    # 1. Sauvegarde du code actuel (retour arriere possible), 5 gardees
    mkdir -p "$SAUV_CODE"
    if [ -d "$REMOTE/backend/app" ]; then
        tar -czf "$SAUV_CODE/veille-code-$(date +%Y%m%d-%H%M%S).tgz" -C "$(dirname "$REMOTE")" \
            --exclude='veille/backend/.venv' --exclude='veille/backend/data' "$(basename "$REMOTE")"
        ls -1t "$SAUV_CODE"/veille-code-*.tgz | tail -n +6 | xargs -r rm -f
        ok "code precedent sauvegarde"
    fi

    # 2. Nouveau code (jamais .env, base ni environnement Python)
    rm -rf /tmp/veille_extract && mkdir -p /tmp/veille_extract "$REMOTE"
    tar -xzf "$PAQUET" -C /tmp/veille_extract
    [ -d /tmp/veille_extract/veille/backend/app ] || die "paquet incomplet"
    rsync -a --delete \
        --exclude='backend/.env' --exclude='backend/data/' --exclude='backend/.venv/' --exclude='.git/' \
        /tmp/veille_extract/veille/ "$REMOTE/"
    mkdir -p "$REMOTE/backend/data"
    # Identifiant unique de ce deploiement : le controle de sante exige de le voir
    echo "dep-$(date +%Y%m%d-%H%M%S)-$RANDOM" > "$REMOTE/backend/DEPLOIEMENT"
    ok "code installe ($(cat "$REMOTE/backend/DEPLOIEMENT"))"

    # 3. Environnement Python
    if ! "$PY" -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" 2>/dev/null; then
        rm -rf "$REMOTE/backend/.venv"
        python3 -m venv "$REMOTE/backend/.venv"
        "$PY" -m pip install -q --upgrade pip
    fi
    "$PY" -m pip install -q -r "$REMOTE/backend/requirements.txt"
    ok "bibliotheques Python a jour"

    # 4. Configuration .env (vos secrets existants ne sont jamais ecrases)
    cd "$REMOTE/backend"
    "$PY" scripts/init_env.py
    printf '%s' "vps" | "$PY" scripts/definir_env.py ENVIRONNEMENT >/dev/null
    printf '%s' "https://$FQDN" | "$PY" scripts/definir_env.py URL_PUBLIQUE >/dev/null
    printf '%s' "$APP_PORT" | "$PY" scripts/definir_env.py BACKEND_PORT >/dev/null
    chmod 600 .env
    ok ".env : ENVIRONNEMENT=vps, URL_PUBLIQUE=https://$FQDN"

    # 5. Base importee depuis le Mac (option --copier-base, premier deploiement)
    if [ -f "$BASE_IMPORT" ]; then
        [ -f data/veille.db ] && cp data/veille.db "data/veille.db.avant-import-$(date +%Y%m%d-%H%M%S)"
        rm -f data/veille.db-wal data/veille.db-shm
        mv "$BASE_IMPORT" data/veille.db
        ok "base importee depuis le Mac"
    fi
    "$PY" scripts/init_db.py

    # 6. Tests sur le VPS (base temporaire, aucun secret utilise)
    if ! "$PY" -m pytest -p no:warnings >/tmp/veille_tests.log 2>&1; then
        tail -20 /tmp/veille_tests.log
        restaurer_code
        die "tests en echec sur le VPS : version precedente remise en place, rien n'a ete redemarre"
    fi
    ok "tests : $(grep -E 'passed|failed' /tmp/veille_tests.log | tail -1)"
}

port_occupe() { (exec 3<>"/dev/tcp/127.0.0.1/$APP_PORT") 2>/dev/null; }

attendre_port_libre() {
    for _ in $(seq 1 15); do port_occupe || return 0; sleep 1; done
    die "le port $APP_PORT reste occupe apres l'arret de VEILLE (autre programme ?) : rien n'est tue automatiquement"
}

sante() {
    # Repond ET c'est bien la nouvelle version (pas l'ancien processus encore en arret)
    local attendu
    attendu=$(cat "$REMOTE/backend/DEPLOIEMENT" 2>/dev/null || echo "?")
    sleep 2
    for _ in $(seq 1 25); do
        if curl -s "http://127.0.0.1:$APP_PORT/api/v1/health" | grep -q "\"deploiement\":\"$attendu\""; then
            return 0
        fi
        sleep 1
    done
    return 1
}

retour_arriere() {
    pm2 logs veille --lines 30 --nostream 2>/dev/null || true
    echo "   ... RETOUR ARRIERE"
    restaurer_code
    cd "$REMOTE" && pm2 delete veille >/dev/null 2>&1 || true
    attendre_port_libre
    VEILLE_PORT="$APP_PORT" pm2 start ecosystem.config.cjs >/dev/null && pm2 save >/dev/null
    for _ in $(seq 1 25); do
        [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$APP_PORT/api/v1/health")" = "200" ] && break
        sleep 1
    done
    die "la nouvelle version ne repond pas : version precedente relancee (voir les journaux ci-dessus)"
}

demarrer() {
    echo "==> Demarrage"
    cd "$REMOTE"
    if ! pm2 describe veille >/dev/null 2>&1 && port_occupe; then
        die "le port $APP_PORT est deja pris par un autre service (changez appPort dans deploy-config.json)"
    fi
    grep -q '^MOT_DE_PASSE_PAGES=.\{12,\}' backend/.env || die "MOT_DE_PASSE_PAGES absent (relancez avec --init)"
    pm2 delete veille >/dev/null 2>&1 || true
    attendre_port_libre
    VEILLE_PORT="$APP_PORT" pm2 start ecosystem.config.cjs >/dev/null
    pm2 save >/dev/null
    sante || retour_arriere
    ok "VEILLE repond sur 127.0.0.1:$APP_PORT"

    if [ "${SKIP_NGINX:-0}" != "1" ]; then
        CONF="/etc/nginx/sites-available/$FQDN.conf"
        if [ -f "$CONF" ]; then
            info "vhost Nginx deja present ($CONF) : conserve"
        else
            sed -e "s/__FQDN__/$FQDN/g" -e "s/__PORT__/$APP_PORT/g" "$REMOTE/deploy/nginx-veille.conf" | sudo tee "$CONF" >/dev/null
            sudo ln -sf "$CONF" "/etc/nginx/sites-enabled/$FQDN.conf"
            if sudo nginx -t 2>/tmp/nginx-test.log; then
                sudo systemctl reload nginx && ok "Nginx : $FQDN"
            else
                sudo rm -f "/etc/nginx/sites-enabled/$FQDN.conf" "$CONF"
                cat /tmp/nginx-test.log; die "configuration Nginx refusee : retiree, les autres sites ne sont pas touches"
            fi
        fi
    fi

    if [ "${SKIP_CERTBOT:-0}" != "1" ] && [ "$INIT" = "1" ] && [ -n "${EMAIL_CERTBOT:-}" ]; then
        sudo certbot --nginx --non-interactive --agree-tos --email "$EMAIL_CERTBOT" --redirect -d "$FQDN" \
            && ok "HTTPS actif" || echo "   [ATTENTION] Certbot a echoue (DNS pas encore pret ?) : relancez plus tard avec --init"
    fi

    # Sauvegarde quotidienne de la base a 03:15 (30 gardees)
    if command -v crontab >/dev/null 2>&1; then
        LIGNE="15 3 * * * cd $REMOTE/backend && .venv/bin/python scripts/sauvegarde_db.py >> $HOME/logs/veille-sauvegarde.log 2>&1"
        mkdir -p "$HOME/logs"
        ( crontab -l 2>/dev/null | grep -v 'veille/backend && .venv/bin/python scripts/sauvegarde_db.py' ; echo "$LIGNE" ) | crontab -
        ok "sauvegarde quotidienne programmee (03:15, ~/backups/veille)"
    fi
    rm -f "$PAQUET"
}

case "$ETAPE" in
    preparer) preparer ;;
    demarrer) demarrer ;;
    *) die "usage : vps-installer.sh preparer|demarrer" ;;
esac
