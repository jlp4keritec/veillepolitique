# VEILLE

Système personnel de veille politique et médiatique (France, focus Lyon / Auvergne-Rhône-Alpes).
Référence : *Cahier des spécifications fonctionnelles v1.0*.

Principe : les agents IA **proposent**, les règles de J **décident**, l'exécuteur **agit**.

## Démarrer (Windows)
| Script | Rôle |
|---|---|
| `start-backend.cmd` | Installe si besoin et lance l'API + les tâches automatiques (http://127.0.0.1:8710) |
| `test-backend.cmd` | Lance les tests (doivent tous passer) |
| `relancer-tout.cmd` | Ferme, teste, relance |
| `backup-veille.bat` | Sauvegarde ZIP dans `C:\veille-backups\` |

## Démarrer (Mac) — double-clic dans le Finder
| Script | Rôle |
|---|---|
| `start-backend.command` | Installe si besoin et lance VEILLE |
| `test-backend.command` | Lance les tests |
| `relancer-tout.command` | Ferme, teste, relance |
| `backup-veille.command` | Sauvegarde ZIP dans `~/veille-backups/` |
| `deploy-veille.command` | Mise en ligne sur le VPS (voir `docs/DEPLOIEMENT.md`) |

Configuration : `backend\.env` (Mac : `backend/.env`) (voir `docs/livraisons/README-2026-11-22-mvp.md`).

## Fonctionnement
Toutes les 5 min : collecte RSS → filtrage → classification → regroupement → tendance,
score, vérification → alerte si critique. Chaque minute : briefing 08:00, synthèse 20:00,
point de veille toutes les 2 h. Toutes les 5 s : lecture des commandes Telegram de J.

## Pages de lecture
http://127.0.0.1:8710/ — accueil, archives, fiche événement (score expliqué), recherche.
Mot de passe : `MOT_DE_PASSE_PAGES` dans `backend/.env` (vide = pas de protection, en local seulement).

## API locale (documentation interactive : http://127.0.0.1:8710/docs)
`/api/v1/health` · `sources` · `parametres` · `themes` · `evenements` · `articles` ·
`notifications` · `journal` · `couts` · `question` · `cycle` · `syntheses/{type}` · `pause` · `reprise`

## État
Version 0.7.0 : MVP + pages (bulles d aide, Comment ca marche) + journal quotidien + e-mail + mise en ligne VPS depuis le PC ou le Mac (`docs/DEPLOIEMENT.md`). Voir `CHANGELOG.md`.
