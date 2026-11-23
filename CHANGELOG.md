# CHANGELOG - VEILLE

## [0.4.1] - 2026-11-23 - Installation sur PC Windows

### Corrige
- Les messages (alertes, points, briefings) sont dates avec l'heure du traitement, et non
  l'heure de l'ordinateur au moment de l'ecriture (meme valeur en usage reel ; coherence des tests).
- Test test_horloge_synthese_et_points : il ne passait que si la date du jour etait avant le
  23/11/2026. Un evenement deja alerte n'est pas repete dans le point suivant : le test utilise
  desormais un evenement sous le seuil d'alerte.

### Ajoute
- .gitattributes : scripts .sh/.command toujours en fins de ligne Unix, .cmd/.bat/.ps1 en Windows
  (evite qu'un commit fait depuis le PC casse les scripts du VPS).
- docs/livraisons/README-2026-11-23-pc.md : installation sur un PC neuf.

## [0.4.0] - 2026-11-22 - Diffusion e-mail, kit VPS, nouvelles sources

### Ajoute
- Diffusion (F05-F08) : canal e-mail (SMTP, Gmail compatible) en plus de Telegram ; un seul
  destinataire (J). Messages courts avec lien "Lire en entier" vers les pages si URL_PUBLIQUE
  est renseignee (archive toujours complete). Un canal en panne n'empeche pas l'autre.
- Kit de mise en ligne VPS pilote depuis le Mac : deploy-veille.command (--init, --copier-base),
  deploy/vps-installer.sh, ecosystem.config.cjs (PM2), vhost Nginx, Certbot, sauvegarde
  quotidienne de la base (30 gardees), tests executes sur le VPS, retour arriere automatique.
- Garde-fou : ENVIRONNEMENT=vps refuse de demarrer sans MOT_DE_PASSE_PAGES (12 caracteres).
- scripts/sauvegarde_db.py (copie coherente + verification), scripts/definir_env.py (secret
  lu sur l'entree standard, jamais en argument).
- Sources : Vie-publique Discours publics, LCP Assemblee nationale ; Senat (communiques de presse)
  et Le Progres activés avec leur flux. Notes "pas de flux trouve" pour Elysee, Gouvernement,
  Assemblee, Metropole, Region.

### Securite
- Les tests n'utilisent jamais les secrets du vrai .env (aucun e-mail, Telegram ni appel IA reel).
- deploy-config.json exclu de git ; le paquet de deploiement est verifie (ni .env ni base).

## [0.3.1] - 2026-11-22 - Design "Glassy Dashboard"

### Modifie
- Pages : design Glassy Dashboard de J (fond bleu nuit, halos indigo/cyan/magenta, cartes en verre),
  version compacte, polices de l'appareil (aucun appel a Google Fonts).
- Barre laterale (ordinateur) / barre du haut (telephone), encart Budget IA avec jauge.
- Accueil : 4 indicateurs avec mini-courbes mesurees (articles et evenements par heure sur 24 h),
  pastilles de couleur pour score et verification, repartition des themes sur 24 h.
- Fiche evenement : les 6 criteres du score en barres de progression, tableau des fenetres de tendance.
- Nouveau parametre nom_affiche (prenom sur l'accueil).

## [0.3.0] - 2026-11-22 - Pages de lecture (F10) + mot de passe

### Ajoute
- Pages web en lecture seule : accueil (etat, alertes du jour, top 24 h, dernier briefing),
  archives (briefings, syntheses, points, alertes), lecture d'un message, fiche evenement
  (score detaille par critere, tendance, verification, chronologie et liens), recherche F10.
- Protection par mot de passe (MOT_DE_PASSE_PAGES dans .env) : vide = pas de protection (usage local) ;
  renseigne = pages ET API protegees sauf /api/v1/health ; session 30 jours (cookie signe, HttpOnly) ;
  blocage apres 5 essais rates en 15 min ; changer le mot de passe deconnecte tout le monde.
- Securite : contenu collecte echappe (2 protections), liens limites a http(s), pas de redirection
  vers un autre site, pages non indexees par les moteurs de recherche.
- 9 tests (76 au total).

### Modifie
- requirements.txt : + jinja2, markupsafe.
- relancer-tout (Mac et Windows) : ouvre la page d'accueil.

## [0.2.4] - 2026-11-22 - Reglages classement, 2e passe sur donnees reelles

### Modifie
- A. F02 : titre court fait uniquement de noms propres ("Marine Le Pen") = page sujet, ecarte.
- B. F02 : un theme trouve seulement dans le resume exige 2 mots-cles differents
  (parametre theme_resume_mots_min) ; 1 mot-cle dans le titre suffit.
- C. Theme Pouvoir d'achat : + "vie chere", "cout de la vie" (si le theme n'a pas ete modifie par J).
- D. F03 : dans un nom compose, seul le dernier mot compte comme nom propre ; les prenoms
  ("Marine", "Jean-Luc") ne comptent pas comme mots communs.
- E. F03 : les nombres (2027, 49.3) ne comptent pas pour regrouper.

### Ajoute
- 6 tests sur les vrais titres (Darmanin / Tondelier, Gelinotte, vie chere) : 67 tests.

## [0.2.2] - 2026-11-22 - Reglage du classement sur donnees reelles

### Modifie (constats du 1er test reel)
- F03 Regroupement : comparaison des titres par token_sort (seuil 83) ; ajout d'une regle
  "nom propre rare" (ex. Moutouh) + 3 mots communs. Nouveaux parametres mot_rare_*.
- F02 Type d'evenement deduit du TITRE seulement (parametre type_depuis_resume).
- F04 Acteur cite dans le titre = points pleins ; seulement dans le resume = moitie.
- Verification : conditionnel ("serait", "pourrait") cherche dans le titre ; dans le resume,
  seulement les mots explicites (parametre marqueurs_rumeur_texte).
- F02 Titres de moins de 3 mots (pages sujet) ecartes (parametre titre_mots_min).
- Theme International : pays ajoutes ; actualite etrangere sans acteur francais = moins de points.
- Mise a jour des valeurs par defaut UNIQUEMENT si J ne les a pas modifiees.

### Ajoute
- scripts/reclasser.py : reapplique les regles aux articles recents, sans toucher aux evenements alertes.
- 10 tests construits sur les vrais titres du 21/11 (61 tests au total).

## [0.2.1] - 2026-11-22 - Scripts Mac

### Ajoute
- `start-backend.command`, `test-backend.command`, `relancer-tout.command`, `backup-veille.command`
  et `_commun.sh` (fonctions partagees) : memes roles que les scripts Windows.
- `.gitignore` : exclusion de `.DS_Store`.

### Inchange
- Code de VEILLE et requirements.txt : aucune modification.

## [0.2.0] - 2026-11-22 - MVP phase 1 (a valider en conditions reelles)

### Ajoute
- F01 Collecte RSS : frequence par source, ETag/Last-Modified, taille max, extrait court,
  erreurs journalisees, nouvelle tentative avec delai croissant, URL verifiee au 1er succes.
- F02 Filtrage et classification par regles : themes, zone Lyon/AURA, acteurs publics,
  type d'evenement, mots exclus.
- F03 Deduplication (URL, guid, titre) et regroupement en evenements (similarite des titres).
- Tendances mesurees (15 min / 1 h / 24 h), score sur 100 explicable (6 criteres du cahier),
  statuts de verification du cahier 5.5 (rumeur = "a confirmer").
- F05 Alertes Telegram critiques : jamais deux fois, mise a jour seulement si element nouveau.
- F06 Point de veille toutes les 2 h (08:00-22:00), F07 briefing 08:00, F08 synthese 20:00,
  rattrapage 3 h apres interruption.
- Agents Claude (optionnels) : propositions de classification + resume validees par les regles,
  resume executif, reponses aux questions. Protection anti-injection.
- F09 Questions en francais (Telegram ou API), F10 historique / chronologie / recherche.
- F11 Regles modifiables (42 parametres + 21 themes) par Telegram /param et par l'API.
- F12 Couts : mesure par appel et par agent, plafond mensuel bloquant, alertes 80 % et 100 %.
- Commandes Telegram : /etat /sources /source_on /source_off /pause /reprise /params /param
  /couts /top /evenement /cherche /point /briefing /soir + questions libres.
- API locale : sources, parametres, themes, evenements, articles, notifications, journal, couts,
  question, cycle, syntheses, pause/reprise.
- Planificateur interne (APScheduler), sans outil externe.

### Modifie
- requirements.txt : ajout feedparser, rapidfuzz, apscheduler, tzdata.
- Base : nouvelles tables, migration douce (aucune donnee effacee).

### Limites connues
- Flux RSS par defaut non testes en reel (non accessibles depuis l'environnement de dev).
- Pas de detection "contradictoire" automatique (statut reserve), pas d'agenda, pas de X (phase 2).

## [0.1.0] - 2026-11-21 - Socle technique

### Ajoute
- Arborescence `backend/` (Python + FastAPI) et `frontend/` (vide, phase dashboard).
- Configuration par `backend/.env` (modele `.env.example`), secrets exclus de git.
- Base SQLite `backend/data/veille.db` avec la table `sources` (cahier 4.2).
- 17 sources par defaut (10 actives, 7 inactives "flux a identifier"), adresses NON verifiees.
- Seed idempotent : relance sans doublon, ne modifie jamais une source existante.
- API locale (127.0.0.1:8710) : `GET /api/v1/health`, `GET /api/v1/sources`.
- Scripts Windows : `start-backend.cmd`, `test-backend.cmd`, `relancer-tout.cmd`, `backup-veille.bat/.ps1`.
- 7 tests automatiques.

### Non inclus (etapes suivantes)
- Aucune collecte, aucun appel a Claude, aucun envoi Telegram. Cout : 0 EUR.
