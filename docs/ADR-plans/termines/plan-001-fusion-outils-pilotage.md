# Plan 001 — Fusion des outils de pilotage

ADR : [ADR-001](../../ADR/termines/001-fusion-outils-pilotage.md) (Accepté le 2026-11-10). Un seul jeu à la fois (`--wait-idle 3600`). Chaque
étape : bancs unitaires, luacheck sur le mod, test en jeu automatique si l'étape touche le lancement ou le mod (code de
sortie, ligne `summary` et dossier `runs\` cités), commit unique sur demande explicite.

## Tableau de bord

| # | Étape | Statut | Dépend de | Décisions ADR | Taille | Parallélisable avec |
|---|---|---|---|---|---|---|
| 0 | Étude (lecture seule) | Terminée (2026-11-10) | — | — | M | — |
| 1 | Document de conception et arbitrages | Terminée (2026-11-10, ADR accepté) | 0 | D11-D14 | M | — |
| 2 | Squelette du projet, barrière de publication, empreinte des données réelles | Terminée (2026-11-11, recette de l'écran d'envoi dispensée par l'utilisateur) | 1 | D01, D05 | S | — |
| 3 | Lanceur déplacé dans la CLI, pilote renommé, alias `pz_autotest.py`/`pzat` | Terminée (2026-11-11) | 2 | D04, D07, D10 | L | — |
| 4 | Canal live et mode attaché, `lua`, `repl`, `attach` | Terminée (2026-11-11) | 3 | D03, D07 | M | 6 |
| 5 | `World` fusionné, sous-commandes `world` | Terminée (2026-11-11) | 4 | D06, D10 | M | — |
| 6 | Journaux : `logs` | Terminée (2026-11-11) | 3 | — | S | 4 |
| 7 | Moteur de scénarios intégré, `scenario`, alias `PZPuppet` | Terminée (2026-11-11) | 5 | D08, D09 | L | — |
| 8 | Productions PZDirector, `film` sans ZombieBuddy, alias `PZDirector` | Terminée (2026-11-11) | 7 | D02 | L | — |
| 9 | Tournage : `Tuto`, `record`, `take`, `quit`, `sheet`, `assemble` | Terminée (2026-11-11) | 5 | D06, Q03 | M | 7 |
| 10 | Étape finale : migration des appelants, skills, retrait des alias Python et `pztuto_*`, archivage | Terminée (2026-11-11) | 3-9 | D07, Q04 | L | — |

## Fiches

### Étape 2 — Squelette, barrière, empreinte
Création du projet (`Contents\mods\batman_PZDevKit\{common,42.21}`, `mod.info` DEV-ONLY, fichier témoin, `README.md`),
`git init` selon Q02, refus dans `steam_workshop_publish.py`, script d'empreinte SHA-256 de `Saves`, `options.ini`,
`mods.txt` réels.
**Sortie** : `steam_workshop_publish.py PZDevKit` refuse (code ≠ 0) ; test unitaire du refus ; empreinte calculée et
rangée. Écran d'envoi du jeu : protocole court pour l'utilisateur (le dossier doit être refusé à « Suivant »).

**Preuves (2026-11-10)** :
- Vert : `python -m unittest discover -s tests` (dans `PZDevKit`) → `Ran 10 tests … OK` (7 empreinte, 3 refus de
  publication).
- `python .claude/tools/steam_workshop_publish.py PZDevKit` → `Bloquant : projet DEV-ONLY …`, code 1.
- Empreinte réelle : `pzdev.py fingerprint save fingerprints/reference-2026-11-10.json` → 72 500 fichiers en 3,7 s ;
  `check` immédiat → `identical`, code 0. Dossier `fingerprints/` ignoré par git (liste de noms de sauvegardes).
- `git init -b main` fait ; aucun commit, aucun dépôt distant créé (sur demande seulement).
- Modifiés hors projet : `.claude/tools/pz_workshop_project.py` (`DEV_ONLY_MARKER`, `is_dev_only`, refus dans
  `validate`), `.claude/tools/steam_workshop_publish.py` (refus avant lecture de `workshop.txt`, qui plantait),
  `docs/agents/fiches-des-mods.md` (ligne PZDevKit).
- Recette de l'écran d'envoi du jeu : dispensée par l'utilisateur le 2026-11-11 (« considère que c'est bon »), non jouée.

Protocole (2 min, jeu lancé normalement) : menu principal → Workshop → Créer et mettre à jour des objets → choisir
`PZDevKit` → Suivant. Attendu : page d'erreur (aperçu introuvable ou fichier interdit dans Contents), aucun envoi.

### Étape 3 — Lanceur
Déplacement de `pzat/*` dans `cli/pzdev/` ; pilote Lua déplacé dans le mod (`Driver*`), id `batman_PZDevKit` ajouté
en dernier ; correction `getGameMode` avec test ; `pz_autotest.py` et `pzat` deviennent des alias ; 42 tests
existants déplacés et verts.
**Sortie** : bancs verts ; `pzdev check` vert sur les dix `autotest.json` (inchangés, empreinte git) ; `pzdev sp
SignalSmoke`, `pzdev server SignalSmoke`, `pzdev mp SignalSmoke --clients 1` puis `--clients 2` : code 0 cités ;
`pz_autotest.py sp SignalSmoke` (alias) : code 0 ; empreinte des données réelles identique. (Serveur : voir preuves, BeltRadio.)

**Preuves (2026-11-11)** :
- Déplacements : `pzat/{core,runner,winproc}.py` → `cli/pzdev/{core,launcher,winproc}.py`, `pz_autotest.py` →
  `cli/pzdev/autotest.py` (branché sur `pzdev sp|server|mp|check`) ; pilote → `shared/PZDevKit/Driver.lua`,
  `client/PZDevKit/DriverClient.lua`, `server/PZDevKit/DriverServer.lua` (table `PZDevKit.Driver`, id
  `batman_PZDevKit` ajouté en dernier) ; 42 tests repris (`test_core`, `test_launcher` ex-`test_runner`,
  `test_driver_lua`, `fake_game.py`) ; README de pz-autotest déplacé en `docs/wiki/fr/01-tests-automatiques.md`.
- Alias : `.claude/tools/pz-autotest/pz_autotest.py` délègue à `pzdev.autotest` ; `pzat.core|runner|winproc` sont les
  modules `pzdev.core|launcher|winproc` (`sys.modules`, même objet). Tests `test_aliases.py` (2).
- Corrections 42.22 (test rouge puis vert, dans `test_driver_lua.py`) :
  - `getGameMode()` renvoie un objet `GameMode` (`toString` = id, `GameMode.java:61`) : comparaison par `tostring`.
  - Monde 42.21 (version 249) chargé en 42.22 (251, `IsoWorld.java:391`) : `MainScreen.continueLatestSaveAux` ouvre
    l'avertissement `UI_worldscreen_SavefileConversion`, que le pilote prenait pour un refus (premier essai solo : code 2,
    `SignalSmoke\runs\20261111-104217-sp-1e85eb19ae9a`). Le pilote répond OUI une fois, sur la copie du cache, et
    l'écrit dans l'état (`save conversion accepted`).
- `pzdev fingerprint` refuse (code 3) quand un jeu ou un serveur tourne (test `test_cli_refuses_while_a_game_runs`).
- Vert : `python -m unittest discover -s tests` → `Ran 57 tests … OK` ; `luacheck Contents --config .luacheckrc` →
  `0 warnings / 0 errors in 3 files`. `test_mp_server_go_after_client_hooks` (hérité, minuté) a échoué une fois sur 5
  passages pendant un passage lent (40 s au lieu de 28 s) : hypothèse, charge machine ; à surveiller.
- `pzdev check` code 0 sur les dix `autotest.json`, aucun modifié (`git status` vide dans chaque projet).
- En jeu (42.22.2, confirmé en jeu) :
  - `pzdev sp SignalSmoke` : code 0, `sp 41 PASS, 0 FAIL`, `SignalSmoke\runs\20261111-104519-sp-3bcbb9f30719`.
  - `pzdev server SignalSmoke` : code 2 après 600 s, `SignalSmoke\runs\20261111-104752-server-560d4922df54`. Cause
    (confirmé statiquement) : les hooks serveur de Signal Smoke attendent un joueur (`mp.server.join`), le projet n'a
    pas de passage serveur seul ; critère de sortie mal choisi, remplacé par BeltRadio.
  - `pzdev server BeltRadio` : code 0, `9/9 PASS`, `BeltRadio\runs\20261111-105950-server-73a4ed531ef3`.
  - `pzdev mp SignalSmoke --clients 1` : code 0, `server 36 PASS, 0 FAIL` / `client 11 PASS, 0 FAIL`,
    `SignalSmoke\runs\20261111-110035-mp-2e4313edd364`.
  - `pzdev mp SignalSmoke --clients 2` : code 0, mêmes lignes, `SignalSmoke\runs\20261111-110710-mp-1de0638f25ba`.
  - Alias `pz_autotest.py sp SignalSmoke` : code 0, `sp 41 PASS, 0 FAIL`,
    `SignalSmoke\runs\20261111-111111-sp-b68ceb81419b`.
- Empreinte : `check` contre la référence de 10:39 → 391 différences, toutes dans une seule sauvegarde personnelle,
  écrites entre 10:41:58 et 10:42:10 par une partie normale (le `console.txt` réel la montre refermée à 10:42:11 ;
  les essais écrivent le leur dans leur cache). Premier lancement à 10:42:17 ; aucun fichier modifié après 10:42:15 ;
  options, listes de mods et `Server` identiques. Défaut de méthode corrigé ci-dessus (référence prise pendant une
  partie ; contrôle `tasklist` à deux filtres, qui se combinent en ET). Nouvelle référence `after-step3.json`.

### Étape 4 — Canal live et mode attaché
`Live.lua`, `pzdev lua|repl|attach`, lecture provisoire des anciens fichiers `pztuto_*`.
**Sortie** : tests du protocole (lupa + unittest) ; en jeu (cache, `sp --no-quit`) : `return 1+1` → `-> 2`, une erreur
volontaire → `status=error` et le jeu continue, `--shot` produit un PNG ; mode attaché : protocole court à jouer par
l'utilisateur sur une partie de test (jamais annoncé sans son retour).

**Preuves (2026-11-11)** :
- Code : `client/PZDevKit/Live.lua` (canal, `PZDevKit.info`, sérialisation bornée, débogueur coupé pendant l'appel
  seulement), `cli/pzdev/live.py` (`pzdev lua|repl|attach`, cible `cache:<dir>|real`, pointeur `sp --no-quit`),
  `launcher.py` (pointeur `last-live.json`). Écart à la fiche : les anciens fichiers `pztuto_*` ne sont pas lus par
  `Live.lua` (double exécution pendant `record.py --live`) ; ils restent servis par `tuto_lib.lua` jusqu'à l'étape 9.
- Vert : `python -m unittest discover -s tests` → `Ran 80 tests … OK` (9 `test_live_lua`, 13 `test_live`, 1 pointeur
  dans `test_launcher`) ; `luacheck Contents --config .luacheckrc` → `0 warnings / 0 errors in 4 files`.
- En jeu (cache, confirmé en jeu, 42.22.2) : `pzdev sp SignalSmoke --no-quit` → code 0, `sp 41 PASS, 0 FAIL`,
  `SignalSmoke\runs\20261111-112833-sp-350428d1b68e`, partie laissée ouverte ; puis, cible par défaut :
  - `pzdev lua "return 1+1"` → `-> 2`, code 0 ;
  - `error("deliberate test error")` → `status error`, code 2 ; `return (` → `status compile-error`, code 2 ;
  - la commande suivante répond (nom du personnage, position, table `{a=1, b={c=2}}`, ligne `info`) : le jeu continue ;
  - `--shot` → PNG copié dans `runs\live\` et regardé ;
  - `getCore():quitToDesktop()` par le canal → jeu fermé.
  - Limite : l'erreur rattrapée est comptée par le jeu en mode debug (compteur « ERROR 1 », pile dans la console).
- Empreinte : `before-step4.json` → `check` après fermeture : `identical`.
- Incident : un essai `attach --target cache:/nonexistent` a créé `C:\nonexistent\Lua\pzdev\cmd.lua` (58 octets,
  `return "pong"`) ; suppression refusée par la sécurité de l'agent, laissée à l'utilisateur. Corrigé : cible absente
  refusée sans rien créer (test `test_missing_target_folder_is_refused_without_creating_it`).
- Mode attaché (confirmé en jeu, 2026-11-11) : partie de test lancée par l'utilisateur avec `-debug` et le mod ;
  `pzdev attach --target real` → `-> pong`, `attached`, code 0 ; `pzdev lua "…getUsername(), getCore():getVersion()…"
  --target real` → nom du personnage, `42.22.2 3d39148846`, position, code 0. Fichiers du canal laissés dans
  `%USERPROFILE%\Zomboid\Lua\pzdev\` (ignorés par l'empreinte).

Protocole du mode attaché (5 min, partie de test, jamais une vraie sauvegarde) : Steam → Project Zomboid →
Propriétés → Options de lancement : `-debug` ; lancer le jeu ; nouvelle partie de test avec le mod
« batman_PZDevKit (DEV-ONLY) » coché ; une fois en jeu, `python PZDevKit/pzdev.py attach --target real` (attendu :
`attached`, code 0) puis `python PZDevKit/pzdev.py lua "return getPlayer():getUsername()" --target real` (attendu : le
nom du personnage). Quitter, retirer `-debug`.

### Étape 5 — World
Fusion `PZPuppet.Debug` + aides monde de `tuto_lib` ; vérification de `addZombiesInOutfit` en 42.22 avec test ;
`pzdev world …`.
**Sortie** : tests Lua repris de `test_debug.lua` et nouveaux tests verts ; en jeu : téléportation, objet, 3 zombies,
véhicule, heure, météo vérifiés par une commande live chacun (code 0 du passage automatique).

**Preuves (2026-11-11)** :
- Code : `client/PZDevKit/World.lua` (une implémentation par aide : `PZPuppet_Debug.lua` + `clearZombies`,
  `clearBodies`, `clearSquare`, `holdWeather`, `night`, `zoom`, `speed` de `tuto_lib.lua`) ; `cli/pzdev/world.py`
  (`pzdev world <action>`). Les fonctions sources restent en place jusqu'aux étapes 7 (alias `PZPuppet.Debug`) et 9
  (`Tuto.lua` appellera `World`). `P.Scenario:teleport` part avec le moteur à l'étape 7.
- `addZombiesInOutfit` : pas de correction (surcharge à 13 paramètres présente en 42.22, `LuaManager.java:8334`,
  confirmé statiquement) ; le test vérifie l'appel à 13 paramètres. ADR D10 et étude mis à jour.
- Vert : `python -m unittest discover -s tests` → `Ran 100 tests … OK` (13 `test_world_lua` dont les 8 cas de
  `test_debug.lua` adaptés, 7 `test_world_cli` qui exécutent le Lua généré contre `World.lua`) ;
  `luacheck Contents --config .luacheckrc` → `0 warnings / 0 errors in 5 files`.
- En jeu (cache, confirmé en jeu, 42.22.2) : `pzdev sp SignalSmoke --no-quit` → code 0, `sp 41 PASS, 0 FAIL`,
  `SignalSmoke\runs\20261111-115701-sp-cb670d53eaf2` ; puis chacune code 0 :
  `world tp 10830 9446` (`pos` → `10830, 9446, 0`, capture : dehors), `world item Base.Hammer 2`,
  `world item Base.Apple --at 10831 9446 0`, `world zombies 10834 9447 0 3 --frozen`,
  `world vehicle Base.PickUpTruck 10840 9455 --key` (`id 4`), `world time 22`, `world weather storm 1`.
  Contrôle par une commande live : 2 marteaux, 1 clé, 3 zombies dans la cellule, heure 22 ; capture : 3 zombies
  debout immobiles, journal météo `STORM`. Partie fermée par le canal.
- Empreinte : `before-step5.json` → `check` après fermeture : `identical`.

### Étape 6 — Journaux
`pzdev logs` : session courante (début de session de `console.txt`), filtres, erreurs Lua, `PZAT-RESULT`, rapports.
**Sortie** : tests sur des journaux d'exemple anonymisés.

**Preuves (2026-11-11)** :
- Code : `cli/pzdev/logs.py` (`pzdev logs`). La session est le fichier entier (`console.txt` est réécrit à chaque
  démarrage) ; les chargements Lua sont comptés par le premier mod chargé. Erreur Lua : bloc `ERROR` dont une ligne
  porte `Lua(` ou `KahluaException`, réduit au message et aux cadres Lua. `--report` (rapports de scénario) passe à
  l'étape 7 avec le moteur.
- Vert : `python -m unittest discover -s tests` → `Ran 110 tests … OK` (10 `test_logs` sur
  `tests/data/console-sample.txt`, extrait anonymisé d'un vrai journal 42.22.2) ; `luacheck` → `0 warnings / 0 errors`.
- Essai sur de vrais journaux (lecture seule) : cache de l'étape 4 → `--errors` retrouve l'erreur volontaire avec
  `Live.lua:105` ; `console.txt` réel (559 mods) → deux défauts trouvés et corrigés avec test rouge puis vert :
  `--tail 0` affichait tout, liste des mods illisible (désormais 20 premiers et « +N more »).

### Étape 7 — Scénarios
Moteur PZPuppeteer dans `Scenario.lua`/`Game.lua`, `collect_reports` dans `pzdev scenario`, adaptateur MilitaryDrop
sorti (D08), alias `PZPuppet`. Les ~80 cas Lua et les 11 cas de `test_collect_reports.py` sont repris (ces derniers
entrent enfin dans la suite).
**Sortie** : bancs verts ; en jeu : `examples/01-aller-retour.lua` de PZPuppeteer lancé par `pzdev scenario run`
(rapport `passed`, code 0) ; un scénario personnel existant lancé sans modification par l'alias.

**Preuves (2026-11-11)** :
- Code : `client/PZDevKit/Scenario.lua` (ex-`PZPuppet_Core.lua`, table `PZDevKit.Scenario`), `Game.lua`
  (ex-`PZPuppet_Game.lua` + étape `:teleport` sur `PZDevKit.World`), `Compat.lua` (alias `PZPuppet`,
  `PZPuppet.Debug`, pas posé si `batman_PZPuppeteer` est actif) ; `cli/pzdev/scenario.py` (`pzdev scenario
  run|batch|status|stop`), `cli/pzdev/collect.py` (`scenario collect`, chemin par défaut sans nom d'utilisateur) ;
  exemples dans `examples/scenarios/` (01 et 02 au format fichier rechargeable) ; documentation d'écriture et de
  campagne dans `docs/wiki/en/02-…`, `03-…`. Contrats gardés : `[PZPuppet]`, `PZPuppet 0.1.0`, `Lua/PZPuppet/…`.
- Écarts : adaptateur MilitaryDrop abandonné (aucun appelant, ADR D08 mis à jour) et ses 4 cas retirés ; le décompte
  réel des cas Lua repris est 69 (40 moteur + 21 campagnes + 6 chargeur + 2 téléportation/exemple 04 ; les 7 autres cas
  de `test_debug.lua` sont à l'étape 5) ; pas de scénario personnel sans dépendance (tous exigent Opération Artemis
  ou PZDirector) : l'alias est prouvé par l'exemple 04 d'origine de PZPuppeteer, écrit en `PZPuppet.*`, non modifié ;
  les scénarios Artemis seront relancés à l'étape 10. *Mise à jour 2026-11-11* : sur demande de l'utilisateur
  (« on les refera plus tard »), les scénarios personnels Opération Artemis, OperationArtemisTrailer, PZDirector et
  Studio (75 fichiers, dont 15 absents de tout dépôt) ont été archivés dans
  `%USERPROFILE%\Zomboid\archives\pzpuppet-scenarios-artemis-pzdirector-2026-11-11.zip` (contenu vérifié octet par
  octet), puis supprimés de `Lua\PZPuppet\`. Plus aucune relance prévue à l'étape 10.
- Vert : `python -m unittest discover -s tests` → `Ran 200 tests … OK` (70 `test_scenario_lua`, 11 `test_collect`,
  7 `test_scenario_cli`, 2 `test_compat_lua`) ; `luacheck Contents --config .luacheckrc` → `0 warnings / 0 errors in
  8 files`.
- En jeu (cache, confirmé en jeu, 42.22.2) : `pzdev sp SignalSmoke --no-quit` → code 0, `sp 41 PASS, 0 FAIL`,
  `SignalSmoke\runs\20261111-121356-sp-6174e2b90453` ; `PZPuppet == PZDevKit.Scenario` et
  `PZPuppet.Debug == PZDevKit.World` → `true, true` ; après `world tp 10830 9446` :
  - `pzdev scenario run PZDevKit/examples/scenarios/01-aller-retour.lua` → `Aller-retour : passed`, 4 étapes
    réussies en 4,1 s, progression affichée par étape, code 0 ;
  - `pzdev scenario run PZPuppeteer/examples/04-equipped-fixture.lua -P itemType=Base.Hammer` (fichier d'origine,
    API `PZPuppet.*`) → `Generic equipment with fixture : passed`, code 0 ;
  - `pzdev logs --errors` : une seule erreur Lua, `handleMannequinZone` (carte vanilla, `f:0`, au chargement).
- Empreinte : `before-step7.json` → `check` après fermeture : `identical`.

### Étape 8 — Productions et film
PZDirector dans `Production.lua`, `Actions.lua`, `UI.lua` (traductions EN/FR) ; `pzdev film` (ex-`tournage.py` +
`recorder.py`) sur le lanceur en mode cache avec son ; suppression de `pzremote.py`, `PZDirector-Tournage.bat`,
`zombiebuddy-patch`, du dossier `tools/zombiebuddy` et de toute mention `-javaagent`. Les 39 cas Lua repris.
**Sortie** : bancs verts ; en jeu : `examples/stills.lua` de PZDirector tourné par `pzdev film` (code 0, captures) ;
`rg -i "zombiebuddy|javaagent"` vide dans le projet.

**Preuves (2026-11-11)** :
- Code : `client/PZDevKit/Production.lua`, `Actions.lua`, `Staging.lua`, `Demos.lua`, `UI.lua` (ex-`PZDirector_*`,
  table `PZDevKit.Production`), traductions `shared/Translate/EN|FR/IG_UI.json`, alias `PZDirector` dans `Compat.lua`
  (pas posé si `batman_PZDirector` est actif) ; `cli/pzdev/film.py` (régie sur le canal live), `cli/pzdev/recorder.py`,
  arrêt sur étape figée (`--stall`) ajouté à `scenario.follow` ; exemples dans `examples/productions/`. Défaut hérité
  corrigé : chaîne non ASCII d'`Actions.lua:66`. Commentaires des exemples passés en ASCII.
- Écarts : la suppression de `pzremote.py`, `PZDirector-Tournage.bat`, `zombiebuddy-patch` et `tools/zombiebuddy`
  porte sur le dépôt PZDirector, archivé à l'étape 10 (D14) : elle y est reportée. Dans PZDevKit, `rg -i
  "zombiebuddy|javaagent|pzremote"` sur `cli`, `tests`, `examples`, `Contents`, `pzdev.py`, `README.md` : vide ;
  seuls les documents de décision en parlent. 39 cas Lua de `test_director.lua` repris (40 fonctions dont `setup`).
- Vert : `python -m unittest discover -s tests` → `Ran 246 tests … OK` ; `luacheck` → `0 warnings / 0 errors in 13
  files`.
- En jeu (cache avec son `PZAT_SOUND=1`, confirmé en jeu, 42.22.2) : `pzdev sp SignalSmoke --no-quit` → code 0,
  `sp 41 PASS, 0 FAIL`, `SignalSmoke\runs\20261111-123035-sp-bab25b9aa388` ; après `world tp` :
  - `pzdev film PZDevKit/examples/productions/stills.lua` → `PZDirector / Captures sur place : passed` (13 étapes),
    2 PNG copiés et regardés (interface masquée, personnage centré), code 0,
    `runs\film\2026-11-11_12-33-00_stills` ;
  - même prise avec `--video` → passed, `take.mp4` 1600x900 de 9,8 s, 4 repères horodatés, affichage rendu en
    1280x720, image extraite à 6 s regardée ; son absent (module `soundcard` non installé, signalé dans
    `capture.json`, comme avec l'ancienne régie).
  - Observation (hypothèse) : dans `stills.lua`, « serre » (zoom 1,5) donne le plan large et « large » (zoom 0,5) le
    plan serré : noms de l'exemple d'origine inversés.
- Empreinte : `before-step8.json` (prise après la fin d'un test LiveWire d'une autre session) → `identical`.
- Son (ajout demandé par l'utilisateur) : `pzdev sound check|install` (`cli/pzdev/sound.py`, 4 tests) installe
  `soundcard` et `numpy` dans `PZDevKit/.pydeps` (ignoré par git) ; `sound install` → `loopback of <casque>`, code 0. Prise `film stills.lua --video` sur une partie `PZAT_SOUND=1`
  (`SignalSmoke\runs\20261111-123918-sp-ae5418ac4932`, code 0) → passed, `capture.json` `audio: true`, aucun
  avertissement, piste AAC stéréo 48 kHz, `volumedetect` max −25,1 dB / moyenne −52,5 dB (ambiance de rue, non
  muette), `runs\film\2026-11-11_12-41-40_stills`. La boucle locale enregistre toute la sortie par défaut, y compris
  les autres applications. Vert : `Ran 250 tests … OK`. Empreinte `before-sound.json` → `identical` (contrôlée
  après la fin d'un test LiveWire d'une autre session, lancé cette fois par `pzdev`).

### Étape 9 — Tournage
`Tuto.lua` (sans les aides monde), `record`, `take`, `quit`, `sheet`, `assemble` (Q03) ; contrôle ASCII conservé.
**Sortie** : tests de `record` (génération des hooks) ; en jeu : une vidéo existante (`youtube/tutoriaux/livewire/01-…`)
répétée avec `record --rehearse` (code 0) et une prise `take` via `--live`.

**Preuves (2026-11-11)** :
- Code : `client/PZDevKit/Tuto.lua` (ex-`tuto_lib.lua`, `PZDevKit.Tuto.new()` rend une table `T` neuve ; aides monde
  déléguées à `PZDevKit.World` : `clearSquare`, `clearZombies`, `clearBodies`, `setTime`, `holdWeather`, `night`,
  `zoom`, et `World.setPosition` ajouté pour `T.teleport`) ; tick live, fichiers `pztuto_*` et `speedTick` retirés,
  le canal live de l'étape 4 les remplace. `cli/pzdev/record.py` (`record`, `take`, `quit`), `sheet.py`,
  `assemble.py` ; contrôle ASCII limité à `scene.lua`.
- Exception générique retirée : l'entrée « Inspect » de LiveWire n'est plus codée en dur dans l'outil ; une scène
  garde une entrée de menu avec `T.keepEntry(callback)` (ajouté à la vidéo LiveWire 12).
- Anciens points d'entrée : `.claude/tools/pz-tutorial/record.py`, `live.py`, `sheet.py`, `assemble.py` sont des
  alias vers `pzdev` ; `tuto_lib.lua` supprimé ; skill `pz-tutorial-video` et mémoire mises à jour.
- Vert : `python -m unittest discover -s tests` → `Ran 265 tests … OK` (dont `test_tuto_lua` 6 et `test_record` 8) ;
  `luacheck` → `0 warnings / 0 errors in 14 files`.
- En jeu (confirmé en jeu, 42.22.2) :
  - `pzdev record youtube/tutoriaux/livewire/01-first-solar-grid --rehearse` → code 0, 25 étapes, toutes les
    vérifications PASS dont « kitchen powered by Live Wire », 0 FAIL,
    `01-first-solar-griduild
uns61111-125254-sp-4977410c3508` ; captures `step_08` (panneau posé) et
    `step_24` (zone alimentée autour du garage) regardées.
  - `pzdev record … --live` → partie prête en 15 s (`pzdev attach` → `pong`), préparation finie
    (`[PZTUTO] live: ready`) ; `pzdev take …` → prise de 74,1 s, 3 coupes, 8 sous-titres, frise écrite, code 1 :
    `FAILS: kitchen powered by Live Wire - false`. Cause : le panneau 2 n'a pas été relié pendant l'étape `link2`
    (`panel 2 grid=nil`, limite de 10 s atteinte) ; l'utilisateur, qui regardait, a vu le joueur prendre une décharge
    électrique à ce moment (confirmé en jeu par l'utilisateur, cause du choc non analysée). Défaut de la scène ou de
    LiveWire, pas de l'outil : le même raté figure déjà
    dans deux passages de l'ancien outil (`build
uns61110-125850-sp-6ef143589e48`,
    `20261110-130054-sp-ad1e579c2353`). La chaîne `take` est donc vérifiée, y compris le refus d'une prise ratée
    (`record --live` → `TAKE REJECTED`, code 2). `pzdev quit …` → `quitting`, code 0.
  - Effet de bord : la prise refusée a remplacé `build/body_raw.mp4` (fichier intermédiaire) ; la vidéo finale
    `01-first-solar-grid.mp4` du 2026-11-10 est intacte.
- Empreinte : `before-step9.json` → `identical`.

### Étape 10 — Finale
Migration des scripts appelants (LiveWire ×6, MilitaryDrop ×2, un projet privé ×1, Artemis ×3) vers les nouveaux chemins, chacun
dans son dépôt sur sa branche courante ; skills `pz-autotest` (fait le 2026-11-11, avec `AGENTS.md` et `docs/agents/tests-automatises.md`) et `pz-tutorial-video`,
`docs/agents/tests-automatises.md`, `docs/agents/fiches-des-mods.md`, mémoire `pz-live-channel.md` ; retrait de
`.claude/tools/pz-autotest`, `.claude/tools/pz-tutorial`, des alias Python et `pztuto_*` et de leurs tests ;
PZPuppeteer et PZDirector selon Q04.
**Sortie** : critères d'acceptation 1 à 9 du cahier des charges ; empreinte des données réelles identique ;
`rg` sans chemin contenant le nom d'utilisateur dans les fichiers versionnés.

**Preuves (2026-11-11)** :
- Appelants migrés (imports `pzdev.core`, `pzdev.launcher`, `pzdev.winproc`, `pzdev.autotest.main`, chemin
  `PZDevKit/pzdev.py`) : LiveWire `autotest/record_movie.py`, `run_c25.py`, `run_ext_removed.py`, `run_ixx.py`,
  `run_remaining.py`, `run_sound.py` (4 d'entre eux sont ignorés par git, modifiés en local) ; MilitaryDrop
  `tools/retest_cached_save.py`, `run_improvements_campaign.py` ; un script d'un projet privé. Contrôle : les 9
  compilent et leurs imports `pzdev` se chargent.
- Opération Artemis : `tests/puppeteer/verify.py` et `test_campaign.py` chargent `PZDevKit.Scenario` (harnais lupa de
  `tests/test_scenario_lua.py`) puis `Compat.lua` pour la globale `PZPuppet` ; `collect_results.py` importe
  `pzdev.collect`. Chemins `C:/Users/<nom>` remplacés par `USERPROFILE`. `test_campaign.py` → code 0 (« route plans,
  two actual wrapper/suite batch constructions, five collector file integrations passed ») ; `test_collector.py` →
  code 0. `verify.py` → code 1 avant **et** après migration, au même endroit : la comparaison avec les copies
  installées sous `Lua\PZPuppet\scenarios\OperationArtemis`, dossier vidé et archivé à la demande de l'utilisateur
  (étape 7) ; toute la partie moteur, contrats et luacheck passe avant.
- Commentaires et documentation courante pointés vers `pzdev` : en-têtes des dix `autotest.json`, hooks
  `autotest/*.lua`, fiches de test des projets, consignes des tutoriels LiveWire (`BRIEF.md`, `REPRISE.md`),
  `AGENTS.md`, `docs/agents/tests-automatises.md`, skills `pz-autotest` et `pz-tutorial-video`, mémoire. Historique
  (plans terminés, CHANGELOG, rapports, `run.log`) laissé tel quel. Aucun chemin d'exécution modifié dans les hooks.
- Alias Python retirés : `.claude/tools/pz-autotest` et `.claude/tools/pz-tutorial` supprimés, `tests/test_aliases.py`
  supprimé, mentions retirées (`autotest.py`, wiki, spécifications, exemple).
- Globales `PZPuppet` et `PZDirector` retirées aussi, à la demande de l'utilisateur (ADR D07 mis à jour) :
  `Compat.lua` et `tests/test_compat_lua.py` supprimés. Artemis migré : 31 scénarios, `suite.lua`, campagnes,
  diagnostics, `manifest.json`, collecteur et ses tests, productions promo `film.lua` et `teaser.lua`
  (`require "PZDevKit/Production"`), guides `README.md`, `CAMPAGNES.md`, `CAMPAGNE-NEGATIFS.md`. Contrats de données
  gardés (`[PZPuppet]`, `Lua/PZPuppet/`, noms de parties `PZPuppet_Artemis_*`). Après migration : `test_campaign.py` et
  `test_collector.py` → code 0 ; `verify.py` → code 1 au même endroit qu'avant (copies installées absentes) ;
  `film.lua` et `teaser.lua` compilent.
- Vert : `python -m unittest discover -s tests` → `Ran 260 tests … OK` (2 tests d'alias et 3 de `Compat` en moins) ;
  `luacheck` → `0 warnings / 0 errors in 13 files`.
- En jeu (confirmé en jeu, 42.22.2) : `pzdev sp SignalSmoke --no-quit` → code 0, `sp 41 PASS, 0 FAIL`,
  `SignalSmoke\runs\20261111-131817-sp-45b65e4e1aec` ; `pzdev lua` → `PZPuppet` et `PZDirector` à `nil`,
  `PZDevKit.Scenario.runFile`, `PZDevKit.Production.production` et `PZDevKit.World.setPosition` présents ;
  `pzdev scenario run examples/scenarios/01-aller-retour.lua` → `scenario passed`, code 0 ; `pzdev logs --errors` →
  une erreur vanilla de la carte (`handleMannequinZone`, Muldraugh), déjà présente au passage de l'étape 3.
- Critère 5 : `pzdev check` sur les dix projets → code 0 chacun (`mp: hooks ok`). Les `autotest.json` n'ont changé que
  dans leurs commentaires d'en-tête.
- Critère 7 : aucune occurrence de `zombiebuddy` ni `javaagent` dans le code, les tests, les exemples et le mod.
- Critère 9 : `git ls-files | xargs grep "users/<nom>"` dans PZDevKit → aucun fichier.
- Archives (D14) : `%USERPROFILE%\Zomboid\archives\PZDirector-archive-2026-11-11.zip` (168 fichiers, historique git
  compris, sans `tools/zombiebuddy`) et `PZPuppeteer-archive-2026-11-11.zip` (36 fichiers), relues sans erreur.
- D14 : dépôt GitHub `PZDirector` archivé (`gh repo view` → `isArchived: true`) ; dossiers `PZDirector` (dont
  `tools/zombiebuddy`, 318 Mo) et `PZPuppeteer` retirés de `Workshop` après archivage, avec l'accord de l'utilisateur.
- Critère 6 : empreinte `before-step9.json` → `identical` (après toutes les parties de l'étape 10 et celles de l'autre
  session).
