"""style_desk.py - the Desk style: a faceless motion-graphics reel where drawn objects do what a presenter's face does.

Why it exists. A talking-head reel holds attention because a person is always on screen and every graphic is a literal picture of the words being
said (say "no CapCut" and the CapCut icon appears crossed out). Lee has no on-camera footage, so the objects have to be the performer.
  - one stable stage, deep green with a slow pool of warm light, so the eye always has somewhere to return to;
  - each sentence gets the drawn object it names (a loan term sheet with a rate that climbs, a calendar with the closing date ringed, a rent roll
    with the gap to market, a grid of units filling up, a listing card, a text thread, a stamped document, a balance counting up),
    dropped on the stage as a sheet of paper with a shadow, a spring and a small tilt;
  - a sentence nothing can picture becomes kinetic type: heavy sans for the first part, italic serif in gold for the last, a word at a time;
  - captions are small serif lines on dark glass, the spoken word in gold;
  - sound is almost absent: a thud when an amount lands, a stamp when a decision is stamped.
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

import generate_video as g
import broll
import brand_profile as profile
import script_story
import story_icons
import story_scenes
import streaming
import voice
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

STYLE_ID = "desk"
OUT_DIR = projects.style_dir(STYLE_ID)
VIDEO_TITLE = "desk"
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
INK = (238, 236, 225)               # the stage (Lee's paper) - also the colour things fade into
BONE = (42, 27, 19)                 # text on the stage (Lee's ink)
ASH = (150, 140, 126)
CARD = (252, 250, 245)
ACCENT = (246, 97, 27)              # Lee's orange
RED = (206, 52, 38)
GREEN = (109, 195, 148)
LIGHT = (252, 250, 245)             # light text on a dark or orange fill
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
    """Studio settings -> the Desk look."""
    global ACCENT, USE_BROLL, GRAIN, CAPTION_SCALE, KINETIC, DRIFT
    cfg = studio_config.normalize(cfg) if cfg else studio_config.load()
    n = cfg["desk"]
    ACCENT = studio_config.rgb(n["palette"]["accent"])
    USE_BROLL = False
    GRAIN = float(n["look"]["grain"])
    CAPTION_SCALE = float(n["layout"]["caption_size"])
    KINETIC = bool(n["layout"]["kinetic_caption"])
    DRIFT = float(n["camera"]["drift"])
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
        for name in ("seguisb.ttf", "SourceSansPro-Semibold.ttf", "arialbd.ttf"):
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
        for name in ("palab.ttf", "georgiab.ttf"):
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
        for name in ("seguisb.ttf", "arialbd.ttf"):
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
    f = f or font(px)
    if stroke and sum(fill) < 420:
        shadow_text(img, x, y, s, f, px, anchor=anchor)
    ImageDraw.Draw(img).text((x * SS, y * SS), s, fill=fill, font=f, anchor=anchor)


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














# ------------------------------------------------------------------ scenes (story_scenes primitives, restrained)
class DocuBE(story_scenes.Backend):
    """The scenes are the same as in the other styles. Here colours are flipped for a dark page (ink is bone white, the fill of a card is a dark
    card, white is the light text that sits on a crimson fill), icons become thin medallions and every element pops in with a spring."""

    def __init__(self, img, t, ox, oy, k, s0=None, first=None):
        super().__init__(t, ox, oy, k)
        self.img, self.s0, self.first = img, s0, first
        self.d = g.D2(ImageDraw.Draw(img))
        self.char_w = 22
        self.pal = {"ink": BONE, "accent": ACCENT, "mute": ASH, "neg": ACCENT, "soft": CARD, "white": LIGHT}

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
        put(self.img, x, y + 0.03 * px, s, px, mix(color, INK, min(1.0, a * 2.2)), "mm" if anchor == "m" else "lm", stroke=True)

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


# ------------------------------------------------------------------ scene drawers kept from the Docu style (re-coloured by the palette)


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
    be.reserve(100, 10, 900, 600)
    tl0 = sched[0][2][0]
    be.rect(100, 10, 900, 600, tl0 - 0.25, fill=DEEP, line=(96, 76, 62), w=4, r=34, dur=0.30)
    cur = 0
    for i, (r, keys, times, tv) in enumerate(sched):
        if be.t >= times[0] - 0.05:
            cur = i
    r, keys, times, tv = sched[cur]
    pressed = sum(1 for tt in times if be.t >= tt)
    if be.t >= tv:                                           # the answer, big, with a crimson rule under it
        val = r["value"].upper()
        px = fit_px(val, 700, 130)
        be.text(val, 500, 112, px, tv, color=LIGHT)
        be.line([(150, 112 + px * 0.74), (850, 112 + px * 0.74)], tv + be.lag(0.08), color="accent", w=7, dur=0.3)
        if r["unit"]:
            be.text(r["unit"], 500, 196, 36, tv + be.lag(0.12), color=(196, 182, 166))
    else:                                                    # what has been typed so far
        typed = fmt_typed(keys, pressed) or "0"
        be.text(typed, 500, 120, fit_px(typed, 700, 112), times[0] - 0.2, color=LIGHT)
    cx = [200, 380, 560, 740]
    cy = [262, 340, 418, 496, 574]
    now = {keys[j] for j, tt in enumerate(times) if tt <= be.t < tt + 0.16}
    for ri, row in enumerate(_LAYOUT):
        for ci, lab in enumerate(row):
            wide = lab == "0"
            x = ((cx[0] + cx[1]) / 2 if wide else cx[ci + 1]) if ri == 4 else cx[ci]
            op = lab in ("÷", "×", "−", "+", "=")
            fn = lab in ("AC", "±", "%")
            hit = lab in now
            fill = (255, 156, 112) if (op and hit) else ACCENT if op else (150, 128, 112) if (fn and hit) else (92, 72, 58) if fn else (116, 92, 76) if hit else (76, 58, 46)
            half = 134 if wide else 80
            be.rect(x - half, cy[ri] - 32, x + half, cy[ri] + 32, tl0 - 0.2, fill=fill, line=None, r=14, dur=0.25)
            if be.t >= tl0 - 0.1:
                col = LIGHT
                lx = x - 100 if wide else x
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
        fill = mix(CARD, INK, slot * 0.30)
        be.rect(70, y0, 930, y0 + 88, trig, fill=fill, line=(221, 214, 201), w=2, r=22, dur=0.18)
        be.rect(92, y0 + 18, 144, y0 + 70, trig + be.lag(0.03), fill=BONE, line=None, r=12, dur=0.15)
        be.text("$", 118, y0 + 44, 34, trig + be.lag(0.05), color=LIGHT)
        be.text("RAISE APPROVED" if plus else "RENT RECEIVED", 168, y0 + 28, 24, trig + be.lag(0.06), anchor="l", color=ASH)
        be.text(f"UNIT {k + 1} " + ("+" if plus else "PAID ") + f"${amt}", 168, y0 + 62, 31, trig + be.lag(0.08), anchor="l", color=BONE)
        be.text("NOW", 880, y0 + 30, 22, trig + be.lag(0.1), color=ASH)


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
        be.rect(60, y0, 940, y0 + rh, tr, fill=CARD, line=(221, 214, 201), w=3, r=18)
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






# scenes that carry words and numbers need a darker footage behind them






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
        toks0 = story()["feats"][str(c["id"])][idx]["text"].split()
        if ws and len(toks0) == len(ws):
            ws = [(tk, w[1]) for tk, w in zip(toks0, ws)]
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








# ------------------------------------------------------------------ drawing








STAMPS = ((re.compile(r"\b(walked away|walk away|passed on|i passed|i said no)\b", re.I), "PASSED"),
          (re.compile(r"\b(approved|closed|signed|bought|funded)\b", re.I), "APPROVED"),
          (re.compile(r"\b(denied|declined|rejected)\b", re.I), "DENIED"))


def stamp_of(f):
    for rx, label in STAMPS:
        if rx.search(f["text"]):
            return label
    return ""














# ------------------------------------------------------------------ hook










# ------------------------------------------------------------------ sound cues




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


# ------------------------------------------------------------------ Desk look: fonts, paper, the stage
PAPER = (252, 250, 245)
PAPER2 = (240, 236, 226)
TXT = (42, 27, 19)
MUTED = (150, 140, 126)
LINE = (225, 219, 208)
DEEP = (66, 48, 38)

FONTS = {"heavy": ("seguisb.ttf", "SourceSansPro-Semibold.ttf", "arialbd.ttf"), "ital": ("palai.ttf", "georgiai.ttf"), "serif": ("pala.ttf", "georgia.ttf"),
         "serifb": ("palab.ttf", "georgiab.ttf"), "sans": ("seguisb.ttf", "arialbd.ttf"), "sansr": ("segoeui.ttf", "arial.ttf")}
_FC = {}


def F(name, px):
    px = max(8, int(round(px)))
    k = (name, px)
    if k not in _FC:
        f = None
        for fn in FONTS[name]:
            try:
                f = ImageFont.truetype(fn, px * SS)
                break
            except Exception:
                pass
        _FC[k] = f or ImageFont.load_default()
    return _FC[k]


def stage(t=0.0):
    """Lee's paper (flat cream, a dotted grid, a very soft vignette). It does not move, so the cards are what the eye follows."""
    key = ("stage", VRW, VRH)
    if key not in _CACHE:
        arr = np.zeros((VRH, VRW, 3), dtype=np.float32)
        arr[...] = INK
        step = 54 * SS
        dot = (221, 219, 208)
        for y in range(step // 2, VRH, step):
            for x in range(step // 2, VRW, step):
                arr[y - SS:y + SS, x - SS:x + SS] = dot
        yy, xx = np.mgrid[0:VRH:8, 0:VRW:8].astype(np.float32)
        nx, ny = (xx / VRW - 0.5) * 2, (yy / VRH - 0.5) * 2
        v = 1.0 - 0.05 * np.clip((nx ** 2 + ny ** 2) / 1.6, 0, 1)
        v = np.asarray(Image.fromarray((v * 255).astype(np.uint8), "L").resize((VRW, VRH), Image.BICUBIC)).astype(np.float32) / 255.0
        arr *= v[..., None]
        _CACHE[key] = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    return _CACHE[key].copy()


def shadow_text(img, x, y, s, f, px, anchor="mm", strength=1.0):
    """A soft, low shadow under dark text on the paper (a broad blur plus a tight contact shadow), so type sits on the page instead of being printed flat."""
    if strength <= 0.03 or not s.strip():
        return
    l, t0, r, b = [int(v) for v in f.getbbox(s, anchor=anchor)]
    blur = max(2, int(px * 0.05 * SS))
    pad = blur * 3 + int(px * 0.08 * SS)
    w, h = r - l + 2 * pad, b - t0 + 2 * pad
    lay = Image.new("L", (w, h), 0)
    ImageDraw.Draw(lay).text((pad - l, pad - t0), s, font=f, fill=255, anchor=anchor)
    broad = lay.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * 0.30 * strength))
    tight = lay.filter(ImageFilter.GaussianBlur(max(1, blur // 4))).point(lambda v: int(v * 0.16 * strength))
    col = Image.new("RGB", (w, h), (58, 38, 24))
    ox = int(x * SS) + l - pad
    oy = int(y * SS) + t0 - pad
    img.paste(col, (ox, oy + int(px * 0.055 * SS)), broad)
    img.paste(col, (ox, oy + max(1, int(px * 0.012 * SS))), tight)


# ------------------------------------------------------------------ paper cards
PAD = 70


class Card:
    """A sheet of paper drawn in its own coordinates (1x units), later placed on the stage with a shadow, a spring and a small tilt."""

    def __init__(self, w, h, fill=PAPER, r=28):
        self.w, self.h, self.r = int(w), int(h), r
        self.im = Image.new("RGBA", (self.w * SS, self.h * SS), (0, 0, 0, 0))
        self.raw = ImageDraw.Draw(self.im)
        self.d = g.D2(self.raw)
        self.d.rounded_rectangle([0, 0, self.w, self.h], radius=r, fill=tuple(fill) + (255,))

    def text(self, x, y, s, f, fill, anchor="lm"):
        self.raw.text((x * SS, y * SS), s, font=f, fill=tuple(fill) + (255,), anchor=anchor)

    def tw(self, s, f):
        return self.raw.textlength(s, font=f) / SS

    def rect(self, x0, y0, x1, y1, fill, r=0, outline=None, w=2):
        if r:
            self.d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=None if fill is None else tuple(fill) + (255,),
                                     outline=None if outline is None else tuple(outline) + (255,), width=w)
        else:
            self.d.rectangle([x0, y0, x1, y1], fill=None if fill is None else tuple(fill) + (255,),
                             outline=None if outline is None else tuple(outline) + (255,), width=w)

    def line(self, pts, fill, w):
        self.d.line(pts, fill=tuple(fill) + (255,), width=w, joint="curve")

    def disc(self, cx, cy, r, fill, outline=None, w=2):
        self.d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=None if fill is None else tuple(fill) + (255,),
                       outline=None if outline is None else tuple(outline) + (255,), width=w)


_SHADOW = {}


def shadow_of(w, h, r):
    k = (w, h, r)
    if k not in _SHADOW:
        m = Image.new("L", ((w + 2 * PAD) * SS, (h + 2 * PAD) * SS), 0)
        ImageDraw.Draw(m).rounded_rectangle([PAD * SS, PAD * SS, (PAD + w) * SS, (PAD + h) * SS], radius=r * SS, fill=120)
        _SHADOW[k] = m.filter(ImageFilter.GaussianBlur(24 * SS))
    return _SHADOW[k]


def place(img, card, cx, cy, t, t0, rot=0.0, sc=1.0):
    """Drop a card on the stage at (cx, cy). It springs up from slightly small and tilted, then floats a little."""
    a = clamp01((t - t0) / 0.38)
    if a <= 0.01:
        return
    sh = shadow_of(card.w, card.h, card.r)
    base = Image.new("RGBA", sh.size, (0, 0, 0, 0))
    blk = Image.new("RGBA", sh.size, (96, 74, 54, 255))
    blk.putalpha(sh)
    base.alpha_composite(blk, (0, 14 * SS))
    base.alpha_composite(card.im, (PAD * SS, PAD * SS))
    s = sc * (0.86 + 0.14 * spring(a, 11.0)) if a < 1 else sc
    ang = rot + (1 - ease_out(a)) * -4.0 + 0.45 * math.sin(t * 0.8)
    if abs(s - 1.0) > 0.002:
        base = base.resize((max(2, int(base.width * s)), max(2, int(base.height * s))), Image.BILINEAR)
    if abs(ang) > 0.02:
        base = base.rotate(ang, resample=Image.BICUBIC, expand=True)
    if a < 1:
        al = base.getchannel("A").point(lambda v: int(v * min(1.0, a * 2.4)))
        base.putalpha(al)
    dy = (1 - ease_out(a)) * 46 + 5 * math.sin(t * 1.2)
    img.paste(base, (int(cx * SS - base.width / 2), int((cy + dy) * SS - base.height / 2)), base)


def fit_box():
    x0, y0, x1, y1 = vis_box()
    return x0, y0, x1, y1


# ------------------------------------------------------------------ the object library (each one a picture of what is being said)
def _num(s):
    try:
        return float(str(s).replace(",", ""))
    except ValueError:
        return None


def hook_units():
    m = re.search(r"(\d[\d,]*)\s*[- ]?\s*(?:unit|door|lot|pad|apartment)", story().get("hook", ""), re.I)
    return int(_num(m.group(1))) if m else None


def object_spec(text, f_=None):
    """Which drawn object shows what this sentence says (None when nothing fits and the words themselves carry the beat)."""
    tx = text
    low = tx.lower()
    pct = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|percent)", tx)
    pcv = _num(pct.group(1)) if pct else None
    money = re.search(r"\$\s?[\d,]*\d(?:\.\d+)?(?:\s?(?:million|billion|thousand|k|m)\b)?", tx, re.I)
    if f_ is not None and stamp_of(f_):
        return {"kind": "doc", "stamp": stamp_of(f_)}
    if re.search(r"\b(loan|lender|financing|floating|interest|refinanc|leverage|debt|mortgage|seller note)\b", low) and re.search(r"\d+(?:\.\d+)?\s*(?:%|percent)|floating|variable|adjustable", low):
        return {"kind": "loan", "ltv": pcv if pct and re.search(r"financ|ltv|loan|leverag|lend", low) else None,
                "floating": bool(re.search(r"floating|variable|adjustable", low)), "rate": pcv if pct and re.search(r"\brate\b|interest", low) else None}
    if re.search(r"\b(close|closing|deadline|hard date|due date|expires?)\b", low):
        return {"kind": "calendar", "fast": bool(re.search(r"fast|hard|quick|short|tight", low))}
    if re.search(r"\b(rent|rents|below market|above market|market rent)\b", low) and not money:
        return {"kind": "rentroll", "pct": pcv, "below": "below" in low or "under" in low}
    if re.search(r"\b(occupied|occupancy|vacan\w+)\b", low):
        return {"kind": "grid", "n": hook_units() or 100, "pct": pcv or 100.0, "title": f"{int(pcv)}%" if pcv else "", "sub": "occupied", "word": "occupied"}
    m = re.search(r"(\d[\d,]*)\s*[- ]?\s*(units?|doors?|lots?|pads?|apartments?|houses|homes|properties|buildings)\b", low)
    if money and re.search(r"\b(building|price|asking|offer|purchase)\b", low):
        mu = m and int(_num(m.group(1)) or 0)
        return {"kind": "listing", "price": _price(money.group(0)), "units": mu or hook_units()}
    if re.search(r"\b(price|asking)\b", low) and money:
        return {"kind": "listing", "price": _price(money.group(0)), "units": hook_units()}
    if m and int(_num(m.group(1)) or 0) >= 12:
        n = int(_num(m.group(1)))
        return {"kind": "grid", "n": n, "pct": 100.0, "title": f"{n:,}", "sub": m.group(2).upper(), "word": m.group(2)}
    if re.search(r"\b(spreadsheet|model|underwrit\w*|projections?|pro forma)\b", low):
        return {"kind": "sheet"}
    if re.search(r"\b(text|texted|message|email|emailed|called|told me|said)\b", low):
        return {"kind": "thread", "who": "Seller" if "seller" in low else "Message"}
    if money:
        return {"kind": "balance", "amount": money.group(0)}
    return None


def _price(s):
    s = s.upper().replace(" ", "")
    s = re.sub(r"MILLION|M$", "M", s)
    s = re.sub(r"THOUSAND|K$", "K", s)
    return s


def o_loan(sp, t, at):
    W, H = 900, 940
    c = Card(W, H)
    c.text(52, 58, "LOAN TERM SHEET", F("sans", 28), MUTED)
    c.rect(52, 92, W - 52, 95, LINE)
    c.disc(W - 92, 58, 24, None, outline=ACCENT, w=4)
    c.disc(W - 92, 58, 10, ACCENT)
    rows = []
    if sp.get("ltv"):
        rows.append(("Financing", f"{int(sp['ltv'])}% LTV", at("financing", 0.18)))
    if sp.get("floating"):
        rows.append(("Rate", "FLOATING", at("floating", 0.3)))
    elif sp.get("rate"):
        rows.append(("Rate", f"{sp['rate']:g}%", at("rate", 0.3)))
    for lab, k in (("Amount", 0.15), ("Term", 0.3), ("Rate", 0.45), ("Fees", 0.6)):
        if len(rows) >= (2 if sp.get("floating") else 3):
            break
        if lab not in [r[0] for r in rows]:
            rows.append((lab, None, at(None, k)))
    y = 200
    for label, val, tr in rows:
        a = ease_out((t - tr) / 0.30)
        if a <= 0.01:
            y += 150
            continue
        col = mix(TXT, PAPER, a)
        c.text(52, y, label, F("ital", 50), mix(MUTED, PAPER, a))
        if val:
            c.text(W - 52, y - 4, val, F("heavy", 74), col, "rm")
            if val == "FLOATING":
                bob = 8 * math.sin(t * 5.0)
                cx, cy = W - 52 - c.tw(val, F("heavy", 74)) - 48, y - 10 + bob
                c.d.polygon([(cx, cy - 24), (cx + 22, cy + 14), (cx - 22, cy + 14)], fill=tuple(mix(RED, PAPER, a)) + (255,))
        else:
            c.rect(W - 360, y - 14, W - 52, y + 14, mix(LINE, PAPER, a), r=14)
        c.rect(52, y + 58, W - 52, y + 60, mix(LINE, PAPER, a))
        y += 150
    if sp.get("floating"):
        tr = at("floating", 0.3)
        pr = clamp01((t - tr) / 1.4)
        pts = [0.16, 0.22, 0.18, 0.27, 0.34, 0.31, 0.46, 0.55, 0.62, 0.82, 0.78, 0.95]
        gx0, gx1, gy0, gy1 = 70, W - 70, H - 70, H - 330
        n = max(2, int(2 + pr * (len(pts) - 2)))
        xy = [(gx0 + (gx1 - gx0) * i / (len(pts) - 1), gy0 + (gy1 - gy0) * pts[i]) for i in range(n)]
        c.line(xy, RED, 7)
        c.disc(xy[-1][0], xy[-1][1], 12, RED)
    return c


def o_calendar(sp, t, at):
    W, H = 840, 820
    c = Card(W, H)
    c.rect(0, 0, W, 150, DEEP, r=28)
    c.rect(0, 100, W, 150, DEEP)
    c.text(W / 2, 76, "CLOSING", F("heavy", 56), LIGHT, "mm")
    days = ["M", "T", "W", "T", "F", "S", "S"]
    cw, ch = 104, 108
    gx = (W - 7 * cw) / 2
    for i, dname in enumerate(days):
        c.text(gx + cw * i + cw / 2, 190, dname, F("sans", 30), MUTED, "mm")
    target = 23 if not sp.get("fast") else 14
    tr = at("close", 0.2)
    prog = clamp01((t - tr) / 0.9)
    crossed = int(prog * (target - 1))
    for dn in range(1, 31):
        i = dn + 1
        col, row = i % 7, i // 7
        x, y = gx + cw * col + cw / 2, 258 + ch * row
        hit = dn == target
        c.text(x, y, str(dn), F("serifb" if hit else "serif", 44), TXT if dn >= target else mix(MUTED, PAPER, 0.7), "mm")
        if dn < target and dn <= crossed:
            c.line([(x - 26, y - 20), (x + 26, y + 20)], mix(RED, PAPER, 0.75), 4)
    x, y = gx + cw * ((target + 1) % 7) + cw / 2, 258 + ch * ((target + 1) // 7)
    p = clamp01((t - tr - 0.55) / 0.5)
    if p > 0:
        c.d.arc([x - 56, y - 56, x + 56, y + 56], -90, -90 + 360 * ease_out(p), fill=tuple(RED) + (255,), width=9)
    if sp.get("fast") and t > tr + 1.0:
        c.text(W / 2, H - 56, "hard date.", F("ital", 54), RED, "mm")
    return c


def o_rentroll(sp, t, at):
    W, H = 900, 940
    c = Card(W, H)
    c.text(52, 58, "RENT ROLL", F("sans", 28), MUTED)
    c.text(W - 52, 58, "RENT vs MARKET", F("sans", 24), MUTED, "rm")
    c.rect(52, 92, W - 52, 95, LINE)
    bx0, bx1 = 230, W - 150
    pct = sp.get("pct") or 18.0
    cur = (bx1 - bx0) * (1 - pct / 100.0) if sp.get("below", True) else (bx1 - bx0)
    top = (bx1 - bx0) if sp.get("below", True) else (bx1 - bx0) * (1 - pct / 100.0)
    for i in range(5):
        y = 190 + i * 140
        tr = at(None, 0.12 + 0.10 * i)
        a = ease_out((t - tr) / 0.3)
        if a <= 0.01:
            continue
        c.text(52, y, f"Unit {i + 1}", F("ital", 44), mix(MUTED, PAPER, a))
        c.rect(bx0, y - 34, bx0 + top * a, y - 4, None, r=9, outline=mix(GREEN, PAPER, a), w=3)
        c.rect(bx0, y + 6, bx0 + cur * a, y + 38, mix(ACCENT, PAPER, a), r=9)
    tg = at("below", 0.4) if sp.get("below", True) else at("market", 0.4)
    ga = ease_out((t - tg) / 0.3)
    if ga > 0.01 and sp.get("pct"):
        xe = bx0 + cur
        c.line([(xe + 10, 150), (xe + 36, 150), (xe + 36, 790), (xe + 10, 790)], mix(RED, PAPER, ga), 5)
        c.text(xe + 54, 470, f"{'-' if sp.get('below', True) else '+'}{int(pct)}%", F("heavy", 64), mix(RED, PAPER, ga), "lm")
    return c


def o_grid(sp, t, at):
    W, H = 900, 980
    c = Card(W, H)
    n = max(4, min(700, int(sp.get("n") or 100)))
    title = sp.get("title") or ""
    sub = sp.get("sub") or ""
    if title:
        c.text(W / 2, 140, title, F("heavy", 130), TXT, "mm")
    if sub:
        c.text(W / 2, 250, sub.lower() + ".", F("ital", 66), RED if "vac" in sub.lower() else mix(DEEP, PAPER, 0.9), "mm")
    ax0, ay0, ax1, ay1 = 64, 330, W - 64, H - 60
    aw, ah = ax1 - ax0, ay1 - ay0
    cols = max(1, int(math.ceil(math.sqrt(n * aw / ah))))
    rows = int(math.ceil(n / cols))
    cell = min(aw / cols, ah / rows)
    ox = ax0 + (aw - cell * cols) / 2
    oy = ay0 + (ah - cell * rows) / 2
    filled = int(round(n * (sp.get("pct") or 100.0) / 100.0))
    tr = at(sp.get("word"), 0.15)
    shown = int(clamp01((t - tr) / 1.2) * filled) if filled < n else int(clamp01((t - (tr - 0.2)) / 1.3) * n)
    r = max(2.0, cell * 0.36)
    for i in range(n):
        x = ox + (i % cols + 0.5) * cell
        y = oy + (i // cols + 0.5) * cell
        if i < shown:
            c.disc(x, y, r, ACCENT)
        else:
            c.disc(x, y, r, None, outline=LINE, w=max(2, int(r * 0.35)))
    return c


def o_listing(sp, t, at):
    W, H = 840, 1000
    c = Card(W, H)
    c.rect(36, 36, W - 36, 600, DEEP, r=20)
    rng = np.random.default_rng(7)
    c.rect(150, 150, W - 150, 600, (92, 72, 60))
    c.rect(130, 130, W - 130, 156, (80, 60, 49))
    for r_ in range(7):
        for cc in range(6):
            x0 = 176 + cc * 86
            y0 = 190 + r_ * 56
            lit = rng.random() < 0.46 + 0.1 * math.sin(t * 0.6 + r_ + cc)
            c.rect(x0, y0, x0 + 46, y0 + 32, (255, 208, 72) if lit else (56, 40, 31), r=4)
    c.rect(150, 540, W - 150, 600, (50, 36, 28))
    c.rect(W / 2 - 40, 520, W / 2 + 40, 600, (255, 208, 72), r=4)
    tr = at("price", 0.15)
    a = ease_out((t - tr) / 0.35)
    c.text(52, 664, "ASKING", F("sans", 28), mix(MUTED, PAPER, max(a, 0.01)))
    price = sp.get("price") or ""
    px = 150
    while c.tw(price, F("heavy", px)) > W - 104 and px > 60:
        px -= 6
    c.text(52, 770, price, F("heavy", px), mix(TXT, PAPER, a))
    c.rect(52, 846, W - 52, 849, LINE)
    if sp.get("units"):
        c.text(52, 920, f"{int(sp['units'])} units", F("ital", 58), mix(DEEP, PAPER, ease_out((t - tr - 0.3) / 0.3)))
        if price and re.match(r"^\$[\d.,]+[MK]?$", price):
            pass
    return c


def o_thread(sp, t, at, text, t0, t1):
    W, H = 900, 760
    c = Card(W, H)
    c.disc(78, 74, 34, DEEP)
    c.text(78, 74, sp.get("who", "Message")[0], F("serifb", 34), LIGHT, "mm")
    c.text(132, 62, sp.get("who", "Message"), F("sans", 34), TXT)
    c.text(132, 100, "now", F("sansr", 24), MUTED)
    c.rect(40, 130, W - 40, 133, LINE)
    start = t0 + 0.45
    dots = start - 0.45 <= t < start
    if dots:
        for i in range(3):
            k = 0.5 + 0.5 * math.sin(t * 9 - i * 0.9)
            c.disc(120 + i * 40, 230, 11 + 3 * k, mix(MUTED, PAPER2, 0.5 + 0.5 * k))
    elif t >= start:
        full = text
        n = int(len(full) * clamp01((t - start) / max(0.6, (t1 - start) * 0.8)))
        shown = full[:max(1, n)]
        f = F("serif", 56)
        lines = wrap(shown, f, W - 190)
        hh = len(lines) * 76 + 60
        bw = max(c.tw(l, f) for l in lines) + 70
        c.rect(52, 170, 52 + bw, 170 + hh, PAPER2, r=34)
        for i, l in enumerate(lines):
            c.text(88, 170 + 58 + i * 76, l, f, TXT)
    return c


def o_doc(sp, t, at, f_, t0, t1):
    W, H = 800, 1000
    c = Card(W, H)
    c.rect(0, 0, W, 120, DEEP, r=28)
    c.rect(0, 80, W, 120, DEEP)
    c.rect(48, 36, 48 + 220, 62, mix(PAPER, DEEP, 0.7), r=8)
    c.rect(48, 74, 48 + 140, 90, mix(PAPER, DEEP, 0.4), r=8)
    y = 176
    for i in range(7):
        wd = [640, 560, 620, 380, 600, 520, 300][i]
        c.rect(48, y, 48 + wd, y + 16, LINE, r=8)
        y += 44
    c.rect(48, 540, W - 48, 700, None, r=14, outline=LINE, w=3)
    for i in range(3):
        c.rect(72, 570 + i * 44, 72 + [300, 200, 260][i], 584 + i * 44, LINE, r=7)
    c.line([(48, 900), (330, 900)], MUTED, 3)
    c.line([(52, 884), (92, 850), (130, 884), (164, 842), (210, 888)], DEEP, 4)
    ws = beat_words_of(f_)
    ts = (ws[-1][1] - 0.4) if ws else t0 + 0.4
    a = clamp01((t - ts) / 0.16)
    if a > 0.02:
        label = sp["stamp"]
        col = RED if label in ("PASSED", "DENIED") else GREEN
        px = 120
        f = F("heavy", px)
        w = c.tw(label, f) + 90
        h = px * 1.42
        L = int(w + 60)
        layer = Image.new("RGBA", (L * SS, int((h + 60) * SS)), (0, 0, 0, 0))
        dd = g.D2(ImageDraw.Draw(layer))
        cc = tuple(col) + (235,)
        dd.rectangle([30, 30, 30 + w, 30 + h], outline=cc, width=6)
        dd.rectangle([42, 42, 18 + w, h + 18], outline=cc, width=2)
        ImageDraw.Draw(layer).text(((30 + w / 2) * SS, (30 + h / 2) * SS), label, fill=cc, font=f, anchor="mm")
        sc = 1.0 + 0.5 * (1 - ease_out(a))
        layer = layer.resize((int(layer.width * sc), int(layer.height * sc)), Image.BILINEAR).rotate(-11, expand=True, resample=Image.BICUBIC)
        c.im.alpha_composite(layer, (max(0, int((W / 2) * SS - layer.width / 2)), max(0, int(700 * SS - layer.height / 2))))
    return c


def beat_words_of(f_):
    return f_.get("_ws") or []


def o_sheet(sp, t, at):
    W, H = 920, 940
    c = Card(W, H)
    c.rect(0, 0, W, 110, DEEP, r=28)
    c.rect(0, 70, W, 110, DEEP)
    c.text(52, 56, "fx", F("ital", 44), LIGHT, "lm")
    c.rect(130, 28, W - 52, 84, (96, 76, 62), r=10)
    c.rect(150, 48, 420, 64, mix(LIGHT, DEEP, 0.55), r=8)
    cw, ch = 205, 104
    heads = "ABCD"
    for i in range(4):
        c.text(52 + 28 + cw * i + cw / 2, 146, heads[i], F("sans", 28), MUTED, "mm")
    rng = np.random.default_rng(3)
    tr = at(None, 0.15)
    for r_ in range(7):
        for cc in range(4):
            x0, y0 = 52 + cw * cc, 180 + ch * r_
            a = ease_out((t - tr - 0.05 * (r_ * 4 + cc)) / 0.25)
            c.rect(x0, y0, x0 + cw, y0 + ch, None, outline=LINE, w=2)
            if a > 0.02:
                wd = int((cw - 60) * (0.35 + 0.6 * rng.random()) * a)
                c.rect(x0 + 24, y0 + 40, x0 + 24 + wd, y0 + 62, mix(DEEP, PAPER, 0.65), r=8)
    tf = at("lying", 0.75) if True else 0
    a = ease_out((t - tf) / 0.3)
    if a > 0.02:
        x0, y0 = 52 + cw * 2, 180 + ch * 3
        c.rect(x0, y0, x0 + cw, y0 + ch, None, outline=mix(RED, PAPER, a), w=7)
        c.disc(x0 + cw - 4, y0 + 4, 24, mix(RED, PAPER, a))
        c.text(x0 + cw - 4, y0 + 5, "!", F("heavy", 30), LIGHT, "mm")
    return c


def o_balance(sp, t, at):
    W, H = 900, 760
    c = Card(W, H)
    c.text(56, 70, "BALANCE", F("sans", 30), MUTED)
    c.disc(W - 84, 66, 22, None, outline=ACCENT, w=4)
    c.disc(W - 84, 66, 8, ACCENT)
    amt = sp["amount"].upper()
    digits = re.sub(r"[^0-9.]", "", amt.split()[0])
    tail = re.sub(r"^[\$0-9.,]+", "", amt).strip()
    tr = at(re.sub(r"[^A-Za-z0-9]", "", amt.split()[0]), 0.25)
    v = _num(digits)
    p = ease_out((t - tr) / 0.8)
    if v is not None and p < 1:
        shown = v * p
        txt = f"${shown:,.0f}" if v >= 100 or float(v).is_integer() else f"${shown:,.1f}"
    else:
        txt = amt.split()[0]
        if not txt.startswith("$"):
            txt = "$" + txt
    txt += (" " + tail) if tail and p >= 1 else ""
    px = 220
    while c.tw(txt, F("heavy", px)) > W - 100 and px > 70:
        px -= 8
    c.text(W / 2, 360, txt, F("heavy", px), TXT, "mm")
    c.rect(64, 500, 64 + (W - 128) * ease_out((t - tr) / 0.6), 508, ACCENT)
    c.text(64, 600, "checking", F("ital", 54), MUTED)
    return c


OBJ_SIZE = {"loan": (900, 700), "calendar": (840, 820), "rentroll": (900, 740), "grid": (900, 780), "listing": (840, 1000), "thread": (900, 560),
            "doc": (800, 1000), "sheet": (920, 780), "balance": (900, 560)}


def build_obj(sp, t, at, text="", f_=None, t0=0.0, t1=1.0):
    k = sp["kind"]
    if k == "loan":
        return o_loan(sp, t, at)
    if k == "calendar":
        return o_calendar(sp, t, at)
    if k == "rentroll":
        return o_rentroll(sp, t, at)
    if k == "grid":
        return o_grid(sp, t, at)
    if k == "listing":
        return o_listing(sp, t, at)
    if k == "thread":
        return o_thread(sp, t, at, text, t0, t1)
    if k == "doc":
        return o_doc(sp, t, at, f_ or {}, t0, t1)
    if k == "sheet":
        return o_sheet(sp, t, at)
    return o_balance(sp, t, at)


# ------------------------------------------------------------------ own scenes in the Desk look (message, comment, follow)
def p_send(img, t, at, label, t0):
    c = Card(900, 780)
    a = ease_out((t - t0) / 0.3)
    c.text(56, 70, "NEW MESSAGE", F("sans", 28), MUTED)
    c.rect(56, 104, 900 - 56, 107, LINE)
    c.text(56, 190, "To", F("ital", 52), MUTED)
    to = at("someone", 0.3)
    lines = wrap(label.lower(), F("serif", 50), 560)[:2]
    c.rect(130, 150, 850, 150 + 40 + 62 * len(lines), PAPER2, r=36)
    for li, ln in enumerate(lines):
        c.text(164, 206 + li * 62, ln, F("serif", 50), TXT)
    tp = at("send", 0.12)
    p = ease_out((t - tp - 0.7) / 0.5)
    cx, cy = 450, 560
    pts = [(-80, -50), (90, 0), (-80, 50), (-45, 0)]
    off = (1 - p) * 0 + max(0.0, (t - tp - 1.3)) * 520
    c.d.polygon([(cx + x + off, cy + y - off * 0.5) for x, y in pts], fill=tuple(ACCENT) + (255,))
    c.text(450, 700, "sent." if off > 40 else "send", F("ital", 64), TXT, "mm")
    return c


def p_comment(img, t, at, word, t0):
    c = Card(900, 560)
    c.text(56, 70, "COMMENT", F("sans", 28), MUTED)
    c.rect(56, 104, 900 - 56, 107, LINE)
    c.rect(56, 170, 900 - 56, 350, PAPER2, r=44)
    tw_ = at(word.split()[-1].lower(), 0.3)
    n = int(len(word) * clamp01((t - (tw_ - 0.5)) / 0.5))
    shown = word[:n]
    if n == 0:
        c.text(100, 260, "Add a comment", F("sansr", 48), MUTED)
    else:
        c.text(100, 262, shown + ("|" if int(t * 3) % 2 == 0 and n < len(word) else ""), F("heavy", 76), TXT)
    pb = clamp01((t - tw_) / 0.2)
    c.disc(900 - 130, 260, 42, mix(ACCENT, PAPER2, 0.3 + 0.7 * pb))
    c.line([(900 - 130, 280), (900 - 130, 242)], TXT, 7)
    c.line([(900 - 148, 258), (900 - 130, 240), (900 - 112, 258)], TXT, 7)
    c.text(56, 470, "Reply publicly", F("ital", 46), MUTED)
    return c



def avatar(target, cx, cy, d, prof, ring=5, card=False):
    """The account's round profile picture (initials on a dark disc when there is no picture file yet) with a ring in the accent colour.
    `target` is a Card (card=True, 1x units) or a page image (card=False)."""
    px = int(d * SS)
    if prof.get("picture"):
        pic = profile.circle(prof["picture"], px)
    else:
        pic = Image.new("RGBA", (px, px), (0, 0, 0, 0))
        dd = ImageDraw.Draw(pic)
        dd.ellipse([0, 0, px - 1, px - 1], fill=tuple(DEEP) + (255,))
        dd.text((px / 2, px / 2), profile.initials(prof), font=F("heavy", d * 0.40), fill=tuple(LIGHT) + (255,), anchor="mm")
    ringl = Image.new("RGBA", (px + 2 * ring * SS, px + 2 * ring * SS), (0, 0, 0, 0))
    ImageDraw.Draw(ringl).ellipse([0, 0, ringl.width - 1, ringl.height - 1], fill=tuple(ACCENT) + (255,))
    gap = Image.new("RGBA", ringl.size, (0, 0, 0, 0))
    ImageDraw.Draw(gap).ellipse([ring * SS * 0.45, ring * SS * 0.45, ringl.width - 1 - ring * SS * 0.45, ringl.height - 1 - ring * SS * 0.45], fill=tuple(LIGHT) + (255,))
    ringl.alpha_composite(gap)
    ringl.alpha_composite(pic, (ring * SS, ring * SS))
    if card:
        target.im.alpha_composite(ringl, (int(cx * SS - ringl.width / 2), int(cy * SS - ringl.height / 2)))
    else:
        pad = 36 * SS                                           # room for the blur, so the shadow fades out instead of being cut off in a square
        sa = Image.new("L", (ringl.width + 2 * pad, ringl.height + 2 * pad), 0)
        sa.paste(ringl.getchannel("A"), (pad, pad))
        sa = sa.filter(ImageFilter.GaussianBlur(10 * SS)).point(lambda v: int(v * 0.35))
        target.paste(Image.new("RGB", sa.size, (96, 74, 54)), (int(cx * SS - sa.width / 2), int(cy * SS - sa.height / 2 + 10 * SS)), sa)
        target.paste(ringl, (int(cx * SS - ringl.width / 2), int(cy * SS - ringl.height / 2)), ringl)


def p_follow(img, t, at, label, t0):
    c = Card(900, 720)
    prof = profile.load()
    if prof:
        avatar(c, 150, 170, 150, prof, card=True)
        hf = F("serifb", 52)
        while c.tw(prof["handle"], hf) > 540 and hf.size / SS > 30:
            hf = F("serifb", hf.size / SS - 4)
        c.text(262, 146, prof["handle"], hf, TXT)
        c.text(262, 214, "real numbers behind every deal", F("ital", 40), MUTED)
    else:
        c.disc(140, 170, 80, DEEP)
        c.disc(140, 170, 80, None, outline=ACCENT, w=5)
        c.disc(140, 148, 27, LIGHT)
        c.rect(92, 180, 188, 228, LIGHT, r=24)
        c.text(260, 146, "Real numbers", F("serifb", 56), TXT)
        c.text(260, 214, "behind every deal", F("ital", 50), MUTED)
    tf = at("follow", 0.15)
    p = clamp01((t - tf) / 0.25)
    col = mix(ACCENT, DEEP, p)
    c.rect(56, 400, 900 - 56, 560, col, r=80)
    c.text(450, 480, "Following" if t > tf + 0.8 else "+ Follow", F("heavy", 72), LIGHT, "mm")
    return c



def icon_card(name, neg=False, size=580):
    """A square sheet with one line drawing on it, the picture of a noun the sentence names (a house, a storm cloud, a key). A negated noun is struck through."""
    c = Card(size, size, r=56)
    spec = story_icons.ICONS[name]
    isz = size * 0.64
    ox = oy = (size - isz) / 2
    w = max(4.0, isz / 22.0)
    for ck, pts in spec:
        pp = [(ox + px * isz / 100.0, oy + py * isz / 100.0) for px, py in pts]
        col = TXT if ck == "i" else ACCENT
        c.line(pp, col, w)
        for q in (pp[0], pp[-1]):
            c.disc(q[0], q[1], w / 2, col)
    if neg:
        c.line([(size * 0.16, size * 0.84), (size * 0.84, size * 0.16)], RED, 14)
    return c


def noun_of(text):
    ics = story_scenes.concrete(text)
    ics = [c for c in ics if c["icon"] in story_icons.ICONS]
    if not ics:
        return None
    return next((c for c in ics if c.get("strong")), ics[0])



# ------------------------------------------------------------------ stock footage, framed as a print on paper (only where the script picks a shot)
FOOTAGE = False                      # off in the Desk style (graphics only), switched on by the Board style


def footage_for(cid, idx, f_):
    """The curated clip id a beat asked for with a [broll tag] line (None when it asked for none or the library has nothing for the tag)."""
    tags = [q for q in (f_.get("broll") or []) if q and q.lower() != "none"]
    for k, q in enumerate(tags):
        clip = broll.lookup(q, cid * 3 + idx + k)
        if clip:
            return clip
    return None


def o_footage(clip, t, t0, off=0.0):
    """A print: the footage graded warm and a little faded, inside a white border with a strip of tape, drifting slowly (a push-in)."""
    fr = broll.frame(clip, max(0.0, t - t0) + off)
    if fr is None:
        return None
    W, H, B = 900, 1040, 38
    c = Card(W, H, r=18)
    iw, ih = W - 2 * B, H - 2 * B - 70
    z = 1.06 + 0.05 * clamp01((t - t0) / 3.0)
    bw, bh = fr.size
    cw = min(bw, bh * iw / ih) / z
    ch = cw * ih / iw
    x0, y0 = (bw - cw) / 2, (bh - ch) / 2
    ph = fr.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((iw * SS, ih * SS), Image.BILINEAR)
    ph = ImageEnhance.Color(ph).enhance(0.80)
    ph = Image.blend(ph, Image.new("RGB", ph.size, (236, 226, 208)), 0.10)
    mask = Image.new("L", ph.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, ph.width - 1, ph.height - 1], radius=10 * SS, fill=255)
    c.im.paste(ph, (B * SS, B * SS), mask)
    tape = Image.new("RGBA", (190 * SS, 54 * SS), (226, 210, 168, 205))
    tape = tape.rotate(-4, expand=True, resample=Image.BICUBIC)
    c.im.alpha_composite(tape, (int((W / 2 - 95) * SS), 0))
    return c


# ------------------------------------------------------------------ kinetic type (the sentence itself, big)
def split_emph(text):
    toks = text.split()
    n = len(toks)
    if n <= 1:
        return n, toks
    bounds = [i for i, w in enumerate(toks[:-1]) if w[-1:] in ".,!?;"]
    if bounds:
        return bounds[-1] + 1, toks
    k = max(1, int(round(n * 0.55)))
    soft = {"i", "a", "an", "the", "and", "or", "to", "of", "that", "we", "you", "it", "my", "is", "so", "in", "on", "at", "for", "with", "but"}
    while k < n - 1 and re.sub(r"[^a-z']", "", toks[k].lower()) in soft:
        k += 1
    return k, toks


def draw_type(img, text, tw_of, t, s0, box=None, pxmax=172):
    x0, y0, x1, y1 = box or ((50, 330, VW - 50, 1230) if PORTRAIT else vis_box())
    maxw = x1 - x0
    k, toks = split_emph(text)
    px = pxmax
    while True:
        runs = []
        for i, w in enumerate(toks):
            heavy = i < k
            runs.append((w.upper() if heavy else (w[:1].upper() + w[1:] if i == 0 else w), heavy))
        lines, cur, curw = [], [], 0.0
        for i, (w, heavy) in enumerate(runs):
            f = F("heavy", px * 1.06) if heavy else F("ital", px * 1.16)
            ww = width(w, f)
            sp = width(" ", f)
            if cur and curw + sp + ww > maxw:
                lines.append(cur)
                cur, curw = [], 0.0
            cur.append((i, w, heavy, f, ww))
            curw += (sp if len(cur) > 1 else 0) + ww
        if cur:
            lines.append(cur)
        if len(lines) * px * 1.12 <= (y1 - y0) * 0.80 or px <= 54:
            break
        px -= 6
    lh = px * 1.12
    top = (y0 + y1) / 2 - len(lines) * lh / 2
    d = ImageDraw.Draw(img)
    cx = VW / 2
    last_xy = None
    for li, ln in enumerate(lines):
        sp = width(" ", ln[0][3])
        total = sum(e[4] for e in ln) + sp * (len(ln) - 1)
        xx = cx - total / 2
        by = top + li * lh + px * 0.86
        for i, w, heavy, f, ww in ln:
            tw_ = tw_of(i)
            a = ease_out((t - tw_) / 0.17)
            if a > 0.02:
                bad = word_color(w) == RED
                col = RED if bad else (BONE if heavy else ACCENT)
                shadow_text(img, xx, by + (1 - a) * 26, w, f, px, anchor="ls", strength=a)
                d.text((xx * SS, (by + (1 - a) * 26) * SS), w, font=f, fill=mix(col, INK, a), anchor="ls")
            last_xy = (xx, by, ww, heavy)
            xx += ww + sp
    if last_xy and not last_xy[3] and len(toks) > 1:
        tl = tw_of(len(toks) - 1)
        a = ease_out((t - tl - 0.1) / 0.35)
        xl, bl, wl, _h = last_xy
        d.rectangle([xl * SS, (bl + px * 0.16) * SS, (xl + wl * a) * SS, (bl + px * 0.16 + 5) * SS], fill=ACCENT)


# ------------------------------------------------------------------ captions: the spoken line, small and serif, on a dark glass strip
def draw_caption(img, c, idx, t, s0, big=1.0):
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
    cx, cy, maxw, _px0 = caption_geometry()
    words = [w for w, _t in cur]
    times = [tt for _w, tt in cur]
    px = 66 * CAPTION_SCALE
    f = F("serif", px)
    sp = width(" ", f)
    ws_w = [width(w, f) for w in words]
    total = sum(ws_w) + sp * (len(words) - 1)
    while total > maxw - 70 and px > 34:
        px -= 3
        f = F("serif", px)
        sp = width(" ", f)
        ws_w = [width(w, f) for w in words]
        total = sum(ws_w) + sp * (len(words) - 1)
    a = clamp01((t - times[0]) / 0.14)
    bw, bh = total + 70, px * 1.55
    x0, y0 = cx - bw / 2, cy - bh / 2 + (1 - ease_out(a)) * 14
    box = (int(x0 * SS), int(y0 * SS), int((x0 + bw) * SS), int((y0 + bh) * SS))
    shw = Image.new("L", (box[2] - box[0] + 120 * SS, box[3] - box[1] + 120 * SS), 0)
    ImageDraw.Draw(shw).rounded_rectangle([60 * SS, 60 * SS, shw.width - 60 * SS, shw.height - 60 * SS], radius=int(bh * 0.30 * SS), fill=int(70 * min(1.0, a * 2)))
    shw = shw.filter(ImageFilter.GaussianBlur(14 * SS))
    img.paste(Image.new("RGB", shw.size, (96, 74, 54)), (box[0] - 60 * SS, box[1] - 60 * SS + 10 * SS), shw)
    reg = img.crop(box)
    glass = Image.blend(reg, Image.new("RGB", reg.size, LIGHT), 0.95 * min(1.0, a * 2))
    mask = Image.new("L", reg.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, reg.width - 1, reg.height - 1], radius=int(bh * 0.30 * SS), fill=255)
    img.paste(glass, box[:2], mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([box[0], box[1], box[2] - 1, box[3] - 1], radius=int(bh * 0.30 * SS), outline=mix(LINE, INK, 0.9 * min(1.0, a * 2)), width=2 * SS)
    xx = cx - total / 2
    for i, w in enumerate(words):
        nxt = times[i + 1] if i + 1 < len(times) else times[0] + 9
        spoken, active = t >= times[i] - 0.02, times[i] - 0.02 <= t < nxt
        col = (RED if word_color(w) == RED else ACCENT) if active else (BONE if spoken else mix(BONE, LIGHT, 0.45))
        d.text(((xx) * SS, (y0 + bh / 2 + 0.03 * px) * SS), w, font=f, fill=col, anchor="lm")
        xx += ws_w[i] + sp


# ------------------------------------------------------------------ planning
SCENE_TYPES = {"calc", "steps", "count", "stat", "hub", "flow", "cards", "ab", "compare", "bank", "chat", "freedom", "growth", "own", "ceiling",
               "income_stop", "hours", "stack"}
CUSTOM = {"keyword", "send", "follow"}


def plan_beat(cid, idx):
    key = (cid, idx)
    if key in _PLAN:
        return _PLAN[key]
    f_ = story()["feats"][str(cid)][idx]
    sp = story_scenes.scene_of(story(), cid, idx)
    typ = sp.get("type")
    route, obj = "type", None
    if typ in CUSTOM:
        route = "custom"
    elif typ in SCENE_TYPES and (typ != "steps" or sp.get("rows")) and (typ != "count" or sp.get("tag")):
        route = "scene"
    else:
        obj = object_spec(f_["text"], f_)
        if obj:
            route = "obj"
    p = {"route": route, "obj": obj, "typ": typ, "kind": beat_kind(cid, idx), "first": None, "scene": (0, 0, 1.0)}
    if route == "scene":
        x0, y0, x1, y1 = vis_box()
        ex0, ey0, ex1, ey1, first = scene_extent(cid, idx)
        kk = max(0.5, min((x1 - x0) / (ex1 - ex0 + 40.0), (y1 - y0) / (ey1 - ey0 + 40.0), 3.0))
        p["scene"] = ((x0 + x1) / 2 - kk * (ex0 + ex1) / 2, (y0 + y1) / 2 - kk * (ey0 + ey1) / 2, kk)
        p["first"] = first
    _PLAN[key] = p
    return p


def draw_scene(be, ctx, sp):
    be.deadline = ctx.t1 - 0.12
    be.earliest = ctx.t0 + 0.06
    typ = sp.get("type")
    if typ == "count" and sp.get("tag"):
        p_notifs(be, ctx, sp)
    elif typ == "steps" and sp.get("rows"):
        p_steps(be, ctx, sp)
    elif typ == "calc":
        p_calc(be, ctx, sp)
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


def word_color(w):
    low = re.sub(r"[^a-z']", "", w.lower())
    return RED if low in NEG_WORDS else BONE


def stage_card_xy(card):
    x0, y0, x1, y1 = (40, 320, VW - 40, 1200) if PORTRAIT else vis_box()
    sc = min((x1 - x0) / card.w, (y1 - y0) / card.h, 1.25)
    return (x0 + x1) / 2, (y0 + y1) / 2 - 10, sc


def draw_progress(img, cid, t):
    try:
        total = sum(n for _nm, n in _SEGS) / FPS if _SEGS else 0
        before = (_setup()[1]) / FPS + sum((CLIPS[i].get("total_frames") or 0) for i in range(cid - 1)) / FPS
        frac = clamp01((before + t) / total) if total else 0
    except Exception:
        return
    y = VH * (0.058 if PORTRAIT else 0.02)
    d = ImageDraw.Draw(img)
    d.rectangle([0, y * SS, VRW, (y + 3) * SS], fill=mix(BONE, INK, 0.14))
    d.rectangle([0, y * SS, VRW * frac, (y + 3) * SS], fill=ACCENT)


def page_for(cid, idx, t, frame_no=0, base=None, progress=True):
    c = CLIPS[cid - 1]
    s0, s1 = g.clip_beats(c)[idx]
    p = plan_beat(cid, idx)
    img = base if base is not None else stage(t + cid * 1.9)
    f_ = story()["feats"][str(cid)][idx]
    sp = story_scenes.scene_of(story(), cid, idx)
    ws = beat_words(c, idx)
    ctx = story_scenes.Ctx(s0, s1, ws, lambda kk: t_word(c, idx, kk))
    route = p["route"]
    show_caption = True
    if route == "obj":
        o = p["obj"]
        f2 = dict(f_, _ws=ws)
        card = build_obj(o, t, ctx.at, f_["text"], f2, s0, s1)
        cx, cy, sc = stage_card_xy(card)
        place(img, card, cx, cy, t, s0 + 0.04, rot=-1.0 if idx % 2 else 1.0, sc=sc)
    elif route == "custom":
        typ = p["typ"]
        if typ == "send":
            card = p_send(img, t, ctx.at, sp["label"], s0)
        elif typ == "keyword":
            card = p_comment(img, t, ctx.at, sp["word"], s0)
        else:
            card = p_follow(img, t, ctx.at, sp.get("label", ""), s0)
        cx, cy, sc = stage_card_xy(card)
        place(img, card, cx, cy, t, s0 + 0.04, rot=0.0, sc=sc)
    elif route == "scene":
        ox, oy, k = p["scene"]
        be = DocuBE(img, t, ox, oy, k, s0=s0, first=p["first"])
        be.has_footage = False
        draw_scene(be, ctx, sp)
    else:
        text = f_["text"]
        if f_["kind"] == "quote" and f_.get("quote"):
            text = "“" + f_["quote"] + "”"
        n = len(text.split())
        tw_of = lambda i: t_word(c, idx, min(i, max(0, nwords(f_["text"]) - 1))) if ws else s0 + (s1 - s0) * 0.12 + (s1 - s0) * 0.7 * i / max(1, n)
        noun = noun_of(f_["text"]) if PORTRAIT else None
        foot = footage_for(cid, idx, f_) if PORTRAIT and FOOTAGE else None
        card = o_footage(foot, t, s0, 0.3 * idx) if foot else None
        if card is not None:
            place(img, card, VW / 2, 700, t, s0 + 0.04, rot=-1.5 if idx % 2 else 1.5, sc=min(780 / card.h, 860 / card.w))
            draw_type(img, text, tw_of, t, s0, box=(50, 1110, VW - 50, 1480), pxmax=118)
        elif noun:
            card = icon_card(noun["icon"], noun.get("neg", False))
            place(img, card, VW / 2, 670, t, ctx.at(noun["word"], 0.12) - 0.1, rot=-2.0 if idx % 2 else 2.0, sc=1.0)
            draw_type(img, text, tw_of, t, s0, box=(50, 1010, VW - 50, 1420), pxmax=124)
        else:
            draw_type(img, text, tw_of, t, s0)
        show_caption = False
    if show_caption:
        draw_caption(img, c, idx, t, s0)
    if progress:
        draw_progress(img, cid, t)
    return img


def render_frame(cid, t, frame_no=0):
    c = CLIPS[cid - 1]
    beats = g.clip_beats(c)
    idx, prog = g.local_beat(c, t)
    if idx > 0 and t < beats[idx][0]:
        idx -= 1
    s0, s1 = beats[idx]
    img = page_for(cid, idx, t, frame_no)
    img = add_grain(img, frame_no)
    u = clamp01((t - s0) / max(0.5, s1 - s0))
    return g.apply_camera(img, 1.0 + DRIFT * u, 0.0, 0.0)


# ------------------------------------------------------------------ hook and close
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
    w = x1 - x0 + (30 if PORTRAIT else 0)
    t1, t2 = st["hook_head"][0], st["hook_head"][1]
    t1 = t1.upper()
    top = 300 if PORTRAIT else 60
    h_avail = (VH * 0.25 if PORTRAIT else VH * 0.50)
    px = 118 if PORTRAIT else 86
    while True:
        l1 = wrap(t1, F("heavy", px), w)
        l2 = wrap(t2, F("ital", px * 1.14), w)
        if (len(l1) + len(l2)) * px * 1.1 <= h_avail or px <= 46:
            break
        px -= 2
    return {"w": w, "top": top, "px": px, "l1": l1, "l2": l2}


def intro_draw(img, t, total):
    """The hook, drawn onto `img` (a page the size of the frame)."""
    st = story()
    L = hook_layout()
    cx = VW / 2
    px = L["px"]
    yy = L["top"]
    d = ImageDraw.Draw(img)
    a0 = ease_out(t / 0.28)
    for ln in L["l1"]:
        shadow_text(img, cx, yy + px * 0.62 + (1 - a0) * 24, ln, F("heavy", px), px, anchor="mm", strength=a0)
        d.text((cx * SS, (yy + px * 0.62 + (1 - a0) * 24) * SS), ln, font=F("heavy", px), fill=mix(BONE, INK, a0), anchor="mm")
        yy += px * 1.06
    yy += px * 0.1
    a1 = ease_out((t - 0.12) / 0.3)
    for ln in L["l2"]:
        shadow_text(img, cx, yy + px * 0.62 + (1 - a1) * 24, ln, F("ital", px * 1.14), px, anchor="mm", strength=a1)
        d.text((cx * SS, (yy + px * 0.62 + (1 - a1) * 24) * SS), ln, font=F("ital", px * 1.14), fill=mix(ACCENT, INK, a1), anchor="mm")
        yy += px * 1.16
    obj = object_spec(st["hook_head"][0])
    foot = None if obj else (footage_for(0, 0, {"broll": st.get("hook_broll")}) if PORTRAIT and FOOTAGE else None)
    fcard = o_footage(foot, t, 0.0) if foot else None
    if fcard is not None:
        sc = min(1.0, (1440 - (yy + 30)) / fcard.h, 900 / fcard.w)
        if sc > 0.3:
            place(img, fcard, cx, yy + 30 + fcard.h * sc / 2, t, 0.3, rot=1.2, sc=sc)
    if obj:
        words = []
        try:
            words = [(w["word"], g.INTRO_PAD_BEFORE + w["start"]) for w in json.loads((g.TIMING_DIR / f"clip{HOOK_ID}.json").read_text(encoding="utf-8"))["words"]]
        except Exception:
            pass
        ctx = story_scenes.Ctx(0.0, total, words, lambda kk: 0.0)
        card = build_obj(obj, t, ctx.at, st.get("hook", ""), {"_ws": words}, 0.0, total)
        sc = min(1.0, (1420 - (yy + 30)) / card.h, 940 / card.w)
        if sc > 0.3:
            place(img, card, cx, yy + 30 + card.h * sc / 2, t, 0.3, rot=1.0, sc=sc)


def intro_frame(f, setup=None):
    total, _n, cut_t = setup or intro_setup()
    t = f / FPS
    img = stage(t)
    intro_draw(img, t, total)
    img = add_grain(img, f)
    return g.apply_camera(img, 1.0 + 0.03 * ease(t / max(0.5, total)), 0.0, 0.0)


def outro_draw(img, t):
    """The closing card, drawn onto `img` (a page the size of the frame)."""
    st = story()
    x0, y0, x1, y1 = vis_box()
    cx = VW / 2
    lines = st["outro"]["lines"]
    w = x1 - x0 + 30
    px = 104 if PORTRAIT else 70
    while True:
        ls = []
        for i, l in enumerate(lines):
            last = i == len(lines) - 1
            l = (l[:1].upper() + l[1:]) if last else l.upper()
            ls.append(wrap(l, F("ital", px * 1.12) if last else F("heavy", px), w))
        if sum(len(x) for x in ls) * px * 1.12 <= (y1 - y0) * 0.55 or px <= 44:
            break
        px -= 2
    flat = [(ln, i == len(ls) - 1) for i, part in enumerate(ls) for ln in part]
    prof = profile.load()
    head_h = 460 if prof else 300
    total_h = head_h + 60 + len(flat) * px * 1.12
    top = y0 + max(0, (y1 - y0 - total_h) / 2)
    d = ImageDraw.Draw(img)
    if prof:
        a = ease_out(t / 0.35)
        if a > 0.02:
            s_ = 0.8 + 0.2 * spring(a, 11.0) if a < 1 else 1.0
            avatar(img, cx, top + 170 + (1 - a) * 24, 300 * s_, prof)
            hf = F("heavy", 50)
            at_ = "@" + prof["handle"]
            while width(at_, hf) > VW - 140 and hf.size / SS > 28:
                hf = F("heavy", hf.size / SS - 4)
            shadow_text(img, cx, top + 392, at_, hf, 50, anchor="mm", strength=a)
            d.text((cx * SS, (top + 392) * SS), at_, font=hf, fill=mix(BONE, INK, a), anchor="mm")
        yy = top + head_h
    else:
        be = DocuBE(img, t, cx - 500, top + 150 - 400, 1.0)
        be.icon(st["outro"]["icon"], 500, 400, 330, 0.0, dur=0.4)
        yy = top + 330
    for j, (ln, last) in enumerate(flat):
        a = ease_out((t - 0.35 - 0.12 * j) / 0.2)
        if a > 0.02:
            f_ = F("ital", px * 1.12) if last else F("heavy", px)
            shadow_text(img, cx, yy + px * 0.56 + (1 - a) * 16, ln, f_, px, anchor="mm", strength=a)
            d.text((cx * SS, (yy + px * 0.56 + (1 - a) * 16) * SS), ln, font=f_, fill=mix(ACCENT if last else BONE, INK, a), anchor="mm")
        yy += px * 1.12


def outro_frame(f):
    t = f / FPS
    img = stage(t + 9.0)
    outro_draw(img, t)
    img = add_grain(img, f)
    return g.apply_camera(img, 1.0 + 0.02 * ease(t / 2.0), 0.0, 0.0)


# ------------------------------------------------------------------ sound cues
INTRO_SFX = []
OUTRO_SFX = []


def sfx_events(clip):
    """Rare and soft. A low thud when an amount lands, a thud when a calculator answer lands, a stamp when a decision is stamped. Nothing else."""
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
        elif p["route"] == "obj" and p["obj"]["kind"] == "balance":
            evs.append((ctx.at(re.sub(r"[^A-Za-z0-9]", "", p["obj"]["amount"].split()[0]), 0.25) + 0.7, "thud", 0.36))
        elif p["route"] == "obj" and p["obj"]["kind"] == "doc":
            ws = beat_words(clip, bi)
            evs.append(((ws[-1][1] - 0.4) if ws else s0 + 0.4, "stamp", 0.40))
    return [(max(0.0, t), n, g_) for t, n, g_ in evs]


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
