"""style_text.py - the engine behind the type-only styles (Kinetic Type and Editorial Grain).

Both styles show one screen per spoken sentence and nothing else: the words of the sentence, each one arriving on the moment it is said, with the key word
picked out. No cards, no icons, no footage, no captions (the sentence IS the picture). Everything the studio needs from a style (segments, frames, narration
timing, the mixed sound) is here once; a style module only supplies its look:

    STYLE_ID                       "kinetic" or "editorial"
    THEME                          dict of colours and numbers the module reads (apply_config fills it from the studio settings)
    paint(mod, scene, t)           PIL image (W*SS x H*SS) of one screen at time t. `scene` = {"words": [(token, time)], "t0", "t1", "accent": index}
    finish(mod, img, frame_no)     the finished 1x frame (grain, vignette ...), after the gentle push-in

and calls `bind(sys.modules[__name__])` at the bottom, which gives the module the same interface style_desk has (apply_to, prepare, segments, frame_bytes).
Sound follows the starter kit's rule: small clicks on what matters (the key word), no whooshes, nothing when a screen comes or goes.
"""
import json
import re
import sys
from pathlib import Path

import projects
import script_story
import streaming
import voice
import generate_video as g
from PIL import Image, ImageDraw, ImageFont

SS = g.SS
FPS = g.FPS
W, H = g.W, g.H
FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
HOOK_ID = "hook"
QA_MAX_DUR = 100

# the middle 80% of the width and the band of the frame that phones do not cover with their own interface
MARGIN_X = 0.10


def text_box():
    """(x0, y0, x1, y1) in 1x pixels where the words may go."""
    x0, x1 = W * MARGIN_X, W * (1 - MARGIN_X)
    if g.ASPECT == "9:16":
        return x0, 340, x1, 1500
    return x0, H * 0.10, x1, H * 0.90


def clamp01(v):
    return max(0.0, min(1.0, v))


def ease_out(v, p=3):
    return 1 - (1 - clamp01(v)) ** p


def ease_in(v, p=3):
    return clamp01(v) ** p


def back_out(v, s=1.7):
    v = clamp01(v) - 1
    return v * v * ((s + 1) * v + s) + 1


# ------------------------------------------------------------------ fonts
_FONTS = {}


def font(name, px):
    """The kit's font `name` (file stem in assets/fonts) at `px` 1x pixels (drawn at SS times that)."""
    key = (name, max(8, int(round(px))))
    if key not in _FONTS:
        try:
            _FONTS[key] = ImageFont.truetype(str(FONT_DIR / f"{name}.ttf"), key[1] * SS)
        except OSError:
            _FONTS[key] = ImageFont.truetype("arialbd.ttf", key[1] * SS)
    return _FONTS[key]


_SCRATCH = ImageDraw.Draw(Image.new("L", (8, 8)))


def text_w(s, f):
    """Width of `s` in 1x pixels."""
    return _SCRATCH.textlength(s, font=f) / SS


def layer(s, f, fill, pad=0.12, tracking=0.0):
    """RGBA image of `s` (tight, with a pad of `pad` x the font size) and the baseline offset: returns (img, ox, oy) where (ox, oy) is where the text origin
    ('ls' anchor) sits inside the image, in SS pixels."""
    px = f.size
    p = int(px * pad)
    if tracking:
        w = sum(_SCRATCH.textlength(ch, font=f) for ch in s) + tracking * px * (len(s) - 1)
    else:
        w = _SCRATCH.textlength(s, font=f)
    asc, desc = f.getmetrics()
    img = Image.new("RGBA", (int(w) + 2 * p, asc + desc + 2 * p), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if tracking:
        x = p
        for ch in s:
            d.text((x, p + asc), ch, font=f, fill=fill, anchor="ls")
            x += _SCRATCH.textlength(ch, font=f) + tracking * px
    else:
        d.text((p, p + asc), s, font=f, fill=fill, anchor="ls")
    return img, p, p + asc


def paste_layer(img, lay, x, y, alpha=1.0):
    """Paste RGBA `lay` with its top-left at (x, y) SS pixels, faded by `alpha`."""
    if alpha <= 0.01:
        return
    if alpha < 0.99:
        a = lay.getchannel("A").point(lambda v: int(v * alpha))
        lay = lay.copy()
        lay.putalpha(a)
    img.paste(lay, (int(x), int(y)), lay)


def flow(widths, maxw, space):
    """Greedy line breaking: `widths` = [(index, width)] -> [[(index, width)]] with every line at most `maxw` wide (a single word never splits)."""
    lines, cur, cw = [], [], 0.0
    for i, w in widths:
        add = w + (space if cur else 0)
        if cur and cw + add > maxw:
            lines.append(cur)
            cur, cw, add = [], 0.0, w
        cur.append((i, w))
        cw += add
    if cur:
        lines.append(cur)
    return lines


# ------------------------------------------------------------------ the story and its word times
_STORY = None
_WORDS = {}
_ACC = {}


def story():
    global _STORY
    if _STORY is None:
        _STORY = script_story.load(projects.active()) or script_story.build(DEMO_SCRIPT)
    return _STORY


DEMO_SCRIPT = """Most product videos lose people in two seconds.
Here's how to keep them.
Show the result first.
Cut every pause.
One idea on screen at a time.
Then tell them what to do next."""


def beat_words(c, bi):
    """[(word, clip time)] spoken inside beat `bi` of clip `c`."""
    cid = c["id"]
    path = g.TIMING_DIR / f"clip{cid}.json"
    try:
        stamp = path.stat().st_mtime
    except OSError:
        stamp = 0
    key = (cid, bi, str(path), stamp)
    if key not in _WORDS:
        out = []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))["words"]
            bs, be = g.clip_beats(c)[bi]
            pad = g.PAD_BEFORE.get(cid, 0.45)
            out = [(w["word"], pad + w["start"]) for w in data if bs - 0.01 <= pad + w["start"] <= be - 0.01]
        except Exception:
            pass
        _WORDS[key] = out
    return _WORDS[key]


def accent_index(tokens):
    """The key word of a sentence: a number first, then the longest real word (the later one on a tie)."""
    best, score = len(tokens) - 1, -1
    for i, tk in enumerate(tokens):
        w = re.sub(r"[^A-Za-z0-9$%']", "", tk)
        if not w:
            continue
        if re.search(r"\d|\$", w):
            s = 100 + len(w)
        elif w.lower() in script_story.STOP:
            s = 0
        else:
            s = len(w)
        if s >= score:
            best, score = i, s
    return best


def scene_of(c, bi):
    """The screen of beat `bi`: its words with their spoken times, its window and the key word."""
    text = story()["feats"][str(c["id"])][bi]["text"]
    toks = text.split()
    ws = beat_words(c, bi)
    bs, be = g.clip_beats(c)[bi]
    if ws and len(ws) == len(toks):
        words = [(tk, w[1]) for tk, w in zip(toks, ws)]
    else:                                       # no timing yet (or it does not line up): spread the words over the beat
        words = [(tk, bs + (be - bs) * 0.85 * i / max(1, len(toks))) for i, tk in enumerate(toks)]
    return {"words": words, "t0": bs, "t1": be, "accent": accent_index(toks), "key": (c["id"], bi)}


def hook_scene(total):
    st = story()
    toks = " ".join(st["hook_head"]).split()
    try:
        data = json.loads((g.TIMING_DIR / f"clip{HOOK_ID}.json").read_text(encoding="utf-8"))["words"]
        ts = [g.INTRO_PAD_BEFORE + w["start"] for w in data]
    except Exception:
        ts = []
    if len(ts) != len(toks):
        ts = [0.1 + 0.9 * i / max(1, len(toks)) for i in range(len(toks))]
    return {"words": list(zip(toks, ts)), "t0": 0.0, "t1": total, "accent": accent_index(toks), "key": ("hook",)}


def outro_scene(dur=1.6):
    lines = story()["outro"]["lines"]
    toks = " ".join(lines).split()
    return {"words": [(tk, 0.1 + 0.9 * i / max(1, len(toks))) for i, tk in enumerate(toks)], "t0": 0.0, "t1": dur, "accent": accent_index(toks), "key": ("outro",)}


# ------------------------------------------------------------------ the interface every style gives the studio
def bind(mod):
    """Give style module `mod` (STYLE_ID, THEME, paint, finish) the interface the studio uses for every style."""
    state = {"setup": None, "segs": []}
    mod.OUT_DIR = projects.style_dir(mod.STYLE_ID)
    mod.VIDEO_TITLE = mod.STYLE_ID
    mod.HOOK_ID = HOOK_ID
    mod.HOOK_TEXT = ""
    mod.QA_MAX_DUR = QA_MAX_DUR
    mod.CLIPS, mod.NARR_BEATS, mod.PAD_BEFORE = [], {}, {}
    mod.INTRO_SFX, mod.OUTRO_SFX = [], []
    mod.layout_problems = lambda: []           # the layout is measured from the real text, so nothing can collide

    def apply_to(gm):
        global _STORY
        mod.OUT_DIR = projects.style_dir(mod.STYLE_ID)
        _STORY = None
        _WORDS.clear()
        state["setup"] = None
        story_ = story()
        mod.CLIPS[:] = story_["clips"]
        mod.NARR_BEATS.clear()
        mod.NARR_BEATS.update({int(k): v for k, v in story_["beats"].items()})
        mod.PAD_BEFORE.clear()
        mod.PAD_BEFORE.update({i: 0.30 for i in range(1, len(story_["clips"]) + 1)})
        mod.HOOK_TEXT = story_["hook"]
        gm.VIDEO_TITLE = mod.VIDEO_TITLE
        gm.CLIPS = mod.CLIPS
        gm.NARR_BEATS = mod.NARR_BEATS
        gm.PAD_BEFORE = mod.PAD_BEFORE
        gm.PAD_AFTER = 0.10
        gm.INTRO_PAD_AFTER = 0.10
        gm.QA_MAX_DUR = QA_MAX_DUR
        gm.MUSIC_BED = None
        gm.INTRO_HOOK_ID = HOOK_ID
        gm.OUTPUT_DIR = mod.OUT_DIR
        gm.FRAMES_DIR = mod.OUT_DIR / "frames"
        gm.AUDIO_DIR = mod.OUT_DIR / "audio"
        gm.TIMING_DIR = mod.OUT_DIR / "timing"
        gm.VIDEO_DIR = mod.OUT_DIR / "video"
        gm.STREAM_FRAMES = True
        gm.compile_video = lambda: streaming.compile_segments(mod)
        gm._TIMING_CACHE.clear()
        gm._WORD_P_CACHE.clear()
        gm._CAM_EVENTS_CACHE.clear()
        gm.sfx_events = sfx_events
        gm.build_mixed_audio = mixed_audio
        mod.apply_config()

    def intro_setup():
        if state["setup"] is None:
            hook_dur = g.get_audio_duration(g.AUDIO_DIR / f"clip{HOOK_ID}.mp3")
            total = hook_dur + g.INTRO_PAD_BEFORE + g.INTRO_PAD_AFTER
            state["setup"] = (total, max(1, int(total * FPS)))
        return state["setup"]

    def sfx_events(clip):
        """One quiet click on the key word of each screen (the kit's rule: small sounds on what matters, nothing when a screen comes or goes)."""
        if not mod.THEME.get("click"):
            return []
        evs = []
        for bi in range(len(g.clip_beats(clip))):
            sc = scene_of(clip, bi)
            evs.append((max(0.0, sc["words"][sc["accent"]][1]), mod.THEME["click"], 0.30))
        return evs

    def mixed_audio(name):
        import sfx_gen
        wav = g.AUDIO_DIR / f"{name}_mixed.wav"
        if name == "intro":
            hook_path = g.AUDIO_DIR / f"clip{g.INTRO_HOOK_ID}.mp3"
            narr = sfx_gen.decode_mp3(hook_path)
            dur = g.get_audio_duration(hook_path) + g.INTRO_PAD_BEFORE + g.INTRO_PAD_AFTER
            sfx_gen.make_track(dur, [], narr, g.INTRO_PAD_BEFORE, wav, sfx_gain=0.45, bed=None, bed_gain=0.0)
        elif name == "outro":
            sfx_gen.make_track(2.0, [], None, 0.0, wav, sfx_gain=0.45, bed=None, bed_gain=0.0)
        else:
            cid = int(name[4:])
            clip = g.CLIPS[cid - 1]
            narr = sfx_gen.decode_mp3(g.AUDIO_DIR / f"clip{cid}.mp3")
            sfx_gen.make_track(clip["total_frames"] / g.FPS, sfx_events(clip), narr, g.PAD_BEFORE.get(cid, 0.30), wav, sfx_gain=0.45, bed=None, bed_gain=0.0)
        return wav

    async def prepare():
        for d in (g.OUTPUT_DIR, g.AUDIO_DIR, g.TIMING_DIR, g.VIDEO_DIR):
            d.mkdir(parents=True, exist_ok=True)
        await voice.ensure_audio(g, mod.CLIPS, HOOK_ID, mod.HOOK_TEXT)
        import tighten
        tighten.apply(g.AUDIO_DIR, g.TIMING_DIR, [c["id"] for c in mod.CLIPS] + [HOOK_ID], True)

    def segments():
        out = [("intro", intro_setup()[1])]
        for c in mod.CLIPS:
            dur = g.get_audio_duration(g.AUDIO_DIR / f"clip{c['id']}.mp3")
            n = max(1, int((dur + g.PAD_BEFORE.get(c["id"], 0.30) + g.PAD_AFTER) * FPS))
            c["total_frames"] = n
            out.append((f"clip{c['id']}", n))
        out.append(("outro", int(1.6 * FPS)))
        state["segs"][:] = out
        return out

    def frame(seg, f):
        t = f / FPS
        if seg == "intro":
            total = intro_setup()[0]
            sc, tt = hook_scene(total), t
        elif seg == "outro":
            sc, tt = outro_scene(), t
        else:
            c = mod.CLIPS[int(seg[4:]) - 1]
            beats = g.clip_beats(c)
            idx, _p = g.local_beat(c, t)
            if idx > 0 and t < beats[idx][0]:
                idx -= 1
            sc, tt = scene_of(c, idx), t
        img = mod.paint(sc, tt, f, seg)
        u = clamp01((tt - sc["t0"]) / max(0.5, sc["t1"] - sc["t0"]))
        img = g.apply_camera(img, 1.0 + mod.THEME.get("push", 0.02) * u, 0.0, 0.0)
        return mod.finish(img, f)

    mod.apply_to = apply_to
    mod.prepare = prepare
    mod.segments = segments
    mod.frame = frame
    mod.frame_bytes = lambda seg, f: frame(seg, f).tobytes()
    mod.sfx_events = sfx_events
    mod.seed_audio = lambda: None
