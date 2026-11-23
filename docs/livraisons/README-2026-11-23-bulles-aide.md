# Livraison 2026-11-23 e — Bulles d'aide et « Comment ça marche » (v0.7.0)

**Fonctions : F04 (score explicable), F10 (historique / consultation).**

## Quoi
- **Bulles d'aide** (souris : survol ; téléphone : toucher) sur l'accueil, le Journal et la fiche événement :
  - **score** : niveau + les 6 critères (points / maximum / raison) ;
  - **vérification** : ce que veut dire le statut + pourquoi ici ;
  - **tendance** : le calcul mesuré (articles par fenêtre, avant / maintenant) ;
  - **thème · zone** (souligné en pointillés) : mots-clés trouvés, raison de la zone et du type, part de l'IA ;
  - **rang** dans le Journal.
- **Page « Comment ça marche »** (menu) : parcours d'une information, fiche de chaque agent, échelle des scores,
  tendances, statuts de vérification, ta revue de presse (sources et leur état). Générée en direct.
- Les mots-clés trouvés sont enregistrés **à partir de cette version** (anciens articles : « mots non conservés »).

## Testé ici
- 102 tests (6 nouveaux) ; contenu piégé `<script>` échappé dans les bulles.
- Rendu vérifié dans Chrome (ordinateur + téléphone) sur des données de test.

## Installation (PowerShell)
```
Expand-Archive -Force "$HOME\Downloads\veille_maj_20261123e.zip" -DestinationPath C:\
```
`C:\veille\test-backend.cmd` → `102 passed`, puis `backup-veille.bat` (choix 2).

## Mise en ligne
`C:\veille\deploy-veille.bat` puis https://veille.mesoutilsagile.com/fonctionnement

## Commit
```
cd C:\veille ; git add -A ; git commit -m "aide-v0.7.0 : bulles d'aide et page Comment ca marche" ; git tag -a v0.7.0 -m "v0.7.0 - bulles d'aide" ; git push ; git push origin v0.7.0
git log --oneline -5
```
