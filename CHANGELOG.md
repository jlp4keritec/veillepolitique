# CHANGELOG - VEILLE

## [0.12.0] - 2026-11-23 - Vrai acces OAuth pour le connecteur Claude (F09)

### Ajoute
- OAuth 2.1 sur le serveur MCP : metadonnees (RFC 9728, RFC 8414), enregistrement des clients (RFC 7591),
  autorisation avec PKCE S256 obligatoire, jeton d'acces 1 h, renouvellement 30 j avec rotation, revocation.
- Seul J autorise : la page d'autorisation exige le MOT DE PASSE DES PAGES puis un clic "Autoriser" (ou "Refuser").
  OAuth actif seulement si ce mot de passe est regle (VPS).
- Reglages > Acces : etat du jeton fixe et d'OAuth, clients autorises (dernier usage), bouton Revoquer.
- Teste de bout en bout avec le client MCP officiel (Python v2.3.0) : decouverte, enregistrement,
  connexion de J, autorisation, jetons, 8 outils, appel. 8 tests (155 au total).

### Securite
- Jetons et codes stockes haches (SHA-256). Un jeton OAuth n'ouvre que /mcp (pas les pages, pas l'API).
- Retours autorises : https, ou http://localhost (Claude Code). Une demande SANS jeton ne compte plus comme
  essai rate (sinon la 1re demande de Claude bloquerait l'acces).

### Inchange
- LILY : jeton fixe MCP_TOKEN accepte exactement comme avant (verifie avec le client MCP de LILY : 8 outils).

## [0.11.1] - 2026-11-23 - Fusion des livraisons paralleles + outils MCP compatibles LILY

### Fusion
- Reunit deux livraisons faites en parallele : flux officiels (0.10.1) et lecteur Elysee (0.11.0)
  d'une part, noms d'outils MCP compatibles LILY d'autre part (livre sous le meme numero 0.10.1).
  A installer seule, par-dessus n'importe laquelle des livraisons du 23/11.


### Corrige
- LILY ne branche que les outils dont le nom contient un verbe de lecture (lister, lire, consulter,
  rechercher...). 7 outils sur 8 auraient ete ignores. Nouveaux noms : veille_lister_evenements,
  veille_lire_evenement, veille_rechercher, veille_consulter_sujet, veille_lire_journal,
  veille_lister_syntheses, veille_consulter_etat, veille_lister_sources.
- Verifie avec le client MCP de LILY lui-meme (depot lily, app/mcp_serveurs.py) : 8 outils branches.

## [0.11.0] - 2026-11-23 - Lecteur de page pour les sites sans flux : Elysee (F01)

### Ajoute
- Lecteur de page (app/lecteurs.py) : pour un site officiel SANS flux RSS, lit uniquement sa page liste
  et garde date, type, titre et lien (jamais l'article entier, jamais la recherche du site).
  Bibliotheque standard seulement : aucune dependance ajoutee.
- Premiere source : Elysee - Toutes les actualites (https://www.elysee.fr/toutes-les-actualites),
  1 lecture par heure. robots.txt du site : page autorisee (seule la recherche est interdite).
  Le type de publication (ex. "Communique de presse") est stocke comme extrait : tes regles peuvent s'en servir.
  Aucun changement de score par defaut.
- Securites : un lecteur par site declare (sinon erreur claire) ; page sans publication reconnue
  (site refait) -> source en "erreur", rien n'est invente ; date tiree de l'adresse, jamais dans le futur ;
  liens hors elysee.fr ignores ; 50 publications max par lecture.
- Base existante : l'ancienne ligne "Elysee" desactivee passe sur la page liste (sauf si tu l'as modifiee).
- 6 tests (146 au total).

### Ecart au cahier (valide par J le 23/11/2026)
- Le cahier privilegie API et flux RSS. Lecture d'une page HTML acceptee pour l'Elysee, faute de flux.

## [0.10.1] - 2026-11-23 - Trois flux officiels retrouves (F01)

### Ajoute
- 3 sources institutionnelles passent de "desactivee" a flux RSS actif (verifies le 23/11/2026) :
  - Gouvernement : https://www.info.gouv.fr/rss/actualites.xml
  - Assemblee nationale (comptes rendus des seances) : https://www2.assemblee-nationale.fr/feeds/detail/crs
  - Metropole de Lyon : https://www.grandlyon.com/actualites.xml
- Base existante : mise a jour automatique au demarrage, SEULEMENT si J n'a pas modifie l'ancienne ligne
  (toujours "site", desactivee, meme adresse). Sinon le nouveau flux est ajoute a cote, rien n'est ecrase.
- Test de cette mise a jour (140 au total).

### Modifie
- Notes Elysee (pas de flux, reverifie) et Region AURA (flux /rss.xml technique, inutilisable).

## [0.10.0] - 2026-11-23 - Serveur MCP (lecture seule) et conservation de la base (F09, F10)

### Ajoute
- Serveur MCP VEILLE (https://veille.mesoutilsagile.com/mcp) pour Claude, LILY ou tout client MCP :
  8 outils en LECTURE SEULE (veille_evenements, veille_evenement, veille_rechercher, veille_sujet,
  veille_journal, veille_syntheses, veille_etat, veille_sources). Chaque resultat porte ses sources et
  ses liens, et rappelle que les contenus collectes sont des donnees, jamais des instructions.
  Transport Streamable HTTP sans etat (reponses JSON). Teste avec le client MCP officiel (Python, v2.3.0).
- Acces par jeton MCP_TOKEN (.env) : en-tete "Authorization: Bearer" (LILY, Claude Code) ou adresse
  /mcp/<jeton> (connecteur Claude.ai). Sans jeton : ferme (404). Essais rates bloques, 120 appels/min max.
  scripts/generer_jeton_mcp.py cree le jeton et l'affiche une seule fois dans ton terminal.
- Conservation (reglable dans Reglages) : texte des extraits d'articles retire apres 12 mois (titre, lien,
  source, date, classement gardes), messages techniques purges apres 90 jours, entretien de nuit a 03:45,
  compactage de la base une fois par mois. Evenements, syntheses, alertes, Journal, couts : pour toujours.
- "Comment ca marche" : taille de la base, rythme d'articles par jour, projection sur un an (apres 3 jours
  de mesure), dates du dernier entretien et compactage, etat de l'acces MCP.
- Tests MCP et conservation (139 au total).

## [0.9.0] - 2026-11-23 - IA locale ou en ligne, relais, double avis, banc d'essai (F12)

### Ajoute
- IA multi-fournisseurs : IA locale Ollama (bandit via le VPN, gratuite), Claude (Anthropic), OpenRouter.
  Par agent (classement, syntheses, questions), une liste de modeles essayes dans l'ordre (relais) ;
  sans reponse : regles seules. IA locale injoignable -> mise en pause 10 min (pas de cycle ralenti).
- Double avis IA / regles sur le classement : accord -> retenu ; regles vides -> l'IA complete (dans la
  liste de J) ; desaccord -> les regles tranchent, article marque "avis divergents" (bulle d'aide).
  Chaque comparaison est mesuree (table avis_ia) et affichee (taux d'accord sur 30 jours).
- Banc d'essai (Reglages > Modele IA) : 1 ou 2 modeles sur N articles recents ; mesure reponses valides,
  accord avec les regles, accord entre modeles, temps par lot. Tache de fond, articles jamais modifies.
- Onglet Reglages > Modele IA : etat des fournisseurs (cles presentes ou non, jamais affichees),
  modeles par agent, adresse de l'IA locale, bouton Tester, liste des modeles disponibles, derniers appels.
- Configuration : OPENROUTER_API_KEY (.env) ; parametres ia_local_url, ia_routage, ia_local_timeout_s,
  prix OpenRouter (estimation prudente), budget_x_eur (30 EUR, phase X).
- Couts : colonne fournisseur ; l'IA locale compte 0 EUR et n'est jamais bloquee par le budget.
- 14 tests.

### Modifie
- Budget : 50 EUR tout compris = IA en ligne 20 EUR + veille X 30 EUR. budget_mensuel_eur passe de 50 a 20
  SEULEMENT si J ne l'avait pas modifie. Encart du menu : "IA en ligne".
- Historique des propositions IA : modele utilise (ex. local:ministral-3:3b).

### Securite
- Les cles ne passent jamais par une page : uniquement le .env du serveur.

## [0.8.0] - 2026-11-23 - Page Reglages (F11)

### Ajoute
- Page Reglages (menu), onglets : Score et horaires, Listes, Themes, Sources, Historique.
- Ponderation du score : curseurs, total = 100 obligatoire, APERCU du top 24 h avec les nouveaux poids
  (les deux colonnes calculees au meme instant : seul l'effet des poids apparait), alerte signalee si un
  evenement passerait le seuil. Enregistrement : evenements des 48 h recalcules ; photos du Journal intactes.
- Seuils et alertes, horaires, collecte et budget, prenom : chaque section validee entierement (tout ou rien).
- Listes (personnalites suivies, mots exclus, mots regionaux, mots a fort impact, partis/acteurs locaux).
- Themes : mots-cles, actif/inactif, ajout (jamais de suppression) ; bouton "Reappliquer mes regles aux
  3 derniers jours" (evenements deja alertes jamais touches).
- Sources : active, fiabilite, priorite, frequence ; ajout d'un flux RSS.
- Historique de tous les changements (page, API, Telegram) avec bouton Annuler ; retour aux valeurs par defaut.
- 13 tests.

### Securite
- Formulaires proteges contre la falsification (jeton + cookie SameSite=Strict).
- Ajout de source (page ET API) : adresses privees refusees (serveur, VPN 10.x, maison 192.168.x,
  127.0.0.1, 169.254.x) : le serveur ne peut pas etre utilise pour sonder ton reseau.

## [0.7.0] - 2026-11-23 - Bulles d'aide et page "Comment ca marche" (F04, F10)

### Ajoute
- Bulles d'aide (survol a la souris, toucher sur telephone) sur l'accueil, le Journal et la fiche evenement :
  score (niveau + 6 criteres : points, maximum, raison), verification (sens du statut + raison),
  tendance (calcul mesure par fenetre), theme/zone/type (mots-cles trouves, part de l'IA), rang du Journal.
  Seuils affiches = reglages en vigueur.
- Page "Comment ca marche" (/fonctionnement, menu) : parcours d'une information, fiche par agent
  (role, entrees, sorties, IA ou non, qui decide, reglages en vigueur), echelle des scores, tendances,
  statuts de verification, revue de presse (sources : type, niveau, zone, fiabilite, frequence, etat).
  Generee en direct depuis la base.
- Classement : les mots-cles trouves (titre / resume), la raison de la zone et du type sont enregistres
  (colonne articles.classif_details). Articles anterieurs : "mots non conserves".
- Journal : chaque photo garde aussi le detail du score, la raison de verification et le calcul de tendance.
- 6 tests (102 au total).

## [0.6.0] - 2026-11-23 - Journal quotidien (F10)

### Ajoute
- Page Journal (/journal, menu) : un jour au choix (fleches ou calendrier), son top (score,
  raisons, verification, sources et liens), ses chiffres mesures (articles collectes et retenus,
  nouveaux evenements, alertes, cout IA) et tous ses messages (briefing, points, synthese, alertes).
- Photo quotidienne du top par l'executeur a heure_journal (23:55 par defaut), jamais modifiee
  ensuite ; rattrapage de la veille au redemarrage si le serveur etait arrete (signale).
- Jours sans photo : classement recalcule avec les scores actuels, affiche "reconstitue".
- Parametres : heure_journal (23:55), journal_taille_top (10). Table journal_quotidien.
- 7 tests (96 au total).

### Modifie
- Version affichee : 0.6.0 (0.4.0 auparavant).

## [0.5.0] - 2026-11-23 - Deploiement depuis le PC Windows

### Ajoute
- deploy-veille.ps1 + deploy-veille.bat : mise en ligne sur le VPS depuis le PC (-Init, -CopierBase,
  -SkipNginx, -SkipCertbot). Verifie le port avant tout envoi, tests locaux obligatoires, paquet tar.gz
  controle (ni .env, ni base, ni deploy-config.json, ni chemin Windows), mot de passe des pages envoye
  par l'entree standard (jamais affiche, ecrit ou journalise). Reutilise deploy/vps-installer.sh.
- deploy-config.json propre a VEILLE (hors git) ; le script refuse tout remoteDir autre que
  /home/ubuntu/veille.

### Modifie
- Port interne par defaut 5710 -> 5727 (5710 occupe sur le VPS) : ecosystem.config.cjs,
  vps-installer.sh, deploy-veille.command, deploy-config.example.json, docs/DEPLOIEMENT.md.
- docs/DEPLOIEMENT.md : procedure PC en premier.

## [0.4.1] - 2026-11-23 - Installation sur PC Windows

### Corrige
- Les messages (alertes, points, briefings) sont dates avec l'heure du traitement, et non
  l'heure de l'ordinateur au moment de l'ecriture (meme valeur en usage reel ; coherence des tests).
- Test test_horloge_synthese_et_points : il ne passait que si la date du jour etait avant le
  23/11/2026. Un evenement deja alerte n'est pas repete dans le point suivant : le test utilise
  desormais un evenement sous le seuil d'alerte.
- Test test_definir_env : la verification des droits du fichier .env (600) ne s'applique
  plus sous Windows, qui ne gere pas ces droits (toujours verifiee sur le VPS et le Mac).

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
