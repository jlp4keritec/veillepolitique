# Livraison 2026-11-22 h — Diffusion e-mail, kit VPS, sources (v0.4.0)

**Fonctions livrées :** F05-F08 (diffusion e-mail + messages courts avec lien),
mise en ligne VPS (fonctionnement sans intervention quotidienne, cahier ch. 13),
F01 (nouvelles sources), F12 inchangé.

Procédure complète : `docs/DEPLOIEMENT.md`.

## Ce qui a été testé ici (simulation, pas ton vrai VPS)
- 89 tests automatiques.
- Installateur VPS exécuté sur un faux serveur : 1er déploiement, 3 mises à jour, version qui
  casse les tests (refusée, ancienne gardée), version qui ne démarre pas (retour arrière auto),
  démarrage refusé sans mot de passe.
- Lanceur Mac complet (ssh simulé) : mot de passe jamais affiché, bien enregistré sur le VPS,
  copie de la base du Mac (réglages retrouvés).
- **Non testé** : vraie connexion SSH, Nginx, Certbot, PM2 réels, vrais flux des nouvelles sources.

## Installation (Mac)
```
cd ~ && unzip -o ~/Downloads/veille_maj_20261122h.zip; xattr -d com.apple.quarantine ~/veille/*.command ~/veille/_commun.sh 2>/dev/null; chmod +x ~/veille/*.command ~/veille/_commun.sh ~/veille/deploy/*.sh; ~/veille/relancer-tout.command
```

## Vérification
1. `relancer-tout.command` → `89 passed`, accueil ouvert.
2. http://127.0.0.1:8710/api/v1/sources → 19 sources ; après 5 min, `url_verifiee` des nouvelles.

## Commit
```
cd ~/veille && git add -A && git commit -m "vps-v0.4.0 : diffusion e-mail, messages courts, kit de deploiement VPS, nouvelles sources" && git push
git log --oneline -5
```
