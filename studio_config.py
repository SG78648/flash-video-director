"""studio_config.py - settings schema + load/save for Flash Studio.

The schema below is the single source of truth: the studio UI builds its
controls from it, the style modules read the resulting values, and presets are
just saved copies of the config.

Config layout:  {"style": "adi"|"dan", "adi": {...}, "dan": {...}, "render": {...}}
Render jobs write their config to a JSON file and pass its path to the worker
processes through the FLASH_STUDIO_CONFIG environment variable.
"""
import copy
import json
import os
from pathlib import Path

import projects

ENV = "FLASH_STUDIO_CONFIG"
DATA_DIR = projects.DATA_DIR              # the app's own bookkeeping (active project, jobs, logs)
PRESET_DIR = projects.LIB_PRESETS         # presets and cloned voices belong to the user, not to a project
VOICE_DIR = projects.LIB_VOICES


def _c(key, label, kind, default, **kw):
    return {"key": key, "label": label, "kind": kind, "default": default, **kw}


SCHEMA = {
    "adi": [
        {"group": "Colours", "controls": [
            _c("palette.bg", "Paper", "color", "#EEECE1"),
            _c("palette.grid", "Grid lines", "color", "#DDDBD0"),
            _c("palette.ink", "Text / ink", "color", "#2A1B13"),
            _c("palette.accent", "Accent", "color", "#F6611B"),
            _c("palette.negative", "Negative / alert", "color", "#DD4226"),
            _c("palette.highlight", "Highlighter", "color", "#FFD400"),
            _c("palette.card", "Card surface", "color", "#FCFAF5"),
            _c("palette.shadow", "Card shadow", "color", "#D2C9BE"),
            _c("palette.thread", "Thread", "color", "#96948C"),
            _c("palette.muted", "Muted text", "color", "#968C7E"),
            _c("palette.dark_chip", "Dark chip", "color", "#0E0C0A"),
        ]},
        {"group": "Layout", "controls": [
            _c("layout.margin", "Side margin", "range", 64, min=40, max=110, step=2, unit="px"),
            _c("layout.headline_scale", "Headline size", "range", 1.0, min=0.7, max=1.3, step=0.02, unit="x"),
            _c("layout.headline_dy", "Headline up / down", "range", 0, min=-200, max=200, step=4, unit="px"),
            _c("layout.content_dy", "Whole content up / down", "range", 0, min=-200, max=200, step=4, unit="px"),
            _c("layout.hero", "Hero illustration", "select", "top-right", options=["top-right", "top-left", "off"]),
            _c("layout.hero_size", "Hero size", "range", 190, min=110, max=300, step=5, unit="px"),
        ]},
        {"group": "Elements", "controls": [
            _c("layout.show_grid", "Paper grid", "toggle", True),
            _c("layout.show_thread", "Thread between frames", "toggle", True),
            _c("layout.progress_bar", "Progress line", "toggle", True),
            _c("layout.card_shadow", "Card shadows", "toggle", True),
            _c("layout.card_dots", "Card window dots", "toggle", True),
            _c("layout.inline_icons", "Icons inside cards", "toggle", True),
            _c("layout.marks", "Marker circles / underlines", "toggle", True),
            _c("layout.notes", "Handwritten notes", "toggle", True),
            _c("layout.stamps", "Stamps", "toggle", True),
        ]},
        {"group": "Type", "controls": [
            _c("type.tracking", "Letter spacing", "range", -0.012, min=-0.04, max=0.03, step=0.002, unit="em"),
        ]},
        {"group": "Camera", "controls": [
            _c("camera.pan_ms", "Pan duration", "range", 560, min=200, max=800, step=20, unit="ms"),
            _c("camera.blur_samples", "Motion blur quality", "range", 13, min=1, max=16, step=1, unit="taps"),
            _c("camera.blur_shutter", "Motion blur amount", "range", 0.5, min=0.1, max=1.0, step=0.05, unit="frame"),
            _c("camera.follow", "Drift along the thread", "range", 0.6, min=0.0, max=1.5, step=0.05, unit="x"),
            _c("camera.ghost", "Next-frame preview", "range", 0.2, min=0.0, max=0.5, step=0.02, unit="opacity"),
        ]},
    ],
    "dan": [
        {"group": "Look", "controls": [
            _c("theme", "Theme", "select", "light", options=["light", "dark"]),
            _c("palette.accent", "Accent", "color", "#46AAEB"),
            _c("palette.negative", "Negative / alert", "color", "#E12D2D"),
            _c("fx.post", "Film finish (tone, vignette, grain)", "toggle", True),
        ]},
        {"group": "Layout", "controls": [
            _c("layout.caption_y", "Caption bar height", "range", 500, min=380, max=640, step=4, unit="px"),
            _c("layout.show_grid", "Background grid", "toggle", True),
        ]},
        {"group": "Camera", "controls": [
            _c("camera.drift", "Slow push-in", "range", 0.014, min=0.0, max=0.05, step=0.002, unit="x"),
        ]},
    ],
    "voice": [
        {"group": "Voice", "controls": [
            _c("engine", "Voice engine", "select", "edge", options=["edge", "chatterbox"]),
            _c("edge_voice", "Edge voice", "select", "en-US-GuyNeural",
               options=["en-US-GuyNeural", "en-US-ChristopherNeural", "en-US-AriaNeural", "en-US-JennyNeural",
                        "en-GB-RyanNeural", "en-GB-SoniaNeural"]),
            _c("speed", "Speaking speed", "range", 1.12, min=0.9, max=1.4, step=0.02, unit="x"),
            _c("reference", "Reference voice to clone", "select", "", options=[""]),
            _c("exaggeration", "Expressiveness", "range", 0.5, min=0.25, max=1.5, step=0.05, unit=""),
            _c("cfg_weight", "Pacing / adherence", "range", 0.5, min=0.1, max=1.0, step=0.05, unit=""),
            _c("pause", "Pause between sentences", "range", 0.75, min=0.4, max=1.2, step=0.05, unit="s"),
            _c("seed", "Variation seed", "range", 7, min=1, max=99, step=1, unit=""),
        ]},
    ],
    "music": [
        {"group": "Music", "controls": [
            _c("file", "Track", "select", "", options=[""]),
            _c("enabled", "Use music", "toggle", True),
            _c("start", "Starts at", "range", 0.0, min=0, max=120, step=0.05, unit="s"),
            _c("in_point", "Start inside the track", "range", 0.0, min=0, max=600, step=0.05, unit="s"),
            _c("length", "Plays for", "range", 0.0, min=0, max=120, step=0.1, unit="s", zero="Until the end"),
            _c("volume_db", "Volume", "range", -12.0, min=-40, max=6, step=0.5, unit="dB"),
            _c("fade_in", "Fade in", "range", 1.5, min=0, max=10, step=0.1, unit="s"),
            _c("fade_out", "Fade out", "range", 3.0, min=0, max=15, step=0.1, unit="s"),
            _c("duck_db", "Dip under speech", "range", 8.0, min=0, max=20, step=0.5, unit="dB", zero="Off"),
            _c("loop", "Loop if the track is shorter", "toggle", True),
        ]},
    ],
    "render": [
        {"group": "Render", "controls": [
            _c("aspect", "Format", "select", "9:16", options=["9:16", "1:1", "16:9"]),
            _c("cooling", "Cooling", "select", "balanced", options=["quiet", "balanced", "fast"]),
            _c("gpu_compose", "GPU camera / compositing", "toggle", True),
            _c("gpu_encode", "GPU video encoder (NVENC)", "toggle", True),
            _c("quality", "Quality (lower = better, bigger file)", "range", 25, min=16, max=32, step=1, unit="cq"),
        ]},
    ],
}


def _set(d, dotted, value):
    parts = dotted.split(".")
    for p in parts[:-1]:
        d = d.setdefault(p, {})
    d[parts[-1]] = value


def _get(d, dotted, default=None):
    for p in dotted.split("."):
        if not isinstance(d, dict) or p not in d:
            return default
        d = d[p]
    return d


def defaults():
    cfg = {"style": "adi"}
    for section, groups in SCHEMA.items():
        sec = {}
        for grp in groups:
            for c in grp["controls"]:
                _set(sec, c["key"], c["default"])
        cfg[section] = sec
    return cfg


def _merge(base, over):
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        elif k in base:
            base[k] = v
    return base


def normalize(cfg):
    """Defaults overlaid with `cfg`; unknown keys are dropped."""
    return _merge(defaults(), copy.deepcopy(cfg or {}))


def load(path=None):
    """Settings from `path`, else the file named by FLASH_STUDIO_CONFIG (set for render
    jobs), else the active project's project.json so command-line tools follow what was
    configured in the app, else the defaults."""
    p = Path(path) if path else (Path(os.environ[ENV]) if os.environ.get(ENV) else projects.config_path())
    if p and p.exists():
        try:
            return normalize(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    return defaults()


def save(cfg, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(normalize(cfg), indent=2), encoding="utf-8")


def rgb(hex_str):
    h = hex_str.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def list_presets():
    PRESET_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(p.stem for p in PRESET_DIR.glob("*.json"))


def save_preset(name, cfg):
    safe = "".join(ch for ch in name if ch.isalnum() or ch in " -_").strip()
    if not safe:
        raise ValueError("preset name is empty")
    save(cfg, PRESET_DIR / f"{safe}.json")
    return safe


def load_preset(name):
    safe = "".join(ch for ch in name if ch.isalnum() or ch in " -_").strip()
    return load(PRESET_DIR / f"{safe}.json")


def ensure_aspect_env(cfg=None):
    """Export the chosen video format as FLASH_ASPECT. generate_video reads it once, when it is
    imported, so this must run BEFORE the first import of generate_video / streaming / a style module."""
    cfg = cfg or load()
    a = cfg["render"].get("aspect", "9:16")
    os.environ["FLASH_ASPECT"] = a if a in ("9:16", "1:1", "16:9") else "9:16"
    return os.environ["FLASH_ASPECT"]


def apply_render_env(cfg):
    """Translate the render settings into the environment variables the engine reads
    (set before worker processes start so they inherit them)."""
    r = cfg["render"]
    ensure_aspect_env(cfg)
    os.environ["FLASH_ENCODER"] = "gpu" if r["gpu_encode"] else "cpu"
    os.environ["FLASH_RENDER"] = "gpu" if r["gpu_compose"] else "cpu"
    os.environ["FLASH_CQ"] = str(int(r["quality"]))


def _safe(name):
    return "".join(ch for ch in name if ch.isalnum() or ch in " -_").strip()


def list_voices():
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(p.stem for p in VOICE_DIR.glob("*.wav"))


def voice_path(name):
    """Reference wav for a saved voice name ('' = Chatterbox's built-in voice -> None)."""
    n = _safe(name or "")
    p = VOICE_DIR / f"{n}.wav"
    return p if n and p.exists() else None
