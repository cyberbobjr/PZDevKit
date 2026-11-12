"""pzdev assemble: assemble a tutorial video (formerly pz-tutorial assemble.py): trailer intro, edited body, Ko-fi outro, game music, EN/FR subtitles.

Usage (from the Workshop folder):
  python PZDevKit/pzdev.py assemble <video-dir>

Reads <video-dir>/video.json (slug, title.en, series, kofi, music), captions.json ({id: {en, fr, dur}})
and build/ (body_raw.mp4, body.wav, timeline.json from pzdev record).
- Body: each caption segment is brought to its "dur" seconds when it is longer, sped up at most
  maxSpeed times (video.json, default 1.25: faster is hard to follow; pitch kept).
- Intro (about 5 s): three quick shots of the body cut by white flashes and deep hits, then the
  series and the title over a slow zoom, on the game's main theme.
- Outro (6 s, YouTube end screen: 5 to 20 s): thanks, Ko-fi link and QR code on the left; the right
  half stays clear for the YouTube end screen elements (subscribe, next video).
- Voice (optional, video.json "voice": {"id", "model"}): each English caption is spoken (ElevenLabs,
  key in the ELEVEN_LABS_KEY environment variable, lines cached in build/voice/); a segment lasts at least
  its line, the game sound and the music go down under the voice. No burnt subtitles then. Units are said
  in full (340 W -> "340 watts", see SPOKEN_UNITS); a caption may give its own spoken text in "say".
- Several takes (video.json "takes": [subdirs]): each subdir is recorded with pzdev record on its own
  (own video.json, scene.lua, mods); the bodies are joined in that order. Lines all in the top captions.json.
- Music: one of the game's own tracks (read only from the game folder), never sped up, laid over the
  whole video: full in the intro, low under the body (game sound on top), up again in the outro.
Outputs in <video-dir>: <slug>.mp4 (1920x1080, no burnt subtitles), <slug>.en.srt, <slug>.fr.srt,
<slug>.preview-fr.mp4 (French subtitles burnt, for review).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE", "ffprobe")
GAME_MUSIC = Path(os.environ.get("PZ_GAME_DIR", r"D:\SteamLibrary\steamapps\common\ProjectZomboid")) / "media" / "music"
FONTS = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
W, H, FPS = 1920, 1080, 30
INTRO_SHOT, FLASH, TITLE = 0.55, 0.08, 3.0
OUTRO_DEFAULT = 7.0
# the end card must stay readable at least 5 s once its fades are counted (user, 2026-11-12)
OUTRO_MIN = 6.5
MUSIC_BODY = 0.13   # music level under the game sound of the body
ACCENT = (242, 178, 51)


def run(args, cwd=None):
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *args], check=True, cwd=cwd)


def duration(path):
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def atempo(speed):
    parts = []
    while speed > 2.0:
        parts.append("atempo=2.0")
        speed /= 2.0
    parts.append(f"atempo={speed:.4f}")
    return ",".join(parts)


def stamp(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


VOICE_LEAD = 0.15    # seconds of silence before a line
VOICE_TAIL = 0.30    # seconds after it, before the next segment
GAME_UNDER_VOICE = 0.45


# Units written on screen, said in full by the voice (the subtitles keep the short form).
SPOKEN_UNITS = [(r"(\d)\s?kWh\b", r"\1 kilowatt-hours"), (r"(\d)\s?Wh\b", r"\1 watt-hours"),
                (r"(\d)\s?kW\b", r"\1 kilowatts"), (r"(\d)\s?W\b", r"\1 watts"),
                (r"(\d)\s?A\b", r"\1 amp"), (r"(\d)\s?V\b", r"\1 volts"),
                (r"(\d)\s?km/h", r"\1 kilometers per hour"), (r"(\d)\s?%", r"\1 percent"),
                # menu paths written "A > B" (read "greater than"), the I/O switch, skill levels
                (r"\s*>\s*", ", "), (r"\bI/O\b", "on-off"), (r"\bElectrical (\d)", r"Electrical level \1")]


def spoken(text: str) -> str:
    import re
    for pat, rep in SPOKEN_UNITS:
        text = re.sub(pat, rep, text)
    return text


def voice_line(text: str, voice: dict, cache: Path) -> Path:
    """English narration of one caption (ElevenLabs text-to-speech), cached by text and voice."""
    import hashlib
    import urllib.request
    cache.mkdir(parents=True, exist_ok=True)
    text = spoken(text)
    key = hashlib.sha1(f"{voice['id']}|{voice.get('model', '')}|{text}".encode("utf-8")).hexdigest()[:16]
    out = cache / f"{key}.mp3"
    if out.exists():
        return out
    api_key = os.environ.get("ELEVEN_LABS_KEY")
    if not api_key:
        raise SystemExit("ELEVEN_LABS_KEY is not set (load the .env into the environment, never print it)")
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice['id']}?output_format=mp3_44100_128",
        data=json.dumps({"text": text, "model_id": voice.get("model", "eleven_multilingual_v2")}).encode("utf-8"),
        headers={"xi-api-key": api_key, "Content-Type": "application/json"})
    out.write_bytes(urllib.request.urlopen(req, timeout=120).read())
    print(f"voice: {len(text)} characters generated")
    return out


def edit_body(build: Path, caps: dict, tmp: Path, max_speed: float, voice: dict | None = None):
    """Cut the raw body at caption changes, bring each segment to its target duration. With a voice,
    each segment lasts at least its spoken line (the last frame is held if the take is shorter)."""
    tl = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    marks, end = tl["captions"], tl["end"]
    if tl.get("fails") and os.environ.get("TUTO_FORCE") != "1":
        raise SystemExit("take rejected, FAIL lines (Lua error shown on screen, missing step...): "
                         + " | ".join(tl["fails"]) + " -- fix the scene and record again (TUTO_FORCE=1 to override).")
    cuts = tl.get("cuts", [])
    segs, out_t, subs, xcuts = [], 0.0, [], []
    for i, m in enumerate(marks):
        a = m["t"]
        b = marks[i + 1]["t"] if i + 1 < len(marks) else end
        if b - a < 0.2:
            continue
        cap = caps.get(m["id"]) if m["id"] else None
        # "keep": seconds of the take kept for a long, repetitive action (a craft, a walk): its start and
        # its end, joined by a cut; the rest is dropped instead of being shown at high speed.
        span = b - a
        cut_v = cut_a = ""
        keep = (cap or {}).get("keep")
        if keep and span > keep + 0.5:
            k1, k2 = keep * 0.5, span - keep * 0.5
            cut_v = f"select='lt(t,{k1:.3f})+gte(t,{k2:.3f})',setpts=N/FRAME_RATE/TB,"
            cut_a = f"aselect='lt(t,{k1:.3f})+gte(t,{k2:.3f})',asetpts=N/SR/TB,"
            span = keep
        target = (cap or {}).get("dur", span)
        vfile = voice_line(cap.get("say", cap["en"]), voice, build / "voice") if (voice and cap) else None
        vlen = duration(vfile) if vfile else 0.0
        if vfile:
            target = max(target, VOICE_LEAD + vlen + VOICE_TAIL)
        speed = max(1.0, min(max_speed, span / target))
        hold = max(0.0, target - span / speed) if vfile else 0.0
        n = len(segs)
        seg = tmp / f"seg{n:02d}.mkv"
        inputs = ["-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(build / "body_raw.mp4"),
                  "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(build / "body.wav")]
        # a cut (teleport) becomes a cross-fade between the two places (user, 2026-11-12: "fondus enchaines"),
        # applied on the whole body once it is joined (crossfade_cuts), so a cut at a segment start fades too.
        # A teleport usually runs in the very step that starts a caption: its time equals the segment
        # start, so the bounds include it. Inside a "keep" segment, the time is mapped onto the kept parts.
        for c in cuts:
            if a - 0.05 <= c < b:
                rel = c - a
                if cut_v:
                    rel = rel if rel < k1 else (k1 if rel < k2 else rel - (k2 - k1))
                xcuts.append(out_t + max(0.0, rel / speed))
        vf = f"[0:v]fps={FPS},setpts=PTS-STARTPTS,{cut_v}setpts=PTS/{speed:.4f},scale={W}:{H}:flags=lanczos,fps={FPS}"
        if hold > 0.01:
            vf += f",tpad=stop_mode=clone:stop_duration={hold:.3f}"
        af = (f"[1:a]asetpts=PTS-STARTPTS,{cut_a}{atempo(speed)},aresample=48000,aformat=channel_layouts=stereo,"
              f"apad,atrim=0:{span / speed + hold:.3f}")
        if vfile:
            inputs += ["-i", str(vfile)]
            lead = int(VOICE_LEAD * 1000)
            graph = (f"{vf}[v];{af},volume={GAME_UNDER_VOICE}[g];"
                     f"[2:a]aresample=48000,aformat=channel_layouts=stereo,adelay={lead}|{lead}[s];"
                     f"[g][s]amix=inputs=2:normalize=0:duration=first[a]")
        else:
            graph = f"{vf}[v];{af}[a]"
        run([*inputs, "-filter_complex", graph, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "17",
             "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", str(seg)])
        d = duration(seg)
        segs.append(seg)
        if cap:
            subs.append((out_t, out_t + d, cap))
        out_t += d
    lst = tmp / "segs.txt"
    lst.write_text("".join(f"file '{s.as_posix()}'\n" for s in segs), encoding="utf-8")
    body = tmp / "body.mkv"
    run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c:v", "copy",
         "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "48000", "-c:a", "pcm_s16le", str(body)])
    if xcuts:
        body = crossfade_cuts(body, xcuts, out_t, tmp)
    idle_check(body)
    return body, out_t, subs


XFADE = 0.6  # cross-fade length at a change of place (s)


def crossfade_cuts(body: Path, cuts: list, total: float, tmp: Path) -> Path:
    """Replace each hard cut (teleport) by a cross-fade, length unchanged: the last image of the old place
    (taken 0.1 s before the cut, surely still the old place) is held and fades into the new place from
    0.25 s after the cut (surely rendered). Subtitles and audio keep their times."""
    parts, cur = [], "[0:v]"
    for i, t in enumerate(sorted(cuts)):
        t0, t1 = max(0.04, t - 0.1), t + 0.25
        if t1 + XFADE >= total - 0.1:
            continue
        hold = (t1 - t0) + XFADE
        parts.append(f"{cur}split[a{i}][b{i}];"
                     f"[a{i}]trim=end={t0:.3f},setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={hold:.3f}[pa{i}];"
                     f"[b{i}]trim=start={t1:.3f},setpts=PTS-STARTPTS[pb{i}];"
                     f"[pa{i}][pb{i}]xfade=transition=fade:duration={XFADE}:offset={t1:.3f}[v{i}]")
        cur = f"[v{i}]"
    if not parts:
        return body
    out = tmp / "body_xfade.mkv"
    run(["-i", str(body), "-filter_complex", ";".join(parts), "-map", cur, "-map", "0:a", "-c:v", "libx264",
         "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "copy", str(out)])
    print(f"cross-fades: {len(parts)} at " + ", ".join(f"{t:.1f} s" for t in sorted(cuts)))
    return out


def idle_check(video: Path, limit: float = 2.5):
    """Dead time: the image hardly changes for more than `limit` seconds. Printed as IDLE lines: cut the
    action ("keep" in captions.json), shorten the wait or the line, or the viewer waits for nothing."""
    import re
    out = subprocess.run([FFMPEG, "-hide_banner", "-i", str(video), "-vf", f"freezedetect=n=0.002:d={limit}",
                          "-map", "0:v", "-f", "null", "-"], capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", out)]
    durs = [float(x) for x in re.findall(r"freeze_duration: ([\d.]+)", out)]
    for st, du in zip(starts, durs):
        print(f"IDLE {du:.1f} s at {st:.1f} s of the body (nothing moves on screen)")


def frame_at(video: Path, t: float, out: Path):
    run(["-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", str(out)])
    return Image.open(out).convert("RGB")


def text_center(draw, y, text, fnt, fill, shadow=True):
    w = draw.textlength(text, font=fnt)
    if shadow:
        draw.text(((W - w) / 2 + 4, y + 4), text, font=fnt, fill=(0, 0, 0))
    draw.text(((W - w) / 2, y), text, font=fnt, fill=fill)


def title_card(bg: Image.Image, series: str, title: str, out: Path):
    img = bg.resize((W, H)).filter(ImageFilter.GaussianBlur(3))
    img = Image.blend(img, Image.new("RGB", (W, H), (8, 10, 14)), 0.62)
    d = ImageDraw.Draw(img)
    text_center(d, 330, series, font("impact.ttf", 150), ACCENT)
    d.rectangle(((W - 520) / 2, 505, (W + 520) / 2, 511), fill=ACCENT)
    # a long title goes on two lines (split at its colon), each line shrunk to fit the frame
    head, _, tail = title.partition(": ")
    lines = [(head.upper(), "impact.ttf", 92)] + ([(tail.upper(), "impact.ttf", 62)] if tail else [])
    if not tail and d.textlength(head.upper(), font=font("impact.ttf", 92)) > W - 200:
        words = head.upper().split()
        lines = [(" ".join(words[:len(words) // 2]), "impact.ttf", 92), (" ".join(words[len(words) // 2:]), "impact.ttf", 92)]
    y = 540
    for text, face, size in lines:
        while size > 30 and d.textlength(text, font=font(face, size)) > W - 200:
            size -= 4
        text_center(d, y, text, font(face, size), (245, 240, 230))
        y += int(size * 1.25)
    text_center(d, y + 20, "TUTORIAL", font("bahnschrift.ttf", 44), (200, 200, 200), shadow=False)
    img.save(out)


def outro_card(bg: Image.Image, kofi: str, out: Path):
    import qrcode
    img = bg.resize((W, H)).filter(ImageFilter.GaussianBlur(8))
    img = Image.blend(img, Image.new("RGB", (W, H), (8, 10, 14)), 0.72)
    d = ImageDraw.Draw(img)
    x = 140
    d.text((x, 170), "THANKS FOR WATCHING!", font=font("impact.ttf", 96), fill=(245, 240, 230))
    d.text((x, 300), "Enjoying the mod? Support my work on Ko-fi.", font=font("bahnschrift.ttf", 46), fill=(220, 220, 220))
    qr = qrcode.QRCode(border=2, box_size=10)
    qr.add_data("https://" + kofi)
    qr.make(fit=True)
    q = qr.make_image(fill_color="black", back_color="white").convert("RGB").resize((300, 300), Image.NEAREST)
    d.rounded_rectangle((x - 12, 400 - 12, x + 300 + 12, 400 + 300 + 12), 16, fill=(255, 255, 255))
    img.paste(q, (x, 400))
    d.text((x + 350, 470), "ko-fi.com/", font=font("bahnschrift.ttf", 58), fill=(220, 220, 220))
    d.text((x + 350, 540), kofi.split("/", 1)[1], font=font("impact.ttf", 84), fill=ACCENT)
    d.text((x, 760), "Links, wiki and Workshop page in the description.", font=font("bahnschrift.ttf", 36),
           fill=(180, 180, 180))
    img.save(out)


def main(argv=None):
    argv = ["assemble"] + list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 2
    video = Path(argv[1]).resolve()
    cfg = json.loads((video / "video.json").read_text(encoding="utf-8"))
    caps = json.loads((video / "captions.json").read_text(encoding="utf-8"))
    slug, kofi = cfg["slug"], cfg.get("kofi", "ko-fi.com/batmanfr")
    music = GAME_MUSIC / cfg.get("music", "theme2.ogg")
    build = video / "build"
    with tempfile.TemporaryDirectory(prefix="pztuto-") as td:
        tmp = Path(td)
        voice = cfg.get("voice")
        max_speed = float(cfg.get("maxSpeed", 1.25))
        if cfg.get("takes"):
            # several takes (e.g. with and without an optional mod), each recorded in <video>/<take>/ with
            # its own video.json and scene.lua; captions.json of the video holds the lines of all of them
            parts, body_d, subs = [], 0.0, []
            for k, take in enumerate(cfg["takes"]):
                sub_tmp = tmp / f"take{k}"
                sub_tmp.mkdir()
                b, d, s_ = edit_body(video / take / "build", caps, sub_tmp, max_speed, voice)
                parts.append(b)
                subs += [(x + body_d, y + body_d, c) for x, y, c in s_]
                body_d += d
            lst = tmp / "takes.txt"
            lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
            body = tmp / "body_all.mkv"
            run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(body)])
        else:
            body, body_d, subs = edit_body(build, caps, tmp, max_speed, voice)
        music_body = MUSIC_BODY * (0.6 if voice else 1.0)
        OUTRO = max(OUTRO_MIN, float(cfg.get("outro", OUTRO_DEFAULT)))  # end card fully shown >= 5 s
        # ---------------- intro: quick shots, flashes, title
        shots = []
        for i, f in enumerate((0.30, 0.55, 0.80)):
            s = tmp / f"shot{i}.mkv"
            run(["-ss", f"{body_d * f:.3f}", "-t", f"{INTRO_SHOT}", "-i", str(body), "-an",
                 "-vf", f"scale={W}:{H},fps={FPS},eq=contrast=1.15:saturation=1.2", "-c:v", "libx264", "-crf", "17",
                 "-pix_fmt", "yuv420p", str(s)])
            fl = tmp / f"flash{i}.mkv"
            run(["-f", "lavfi", "-i", f"color=white:s={W}x{H}:r={FPS}:d={FLASH}", "-c:v", "libx264", "-crf", "17",
                 "-pix_fmt", "yuv420p", str(fl)])
            shots += [s, fl]
        card = tmp / "title.png"
        title_card(frame_at(body, body_d * 0.92, tmp / "tbg.png"), cfg.get("series", "LIVE WIRE"), cfg["title"]["en"], card)
        tclip = tmp / "title.mkv"
        frames = int(TITLE * FPS)
        run(["-loop", "1", "-i", str(card), "-t", f"{TITLE}", "-vf",
             f"zoompan=z='1+0.06*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS},"
             f"fade=in:st=0:d=0.25", "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", str(tclip)])
        shots.append(tclip)
        lst = tmp / "intro.txt"
        lst.write_text("".join(f"file '{s.as_posix()}'\n" for s in shots), encoding="utf-8")
        intro_v = tmp / "intro_v.mkv"
        run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(intro_v)])
        intro_d = duration(intro_v)
        # music + a deep hit on each cut
        hits = [(INTRO_SHOT + FLASH) * i + INTRO_SHOT for i in range(3)]
        boom = "0.9*sin(2*PI*48*t)*exp(-3.5*t)+0.25*(random(0)-0.5)*exp(-30*t)"
        hit_inputs, mix = [], []
        for i, t in enumerate(hits):
            hit_inputs += ["-f", "lavfi", "-t", "1.2", "-i", f"aevalsrc='{boom}':s=48000"]
            mix.append(f"[{i + 2}:a]adelay={int(t * 1000)}|{int(t * 1000)},aformat=channel_layouts=stereo[h{i}]")
        intro = tmp / "intro.mkv"
        run(["-i", str(intro_v), "-f", "lavfi", "-t", f"{intro_d:.3f}", "-i", "anullsrc=r=48000:cl=stereo", *hit_inputs,
             "-filter_complex", ";".join(mix) +
             ";[1:a]" + "".join(f"[h{i}]" for i in range(3)) + f"amix=inputs=4:normalize=0,atrim=0:{intro_d:.3f}[a]",
             "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "pcm_s16le", str(intro)])
        # ---------------- outro
        ocard = tmp / "outro.png"
        outro_card(frame_at(body, max(0, body_d - 0.5), tmp / "obg.png"), kofi, ocard)
        outro = tmp / "outro.mkv"
        run(["-loop", "1", "-i", str(ocard), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{OUTRO}",
             "-filter_complex", f"[0:v]fps={FPS},fade=in:st=0:d=0.5,fade=out:st={OUTRO - 0.7}:d=0.7[v]",
             "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p",
             "-c:a", "pcm_s16le", str(outro)])
        # ---------------- final
        lst = tmp / "all.txt"
        lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in (intro, body, outro)), encoding="utf-8")
        joined = tmp / "joined.mkv"
        run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])
        total = intro_d + body_d + OUTRO
        b0, b1 = intro_d, intro_d + body_d
        # music level: 0.9 in the intro, MUSIC_BODY under the body, 0.75 in the outro (0.6 s ramps)
        lvl = (f"if(lt(t,{b0 - 0.6:.2f}),0.9,if(lt(t,{b0:.2f}),0.9-(t-{b0 - 0.6:.2f})/0.6*{0.9 - music_body},"
               f"if(lt(t,{b1 - 0.6:.2f}),{music_body},if(lt(t,{b1:.2f}),{music_body}+(t-{b1 - 0.6:.2f})/0.6*{0.75 - music_body},0.75))))")
        final = video / f"{slug}.mp4"
        run(["-i", str(joined), "-stream_loop", "-1", "-i", str(music), "-filter_complex",
             f"[1:a]atrim=0:{total:.3f},aresample=48000,aformat=channel_layouts=stereo,volume='{lvl}':eval=frame,"
             f"afade=in:st=0:d=0.3,afade=out:st={total - 2.5:.3f}:d=2.5[m];"
             f"[0:a][m]amix=inputs=2:normalize=0,alimiter=limit=0.95[a]",
             "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-movflags", "+faststart", str(final)])
        for lang in ("en", "fr"):
            entries = [f"{i + 1}\n{stamp(intro_d + a)} --> {stamp(intro_d + b - 0.05)}\n{cap[lang]}\n"
                       for i, (a, b, cap) in enumerate(subs)]
            (video / f"{slug}.{lang}.srt").write_text("\n".join(entries), encoding="utf-8")
        style = ("FontName=Arial,FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3,"
                 "BackColour=&H90000000,Outline=1,Shadow=0,MarginV=40")
        run(["-i", final.name, "-vf", f"subtitles={slug}.fr.srt:force_style='{style}'", "-c:v", "libx264",
             "-crf", "20", "-c:a", "copy", f"{slug}.preview-fr.mp4"], cwd=video)
        total = duration(final)
        print(f"{final.name}: {total:.1f} s (intro {intro_d:.1f} s, body {body_d:.1f} s, outro {OUTRO:.1f} s), "
              f"{len(subs)} subtitles" + ("  WARNING: over 60 s" if total > 60 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
