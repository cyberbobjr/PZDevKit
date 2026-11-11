# Architecture — PZDevKit (cible)

> **DEV-ONLY. Ne jamais publier.** Outil de développement local. Ni Workshop, ni serveur de jeu, ni sauvegarde réelle.

Statut : **proposée** (ADR-001, en attente de validation). Rien n'est encore codé. Les contrats précis (fichiers,
commandes, correspondance ancien → nouveau) sont dans [specifications-techniques.md](specifications-techniques.md) ;
l'état des outils actuels dans [annexes/recherches/etude-etape-0.md](annexes/recherches/etude-etape-0.md).

## 1. Vue d'ensemble

```
            pzdev (CLI Python, Windows)
   ┌──────────────┬───────────────┬──────────────┬──────────────┐
   │ lanceur      │ canal live    │ journaux     │ tournage     │
   │ sp/server/mp │ lua/repl/     │ logs/report  │ record/take/ │
   │ check (cache)│ world/scenario│ campagnes    │ film/sheet   │
   └──────┬───────┴──────┬────────┴──────┬───────┴──────┬───────┘
          │ copie + java │ fichiers      │ lecture      │ ffmpeg
          ▼              ▼               ▼              ▼
   %TEMP%\pzat-*   <Lua>\pzdev\cmd.lua  console.txt   fenêtre du jeu
   (cache isolé)   <Lua>\pzdev\out.txt  runs\, reports
          │              ▲
          ▼              │
   ┌─────────────── mod batman_PZDevKit (Lua, -debug) ───────────────┐
   │ Driver (ex-pilote PZAT) │ Live │ World │ Scenario │ Production │
   │ Tuto (ex-tuto_lib) │                                           │
   └─────────────────────────────────────────────────────────────────┘
```

Deux façons de faire tourner le mod :

1. **Mode cache** (tests automatiques, tournage) : le lanceur copie mods, sauvegarde et options dans
   `%TEMP%\pzat-<label>-*`, ajoute `batman_PZDevKit` en dernier, lance `java … -cachedir=<cache> -debug -nosteam`.
   Comportement et codes de sortie identiques à pz-autotest.
2. **Mode attaché** : l'utilisateur lance lui-même le jeu en `-debug`, active `batman_PZDevKit` dans une partie de
   test. Le canal live lit `%USERPROFILE%\Zomboid\Lua\pzdev\cmd.lua`. `pzdev attach` vérifie que le jeu répond.

Le chemin relatif `pzdev/cmd.lua` est le même dans les deux modes (`getFileReader` est relatif au dossier `Lua` du
`cachedir`) ; seule la racine change côté CLI.

## 2. Arborescence du projet

```
PZDevKit/
├── README.md                    anglais, bandeau DEV-ONLY
├── pzdev.py                     point d'entrée de la CLI
├── cli/pzdev/                   paquet Python
│   ├── __main__.py              analyse des sous-commandes
│   ├── autotest.py              ex-pz_autotest.py (options de sp, server, mp, check)
│   ├── core.py                  ex-pzat/core.py (config, résultat, codes, masquage)
│   ├── launcher.py              ex-pzat/runner.py (cache, java, barrières, runs\)
│   ├── winproc.py               ex-pzat/winproc.py
│   ├── live.py                  canal par fichiers (client), REPL
│   ├── world.py                 sous-commandes « monde » → Lua
│   ├── scenarios.py             runFile, campagnes, accusés (ex-collect_reports.py)
│   ├── logs.py                  extraits filtrés de console.txt, server-console.txt, rapports
│   ├── record.py, sheet.py, assemble.py   ex-pz-tutorial (record, take, quit, sheet, assemble)
│   ├── film.py                  ex-tournage.py, sur le canal live (sans agent Java)
│   └── recorder.py              ex-PZDirector tools/recorder.py (FFmpeg gfxcapture, son en boucle locale)
├── tests/                       unittest (Python) + lupa (Lua) + luacheck
├── Contents/
│   ├── DEV-ONLY-DO-NOT-UPLOAD.txt   barrière de l'écran d'envoi (voir § 5)
│   └── mods/batman_PZDevKit/
│       ├── common/              vide (.gitkeep)
│       └── 42.21/
│           ├── mod.info         name=batman_PZDevKit (DEV-ONLY), id=batman_PZDevKit
│           └── media/lua/
│               ├── shared/PZDevKit/   Driver commun (fichiers, journal, commandes, hooks)
│               ├── client/PZDevKit/   Driver client, Live, World, Scenario, Game, Production, Tuto, UI
│               ├── server/PZDevKit/   Driver serveur
│               └── shared/Translate/EN|FR/IG_UI.json   (fenêtre de régie)
└── docs/
```

Ni `preview.png`, ni `workshop.txt`, ni `README.steam*`.

## 3. Modules Lua (client sauf mention)

| Module | Origine | Responsabilité |
|---|---|---|
| `shared/PZDevKit/Driver.lua`, `client/PZDevKit/DriverClient.lua`, `server/PZDevKit/DriverServer.lua` | `PZAT_Core.lua`, `PZAT_Client.lua`, `PZAT_Server.lua` (table globale `PZDevKit.Driver`, ex-`PZAutoTest` ; journal `[PZAT]` gardé) | mode cache : menu, chargement, jonction MP, barrières, hooks, `result.txt`. **Inerte sans `Lua/pz-autotest/command.txt`** |
| `Live.lua` | `T.liveTick`, `pzremote.py` | canal par fichiers ; actif seulement si `isDebugEnabled()` ; `PZDevKit.info` ; sérialisation bornée ; fonctions de fichiers de `Driver.lua` (pas de `Core.lua` : décidé à l'étape 4, aucune duplication) |
| `World.lua` | `PZPuppet.Debug` + `tuto_lib` (monde) | téléporter, objets, zombies, véhicules, heure, météo, statistiques, compétences, drapeaux, nettoyage. Une seule implémentation par aide |
| `Scenario.lua`, `Game.lua` | `PZPuppet_Core.lua`, `PZPuppet_Game.lua` | moteur de scénarios, actions réelles du joueur, rapports, campagnes |
| `Production.lua`, `Actions.lua`, `Staging.lua`, `Demos.lua`, `UI.lua` | `PZDirector_Core`, `_Actions`, `_Staging`, `_Demos`, `_UI` | productions (table `PZDevKit.Production`), régie, mise en scène, démos enregistrées, fenêtre Ctrl+Maj+F10. Contrats gardés pour la régie : lignes `[PZDirector] MARK\|` et `SCREENSHOT\|`, fichiers `Screenshots/PZDirector_<nom>.png`, clés `IGUI_PZDirector_*` |
| `Tuto.lua` | `tuto_lib.lua` | gestes filmés (menus, artisanat, vitesse différée, prises) ; appelle `World` pour le monde |

Les adaptateurs propres à un mod (`PZPuppet_MilitaryDrop.lua`, appel `LiveWire.Menu.onInspect` de `tuto_lib`)
**sortent du mod générique** et vont dans le projet concerné (scénario ou hooks), chargés à la demande. L'exception
LiveWire est devenue `T.keepEntry(LiveWire.Menu.onInspect)` dans la scène de la vidéo 12 (étape 9).
L'adaptateur MilitaryDrop, sans appelant, est abandonné (ADR D08, mise à jour de l'étape 7).

Événements : `OnTickEvenPaused` (canal live et pilote, cadencés à 400 ms et 250 ms), `OnFETick`, `OnMainMenuEnter`,
`OnGameStart`, `OnConnectFailed` (pilote), `OnTick`/`OnServerCommand` pendant un scénario seulement,
`OnServerStarted`/`OnClientCommand` (pilote serveur). Aucun crochet global permanent sur une fonction appelée à chaque
image.

## 4. Mode solo, serveur, MP

- Pilote : comme aujourd'hui (client et serveur dédié Linux ou Windows ; le lanceur, lui, est Windows seulement).
- Canal live : client seulement (solo ou client MP). Sur un serveur dédié, l'exécution passe par les hooks
  `server` d'un `autotest.json`, comme aujourd'hui.
- Aides `World` qui modifient le monde : solo et `-debug`. En client MP, elles refusent avec un message clair
  (pas de commande réseau d'administration dans cette version).

## 5. Sécurité

- **Workshop Steam** (`D:\SteamLibrary\steamapps\workshop\content\108600`) : jamais écrit. Le lanceur le lit seulement
  pour copier les mods abonnés dans le cache.
- **Données réelles** : `Saves`, `options.ini`, `mods.txt`, `Server\` jamais modifiés par le lanceur ; il travaille sur
  des copies. Un test d'empreinte (SHA-256 avant/après) fait partie des critères de sortie. Seule exception
  existante : `record --make-save` crée une **nouvelle** sauvegarde nommée ; elle refuse d'écraser sans `--replace`.
- **Mode attaché** : écrit seulement sous `%USERPROFILE%\Zomboid\Lua\pzdev\` (commande, réponse, captures copiées).
- **Canal live** : exécute du Lua arbitraire ; actif seulement en `-debug`, fichier local. C'est un outil de
  développement : pas d'usage sur un serveur partagé.
- **Jamais publié** : pas d'aperçu, pas de `workshop.txt`, fichier témoin dans `Contents\` (refus de l'écran d'envoi
  aux boutons Suivant et Publier, voir l'étude § 9), `name=` et `description=` marqués DEV-ONLY,
  `steam_workshop_publish.py` refuse un projet portant le fichier témoin.
- **Secrets** : masquage `redactEnv` conservé, jamais affiché ; les valeurs `-P` sont aussi masquées si elles
  correspondent à une valeur de `redactEnv` (correction d'un défaut relevé à l'étude).

## 6. Fonctions perdues (retrait de ZombieBuddy)

Vidage d'état Java (`JavaStateDumper`), journal superposé (`LogOverlay`), accès HTTP distant, appel de classes Java
non exposées à Lua, exécution de Lua hors `-debug`. Tout le reste est réécrit sur le canal par fichiers (étude § 6).
