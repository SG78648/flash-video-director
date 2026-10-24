"""style_docu.py - the Docu style: a gritty finance-documentary montage, in the spirit of The Big Short.

Why it exists. Bright accent colours and sticker icons (the Pulse experiment) read as a cheap hustle bar, and the black-and-white anime look of the
Noir experiment was the wrong world. A finance film like The Big Short is cut like a documentary that cannot sit still: grainy handheld footage, a
cut every second or two, text that pops up on the picture, stock tickers, newspaper headlines, spreadsheets, a red stamp, a freeze on a number. That is
premium without being polished, and it keeps a cold audience watching.
  - EVERY beat sits on B-ROLL (broll.py, real footage cropped to 9:16) with two shots per beat, graded like 2000s film stock (muted colour, lifted
    blacks, warm highlights, cool shadows), a handheld wobble, a vignette, film grain and a slight flicker;
  - white Arial Black captions, three words at a time, the spoken word in terminal amber (the colour of a Bloomberg screen);
  - a news chyron keeps the stake of the video on screen (THE DEAL and the amount) and a ticker tape of the numbers in the script scrolls under the
    picture, red for what hurts and green for what pays;
  - a bad beat gets a newspaper clipping with a headline, a red flash and a record-scratch; a decision gets a red stamp (PASSED, APPROVED);
  - amounts are slammed in as big numerals with an amber rule, maths runs on a calculator, rent arrives as phone notifications;
  - the hook is on screen at frame 1 over the footage.
It draws any script_story with the same planner and scenes as the other styles (story_scenes.py) and gives the studio the same interface:
OUT_DIR, segments(), frame_bytes(), prepare(), apply_to().
"""
import json
import math
import os
import re
import sys

import numpy as np

import projects
import studio_config

if "FLASH_ASPECT" not in os.environ:     # command line: follow the app's saved format
    studio_config.ensure_aspect_env()

import broll
import generate_video as g
import script_story
import story_icons
import story_scenes
import streaming
import voice
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFont, ImageOps

STYLE_ID = "docu"
OUT_DIR = projects.style_dir(STYLE_ID)
VIDEO_TITLE = "docu"
HOOK_ID = "hook"
HOOK_TEXT = ""
QA_MAX_DUR = 100
SS = g.SS
FPS = g.FPS

CLIPS, NARR_BEATS, PAD_BEFORE = [], {}, {}
layout_problems = lambda: []           # the layout is computed from measured text, so there is nothing to collide

DEMO_SCRIPT = """You're not broke. You're leaking.
You get a raise? New car. You get a bonus? New vacation.
You start making six figures? Suddenly, you need a six figure lifestyle.
And then you have the audacity to say, I just need to make more money.
No. You need to stop turning every increase in income into an increase in expenses.
Because here's the uncomfortable truth. Your lifestyle is eating the future you keep saying you want.
You want financial freedom? But you spend every dollar trying to look like you've already achieved it.
You want to retire early? But you haven't bought a single asset that can pay you when you stop working.
Start asking how to turn the money you make into something that pays you back.
Because looking rich is easy. Building wealth is the part most people never get around to."""

# ------------------------------------------------------------------ palette (ink, white, terminal amber, red and green only for money)
INK = (9, 9, 11)
BONE = (246, 246, 242)
ASH = (150, 150, 150)
CARD = (24, 24, 28)
ACCENT = (255, 176, 0)             # terminal amber
RED = (222, 58, 50)
GREEN = (62, 190, 112)
USE_BROLL = True
GRAIN = 0.55
CAPTION_SCALE = 1.0
KINETIC = True
PUNCH = 0.06
DRIFT = 0.04
SHAKE = 0.006
FLASH = 0.10


def mix(c, bg, a):
    a = max(0.0, min(1.0, a))
    return tuple(int(bg[i] + (c[i] - bg[i]) * a) for i in range(3))


def clamp01(v):
    return max(0.0, min(1.0, v))


def ease(v):
    v = clamp01(v)
    return v * v * (3 - 2 * v)


def ease_out(v):
    v = clamp01(v)
    return 1 - (1 - v) ** 3


def spring(v, k=13.0):
    return g.spring(v, k)


def apply_config(cfg=None):
    """Studio settings -> the Docu look."""
    global ACCENT, USE_BROLL, GRAIN, CAPTION_SCALE, KINETIC, PUNCH, DRIFT, SHAKE, FLASH
    cfg = studio_config.normalize(cfg) if cfg else studio_config.load()
    n = cfg["docu"]
    ACCENT = studio_config.rgb(n["palette"]["accent"])
    USE_BROLL = bool(n["layout"]["broll"])
    GRAIN = float(n["look"]["grain"])
    CAPTION_SCALE = float(n["layout"]["caption_size"])
    KINETIC = bool(n["layout"]["kinetic_caption"])
    PUNCH = float(n["camera"]["punch"])
    DRIFT = float(n["camera"]["drift"])
    SHAKE = float(n["camera"]["shake"])
    FLASH = float(n["camera"]["flash"])
    _CACHE.clear()
    _PLAN.clear()


# ------------------------------------------------------------------ the page
PORTRAIT = g.ASPECT == "9:16"
LANDSCAPE = g.ASPECT == "16:9"
VW, VH = {"9:16": (g.W, g.H), "1:1": (860, 860), "16:9": (1529, 860)}[g.ASPECT]       # 1:1 and 16:9 lay out on a compact page
VRW, VRH = VW * SS, VH * SS


def safe_on():
    return PORTRAIT and story_scenes.safe_area()


def vis_box():
    """(x0, y0, x1, y1) of the area graphics may use."""
    if PORTRAIT:
        if safe_on():                                          # above the like / comment column (it starts about y 1000) the picture may use the full width
            return 70, 290, VW - 70, 1030
        return 60, 240, VW - 60, 1160
    if LANDSCAPE:
        return 80, 50, VW - 80, int(VH * 0.66)
    return 50, 40, VW - 50, int(VH * 0.62)


def caption_geometry():
    """(centre x, centre y, max width, base px)."""
    if PORTRAIT:
        x0, x1 = (story_scenes.SAFE_LEFT, VW - story_scenes.SAFE_RIGHT) if safe_on() else (60, VW - 60)
        return (x0 + x1) / 2, 1285 if safe_on() else 1340, x1 - x0 + 30, 104
    if LANDSCAPE:
        return VW / 2, VH * 0.84, VW - 160, 72
    return VW / 2, VH * 0.80, VW - 100, 66


# ------------------------------------------------------------------ text
_FONTS = {}


def font(px):
    px = max(8, int(round(px)))
    if px not in _FONTS:
        f = None
        for name in ("ariblk.ttf", "arialbd.ttf"):
            try:
                f = ImageFont.truetype(name, px * SS)
                break
            except Exception:
                pass
        _FONTS[px] = f or ImageFont.load_default()
    return _FONTS[px]


_SERIF = {}


def serif(px):
    px = max(8, int(round(px)))
    if px not in _SERIF:
        f = None
        for name in ("timesbd.ttf", "georgiab.ttf"):
            try:
                f = ImageFont.truetype(name, px * SS)
                break
            except Exception:
                pass
        _SERIF[px] = f or ImageFont.load_default()
    return _SERIF[px]


_SANS = {}


def sans(px):
    px = max(8, int(round(px)))
    if px not in _SANS:
        f = None
        for name in ("segoeuib.ttf", "arialbd.ttf"):
            try:
                f = ImageFont.truetype(name, px * SS)
                break
            except Exception:
                pass
        _SANS[px] = f or ImageFont.load_default()
    return _SANS[px]


_SCRATCH = None


def width(s, f):
    global _SCRATCH
    if _SCRATCH is None:
        _SCRATCH = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    return _SCRATCH.textlength(s, font=f) / SS


def put(img, x, y, s, px, fill, anchor="mm", stroke=True, stroke_fill=INK, f=None):
    d = ImageDraw.Draw(img)
    sw = int(round(px * 0.06 * SS)) if stroke else 0
    d.text((x * SS, y * SS), s, fill=fill, font=f or font(px), anchor=anchor, stroke_width=sw, stroke_fill=stroke_fill)


def wrap(text, f, maxw):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if cur and width(t, f) > maxw:
            lines.append(cur)
            cur = w
        else:
            cur = t
    return lines + ([cur] if cur else [])


def fit_lines(text, maxw, px_max, px_min, max_lines):
    px = px_max
    while True:
        lines = wrap(text, font(px), maxw)
        if len(lines) <= max_lines or px <= px_min:
            return lines, px
        px -= 2


def fit_px(text, maxw, cap, floor=18):
    """The largest scene text size (at most `cap`) at which `text` is no wider than `maxw` scene units in the heavy font."""
    px = cap
    while px > floor:
        if width(text.upper(), font(px * 1.22 * 1.08)) <= maxw:
            return px
        px -= 3
    return floor


# ------------------------------------------------------------------ the story
_STORY = None


def story():
    global _STORY
    if _STORY is None:
        _STORY = script_story.load(projects.active()) or script_story.build(DEMO_SCRIPT)
    return _STORY


_WORDS = {}


def beat_words(c, bi):
    """[(word, clip time)] of the words spoken inside beat `bi` (the same window the beat sync uses)."""
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


def t_word(c, bi, k):
    ws = beat_words(c, bi)
    if ws:
        return ws[max(0, min(len(ws) - 1, int(k)))][1]
    bs, be = g.clip_beats(c)[bi]
    return bs + (be - bs) * min(0.95, 0.1 + 0.8 * k / 12.0)


def nwords(s):
    return len([w for w in s.split() if re.sub(r"[^A-Za-z0-9]", "", w)])


# ------------------------------------------------------------------ the look: footage, grade, vignette, grain
_CACHE = {}


def scrim():
    """One multiply layer for the whole picture: a dark vignette, a darker top (for the stake tag) and a dark foot (for the caption)."""
    key = ("scrim", VRW, VRH)
    if key not in _CACHE:
        w, h = 270, int(270 * VRH / VRW)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        nx, ny = (xx / w - 0.5) * 2, (yy / h - 0.5) * 2
        vig = 1.0 - 0.38 * np.clip((nx ** 2 + ny ** 2) / 1.5, 0, 1)
        foot = 1.0 - 0.66 * np.clip((yy / h - 0.52) / 0.48, 0, 1) ** 1.3
        top = 1.0 - 0.45 * np.clip(1 - (yy / h) / 0.18, 0, 1)
        m = np.clip(vig * foot * top, 0, 1)
        arr = np.stack([m, m, m], axis=-1) * 255
        _CACHE[key] = Image.fromarray(arr.astype(np.uint8), "RGB").resize((VRW, VRH), Image.BICUBIC)
    return _CACHE[key]


def grain_tile(i):
    key = ("grain", i % 3, VRW, VRH)
    if key not in _CACHE:
        rng = np.random.default_rng(100 + i % 3)
        n = (rng.random((VRH // 2, VRW // 2)) * 255).astype(np.uint8)
        _CACHE[key] = Image.fromarray(n, "L").resize((VRW, VRH), Image.NEAREST)
    return _CACHE[key]


def add_grain(img, frame_no):
    if GRAIN <= 0.01:
        return img
    n = grain_tile(frame_no)
    n = n.point(lambda v: int((v - 128) * 0.16 * GRAIN) + 128)             # a small signed noise around mid grey
    n3 = Image.merge("RGB", (n, n, n))
    return ImageChops.add(img, n3, 1.0, -128)


_GRADE = {}


def grade(fr):
    """2000s film stock: muted colour, lifted blacks, warm highlights, cool shadows, a gentle S curve."""
    if "luts" not in _GRADE:
        def lut(black, white, gamma):
            out = []
            for i in range(256):
                x = i / 255.0
                y = 0.5 + 0.5 * math.tanh(1.5 * (x - 0.5)) / math.tanh(0.75)
                y = max(0.0, min(1.0, y)) ** gamma
                out.append(int(black + (white - black) * y))
            return out
        _GRADE["luts"] = (lut(15, 252, 0.97), lut(17, 244, 1.0), lut(22, 232, 1.04))
    fr = ImageEnhance.Color(fr).enhance(0.68)
    r, g_, b = fr.split()
    lr, lg, lb = _GRADE["luts"]
    return Image.merge("RGB", (r.point(lr), g_.point(lg), b.point(lb)))


def ink_page(t=0.0):
    """No footage: a clean dark page, a soft vertical gradient and one slow pool of warm light drifting across it."""
    key = ("ink", VRW, VRH)
    if key not in _CACHE:
        w, h = 120, int(120 * VRH / VRW)
        yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
        base = np.zeros((h, w, 3), dtype=np.float32)
        for i, (top, bot) in enumerate(((20, 8), (20, 8), (24, 11))):
            base[..., i] = top + (bot - top) * yy
        _CACHE[key] = base
    base = _CACHE[key].copy()
    h, w = base.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx = w * (0.5 + 0.30 * math.sin(t * 0.35))
    cy = h * (0.45 + 0.18 * math.cos(t * 0.27))
    d2 = ((xx - cx) / (w * 0.55)) ** 2 + ((yy - cy) / (h * 0.30)) ** 2
    glow = np.clip(1 - d2, 0, 1) ** 2 * 0.55
    base[..., 0] += glow * 60
    base[..., 1] += glow * 42
    base[..., 2] += glow * 14
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB").resize((VRW, VRH), Image.BICUBIC)


MOVES = ("push", "pull", "panl", "panr")


def hand(t, amp=1.0):
    """A handheld wobble: smooth sideways and up and down drift, in fractions of the picture."""
    return (0.0042 * amp * (math.sin(t * 7.3) + 0.6 * math.sin(t * 13.1 + 1.7)), 0.0030 * amp * (math.sin(t * 6.1 + 0.4) + 0.5 * math.sin(t * 11.7)))


def camera_crop(base, move, u, shake=0.0, shake_y=0.0):
    """The graded 540 x 960 frame framed for the page: a slow push, pull or pan over a shot (u runs 0..1)."""
    bw, bh = base.size
    z = {"push": 1.04 + 0.16 * u, "pull": 1.20 - 0.16 * u, "panl": 1.14, "panr": 1.14}[move]
    ar = VRW / VRH
    cw = bw / z
    ch = cw / ar
    if ch > bh / z:
        ch = bh / z
        cw = ch * ar
    cx = bw / 2 + {"panl": (0.5 - u) * bw * 0.06, "panr": (u - 0.5) * bw * 0.06}.get(move, 0.0) + shake * bw
    cy = bh / 2 + shake_y * bh
    x0 = max(0, min(bw - cw, cx - cw / 2))
    y0 = max(0, min(bh - ch, cy - ch / 2))
    return base.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((VRW, VRH), Image.BILINEAR)


# ------------------------------------------------------------------ scenes (story_scenes primitives, restrained)
class DocuBE(story_scenes.Backend):
    """The scenes are the same as in the other styles. Here colours are flipped for a dark page (ink is bone white, the fill of a card is a dark
    card, white is the light text that sits on a crimson fill), icons become thin medallions and every element pops in with a spring."""

    def __init__(self, img, t, ox, oy, k, s0=None, first=None):
        super().__init__(t, ox, oy, k)
        self.img, self.s0, self.first = img, s0, first
        self.d = g.D2(ImageDraw.Draw(img))
        self.char_w = 22
        self.pal = {"ink": BONE, "accent": ACCENT, "mute": ASH, "neg": ACCENT, "soft": CARD, "white": BONE}

    def color(self, name):
        return self.pal.get(name, name)

    def _tr(self, trig):
        """A cut lands on a picture, not on an empty page: the elements of the beat come a little ahead of the words."""
        if self.s0 is not None and self.first is not None:
            shift = min(1.0, max(0.0, self.first - self.s0 - 0.08))
            trig = max(self.s0 + 0.08, trig - shift)
        return super()._tr(trig)

    def _medallion(self, spec, cx, cy, s, a):
        """A black disc with a thin bone ring, the icon drawn on it in bone with crimson details."""
        L = int(s * 1.5)
        layer = Image.new("RGBA", (L * SS, L * SS), (0, 0, 0, 0))
        d = g.D2(ImageDraw.Draw(layer))
        c = L / 2
        R = s * 0.60
        d.ellipse([c - R, c - R, c + R, c + R], fill=INK + (235,), outline=BONE + (255,), width=max(3.0, s * 0.022))
        isz = s * 0.74
        w = max(5.0, isz / 15.0)
        for ck, pts in spec:
            pp = [(c - isz / 2 + px * isz / 100.0, c - isz / 2 + py * isz / 100.0) for px, py in pts]
            col = (BONE if ck == "i" else ACCENT) + (255,)
            d.line(pp, fill=col, width=w, joint="curve")
            for q in (pp[0], pp[-1]):
                d.ellipse([q[0] - w / 2, q[1] - w / 2, q[0] + w / 2, q[1] + w / 2], fill=col)
        self.img.paste(layer, (int((cx - L / 2) * SS), int((cy - L / 2) * SS)), layer)

    def _strokes(self, spec, x, y, size, trig, dur, lw, color, accent, until, key, claim_w=1.0, claim=True):
        trig = self._tr(trig)
        if self.t < trig or (until is not None and self.t >= until):
            return
        a = clamp01((self.t - trig) / 0.30)
        sc = spring(a, 12.0) if a < 1 else 1.0
        cx, cy = self.P(x, y)
        cy += 4.0 * self.k * math.sin(self.t * 2.4 + x * 0.013)         # a faint float
        dev = size * self.k
        if dev >= 190:
            self._medallion(spec, cx, cy, dev * max(0.05, sc), a)
            return
        s = dev * max(0.04, sc)
        ox, oy = cx - s / 2, cy - s / 2
        w = max(4.0, dev / 15.0 * max(0.4, sc))
        for ck, pts in spec:
            self._line([(ox + px * s / 100.0, oy + py * s / 100.0) for px, py in pts], self.color(color if ck == "i" else accent), w)

    def _line(self, pts, color, w):
        self.d.line(pts, fill=color, width=w, joint="curve")
        for p in (pts[0], pts[-1]):
            self.d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=color)

    def _rect(self, x0, y0, x1, y1, fill, line, w, r):
        self.d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill, outline=line, width=max(2, int(round(w * 1.1))))

    def _ellipse(self, cx, cy, r, fill, line, w):
        if r > 0.5:
            self.d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline=line, width=max(2, int(round(w * 1.1))))

    def _text(self, s, x, y, px, color, anchor, trig, dur, key):
        a = clamp01((self.t - trig) / max(0.12, dur))
        if a <= 0.02:
            return
        sc = 0.78 + 0.22 * spring(a, 12.0) if a < 1 else 1.0
        px = max(16, int(round(px * 1.08 * sc)))
        s = s.upper()
        light = sum(color) > 330
        put(self.img, x, y + 0.03 * px, s, px, mix(color, INK, min(1.0, a * 2.2)), "mm" if anchor == "m" else "lm", stroke=light)

    def _claim(self, key, box):
        pass

    def photo_path(self, node, sp):
        return None                                        # footage and drawings, never stock photos


class _Extent(story_scenes.Backend):
    """Draws a scene to nothing and records the box it covers, so the graphic can be scaled to fill the screen."""

    def __init__(self, k=1.0):
        super().__init__(99.0, 0.0, 0.0, k)
        self.pts = []
        self.trigs = []
        self.char_w = 22

    def color(self, name):
        return name

    def _tr(self, trig):
        self.trigs.append(trig)
        return trig

    def _strokes(self, spec, x, y, size, trig, dur, lw, color, accent, until, key, claim_w=1.0, claim=True):
        self._tr(trig)
        cx, cy = self.P(x, y)
        s = size * self.k
        self.pts += [(cx - s / 2, cy - s / 2), (cx + s / 2, cy + s / 2)]

    def _line(self, pts, color, w):
        self.pts += list(pts)

    def _rect(self, x0, y0, x1, y1, fill, line, w, r):
        self.pts += [(x0, y0), (x1, y1)]

    def _ellipse(self, cx, cy, r, fill, line, w):
        self.pts += [(cx - r, cy - r), (cx + r, cy + r)]

    def _text(self, s, x, y, px, color, anchor, trig, dur, key):
        px = max(16, int(round(px * 1.08)))
        w = width(s.upper(), font(px))                           # the real width of the face
        self.pts += [(x - (w / 2 if anchor == "m" else 0), y - px / 2), (x + (w / 2 if anchor == "m" else w), y + px / 2)]

    def _claim(self, key, box):
        pass

    def reserve(self, x0, y0, x1, y1):
        self.pts += [(x0, y0), (x1, y1)]

    def photo_path(self, node, sp):
        return None


# ------------------------------------------------------------------ Docu's own scene drawers
def p_stage(be, ctx, sp):
    """The things a beat names, ONE at a time. An amount is slammed in as a big numeral with an amber rule drawn under it. A thing is only named in big
    type when there is no footage under the beat (with footage the picture and the caption already say it)."""
    nodes = sp["nodes"][:4]
    be.reserve(120, 150, 880, 600)
    trigs = [ctx.at(nd.get("word"), 0.2 + 0.28 * i) for i, nd in enumerate(nodes)]
    cur = 0
    for i, tr in enumerate(trigs):
        if be.t >= tr:
            cur = i
    nd, tr = nodes[cur], trigs[cur]
    label = (nd.get("label") or "").rstrip(".")
    if re.match(r"^[$\d]", label):
        px = fit_px(label, 800, 250)
        be.text(label, 500, 330, px, tr, color="ink")
        be.line([(150, 330 + px * 0.78), (850, 330 + px * 0.78)], tr + be.lag(0.12), color="accent", w=10, dur=0.35)
    elif label and not getattr(be, "has_footage", True):
        px = fit_px(label, 800, 230)
        be.text(label, 500, 330, px, tr, color="ink")
        be.line([(150, 330 + px * 0.78), (850, 330 + px * 0.78)], tr + be.lag(0.12), color="accent", w=10, dur=0.35)


# --- the calculator -----------------------------------------------------------
_OPS = {"×": "×", "÷": "÷", "−": "−", "-": "−", "+": "+"}


def calc_keys(row):
    """The key presses of one working, e.g. '$450 × 20 lots' -> ['4','5','0','×','2','0','=']. Words after the numbers are ignored."""
    toks = re.findall(r"(\d+(?:\.\d+)?%?|[×÷+−-])", row["left"].replace("$", "").replace(",", ""))
    keys = []
    for tk in toks:
        if tk[-1:] == "%":
            keys += list(tk[:-1]) + ["%"]
        elif tk[0].isdigit():
            keys += list(tk)
        else:
            keys.append(_OPS[tk])
    return keys + ["="]


def calc_times(ctx, rows):
    """[(row, keys, [press times], t_answer)] for every row of a sum (the same schedule feeds the picture and the key click sounds)."""
    out = []
    n = len(rows)
    for i, r in enumerate(rows):
        vtok = re.sub(r"[^A-Za-z0-9]", "", r["value"].split()[0]) if r["value"] else ""
        tv = story_scenes.spoken_amount_time(ctx, r["value"])
        if tv is None:
            tv = ctx.at(vtok, min(0.6, 0.25 + 0.35 * (i + 1) / n) if vtok else 0.45)
        tl = max(ctx.t0 + 0.08, tv - 0.9)
        if tv - tl < 0.45:
            tv = tl + 0.45
        keys = calc_keys(r)
        dt = min(0.17, max(0.05, (tv - 0.1 - tl) / len(keys)))
        times = [tl + j * dt for j in range(len(keys))]
        times[-1] = max(times[-1], tv - 0.07)
        out.append((r, keys, times, tv))
    return out


def fmt_typed(keys, upto):
    """What the display shows after `upto` presses: digits grouped by thousands, operators spaced."""
    s, num = "", ""
    for k in keys[:upto]:
        if k.isdigit() or k == ".":
            num += k
        else:
            if num:
                s += (f"{int(num):,}" if num.isdigit() else num)
                num = ""
            if k != "=":
                s += " " + k + " "
    if num:
        s += f"{int(num):,}" if num.isdigit() else num
    return s.strip()


_LAYOUT = [["AC", "±", "%", "÷"], ["7", "8", "9", "×"], ["4", "5", "6", "−"], ["1", "2", "3", "+"], ["0", ".", "="]]


def p_calc(be, ctx, sp):
    """A monochrome calculator. The keys light up as the sum is typed, the answer lands on the display when it is spoken."""
    rows = sp["rows"][:3]
    sched = calc_times(ctx, rows)
    be.reserve(100, 10, 900, 680)
    tl0 = sched[0][2][0]
    be.rect(100, 10, 900, 680, tl0 - 0.25, fill=(8, 8, 10), line=(96, 96, 104), w=4, r=34, dur=0.30)
    cur = 0
    for i, (r, keys, times, tv) in enumerate(sched):
        if be.t >= times[0] - 0.05:
            cur = i
    r, keys, times, tv = sched[cur]
    pressed = sum(1 for tt in times if be.t >= tt)
    if be.t >= tv:                                           # the answer, big, with a crimson rule under it
        val = r["value"].upper()
        px = fit_px(val, 700, 130)
        be.text(val, 500, 112, px, tv, color="ink")
        be.line([(150, 112 + px * 0.74), (850, 112 + px * 0.74)], tv + be.lag(0.08), color="accent", w=7, dur=0.3)
        if r["unit"]:
            be.text(r["unit"], 500, 238, 36, tv + be.lag(0.12), color="mute")
    else:                                                    # what has been typed so far
        typed = fmt_typed(keys, pressed) or "0"
        be.text(typed, 500, 120, fit_px(typed, 700, 112), times[0] - 0.2, color="ink")
    cx = [230, 410, 590, 770]
    cy = [292, 370, 448, 526, 604]
    now = {keys[j] for j, tt in enumerate(times) if tt <= be.t < tt + 0.16}
    for ri, row in enumerate(_LAYOUT):
        for ci, lab in enumerate(row):
            wide = lab == "0"
            x = ((cx[0] + cx[1]) / 2 if wide else cx[ci + 1]) if ri == 4 else cx[ci]
            op = lab in ("÷", "×", "−", "+", "=")
            fn = lab in ("AC", "±", "%")
            hit = lab in now
            fill = (236, 120, 128) if (op and hit) else ACCENT if op else (150, 150, 156) if (fn and hit) else (92, 92, 98) if fn else (96, 96, 102) if hit else (36, 36, 42)
            half = 170 if wide else 80
            be.rect(x - half, cy[ri] - 32, x + half, cy[ri] + 32, tl0 - 0.2, fill=fill, line=None, r=14, dur=0.25)
            if be.t >= tl0 - 0.1:
                col = BONE if not (fn and not hit) else INK
                lx = x - 120 if wide else x
                px_, py_ = be.P(lx, cy[ri])
                put(be.img, px_, py_, lab, max(18, int(38 * be.k)), col, "mm", stroke=False, f=sans(max(18, int(38 * be.k))))


def p_notifs(be, ctx, sp):
    """Rent coming in (or a raise going out) as a stack of phone notifications that slide in one after the other, with a running total on top."""
    n = max(2, min(20, int(sp["n"])))
    tag = sp["tag"]
    plus = tag.startswith("+")
    amt = int(re.sub(r"[^0-9]", "", tag) or 0)
    be.reserve(70, 10, 930, 745)
    tt = ctx.at(sp.get("tag_word"), 0.25)
    ts = min(0.14, max(0.05, (ctx.t1 - 0.3 - tt) / n))
    appeared = [k for k in range(n) if be.t >= tt + k * ts]
    m = len(appeared)
    total = m * amt
    be.text("PER MONTH" if plus else "RENT THIS MONTH", 500, 55, 36, tt - 0.2, color="mute")
    be.text(("+" if plus else "") + f"${total:,}", 500, 140, fit_px(f"${total:,}+", 760, 170), tt - 0.1, color="ink")
    for k in appeared[-5:]:
        slot = m - 1 - k
        y0 = 235 + slot * 100
        trig = tt + k * ts
        fill = mix(BONE, (18, 18, 22), slot * 0.17)
        be.rect(70, y0, 930, y0 + 88, trig, fill=fill, line=None, r=22, dur=0.18)
        be.rect(92, y0 + 18, 144, y0 + 70, trig + be.lag(0.03), fill=INK, line=None, r=12, dur=0.15)
        be.text("$", 118, y0 + 44, 34, trig + be.lag(0.05), color=BONE)
        be.text("RAISE APPROVED" if plus else "RENT RECEIVED", 168, y0 + 28, 24, trig + be.lag(0.06), anchor="l", color=(70, 70, 78))
        be.text(f"UNIT {k + 1} " + ("+" if plus else "PAID ") + f"${amt}", 168, y0 + 62, 31, trig + be.lag(0.08), anchor="l", color=INK)
        be.text("NOW", 880, y0 + 30, 22, trig + be.lag(0.1), color=(110, 110, 120))


def p_steps(be, ctx, sp):
    """A short list of ticked (or crossed) lines, each one big, appearing at its own word."""
    nodes = sp["nodes"][:5]
    n = len(nodes)
    be.reserve(60, 40, 940, 720)
    rh = min(230, 660 // n)
    cross = sp.get("mark") == "cross"
    for i, nd in enumerate(nodes):
        tr = ctx.item(nd["k"]) if "k" in nd else ctx.at(None, 0.2 + 0.2 * i)
        y0 = 50 + i * (rh + 14)
        cy = y0 + rh / 2
        be.rect(60, y0, 940, y0 + rh, tr, fill=(10, 10, 13), line=(96, 96, 104), w=3, r=18)
        be.circle(140, cy, rh * 0.28, tr, fill="accent", line=None)
        if cross:
            be.cross(140, cy, rh * 0.11, tr + be.lag(0.05), color="white")
        elif sp.get("mark") == "check":
            be.check(140, cy, rh * 0.11, tr + be.lag(0.05), color="white")
        else:
            be.text(str(i + 1), 140, cy, rh * 0.28, tr + be.lag(0.05), color="white")
        label = nd["label"]
        lines = story_scenes._wrap(label, 22)[:2]
        px = fit_px(max(lines, key=len), 640, min(72, rh * 0.50 / (1.0 if len(lines) == 1 else 1.5)))
        for j, ln in enumerate(lines):
            be.text(ln, 235, cy + (j - (len(lines) - 1) / 2) * (px * 1.3), px, tr + be.lag(0.08), anchor="l", color="ink")


def p_send(be, ctx, sp):
    """Share it: a phone, an arrow, the person, and who they are."""
    be.reserve(80, 80, 920, 700)
    t = ctx.at("send", 0.1)
    be.icon("phone", 220, 230, 300, t)
    be.arrow((380, 230), (600, 230), t + be.lag(0.3), color="accent", w=10)
    be.icon("person", 790, 230, 300, t + be.lag(0.5))
    for j, ln in enumerate(story_scenes._wrap(sp["label"], 16)[:3]):
        be.text(ln, 500, 480 + j * 90, fit_px(ln, 800, 80), t + be.lag(0.7), color="ink")


def p_keyword(be, ctx, sp):
    """The keyword offer: the comment box with the word big, an arrow, the message."""
    be.reserve(60, 60, 940, 720)
    t0 = ctx.at("comment", 0.08)
    be.rect(70, 60, 930, 340, t0, fill=(10, 10, 13), line="accent", w=5, r=30)
    tw = ctx.at(sp["word"].split()[-1].lower(), 0.25)
    be.text(sp["word"], 500, 200, fit_px(sp["word"], 780, 190), tw, color="ink")
    ta = ctx.at("send", 0.55)
    be.arrow((500, 380), (500, 480), ta, color="accent", w=10)
    be.icon("mail", 500, 590, 200, ta + be.lag(0.2))
    be.text(sp["label"], 500, 730, fit_px(sp["label"], 800, 70), ta + be.lag(0.5), color="ink")


NOIR_SCENES = {"calc": p_calc, "send": p_send, "keyword": p_keyword}
# scenes that carry words and numbers need a darker footage behind them
DENSE = ("calc", "stack", "steps", "stat", "cards", "keyword", "send", "hub", "flow")


def draw_scene(be, ctx, sp):
    be.deadline = ctx.t1 - 0.12
    be.earliest = ctx.t0 + 0.06
    typ = sp.get("type")
    if typ in ("objects", "pictogram") and not sp.get("fig") and sp.get("nodes"):
        p_stage(be, ctx, sp)
    elif typ == "count" and sp.get("tag"):
        p_notifs(be, ctx, sp)
    elif typ == "steps" and sp.get("rows"):
        p_steps(be, ctx, sp)
    elif typ in NOIR_SCENES:
        NOIR_SCENES[typ](be, ctx, sp)
    else:
        story_scenes.draw(be, ctx, sp)


def scene_extent(cid, idx):
    c = CLIPS[cid - 1]
    s0, s1 = g.clip_beats(c)[idx]
    be = _Extent()
    try:
        draw_scene(be, story_scenes.Ctx(s0, s1, beat_words(c, idx), lambda kk: t_word(c, idx, kk)), story_scenes.scene_of(story(), cid, idx))
    except Exception:
        be.pts = []
    first = min(be.trigs) if be.trigs else None
    if not be.pts:
        return 0.0, 0.0, 1000.0, 760.0, first
    xs, ys = [q[0] for q in be.pts], [q[1] for q in be.pts]
    return min(xs), min(ys), max(xs), max(ys), first


# ------------------------------------------------------------------ the plan of one beat (measured once, cached): shots, footage, graphic
_PLAN = {}
NEG_TYPES = ("ceiling", "income_stop", "hours")
NEG_WORDS = {"not", "never", "no", "nothing", "can't", "cannot", "don't", "won't", "isn't", "aren't", "lose", "loses", "lost", "stuck", "broke",
             "leaves", "leave", "wrong", "lying", "lie", "bet", "walk", "risk", "mold", "empty", "short", "squeeze", "collapses", "fail", "fails"}
_PHR = {}


def phrases_of(c, idx):
    """The caption phrases of a beat, [[(word, time), ...], ...]: 2 to 3 words each, cut at punctuation and at long words."""
    key = (c["id"], idx, len(beat_words(c, idx)), id(story()))
    if key not in _PHR:
        ws = beat_words(c, idx)
        if not ws:
            f = story()["feats"][str(c["id"])][idx]
            bs, be = g.clip_beats(c)[idx]
            toks = f["text"].split()
            ws = [(w, bs + (be - bs) * 0.9 * i / max(1, len(toks))) for i, w in enumerate(toks)]
        out, cur = [], []
        for w, t in ws:
            cur.append((w, t))
            chars = sum(len(x[0]) for x in cur) + len(cur) - 1
            if len(cur) >= 3 or w[-1:] in ".,?!" or chars >= 17:
                out.append(cur)
                cur = []
        if cur:
            if out and len(cur) == 1 and len(cur[0][0]) <= 4 and len(out[-1]) < 3 and out[-1][-1][0][-1:] not in ".?!":
                out[-1] += cur
            else:
                out.append(cur)
        _PHR[key] = out
    return _PHR[key]


def beat_kind(cid, idx):
    """'neg' for a negative beat (it cuts with an ink flash and the picture shakes), else 'calm'."""
    f = story()["feats"][str(cid)][idx]
    sp = story_scenes.scene_of(story(), cid, idx)
    if bool(f.get("neg")) or sp.get("type") in NEG_TYPES or bool(sp.get("neg")) or bool(sp.get("gone")):
        return "neg"
    return "calm"


def stake_tag():
    """The first amount or percent of the hook, kept on screen as a small tag all through the body."""
    m = re.search(r"\$[\d,.]+(?:\s?(?:million|billion|thousand|k))?|\d[\d,.]*\s?(?:%|percent)", story().get("hook", ""), re.I)
    return m.group(0).upper().replace(" PERCENT", "%") if m else ""


def shots_of(cid, idx):
    """[(t0, t1, clip id or None, move, offset)] of a beat: two shots when it is long enough, each on its own footage."""
    c = CLIPS[cid - 1]
    s0, s1 = g.clip_beats(c)[idx]
    qs = broll.queries_for(story(), cid, idx) if USE_BROLL else []
    clips = [broll.lookup(q, cid * 3 + idx + k) for k, q in enumerate(qs)]
    clips = [x for x in clips if x]
    if not clips:
        return [(s0, s1, None, "push", 0.0)]
    seed = cid * 7 + idx * 3
    if s1 - s0 >= 2.2:
        ph = phrases_of(c, idx)
        tb = ph[1][0][1] if len(ph) > 1 else (s0 + s1) / 2
        tb = max(s0 + 0.9, min(s1 - 0.9, tb))
        a = clips[0]
        b = clips[1] if len(clips) > 1 else clips[0]
        return [(s0, tb, a, MOVES[seed % 4], 0.3 * seed % 2.0), (tb, s1 + 0.4, b, MOVES[(seed + 1) % 4], (0.3 * seed + 1.1) % 2.0)]
    return [(s0, s1 + 0.4, clips[0], MOVES[seed % 4], 0.3 * seed % 2.0)]


def plan_beat(cid, idx):
    key = (cid, idx)
    if key in _PLAN:
        return _PLAN[key]
    x0, y0, x1, y1 = vis_box()
    ex0, ey0, ex1, ey1, first = scene_extent(cid, idx)
    kk = max(0.5, min((x1 - x0) / (ex1 - ex0 + 40.0), (y1 - y0) / (ey1 - ey0 + 40.0), 3.0))
    ox = (x0 + x1) / 2 - kk * (ex0 + ex1) / 2
    oy = (y0 + y1) / 2 - kk * (ey0 + ey1) / 2
    sp = story_scenes.scene_of(story(), cid, idx)
    p = {"scene": (ox, oy, kk), "first": first, "kind": beat_kind(cid, idx), "shots": shots_of(cid, idx), "dense": sp.get("type") in DENSE,
         "box": (int(ox + kk * ex0 - 30), int(oy + kk * ey0 - 30), int(ox + kk * ex1 + 30), int(oy + kk * ey1 + 30))}
    _PLAN[key] = p
    return p


# ------------------------------------------------------------------ drawing
def word_color(w):
    low = re.sub(r"[^a-z']", "", w.lower())
    if low in NEG_WORDS:
        return RED
    return BONE


def draw_caption(img, c, idx, t, s0, big=1.0):
    if not KINETIC:
        return
    ph = phrases_of(c, idx)
    if not ph:
        return
    cur = None
    for p in ph:
        if t >= p[0][1] - 0.03:
            cur = p
    if cur is None:
        if t < s0 + 0.05:
            return
        cur = ph[0]
    cx, cy, maxw, px0 = caption_geometry()
    px0 = px0 * CAPTION_SCALE * big
    t0 = cur[0][1]
    a = clamp01((t - t0) / 0.14)
    pop = 0.88 + 0.12 * spring(a, 13.0) if a < 1 else 1.0
    words = [w for w, _t in cur]
    times = [tt for _w, tt in cur]
    text = " ".join(words).upper()
    px = px0
    while True:                                                    # one line when it fits, else two balanced lines, else smaller
        f = font(px)
        if width(text, f) <= maxw:
            lines = [list(range(len(words)))]
            break
        if len(words) > 1:
            best, split = None, 1
            for sp_ in range(1, len(words)):
                w1 = width(" ".join(words[:sp_]).upper(), f)
                w2 = width(" ".join(words[sp_:]).upper(), f)
                m = max(w1, w2)
                if best is None or m < best:
                    best, split = m, sp_
            if best <= maxw:
                lines = [list(range(split)), list(range(split, len(words)))]
                break
        px -= 4
        if px < 40:
            lines = [list(range(len(words)))]
            break
    lh = px * 1.12
    yy = cy - (len(lines) - 1) * lh / 2
    d = ImageDraw.Draw(img)
    for ln in lines:
        f = font(px)
        sp_w = width(" ", f)
        ws_w = [width(words[i].upper(), f) for i in ln]
        total = sum(ws_w) + sp_w * (len(ln) - 1)
        xx = cx - total / 2
        for j, i in enumerate(ln):
            nxt = times[i + 1] if i + 1 < len(times) else t0 + 9
            active = times[i] - 0.02 <= t < nxt
            col = (RED if word_color(words[i]) == RED else ACCENT) if active else word_color(words[i])
            bump = 1.0 + (0.08 * math.exp(-(t - times[i]) / 0.10) if active else 0.0)      # the spoken word kicks
            wpx = px * pop * bump
            wx, wy = xx + ws_w[j] / 2, yy + (1 - pop) * 20
            put(img, wx, wy, words[i].upper(), wpx, col, "mm")
            xx += ws_w[j] + sp_w
        yy += lh


def draw_quote(img, c, idx, t, s0, f_, p):
    """A quoted belief, big, crossed out when it is the wrong one."""
    x0, y0, x1, y1 = vis_box()
    text = f_["quote"]
    lines, px = fit_lines('"' + text + '"', x1 - x0 - 40, 92 if PORTRAIT else 62, 36, 5)
    lh = px * 1.18
    ws = beat_words(c, idx)
    t_end = (ws[-1][1] + 0.3) if ws else g.clip_beats(c)[idx][1]
    a = ease_out((t - s0) / 0.16)
    if a <= 0.02:
        return
    top = (y0 + y1) / 2 - len(lines) * lh / 2
    for i, ln in enumerate(lines):
        w_total = width(ln, font(px))
        put(img, (x0 + x1) / 2, top + i * lh + lh / 2 + (1 - a) * 18, ln, px, mix(BONE, INK, a), "mm")
        if t > t_end and f_.get("neg"):
            r = ease_out((t - t_end) / 0.22)
            d = ImageDraw.Draw(img)
            xa = (x0 + x1) / 2 - w_total / 2 - 10
            d.line([xa * SS, (top + i * lh + lh / 2) * SS, (xa + (w_total + 20) * r) * SS, (top + i * lh + lh / 2) * SS], fill=ACCENT, width=int(9 * SS))


def draw_stake(img):
    """A news chyron, top left: an amber label block (THE DEAL) and the stake on a dark bar."""
    tag = stake_tag()
    if not tag or not PORTRAIT:
        return
    d = ImageDraw.Draw(img)
    x, y, h = 90, 292, 54
    lab, val = "THE NUMBER", tag
    lw = width(lab, sans(26)) + 34
    vw = width(val, sans(30)) + 40
    d.rectangle([x * SS, y * SS, (x + lw) * SS, (y + h) * SS], fill=ACCENT)
    put(img, x + lw / 2, y + h / 2, lab, 26, INK, "mm", stroke=False, f=sans(26))
    d.rectangle([(x + lw) * SS, y * SS, (x + lw + vw) * SS, (y + h) * SS], fill=(12, 12, 14))
    put(img, x + lw + vw / 2, y + h / 2, val, 30, BONE, "mm", stroke=False, f=sans(30))


STAMPS = ((re.compile(r"\b(walked away|walk away|passed on|i passed|i said no)\b", re.I), "PASSED"),
          (re.compile(r"\b(approved|closed|signed|bought|funded)\b", re.I), "APPROVED"),
          (re.compile(r"\b(denied|declined|rejected)\b", re.I), "DENIED"))


def stamp_of(f):
    for rx, label in STAMPS:
        if rx.search(f["text"]):
            return label
    return ""


def draw_stamp(img, label, t, t0):
    """A red rubber stamp that thumps down: a double border and heavy capitals, tilted."""
    a = clamp01((t - t0) / 0.14)
    if a <= 0.02:
        return
    px = 130
    f = font(px)
    w = width(label, f) + 90
    h = px * 1.45
    L = int(w + 60)
    layer = Image.new("RGBA", (L * SS, int((h + 60) * SS)), (0, 0, 0, 0))
    d = g.D2(ImageDraw.Draw(layer))
    col = RED + (255,)
    d.rectangle([30, 30, 30 + w, 30 + h], outline=col, width=9)
    d.rectangle([44, 44, 16 + w, h + 16], outline=col, width=3)
    ImageDraw.Draw(layer).text(((30 + w / 2) * SS, (30 + h / 2) * SS), label, fill=col, font=f, anchor="mm")
    sc = 1.0 + 0.5 * (1 - ease_out(a))
    layer = layer.resize((int(layer.width * sc), int(layer.height * sc)), Image.BILINEAR).rotate(-11, expand=True, resample=Image.BICUBIC)
    cx, cy = VW / 2, 840
    img.paste(layer, (int(cx * SS - layer.width / 2), int(cy * SS - layer.height / 2)), layer)


def draw_progress(img, cid, t):
    """A thin bone line along the top, the share of the video that has played."""
    try:
        total = sum(n for _nm, n in _SEGS) / FPS if _SEGS else 0
        before = (_setup()[1]) / FPS + sum((CLIPS[i].get("total_frames") or 0) for i in range(cid - 1)) / FPS
        frac = clamp01((before + t) / total) if total else 0
    except Exception:
        return
    y = VH * (0.058 if PORTRAIT else 0.02)
    d = ImageDraw.Draw(img)
    d.rectangle([0, y * SS, VRW, (y + 3) * SS], fill=mix(BONE, INK, 0.16))
    d.rectangle([0, y * SS, VRW * frac, (y + 3) * SS], fill=BONE)


def base_for(cid, idx, t):
    """The picture under everything at time t: the footage of the current shot (graded, framed with a slow move) or plain ink."""
    p = plan_beat(cid, idx)
    shot = next((s for s in p["shots"] if s[0] <= t < s[1]), p["shots"][-1])
    t0, t1, clip, move, off = shot
    if clip is None:
        return ink_page(t), shot
    fr = broll.frame(clip, (t - t0) + off)
    if fr is None:
        return ink_page(t), shot
    u = clamp01((t - t0) / max(0.5, t1 - t0))
    hx, hy = hand(t, 3.2 if p["kind"] == "neg" else 1.0)
    return camera_crop(grade(fr), move, u, hx, hy), shot


def dim(img, box, a):
    x0, y0, x1, y1 = [int(v * 1) for v in box]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(VW, x1), min(VH, y1)
    if x1 <= x0 or y1 <= y0:
        return
    bx = (x0 * SS, y0 * SS, x1 * SS, y1 * SS)
    reg = img.crop(bx)
    img.paste(Image.blend(reg, Image.new("RGB", reg.size, INK), a), bx)


def page_for(cid, idx, t, frame_no=0):
    """The finished picture of one beat at clip time t, before the cut effects and the camera punch."""
    c = CLIPS[cid - 1]
    s0, s1 = g.clip_beats(c)[idx]
    p = plan_beat(cid, idx)
    img, shot = base_for(cid, idx, t)
    has_clip = shot[2] is not None
    img = ImageChops.multiply(img, scrim())
    f_ = story()["feats"][str(cid)][idx]
    sp = story_scenes.scene_of(story(), cid, idx)
    if has_clip:                                              # graphics read better on a quiet picture (the whole picture, evenly, never a visible box)
        dim(img, (0, 0, VW, VH), 0.34 if p["dense"] else 0.10)
    ox, oy, k = p["scene"]
    if f_["kind"] == "quote" and sp.get("type") == "question":
        draw_quote(img, c, idx, t, s0, f_, p)
    else:
        ctx = story_scenes.Ctx(s0, s1, beat_words(c, idx), lambda kk: t_word(c, idx, kk))
        be = DocuBE(img, t, ox, oy, k, s0=s0, first=p["first"])
        be.has_footage = has_clip
        draw_scene(be, ctx, sp)
    label = stamp_of(f_)
    if label and not p["dense"]:                                     # a decision: a red stamp thumps down when the last word is said
        ws = beat_words(c, idx)
        draw_stamp(img, label, t, (ws[-1][1] - 0.4) if ws else s0 + 0.4)
    draw_caption(img, c, idx, t, s0)
    draw_stake(img)
    draw_progress(img, cid, t)
    return img, shot


def render_frame(cid, t, frame_no=0):
    c = CLIPS[cid - 1]
    beats = g.clip_beats(c)
    idx, prog = g.local_beat(c, t)
    if idx > 0 and t < beats[idx][0]:           # the short gap between two beats: hold the one that was on screen
        idx -= 1
        prog = 1.0
    s0 = beats[idx][0]
    p = plan_beat(cid, idx)
    img, shot = page_for(cid, idx, t, frame_no)
    since = t - s0
    cut_since = t - shot[0]                                  # a punch at every shot change, not only at a beat change
    if FLASH > 0.01 and 0 <= cut_since < 0.07 and (idx > 0 or shot[0] > s0 + 0.05):
        img = Image.blend(img, Image.new("RGB", img.size, BONE), FLASH * (1 - cut_since / 0.07))
    flick = 1.0 + 0.03 * math.sin(frame_no * 2.3) * math.sin(frame_no * 0.7)                      # film flicker
    img = ImageEnhance.Brightness(img).enhance(flick)
    img = add_grain(img, frame_no)
    punch = PUNCH * math.exp(-max(0.0, cut_since) / 0.11) if (idx > 0 or shot[0] > s0 + 0.05) else 0.0
    dx = SHAKE * math.sin(since * 95) * math.exp(-max(0.0, since) / 0.16) if p["kind"] == "neg" else 0.0
    scale = 1.0 + punch
    return g.apply_camera(img, scale, dx, 0.0)


# ------------------------------------------------------------------ hook
def intro_setup():
    st = story()
    path = g.TIMING_DIR / f"clip{HOOK_ID}.json"
    words = json.loads(path.read_text(encoding="utf-8"))["words"]
    k = min(len(words) - 1, st["hook_split"])
    cut_local = words[k]["start"] if words else 1.0
    hook_dur = g.get_audio_duration(g.AUDIO_DIR / f"clip{HOOK_ID}.mp3")
    total = hook_dur + g.INTRO_PAD_BEFORE + g.INTRO_PAD_AFTER
    return total, max(1, int(total * FPS)), g.INTRO_PAD_BEFORE + cut_local


def hook_layout():
    st = story()
    x0, y0, x1, y1 = vis_box()
    w = x1 - x0 + (40 if PORTRAIT else 0)
    t1, t2 = st["hook_head"][0].upper(), st["hook_head"][1].upper()
    top = 330 if PORTRAIT else 60
    h_avail = (VH * 0.34 if PORTRAIT else VH * 0.52)
    px = 138 if PORTRAIT else 90
    while True:
        l1, l2 = wrap(t1, font(px), w), wrap(t2, font(px), w)
        if (len(l1) + len(l2)) * px * 1.1 <= h_avail or px <= 46:
            break
        px -= 2
    return {"w": w, "top": top, "px": px, "l1": l1, "l2": l2}


def hook_clip():
    if not USE_BROLL:
        return None
    for q in broll.hook_queries(story()):
        got = broll.lookup(q, 1)
        if got:
            return got
    return None


def intro_frame(f, setup=None):
    total, _n, cut_t = setup or intro_setup()
    st = story()
    t = f / FPS
    L = hook_layout()
    clip = hook_clip()
    fr = broll.frame(clip, 0.4 + t) if clip else None
    if fr is not None:
        hx, hy = hand(t, 1.0)
        img = camera_crop(grade(fr), "push", clamp01(t / max(1.0, total)), hx, hy)
    else:
        img = ink_page(t)
    img = ImageChops.multiply(img, scrim())
    dim(img, (0, 0, VW, VH), 0.34 if fr is not None else 0.0)
    cx = VW / 2
    px, lh = L["px"], L["px"] * 1.1
    yy = L["top"]
    for ln in L["l1"]:                                           # the whole hook is on screen from frame 1
        put(img, cx, yy + lh / 2, ln, px, BONE, "mm")
        yy += lh
    yy += px * 0.12
    d = ImageDraw.Draw(img)
    d.rectangle([(cx - L["w"] * 0.22) * SS, yy * SS, (cx + L["w"] * 0.22) * SS, (yy + max(6, px * 0.05)) * SS], fill=ACCENT)       # a thin crimson rule between the two parts
    yy += px * 0.30
    for ln in L["l2"]:
        put(img, cx, yy + lh / 2, ln, px, ACCENT, "mm")
        yy += lh
    draw_stake(img)
    if t < 0.08:
        img = Image.blend(img, Image.new("RGB", img.size, BONE), 0.5 * (1 - t / 0.08))
    punch = 0.04 * math.exp(-(t - cut_t) / 0.18) if t >= cut_t else 0.0
    img = add_grain(img, f)
    return g.apply_camera(img, 1.0 + 0.05 * ease(t / max(0.5, total)) + punch, 0.0, 0.0)


def outro_frame(f):
    t = f / FPS
    st = story()
    img = ImageChops.multiply(ink_page(t + 7.0), scrim())
    x0, y0, x1, y1 = vis_box()
    cx = VW / 2
    lines = [l.upper() for l in st["outro"]["lines"]]
    w = x1 - x0 + 30
    px = 112 if PORTRAIT else 72
    while True:
        ls = [wrap(l, font(px), w) for l in lines]
        if sum(len(x) for x in ls) * px * 1.12 <= (y1 - y0) * 0.55 or px <= 44:
            break
        px -= 2
    flat = [(ln, i) for i, part in enumerate(ls) for ln in part]
    total_h = 300 + 60 + len(flat) * px * 1.12
    top = y0 + max(0, (y1 - y0 - total_h) / 2)
    be = DocuBE(img, t, cx - 500, top + 150 - 400, 1.0)
    be.icon(st["outro"]["icon"], 500, 400, 330, 0.0, dur=0.4)
    yy = top + 330
    d = ImageDraw.Draw(img)
    for j, (ln, part) in enumerate(flat):
        a = ease_out((t - 0.35 - 0.12 * j) / 0.2)
        last = j == len(flat) - 1
        if a > 0.02:
            put(img, cx, yy + px * 0.56 + (1 - a) * 16, ln, px, mix(ACCENT if last else BONE, INK, a), "mm")
            if last:
                d.rectangle([(cx - width(ln, font(px)) / 2) * SS, (yy + px * 1.14) * SS, (cx + width(ln, font(px)) / 2) * SS, (yy + px * 1.14 + 6) * SS], fill=ACCENT)
        yy += px * 1.12
    img = add_grain(img, f)
    return g.apply_camera(img, 1.0 + 0.02 * ease(t / 2.0), 0.0, 0.0)


# ------------------------------------------------------------------ sound cues
INTRO_SFX = []           # no chime at the end of the hook, no shimmer on the close: the studio reads these two lists for its program
OUTRO_SFX = []


def sfx_events(clip):
    """Sound is rare and soft: a low thud when an amount lands, a tick when a calculator answer lands, a stamp when a decision is stamped. Nothing on
    cuts, no key clicks, no whooshes, no jingles."""
    cid = clip["id"]
    beats = g.clip_beats(clip)
    evs = []
    if not beats:
        return evs
    st = story()
    for bi, f in enumerate(st["feats"][str(cid)]):
        s0 = beats[bi][0]
        sp = story_scenes.scene_of(st, cid, bi)
        ctx = story_scenes.Ctx(s0, beats[bi][1], beat_words(clip, bi), lambda kk, _c=clip, _b=bi: t_word(_c, _b, kk))
        p = plan_beat(cid, bi)
        if sp.get("type") == "calc":
            for r, keys, times, tv in calc_times(ctx, sp["rows"][:3]):
                evs.append((tv, "thud", 0.40))
        elif sp.get("type") == "stat":
            for nd in sp["nodes"][:2]:
                evs.append((ctx.at(nd["word"], 0.2), "thud", 0.36))
        elif sp.get("type") in ("objects", "pictogram") and sp.get("nodes") and not p["dense"]:
            for nd in sp["nodes"][:4]:
                if re.match(r"^[$\d]", (nd.get("label") or "")):
                    evs.append((ctx.at(nd.get("word"), 0.2), "thud", 0.36))
        lab = stamp_of(f)
        if lab and not p["dense"]:
            ws = beat_words(clip, bi)
            evs.append(((ws[-1][1] - 0.4) if ws else s0 + 0.4, "stamp", 0.40))
    return [(max(0.0, t), n, g_) for t, n, g_ in evs]


def mixed_audio(name):
    """The same mix as the other styles (narration plus the effects of sfx_events), without the jingles: no whoosh and chime on the hook, no shimmer
    on the close, no ambient pad."""
    import sfx_gen
    wav = g.AUDIO_DIR / f"{name}_mixed.wav"
    if name == "intro":
        hook_path = g.AUDIO_DIR / f"clip{g.INTRO_HOOK_ID}.mp3"
        narr = sfx_gen.decode_mp3(hook_path)
        dur = g.get_audio_duration(hook_path) + g.INTRO_PAD_BEFORE + g.INTRO_PAD_AFTER
        sfx_gen.make_track(dur, INTRO_SFX, narr, g.INTRO_PAD_BEFORE, wav, sfx_gain=0.45, bed=None, bed_gain=0.0)
    elif name == "outro":
        sfx_gen.make_track(2.0, OUTRO_SFX, None, 0.0, wav, sfx_gain=0.45, bed=None, bed_gain=0.0)
    else:
        cid = int(name[4:])
        clip = g.CLIPS[cid - 1]
        dur = clip["total_frames"] / g.FPS
        narr = sfx_gen.decode_mp3(g.AUDIO_DIR / f"clip{cid}.mp3")
        sfx_gen.make_track(dur, sfx_events(clip), narr, g.PAD_BEFORE.get(cid, 0.45), wav, sfx_gain=0.45, bed=None, bed_gain=0.0)
    return wav


# ------------------------------------------------------------------ the interface every style gives the studio
_SETUP = None
_SEGS = []


def apply_to(gm):
    global OUT_DIR, _STORY, HOOK_TEXT, _SETUP
    OUT_DIR = projects.style_dir(STYLE_ID)
    _STORY = None
    _SETUP = None
    _WORDS.clear()
    _PLAN.clear()
    _PHR.clear()
    _SEGS.clear()
    st = story()
    CLIPS[:] = st["clips"]
    NARR_BEATS.clear()
    NARR_BEATS.update({int(k): v for k, v in st["beats"].items()})
    PAD_BEFORE.clear()
    PAD_BEFORE.update({i: 0.35 for i in range(1, len(st["clips"]) + 1)})
    HOOK_TEXT = st["hook"]
    gm.VIDEO_TITLE = VIDEO_TITLE
    gm.CLIPS = CLIPS
    gm.NARR_BEATS = NARR_BEATS
    gm.PAD_BEFORE = PAD_BEFORE
    gm.PAD_AFTER = 0.12
    gm.INTRO_PAD_AFTER = 0.12
    gm.QA_MAX_DUR = QA_MAX_DUR
    gm.MUSIC_BED = None
    gm.INTRO_HOOK_ID = HOOK_ID
    gm.OUTPUT_DIR = OUT_DIR
    gm.FRAMES_DIR = OUT_DIR / "frames"
    gm.AUDIO_DIR = OUT_DIR / "audio"
    gm.TIMING_DIR = OUT_DIR / "timing"
    gm.VIDEO_DIR = OUT_DIR / "video"
    gm.STREAM_FRAMES = True
    gm.compile_video = _compile
    gm._TIMING_CACHE.clear()
    gm._WORD_P_CACHE.clear()
    gm._CAM_EVENTS_CACHE.clear()
    gm.sfx_events = sfx_events
    gm.build_mixed_audio = mixed_audio
    apply_config()


def seed_audio():
    pass                                    # narration comes from the voice settings (and the shared cache), never from a demo copy


async def prepare():
    """Make sure narration + word timing exist in this style's folder, with the silence between sentences cut short (every beat must keep moving)."""
    for d in (g.OUTPUT_DIR, g.AUDIO_DIR, g.TIMING_DIR, g.VIDEO_DIR):
        d.mkdir(parents=True, exist_ok=True)
    await voice.ensure_audio(g, CLIPS, HOOK_ID, HOOK_TEXT)
    import tighten
    tighten.apply(g.AUDIO_DIR, g.TIMING_DIR, [c["id"] for c in CLIPS] + [HOOK_ID], True)


def _setup():
    global _SETUP
    if _SETUP is None:
        _SETUP = intro_setup()
    return _SETUP


def segments():
    out = [("intro", _setup()[1])]
    for c in CLIPS:
        dur = g.get_audio_duration(g.AUDIO_DIR / f"clip{c['id']}.mp3")
        n = max(1, int((dur + g.PAD_BEFORE.get(c["id"], 0.45) + g.PAD_AFTER) * FPS))
        c["total_frames"] = n
        out.append((f"clip{c['id']}", n))
    out.append(("outro", int(1.6 * FPS)))
    _SEGS[:] = out
    return out


def frame(seg, f):
    """PIL image of frame f of a segment."""
    if seg == "intro":
        return intro_frame(f, _setup())
    if seg == "outro":
        return outro_frame(f)
    return render_frame(int(seg[4:]), f / FPS, f)


def frame_bytes(seg, f):
    return frame(seg, f).tobytes()


def _compile():
    return streaming.compile_segments(sys.modules[__name__])
