import asyncio
import json
import math
import os
import random
import re
import subprocess
from datetime import datetime
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

import sfx_gen

try:
    import edge_tts
except ImportError:
    subprocess.run(["pip", "install", "edge-tts", "--quiet"])
    import edge_tts

# ---- output geometry ----
# Output geometry. The shape comes from STICKMAN_ASPECT (the studio / CLI set it before this module is
# imported); 9:16 is the original vertical format and stays the default for every older story.
ASPECTS = {"9:16": (1080, 1920), "1:1": (1080, 1080), "16:9": (1920, 1080)}
ASPECT = os.environ.get("STICKMAN_ASPECT", "9:16")
if ASPECT not in ASPECTS:
    ASPECT = "9:16"
ASPECT_TAG = {"9:16": "", "1:1": "_1x1", "16:9": "_16x9"}[ASPECT]
W, H = ASPECTS[ASPECT]     # final output size
SS = 2                     # supersample factor (anti-aliasing)
RW, RH = W * SS, H * SS    # render size
FPS = 24
OUTPUT_DIR = Path("output")
FRAMES_DIR = OUTPUT_DIR / "frames"
AUDIO_DIR = OUTPUT_DIR / "audio"
TIMING_DIR = OUTPUT_DIR / "timing"

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (225, 45, 45)
BLUE = (45, 125, 235)
GOLD = (255, 205, 55)
GRAY = (150, 150, 158)
DIM = (78, 78, 86)
BG_LINE = (18, 18, 22)

VOICE = "en-US-JennyNeural"
RATE = "-5%"
QA_MAX_DUR = 75                # longest allowed final video (s); stories may raise

VIDEO_TITLE = "income_vs_wealth"
MUSIC_BED = None               # story opts in by setting a pad_bed() key via apply_to()
INTRO_HOOK_ID = None            # story opts in with a pseudo-clip id (e.g. "hook") for a spoken intro
INTRO_PAD_BEFORE = 0.12
INTRO_PAD_AFTER = 0.35

CLIPS = [
    {"id": 1, "name": "The Hook",
     "narration": "Someone making ten thousand a month can be poorer than someone making five thousand. Sounds stupid, right? But watch."},
    {"id": 2, "name": "Person A",
     "narration": "Person A makes ten thousand a month. They spend three thousand on the car, two thousand on rent, one thousand on food, and two more thousand trying to look successful. They have two thousand left."},
    {"id": 3, "name": "Person B",
     "narration": "Person B makes five thousand. But they only spend three thousand. The other two thousand goes into assets."},
    {"id": 4, "name": "Compounding",
     "narration": "Month after month. Soon, person B owns things that produce income without working for every dollar."},
    {"id": 5, "name": "The Trap",
     "narration": "And person A? They need their ten thousand paycheck just to maintain their lifestyle."},
    {"id": 6, "name": "The Lesson",
     "narration": "That's why I stopped calling income wealth. Income tells you how much money comes in. Wealth tells you how much keeps working when you stop. Completely different game."},
]

NARR_BEATS = {
    1: ["Someone making ten thousand a month", "can be poorer than someone making five thousand", "Sounds stupid right But watch"],
    2: ["Person A makes ten thousand a month", "spend three thousand on the car two thousand on rent one thousand on food two more thousand trying to look successful", "They have two thousand left"],
    3: ["Person B makes five thousand", "they only spend three thousand", "the other two thousand goes into assets"],
    4: ["Month after month", "person B owns things that produce income", "without working for every dollar"],
    5: ["And person A", "need their ten thousand paycheck", "to maintain their lifestyle"],
    6: ["That's why I stopped calling income wealth", "Income tells you how much money comes in", "Wealth tells you how much keeps working when you stop"],
}

PAD_BEFORE = {1: 0.45, 6: 0.5}
PAD_AFTER = 0.35


# ============================================================ animation math

def clamp01(t): return max(0.0, min(1.0, t))
def ease(t):
    t = clamp01(t)
    return t * t * (3 - 2 * t)
def ease_out(t):
    t = clamp01(t)
    return 1 - (1 - t) ** 3
def ease_in(t):
    t = clamp01(t)
    return t ** 3
def elastic(t):
    """easeOutBack: smooth pop with single gentle overshoot, no oscillation."""
    t = clamp01(t)
    t -= 1
    c1 = 1.70158
    c3 = c1 + 1
    return clamp01(1 + c3 * t * t * t + c1 * t * t)
def bounce_out(t):
    t = clamp01(t)
    if t < 1 / 2.75: return 7.5625 * t * t
    elif t < 2 / 2.75:
        t -= 1.5 / 2.75
        return 7.5625 * t * t + 0.75
    elif t < 2.5 / 2.75:
        t -= 2.25 / 2.75
        return 7.5625 * t * t + 0.9375
    else:
        t -= 2.625 / 2.75
        return 7.5625 * t * t + 0.984375
def lerp(a, b, t): return a + (b - a) * t
def spring(t, k=14.0):
    # underdamped spring from rest-offset
    t = clamp01(t)
    zeta = 0.62
    w = k
    wd = w * math.sqrt(1 - zeta * zeta)
    A = 1.0
    phi = 0.0
    return 1 - math.exp(-zeta * w * t) * (A * math.cos(wd * t) + (zeta * w / wd) * math.sin(wd * t))


# ============================================================ supersampled draw

class D2:
    """Proxy that scales all drawing coordinates & widths by SS for sharp AA."""
    SCALE = SS

    def __init__(self, raw):
        self.r = raw

    def _p(self, xy):
        if isinstance(xy, tuple):
            return tuple(v * D2.SCALE for v in xy)
        if xy and isinstance(xy[0], (list, tuple)):
            return [(x * D2.SCALE, y * D2.SCALE) for x, y in xy]
        return [v * D2.SCALE for v in xy]

    def line(self, xy, fill=None, width=None, joint=None):
        kw = {}
        if joint is not None: kw["joint"] = joint
        self.r.line(self._p(xy), fill=fill,
                    width=None if width is None else max(1, int(round(width * D2.SCALE))), **kw)

    def rectangle(self, xy, fill=None, outline=None, width=1):
        self.r.rectangle(self._p(xy), fill=fill, outline=outline,
                         width=max(1, int(round(width * D2.SCALE))))

    def ellipse(self, xy, fill=None, outline=None, width=1):
        self.r.ellipse(self._p(xy), fill=fill, outline=outline,
                       width=max(1, int(round(width * D2.SCALE))))

    def arc(self, xy, start, end, fill=None, width=1):
        self.r.arc(self._p(xy), start, end, fill=fill,
                   width=max(1, int(round(width * D2.SCALE))))

    def polygon(self, xy, fill=None, outline=None, width=1):
        self.r.polygon([(x * D2.SCALE, y * D2.SCALE) for x, y in xy], fill=fill, outline=outline,
                       width=max(1, int(round(width * D2.SCALE))))

    def rounded_rectangle(self, xy, radius=0, fill=None, outline=None, width=1):
        self.r.rounded_rectangle(self._p(xy), radius=radius * D2.SCALE, fill=fill,
                                 outline=outline, width=max(1, int(round(width * D2.SCALE))))

    def text(self, xy, text, fill=None, font=None, anchor=None):
        x, y = xy
        self.r.text((x * D2.SCALE, y * D2.SCALE), text, fill=fill, font=font)

    def textlength(self, text, font=None):
        return self.r.textlength(text, font=font) / D2.SCALE


class Fonts:
    cache = {}

    @classmethod
    def get(cls, px):
        key = px * D2.SCALE
        if key not in cls.cache:
            try:
                cls.cache[key] = ImageFont.truetype("arialbd.ttf", int(round(px * D2.SCALE)))
            except Exception:
                try:
                    cls.cache[key] = ImageFont.truetype("arial.ttf", int(round(px * D2.SCALE)))
                except Exception:
                    cls.cache[key] = ImageFont.load_default()
        return cls.cache[key]


def bloom(img, radius=30, intensity=0.5):
    blurred = img.filter(ImageFilter.GaussianBlur(radius=radius))
    weighted = blurred.point(lambda x: min(255, int(x * intensity)))
    return ImageChops.add(img, weighted, scale=1, offset=0)


# ---- optional cinematic post pass (opt-in per story via post_process()) ----

_VIGNETTE = None
_GRAIN_TILES = None
_GRADE_LUT = None


def _build_vignette():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = W / 2, H * 0.46
    dist = np.sqrt(((xx - cx) / (W * 0.72)) ** 2 + ((yy - cy) / (H * 0.62)) ** 2)
    falloff = np.clip(1.0 - 0.38 * np.clip(dist - 0.55, 0, None) ** 1.6, 0.55, 1.0)
    arr = (falloff[..., None] * 255).astype(np.uint8).repeat(3, axis=2)
    return Image.fromarray(arr, "RGB")


def _build_grain_tiles(n=8, sigma=10):
    return [Image.effect_noise((W, H), sigma).convert("RGB") for _ in range(n)]


def _build_grade_lut():
    lut = []
    for _ in range(3):
        for i in range(256):
            x = i / 255
            y = x + (0.06 * math.sin(math.pi * x)) - (0.10 * x ** 3)
            lut.append(int(max(0, min(255, y * 255))))
    return lut


def post_process(img, frame_idx=0, grade=True, vignette=True, grain=True):
    """Cheap cinematic finishing pass: filmic tone curve -> vignette -> temporal
    film grain. `img` must already be at final W x H resolution (post-bloom).
    Everything expensive is precomputed once and cached at module scope."""
    global _VIGNETTE, _GRAIN_TILES, _GRADE_LUT
    if grade:
        if _GRADE_LUT is None:
            _GRADE_LUT = _build_grade_lut()
        img = img.point(_GRADE_LUT)
    if vignette:
        if _VIGNETTE is None:
            _VIGNETTE = _build_vignette()
        img = ImageChops.multiply(img, _VIGNETTE)
    if grain:
        if _GRAIN_TILES is None:
            _GRAIN_TILES = _build_grain_tiles()
        img = Image.blend(img, _GRAIN_TILES[frame_idx % len(_GRAIN_TILES)], alpha=0.035)
    return img


# ---- optional beat-locked camera (opt-in per story via apply_camera()) ----

_CAM_EVENTS_CACHE = {}


def camera_punch_events(clip):
    """Beat-locked camera punch times: reuses sfx_events() so a punch always
    lands on the same stamp/slam hit the audio already accents."""
    cid = clip["id"]
    if cid not in _CAM_EVENTS_CACHE:
        evs = sfx_events(clip)
        _CAM_EVENTS_CACHE[cid] = [(t, name) for t, name, *_ in evs if name in ("stamp", "slam")]
    return _CAM_EVENTS_CACHE[cid]


def camera_state(clip, t_abs, base_drift=0.025, punch_amt=0.10, punch_decay=0.22):
    """scale=1.0 at rest (today's exact framing). Drift keys off local_beat()/
    clip_beats(), punches key off sfx_events() timing -- never off raw t_abs
    alone, so a re-voice keeps the camera in sync automatically."""
    idx, p = local_beat(clip, t_abs)
    scale = 1.0 + base_drift * ease(p)
    pan_x = (1 if idx % 2 == 0 else -1) * 0.012 * ease(p)
    for t_ev, _name in camera_punch_events(clip):
        dt = t_abs - t_ev
        if 0 <= dt < 0.5:
            scale += punch_amt * math.exp(-dt / punch_decay)
    return scale, pan_x, 0.0


def apply_camera(img_ss, scale, pan_x, pan_y):
    """Crop-then-resize substitute for the plain SS->1x resize. Since the frame
    is rendered at RW,RH = W*SS,H*SS, cropping a smaller-than-full window and
    resizing up to W,H is still a net downsample (no upsampling softness) as
    long as scale >= 1.0."""
    scale = max(1.0, scale)
    sw, sh = img_ss.size           # the page the story drew on (may differ from RW x RH: Dan's compact pages)
    cw, ch = sw / scale, sh / scale
    cx, cy = sw / 2 + pan_x * sw, sh / 2 + pan_y * sh
    x0 = max(0, min(sw - cw, cx - cw / 2))
    y0 = max(0, min(sh - ch, cy - ch / 2))
    crop = img_ss.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch)))
    return crop.resize((W, H), Image.LANCZOS)


def big_text(d, x, y, text, color=WHITE, px=60, anchor_mid=True):
    f = Fonts.get(px)
    if anchor_mid:
        w = d.textlength(text, font=f) / 2
        d.text((x - w, y - px / 2), text, fill=color, font=f)
    else:
        d.text((x, y), text, fill=color, font=f)


# ============================================================ primitives

def house(d, x, y, size=44, color=WHITE, lw=3, fill=None, shadow=False):
    s = size
    bw = max(2, lw)
    if shadow:
        off = s * 0.10
        d.rectangle([x - s + off, y - s * 0.72 + off, x + s + off, y + off], fill=(14, 14, 18))
        d.polygon([(x - s - s * 0.18 + off, y - s * 0.72 + off),
                   (x + s + s * 0.18 + off, y - s * 0.72 + off),
                   (x + off, y - s * 0.72 - s * 0.58 + off)], fill=(14, 14, 18))
    if fill:
        d.rectangle([x - s, y - s * 0.72, x + s, y], fill=fill, outline=color, width=bw)
    else:
        d.rectangle([x - s, y - s * 0.72, x + s, y], outline=color, width=bw)
    d.line([x - s - s * 0.18, y - s * 0.72, x, y - s * 0.72 - s * 0.58], fill=color, width=bw)
    d.line([x + s + s * 0.18, y - s * 0.72, x, y - s * 0.72 - s * 0.58], fill=color, width=bw)
    d.line([x - s - s * 0.18, y - s * 0.72, x + s + s * 0.18, y - s * 0.72], fill=color, width=bw)
    dw = s * 0.26
    d.rectangle([x - dw, y - s * 0.44, x + dw, y], outline=color, width=max(2, bw - 1))
    win = s * 0.16
    d.rectangle([x - s * 0.55 - win, y - s * 0.48 - win, x - s * 0.55 + win, y - s * 0.48 + win],
                outline=color, width=max(2, bw - 2))
    d.rectangle([x + s * 0.55 - win, y - s * 0.48 - win, x + s * 0.55 + win, y - s * 0.48 + win],
                outline=color, width=max(2, bw - 2))


def coin(d, x, y, r=18, color=GOLD, lw=3, rot=0, shadow=False):
    if shadow:
        off = r * 0.16
        d.ellipse([x - r + off, y - r + off, x + r + off, y + r + off], fill=(14, 14, 18))
    d.ellipse([x - r, y - r, x + r, y + r], outline=color, width=lw)
    ir = r * 0.62
    d.ellipse([x - ir, y - ir, x + ir, y + ir], outline=color, width=max(2, lw - 1))
    for i in range(4):
        a = rot + i * math.pi / 2
        d.line([x, y, x + math.cos(a) * ir, y + math.sin(a) * ir], fill=color, width=2)


def xmark(d, x, y, size=14, color=RED, lw=5):
    d.line([x - size, y - size, x + size, y + size], fill=color, width=lw)
    d.line([x + size, y - size, x - size, y + size], fill=color, width=lw)


def check(d, x, y, size=14, color=BLUE, lw=5):
    d.line([x - size, y, x - size * 0.2, y + size], fill=color, width=lw)
    d.line([x - size * 0.2, y + size, x + size, y - size], fill=color, width=lw)


def stamp_x(d, x, y, size=60, color=RED, rot=0.4, opaque=1.0):
    c, s_ = math.cos(rot), math.sin(rot)
    pairs = [((-1, -1), (1, 1)), ((1, -1), (-1, 1))]
    col = (int(color[0] * opaque), int(color[1] * opaque), int(color[2] * opaque)) if opaque < 1 else color
    for p0, p1 in pairs:
        x1 = x + p0[0] * size * c - p0[1] * size * s_
        y1 = y + p0[0] * size * s_ + p0[1] * size * c
        x2 = x + p1[0] * size * c - p1[1] * size * s_
        y2 = y + p1[0] * size * s_ + p1[1] * size * c
        d.line([x1, y1, x2, y2], fill=col, width=max(8, int(size * 0.16)))


def arrow(d, x1, y1, x2, y2, color=WHITE, lw=5, head=1.0):
    d.line([x1, y1, x2, y2], fill=color, width=lw)
    a = math.atan2(y2 - y1, x2 - x1)
    hl = 26 * head
    d.line([x2, y2, x2 - hl * math.cos(a - 0.45), y2 - hl * math.sin(a - 0.45)], fill=color, width=lw)
    d.line([x2, y2, x2 - hl * math.cos(a + 0.45), y2 - hl * math.sin(a + 0.45)], fill=color, width=lw)


def price_tag(d, x, y, w=70, h=34, color=WHITE, lw=3):
    d.rectangle([x - w, y - h, x + w, y + h], outline=color, width=lw)
    d.line([x - w, y + h, x - w - 16, y + h + 16], fill=color, width=lw)
    d.ellipse([x - w - 21, y + h + 11, x - w - 11, y + h + 21], outline=color, width=lw)


def gold_block(d, x, y, w=46, h=22, alpha=1.0):
    c = (int(GOLD[0] * alpha), int(GOLD[1] * alpha), int(GOLD[2] * alpha))
    d.rectangle([x - w // 2, y - h, x + w // 2, y], outline=c, width=3)
    d.line([x - w // 2, y - h / 2, x + w // 2, y - h / 2], fill=c, width=2)


def gold_building(d, x, y, w, h, alpha=1.0, shadow=False, color=None, shadow_color=None):
    base = color if color is not None else GOLD
    c = (int(base[0] * alpha), int(base[1] * alpha), int(base[2] * alpha))
    if shadow:
        off = max(6, w * 0.09)
        d.rectangle([x - w // 2 + off, y - h + off, x + w // 2 + off, y + off],
                    fill=shadow_color if shadow_color is not None else (14, 14, 18))
    d.rectangle([x - w // 2, y - h, x + w // 2, y], outline=c, width=3)
    n = max(1, int(h / 16))
    for i in range(n):
        wy = y - h + 9 + i * 16
        if wy > y - 4:
            break
        d.line([x - w // 5, wy, x + w // 5, wy], fill=c, width=2)


def glow_circle(d, x, y, r, color, layers=3, alpha=0.5):
    for i in range(layers, 0, -1):
        rr = r * (1 + i * 0.35)
        a = alpha / (i + 1)
        col = (int(color[0] * a), int(color[1] * a), int(color[2] * a))
        d.ellipse([x - rr, y - rr, x + rr, y + rr], outline=col, width=6)


def crease_lines(d, x, y, count=3, color=RED):
    for k in range(count):
        d.line([x + 6 + k * 10, y, x + 22 + k * 12, y + 22 + k * 4], fill=color, width=3)



# ============================================================ timing engine

def norm_tok(w):
    return re.sub(r"[^a-z0-9]", "", w.lower())


async def gen_audio_and_timing(clip):
    cid = clip["id"]
    audio_path = AUDIO_DIR / f"clip{cid}.mp3"
    timing_path = TIMING_DIR / f"clip{cid}.json"
    comm = edge_tts.Communicate(clip["narration"], VOICE, rate=RATE, pitch="+0Hz",
                                boundary="WordBoundary")
    audio = b""
    words = []
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            audio += chunk["data"]
        elif chunk["type"] == "WordBoundary":
            off = chunk.get("offset", chunk.get("Offset"))
            dur = chunk.get("duration", chunk.get("Duration"))
            wtext = chunk.get("text", chunk.get("Text"))
            if isinstance(off, str):
                off = int(off)
                dur = int(dur)
            words.append({
                "word": wtext,
                "start": off / 1e7,
                "end": (off + dur) / 1e7,
            })
    with open(audio_path, "wb") as fh:
        fh.write(audio)
    dur = words[-1]["end"] if words else 0.0
    if words:
        # trim the dead tail ffmpeg-style: mp3 outlasts the last word by ~1s
        limit = dur + 0.30
        tmp = audio_path.with_suffix(".trim.mp3")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(audio_path),
                        "-t", f"{limit:.3f}", "-c:a", "libmp3lame", "-b:a", "192k",
                        str(tmp)], check=False)
        if tmp.exists() and tmp.stat().st_size > 0:
            tmp.replace(audio_path)
    with open(timing_path, "w") as fh:
        json.dump({"words": words, "duration": dur, "narration": clip["narration"],
                   "voice": VOICE}, fh)
    print(f"    clip{cid}: {len(words)} words, {dur:.2f}s")


def beat_ranges_abs(clip):
    """Return [(start_abs, end_abs)] for each beat, clip-time (seconds)."""
    cid = clip["id"]
    timing_path = TIMING_DIR / f"clip{cid}.json"
    try:
        with open(timing_path) as fh:
            data = json.load(fh)
        words = data["words"]
    except Exception:
        return None

    pad = PAD_BEFORE.get(cid, 0.45)
    beats = NARR_BEATS[cid]
    ranges = []
    idx = 0
    last_end = words[-1]["end"] if words else pad
    for phrase in beats:
        expected = [norm_tok(w) for w in phrase.split() if norm_tok(w)]
        if idx >= len(words):
            break
        start_t = words[idx]["start"]
        consumed = 0
        j = idx
        while j < len(words) and consumed < len(expected):
            tok = norm_tok(words[j]["word"])
            if tok == expected[consumed]:
                consumed += 1
            j += 1
        end_t = words[j - 1]["end"] if j > idx else start_t + 0.5
        ranges.append((pad + start_t, pad + end_t))
        idx = j
    # residual beats (repeated phrases with no new words) sit at the tail
    s = pad + last_end if len(ranges) == len(beats) - 1 else (ranges[-1][1] if ranges else pad + last_end)
    while len(ranges) < len(beats):
        ranges.append((s, s + 0.75))
        s += 0.75
    return ranges


_TIMING_CACHE = {}


def clip_beats(clip):
    cid = clip["id"]
    if cid not in _TIMING_CACHE:
        r = beat_ranges_abs(clip)
        _TIMING_CACHE[cid] = r or [(0.5 + i * 2.5, 1.5 + i * 2.5) for i in range(len(NARR_BEATS[cid]))]
    return _TIMING_CACHE[cid]


def local_beat(clip, t_abs):
    beats = clip_beats(clip)
    for i, (bs, be) in enumerate(beats):
        if t_abs < bs:
            return i, 0.0
        if t_abs <= be:
            return i, clamp01((t_abs - bs) / (be - bs + 1e-6))
    return len(beats) - 1, 1.0


_WORD_P_CACHE = {}


def beat_word_p(clip, bi, word):
    """p (0..1) inside beat `bi` at which the spoken word lands (word-locked triggers)."""
    key = (clip["id"], bi, word)
    if key in _WORD_P_CACHE:
        return _WORD_P_CACHE[key]
    beats = clip_beats(clip)
    v = 0.5
    if bi < len(beats) and beats[bi][1] > beats[bi][0]:
        bs, be = beats[bi]
        pad = PAD_BEFORE.get(clip["id"], 0.45)
        span = be - bs
        try:
            with open(TIMING_DIR / f"clip{clip['id']}.json") as fh:
                words = json.load(fh)["words"]
        except Exception:
            words = []
        target = norm_tok(word)
        for w in words:
            ct = pad + w["start"]
            if ct >= bs - 0.01 and ct <= be - 0.01 and norm_tok(w["word"]) == target:
                v = clamp01((ct - bs) / span)
                break
    _WORD_P_CACHE[key] = v
    return v


def beat_abs(clip, bi, prog=0.0):
    """Absolute clip-time of progress `prog` inside beat `bi` (0..1)."""
    bs, be = clip_beats(clip)[bi]
    return bs + clamp01(prog) * (be - bs)


def beat_word_t(clip, bi, word, fallback_p=0.5):
    """Absolute clip-time when the spoken word lands inside beat `bi`."""
    bs, be = clip_beats(clip)[bi]
    return bs + beat_word_p(clip, bi, word) * (be - bs)


def fade_text(d, x, y, t_abs, trig, text, color=WHITE, px=60, dur=0.16):
    """Draw text that fades (and gently scales) in over `dur` seconds after `trig`."""
    aq = clamp01((t_abs - trig) / dur)
    aq = aq * aq * (3 - 2 * aq)
    if aq <= 0.02:
        return
    c = tuple(min(255, int(v * aq)) for v in color)
    big_text(d, x, y, text, color=c, px=px)


def pop_text(d, x, y, t_abs, trig, text, color=WHITE, px=60, dur=0.16, grow=1.10):
    """Like fade_text but scales in with a single soft overshoot (no flash),
    settling at exactly `px`. (Previously the smoothstep-based scale curve
    asymptoted to (0.6+grow)x ~= 1.7x instead of 1.0x -- it never actually
    settled, which is why fully-popped-in captions ran oversized and could
    collide with neighboring labels the layout guard had otherwise placed
    correctly. elastic() already implements exactly this "overshoot then
    settle at 1.0" curve, so reuse it instead of a bespoke formula.)"""
    aq = clamp01((t_abs - trig) / (dur * 1.4))
    px2 = max(1, int(px * elastic(aq)))
    aq2 = clamp01((t_abs - trig) / dur)
    aq2 = aq2 * aq2 * (3 - 2 * aq2)
    if aq2 <= 0.02:
        return
    c = tuple(min(255, int(v * aq2)) for v in color)
    big_text(d, x, y, text, color=c, px=px2)


def get_audio_duration(audio_path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 6.0


# ============================================================ scene: clip 1

def _mix_col(bg, fg, a):
    return (int(bg[0] + (fg[0] - bg[0]) * a),
            int(bg[1] + (fg[1] - bg[1]) * a),
            int(bg[2] + (fg[2] - bg[2]) * a))


def _coin_pile(d, x, y, n, color=GOLD, r=13, gap=26, rot=0.0):
    for i in range(max(0, n)):
        coin(d, x, y - 12 - i * gap, r=r, color=color, rot=rot + i)


def draw_clip1(d, t_abs):
    idx, p = local_beat(CLIPS[0], t_abs)
    cx, cy = W // 2, H // 2 + 90
    ax, ay = cx - 250, cy + 200
    bx, by = cx + 250, cy + 200
    c1 = CLIPS[0]

    if idx == 0:
        # A makes 10K, B makes 5K -> wait, A can be poorer
        _coin_pile(d, ax, ay, int(spring(p, k=10) * 10), GOLD, r=14)
        if p > 0.12:
            _coin_pile(d, bx, by, int(spring(clamp01((p - 0.12) / 0.8), k=10) * 5), BLUE, r=14)
        fade_text(d, ax, ay + 90, t_abs, beat_abs(c1, 0, 0), "PERSON A", WHITE, 28)
        fade_text(d, ax, ay + 150, t_abs, beat_abs(c1, 0, 0), "$10,000 / MO", GOLD, 26)
        fade_text(d, bx, by + 90, t_abs, beat_abs(c1, 0, 0.12), "PERSON B", WHITE, 28)
        fade_text(d, bx, by + 150, t_abs, beat_abs(c1, 0, 0.12), "$5,000 / MO", BLUE, 26)

    elif idx == 1:
        # "can be poorer than someone making five thousand"
        slots = [("A STACK", ax, ay, 10, GOLD), ("B STACK", bx, by, 5, BLUE)]
        for lab, xx, yy, n, col in slots:
            _coin_pile(d, xx, yy, int(n + 6 * spring(p, k=10)), col, r=13, rot=t_abs * 0.5)
        fade_text(d, ax, ay + 90, t_abs, beat_abs(c1, 1, 0), "PERSON A", WHITE, 26)
        fade_text(d, ax, ay + 140, t_abs, beat_abs(c1, 1, 0), "$10,000 / MO", GOLD, 22)
        fade_text(d, bx, by + 90, t_abs, beat_abs(c1, 1, 0), "PERSON B", WHITE, 26)
        fade_text(d, bx, by + 140, t_abs, beat_abs(c1, 1, 0), "$5,000 / MO", BLUE, 22)
        poorer = beat_word_p(c1, 1, "poorer")
        st = spring(clamp01((p - poorer) / 0.12), k=14)
        if st > 0.05:
            stamp_x(d, ax, ay - 300, size=88 * st, color=RED, rot=0.4 * st, opaque=0.85 * st)
        pop_text(d, ax, ay - 380, t_abs, beat_word_t(c1, 1, "poorer"), "POORER?", RED, 34)
        if st > 0.6:
            arrow(d, ax + 70, ay - 170, bx - 70, by - 170, color=RED, lw=5)

    else:
        # "But watch"
        watch = beat_word_p(c1, 2, "watch")
        ring = 60 + spring(p, k=8) * 300
        glow_circle(d, cx, cy + 140, ring, RED, layers=2, alpha=0.5)
        if p > 0.25:
            d.ellipse([cx - ring, cy + 140 - ring, cx + ring, cy + 140 + ring],
                      outline=RED, width=6)
        if watch > 0:
            w = elastic(clamp01((p - watch) / 0.15))
            big_text(d, cx, cy - 160, "BUT WATCH", px=int(58 + 10 * w), color=GOLD)
        _coin_pile(d, ax, cy + 400, 10, GOLD, r=12, rot=t_abs)
        _coin_pile(d, bx, cy + 400, 5, BLUE, r=12, rot=t_abs)
        fade_text(d, cx, cy + 460, t_abs, beat_abs(c1, 2, 0.1), "A > B... OR IS IT?", GRAY, 24)


# ============================================================ scene: clip 2

def draw_clip2(d, t_abs):
    idx, p = local_beat(CLIPS[1], t_abs)
    cx, cy = W // 2, H // 2 + 90
    base = cy + 170
    sx = cx - 280
    c2 = CLIPS[1]
    slots = [("CAR", 3, "$3K", (-50, -90)), ("RENT", 2, "$2K", (150, -90)),
             ("FOOD", 1, "$1K", (-50, 100)), ("LOOK", 2, "$2K", (150, 100))]
    wkey = ["car", "rent", "food", "look"]
    th = [beat_word_p(c2, 1, w) for w in wkey]

    if idx == 0:
        lift = spring(p, k=10)
        _coin_pile(d, cx, base, int(lift * 10))
        fade_text(d, cx, base + 90, t_abs, beat_abs(c2, 0, 0), "PERSON A", WHITE, 32)
        fade_text(d, cx, base + 150, t_abs, beat_abs(c2, 0, 0), "$10,000 / MONTH", GOLD, 28)
        glow_circle(d, cx, base, 150, GOLD, layers=2, alpha=0.25)

    elif idx == 1:
        # expenses peel off the stack as each word is spoken
        spent = 0
        for i, (lab, n, amt, (ox, oy)) in enumerate(slots):
            prog = clamp01((p - th[i]) / 0.08)
            if prog <= 0:
                continue
            spent += n
            tx, ty = cx + ox, cy + oy
            if prog < 0.75:
                ex = lerp(sx, tx, ease_out(prog))
                ey = lerp(base - 30, ty + 16, ease_out(prog))
                for k in range(n):
                    coin(d, ex, ey - k * 24, r=12, color=GOLD, rot=t_abs * 2 + i)
            else:
                arr = spring(clamp01((prog - 0.75) / 0.25), k=10)
                hw, hh = 84 * arr, 46 * arr
                if arr > 0.2:
                    d.rectangle([tx - hw, ty - hh, tx + hw, ty + hh], outline=RED, width=4)
                    pop_text(d, tx, ty - 9, t_abs, beat_abs(c2, 1, th[i] + 0.07), lab, WHITE, 22)
                    pop_text(d, tx, ty + 25, t_abs, beat_abs(c2, 1, th[i] + 0.075), amt, RED, 22)
                    for k2 in range(n):
                        coin(d, tx, ty - 2 - k2 * 24, r=12,
                             color=_mix_col(GOLD, RED, 0.35), rot=t_abs * 2 + i)
        rem = max(0, 10 - spent)
        _coin_pile(d, sx, base, int(spring(p, k=10) * 10) if spent == 0 else rem, GOLD)
        fade_text(d, sx, base + 80, t_abs, beat_abs(c2, 1, 0), "STACK", GRAY, 22)

    else:
        # "They have two thousand left" — pop when "left" lands
        g = elastic(p)
        _coin_pile(d, sx, base, 2)
        left = beat_word_p(c2, 2, "left")
        fade_text(d, sx, base + 70, t_abs, beat_abs(c2, 2, left), "LEFT", WHITE, 36)
        fade_text(d, sx, base + 130, t_abs, beat_abs(c2, 2, left + 0.04), "$2,000", GOLD, 40)
        for i, (lab, n, amt, (ox, oy)) in enumerate(slots):
            a = clamp01((p - left) / 0.4)
            tx, ty = cx + ox, cy + oy
            d.rectangle([tx - 84, ty - 46, tx + 84, ty + 46], outline=DIM, width=4) if a > 0.15 else None
            xmark(d, tx, ty + 66, size=18, color=RED) if a > 0.55 else None
        fade_text(d, cx, cy - 300, t_abs, beat_abs(c2, 2, min(1.0, left + 0.2)),
                  "ALL THE REST IS GONE", RED, 30)


# ============================================================ scene: clip 3

def draw_clip3(d, t_abs):
    idx, p = local_beat(CLIPS[2], t_abs)
    cx, cy = W // 2, H // 2 + 90
    base = cy + 200
    bx = cx + 260
    c3 = CLIPS[2]

    if idx == 0:
        g = spring(p, k=10)
        _coin_pile(d, cx, base, int(g * 5), BLUE, r=14)
        fade_text(d, cx, base + 90, t_abs, beat_abs(c3, 0, 0), "PERSON B", WHITE, 32)
        fade_text(d, cx, base + 150, t_abs, beat_abs(c3, 0, 0), "$5,000 / MONTH", BLUE, 26)
        glow_circle(d, cx, base, 150, BLUE, layers=2, alpha=0.3)

    elif idx == 1:
        # only spend 3 of 5
        s3 = spring(clamp01(p / 0.6), k=10)
        s2 = spring(clamp01((p - 0.3) / 0.7), k=10)
        _coin_pile(d, cx - 150, base + 60, int(s3 * 3), _mix_col(BLUE, RED, 0.45), r=13)
        _coin_pile(d, cx + 150, base, int(s2 * 2), GOLD, r=13)
        fade_text(d, cx - 150, base + 150, t_abs, beat_abs(c3, 1, 0), "SPEND", RED, 28)
        fade_text(d, cx - 150, base + 205, t_abs, beat_abs(c3, 1, 0), "$3,000", RED, 24)
        fade_text(d, cx + 150, base + 95, t_abs, beat_abs(c3, 1, 0), "KEEP", WHITE, 28)
        fade_text(d, cx + 150, base + 150, t_abs, beat_abs(c3, 1, 0), "$2,000", GOLD, 24)
        three = beat_word_p(c3, 1, "three")
        fade_text(d, cx, cy - 330, t_abs, beat_abs(c3, 1, three), "SPENDS ONLY 3 OF 5", RED, 34)

    else:
        # the other 2 go into assets
        two = beat_word_p(c3, 2, "two")
        flow = clamp01((p - two) / 0.55)
        for k in range(2):
            ex = lerp(cx + 150, bx, ease_out(flow))
            ey = lerp(base - 40, cy + 30, ease_out(flow))
            coin(d, ex, ey, r=12, color=GOLD, rot=t_abs * 2 + k)
        grow = spring(clamp01((p - two) / 0.6), k=10)
        bh = 70 + grow * 200
        gold_building(d, bx, cy + 60, 90, bh, 1.0)
        glow_circle(d, bx, cy + 60, 130 + grow * 60, GOLD, alpha=0.35)
        arrow(d, cx + 120, base - 90, bx - 50, cy + 20, color=GOLD, lw=6) if p > two else None
        assets = beat_word_p(c3, 2, "assets")
        if p >= assets:
            check(d, bx, cy + 60 - bh, size=22, color=BLUE)
        pop_text(d, bx, cy + 60 - bh - 80, t_abs, beat_abs(c3, 2, assets), "ASSET", GOLD, 32)
        fade_text(d, cx, cy - 330, t_abs, beat_abs(c3, 2, assets - 0.15),
                  "THE 2K BECOMES AN ASSET", GOLD, 30)


# ============================================================ scene: clip 4

def draw_clip4(d, t_abs):
    idx, p = local_beat(CLIPS[3], t_abs)
    cx, cy = W // 2, H // 2 + 90
    c4 = CLIPS[3]

    if idx == 0:
        # month after month, building + income pile grow
        g = int(spring(p, k=10) * 24)
        gh = 80 + g * 12
        gold_building(d, cx - 180, cy + 220, 90, gh, 1.0)
        m = min(3, 1 + int(p * 3))
        for i in range(m):
            fade_text(d, cx - 180, cy + 220 - gh - 50 - i * 70, t_abs,
                      beat_abs(c4, 0, i / 3.0), f"MONTH {i+1}", GRAY, 30)
        _coin_pile(d, cx + 170, cy + 300, int(spring(p, k=9) * 14), GOLD, r=11, gap=22)
        fade_text(d, cx + 170, cy + 360, t_abs, beat_abs(c4, 0, 0.3), "INCOME", GOLD, 30)
        fade_text(d, cx, cy - 320, t_abs, beat_abs(c4, 0, 0), "MONTH AFTER MONTH", WHITE, 40)

    elif idx == 1:
        # owns things that produce income
        gold_building(d, cx - 190, cy + 220, 90, 210, 1.0)
        owns = beat_word_p(c4, 1, "owns")
        if p > owns:
            badge = spring(clamp01((p - owns) / 0.4), k=10)
            d.rectangle([cx - 190 - 88, cy - 30, cx - 190 + 88, cy + 6], outline=GOLD, width=4) if badge > 0.1 else None
        pop_text(d, cx - 190, cy - 12, t_abs, beat_word_t(c4, 1, "owns"), "YOU OWN IT", GOLD, 26)
        _coin_pile(d, cx + 170, cy + 300, int(spring(p, k=9) * 20), GOLD, r=11, gap=22)
        fade_text(d, cx + 170, cy + 370, t_abs, beat_abs(c4, 1, 0), "PAYS YOU", GOLD, 30)
        d.line([cx, cy + 60, cx + 60, cy + 210], fill=GOLD, width=4)
        fade_text(d, cx - 20, cy - 130, t_abs, beat_abs(c4, 1, 0.5), "BUILD THE INCOME", GOLD, 34)

    else:
        # without working for every dollar
        working = beat_word_p(c4, 2, "working")
        if p > working:
            w = elastic(clamp01((p - working) / 0.1))
            xmark(d, cx, cy - 190, size=int(72 * w), color=RED)
        pop_text(d, cx, cy - 290, t_abs, beat_word_t(c4, 2, "working"),
                 "WORK FOR EVERY DOLLAR?", RED, 40)
        gold_building(d, cx - 230, cy + 240, 100, 240, 1.0)
        _coin_pile(d, cx + 160, cy + 320, min(22, int(spring(p, k=9) * 22)), GOLD, r=11, gap=22)
        arrow(d, cx - 90, cy + 70, cx + 70, cy + 210, color=GOLD, lw=6)
        fade_text(d, cx + 160, cy + 390, t_abs, beat_abs(c4, 2, 0), "INCOME FLOWS ON", GOLD, 28)
        fade_text(d, cx, cy + 500, t_abs, beat_abs(c4, 2, working + 0.1),
                  "WITHOUT YOU WORKING", RED, 30)


# ============================================================ scene: clip 5

def draw_clip5(d, t_abs):
    idx, p = local_beat(CLIPS[4], t_abs)
    cx, cy = W // 2, H // 2 + 90
    c5 = CLIPS[4]

    if idx == 0:
        # And person A?
        _coin_pile(d, cx, cy + 150, int(spring(p, k=10) * 10), GOLD, r=13)
        fade_text(d, cx, cy + 260, t_abs, beat_abs(c5, 0, 0), "PERSON A", WHITE, 32)
        if p > 0.2:
            for k, chy in enumerate([cy + 40, cy + 110, cy + 180]):
                ck = clamp01((p - 0.2) / 0.6) * (1 - k * 0.15)
                d.ellipse([cx - 62 - ck * 30, chy - 18, cx + 62 + ck * 30, chy + 18],
                          outline=GRAY, width=6)
        qs = elastic(clamp01((p - 0.3) / 0.5))
        if qs > 0.1:
            big_text(d, cx - 250, cy + 60, "?", px=int(120 * qs) + 10, color=RED)
        fade_text(d, cx, cy + 340, t_abs, beat_abs(c5, 0, 0.6), "WAIT, WHAT ABOUT A?", RED, 30)

    elif idx == 1:
        # need their ten thousand paycheck
        pay = beat_word_p(c5, 1, "paycheck")
        pay_e = elastic(clamp01((p - pay) / 0.15))
        d.rectangle([cx - 190, cy - 60, cx + 190, cy + 60], outline=GOLD, width=6)
        if pay_e > 0.3:
            pop_text(d, cx, cy, t_abs, beat_word_t(c5, 1, "paycheck"), "PAYCHECK", GOLD, 34)
            pop_text(d, cx, cy + 90, t_abs, beat_word_t(c5, 1, "paycheck") + 0.06,
                     "$10,000 / MO", GOLD, 26)
        for i in range(4):
            a = clamp01((p - pay - 0.1 - i * 0.18) / 0.2)
            if a > 0:
                xs = cx - 240 + i * 160
                d.rectangle([xs - 60, cy + 180, xs + 60, cy + 240], outline=RED, width=4)
                xmark(d, xs, cy + 210, size=15, color=RED)
        fade_text(d, cx, cy + 310, t_abs, beat_abs(c5, 1, pay + 0.45),
                  "REQUIRED AGAIN NEXT MONTH", RED, 30)

    else:
        # to maintain their lifestyle
        maint = beat_word_p(c5, 2, "maintain")
        life = beat_word_p(c5, 2, "lifestyle")
        own = ease(clamp01((p - maint) / 0.6))
        d.rectangle([cx - 190, cy - 40, cx + 190, cy + 80], outline=GOLD, width=6)
        fade_text(d, cx, cy + 20, t_abs, beat_abs(c5, 2, 0), "PAYCHECK", GOLD, 32)
        if own > 0.1:
            sw_ = math.sin(t_abs * 3)
            d.line([cx, cy + 80, cx + sw_ * 16, cy + 270], fill=GRAY, width=6)
            d.ellipse([cx - 120 + sw_ * 14, cy + 270, cx + 120 + sw_ * 14, cy + 490],
                      outline=RED, width=8)
        pop_text(d, cx + 170, cy + 380, t_abs, beat_word_t(c5, 2, "lifestyle"), "LIFESTYLE", RED, 28)
        if p > life:
            glow_circle(d, cx, cy + 380, 220, RED, layers=1, alpha=0.2)
        fade_text(d, cx, cy - 130, t_abs, beat_abs(c5, 2, maint + 0.05),
                  "MUST KEEP WORKING", RED, 44)
        fade_text(d, cx, cy + 560, t_abs, beat_abs(c5, 2, life + 0.1),
                  "IT'S NOT FREE. IT'S OWNED.", GRAY, 28)


# ============================================================ scene: clip 6

def draw_clip6(d, t_abs):
    idx, p = local_beat(CLIPS[5], t_abs)
    cx, cy = W // 2, H // 2 + 90
    c6 = CLIPS[5]

    if idx == 0:
        # stopped calling income wealth
        fade_text(d, cx, cy - 130, t_abs, beat_abs(c6, 0, 0), "INCOME", GOLD, 68)
        fade_text(d, cx, cy - 10, t_abs, beat_abs(c6, 0, 0), "=", WHITE, 48)
        fade_text(d, cx, cy + 100, t_abs, beat_abs(c6, 0, 0), "WEALTH", GOLD, 68)
        wealth = beat_word_p(c6, 0, "wealth")
        sxm = elastic(clamp01((p - wealth) / 0.15))
        if sxm > 0.1:
            sz = 175 * sxm
            d.line([cx - sz, cy - 60 - sz, cx + sz, cy + 60 + sz], fill=RED, width=14)
            d.line([cx - sz, cy + 60 + sz, cx + sz, cy - 60 - sz], fill=RED, width=14)
        fade_text(d, cx, cy + 290, t_abs, beat_abs(c6, 0, wealth + 0.15),
                  "STOP CALLING IT THAT", RED, 36)

    elif idx == 1:
        # income tells you how much money comes in
        pop = spring(p, k=10)
        d.rectangle([cx + 110, cy + 30, cx + 300, cy + 250], outline=GOLD, width=6)
        inn = beat_word_p(c6, 1, "in")
        pop_text(d, cx + 205, cy + 130, t_abs, beat_word_t(c6, 1, "in"), "IN", GOLD, 44)
        nx = int(pop * 12)
        for i in range(min(12, nx)):
            coin(d, cx - 120 + i * 18, cy + 250 - i * 20, r=11, color=GOLD, rot=t_abs * 2 + i)
        arrow(d, cx - 190, cy + 260, cx + 40, cy + 190, color=GOLD, lw=7)
        fade_text(d, cx - 190, cy + 330, t_abs, beat_abs(c6, 1, 0), "MONEY COMES IN", GOLD, 30)
        fade_text(d, cx - 170, cy - 270, t_abs, beat_abs(c6, 1, 0), "INCOME", WHITE, 46)
        comes = beat_word_p(c6, 1, "comes")
        fade_text(d, cx - 170, cy - 190, t_abs, beat_word_t(c6, 1, "comes"),
                  "= WHAT COMES IN", GRAY, 30)

    else:
        # wealth keeps working when you stop
        stop = beat_word_p(c6, 2, "stop")
        pop_text(d, cx, cy - 280, t_abs, beat_word_t(c6, 2, "stop"), "YOU STOP", RED, 44)
        if p > stop:
            xmark(d, cx + 230, cy - 230, size=40, color=RED)
        gr = spring(p, k=9)
        r0 = 90 + gr * 190
        glow_circle(d, cx + 40, cy + 120, r0, GOLD, layers=2, alpha=0.4)
        d.ellipse([cx + 40 - r0, cy + 120 - r0, cx + 40 + r0, cy + 120 + r0],
                  outline=GOLD, width=8) if gr > 0.2 else None
        for i in range(8):
            ang = i * 0.785 + t_abs * 2.2
            rx = cx + 40 + math.cos(ang) * r0
            ry = cy + 120 + math.sin(ang) * r0 * 0.9
            coin(d, rx, ry, r=11, color=GOLD, rot=t_abs + i)
        fade_text(d, cx + 40, cy + 120, t_abs, beat_abs(c6, 2, 0), "WEALTH", GOLD, 40)
        fade_text(d, cx + 40, cy + 330, t_abs, beat_abs(c6, 2, 0),
                  "KEEPS WORKING WHEN YOU STOP", GRAY, 27)
        if stop > 0 and p > stop:
            bs = elastic(clamp01((p - stop) / 0.25))
            big_text(d, cx + 40, cy - 390, "A DIFFERENT GAME", px=int(40 + 10 * bs), color=GOLD)



# ============================================================ render pipeline

def render_frame(clip_id, t_abs):
    img = Image.new("RGB", (RW, RH), BLACK)
    raw = ImageDraw.Draw(img)
    d = D2(raw)

    # base atmosphere
    for x in range(0, W, 88):
        d.line([x, 0, x, H], fill=BG_LINE, width=1)
    for y in range(0, H, 88):
        d.line([0, y, W, y], fill=BG_LINE, width=1)
    d.line([0, H - 90, W, H - 90], fill=DIM, width=2)

    if clip_id == 1:
        draw_clip1(d, t_abs)
    elif clip_id == 2:
        draw_clip2(d, t_abs)
    elif clip_id == 3:
        draw_clip3(d, t_abs)
    elif clip_id == 4:
        draw_clip4(d, t_abs)
    elif clip_id == 5:
        draw_clip5(d, t_abs)
    elif clip_id == 6:
        draw_clip6(d, t_abs)

    # supersample downscale for crisp AA + bloom glow
    final = img.resize((W, H), Image.LANCZOS)
    return bloom(final)


def render_clip(clip):
    cid = clip["id"]
    dirpath = FRAMES_DIR / f"clip{cid}"
    if dirpath.exists():
        import shutil
        shutil.rmtree(dirpath)
    dirpath.mkdir(parents=True, exist_ok=True)

    audio_path = AUDIO_DIR / f"clip{cid}.mp3"
    audio_dur = get_audio_duration(audio_path)
    pad_before = PAD_BEFORE.get(cid, 0.45)
    total = max(1, int((audio_dur + pad_before + PAD_AFTER) * FPS))
    clip["total_frames"] = total

    for f in range(total):
        t_abs = f / FPS
        img = render_frame(cid, t_abs)
        img.save(dirpath / f"frame_{f:04d}.png")


def create_intro_clip():
    dirpath = FRAMES_DIR / "intro"
    if dirpath.exists():
        import shutil
        shutil.rmtree(dirpath)
    dirpath.mkdir(parents=True, exist_ok=True)
    total = 2 * FPS
    for f in range(total):
        t = f / FPS
        img = Image.new("RGB", (RW, RH), BLACK)
        raw = ImageDraw.Draw(img)
        d = D2(raw)
        for x in range(0, W, 88):
            d.line([x, 0, x, H], fill=BG_LINE, width=1)
        for y in range(0, H, 88):
            d.line([0, y, W, y], fill=BG_LINE, width=1)
        cx = W // 2
        iy = H // 2 - 40

        # flash: immediate bright pulse that fades fast
        flash = max(0.0, 1.0 - t * 4.0)
        if flash > 0.05:
            glow_circle(d, cx, iy + 200, 600, GOLD, alpha=flash * 0.7)

        # LEFT: INCOME — coins flow right into a gate, then stop
        a1 = ease(clamp01(t / 1.0))
        gx = cx - 230
        d.rectangle([gx - 60, iy - 140, gx + 60, iy + 60], outline=GOLD, width=6)
        if a1 > 0.2:
            nx = int(a1 * 9)
            for i in range(min(9, nx)):
                px = gx - 240 + i * 38 + (nx - i) * 8 * (1 - a1)
                coin(d, px, iy - 40, r=12, color=GOLD, rot=t * 2 + i)
            arrow(d, gx - 300, iy - 40, gx - 30, iy - 40, color=GOLD, lw=7)
        fade_text(d, gx, iy + 140, t, 0.55, "INCOME", GOLD, 34)
        fade_text(d, gx, iy + 195, t, 0.7, "GOES IN", GRAY, 24)

        # RIGHT: WEALTH — cycle ring forms, coins orbit
        a2 = ease(clamp01((t - 0.25) / 0.9))
        rx = cx + 230
        r0 = 50 + a2 * 120
        glow_circle(d, rx, iy - 40, r0 + 30, GOLD, layers=2, alpha=0.35)
        d.ellipse([rx - r0, iy - 40 - r0, rx + r0, iy - 40 + r0], outline=GOLD, width=7) if a2 > 0.15 else None
        for i in range(7):
            ang = i * 0.9 + t * 2.6
            coin(d, rx + math.cos(ang) * r0, iy - 40 + math.sin(ang) * r0 * 0.85, r=11,
                 color=GOLD, rot=t + i) if a2 > 0.2 else None
        fade_text(d, rx, iy + 140, t, 0.925, "WEALTH", GOLD, 34)
        fade_text(d, rx, iy + 195, t, 1.06, "KEEPS WORKING", GRAY, 24)

        # center: VS divider
        if t > 0.45:
            dv = ease(clamp01((t - 0.45) / 0.4))
            big_text(d, cx, iy - 20, "VS", px=54, color=_mix_col(BLACK, WHITE, dv))

        # title pops late
        if t > 1.05:
            ta = elastic(clamp01((t - 1.05) / 0.5))
            big_text(d, cx, iy + 300, "INCOME VS WEALTH", px=50,
                     color=(min(255, int(255 * ta)), min(255, int(220 * ta)), min(255, int(60 * ta))))
        bloom(img.resize((W, H), Image.LANCZOS)).save(dirpath / f"frame_{f:04d}.png")


def create_outro_clip():
    dirpath = FRAMES_DIR / "outro"
    if dirpath.exists():
        import shutil
        shutil.rmtree(dirpath)
    dirpath.mkdir(parents=True, exist_ok=True)
    total = 2 * FPS
    for f in range(total):
        t = f / FPS
        img = Image.new("RGB", (RW, RH), BLACK)
        raw = ImageDraw.Draw(img)
        d = D2(raw)
        for x in range(0, W, 88):
            d.line([x, 0, x, H], fill=BG_LINE, width=1)
        for y in range(0, H, 88):
            d.line([0, y, W, y], fill=BG_LINE, width=1)
        cx, cy = W // 2, H // 2 + 90
        gr = spring(clamp01(t / 0.6), k=9)
        r0 = 60 + gr * 240
        glow_circle(d, cx, cy, r0 + 40, GOLD, layers=2, alpha=0.4)
        d.ellipse([cx - r0, cy - r0, cx + r0, cy + r0], outline=GOLD, width=9) if gr > 0.2 else None
        for i in range(9):
            ang = i * 0.7 + t * 2.4
            coin(d, cx + math.cos(ang) * r0, cy + math.sin(ang) * r0 * 0.85, r=12,
                 color=GOLD, rot=t + i) if gr > 0.3 else None
        txt_a = elastic(clamp01(t / 0.55))
        fade_out = 1 - ease_out(clamp01((t - 1.5) / 0.5))
        txt_a *= fade_out
        big_text(d, cx, cy + 80, "WEALTH IS A", px=40, color=WHITE) if txt_a > 0.1 else None
        big_text(d, cx, cy + 160, "DIFFERENT GAME", px=48, color=GOLD) if txt_a > 0.4 else None
        bloom(img.resize((W, H), Image.LANCZOS)).save(dirpath / f"frame_{f:04d}.png")


def sfx_events(clip):
    """Return list of (time_in_clip, sfx_name, gain) for a clip's beats."""
    cid = clip["id"]
    beats = clip_beats(clip)
    evs = []
    if not beats:
        return evs
    b0, b1, b2 = beats[0], beats[1] if len(beats) > 1 else beats[0], beats[2] if len(beats) > 2 else beats[1]
    mid = lambda a, e: (a + e) / 2

    if cid == 1:
        evs += [(b0[0], "whoosh", 0.55), (mid(*b0), "whoosh", 0.45)]
        evs += [(b1[0] - 0.05, "tick", 0.55), (b1[0] + 0.2, "tick", 0.5), (b1[0] + 0.45, "tick", 0.5)]
        evs += [(b2[0], "stamp", 0.55), (b2[0] + 0.25, "crumble", 0.45)]
    elif cid == 2:
        evs += [(b0[0], "whoosh", 0.45), (b0[1] - 0.12, "ding", 0.5)]
        evs += [(b1[0], "pop", 0.5), (mid(*b1), "clink", 0.6)]
        evs += [(b2[0], "rise", 0.5), (b2[0] + 0.4, "clink", 0.55), (b2[1] - 0.2, "chime", 0.7)]
    elif cid == 3:
        evs += [(b0[0], "rise", 0.5), (b0[1] - 0.3, "shimmer", 0.5)]
        evs += [(b1[0], "pop", 0.45), (b1[0] + 0.3, "ding", 0.5)]
        evs += [(b2[0], "tick", 0.45), (b2[0] + 0.35, "tick", 0.45), (b2[0] + 0.65, "stamp", 0.55)]
    elif cid == 4:
        evs += [(b0[0], "rise", 0.5), (b0[1] - 0.3, "chime", 0.6)]
        span = max(0.01, b1[1] - b1[0])
        for k in range(3):
            evs.append((b1[0] + span * k / 3, "slam", 0.4))
        evs += [(b2[0], "pop", 0.5), (mid(*b2), "pop", 0.45), (b2[1] - 0.2, "ding", 0.5)]
    elif cid == 5:
        evs += [(b0[0], "pop", 0.5), (mid(*b0), "pop", 0.45), (b0[1] - 0.15, "clink", 0.6)]
        evs += [(b1[0], "crumble", 0.45), (mid(*b1), "tick", 0.4)]
        evs += [(b2[0], "slam", 0.5), (b2[0] + 0.3, "shimmer", 0.5), (b2[1] - 0.15, "whoosh", 0.4)]
    elif cid == 6:
        evs += [(b0[0], "whoosh", 0.45), (b0[1] - 0.2, "crumble", 0.45)]
        evs += [(b1[0], "tick", 0.4), (mid(*b1), "crumble", 0.45)]
        evs += [(b2[0], "rise", 0.6)]
        for k in range(6):
            evs.append((b2[0] + 0.15 + 0.12 * k, "clink", 0.5))
    # flush times inside clip bounds
    tot_dur = 20.0
    evs = [(max(0.0, t), n, g) for t, n, g in evs]
    return evs


_NVENC_OK = None


def video_codec_args():
    """Video encoder args: the GPU (NVENC) when it works on this machine, else
    libx264 on the CPU. Set STICKMAN_ENCODER=cpu to force the CPU encoder."""
    global _NVENC_OK
    import os
    if _NVENC_OK is None:
        _NVENC_OK = False
        if os.environ.get("STICKMAN_ENCODER", "gpu").lower() != "cpu":
            r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                                f"color=c=black:s={W}x{H}:d=0.2:r=24", "-c:v", "h264_nvenc",
                                "-f", "null", "-"], capture_output=True)
            _NVENC_OK = r.returncode == 0
    if _NVENC_OK:
        return ["-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq", "-rc", "vbr", "-cq", os.environ.get("STICKMAN_CQ", "25"),
                "-b:v", "0", "-spatial-aq", "1", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p"]


def build_mixed_audio(name):
    wav = AUDIO_DIR / f"{name}_mixed.wav"
    if name == "intro":
        if INTRO_HOOK_ID:
            hook_path = AUDIO_DIR / f"clip{INTRO_HOOK_ID}.mp3"
            narr = sfx_gen.decode_mp3(hook_path)
            hook_dur = get_audio_duration(hook_path)   # real (trimmed) file duration, not the JSON word-end time
            dur = hook_dur + INTRO_PAD_BEFORE + INTRO_PAD_AFTER
            offset = INTRO_PAD_BEFORE
            evs = [(offset + 0.02, "whoosh", 0.6), (max(offset + 0.02, dur - 0.45), "chime", 0.45)]
        else:
            narr, dur, offset = None, 2.0, 0.0
            evs = [(0.02, "whoosh", 0.8), (0.35, "shimmer", 0.55), (0.7, "chime", 0.5)]
        bed = sfx_gen.pad_bed(dur, key=MUSIC_BED) if MUSIC_BED else None
        sfx_gen.make_track(dur, evs, narr, offset, wav, sfx_gain=0.55, bed=bed, bed_gain=0.16)
    elif name == "outro":
        bed = sfx_gen.pad_bed(2.0, key=MUSIC_BED) if MUSIC_BED else None
        sfx_gen.make_track(2.0, [(0.25, "shimmer", 0.5), (0.6, "chime", 0.5)], None, 0.0, wav, sfx_gain=0.5, bed=bed, bed_gain=0.16)
    else:
        cid = int(name[4:])
        clip = CLIPS[cid - 1]
        dur = clip["total_frames"] / FPS
        narr = sfx_gen.decode_mp3(AUDIO_DIR / f"clip{cid}.mp3")
        evs = sfx_events(clip)
        bed = sfx_gen.pad_bed(dur, key=MUSIC_BED, seed=cid) if MUSIC_BED else None
        sfx_gen.make_track(dur, evs, narr, PAD_BEFORE.get(cid, 0.45), wav, sfx_gain=0.45, bed=bed, bed_gain=0.16)
    return wav


def compile_video():
    print("\nCompiling video with ffmpeg...")
    all_clips = []
    entries = [("intro", None)]
    for c in CLIPS:
        entries.append((f"clip{c['id']}", None))
    entries.append(("outro", None))

    for name, _ in entries:
        clip_video = OUTPUT_DIR / f"{name}.mp4"
        print(f"  Mixing + encoding {name}...")
        audio_path = build_mixed_audio(name)
        if name in ("intro", "outro"):
            frame_pattern = str(FRAMES_DIR / name / "frame_%04d.png")
        else:
            frame_pattern = str(FRAMES_DIR / name / "frame_%04d.png")
        cmd = ["ffmpeg", "-y", "-framerate", str(FPS),
               "-i", frame_pattern,
               "-i", str(audio_path),
               *video_codec_args(),
               "-c:a", "aac", "-b:a", "192k", str(clip_video)]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0:
            print(r.stderr.decode()[-2000:])
        all_clips.append(clip_video)

    with open(OUTPUT_DIR / "concat.txt", "w") as fh:
        for cv in all_clips:
            fh.write(f"file '{cv.name}'\n")

    print("  Concatenating all clips...")
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    final = OUTPUT_DIR / f"{VIDEO_TITLE}_{stamp}.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(OUTPUT_DIR / "concat.txt"), "-c", "copy", str(final)],
                   capture_output=True)
    print(f"\nVideo saved to: {final}")
    return final


async def gen_all_audio():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    TIMING_DIR.mkdir(parents=True, exist_ok=True)
    for clip in CLIPS:
        cid = clip["id"]
        ap = AUDIO_DIR / f"clip{cid}.mp3"
        tp = TIMING_DIR / f"clip{cid}.json"
        if ap.exists() and tp.exists():
            try:
                with open(tp) as fh:
                    data = json.load(fh)
                cached_narr = data.get("narration")
                cached_voice = data.get("voice")
            except Exception:
                cached_narr = cached_voice = None
            if cached_narr == clip["narration"] and cached_voice == VOICE:
                print(f"  clip{cid} audio+timing cached")
                continue
            # stale cache from another story -> regenerate
            for stale in (ap, tp):
                if stale.exists():
                    stale.unlink()
        print(f"  Synthesizing clip{cid}: {clip['name']}")
        await gen_audio_and_timing(clip)


async def main():
    print("=" * 60)
    print("Stickman Video Generator v5 - No Figure + SFX")
    print("=" * 60)

    print("\n[1/3] Generating narration + word timing...")
    await gen_all_audio()

    print("\n[2/3] Rendering frames (2x supersampled)...")
    create_intro_clip()
    for clip in CLIPS:
        print(f"  clip{clip['id']}: {clip['name']}")
        render_clip(clip)
    create_outro_clip()

    print("\n[3/3] Sound effects + encoding final video...")
    sfx_gen.ensure_sfx()
    final = compile_video()

    total = sum(len(list((FRAMES_DIR / f"clip{c['id']}").glob('*.png'))) for c in CLIPS) \
            + len(list((FRAMES_DIR / "intro").glob('*.png'))) + len(list((FRAMES_DIR / "outro").glob('*.png')))
    print("=" * 60)
    print(f"DONE! {total} frames -> output/{final.name}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

