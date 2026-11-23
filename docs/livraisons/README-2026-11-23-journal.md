# Livraison 2026-11-23 d — Journal quotidien (v0.6.0)

**Fonction livrée : F10 (historique)** — page Journal.

## Quoi
- Menu **Journal** : choisir un jour (← →, calendrier) et voir :
  - le **top 10** de ce jour (score, raisons du score, vérification, sources avec liens) ;
  - les chiffres mesurés (articles, retenus, nouveaux événements, alertes, coût IA) ;
  - tous les messages du jour (briefing, points, synthèse, alertes), cliquables.
- Chaque soir à **23:55** (Paris), l'exécuteur **photographie** le top : il reste tel qu'il était,
  même si les scores changent ensuite. Serveur arrêté à 23:55 → photo rattrapée au redémarrage (signalée).
- Jour sans photo (avant cette version) : « reconstitué » avec les scores actuels, signalé clairement.
- Aucun appel IA. Règles modifiables : `heure_journal`, `journal_taille_top`
  (http://127.0.0.1:8710/docs → `PUT /api/v1/parametres/{cle}`).

## Fichiers
- nouveaux : `backend/app/quotidien.py`, `backend/app/templates/journal.html`,
  `backend/tests/test_journal_quotidien.py`
- modifiés : `backend/app/db.py`, `parametres.py`, `orchestrateur.py`, `pages.py`, `__init__.py`,
  `templates/base.html`, `CHANGELOG.md`, `README.md`

## Testé ici
- 96 tests (7 nouveaux), aussi avec une horloge simulée au 20/11 et au 10/12.
- Titre piégé `<script>` échappé dans la page ; liens non http(s) écartés.
- **Non vérifié** : rendu visuel dans ton navigateur.

## Installation (PowerShell)
```
Expand-Archive -Force "$HOME\Downloads\veille_maj_20261123d.zip" -DestinationPath C:\
```
`C:\veille\test-backend.cmd` → `96 passed`. Puis `backup-veille.bat` (choix 2).

## Mise en ligne
```
C:\veille\deploy-veille.bat
```
Puis https://veille.mesoutilsagile.com/journal

## Commit
```
cd C:\veille ; git add -A ; git commit -m "journal-v0.6.0 : journal quotidien F10, photo du top a 23:55" ; git tag -a v0.6.0 -m "v0.6.0 - journal quotidien" ; git push ; git push origin v0.6.0
git log --oneline -5
```
