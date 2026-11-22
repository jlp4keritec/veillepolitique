# Livraison 2026-11-22 g — Design « Glassy Dashboard » (v0.3.1)

**Fonction livrée :** F10 Historique (pages de lecture) — apparence uniquement.
Reprise de ton artefact « Glassy Dashboard », en version compacte, avec les polices de l'appareil
(option B : aucun appel à Google).

- Accueil : 4 indicateurs avec mini-courbes (données réelles par heure), Top 24 h avec pastilles
  de score et de vérification, alertes du jour, thèmes des 24 h, dernier briefing.
- Fiche événement : 6 critères du score en barres, vérification, tendance (15 min / 1 h / 24 h).
- Encart « Budget IA » dans la barre latérale.
- Réglage `nom_affiche` (défaut : Jean-Luc).

Contenu, sécurité, mot de passe : inchangés.

## Installation (Mac)
```
cd ~ && unzip -o ~/Downloads/veille_maj_20261122g.zip
```
Puis `~/veille/relancer-tout.command`.

## Vérification
1. `~/veille/test-backend.command` → `76 passed`.
2. http://127.0.0.1:8710/ → fond bleu nuit, cartes en verre, Top 24 h en pastilles.

## Commit
```
cd ~/veille && git add -A && git commit -m "glassy-v0.3.1 : design Glassy Dashboard compact pour les pages de lecture" && git push
git log --oneline -5
```
