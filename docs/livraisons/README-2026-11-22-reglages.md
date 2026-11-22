# Livraison 2026-11-22 c — Réglage du classement (v0.2.2)

**Fonctions livrées :** F02 Filtrage · F03 Déduplication/regroupement · F04 Scoring (réglages),
d'après le premier test réel du 22/11 (10 sources, ~130 événements).

| # | Constat réel | Correction |
|---|---|---|
| 1 | Affaire Moutouh éclatée en 3 événements | nom propre rare commun + 3 mots communs → même événement ; comparaison des titres plus stricte (token_sort, seuil 83) |
| 2 | CFDT classé « vote » | type déduit du titre seulement |
| 3 | CFDT 25/25 « institutionnel » | acteur du titre = points pleins, du résumé = moitié |
| 4 | « Bruno Retailleau » « à confirmer » | conditionnel cherché dans le titre ; dans le résumé, seulement les mots explicites |
| 5 | Titre « Bruno Retailleau » (page sujet) | titres de moins de 3 mots écartés |
| 6 | Bolsonaro = Justice | pays ajoutés au thème International, moins de points pour l'actualité étrangère |

Toutes ces valeurs sont des règles modifiables (`titre_mots_min`, `type_depuis_resume`,
`marqueurs_rumeur_texte`, `mot_rare_*`, `seuil_similarite_titre`).
Tes réglages déjà modifiés ne sont jamais écrasés.

## Installation (Mac)
```
cd ~ && unzip -o ~/Downloads/veille_maj_20261122c.zip
```
requirements.txt inchangé : pas besoin de recréer `.venv`.

Puis, pour appliquer les nouvelles règles aux articles déjà collectés (3 derniers jours) :
```
cd ~/veille/backend && .venv/bin/python scripts/reclasser.py
```
Les événements déjà alertés ne sont jamais modifiés. Relancer le script est sans danger.

## Vérification
1. `~/veille/test-backend.command` → `61 passed`.
2. `~/veille/relancer-tout.command`
3. http://127.0.0.1:8710/api/v1/evenements?limite=15 → l'affaire Moutouh = 1 seul événement.

## Commit
```
cd ~/veille && git add -A && git commit -m "reglages-v0.2.2 : regroupement par nom rare, type et acteurs depuis le titre, rumeurs, pages sujet, international" && git push
git log --oneline -5
```
