"""music.py - background music for the studio: library, waveform peaks and the final mix.

The finished video is rendered first (narration + sound effects, no music). The music is then mixed
onto it in a separate fast pass - the video stream is copied, only the audio is re-encoded - so the
music can be re-aligned and exported again in seconds without re-rendering a single frame.

Settings (config["music"]):
  file        name of a track in the library ("" = no music)
  enabled     switch the music on / off without losing the settings
  start       where the music begins on the video timeline (s)
  in_point    where inside the track to start playing (s)
  length      how long the music plays (s); 0 = until the end of the video
  volume_db   level of the music under the narration
  fade_in / fade_out   seconds
  duck_db     how far the music dips while someone is speaking (0 = no ducking)
  loop        repeat the track if it is shorter than `length`
"""
import re
import subprocess
from pathlib import Path

import shutil

import numpy as np

import projects

LIBRARY_DIR = projects.LIB_MUSIC            # every track you ever added (levelled once, on import)
_peak_cache = {}
_dur_cache = {}


def _safe(name):
    return "".join(ch for ch in name if ch.isalnum() or ch in " -_").strip()


def duration(path):
    path = Path(path)
    key = (str(path), path.stat().st_mtime)
    if key not in _dur_cache:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                            "default=noprint_wrappers=1:nokey=1", str(path)], capture_output=True, text=True)
        try:
            _dur_cache[key] = float(r.stdout.strip())
        except ValueError:
            _dur_cache[key] = 0.0
    return _dur_cache[key]


def project_dir():
    return projects.music_dir()


def path_of(name):
    """The project's copy of a track - what the timeline plays and what the export mixes."""
    p = project_dir() / f"{_safe(name)}.flac"
    return p if _safe(name) and p.exists() else None


def library_path(name):
    p = LIBRARY_DIR / f"{_safe(name)}.flac"
    return p if _safe(name) and p.exists() else None


def _list(folder):
    folder.mkdir(parents=True, exist_ok=True)
    return [{"name": p.stem, "file": p.name, "duration": round(duration(p), 2), "size": p.stat().st_size}
            for p in sorted(folder.glob("*.flac"))]


def list_project():
    return _list(project_dir())


def list_library():
    return _list(LIBRARY_DIR)


def import_to_project(name):
    """Copy a library track into the active project (the project keeps its own copy)."""
    src = library_path(name)
    if not src:
        raise ValueError("that track is not in the library")
    dst = project_dir() / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        shutil.copy2(src, dst)
    return src.stem


def save_to_library(name, raw_bytes, ext=".mp3"):
    """Store an uploaded track in the library as lossless FLAC (plays in every modern browser, exact for ffmpeg)."""
    safe = _safe(name)
    if not safe:
        raise ValueError("give the track a name")
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    ext = ext if ext.startswith(".") else "." + ext
    tmp = LIBRARY_DIR / f"_upload{re.sub(r'[^.a-zA-Z0-9]', '', ext)[:8]}"
    tmp.write_bytes(raw_bytes)
    out = LIBRARY_DIR / f"{safe}.flac"
    gain = _normalizing_gain(tmp)
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp), "-vn", "-af", f"volume={gain:.2f}dB",
                        "-ac", "2", "-ar", "44100", str(out)], capture_output=True, text=True)
    tmp.unlink(missing_ok=True)
    if r.returncode != 0 or not out.exists():
        raise ValueError("could not read that audio file: " + r.stderr[-200:])
    return safe


TARGET_LUFS = -16.0     # every imported track is brought to this loudness, so the volume slider means the same thing for all


def _normalizing_gain(path):
    """Static gain (dB) that brings the track's integrated loudness to TARGET_LUFS without changing its dynamics,
    limited so the true peak stays below -1 dBFS."""
    r = subprocess.run(["ffmpeg", "-nostats", "-i", str(path), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    tail = r.stderr[r.stderr.rfind("Summary:"):] if "Summary:" in r.stderr else ""
    li = re.search(r"I:\s+(-?[\d.]+)\s+LUFS", tail)
    pk = re.search(r"Peak:\s+(-?[\d.]+)\s+dBFS", tail)
    if not li:
        return 0.0
    gain = TARGET_LUFS - float(li.group(1))
    if pk:
        gain = min(gain, -1.0 - float(pk.group(1)))
    return max(-30.0, min(30.0, gain))


def delete_library(name):
    p = library_path(name)
    if p:
        p.unlink()


def delete_project_copy(name):
    p = path_of(name)
    if p:
        p.unlink()


def peaks(path, per_sec=50):
    """Loudness envelope (0..1) of an audio file, `per_sec` values per second, for waveform drawing."""
    path = Path(path)
    key = (str(path), path.stat().st_mtime, per_sec)
    if key not in _peak_cache:
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-f", "f32le", "-ac", "1",
                            "-ar", "8000", "-"], capture_output=True)
        y = np.abs(np.frombuffer(r.stdout, np.float32))
        step = max(1, 8000 // per_sec)
        n = len(y) // step
        if n == 0:
            _peak_cache[key] = []
        else:
            env = y[: n * step].reshape(n, step).max(axis=1)
            top = float(np.percentile(env, 99.5)) or 1.0
            _peak_cache[key] = [round(float(v), 3) for v in np.clip(env / top, 0, 1)]
    return _peak_cache[key]


def video_duration(path):
    return duration(path)


def mix(video_in, video_out, m, log=print):
    """Mix the music described by `m` onto `video_in` (narration + SFX) -> `video_out`.
    Returns video_out, or None if there is nothing to mix."""
    if not m.get("enabled", True) or not m.get("file"):
        return None
    mp = path_of(m["file"])
    if not mp:
        log(f"music: track '{m['file']}' is missing - skipped")
        return None
    total = video_duration(video_in)
    start = max(0.0, float(m["start"]))
    if start >= total:
        log("music: starts after the end of the video - skipped")
        return None
    avail = total - start
    length = float(m["length"]) if float(m["length"]) > 0 else avail
    length = min(length, avail)
    loop = bool(m["loop"])
    in_point = max(0.0, float(m["in_point"]))
    fi = min(max(0.0, float(m["fade_in"])), length / 2)
    fo = min(max(0.0, float(m["fade_out"])), length / 2)
    chain = [f"atrim=start={in_point:.3f}:duration={length:.3f}", "asetpts=PTS-STARTPTS",
             f"volume={float(m['volume_db']):.1f}dB"]
    if fi > 0:
        chain.append(f"afade=t=in:st=0:d={fi:.3f}")
    if fo > 0:
        chain.append(f"afade=t=out:st={length - fo:.3f}:d={fo:.3f}")
    ms = int(round(start * 1000))
    chain.append(f"adelay={ms}|{ms}")
    duck = float(m["duck_db"])
    if duck > 0:
        ratio = min(20.0, 1.0 + duck * 0.9)
        fc = (f"[1:a]{','.join(chain)}[m0];[0:a]asplit=2[pa][sc];"
              f"[m0][sc]sidechaincompress=threshold=0.04:ratio={ratio:.1f}:attack=25:release=400[m1];"
              f"[pa][m1]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.97[out]")
    else:
        fc = (f"[1:a]{','.join(chain)}[m1];"
              f"[0:a][m1]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.97[out]")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(video_in)]
    if loop:
        cmd += ["-stream_loop", "-1"]
    cmd += ["-i", str(mp), "-filter_complex", fc, "-map", "0:v", "-map", "[out]", "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", str(video_out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("music mix failed: " + r.stderr[-400:])
    log(f"music: mixed '{m['file']}' at {start:.1f}s ({float(m['volume_db']):+.0f} dB, duck {duck:.0f} dB)")
    return Path(video_out)
