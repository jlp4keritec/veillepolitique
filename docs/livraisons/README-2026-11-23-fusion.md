# Livraison 2026-11-23 j — Fusion des livraisons parallèles (v0.11.1)

**Fonctions : F01 (collecte : flux officiels, lecteur Élysée), F09 (MCP compatible LILY).**

## Pourquoi
Deux conversations ont livré en parallèle le 23/11 : la `h` « flux officiels » et la `i` « lecteur Élysée »
d'un côté, la `h` « outils MCP compatibles LILY » de l'autre (même numéro 0.10.1). Celle-ci les réunit.

## Contient
- Flux officiels : Gouvernement, Assemblée nationale (comptes rendus), Métropole de Lyon (0.10.1).
- Lecteur de page Élysée, 1 lecture par heure, titre/date/type/lien seulement (0.11.0).
- Outils MCP renommés pour le filtre de lecture de LILY : 8 outils gardés (0.10.1 MCP).
- CHANGELOG complet, version unique 0.11.1.

## Testé ici
- 147 tests, aussi avec horloges simulées (20/11 et 10/12) ; vérification automatique du code sans erreur.

## Installation (PowerShell) — seule, par-dessus ce que tu as déjà
```
Expand-Archive -Force "$HOME\Downloads\veille_maj_20261123j.zip" -DestinationPath C:\
```
`C:\veille\test-backend.cmd` → `147 passed`, `backup-veille.bat` (choix 2), puis `deploy-veille.bat`.
Pas de changement de requirements.txt.

## Commit
```
cd C:\veille ; git add -A ; git commit -m "fusion-v0.11.1 : flux officiels + lecteur Elysee + outils MCP compatibles LILY" ; git tag -a v0.11.1 -m "v0.11.1 - fusion" ; git push ; git push origin v0.11.1
git log --oneline -5
```
