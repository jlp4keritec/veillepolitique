# Livraison 2026-11-23 h — Flux officiels retrouvés (v0.10.1)

**Fonction livrée : F01 (Collecte)** — registre des sources.

## Quoi
3 sources « désactivées » ont un vrai flux RSS officiel (ouvert et vérifié le 23/11/2026) :

| Source | Flux |
|---|---|
| Gouvernement - info.gouv.fr | https://www.info.gouv.fr/rss/actualites.xml |
| Assemblée nationale - Comptes rendus des séances | https://www2.assemblee-nationale.fr/feeds/detail/crs |
| Métropole de Lyon | https://www.grandlyon.com/actualites.xml |

- Au démarrage, la base est mise à jour **seulement si tu n'as pas touché** à l'ancienne ligne
  (type site, désactivée, même adresse). Sinon le flux est ajouté à côté : rien n'est écrasé.
- Élysée : toujours pas de flux (discours via Vie-publique). Région AURA : son `/rss.xml` est
  technique (fiches d'aides), laissé désactivé.
- Réglages par défaut (fréquence 60/60/120 min, niveau 1, fiabilité 5) : modifiables par toi.

## Fichiers modifiés
`backend/app/data/sources_defaut.json`, `backend/app/sources.py`, `backend/app/__init__.py`,
`backend/tests/test_socle.py`, `CHANGELOG.md`, ce README.

## Testé ici
- 140 tests passent (1 nouveau : mise à jour d'une base existante, sans doublon, sans écraser).
- **Non vérifié** : lecture réelle depuis ton PC/VPS. info.gouv.fr a refusé un robot pendant mes
  essais (ouvert sans souci dans un navigateur) → regarder la colonne **État** après la 1re collecte.

## Installation (PowerShell)
```
Expand-Archive -Force "$HOME\Downloads\veille_maj_20261123h.zip" -DestinationPath C:\
```
`C:\veille\test-backend.cmd` → `140 passed`. Pas de changement de requirements.txt ni package.json.

## Mise en ligne
```
C:\veille\deploy-veille.bat
```
Puis https://veille.mesoutilsagile.com/fonctionnement → les 3 sources « ok » après leur 1re lecture.

## Commit
```
cd C:\veille ; git add -A ; git commit -m "flux-officiels-v0.10.1 : info.gouv.fr, Assemblee nationale et Metropole de Lyon en RSS (F01)" ; git push
git log --oneline -5
```
