# Livraison 2026-11-23 f — Réglages (v0.8.0) + IA locale, double avis, banc d'essai (v0.9.0)

**Fonctions : F11 (règles de J), F12 (IA et coûts), F04 (score), F02 (classement).**

## Quoi
### Page Réglages (menu)
- **Score et horaires** : pondération du score avec **aperçu** avant d'enregistrer, seuils, horaires, collecte, budget.
- **Modèle IA** : IA locale (bandit), Claude, OpenRouter ; modèles par agent avec relais ; Tester ; liste des modèles ;
  **double avis** (taux d'accord IA / tes règles) ; **banc d'essai** (1 ou 2 modèles, mesures).
- **Listes**, **Thèmes**, **Sources** : modifiables, avec ajout.
- **Historique** : tout changement (page, API, Telegram) daté, annulable.

### Règles de fonctionnement
- L'IA **propose**, tes règles **tranchent** : en cas de désaccord, la règle gagne et l'article est marqué « avis divergents ».
- Relais : IA locale → Claude → règles seules. Bandit éteint = pause de 10 min, rien ne bloque.
- Budget : 50 € tout compris = **20 € IA en ligne + 30 € X** (l'IA locale est gratuite). Modifiable.

## Testé ici
- 129 tests (40 nouveaux depuis la v0.7.0), aussi avec horloges simulées (20/11 et 10/12).
- Navigateur (Chrome) : page Réglages complète, aperçu de pondération, onglet Modèle avec une **fausse IA locale**
  sur le réseau (Tester = JSON valide, liste des modèles, banc d'essai terminé).
- **Non testé** : ton vrai bandit (Ollama + VPN), une vraie clé Claude/OpenRouter.

## Installation (PowerShell)
```
Expand-Archive -Force "$HOME\Downloads\veille_maj_20261123f.zip" -DestinationPath C:\
```
`C:\veille\test-backend.cmd` → `129 passed`, puis `backup-veille.bat` (choix 2).
Pas de nouvelle bibliothèque (requirements.txt inchangé).

## Mise en ligne puis réglage de bandit
1. `C:\veille\deploy-veille.bat`
2. https://veille.mesoutilsagile.com/reglages?onglet=modele → adresse `http://10.10.0.2:11434` → Enregistrer → **Tester**.
3. Lancer un **banc d'essai** (40 articles) pour mesurer `ministral-3:3b`.

## Commit
```
cd C:\veille ; git add -A ; git commit -m "reglages-ia-v0.9.0 : page Reglages, IA locale, relais, double avis, banc d'essai" ; git tag -a v0.9.0 -m "v0.9.0 - reglages et IA locale" ; git push ; git push origin v0.9.0
git log --oneline -5
```
