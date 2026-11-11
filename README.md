# PZDevKit (DEV-ONLY)

> **Development tool. Never publish this mod or this folder to the Steam Workshop.**
> `Contents/DEV-ONLY-DO-NOT-UPLOAD.txt` makes the game's upload screen and the local publishing tool refuse it.

PZDevKit gathers the local development tools for Project Zomboid Build 42.22 into one mod (`batman_PZDevKit`) and
one command line (`pzdev`): automated single player / dedicated server / multiplayer test runs on copies of the game
data, a live Lua channel through files, world helpers, scripted scenarios, filmed productions and tutorial takes.
No Java agent.

Status: plan 001 done on 2026-11-11 (see `docs/ADR-plans/termines/plan-001-fusion-outils-pilotage.md`).

```
python PZDevKit/pzdev.py check  <Project>                       # configuration and mods only
python PZDevKit/pzdev.py sp     <Project> --wait-idle 3600      # solo run on a cached copy of a save
python PZDevKit/pzdev.py server <Project> --wait-idle 3600      # dedicated server only
python PZDevKit/pzdev.py mp     <Project> --clients 2 --wait-idle 3600
# exit codes: 0 ok, 1 tests failed, 2 timeout / start failure / error, 3 a game or server is already running

python PZDevKit/pzdev.py sp <Project> --no-quit             # leaves the test game open for the live channel
python PZDevKit/pzdev.py lua "return 1+1" [--shot]          # runs Lua in that game (or --target real: own -debug game)
python PZDevKit/pzdev.py repl | attach

python PZDevKit/pzdev.py fingerprint save <file.json>     # before a run (refused while a game runs)
python PZDevKit/pzdev.py fingerprint check <file.json>    # after: exit 0 = real saves and options untouched
```

Tests: `python -m unittest discover -s tests` (from this folder).

Documentation (French): [docs/README.md](docs/README.md).
