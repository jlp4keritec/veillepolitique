# Livraison 2026-11-22 e — Réglages classement, 2e passe (v0.2.4)

**Fonctions livrées :** F02 Filtrage · F03 Regroupement (réglages sur données réelles).

| # | Constat réel | Correction | Test |
|---|---|---|---|
| A | page « Marine Le Pen » gardée | titre court uniquement en noms propres = écarté | ✅ |
| B | « La Gélinotte va fermer » = Justice | thème du résumé seul : 2 mots-clés différents requis | ✅ |
| C | « vie chère à Lyon » sans thème | + vie chère, coût de la vie | ✅ |
| D | Darmanin (Marine **Le Pen**) rangé avec Marine **Tondelier** | seul le nom de famille compte ; prénoms ignorés | ✅ |
| E | « 2027 » comptait comme mot commun | nombres ignorés | ✅ |

Règle modifiable : `theme_resume_mots_min` (défaut 2).

## Installation (Mac)
```
cd ~ && unzip -o ~/Downloads/veille_maj_20261122e.zip
cd ~/veille/backend && .venv/bin/python scripts/reclasser.py 7
```

## Vérification
1. `~/veille/test-backend.command` → `67 passed`.
2. `~/veille/relancer-tout.command`
3. http://127.0.0.1:8710/api/v1/articles?q=gagnera → noter `evenement_id`, puis
   http://127.0.0.1:8710/api/v1/evenements/<id> → l'article Darmanin est seul.

## Commit
```
cd ~/veille && git add -A && git commit -m "reglages2-v0.2.4 : pages sujet, themes du resume, vie chere, prenoms et nombres ignores" && git push
git log --oneline -5
```
