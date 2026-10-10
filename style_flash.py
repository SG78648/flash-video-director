"""style_flash.py - the Flash style: a white page, the mint-teal of the Flash bolt, and guildshore-style editing.

What the guildshore reels do (see docs/IMPROVING.md, iterations 14-15) and what Flash takes from them:
  - the hook is already on screen at frame 1, then ONE hard cut (a two-frame mint flash) to the sharper line;
  - ONE dominant caption at a time in a dark lower-third bar, words highlighted as they are spoken;
  - the picture sits on a clean white explainer card, with calm, restrained motion;
  - a beat change is a clean jump cut (a very short dissolve, not a wipe or a fade), and the camera only drifts slowly.

It draws any script_story (the same scenes and planner as Lee and Dan, see story_scenes.py) and gives the studio the
same interface as every style: OUT_DIR, segments(), frame_bytes(), prepare(), apply_to(). Without a pasted script it
shows a short sample story.
"""
import math
import os
import re
import sys
from pathlib import Path

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

STYLE_ID = "flash"
OUT_DIR = projects.style_dir(STYLE_ID)
VIDEO_TITLE = "flash"
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

# ------------------------------------------------------------------ palette (the Flash bolt: mint on white)
PAGE = (255, 255, 255)
WHITE = (255, 255, 255)
INK = (10, 42, 46)
MINT = (44, 229, 190)           # the bolt: fills, highlights, the spoken word
TEAL = (30, 178, 148)           # the same hue, darker, for strokes and small accents on white
MUTE = (118, 148, 146)
NEG = (239, 83, 80)
CARD = (238, 252, 248)
CARD_LINE = (190, 238, 226)
SOFT = (214, 246, 237)
BAR = (9, 36, 40)
DIM_TEXT = (110, 140, 140)
GRID_DOT = (222, 247, 240)
SHOW_GRID = True
KARAOKE = True
DRIFT = 0.012
CUT_S = 0.12                    # length of the dissolve at a beat change (0 = a hard cut)
FADE_IN, FADE_OUT = 0.10, 0.12  # between clips: through the white page

BOLT = [(18, 0), (35, 33), (54, 37), (7, 93), (24, 46), (0, 45)]      # the Flash bolt, traced from the logo (54 x 93)


def mix(c, bg, a):
    """`c` at fraction `a` over `bg`."""
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


def apply_config(cfg=None):
    """Studio settings -> the Flash look."""
    global MINT, TEAL, INK, NEG, CARD, CARD_LINE, SOFT, BAR, DIM_TEXT, GRID_DOT, SHOW_GRID, KARAOKE, DRIFT, CUT_S, _BG, MUTE
    cfg = studio_config.normalize(cfg) if cfg else studio_config.load()
    f = cfg["flash"]
    MINT = studio_config.rgb(f["palette"]["accent"])
    INK = studio_config.rgb(f["palette"]["ink"])
    NEG = studio_config.rgb(f["palette"]["negative"])
    TEAL = mix(MINT, (0, 40, 36), 0.78)
    CARD = mix(MINT, PAGE, 0.10)
    CARD_LINE = mix(MINT, PAGE, 0.32)
    SOFT = mix(MINT, PAGE, 0.20)
    GRID_DOT = mix(MINT, PAGE, 0.16)
    BAR = mix(INK, (0, 0, 0), 0.82)
    MUTE = mix(INK, PAGE, 0.55)
    DIM_TEXT = mix((255, 255, 255), BAR, 0.42)
    SHOW_GRID = bool(f["layout"]["show_grid"])
    KARAOKE = bool(f["layout"]["highlight_spoken"])
    DRIFT = float(f["camera"]["drift"])
    CUT_S = float(f["camera"]["cut_ms"]) / 1000.0
    _BG = None
    _PLAN.clear()


# ------------------------------------------------------------------ the page
PORTRAIT = g.ASPECT == "9:16"
LANDSCAPE = g.ASPECT == "16:9"
VW, VH = {"9:16": (g.W, g.H), "1:1": (860, 860), "16:9": (1529, 860)}[g.ASPECT]       # 1:1 and 16:9 lay out on a compact page
VRW, VRH = VW * SS, VH * SS


def safe_on():
    return PORTRAIT and story_scenes.safe_area()


def region():
    """(x0, x1, y0, y1): where the content may go."""
    if PORTRAIT:
        if safe_on():
            return story_scenes.SAFE_LEFT, VW - story_scenes.SAFE_RIGHT, 300, story_scenes.SAFE_BOTTOM_Y - 20
        return 56, VW - 56, 220, VH - 200
    if LANDSCAPE:
        return 70, VW - 70, 50, VH - 50
    return 50, VW - 50, 44, VH - 44


_BG = None


def new_page():
    global _BG
    if _BG is None:
        im = Image.new("RGB", (VRW, VRH), PAGE)
        if SHOW_GRID:
            d = g.D2(ImageDraw.Draw(im))
            step = 54 if PORTRAIT else 48
            for y in range(step // 2, VH, step):
                for x in range(step // 2, VW, step):
                    d.ellipse([x - 2.2, y - 2.2, x + 2.2, y + 2.2], fill=GRID_DOT)
        _BG = im
    return _BG.copy()


# ------------------------------------------------------------------ text
_FONTS = {}


def font(px, black=False):
    px = max(8, int(round(px)))
    key = (px, black)
    if key not in _FONTS:
        f = None
        for name in (("seguibl.ttf", "segoeuib.ttf") if black else ("segoeuib.ttf",)) + ("arialbd.ttf", "arial.ttf"):
            try:
                f = ImageFont.truetype(name, px * SS)
                break
            except Exception:
                pass
        _FONTS[key] = f or ImageFont.load_default()
    return _FONTS[key]


_SCRATCH = None


def width(s, f):
    global _SCRATCH
    if _SCRATCH is None:
        _SCRATCH = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    return _SCRATCH.textlength(s, font=f) / SS


def put(d, x, y, s, f, fill, anchor="mm"):
    d.r.text((x * SS, y * SS), s, fill=fill, font=f, anchor=anchor)


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


def fit_lines(text, maxw, px_max, px_min, max_lines, black=True):
    """The largest size at which `text` wraps into at most max_lines lines of width maxw. Returns (lines, px)."""
    px = px_max
    while True:
        lines = wrap(text, font(px, black), maxw)
        if len(lines) <= max_lines or px <= px_min:
            return lines, px
        px -= 2


def bolt(d, cx, cy, h, fill):
    """The Flash bolt, h pixels tall, centred on (cx, cy); the outline stroke rounds its corners a little, like the logo."""
    s = h / 93.0
    pts = [(cx + (x - 27) * s, cy + (y - 46.5) * s) for x, y in BOLT]
    d.polygon(pts, fill=fill)
    d.line(pts + [pts[0]], fill=fill, width=max(1.0, 3.0 * s), joint="curve")


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
    import json
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


# ------------------------------------------------------------------ scenes (story_scenes primitives, Flash palette)
class FlashBE(story_scenes.Backend):
    def __init__(self, d, t, ox, oy, k, bg=None, s0=None, first=None):
        super().__init__(t, ox, oy, k)
        self.d, self.bg, self.s0, self.first = d, bg or PAGE, s0, first
        self.char_w = 22                                   # labels are capitals: wrap them a little earlier
        self.pal = {"ink": INK, "accent": TEAL, "mute": MUTE, "neg": NEG, "soft": SOFT, "white": WHITE}

    def color(self, name):
        return self.pal.get(name, name)

    def _tr(self, trig):
        """A jump cut lands on a picture, not on an empty card: the elements of the beat come a little ahead of the words
        (the first right after the cut - at most a second early - the rest keep their order and spacing)."""
        if self.s0 is not None and self.first is not None:
            shift = min(1.0, max(0.0, self.first - self.s0 - 0.08))
            trig = max(self.s0 + 0.08, trig - shift)
        return super()._tr(trig)

    def _line(self, pts, color, w):
        self.d.line(pts, fill=color, width=w, joint="curve")
        for p in (pts[0], pts[-1]):
            self.d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=color)

    def _rect(self, x0, y0, x1, y1, fill, line, w, r):
        self.d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill, outline=line, width=max(1, int(round(w))))

    def _ellipse(self, cx, cy, r, fill, line, w):
        if r > 0.5:
            self.d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline=line, width=max(1, int(round(w))))

    def _text(self, s, x, y, px, color, anchor, trig, dur, key):
        a = clamp01((self.t - trig) / dur)
        if a <= 0.02:
            return
        px = max(16, int(round(px)))
        col = mix(color, self.bg, ease(a))
        s = s.upper()
        put(self.d, x, y + 0.03 * px, s, font(px), col, "mm" if anchor == "m" else "lm")

    def _claim(self, key, box):
        pass

    def photo_path(self, node, sp):
        return story_scenes.photo_for(node)

    def _photo(self, path, ax, ay, bx, by, q, r):
        w, h = int(round((bx - ax) * SS)), int(round((by - ay) * SS))
        if w < 8 or h < 8:
            return
        im = story_scenes.photo_image(path, w, h, int(r * SS))
        if q < 0.99:
            im = im.copy()
            im.putalpha(im.getchannel("A").point(lambda v: int(v * q)))
        self.d.r._image.paste(im, (int(round(ax * SS)), int(round(ay * SS))), im)
        self.d.rounded_rectangle([ax, ay, bx, by], radius=r, outline=INK, width=3)


def icon_at(d, t, name, cx, cy, size, trig, dur=0.5, bg=None):
    """One story icon of `size` pixels centred on (cx, cy)."""
    FlashBE(d, t, cx - 500, cy - 400, 1.0, bg).icon(name, 500, 400, size, trig, dur=dur)


# ------------------------------------------------------------------ layout of one beat (measured once, cached)
_PLAN = {}
PAD = 22                       # inside the white explainer card
GAP = 26


def caption_text(f):
    if f["kind"] == "statement":
        return f["text"]
    if f["kind"] == "quote":
        return f.get("lead") or " ".join(f["head"])
    return " ".join(f["head"]) or f.get("lead", "")


def caption_fit(text, maxw, px0, max_lines):
    """Lines of (word index, word, width) for the caption bar, at the largest size that fits."""
    toks = text.split()
    if not toks:
        return None
    padx, pady = 30, 22
    px = px0
    while True:
        f = font(px)
        sp = width(" ", f)
        lines, cur, curw = [], [], 0.0
        for i, w in enumerate(toks):
            ww = width(w, f)
            add = ww if not cur else sp + ww
            if cur and curw + add > maxw - 2 * padx:
                lines.append(cur)
                cur, curw = [(i, w, ww)], ww
            else:
                cur.append((i, w, ww))
                curw += add
        if cur:
            lines.append(cur)
        if len(lines) <= max_lines or px <= 26:
            break
        px -= 2
    lh = px * 1.3
    lw = [sum(x[2] for x in ln) + sp * (len(ln) - 1) for ln in lines]
    return {"lines": lines, "px": px, "lh": lh, "sp": sp, "lw": lw, "bw": min(maxw, max(lw) + 2 * padx), "bh": len(lines) * lh + 2 * pady,
            "n": len(toks)}


def quote_fit(text, maxw, px0):
    padx = 36
    lines, px = fit_lines(text, maxw - 2 * padx - 30, px0, 28, 4, black=False)
    lh = px * 1.3
    return {"lines": lines, "px": px, "lh": lh, "h": len(lines) * lh + 64, "w": maxw}


class _Extent(story_scenes.Backend):
    """Draws a scene to nothing and records the box it covers (in scene units), so the card can be filled."""

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

    def _line(self, pts, color, w):
        self.pts += list(pts)

    def _rect(self, x0, y0, x1, y1, fill, line, w, r):
        self.pts += [(x0, y0), (x1, y1)]

    def _ellipse(self, cx, cy, r, fill, line, w):
        self.pts += [(cx - r, cy - r), (cx + r, cy + r)]

    def _text(self, s, x, y, px, color, anchor, trig, dur, key):
        w = len(s) * px * 0.64
        self.pts += [(x - (w / 2 if anchor == "m" else 0), y - px / 2), (x + (w / 2 if anchor == "m" else w), y + px / 2)]

    def _claim(self, key, box):
        pass

    def reserve(self, x0, y0, x1, y1):
        self.pts += [(x0, y0), (x1, y1)]

    def photo_path(self, node, sp):
        return story_scenes.photo_for(node)

    def _photo(self, path, ax, ay, bx, by, q, r):
        self.pts += [(ax, ay), (bx, by)]


def scene_extent(cid, idx):
    """(x0, y0, x1, y1) of everything the scene of this beat draws, in scene units (the scene box is 1000 x 760)."""
    c = CLIPS[cid - 1]
    s0, s1 = g.clip_beats(c)[idx]
    be = _Extent()
    try:
        story_scenes.draw(be, story_scenes.Ctx(s0, s1, beat_words(c, idx), lambda kk: t_word(c, idx, kk)), story_scenes.scene_of(story(), cid, idx))
    except Exception:
        be.pts = []
    first = min(be.trigs) if be.trigs else None
    if not be.pts:
        return 0.0, 0.0, 1000.0, 760.0, first
    xs, ys = [q[0] for q in be.pts], [q[1] for q in be.pts]
    return min(xs), min(ys), max(xs), max(ys), first


def plan_beat(cid, idx):
    key = (cid, idx)
    if key in _PLAN:
        return _PLAN[key]
    f = story()["feats"][str(cid)][idx]
    kind = f["kind"]
    x0, x1, y0, y1 = region()
    W_, H_ = x1 - x0, y1 - y0
    px_cap = 50 if PORTRAIT else 36 if not LANDSCAPE else 40
    px_q = 42 if PORTRAIT else 32 if not LANDSCAPE else 36
    if LANDSCAPE:
        card_w = 800 + 2 * PAD
        col_x0, col_x1 = x0 + card_w + 50, x1
        cap = caption_fit(caption_text(f), col_x1 - col_x0, px_cap, 6)
        q = quote_fit(f["quote"], col_x1 - col_x0, px_q) if kind == "quote" else None
        k = min((H_ - 2 * PAD) / 760.0, 800 / 1000.0)
        ch = 760 * k + 2 * PAD
        card = (x0, y0 + (H_ - ch) / 2, x0 + 1000 * k + 2 * PAD, y0 + (H_ - ch) / 2 + ch)
        stack = (q["h"] if q else 0) + (cap["bh"] if cap else 0) + (GAP if q and cap else 0)
        yy = y0 + (H_ - stack) / 2
        qbox = capbox = None
        if q:
            qbox = (col_x0, yy, col_x1, yy + q["h"])
            yy += q["h"] + GAP
        if cap:
            capbox = (col_x0 + (col_x1 - col_x0 - cap["bw"]) / 2, yy, col_x0 + (col_x1 - col_x0 - cap["bw"]) / 2 + cap["bw"], yy + cap["bh"])
    else:
        cap = caption_fit(caption_text(f), W_, px_cap, 3)
        q = quote_fit(f["quote"], W_, px_q) if kind == "quote" else None
        used = (cap["bh"] + GAP if cap else 0) + (q["h"] + GAP if q else 0)
        k = min((W_ - 2 * PAD) / 1000.0, (H_ - used - 2 * PAD) / 760.0)
        stack_h = used + 760 * k + 2 * PAD
        yy = y0 + (min(110.0, max(0.0, (H_ - stack_h) * 0.3)) if PORTRAIT else 0.0)
        qbox = capbox = None
        if q:
            qbox = (x0, yy, x1, yy + q["h"])
            yy += q["h"] + GAP
        cw, ch = 1000 * k + 2 * PAD, 760 * k + 2 * PAD
        card = (x0 + (W_ - cw) / 2, yy, x0 + (W_ - cw) / 2 + cw, yy + ch)
        yy += ch + GAP + (14 if PORTRAIT else 0)
        if cap:
            cx0 = x0 + (W_ - cap["bw"]) / 2
            capbox = (cx0, yy, cx0 + cap["bw"], yy + cap["bh"])
    # the scene is enlarged to fill the card (a lone icon is shown big), never beyond 1.9 x its normal size
    ex0, ey0, ex1, ey1, first = scene_extent(cid, idx)
    iw, ih = card[2] - card[0] - 2 * PAD, card[3] - card[1] - 2 * PAD
    kk = max(0.9 * k, min(1.9 * k, iw / (ex1 - ex0 + 60.0), ih / (ey1 - ey0 + 60.0)))
    ox = card[0] + PAD + iw / 2 - kk * (ex0 + ex1) / 2
    oy = card[1] + PAD + ih / 2 - kk * (ey0 + ey1) / 2
    p = {"f": f, "kind": kind, "cap": cap, "capbox": capbox, "q": q, "qbox": qbox, "card": card, "scene": (ox, oy, kk), "first": first}
    _PLAN[key] = p
    return p


# ------------------------------------------------------------------ drawing one beat
def draw_caption(d, p, c, idx, t, s0):
    cap, box = p["cap"], p["capbox"]
    if not cap or not box:
        return
    aq = ease_out((t - s0 - 0.03) / 0.16)
    if aq <= 0.02:
        return
    x0, y0, x1, y1 = box
    y0 += (1 - aq) * 14
    y1 += (1 - aq) * 14
    d.rounded_rectangle([x0, y0, x1, y1], radius=22, fill=mix(BAR, PAGE, aq))
    ws = beat_words(c, idx)
    n = cap["n"]
    times = [ws[min(len(ws) - 1, int(i * len(ws) / n))][1] if ws else s0 + 0.2 + i * 0.25 for i in range(n)]
    acc = p["f"].get("accent") or 0 if p["kind"] == "statement" else 0
    acc_from = n - acc if acc else n + 1
    f = font(cap["px"])
    yy = y0 + 22 + cap["lh"] / 2
    for ln, lw in zip(cap["lines"], cap["lw"]):
        xx = (x0 + x1) / 2 - lw / 2
        # the highlighter behind the closing words: it appears as the first of them is spoken
        run = [w for w in ln if w[0] >= acc_from and ((not KARAOKE) or t >= times[w[0]] - 0.02)]
        if run:
            first = run[0][0]
            rx0 = xx + sum(w[2] + cap["sp"] for w in ln if w[0] < first)
            rx1 = rx0 + sum(w[2] for w in run) + cap["sp"] * (len(run) - 1)
            pa = ease_out((t - times[first]) / 0.14) if KARAOKE else 1.0
            if pa > 0.02:
                d.rounded_rectangle([rx0 - 8, yy - cap["lh"] * 0.46, rx1 + 8, yy + cap["lh"] * 0.46], radius=13, fill=mix(MINT, BAR, pa))
        for i, w, ww in ln:
            spoken = (not KARAOKE) or t >= times[i] - 0.02
            if i >= acc_from:
                pa = ease_out((t - times[i]) / 0.14) if KARAOKE else 1.0
                col = mix(INK, WHITE, pa) if spoken else DIM_TEXT
            else:
                col = WHITE if spoken else DIM_TEXT
            put(d, xx, yy + 0.03 * cap["px"], w, f, mix(col, BAR, aq), "lm")
            xx += ww + cap["sp"]
        yy += cap["lh"]


def draw_quote(d, p, c, idx, t, s0):
    q, box = p["q"], p["qbox"]
    if not q or not box:
        return
    f_ = p["f"]
    aq = ease_out((t - s0) / 0.18)
    if aq <= 0.02:
        return
    x0, y0, x1, y1 = box
    y0 += (1 - aq) * 12
    y1 += (1 - aq) * 12
    d.rounded_rectangle([x0, y0, x1, y1], radius=22, fill=mix(BAR, PAGE, aq))
    put(d, x0 + 44, y0 + 46, "“", font(96, True), mix(MINT, BAR, aq), "mm")
    lead_k = nwords(f_.get("lead", ""))
    fo = font(q["px"])
    k = lead_k
    yy = y0 + 32 + q["lh"] / 2
    ws = beat_words(c, idx)
    t_end = (ws[-1][1] + 0.3) if ws else c_beat_end(c, idx)
    sp = width(" ", fo)
    for ln in q["lines"]:
        xx = x0 + 74
        for w in ln.split():
            tw_ = t_word(c, idx, k)
            k += 1 if nwords(w) else 0
            if t >= tw_ - 0.02:
                put(d, xx, yy + 0.03 * q["px"], w, fo, WHITE, "lm")
            xx += width(w, fo) + sp
        if t > t_end and f_.get("neg"):
            r = ease_out((t - t_end) / 0.25)
            lw = width(ln, fo)
            d.line([74 + x0 - 8, yy, x0 + 74 - 8 + (lw + 16) * r, yy], fill=NEG, width=6)
        yy += q["lh"]
    if t > t_end:
        r = ease_out((t - t_end) / 0.25)
        if f_.get("neg"):
            cx, cy, s = x1 - 44, y0 + 44, 14 * r
            d.line([cx - s, cy - s, cx + s, cy + s], fill=NEG, width=8)
            d.line([cx + s, cy - s, cx - s, cy + s], fill=NEG, width=8)
        else:
            cx, cy, s = x1 - 48, y1 - 44, 15 * r
            d.line([cx - s, cy, cx - s * 0.25, cy + s * 0.8, cx + s * 1.05, cy - s * 0.8], fill=MINT, width=8, joint="curve")


def c_beat_end(c, idx):
    return g.clip_beats(c)[idx][1]


def draw_beat(img, cid, idx, t):
    """One beat of one clip on a page image."""
    d = g.D2(ImageDraw.Draw(img))
    c = CLIPS[cid - 1]
    s0, s1 = g.clip_beats(c)[idx]
    p = plan_beat(cid, idx)
    a = ease_out((t - (s0 - 0.25)) / 0.2) if idx == 0 else 1.0       # the first card of a clip eases in just before it is spoken
    if a > 0.3:
        ox, oy, k = p["scene"]
        ctx = story_scenes.Ctx(s0, s1, beat_words(c, idx), lambda kk: t_word(c, idx, kk))
        story_scenes.draw(FlashBE(d, t, ox, oy, k, s0=s0, first=p["first"]), ctx, story_scenes.scene_of(story(), cid, idx))
    draw_quote(d, p, c, idx, t, s0)
    draw_caption(d, p, c, idx, t, s0)


def beat_scale(idx, p):
    """The slow drift: in on one beat, back out on the next (so the scale is continuous across every cut)."""
    e = ease(p)
    return 1.0 + DRIFT * (e if idx % 2 == 0 else 1.0 - e)


def clip_fade(cid, t):
    try:
        total = CLIPS[cid - 1].get("total_frames") or 0
        total = total / FPS if total else (g.get_audio_duration(g.AUDIO_DIR / f"clip{cid}.mp3") + g.PAD_BEFORE.get(cid, 0.45) + g.PAD_AFTER)
    except Exception:
        return 1.0
    return ease(min(t / FADE_IN, (total - t) / FADE_OUT))


def render_frame(cid, t):
    c = CLIPS[cid - 1]
    beats = g.clip_beats(c)
    idx, prog = g.local_beat(c, t)
    if idx > 0 and t < beats[idx][0]:           # the short gap between two beats: hold the one that was on screen
        idx -= 1
        prog = 1.0
    img = new_page()
    draw_beat(img, cid, idx, t)
    s0 = beats[idx][0]
    if idx > 0 and CUT_S > 0 and 0 <= t - s0 < CUT_S:       # the jump cut: a very short dissolve from the last picture of the beat before
        prev = new_page()
        draw_beat(prev, cid, idx - 1, s0 - 0.001)
        img = Image.blend(prev, img, ease((t - s0) / CUT_S))
    out = g.apply_camera(img, beat_scale(idx, prog), 0.0, 0.0)
    a = clip_fade(cid, t)
    if a < 0.999:
        out = Image.blend(Image.new("RGB", out.size, PAGE), out, a)
    return out


# ------------------------------------------------------------------ hook
def intro_setup():
    import json
    st = story()
    path = g.TIMING_DIR / f"clip{HOOK_ID}.json"
    words = json.loads(path.read_text(encoding="utf-8"))["words"]
    k = min(len(words) - 1, st["hook_split"])
    cut_local = words[k]["start"] if words else 1.0
    hook_dur = g.get_audio_duration(g.AUDIO_DIR / f"clip{HOOK_ID}.mp3")
    total = hook_dur + g.INTRO_PAD_BEFORE + g.INTRO_PAD_AFTER
    return total, max(1, int(total * FPS)), g.INTRO_PAD_BEFORE + cut_local


def lines_block(d, lines, f, cx, y_top, lh, color, pill=None, a=1.0, bg=PAGE):
    """Centred lines; with `pill` a highlighter rectangle sits behind each line. Returns the bottom."""
    yy = y_top
    for ln in lines:
        w = width(ln, f)
        if pill is not None:
            d.rounded_rectangle([cx - w / 2 - 22, yy - 4, cx + w / 2 + 22, yy + lh - 8], radius=18, fill=mix(pill, bg, a))
        put(d, cx, yy + lh / 2 - 6, ln, f, mix(color, bg, a), "mm")
        yy += lh
    return yy


def hook_layout():
    """px, lines of both parts, and where everything sits - the same for every frame of the hook."""
    st = story()
    x0, x1, y0, y1 = region()
    w = x1 - x0 - (60 if not LANDSCAPE else 200)
    h = y1 - y0
    t1, t2 = st["hook_head"][0], st["hook_head"][1]
    # before the cut: the first part alone, as large as it will go
    px_a = {"9:16": 120, "1:1": 84, "16:9": 96}[g.ASPECT]
    la, px_a = fit_lines(t1, w, px_a, 44, 5)
    # after the cut: both parts, with room for the picture below
    px_b = {"9:16": 92, "1:1": 64, "16:9": 72}[g.ASPECT]
    while True:
        l1, l2 = wrap(t1, font(px_b, True), w), wrap(t2, font(px_b, True), w)
        if (len(l1) + len(l2)) * px_b * 1.2 + 30 <= h * 0.66 or px_b <= 40:
            break
        px_b -= 2
    return {"x0": x0, "x1": x1, "y0": y0, "y1": y1, "a": (la, px_a), "b": (l1, l2, px_b)}


def intro_frame(f, setup=None):
    total, _n, cut_t = setup or intro_setup()
    st = story()
    t = f / FPS
    L = hook_layout()
    img = new_page()
    d = g.D2(ImageDraw.Draw(img))
    cx = (L["x0"] + L["x1"]) / 2
    cut_f = int(cut_t * FPS)
    h = L["y1"] - L["y0"]
    if f < cut_f:
        lines, px = L["a"]
        lh = px * 1.2
        top = L["y0"] + (h * 0.8 - len(lines) * lh) / 2 + 10
        lines_block(d, lines, font(px, True), cx, top, lh, INK)
    else:
        l1, l2, px = L["b"]
        lh = px * 1.2
        ft = font(px, True)
        text_h = (len(l1) + len(l2)) * lh + 22
        top = L["y0"] + max(0.0, (h - text_h - min(520, h * 0.4)) * 0.35)
        yy = lines_block(d, l1, ft, cx, top, lh, INK)
        yy = lines_block(d, l2, ft, cx, yy + 22, lh, INK, pill=MINT)
        room = L["y1"] - yy - 30
        if room > 170:
            size = min(room * 0.8, 520 if PORTRAIT else 360)
            cy = yy + 30 + room / 2
            icon_at(d, t, story_scenes.hook_icon(st), cx, cy, size * 0.78, cut_t + 0.1, dur=0.5, bg=PAGE)
    since = f - cut_f
    if 0 <= since < 2:                                    # the hard cut: a two-frame mint flash
        d.rectangle([0, 0, VW, VH], fill=mix(MINT, PAGE, (0.55, 0.22)[since]))
    punch = 0.03 * math.exp(-(t - cut_t) / 0.25) if t >= cut_t else 0.0
    out = g.apply_camera(img, 1.0 + DRIFT * ease(t / max(0.5, total)) + punch, 0.0, 0.0)
    fade = 1 - ease_out((t - (total - 0.12)) / 0.12)
    if fade < 0.999:
        out = Image.blend(Image.new("RGB", out.size, PAGE), out, fade)
    return out


def outro_frame(f):
    t = f / FPS
    st = story()
    x0, x1, y0, y1 = region()
    cx = (x0 + x1) / 2
    img = new_page()
    d = g.D2(ImageDraw.Draw(img))
    lines = [" ".join(st["outro"]["lines"])]
    w = x1 - x0 - 60
    px = {"9:16": 96, "1:1": 64, "16:9": 72}[g.ASPECT]
    while True:
        ls = [wrap(l.upper(), font(px, True), w) for l in lines]
        if sum(len(x) for x in ls) * px * 1.2 <= (y1 - y0) * 0.5 or px <= 40:
            break
        px -= 2
    flat = [(ln, i) for i, part in enumerate(ls) for ln in part]
    bh = {"9:16": 330, "1:1": 230, "16:9": 250}[g.ASPECT]
    total_h = bh + 70 + len(flat) * px * 1.2
    top = y0 + max(0, (y1 - y0 - total_h) / 2) - (40 if PORTRAIT else 0)
    s = g.spring(clamp01(t / 0.55), k=9)
    bcy = top + bh / 2
    bolt(d, cx, bcy, bh * 0.74 * max(0.01, s), MINT)
    ft = font(px, True)
    yy = top + bh + 70
    for j, (ln, part) in enumerate(flat):
        a = ease_out((t - 0.45 - 0.14 * part) / 0.25)
        last = j == len(flat) - 1
        w_ = width(ln, ft)
        if a > 0.02:
            if last:
                d.rounded_rectangle([cx - w_ / 2 - 22, yy - 4, cx + w_ / 2 + 22, yy + px * 1.2 - 8], radius=18, fill=mix(MINT, PAGE, a))
            put(d, cx, yy + px * 0.6 - 6 + (1 - a) * 10, ln, ft, mix(INK, PAGE if not last else MINT, a), "mm")
        yy += px * 1.2
    return g.apply_camera(img, 1.0, 0.0, 0.0)


# ------------------------------------------------------------------ sound cues (a few, soft)
def sfx_events(clip):
    cid = clip["id"]
    beats = g.clip_beats(clip)
    evs = []
    if not beats:
        return evs
    for bi, f in enumerate(story()["feats"][str(cid)]):
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


def apply_to(gm):
    global OUT_DIR, _STORY, HOOK_TEXT, _SETUP
    OUT_DIR = projects.style_dir(STYLE_ID)
    _STORY = None
    _SETUP = None
    _WORDS.clear()
    _PLAN.clear()
    st = story()
    CLIPS[:] = st["clips"]
    NARR_BEATS.clear()
    NARR_BEATS.update({int(k): v for k, v in st["beats"].items()})
    PAD_BEFORE.clear()
    PAD_BEFORE.update({i: 0.5 for i in range(1, len(st["clips"]) + 1)})
    HOOK_TEXT = st["hook"]
    gm.VIDEO_TITLE = VIDEO_TITLE
    gm.CLIPS = CLIPS
    gm.NARR_BEATS = NARR_BEATS
    gm.PAD_BEFORE = PAD_BEFORE
    gm.PAD_AFTER = 0.25
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
    """Make sure narration + word timing exist in this style's folder."""
    for d in (g.OUTPUT_DIR, g.AUDIO_DIR, g.TIMING_DIR, g.VIDEO_DIR):
        d.mkdir(parents=True, exist_ok=True)
    await voice.ensure_audio(g, CLIPS, HOOK_ID, HOOK_TEXT)


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
    out.append(("outro", 2 * FPS))
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
