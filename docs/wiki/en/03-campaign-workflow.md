# Reusable workflow for mod campaigns

This procedure incorporates the Operation Artemis campaign feedback: avoid repeated console commands, unnecessary pauses between cases and scattered evidence. It applies to future mods. Offline contracts pass; one real solo 42.21 campaign completed13 children with distinct reports, verified archival ACKs and one optional skip. The project collector used the shared ACK implementation. Standalone generic CLI, rejection/timeout probes after the latest fix and multiplayer still need their own in-game validation.

## Prepare before asking the player to start

Read the workspace/project instructions, the authoring guide, actual mod code and metadata, then the sources for the running Build. Inspect loading errors and active variants. Compare old protocols with implemented actions. Keep existing changes and all evidence. Use only dedicated test games; never edit Steam Workshop sources or personal saves.

Prepare reloadable scenarios and a reloadable plan for each compatible route. Give named assertions, bounded waits and explicit cleanup. Use debug helpers only for preconditions: objectives must use actual game actions. Do not reset progress to join exclusive endings. Plan optional entries with read-only `when` conditions and a stated skip reason; a skipped case is unexecuted, never passed.

Record which actions remain human: creating/loading a game, a final confirmation, visuals/audio, full save/restart and multiplayer. Estimate real waits from the configured game day and distinguish gameplay waits from test/archival waits. Combine compatible negative cases before irreversible commitments. Keep long or destructive branches explicit rather than silently making a nominal run much longer.

## Run with one command per compatible game

Install scenarios under `Zomboid/Lua/PZPuppet/scenarios/<Namespace>/`. Back up a differing installed copy before replacement. Restart the entire game after an engine or mod change; scenario files alone are reloadable. Review the new startup log before execution.

Start exactly one collector before launching the plan. A generic collector is provided:

```powershell
python PZDevKit/pzdev.py scenario collect --output <Project>/tests/puppeteer/reports/runs
```

`--user` selects another game-user directory; `--seconds 0` watches until interrupted. Project-specific collectors may also maintain a coverage table, provided they implement the same archive acknowledgement contract. Never run both against one game directory.

Then paste the installed plan command:

```lua
PZDevKit.Scenario.runBatchFile("MyMod/campaign.lua",{playerIndex=0},{route="nominal"})
```

Close the console and resume the game. Compatible cases sequence automatically after cleanup and verified archival. The collector compares the closed persistent report with `last-report.txt`, saves distinct evidence and rejects new Lua errors since batch start, including errors between children. Missing archival stops the engine within a bounded deadline; do not fabricate an acknowledgement. Inspect `PZDevKit.Scenario.batchStatus()` if stalled.

An assertion failure, exception, cancellation or archive rejection stops the plan. Read the actual report and first relevant error, distinguish a test defect from a mod defect and preserve the failed attempt. Fix production only within user authorization. A retry must document retained real acquisitions; never claim an earlier acquisition was replayed. Provide the precise next command as soon as the outcome and preconditions are known. Automatic file collection does not itself let an agent type in an inaccessible game console or send chat updates while it is inactive.

## Keep one index and clear bug status

Store one immutable directory per execution under `reports/runs/`, with raw report, console, pre-scenario context, new errors, runtime metadata and, for batches, receipt and batch errors. Keep before-fix sources/patches under `reports/fixes/`, offline checks under `reports/inspection/` and isolated console captures under `reports/snapshots/`.

Maintain an index, a coverage table and a current bug register. The table contains scenario, preconditions, exact command, expected result, observed result, proof and passed/failed/unexecuted status. Keep historical passes attached to their source version; adding assertions or fixing production does not revalidate them automatically. Separate confirmed mod bugs, test/engine defects, native resource warnings and unresolved attribution.

For each bug, state evidence, cause confidence, authorization, files changed, offline checks, actual game revalidation and remaining limits. Distinguish “fix applied”, “offline checks passed” and “verified in game”. Never mark every bug closed because some scenarios passed. Archive stopped children as well as successful ones. A batch failure leaves later cases unexecuted.

Complete visual/audio, full process restart/save checks and multiplayer with their distinct procedures. Lua contract tests establish orchestration behavior, not game physics, Java rendering, persistence or networking.
