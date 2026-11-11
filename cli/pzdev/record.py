"""pzdev record: record the body of a tutorial video (formerly pz-tutorial record.py): the scene played by the real
game, its image and its sound.

Usage (from the Workshop folder):
  python PZDevKit/pzdev.py record <video-dir> [--rehearse | --live | --make-save NAME [--replace]] [-P key=value ...]

<video-dir>/video.json  { "slug", "mods": [paths from the Workshop folder], "save", "gameMode",
                          "scene": "scene.lua", "timeoutSec", "params": {} }
<video-dir>/scene.lua   steps written with PZDevKit.Tuto (T.setup, T.step; client/PZDevKit/Tuto.lua)

Builds <video-dir>/build/hooks.lua (T = PZDevKit.Tuto.new() + scene.lua) and build/autotest.json, then runs
`pzdev sp` in solo with the game sound (PZAT_SOUND=1) and fixed options (English, 1600x900, in-game
music off: the music is added clean by assemble.py, never sped up).
Between "[PZTUTO] start" and "[PZTUTO] end" it keeps the game window on top (no focus taken) and
records its client area (ffmpeg gdigrab, 30 fps, no mouse pointer) and the game process sound alone
(.claude/tools/proc-audio: never a microphone nor another application). If the window moves or
changes size, the recording is deleted at once: nothing but the game may ever be filmed.
Outputs in build/: body_raw.mp4, body.wav, timeline.json (caption ids and their times), run.log.
--live: the game stays open after the prep steps and runs the Lua sent by `pzdev lua` (probe, place, remove, retry
  without relaunching; this game becomes its default target); `pzdev take <video-dir>` plays the recorded steps
  and this command films them,
  as many takes as wanted in the same session (each take replaces build/body_raw.mp4, body.wav, timeline.json).
--rehearse: no recording; a game screenshot after every step (-P shots=1) to check the staging.
--make-save NAME: no recording; plays the scene (a set-up scene: equipment placed, linked...), lets the
  game save on quit, then copies that save to %USERPROFILE%/Zomboid/Saves/<gameMode>/NAME (refused if it
  exists, unless --replace). Videos then start from it ("save": NAME in video.json): each take works on
  its own temporary copy, the base save is never modified.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from pzdev import live as live_channel
from pzdev import winproc

PROJECT_DIR = Path(__file__).resolve().parents[2]
WORKSHOP = PROJECT_DIR.parent

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
PROC_AUDIO = WORKSHOP / ".claude/tools/proc-audio/bin/proc-audio.exe"
GAME_OPTIONS = ("language=EN;width=1600;height=900;musicVolume=0;soundVolume=7;ambientVolume=5;"
                "doContainerOutline=false")
user32 = ctypes.windll.user32


def client_rect(hwnd):
    r = wt.RECT()
    user32.GetClientRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
    pt = wt.POINT(0, 0)
    user32.ClientToScreen(ctypes.c_void_p(hwnd), ctypes.byref(pt))
    return pt.x, pt.y, (r.right - r.left) // 2 * 2, (r.bottom - r.top) // 2 * 2


def topmost(hwnd, on):
    user32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(-1 if on else -2), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)


def hooks_text(slug: str, scene: str) -> str:
    """Hooks of a video: a fresh T from the mod (PZDevKit.Tuto), the scene, then T.hooks()."""
    return f"T = PZDevKit.Tuto.new()\nT.name = {json.dumps(slug)}\n{scene}\nreturn T.hooks()\n"


def build(video: Path, rehearse: bool, extra: list[str], live: bool = False):
    cfg = json.loads((video / "video.json").read_text(encoding="utf-8"))
    out = video / "build"
    out.mkdir(exist_ok=True)
    scene = (video / cfg.get("scene", "scene.lua")).read_text(encoding="utf-8")
    bad = [i + 1 for i, line in enumerate(scene.splitlines()) if any(ord(c) > 127 for c in line)]
    if bad:
        raise SystemExit(f"scene.lua: non-ASCII characters on lines {bad[:5]} (Kahlua): put player text in captions.json")
    (out / "hooks.lua").write_text(hooks_text(cfg["slug"], scene), encoding="utf-8", newline="\n")
    params = dict(cfg.get("params", {}))
    if rehearse:
        params.update(shots="1", dry="1")
    if live:
        params.update(live="1")
    for e in extra:
        k, _, v = e.partition("=")
        params[k] = v
    auto = {
        "name": "Tutorial-" + cfg["slug"], "gameVersion": cfg.get("gameVersion", "42.21"),
        "mods": [{"path": str((WORKSHOP / m).resolve())} for m in cfg["mods"]],
        "hooks": "hooks.lua", "runsDir": str((out / "runs").resolve()), "params": params,
        "sp": {"save": cfg["save"], "gameMode": cfg.get("gameMode", "Apocalypse"), "saveMods": "replace",
               "timeoutSec": 14400 if live else cfg.get("timeoutSec", 900), "startDelaySec": 5},
    }
    (out / "autotest.json").write_text(json.dumps(auto, indent=2), encoding="utf-8")
    return out


def main(argv: list[str] | None = None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    video = Path(args[0]).resolve()
    make_save = args[args.index("--make-save") + 1] if "--make-save" in args else None
    rehearse = "--rehearse" in args or make_save is not None
    live = "--live" in args
    extra = [args[i + 1] for i, a in enumerate(args) if a == "-P" and i + 1 < len(args)]
    out = build(video, rehearse, extra, live)
    raw, wav, timeline, log = out / "body_raw.mp4", out / "body.wav", out / "timeline.json", out / "run.log"
    if not rehearse:
        for f in (raw, wav, timeline):
            if f.exists():
                f.unlink()
    env = dict(os.environ, PZAT_OPTIONS=GAME_OPTIONS, PZAT_SOUND="1")
    cmd = [sys.executable, str(PROJECT_DIR / "pzdev.py"), "sp",
           str(out / "autotest.json"), "--wait-idle", "3600"]
    cfg = json.loads((video / "video.json").read_text(encoding="utf-8"))
    if make_save:
        target = Path(os.environ["USERPROFILE"]) / "Zomboid" / "Saves" / cfg.get("gameMode", "Apocalypse") / make_save
        if target.exists() and "--replace" not in args:
            raise SystemExit(f"{target} exists (add --replace to rebuild it)")
        cmd.append("--keep-cache")
    with open(log, "w", encoding="utf-8") as lf:
        run = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=WORKSHOP, env=env)
    ff = audio = hwnd = rect = t0 = console = None
    captions, pos, aborted, follows, end_t = [], 0, False, False, None
    cuts, fails = [], []
    while run.poll() is None:
        time.sleep(0.05)
        text = log.read_text(encoding="utf-8", errors="replace")
        if console is None:
            m = re.search(r"PZAT_CACHE=(\S+)", text)
            if m:
                console = Path(m.group(1)) / "console.txt"
                if live:
                    live_channel.remember_cache(Path(m.group(1)))  # default target of pzdev lua, take, quit
        pid = re.search(r"client started \(pid (\d+)\)", text)
        if not console or not console.exists():
            continue
        lines = console.read_text(encoding="utf-8", errors="replace").splitlines()
        new, pos = lines[pos:], len(lines)
        for line in new:
            if "[PZTUTO]" in line and "caption" not in line:
                print(line.split("[PZTUTO]", 1)[1].strip()[:160])
            if "[PZTUTO] start" in line and ff is None and pid and not rehearse:
                hwnd = winproc.find_window(int(pid.group(1)))
                if not hwnd:
                    print("game window not found")
                    continue
                topmost(hwnd, True)
                time.sleep(0.3)
                rect = client_rect(hwnd)
                x, y, w, h = rect
                buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(ctypes.c_void_p(hwnd), buf, 256)
                title = buf.value
                if title:
                    # the window itself: gdigrab follows it; the frame is cropped off
                    src = ["-i", f"title={title}"]
                    crop = ["-vf", f"crop={w}:{h}:(in_w-{w})/2:in_h-{h}-(in_w-{w})/2"]
                else:
                    src = ["-offset_x", str(x), "-offset_y", str(y), "-video_size", f"{w}x{h}", "-i", "desktop"]
                    crop = []
                ff = subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-f", "gdigrab", "-framerate", "30",
                                       "-draw_mouse", "0", *src, *crop, "-c:v", "libx264", "-preset", "veryfast",
                                       "-crf", "16", "-pix_fmt", "yuv420p", str(raw)], stdin=subprocess.PIPE)
                follows = bool(title)
                audio = subprocess.Popen([str(PROC_AUDIO), pid.group(1), str(wav)], stdin=subprocess.PIPE)
                t0 = time.time()
                captions, cuts, fails = [], [], []
                print(f"recording {w}x{h}")
            elif "[PZTUTO] caption " in line and t0:
                captions.append({"t": round(time.time() - t0, 3), "id": line.split("[PZTUTO] caption ", 1)[1].strip()})
            elif "[PZTUTO] cut" in line and t0:
                cuts.append(round(time.time() - t0, 3))
            elif "[PZTUTO] FAIL" in line:
                fails.append(line.split("[PZTUTO] FAIL", 1)[1].strip())
            elif "[PZTUTO] uncaption" in line and t0:
                captions.append({"t": round(time.time() - t0, 3), "id": None})
            elif "[PZTUTO] end" in line and ff:
                time.sleep(1.0)
                end_t = round(time.time() - t0 - 1.0, 3)
                try:
                    ff.communicate(b"q", timeout=30)
                except subprocess.TimeoutExpired:
                    ff.kill()
                    ff.wait()
                ff = None
                if audio:
                    try:
                        audio.communicate(b"q\n", timeout=30)
                    except subprocess.TimeoutExpired:
                        audio.kill()
                        audio.wait()
                    audio = None
                topmost(hwnd, False)
                print(f"recorded {end_t:.1f} s")
                if live:
                    timeline.write_text(json.dumps({"captions": captions, "end": end_t, "cuts": cuts, "fails": fails},
                                                   indent=1), encoding="utf-8")
                    print("TAKE " + ("REJECTED: " + " | ".join(fails) if fails else "OK") + " (build/, next: pzdev take)")
                    t0 = None
        if ff and hwnd and not follows and client_rect(hwnd) != rect:
            ff.kill(); ff.wait(); ff = None
            if audio:
                audio.kill(); audio = None
            for f in (raw, wav):
                if f.exists():
                    f.unlink()
            topmost(hwnd, False)
            aborted = True
            print("ABORTED: the game window moved; recording deleted")
    if ff:
        ff.communicate(b"q", timeout=30)
    tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-4:]
    print("\n".join(tail))
    if make_save:
        import shutil
        cache = Path(re.search(r"PZAT_CACHE=(\S+)", log.read_text(encoding="utf-8", errors="replace")).group(1))
        src = cache / "Saves" / cfg.get("gameMode", "Apocalypse") / cfg["save"]
        if run.returncode != 0 or not (src / "global_mod_data.bin").exists():
            print(f"no base save made (exit {run.returncode}); cache kept: {cache}")
            return 1
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(src, target)
        shutil.rmtree(cache, ignore_errors=True)
        print(f"base save: {target}")
        return 0
    if rehearse:
        return run.returncode
    if aborted or not raw.exists():
        print("no recording")
        return 1
    timeline.write_text(json.dumps({"captions": captions, "end": end_t, "cuts": cuts, "fails": fails}, indent=1),
                        encoding="utf-8")
    if fails:
        print("TAKE REJECTED (pzdev assemble will refuse it): " + " | ".join(fails))
    print(f"body: {raw} ({len(captions)} captions)")
    return run.returncode




def cache_lua(video: Path) -> Path:
    """Lua folder of the game started by `pzdev record <video-dir> --live` (PZAT_CACHE in build/run.log)."""
    log = video / "build" / "run.log"
    m = re.search(r"PZAT_CACHE=(\S+)", log.read_text(encoding="utf-8", errors="replace")) if log.exists() else None
    if not m:
        raise SystemExit("no PZAT_CACHE in build/run.log: is `pzdev record <video-dir> --live` running?")
    return Path(m.group(1)) / "Lua"


def take(video: Path, send=None, timeout: float = 900, sleep=time.sleep) -> int:
    """pzdev take <video-dir>: plays the recorded steps (T.take()) in the live game and waits for the take."""
    send = send or live_channel.send
    lua_dir = cache_lua(video)
    timeline = video / "build" / "timeline.json"
    before = timeline.stat().st_mtime if timeline.exists() else 0
    code, _ = send(lua_dir, "return T.take()", timeout=30)
    if code != 0:
        return 2
    start = last = time.monotonic()
    while time.monotonic() - start < timeout:
        sleep(0.5)
        if timeline.exists() and timeline.stat().st_mtime > before:
            sleep(0.5)
            d = json.loads(timeline.read_text(encoding="utf-8"))
            print(f"take done: {d['end']:.1f} s, cuts {d.get('cuts')}, captions {[c['id'] for c in d['captions']]}")
            print("FAILS: " + " | ".join(d["fails"]) if d["fails"] else "no FAIL")
            return 1 if d["fails"] else 0
        if time.monotonic() - last >= live_channel.PROGRESS_S:
            last = time.monotonic()
            print(f"take running {last - start:.0f} s")
    print(f"take not finished after {timeout:.0f} s")
    return 2


def quit_game(video: Path, send=None) -> int:
    """pzdev quit <video-dir>: closes the game started by `pzdev record --live`."""
    send = send or live_channel.send
    return send(cache_lua(video), "getCore():quitToDesktop(); return \"quitting\"", timeout=10)[0]
