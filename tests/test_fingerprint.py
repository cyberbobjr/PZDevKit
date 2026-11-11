"""Fingerprint of the real user data (saves, options, mod lists) before and after a run."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from pzdev import fingerprint  # noqa: E402


def make_user_dir(root: Path) -> None:
    (root / "Saves" / "Sandbox" / "World1" / "map").mkdir(parents=True)
    (root / "Saves" / "Sandbox" / "World1" / "mods.txt").write_text("mods\n{\n}\n", encoding="utf-8")
    (root / "Saves" / "Sandbox" / "World1" / "map" / "map_0_0.bin").write_bytes(b"\x00" * 64)
    (root / "Server").mkdir()
    (root / "Server" / "servertest.ini").write_text("Public=false\n", encoding="utf-8")
    (root / "Lua").mkdir()
    (root / "Lua" / "pz_modlist_settings.cfg").write_text("mods\n", encoding="utf-8")
    (root / "options.ini").write_text("version=1\n", encoding="utf-8")


class FingerprintTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        make_user_dir(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_identical_snapshots_compare_equal(self):
        self.assertEqual(fingerprint.compare(fingerprint.snapshot(self.root), fingerprint.snapshot(self.root)), [])

    def test_hashed_file_change_is_reported(self):
        before = fingerprint.snapshot(self.root)
        (self.root / "options.ini").write_text("version=2\n", encoding="utf-8")
        self.assertEqual(fingerprint.compare(before, fingerprint.snapshot(self.root)), ["changed: options.ini"])

    def test_save_file_change_added_and_removed_are_reported(self):
        before = fingerprint.snapshot(self.root)
        bin_file = self.root / "Saves" / "Sandbox" / "World1" / "map" / "map_0_0.bin"
        bin_file.write_bytes(b"\x01" * 65)
        (self.root / "Saves" / "Sandbox" / "World1" / "new.bin").write_bytes(b"x")
        (self.root / "Saves" / "Sandbox" / "World1" / "mods.txt").unlink()
        diff = fingerprint.compare(before, fingerprint.snapshot(self.root))
        self.assertEqual(diff, ["changed: Saves/Sandbox/World1/map/map_0_0.bin",
                                "removed: Saves/Sandbox/World1/mods.txt",
                                "added: Saves/Sandbox/World1/new.bin"])

    def test_mtime_only_change_is_reported(self):
        before = fingerprint.snapshot(self.root)
        bin_file = self.root / "Saves" / "Sandbox" / "World1" / "map" / "map_0_0.bin"
        st = bin_file.stat()
        os.utime(bin_file, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000_000))
        self.assertEqual(fingerprint.compare(before, fingerprint.snapshot(self.root)),
                         ["changed: Saves/Sandbox/World1/map/map_0_0.bin"])

    def test_lua_scratch_files_are_ignored(self):
        before = fingerprint.snapshot(self.root)
        (self.root / "Lua" / "pzdev").mkdir()
        (self.root / "Lua" / "pzdev" / "cmd.lua").write_text("return 1\n", encoding="utf-8")
        self.assertEqual(fingerprint.compare(before, fingerprint.snapshot(self.root)), [])

    def test_snapshot_is_json_and_contains_no_absolute_path(self):
        text = json.dumps(fingerprint.snapshot(self.root))
        self.assertNotIn(str(self.root), text)
        self.assertNotIn(str(self.root).replace("\\", "/"), text)

    def test_cli_save_then_check(self):
        out = self.root / "ref.json"
        idle = lambda: []  # noqa: E731
        self.assertEqual(fingerprint.main(["save", str(out), "--user-dir", str(self.root)], busy=idle), 0)
        self.assertEqual(fingerprint.main(["check", str(out), "--user-dir", str(self.root)], busy=idle), 0)
        (self.root / "options.ini").write_text("changed\n", encoding="utf-8")
        self.assertEqual(fingerprint.main(["check", str(out), "--user-dir", str(self.root)], busy=idle), 1)

    def test_cli_refuses_while_a_game_runs(self):
        """A running game writes its save: a fingerprint taken or checked then proves nothing (exit 3)."""
        out = self.root / "ref.json"
        running = lambda: ["java.exe 1234"]  # noqa: E731
        self.assertEqual(fingerprint.main(["save", str(out), "--user-dir", str(self.root)], busy=running), 3)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
