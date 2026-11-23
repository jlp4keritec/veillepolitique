# Livraison 2026-11-23 c — Déploiement depuis le PC (v0.5.0)

**Fonction livrée :** mise en ligne sur le VPS depuis Windows (cahier ch. 13, fonctionnement
sans intervention quotidienne), au service de F05-F08 (diffusion) et F10 (pages).

## Fichiers
- nouveaux : `deploy-veille.ps1`, `deploy-veille.bat`, `deploy-config.json` (hors git)
- modifiés : `ecosystem.config.cjs`, `deploy/vps-installer.sh`, `deploy-veille.command`,
  `deploy/deploy-config.example.json`, `docs/DEPLOIEMENT.md`, `CHANGELOG.md`

## Testé ici (simulation, pas ton vrai VPS)
- Analyse du script PowerShell : 0 erreur.
- Faux VPS : 1er déploiement avec copie de base ; port occupé → arrêt ; VEILLE absent sans -Init → arrêt ;
  mise à jour. Mot de passe reçu intact (accents compris, sans retour à la ligne). Paquet sans
  `.env`, base ni config. Script VPS converti en fins de ligne Unix.
- **Non testé** : vraie connexion SSH, Windows PowerShell 5.1 réel, Nginx, Certbot, PM2.

## Installation (PowerShell)
```
Expand-Archive -Force "$HOME\Downloads\veille_maj_20261123c.zip" -DestinationPath C:\
```

## Avant le déploiement
1. `C:\veille\test-backend.cmd` → `89 passed`.
2. `C:\veille\backup-veille.bat` → choix 2.
3. Commit + tag (ci-dessous).

## Premier déploiement
```
C:\veille\deploy-veille.bat -Init
```
Puis https://veille.mesoutilsagile.com et arrêter VEILLE sur le PC.

## Commit
```
cd C:\veille ; git add -A ; git commit -m "deploy-pc-v0.5.0 : deploiement VPS depuis le PC, port 5727" ; git tag -a v0.5.0 -m "v0.5.0 - deploiement depuis le PC" ; git push ; git push origin v0.5.0
git log --oneline -5
```
