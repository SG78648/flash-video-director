"""sfxlib.py - the sound-effect library, the twin of the music library.

  library/sfx/<name>.flac        every effect you ever added (peak-levelled once, on import)
  projects/<p>/sfx/<name>.flac   the copy a project uses (what the timeline plays and the export mixes)
  built-in effects               the twelve generated sounds the renderer uses (whoosh, pop, stamp...);
                                 they live in library/cache/sfx and can be placed anywhere on the timeline

Uploaded effects are brought to a -3 dBFS peak so they are comparable; on the timeline they start at
-10 dB, about as loud as the renderer's own effects.
"""
import re
import shutil
import subprocess
import wave

import music
import projects
import sfx_gen

LIBRARY_DIR = projects.LIB_SFX
PEAK_DB = -3.0
_safe = music._safe


def project_dir():
    return projects.sfx_dir()


def path_of(name):
    p = project_dir() / f"{_safe(name)}.flac"
    return p if _safe(name) and p.exists() else None


def library_path(name):
    p = LIBRARY_DIR / f"{_safe(name)}.flac"
    return p if _safe(name) and p.exists() else None


def _list(folder):
    folder.mkdir(parents=True, exist_ok=True)
    return [{"name": p.stem, "duration": round(music.duration(p), 2), "size": p.stat().st_size}
            for p in sorted(folder.glob("*.flac"))]


def list_project():
    return _list(project_dir())


def list_library():
    return _list(LIBRARY_DIR)


def builtin():
    """The renderer's own effects with their lengths."""
    sfx_gen.ensure_sfx()
    out = []
    for name in sfx_gen.GENERATORS:
        p = sfx_gen.SFX_DIR / f"{name}.wav"
        try:
            with wave.open(str(p), "rb") as w:
                dur = w.getnframes() / w.getframerate()
        except Exception:
            dur = 0.0
        out.append({"name": name, "duration": round(dur, 2)})
    return out


def builtin_path(name):
    p = sfx_gen.SFX_DIR / f"{_safe(name)}.wav"
    return p if _safe(name) and name in sfx_gen.GENERATORS and p.exists() else None


def import_to_project(name):
    src = library_path(name)
    if not src:
        raise ValueError("that effect is not in the library")
    dst = project_dir() / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        shutil.copy2(src, dst)
    return src.stem


def _peak_gain(path):
    r = subprocess.run(["ffmpeg", "-nostats", "-i", str(path), "-vn", "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"max_volume:\s*(-?[\d.]+) dB", r.stderr)
    return max(-30.0, min(30.0, PEAK_DB - float(m.group(1)))) if m else 0.0


def save_to_library(name, raw_bytes, ext=".wav"):
    safe = _safe(name)
    if not safe:
        raise ValueError("give the effect a name")
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    ext = ext if ext.startswith(".") else "." + ext
    tmp = LIBRARY_DIR / f"_upload{re.sub(r'[^.a-zA-Z0-9]', '', ext)[:8]}"
    tmp.write_bytes(raw_bytes)
    out = LIBRARY_DIR / f"{safe}.flac"
    gain = _peak_gain(tmp)
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp), "-vn", "-af", f"volume={gain:.2f}dB",
                        "-ac", "2", "-ar", "48000", str(out)], capture_output=True, text=True)
    tmp.unlink(missing_ok=True)
    if r.returncode != 0 or not out.exists():
        raise ValueError("could not read that audio file: " + r.stderr[-200:])
    return safe


def delete_library(name):
    p = library_path(name)
    if p:
        p.unlink()


def delete_project_copy(name):
    p = path_of(name)
    if p:
        p.unlink()
