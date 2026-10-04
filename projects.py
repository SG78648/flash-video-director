"""projects.py - where Flash Studio keeps things.

    projects/<Project name>/      one folder per project (made in the app)
        project.json              every setting of the project (style, look, voice, music, render, format)
        adi/  dan/                the working files of each style: narration + timing, video segments, mixed audio
        music/  sfx/              copies of the library tracks / effects used in this project
        <style>/edit.json         the post-production edit of that style
    library/                      things that belong to the user, not to one project
        voices/                   cloned voices (reference samples)
        presets/                  saved presets
        music/                    the music library (levelled tracks)
        sfx/                      the sound-effect library
        cache/                    re-usable generated data: synthesised narration, sound effects
    output/                       the finished videos, all in one flat folder
    studio_data/                  the app's own bookkeeping (active project, jobs, preview, logs)

The active project is `FLASH_PROJECT` (set for worker processes), else the one saved in
studio_data/app.json, else the default project.
"""
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECTS_DIR = ROOT / "projects"
LIBRARY_DIR = ROOT / "library"
OUTPUT_DIR = ROOT / "output"
DATA_DIR = ROOT / "studio_data"
ENV = "FLASH_PROJECT"
DEFAULT_PROJECT = "Lifestyle Inflation"
STYLES = ("adi", "dan")

LIB_VOICES = LIBRARY_DIR / "voices"
LIB_PRESETS = LIBRARY_DIR / "presets"
LIB_MUSIC = LIBRARY_DIR / "music"
LIB_SFX = LIBRARY_DIR / "sfx"
LIB_CACHE = LIBRARY_DIR / "cache"
ORIGINAL_NARRATION = LIB_CACHE / "narration-original"      # {audio,timing}/ of the edge voice every new project starts from
APP_FILE = DATA_DIR / "app.json"


# ---------------------------------------------------------------- names
def safe_name(name):
    """A project name that is safe as a folder name and as part of a file name (no '_' - it separates the parts)."""
    n = "".join(ch if (ch.isalnum() or ch in " -") else " " for ch in (name or ""))
    n = re.sub(r"\s+", " ", n).strip(" -")
    return n[:60]


# ---------------------------------------------------------------- projects
def project_dir(name=None):
    return PROJECTS_DIR / (name or active())


def style_dir(style, name=None):
    return project_dir(name) / style


def music_dir(name=None):
    return project_dir(name) / "music"


def sfx_dir(name=None):
    return project_dir(name) / "sfx"


def assets_dir(name=None):
    """Images used in this project (logos, stickers, end cards) - always PNG."""
    return project_dir(name) / "assets"


def edit_path(style, name=None):
    """The post-production edit of a style (cuts, trims, audio clips...) - non-destructive, applied at export."""
    return style_dir(style, name) / "edit.json"


def config_path(name=None):
    return project_dir(name) / "project.json"


def exists(name):
    return bool(name) and (PROJECTS_DIR / name).is_dir()


def list_projects():
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for p in sorted(PROJECTS_DIR.iterdir(), key=lambda q: q.name.lower()):
        if p.is_dir() and not p.name.startswith((".", "_")):
            f = p / "project.json"
            out.append({"name": p.name, "mtime": (f if f.exists() else p).stat().st_mtime,
                        "styles": [s for s in STYLES if (p / s).is_dir()],
                        "script": (p / "script.txt").exists()})
    return out


def create(name, script=None, config=None):
    """Make the folder of a new project with the factory settings (and, with a script, its story). Returns the (cleaned) name."""
    import studio_config
    n = safe_name(name)
    if not n:
        raise ValueError("give the project a name")
    if exists(n):
        raise ValueError(f"a project called '{n}' already exists")
    for s in STYLES:
        (PROJECTS_DIR / n / s).mkdir(parents=True, exist_ok=True)
    (PROJECTS_DIR / n / "music").mkdir(parents=True, exist_ok=True)
    (PROJECTS_DIR / n / "sfx").mkdir(parents=True, exist_ok=True)
    (PROJECTS_DIR / n / "assets").mkdir(parents=True, exist_ok=True)
    studio_config.save(config or studio_config.defaults(), PROJECTS_DIR / n / "project.json")
    if script and script.strip():
        import script_story
        try:
            script_story.save_script(script, n)
        except ValueError:
            shutil.rmtree(PROJECTS_DIR / n)
            raise
    return n


def rename(old, new):
    n = safe_name(new)
    if not n:
        raise ValueError("give the project a name")
    if not exists(old):
        raise ValueError("no such project")
    if n != old and exists(n):
        raise ValueError(f"a project called '{n}' already exists")
    if n != old:
        (PROJECTS_DIR / old).rename(PROJECTS_DIR / n)
        if active() == old:
            set_active(n)
    return n


def delete(name):
    """Remove a project's working files. Finished videos live in output/ and are not touched."""
    if not exists(name):
        raise ValueError("no such project")
    shutil.rmtree(PROJECTS_DIR / name)
    if _saved_active() == name:
        rest = list_projects()
        set_active(rest[0]["name"] if rest else None)


def _saved_active():
    try:
        return json.loads(APP_FILE.read_text(encoding="utf-8")).get("project")
    except Exception:
        return None


def set_active(name):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    APP_FILE.write_text(json.dumps({"project": name}), encoding="utf-8")


def active():
    """The project everything works on right now (created on first use)."""
    name = os.environ.get(ENV) or _saved_active()
    if not name or not exists(name):
        projs = list_projects()
        name = projs[0]["name"] if projs else create(DEFAULT_PROJECT)
        if not os.environ.get(ENV):
            set_active(name)
    return name


# ---------------------------------------------------------------- finished videos (one flat folder)
_FINAL = re.compile(r"^(?P<project>.+)_(?P<style>adi|dan)_(?P<fmt>9x16|1x1|16x9)_(?P<stamp>\d{4}-\d{2}-\d{2}_\d{6})(?P<music>_music|_edit)?\.mp4$")
FMT_OF = {"9:16": "9x16", "1:1": "1x1", "16:9": "16x9"}
ASPECT_OF = {v: k for k, v in FMT_OF.items()}


def final_path(project, style, aspect, music=False, stamp=None, edited=False):
    stamp = stamp or datetime.now().strftime("%Y-%m-%d_%H%M%S")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tail = "_edit" if edited else "_music" if music else ""
    return OUTPUT_DIR / f"{project}_{style}_{FMT_OF[aspect]}_{stamp}{tail}.mp4"


def parse_final(name):
    m = _FINAL.match(name)
    if not m:
        return None
    return {"project": m["project"], "style": m["style"], "aspect": ASPECT_OF[m["fmt"]], "stamp": m["stamp"],
            "music": bool(m["music"])}      # True for the edited / with-music versions; False for the plain render


def list_finals():
    """Videos made by the studio, newest first (other files in output/ are ignored)."""
    out = []
    if OUTPUT_DIR.exists():
        for p in OUTPUT_DIR.glob("*.mp4"):
            info = parse_final(p.name)
            if info:
                st = p.stat()
                out.append(dict(info, name=p.name, size=st.st_size, mtime=st.st_mtime, path=p))
    return sorted(out, key=lambda v: -v["mtime"])
