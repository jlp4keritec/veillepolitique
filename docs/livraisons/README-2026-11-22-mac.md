# Livraison 2026-11-22 b — Scripts Mac (v0.2.1)

**Fonction livrée :** outillage de lancement Mac (aucune fonction F01-F12 modifiée).
Mêmes rôles que les scripts Windows, qui restent en place.

| Script (double-clic) | Rôle |
|---|---|
| `start-backend.command` | Python 3.12-3.14, crée `backend/.venv`, `.env`, base + règles + sources, lance sur http://127.0.0.1:8710 |
| `test-backend.command` | Crée l'environnement si besoin, lance les tests (`nopause` possible) |
| `relancer-tout.command` | Ferme le port 8710, teste, relance dans une nouvelle fenêtre Terminal, ouvre la page de santé |
| `backup-veille.command` | ZIP dans `~/veille-backups/` (jamais `.env`, `.venv`, caches) |
| `_commun.sh` | Fonctions partagées — ne pas lancer |

## Installation (Mac)
```
cd ~ && unzip -o ~/Downloads/veille_maj_20261121.zip && unzip -o ~/Downloads/veille_maj_20261122.zip && unzip -o ~/Downloads/veille_maj_20261122b.zip
```
Puis double-clic sur `~/veille/test-backend.command` (1re fois : installation, quelques minutes).

Si le Mac refuse d'ouvrir un script : `chmod +x ~/veille/*.command ~/veille/_commun.sh`,
puis clic droit → Ouvrir.

## Vérification
1. `test-backend.command` → `51 passed` puis `[OK] Tous les tests passent.`
2. `relancer-tout.command` → le navigateur affiche `"status":"ok"`, `"planificateur":true`.

## Commit
```
cd ~/veille && git add -A && git commit -m "mac-v0.2.1 : scripts de lancement, tests et sauvegarde pour Mac" && git push
git log --oneline -5
```
