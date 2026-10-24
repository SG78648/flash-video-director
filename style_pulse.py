"""style_pulse.py - the Pulse style, made for attention.

Why it exists. Lee and Flash are calm explainers (a small picture, a few words, a lot of empty page). That is fine for people who already
want the answer and wrong for a cold audience of 9 to 5 workers, who decide in the first second whether to stay. Pulse borrows from what
short-form motion-graphics editors do (the Natt Jongsala / Ali Abdaal school and brand promos) and from how screens look on a phone.
  - the hook is a full-bleed accent colour with every word on screen at frame 1, then a hard cut into a dark, MOVING body (two blurred
    colour blobs drift behind everything, a huge ghost word of the beat sits under the picture);
  - one thing at a time and big, as a STICKER (a bright badge with a thick white ring and a shadow that springs in with a spin), amounts as
    giant numbers;
  - maths is shown on a real looking CALCULATOR (the keys are pressed as the sum is typed, the answer pops), rent as a stack of payment
    NOTIFICATIONS that slide in with a running total;
  - ONE kinetic caption at a time, 2 to 3 big words, the spoken word on a highlighter box, numbers in the accent colour, negative words red;
  - every beat starts with a transition (a whip pan with a horizontal smear, a zoom through, a glitch on negative beats, or a flash), a punch-in
    and a sound (whoosh, key clicks, a till for money);
  - no stock photos, no dissolves, no empty page, silences cut.
It draws any script_story with the same planner and scenes as Lee, Dan and Flash (story_scenes.py) and gives the studio the same
interface as every style: OUT_DIR, segments(), frame_bytes(), prepare(), apply_to().
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
import script_story
import story_icons
import story_scenes
import streaming
import voice
from PIL import Image, ImageDraw, ImageFont

STYLE_ID = "pulse"
OUT_DIR = projects.style_dir(STYLE_ID)
VIDEO_TITLE = "pulse"
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

# ------------------------------------------------------------------ palette
ACCENT = (255, 214, 10)        # the hook colour, the spoken word, numbers
HOT = (255, 69, 58)            # negative words and beats
WHITE = (246, 246, 250)
BLACK = (8, 8, 12)
CARD = (30, 30, 44)
MUTE = (150, 150, 172)
STICKERS = [(255, 214, 10), (246, 246, 250), (255, 100, 88), (72, 225, 200), (130, 170, 255), (255, 150, 60)]
PUNCH = 0.055                  # the punch-in at the start of every beat
DRIFT = 0.03                   # the slow push-in during a beat
SHAKE = 0.006                  # how far a negative beat shakes (fraction of the page)
FLASH = 0.16                   # strength of the flash on a cut
CAPTION_SCALE = 1.0
KINETIC = True
TRANS_S = 0.17                 # length of a transition between two beats


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


def schemes():
    """(base colour, blob 1, blob 2) for the four kinds of background."""
    return [((10, 10, 17), ACCENT, (255, 90, 70)),
            ((8, 13, 38), (40, 140, 255), ACCENT),
            ((24, 9, 38), (190, 70, 255), (255, 130, 50)),
            (mix(HOT, (0, 0, 0), 0.14), HOT, (255, 150, 20))]


def apply_config(cfg=None):
    """Studio settings -> the Pulse look."""
    global ACCENT, HOT, PUNCH, DRIFT, SHAKE, FLASH, CAPTION_SCALE, KINETIC, STICKERS
    cfg = studio_config.normalize(cfg) if cfg else studio_config.load()
    p = cfg["pulse"]
    ACCENT = studio_config.rgb(p["palette"]["accent"])
    HOT = studio_config.rgb(p["palette"]["negative"])
    STICKERS = [ACCENT, (246, 246, 250), (255, 100, 88), (72, 225, 200), (130, 170, 255), (255, 150, 60)]
    PUNCH = float(p["camera"]["punch"])
    DRIFT = float(p["camera"]["drift"])
    SHAKE = float(p["camera"]["shake"])
    FLASH = float(p["camera"]["flash"])
    CAPTION_SCALE = float(p["layout"]["caption_size"])
    KINETIC = bool(p["layout"]["kinetic_caption"])
    _SPRITES.clear()
    _PLAN.clear()


# ------------------------------------------------------------------ the page
PORTRAIT = g.ASPECT == "9:16"
LANDSCAPE = g.ASPECT == "16:9"
VW, VH = {"9:16": (g.W, g.H), "1:1": (860, 860), "16:9": (1529, 860)}[g.ASPECT]       # 1:1 and 16:9 lay out on a compact page
VRW, VRH = VW * SS, VH * SS


def safe_on():
    return PORTRAIT and story_scenes.safe_area()


def vis_box():
    """(x0, y0, x1, y1) of the big picture."""
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
        return (x0 + x1) / 2, 1270 if safe_on() else 1330, x1 - x0 + 30, 110
    if LANDSCAPE:
        return VW / 2, VH * 0.84, VW - 160, 76
    return VW / 2, VH * 0.80, VW - 100, 70


# ------------------------------------------------------------------ the moving background
_SPRITES = {}


def blob(color, size):
    """A soft round pool of colour (RGBA), cached."""
    key = (color, size)
    if key not in _SPRITES:
        yy, xx = np.mgrid[0:size, 0:size]
        d = np.sqrt(((xx - size / 2) / (size / 2)) ** 2 + ((yy - size / 2) / (size / 2)) ** 2)
        a = (np.clip(1 - d, 0, 1) ** 1.6 * 0.55 * 255).astype(np.uint8)
        arr = np.zeros((size, size, 4), dtype=np.uint8)
        arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3] = color[0], color[1], color[2], a
        _SPRITES[key] = Image.fromarray(arr, "RGBA")
    return _SPRITES[key]


_GHOSTF = {}


def ghost_font(px):
    px = max(20, int(px))
    if px not in _GHOSTF:
        f = None
        for name in ("seguibl.ttf", "ariblk.ttf", "arialbd.ttf"):
            try:
                f = ImageFont.truetype(name, px)
                break
            except Exception:
                pass
        _GHOSTF[px] = f or ImageFont.load_default()
    return _GHOSTF[px]


def background(scheme_i, t, ghost=""):
    """The page: a dark base, two big blurred blobs drifting at different speeds, and under the picture a huge ghost word (7 percent white)."""
    base, c1, c2 = schemes()[scheme_i]
    w, h = VRW // 4, VRH // 4
    im = Image.new("RGB", (w, h), base)
    for col, sx, sy, ph, size in ((c1, 0.50, 0.38, 0.0, 0.95), (c2, 0.33, 0.47, 2.1, 0.85)):
        s = int(w * size)
        sp = blob(col, s)
        cx = w * (0.5 + 0.34 * math.sin(t * sx + ph))
        cy = h * (0.42 + 0.26 * math.cos(t * sy + ph * 1.7))
        im.paste(sp, (int(cx - s / 2), int(cy - s / 2)), sp)
    if ghost:
        px = int(h * 0.30 * (1.0 + 0.04 * math.sin(t * 0.8)))
        f = ghost_font(px)
        d0 = ImageDraw.Draw(Image.new("L", (8, 8)))
        tw = d0.textlength(ghost, font=f)
        if tw > w * 1.05:                                      # a long word is shrunk to the page
            f = ghost_font(int(px * w * 1.05 / tw))
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).text((w / 2, h * 0.40), ghost, fill=255, font=f, anchor="mm")
        mask = mask.rotate(-7 + 2 * math.sin(t * 0.6), resample=Image.BICUBIC)
        mask = mask.point(lambda v: int(v * 0.075))
        im.paste((255, 255, 255), (0, 0), mask)
    return im.resize((VRW, VRH), Image.BICUBIC)


# ------------------------------------------------------------------ text
_FONTS = {}


def font(px):
    px = max(8, int(round(px)))
    if px not in _FONTS:
        f = None
        for name in ("seguibl.ttf", "ariblk.ttf", "segoeuib.ttf", "arialbd.ttf"):
            try:
                f = ImageFont.truetype(name, px * SS)
                break
            except Exception:
                pass
        _FONTS[px] = f or ImageFont.load_default()
    return _FONTS[px]


_SCRATCH = None


def width(s, f):
    global _SCRATCH
    if _SCRATCH is None:
        _SCRATCH = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    return _SCRATCH.textlength(s, font=f) / SS


def put(img, x, y, s, px, fill, anchor="mm", stroke=True, stroke_fill=BLACK):
    d = ImageDraw.Draw(img)
    sw = int(round(px * 0.075 * SS)) if stroke else 0
    d.text((x * SS, y * SS), s, fill=fill, font=font(px), anchor=anchor, stroke_width=sw, stroke_fill=stroke_fill)


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


# ------------------------------------------------------------------ scenes (story_scenes primitives, heavy and popping)
class PulseBE(story_scenes.Backend):
    """The scenes are the same as in the other styles. Here colours are flipped for a dark page (ink is white, the fill of a card is a dark
    card, white is the dark text that sits on an accent fill), big icons become stickers and every element pops in with a spring."""

    def __init__(self, img, t, ox, oy, k, s0=None, first=None):
        super().__init__(t, ox, oy, k)
        self.img, self.s0, self.first = img, s0, first
        self.d = g.D2(ImageDraw.Draw(img))
        self.char_w = 22
        self.pal = {"ink": WHITE, "accent": ACCENT, "mute": MUTE, "neg": HOT, "soft": CARD, "white": BLACK}

    def color(self, name):
        return self.pal.get(name, name)

    def _tr(self, trig):
        """A cut lands on a picture, not on an empty page: the elements of the beat come a little ahead of the words."""
        if self.s0 is not None and self.first is not None:
            shift = min(1.0, max(0.0, self.first - self.s0 - 0.08))
            trig = max(self.s0 + 0.08, trig - shift)
        return super()._tr(trig)

    def _sticker(self, spec, cx, cy, s, a, name_key, rot_phase):
        """A bright round badge with a thick white ring and a shadow, the icon on it in black. It spins in and then wobbles a little."""
        L = int(s * 1.72)
        layer = Image.new("RGBA", (L * SS, L * SS), (0, 0, 0, 0))
        d = g.D2(ImageDraw.Draw(layer))
        c = L / 2
        col = STICKERS[sum(ord(ch) for ch in name_key) % len(STICKERS)]
        R = s * 0.60
        ring = (255, 255, 255, 255) if col != STICKERS[1] else (40, 40, 52, 255)
        d.ellipse([c - R * 1.06, c - R * 1.06 + s * 0.05, c + R * 1.06, c + R * 1.06 + s * 0.05], fill=(0, 0, 0, 110))           # the shadow
        d.ellipse([c - R, c - R, c + R, c + R], fill=ring)
        d.ellipse([c - R * 0.9, c - R * 0.9, c + R * 0.9, c + R * 0.9], fill=tuple(col) + (255,))
        isz = s * 0.80
        w = max(7.0, isz / 11.0)
        for ck, pts in spec:
            pp = [(c - isz / 2 + px * isz / 100.0, c - isz / 2 + py * isz / 100.0) for px, py in pts]
            d.line(pp, fill=(14, 14, 22, 255), width=w, joint="curve")
            for q in (pp[0], pp[-1]):
                d.ellipse([q[0] - w / 2, q[1] - w / 2, q[0] + w / 2, q[1] + w / 2], fill=(14, 14, 22, 255))
        ang = (1 - clamp01(a)) * -32.0 + 4.0 * math.sin(self.t * 2.1 + rot_phase)
        layer = layer.rotate(ang, resample=Image.BICUBIC)
        self.img.paste(layer, (int((cx - L / 2) * SS), int((cy - L / 2) * SS)), layer)

    def _strokes(self, spec, x, y, size, trig, dur, lw, color, accent, until, key, claim_w=1.0, claim=True):
        trig = self._tr(trig)
        if self.t < trig or (until is not None and self.t >= until):
            return
        a = clamp01((self.t - trig) / 0.34)
        sc = spring(a, 12.0) if a < 1 else 1.0
        cx, cy = self.P(x, y)
        cy += 5.0 * self.k * math.sin(self.t * 3.1 + x * 0.013)         # everything breathes a little, nothing on the page is ever still
        dev = size * self.k
        if dev >= 190:
            self._sticker(spec, cx, cy, dev * max(0.05, sc), a, str(key), x * 0.01)
            return
        s = dev * max(0.04, sc)
        ox, oy = cx - s / 2, cy - s / 2
        w = max(5.0, dev / 13.0 * max(0.4, sc))
        for ck, pts in spec:
            self._line([(ox + px * s / 100.0, oy + py * s / 100.0) for px, py in pts], self.color(color if ck == "i" else accent), w)

    def _line(self, pts, color, w):
        self.d.line(pts, fill=color, width=w, joint="curve")
        for p in (pts[0], pts[-1]):
            self.d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=color)

    def _rect(self, x0, y0, x1, y1, fill, line, w, r):
        self.d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill, outline=line, width=max(2, int(round(w * 1.25))))

    def _ellipse(self, cx, cy, r, fill, line, w):
        if r > 0.5:
            self.d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline=line, width=max(2, int(round(w * 1.25))))

    def _text(self, s, x, y, px, color, anchor, trig, dur, key):
        a = clamp01((self.t - trig) / max(0.12, dur))
        if a <= 0.02:
            return
        sc = 0.7 + 0.3 * spring(a, 12.0) if a < 1 else 1.0
        px = max(16, int(round(px * 1.08 * sc)))
        s = s.upper()
        put(self.img, x, y + 0.03 * px, s, px, mix(color, (0, 0, 0), min(1.0, a * 2.2)), "mm" if anchor == "m" else "lm", stroke=sum(color) > 330)      # dark text on an accent fill needs no outline

    def _claim(self, key, box):
        pass

    def photo_path(self, node, sp):
        return None                                        # icons, never stock photos


class _Extent(story_scenes.Backend):
    """Draws a scene to nothing and records the box it covers, so the picture can be scaled to fill the screen."""

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
        w = width(s.upper(), font(px))                           # the real width of the heavy font
        self.pts += [(x - (w / 2 if anchor == "m" else 0), y - px / 2), (x + (w / 2 if anchor == "m" else w), y + px / 2)]

    def _claim(self, key, box):
        pass

    def reserve(self, x0, y0, x1, y1):
        self.pts += [(x0, y0), (x1, y1)]

    def photo_path(self, node, sp):
        return None


# ------------------------------------------------------------------ Pulse's own scene drawers
def p_stage(be, ctx, sp):
    """The things a beat names, ONE at a time and big. The newest one fills the stage (an amount becomes a giant number, a thing a giant sticker
    with its name), the ones before it shrink into a trail of small icons along the top."""
    nodes = sp["nodes"][:4]
    be.reserve(120, 30, 880, 700)
    trigs = [ctx.at(nd.get("word"), 0.2 + 0.28 * i) for i, nd in enumerate(nodes)]
    cur = 0
    for i, tr in enumerate(trigs):
        if be.t >= tr:
            cur = i
    for i in range(cur):
        be.icon(nodes[i]["icon"], 150 + i * 120, 70, 96, trigs[i], color="mute", accent="mute")
    nd, tr = nodes[cur], trigs[cur]
    label = (nd.get("label") or "").rstrip(".")
    top = 150 if cur else 110
    if re.match(r"^[$\d]", label):
        be.icon(nd["icon"], 500, top + 120, 230, tr)
        be.text(label, 500, top + 420, fit_px(label, 800, 230), tr + be.lag(0.1), color="accent")
    else:
        be.icon(nd["icon"], 500, top + 190, 400, tr)
        if label:
            be.text(label, 500, top + 480, fit_px(label, 800, 90), tr + be.lag(0.12), color="ink")
    if nd.get("neg"):
        be.cross(500, top + 190, 130, tr + be.lag(0.4), color="neg")


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
    """A real looking calculator. The keys light up as the sum is typed, the answer pops on the display when it is spoken."""
    rows = sp["rows"][:3]
    sched = calc_times(ctx, rows)
    be.reserve(100, 10, 900, 648)
    tl0 = sched[0][2][0]
    be.rect(100, 10, 900, 648, tl0 - 0.25, fill=(10, 10, 12), line=(70, 70, 82), w=5, r=60, dur=0.30)
    cur = 0
    for i, (r, keys, times, tv) in enumerate(sched):
        if be.t >= times[0] - 0.05:
            cur = i
    r, keys, times, tv = sched[cur]
    pressed = sum(1 for tt in times if be.t >= tt)
    if be.t >= tv:                                           # the answer, big, in the accent colour
        val = r["value"].upper()
        be.text(val, 500, 112, fit_px(val, 700, 130), tv, color="accent")
        if r["unit"]:
            be.text(r["unit"], 500, 190, 38, tv + be.lag(0.12), color="mute")
    else:                                                    # what has been typed so far
        typed = fmt_typed(keys, pressed) or "0"
        be.text(typed, 500, 120, fit_px(typed, 700, 112), times[0] - 0.2, color="ink")
    cx = [230, 410, 590, 770]
    cy = [262, 340, 418, 496, 574]
    now = {keys[j] for j, tt in enumerate(times) if tt <= be.t < tt + 0.16}
    for ri, row in enumerate(_LAYOUT):
        for ci, lab in enumerate(row):
            wide = lab == "0"
            if ri == 4:
                x = (cx[0] + cx[1]) / 2 if wide else cx[ci + 1]
            else:
                x = cx[ci]
            op = lab in ("÷", "×", "−", "+", "=")
            fn = lab in ("AC", "±", "%")
            hit = lab in now
            fill = (255, 214, 120) if (op and hit) else (255, 159, 10) if op else (205, 205, 210) if (fn and hit) else (165, 165, 165) if fn else (140, 140, 146) if hit else (51, 51, 51)
            half = 170 if wide else 80
            be.rect(x - half, cy[ri] - 32, x + half, cy[ri] + 32, tl0 - 0.2, fill=fill, line=None, r=32, dur=0.25)
            if be.t >= tl0 - 0.1:
                col = (255, 255, 255) if not fn and not (op and hit) else (10, 10, 12)
                lx = x - 120 if wide else x
                px_, py_ = be.P(lx, cy[ri])
                put(be.img, px_, py_, lab, max(18, int(40 * be.k)), col, "mm", stroke=False)


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
    be.text("PER MONTH" if plus else "RENT THIS MONTH", 500, 55, 38, tt - 0.2, color="mute")
    be.text(("+" if plus else "") + f"${total:,}", 500, 140, fit_px(f"${total:,}+", 760, 170), tt - 0.1, color="accent")
    for k in appeared[-5:]:
        slot = m - 1 - k
        y0 = 235 + slot * 100
        trig = tt + k * ts
        fill = mix((245, 245, 250), (20, 20, 30), slot * 0.17)
        be.rect(70, y0, 930, y0 + 88, trig, fill=fill, line=None, r=26, dur=0.18)
        be.rect(92, y0 + 18, 144, y0 + 70, trig + be.lag(0.03), fill=(52, 199, 89), line=None, r=14, dur=0.15)
        be.text("$", 118, y0 + 44, 36, trig + be.lag(0.05), color="white")
        title = "RAISE APPROVED" if plus else "RENT RECEIVED"
        be.text(title, 168, y0 + 28, 24, trig + be.lag(0.06), anchor="l", color=(60, 60, 70))
        be.text(f"UNIT {k + 1} " + ("+" if plus else "PAID ") + f"${amt}", 168, y0 + 62, 31, trig + be.lag(0.08), anchor="l", color=(20, 20, 28))
        be.text("NOW", 880, y0 + 30, 22, trig + be.lag(0.1), color=(120, 120, 135))


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
        be.rect(60, y0, 940, y0 + rh, tr, fill="soft", line="accent", w=5, r=30)
        be.circle(140, cy, rh * 0.30, tr, fill="neg" if cross else "accent", line=None)
        if cross:
            be.cross(140, cy, rh * 0.12, tr + be.lag(0.05), color="white")
        elif sp.get("mark") == "check":
            be.check(140, cy, rh * 0.12, tr + be.lag(0.05), color="white")
        else:
            be.text(str(i + 1), 140, cy, rh * 0.30, tr + be.lag(0.05), color="white")
        label = nd["label"]
        lines = story_scenes._wrap(label, 22)[:2]
        px = fit_px(max(lines, key=len), 640, min(76, rh * 0.52 / (1.0 if len(lines) == 1 else 1.5)))
        for j, ln in enumerate(lines):
            be.text(ln, 235, cy + (j - (len(lines) - 1) / 2) * (px * 1.3), px, tr + be.lag(0.08), anchor="l", color="ink")


def p_send(be, ctx, sp):
    """Share it: a phone, an arrow, the person, and who they are, all big."""
    be.reserve(80, 80, 920, 700)
    t = ctx.at("send", 0.1)
    be.icon("phone", 220, 230, 300, t)
    be.arrow((380, 230), (600, 230), t + be.lag(0.3), color="accent", w=12)
    be.icon("person", 790, 230, 300, t + be.lag(0.5))
    for j, ln in enumerate(story_scenes._wrap(sp["label"], 16)[:3]):
        be.text(ln, 500, 480 + j * 90, fit_px(ln, 800, 84), t + be.lag(0.7), color="accent")


def p_keyword(be, ctx, sp):
    """The keyword offer: the comment box with the word GIANT, an arrow, the message."""
    be.reserve(60, 60, 940, 720)
    t0 = ctx.at("comment", 0.08)
    be.rect(70, 60, 930, 340, t0, fill="soft", line="accent", w=8, r=50)
    tw = ctx.at(sp["word"].split()[-1].lower(), 0.25)
    be.text(sp["word"], 500, 200, fit_px(sp["word"], 780, 200), tw, color="accent")
    ta = ctx.at("send", 0.55)
    be.arrow((500, 380), (500, 480), ta, color="accent", w=12)
    be.icon("mail", 500, 590, 200, ta + be.lag(0.2))
    be.text(sp["label"], 500, 730, fit_px(sp["label"], 800, 72), ta + be.lag(0.5), color="ink")


PULSE_SCENES = {"calc": p_calc, "send": p_send, "keyword": p_keyword}


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
    elif typ in PULSE_SCENES:
        PULSE_SCENES[typ](be, ctx, sp)
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


# ------------------------------------------------------------------ layout of one beat (measured once, cached)
_PLAN = {}
NEG_TYPES = ("ceiling", "income_stop", "hours")
NEG_WORDS = {"not", "never", "no", "nothing", "can't", "cannot", "don't", "won't", "isn't", "aren't", "lose", "loses", "lost", "stuck", "broke",
             "leaves", "leave", "wrong", "lying", "lie", "bet", "walk", "risk", "mold", "empty", "short", "squeeze", "collapses", "fail", "fails"}


def beat_kind(cid, idx):
    """'neg' for a negative beat, else 0, 1 or 2 (the three body backgrounds take turns)."""
    f = story()["feats"][str(cid)][idx]
    sp = story_scenes.scene_of(story(), cid, idx)
    if bool(f.get("neg")) or sp.get("type") in NEG_TYPES or bool(sp.get("neg")) or bool(sp.get("gone")):
        return "neg"
    order = sum(len(story()["feats"][str(c)]) for c in range(1, cid)) + idx
    return order % 3


def ghost_of(cid, idx):
    """The word that sits huge and faint behind the picture, an amount if the beat has one, else its longest word."""
    text = story()["feats"][str(cid)][idx]["text"]
    m = re.search(r"\$[\d,.]+(?:\s?(?:million|billion|thousand|k))?|\d[\d,.]*\s?(?:%|percent)", text, re.I)
    if m:
        return m.group(0).upper().replace(" PERCENT", "%")
    words = [w for w in re.findall(r"[A-Za-z']+", text) if len(w) >= 5]
    return max(words, key=len).upper() if words else ""


def plan_beat(cid, idx):
    key = (cid, idx)
    if key in _PLAN:
        return _PLAN[key]
    x0, y0, x1, y1 = vis_box()
    ex0, ey0, ex1, ey1, first = scene_extent(cid, idx)
    kk = max(0.5, min((x1 - x0) / (ex1 - ex0 + 40.0), (y1 - y0) / (ey1 - ey0 + 40.0), 3.0))
    ox = (x0 + x1) / 2 - kk * (ex0 + ex1) / 2
    oy = (y0 + y1) / 2 - kk * (ey0 + ey1) / 2
    kind = beat_kind(cid, idx)
    p = {"scene": (ox, oy, kk), "first": first, "kind": kind, "scheme": 3 if kind == "neg" else kind, "ghost": ghost_of(cid, idx)}
    _PLAN[key] = p
    return p


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


def word_color(w, active):
    low = re.sub(r"[^a-z']", "", w.lower())
    if re.search(r"\d", w) or w.startswith("$"):
        return ACCENT
    if low in NEG_WORDS:
        return HOT
    return WHITE


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
    pop = 0.84 + 0.16 * spring(a, 13.0) if a < 1 else 1.0
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
            col = word_color(words[i], active)
            bump = 1.0 + (0.12 * math.exp(-(t - times[i]) / 0.10) if active else 0.0)      # the spoken word kicks
            wpx = px * pop * bump
            wx, wy = xx + ws_w[j] / 2, yy + (1 - pop) * 24
            if active:                                                  # the highlighter box behind the word being spoken
                bw, bh = ws_w[j] * bump * pop + px * 0.34, wpx * 1.02
                d.rounded_rectangle([(wx - bw / 2) * SS, (wy - bh / 2) * SS, (wx + bw / 2) * SS, (wy + bh / 2) * SS], radius=int(px * 0.20 * SS),
                                    fill=HOT if col == HOT else ACCENT)
                put(img, wx, wy, words[i].upper(), wpx, WHITE if col == HOT else BLACK, "mm", stroke=False)
            else:
                put(img, wx, wy, words[i].upper(), wpx, col, "mm")
            xx += ws_w[j] + sp_w
        yy += lh


def draw_quote(img, c, idx, t, s0, f_, p):
    """A quoted belief, big, crossed out when it is the wrong one."""
    x0, y0, x1, y1 = vis_box()
    text = f_["quote"]
    lines, px = fit_lines('"' + text + '"', x1 - x0 - 40, 96 if PORTRAIT else 64, 36, 5)
    lh = px * 1.18
    ws = beat_words(c, idx)
    t_end = (ws[-1][1] + 0.3) if ws else g.clip_beats(c)[idx][1]
    a = ease_out((t - s0) / 0.16)
    if a <= 0.02:
        return
    top = (y0 + y1) / 2 - len(lines) * lh / 2
    for i, ln in enumerate(lines):
        w_total = width(ln, font(px))
        put(img, (x0 + x1) / 2, top + i * lh + lh / 2 + (1 - a) * 18, ln, px, mix(WHITE, BLACK, a), "mm")
        if t > t_end and f_.get("neg"):
            r = ease_out((t - t_end) / 0.22)
            d = ImageDraw.Draw(img)
            xa = (x0 + x1) / 2 - w_total / 2 - 10
            d.line([xa * SS, (top + i * lh + lh / 2) * SS, (xa + (w_total + 20) * r) * SS, (top + i * lh + lh / 2) * SS], fill=HOT, width=int(10 * SS))


def draw_progress(img, cid, t):
    """A thin bar along the top, the share of the video that has played."""
    try:
        total = sum(n for _nm, n in _SEGS) / FPS if _SEGS else 0
        before = (_setup()[1]) / FPS + sum((CLIPS[i].get("total_frames") or 0) for i in range(cid - 1)) / FPS
        frac = clamp01((before + t) / total) if total else 0
    except Exception:
        return
    y = VH * (0.055 if PORTRAIT else 0.02)
    d = ImageDraw.Draw(img)
    d.rectangle([0, y * SS, VRW, (y + 8) * SS], fill=mix(WHITE, BLACK, 0.10))
    d.rectangle([0, y * SS, VRW * frac, (y + 8) * SS], fill=ACCENT)


# ------------------------------------------------------------------ drawing one beat
def page_for(cid, idx, t):
    """The finished page of one beat at clip time t (background, scene, caption, progress bar), before any camera move."""
    c = CLIPS[cid - 1]
    s0, s1 = g.clip_beats(c)[idx]
    p = plan_beat(cid, idx)
    img = background(p["scheme"], t + cid * 3.7, p["ghost"])
    f_ = story()["feats"][str(cid)][idx]
    ox, oy, k = p["scene"]
    sp = story_scenes.scene_of(story(), cid, idx)
    if f_["kind"] == "quote" and sp.get("type") == "question":
        draw_quote(img, c, idx, t, s0, f_, p)
    else:
        ctx = story_scenes.Ctx(s0, s1, beat_words(c, idx), lambda kk: t_word(c, idx, kk))
        draw_scene(PulseBE(img, t, ox, oy, k, s0=s0, first=p["first"]), ctx, sp)
    draw_caption(img, c, idx, t, s0)
    draw_progress(img, cid, t)
    return img


def smear(img, amount):
    """Horizontal motion blur: the image squeezed sideways and stretched back."""
    if amount <= 0.02:
        return img
    w, h = img.size
    f = max(2, int(2 + 26 * amount))
    return img.resize((max(8, w // f), h), Image.BILINEAR).resize((w, h), Image.BILINEAR)


def transition(kind, prev, new, a):
    """The picture `a` (0 to 1) of the way through a transition into `new`. Only the whip shows the old picture sliding away. The others act on the
    new picture alone, so two captions are never blended into each other."""
    e = ease(a)
    w, h = new.size
    if kind == "whip":                                       # both pictures slide left, smeared, the new one arrives from the right
        s = smear(prev, math.sin(math.pi * a))
        n = smear(new, math.sin(math.pi * a))
        out = Image.new("RGB", (w, h), BLACK)
        out.paste(s, (-int(w * e), 0))
        out.paste(n, (int(w * (1 - e)), 0))
        return out
    if kind == "zoom":                                       # the new picture settles from big (a push through)
        z = 1.0 + 0.40 * (1 - e) ** 2
        cw, ch = w / z, h / z
        return new.crop((int((w - cw) / 2), int((h - ch) / 2), int((w + cw) / 2), int((h + ch) / 2))).resize((w, h), Image.BILINEAR)
    if kind == "glitch":                                     # colour channels pull apart and slices of the picture jump sideways
        r_, g_, b_ = new.split()
        dx = int(34 * SS * (1 - a))
        r2 = Image.new("L", new.size, 0)
        r2.paste(r_, (dx, 0))
        b2 = Image.new("L", new.size, 0)
        b2.paste(b_, (-dx, 0))
        out = Image.merge("RGB", (r2, g_, b2))
        rng = np.random.default_rng(int(a * 1000) + 7)
        for _ in range(8):
            y0 = int(rng.integers(0, h - 80 * SS))
            hh = int(rng.integers(20 * SS, 80 * SS))
            sh = int(rng.integers(-110 * SS, 110 * SS) * (1 - a))
            band = out.crop((0, y0, w, y0 + hh))
            out.paste(band, (sh, y0))
        return out
    return new                                               # "flash": a hard cut, the white pop is added by the caller


def transition_kind(cid, idx):
    p = plan_beat(cid, idx)
    if p["kind"] == "neg":
        return "glitch"
    ghost = p["ghost"]
    if ghost and re.match(r"^[$\d]", ghost):
        return "zoom"
    return ("whip", "zoom", "flash", "zoom")[(idx + cid) % 4]


def render_frame(cid, t):
    c = CLIPS[cid - 1]
    beats = g.clip_beats(c)
    idx, prog = g.local_beat(c, t)
    if idx > 0 and t < beats[idx][0]:           # the short gap between two beats: hold the one that was on screen
        idx -= 1
        prog = 1.0
    s0 = beats[idx][0]
    p = plan_beat(cid, idx)
    img = page_for(cid, idx, t)
    since = t - s0
    if idx > 0 and 0 <= since < TRANS_S:
        kind = transition_kind(cid, idx)
        prev = page_for(cid, idx - 1, s0 - 0.001) if kind == "whip" else None
        img = transition(kind, prev, img, since / TRANS_S)
        if kind in ("flash", "glitch") and since < 0.085:
            img = Image.blend(img, Image.new("RGB", img.size, WHITE), FLASH * (1 - since / 0.085))
    punch = PUNCH * math.exp(-max(0.0, since) / 0.11) if idx > 0 else 0.0
    dx = SHAKE * math.sin(since * 95) * math.exp(-max(0.0, since) / 0.16) if p["kind"] == "neg" else 0.0
    scale = 1.0 + DRIFT * ease(prog) + punch
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
    top = 270 if PORTRAIT else 50
    h_avail = (VH * 0.47 if PORTRAIT else VH * 0.52)
    px = 150 if PORTRAIT else 92
    while True:
        l1, l2 = wrap(t1, font(px), w), wrap(t2, font(px), w)
        if (len(l1) + len(l2)) * px * 1.14 <= h_avail or px <= 46:
            break
        px -= 2
    return {"w": w, "top": top, "px": px, "l1": l1, "l2": l2}


def intro_frame(f, setup=None):
    total, _n, cut_t = setup or intro_setup()
    st = story()
    t = f / FPS
    L = hook_layout()
    img = Image.new("RGB", (VRW, VRH), ACCENT)
    d = g.D2(ImageDraw.Draw(img))
    cx = VW / 2
    px, lh = L["px"], L["px"] * 1.14
    stripe = mix((255, 255, 255), ACCENT, 0.10)                  # faint diagonal stripes sliding across the card
    off = (t * 90) % 160
    for xs in range(-int(VH), int(VW) + int(VH), 160):
        d.polygon([(xs + off, 0), (xs + off + 70, 0), (xs + off + 70 - VH * 0.45, VH), (xs + off - VH * 0.45, VH)], fill=stripe)
    yy = L["top"]
    for ln in L["l1"]:                                           # the whole hook is on screen from frame 1
        put(img, cx, yy + lh / 2, ln, px, BLACK, "mm", stroke=False)
        yy += lh
    for ln in L["l2"]:
        w_ = width(ln, font(px))
        d.rounded_rectangle([cx - w_ / 2 - 22, yy + 4, cx + w_ / 2 + 22, yy + lh - 2], radius=22, fill=BLACK)
        put(img, cx, yy + lh / 2 + 2, ln, px, ACCENT, "mm", stroke=False)
        yy += lh
    room_top = yy + 30
    room = (VH * 0.80 if PORTRAIT else VH * 0.90) - room_top
    if room > 150:
        size = min(room * 0.95, 560 if PORTRAIT else 330)
        be = PulseBE(img, t, VW / 2 - 500, room_top + room / 2 - 400, 1.0)
        be.icon(story_scenes.hook_icon(st), 500, 400, size * 0.8, 0.12, dur=0.5)
    punch = 0.045 * math.exp(-(t - cut_t) / 0.18) if t >= cut_t else 0.0
    beat = 0.012 * max(0.0, 1 - ((t * 1.25) % 1.0) * 5)             # a small kick about every 0.8 s so the hook is never a still
    return g.apply_camera(img, 1.0 + 0.06 * ease(t / max(0.5, total)) + punch + beat, 0.0, 0.0)


def outro_frame(f):
    t = f / FPS
    st = story()
    img = background(0, t + 40.0, "")
    x0, y0, x1, y1 = vis_box()
    cx = VW / 2
    lines = [l.upper() for l in st["outro"]["lines"]]
    w = x1 - x0 + 30
    px = 120 if PORTRAIT else 76
    while True:
        ls = [wrap(l, font(px), w) for l in lines]
        if sum(len(x) for x in ls) * px * 1.12 <= (y1 - y0) * 0.62 or px <= 44:
            break
        px -= 2
    flat = [(ln, i) for i, part in enumerate(ls) for ln in part]
    bh = 330 if PORTRAIT else 220
    total_h = bh + 60 + len(flat) * px * 1.12
    top = y0 + max(0, (y1 - y0 - total_h) / 2)
    be = PulseBE(img, t, cx - 500, top + bh / 2 - 400, 1.0)
    be.icon(st["outro"]["icon"], 500, 400, bh * 1.15, 0.0, dur=0.4)
    yy = top + bh + 60
    d = g.D2(ImageDraw.Draw(img))
    for j, (ln, part) in enumerate(flat):
        a = ease_out((t - 0.35 - 0.12 * j) / 0.2)
        if a <= 0.02:
            yy += px * 1.12
            continue
        last = j == len(flat) - 1
        w_ = width(ln, font(px))
        if last:
            d.rounded_rectangle([cx - w_ / 2 - 24, yy + 2, cx + w_ / 2 + 24, yy + px * 1.12 - 2], radius=24, fill=mix(ACCENT, BLACK, a))
        put(img, cx, yy + px * 0.56 + (1 - a) * 16, ln, px, mix(BLACK if last else WHITE, BLACK, a), "mm", stroke=not last)
        yy += px * 1.12
    return g.apply_camera(img, 1.0 + 0.02 * ease(t / 2.0), 0.0, 0.0)


# ------------------------------------------------------------------ sound cues
def sfx_events(clip):
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
        if bi > 0:
            kind = transition_kind(cid, bi)
            evs.append((s0 - 0.02, "swoosh" if kind in ("whip", "zoom") else "slam" if kind == "glitch" else "pop", 0.40))
        else:
            evs.append((s0 + 0.02, "pop", 0.34))
        if sp.get("type") == "calc":
            for r, keys, times, tv in calc_times(ctx, sp["rows"][:3]):
                for tt, k in zip(times, keys):
                    if k != "=":
                        evs.append((tt, "type", 0.30))
                evs.append((tv, "kaching" if r["value"].lstrip("-").startswith("$") else "ding", 0.42))
        elif sp.get("type") == "stack":
            for part in sp["parts"][:sp.get("show", 0)]:
                evs.append((ctx.at(re.sub(r"[^A-Za-z0-9]", "", part["value"].split()[0]), 0.4), "pop", 0.4))
        elif sp.get("type") == "stat":
            for nd in sp["nodes"]:
                evs.append((ctx.at(nd["word"], 0.2), "ding", 0.4))
        elif sp.get("type") == "count" and sp.get("tag"):
            tt = ctx.at(sp.get("tag_word"), 0.25)
            ts = min(0.14, max(0.05, (beats[bi][1] - 0.3 - tt) / max(2, int(sp["n"]))))
            for k in range(0, min(int(sp["n"]), 12)):
                evs.append((tt + k * ts, "pop" if k % 2 else "tick", 0.30))
            if sp["tag"].startswith("$"):
                evs.append((tt + min(int(sp["n"]), 12) * ts, "kaching", 0.40))
        elif sp.get("type") == "count":
            evs.append((ctx.at(sp.get("word"), 0.15), "pop", 0.4))
        if f["kind"] == "list":
            k = nwords(f.get("lead", ""))
            for item in f["items"][:6]:
                evs.append((t_word(clip, bi, k) + 0.05, "tick", 0.4))
                k += nwords(item)
        elif f["kind"] == "quote":
            ws = beat_words(clip, bi)
            end = (ws[-1][1] + 0.3) if ws else beats[bi][1]
            evs += [(end + 0.02, "slam", 0.5), (end + 0.06, "crumble", 0.3)] if f.get("neg") else [(end + 0.02, "ding", 0.45)]
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
    return render_frame(int(seg[4:]), f / FPS)


def frame_bytes(seg, f):
    return frame(seg, f).tobytes()


def _compile():
    return streaming.compile_segments(sys.modules[__name__])
