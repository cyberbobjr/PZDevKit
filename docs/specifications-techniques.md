# Spécifications techniques — PZDevKit (cible)

Statut : **proposées** (ADR-001). Cible PZ 42.22 ; variante de mod `42.21/` (chargée en 42.22).

## 1. Canal live par fichiers

Racine `<Lua>` = `<cache>\Lua` en mode cache, `%USERPROFILE%\Zomboid\Lua` en mode attaché.

### Commande — `<Lua>\pzdev\cmd.lua` (écrite par la CLI)

```
--pzdev 1 id=<entier croissant> [shot] [timeoutMs=<n>]
<code Lua : un bloc, « return » facultatif>
```

La CLI écrit `cmd.lua.tmp` puis renomme (écriture atomique côté Windows). Le mod relit le fichier toutes les 400 ms
(`OnTickEvenPaused`, donc aussi en pause) et n'exécute qu'une fois chaque `id`.

### Réponse — `<Lua>\pzdev\out.txt` (écrite par le mod)

```
--pzdev 1 id=<n> status=ok|error|compile-error durationMs=<n>
-> <valeur rendue, sérialisée, 4 Kio max, profondeur 2>
info <ligne émise par PZDevKit.info(...)>
error <message>            (si status ≠ ok)
shot pzdev_<id>.png        (si « shot » demandé)
--end
```

La CLI ne lit la réponse que si `--end` est présent (même principe que `PZAT-END`). Erreur : attrapée par `pcall`,
le jeu continue ; une erreur de compilation est distinguée. La capture est copiée par la CLI vers
`<runs ou build>\live\`.

**Durée** : une commande s'exécute dans une seule image. Un travail long (marche, action chronométrée) passe par un
scénario lancé par la commande puis suivi par `return PZDevKit.status()`. La CLI n'attend jamais plus de 2 s sans
afficher d'état (règle « l'utilisateur regarde en direct ») ; délai total par défaut 30 s.

**Compatibilité** : depuis l'étape 9, `tuto_lib.lua` est supprimé et un tournage `record --live` passe par ce même
canal ; les anciens fichiers `pztuto_cmd.lua` / `pztuto_out.txt` ne sont plus lus ni écrits. L'ancien `live.py` a été retiré
à l'étape 10.

**Mise en œuvre (étape 4)** :
- `Live.lua` n'est inscrit sur `OnTickEvenPaused` que si `isDebugEnabled()` ; il réutilise les fonctions de fichiers
  de `Driver.lua` (pas de `Core.lua` séparé). Un `id` déjà répondu dans `out.txt` n'est pas rejoué après un
  rechargement Lua. La fenêtre du débogueur Lua est coupée pendant l'appel seulement, réglage de l'utilisateur rétabli.
- Valeurs : une ligne `->` par valeur rendue (`nil` compris), tables triées sur 2 niveaux (`{...}` au-delà),
  chaînes multilignes ramenées à une ligne (` / `), 4 096 caractères au plus.
- `id` : millisecondes de l'horloge, toujours supérieur au dernier id répondu. Cible absente : refus (code 2),
  aucun dossier créé.
- Capture : `Zomboid/Screenshots/pzdev_<id>.png` de la cible (le jeu l'écrit à l'image suivante), copiée dans
  `PZDevKit/runs/live/` (ignoré par git).
- `sp --no-quit` inscrit son cache dans `%TEMP%\pzdev\last-live.json` : cible par défaut tant que le cache existe.
- Limite (confirmé en jeu) : une erreur rattrapée reste comptée par le jeu en mode debug (compteur « ERROR » en
  bas à droite, pile dans la console) : un test qui compte les erreurs Lua la verra.

## 2. CLI `pzdev`

| Sous-commande | Rôle | Remplace |
|---|---|---|
| `sp|server|mp|check <Projet> [options]` | tests automatisés, options et codes identiques | `pz_autotest.py` |
| `attach [--timeout]` | vérifie qu'un jeu `-debug` avec le mod répond (ping par le canal) | `pzremote.py wait` |
| `lua "<code>" [-f fichier] [--shot] [--target cache:<dir>|real]` | une commande live | `live.py`, `pzremote.py lua/file` |
| `repl [--target …]` | boucle interactive sur le canal | — |
| `world tp|item|zombies|vehicle|time|weather|stat|skill|flags|clean …` | aides monde, traduites en Lua `PZDevKit.World.*` | `PZPuppet.Debug`, `T.*` monde |
| `scenario run|batch|status|stop|collect …` | moteur de scénarios, campagnes et accusés | `PZPuppet.runFile/runBatchFile`, `collect_reports.py` |
| `logs [--errors\|--all-errors\|--result\|--grep RE] [--tail N] [--server] [--target …\|--file F]` | résumé de la session (début, version, mods, chargements Lua, erreurs, `PZAT-RESULT`) et extraits filtrés de `console.txt` ou `server-console.txt` ; `--errors` rend 1 s'il y a une erreur Lua. Rapports de scénario : `pzdev scenario` (étape 7) | — |
| `record <video-dir> [--live|--rehearse] [-P] [--make-save NOM [--replace]]` | tournage scripté | `record.py` |
| `take <video-dir>`, `quit <video-dir>` | nouvelle prise (envoie `T.take()`, attend `build/timeline.json`, code 1 si la prise a un FAIL), fermeture du jeu | `live.py take|quit` |
| `sound check\|install` | son de `film --video` : `soundcard` + `numpy` dans `PZDevKit/.pydeps` (boucle locale de la sortie par défaut, aucun micro) ; `check` rend 0 si FFmpeg et le son sont prêts | `pip install --target tools/.pydeps …` |
| `film FILE.lua\|--path REL [-P] [--video [--no-audio] [--size]] [--stall S] [--target …]` | production filmée dans la partie ouverte (`sp --no-quit`, `PZAT_SOUND=1` pour le son, ou `--target real`) ; résultats dans `runs/film/<date>_<nom>/` (`take.json`, PNG, vidéo) | `tournage.py` + `recorder.py` |
| `sheet <video-dir> [pas]` | planche contact | `sheet.py` |
| `assemble <video-dir>` | intro, corps monté, outro, musique, sous-titres EN/FR (D13 : déplacé sans changement) | `assemble.py` |

Codes de sortie de toutes les sous-commandes : 0 OK, 1 échec du test ou de l'assertion, 2 délai, démarrage ou erreur
Lua, 3 jeu déjà lancé (jamais tué). `pzdev attach` rend 2 si le jeu ne répond pas.

`--target` par défaut : la dernière session live ouverte par `record --live` ou `sp --no-quit` (pointeur
`%TEMP%\pzdev\last-live.json`), sinon `real`.

## 3. API Lua publique (`PZDevKit`)

- `PZDevKit.info(...)`, `PZDevKit.status()`, `PZDevKit.stop(reason)`.
- `PZDevKit.World` : `position`, `teleport`, `spawnItem`, `spawnWorldItem`, `spawnVehicle`, `vehicleKey`,
  `spawnZombies`, `spawnZombie`, `freezeZombie`, `removeSpawned`, `clearZombies`, `clearBodies`,
  `clearSquare(x, y, z, test)`, `setTime`, `weather(kind, hours)` (événement), `holdWeather(clouds, wind)` (météo
  sèche tenue pour un plan), `night`, `setStats`, `heal`, `setSkill`, `setFlags`, `zoom`, `speed` (différée pendant
  une marche, `OnTick` seulement pendant l'attente), `itemTypes`, `vehicleTypes`. Changements : `-debug` et partie
  solo exigés ; valeur précédente rendue quand elle existe. CLI : `pzdev world <action>` (`world -h`), traduite en
  appel Lua envoyé par le canal live.
- `PZDevKit.Scenario` : `scenario`, `register`, `run`, `loadScenario`, `runFile`, `runFiles`, `runBatchFile`,
  constructeur et actions de PZPuppeteer inchangés (`Scenario.lua`, `Game.lua`), plus l'étape `:teleport` (ex-`Debug`).
  Contrats gardés à l'identique pour les collecteurs : préfixe `[PZPuppet]` du journal, en-tête `PZPuppet 0.1.0` des
  rapports, fichiers sous `Zomboid/Lua/PZPuppet/`. Plus de globale `PZPuppet` depuis l'étape 10 :
  les scénarios appellent `PZDevKit.Scenario`.
  CLI : `pzdev scenario run FILE|--path|--name`, `batch --path`, `status`, `stop`, `collect` (`scenario -h`) ;
  `run` copie FILE sous `PZPuppet/scenarios/pzdev/`, suit la progression (au moins toutes les 2 s) et affiche le
  rapport ; codes 0 réussi, 1 échoué ou annulé, 2 erreur, pas de réponse ou délai (scénario arrêté).
- `PZDevKit.Production` : `production`, `scene` et méthodes de PZDirector inchangées ; un seul défaut corrigé : la
  chaîne non ASCII d'`Actions.lua:66` (interdite en Kahlua), désormais message anglais. Différence avec `tournage.py` :
  `film` n'ouvre ni le jeu ni une sauvegarde (plus de clic simulé, plus de copie `Saves_backup`) ; la partie est celle du
  lanceur (copie en cache) ou celle de l'utilisateur. `--reload` n'est pas repris (redémarrer la partie de test).
- `PZDevKit.Tuto` : `PZDevKit.Tuto.new()` rend une table `T` neuve par tournage, avec les fonctions de `tuto_lib`
  (`step`, `caption`, `openCraft`, `showMenuPath`, `take`…). Les aides monde (`clearSquare`, `clearZombies`,
  `clearBodies`, `time`, `weather`, `night`, `zoom`, `teleport`) délèguent à `PZDevKit.World` (`setPosition` ajouté
  pour `teleport`). `T.keepEntry(callback)` garde une entrée de menu qu'un tournage masquerait comme entrée de débogage
  (remplace l'exception LiveWire codée en dur). `record` écrit les hooks `T = PZDevKit.Tuto.new()`, `T.name`, la scène,
  `return T.hooks()` ; seule `scene.lua` est contrôlée ASCII.

Fichiers de scénarios et rapports : chemins de PZPuppeteer conservés (`Lua/PZPuppet/scenarios`, `reports`,
`last-report.txt`, `batch-ack.txt`) pour ne pas déplacer les 47 scénarios personnels ni les campagnes d'Artemis.

## 4. Correspondance ancien → nouveau

| Ancien | Nouveau | Alias |
|---|---|---|
| `python .claude/tools/pz-autotest/pz_autotest.py …` | `python PZDevKit/pzdev.py …` | retiré à l'étape 10 |
| `pzat.core`, `pzat.runner` (`Env`, `Options`, `Runner`, `client_java_command`, `server_java_command`), `pzat.winproc`, `pz_autotest.main` | `pzdev.core`, `pzdev.launcher`, `pzdev.winproc`, `pzdev.autotest.main` | retiré à l'étape 10, après migration des 9 scripts (LiveWire ×6, MilitaryDrop ×2, un projet privé ×1) |
| `batman_PZAutoTestDriver` | `batman_PZDevKit` (Driver) | — (ajouté automatiquement, absent des `autotest.json`) |
| `Lua/pz-autotest/command.txt`, `control.txt`, `status.txt`, `result.txt`, `hooks.lua` | inchangés | — |
| `tuto_lib.lua` concaténé aux hooks | `T = PZDevKit.Tuto.new()` en tête des hooks | — (supprimé à l'étape 9) |
| `record.py`, `live.py`, `sheet.py`, `assemble.py` | `pzdev record`, `lua`, `take`, `quit`, `sheet`, `assemble` | retirés à l'étape 10 |
| `pztuto_cmd.lua` / `pztuto_out.txt` | `pzdev/cmd.lua` / `pzdev/out.txt` | — (plus servis depuis l'étape 9) |
| `PZPuppet.*` | `PZDevKit.Scenario.*`, `PZDevKit.World.*` (`Debug`) | retiré à l'étape 10 (`Compat.lua`) ; campagne Artemis migrée |
| `PZDirector.*` | `PZDevKit.Production.*` | retiré à l'étape 10 (`Compat.lua`) ; productions Artemis migrées |
| `PZPuppeteer/tools/collect_reports.py` | `pzdev scenario collect` (+ module `pzdev.collect`, importé par le collecteur d'Artemis) | PZPuppeteer archivé (D14) |
| `pzremote.py`, `tournage.py`, `PZDirector-Tournage.bat`, ZombieBuddy | `pzdev lua/attach`, `pzdev film` | aucun (supprimés) |

## 5. Contrats conservés à l'identique

`autotest.json` des dix projets (aucune modification), contrat `H.start/H.done/H.result(ctx)` et `ctx.params`,
format `result.txt`, `summary.json`, `summary.txt`, dossier `runs\`, lignes console `[PZTUTO]` (lues par
`record`), `[PZPuppet]` (lues par les campagnes).

## 6. Corrections 42.22 à intégrer

- Comparaison de `getWorld():getGameMode()` (objet `GameMode` en 42.22) : comparer `tostring(v)`.
- `addZombiesInOutfit` : surcharge à 13 paramètres gardée en 42.22 (`LuaManager.java:8334`), appel inchangé.
- Pièges connus repris tels quels : accélération différée pendant une marche, arrêt immédiat d'une préparation
  ratée (`abort`), remise en place de la fenêtre avant `gdigrab`, coupe en début de segment (contrôle `blackdetect`).
