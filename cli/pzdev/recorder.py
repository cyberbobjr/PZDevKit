"""Enregistreur d'une prise : fenêtre du jeu (FFmpeg gfxcapture) et son de la sortie Windows (ex-PZDirector
tools/recorder.py).

Utilisé par `pzdev film --video`. Produit dans le dossier de la prise :
  video.mp4    image seule, MP4 fragmenté (lisible même si FFmpeg doit être tué) ;
  audio.wav    son de la sortie audio par défaut (loopback), si le module soundcard est présent ;
  take.mp4     image + son assemblés (ou l'image seule) ;
  capture.json horodatage, repères MARK, erreurs et avertissements.

Le son : `pip install --target PZDevKit/.pydeps soundcard numpy` (dossier ignoré par git). Sans lui,
l'enregistrement est muet et un avertissement est noté. Aucun micro n'est ouvert.
L'image : uniquement la fenêtre « Project Zomboid » (jamais le bureau). En plein écran sans bordure
et au premier plan, cette capture se fige : `pzdev film --video` passe le jeu en fenêtre 1600 x 900.
"""
from pathlib import Path
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import threading
import time
import wave

DEPS = Path(__file__).resolve().parents[2] / ".pydeps"
if DEPS.is_dir():
    sys.path.insert(0, str(DEPS))
try:
    import numpy as np
    import soundcard as sc
except ImportError:  # optional: video without sound
    np = sc = None

WINDOW = "gfxcapture=window_title=^Project Zomboid$:capture_cursor=0:max_framerate=30"
MARK = re.compile(r"\[PZDirector\] (MARK|SCREENSHOT)\|([\w-]+)\s*$")


def ffmpeg(*args):
    argv = [f"{a:.6f}" if isinstance(a, float) else str(a) for a in args]
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *argv], check=True)


class ConsoleWatcher(threading.Thread):
    """Follow console.txt from its current end and report [PZDirector] MARK/SCREENSHOT lines."""

    def __init__(self, path, callback):
        super().__init__(daemon=True)
        self.path, self.callback = Path(path), callback
        self.offset = self.path.stat().st_size if self.path.exists() else 0
        self.stopped = threading.Event()

    def run(self):
        partial = b""
        while not self.stopped.is_set():
            if self.path.exists() and self.path.stat().st_size < self.offset:
                self.offset, partial = 0, b""  # the game recreates console.txt at launch
            if self.path.exists():
                with self.path.open("rb") as handle:
                    handle.seek(self.offset)
                    partial += handle.read()
                    self.offset = handle.tell()
                lines = partial.split(b"\n")
                partial = lines.pop()
                for raw in lines:
                    match = MARK.search(raw.decode("utf-8", "replace"))
                    if match:
                        self.callback(match.group(1), match.group(2))
            time.sleep(0.1)

    def stop(self):
        self.stopped.set()
        self.join(2)


class Recorder:
    def __init__(self, directory, audio=True):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.want_audio = audio
        self.markers, self.errors, self.warnings = [], [], []
        self.audio_thread = None
        self.audio_started = None
        self.audio_peak = 0
        self.stop_audio = threading.Event()
        self.audio_ready = threading.Event()
        self.speaker = None
        self.video = None
        self.started = None

    # --- sound -------------------------------------------------------------------------------
    def _record_audio(self):
        try:
            loopback = sc.get_microphone(id=self.speaker.id, include_loopback=True)
            with wave.open(str(self.directory / "audio.wav"), "wb") as output:
                output.setnchannels(2)
                output.setsampwidth(2)
                output.setframerate(48000)
                with loopback.recorder(samplerate=48000, channels=[0, 1], blocksize=2048) as recorder:
                    self.audio_started = time.perf_counter()
                    self.audio_ready.set()
                    while not self.stop_audio.is_set():
                        block = recorder.record(numframes=2048)
                        samples = (np.clip(np.nan_to_num(block), -1, 1) * 32767).astype("<i2")
                        self.audio_peak = max(self.audio_peak, int(np.abs(samples.astype("i4")).max()))
                        output.writeframes(samples.tobytes())
        except Exception as error:  # the take continues without sound
            self.warnings.append("son : " + repr(error))
            self.audio_ready.set()

    def start(self):
        if self.want_audio and sc is None:
            self.warnings.append("son : module soundcard absent (python PZDevKit/pzdev.py sound install)")
        if self.want_audio and sc is not None:
            self.speaker = sc.default_speaker()
            self.audio_thread = threading.Thread(target=self._record_audio, daemon=True)
            self.audio_thread.start()
            self.audio_ready.wait(5)
        self.started = time.perf_counter()
        self.log = (self.directory / "ffmpeg.log").open("w", encoding="utf-8")
        # Fragmented MP4: a frozen window (long teleport) sends no frame, ffmpeg then never reads
        # the "q" key and has to be killed; the take must stay readable.
        self.video = subprocess.Popen(
            ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-n", "-f", "lavfi", "-i", WINDOW,
             "-vf", "hwdownload,format=bgra,crop=trunc(iw/2)*2:trunc(ih/2)*2", "-r", "30", "-an",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
             "-movflags", "+frag_keyframe+empty_moov+default_base_moof", str(self.directory / "video.mp4")],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self.log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return self

    def mark(self, kind, name):
        if self.started is not None:
            self.markers.append({"kind": kind, "name": name,
                                 "seconds": round(time.perf_counter() - self.started, 3)})

    def stop(self):
        self.stop_audio.set()
        killed = False
        if self.video and self.video.poll() is None:
            try:
                self.video.stdin.write(b"q\n")
                self.video.stdin.flush()
                self.video.wait(20)
            except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                self.video.kill()
                self.video.wait(5)
                killed = True
        self.log.close()
        raw = self.directory / "video.mp4"
        usable = raw.exists() and raw.stat().st_size >= 4096
        if not usable:
            self.errors.append("vidéo vide : la fenêtre du jeu n'a fourni aucune image (plein écran sans bordure ?)")
        elif killed:
            self.warnings.append("FFmpeg arrêté de force (fenêtre figée) ; vidéo fragmentée conservée")
        elif self.video.returncode:
            self.errors.append(f"FFmpeg code {self.video.returncode} (voir ffmpeg.log)")
        elapsed = time.perf_counter() - self.started if self.started else 0
        length = video_seconds(raw) if usable else None
        if length is not None and elapsed > 4 and length < elapsed / 4:
            self.errors.append(f"vidéo de {length:.1f} s pour {elapsed:.0f} s d'enregistrement : fenêtre figée "
                               "(jeu en plein écran sans bordure au premier plan ?)")
        if self.audio_thread:
            self.audio_thread.join(5)
        has_audio = (self.directory / "audio.wav").exists() and self.audio_peak > 0
        if self.audio_thread and not has_audio:
            self.warnings.append("son muet ou absent")
        take = self.directory / "take.mp4"
        if usable:
            if has_audio:
                offset = (self.audio_started or self.started) - self.started
                audio_args = ["-ss", -offset] if offset < 0 else ["-itsoffset", offset]
                ffmpeg("-i", raw, *audio_args, "-i", self.directory / "audio.wav", "-map", "0:v:0", "-map", "1:a:0",
                       "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", take)
            else:
                ffmpeg("-i", raw, "-c", "copy", "-movflags", "+faststart", take)
        data = {"utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "duration": round(time.perf_counter() - self.started, 2) if self.started else 0,
                "video": "take.mp4" if usable else None, "audio": has_audio,
                "audioOutput": self.speaker.name if self.speaker else None,
                "markers": self.markers, "errors": self.errors, "warnings": self.warnings,
                "markerPrecision": "lecture de console.txt toutes les 0,1 s ; démarrage de l'encodeur ≈ 1 à 2 s"}
        (self.directory / "capture.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return data


def video_seconds(path):
    """Duration read by ffprobe, or None when it cannot be measured."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                              str(path)], capture_output=True, text=True, check=True).stdout
        return float(out.strip())
    except (OSError, subprocess.CalledProcessError, ValueError):
        return None


def ffmpeg_available():
    return shutil.which("ffmpeg") is not None
