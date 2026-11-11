"""pzdev sheet: contact sheet of a recorded take: one frame every N seconds of build/body_raw.mp4, with the time.

Usage: python PZDevKit/pzdev.py sheet <video-dir> [every_seconds=3]
Writes <video-dir>/build/sheet.png (look at it with an image viewer / Read).
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")


def main(argv=None):
    argv = ["sheet"] + list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 2
    build = Path(argv[1]).resolve() / "build"
    every = float(argv[2]) if len(argv) > 2 else 3.0
    end = json.loads((build / "timeline.json").read_text(encoding="utf-8")).get("end") or 60
    tiles, t = [], 0.5
    with tempfile.TemporaryDirectory() as td:
        while t < end:
            out = Path(td) / f"{t:06.1f}.png"
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(build / "body_raw.mp4"),
                            "-frames:v", "1", "-vf", "scale=480:270", str(out)], check=False)
            if out.exists():
                im = Image.open(out).convert("RGB")
                ImageDraw.Draw(im).text((6, 6), f"{t:.1f}s", fill=(255, 0, 0))
                tiles.append(im)
            t += every
    cols = 4
    sheet = Image.new("RGB", (cols * 480, ((len(tiles) + cols - 1) // cols) * 270))
    for i, im in enumerate(tiles):
        sheet.paste(im, ((i % cols) * 480, (i // cols) * 270))
    sheet.save(build / "sheet.png")
    print(f"{build / 'sheet.png'}: {len(tiles)} frames")
    return 0


