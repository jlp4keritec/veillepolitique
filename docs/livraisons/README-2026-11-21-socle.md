# Livraison 2026-11-21 - Socle technique (v0.1.0)

**Fonction livrée :** socle technique + registre des sources.
**Références cahier :** préparation de **F01 Collecte** et de **F11 Paramètres**
(fiche source du ch. 4.2). Rien n'est encore « opérationnel » côté veille.

## Ce que ça fait
- Crée la base SQLite et la table `sources` : nom, URL, type, catégorie, niveau,
  zone, fiabilité, priorité, fréquence, actif/inactif, dernière collecte, dernière erreur.
- Ajoute 17 sources par défaut (fichier `backend/app/data/sources_defaut.json`).
  - 10 actives (flux RSS presse nationale + régionale + Vie-publique).
  - 7 inactives : sites institutionnels dont le flux RSS reste à identifier.
  - **Toutes marquées `url_verifiee = 0`** : je n'ai pas pu les tester d'ici.
    Elles seront testées à l'étape F01.
- Relancer le seed = sans danger : il n'ajoute que les sources absentes,
  ne touche jamais à vos modifications.
- API locale sur http://127.0.0.1:8710 (uniquement votre PC) :
  - `/api/v1/health` : état, nombre de sources, clés renseignées (oui/non, jamais la valeur).
  - `/api/v1/sources` : liste des sources.
  - `/docs` : documentation interactive.

## Installation
```powershell
Expand-Archive -Force .\veille_maj_20261121.zip -DestinationPath C:\
```
Puis double-clic sur `C:\veille\start-backend.cmd` (1re fois : création de l'environnement Python, quelques minutes).
Le fichier `backend\.env` est créé : renseignez-y vos clés plus tard (jamais dans le chat).

## Vérification
1. `test-backend.cmd` → doit afficher `7 passed` puis `[OK] Tous les tests passent.`
2. Ouvrir http://127.0.0.1:8710/api/v1/health → `"status":"ok"`, `"sources":17`, `"sources_actives":10`.

## Sécurité
- `.env` et la base sont exclus de git et du backup.
- L'API écoute seulement sur 127.0.0.1.

## Coût
0 € : aucun appel externe.

## Commit
```
git add -A ; git commit -m "socle-v0.1.0 : base SQLite, registre des sources, API sante, scripts Windows" ; git push
git log --oneline -5
```
