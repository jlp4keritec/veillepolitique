# Livraison 2026-11-22 — MVP phase 1 (v0.2.0)

**Fonctions livrées :** F01 Collecte · F02 Filtrage · F03 Déduplication · F04 Scoring ·
F05 Alertes · F06 Point de veille · F07 Briefing 08:00 · F08 Synthèse 20:00 ·
F09 Questions · F10 Historique · F11 Paramètres · F12 Coûts.

**Statut : codé et testé avec des données simulées (51 tests). PAS encore « opérationnel »**
tant que le test réel n'a pas réussi chez J (vrais flux RSS, vrai bot, vraie clé).

## Qui fait quoi (modèle respecté)
| Rôle | Ce qu'il fait | Fichier |
|---|---|---|
| Règles de J | seuils, sources, thèmes, mots-clés, horaires, budget | `app/parametres.py` (modifiables) |
| Agent collecte | lit les flux RSS | `app/collecte.py` |
| Agent classification | règles + proposition Claude **validée** | `app/classification.py`, `app/ia.py` |
| Agent tendances / score / vérification | calcul **mesuré**, raisons affichées | `app/analyse.py` |
| Agent synthèse | alertes, points, briefing, soir | `app/syntheses.py` |
| Orchestrateur | enchaîne, planifie | `app/orchestrateur.py` |
| Exécuteur | envoi Telegram, archivage | `app/telegram.py`, `app/alertes.py` |

L'IA ne décide jamais : pas de score, pas d'envoi, pas de réglage. Une proposition IA hors
des listes de J est rejetée (trace dans `historique` de l'article).

## Installation
```powershell
Expand-Archive -Force .\veille_maj_20261122.zip -DestinationPath C:\
```
**requirements.txt a changé** → supprimer `C:\veille\backend\.venv` puis relancer `start-backend.cmd`.

## Configuration (dans `backend\.env`, jamais dans le chat)
1. **Bot Telegram** : dans Telegram, ouvrir @BotFather → `/newbot` → copier le token dans `TELEGRAM_BOT_TOKEN`.
2. **Votre identifiant** : envoyer un message à @userinfobot → copier le nombre « Id » dans `TELEGRAM_CHAT_ID`.
3. Envoyer `/start` à VOTRE bot (sinon il ne peut pas vous écrire).
4. **Clé Claude** (facultative) : console.anthropic.com → API Keys → `ANTHROPIC_API_KEY`.
   Sans clé : tout marche par règles, sans résumé IA.
5. Relancer `relancer-tout.cmd`.

Sans token Telegram, les messages sont archivés en mode « simulé » (visibles dans
http://127.0.0.1:8710/api/v1/notifications).

## Vérification
1. `test-backend.cmd` → `51 passed`, `[OK] Tous les tests passent.`
2. http://127.0.0.1:8710/api/v1/health → `"planificateur": true`, `"dernier_cycle"` renseigné.
3. Après 5 min : http://127.0.0.1:8710/api/v1/sources → regarder `url_verifiee` et `derniere_erreur`
   de chaque source. Envoyer une capture : je corrigerai les adresses en erreur.
4. Telegram : `/etat`, puis `/top`, puis « Que s'est-il passé aujourd'hui ? ».

## Règles par défaut à connaître (toutes modifiables : `/params`, `/param cle valeur`)
- Alerte critique : score ≥ 85 et (≥ 2 sources ou source institutionnelle ou source unique fiabilité ≥ 4).
- Mise à jour d'alerte : +10 points ou +2 sources, 3 mises à jour maximum.
- Points de veille : toutes les 2 h entre 08:00 et 22:00, seulement s'il y a du nouveau
  (**choix ajouté**, le cahier ne précise pas la nuit → `/param plage_points 00:00-23:59` pour 24 h/24).
- IA : modèle `claude-haiku-5-5`, 20 articles max par cycle, budget 50 €/mois bloquant.
  Prix 0,10 $ / 0,50 $ par million de tokens (à vérifier sur la page de prix Anthropic).

## Sécurité
- Le bot ne répond qu'à votre identifiant ; les autres messages sont ignorés et journalisés.
- Contenus collectés = données : balisés, neutralisés, jamais exécutés.
- Le token n'apparaît jamais dans les journaux.
- L'API n'a pas de mot de passe : elle écoute seulement sur 127.0.0.1. **Ne pas l'ouvrir sur internet.**
- **Une seule instance à la fois** (PC ou VPS) : deux instances = alertes en double et bot en conflit.

## Limites connues
- Adresses RSS par défaut non testées en réel. 7 sources institutionnelles inactives (flux à identifier).
- Statut « contradictoire » non détecté automatiquement ; pas d'agenda du jour ; pas de X (phase 2).
- Déploiement VPS : pas fait (étape suivante, après validation locale).

## Commit
```
git add -A ; git commit -m "mvp-v0.2.0 : collecte RSS, classement, score, alertes Telegram, syntheses, questions, couts" ; git push
git log --oneline -5
```
