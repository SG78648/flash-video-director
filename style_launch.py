"""style_launch.py - the Launch style: a product-launch reel made only of motion graphics (no one on camera), from the Motion Graphics starter kit.

Why it exists. Lee does not record content, so the reel has to carry itself the way a product launch video does: the idea is revealed like a product, the three
or four moments of the script each SHOW the thing happening (a drawn object that does what the sentence says, not just words), and it ends on a clean end card
with one line and one call to action (comment ZOOM). It is the Desk style's whole content engine (the same planner, drawn objects, scenes and sound) with the kit's
Liquid Glass look and calm motion instead of Desk's paper and spring:
  - a soft light gradient with three blurred colour blobs (pale blue, lilac, peach) drifting slowly;
  - frosted white cards with big rounded corners and a soft shadow that rise 30 px and fade in over 0.6 s while scaling up from 0.96, nothing bounces or tilts;
  - Inter for everything, dark grey text, the key words of a sentence in blue, green only for ticks and checks;
  - sentences that nothing can picture become big sentence-case type whose words arrive one by one;
  - the hook is a reveal (the headline rises word by word) and the close is an end card (icon, the line, the call to action);
  - no progress bar and no labels on screen, captions are small Inter lines on a frosted pill.
The studio talks to this module exactly as it does to the Mint style: every name it does not define itself is forwarded to style_desk.
"""
import json
import math
import os
import sys

import numpy as np

import studio_config

if "FLASH_ASPECT" not in os.environ:     # command line: follow the app's saved format
    studio_config.ensure_aspect_env()

from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import desk_rich
import generate_video as g
import story_scenes
import style_desk as D

STYLE_ID = "launch"
INTRO_SFX = []            # the studio reads these two lists for its program: no chime on the hook, no shimmer on the close
OUTRO_SFX = []
FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"

INK_PAGE = (244, 246, 252)          # what text fades toward (the page is a gradient around this)
TEXT = (29, 29, 31)
GREY = (134, 134, 139)
BLUE = (0, 113, 227)
GREEN = (52, 199, 89)
RED = (255, 59, 48)
WHITE = (255, 255, 255)

SS = D.SS


def __getattr__(name):
    """Whatever this module does not define is the Desk style's (segments, frame_bytes, prepare, OUT_DIR ...)."""
    return getattr(D, name)


# ------------------------------------------------------------------ fonts (Inter for everything)
def _ttf(stem):
    return str(FONT_DIR / f"{stem}.ttf")


FONTS = {"heavy": (_ttf("Inter-700"),), "ital": (_ttf("InstrumentSerif-400-italic"),), "serif": (_ttf("Inter-700"),), "serifb": (_ttf("Inter-700"),),
         "sans": (_ttf("Inter-700"),), "sansr": (_ttf("Inter-400"),)}


def _font_of(name):
    def f(px):
        return D.F(name, px)
    return f


# ------------------------------------------------------------------ the stage: a soft gradient with three drifting blobs
_STAGE = {}
STOPS = [(222, 235, 255), (232, 226, 252), (255, 232, 226)]               # pale blue, lilac, peach
BLOBS = [((176, 208, 255), 0.0, 0.13), ((208, 188, 250), 2.1, 0.10), ((255, 208, 186), 4.2, 0.12)]


def stage(t=0.0):
    w = 90
    h = max(2, int(round(w * D.VRH / D.VRW)))
    key = (w, h)
    if key not in _STAGE:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        u = np.clip((xx / w * 0.45 + yy / h * 0.75) / 1.2, 0, 1)[..., None]
        s = np.array(STOPS, dtype=np.float32)
        lo = np.clip(u * 2, 0, 1)
        base = np.where(u < 0.5, s[0] + (s[1] - s[0]) * lo, s[1] + (s[2] - s[1]) * (u * 2 - 1))
        _STAGE[key] = (xx / w, yy / h, base)
    xx, yy, base = _STAGE[key]
    arr = base.copy()
    for k, (col, ph, sp) in enumerate(BLOBS):
        cx = 0.5 + 0.34 * math.sin(t * sp + ph)
        cy = 0.5 + 0.30 * math.cos(t * sp * 0.8 + ph * 1.3) + (k - 1) * 0.12
        dd = ((xx - cx) ** 2 * 1.0 + (yy - cy) ** 2 * 0.55) / 0.045
        a = (np.exp(-dd) * 0.62)[..., None]
        arr = arr * (1 - a) + np.array(col, dtype=np.float32) * a
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    return im.resize((D.VRW, D.VRH), Image.BICUBIC)


# ------------------------------------------------------------------ calm cards: rise, fade, scale up from 0.96, no tilt and no bounce
def place(img, card, cx, cy, t, t0, rot=0.0, sc=1.0):
    a = D.clamp01((t - t0) / 0.6)
    if a <= 0.01:
        return
    e = D.ease_out(a)
    sh = D.shadow_of(card.w, card.h, card.r)
    base = Image.new("RGBA", sh.size, (0, 0, 0, 0))
    blk = Image.new("RGBA", sh.size, tuple(D.SHADOW_RGB) + (255,))
    blk.putalpha(sh.point(lambda v: int(v * 0.55)))
    base.alpha_composite(blk, (0, 18 * SS))
    base.alpha_composite(card.im, (D.PAD * SS, D.PAD * SS))
    s = sc * (0.96 + 0.04 * e)
    if abs(s - 1.0) > 0.002:
        base = base.resize((max(2, int(base.width * s)), max(2, int(base.height * s))), Image.BILINEAR)
    if a < 1:
        base.putalpha(base.getchannel("A").point(lambda v: int(v * e)))
    dy = (1 - e) * 30
    img.paste(base, (int(cx * SS - base.width / 2), int((cy + dy) * SS - base.height / 2)), base)


def stage_card_xy(card):
    x0, y0, x1, y1 = (40, 460, D.VW - 40, 1460) if D.PORTRAIT else D.vis_box()
    sc = min((x1 - x0) / card.w, (y1 - y0) / card.h, 1.25)
    return (x0 + x1) / 2, (y0 + y1) / 2, sc


def draw_progress(img, cid, t):
    return                                  # nothing on screen counts or labels the video


# ------------------------------------------------------------------ sentence-case type whose words arrive one by one
def draw_type(img, text, tw_of, t, s0, box=None, pxmax=150):
    x0, y0, x1, y1 = box or ((70, 560, D.VW - 70, 1460) if D.PORTRAIT else D.vis_box())
    maxw = x1 - x0
    k, toks = D.split_emph(text)
    px = pxmax
    while True:
        lines, cur, curw = [], [], 0.0
        f = D.F("heavy", px)
        sp = D.width(" ", f)
        for i, w in enumerate(toks):
            w2 = (w[:1].upper() + w[1:]) if i == 0 else w
            ww = D.width(w2, f)
            if cur and curw + sp + ww > maxw:
                lines.append(cur)
                cur, curw = [], 0.0
            cur.append((i, w2, ww))
            curw += (sp if len(cur) > 1 else 0) + ww
        if cur:
            lines.append(cur)
        if len(lines) * px * 1.16 <= (y1 - y0) * 0.80 or px <= 54:
            break
        px -= 6
    lh = px * 1.16
    top = (y0 + y1) / 2 - len(lines) * lh / 2
    d = ImageDraw.Draw(img)
    cx = D.VW / 2
    for li, ln in enumerate(lines):
        total = sum(e[2] for e in ln) + sp * (len(ln) - 1)
        xx = cx - total / 2
        by = top + li * lh + px * 0.86
        for i, w, ww in ln:
            a = D.ease_out((t - (s0 + 0.06 + min(0.06 * i, 0.5))) / 0.5)          # the sentence arrives whole and fast, word by word, the way a launch video shows a line
            if a > 0.02:
                bad = D.word_color(w) == D.RED
                col = D.RED if bad else (D.BONE if i < k else D.ACCENT)
                d.text((xx * SS, (by + (1 - a) * 28) * SS), w, font=f, fill=D.mix(col, INK_PAGE, a), anchor="ls")
            xx += ww + sp


# ------------------------------------------------------------------ the hook is a reveal, the close is an end card
def intro_draw(img, t, total):
    st = D.story()
    x0, y0, x1, y1 = D.vis_box()
    w = x1 - x0 + (30 if D.PORTRAIT else 0)
    t1, t2 = st["hook_head"][0], st["hook_head"][1]
    top = 520 if D.PORTRAIT else 70
    px = 112 if D.PORTRAIT else 82
    h_avail = D.VH * (0.25 if D.PORTRAIT else 0.50)
    while True:
        f = D.F("heavy", px)
        l1, l2 = D.wrap(t1, f, w), D.wrap(t2, f, w)
        if (len(l1) + len(l2)) * px * 1.14 <= h_avail or px <= 46:
            break
        px -= 2
    d = ImageDraw.Draw(img)
    cx = D.VW / 2
    yy = top
    n = 0
    for part, col in ((l1, D.BONE), (l2, D.ACCENT)):
        for ln in part:
            a = D.ease_out((t - 0.12 * n) / 0.7)
            d.text((cx * SS, (yy + px * 0.62 + (1 - a) * 40) * SS), ln, font=f, fill=D.mix(col, INK_PAGE, a), anchor="mm")
            yy += px * 1.14
            n += 1
    obj = D.object_spec(st["hook_head"][0])
    if obj:
        words = []
        try:
            words = [(wd["word"], g.INTRO_PAD_BEFORE + wd["start"]) for wd in json.loads((g.TIMING_DIR / f"clip{D.HOOK_ID}.json").read_text(encoding="utf-8"))["words"]]
        except Exception:
            pass
        ctx = story_scenes.Ctx(0.0, total, words, lambda kk: 0.0)
        card = D.build_obj(obj, t, ctx.at, st.get("hook", ""), {"_ws": words}, 0.0, total)
        sc = min(1.0, (1420 - (yy + 40)) / card.h, 940 / card.w)
        if sc > 0.3:
            place(img, card, cx, yy + 40 + card.h * sc / 2, t, 0.45, sc=sc)


def outro_draw(img, t):
    st = D.story()
    lines = st["outro"]["lines"]
    x0, y0, x1, y1 = D.vis_box()
    cx = D.VW / 2
    icon = D.icon_card(st["outro"]["icon"], size=380)
    place(img, icon, cx, y0 + 480, t, 0.05)
    px = 92 if D.PORTRAIT else 66
    f = D.F("heavy", px)
    fr = D.F("sansr", px * 0.62)
    d = ImageDraw.Draw(img)
    yy = y0 + 800
    for j, ln in enumerate(lines):
        a = D.ease_out((t - 0.3 - 0.14 * j) / 0.55)
        if a <= 0.02:
            yy += px * (1.18 if j == 0 else 0.8)
            continue
        first = j == 0
        ff = f if first else fr
        # the keyword (written in capitals in the script) is picked out in blue
        words = ln.split()
        total = sum(D.width(wd, ff) for wd in words) + D.width(" ", ff) * (len(words) - 1)
        xx = cx - total / 2
        for wd in words:
            col = D.ACCENT if wd.isupper() and len(wd) > 1 else (D.BONE if first else GREY)
            d.text((xx * SS, (yy + (1 - a) * 26) * SS), wd, font=ff, fill=D.mix(col, INK_PAGE, a), anchor="ls")
            xx += D.width(wd, ff) + D.width(" ", ff)
        yy += px * (1.18 if first else 0.8)


# ------------------------------------------------------------------ the look
def apply_config(cfg=None):
    cfg = studio_config.normalize(cfg) if cfg else studio_config.load()
    n = cfg["launch"]
    rgb = studio_config.rgb
    D.FONTS = FONTS
    D._FC.clear()
    D.font, D.serif, D.sans = _font_of("sans"), _font_of("serif"), _font_of("sans")
    D._FONTS.clear()
    D.stage, D.place, D.draw_type, D.draw_progress, D.stage_card_xy = stage, place, draw_type, draw_progress, stage_card_xy
    D.intro_draw, D.outro_draw = intro_draw, outro_draw
    desk_rich.ENABLED = False                       # calm and clean: a card or big type per sentence, no stickers or hand-drawn marks
    D.USE_BROLL = False
    D.GRAIN = float(n["look"]["grain"])
    D.KINETIC = True
    D.DRIFT = 0.025
    D.INK, D.BONE, D.ASH, D.CARD = INK_PAGE, TEXT, GREY, WHITE
    D.ACCENT, D.RED, D.GREEN, D.LIGHT = rgb(n["palette"]["accent"]), RED, GREEN, WHITE
    D.PAPER, D.PAPER2, D.TXT, D.MUTED, D.LINE, D.DEEP = WHITE, (240, 242, 248), TEXT, GREY, (224, 228, 238), (36, 40, 66)
    D.SHADOW_RGB, D.TEXT_SHADOW_RGB, D.HAIR = (70, 84, 140), (40, 50, 100), (224, 228, 238)
    D.TAPE_RGBA, D.PHOTO_TINT = (214, 222, 245, 200), (236, 240, 250)
    D.BLDG = {"body": (88, 96, 128), "cornice": (72, 80, 112), "off": (52, 58, 86), "base": (44, 50, 76), "on": (255, 214, 102)}
    D.CALC = {"edge": (96, 104, 136), "unit": (190, 198, 222), "op_hit": (255, 159, 10), "fn_hit": (140, 150, 180), "fn": (88, 96, 128), "hit": (110, 120, 150), "key": (70, 78, 108)}
    D.SHEETBAR = (88, 96, 128)
    D._CACHE.clear()
    D._PLAN.clear()


def apply_to(gm):
    D.STYLE_ID = STYLE_ID
    D.VIDEO_TITLE = STYLE_ID
    D.apply_to(gm)                  # the Desk engine (story, timing, sound, streaming), then this style's look on top
    gm.VIDEO_TITLE = STYLE_ID
    apply_config()
