# Writing scenarios for PZDevKit (formerly PZPuppeteer)

This contract is for mod developers and coding agents. Target: Project Zomboid 42.21; public namespace: `PZPuppet`. The engine is generic: scenarios drive the character's Lua actions and interface callbacks, then observe their results.

## Expected deliverables from a test author

For each scenario, provide:

1. A name prefixed with the mod's name, its objective and preconditions: mods/versions, singleplayer or client, permissions, map, items, skills and sandbox settings.
2. The Lua file, its location and a copyable launch command. Choose the console, registered module or reloadable file format described in the [README](../../../README.md).
3. Actual game actions, observable assertions and bounded timeouts. Name each assertion so the report explains failures.
4. Explicit setup and cleanup of only the test's own creations. State which persistent changes cannot be restored.
5. The expected result and validation limits: static inspection, Lua simulation or actual execution with its game version. Do not claim in-game validation based only on mocks.

Before writing an adapter, read the tested mod's code and the vanilla sources for the running Build: callback, action class, signature, event, server authority and result. Do not invent APIs or interface fields. The names `MyMod`, `window` and `confirmButton` in the README are placeholders to replace.

## Locations and formats

**Console**: a chunk that builds a scenario and calls `:run()` can be pasted into the debug Lua console or sent with `pzdev lua -f file.lua`. The examples in `PZDevKit/examples/scenarios/` are reloadable files (below); `pzdev scenario run FILE.lua` copies one to `Zomboid/Lua/PZPuppet/scenarios/pzdev/` and runs it.

**Registered module**: create a separate test mod with `common` and `42.21` directories, a `mod.info` declaring `require=\batman_PZDevKit\<testedModId>`, and the module under `42.21/media/lua/client/<Namespace>/PZTests/`. Give the test mod its own identifier. Use `require "PZPuppet/PZPuppet_Game"` and, if needed, `require "PZPuppet/PZPuppet_Debug"` before registration. Loading registers a factory without acting on the player:

```lua
PZDevKit.Scenario.register("MyMod.case",function(params)
    return PZDevKit.Scenario.scenario("MyMod: case")
        :check("Precondition",function(c) return c.player~=nil end)
end,true)
```

`PZDevKit.Scenario.run("MyMod.case",options,params)` calls the factory on every launch. `PZDevKit.Scenario.listScenarios()` returns a sorted Lua array. `replace=true` in `register(name,factory,replace)` allows replacement on reload; use unique names to avoid overwriting another mod's factory. Without `replace`, a collision fails.

**Reloadable file**: under the game's user data directory, create `Zomboid/Lua/PZPuppet/scenarios/<Namespace>/<Case>.lua`. Save it as UTF-8 and return `function(params) ... return scenario end`; do not put `:run()` in this file. Copy [examples/04-equipped-fixture.lua](../examples/04-equipped-fixture.lua) to that location, then launch:

```lua
PZDevKit.Scenario.runFile("MyMod/equipment.lua",{playerIndex=0},{itemType="Base.Screwdriver"})
```

`runFile(path,options,params)` reads and compiles the file again each time; `loadScenario(path,params)` only returns the constructed scenario. Paths use `/`, without a drive letter, absolute path, `..` or extension other than `.lua`; names contain letters, digits, `_` or `-`. Limit: 256 KiB. No system `dofile`/`loadfile` is needed. The loader uses Lua APIs exposed by the game. It does not find or execute files automatically. Modules imported through `require` keep their cache: editing the scenario file does not reload the tested mod's code.

A factory receives `params` (an empty table by default) and returns **a fresh scenario**. It validates its parameters but has no side effects. Defer player lookups, spawns and actions to callbacks executed during the scenario. Files are trusted Lua code executed in the game environment, without isolation.

## Execution contract

`:run({playerIndex=0,manualStop=true,writeReport=true})` starts on the next tick and returns the report table. These three options show the default values. Only one scenario runs at a time. The local player must be alive, its action queue empty and `-debug` enabled. A scenario object can be used only once.

Each callback receives `c`, containing `player`, `playerIndex` and `vars` (a fresh table for each run). `step` also passes a `data` table specific to that step. Keep callbacks short, without waiting loops, sleeps or shell execution. Store references in `c.vars` rather than globals shared between tests. The method list is in the README.

Predicates for `check`, `await`, `step.poll` and actions must return **exactly `true`** on success. A Java value, number or nonempty string is not enough. `check` fails immediately otherwise; `return false,"reason"` supplies a diagnostic. `await` retries until the timeout. An exception also fails the scenario. For movement, check position and floor; for equipment, the expected hand; for a recipe, the produced item, consumed ingredients and their quantities.

An unmet `check` records a failed result and runs cleanup without raising a Lua assertion. This avoids a debugger break for an expected test failure. Exceptions inside callbacks still remain runtime errors and may trigger the game's Break On Error setting before they are caught.

Waits count seconds of active execution, suspend during pauses and cap large gaps between ticks. Close the console and unpause at normal speed. Death, sleep, disconnection and, by default, manual movement/cancellation stop the test. `manualStop=false` disables only the last type of interruption.

`call` is synchronous. For an operation that queues a timed action, use `act(label,factory,predicate,timeout)` or `interact(label,callback,predicate,timeout)`: the engine waits for its queue to finish **and** the observed result to match. The action factory returns an instance associated with `c.player`. The instance must not have `ignoreAction` enabled. Do not globally replace vanilla classes. Transfers and equipment require objects accessible through the normal interface.

Register `finally(callback)` before `run`; callbacks execute in reverse registration order on success, failure or cancellation. A cleanup error turns a success into a failure. This is not a save transaction: do not promise to automatically restore killed zombies, consumed recipe inputs, the world or weather.

## Setup and debug helpers

`local D=PZDevKit.World`. All functions require `-debug`. The mutations below also require a **singleplayer game** to use native authority and return the actual created objects. Calls fail on a client or server; they do not send implicit admin commands. `position`, `itemTypes` and `vehicleTypes` are read operations. This scope does not constitute multiplayer validation of the engine.

| Function | Arguments, return value and conditions |
|---|---|
| `D.position(index)` | Local index defaults to 0; returns `{x,y,z}`. |
| `D.teleport(x,y,z,index)` | Calls `player:teleportTo`; requires the player to be outside a vehicle with an empty queue; returns the player. X/Y are rounded down; Z is an integer from -32 to 31. To wait for loading, use `scenario:teleport(x,y,z,timeout)` (60 s by default). |
| `D.spawnItem(fullType,count,index)` | Exact full type, integer count 1–100, default 1; returns a Lua array of `InventoryItem` objects in the main inventory. |
| `D.spawnWorldItem(fullType,x,y,z,count)` | Same return type; ordinary ground items on an already loaded tile. Rejects generators, animals and corpses that turn into distinct world objects. |
| `D.spawnVehicle(fullType,x,y,z,options)` | Exact script of an available vehicle; floor 0, clear and loaded area. Options: `direction="N"` (`N/S/E/W`), `skin` (index starting at 0), `clearRadius=4` (integer 1–20). Returns a placed `BaseVehicle`. Increase the radius for large models; the game may still reject placement. Orientation and condition follow the vanilla debug spawn behavior. |
| `D.vehicleKey(vehicle,index)` | Creates the vehicle's key, adds it to the inventory and returns the item. |
| `D.spawnZombie(x,y,z,options)` | Loaded tile; returns an `IsoZombie`. |
| `D.spawnZombies(x,y,z,count,options)` | Integer count 1–100; returns a Lua array. Options: exact `outfit` or omitted, `femaleChance=50` (0–100), `health=1` (>0), booleans `crawler`, `fallOnFront`, `fakeDead`, `knockedDown`, `invulnerable`, `sitting`. These booleans default to `false`. Coordinates are rounded down to the tile. |
| `D.freezeZombie(zombie,boolean)` | Enables/disables `setUseless`; returns the previous state. Changes AI behavior; cannot validate an active zombie's behavior. |
| `D.setFlags(table,index)` | Boolean keys: `god`, `ghost`, `invisible`, `instantActions`, `unlimitedCarry`. Returns previous values for only the changed keys; pass them back to `setFlags` to restore them. |
| `D.setStats(table,index)` | Exact `CharacterStat` identifiers: `Hunger`, `Thirst`, `Endurance`, etc. Values must be within game bounds; returns previous values. For example, `Hunger/Thirst/Fatigue/Endurance`: 0–1; `Panic/Pain/Boredom/Unhappiness`: 0–100. |
| `D.heal(index)` | `RestoreToFullHealth`, living player only; does not resurrect. |
| `D.setSkill(name,level,index)` | Exact `Perks` identifier and integer 0–10; sets the level and XP to that level's threshold, returns the previous level. Does not preserve the exact previous XP. |
| `D.setTimeOfDay(hours)` | Hour in the range [0,24); returns the previous time. |
| `D.weather(kind,hours)` | `clear` stops weather and thunder; `storm/tropical/blizzard` start an episode (positive duration, default 24 game hours). The previous weather is not saved. |
| `D.itemTypes(query)` / `D.vehicleTypes(query)` | Sorted Lua arrays of full names, with an optional case-insensitive text filter. Discover types from enabled mods. |
| `D.removeSpawned(object)` | Removes only a creation from these helpers; rejects unregistered objects and occupied vehicles. Does not remove a corpse produced after a spawned zombie dies. |

Direct helper calls execute immediately. For setup inside a scenario, call them in `:call("SETUP: ...",function(c) ... end)`. Store each returned creation in `c.vars` and arrange its `finally` cleanup. Creations are tracked during the Lua session; restarting does not allow automatic cleanup of persistent objects from the previous game session.

Do not grant a skill, place the finished product, enable `instantActions` or teleport the player when the result being tested is precisely gaining that skill, crafting, timing or walking. These helpers establish **preconditions**; the tested actions must then use the game. Use a test game for scenarios that change the world.

## Other mod adapters and networking

Import action classes using the exact case of their path under `client` or `shared`. Read their preconditions and menu callback: call that callback through `interact` when the vanilla sequence prepares several actions. Check a state outside the action itself; removal from the queue is not proof of success.

For fixed world loot, use `:approachContainer(function(c) return c.vars.item:getContainer() end,45)` before `:transfer`. It selects an adjacent square with vanilla `AdjacentFreeTileFinder.Find`, walks there with `ISPathFindAction`, then waits for inclusion in the vanilla accessible-container list. It does not open locks, cross floors or bypass transfer checks. For vehicle containers, use `walkToVehicle` with the appropriate area. Keep partial real pickups after an interrupted run; any resumption must identify these explicitly rather than silently recreating loot or reporting the pickup as replayed.

For a network response, `:awaitServerCommand(module,command,function(c,args) ... end,timeout)` observes commands from the start of the scenario and keeps the latest 64. On a match, `c.vars.lastCommand=args`. Previously consumed responses cannot satisfy later waits. Correlate scenario and command identifiers rather than accepting the first event with the same name. A stream of more than 64 commands may evict a response; place waits promptly.

Some mods call their handler directly in singleplayer. An adapter can use `PZDevKit.Scenario.captureServerCommand(module,command,args)` from a targeted temporary interception. Preserve the original handler's arguments and return values, and restore it in `finally` only if the installed reference is still the adapter's own. Do not assume all mods use the same protocol. Respect server authority and the tested mod's permissions.

## Reports and validation

`PZDevKit.Scenario.status()` returns the active step; `printStatus()` writes a summary. `lastReport` contains `name`, `status`, `steps`, `reason`, `duration` and `position` (`x/y/z/queued`). Each step row contains `label`, `status`, `duration` and an optional `reason`. Unexecuted steps remain `pending`; final status is `passed`, `failed` or `cancelled`. `PZDevKit.Scenario.stop()` cancels the scenario and only the actions it owns.

Every run has a distinct `runToken` and text report under `Zomboid/Lua/PZPuppet/reports/<runToken>.txt`. `Zomboid/Lua/PZPuppet/last-report.txt` is also replaced when the next scenario finishes. Reports include the actual player index and manual-stop option. Logs use `[PZPuppet]` in `console.txt`. `writeReport=false` disables the files for individual runs; the table and logs remain available.

## Sequential campaigns and the archive ACK contract

Apply the [campaign workflow](03-campaign-workflow.md) when preparing a complete mod campaign. The reusable external implementation is `pzdev scenario collect` (`cli/pzdev/collect.py`); start it with `--output <project>/tests/puppeteer/reports/runs`. Project-specific collectors may maintain their own result tables but must preserve the same evidence checks.

`PZDevKit.Scenario.runFiles(entries,options)` sequences reloadable scenarios. Each entry is `{path="MyMod/case.lua",params={...},options={...}}`. Entry options override global options; `playerIndex` defaults to 0, `manualStop` to true. `writeReport=false` is forbidden in a campaign. `ackTimeout` defaults to 30 wall-clock seconds and is bounded to 300 seconds. Scenario steps retain their normal active-time timeouts and actual game actions.

`PZDevKit.Scenario.runBatchFile(path,options,params)` hot-loads a plan with the same path restrictions and 256 KiB limit as scenario files. The plan returns `function(params) return entries end`. It must have no actions or automatic launches during loading. [The batch example](../examples/06-batch-plan.lua) sequences two equipment scenarios, each with its own actual equip action and cleanup.

A child factory may delegate construction to another file through `PZDevKit.Scenario.loadScenario`, as a wrapper loading a shared suite. During this synchronous construction only, the batch permits nested factory loading. Factory calls to `runFile`, `run`, `runFiles` or `Scenario:run()` remain forbidden. Outside construction, including during archive waits, public loading remains blocked. A loading exception releases the construction permission and stops the batch.

An optional entry may provide `when=function(params) return boolean end` and a nonempty `skipReason`. The condition is evaluated immediately before that entry, must return exactly true or false, and should only observe current state. False emits a `Batch skipped` log and increments `skipped`; it does not run the case or assign it a successful scenario report. Conditions returning another value or raising an error stop the campaign. An entirely skipped plan has `completed=0` even though orchestration finishes normally.

Only one scenario or campaign can run. While a campaign awaits archival, `run`, `runFile`, `loadScenario`, another campaign and direct `scenario:run()` are refused. `PZDevKit.Scenario.batchStatus()` returns a snapshot with `token`, `status`, `index`, `total`, `path`, `runToken`, `completed`, `skipped` and optional `reason`. `PZDevKit.Scenario.runStatus()` returns `busy`, `scenario` and `batch`. `stopBatch(reason)` cancels its active child, executes cleanup once and removes the batch listener. `stop()` also stops an active campaign. A Lua engine reload stops old runners and removes their listeners before installing new ones.

The engine uses the following file bridge, implemented with the inspected Build 42.21 `getFileReader`/`getFileWriter` APIs:

1. Each child writes its full report and closes both `PZPuppet/reports/<runToken>.txt` and `PZPuppet/last-report.txt`, after all cleanup. The text keeps its existing first two lines, plus `Run token`, `Batch token`, `Batch index`, `Scenario path`, `Persistent report`, `Player index` and `Manual stop` metadata.
2. A successful child emits `[PZPuppet] Batch archive requested: <runToken> | report: PZPuppet/reports/<runToken>.txt`. The run token is also logged immediately after `Starting`. Tokens combine timestamp and a sequence preserved during Lua reloads.
3. An external collector must verify the persistent file's token, batch token and final status, archive distinct report and console evidence, and check every new Lua error since campaign start, including errors after child completion. Java's file writer can suppress some I/O failures, so a mere file-exists check is insufficient. An external game error is not visible to the Lua runner automatically.
4. After closing its evidence files and updating its result table, the collector atomically replaces `Zomboid/Lua/PZPuppet/batch-ack.txt` with one line: `PZPuppet ACK <runToken> passed`. If evidence is incomplete or a new game error is present, it writes `PZPuppet ACK <runToken> rejected <reason>` instead. Use a temporary file and rename, not a partial in-place write; run only one collector per game directory. Never fabricate an ACK to bypass evidence collection.
5. The engine polls every 500 ms on available ticks. A stale token or malformed line is ignored. A matching rejection or expired ACK timeout fails the campaign. Each child, including the final child, needs an ACK. A pause suspends ticks but the archive deadline is wall-clock time; on resumption the engine checks an available matching ACK before declaring a timeout.

The external error check only covers evidence observed before the collector's ACK. It cannot predict an unrelated error after confirmation. Keep the collector running across the entire campaign. No acknowledgement advances story state; it only permits loading the next case.

An unmet assertion, interrupted child, cleanup error, report failure or loading error stops the campaign. Children are freshly loaded and keep individual reports; no debug progression is added. Separate branches and mutually exclusive endings need separate dedicated test games. A campaign does not create or edit saves, change game speed, shorten gameplay waits or restore irreversible changes by itself. Human checks such as visuals, audio, save/reload and multiplayer remain separately reported.

The batch runner and ACK reader have contract tests with simulated Lua services. Separately, one real solo 42.21 campaign completed 13 children with a project collector using the shared ACK implementation, one conditional skip and final batch success after a full engine restart. This validates the exercised positive path; standalone generic collector CLI, rejection/timeout probes after the latest fix and multiplayer still need their own in-game checks.

Run local syntax and contract checks, then the in-game check (`pzdev scenario run` on a game left open by `pzdev sp --no-quit`). For a new mod test, also check an expected failure, its cleanup, a real success and missing preconditions. For multiplayer, add client/server and reconnection cases; Lua mocks do not prove physics, rendering or Java networking behavior in the game.
