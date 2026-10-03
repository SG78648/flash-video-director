"""style_dan.py - streaming adapter for the Dan (lifestyle) style.

The Dan look itself lives, unchanged, in generate_lifestyle.py. This adapter
only gives it the same interface the studio uses for every style (own output
folder, segments(), frame_bytes()), so it can be rendered through the shared
GPU encoder pipeline without writing PNG frames and without touching the files
the original Dan flow produces in output/.
"""
import os
import sys
from pathlib import Path

import studio_config

if "FLASH_ASPECT" not in os.environ:     # command line: follow the app's saved format
    studio_config.ensure_aspect_env()

import generate_lifestyle as L
import streaming
import voice

STYLE_ID = "dan"
OUT_DIR = Path("output/dan")
VIDEO_TITLE = "lifestyle_inflation_dan"
CLIPS = L.CLIPS
layout_problems = L.layout_problems       # for qa_check's collision gate
apply_config = L.apply_config             # studio settings -> the Dan look

_SETUP = None


def apply_to(gm):
    L.apply_to(gm)
    gm.VIDEO_TITLE = VIDEO_TITLE
    gm.OUTPUT_DIR = OUT_DIR
    gm.FRAMES_DIR = OUT_DIR / "frames"
    gm.AUDIO_DIR = OUT_DIR / "audio"
    gm.TIMING_DIR = OUT_DIR / "timing"
    gm.VIDEO_DIR = OUT_DIR / "video"
    gm.STREAM_FRAMES = True
    gm.compile_video = _compile
    global _SETUP
    _SETUP = None


def seed_audio():
    streaming.seed_audio(OUT_DIR, [c["id"] for c in L.CLIPS] + [L.HOOK_ID])


async def prepare():
    """Make sure narration + word timing exist in this style's folder."""
    import generate_video as g
    for d in (g.OUTPUT_DIR, g.AUDIO_DIR, g.TIMING_DIR, g.VIDEO_DIR):
        d.mkdir(parents=True, exist_ok=True)
    seed_audio()
    await voice.ensure_audio(g, L.CLIPS, L.HOOK_ID, L.HOOK_TEXT)


def _setup():
    global _SETUP
    if _SETUP is None:
        _SETUP = L.intro_setup()
    return _SETUP


def segments():
    import generate_video as g
    out = [("intro", _setup()[1])]
    for c in L.CLIPS:
        dur = g.get_audio_duration(g.AUDIO_DIR / f"clip{c['id']}.mp3")
        n = max(1, int((dur + g.PAD_BEFORE.get(c["id"], 0.45) + g.PAD_AFTER) * g.FPS))
        c["total_frames"] = n
        out.append((f"clip{c['id']}", n))
    out.append(("outro", 2 * g.FPS))
    return out


def frame(seg, f):
    """PIL image of frame f of a segment."""
    import generate_video as g
    if seg == "intro":
        return L.intro_frame(f, _setup())
    if seg == "outro":
        return L.outro_frame(f)
    return L.render_frame(int(seg[4:]), f / g.FPS)


def frame_bytes(seg, f):
    return frame(seg, f).tobytes()


def _compile():
    return streaming.compile_segments(sys.modules[__name__])
