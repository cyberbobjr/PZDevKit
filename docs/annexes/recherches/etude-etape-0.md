# Étude de l'étape 0 — fusion des outils de pilotage

Date : 2026-11-10. Lecture seule : aucun fichier des outils étudiés n'a été modifié, aucun jeu lancé, aucun banc exécuté.
Chaque constat est qualifié : **[statique]** = confirmé statiquement (lecture du code ou des sources 42.22),
**[hypothèse]** = à vérifier. Rien n'est « confirmé en jeu » dans ce document.

Abréviations : `PZAT` = `.claude/tools/pz-autotest/`, `TUTO` = `.claude/tools/pz-tutorial/`,
`PUP` = `PZPuppeteer/Contents/mods/batman_PZPuppeteer/42.21/media/lua/client/PZPuppet/`,
`DIR` = `PZDirector/Contents/mods/batman_PZDirector/42.21/media/lua/client/PZDirector/`.

## 1. Taille des outils

| Outil | Python | Lua | Bancs |
|---|---|---|---|
| pz-autotest | ~1 470 lignes (`pz_autotest.py`, `pzat/core.py`, `runner.py`, `winproc.py`) | ~920 (pilote `batman_PZAutoTestDriver`) | 42 tests unittest (11 core, 14 Lua via lupa, 17 runner simulé) |
| pz-tutorial | ~750 (`record.py`, `live.py`, `assemble.py`, `sheet.py`) | 485 (`tuto_lib.lua`) | aucun |
| PZPuppeteer | 134 (`collect_reports.py`) | ~1 230 | ~80 cas Lua (lupa) + 11 unittest hors CI |
| PZDirector | ~710 (`tournage.py`, `recorder.py`, `pzremote.py`) | ~1 400 | 39 cas Lua (lupa) |
| ZombieBuddy | `tools/zombiebuddy/` 318 Mo (JDK, jar, sources tierces), ignoré par git ; `zombiebuddy-patch/` suivi (2 `.java`, `build_winfix.py`) | 0 | 0 |

## 2. pz-autotest **[statique]**

- **CLI** (`pz_autotest.py:25-53`) : `sp|server|mp|check <projet>` ; `-P NOM=VAL`, `--lua`, `--done-lua`, `--save`,
  `--game-mode`, `--timeout`, `--menu-timeout`, `--quit-timeout`, `--wait-idle`, `--start-delay`, `--lua-timeout`,
  `--bridge auto|on|off|offline`, `--clients`, `--client-run`, `--server-debug`, `--no-quit`, `--no-screenshot`,
  `--keep-cache`, `--out`, `--dry-run`. Variables `PZAT_SOUND=1`, `PZAT_OPTIONS`.
- **Cache** : `tempfile.mkdtemp(prefix='pzat-<label>-')`, labels `sp`, `server`, `client1..N`, `client1-reconnect`
  (`runner.py:428-431`). Copie des mods (sans `.git`, `.env`, `*.pyc`…), `mods/default.txt`, `options.ini` copié puis
  modifié dans le cache (1280×720 fenêtré), en solo copie entière de la sauvegarde ; `Lua/pz-autotest/command.txt` et
  `hooks.lua`. Rien n'est écrit dans `%USERPROFILE%\Zomboid` ni dans le Workshop Steam. Écart : le README annonce
  `pzat-<mode>-*`.
- **Pilote** : `driver/batman_PZAutoTestDriver` ajouté en dernier à la liste des mods (`core.py:147-148`), copié dans le
  cache seulement. Variante `42/`, `versionMin=42.0`.
- **Lancement** : `jre64\bin\java.exe` avec les vmArgs de `ProjectZomboid64.json`, `-Dzomboid.steam=0`,
  `-cachedir=<cache> -debug -nosteam` (+ `-nosound` sauf `PZAT_SOUND=1`) ; serveur `zombie.network.GameServer`, mot de
  passe admin aléatoire (`runner.py:67-103`).
- **Barrières** : `world` (joueur, case, chunk, 10 images), puis en MP `ready`/`go`, `players`
  (`PZAT_Core.lua:390-415`, `PZAT_Client.lua:270-293`, `PZAT_Server.lua:35-50`).
- **Résultat** : `PZAT-RESULT ok=… side=… durationMs=… [error=…] summary=…`, lignes du hook, `PZAT-END`
  (`PZAT_Core.lua:290-315`) ; lu seulement complet (`core.py:300-317`).
- **Codes** : 0 OK, 1 `ok=false`, 2 erreur/délai/démarrage, 3 jeu déjà lancé jamais tué ; MP = max des codes
  (`core.py:326-328`).
- **runs/** : `<projet>/<runsDir|runs>/<AAAAmmjj-HHMMSS>-<mode>-<jeton>/` avec `summary.json` (project, mode, token,
  exitCode, reason, warnings, params, durationSec, date, redactedStrings, bridge, processes[]), `result.txt`, journaux,
  captures ; un sous-dossier par processus en MP.
- **autotest.json** : clés lues `mods`, `hooks` XOR `lua`, `name`, `gameVersion`, `params`, `collect`, `redactEnv`,
  `runsDir`, `bridge`, `port`, `serverName`, `serverDebug`, `startDelaySec`, `readyTimeoutSec`, `readyFrames`,
  `timeoutSec`, `xmx`, `saveMods`, `playerWaitSec`, `spawn`, sections `sp`, `server`, `mp` (une clé de section
  prime sur la racine, `runner.py:404-405`).
- **Contrat des hooks** : `H.start(ctx)` obligatoire, `H.done(ctx)` sondé toutes les 250 ms, `H.result(ctx)` →
  `{ok, summary, lines}` ; `ctx` = side, role, token, params, log, players(), Z, ready.
- **Code Windows uniquement** : `winproc.py` (EnumWindows, PostMessageW, tasklist), séparateur `;` du classpath.
- **Chemins** : `core.py:11-12` code en dur `D:\SteamLibrary\...` (pas de nom d'utilisateur) ; `README.md:22,123`
  contient un chemin avec le nom d'utilisateur (à corriger lors de la migration).
- Fragilités relevées : `-P` écrit en clair dans `summary.json` (non masqué) ; mot de passe admin du serveur sur la ligne
  de commande ; `Events.OnClientCommand.Add` remplacé temporairement (`PZAT_Core.lua:363-368`).

## 3. pz-tutorial **[statique]**

- `tuto_lib.lua` : `T.rec`, `require`, `info`, `caption`, `step`, `sq`, `idle`, `objectWith`, `clearSquare`,
  `clearZombies`, `clearBodies`, `quiet`, `inventories`, `teleport` (émet `cut`), `clearWalk`, `walkTo`, `nearSquare`,
  `near`, `face`, `time`, `weather`, `night`, `zoom`, `buildingAt`, `roomOf`, `placeItem`, `speed`/`speedTick` (différée
  pendant une marche), `openCraft`, `craftWindow`, `startCraft`, `closeCraft`, `showMenuPath`, `menuTick`, `menuDone`,
  `clickMenu`, `closeMenu`, `take`, `liveTick`, `hooks` (H.start/H.done/H.result).
- **Chargement** : `record.py:67-73` concatène `tuto_lib.lua` + `scene.lua` dans `build/hooks.lua`, passé à pz-autotest
  comme hooks. `tuto_lib` n'est donc pas un mod aujourd'hui.
- **Canal live** : `live.py` écrit `<cache>/Lua/pztuto_cmd.lua` (`--id N [shot]` + code) ; `T.liveTick` le lit toutes
  les 400 ms, exécute une fois par id avec `loadstring`, écrit `pztuto_out.txt` (`--id N`, `-> valeur`, `ERROR`,
  `COMPILE ERROR`, `info …`, `shot live_N.png`). `live.py` attend 30 s ; `take` attend `timeline.json` jusqu'à 900 s.
- Lignes console `[PZTUTO]` : start, end, caption, uncaption, cut, step N, PASS/FAIL, info, `live: ready` ; lues par
  `record.py` pour piloter `ffmpeg gdigrab`.
- Seule écriture hors cache : `record.py --make-save` crée une sauvegarde dans `%USERPROFILE%\Zomboid\Saves`.
- Couplage à un mod : `tuto_lib.lua:269` appelle `LiveWire.Menu.onInspect`.
- `assemble.py` : montage ffmpeg, sous-titres EN/FR, voix ElevenLabs facultative, valeurs par défaut machine
  (`D:\SteamLibrary`, polices Windows, lien Ko-fi).

## 4. PZPuppeteer **[statique]**

- **API** : `scenario`, `register`, `listScenarios`, `run`, `loadScenario`, `runFile`, `runFiles`, `runBatchFile`,
  `stop`, `stopBatch`, `status`, `printStatus`, `batchStatus`, `runStatus`, `captureServerCommand`, champs
  `lastReport`, `lastBatch`, `Game`, `Debug`, `Scenario`, `MilitaryDrop`.
- **Constructeur** : `step`, `call`, `check`, `wait`, `await`, `awaitServerCommand`, `finally`, `run` ; actions
  `walkTo`, `walkToVehicle`, `travelTo`, `interact`, `act`, `click`, `equip`, `approachContainer`, `transfer`, `door`,
  `teleport`.
- **Debug** (solo et `-debug` pour les mutations) : `position`, `teleport`, `spawnItem`, `spawnWorldItem`,
  `spawnVehicle`, `vehicleKey`, `spawnZombies`, `spawnZombie`, `freezeZombie`, `setFlags`, `setStats`, `heal`,
  `setSkill`, `setTimeOfDay`, `weather`, `itemTypes`, `vehicleTypes`, `removeSpawned`.
- **Fichiers** : scénarios sous `Zomboid/Lua/PZPuppet/scenarios/` (motif `[%w_/-]+%.lua`, 256 Kio max) ; rapports
  `PZPuppet/reports/<jeton>.txt` et `last-report.txt` ; campagne avec accusé `PZPuppet/batch-ack.txt`
  (`PZPuppet ACK <jeton> passed|rejected <raison>`), écrit par `tools/collect_reports.py`.
- Aucun HTTP, socket, agent Java ni ZombieBuddy.
- `PZPuppet_MilitaryDrop.lua` : adaptateur propre à Military Drop, couplé à `MilitaryDrop.Secrets.privateState()`.
- `collect_reports.py:10` et `tests/run_tests.py:61` contiennent des chemins machine (dont un avec le nom d'utilisateur).
  `test_collect_reports.py` (11 cas) n'est lancé ni par `run_tests.py` ni par la CI.

## 5. PZDirector et ZombieBuddy **[statique]**

- **API** : `production`, `scene`, `status`, `stop`, `square`, `sound`, `zombie`, `thunder`, `demo`, `observation`,
  `open` ; méthodes `cue`, `moveBy`, `run`, `mark`, `screenshot`, `runBy`, `sprintBy`, `sneakBy`, `crouch`, `stand`,
  `emote`, `eat`, `drink`, `reload`, `rack`, `aimAt`, `shootAt`, `openDoor`, `closeDoor`, `cast`, `activate`,
  `location`, `extra`, `releaseExtra(s)`, `clearExtras`, `moveOnSet`, `light`, `blinkLight`, `stashInventory`, `frame`,
  `showUI`, `document`, `openLoot`, `think`. Fenêtre de régie (Ctrl+Maj+F10, arrêt d'urgence Ctrl+Maj+F11), 10 clés
  `IGUI_PZDirector_*` EN/FR.
- **Le Lua du mod n'utilise pas ZombieBuddy** : il tourne avec `-debug` seul.
- **ZombieBuddy ne sert qu'au pilotage externe** : `pzremote.py` (HTTP 127.0.0.1:7878 : `wait`, `lua`, `file`) et
  `tournage.py` (état, préparation, fenêtre, contrôle des mods, suivi, chargement de sauvegarde, rechargement de
  modules), lancés par `PZDirector-Tournage.bat` (`-javaagent:ZombieBuddy-2.3.4-winfix.jar=…`, chemin du jeu en dur).
- `recorder.py` : `ffmpeg gfxcapture`, audio en boucle locale, `ffprobe` ; indépendant de ZombieBuddy.
- Aucun test ne couvre ZombieBuddy, `pzremote`, `tournage` ou `recorder` : rien à supprimer côté tests.
- `docs/API.md:77` contient un chemin avec le nom d'utilisateur.

## 6. Ce qui dépend de ZombieBuddy, et son remplacement

Toutes les fonctions Lua que le canal par fichiers doit appeler sont exposées en 42.22 **[statique]** :
`loadstring` (`java/se/krka/kahlua/luaj/compiler/LuaCompiler.java:109`), `reloadLuaFile` (`LuaManager.java:3553`),
`getFileReader`/`getFileWriter` (`LuaManager.java:5517`), `takeScreenshot` (`LuaManager.java:4685`),
`isDebugEnabled` (`LuaManager.java:3703`).

| Fonction ZombieBuddy | Devenir |
|---|---|
| `pzremote.py wait/lua/file` (HTTP) | réécrite : `pzdev lua` / `pzdev attach` sur le canal par fichiers |
| `tournage.py` : état, préparation, fenêtre, contrôle des mods, suivi, lancement de film | réécrite : lanceur (cache) + canal par fichiers |
| `load_save` (`MainScreen.continueLatestSave`) | réécrite en mode cache (déjà fait par le pilote) ; en mode attaché, le joueur charge la partie lui-même **[hypothèse : le canal peut aussi tourner au menu si le mod est actif globalement]** |
| `reload_modules` (`reloadLuaFile`) | réécrite : `reloadLuaFile` est exposé |
| `-javaagent`, `PZDirector-Tournage.bat`, jar, JDK, `build_winfix.py` | supprimés |
| `JavaStateDumper.java` (vidage d'état Java) | **perdue** |
| `LogOverlay.java` (journal superposé à l'écran) | **perdue** (remplaçable plus tard par une fenêtre Lua, non prévu) |
| Accès à du Java non exposé à Lua, exécution hors `-debug`, accès HTTP distant | **perdus** |

## 7. Comparaison 42.21 → 42.22 des API retenues **[statique]** (`api-diff-42.21-42.22.txt` des sources de référence locales)

| API | Changement 42.22 | Effet sur l'outil |
|---|---|---|
| `IsoWorld.getGameMode`, `Core.getGameMode` | renvoie `GameMode` au lieu de `String` | `PZAT_Client.lua:149` compare à `"Multiplayer"` : comparaison toujours vraie en 42.22. À corriger (comparer `tostring(v)`). Effet réel sur la jonction MP : **[hypothèse]** |
| `addZombiesInOutfit` | 18 paramètres en 42.22 (`isUseless` ajouté) ; 17 en 42.21 | `PUP/PZPuppet_Debug.lua:151` en passe 13 : appel probablement refusé. **[hypothèse]** *Réfutée le 2026-11-11 (confirmé statiquement) : la surcharge à 13 paramètres existe toujours en 42.22, `LuaManager.java:8334`.* à vérifier en jeu, réécrire avec la signature complète |
| `IsoGameCharacter.teleportTo` | `(float,float,int)` → `(float,float,float)` | sans effet pour Lua |
| `IsoGridSquare.getObjects` et listes de conteneurs | `PZArrayList` → `List` | sans effet (`size`/`get` existent) |
| `IsoPlayer.isTimedActionInstant` | supprimée | non utilisée (les outils utilisent `isTimedActionInstantCheat`) |
| Événements Lua | aucun retiré | — |
| Fonctions Lua vanilla utilisées (`ISTimedActionQueue`, `ISPathFindAction`, `ISWalkToTimedAction`, `MainScreen`, `ISEntityUI`, `ISWorldObjectContextMenu`…) | aucune retirée ni modifiée | — |

Appels de PZDirector à revérifier en jeu car peu courants : `CanAttack`, `getBallisticsController`,
`updateBallistics`, `setUiSoundMuted`, `setForceSelectedContainer`, `spotted` **[hypothèse]**.

## 8. Dépendances extérieures à préserver **[statique]**

- **Dix `autotest.json`, pas neuf** : BeltRadio, ErisFoodExpiry, un projet privé, **LiveWire**,
  MilitaryDrop, MyTailorIsRich, RadioSurvivor, SignalSmoke, TimberChainsaw, TrainingTarget. Aucun ne cite le pilote,
  PZPuppeteer ni PZDirector dans `mods`.
- **Import Python direct des modules internes** (pas seulement la CLI) :
  - `LiveWire/autotest/run_c25.py`, `run_ixx.py`, `run_remaining.py`, `run_ext_removed.py`, `run_sound.py`,
    `record_movie.py` : `from pzat import core, winproc`, `from pzat.runner import Env, Options, Runner,
    client_java_command, server_java_command`, `from pz_autotest import main`.
  - `MilitaryDrop/tools/retest_cached_save.py` (`import pz_autotest`, `pzat.runner`),
    `run_improvements_campaign.py` (chemin de `pz_autotest.py`).
  - un script d'un projet privé (chemin de `pz_autotest.py`).
- **Opération Artemis dépend de PZPuppeteer par chemin** : `tests/puppeteer/verify.py:11` et `test_campaign.py:45`
  chargent `PZPuppeteer/.../PZPuppet_Core.lua` ; `collect_results.py:13-14` importe `PZPuppeteer/tools/collect_reports`
  ; environ 31 scénarios `NN_*.lua`.
- **47 scénarios personnels non versionnés** sous `%USERPROFILE%\Zomboid\Lua\PZPuppet\scenarios\` appellent
  `PZPuppet.runFile` (48), `loadScenario` (36), `Debug` (25), `status`, `Game.item`, `Scenario.teleport`,
  `runBatchFile`, `scenario`, `PZDirector.production`, `scene`, `sound`, `thunder`, `observation`, `demo` : alias
  `PZPuppet.*` et `PZDirector.*` obligatoires.
- **Une vidéo** (`youtube/tutoriaux/livewire/01-first-solar-grid/build/hooks.lua`) contient une copie générée de
  `tuto_lib`.
- **Documentation et skills** : 48 fichiers `.md` citent `pz-autotest`, `pz-tutorial`, `PZAutoTestDriver` ou
  `pztuto` (skills `pz-autotest` et `pz-tutorial-video`, `AGENTS.md`, `docs/agents/tests-automatises.md`,
  docs des projets).

## 9. Écran d'envoi du jeu et blocage d'un envoi accidentel **[statique]**

- `SteamWorkshop.getStageFolders()` (`java/zombie/core/znet/SteamWorkshop.java:100-119`) liste chaque sous-dossier de
  `<cachedir>\Workshop` ; le jeu charge ensuite `<dossier>\Contents\mods` seulement en mode Steam
  (`ZomboidFileSystem.java:443-451`).
- `WorkshopSubmitScreen.lua:122` (bouton Suivant) et `:843` (bouton Publier) appellent
  `SteamWorkshopItem.validateContents()`. Celle-ci refuse :
  - un aperçu absent (`PreviewNotFound`, `SteamWorkshopItem.java:484`) ;
  - tout **fichier** posé directement dans `Contents\` (`FileNotAllowedInContents`, `:558`) ;
  - tout dossier de `Contents\` autre que `buildings`, `creative`, `mods` (`:546`).
- **Barrière retenue** : pas de `preview.png` ni de `workshop.txt`, et un fichier témoin
  `Contents\DEV-ONLY-DO-NOT-UPLOAD.txt`. Le chargement du mod (qui ne lit que `Contents\mods`) n'est pas affecté ;
  l'écran d'envoi refuse aux deux étapes. Effet réel à constater une fois en jeu **[hypothèse]**.
- L'outil local `.claude/tools/steam_workshop_publish.py` doit aussi refuser ce projet (fichier témoin présent).
- En mode test (`-nosteam -cachedir=<cache>`), le dossier réel `Zomboid\Workshop` n'est pas lu : le mod est copié dans
  le cache comme le pilote actuel.
