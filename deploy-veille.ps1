# ============================================================================
# deploy-veille.ps1 - Met VEILLE en ligne sur le VPS, depuis le PC Windows
#
#   1er deploiement : deploy-veille.bat -Init
#   mise a jour     : deploy-veille.bat
# Options : -Init         Nginx, HTTPS, mot de passe des pages (1re fois)
#           -CopierBase   envoie la base du PC (historique, reglages) - avec -Init
#           -SkipNginx -SkipCertbot   (depannage)
#
# Pre-requis : C:\veille\deploy-config.json (cle SSH, jamais de mot de passe SSH),
#              enregistrement DNS veille -> IP du VPS.
# Le travail sur le VPS est fait par deploy\vps-installer.sh (le meme que pour le Mac).
# ============================================================================
[CmdletBinding()]
param(
    [switch]$Init,
    [switch]$CopierBase,
    [switch]$SkipNginx,
    [switch]$SkipCertbot
)

$ErrorActionPreference = 'Stop'
$RACINE = $PSScriptRoot
$REMOTE_ATTENDU = '/home/ubuntu/veille'

function Write-Step { param($m) Write-Host "`n[$((Get-Date).ToString('HH:mm:ss'))] >> $m" -ForegroundColor Cyan }
function Write-Ok   { param($m) Write-Host "   OK  $m" -ForegroundColor Green }
function Write-Info { param($m) Write-Host "   ... $m" -ForegroundColor Gray }
function Write-Warn { param($m) Write-Host "   !!  $m" -ForegroundColor Yellow }
function Stop-Deploy { param($m) Write-Host "   ERREUR $m" -ForegroundColor Red; exit 1 }

Write-Host '============================================'
Write-Host '  VEILLE - deploiement sur le VPS (PC)'
Write-Host '============================================'

# --- Configuration -----------------------------------------------------------
$cfgPath = Join-Path $RACINE 'deploy-config.json'
if (-not (Test-Path $cfgPath)) {
    Stop-Deploy "deploy-config.json introuvable dans $RACINE (copiez deploy\deploy-config.example.json et adaptez sshKeyPath)."
}
$cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
$HOTE   = [string]$cfg.host
$UTIL   = if ($cfg.user) { [string]$cfg.user } else { 'ubuntu' }
$PORT   = if ($cfg.port) { [string]$cfg.port } else { '22' }
$CLE    = [string]$cfg.sshKeyPath
$REMOTE = if ($cfg.remoteDir) { [string]$cfg.remoteDir } else { $REMOTE_ATTENDU }
$FQDN   = if ($cfg.fqdn) { [string]$cfg.fqdn } else { 'veille.mesoutilsagile.com' }
$APP_PORT = if ($cfg.appPort) { [string]$cfg.appPort } else { '5727' }

if (-not $HOTE) { Stop-Deploy "host manquant dans $cfgPath" }
if (-not (Test-Path $CLE)) { Stop-Deploy "cle SSH introuvable : $CLE" }
if ($REMOTE -ne $REMOTE_ATTENDU) {
    Stop-Deploy "remoteDir = '$REMOTE' : VEILLE s'installe uniquement dans $REMOTE_ATTENDU (protection des autres projets)."
}
if ($APP_PORT -notmatch '^\d{4,5}$') { Stop-Deploy "appPort invalide : $APP_PORT" }
if ($FQDN -notmatch '^[a-z0-9.-]+$') { Stop-Deploy "fqdn invalide : $FQDN" }

# Outils natifs de Windows (pas ceux de Git, dont le tar ne comprend pas C:\)
$SSH_EXE = Join-Path $env:SystemRoot 'System32\OpenSSH\ssh.exe'
$SCP_EXE = Join-Path $env:SystemRoot 'System32\OpenSSH\scp.exe'
$TAR_EXE = Join-Path $env:SystemRoot 'System32\tar.exe'
if (-not (Test-Path $SSH_EXE)) { $SSH_EXE = (Get-Command ssh -ErrorAction SilentlyContinue).Source }
if (-not (Test-Path $SCP_EXE)) { $SCP_EXE = (Get-Command scp -ErrorAction SilentlyContinue).Source }
if (-not $SSH_EXE -or -not $SCP_EXE) { Stop-Deploy 'ssh/scp introuvables : installez le client OpenSSH de Windows' }
if (-not (Test-Path $TAR_EXE)) { Stop-Deploy 'tar.exe de Windows introuvable (Windows 10 1803+ requis)' }

# Lance un programme externe sans que ses messages d'avertissement arretent le script
function Invoke-Native {
    param([string]$Exe, [string[]]$Arguments)
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try { $o = & $Exe @Arguments 2>&1 | ForEach-Object { "$_" } } finally { $ErrorActionPreference = $old }
    return ,@($o)
}

$SSH_ARGS = @('-i', $CLE, '-p', $PORT, '-o', 'ConnectTimeout=15', '-o', 'StrictHostKeyChecking=accept-new', '-o', 'BatchMode=yes')
$SCP_ARGS = @('-i', $CLE, '-P', $PORT, '-o', 'ConnectTimeout=15', '-o', 'StrictHostKeyChecking=accept-new', '-o', 'BatchMode=yes')
$CIBLE = "$UTIL@$HOTE"

function Invoke-Ssh {
    param([string]$Commande)
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try { & $SSH_EXE @SSH_ARGS $CIBLE $Commande 2>&1 | ForEach-Object { "$_" } | Out-Host; $rc = $LASTEXITCODE }
    finally { $ErrorActionPreference = $old }
    return $rc
}

function Send-Scp {
    param([string[]]$Fichiers, [string]$Destination)
    $o = Invoke-Native $SCP_EXE ($SCP_ARGS + $Fichiers + @("$($CIBLE):$Destination"))
    if ($LASTEXITCODE -ne 0) { $o | Out-Host }
    if ($LASTEXITCODE -ne 0) { Stop-Deploy "envoi impossible ($LASTEXITCODE)" }
}

# Envoie un secret par l'entree standard de ssh (jamais dans une commande, un fichier ou un journal)
function Send-Secret {
    param([string]$Secret, [string]$Commande)
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $SSH_EXE
    $q = { param($s) '"' + ($s -replace '"', '\"') + '"' }
    $parts = @()
    foreach ($a in $SSH_ARGS) { $parts += (& $q $a) }
    $parts += (& $q $CIBLE)
    $parts += (& $q $Commande)
    $psi.Arguments = ($parts -join ' ')
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $p = [System.Diagnostics.Process]::Start($psi)
    $octets = (New-Object System.Text.UTF8Encoding($false)).GetBytes($Secret)
    $p.StandardInput.BaseStream.Write($octets, 0, $octets.Length)
    $p.StandardInput.Close()
    $null = $p.StandardOutput.ReadToEnd()
    $err = $p.StandardError.ReadToEnd()
    $p.WaitForExit()
    if ($p.ExitCode -ne 0) { Write-Host $err; return $false }
    return $true
}

Write-Ok "config : $cfgPath -> $CIBLE, https://$FQDN (port interne $APP_PORT)"


# --- Connexion + port --------------------------------------------------------
Write-Step 'Connexion SSH'
$out = Invoke-Native $SSH_EXE ($SSH_ARGS + @($CIBLE, 'echo connexion-ok'))
if (($out -join ' ') -notmatch 'connexion-ok') { $out | Out-Host; Stop-Deploy 'connexion SSH impossible (cle, reseau ?)' }
Write-Ok 'VPS joignable'

Write-Step "Port $APP_PORT sur le VPS"
$etat = Invoke-Native $SSH_EXE ($SSH_ARGS + @($CIBLE, "if pm2 describe veille >/dev/null 2>&1; then echo VEILLE; elif ss -ltnH 'sport = :$APP_PORT' | grep -q .; then echo OCCUPE; else echo LIBRE; fi"))
$etat = ($etat -join ' ')
if ($etat -match 'OCCUPE') { Stop-Deploy "le port $APP_PORT est pris par un autre service : changez appPort dans deploy-config.json" }
if ($etat -match 'VEILLE') { Write-Ok 'VEILLE deja installe : mise a jour' }
elseif ($etat -match 'LIBRE') {
    Write-Ok 'port libre'
    if (-not $Init) { Stop-Deploy 'VEILLE n''est pas encore installe sur le VPS : relancez avec -Init' }
}
else { Write-Host $etat; Stop-Deploy 'verification du port impossible' }

# --- Pre-vol : les tests doivent passer avant tout envoi ---------------------
Write-Step 'Tests locaux (pre-vol obligatoire)'
$log = Join-Path $env:TEMP 'veille_prevol.log'
& cmd.exe /c "`"`"$(Join-Path $RACINE 'test-backend.cmd')`" nopause > `"$log`" 2>&1`""
$rc = $LASTEXITCODE
$resume = (Select-String -Path $log -Pattern 'passed|failed' | Select-Object -Last 1).Line
if ($rc -ne 0) { Get-Content $log -Tail 15 | Out-Host; Stop-Deploy 'tests en echec : rien n''est envoye' }
Write-Ok $resume

# --- Questions du premier deploiement ----------------------------------------
$EMAIL = ''
$MDP = $null
if ($Init) {
    Write-Step 'Premier deploiement : informations'
    $ipDns = $null
    try { $ipDns = (Resolve-DnsName $FQDN -Type A -ErrorAction Stop | Where-Object { $_.IPAddress } | Select-Object -First 1).IPAddress } catch { }
    if ($ipDns -ne $HOTE) {
        Write-Warn "$FQDN ne pointe pas vers $HOTE (DNS : $ipDns). HTTPS saute ; relancez -Init plus tard."
        $SkipCertbot = $true
    } else { Write-Ok "DNS : $FQDN -> $HOTE" }
    if (-not $SkipCertbot) {
        $EMAIL = Read-Host "   E-mail pour le certificat HTTPS (Let's Encrypt)"
        if ($EMAIL -notmatch '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$') {
            Write-Warn 'e-mail invalide : HTTPS saute (relancez -Init plus tard)'
            $EMAIL = ''; $SkipCertbot = $true
        }
    }
    while ($true) {
        $s1 = Read-Host '   Mot de passe des pages (12 caracteres minimum)' -AsSecureString
        $s2 = Read-Host '   Confirmez' -AsSecureString
        $p1 = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s1))
        $p2 = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s2))
        if ($p1.Length -ge 12 -and $p1 -ceq $p2 -and $p1 -notmatch "[`r`n]") { $MDP = $p1; $p1 = $null; $p2 = $null; break }
        Write-Warn 'trop court ou different, recommencez'
    }
}

# --- Paquet (jamais .env, base, environnement Python, git) -------------------
Write-Step 'Paquet'
$tmp = Join-Path $env:TEMP ('veille_deploy_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    $paquet = Join-Path $tmp 'veille_deploy.tgz'
    $parent = Split-Path $RACINE -Parent
    $nom = Split-Path $RACINE -Leaf
    if ($nom -ne 'veille') { Stop-Deploy "le projet doit etre dans un dossier nomme veille (actuel : $nom)" }
    $exclus = @('.git', '.venv', '__pycache__', '.pytest_cache', '.ruff_cache', 'node_modules',
                '.env', '*.db', '*.db-wal', '*.db-shm', '*.db.bak*', '*.zip', '*.bak', '*.log',
                'deploy-config.json', '.DS_Store')
    $targs = @('-czf', $paquet, '-C', $parent)
    foreach ($e in $exclus) { $targs += "--exclude=$e" }
    $targs += $nom
    $o = Invoke-Native $TAR_EXE $targs
    if ($LASTEXITCODE -ne 0) { $o | Out-Host }
    if ($LASTEXITCODE -ne 0) { Stop-Deploy "tar a echoue ($LASTEXITCODE)" }
    $liste = Invoke-Native $TAR_EXE @('-tzf', $paquet)
    if ($LASTEXITCODE -ne 0) { Stop-Deploy 'paquet illisible' }
    $interdits = $liste | Where-Object { $_ -match '(^|/)\.env$' -or $_ -match '\.db$' -or $_ -match 'deploy-config\.json$' -or $_ -match '\\' }
    if ($interdits) { $interdits | Out-Host; Stop-Deploy 'paquet contient un secret, une base ou un chemin Windows : arret' }
    if (-not ($liste -match '^veille/backend/app/main\.py$')) { Stop-Deploy 'paquet incomplet (veille/backend/app/main.py absent)' }
    Write-Ok ("{0:N0} Ko, {1} fichiers - sans secret ni base" -f ((Get-Item $paquet).Length / 1KB), $liste.Count)

    # Le script bash doit avoir des fins de ligne Unix, quel que soit le reglage git du PC
    $installeur = Join-Path $tmp 'vps-installer.sh'
    $texte = [IO.File]::ReadAllText((Join-Path $RACINE 'deploy\vps-installer.sh')) -replace "`r`n", "`n"
    [IO.File]::WriteAllText($installeur, $texte, (New-Object System.Text.UTF8Encoding($false)))

    Send-Scp @($paquet, $installeur) '/tmp/'
    Write-Ok 'paquet envoye'

    if ($CopierBase -and $Init) {
        Write-Step 'Copie de la base du PC'
        $py = Join-Path $RACINE 'backend\.venv\Scripts\python.exe'
        $sauv = Join-Path $tmp 'base'
        $o = Invoke-Native $py @((Join-Path $RACINE 'backend\scripts\sauvegarde_db.py'), $sauv, '1')
        if ($LASTEXITCODE -ne 0) { $o | Out-Host; Stop-Deploy 'copie de la base impossible' }
        $db = Get-ChildItem $sauv -Filter 'veille_*.db' -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $db) { Stop-Deploy 'copie de la base impossible' }
        Send-Scp @($db.FullName) '/tmp/veille_base.db'
        Write-Ok 'base envoyee'
    }

    $vars = "REMOTE_DIR=$REMOTE FQDN=$FQDN APP_PORT=$APP_PORT INIT=$([int][bool]$Init) SKIP_NGINX=$([int][bool]$SkipNginx) SKIP_CERTBOT=$([int][bool]$SkipCertbot) EMAIL_CERTBOT='$EMAIL'"

    Write-Step 'Installation sur le VPS (code, Python, tests)'
    if ((Invoke-Ssh "$vars bash /tmp/vps-installer.sh preparer") -ne 0) { Stop-Deploy 'preparation echouee (rien n''a ete redemarre)' }

    if ($MDP) {
        if (-not (Send-Secret $MDP "cd $REMOTE/backend && .venv/bin/python scripts/definir_env.py MOT_DE_PASSE_PAGES")) {
            Stop-Deploy 'enregistrement du mot de passe impossible'
        }
        $MDP = $null
        Write-Ok 'mot de passe des pages enregistre sur le VPS'
    }

    Write-Step 'Demarrage sur le VPS'
    if ((Invoke-Ssh "$vars bash /tmp/vps-installer.sh demarrer") -ne 0) { Stop-Deploy 'demarrage echoue (voir ci-dessus)' }
}
finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    $MDP = $null
}

Write-Host ''
Write-Host '============================================' -ForegroundColor Green
Write-Host "  VEILLE en ligne : https://$FQDN" -ForegroundColor Green
Write-Host '============================================' -ForegroundColor Green
Write-Host '  Arretez VEILLE sur le PC et le Mac (une seule instance a la fois).'
Write-Host "  Journaux : ssh -i `"$CLE`" $CIBLE `"pm2 logs veille --lines 30 --nostream`""
exit 0
