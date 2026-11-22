# Livraison 2026-11-22 f — Pages de lecture + mot de passe (v0.3.0)

**Fonction livrée :** F10 Historique (consultation web) + lecture des F05-F08 (alertes, points,
briefing, synthèse). Lecture seule.

| Page | Contenu |
|---|---|
| `/` | état, alertes du jour, top 24 h, dernier briefing ou synthèse |
| `/archives` | briefings, synthèses, points, alertes (filtre par type, 50 par page) |
| `/lecture/N` | un message en entier, avec liens vers les sources |
| `/evenement/N` | score détaillé (6 critères + raisons), tendance, vérification, chronologie |
| `/recherche` | mots, thème, zone, dates |
| `/connexion` | seulement si `MOT_DE_PASSE_PAGES` est rempli |

## Mot de passe
- `backend/.env` → `MOT_DE_PASSE_PAGES=` (la ligne est ajoutée automatiquement au démarrage).
- **Vide sur ton Mac** (pages accessibles depuis ce Mac seulement). **Obligatoire sur le VPS** (long, unique).
- Session 30 jours ; 5 essais ratés en 15 min = blocage ; changer le mot de passe déconnecte tout.
- Quand il est rempli : pages + API protégées, sauf `/api/v1/health`.

## Installation (Mac)
```
cd ~ && unzip -o ~/Downloads/veille_maj_20261122f.zip
```
requirements.txt a changé : sur Mac, le script réinstalle tout seul (jinja2).
Sous Windows : supprimer `backend\.venv` puis relancer `start-backend.cmd`.

## Vérification
1. `~/veille/test-backend.command` → `76 passed`.
2. `~/veille/relancer-tout.command` → le navigateur ouvre http://127.0.0.1:8710/
3. Cliquer un événement du Top 24 h → « Pourquoi ce score » détaillé.
4. Le briefing apparaît sur l'accueil après 08:00 (ou dans Archives).

## Commit
```
cd ~/veille && git add -A && git commit -m "pages-v0.3.0 : pages de lecture, archives, fiche evenement, recherche, mot de passe" && git push
git log --oneline -5
```
