# Livraison 2026-11-23 g — Serveur MCP + conservation de la base (v0.10.0)

**Fonctions : F09 (questions sur l'historique, via Claude / LILY), F10 (historique), F12 (exploitation).**

## Quoi
### Serveur MCP (lecture seule) — `https://veille.mesoutilsagile.com/mcp`
Claude ou LILY peuvent interroger VEILLE avec 8 outils :
| Outil | Sert à |
|---|---|
| `veille_evenements` | événements récents classés par score, raisons, vérification, sources |
| `veille_evenement` | dossier complet d'un événement (chronologie, liens) |
| `veille_rechercher` | chercher dans l'historique (mots, thème, zone, acteur, dates) |
| `veille_sujet` | suivre un sujet jour par jour |
| `veille_journal` | le Journal d'un jour (top tel qu'il était) |
| `veille_syntheses` | briefings, synthèses, points, alertes |
| `veille_etat` / `veille_sources` | état du système, revue de presse |
- **Rien ne peut être modifié** par ce canal. Chaque réponse porte ses sources et ses liens.
- Accès par **jeton** (MCP_TOKEN) ; sans jeton, fermé. Voir `docs/DEPLOIEMENT.md` → « Serveur MCP ».

### Conservation (Réglages > Score et horaires > Collecte, budget et conservation)
- Gardé **pour toujours** : événements, synthèses, alertes, Journal, coûts, historique des réglages.
- Après **12 mois** : le texte des extraits est retiré (titre, lien, source, date gardés).
- Messages techniques gardés **90 jours**. Entretien chaque nuit à **03:45**, compactage une fois par mois.
- « Comment ça marche » affiche la taille de la base et sa projection sur un an.

## Testé ici
- 139 tests ; client MCP **officiel** (Python, v2.3.0) branché en HTTP : connexion, liste des outils,
  appels, avec jeton en en-tête et dans l'adresse ; pages toujours protégées par le mot de passe.
- **Non testé** : sur le VPS, avec Claude.ai et avec LILY.

## Installation (PowerShell)
```
Expand-Archive -Force "$HOME\Downloads\veille_maj_20261123g.zip" -DestinationPath C:\
```
`test-backend.cmd` → `139 passed`, `backup-veille.bat` (choix 2), commit, `deploy-veille.bat`.
Puis créer le jeton MCP sur le VPS (commande dans `docs/DEPLOIEMENT.md`).

## Commit
```
cd C:\veille ; git add -A ; git commit -m "mcp-v0.10.0 : serveur MCP lecture seule, conservation de la base" ; git tag -a v0.10.0 -m "v0.10.0 - MCP et conservation" ; git push ; git push origin v0.10.0
git log --oneline -5
```
