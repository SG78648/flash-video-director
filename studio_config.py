"""studio_config.py - settings schema + load/save for Stickman Studio.

The schema below is the single source of truth: the studio UI builds its
controls from it, the style modules read the resulting values, and presets are
just saved copies of the config.

Config layout:  {"style": "adi"|"dan", "adi": {...}, "dan": {...}, "render": {...}}
Render jobs write their config to a JSON file and pass its path to the worker
processes through the STICKMAN_STUDIO_CONFIG environment variable.
"""
import copy
import json
import os
from pathlib import Path

ENV = "STICKMAN_STUDIO_CONFIG"
DATA_DIR = Path("studio_data")
PRESET_DIR = DATA_DIR / "presets"


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
            _c("camera.pan_ms", "Pan duration", "range", 420, min=200, max=800, step=20, unit="ms"),
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
    "render": [
        {"group": "Render", "controls": [
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
    p = Path(path) if path else (Path(os.environ[ENV]) if os.environ.get(ENV) else None)
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


def apply_render_env(cfg):
    """Translate the render settings into the environment variables the engine reads
    (set before worker processes start so they inherit them)."""
    r = cfg["render"]
    os.environ["STICKMAN_ENCODER"] = "gpu" if r["gpu_encode"] else "cpu"
    os.environ["STICKMAN_RENDER"] = "gpu" if r["gpu_compose"] else "cpu"
    os.environ["STICKMAN_CQ"] = str(int(r["quality"]))
