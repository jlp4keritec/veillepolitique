# Livraison 2026-11-23 i — Lecteur de page : Élysée (v0.11.0)

**Fonction livrée : F01 (Collecte)** — lecteur de page pour les sites officiels sans flux RSS.

## Quoi
- Nouvelle source **Élysée - Toutes les actualités** (https://www.elysee.fr/toutes-les-actualites),
  lue **1 fois par heure**.
- On garde seulement : **date, type** (Article, Communiqué de presse…), **titre, lien**.
  Jamais l'article entier, jamais la recherche du site (interdite par son robots.txt).
- Le type est rangé dans l'extrait : tu peux t'en servir dans tes règles (ex. mot-clé « communiqué »).
  **Aucun changement de score par défaut** : c'est toi qui décides.
- Site refait / page méconnaissable → la source passe en **erreur** dans « Comment ça marche ».
  Rien n'est inventé.
- Coût : 0 €, aucune IA. Aucune nouvelle bibliothèque.
- Base existante : l'ancienne ligne « Elysee » désactivée est convertie automatiquement
  (sauf si tu l'avais modifiée).

**Écart au cahier, validé par toi** : le cahier privilégie API et RSS ; ici lecture d'une page HTML.

Cette livraison contient aussi la v0.10.1 (flux info.gouv.fr, Assemblée, Métropole) si tu ne l'as pas encore installée.

## Fichiers
- nouveaux : `backend/app/lecteurs.py`, `backend/tests/test_lecteurs.py`, ce README
- modifiés : `backend/app/collecte.py`, `sources.py`, `__init__.py`, `data/sources_defaut.json`,
  `backend/tests/test_socle.py`, `CHANGELOG.md`, `docs/livraisons/README-2026-11-23-flux-officiels.md`

## Testé ici
- 146 tests passent (6 nouveaux : extraction, doublons, page changée, site sans lecteur, conversion base).
- La page test reproduit la structure vue sur le vrai site le 23/11.
- **Non vérifié** : lecture réelle du site depuis ton VPS → regarder la colonne **État** après 1 h.

## Installation (PowerShell)
```
Expand-Archive -Force "$HOME\Downloads\veille_maj_20261123i.zip" -DestinationPath C:\
```
`C:\veille\test-backend.cmd` → `146 passed`. Pas de changement de requirements.txt ni package.json.

## Mise en ligne
```
C:\veille\deploy-veille.bat
```
Puis https://veille.mesoutilsagile.com/fonctionnement → « Elysee - Toutes les actualites » : **ok**.

## Commit
```
cd C:\veille ; git add -A ; git commit -m "lecteur-elysee-v0.11.0 : lecteur de page pour sites sans flux, Elysee (F01)" ; git tag -a v0.11.0 -m "v0.11.0 - lecteur de page Elysee" ; git push ; git push origin v0.11.0
git log --oneline -5
```
