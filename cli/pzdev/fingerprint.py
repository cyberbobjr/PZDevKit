"""Fingerprint of the real user data, to prove a run left it untouched.

Small configuration files are hashed (SHA-256): options.ini, Lua/pz_modlist_settings.cfg, every file under Server/
and every mods.txt under Saves/. Other files under Saves/ (worlds can weigh many gigabytes) are recorded by size and
modification time. Paths are stored relative to the user directory, with forward slashes.

    pzdev fingerprint save <file.json> [--user-dir DIR]
    pzdev fingerprint check <file.json> [--user-dir DIR]     exit 0 identical, 1 different
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

HASHED_FILES = ("options.ini", "Lua/pz_modlist_settings.cfg")
HASHED_TREES = ("Server",)
STAT_TREES = ("Saves",)


def default_user_dir() -> Path:
    return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Zomboid"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _walk(root: Path):
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except FileNotFoundError:
            continue
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                stack.append(Path(entry.path))
            elif entry.is_file(follow_symlinks=False):
                yield Path(entry.path), entry.stat(follow_symlinks=False)


def snapshot(user_dir: Path) -> dict[str, str]:
    """Map relative path -> 'sha256:<hex>' or 'stat:<size>:<mtime_ns>'."""
    result: dict[str, str] = {}

    def rel(path: Path) -> str:
        return path.relative_to(user_dir).as_posix()

    for name in HASHED_FILES:
        path = user_dir / name
        if path.is_file():
            result[rel(path)] = "sha256:" + _sha256(path)
    for tree in HASHED_TREES:
        for path, _ in _walk(user_dir / tree):
            result[rel(path)] = "sha256:" + _sha256(path)
    for tree in STAT_TREES:
        for path, st in _walk(user_dir / tree):
            if path.name == "mods.txt":
                result[rel(path)] = "sha256:" + _sha256(path)
            else:
                result[rel(path)] = f"stat:{st.st_size}:{st.st_mtime_ns}"
    return result


def compare(before: dict[str, str], after: dict[str, str]) -> list[str]:
    lines = []
    for key in sorted(set(before) | set(after)):
        if key not in before:
            lines.append(f"added: {key}")
        elif key not in after:
            lines.append(f"removed: {key}")
        elif before[key] != after[key]:
            lines.append(f"changed: {key}")
    return lines


def main(argv: list[str] | None = None, busy=None) -> int:
    parser = argparse.ArgumentParser(prog="pzdev fingerprint", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("save", "check"))
    parser.add_argument("file", type=Path)
    parser.add_argument("--user-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    if busy is None:
        from pzdev.winproc import busy_processes as busy
    running = busy()
    if running:
        # A running game writes its save while it plays: the fingerprint would prove nothing.
        print("fingerprint: refused, a game or server is running: " + ", ".join(running))
        return 3
    user_dir = args.user_dir or default_user_dir()
    current = snapshot(user_dir)
    if args.action == "save":
        args.file.parent.mkdir(parents=True, exist_ok=True)
        args.file.write_text(json.dumps(current, indent=0, sort_keys=True), encoding="utf-8")
        print(f"fingerprint saved: {len(current)} files")
        return 0
    diff = compare(json.loads(args.file.read_text(encoding="utf-8")), current)
    for line in diff[:50]:
        print(line)
    if len(diff) > 50:
        print(f"... {len(diff) - 50} more")
    print("fingerprint: identical" if not diff else f"fingerprint: {len(diff)} differences")
    return 0 if not diff else 1
