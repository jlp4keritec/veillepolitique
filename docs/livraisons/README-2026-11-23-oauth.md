# Livraison 2026-11-23 k — Vrai accès OAuth pour Claude (v0.12.0)

**Fonction : F09 (questions sur l'historique via Claude).**

## Quoi
- Le connecteur Claude.ai se branche par **OAuth** : Claude ouvre une page VEILLE, tu te connectes avec
  **ton mot de passe des pages** et tu cliques **Autoriser**. Personne d'autre ne peut autoriser.
- Accès **lecture seule** (8 outils), jeton 1 h renouvelé automatiquement 30 jours.
- **Réglages > Accès** : clients autorisés, dernier usage, bouton **Révoquer**.
- **LILY inchangée** : son jeton fixe marche comme avant.

## Testé ici
- 155 tests (8 nouveaux : parcours complet, PKCE, renouvellement, révocation, refus, LILY inchangée).
- Bout en bout avec le **client MCP officiel** (OAuth complet) et avec le **client MCP de LILY** : OK.
- **Non testé** : le vrai connecteur Claude.ai sur ton VPS.

## Installation (PowerShell)
```
Expand-Archive -Force "$HOME\Downloads\veille_maj_20261123k.zip" -DestinationPath C:\
```
`test-backend.cmd` → `155 passed`, `backup-veille.bat` (choix 2), commit, `deploy-veille.bat`.
Pas de nouvelle bibliothèque.

## Dans Claude
Customize > Connectors > **Add custom connector** → nom `veille`, adresse `https://veille.mesoutilsagile.com/mcp`,
rien dans « Advanced settings » → **Add** → **Connect** → page VEILLE : mot de passe → **Autoriser**.

## Commit
```
cd C:\veille ; git add -A ; git commit -m "oauth-v0.12.0 : acces OAuth au serveur MCP pour Claude, page Acces" ; git tag -a v0.12.0 -m "v0.12.0 - OAuth MCP" ; git push ; git push origin v0.12.0
git log --oneline -5
```
