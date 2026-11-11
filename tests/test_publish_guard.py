"""The local Workshop publishing tool must refuse a DEV-ONLY project."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / ".claude" / "tools"
sys.path.insert(0, str(TOOLS))

import pz_workshop_project  # noqa: E402

MARKER = "DEV-ONLY-DO-NOT-UPLOAD.txt"


def make_project(root: Path, workshop_txt: bool) -> None:
    (root / "Contents" / "mods" / "batman_Example" / "42.21").mkdir(parents=True)
    (root / "Contents" / "mods" / "batman_Example" / "42.21" / "mod.info").write_text(
        "id=batman_Example\nname=batman_Example\n", encoding="utf-8")
    (root / "Contents" / MARKER).write_text("dev only\n", encoding="utf-8")
    if workshop_txt:
        (root / "workshop.txt").write_text("version=1\ntitle=Example\nvisibility=private\n", encoding="utf-8")


class PublishGuardTest(unittest.TestCase):
    def test_validate_reports_dev_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root, workshop_txt=True)
            errors = pz_workshop_project.validate(pz_workshop_project.Project.load(root))
            self.assertTrue(any("DEV-ONLY" in e for e in errors), errors)

    def test_publish_tool_refuses_without_workshop_txt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root, workshop_txt=False)
            proc = subprocess.run([sys.executable, str(TOOLS / "steam_workshop_publish.py"), str(root)],
                                  capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertIn("DEV-ONLY", proc.stdout)
            self.assertNotIn("Traceback", proc.stderr)

    def test_this_project_is_marked(self):
        project = Path(__file__).resolve().parents[1]
        self.assertTrue((project / "Contents" / MARKER).is_file())
        self.assertFalse((project / "preview.png").exists())
        self.assertFalse((project / "workshop.txt").exists())


if __name__ == "__main__":
    unittest.main()
