# Livraison 2026-11-23 b — Correctif test sous Windows (v0.4.1)

**Fonction :** outils de mise en ligne VPS (cahier ch. 13, secrets du `.env`) — test uniquement.

## Quoi
`test_definir_env` vérifiait les droits Unix du `.env` (600). Windows ne les gère pas : le test
échouait sur le PC (`438 == 384`). La vérification ne s'applique plus que sur le VPS et le Mac.
Aucun changement du code de VEILLE.

## Installation (PowerShell)
```
Expand-Archive -Force "$HOME\Downloads\veille_maj_20261123b.zip" -DestinationPath C:\
```

## Vérification
`C:\veille\relancer-tout.cmd` → `89 passed`, accueil ouvert.

## Commit
```
cd C:\veille ; git add -A ; git commit -m "pc-v0.4.1 : installation PC, v0.4.0 complete, correctifs date des messages et test Windows" ; git push
git log --oneline -5
```
