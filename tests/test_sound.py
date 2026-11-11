"""pzdev sound check|install: the optional sound of pzdev film --video (soundcard + numpy in PZDevKit/.pydeps)."""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))

from pzdev import sound  # noqa: E402


class SoundTest(unittest.TestCase):
    def run_cli(self, *args, **kw):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = sound.main(list(args), **kw)
        return code, buf.getvalue()

    def test_check_reports_what_is_missing(self):
        code, out = self.run_cli('check', probe=lambda: (False, 'module soundcard absent'), ffmpeg=lambda: False)
        self.assertEqual(code, 1)
        self.assertIn('ffmpeg: missing', out)
        self.assertIn('sound: module soundcard absent', out)
        self.assertIn('pzdev.py sound install', out)

    def test_check_ok(self):
        code, out = self.run_cli('check', probe=lambda: (True, 'Speakers (Realtek)'), ffmpeg=lambda: True)
        self.assertEqual(code, 0)
        self.assertIn('sound: loopback of Speakers (Realtek)', out)

    def test_install_targets_the_project_folder_then_checks(self):
        calls = []
        code, out = self.run_cli('install', run=lambda argv: calls.append(argv) or 0,
                                 probe=lambda: (True, 'Speakers'), ffmpeg=lambda: True)
        self.assertEqual(code, 0)
        argv = calls[0]
        self.assertEqual(argv[1:4], ['-m', 'pip', 'install'])
        self.assertEqual(argv[argv.index('--target') + 1], str(sound.DEPS))
        self.assertIn('soundcard', argv)
        self.assertIn('numpy', argv)

    def test_failed_install_gives_exit_2(self):
        code, out = self.run_cli('install', run=lambda argv: 1, probe=lambda: (False, 'x'), ffmpeg=lambda: True)
        self.assertEqual(code, 2)


if __name__ == '__main__':
    unittest.main()
