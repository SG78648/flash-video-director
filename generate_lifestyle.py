"""generate_lifestyle.py - short-form story: "lifestyle inflation".

A fast-paced, high-retention Reels-style piece on lifestyle inflation (every
raise gets spent) that pivots into a real-estate-investing pitch. Same
collision-free layout engine (layout_guard) + design rhythm as the other
stories:

    kicker    y = cy - 460   (small gray, scene title)
    statement y = cy - 360   (bold white/colored, the line said that beat)
    diagram   y in [cy-240 .. cy+260]
    footnote  y = cy + 430   (small gray/golded, reinforcing line)

The visual motif for this story is literal: two opposing elements (a gain
and an expense, a question and its answer, a card and a stamp) fly toward
each other and COLLIDE with an impact flash, timed to a stamp/slam SFX event
so the shared engine's beat-locked camera automatically punches on contact.

9 clips x 3 beats = 27 beats, all planned/audited before rendering.
"""
import asyncio
import json
import math
import sys
from pathlib import Path

import generate_video as g

from layout_guard import (Scene, ground_box, coin_pile_box, house_box,
                          building_box, arrow_box, tag_box, card_box,
                          glyph_box)
from layout_guard import (GROUND, PROP, ACCENT, TEXT,
                          PRIO_PIECE, PRIO_KICKER, PRIO_FOOT, PRIO_STATEMENT)

# ---- this story's palette (kept local -- other stories keep g.GOLD) ----
INK = (34, 34, 40)          # dark ink -- primary text/icon color in light theme
MUTE = (140, 140, 148)       # secondary gray -- works on either background
SKY = (70, 170, 235)         # accent color (replaces gold -- yellow+red read badly together)

# ---- light/dark theme ---------------------------------------------------
# Everything below is derived from set_theme() so the story can flip between
# the two without touching any draw function (the studio app calls it too).
LIGHT_THEME = True
PAGE_BG = GRID_LINE = GRID_BASE = FG = CAP_BG = CAP_BORDER = PANEL_BG = PANEL_SHADOW = FLASH_COLOR = None


def set_theme(light):
    global LIGHT_THEME, PAGE_BG, GRID_LINE, GRID_BASE, FG, CAP_BG, CAP_BORDER
    global PANEL_BG, PANEL_SHADOW, FLASH_COLOR
    LIGHT_THEME = bool(light)
    if LIGHT_THEME:
        PAGE_BG = (246, 247, 249)      # page background (was g.BLACK)
        GRID_LINE = (227, 229, 233)    # faint grid, dark-on-light instead of light-on-dark
        GRID_BASE = (205, 208, 213)    # baseline rule at the bottom edge
        FG = INK                        # primary text/icon color drawn on the page
        CAP_BG = (255, 255, 255)        # caption-bar fill
        CAP_BORDER = (222, 224, 228)    # caption-bar hairline (dark theme has none)
        PANEL_BG = (255, 255, 255)      # dashboard-panel fill
        PANEL_SHADOW = (222, 224, 228)  # dashboard-panel drop shadow (light gray, not near-black)
        FLASH_COLOR = INK               # hard-cut flash must contrast the page -- white-on-white would vanish
    else:
        PAGE_BG = g.BLACK
        GRID_LINE = g.BG_LINE
        GRID_BASE = g.DIM
        FG = g.WHITE
        CAP_BG = (16, 16, 20)
        CAP_BORDER = None
        PANEL_BG = (15, 15, 19)
        PANEL_SHADOW = (9, 9, 12)
        FLASH_COLOR = g.WHITE


set_theme(True)

# ---- collision-free layout engine (beat-aware) -------------------------
_CID = None
_IDX = None
_SC = {}


def set_beat(cid, idx):
    global _CID, _IDX
    _CID, _IDX = cid, idx


def current_scene():
    cid, idx = _CID, _IDX
    if cid is None or idx is None:
        return None
    return scene(cid, idx)


def scene(cid, idx):
    key = (cid, idx)
    sc = _SC.get(key)
    if sc is None:
        sc = Scene(cid, idx)
        build_scene(sc, cid, idx)
        sc.solve()
        _SC[key] = sc
    return sc


def layout_problems():
    out = []
    for cid in range(1, 10):
        for idx in (0, 1, 2):
            out.extend(scene(cid, idx).problems)
    return sorted(set(out))


def layout_report():
    lines = []
    for cid in range(1, 10):
        for idx in (0, 1, 2):
            lines.append(scene(cid, idx).report())
    return "\n".join(lines)


CAP_Y = 500   # offset from cy: consistent lower-third caption-bar band, guildshore-style
CAM_DRIFT = 0.014   # slow push-in over a beat
SHOW_GRID = True
POST_FX = True      # tone curve + vignette + grain


def apply_config(cfg=None):
    """Load the studio settings (cfg, else the file named by STICKMAN_STUDIO_CONFIG,
    else defaults -- which reproduce the original look exactly)."""
    global SKY, CAP_Y, CAM_DRIFT, SHOW_GRID, POST_FX
    import studio_config
    cfg = studio_config.normalize(cfg) if cfg else studio_config.load()
    d = cfg["dan"]
    set_theme(d["theme"] == "light")
    SKY = studio_config.rgb(d["palette"]["accent"])
    g.RED = studio_config.rgb(d["palette"]["negative"])
    CAP_Y = int(d["layout"]["caption_y"])
    SHOW_GRID = bool(d["layout"]["show_grid"])
    CAM_DRIFT = float(d["camera"]["drift"])
    POST_FX = bool(d["fx"]["post"])
    _SC.clear()


def build_scene(sc, cid, idx):
    cx, cy = g.W // 2, g.H // 2 + 90
    base = cy + 190
    cy_cap = cy + CAP_Y
    impact = (cx - 280, cy - 40, cx + 280, cy + 220)   # generic collision-zone claim

    if cid == 1:
        if idx == 0:
            sc.fixed("dash", (cx - 230, cy - 185, cx + 230, cy + 5), PROP, "c1")
            sc.text("NOT AN INCOME PROBLEM", cx, cy_cap, "NOT AN INCOME PROBLEM", 34, PRIO_FOOT)
        elif idx == 1:
            sc.fixed("dash", (cx - 240, cy - 190, cx + 240, cy + 70), PROP, "c1")
            sc.text("EVERY RAISE GETS MATCHED", cx, cy_cap, "EVERY RAISE GETS MATCHED", 32, PRIO_FOOT)
        else:
            sc.fixed("dash", (cx - 240, cy - 250, cx + 240, cy + 70), PROP, "c1")
            sc.text("GONE. EVERY TIME.", cx, cy_cap, "GONE. EVERY TIME.", 36, PRIO_FOOT)
    elif cid == 2:
        if idx == 0:
            sc.fixed("card", (cx - 230, cy - 190, cx + 230, cy + 110), PROP, "raise")
            sc.text("RAISE? NEW CAR.", cx, cy_cap, "RAISE? NEW CAR.", 36, PRIO_FOOT)
        elif idx == 1:
            sc.fixed("card", (cx - 230, cy - 190, cx + 230, cy + 110), PROP, "bonus")
            sc.text("BONUS? NEW VACATION.", cx, cy_cap, "BONUS? NEW VACATION.", 34, PRIO_FOOT)
        else:
            sc.fixed("card", (cx - 230, cy - 190, cx + 230, cy + 110), PROP, "six")
            sc.text("MORE INCOME? MORE OUTGO.", cx, cy_cap, "MORE INCOME? MORE OUTGO.", 30, PRIO_FOOT)
    elif cid == 3:
        if idx == 0:
            sc.fixed("bubble", card_box(cx, cy + 20, 480, 200), PROP, "exc")
            sc.text("THE AUDACITY TO SAY...", cx, cy_cap, "THE AUDACITY TO SAY...", 32, PRIO_FOOT)
        elif idx == 1:
            sc.fixed("bubble", card_box(cx, cy + 20, 480, 200), PROP, "exc")
            sc.text("NO.", cx, cy_cap, "NO.", 58, PRIO_FOOT)
        else:
            sc.fixed("arrows", (cx - 260, cy - 60, cx + 260, cy + 220), PROP, "arr")
            sc.text("STOP MATCHING EVERY RAISE", cx, cy_cap, "STOP MATCHING EVERY RAISE", 30, PRIO_FOOT)
    elif cid == 4:
        if idx == 0:
            sc.text("HERE'S THE TRUTH", cx, cy_cap, "HERE'S THE TRUTH", 38, PRIO_FOOT)
        elif idx == 1:
            sc.fixed("card", card_box(cx, cy + 60, 300, 220), PROP, "eat")
            sc.text("YOUR LIFESTYLE IS EATING IT", cx, cy_cap,
                    "YOUR LIFESTYLE IS EATING IT", 30, PRIO_FOOT)
        else:
            sc.fixed("card", card_box(cx, cy + 60, 300, 220), PROP, "eat")
            sc.text("PIECE BY PIECE", cx, cy_cap, "PIECE BY PIECE", 38, PRIO_FOOT)
    elif cid == 5:
        if idx == 0:
            sc.fixed("goal", card_box(cx, cy - 80, 260, 110), PROP, "free")
            sc.text("YOU WANT FREEDOM?", cx, cy_cap, "YOU WANT FREEDOM?", 36, PRIO_FOOT)
        elif idx == 1:
            sc.fixed("goal", card_box(cx, cy - 240, 220, 90), PROP, "free")
            sc.fixed("impact", (cx - 260, cy - 40, cx + 260, cy + 240), PROP, "look")
            sc.text("BUT CHASE THE LOOK INSTEAD", cx, cy_cap,
                    "BUT CHASE THE LOOK INSTEAD", 28, PRIO_FOOT)
        else:
            sc.fixed("goal", card_box(cx, cy - 240, 220, 90), PROP, "free")
            sc.text("NOT ONE DOLLAR TOWARD IT", cx, cy_cap, "NOT ONE DOLLAR TOWARD IT", 28, PRIO_FOOT)
    elif cid == 6:
        if idx == 0:
            sc.accent("clock", glyph_box(cx, cy + 20, 140, 140), "ret")
            sc.text("YOU WANT OUT EARLY?", cx, cy_cap, "YOU WANT OUT EARLY?", 36, PRIO_FOOT)
        elif idx == 1:
            sc.fixed("dash", (cx - 210, cy - 120, cx + 210, cy + 60), PROP, "sh")
            sc.text("ZERO ASSETS BOUGHT", cx, cy_cap, "ZERO ASSETS BOUGHT", 34, PRIO_FOOT)
        else:
            sc.accent("clock", glyph_box(cx, cy + 20, 140, 140), "ret")
            sc.text("NOTHING PAYS YOU BACK", cx, cy_cap, "NOTHING PAYS YOU BACK", 30, PRIO_FOOT)
    elif cid == 7:
        if idx == 0:
            sc.fixed("impact", (cx - 210, cy - 60, cx + 210, cy + 100), PROP, "q1")
            sc.text("WRONG QUESTION", cx, cy_cap, "WRONG QUESTION", 38, PRIO_FOOT)
        elif idx == 1:
            sc.fixed("bldg", building_box(cx + 120, base, 200, 220), PROP, "q2")
            sc.text("RIGHT QUESTION:", cx, cy_cap, "RIGHT QUESTION:", 38, PRIO_FOOT)
        else:
            sc.fixed("bldg", building_box(cx + 120, base, 200, 220), PROP, "q2")
            sc.text("HOW DO I MAKE IT PAY ME?", cx, cy_cap, "HOW DO I MAKE IT PAY ME?", 28, PRIO_FOOT)
    elif cid == 8:
        if idx == 0:
            sc.fixed("bldg", building_box(cx, base, 260, 220), PROP, "b")
            sc.text("BUILD REAL ASSETS", cx, cy_cap, "BUILD REAL ASSETS", 34, PRIO_FOOT)
        elif idx == 1:
            sc.fixed("dash", (cx - 200, cy - 230, cx + 200, cy + 50), PROP, "b")
            sc.text("ASSETS. INCOME. WEALTH.", cx, cy_cap, "ASSETS. INCOME. WEALTH.", 30, PRIO_FOOT)
        else:
            sc.fixed("bldg", building_box(cx - 140, base, 220, 200), PROP, "b")
            sc.text("WEALTH THAT DOESN'T NEED YOU", cx, cy_cap,
                    "WEALTH THAT DOESN'T NEED YOU", 26, PRIO_FOOT)
    else:
        if idx == 0:
            sc.fixed("rich", card_box(cx, cy, 320, 150), PROP, "rich")
            sc.text("LOOKING RICH IS EASY", cx, cy_cap, "LOOKING RICH IS EASY", 34, PRIO_FOOT)
        elif idx == 1:
            sc.fixed("bldg", building_box(cx, base, 260, 180), PROP, "wealth")
            sc.text("BUILDING WEALTH IS THE PART", cx, cy_cap,
                    "BUILDING WEALTH IS THE PART", 28, PRIO_FOOT)
        else:
            sc.fixed("bldg", building_box(cx, base, 260, 260), PROP, "wealth")
            sc.text("MOST PEOPLE NEVER GET TO", cx, cy_cap, "MOST PEOPLE NEVER GET TO", 28, PRIO_FOOT)
            sc.text("START TODAY", cx, cy_cap - 100, "START TODAY", 30, PRIO_STATEMENT)


# ============================================================ story data

VIDEO_TITLE = "lifestyle_inflation"
VOICE = "en-US-GuyNeural"      # male narrator, same channel voice as harder_to_ignore
RATE = "+12%"                   # faster read for Reels-style pacing
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

PAD_BEFORE = {i: 0.35 for i in range(1, 10)}
PAD_BEFORE[1] = 0.45
PAD_AFTER = 0.25

HOOK_ID = "hook"                                   # pseudo-clip id for the spoken intro line
HOOK_TEXT = "You're not broke. You're leaking."     # must match the two on-screen hook lines


def apply_to(gm):
    """Point engine module globals at this story (used before render/compile/QA)."""
    gm.VIDEO_TITLE = VIDEO_TITLE
    gm.CLIPS = CLIPS
    gm.NARR_BEATS = NARR_BEATS
    gm.PAD_BEFORE = PAD_BEFORE
    gm.PAD_AFTER = PAD_AFTER
    gm.QA_MAX_DUR = QA_MAX_DUR
    gm.VOICE = VOICE
    gm.RATE = RATE
    gm.MUSIC_BED = None   # the synthesized pad had an audible low-end hum ("hmm"); user asked to remove it
    gm.INTRO_HOOK_ID = HOOK_ID   # intro now speaks the hook instead of playing silent-of-voice
    gm._TIMING_CACHE.clear()
    gm._WORD_P_CACHE.clear()
    gm.sfx_events = sfx_events
    gm._SC = _SC if hasattr(gm, "_SC") else _SC
    apply_config()


async def gen_hook_narration(gm):
    """Synthesize the intro hook line as a pseudo-clip (reuses the same
    word-boundary + tail-trim logic as every other clip's narration)."""
    await gm.gen_audio_and_timing({"id": HOOK_ID, "narration": HOOK_TEXT})


def load_hook_timing():
    with open(g.TIMING_DIR / f"clip{HOOK_ID}.json") as fh:
        return json.load(fh)


# ============================================================ design system

def clamp01(t):
    return g.clamp01(t)


def dim_col(color, a):
    """Blend `color` toward the page background at fraction `a` (0=invisible
    -- reads as the background -- 1=full color). In dark theme PAGE_BG is
    black, so this reduces to the old scale-toward-black formula exactly;
    in light theme it correctly fades toward the light page instead of
    toward black, which the old black-only formula got wrong (every
    fade-in would have darkened toward black regardless of theme)."""
    a = max(0.0, min(1.0, a))
    bg = PAGE_BG
    return tuple(int(bg[i] + (color[i] - bg[i]) * a) for i in range(3))


def halo(d, cx, cy, r, color, alpha=0.16, layers=2):
    """Local reimplementation of the shared g.glow_circle, using this
    story's theme-aware dim_col instead of glow_circle's hardcoded
    scale-toward-black (which would draw dark rings, not a soft glow, on
    a light page)."""
    for i in range(layers, 0, -1):
        rr = r * (1 + i * 0.35)
        a = alpha / (i + 1)
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=dim_col(color, a), width=6)


def floorline(d, cx, cy, span=820):
    d.line([cx - span, cy, cx + span, cy], fill=dim_col(g.GRAY, 0.55), width=3)


def card(d, x, y, w, h, color, radius=20, a=1.0, shadow=True):
    if shadow and a > 0.05:
        off = 8
        # PANEL_SHADOW: near-black used to blend invisibly into a black page;
        # on a light page that same near-black instead reads as a solid
        # black fill behind the (thin, outline-only) card below it.
        d.rounded_rectangle([x - w / 2 + off, y - h / 2 + off, x + w / 2 + off, y + h / 2 + off],
                            radius=radius, fill=PANEL_SHADOW)
    c = dim_col(color, a)
    d.rounded_rectangle([x - w / 2, y - h / 2, x + w / 2, y + h / 2],
                        radius=radius, outline=c, width=4)


def badge(d, x, y, text, color, px=24, w=170, h=40, a=1.0):
    card(d, x, y, w, h, color, radius=12, a=a)
    g.big_text(d, x, y, text, color=color, px=px)


def slide_fade(d, x, y, t, trig, text, px=40, color=g.WHITE, dur=0.24, dy=20):
    """Fade + slide-up entrance for text. Call LAST in any beat."""
    sc = current_scene()
    if sc is not None:
        p = sc.pos(text)
        if p:
            x, y, px = p
    aq = clamp01((t - trig) / dur)
    aq = aq * aq * (3 - 2 * aq)
    if aq <= 0.02:
        return
    yy = y + dy * (1 - aq)
    g.big_text(d, x, yy, text, color=dim_col(color, aq), px=px)


def pop_text(d, x, y, t_abs, trig, text, color=g.WHITE, px=60, dur=0.16, grow=1.10):
    sc = current_scene()
    if sc is not None:
        p = sc.pos(text)
        if p:
            x, y, px = p
    g.pop_text(d, x, y, t_abs, trig, text, color=color, px=px, dur=dur, grow=grow)


def clock_g(d, x, y, r, color, a=1.0, deg=0.0):
    c = dim_col(color, a)
    d.ellipse([x - r, y - r, x + r, y + r], outline=c, width=5)
    ang = math.radians(deg)
    d.line([x, y, x + math.sin(ang) * r * 0.6, y - math.cos(ang) * r * 0.6], fill=c, width=4)
    d.line([x, y, x + math.sin(ang * 2.4) * r * 0.85, y - math.cos(ang * 2.4) * r * 0.85],
           fill=c, width=3)


# ============================================================ guildshore-style caption/dashboard system
#
# Reference behaviors observed from @guildshore's reels (real screen-recorded
# financial dashboards + burned-in captions, not vector infographics):
#   - one dominant caption at a time, lower-third, dark semi-transparent bar,
#     bold clean sans, short ALL-CAPS-ish phrases -- not 3-4 simultaneous
#     text elements spread across the frame.
#   - hooks are instant: bold statement is already on screen frame 1, no
#     build-up glow.
#   - numbers are shown like a real financial UI: dark panel, label/value
#     rows, a highlighted hero value, a progress/allocation bar, sometimes
#     a cursor pointer "clicking" the number that matters.
# These helpers translate that into this engine's flat-vector primitives.

def caption_bar(d, cx, y, t_abs, trig, text, px=34, color=None, dur=0.16, w=None):
    color = FG if color is None else color
    """Lower-third burned-in-caption look: bar + bold text, one line.
    This is the PRIMARY narration text for this story -- not a spread-out
    kicker/statement/footnote hierarchy."""
    sc = current_scene()
    xx, yy, ppx = cx, y, px
    if sc is not None:
        p = sc.pos(text)
        if p:
            xx, yy, ppx = p
    aq = clamp01((t_abs - trig) / dur)
    aq = aq * aq * (3 - 2 * aq)
    if aq <= 0.02:
        return
    f = g.Fonts.get(int(ppx))
    tw = d.textlength(text, font=f)
    bw = w or (tw + 64)
    bh = ppx + 40
    slide = (1 - aq) * 14
    by = yy + slide
    d.rounded_rectangle([xx - bw / 2, by - bh / 2, xx + bw / 2, by + bh / 2],
                        radius=14, fill=CAP_BG, outline=CAP_BORDER, width=2 if CAP_BORDER else 0)
    g.big_text(d, xx, by, text, color=dim_col(color, aq), px=ppx)


def dashboard_panel(d, x, y, w, h, a=1.0, accent=None):
    """Financial-dashboard panel shell: border + header rule."""
    accent = accent or SKY
    d.rounded_rectangle([x - w / 2 + 6, y - h / 2 + 6, x + w / 2 + 6, y + h / 2 + 6],
                        radius=18, fill=PANEL_SHADOW)
    d.rounded_rectangle([x - w / 2, y - h / 2, x + w / 2, y + h / 2],
                        radius=18, outline=dim_col(g.GRAY, a), width=3,
                        fill=PANEL_BG)
    d.line([x - w / 2 + 20, y - h / 2 + 46, x + w / 2 - 20, y - h / 2 + 46],
           fill=dim_col(accent, 0.5 * a), width=2)


def dash_row(d, x0, x1, y, label, value, color=None, px=24, a=1.0, bar=None, bar_color=None):
    color = FG if color is None else color
    """One label(left)/value(right) row spanning [x0,x1] inside a
    dashboard_panel; `bar` (0..1) draws an allocation/progress bar under
    the row if given."""
    f = g.Fonts.get(px)
    g.big_text(d, x0, y - px / 2, label, color=dim_col(g.GRAY, a), px=px, anchor_mid=False)
    vw = d.textlength(value, font=f)
    g.big_text(d, x1 - vw, y - px / 2, value, color=dim_col(color, a), px=px, anchor_mid=False)
    if bar is not None:
        by0 = y + px * 0.55
        d.rounded_rectangle([x0, by0, x1, by0 + 8], radius=4,
                            outline=dim_col(g.GRAY, 0.5 * a), width=2)
        fw = max(4, (x1 - x0) * clamp01(bar))
        d.rounded_rectangle([x0, by0, x0 + fw, by0 + 8], radius=4,
                            fill=dim_col(bar_color or color, a))


def cursor_g(d, x, y, a=1.0, color=None):
    color = FG if color is None else color
    """Small screen-recording-style mouse pointer, to sell 'someone is
    showing you a real number' the way a cursor click-highlight does."""
    c = dim_col(color, a)
    pts = [(x, y), (x, y + 26), (x + 6, y + 20), (x + 10, y + 29),
           (x + 14, y + 27), (x + 10, y + 18), (x + 18, y + 18)]
    d.polygon(pts, fill=c, outline=(0, 0, 0))


def checklist_row(d, x, y, text, t_abs, trig, color=None, px=28, dur=0.2):
    color = SKY if color is None else color
    a = clamp01((t_abs - trig) / dur)
    if a <= 0.02:
        return
    r = 16
    st = g.spring(a, k=14)
    d.ellipse([x - r, y - r, x + r, y + r], outline=dim_col(color, a), width=4)
    if st > 0.3:
        g.check(d, x, y, size=int(10 * st), color=color, lw=4)
    g.big_text(d, x + 40, y, text, color=dim_col(FG, a), px=px, anchor_mid=False)


# ============================================================ premium explainer system
#
# Second visual pass, per the user's explicit editing-style brief (modeled
# on a real guildshore reel): clean jump cuts, minimal gray caption bars
# (already built above), white-background explainer cutaways for concepts,
# an expanded dark-mode "underwriting platform" look for numbers, and
# restrained motion -- no crash/flash collisions, no oversized text pops.
# collide()/card_glyph()/xmark_glyph() below are kept (harmless, unused)
# rather than deleted, since Iteration 13/14 still reference the pattern.


def explainer_card(d, x, y, w, h, a=1.0):
    """White 'explainer graphic' card floating on the dark scene -- reads as
    a white-background cutaway without reworking the whole frame/post-process
    pipeline (built for a dark scene) into a second light-mode variant."""
    if a <= 0.02:
        return
    halo(d, x, y, max(w, h) * 0.55, g.WHITE, alpha=0.05 * a)
    if LIGHT_THEME:
        off = 8
        d.rounded_rectangle([x - w / 2 + off, y - h / 2 + off, x + w / 2 + off, y + h / 2 + off],
                            radius=24, fill=dim_col(PANEL_SHADOW, a))
    d.rounded_rectangle([x - w / 2, y - h / 2, x + w / 2, y + h / 2], radius=24,
                        fill=dim_col(g.WHITE, a), outline=dim_col((210, 210, 218), a), width=2)


def doc_icon(d, x, y, s=60, color=None, a=1.0):
    color = INK if color is None else color
    c = dim_col(color, a)
    w, h = s * 0.78, s
    d.rounded_rectangle([x - w / 2, y - h / 2, x + w / 2, y + h / 2], radius=6, outline=c, width=4)
    for i in range(4):
        ly = y - h / 2 + h * 0.3 + i * h * 0.16
        d.line([x - w / 2 + w * 0.18, ly, x + w / 2 - w * 0.18, ly], fill=c, width=3)


def bldg_icon(d, x, y, s=60, color=None, a=1.0):
    color = INK if color is None else color
    c = dim_col(color, a)
    w, h = s * 0.9, s * 1.1
    d.rectangle([x - w / 2, y - h / 2, x + w / 2, y + h / 2], outline=c, width=4)
    for row in range(3):
        for col in range(2):
            wx = x - w / 2 + w * 0.22 + col * w * 0.42
            wy = y - h / 2 + h * 0.18 + row * h * 0.26
            ww, wh = w * 0.14, h * 0.12
            d.rectangle([wx - ww / 2, wy - wh / 2, wx + ww / 2, wy + wh / 2], outline=c, width=2)


def dash_header(d, x, y, w, title):
    g.big_text(d, x, y + 6, title, color=FG, px=23)
    d.line([x - w / 2, y + 24, x + w / 2, y + 24], fill=dim_col(g.GRAY, 0.35), width=2)


def result_chip(d, x0, x1, y, label, value, color=None, px=24, a=1.0):
    color = SKY if color is None else color
    h = px + 30
    d.rounded_rectangle([x0, y - h / 2, x1, y + h / 2], radius=12, fill=dim_col(color, 0.14 * a))
    g.big_text(d, x0 + 18, y - (px - 4) / 2, label, color=dim_col(color, a), px=px - 4, anchor_mid=False)
    f = g.Fonts.get(px)
    vw = d.textlength(value, font=f)
    g.big_text(d, x1 - 18 - vw, y - px / 2, value, color=dim_col(FG, a), px=px, anchor_mid=False)


# ============================================================ collision helper

def collide(d, t_abs, trig, dur, x1, y1, x2, y2, draw_a, draw_b,
            impact_color=g.WHITE, impact_r=170):
    """Two elements accelerate toward a shared point and crash together with
    an impact flash. Pair the same `trig+dur` instant with a stamp/slam
    sfx_event so the shared engine's beat-locked camera punches on contact
    (camera_punch_events() keys off the same SFX names)."""
    prog = clamp01((t_abs - trig) / dur)
    e = g.ease_in(prog)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    ax, ay = g.lerp(x1, cx, e), g.lerp(y1, cy, e)
    bx, by = g.lerp(x2, cx, e), g.lerp(y2, cy, e)
    if prog > 0.01:
        draw_a(d, ax, ay, prog)
        draw_b(d, bx, by, prog)
    since = t_abs - (trig + dur)
    if -0.02 <= since < 0.4:
        f = (1 - g.ease_out(clamp01(since / 0.35))) if since > 0 else 1.0
        if f > 0.03:
            halo(d, cx, cy, impact_r * (0.3 + 0.7 * f), impact_color, alpha=0.55 * f)
    return cx, cy, prog >= 0.999


def money_glyph(n=6, r=12, color=None):
    color = color or SKY

    def _draw(d, x, y, prog):
        g._coin_pile(d, x, y - n * 10, n, color, r=r, gap=20)
    return _draw


def card_glyph(w, h, color, text, px=26, text_color=None):
    """Opaque-filled card (unlike the shared outline-only `card()`): when two
    colliding elements land on the same spot, whichever is drawn second must
    fully occlude the first or their labels garble together."""
    text_color = text_color or color

    def _draw(d, x, y, prog):
        a = clamp01(prog * 1.6)
        if a > 0.05:
            d.rounded_rectangle([x - w / 2, y - h / 2, x + w / 2, y + h / 2],
                                radius=20, fill=PANEL_BG)
        card(d, x, y, w, h, color, a=a, shadow=False)
        if a > 0.3:
            g.big_text(d, x, y, text, color=dim_col(text_color, a), px=px)
    return _draw


def xmark_glyph(size=70, color=g.RED):
    def _draw(d, x, y, prog):
        s = g.elastic(prog) * size
        if s > 2:
            g.xmark(d, x, y, size=s, color=color, lw=8)
    return _draw


# ============================================================ scene: clip 1

def draw1(d, t_abs):
    set_beat(1, g.local_beat(CLIPS[0], t_abs)[0])
    idx, p = g.local_beat(CLIPS[0], t_abs)
    cx, cy = g.W // 2, g.H // 2 + 90
    base = cy + 190
    c = CLIPS[0]

    if idx == 0:
        pa = g.ease_out(clamp01(p / 0.3))
        pcy, ph, pw = cy - 90, 190, 460
        top = pcy - ph / 2
        header_y = top + 34
        row_y = header_y + 56
        dashboard_panel(d, cx, pcy, pw, ph)
        dash_header(d, cx, header_y, pw - 40, "MONTHLY CASH FLOW")
        dash_row(d, cx - 190, cx + 190, row_y, "INCOME", "+$1,200/mo", color=SKY,
                 a=clamp01(pa * 2), bar=pa, bar_color=SKY)
        if pa > 0.5:
            cursor_g(d, cx + 150, row_y - 38, a=clamp01((pa - 0.5) * 2))
        caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, 0, 0.1), "NOT AN INCOME PROBLEM", 34)
    elif idx == 1:
        pa = g.ease_out(clamp01(p / 0.35))
        pcy, ph, pw = cy - 60, 260, 480
        top = pcy - ph / 2
        header_y = top + 34
        row1_y = header_y + 56
        row2_y = row1_y + 90
        dashboard_panel(d, cx, pcy, pw, ph)
        dash_header(d, cx, header_y, pw - 40, "MONTHLY CASH FLOW")
        dash_row(d, cx - 200, cx + 200, row1_y, "RAISE", "+$1,200/mo", color=SKY,
                 bar=1.0, bar_color=SKY)
        dash_row(d, cx - 200, cx + 200, row2_y, "SPENDING", "+$1,200/mo", color=g.RED,
                 a=clamp01(pa * 2), bar=pa, bar_color=g.RED)
        if pa > 0.6:
            cursor_g(d, cx + 130, row2_y - 38, a=clamp01((pa - 0.6) * 2.5))
        caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, 1, 0.1), "EVERY RAISE GETS MATCHED", 32)
    else:
        spend = g.beat_word_p(c, 2, "spend")
        trig = g.beat_abs(c, 2, spend)
        ra = clamp01((t_abs - trig) / 0.3)
        pcy, ph, pw = cy - 90, 320, 480
        top = pcy - ph / 2
        header_y = top + 34
        row1_y = header_y + 56
        row2_y = row1_y + 90
        chip_y = row2_y + 90
        dashboard_panel(d, cx, pcy, pw, ph)
        dash_header(d, cx, header_y, pw - 40, "MONTHLY CASH FLOW")
        dash_row(d, cx - 200, cx + 200, row1_y, "RAISE", "+$1,200/mo", color=SKY, bar=1.0, bar_color=SKY)
        dash_row(d, cx - 200, cx + 200, row2_y, "SPENDING", "+$1,200/mo", color=g.RED, bar=1.0, bar_color=g.RED)
        if ra > 0.05:
            result_chip(d, cx - 200, cx + 200, chip_y, "LEFT OVER", "$0", color=g.RED, px=26, a=ra)
        caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, 2, 0.05), "GONE. EVERY TIME.", 36, g.RED)


# ============================================================ scene: clip 2

def draw2(d, t_abs):
    set_beat(2, g.local_beat(CLIPS[1], t_abs)[0])
    idx, p = g.local_beat(CLIPS[1], t_abs)
    cx, cy = g.W // 2, g.H // 2 + 90
    c = CLIPS[1]

    rounds = [
        ("raise", "car", "RAISE", "NEW CAR", "RAISE? NEW CAR.", 38),
        ("bonus", "vacation", "BONUS", "NEW VACATION", "BONUS? NEW VACATION.", 36),
        ("figures", "lifestyle", "SIX FIGURES", "SIX FIGURE LIFESTYLE", "MORE INCOME? MORE OUTGO.", 30),
    ]
    key0, key1, labA, labB, statement, spx = rounds[idx]
    a1 = g.ease_out(clamp01(p / 0.3))
    trig2 = g.beat_word_p(c, idx, key1)
    a2 = g.ease_out(clamp01((p - trig2) / 0.35)) if p > trig2 else 0.0

    pcy, pw, ph = cy - 40, 460, 300
    top = pcy - ph / 2
    row1_y = top + 90
    row2_y = row1_y + 110

    explainer_card(d, cx, pcy, pw, ph)
    g.big_text(d, cx - pw / 2 + 24, top + 24, f"{idx + 1}/3", color=MUTE, px=18, anchor_mid=False)
    if a1 > 0.02:
        bldg_icon(d, cx - pw / 2 + 66, row1_y, s=56, color=SKY, a=a1)
        g.big_text(d, cx - pw / 2 + 118, row1_y - 15, labA, color=dim_col(INK, a1), px=30, anchor_mid=False)
    if a2 > 0.02:
        g.arrow(d, cx - pw / 2 + 66, row1_y + 42, cx - pw / 2 + 66, row2_y - 40,
               color=dim_col(MUTE, a2), lw=5)
        doc_icon(d, cx - pw / 2 + 66, row2_y, s=56, color=g.RED, a=a2)
        g.big_text(d, cx - pw / 2 + 118, row2_y - 15, labB, color=dim_col(g.RED, a2), px=27, anchor_mid=False)
    caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, idx, 0.05), statement, spx)


# ============================================================ scene: clip 3

def draw3(d, t_abs):
    set_beat(3, g.local_beat(CLIPS[2], t_abs)[0])
    idx, p = g.local_beat(CLIPS[2], t_abs)
    cx, cy = g.W // 2, g.H // 2 + 90
    c = CLIPS[2]

    if idx == 0:
        a = g.ease_out(clamp01(p / 0.35))
        explainer_card(d, cx, cy + 20, 480, 200, a=a)
        if a > 0.4:
            doc_icon(d, cx, cy - 30, s=60, color=INK, a=a)
            g.big_text(d, cx, cy + 55, "I JUST NEED MORE MONEY",
                      color=dim_col(INK, a), px=26)
        caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, 0, 0.1), "THE AUDACITY TO SAY...", 32)
    elif idx == 1:
        explainer_card(d, cx, cy + 20, 480, 200)
        doc_icon(d, cx, cy - 30, s=60, color=INK)
        g.big_text(d, cx, cy + 55, "I JUST NEED MORE MONEY", color=INK, px=26)
        no = g.beat_word_p(c, 1, "No")
        st = g.spring(clamp01((p - no) / 0.16), k=16)
        if st > 0.05:
            g.stamp_x(d, cx, cy - 30, size=100 * st, color=g.RED, rot=0.3 * st, opaque=0.9)
        caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_word_t(c, 1, "No"), "NO.", 58, g.RED)
    else:
        rise = g.ease_out(clamp01(p / 0.7))
        inc_y = cy + 220 - rise * 260
        exp_y = cy + 220 - rise * 260
        g.arrow(d, cx - 200, cy + 220, cx - 40, inc_y, color=SKY, lw=8)
        g.arrow(d, cx + 200, cy + 220, cx + 40, exp_y, color=g.RED, lw=8)
        if rise > 0.85:
            halo(d, cx, inc_y, 90, FG, alpha=0.4)
        g.big_text(d, cx - 200, cy + 260, "INCOME", color=SKY, px=26)
        g.big_text(d, cx + 200, cy + 260, "EXPENSES", color=g.RED, px=26)
        caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, 2, 0.1), "STOP MATCHING EVERY RAISE", 30)


# ============================================================ scene: clip 4

def draw4(d, t_abs):
    set_beat(4, g.local_beat(CLIPS[3], t_abs)[0])
    idx, p = g.local_beat(CLIPS[3], t_abs)
    cx, cy = g.W // 2, g.H // 2 + 90
    c = CLIPS[3]

    if idx == 0:
        pulse = 0.5 + 0.5 * math.sin(t_abs * 4)
        halo(d, cx, cy + 60, 200 + 40 * pulse, g.RED, alpha=0.16)
        caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, 0, 0.1), "HERE'S THE TRUTH", 36)
    else:
        eat_t = g.beat_word_t(c, 1, "eating")
        grow = clamp01((t_abs - eat_t) / 1.6) if t_abs > eat_t else 0.0
        ca = g.ease_out(clamp01(p / 0.3)) if idx == 1 else 1.0
        explainer_card(d, cx, cy + 60, 300, 220, a=ca)
        if ca > 0.3:
            bldg_icon(d, cx, cy + 10, s=70, color=SKY, a=ca * (1.0 - grow * 0.5))
            g.big_text(d, cx, cy + 90, "FUTURE", color=dim_col(INK, ca * (1.0 - grow * 0.4)), px=28)
        if grow > 0.02:
            r = 40 + grow * 190
            d.ellipse([cx - r, cy + 40 - r, cx + r, cy + 40 + r], fill=dim_col((60, 60, 66), 0.85 * grow))
        if idx == 1:
            caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, 1, 0.1),
                       "YOUR LIFESTYLE IS EATING IT", 30)
        else:
            caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, 2, 0.05), "PIECE BY PIECE", 36)


# ============================================================ scene: clip 5

def draw5(d, t_abs):
    set_beat(5, g.local_beat(CLIPS[4], t_abs)[0])
    idx, p = g.local_beat(CLIPS[4], t_abs)
    cx, cy = g.W // 2, g.H // 2 + 90
    c = CLIPS[4]

    goal_y = cy - 80 if idx == 0 else cy - 240
    goal_dim = 1.0 if idx == 0 else 0.4
    card(d, cx, goal_y, 220 if idx else 260, 90 if idx else 110, SKY, a=goal_dim)
    g.big_text(d, cx, goal_y, "FREEDOM", color=dim_col(SKY, goal_dim), px=26)
    if idx:
        dashboard_panel(d, cx, goal_y + 70, 260, 70)
        dash_row(d, cx - 100, cx + 100, goal_y + 74, "PROGRESS", "4%", color=g.GRAY, px=16,
                 bar=0.04, bar_color=g.GRAY)

    if idx == 0:
        halo(d, cx, goal_y, 180, SKY, alpha=0.2)
        caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, 0, 0.1), "YOU WANT FREEDOM?", 36)
    elif idx == 1:
        trig = g.beat_abs(c, 1, g.beat_word_p(c, 1, "dollar"))
        ra = g.ease_out(clamp01((t_abs - trig) / 0.35)) if t_abs > trig else 0.0
        card(d, cx, cy + 200, 240, 130, g.RED, a=clamp01(ra * 2))
        if ra > 0.3:
            g.big_text(d, cx, cy + 200, "LOOK RICH", color=dim_col(g.RED, clamp01(ra * 2)), px=26)
        if ra > 0.5:
            g._coin_pile(d, cx - 160, cy + 260, 4, SKY, r=11, gap=18, rot=t_abs)
        caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, 1, 0.05),
                   "BUT CHASE THE LOOK INSTEAD", 28)
    else:
        card(d, cx, cy + 100, 240, 130, g.RED, a=1.0)
        g.big_text(d, cx, cy + 100, "LOOK RICH", color=g.RED, px=26)
        caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, 2, 0.1), "NOT ONE DOLLAR TOWARD IT", 28)


# ============================================================ scene: clip 6

def draw6(d, t_abs):
    set_beat(6, g.local_beat(CLIPS[5], t_abs)[0])
    idx, p = g.local_beat(CLIPS[5], t_abs)
    cx, cy = g.W // 2, g.H // 2 + 90
    base = cy + 190
    c = CLIPS[5]

    if idx == 0:
        clock_g(d, cx, cy + 20, 70, SKY, deg=t_abs * 90)
        halo(d, cx, cy + 20, 150, SKY, alpha=0.2)
        caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, 0, 0.1), "YOU WANT OUT EARLY?", 36)
    elif idx == 1:
        dashboard_panel(d, cx, cy - 30, 420, 180)
        dash_header(d, cx, cy - 30 - 90 + 34, 380, "RETIREMENT READINESS")
        dash_row(d, cx - 170, cx + 170, cy - 10, "ASSETS OWNED", "0", color=g.RED, px=24,
                 bar=0.0, bar_color=g.RED)
        caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, 1, 0.15), "ZERO ASSETS BOUGHT", 34)
    else:
        stop = g.beat_word_p(c, 2, "working")
        clock_g(d, cx, cy + 20, 70, g.RED if p > stop else SKY, deg=min(90, p * 300))
        halo(d, cx, cy + 20, 150, g.RED if p > stop else SKY, alpha=0.25)
        caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, 2, 0.05), "NOTHING PAYS YOU BACK", 30)


# ============================================================ scene: clip 7

def draw7(d, t_abs):
    set_beat(7, g.local_beat(CLIPS[6], t_abs)[0])
    idx, p = g.local_beat(CLIPS[6], t_abs)
    cx, cy = g.W // 2, g.H // 2 + 90
    base = cy + 190
    c = CLIPS[6]

    if idx == 0:
        a = g.ease_out(clamp01(p / 0.3))
        trig = g.beat_abs(c, 0, g.beat_word_p(c, 0, "money"))
        explainer_card(d, cx, cy + 20, 420, 160, a=a)
        if a > 0.3:
            g.big_text(d, cx, cy + 20, "HOW DO I MAKE MORE?", color=dim_col(INK, a), px=24)
        if t_abs > trig:
            xf = g.ease_out(clamp01((t_abs - trig) / 0.25))
            g.xmark(d, cx, cy + 20, size=int(70 * xf), color=g.RED, lw=8)
        caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, 0, 0.55), "WRONG QUESTION", 38, g.RED)
    elif idx == 1:
        g.gold_building(d, cx + 120, base, 200, int(120 * g.spring(p, k=8)), alpha=1.0, shadow=True, color=SKY, shadow_color=PANEL_SHADOW)
        g.arrow(d, cx - 180, cy, cx + 30, base - 100, color=SKY, lw=7)
        caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, 1, 0.1), "RIGHT QUESTION:", 38)
    else:
        g.gold_building(d, cx + 120, base, 200, 220, alpha=1.0, shadow=True, color=SKY, shadow_color=PANEL_SHADOW)
        pay = g.beat_word_p(c, 2, "pays")
        if p > pay:
            g.check(d, cx + 120, base - 240, size=26, color=SKY, lw=6)
            halo(d, cx + 120, base - 220, 120, SKY, alpha=0.25)
        caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, 2, 0.05), "HOW DO I MAKE IT PAY ME?", 28)


# ============================================================ scene: clip 8

def draw8(d, t_abs):
    set_beat(8, g.local_beat(CLIPS[7], t_abs)[0])
    idx, p = g.local_beat(CLIPS[7], t_abs)
    cx, cy = g.W // 2, g.H // 2 + 90
    base = cy + 190
    c = CLIPS[7]

    if idx == 0:
        g.gold_building(d, cx, base, 260, int(220 * g.spring(p, k=9)), alpha=1.0, shadow=True, color=SKY, shadow_color=PANEL_SHADOW)
        halo(d, cx, base - 100, 220, SKY, alpha=0.18)
        caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, 0, 0.1), "BUILD REAL ASSETS", 34)
    elif idx == 1:
        pcy, ph, pw = cy - 90, 280, 400
        top = pcy - ph / 2
        header_y = top + 34
        row1_y = header_y + 56
        dashboard_panel(d, cx, pcy, pw, ph)
        dash_header(d, cx, header_y, pw - 40, "WHAT WE BUILD")
        checklist_row(d, cx - 140, row1_y, "ASSETS", t_abs, g.beat_abs(c, 1, 0.1), color=SKY)
        checklist_row(d, cx - 140, row1_y + 70, "INCOME", t_abs, g.beat_abs(c, 1, 0.4), color=SKY)
        checklist_row(d, cx - 140, row1_y + 140, "WEALTH", t_abs, g.beat_abs(c, 1, 0.7), color=SKY)
        caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, 1, 0.02), "ASSETS. INCOME. WEALTH.", 30)
    else:
        g.gold_building(d, cx - 140, base, 220, 200, alpha=1.0, shadow=True, color=SKY, shadow_color=PANEL_SHADOW)
        pay = g.beat_word_p(c, 2, "paycheck")
        fo = clamp01((p - pay) / 0.6)
        px, py = cx + 190, base - 60
        card(d, px, py, 190, 90, g.GRAY, a=1.0 - fo)
        if fo < 0.9:
            g.big_text(d, px, py, "PAYCHECK", color=dim_col(g.GRAY, 1.0 - fo), px=22)
        caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, 2, 0.05),
                   "WEALTH THAT DOESN'T NEED YOU", 26)


# ============================================================ scene: clip 9

def draw9(d, t_abs):
    set_beat(9, g.local_beat(CLIPS[8], t_abs)[0])
    idx, p = g.local_beat(CLIPS[8], t_abs)
    cx, cy = g.W // 2, g.H // 2 + 90
    base = cy + 190
    c = CLIPS[8]

    if idx == 0:
        pop = g.ease_out(clamp01(p / 0.3))
        explainer_card(d, cx, cy, 320, 150, a=clamp01(pop * 2))
        if pop > 0.3:
            g.big_text(d, cx, cy, "LOOKING RICH", color=dim_col(INK, clamp01(pop * 2)), px=32)
        caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, 0, 0.05), "LOOKING RICH IS EASY", 34)
    elif idx == 1:
        g.gold_building(d, cx, base, 260, int(180 * g.spring(p, k=6)), alpha=1.0, shadow=True, color=SKY, shadow_color=PANEL_SHADOW)
        caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, 1, 0.05),
                   "BUILDING WEALTH IS THE PART", 28)
    else:
        h = 180 + int(80 * g.spring(p, k=7))
        g.gold_building(d, cx, base, 260, h, alpha=1.0, shadow=True, color=SKY, shadow_color=PANEL_SHADOW)
        halo(d, cx, base - h // 2, 100 + h * 0.6, SKY, alpha=0.22)
        got = g.beat_word_p(c, 2, "around")
        if p > got:
            g.check(d, cx, base - h - 40, size=30, color=SKY, lw=7)
        caption_bar(d, cx, cy + CAP_Y, t_abs, g.beat_abs(c, 2, 0.05), "MOST PEOPLE NEVER GET TO", 28)
        caption_bar(d, cx, cy + CAP_Y - 100, t_abs, g.beat_abs(c, 2, 0.65), "START TODAY", 30, SKY)


REG = {}
for _i in range(1, 10):
    REG[_i] = globals()[f"draw{_i}"]


# ============================================================ render pipeline

def bg_scene(d, t_abs):
    if SHOW_GRID:
        for x in range(0, g.W, 88):
            d.line([x, 0, x, g.H], fill=GRID_LINE, width=1)
        for y in range(0, g.H, 88):
            d.line([0, y, g.W, y], fill=GRID_LINE, width=1)
    d.line([0, g.H - 90, g.W, g.H - 90], fill=GRID_BASE, width=2)


def finish_frame(img, frame_idx):
    """bloom() is an additive glow built for bright elements on a dark
    background -- on a light page it blurs-and-adds toward white, which
    washes out thin borders and small text sitting next to large light
    regions (a dashboard panel's outline all but disappears). Skip it in
    light theme; post_process's grade/vignette/grain are theme-agnostic."""
    if not POST_FX:
        return img
    if LIGHT_THEME:
        return g.post_process(img, frame_idx=frame_idx)
    return g.post_process(g.bloom(img), frame_idx=frame_idx)


def render_frame(cid, t_abs):
    img = g.Image.new("RGB", (g.RW, g.RH), PAGE_BG)
    raw = g.ImageDraw.Draw(img)
    d = g.D2(raw)
    bg_scene(d, t_abs)
    REG[cid](d, t_abs)
    clip = g.CLIPS[cid - 1]
    scale, px, py = g.camera_state(clip, t_abs, base_drift=CAM_DRIFT, punch_amt=0.0)
    framed = g.apply_camera(img, scale, px, py)
    return finish_frame(framed, round(t_abs * g.FPS))


def render_clip(clip):
    import shutil
    cid = clip["id"]
    dirpath = g.FRAMES_DIR / f"clip{cid}"
    if dirpath.exists():
        shutil.rmtree(dirpath)
    dirpath.mkdir(parents=True, exist_ok=True)
    audio_path = g.AUDIO_DIR / f"clip{cid}.mp3"
    audio_dur = g.get_audio_duration(audio_path)
    pad_before = g.PAD_BEFORE.get(cid, 0.45)
    total = max(1, int((audio_dur + pad_before + g.PAD_AFTER) * g.FPS))
    clip["total_frames"] = total
    for f in range(total):
        t_abs = f / g.FPS
        render_frame(cid, t_abs).save(dirpath / f"frame_{f:04d}.png")


def _render_frame_chunk(args):
    """Multiprocessing worker: re-imports and re-applies the story (each
    worker is a fresh interpreter under Windows' spawn start method, so
    module-level caches like _TIMING_CACHE aren't inherited) then renders
    its assigned frame indices. Must stay a module-level function so it's
    picklable by name for ProcessPoolExecutor."""
    cid, frame_indices, dirpath_str = args
    import generate_video as g2
    import generate_lifestyle as m2
    m2.apply_to(g2)
    dirpath = Path(dirpath_str)
    for f in frame_indices:
        m2.render_frame(cid, f / g2.FPS).save(dirpath / f"frame_{f:04d}.png")
    return len(frame_indices)


def render_clip_parallel(clip, workers=None):
    """Same output as render_clip(), split across worker processes -- each
    frame is independent (no shared mutable state across frames), so this
    is a straightforward wall-clock win on a multi-core machine."""
    import os
    import shutil
    from concurrent.futures import ProcessPoolExecutor

    cid = clip["id"]
    dirpath = g.FRAMES_DIR / f"clip{cid}"
    if dirpath.exists():
        shutil.rmtree(dirpath)
    dirpath.mkdir(parents=True, exist_ok=True)
    audio_path = g.AUDIO_DIR / f"clip{cid}.mp3"
    audio_dur = g.get_audio_duration(audio_path)
    pad_before = g.PAD_BEFORE.get(cid, 0.45)
    total = max(1, int((audio_dur + pad_before + g.PAD_AFTER) * g.FPS))
    clip["total_frames"] = total

    workers = workers or min(8, os.cpu_count() or 4)
    workers = max(1, min(workers, total))
    chunks = [list(range(i, total, workers)) for i in range(workers)]
    tasks = [(cid, chunk, str(dirpath)) for chunk in chunks if chunk]
    with ProcessPoolExecutor(max_workers=len(tasks)) as ex:
        for _ in ex.map(_render_frame_chunk, tasks):
            pass


# ============================================================ intro / outro

def _find_word_time(words, target, occurrence=1):
    """Start time (seconds, relative to the narration's own t=0) of the
    Nth occurrence of a normalized word token, or None if not found."""
    n = 0
    for w in words:
        if g.norm_tok(w["word"]) == target:
            n += 1
            if n == occurrence:
                return w["start"]
    return None


def intro_setup():
    """(total seconds, total frames, hard-cut time) of the spoken hook."""
    hook = load_hook_timing()
    words = hook["words"]
    word_end_dur = hook["duration"]     # last word's end time -- for the cut-point fallback only
    hook_dur = g.get_audio_duration(g.AUDIO_DIR / f"clip{HOOK_ID}.mp3")  # real (trimmed) file duration
    total_dur = hook_dur + g.INTRO_PAD_BEFORE + g.INTRO_PAD_AFTER
    total_frames = max(1, int(total_dur * g.FPS))
    cut_local = _find_word_time(words, "youre", occurrence=2)
    if cut_local is None:
        cut_local = word_end_dur * 0.5
    return total_dur, total_frames, g.INTRO_PAD_BEFORE + cut_local


def intro_frame(f, setup=None):
    """Instant hard-cut hook (guildshore-style): bold statement is already
    on screen at frame 1 -- no glow build-up to wait through -- then a
    single hard cut (white flash + camera punch) to the sharper line, timed
    to the actual spoken narration instead of a silent fixed 2.0s clock, so
    the hook is heard as it's shown, not just displayed silently."""
    total_dur, _total_frames, cut_t = setup or intro_setup()
    cx, cy = g.W // 2, g.H // 2 - 20
    t = f / g.FPS
    img = g.Image.new("RGB", (g.RW, g.RH), PAGE_BG)
    raw = g.ImageDraw.Draw(img)
    d = g.D2(raw)
    bg_scene(d, t)

    cut_f = int(cut_t * g.FPS)
    # frame-indexed (not continuous-time) so the hook is on screen at
    # literal frame 0 -- a fractional-second fade would leave frame 0
    # blank, exactly the "dead first frame" this redesign is fixing.
    if f < cut_f:
        halo(d, cx, cy, 300, FG, alpha=0.16)
        g.big_text(d, cx, cy, "YOU'RE NOT BROKE.", px=52, color=FG)
    else:
        halo(d, cx, cy, 340, g.RED, alpha=0.22)
        g.big_text(d, cx, cy, "YOU'RE LEAKING.", px=60, color=g.RED)
        trig = cut_t + 0.05
        collide(d, t, trig, 0.2,
                cx - 260, cy + 260, cx + 260, cy + 260,
                money_glyph(7), card_glyph(220, 110, g.RED, "SPENT", 26),
                impact_color=g.RED, impact_r=180)

    # a 2-frame flash strictly AFTER the cut (never straddling both
    # lines) so it reads as a punch on the reveal, not a whiteout
    frames_since_cut = f - cut_f
    flash = max(0.0, 1.0 - frames_since_cut * 0.55) if 0 <= frames_since_cut < 2 else 0.0
    if flash > 0.02:
        d.rectangle([0, 0, g.W, g.H], fill=dim_col(FLASH_COLOR, flash * 0.55))

    fade_out = 1 - g.ease_out(clamp01((t - (total_dur - 0.25)) / 0.25))
    punch = 0.05 * math.exp(-(t - cut_t) / 0.18) if cut_t <= t < cut_t + 0.5 else 0.0
    cam_scale = 1.0 + 0.02 * g.ease(clamp01(t / max(0.5, total_dur))) + punch
    framed = g.apply_camera(img, cam_scale, 0.0, 0.0)
    out = finish_frame(framed, f)
    if fade_out < 0.999:
        out = g.Image.blend(g.Image.new("RGB", out.size, PAGE_BG), out, fade_out)
    return out


def create_intro_clip():
    import shutil
    dirpath = g.FRAMES_DIR / "intro"
    if dirpath.exists():
        shutil.rmtree(dirpath)
    dirpath.mkdir(parents=True, exist_ok=True)
    setup = intro_setup()
    for f in range(setup[1]):
        intro_frame(f, setup).save(dirpath / f"frame_{f:04d}.png")


def outro_frame(f):
    cx, cy = g.W // 2, g.H // 2 + 40
    t = f / g.FPS
    img = g.Image.new("RGB", (g.RW, g.RH), PAGE_BG)
    raw = g.ImageDraw.Draw(img)
    d = g.D2(raw)
    bg_scene(d, t)
    h = int(240 * g.spring(clamp01(t / 0.6), k=9))
    g.gold_building(d, cx, cy + 160, 260, h, alpha=1.0, shadow=True, color=SKY, shadow_color=PANEL_SHADOW)
    halo(d, cx, cy + 160 - h // 2, 120 + h * 0.6, SKY, alpha=0.3)
    a2 = g.elastic(clamp01((t - 0.5) / 0.45))
    fade_out = 1 - g.ease_out(clamp01((t - 1.5) / 0.5))
    a2 *= fade_out
    if a2 > 0.1:
        g.big_text(d, cx, cy - 260, "STOP LOOKING RICH.", px=40, color=dim_col(FG, a2))
        g.big_text(d, cx, cy - 190, "START BUILDING WEALTH.", px=40, color=dim_col(SKY, a2))
    return finish_frame(img.resize((g.W, g.H), g.Image.LANCZOS), f)


def create_outro_clip():
    import shutil
    dirpath = g.FRAMES_DIR / "outro"
    if dirpath.exists():
        shutil.rmtree(dirpath)
    dirpath.mkdir(parents=True, exist_ok=True)
    for f in range(2 * g.FPS):
        outro_frame(f).save(dirpath / f"frame_{f:04d}.png")


# ============================================================ sound design

def sfx_events(clip):
    cid = clip["id"]
    beats = g.clip_beats(clip)
    evs = []
    if not beats:
        return evs
    b0, b1, b2 = beats[0], beats[1], beats[2]

    if cid == 1:
        evs += [(b0[0], "whoosh", 0.5), (b0[1] - 0.2, "tick", 0.45)]
        evs += [(b1[0], "rise", 0.45), (b1[1] - 0.15, "tick", 0.4)]
        spend_t = g.beat_word_t(clip, 2, "spend")
        evs += [(spend_t + 0.28, "slam", 0.6), (spend_t + 0.32, "crumble", 0.4)]
    elif cid == 2:
        for i in range(3):
            key1 = ("car", "vacation", "lifestyle")[i]
            t_hit = g.beat_word_t(clip, i, key1)
            evs.append((max(0.0, t_hit - 0.05), "whoosh", 0.4))
            evs.append((t_hit + 0.24, "stamp", 0.55))
            evs.append((t_hit + 0.3, "crumble", 0.35))
    elif cid == 3:
        evs += [(b0[0], "whoosh", 0.4)]
        no_t = g.beat_word_t(clip, 1, "No")
        evs += [(no_t, "slam", 0.6), (no_t + 0.05, "stamp", 0.5)]
        evs += [(b2[0] + 0.1, "rise", 0.5), (b2[1] - 0.3, "ding", 0.5)]
    elif cid == 4:
        evs += [(b0[0], "rise", 0.45)]
        eat_t = g.beat_word_t(clip, 1, "eating")
        evs += [(eat_t, "crumble", 0.55), (eat_t + 0.6, "crumble", 0.4)]
        evs += [(b2[0] + 0.3, "crumble", 0.4)]
    elif cid == 5:
        evs += [(b0[0], "chime", 0.4)]
        dollar_t = g.beat_word_t(clip, 1, "dollar")
        evs += [(dollar_t + 0.3, "slam", 0.55), (dollar_t + 0.34, "crumble", 0.35)]
        evs += [(b2[0] + 0.2, "tick", 0.4)]
    elif cid == 6:
        evs += [(b0[0], "tick", 0.4), (b0[0] + 0.4, "tick", 0.4)]
        asset_t = g.beat_word_t(clip, 1, "asset")
        evs += [(asset_t + 0.16, "stamp", 0.55)]
        evs += [(b2[0], "tick", 0.4), (b2[1] - 0.3, "crumble", 0.4)]
    elif cid == 7:
        money_t = g.beat_word_t(clip, 0, "money")
        evs += [(money_t + 0.26, "slam", 0.55), (money_t + 0.3, "crumble", 0.35)]
        evs += [(b1[0] + 0.2, "rise", 0.5)]
        evs += [(b2[0] + 0.1, "ding", 0.55)]
    elif cid == 8:
        evs += [(b0[0], "rise", 0.5)]
        evs += [(b1[0] + 0.2, "chime", 0.5), (b1[0] + 0.5, "clink", 0.45)]
        pay_t = g.beat_word_t(clip, 2, "paycheck")
        evs += [(pay_t + 0.3, "whoosh", 0.5)]
    else:
        evs += [(b0[0], "pop", 0.5)]
        evs += [(b1[0], "rise", 0.5)]
        got_t = g.beat_word_t(clip, 2, "around")
        evs += [(got_t, "slam", 0.6), (got_t + 0.05, "chime", 0.5)]
    evs = [(max(0.0, t), n, gl) for t, n, gl in evs]
    return evs


# ============================================================ pipeline

async def main():
    print("=" * 60)
    print("Stickman Video Generator - Lifestyle Inflation (male voice)")
    print("=" * 60)
    if "--audit" in sys.argv:
        print("\n[layout] collision audit (27 beats)")
        print(layout_report())
        probs = layout_problems()
        print(f"\n[layout] unresolved problems: {len(probs)}")
        for pr in probs:
            print("  !!", pr)
        if probs:
            print("AUDIT FAIL")
            return 0 if "--no-fail" in sys.argv else 1
        print("AUDIT PASS")
        return 0
    apply_to(g)
    g.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    g.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    g.TIMING_DIR.mkdir(parents=True, exist_ok=True)
    g.FRAMES_DIR.mkdir(parents=True, exist_ok=True)

    print("\n[1/3] Generating narration + word timing...")
    await g.gen_all_audio()
    await gen_hook_narration(g)

    print("\n[2/3] Rendering frames (2x supersampled)...")
    create_intro_clip()
    for clip in CLIPS:
        print(f"  clip{clip['id']}: {clip['name']}")
        render_clip(clip)
    create_outro_clip()

    print("\n[3/3] Sound effects + encoding final video...")
    g.sfx_gen.ensure_sfx()
    final = g.compile_video()

    total = sum(len(list((g.FRAMES_DIR / f"clip{c['id']}").glob('*.png'))) for c in CLIPS) \
        + len(list((g.FRAMES_DIR / "intro").glob('*.png'))) \
        + len(list((g.FRAMES_DIR / "outro").glob('*.png')))
    print("=" * 60)
    print(f"DONE! {total} frames -> output/{final.name}")
    print("=" * 60)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
