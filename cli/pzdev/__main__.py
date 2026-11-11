"""Sub-command dispatcher of pzdev."""

from __future__ import annotations

import sys

USAGE = """usage: pzdev <command> [args]

commands:
  sp|server|mp|check <project> [options]   automated in-game test run (formerly pz-autotest; -h for options)
  lua "<code>" | -f file.lua [--shot] [--target cache:<dir>|real]   run Lua in a running game (live channel)
  repl [--target ...]                     one Lua command per line
  attach [--target ...]                   check that a game answers on the live channel
  world <action> ...                      world helpers through the live channel (world -h)
  scenario run|batch|status|stop|collect ...   scenario engine (scenario -h)
  film FILE.lua [-P ...] [--video]        shoot a production in the open game (film -h)
  sound check|install                     sound of film --video (soundcard + numpy in PZDevKit/.pydeps)
  record <video-dir> [--rehearse|--live|--make-save NAME] [-P k=v]   film a tutorial video body (Tuto scenes)
  take <video-dir> | quit <video-dir>      new take / close the game of record --live
  sheet <video-dir> [seconds]             contact sheet of the recorded body
  assemble <video-dir>                    intro, edited body, outro, music, EN/FR subtitles
  logs [--errors|--result|--grep RE] [--server] [--target ...|--file F]   game log of the session
  fingerprint save|check <file.json>   fingerprint of the real saves, options and mod lists
"""


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0 if argv else 2
    command, rest = argv[0], argv[1:]
    if command in ("sp", "server", "mp", "check"):
        from pzdev import autotest
        return autotest.main(argv)
    if command in ("lua", "repl", "attach"):
        from pzdev import live
        return live.main(argv)
    if command == "record":
        from pzdev import record
        return record.main(rest)
    if command in ("take", "quit"):
        from pathlib import Path
        from pzdev import record
        if len(rest) != 1:
            print(f"usage: pzdev {command} <video-dir>", file=sys.stderr)
            return 2
        return record.take(Path(rest[0]).resolve()) if command == "take" else record.quit_game(Path(rest[0]).resolve())
    if command == "sheet":
        from pzdev import sheet
        return sheet.main(rest)
    if command == "assemble":
        from pzdev import assemble
        return assemble.main(rest)
    if command == "sound":
        from pzdev import sound
        return sound.main(rest)
    if command == "film":
        from pzdev import film
        return film.main(rest)
    if command == "scenario":
        from pzdev import scenario
        return scenario.main(rest)
    if command == "logs":
        from pzdev import logs
        return logs.main(rest)
    if command == "world":
        from pzdev import world
        return world.main(rest)
    if command == "fingerprint":
        from pzdev import fingerprint
        return fingerprint.main(rest)
    print(f"pzdev: unknown command {command!r}\n\n{USAGE}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
