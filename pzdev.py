"""Entry point of the PZDevKit command line (DEV-ONLY).

    python PZDevKit/pzdev.py <command> ...
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "cli"))

from pzdev.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
