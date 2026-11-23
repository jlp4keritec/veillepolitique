# Livraison 2026-11-23 h — Outils MCP compatibles LILY (v0.10.1)

**Fonction : F09 (questions sur l'historique via LILY / Claude).**

## Quoi
LILY ne branche que les outils « de lecture », reconnus à leur nom (lister, lire, consulter, rechercher…).
Les outils VEILLE sont renommés pour être tous gardés : `veille_lister_evenements`, `veille_lire_evenement`,
`veille_rechercher`, `veille_consulter_sujet`, `veille_lire_journal`, `veille_lister_syntheses`,
`veille_consulter_etat`, `veille_lister_sources`.

## Testé ici
- 140 tests (1 nouveau : les noms passent le filtre de lecture de LILY).
- Le **client MCP de LILY** (copie de ton dépôt lily) branché sur VEILLE en local : 8 outils gardés, appel réussi.

## Installation (PowerShell)
```
Expand-Archive -Force "$HOME\Downloads\veille_maj_20261123h.zip" -DestinationPath C:\
```
`test-backend.cmd` → `140 passed`, sauvegarde, commit, `deploy-veille.bat`.

## Dans LILY
Paramètres → Serveurs MCP → autres serveurs : id `veille`, nom `VEILLE`, adresse `https://veille.mesoutilsagile.com/mcp`,
jeton VEILLE → Tester → Ajouter.

## Commit
```
cd C:\veille ; git add -A ; git commit -m "mcp-lily-v0.10.1 : noms d'outils MCP compatibles avec le filtre de lecture de LILY" ; git tag -a v0.10.1 -m "v0.10.1 - MCP compatible LILY" ; git push ; git push origin v0.10.1
git log --oneline -5
```
