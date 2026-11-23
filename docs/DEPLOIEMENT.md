# Mise en ligne de VEILLE sur le VPS

Port interne : **5727** (5710 est pris par un autre service du VPS). Dossier : `/home/ubuntu/veille`.
Une seule instance à la fois : une fois le VPS en route, arrêter VEILLE sur le PC et le Mac.

## Depuis le PC Windows (poste principal)

### Avant (une seule fois)
1. **DNS chez OVH** : enregistrement **A** `veille` → `151.80.232.214` (fait).
2. **`C:\veille\deploy-config.json`** : propre à VEILLE (clé SSH, `remoteDir` = `/home/ubuntu/veille`,
   `appPort` = 5727). Jamais de mot de passe SSH. Hors git. Le script refuse tout autre `remoteDir`.

### Avant chaque déploiement
`test-backend.cmd` vert → `backup-veille.bat` (choix 2) → CHANGELOG à jour → commit + push + tag.

### Premier déploiement
```
C:\veille\deploy-veille.bat -Init
```
- Demande : l'e-mail du certificat HTTPS, puis le **mot de passe des pages** (12 caractères min.,
  tapé deux fois, jamais affiché ; envoyé au VPS par l'entrée standard, jamais écrit sur disque).
- `-CopierBase` (facultatif) : envoie la base du PC (historique, réglages).
- Fait : vérif. port → tests sur le PC → paquet `tar.gz` vérifié (ni `.env`, ni base, ni config) →
  envoi → installation et tests sur le VPS → PM2 → contrôle de santé (retour arrière auto si KO) →
  Nginx → HTTPS → sauvegarde quotidienne de la base à 03:15.

### Mises à jour
```
C:\veille\deploy-veille.bat
```
Dépannage : `-SkipNginx`, `-SkipCertbot`.

## Depuis le Mac
Mêmes étapes avec `~/veille/deploy-veille.command` (`--init`, `--copier-base`), config dans
`~/veille/deploy-config.json`.

## IA (facultatif)
- **IA locale (bandit)** : page Réglages > Modèle IA > adresse `http://10.10.0.2:11434`, puis **Tester**.
  Le VPN doit être actif sur bandit (tunnel WireGuard `kikkoai-wg0`) et Ollama démarré.
- **Clés Claude / OpenRouter** : jamais dans une page ni dans le chat. Sur le VPS, sans l'afficher :
```
ssh -t -i C:\mailou\id-ed25519 ubuntu@151.80.232.214 'cd ~/veille/backend && read -rsp "Cle : " P && printf %s "$P" | .venv/bin/python scripts/definir_env.py ANTHROPIC_API_KEY && cd ~/veille && (pm2 delete veille; VEILLE_PORT=5727 pm2 start ecosystem.config.cjs && pm2 save)'
```
(remplacer `ANTHROPIC_API_KEY` par `OPENROUTER_API_KEY` pour OpenRouter.)

## Serveur MCP (Claude, LILY)
1. Créer le jeton **sur le VPS** (il s'affiche une seule fois dans ton terminal ; ne jamais le coller dans un chat) :
```
ssh -t -i C:\mailou\id-ed25519 ubuntu@151.80.232.214 'cd ~/veille/backend && .venv/bin/python scripts/generer_jeton_mcp.py && cd ~/veille && (pm2 delete veille; VEILLE_PORT=5727 pm2 start ecosystem.config.cjs && pm2 save)'
```
2. Brancher :
   - **Claude Code** : `claude mcp add --transport http veille https://veille.mesoutilsagile.com/mcp --header "Authorization: Bearer <jeton>"`
   - **LILY** : Paramètres → Serveurs MCP → onglet des autres serveurs : id `veille`, nom `VEILLE`, adresse
     `https://veille.mesoutilsagile.com/mcp`, jeton = le jeton VEILLE → **Tester** (8 outils gardés) → **Ajouter**.
     LILY range le jeton elle-même.
   - **Claude.ai** (connecteur personnalisé, sans en-tête possible) : adresse `https://veille.mesoutilsagile.com/mcp/<jeton>`.
     Attention : une adresse contenant le jeton apparaît dans les journaux Nginx du serveur ; préférer l'en-tête quand c'est possible.
3. Vérifier : page « Comment ça marche » → « Accès Claude / LILY (MCP) : actif ».
4. Changer de jeton : même commande avec `--nouveau`, puis mettre à jour Claude / LILY.

## E-mail (facultatif)
Sur le VPS, dans `~/veille/backend/.env` : `SMTP_HOTE=smtp.gmail.com`, `SMTP_PORT=587`,
`SMTP_UTILISATEUR`, `EMAIL_DESTINATAIRE`. Le mot de passe d'application Google se pose sans
l'écrire dans une commande :
```
ssh -t -i C:\mailou\id-ed25519 ubuntu@151.80.232.214 'cd ~/veille/backend && read -rsp "Mot de passe application : " P && printf %s "$P" | .venv/bin/python scripts/definir_env.py SMTP_MOT_DE_PASSE && cd ~/veille && (pm2 delete veille; VEILLE_PORT=5727 pm2 start ecosystem.config.cjs && pm2 save)'
```
(taper le mot de passe puis Entrée ; rien ne s'affiche.)

## Diagnostic
```
ssh -i C:\mailou\id-ed25519 ubuntu@151.80.232.214 'pm2 status'
ssh -i C:\mailou\id-ed25519 ubuntu@151.80.232.214 'pm2 logs veille --lines 30 --nostream'
curl.exe https://veille.mesoutilsagile.com/api/v1/health
ssh -i C:\mailou\id-ed25519 ubuntu@151.80.232.214 'ls ~/backups/veille | tail -3'
```
