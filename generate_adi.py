"""generate_adi.py - "adi" visual style for the lifestyle-inflation script.

A separate, self-contained style next to generate_lifestyle.py (the "Dan Koe"
look). Same script, same narration, same 9 clips x 3 beats -- only the
visual language changes. Nothing in generate_lifestyle.py is touched, and
this style renders into its own folder (output/adi/) so the two never
overwrite each other's frames, audio mixes or videos.

Look (taken from the reference reel):
  - warm cream paper background with a faint grid, no vignette/grain/bloom
  - heavy near-black grotesque, lowercase, LEFT aligned, shown line by line
    exactly when each line is spoken
  - one orange accent + yellow highlighter chips + a green rubber stamp
  - tiny letter-spaced monospace labels and orange handwritten annotations
  - white UI cards with square corners and hard offset shadows (bug report,
    stat card, receipts), a thin hand-drawn swoosh behind the content
  - a thin orange progress line along the very bottom of the frame that
    grows across the whole video
"""
import asyncio
import json
import math
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import cooling
import studio_config

if "STICKMAN_ASPECT" not in os.environ:     # command line: follow the app's saved format
    studio_config.ensure_aspect_env()

import generate_video as g
import streaming
import voice

W, H, SS = g.W, g.H, g.SS
RW, RH = g.RW, g.RH

# ============================================================ palette
BG = (238, 236, 225)
GRID_C = (221, 219, 208)
INK = (42, 27, 19)
ORANGE = (246, 97, 27)
RED = (221, 66, 38)
YELLOW = (255, 212, 0)
BLACK = (14, 12, 10)
WHITE = (252, 250, 245)
MUTE = (150, 140, 126)
SHADOW = (210, 201, 190)
GREEN = (109, 195, 148)
CURVE = (150, 148, 140)

LM = 64                      # left margin of the type column
MAXW = W - 2 * LM            # widest line before a block shrinks
TRACK = -0.012               # tight heading tracking (em)
GRID = 84
GAP = 180                    # empty board space between two storyboard frames
MV = 120                     # vertical margin of a tile (room for the zoom-out)
P = W + GAP                  # frame pitch on the board (a multiple of GRID, so the grid is seamless)
ASPECT = g.ASPECT            # "9:16" (original), "1:1" or "16:9"
PORTRAIT = ASPECT == "9:16"
SQUARE = ASPECT == "1:1"
LANDSCAPE = ASPECT == "16:9"
ZOOM = 0.07                  # zoom-out at the middle of a pan
GHOST = 0.20                 # preview opacity of the not-yet-revealed content of the incoming frame
PAN_D_MAX = 0.42
BOB_ON = False
RENDER_WORKERS = 4           # CPU draws the tiles; the GPU does camera + encode

# derived tints (recomputed by apply_config so any palette stays readable)
DIV = (225, 219, 208)         # divider lines inside cards
TRACKBG = (235, 230, 219)     # empty progress-bar track
GRIDDOT = (226, 220, 208)     # dotted chart gridlines
ROWLINE = (214, 208, 196)     # list underlines

# configurable layout / element switches (see studio_config.SCHEMA["adi"])
HEAD_SCALE = 1.0
HEAD_DY = 0
CONTENT_DY = 0
HERO_MODE = "top-right"
HERO_SIZE = 190
SHOW_GRID = True
SHOW_THREAD = True
SHOW_PROGRESS = True
CARD_SHADOW = True
CARD_DOTS = True
INLINE_ICONS = True
MARKS_ON = True
NOTES_ON = True
STAMPS_ON = True
BLUR_SAMPLES = 13
BLUR_SHUTTER = 0.5

OUT_DIR = Path("output/adi")
SRC_DIR = Path("output")      # lifestyle's narration is reused (same script/voice)

# ============================================================ story data
VIDEO_TITLE = "lifestyle_inflation_adi"
VOICE = "en-US-GuyNeural"
RATE = "+12%"
QA_MAX_DUR = 100

CLIPS = [
    {"id": 1, "name": "The Real Reason",
     "narration": "You're not broke because you don't make enough money. "
                  "You're broke because every time you make more money, "
                  "you find a new way to spend it."},
    {"id": 2, "name": "Lifestyle Inflation",
     "narration": "You get a raise? New car. You get a bonus? New vacation. "
                  "You start making six figures? Suddenly, you need a "
                  "six figure lifestyle."},
    {"id": 3, "name": "The Excuse",
     "narration": "And then you have the audacity to say, I just need to "
                  "make more money. No. You need to stop turning every "
                  "increase in income into an increase in expenses."},
    {"id": 4, "name": "Uncomfortable Truth",
     "narration": "Because here's the uncomfortable truth. Your lifestyle "
                  "is eating the future you keep saying you want."},
    {"id": 5, "name": "Financial Freedom?",
     "narration": "You want financial freedom? But you spend every dollar "
                  "trying to look like you've already achieved it."},
    {"id": 6, "name": "Retire Early?",
     "narration": "You want to retire early? But you haven't bought a "
                  "single asset that can pay you when you stop working."},
    {"id": 7, "name": "Ask a Better Question",
     "narration": "You want to become wealthy? Then stop asking how to "
                  "make more money. Start asking how to turn the money "
                  "you make into something that pays you back."},
    {"id": 8, "name": "What We Teach",
     "narration": "That's what we teach. How to use real estate investing "
                  "to build assets, generate income, and create wealth "
                  "that doesn't depend entirely on your next paycheck."},
    {"id": 9, "name": "Two Paths",
     "narration": "Because looking rich is easy. Building wealth is the "
                  "part most people never get around to."},
]

NARR_BEATS = {
    1: ["You're not broke because you don't make enough money",
        "You're broke because every time you make more money",
        "you find a new way to spend it"],
    2: ["You get a raise New car",
        "You get a bonus New vacation",
        "You start making six figures Suddenly you need a six figure lifestyle"],
    3: ["And then you have the audacity to say I just need to make more money",
        "No",
        "You need to stop turning every increase in income into an increase in expenses"],
    4: ["Because here's the uncomfortable truth",
        "Your lifestyle is eating the future",
        "you keep saying you want"],
    5: ["You want financial freedom",
        "But you spend every dollar",
        "trying to look like you've already achieved it"],
    6: ["You want to retire early",
        "But you haven't bought a single asset",
        "that can pay you when you stop working"],
    7: ["You want to become wealthy Then stop asking how to make more money",
        "Start asking how to turn the money you make",
        "into something that pays you back"],
    8: ["That's what we teach",
        "How to use real estate investing to build assets generate income",
        "and create wealth that doesn't depend entirely on your next paycheck"],
    9: ["Because looking rich is easy",
        "Building wealth is the part",
        "most people never get around to"],
}

def beat_ends_at_pause(cid):
    """For each of a clip's 3 beats: does it end on a pause in the narration
    (, . ? ! ; :)? Derived from the original punctuated text, not from timing."""
    toks = CLIPS[cid - 1]["narration"].split()
    ni, out = 0, []
    for phrase in NARR_BEATS[cid]:
        exp = [g.norm_tok(w) for w in phrase.split() if g.norm_tok(w)]
        got = 0
        while ni < len(toks) and got < len(exp):
            if g.norm_tok(toks[ni]) == exp[got]:
                got += 1
            ni += 1
        out.append(toks[ni - 1][-1] in ",.?!;:")
    return out


def _build_panels():
    """Board frames. A camera move happens only where the narration pauses; a
    beat boundary in the middle of a sentence stays in the same frame."""
    panels, panel_of = [("intro",)], {}
    for c in CLIPS:
        cid = c["id"]
        pauses = beat_ends_at_pause(cid)
        groups = [[0]]
        for k in (1, 2):
            if pauses[k - 1]:
                groups.append([k])
            else:
                groups[-1].append(k)
        for gp in groups:
            for k in gp:
                panel_of[(cid, k)] = len(panels)
            panels.append(("beats", cid, tuple(gp)))
    panels.append(("outro",))
    return panels, panel_of


PAD_BEFORE = {i: 0.35 for i in range(1, 10)}
PAD_BEFORE[1] = 0.45
PAD_AFTER = 0.25

HOOK_ID = "hook"
HOOK_TEXT = "You're not broke. You're leaking."
OUTRO_FRAMES = 2 * g.FPS
PANELS, PANEL_OF = _build_panels()
NT = len(PANELS)


def apply_to(gm):
    """Point engine globals at this story AND at its own output folder."""
    gm.VIDEO_TITLE = VIDEO_TITLE
    gm.CLIPS = CLIPS
    gm.NARR_BEATS = NARR_BEATS
    gm.PAD_BEFORE = PAD_BEFORE
    gm.PAD_AFTER = PAD_AFTER
    gm.QA_MAX_DUR = QA_MAX_DUR
    gm.VOICE = VOICE
    gm.RATE = RATE
    gm.MUSIC_BED = None
    gm.INTRO_HOOK_ID = HOOK_ID
    gm.OUTPUT_DIR = OUT_DIR
    gm.FRAMES_DIR = OUT_DIR / "frames"
    gm.AUDIO_DIR = OUT_DIR / "audio"
    gm.TIMING_DIR = OUT_DIR / "timing"
    gm.VIDEO_DIR = OUT_DIR / "video"     # video-only segments encoded straight from the render stream
    gm.STREAM_FRAMES = True              # no PNG frames on disk
    gm.compile_video = _compile
    gm._TIMING_CACHE.clear()
    gm._WORD_P_CACHE.clear()
    gm._CAM_EVENTS_CACHE.clear()
    gm.sfx_events = sfx_events
    apply_config()


def apply_config(cfg=None):
    """Load the studio settings (from `cfg`, else the file named by
    STICKMAN_STUDIO_CONFIG, else defaults) into the module globals."""
    global BG, GRID_C, INK, ORANGE, RED, YELLOW, WHITE, SHADOW, CURVE, MUTE, BLACK
    global DIV, TRACKBG, GRIDDOT, ROWLINE, LM, MAXW, TRACK, GHOST, PAN_D_MAX, FOLLOW
    global HEAD_SCALE, HEAD_DY, CONTENT_DY, HERO_MODE, HERO_SIZE, SHOW_GRID, SHOW_THREAD
    global SHOW_PROGRESS, CARD_SHADOW, CARD_DOTS, INLINE_ICONS, MARKS_ON, NOTES_ON, STAMPS_ON
    global BLUR_SAMPLES, BLUR_SHUTTER, _TILE_BG, _GPU, _AUDIT, HEAD_RESERVE
    cfg = studio_config.normalize(cfg) if cfg else studio_config.load()
    a = cfg["adi"]
    pal, lay, cam, typ = a["palette"], a["layout"], a["camera"], a["type"]
    rgb = studio_config.rgb
    BG, GRID_C, INK = rgb(pal["bg"]), rgb(pal["grid"]), rgb(pal["ink"])
    ORANGE, RED, YELLOW = rgb(pal["accent"]), rgb(pal["negative"]), rgb(pal["highlight"])
    WHITE, SHADOW, CURVE = rgb(pal["card"]), rgb(pal["shadow"]), rgb(pal["thread"])
    MUTE, BLACK = rgb(pal["muted"]), rgb(pal["dark_chip"])
    DIV, TRACKBG, GRIDDOT = mix(WHITE, INK, 0.10), mix(WHITE, INK, 0.07), mix(WHITE, INK, 0.11)
    ROWLINE = mix(BG, INK, 0.12)
    LM = int(lay["margin"])
    MAXW = W - 2 * LM
    TRACK = float(typ["tracking"])
    HEAD_SCALE, HEAD_DY, CONTENT_DY = float(lay["headline_scale"]), int(lay["headline_dy"]), int(lay["content_dy"])
    HERO_MODE, HERO_SIZE = lay["hero"], int(lay["hero_size"])
    SHOW_GRID, SHOW_THREAD, SHOW_PROGRESS = bool(lay["show_grid"]), bool(lay["show_thread"]), bool(lay["progress_bar"])
    CARD_SHADOW, CARD_DOTS, INLINE_ICONS = bool(lay["card_shadow"]), bool(lay["card_dots"]), bool(lay["inline_icons"])
    MARKS_ON, NOTES_ON, STAMPS_ON = bool(lay["marks"]), bool(lay["notes"]), bool(lay["stamps"])
    PAN_D_MAX = float(cam["pan_ms"]) / 1000.0
    BLUR_SAMPLES = max(1, min(16, int(cam["blur_samples"])))
    BLUR_SHUTTER = float(cam["blur_shutter"])
    FOLLOW = float(cam["follow"])
    GHOST = float(cam["ghost"])
    _TILE_BG = None
    _SET.clear()
    _AUTO.clear()
    _AUDIT = None
    _build_layout()
    if _GPU not in (False, None):
        try:
            _GPU.close()
        except Exception:
            pass
    _GPU = False


def seed_audio():
    """Reuse lifestyle's already-synthesized narration + word timing (same
    script, voice and rate) instead of calling the TTS service again."""
    for sub, pat in (("audio", "clip{}.mp3"), ("timing", "clip{}.json")):
        dst_dir = OUT_DIR / sub
        dst_dir.mkdir(parents=True, exist_ok=True)
        for cid in [c["id"] for c in CLIPS] + [HOOK_ID]:
            src = SRC_DIR / sub / pat.format(cid)
            dst = dst_dir / pat.format(cid)
            if src.exists() and not dst.exists():
                shutil.copy(src, dst)


async def gen_hook_narration(gm):
    if (g.AUDIO_DIR / f"clip{HOOK_ID}.mp3").exists() and (g.TIMING_DIR / f"clip{HOOK_ID}.json").exists():
        return
    await gm.gen_audio_and_timing({"id": HOOK_ID, "narration": HOOK_TEXT})


def load_hook_timing():
    with open(g.TIMING_DIR / f"clip{HOOK_ID}.json") as fh:
        return json.load(fh)


# ============================================================ page layout per format
#
# Every scene is authored on a 1080 x 1920 "page": a headline block (+ a hero icon) in the upper part and
# the visual (card, chart, list...) in the lower part. For the other formats the page is not stretched, it
# is RE-ARRANGED. Scene code draws into named zones; a zone maps its page coordinates to the frame
# (x' = dx + s*x, y' = by + s*(y - ay)):
#
#   9:16   one zone, identity                          (the original look, pixel for pixel)
#   1:1    one zone, the whole page scaled by 0.82 on a wider virtual page (1317 wide), so the headline
#          sits left with the hero icon beside it and the card spans the width underneath
#   16:9   three zones: T (hero + headline) fills the left half at full size, V (cards, charts, lists) is
#          centred in the right half at 0.9, C (the one-word "NO." beat) is centred on the whole frame

class Zone:
    def __init__(self, name, vw, s, dx, ay, by, rect, direct=False):
        self.name, self.vw, self.s, self.dx, self.ay, self.by = name, vw, s, dx, ay, by
        self.rect, self.direct = rect, direct      # rect: where the zone lands on the page (real px)


ZONES = {}
ZALIAS = {}
HEAD_RESERVE = 0          # width kept free beside the headline for the hero icon (1:1 only)
SQ_S, SQ_AY, SQ_BY = 0.82, 420.0, 48.0
LS_T_AY, LS_V_S, LS_V_AY = 40.0, 0.90, 1250.0
SCENE_DY = {("16:9", "outro"): -90.0}      # {(format, scene key): virtual px} nudges for individual scenes (positive = down)


def _build_layout():
    global ZONES, ZALIAS, HEAD_RESERVE
    full = (-GAP / 2, -MV, W + GAP / 2, H + MV)
    HEAD_RESERVE = 0
    if PORTRAIT:
        ZONES = {"ALL": Zone("ALL", W, 1.0, 0.0, 0.0, 0.0, full, direct=True)}
        ZALIAS = {"T": "ALL", "V": "ALL", "C": "ALL"}
    elif SQUARE:
        ZONES = {"ALL": Zone("ALL", W / SQ_S, SQ_S, 0.0, SQ_AY, SQ_BY, full)}
        ZALIAS = {"T": "ALL", "V": "ALL", "C": "ALL"}
        HEAD_RESERVE = 0 if HERO_MODE == "off" else int(HERO_SIZE + 50)
    else:
        half = W / 2
        vx = 1000 - LM * LS_V_S                     # card left edge lands at x = 1000
        ZONES = {"T": Zone("T", half, 1.0, 0.0, LS_T_AY, 0.0, (-GAP / 2, -MV, half, H + MV)),
                 "V": Zone("V", 1080, LS_V_S, vx, LS_V_AY, H / 2,
                           (half, -MV, W + GAP / 2, H + MV)),
                 "C": Zone("C", 1080, 1.0, W / 2 - 540, 880.0, H / 2, full)}
        ZALIAS = {}


_build_layout()


def to_page(zone_name, box):
    """Page (real px) box of a claim recorded in zone coordinates."""
    z = ZONES[zone_name]
    return (z.dx + z.s * box[0], z.by + z.s * (box[1] - z.ay) + CONTENT_DY,
            z.dx + z.s * box[2], z.by + z.s * (box[3] - z.ay) + CONTENT_DY)


# ============================================================ fonts / text sprites

_FONT_FILES = {"head": "arialbd.ttf", "mono": "consola.ttf", "monob": "consolab.ttf",
               "hand": "Inkfree.ttf"}
_FC = {}
_TS = {}
_ASC = {"head": 0.75, "mono": 0.75, "monob": 0.75, "hand": 0.85}
_DESC = {"head": 0.22, "mono": 0.22, "monob": 0.22, "hand": 0.32}


def clamp01(v):
    return max(0.0, min(1.0, v))


def ease_out(v):
    v = clamp01(v)
    return 1 - (1 - v) ** 3


def back_out(v, k=1.9):
    v = clamp01(v) - 1
    return 1 + (k + 1) * v ** 3 + k * v ** 2


def mix(c1, c2, a):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * a) for i in range(3))


def font(kind, px):
    key = (kind, int(round(px * SS)))
    f = _FC.get(key)
    if f is None:
        try:
            f = ImageFont.truetype(_FONT_FILES[kind], key[1])
        except Exception:
            f = ImageFont.truetype("arialbd.ttf", key[1])
        _FC[key] = f
    return f


def text_w(kind, px, s, track=0.0):
    f = font(kind, px)
    return f.getlength(s) / SS + track * px * max(0, len(s) - 1)


def text_sprite(s, kind, px, color, track):
    key = (s, kind, round(px, 2), color, track)
    hit = _TS.get(key)
    if hit is not None:
        return hit
    f = font(kind, px)
    pad = 8
    w = text_w(kind, px, s, track)
    asc = int(px * (_ASC[kind] + 0.3)) + pad
    desc = int(px * (_DESC[kind] + 0.2)) + pad
    im = Image.new("RGBA", (int((w + 2 * pad) * SS) + 6, (asc + desc) * SS), color + (0,))
    dr = ImageDraw.Draw(im)
    ox, oy = pad * SS, asc * SS
    if track == 0:
        dr.text((ox, oy), s, font=f, fill=color + (255,), anchor="ls")
    else:
        step = track * px * SS
        for i, ch in enumerate(s):
            xi = f.getlength(s[:i + 1]) - f.getlength(ch) + step * i
            dr.text((ox + xi, oy), ch, font=f, fill=color + (255,), anchor="ls")
    _TS[key] = (im, ox, oy)
    return _TS[key]


def _composite(dst, spr, x, y):
    dw, dh = dst.size
    w, h = spr.size
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dw, x + w), min(dh, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    crop = spr.crop((x0 - x, y0 - y, x1 - x, y1 - y))
    if dst.mode == "RGBA":
        region = dst.crop((x0, y0, x1, y1))
        dst.paste(Image.alpha_composite(region, crop), (x0, y0))
    else:
        dst.paste(crop.convert("RGB"), (x0, y0), crop.getchannel("A"))


def blit(dst, spr, dx, dy, ox, oy, alpha=1.0, scale=1.0, rot=0.0):
    """Paste `spr` so its anchor (ox,oy) lands at (dx,dy); everything in SS pixels."""
    if alpha <= 0.004:
        return
    if abs(scale - 1.0) > 1e-3:
        nw, nh = max(1, int(spr.width * scale)), max(1, int(spr.height * scale))
        spr = spr.resize((nw, nh), Image.BICUBIC)
        ox, oy = ox * scale, oy * scale
    if rot:
        cw, ch = spr.width / 2, spr.height / 2
        r = spr.rotate(rot, resample=Image.BICUBIC, expand=True)
        th = math.radians(rot)
        vx, vy = ox - cw, oy - ch
        nx = vx * math.cos(th) + vy * math.sin(th)
        ny = -vx * math.sin(th) + vy * math.cos(th)
        ox, oy = r.width / 2 + nx, r.height / 2 + ny
        spr = r
    if alpha < 0.996:
        spr = spr.copy()
        spr.putalpha(spr.getchannel("A").point(lambda v: int(v * alpha)))
    _composite(dst, spr, int(round(dx - ox)), int(round(dy - oy)))


# ============================================================ canvas

class Canvas:
    """Draws in page coordinates onto either the full page or a local layer
    (ox,oy is the layer's page-space origin). Records layout claims."""

    def __init__(self, img, t, ox=0.0, oy=0.0, rec=None, group=None, ghost=0.0, zone="ALL", vw=None, zones=None):
        self.img, self.t, self.ox, self.oy = img, t, ox, oy
        self.rec, self.group, self.ghost = rec, group, ghost
        self.zone = zone                        # the zone this canvas draws into (claims are recorded in it)
        self.vw = W if vw is None else vw       # page width of that zone: use it instead of W for centring / right edges
        self.zones = zones                      # ZoneSet on a scene canvas; None on a card layer
        self.cur = "V"                          # logical zone (T / V / C) currently selected
        self.claim_dy = 0.0                     # per-scene nudge (virtual px), applied to claim boxes
        self.head_top = None                    # y of the first headline of the scene (the hero icon follows it in 1:1)
        self.d = g.D2(ImageDraw.Draw(img)) if img is not None else None

    @property
    def maxw(self):
        """Widest block that fits this zone between the margins."""
        return self.vw - 2 * LM

    def use(self, name):
        """Switch to logical zone `name` (T = hero + headline, V = visuals, C = centred beat); returns the old one."""
        prev = self.cur
        if self.zones is not None:
            self.cur = name
            z = ZALIAS.get(name, name)
            if z != self.zone:
                self.zones.activate(self, z)
        return prev

    def claim(self, key, box, group=None):
        if self.rec is not None:
            b = tuple(box)
            if self.claim_dy:
                b = (b[0], b[1] + self.claim_dy, b[2], b[3] + self.claim_dy)
            self.rec.append((key, b, group if group is not None else self.group, self.zone))

    def _pts(self, pts):
        return [(x - self.ox, y - self.oy) for x, y in pts]

    def rect(self, x0, y0, x1, y1, fill=None, outline=None, width=1):
        self.d.rectangle([x0 - self.ox, y0 - self.oy, x1 - self.ox, y1 - self.oy],
                         fill=fill, outline=outline, width=width)

    def rrect(self, x0, y0, x1, y1, r, fill=None, outline=None, width=1):
        self.d.rounded_rectangle([x0 - self.ox, y0 - self.oy, x1 - self.ox, y1 - self.oy],
                                 radius=r, fill=fill, outline=outline, width=width)

    def ellipse(self, cx, cy, r, fill=None, outline=None, width=1):
        self.d.ellipse([cx - r - self.ox, cy - r - self.oy, cx + r - self.ox, cy + r - self.oy],
                       fill=fill, outline=outline, width=width)

    def line(self, pts, color, width, dots=True):
        if len(pts) < 2:
            return
        self.d.line(self._pts(pts), fill=color, width=width, joint="curve")
        if dots:
            r = width / 2
            for p in (pts[0], pts[-1]):
                self.ellipse(p[0], p[1], r, fill=color)

    def arc(self, cx, cy, r, a0, a1, color, width):
        self.d.arc([cx - r - self.ox, cy - r - self.oy, cx + r - self.ox, cy + r - self.oy],
                   a0, a1, fill=color, width=width)

    def poly(self, pts, fill):
        self.d.polygon(self._pts(pts), fill=fill)

    def text(self, x, y, s, kind="head", px=40, color=None, anchor="l", track=0.0,
             trig=None, dur=0.16, rise=16, alpha=1.0, rot=0.0, scale=1.0,
             key=None, claim=True):
        color = INK if color is None else color
        q = 1.0
        ghosting = False
        if trig is not None:
            if self.t < trig:
                if self.ghost <= 0.01:
                    return None
                ghosting = True
            else:
                q = ease_out((self.t - trig) / dur)
        w = text_w(kind, px, s, track)
        x0 = x if anchor == "l" else (x - w / 2 if anchor == "m" else x - w)
        spr, ox, oy = text_sprite(s, kind, px, color, track)
        blit(self.img, spr, (x0 - self.ox) * SS, (y + (1 - q) * rise - self.oy) * SS, ox, oy,
             alpha=alpha * (self.ghost if ghosting else min(1.0, q * 1.8)), scale=scale, rot=rot)
        if claim and not ghosting:
            self.claim(key or s, (x0, y - _ASC[kind] * px, x0 + w, y + _DESC[kind] * px))
        return x0, w


class ZoneSet:
    """The drawing surfaces of one board tile: the tile itself (9:16) or one transparent overlay per zone that
    is scaled and pasted onto the tile when the scene is finished."""

    def __init__(self, tile, scene_dy=0.0):
        self.tile, self.scene_dy, self.imgs = tile, scene_dy, {}

    def activate(self, cv, name):
        z = ZONES[name]
        if name not in self.imgs:
            if z.direct:
                self.imgs[name] = self.tile
            else:
                rw = max(1, round((z.rect[2] - z.rect[0]) / z.s * SS))
                rh = max(1, round((z.rect[3] - z.rect[1]) / z.s * SS))
                self.imgs[name] = Image.new("RGBA", (rw, rh), (0, 0, 0, 0))
        cv.img = self.imgs[name]
        cv.d = g.D2(ImageDraw.Draw(cv.img))
        cv.zone, cv.vw = name, z.vw
        cv.ox = (z.rect[0] - z.dx) / z.s
        cv.oy = z.ay + (z.rect[1] - z.by - CONTENT_DY) / z.s - self.scene_dy

    def flush(self):
        for name, img in self.imgs.items():
            z = ZONES[name]
            if z.direct:
                continue
            rw, rh = round((z.rect[2] - z.rect[0]) * SS), round((z.rect[3] - z.rect[1]) * SS)
            if img.size != (rw, rh):
                img = img.resize((rw, rh), Image.LANCZOS)
            self.tile.paste(img, (round((z.rect[0] + GAP / 2) * SS), round((z.rect[1] + MV) * SS)), img)


@contextmanager
def zone(cv, name):
    prev = cv.use(name)
    try:
        yield
    finally:
        cv.use(prev)


@contextmanager
def layer(cv, key, x, y, w, h, trig, rot=0.0, dur=0.22, rise=24, margin=34,
          bob=0.0, scale0=0.965, alpha=1.0, group=None):
    """Draw a card/chip/stamp into its own RGBA layer, then composite it with
    a pop-in (fade + rise + tiny scale) and optional tilt."""
    ghosting = False
    if cv.t < trig:
        if cv.ghost <= 0.01:
            yield None
            return
        ghosting, q = True, 1.0
    else:
        q = ease_out((cv.t - trig) / dur)
    if not BOB_ON:
        bob = 0.0
    m = margin
    lay = Image.new("RGBA", (int((w + 2 * m) * SS), int((h + 2 * m) * SS)), (0, 0, 0, 0))
    lc = Canvas(lay, cv.t, ox=x - m, oy=y - m, rec=cv.rec, group=group or key, ghost=0.0,
                zone=cv.zone, vw=cv.vw)
    lc.claim_dy = cv.claim_dy
    yield lc
    cx = x + w / 2 - cv.ox
    cy = y + h / 2 - cv.oy + (1 - q) * rise + bob * math.sin(cv.t * 2.1)
    blit(cv.img, lay, cx * SS, cy * SS, lay.width / 2, lay.height / 2,
         alpha=alpha * (cv.ghost if ghosting else min(1.0, q * 1.8)),
         scale=scale0 + (1 - scale0) * q, rot=rot)


# ============================================================ background / progress

_BG_IMG = None
_TL = None


def bg_image():
    global _BG_IMG
    if _BG_IMG is None:
        im = Image.new("RGB", (RW, RH), BG)
        dr = ImageDraw.Draw(im)
        for x in range(GRID // 2, W, GRID):
            dr.line([x * SS, 0, x * SS, RH], fill=GRID_C, width=SS)
        for y in range(GRID // 2, H, GRID):
            dr.line([0, y * SS, RW, y * SS], fill=GRID_C, width=SS)
        _BG_IMG = im
    return _BG_IMG.copy()


def _hook_frames():
    hook_dur = g.get_audio_duration(g.AUDIO_DIR / f"clip{HOOK_ID}.mp3")
    return max(1, int((hook_dur + g.INTRO_PAD_BEFORE + g.INTRO_PAD_AFTER) * g.FPS))


def timeline():
    """(start frame of each segment, total frames) -- drives the progress line."""
    global _TL
    if _TL is None:
        offs = {"intro": 0}
        cur = _hook_frames()
        for c in CLIPS:
            dur = g.get_audio_duration(g.AUDIO_DIR / f"clip{c['id']}.mp3")
            offs[c["id"]] = cur
            cur += max(1, int((dur + PAD_BEFORE.get(c["id"], 0.45) + PAD_AFTER) * g.FPS))
        offs["outro"] = cur
        _TL = (offs, cur + OUTRO_FRAMES)
    return _TL


def progress_frac(seg, frame_idx):
    if not SHOW_PROGRESS:
        return 0.0
    offs, total = timeline()
    return clamp01((offs[seg] + frame_idx + 1) / total)


def draw_progress(out, seg, frame_idx):
    frac = progress_frac(seg, frame_idx)
    if frac > 0:
        ImageDraw.Draw(out).rectangle([0, H - 9, int(W * frac), H], fill=ORANGE)


# ============================================================ keys + audit registry

_KEYS = set()


def K(c, bi, word):
    """Absolute clip time at which `word` is spoken inside beat `bi`."""
    _KEYS.add((c["id"], bi, g.norm_tok(word)))
    return g.beat_word_t(c, bi, word)


def S(c, bi, frac=0.0):
    return g.beat_abs(c, bi, frac)


def _word_in_beat(c, bi, word):
    bs, be = g.clip_beats(c)[bi]
    pad = PAD_BEFORE.get(c["id"], 0.45)
    with open(g.TIMING_DIR / f"clip{c['id']}.json") as fh:
        words = json.load(fh)["words"]
    for w in words:
        ct = pad + w["start"]
        if bs - 0.01 <= ct <= be - 0.01 and g.norm_tok(w["word"]) == word:
            return True
    return False


# ============================================================ components

def head(cv, lines, y_top, **kw):
    """Headline block: drawn in the T zone (left column in 16:9). See _head for the arguments."""
    with zone(cv, "T"):
        if cv.head_top is None:
            cv.head_top = y_top + HEAD_DY
        return _head(cv, lines, y_top, **kw)


def _head(cv, lines, y_top, px=112, lead=1.05, x=None, hl=None, strike=None, anchor="l",
          dur=0.17, marks=None):
    """Stacked left-aligned statement. lines: [(str | [(text,color)...], trig)].
    hl: [(line, seg, trig)] yellow highlighter wipe behind a segment.
    strike: [(line, trig, color)] line struck through. Returns bottom y."""
    x = LM if x is None else x
    px = px * HEAD_SCALE
    y_top = y_top + HEAD_DY
    norm = []
    for ln, trig in lines:
        segs = [(ln, INK)] if isinstance(ln, str) else ln
        norm.append((segs, trig))
    widest = max(sum(text_w("head", px, s, TRACK) for s, _ in segs) for segs, _ in norm)
    maxw = cv.maxw - HEAD_RESERVE
    if widest > maxw:
        px = px * maxw / widest
    px = int(px)
    for i, (segs, trig) in enumerate(norm):
        base = y_top + 0.76 * px + i * lead * px
        lw = sum(text_w("head", px, s, TRACK) for s, _ in segs)
        xx = x if anchor == "l" else (cv.vw / 2 - lw / 2)
        cur = xx
        for si, (s, col) in enumerate(segs):
            sw = text_w("head", px, s, TRACK)
            for (hli, hsi, htrig) in (hl or []):
                if hli == i and hsi == si and cv.t >= htrig:
                    q = ease_out((cv.t - htrig) / 0.3)
                    cv.rect(cur - 8, base - 0.72 * px, cur - 8 + (sw + 16) * q,
                            base + 0.2 * px, fill=YELLOW)
            cv.text(cur, base, s, "head", px, col, trig=trig, track=TRACK, dur=dur, key=f"head{i}_{si}")
            for (mli, msi, mkind, mtrig, mcol) in (marks or []):
                if mli == i and msi == si:
                    mark(cv, mkind, cur, cur + sw - (px * 0.05 if mkind == "circle" else 0), base, px, mtrig, mcol)
            cur += sw
        for (sli, strig, scol) in (strike or []):
            if sli == i and cv.t >= strig:
                q = ease_out((cv.t - strig) / 0.25)
                yy = base - 0.28 * px
                cv.line([(xx - 4, yy), (xx - 4 + (lw + 8) * q, yy)], scol, max(5, px * 0.07))
    return y_top + 0.76 * px + (len(norm) - 1) * lead * px + 0.22 * px


def label(cv, x, y, s, trig, color=None, px=27, anchor="l"):
    color = MUTE if color is None else color
    cv.text(x, y, s, "mono", px, color, anchor=anchor, track=0.14, trig=trig, dur=0.2, rise=8)


def note(cv, x, y, s, trig, color=None, px=52, rot=-3.0, anchor="l"):
    if not NOTES_ON:
        return
    color = ORANGE if color is None else color
    cv.text(x, y, s, "hand", px, color, anchor=anchor, trig=trig, dur=0.25, rise=10, rot=rot)


def swoosh(cv, t0, p0, c1, c2, p1, dur=1.1):
    """Thin hand-drawn connector that draws itself, behind the content."""
    if cv.t < t0:
        return
    q = ease_out((cv.t - t0) / dur)
    pts = []
    for i in range(41):
        u = i / 40
        a = (1 - u) ** 3
        b = 3 * (1 - u) ** 2 * u
        c_ = 3 * (1 - u) * u ** 2
        d_ = u ** 3
        pts.append((a * p0[0] + b * c1[0] + c_ * c2[0] + d_ * p1[0],
                    a * p0[1] + b * c1[1] + c_ * c2[1] + d_ * p1[1]))
    n = max(2, int(len(pts) * q))
    cv.line(pts[:n], CURVE, 3, dots=False)


def chip(cv, key, x, y, s, trig, fill, fg, px=44, rot=0.0, padx=22, pady=14, group="chips"):
    w = text_w("head", px, s, TRACK) + 2 * padx
    h = px * 1.0 + 2 * pady
    with layer(cv, key, x, y, w, h, trig, rot=rot, rise=14, dur=0.18, margin=10, group=group) as l:
        if l:
            l.rrect(x, y, x + w, y + h, 14, fill=fill)
            l.text(x + padx, y + pady + 0.78 * px, s, "head", px, fg, track=TRACK, claim=False)
            l.claim(key, (x, y, x + w, y + h))
    return w, h


def card_frame(cv, x, y, w, h, header=None, hfill=None, hh=48, dots=True):
    hfill = RED if hfill is None else hfill
    dots = dots and CARD_DOTS
    cv.claim("card", (x, y, x + w + 10, y + h + 10))
    if CARD_SHADOW:
        cv.rect(x + 10, y + 10, x + w + 10, y + h + 10, fill=SHADOW)
    cv.rect(x, y, x + w, y + h, fill=WHITE, outline=INK, width=3)
    if header:
        cv.rect(x, y, x + w, y + hh, fill=hfill, outline=INK, width=3)
        cv.text(x + 24, y + hh * 0.7, header, "monob", 26, WHITE, track=0.12, claim=False)
        if dots:
            for i in range(3):
                cv.ellipse(x + w - 34 - 26 * i, y + hh / 2, 6, fill=WHITE)
    elif dots:
        for i in range(3):
            cv.ellipse(x + w - 34 - 26 * i, y + 28, 6, outline=MUTE, width=2)


def check(cv, x, y, size, color, width=9):
    cv.line([(x - size, y), (x - size * 0.25, y + size * 0.8), (x + size * 1.05, y - size * 0.8)],
            color, width)


def xmark(cv, x, y, size, color, width=9):
    cv.line([(x - size, y - size), (x + size, y + size)], color, width)
    cv.line([(x + size, y - size), (x - size, y + size)], color, width)


def stamp(cv, key, x, y, s, trig, color, px=62, rot=-7.0, alpha=0.92, group=None):
    if not STAMPS_ON:
        return 0, 0
    w = text_w("head", px, s, 0.02) + 56
    h = px * 1.0 + 38
    with layer(cv, key, x, y, w, h, trig, rot=rot, rise=0, dur=0.13, margin=20,
               scale0=1.5, alpha=alpha, group=group or key) as l:
        if l:
            l.rect(x, y, x + w, y + h, outline=color, width=6)
            l.rect(x + 9, y + 9, x + w - 9, y + h - 9, outline=color, width=2)
            l.text(x + 28, y + 19 + 0.78 * px, s, "head", px, color, track=0.02, claim=False)
            l.claim(key, (x, y, x + w, y + h))
    return w, h


def poly_prog(pts, p):
    if p <= 0:
        return []
    segs = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    target = sum(segs) * min(1.0, p)
    out, acc = [pts[0]], 0.0
    for i, sl in enumerate(segs):
        if acc + sl <= target + 1e-9:
            out.append(pts[i + 1])
            acc += sl
        else:
            r = (target - acc) / sl if sl else 0
            out.append((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * r,
                        pts[i][1] + (pts[i + 1][1] - pts[i][1]) * r))
            break
    return out


def chart(cv, x, y, w, h, series, labels=None):
    """Axis + stepped lines. series: [(normalized points, color, progress)]."""
    for gy in (0.25, 0.5, 0.75):
        yy = y + h - 8 - gy * (h - 22)
        for k in range(0, int(w), 22):
            cv.line([(x + k, yy), (x + min(k + 10, w), yy)], GRIDDOT, 2, dots=False)
    cv.line([(x, y), (x, y + h), (x + w, y + h)], INK, 4, dots=False)
    if labels:
        for i, lab in enumerate(labels):
            cv.text(x + w * i / max(1, len(labels) - 1) * 0.94, y + h + 30, lab, "mono", 20, MUTE,
                    track=0.1, claim=False)
    for pts_n, col, prog in series:
        pts = [(x + u * w, y + h - 8 - v * (h - 22)) for u, v in pts_n]
        seg = poly_prog(pts, prog)
        if len(seg) >= 2:
            cv.line(seg, col, 7)
            cv.ellipse(seg[-1][0], seg[-1][1], 11, fill=col)
            if prog >= 0.999:
                ph = (cv.t * 1.3) % 1.0
                cv.ellipse(seg[-1][0], seg[-1][1], 12 + 16 * ph, outline=mix(col, WHITE, 0.35 + 0.65 * ph), width=3)


def gauge(cv, cx, cy, r, needle, trig, color=None):
    color = INK if color is None else color
    """Semicircle dial with an orange needle (needle 0..1 = left..right)."""
    if cv.t < trig:
        return
    q = ease_out((cv.t - trig) / 0.35)
    cv.arc(cx, cy, r, 180, 360, color, 9)
    for ang in (180, 360):
        a = math.radians(ang)
        cv.ellipse(cx + math.cos(a) * r, cy + math.sin(a) * r, 6, fill=color)
    ang = math.radians(180 + 180 * needle * q)
    cv.line([(cx, cy), (cx + math.cos(ang) * r * 0.78, cy + math.sin(ang) * r * 0.78)], ORANGE, 8)
    cv.ellipse(cx, cy, 12, fill=ORANGE)
    cv.claim("gauge", (cx - r - 8, cy - r - 8, cx + r + 8, cy + 14))


# ============================================================ composite cards

def stat_card(cv, key, x, y, w, h, trig, header, big, big_color, series=None, sub=None):
    with layer(cv, key, x, y, w, h, trig, bob=3.0) as l:
        if not l:
            return
        card_frame(l, x, y, w, h)
        l.text(x + 28, y + 52, header, "mono", 24, MUTE, track=0.1, claim=False)
        chart(l, x + 36, y + 84, w * 0.50, h - 130, series or [])
        l.text(x + w - 40, y + h * 0.72, big, "head", 190, big_color, anchor="r", claim=False)
        if sub:
            l.text(x + w - 40, y + h - 30, sub, "mono", 22, MUTE, anchor="r", track=0.12, claim=False)
        l.claim("stat", (x, y, x + w, y + h))


def quote_card(cv, key, x, y, w, trig, lines, dim=1.0, cross=None, hl=None, close=True, tape=True):
    """White 'pasted note' card holding quoted copy (+ optional x / tape)."""
    px = 50
    h = 52 + len(lines) * 66 + 24
    with layer(cv, key, x, y, w, h, trig, alpha=dim, bob=2.0) as l:
        if not l:
            return h
        card_frame(l, x, y, w, h, dots=False)
        for i, ln in enumerate(lines):
            by = y + 56 + 44 + i * 66
            if hl and hl[0] == i and cv.t >= hl[1]:
                q = ease_out((cv.t - hl[1]) / 0.3)
                hx0 = x + 30 + text_w("head", px, hl[2], TRACK)
                hw = text_w("head", px, hl[3], TRACK)
                l.rect(hx0 - 6, by - 38, hx0 - 6 + (hw + 12) * q, by + 10, fill=YELLOW)
            l.text(x + 30, by, ln, "head", px, INK, track=TRACK, claim=False)
        if close:
            col = RED if (cross is not None and cv.t >= cross) else MUTE
            xmark(l, x + w - 38, y + 36, 11, col, 6)
        if tape:
            l.rect(x + 28, y - 16, x + 150, y + 14, fill=(255, 205, 60, 190))
        l.claim("quote", (x, y, x + w + 10, y + h + 10))
        if cross is not None and cv.t >= cross:
            q = ease_out((cv.t - cross) / 0.25)
            for i, ln in enumerate(lines):
                by = y + 56 + 44 + i * 66
                lw = text_w("head", px, ln, TRACK)
                l.line([(x + 24, by - 15), (x + 24 + (lw + 12) * q, by - 15)], RED, 7)
    return h


# ============================================================ graphics library
#
# Hand-drawn line icons (100x100 design box, ink strokes + orange accents) that
# draw themselves on, hero illustrations for the empty top-right area of a
# frame, and marker-style marks (circle / underline) for key words.

def _circ(cx, cy, r, a0=0, a1=360, n=32):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def _rr(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


ICONS = {
    "coin": [("i", _circ(50, 50, 40)), ("i", _circ(50, 50, 29)), ("a", [(50, 34), (50, 66)]),
             ("a", [(60, 40), (42, 40), (42, 50), (58, 50), (58, 60), (40, 60)])],
    "bars": [("i", [(12, 88), (90, 88)]), ("i", _rr(20, 62, 36, 88)), ("i", _rr(44, 46, 60, 88)),
             ("i", _rr(68, 28, 84, 88)), ("a", [(16, 50), (46, 30), (60, 38), (88, 8)]),
             ("a", [(72, 8), (88, 8), (88, 24)])],
    "wallet": [("i", _rr(10, 30, 90, 82)), ("i", [(10, 30), (22, 16), (78, 16), (86, 30)]),
               ("i", _rr(60, 46, 90, 66)), ("a", _circ(74, 56, 4)),
               ("a", [(24, 88), (24, 96)]), ("a", [(44, 90), (44, 99)]), ("a", [(64, 88), (64, 95)])],
    "car": [("i", [(6, 64), (6, 52), (20, 48), (32, 30), (66, 30), (80, 46), (94, 52), (94, 64), (6, 64)]),
            ("i", _circ(28, 66, 10)), ("i", _circ(72, 66, 10)),
            ("a", [(36, 37), (62, 37), (72, 46), (30, 46), (36, 37)])],
    "plane": [("i", [(8, 52), (92, 10), (62, 90), (48, 60), (8, 52)]), ("i", [(48, 60), (92, 10)]),
              ("a", [(4, 70), (18, 66)]), ("a", [(14, 84), (32, 78)])],
    "house": [("i", [(12, 48), (50, 14), (88, 48)]), ("i", [(22, 42), (22, 86), (78, 86), (78, 42)]),
              ("i", [(44, 86), (44, 62), (58, 62), (58, 86)]),
              ("a", [(80, 8), (80, 26)]), ("a", [(71, 17), (89, 17)])],
    "bubble": [("i", [(12, 14), (88, 14), (88, 62), (48, 62), (28, 84), (30, 62), (12, 62), (12, 14)]),
               ("a", _circ(32, 38, 3.5, n=10)), ("a", _circ(50, 38, 3.5, n=10)), ("a", _circ(68, 38, 3.5, n=10))],
    "warning": [("i", [(50, 10), (92, 86), (8, 86), (50, 10)]), ("a", [(50, 36), (50, 62)]),
                ("a", _circ(50, 74, 2.5, n=8))],
    "hourglass": [("i", [(24, 12), (76, 12), (52, 50), (76, 88), (24, 88), (48, 50), (24, 12)]),
                  ("a", [(36, 80), (64, 80)]), ("a", [(50, 54), (50, 74)])],
    "padlock": [("i", _rr(22, 46, 78, 90)), ("i", [(34, 46), (34, 30)] + _circ(50, 30, 16, 180, 330, n=16)),
                ("a", _circ(50, 62, 5, n=12)), ("a", [(50, 67), (50, 78)])],
    "bag": [("i", [(20, 34), (80, 34), (88, 90), (12, 90), (20, 34)]), ("i", _circ(50, 34, 16, 180, 360, n=16)),
            ("a", [(70, 54), (70, 72)]), ("a", [(61, 63), (79, 63)])],
    "clock": [("i", _circ(50, 50, 40)), ("i", [(50, 14), (50, 20)]), ("i", [(50, 80), (50, 86)]),
              ("i", [(14, 50), (20, 50)]), ("i", [(80, 50), (86, 50)]),
              ("a", [(50, 50), (50, 24)]), ("a", [(50, 50), (68, 60)])],
    "bldg": [("i", _rr(24, 12, 76, 90)), ("i", _rr(34, 24, 44, 34)), ("i", _rr(56, 24, 66, 34)),
             ("i", _rr(34, 44, 44, 54)), ("i", _rr(56, 44, 66, 54)),
             ("a", [(44, 90), (44, 72), (56, 72), (56, 90)])],
    "bulb": [("i", _circ(50, 40, 26)), ("i", [(40, 68), (60, 68)]), ("i", [(42, 76), (58, 76)]),
             ("i", [(46, 84), (54, 84)]), ("a", [(44, 50), (50, 38), (56, 50)]),
             ("a", [(50, 2), (50, 9)]), ("a", [(16, 12), (22, 18)]), ("a", [(84, 12), (78, 18)]),
             ("a", [(6, 40), (13, 40)]), ("a", [(87, 40), (94, 40)])],
    "sprout": [("i", [(50, 90), (50, 46)]), ("i", [(50, 62), (30, 58), (18, 40), (36, 42), (50, 58)]),
               ("i", [(50, 48), (70, 44), (82, 26), (62, 28), (50, 44)]), ("a", [(24, 90), (76, 90)])],
    "watch": [("i", _rr(32, 30, 68, 70)), ("i", [(38, 30), (40, 10), (60, 10), (62, 30)]),
              ("i", [(38, 70), (40, 90), (60, 90), (62, 70)]), ("a", [(50, 50), (50, 40)]),
              ("a", [(50, 50), (58, 54)])],
    "bottle": [("i", [(44, 6), (56, 6), (56, 26), (66, 44), (66, 94), (34, 94), (34, 44), (44, 26), (44, 6)]),
               ("a", _rr(38, 58, 62, 78)), ("a", _circ(74, 18, 2.5, n=8))],
    "key": [("i", _circ(28, 50, 16)), ("i", _circ(28, 50, 6)), ("i", [(44, 50), (92, 50)]),
            ("a", [(76, 50), (76, 64)]), ("a", [(86, 50), (86, 60)])],
    "fork": [("i", [(26, 8), (26, 34)]), ("i", [(38, 8), (38, 34)]), ("i", [(50, 8), (50, 34)]),
             ("i", [(26, 34), (30, 44), (46, 44), (50, 34)]), ("i", [(38, 44), (38, 92)]),
             ("a", [(72, 8), (72, 92)]), ("a", [(72, 8), (84, 22), (84, 52), (72, 52)])],
}


def _plen(pts):
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def icon(cv, name, cx, cy, size, trig, color=None, accent=None, dur=0.6, key=None, claim=True):
    """Line icon that draws itself on, stroke after stroke, starting at `trig`."""
    if cv.t < trig or (not INLINE_ICONS and key != "hero"):
        return
    color = INK if color is None else color
    accent = ORANGE if accent is None else accent
    q = ease_out((cv.t - trig) / dur)
    spec = ICONS[name]
    sc = size / 100.0
    ox, oy = cx - size / 2, cy - size / 2
    total = sum(_plen(pts) for _k, pts in spec)
    target, acc = total * q, 0.0
    lw = max(3.5, size / 24.0)
    for ck, pts in spec:
        if acc >= target:
            break
        ln = _plen(pts)
        seg = poly_prog([(ox + x * sc, oy + y * sc) for x, y in pts],
                        clamp01((target - acc) / ln) if ln > 0 else 1.0)
        if len(seg) >= 2:
            cv.line(seg, color if ck == "i" else accent, lw)
        acc += ln
    if claim:
        cv.claim(key or f"icon_{name}", (ox, oy, ox + size, oy + size))


def hero(cv, name, trig, color=None, accent=None, side=None, beside=False, big=None):
    """Large illustration in the free zone above the text (top-right / top-left / off)."""
    if HERO_MODE == "off":
        return
    if big:                          # a large illustration centred in the visual zone (16:9 closing frame)
        with zone(cv, "V"):
            icon(cv, name, cv.vw / 2, LS_V_AY, big, trig, color=color, accent=accent, dur=0.7, key="hero")
        return
    with zone(cv, "T"):
        right = (HERO_MODE == "top-right" and not LANDSCAPE) or SQUARE   # 1:1: beside the headline, on the right; 16:9: above its left edge
        if side:
            right = side == "right"
        beside = beside or SQUARE
        cx = (cv.vw - LM - HERO_SIZE / 2) if right else (LM + HERO_SIZE / 2)
        if beside:
            cy = (cv.head_top if cv.head_top is not None else 560) + HERO_SIZE / 2 + 10
        else:
            cy = 330
        icon(cv, name, cx, cy, HERO_SIZE, trig, color=color, accent=accent, dur=0.7, key="hero")


def mark(cv, kind, x0, x1, base, px, trig, color):
    """Marker-pen circle or scribble underline around a piece of text."""
    if cv.t < trig or not MARKS_ON:
        return
    q = ease_out((cv.t - trig) / 0.45)
    lw = max(5, px * 0.045)
    if kind == "underline":
        n = 28
        pts = [(x0 - 4 + (x1 - x0 + 8) * i / n, base + 0.19 * px + 5 * math.sin(i * 0.9)) for i in range(n + 1)]
        cv.line(pts[:max(2, int(n * q) + 1)], color, lw)
    else:
        cx, cy = (x0 + x1) / 2, base - 0.30 * px
        rx, ry = (x1 - x0) / 2 + 0.24 * px, 0.64 * px
        n = 56
        pts = []
        for i in range(n + 1):
            th = math.radians(-115 + 385 * i / n)
            wob = 1 + 0.025 * math.sin(3 * th) + 0.02 * (i / n)
            pts.append((cx + rx * wob * math.cos(th), cy + ry * wob * math.sin(th)))
        cv.line(pts[:max(2, int(n * q) + 1)], color, lw)


# ============================================================ scenes

def draw1(cv, t):
    c = CLIPS[0]
    idx, p = _beat(c, t)
    if idx == 0:
        head(cv, [("you're not broke", K(c, 0, "youre")),
                  ("because you don't", K(c, 0, "because")),
                  ([("make enough ", INK), ("money.", ORANGE)], K(c, 0, "make"))],
             y_top=560, marks=[(2, 1, "circle", K(c, 0, "money") + 0.12, ORANGE)])
        hero(cv, "coin", S(c, 0, 0.06))
        gauge(cv, LM + 130, 1330, 120, 0.82, K(c, 0, "enough"))
        label(cv, LM + 290, 1300, "INCOME: FINE", K(c, 0, "enough") + 0.15, MUTE)
        note(cv, LM + 290, 1362, "(that's not it)", K(c, 0, "money") + 0.1)
    else:
        if idx == 1:
            head(cv, [("every time you", K(c, 1, "every")),
                      ("make more money,", K(c, 1, "make"))], y_top=580)
            hero(cv, "bars", S(c, 1, 0.06))
        else:
            head(cv, [("you find a new", K(c, 2, "find")),
                      ([("way to ", INK), ("spend it.", ORANGE)], K(c, 2, "spend"))], y_top=580)
            hero(cv, "wallet", K(c, 2, "spend"))
        ip = clamp01((t - S(c, 1, 0.1)) / max(0.2, S(c, 1, 0.95) - S(c, 1, 0.1)))
        sp = clamp01((t - S(c, 2, 0.05)) / max(0.2, S(c, 2, 0.8) - S(c, 2, 0.05)))
        inc = [(0, .18), (.22, .18), (.28, .45), (.52, .45), (.58, .72), (.8, .72), (.86, .96), (1, .96)]
        spd = [(0, .12), (.30, .12), (.36, .39), (.60, .39), (.66, .66), (.88, .66), (.94, .90), (1, .90)]
        x, y, w, h = LM, 1020, cv.maxw, 400
        with layer(cv, "chart", x, y, w, h, S(c, 1, 0.0), bob=3.0) as l:
            if l:
                card_frame(l, x, y, w, h)
                l.text(x + 28, y + 52, "MONTHLY CASH FLOW", "mono", 24, MUTE, track=0.1, claim=False)
                chart(l, x + 40, y + 84, 590, h - 130,
                      [(inc, INK, ip), (spd, ORANGE, sp if idx == 2 else 0)],
                      labels=["JAN", "APR", "JUL", "OCT"])
                l.ellipse(x + 668, y + 104, 10, fill=INK)
                l.text(x + 690, y + 114, "income", "mono", 26, INK, claim=False)
                l.ellipse(x + 668, y + 150, 10, fill=ORANGE)
                l.text(x + 690, y + 160, "spending", "mono", 26, ORANGE, claim=False)
                if idx == 2 and t >= K(c, 2, "spend") + 0.15:
                    left = int(1200 * (1 - ease_out((t - K(c, 2, "spend") - 0.15) / 0.4)))
                    l.text(x + w - 40, y + h - 60, f"${left:,}", "head", 120, RED if left == 0 else INK,
                           anchor="r", claim=False)
                    l.text(x + w - 40, y + h - 188, "LEFT OVER", "mono", 24, MUTE, anchor="r",
                           track=0.12, claim=False)
                l.claim("chart", (x, y, x + w + 10, y + h + 10))
        if idx == 2:
            stamp(cv, "spent", LM + 560, 1000, "SPENT", K(c, 2, "spend") + 0.25, RED, px=64,
                  rot=-8, group="chart")


def draw2(cv, t):
    c = CLIPS[1]
    idx, p = _beat(c, t)
    if idx == 0:
        head(cv, [("raise?", K(c, 0, "raise")),
                  ([("new car.", ORANGE)], K(c, 0, "car"))], y_top=490, px=170, lead=1.0)
        hero(cv, "car", K(c, 0, "car"))
    elif idx == 1:
        head(cv, [("bonus?", K(c, 1, "bonus")),
                  ([("new vacation.", ORANGE)], K(c, 1, "vacation"))], y_top=490, px=150, lead=1.0)
        hero(cv, "plane", K(c, 1, "vacation"))
    else:
        head(cv, [("six figures?", K(c, 2, "figures")),
                  ("suddenly you need", K(c, 2, "suddenly")),
                  ([("a six-figure ", INK), ("lifestyle.", ORANGE)], K(c, 2, "lifestyle"))],
             y_top=490, px=104, lead=1.04)
        hero(cv, "house", K(c, 2, "lifestyle"))
    rows = [("RAISE", "new car", "-$800/mo", K(c, 0, "car") + 0.15),
            ("BONUS", "new vacation", "-$2,400", K(c, 1, "vacation") + 0.15),
            ("SIX FIGURES", "six-figure lifestyle", "-$4,100/mo", K(c, 2, "lifestyle") + 0.15)]
    x, y, w, h = LM, 1130, cv.maxw, 130 + 3 * 92
    with layer(cv, "ledger", x, y, w, h, S(c, 0, 0.0), bob=3.0) as l:
        if l:
            card_frame(l, x, y, w, h, header="!! WHERE THE RAISE WENT", hfill=ORANGE)
            for i, (a, b, amt, tr) in enumerate(rows):
                if t < tr:
                    continue
                by = y + 48 + 84 + i * 92
                icon(l, ("car", "plane", "house")[i], x + 64, by - 4, 58, tr, dur=0.45, claim=False)
                l.text(x + 116, by - 20, a, "mono", 20, MUTE, track=0.1, trig=tr, claim=False)
                l.text(x + 116, by + 22, b, "head", 40, INK, track=TRACK, trig=tr, claim=False)
                l.text(x + w - 30, by + 4, amt, "head", 40, ORANGE, anchor="r", trig=tr + 0.08, claim=False)
                if i < 2:
                    l.line([(x + 24, by + 34), (x + w - 24, by + 34)], DIV, 2, dots=False)
            l.claim("ledger", (x, y, x + w + 10, y + h + 10))


def draw3(cv, t):
    c = CLIPS[2]
    idx, _p = _beat(c, t)
    bs1 = g.clip_beats(c)[1][0]
    if idx == 0:
        head(cv, [("the audacity", K(c, 0, "audacity")),
                  ("to say:", K(c, 0, "say"))], y_top=530)
        hero(cv, "bubble", K(c, 0, "audacity"))
        quote_card(cv, "excuse", LM, 880, cv.maxw, K(c, 0, "just"),
                   ["i just need to", "make more money."], cross=None)
        note(cv, LM + 40, 1230, "(every time)", K(c, 0, "money") + 0.1)
    elif idx == 1:
        with zone(cv, "C"):
            label(cv, cv.vw / 2, 600, "ONE LOUD", bs1, MUTE, anchor="m")
            q = back_out((t - bs1) / 0.28, 2.2)
            cv.text(cv.vw / 2, 1010, "NO.", "head", 400, RED, anchor="m", trig=bs1, dur=0.18, rise=0,
                    scale=max(0.5, 0.78 + 0.22 * q), key="no")
            note(cv, cv.vw / 2, 1160, "not more money.", bs1 + 0.45, INK, 60, -3, anchor="m")
    else:
        head(cv, [("stop turning", K(c, 2, "stop")),
                  ("every raise into", K(c, 2, "every")),
                  ([("bigger expenses.", ORANGE)], K(c, 2, "expenses"))], y_top=530, px=108)
        hero(cv, "bars", K(c, 2, "income"))
        x, y, w, h = LM, 1010, cv.maxw, 250
        with layer(cv, "bug", x, y, w, h, K(c, 2, "income") - 0.1, bob=3.0) as l:
            if l:
                card_frame(l, x, y, w, h, header="!! LIFESTYLE BUG", hfill=RED)
                l.text(x + 30, y + 48 + 80, "income goes up.", "head", 58, INK, track=TRACK,
                       trig=K(c, 2, "income"), claim=False)
                l.text(x + 30, y + 48 + 80 + 76, "expenses follow.", "head", 58, ORANGE, track=TRACK,
                       trig=K(c, 2, "expenses"), claim=False)
                l.claim("bug", (x, y, x + w + 10, y + h + 10))
        stamp(cv, "stop", LM + 600, 1215, "STOP IT", K(c, 2, "expenses") + 0.3, ORANGE, px=60,
              rot=7, group="bug")


def draw4(cv, t):
    c = CLIPS[3]
    idx, p = _beat(c, t)
    if idx == 0:
        hb = head(cv, [("here's the", K(c, 0, "heres")),
                       ("uncomfortable", K(c, 0, "uncomfortable")),
                       ("truth.", K(c, 0, "truth"))], y_top=530, px=124,
                  hl=[(2, 0, K(c, 0, "truth") + 0.05)])
        hero(cv, "warning", S(c, 0, 0.05))
        with zone(cv, "T"):
            note(cv, LM + 4, 1090 if PORTRAIT else hb + 75, "(sorry.)", K(c, 0, "truth") + 0.12)
    else:
        if idx == 1:
            head(cv, [("your lifestyle", K(c, 1, "your")),
                      ("is eating", K(c, 1, "eating")),
                      ([("the future.", ORANGE)], K(c, 1, "future"))], y_top=530, px=118,
                 marks=[(2, 0, "underline", K(c, 1, "future") + 0.1, INK)])
        else:
            head(cv, [("the future", S(c, 2, 0.0)),
                      ("you keep saying", K(c, 2, "keep")),
                      ([("you want.", ORANGE)], K(c, 2, "want"))], y_top=530, px=118)
        hero(cv, "hourglass", S(c, 1, 0.06))
        eat = K(c, 1, "eating")
        drain = ease_out(clamp01((t - eat) / 1.7))
        pct = int(round(100 - 88 * drain))
        x, y, w, h = LM, 1020, cv.maxw, 330
        with layer(cv, "future", x, y, w, h, S(c, 1, 0.0), bob=3.0) as l:
            if l:
                card_frame(l, x, y, w, h, header="YOUR FUTURE FUND", hfill=INK)
                l.text(x + 32, y + 48 + 150, f"{pct}%", "head", 160, ORANGE if pct < 60 else INK,
                       claim=False)
                bx0, bx1, by0 = x + 32, x + w - 32, y + h - 62
                l.rect(bx0, by0, bx1, by0 + 26, fill=TRACKBG, outline=INK, width=3)
                l.rect(bx0, by0, bx0 + (bx1 - bx0) * pct / 100, by0 + 26, fill=ORANGE)
                l.claim("future", (x, y, x + w + 10, y + h + 10))
        if idx == 2:
            note(cv, LM + 520, 1440, "still waiting.", K(c, 2, "want") + 0.3, INK, 56, -4)


def draw5(cv, t):
    c = CLIPS[4]
    idx, p = _beat(c, t)
    if idx == 0:
        head(cv, [("you want", K(c, 0, "want")),
                  ("financial", K(c, 0, "financial")),
                  ([("freedom?", ORANGE)], K(c, 0, "freedom"))], y_top=530, px=128,
             marks=[(2, 0, "circle", K(c, 0, "freedom") + 0.15, INK)])
        hero(cv, "padlock", K(c, 0, "freedom"))
    elif idx == 1:
        head(cv, [("but you spend", K(c, 1, "spend")),
                  ([("every dollar.", ORANGE)], K(c, 1, "dollar"))], y_top=570, px=118)
    else:
        head(cv, [("trying to look", K(c, 2, "trying")),
                  ("like you've", K(c, 2, "like")),
                  ([("already made it.", ORANGE)], K(c, 2, "achieved"))], y_top=530, px=112)
    if idx >= 1:
        hero(cv, "bag", S(c, 1, 0.06))
    x, y, w, h = LM, 1010, cv.maxw, 210
    with layer(cv, "goal", x, y, w, h, S(c, 0, 0.1), bob=3.0) as l:
        if l:
            card_frame(l, x, y, w, h)
            l.text(x + 28, y + 52, "FINANCIAL FREEDOM / PROGRESS", "mono", 24, MUTE, track=0.1, claim=False)
            bx0, bx1, by0 = x + 30, x + w - 230, y + 118
            l.rect(bx0, by0, bx1, by0 + 30, fill=TRACKBG, outline=INK, width=3)
            grow = ease_out((t - S(c, 0, 0.35)) / 0.7) if t >= S(c, 0, 0.35) else 0
            l.rect(bx0, by0, bx0 + (bx1 - bx0) * 0.04 * grow, by0 + 30, fill=ORANGE)
            l.text(x + w - 30, y + 160, "4%", "head", 110, ORANGE, anchor="r", claim=False)
            l.claim("goal", (x, y, x + w + 10, y + h + 10))
    if idx >= 1:
        items = ["new watch", "designer bag", "bottle service", "car lease"]
        px_, py_ = LM, 1290
        for i, s in enumerate(items):
            tr = S(c, 1, 0.12 + 0.2 * i)
            w_ = text_w("head", 40, s, TRACK) + 56 + 46
            if px_ + w_ > cv.vw - LM:
                px_, py_ = LM, py_ + 92
            with layer(cv, f"pill{i}", px_, py_, w_, 70, tr, margin=10, group="pills") as l:
                if l:
                    l.rrect(px_, py_, px_ + w_, py_ + 70, 35, fill=WHITE, outline=INK, width=3)
                    icon(l, ("watch", "bag", "bottle", "key")[i], px_ + 40, py_ + 35, 44, tr, dur=0.4, claim=False)
                    l.text(px_ + 74, py_ + 49, s, "head", 40, INK, track=TRACK, claim=False)
                    l.claim(f"pill{i}", (px_, py_, px_ + w_, py_ + 70))
            px_ += w_ + 18
    if idx == 2:
        stamp(cv, "show", LM + 560, 1500, "FOR SHOW", K(c, 2, "achieved") + 0.25, ORANGE, px=58,
              rot=-6, group="pills")


def draw6(cv, t):
    c = CLIPS[5]
    idx, p = _beat(c, t)
    if idx == 0:
        head(cv, [("you want to", K(c, 0, "want")),
                  ([("retire early?", ORANGE)], K(c, 0, "retire"))], y_top=560, px=124)
        hero(cv, "clock", S(c, 0, 0.06))
        # age timeline
        y = 1260
        tr = K(c, 0, "early") - 0.2
        if t >= tr:
            q = ease_out((t - tr) / 0.5)
            tlw = cv.maxw - 52
            cv.line([(LM + 20, y), (LM + 20 + tlw * q, y)], INK, 6)
            for age, xx in ((25, LM + 20), (45, LM + 20 + tlw / 2), (65, LM + 20 + tlw)):
                if (xx - LM - 20) / tlw <= q:
                    cv.line([(xx, y - 18), (xx, y + 18)], INK, 5)
                    cv.text(xx, y + 64, f"AGE {age}", "mono", 28, MUTE, anchor="m", track=0.1, claim=False)
            if t >= tr + 0.35:
                cv.ellipse(LM + 20 + tlw / 2, y, 17, fill=ORANGE)
                note(cv, LM + 20 + tlw / 2 - 90, y - 104, "retire here", tr + 0.35, ORANGE, 50, -4)
            cv.claim("timeline", (LM, y - 22, LM + cv.maxw + 8, y + 90))
    else:
        if idx == 1:
            head(cv, [("but you haven't", K(c, 1, "havent")),
                      ("bought a single", K(c, 1, "bought")),
                      ([("asset.", ORANGE)], K(c, 1, "asset"))], y_top=530, px=116,
                 marks=[(2, 0, "circle", K(c, 1, "asset") + 0.1, INK)])
        else:
            head(cv, [("that can pay you", K(c, 2, "pay")),
                      ("when you stop", K(c, 2, "stop")),
                      ([("working.", ORANGE)], K(c, 2, "working"))], y_top=530, px=116)
        hero(cv, "bldg", S(c, 1, 0.06), color=MUTE, accent=MUTE)
        flat = [(0, .02), (.5, .02), (1, .02)]
        stat_card(cv, "assets", LM, 1000, cv.maxw, 360, S(c, 1, 0.0), "ASSETS OWNED / TODAY", "0", ORANGE,
                  series=[(flat, ORANGE, 1.0)], sub="ASSETS")
        if idx == 2:
            note(cv, LM + 8, 1440, "nothing coming in.", K(c, 2, "working") + 0.2, INK, 56, -3)


def draw7(cv, t):
    c = CLIPS[6]
    idx, p = _beat(c, t)
    wrong_cross = K(c, 0, "money")
    if idx == 0:
        head(cv, [("stop asking", K(c, 0, "stop")),
                  ("how to make", K(c, 0, "make")),
                  ("more money.", K(c, 0, "money"))], y_top=530, px=116,
             strike=[(2, wrong_cross + 0.3, RED)])
        hero(cv, "bubble", S(c, 0, 0.06))
    elif idx == 1:
        head(cv, [("start asking", K(c, 1, "start")),
                  ("how to turn", K(c, 1, "turn")),
                  ("the money", K(c, 1, "money")),
                  ([("you make", ORANGE)], K(c, 1, "make"))], y_top=500, px=104, lead=1.03)
    else:
        head(cv, [("into something", K(c, 2, "into")),
                  ("that pays you", K(c, 2, "pays")),
                  ([("back.", ORANGE)], K(c, 2, "back"))], y_top=500, px=104, lead=1.03)
    if idx >= 1:
        hero(cv, "bulb", S(c, 1, 0.06))
    dim = 1.0 if idx == 0 else 0.55
    quote_card(cv, "wrong", LM, 1010 if idx < 2 else 960, cv.maxw, K(c, 0, "asking"),
               ["how do i make", "more money?"], dim=dim,
               cross=wrong_cross + 0.1)
    if idx == 2:
        label(cv, LM, 1250, "THE QUESTION I ASK NOW", K(c, 2, "pays"), ORANGE)
        x, y, w, h = LM, 1280, cv.maxw, 190
        with layer(cv, "right", x, y, w, h, K(c, 2, "pays") + 0.1, bob=3.0) as l:
            if l:
                card_frame(l, x, y, w, h)
                l.rect(x + 28 + text_w("head", 52, "how do i make it ", TRACK) - 6, y + 66,
                       x + 28 + text_w("head", 52, "how do i make it pay me?", TRACK) + 4, y + 120,
                       fill=YELLOW)
                l.text(x + 28, y + 108, "how do i make it pay me?", "head", 52, INK, track=TRACK, claim=False)
                check(l, x + w - 70, y + 135, 24, ORANGE, 9)
                l.claim("right", (x, y, x + w + 10, y + h + 10))


def draw8(cv, t):
    c = CLIPS[7]
    idx, p = _beat(c, t)
    if idx == 0:
        head(cv, [("that's what", K(c, 0, "thats")),
                  ([("we teach.", ORANGE)], K(c, 0, "teach"))], y_top=560, px=130)
        # line-art building drawing itself
        tr = K(c, 0, "teach")
        if t >= tr:
            q = ease_out((t - tr) / 0.9)
            bx, by, bw, bh = LM + 20, 1450, 340, 380
            top = by - bh * q
            cv.line([(bx, by), (bx, top), (bx + bw, top), (bx + bw, by), (bx, by)], INK, 7, dots=False)
            for r_ in range(4):
                for c_ in range(3):
                    wy = by - 76 - r_ * 80
                    if wy - 40 > top:
                        wx = bx + 42 + c_ * 100
                        cv.rect(wx, wy - 38, wx + 56, wy, outline=ORANGE if (r_, c_) == (1, 1) else INK, width=5)
            label(cv, bx + bw + 40, by - 10, "REAL ESTATE", tr + 0.5, MUTE)
            cv.claim("building", (bx - 10, by - bh - 10, bx + bw + 10, by + 10))
    else:
        if idx == 1:
            head(cv, [("use real estate", K(c, 1, "real")),
                      ([("to build:", ORANGE)], K(c, 1, "build"))], y_top=530, px=118)
            hero(cv, "key", K(c, 1, "build"))
        else:
            head(cv, [("wealth that", K(c, 2, "wealth")),
                      ("doesn't depend", K(c, 2, "depend")),
                      ([("on a paycheck.", ORANGE)], K(c, 2, "paycheck"))], y_top=500, px=108)
            hero(cv, "coin", K(c, 2, "wealth"))
        rows = [("01", "assets.", K(c, 1, "assets")),
                ("02", "income.", K(c, 1, "income")),
                ("03", "wealth.", K(c, 2, "wealth") + 0.1)]
        base_y = 1120 if idx == 1 else 1130
        for i, (n, s, tr) in enumerate(rows):
            yy = base_y + i * 130
            if t >= tr:
                cv.text(LM, yy, n, "monob", 46, ORANGE, trig=tr, track=0.05, claim=True, key=f"n{i}")
                cv.text(LM + 110, yy + 12, s, "head", 92, INK, trig=tr, track=TRACK, key=f"r{i}")
                cv.line([(LM, yy + 48), (LM + cv.maxw - 12, yy + 48)], ROWLINE, 3, dots=False)
                icon(cv, ("bldg", "coin", "sprout")[i], LM + 860, yy - 24, 84, tr + 0.05, dur=0.5)


def draw9(cv, t):
    c = CLIPS[8]
    idx, p = _beat(c, t)
    if idx == 0:
        head(cv, [("looking rich", K(c, 0, "looking")),
                  ([("is easy.", ORANGE)], K(c, 0, "easy"))], y_top=530, px=130,
             marks=[(1, 0, "underline", K(c, 0, "easy") + 0.1, INK)])
        hero(cv, "bag", S(c, 0, 0.06))
    elif idx == 1:
        head(cv, [("building wealth", K(c, 1, "building")),
                  ([("is the part", ORANGE)], K(c, 1, "part"))], y_top=530, px=116)
    else:
        head(cv, [("most people", K(c, 2, "most")),
                  ("never get", K(c, 2, "never")),
                  ([("around to it.", ORANGE)], K(c, 2, "around"))], y_top=530, px=114)
    if idx >= 1:
        hero(cv, "sprout", S(c, 1, 0.06))
    x, y, w, h = LM, 1000, cv.maxw, 275
    with layer(cv, "easy", x, y, w, h, S(c, 0, 0.12), bob=3.0, alpha=1.0 if idx == 0 else 0.6) as l:
        if l:
            card_frame(l, x, y, w, h, header="LOOKING RICH", hfill=INK)
            for i, s in enumerate(["the watch", "the car", "the dinners"]):
                tr = S(c, 0, 0.25 + 0.2 * i)
                if t >= tr:
                    by = y + 48 + 62 + i * 62
                    l.text(x + 100, by, s, "head", 40, INK, track=TRACK, trig=tr, claim=False)
                    icon(l, ("watch", "car", "fork")[i], x + w - 64, by - 14, 46, tr + 0.05, dur=0.4, claim=False)
                    if t >= tr + 0.1:
                        check(l, x + 52, by - 12, 14, ORANGE, 7)
            l.claim("easy", (x, y, x + w + 10, y + h + 10))
    x2, y2, w2, h2 = LM, 1340, cv.maxw, 230
    with layer(cv, "build", x2, y2, w2, h2, S(c, 1, 0.1), bob=3.0) as l:
        if l:
            card_frame(l, x2, y2, w2, h2, header="BUILDING WEALTH", hfill=ORANGE)
            bx0, bx1, by0 = x2 + 30, x2 + w2 - 230, y2 + 110
            l.rect(bx0, by0, bx1, by0 + 30, fill=TRACKBG, outline=INK, width=3)
            grow = ease_out((t - S(c, 1, 0.3)) / 1.4) if t >= S(c, 1, 0.3) else 0
            l.rect(bx0, by0, bx0 + (bx1 - bx0) * 0.12 * grow, by0 + 30, fill=ORANGE)
            l.text(x2 + w2 - 30, y2 + 164, f"{int(round(12 * grow))}%", "head", 100, ORANGE, anchor="r", claim=False)
            l.text(x2 + 30, y2 + 192, "PROGRESS OF MOST PEOPLE", "mono", 22, MUTE, track=0.1, claim=False)
            l.claim("build", (x2, y2, x2 + w2 + 10, y2 + h2 + 10))
    if idx == 2:
        with zone(cv, "T"):
            chip(cv, "start", LM, 215 if PORTRAIT else 430, "Start today.", S(c, 2, 0.62), YELLOW, BLACK, px=52)


DRAW = {1: draw1, 2: draw2, 3: draw3, 4: draw4, 5: draw5, 6: draw6, 7: draw7, 8: draw8, 9: draw9}


# ============================================================ storyboard board + camera
#
# Every beat is its own drawn frame ("tile") on one long board. The camera
# does not cut between beats: it travels from one frame to the next along the
# board (eased pan + a slight zoom-out + motion blur), like scrubbing a
# thumbnail strip. Tiles are P=W+GAP wide and P is a multiple of the grid
# pitch, so the paper grid runs unbroken across the whole board.

_FORCE = None
_TILE_BG = None
_SET = {}
SETTLE = 60.0


def _beat(c, t):
    if _FORCE is not None:
        return _FORCE, 1.0
    return g.local_beat(c, t)


def tile_bg():
    global _TILE_BG
    if _TILE_BG is None:
        th = H + 2 * MV
        im = Image.new("RGB", (P * SS, th * SS), BG)
        dr = ImageDraw.Draw(im)
        if SHOW_GRID:
            for x in range(GAP // 2 + GRID // 2, P, GRID):
                dr.line([x * SS, 0, x * SS, th * SS], fill=GRID_C, width=SS)
            for y in range(MV + GRID // 2 - 2 * GRID, th, GRID):
                if y >= 0:
                    dr.line([0, y * SS, P * SS, y * SS], fill=GRID_C, width=SS)
        _TILE_BG = im
    return _TILE_BG.copy()


TS = 1.0 if PORTRAIT else H / 1920.0          # the thread's wiggle scales with the frame height


def seam_y(k):
    """Height of the thread where tile k meets tile k+1 (k=-1: start, k=NT-1: end)."""
    return (1120 + 110 * math.sin(k * 1.7) + 60 * math.cos(k * 0.9)) * TS


def _smooth(u):
    return u * u * (3 - 2 * u)


def thread_y(n, u):
    """Thread height (page y) at fraction u (0..1) across tile n. Horizontal
    tangent at both seams, so the line is one unbroken curve over the board."""
    y_in, y_out = seam_y(n - 1), seam_y(n)
    bump = 90 * TS * math.sin(n * 2.3 + 1.0)
    return y_in + (y_out - y_in) * _smooth(u) + bump * math.sin(math.pi * u) ** 2


def thread_board_y(bx):
    n = int(math.floor((bx + GAP / 2) / P))
    n = max(0, min(NT - 1, n))
    u = clamp01((bx + GAP / 2 - n * P) / P)
    return thread_y(n, u)


def thread(cv, n):
    """The thin thread that runs through every frame and links it to the next
    one (drawn behind the content; the seams of neighbouring tiles match)."""
    if not SHOW_THREAD:
        return
    pts = []
    for i in range(81):
        u = i / 80
        pts.append((-GAP / 2 + u * P, thread_y(n, u)))
    cv.line(pts, CURVE, 3, dots=False)


_AUTO = {}


def auto_dy(n):
    """1:1 only: how far (virtual px) to move frame n down so its settled content is vertically centred.
    Measured once per frame from its layout claims, so it is constant while the frame animates."""
    if not SQUARE:
        return 0.0
    if n not in _AUTO:
        rec = []
        make_tile(n, SETTLE, rec=rec, _auto=False)
        boxes = [to_page(zn, b) for _k, b, _gr, zn in rec]
        _AUTO[n] = 0.0
        if boxes:
            mid = (min(b[1] for b in boxes) + max(b[3] for b in boxes)) / 2
            _AUTO[n] = max(-20.0, min(150.0, H / 2 - mid)) / SQ_S
    return _AUTO[n]


def make_tile(n, t, ghost=0.0, rec=None, force=None, _auto=True):
    """Draw board frame n at clip time t. `force` pins which beat of a merged
    frame is drawn (None = whichever beat is live at t)."""
    global _FORCE
    img = tile_bg()
    thread(Canvas(img, t, ox=-GAP / 2, oy=-MV), n)           # the thread is drawn in frame coordinates, behind everything
    info = PANELS[n]
    key = "intro" if info[0] == "intro" else "outro" if info[0] == "outro" else info[1]
    zs = ZoneSet(img, SCENE_DY.get((ASPECT, key), 0.0) + (auto_dy(n) if _auto else 0.0))
    cv = Canvas(img, t, rec=rec, ghost=ghost, zone="", zones=zs)
    cv.claim_dy = zs.scene_dy
    cv.use("V")
    if info[0] == "intro":
        draw_intro(cv, t)
    elif info[0] == "outro":
        draw_outro(cv, t)
    else:
        _FORCE = force
        try:
            DRAW[info[1]](cv, t)
        finally:
            _FORCE = None
    zs.flush()
    return img


def settled_tile(n):
    if n not in _SET:
        if len(_SET) >= 3:
            _SET.pop(next(iter(_SET)))
        _SET[n] = make_tile(n, SETTLE)
    return _SET[n]


def pan_ease(u):
    u = clamp01(u)
    return u * u * u * (u * (u * 6 - 15) + 10)


def compose(tiles, left, dy=0.0):
    """Camera view of the board: W x H window whose left edge is at board x
    `left`, vertically nudged by dy (never scaled -- the move is pure x)."""
    view = Image.new("RGB", (RW, RH), BG)
    for n, img in tiles.items():
        view.paste(img, (int(round(((n * P - GAP / 2) - left) * SS)),
                         int(round((-MV - dy) * SS))))
    return view.resize((W, H), Image.LANCZOS)


FOLLOW = 0.6


def camera_samples(n_from, n_to, t, st, d):
    """Camera path for one frame: board x of the view's left edge and a small
    vertical drift (following the thread). One sample at rest; 13 sub-frame
    samples while travelling (motion blur). x motion is exact."""
    xa = n_from * P + W / 2
    xb = n_to * P + W / 2
    ya, yb = thread_board_y(xa), thread_board_y(xb)

    def one(tt):
        u = clamp01((tt - st) / d) if d > 0 else 1.0
        e = pan_ease(u)
        xc = xa + (xb - xa) * e
        dev = thread_board_y(xc) - (ya + (yb - ya) * e)
        return xc - W / 2, max(-100.0, min(100.0, FOLLOW * dev))
    u = clamp01((t - st) / d) if d > 0 else 1.0
    if 0.0 < u < 1.0:
        shutter, n_s = BLUR_SHUTTER / g.FPS, max(2, BLUR_SAMPLES)
        if not PORTRAIT and BLUR_SAMPLES > 1:
            # a wide board moves further per frame: add samples so the blur stays smooth instead of ghosting
            travel = abs(one(t + shutter / 2)[0] - one(t - shutter / 2)[0])
            n_s = max(n_s, min(64, int(travel / 4) + 1))
        pairs = [one(t + (j / (n_s - 1) - 0.5) * shutter) for j in range(n_s)]
        if BLUR_SAMPLES <= 1:
            pairs = [one(t)]
    else:
        pairs = [one(t)]
    return [p_[0] for p_ in pairs], [p_[1] for p_ in pairs]


def camera_frame(tiles, n_from, n_to, t, st, d):
    """CPU (PIL) version of the camera -- used for stills and as a fallback."""
    lefts, dys = camera_samples(n_from, n_to, t, st, d)
    acc = None
    for j, (lf, dy) in enumerate(zip(lefts, dys)):
        im = compose(tiles, lf, dy)
        acc = im if acc is None else Image.blend(acc, im, 1.0 / (j + 1))
    return acc


def pan_start_dur(c, k):
    """Pan window that leads into beat k. It starts inside the pause before the
    beat (never earlier than the end of the previous word) and lands on the
    first spoken word."""
    beats = g.clip_beats(c)
    bs = beats[k][0]
    if k == 0:
        d = max(0.2, min(PAN_D_MAX, bs - 0.03))
        return bs - d, d
    start = max(beats[k - 1][1] - 0.05, bs - PAN_D_MAX)
    return start, bs - start


def pan_beats(cid):
    """Beats that open a new board frame (the camera moves into them)."""
    first = {PANELS[PANEL_OF[(cid, k)]][2][0] for k in range(3)}
    return sorted(first)


def clip_cam(cid, t):
    c = CLIPS[cid - 1]
    k_act = 0
    for k in pan_beats(cid):
        st, _d = pan_start_dur(c, k)
        if t >= st:
            k_act = k
    st, d = pan_start_dur(c, k_act)
    return PANEL_OF[(cid, k_act)], k_act, st, d


def _plan_clip(cid, t):
    n_to, k_act, st, d = clip_cam(cid, t)
    u = clamp01((t - st) / d)
    if u < 1.0:
        n_from = n_to - 1
        info = PANELS[n_from]
        if info[0] == "beats" and info[1] == cid:
            from_tile = make_tile(n_from, t, force=info[2][-1])
        else:
            from_tile = settled_tile(n_from)
        tiles = {n_from: from_tile,
                 n_to: make_tile(n_to, t, ghost=GHOST * (1 - u), force=PANELS[n_to][2][0])}
    else:
        n_from = n_to
        tiles = {n_to: make_tile(n_to, t)}
    return tiles, n_from, n_to, st, d


def _plan_intro(t):
    return {0: make_tile(0, t)}, 0, 0, 0.0, 0.0


def _plan_outro(t):
    u = clamp01(t / OUTRO_PAN)
    if u < 1.0:
        tiles = {NT - 2: settled_tile(NT - 2), NT - 1: make_tile(NT - 1, t, ghost=GHOST * (1 - u))}
        return tiles, NT - 2, NT - 1, 0.0, OUTRO_PAN
    return {NT - 1: make_tile(NT - 1, t)}, NT - 1, NT - 1, 0.0, OUTRO_PAN


def _plan(name, t):
    if name == "intro":
        return _plan_intro(t)
    if name == "outro":
        return _plan_outro(t)
    return _plan_clip(name, t)


def render_frame_pil(name, f):
    """CPU render of frame f of a segment as a PIL image (stills / fallback)."""
    t = f / g.FPS
    tiles, n_from, n_to, st, d = _plan(name, t)
    out = camera_frame(tiles, n_from, n_to, t, st, d)
    draw_progress(out, name, f)
    return out


def render_frame(cid, t):
    tiles, n_from, n_to, st, d = _plan(cid, t)
    out = camera_frame(tiles, n_from, n_to, t, st, d)
    draw_progress(out, cid, int(round(t * g.FPS)))
    return out


_GPU = False


def _gpu():
    """Lazily create this process's GPU compositor (None -> CPU fallback)."""
    global _GPU
    if _GPU is False:
        _GPU = None
        if os.environ.get("STICKMAN_RENDER", "gpu").lower() != "cpu":
            try:
                import gpu_view
                _GPU = gpu_view.GpuView(W, H, SS, P, GAP, MV, BG, ORANGE)
            except Exception as exc:       # no OpenGL / moderngl: stay on the CPU
                print(f"  [render] GPU compositor unavailable ({exc}); using CPU", flush=True)
    return _GPU


def render_frame_raw(name, f):
    """Final frame as raw RGB bytes. Camera, motion blur and progress line run
    on the GPU; only the board tiles are drawn on the CPU."""
    t = f / g.FPS
    tiles, n_from, n_to, st, d = _plan(name, t)
    gv = _gpu()
    if gv is None:
        out = camera_frame(tiles, n_from, n_to, t, st, d)
        draw_progress(out, name, f)
        return out.tobytes()
    lefts, dys = camera_samples(n_from, n_to, t, st, d)
    return gv.render(tiles, lefts, dys, progress_frac(name, f))


# ============================================================ intro / outro

def intro_times():
    hook = load_hook_timing()
    hook_dur = g.get_audio_duration(g.AUDIO_DIR / f"clip{HOOK_ID}.mp3")
    total = hook_dur + g.INTRO_PAD_BEFORE + g.INTRO_PAD_AFTER
    cut = _find_word_time(hook["words"], "youre", 2)
    if cut is None:
        cut = hook["duration"] * 0.5
    return g.INTRO_PAD_BEFORE + cut, total


def _find_word_time(words, target, occurrence=1):
    n = 0
    for w in words:
        if g.norm_tok(w["word"]) == target:
            n += 1
            if n == occurrence:
                return w["start"]
    return None


def draw_intro(cv, t):
    cut_t, _total = intro_times()
    cv.head_top = 560
    with zone(cv, "T"):
        if SQUARE:           # the two chips sit side by side to save height
            w1, _h1 = chip(cv, "c1", LM, 430, "Income isn't the issue", -1.0, BLACK, YELLOW, px=46)
            chip(cv, "c2", LM + w1 + 24, 430, "Leaks are.", 0.32, YELLOW, BLACK, px=46)
        else:
            chip(cv, "c1", LM, 215, "Income isn't the issue", -1.0, BLACK, YELLOW, px=46)
            chip(cv, "c2", LM + 18, 298, "Leaks are.", 0.32, YELLOW, BLACK, px=46)
        cv.text(LM, 560 + 0.76 * 112, "you're not broke.", "head", 104, INK, track=TRACK,
                trig=-1.0, key="h1")
    if t >= cut_t:
        hero(cv, "wallet", cut_t, side="right")
        with zone(cv, "T"):
            cv.text(LM, 560 + 0.76 * 112 + 118, "you're", "head", 104, INK, track=TRACK, trig=cut_t, key="h2a")
            wlead = text_w("head", 104, "you're ", TRACK)
            cv.text(LM + wlead, 560 + 0.76 * 112 + 118, "leaking.", "head", 104, ORANGE, track=TRACK,
                    trig=cut_t, key="h2b")
        x, y, w, h = LM, 1000, cv.maxw, 470
        with layer(cv, "leaks", x, y, w, h, cut_t + 0.12, bob=3.0) as l:
            if l:
                card_frame(l, x, y, w, h, header="!! MONTHLY LEAKS", hfill=RED)
                rows = [("subscriptions", "-$89"), ("dining out", "-$412"), ("upgrades", "-$640")]
                for i, (a, b) in enumerate(rows):
                    tr = cut_t + 0.3 + 0.17 * i
                    by = y + 48 + 76 + i * 70
                    l.text(x + 30, by, a, "head", 44, INK, track=TRACK, trig=tr, claim=False)
                    l.text(x + w - 30, by, b, "head", 44, ORANGE, anchor="r", trig=tr, claim=False)
                    l.line([(x + 24, by + 24), (x + w - 24, by + 24)], DIV, 2, dots=False)
                tt = cut_t + 0.8
                if t >= tt:
                    total_v = int(1141 * ease_out((t - tt) / 0.35))
                    l.text(x + 30, y + h - 44, f"-${total_v:,}", "head", 104, RED, trig=tt, track=TRACK,
                           claim=False)
                    l.text(x + w - 30, y + h - 48, "EVERY MONTH", "mono", 24, MUTE, anchor="r",
                           track=0.12, trig=tt, claim=False)
                l.claim("leaks", (x, y, x + w + 10, y + h + 10))


def render_intro_frame(f):
    return render_frame_pil("intro", f)


OUTRO_PAN = 0.40


def draw_outro(cv, t):
    head(cv, [("stop looking", 0.5), ("rich.", 0.6)], y_top=470, px=130)
    hero(cv, "bldg", 1.0, big=420 if LANDSCAPE else None)
    head(cv, [("start building", 1.0), ([("wealth.", INK)], 1.12)], y_top=830, px=130,
         hl=[(1, 0, 1.4)])


def render_outro_frame(f):
    return render_frame_pil("outro", f)


def segments():
    """Render segments in order: intro, clip1..clipN, outro."""
    out = [("intro", _hook_frames())]
    for c in CLIPS:
        out.append((f"clip{c['id']}", clip_total_frames(c)))
    out.append(("outro", OUTRO_FRAMES))
    return out


def frame_bytes(seg, f):
    name = int(seg[4:]) if seg.startswith("clip") else seg
    return render_frame_raw(name, f)


async def prepare():
    """Make sure narration + word timing exist in this style's folder."""
    for d in (g.OUTPUT_DIR, g.AUDIO_DIR, g.TIMING_DIR, g.VIDEO_DIR):
        d.mkdir(parents=True, exist_ok=True)
    seed_audio()
    await voice.ensure_audio(g, CLIPS, HOOK_ID, HOOK_TEXT)


def frame(seg, f):
    """PIL image of frame f of a segment (GPU compositor when available)."""
    return Image.frombytes("RGB", (W, H), frame_bytes(seg, f))


def _compile():
    return streaming.compile_segments(sys.modules[__name__])


def clip_total_frames(clip):
    cid = clip["id"]
    dur = g.get_audio_duration(g.AUDIO_DIR / f"clip{cid}.mp3")
    n = max(1, int((dur + g.PAD_BEFORE.get(cid, 0.45) + g.PAD_AFTER) * g.FPS))
    clip["total_frames"] = n
    return n


# ============================================================ layout audit

def _inter(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _check_claims(label_, rec):
    out = []
    mx, my = (40, 150) if PORTRAIT else (36, 36)         # vertical video keeps clear of the app UI; wide / square do not need to
    rec = [(key, to_page(zn, box), grp) for key, box, grp, zn in rec]
    for key, box, grp in rec:
        if box[0] < mx or box[2] > W - mx or box[1] < my or box[3] > H - my:
            out.append(f"{label_}: '{key}' leaves the safe area {tuple(int(v) for v in box)}")
    for i in range(len(rec)):
        for j in range(i + 1, len(rec)):
            ka, ba, ga = rec[i]
            kb, bb, gb = rec[j]
            if ga is not None and ga == gb:
                continue
            if _inter(ba, bb):
                out.append(f"{label_}: '{ka}' overlaps '{kb}'")
    return out


_AUDIT = None


def layout_problems():
    """Draw every board frame in its settled state with a recorder attached and
    report overlaps / safe-area breaches, plus any word-sync key that is not
    really spoken inside its beat."""
    global _AUDIT
    if _AUDIT is not None:
        return _AUDIT
    probs = []
    _KEYS.clear()
    for n, info in enumerate(PANELS):
        if info[0] != "beats":
            continue
        c = CLIPS[info[1] - 1]
        beats = g.clip_beats(c)
        for bi in info[2]:
            rec = []
            make_tile(n, beats[bi][1] + 0.6, rec=rec, force=bi)
            probs += _check_claims(f"clip{c['id']} beat{bi}", rec)
    _cut, total = intro_times()
    rec = []
    make_tile(0, total - 0.2, rec=rec)
    probs += _check_claims("intro", rec)
    rec = []
    make_tile(NT - 1, 1.9, rec=rec)
    probs += _check_claims("outro", rec)
    for cid, bi, word in sorted(_KEYS):
        if not _word_in_beat(CLIPS[cid - 1], bi, word):
            probs.append(f"clip{cid} beat{bi}: sync word '{word}' is not spoken in that beat")
    _AUDIT = sorted(set(probs))
    return _AUDIT


def layout_report():
    return "\n".join(layout_problems()) or "no problems"


# ============================================================ sound design (quiet, clean)

def sfx_events(clip):
    cid = clip["id"]
    beats = g.clip_beats(clip)
    evs = []
    if not beats:
        return evs
    for bi in pan_beats(cid):
        st, d = pan_start_dur(clip, bi)
        evs.append((st + d / 2 - 0.15, "swish", 0.34))
    if cid == 1:
        evs.append((g.beat_word_t(clip, 2, "spend") + 0.25, "stamp", 0.5))
    elif cid == 2:
        for bi, w in enumerate(("car", "vacation", "lifestyle")):
            evs.append((g.beat_word_t(clip, bi, w) + 0.15, "pop", 0.4))
    elif cid == 3:
        evs.append((beats[1][0] + 0.02, "slam", 0.55))
        evs.append((g.beat_word_t(clip, 2, "expenses") + 0.3, "stamp", 0.5))
    elif cid == 4:
        evs.append((g.beat_word_t(clip, 0, "truth") + 0.05, "pop", 0.4))
        evs.append((g.beat_word_t(clip, 1, "eating"), "crumble", 0.45))
    elif cid == 5:
        evs.append((g.beat_word_t(clip, 2, "achieved") + 0.25, "stamp", 0.5))
    elif cid == 6:
        evs.append((g.beat_word_t(clip, 1, "asset") + 0.1, "ding", 0.45))
    elif cid == 7:
        evs.append((g.beat_word_t(clip, 0, "money") + 0.1, "slam", 0.5))
        evs.append((g.beat_word_t(clip, 2, "pays") + 0.1, "ding", 0.5))
    elif cid == 8:
        evs.append((g.beat_word_t(clip, 1, "assets"), "pop", 0.4))
        evs.append((g.beat_word_t(clip, 1, "income"), "pop", 0.4))
        evs.append((g.beat_word_t(clip, 2, "wealth") + 0.1, "ding", 0.5))
    else:
        evs.append((beats[2][0] + (beats[2][1] - beats[2][0]) * 0.62, "pop", 0.5))
    return [(max(0.0, tt), n, gl) for tt, n, gl in evs]


# ============================================================ pipeline

async def main():
    print("=" * 60)
    print("Stickman Video Generator - Lifestyle Inflation (adi style)")
    print("=" * 60)
    apply_to(g)
    for d in (g.OUTPUT_DIR, g.AUDIO_DIR, g.TIMING_DIR, g.VIDEO_DIR):
        d.mkdir(parents=True, exist_ok=True)
    print("\n[1/3] Narration + word timing (reused where available)...")
    await prepare()
    if "--audit" in sys.argv:
        probs = layout_problems()
        print(f"[layout] unresolved problems: {len(probs)}")
        for pr in probs:
            print("  !!", pr)
        print("AUDIT FAIL" if probs else "AUDIT PASS")
        return 1 if probs else 0

    print("\n[2/3] Rendering (GPU camera + GPU encoder, no frame files)...")
    import generate_adi as me
    cfg = studio_config.load()
    studio_config.apply_render_env(cfg)
    final = streaming.render_all(me, cfg["render"]["cooling"])
    print("=" * 60)
    print(f"DONE! -> {final}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
