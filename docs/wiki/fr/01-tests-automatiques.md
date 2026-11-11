# Tests automatiques en jeu (`pzdev sp|server|mp|check`, ex-pz-autotest)

Lanceur générique (Build 42, **Windows seulement**) : copie les mods d'un projet et une sauvegarde dans un dossier de
cache temporaire, lance le vrai client solo, un serveur dédié, ou un serveur et N clients, exécute du Lua de test en jeu
par un mod pilote, récupère le résultat, ferme le jeu et range journaux et captures. Skill associé :
`.agents/skills/pz-autotest/SKILL.md` (source commune ; l'entrée `.claude/skills/pz-autotest/SKILL.md` y renvoie).

```
PZDevKit/
  pzdev.py                          ligne de commande (pzdev sp|server|mp|check, fingerprint, ...)
  cli/pzdev/autotest.py             options de sp, server, mp, check
  cli/pzdev/core.py                 configuration, mods, fichiers de commande, résultats, masquage des clés
  cli/pzdev/launcher.py             caches, processus, pont, surveillance, collecte, résumé
  cli/pzdev/winproc.py              processus Windows, fenêtre du jeu, clic posté, arrêt, mémoire
  Contents/mods/batman_PZDevKit/    mod pilote DEV-ONLY (jamais publié, copié seulement dans le cache)
  .luacheckrc
  examples/autotest.example.json    exemple minimal commenté
  tests/                            bancs (jeu simulé fake_game.py, pilote Lua sous lupa)
```

L'ancienne entrée `.claude/tools/pz-autotest/pz_autotest.py` et le paquet `pzat` ont été retirés à l'étape 10 du
plan 001 ; un script qui les importait passe à `pzdev.core`, `pzdev.launcher` (ex-`pzat.runner`), `pzdev.winproc` et
`pzdev.autotest.main`.

## Commandes

Depuis `%USERPROFILE%\Zomboid\Workshop` :

```powershell
python PZDevKit/pzdev.py check  RadioSurvivor                      # config et mods
python PZDevKit/pzdev.py sp     RadioSurvivor -P suite=rs.env        # client solo
python PZDevKit/pzdev.py server RadioSurvivor -P suite=rst           # serveur dédié seul
python PZDevKit/pzdev.py mp     RadioSurvivor -P suite=rs.identity --clients 2
python PZDevKit/pzdev.py sp     MonProjet --lua "return MonMod.selfTest()"
python PZDevKit/pzdev.py sp     RadioSurvivor -P suite=rs.env --dry-run --keep-cache
```

| Option | Rôle |
|---|---|
| `-P nom=valeur` | Paramètre des hooks (`ctx.params.nom`), répétable ; remplace `params` de la config. Valeur vide gardée. |
| `--lua CODE` / `--done-lua EXPR` | Remplace les hooks : `CODE` au départ (sa valeur rendue = résultat), `EXPR` sondée jusqu'à vrai. |
| `--save`, `--game-mode` | sp : dossier (ou motif glob, le plus récent) de `Zomboid\Saves\<mode>`, copié. |
| `--timeout` | Secondes entre le lancement et le résultat (défaut `timeoutSec` de la section). |
| `--wait-idle N` | Attendre jusqu'à N s qu'aucun `java.exe` / `ProjectZomboid64.exe` ne tourne (sinon code 3). |
| `--menu-timeout`, `--quit-timeout` | Pilote muet au menu (300 s) ; fermeture après le résultat (120 s), puis arrêt forcé. |
| `--start-delay`, `--lua-timeout` | Délai en jeu avant le départ ; délai côté Lua du hook `done` (0 = aucun). |
| `--bridge auto\|on\|off\|offline` | Pont externe de la config (défaut `bridge.default`). |
| `--clients N`, `--client-run` | mp : nombre de clients ; le client 1 exécute aussi les hooks client. |
| `--server-debug` | server, mp : lance le serveur dédié avec la propriété Java `-Ddebug` (`isDebugEnabled()` vrai). Équivaut à `serverDebug: true` dans la section. |
| `--no-quit`, `--no-screenshot`, `--keep-cache`, `--out`, `--dry-run` | Jeu laissé ouvert ; pas de capture ; caches gardés ; dossier de sortie ; préparation seule. |
| variable `PZAT_SOUND` | `1` : le client garde le son (sans `-nosound`), pour une vidéo. Par défaut, silence. |
| variable `PZAT_OPTIONS` | Valeurs `options.ini` en plus pour ce lancement, `clé=valeur` séparées par `;` (exemple : `language=EN` pour une vidéo en anglais). Le fichier de l'utilisateur n'est jamais modifié. |

Codes de sortie : **0** résultat OK ; **1** tests en échec ; **2** délai, démarrage raté, erreur Lua des hooks, partie
refusée, processus tué ; **3** un jeu ou serveur tourne déjà (jamais tué).

## Configuration `<Projet>/autotest.json`

JSON ; les lignes commençant par `//` sont des commentaires. Exemple complet : `examples/autotest.example.json` ;
configuration réelle : `RadioSurvivor/autotest.json`.

| Clé | Rôle |
|---|---|
| `name`, `gameVersion` | Nom affiché ; version cible pour choisir la variante `42.x` des `mod.info` (défaut 42.21). |
| `mods` | Liste dans l'ordre de chargement : `{"path": "..."}` (relatif au projet) ou `{"workshop": "<n°>", "id": "..."}` (lu dans `108600`, jamais écrit). Le pilote est ajouté en dernier. |
| `hooks` ou `lua` | Fichier Lua des hooks, ou corps Lua en ligne `{"start", "done", "result"}` (`P = ctx.params`). Une section (`sp`, `server`, `mp`) peut les redéfinir. |
| `params` | Paramètres par défaut (la section peut en ajouter). |
| `collect` | Motifs glob relatifs à `<cache>/Lua` copiés dans le dossier de résultats (`lua/...`). |
| `redactEnv` | Variables d'environnement dont la valeur est masquée dans les journaux rangés (jamais affichée). |
| `runsDir` | Dossier des résultats (défaut `runs`, à ignorer dans git). |
| `sp` | `save` (nom ou glob), `gameMode`, `saveMods` (`replace` : le `mods.txt` de la copie reçoit la liste de la config), `timeoutSec`, `startDelaySec`, `xmx`, `readyTimeoutSec` (60), `readyFrames` (10) : barrière « monde » ci-dessous. |
| `server` | `serverName` (nom du monde), `port` (UDP = port + 1), `timeoutSec`, `xmx`, `serverDebug` (propriété Java `-Ddebug` : sur un serveur dédié, le seul moyen de rendre `isDebugEnabled()` vrai, l'argument `-debug` du client étant ignoré ; **faux par défaut**, ce qui est l'état d'un serveur de production), `ini` (clés ajoutées ou remplacées dans `Server/<nom>.ini`). |
| `mp` | `serverName`, `port`, `spawn` (`SpawnPoint` fixe : pas d'écran de choix), `clients`, `clientXmx`, `serverRun`, `clientRun`, `timeoutSec`, `joinTimeoutSec`, `serverTimeoutSec`, `ini` ; barrières : `readyTimeoutSec` (60) et `readyFrames` (10) des clients, `clientReadyTimeoutSec` (défaut `readyTimeoutSec` + `startDelaySec` + 30), `clientStartTimeoutSec` (60), `playerWaitSec` (90, serveur). |
| `bridge` | Programme externe lancé avant le jeu : `command` (`{python}`, `{exchange}`, `{project}`), `cwd`, `ready` (ligne attendue), `readyTimeoutSec`, `exchange` (sous-dossier de `<cache>/Lua`), `offlineArgs`, `default`, `auto` (`{"param": [valeurs]}` : lancé si une valeur du paramètre est égale ou préfixe pointé d'une valeur listée ; `true` = toute valeur). |

### Hooks

`mp.clientRunAll: true`, avec `clientRun: true`, exécute les hooks sur **tous** les clients
et exige leurs résultats. Par défaut, seul le client 1 exécute les hooks ; les autres
restent connectés sans scénario. Utiliser `getPlayer():getUsername()` pour répartir les rôles.

`mp.reconnectClient1: true` attend un premier résultat réussi du client 1 et son arrêt
propre, puis le reconnecte au même serveur/compte dans un nouveau processus. Les preuves
de la première connexion restent intactes ; le second hook reçoit `ctx.params.reconnect="1"`.
Les hooks serveur doivent attendre cette seconde connexion avant de conclure. Les deux
connexions figurent dans les résultats collectés.

`hooks.lua` est un chunk Lua chargé par `loadstring` dans l'environnement global du jeu (les modules des mods sont
déjà chargés). Il rend une table de fonctions, ou des sous-tables `client` / `server` :

```lua
local H = {}
function H.start(ctx)  return MonMod.Tests.run(ctx.params.case) end -- true / rien = démarré ; false, raison = refus
function H.done(ctx)   return MonMod.Tests.finished end             -- sondée toutes les 250 ms ; absente = fini
function H.result(ctx) return { ok = MonMod.Tests.ok, summary = "3/3", lines = MonMod.Tests.lines } end
return H
```

`ctx = { side = "client"|"server", role, token, params, log, players(), Z = PZAutoTest, ready }` (`ready` =
`{ ok, detail }` de la barrière ci-dessous, `ok = false` après son délai) ; `PZAutoTest.split`,
`readLines`, `fileEndsWith(chemin, marqueur)` aident à attendre un fichier écrit par le mod.

## Barrières « monde » et ordre de départ

- **Client (sp et mp)** : à `OnGameStart`, le client n'est pas encore dans le monde (en MP, `IngameState.enter`
  déclenche `OnGameStart` **avant** `sendPlayerConnect` et n'attend la réponse du serveur qu'ensuite). Le pilote
  vérifie donc à chaque tick : joueur local, identifiant réseau (`getOnlineID() >= 0`, mp), `getCurrentSquare()`, chunk
  de la case en mémoire (`getCell():getChunk(wx, wy)`, le test de `BuildingDef.isFullyStreamedIn`) et au moins
  `readyFrames` ticks ; puis état `world ok after <ms>, <n> ticks: …`. Passé `readyTimeoutSec`, ligne
  `WARNING: world not ready …`, état `world timeout …` et la suite continue (avertissement dans le résumé).
- **Ordre mp** : clients en jeu → tous `ready` (barrière passée, `startDelaySec` écoulé) → « go » aux clients → leur
  hook `start` a tourné (état `run`, `idle` ou `done` : abonnés `OnServerCommand` inscrits) → « go » au serveur → le
  serveur attend `players=N` joueurs en ligne dont la case est chargée **sur le serveur** (état `players`, délai
  `playerWaitSec`) → hooks serveur. Chaque délai dépassé (`clientReadyTimeoutSec`, `clientStartTimeoutSec`, barrières)
  donne « go » quand même et ajoute une ligne `warning:` à `summary.txt` (`warnings` de `summary.json`).
- **Boîte de réception serveur** : de `OnServerStarted` à la fin du hook `start` serveur, le pilote garde les
  commandes `OnClientCommand` ; les abonnés `OnClientCommand` inscrits **pendant** `start` les reçoivent juste après,
  dans l'ordre d'arrivée (un client qui envoie une requête unique dès son `start` ne la perd plus). Un abonné inscrit
  plus tard (dans `done`) ou par une référence à `Events.OnClientCommand.Add` gardée au chargement du fichier de hooks
  n'en reçoit aucune. Les poignées de main maison (« ready » répété jusqu'à réponse) restent valables : une requête
  répétée est rejouée autant de fois qu'elle est arrivée.

## Déroulement

- **Cache** `%TEMP%\pzat-<mode>-*` : `mods\` (copies), `mods\default.txt` (même liste : pas de rechargement Lua),
  `mods\reset-mods-42_00.txt` (sans lui le jeu vide `default.txt`), `options.ini` copié en fenêtré 1280 × 720, copie
  de la sauvegarde, `Lua\pz-autotest\command.txt` et `hooks.lua` (UTF-8 sans BOM). Rien n'est écrit dans le jeu,
  dans `%USERPROFILE%\Zomboid` ni dans le Workshop Steam. Cache supprimé en cas de succès, gardé sinon.
- **sp** : `java.exe` du jeu avec les `vmArgs` de `ProjectZomboid64.json`, `-cachedir=… -debug -nosound -nosteam`.
  Le pilote coupe « Break On Error », appelle `MainScreen.continueLatestSave` ; l'outil poste un clic gauche à la
  fenêtre (`PostMessage`, sans focus) tant que l'état est `load` ; en jeu, hooks après `startDelaySec` sur
  `OnTickEvenPaused`, `result.txt`, capture, `quitToDesktop` (la copie est sauvegardée).
- **server** : `zombie.network.GameServer -nosteam` sur le cache, `PauseEmpty`, mot de passe d'admin tiré au hasard.
  Le pilote démarre à `OnServerStarted` ; à la fin l'outil envoie `quit` sur stdin (sans BOM), puis arrêt forcé.
- **mp** : serveur (`SpawnPoint` fixe), comptes `pzat1..N` créés et passés admin par la console (`adduser`,
  `setaccesslevel` : un client `-debug` sans `ConnectWithDebug` est déconnecté) ; clients lancés l'un après l'autre
  (le suivant quand le précédent est en jeu), connexion par `ConnectToServer:connect`, création du personnage par
  NEXT, clic de l'écran de chargement ; quand tous sont prêts dans le monde, « go » aux clients puis, leurs hooks
  démarrés, au serveur (section précédente) : le client 1 exécute les hooks `client` si `--client-run`, le serveur
  les hooks `server` (joueurs connectés disponibles par `ctx.players()`) ; les autres restent connectés. À la fin « quit » aux clients puis `quit` au serveur.
- **Résultats** `<Projet>/runs/<date>-<mode>-<jeton>/` : `summary.json`, `summary.txt`, `result.txt`, `status.txt`,
  `command.txt`, `console.txt` / `server-console.txt`, sortie du processus, `Logs\` du serveur, captures, fichiers de
  `collect`, `bridge.log` ; un sous-dossier par processus en mp. Les fichiers texte rangés sont passés au masque des
  formes de clé (`sk-…`, `Bearer …`, `*_KEY=…`, valeurs de `redactEnv`, mots de passe tirés pour le passage).

Format de `result.txt` : `PZAT-RESULT ok=<bool> side=<client|server> durationMs=<n> [error=<texte>] summary=<texte>`,
les lignes rendues par `result`, puis `PZAT-END`.

## Limites

- Windows seulement (fenêtre du jeu, `tasklist`, `taskkill`, clic posté). Pas de partie neuve : une sauvegarde est
  requise en sp. Liste de mods minimale : les objets des autres mods de la sauvegarde d'origine disparaissent de la copie.
- Sans Steam (`-nosteam`), aucun mod Workshop abonné n'est chargé : il doit figurer dans `mods` (copié).
- Un clic posté juste avant l'entrée en jeu peut tomber au centre du monde.
- Rendu, son, sensations : à vérifier à l'œil ; les captures n'en montrent qu'une image.
- mp : chaque client est un jeu complet (`clientXmx`) ; surveiller la mémoire libre (avertissement si insuffisante).

## Essais réels (2026-10-14, 42.21.0, ce PC)

| Commande | Résultat |
|---|---|
| `sp RadioSurvivor -P suite=rs.env` | code 0, 7/7 PASS, 47 s de jeu (menu → chargement cliqué → jeu → sortie code 0) |
| `server RadioSurvivor -P suite=rst,rs.codec` | code 0, 21/21 PASS, serveur arrêté par `quit` (35 s) |
| `mp RadioSurvivor -P suite=rs.identity,rs.codec` (1 client) | code 0, serveur 21/21 PASS avec un joueur connecté (89 s) |
| `mp RadioSurvivor -P suite=rs.env --clients 2 --client-run` | code 0, serveur 6 PASS + 1 SKIP, client 1 4 PASS + 3 SKIP, client 2 connecté (130 s) |
| `sp RadioSurvivor -P suite=rs.npctalk -P tags=world` | code 0, pont lancé seul (`auto`), vrai modèle, 4/4 PASS (110 s) |

Le pont arrêté par l'outil rend le code 1 (`terminate` sous Windows) : sans conséquence.

## Bancs

```powershell
python -m unittest discover -s PZDevKit/tests
luacheck PZDevKit/Contents --config PZDevKit/.luacheckrc
```
