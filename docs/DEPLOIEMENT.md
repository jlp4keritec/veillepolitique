# Mise en ligne de VEILLE sur le VPS (depuis le Mac)

## Avant le premier déploiement (une seule fois)
1. **DNS chez OVH** : zone `mesoutilsagile.com` → ajouter un enregistrement **A** :
   `veille` → `151.80.232.214`. (Quelques minutes à quelques heures pour être actif.)
2. **Fichier de connexion** : copier `deploy/deploy-config.example.json` en
   `~/veille/deploy-config.json` et mettre le chemin de **ta clé SSH du Mac** dans `sshKeyPath`
   (ex. `~/.ssh/id_ed25519`). Jamais de mot de passe SSH. Ce fichier n'est pas dans git.
3. Vérifier que le port `5710` est libre sur le VPS (sinon changer `appPort`) :
   `ssh ubuntu@151.80.232.214 'ss -ltn | grep 5710 || echo libre'`

## Premier déploiement
```
~/veille/deploy-veille.command --init --copier-base
```
- `--copier-base` : reprend ton historique et tes réglages du Mac (facultatif).
- Le script demande : l'e-mail pour le certificat HTTPS, puis le **mot de passe des pages**
  (12 caractères minimum, tapé deux fois, jamais affiché).
- Il fait : tests sur le Mac → envoi (sans `.env` ni base) → installation → tests sur le VPS →
  démarrage PM2 → contrôle de santé (retour arrière auto si KO) → Nginx → HTTPS → sauvegarde à 03:15.

Puis ouvrir **https://veille.mesoutilsagile.com** et **arrêter VEILLE sur le Mac**
(une seule instance à la fois).

## Mises à jour
```
~/veille/deploy-veille.command
```

## E-mail (facultatif)
Sur le VPS, dans `~/veille/backend/.env` : `SMTP_HOTE=smtp.gmail.com`, `SMTP_PORT=587`,
`SMTP_UTILISATEUR`, `EMAIL_DESTINATAIRE`. Le mot de passe d'application Google se pose sans
l'écrire dans une commande :
```
ssh -t ubuntu@151.80.232.214 'cd ~/veille/backend && read -rsp "Mot de passe application : " P && printf %s "$P" | .venv/bin/python scripts/definir_env.py SMTP_MOT_DE_PASSE && cd ~/veille && (pm2 delete veille; VEILLE_PORT=5710 pm2 start ecosystem.config.cjs && pm2 save)'
```
(taper le mot de passe puis Entrée ; rien ne s'affiche.)

## Diagnostic
```
ssh ubuntu@151.80.232.214 'pm2 status'
ssh ubuntu@151.80.232.214 'pm2 logs veille --lines 30 --nostream'
curl https://veille.mesoutilsagile.com/api/v1/health
ssh ubuntu@151.80.232.214 'ls ~/backups/veille | tail -3'
```
