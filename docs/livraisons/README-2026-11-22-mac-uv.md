# Livraison 2026-11-22 d — Scripts Mac : installation fiable (v0.2.3)

**Fonction livrée :** outillage Mac (aucune fonction F01-F12 modifiée).

`_commun.sh` (utilisé par tous les `.command`) :
- installe avec `uv` s'il est présent (sinon pip) ;
- recrée tout seul un environnement abîmé ou trop ancien ;
- réinstalle tout seul les bibliothèques quand `requirements.txt` change
  (sur Mac, plus besoin de supprimer `backend/.venv`).

Testé : installation avec uv, sans uv, relance sans changement, liste modifiée, environnement abîmé.

## Installation (Mac)
```
cd ~ && unzip -o ~/Downloads/veille_maj_20261122d.zip
```

## Vérification
`~/veille/test-backend.command` → `61 passed`.

## Commit
```
cd ~/veille && git add -A && git commit -m "mac-uv-v0.2.3 : installation avec uv, environnement auto-repare" && git push
git log --oneline -5
```
