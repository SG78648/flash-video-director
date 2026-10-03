"""generate_assets.py - second story: "income into assets" (real estate). v2 visual direction.

Design system per scene (bottom-up draw order, z-layering contract):
    1. background  - grid + ambient halo behind the subject (always behind)
    2. midground   - grounded props: floor line, piles, buildings, cards, icons
    3. accents     - stamps, cross-marks, checks ON the props
    4. text LAST   - kicker / statement / footnote, slide-fade in, never covered

Every beat uses the same vertical rhythm so the video reads like a designed
product, not a widget zoo:
    kicker   y = cy - 460   (small gray, scene title)
    statement y = cy - 360  (bold white, the line said that beat)
    diagram  y in [cy-240 .. cy+260]
    footnote y = cy + 430   (small gray/golded, reinforcing line)
"""
import asyncio
import json
import math
import shutil
import sys
from pathlib import Path

import generate_video as g

import layout_guard as lg
from layout_guard import (Scene, ground_box, coin_pile_box, house_box,
                          building_box, arrow_box, tag_box, card_box,
                          loop_box, gate_box_r, clock_box, glyph_box,
                          heart_box, skyline_box)
from layout_guard import (GROUND, PROP, ACCENT, TEXT,
                          PRIO_PIECE, PRIO_KICKER, PRIO_FOOT, PRIO_STATEMENT)

# ---- collision-free layout engine: every beat plans once, text auto-fits ----
_CID = None          # clip id the current drawer is rendering
_IDX = None          # beat index within that clip
_SC = {}             # (cid, idx) -> solved Scene


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
    """QA gate: solve every beat, return list of unresolved overlaps."""
    out = []
    for cid in range(1, 7):
        for idx in (0, 1, 2):
            out.extend(scene(cid, idx).problems)
    return sorted(set(out))


def layout_report():
    lines = []
    for cid in range(1, 7):
        for idx in (0, 1, 2):
            lines.append(scene(cid, idx).report())
    return "\n".join(lines)


def build_scene(sc, cid, idx):
    cx, cy, base = g.W // 2, g.H // 2 + 90, g.H // 2 + 190
    if cid == 1:
        if idx == 0:
            sc.fixed("floor", ground_box(cx, base + 108, 410), GROUND)
            sc.fixed("pile", coin_pile_box(cx - 280, base, 3, 15), PROP, "grow")
            sc.fixed("arrow", arrow_box((cx - 205, base - 150), (cx + 90, base - 150)), PROP, "grow")
            sc.fixed("bld", building_box(cx + 300, base, 160, 450), PROP, "grow")
            sc.fixed("orb", glyph_box(cx + 300, base - 60, 210, 90), ACCENT, "grow")
            sc.text("THE QUESTION", cx, cy - 460, "THE QUESTION", 24, PRIO_KICKER)
            sc.text("BUILD FROM ZERO", cx, cy - 360, "BUILD FROM ZERO", 44)
            sc.text("WHAT YOU EARN  ->  WHAT YOU BUILD", cx, cy + 430,
                    "WHAT YOU EARN  ->  WHAT YOU BUILD", 26, PRIO_FOOT)
        elif idx == 1:
            for i, (xx, lab) in enumerate([(cx - 215, "STOCKS"), (cx, "CRYPTO"),
                                           (cx + 215, "IDEAS")]):
                sc.fixed(f"card{i}", card_box(xx, cy, 210, 240), PROP, f"card{i}")
                sc.fixed(f"x{i}", glyph_box(xx, cy, 120, 120), ACCENT, f"card{i}")
                sc.text(lab, xx, cy + 125, lab, 26, PRIO_PIECE)
            sc.text("THE QUESTION", cx, cy - 460, "THE QUESTION", 24, PRIO_KICKER)
            sc.text("DON'T START THERE", cx, cy - 360, "DON'T START THERE", 44)
            sc.text("STOCKS, CRYPTO, OR THE NEXT BUSINESS IDEA", cx, cy + 430,
                    "STOCKS, CRYPTO, OR THE NEXT BUSINESS IDEA", 26, PRIO_FOOT)
        else:
            sc.fixed("floor", ground_box(cx, base + 108, 410), GROUND)
            sc.fixed("pile", coin_pile_box(cx - 270, base, 10, 15))
            sc.fixed("arrow", arrow_box((cx - 195, base - 150), (cx + 70, base - 150)))
            sc.fixed("bld", building_box(cx + 260, base, 145, 410))
            sc.fixed("q", glyph_box(cx, cy - 150, 230, 230))
            sc.text("THE QUESTION", cx, cy - 460, "THE QUESTION", 24, PRIO_KICKER)
            sc.text("ONE QUESTION", cx, cy - 360, "ONE QUESTION", 40)
            sc.text("HOW DO I TURN INCOME INTO ASSETS?", cx, cy + 400,
                    "HOW DO I TURN INCOME INTO ASSETS?", 30, PRIO_FOOT)
    elif cid == 2:
        if idx == 0:
            sc.fixed("gate", gate_box_r(cx, cy + 20, 230, 130), PROP, "trap")
            sc.fixed("pile", coin_pile_box(cx - 80, cy + 20 - 130, 6, 13), PROP, "trap")
            sc.fixed("arrow", arrow_box((cx - 220, 800), (cx + 20, 800)), PROP, "trap")
            sc.fixed("fall", glyph_box(cx, cy + 190, 150, 170), ACCENT, "trap")
            sc.text("MOST PEOPLE FALL IN", cx, cy - 460, "MOST PEOPLE FALL IN", 24, PRIO_KICKER)
            sc.text("THE TRAP", cx, cy - 360, "THE TRAP", 46)
            sc.text("MONEY IN...  MONEY OUT", cx, cy + 430,
                    "MONEY IN...  MONEY OUT", 26, PRIO_FOOT)
        elif idx == 1:
            sc.fixed("floor", ground_box(cx, base + 108, 410), GROUND)
            sc.fixed("pileL", coin_pile_box(cx - 240, base, 10, 15), PROP, "L")
            sc.fixed("pileR", coin_pile_box(cx + 240, base, 10, 15), PROP, "R")
            sc.fixed("arrow", arrow_box((cx - 130, base - 150), (cx + 130, base - 150)))
            sc.text("THE TRAP", cx, cy - 460, "THE TRAP", 24, PRIO_KICKER)
            sc.text("MAKE", cx - 240, base + 130, "MAKE", 30, PRIO_PIECE, "L")
            sc.text("SPEND", cx + 240, base + 130, "SPEND", 30, PRIO_PIECE, "R")
            sc.text("MORE IN...  MORE OUT", cx, cy - 360, "MORE IN...  MORE OUT", 42)
        else:
            sc.fixed("tag", tag_box(cx - 230, cy + 10, 100, 52), PROP, "tag")
            sc.fixed("plus", glyph_box(cx - 230, cy + 10, 80, 80), ACCENT, "tag")
            sc.fixed("arrow", arrow_box((cx - 110, cy + 10), (cx + 30, cy + 10)), PROP, "tag")
            sc.fixed("bl", loop_box(cx + 230, cy + 10, 145), PROP, "bl")
            sc.fixed("bl2", loop_box(cx + 230, cy + 10, 105), PROP, "bl")
            sc.text("THE TRAP", cx, cy - 460, "THE TRAP", 24, PRIO_KICKER)
            sc.text("RAISE", cx - 230, cy + 115, "RAISE", 28, PRIO_PIECE, "tag")
            sc.text("LIFESTYLE", cx + 230, cy + 210, "LIFESTYLE", 26, PRIO_PIECE, "bl")
            sc.text("RAISE -> LIFESTYLE", cx, cy - 360, "RAISE -> LIFESTYLE", 42)
    elif cid == 3:
        if idx == 0:
            sc.fixed("floor", ground_box(cx, base + 108, 410), GROUND)
            sc.fixed("pile", coin_pile_box(cx, base, 10, 16), PROP, "tag")
            sc.fixed("tag", tag_box(cx, base - 320, 150, 52), PROP, "tag")
            sc.fixed("s10", glyph_box(cx, base - 320, 160, 50), ACCENT, "tag")
            sc.text("THE TREADMILL", cx, cy - 460, "THE TREADMILL", 24, PRIO_KICKER)
            sc.text("MAKE $10K A MONTH", cx, cy - 360, "MAKE $10K A MONTH", 44)
            sc.text("EVERY SINGLE MONTH", cx, cy + 430, "EVERY SINGLE MONTH", 26, PRIO_FOOT)
        elif idx == 1:
            sc.fixed("loop", loop_box(cx, cy + 30, 165), PROP, "tm")
            sc.fixed("tag", tag_box(cx, cy - 150, 130, 48), PROP, "tm")
            sc.fixed("s10", glyph_box(cx, cy - 150, 160, 50), ACCENT, "tm")
            sc.text("THE TREADMILL", cx, cy - 460, "THE TREADMILL", 24, PRIO_KICKER)
            sc.text("STILL NEED IT NEXT MONTH", cx, cy - 360, "STILL NEED IT NEXT MONTH", 40)
            sc.text("REQUIRED AGAIN", cx, cy + 430, "REQUIRED AGAIN", 28, PRIO_FOOT)
        else:
            sc.fixed("struck", glyph_box(cx, cy - 215, 170, 80), PROP, "struck")
            sc.fixed("xm", glyph_box(cx, cy - 205, 60, 60), ACCENT, "struck")
            sc.fixed("loop", loop_box(cx, cy + 110, 270), PROP, "tm2")
            sc.text("THE TREADMILL", cx, cy - 460, "THE TREADMILL", 24, PRIO_KICKER)
            sc.text("A BIGGER TREADMILL", cx, cy - 360, "A BIGGER TREADMILL", 46)
            sc.text("THAT'S NOT WEALTH", cx, cy + 430, "THAT'S NOT WEALTH", 28, PRIO_FOOT)
    elif cid == 4:
        if idx == 0:
            sc.fixed("floor", ground_box(cx, base + 108, 410), GROUND)
            sc.fixed("pileL", coin_pile_box(cx - 250, base, 10, 15), PROP, "L")
            sc.fixed("arrow", arrow_box((cx - 190, base - 160), (cx + 90, base - 160)))
            sc.fixed("bld", building_box(cx + 250, base, 160, 430), PROP, "bld")
            sc.fixed("orb", glyph_box(cx + 250, base - 70, 280, 140), ACCENT, "bld")
            sc.fixed("retA", arrow_box((cx + 180, base - 40), (cx - 80, base - 40)), ACCENT, "bld")
            sc.text("THE GAME CHANGE", cx, cy - 460, "THE GAME CHANGE", 24, PRIO_KICKER)
            sc.text("YOU EARN", cx - 250, base + 130, "YOU EARN", 28, PRIO_PIECE, "L")
            sc.text("IT PAYS YOU", cx + 250, base + 130, "IT PAYS YOU", 28, PRIO_PIECE, "bld")
            sc.text("MONEY THAT MAKES MONEY", cx, cy - 360, "MONEY THAT MAKES MONEY", 42)
        elif idx == 1:
            sc.fixed("heart", heart_box(cx, cy - 40, 1.05), PROP, "heart")
            sc.fixed("hse", house_box(cx, cy - 40, 64), ACCENT, "heart")
            sc.text("THE GAME CHANGE", cx, cy - 460, "THE GAME CHANGE", 24, PRIO_KICKER)
            sc.text("I LOVE REAL ESTATE", cx, cy - 360, "I LOVE REAL ESTATE", 44)
            sc.text("ASSETS THAT SHELTER AND PAY", cx, cy + 430,
                    "ASSETS THAT SHELTER AND PAY", 26, PRIO_FOOT)
        else:
            sc.fixed("loop", loop_box(cx, cy + 20, 210), PROP, "m2")
            sc.fixed("hse", house_box(cx, cy + 60, 100), PROP, "m2")
            sc.fixed("tag", tag_box(cx, cy - 140, 130, 44), PROP, "m2")
            sc.fixed("one", glyph_box(cx, cy - 140, 90, 50), ACCENT, "m2")
            sc.text("THE GAME CHANGE", cx, cy - 460, "THE GAME CHANGE", 24, PRIO_KICKER)
            sc.text("MORE THAN BUYING", cx, cy - 360, "MORE THAN BUYING", 42)
            sc.text("FINANCING. RENT. APPRECIATION. TIME.", cx, cy + 430,
                    "FINANCING. RENT. APPRECIATION. TIME.", 26, PRIO_FOOT)
    elif cid == 5:
        if idx == 0:
            sc.fixed("floor", ground_box(cx, cy + 260, 410), GROUND)
            sc.fixed("hse", house_box(cx, cy - 20, 96), PROP, "h")
            sc.fixed("pileL", coin_pile_box(cx - 270, cy + 200, 4, 13), PROP, "L")
            sc.fixed("pileR", coin_pile_box(cx + 270, cy + 200, 4, 13), PROP, "R")
            sc.fixed("aL", arrow_box((cx - 200, cy + 160), (cx - 60, cy + 10)), ACCENT, "h")
            sc.fixed("aR", arrow_box((cx + 200, cy + 160), (cx + 60, cy + 10)), ACCENT, "h")
            sc.text("REAL ESTATE POWERED", cx, cy - 460, "REAL ESTATE POWERED", 24, PRIO_KICKER)
            sc.text("FINANCING", cx - 270, cy + 250, "FINANCING", 24, PRIO_PIECE, "L")
            sc.text("RENT", cx + 270, cy + 250, "RENT", 24, PRIO_PIECE, "R")
            sc.text("OTHER PEOPLE'S MONEY", cx, cy - 360, "OTHER PEOPLE'S MONEY", 38)
        elif idx == 1:
            sc.fixed("floor", ground_box(cx, cy + 240, 410), GROUND)
            sc.fixed("up", glyph_box(cx - 210, cy, 180, 150), PROP, "up")
            sc.fixed("clk", clock_box(cx + 210, cy, 58), PROP, "clk")
            sc.text("REAL ESTATE POWERED", cx, cy - 460, "REAL ESTATE POWERED", 24, PRIO_KICKER)
            sc.text("APPRECIATION", cx - 210, cy + 160, "APPRECIATION", 28, PRIO_PIECE, "up")
            sc.text("TIME", cx + 210, cy + 160, "TIME", 26, PRIO_PIECE, "clk")
            sc.text("POWERED BY BOTH", cx, cy - 360, "POWERED BY BOTH", 38)
        else:
            sc.fixed("floor", ground_box(cx, cy + 240, 410), GROUND)
            sc.fixed("hse", house_box(cx - 300, cy + 40, 52), PROP, "one")
            sc.fixed("one", glyph_box(cx - 300, cy - 60, 80, 80), ACCENT, "one")
            sc.fixed("arrow", arrow_box((cx - 220, cy - 10), (cx - 90, cy - 10)), PROP, "sky")
            sc.fixed("sky", skyline_box(cx + 130, cy + 150, 560, 130), PROP, "sky")
            sc.text("REAL ESTATE POWERED", cx, cy - 460, "REAL ESTATE POWERED", 24, PRIO_KICKER)
            sc.text("ONE", cx - 300, cy + 140, "ONE", 26, PRIO_PIECE, "one")
            sc.text("ONE INVESTMENT -> ASSET BASE", cx, cy - 360,
                    "ONE INVESTMENT -> ASSET BASE", 40)
    else:
        if idx == 0:
            sc.fixed("loop", loop_box(cx, cy + 90, 120), PROP, "loop")
            sc.fixed("xm", glyph_box(cx, cy + 90, 120, 120), ACCENT, "loop")
            sc.text("WEALTH STARTS", cx, cy - 460, "WEALTH STARTS", 24, PRIO_KICKER)
            sc.text("10 YEARS", cx, cy - 150, "10 YEARS", 62, PRIO_STATEMENT + 1)
            sc.text("DON'T SPEND 10 YEARS EARNING", cx, cy - 360,
                    "DON'T SPEND 10 YEARS EARNING", 38)
            sc.text("WORKING HARDER IS NOT THE ANSWER", cx, cy + 430,
                    "WORKING HARDER IS NOT THE ANSWER", 26, PRIO_FOOT)
        elif idx == 1:
            sc.fixed("floor", ground_box(cx, base + 108, 410), GROUND)
            sc.fixed("pileL", coin_pile_box(cx - 250, base, 10, 15), PROP, "L")
            sc.fixed("arrow", arrow_box((cx - 180, base - 150), (cx + 40, base - 150)))
            sc.fixed("a6", building_box(cx + 230, base, 150, 380), PROP, "a6")
            sc.fixed("hse", house_box(cx + 230, base, 30), ACCENT, "a6")
            sc.fixed("badge", glyph_box(cx + 230, base - 150, 170, 44), ACCENT, "a6")
            sc.fixed("check", glyph_box(cx + 168, base - 150, 30, 30), ACCENT, "a6")
            sc.text("WEALTH STARTS", cx, cy - 460, "WEALTH STARTS", 24, PRIO_KICKER)
            sc.text("EARN", cx - 250, base + 130, "EARN", 30, PRIO_PIECE, "L")
            sc.text("TURN WHAT YOU EARN...", cx, cy - 360, "TURN WHAT YOU EARN...", 40)
            sc.text("...INTO WHAT YOU OWN", cx + 230, cy + 330,
                    "...INTO WHAT YOU OWN", 30, PRIO_FOOT, "a6")
        else:
            sc.fixed("ring", loop_box(cx, cy - 20, 285), PROP, "m6")
            sc.fixed("a6b", building_box(cx, cy + 100, 170, 350), PROP, "m6")
            sc.fixed("spark", glyph_box(cx, cy + 330, 320, 110), ACCENT, "m6")
            sc.text("THAT'S WHERE WEALTH STARTS", cx, cy - 470,
                    "THAT'S WHERE WEALTH STARTS", 24, PRIO_KICKER)
            sc.text("WEALTH", cx, cy - 380, "WEALTH", 56)
            sc.text("TURN WHAT YOU EARN INTO WHAT YOU OWN", cx, cy + 430,
                    "TURN WHAT YOU EARN INTO WHAT YOU OWN", 30, PRIO_FOOT)


VIDEO_TITLE = "stickman_real_estate"

CLIPS = [
    {"id": 1, "name": "The Question",
     "narration": "If I had to start building wealth from zero today, I wouldn't start by "
                  "looking for stocks, crypto, or the next business idea. I'd start with one "
                  "question. How do I turn my income into assets?"},
    {"id": 2, "name": "The Trap",
     "narration": "Because here's the trap most people fall into. They make more money. Then "
                  "they spend more money. They get a raise. They upgrade their lifestyle."},
    {"id": 3, "name": "The Treadmill",
     "narration": "They make ten thousand dollars a month. But they still need ten thousand "
                  "dollars next month. That's not wealth. That's a bigger treadmill."},
    {"id": 4, "name": "The Game Change",
     "narration": "The game changes when you start taking the money you earn and buying "
                  "things that can produce more money. And that's why I love real estate. "
                  "You don't just buy a property."},
    {"id": 5, "name": "Real Estate Powered",
     "narration": "You can use financing, rental income, appreciation, and time to turn one "
                  "investment into a growing asset base."},
    {"id": 6, "name": "Wealth Starts",
     "narration": "So don't spend the next ten years just trying to earn more. Learn how to "
                  "turn what you earn into what you own. That's where wealth starts."},
]

NARR_BEATS = {
    1: ["If I had to start building wealth from zero today",
        "I wouldn't start by looking for stocks crypto or the next business idea",
        "I'd start with one question How do I turn my income into assets"],
    2: ["Because here's the trap most people fall into",
        "They make more money Then they spend more money",
        "They get a raise They upgrade their lifestyle"],
    3: ["They make ten thousand dollars a month",
        "But they still need ten thousand dollars next month",
        "That's not wealth That's a bigger treadmill"],
    4: ["The game changes when you start taking the money you earn and buying things that can produce more money",
        "And that's why I love real estate",
        "You don't just buy a property"],
    5: ["You can use financing rental income",
        "appreciation and time",
        "to turn one investment into a growing asset base"],
    6: ["So don't spend the next ten years just trying to earn more",
        "Learn how to turn what you earn into what you own",
        "That's where wealth starts"],
}

PAD_BEFORE = {1: 0.45, 4: 0.5, 6: 0.45}
PAD_AFTER = 0.35


def apply_to(gm):
    """Point engine module globals at this story (used before render/compile/QA)."""
    gm.VIDEO_TITLE = VIDEO_TITLE
    gm.CLIPS = CLIPS
    gm.NARR_BEATS = NARR_BEATS
    gm.PAD_BEFORE = PAD_BEFORE
    gm._TIMING_CACHE.clear()
    gm._WORD_P_CACHE.clear()
    gm.sfx_events = sfx_events


# ============================================================ design system

def clamp01(t):
    return g.clamp01(t)


def dim_col(color, a):
    return tuple(min(255, int(v * a)) for v in color)


def halo(d, cx, cy, r, color, alpha=0.16):
    """Ambient background glow behind the scene subject. Always drawn FIRST."""
    g.glow_circle(d, cx, cy, r, color, layers=2, alpha=alpha)


def floorline(d, cx, cy, span=780, color=(70, 70, 78)):
    d.line([cx - span, cy, cx + span, cy], fill=color, width=6)


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


def card(d, x, y, w, h, color, radius=20, a=1.0):
    c = dim_col(color, a)
    d.rounded_rectangle([x - w / 2, y - h / 2, x + w / 2, y + h / 2],
                        radius=radius, outline=c, width=4)


# ============================================================ story glyphs

def stock_line(d, x, y, w=150, h=110, color=g.GOLD, t=0.0, a=1.0):
    pts = []
    for i in range(5):
        xx = x - w // 2 + i * w // 5
        yy = y + h // 2 - [0.12, 0.5, 0.22, 0.68, 0.3][i] * h + math.sin(t + i * 1.1) * 7
        pts.append((xx, yy))
    d.line(pts, fill=dim_col(color, a), width=6, joint="curve")


def crypto_coin(d, x, y, r=36, color=g.GOLD, a=1.0):
    c = dim_col(color, a)
    d.ellipse([x - r, y - r, x + r, y + r], outline=c, width=5)
    d.ellipse([x - r * 0.6, y - r * 0.6, x + r * 0.6, y + r * 0.6], outline=c, width=3)
    d.line([x - 8, y - r + 10, x - 8, y + r - 10], fill=c, width=6)
    d.line([x + 11, y - r + 17, x - 7, y - 3], fill=c, width=6)
    d.line([x + 11, y + r - 17, x - 7, y + 3], fill=c, width=6)


def bulb(d, x, y, s=36, color=g.GOLD, a=1.0):
    c = dim_col(color, a)
    d.ellipse([x - s, y - s * 1.15, x + s, y + s * 0.18], outline=c, width=5)
    d.rectangle([x - s * 0.38, y + s * 0.2, x + s * 0.38, y + s * 0.62], outline=c, width=5)
    d.line([x, y - s + 8, x, y + 2], fill=c, width=2)
    d.line([x - s * 0.45, y - s * 0.5, x, y + 2, x + s * 0.45, y - s * 0.5], fill=c, width=4)


def heart(d, x, y, s=1.0, color=g.RED, a=1.0):
    r = 34 * s
    c = dim_col(color, a)
    d.ellipse([x - 2 * r, y - 2 * r, x, y], outline=c, width=5)
    d.ellipse([x, y - 2 * r, x + 2 * r, y], outline=c, width=5)
    d.line([x - 2 * r, y - r * 0.25, x, y + r * 1.9], fill=c, width=5)
    d.line([x + 2 * r, y - r * 0.25, x, y + r * 1.9], fill=c, width=5)


def clock(d, x, y, s=46, t=0.0, color=g.GRAY, a=1.0):
    c = dim_col(color, a)
    d.ellipse([x - s, y - s, x + s, y + s], outline=c, width=5)
    d.line([x, y, x + math.cos(t * 2.2) * s * 0.7, y + math.sin(t * 2.2) * s * 0.7], fill=c, width=4)
    d.line([x, y, x + math.cos(t * 0.4) * s * 0.5, y + math.sin(t * 0.4) * s * 0.5], fill=c, width=4)
    d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=c)


def track_loop(d, cx, cy, r, p, color, width=8, n=10):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=width)
    for i in range(n):
        aa = i * math.tau / n
        x1 = cx + math.cos(aa) * r
        y1 = cy + math.sin(aa) * r
        x2 = cx + math.cos(aa + 0.24) * r
        y2 = cy + math.sin(aa + 0.24) * r
        d.line([x1, y1, x2, y2], fill=color, width=5)
    coin_x = cx + math.cos(p * math.tau * 1.6) * r
    coin_y = cy + math.sin(p * math.tau * 1.6) * r
    g.coin(d, coin_x, coin_y, r=17, color=g.GOLD, rot=p * 6)


def gate_box(d, cx, cy, w, h, color, t, a=1.0):
    c = dim_col(color, a)
    d.rectangle([cx - w, cy - h, cx + w, cy + h], outline=c, width=7)
    for k in range(6):
        xx = cx - w + 14 + k * ((2 * w - 28) / 6)
        d.line([xx + math.sin(t * 3 + k) * 3, cy - h, xx, cy - h + 16], fill=c, width=5)


def skyline_buildings(d, cx, cy, w, h, count, p, color=g.GOLD):
    """House row + rising growth curve beneath; stamps in one by one."""
    base_y = cy + 30
    span_px = w - 120
    for i in range(count):
        snap = clamp01((p - (i * 0.13)) / 0.15)
        if snap <= 0.02:
            continue
        xx = cx - w // 2 + 40 + i * (span_px / (count - 1 if count > 1 else 1))
        hh = max(34, (h * (0.5 + 0.5 * i / (count - 1)) + 60) * snap)
        g.gold_building(d, int(xx), base_y, 76, int(hh), 1.0)
        g.house(d, int(xx), base_y, size=16, color=g.GOLD, lw=3)
    pts = [(cx - w // 2, base_y + 14)]
    for i in range(5):
        xx = cx - w // 2 + i * (w / 4)
        pts.append((xx, base_y + 14 - (30 + 10 * i) * p))
    pts.append((cx + w // 2, base_y + 14))
    d.line(pts, fill=dim_col(g.GOLD, 0.85), width=5, joint="curve")


def badge(d, x, y, text, color, px=24, w=170, h=40):
    card(d, x, y, w, h, color, radius=12)
    g.big_text(d, x, y, text, color=color, px=px)


# ============================================================ scene: story clips

REG = {}


def draw1(d, t_abs):
    global _CID, _IDX; _CID = 1
    idx, p = g.local_beat(CLIPS[0], t_abs)
    global _IDX; _IDX = idx
    cx, cy = g.W // 2, g.H // 2 + 90
    base = cy + 190
    c = CLIPS[0]

    if idx == 0:
        # from zero -> coins -> building on one shared ground
        halo(d, cx + 280, base, 170, g.GOLD, 0.2)
        floorline(d, cx, base + 108, span=820)
        g.glow_circle(d, cx - 280, base, 90, g.GRAY, layers=2, alpha=0.14)
        g._coin_pile(d, cx - 280, base, 3, g.GRAY, r=15)
        g.arrow(d, cx - 205, base - 150, cx + 90, base - 150, color=g.GOLD, lw=7)
        grow = g.spring(p, k=10)
        g.gold_building(d, cx + 300, base, 160, int(150 + grow * 300), 1.0)
        for k in range(4):
            g.coin(d, cx + 300 + math.cos(t_abs * 2.4 + k * 1.6) * 96,
                   base - 60 + math.sin(t_abs * 2.4 + k * 1.6) * 40,
                   r=11, color=g.GOLD, rot=t_abs + k)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 0, 0.2), "BUILD FROM ZERO", 44)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 0, 0.12), "THE QUESTION", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 0, 0.35),
                   "WHAT YOU EARN  ->  WHAT YOU BUILD", 26, g.GRAY)

    elif idx == 1:
        # three card icons, each stamped out as spoken
        halo(d, cx, cy - 10, 320, g.RED, 0.10)
        icons = [(cx - 215, "STOCKS", stock_line, None),
                 (cx, "CRYPTO", crypto_coin, None),
                 (cx + 215, "IDEAS", bulb, None)]
        for i, (xx, lab, fn, _) in enumerate(icons):
            ap = max(0.0, clamp01((p - (0.08 + i * 0.22)) / 0.15))
            if ap <= 0.02:
                continue
            card(d, xx, cy, 210, 240, g.DIM, radius=24, a=ap)
            if lab == "STOCKS":
                stock_line(d, xx, cy - 15, w=150, h=120, t=t_abs, a=ap)
            elif lab == "CRYPTO":
                crypto_coin(d, xx, cy - 10, r=36, a=ap)
            else:
                bulb(d, xx, cy - 10, s=36, a=ap)
            pp = scene(1, 1).pos(lab)
            lx, ly, lpx = (pp if pp else (xx, cy + 125, 26))
            g.big_text(d, lx, ly, lab, color=dim_col(g.GRAY, ap), px=lpx)
            xs = g.spring(clamp01((p - (0.08 + i * 0.22) - 0.18) / 0.16), k=12)
            if xs > 0.05:
                g.xmark(d, xx, cy - 10, size=int(110 * xs), color=g.RED, lw=10)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 1, 0.12), "DON'T START THERE", 44)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 1, 0.05), "THE QUESTION", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 1, 0.55),
                   "STOCKS, CRYPTO, OR THE NEXT BUSINESS IDEA", 26, g.GRAY)

    else:
        # giant question mark + the one flow that matters
        halo(d, cx, cy - 150, 210, g.GOLD, 0.18)
        q = g.elastic(clamp01((p - g.beat_word_p(c, 2, "question")) / 0.2))
        g.big_text(d, cx, cy - 150, "?", px=int(170 + 60 * q), color=g.GOLD)
        floorline(d, cx, base + 108, span=820)
        g._coin_pile(d, cx - 270, base, int(g.spring(p, k=10) * 10), g.GOLD, r=15)
        g.arrow(d, cx - 195, base - 150, cx + 70, base - 150, color=g.GOLD, lw=6)
        g.gold_building(d, cx + 260, base, 145, int(160 + g.spring(p, k=9) * 250), 1.0)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 2, 0.15), "ONE QUESTION", 40)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 2, 0.05), "THE QUESTION", 24, g.GRAY)
        pop_text(d, cx, cy + 400, t_abs, g.beat_word_t(c, 2, "assets"),
                   "HOW DO I TURN INCOME INTO ASSETS?", g.GOLD, 30)


def draw2(d, t_abs):
    global _CID, _IDX; _CID = 2
    idx, p = g.local_beat(CLIPS[1], t_abs)
    global _IDX; _IDX = idx
    cx, cy = g.W // 2, g.H // 2 + 90
    base = cy + 190
    c = CLIPS[1]

    if idx == 0:
        # the trap: income pours in the top, money leaks out the bottom
        halo(d, cx, cy + 10, 280, g.RED, 0.13)
        floorline(d, cx, base + 108, span=760)
        gate_box(d, cx, cy + 20, 230, 130, g.RED, t_abs)
        hb = cy + 20 - 130
        g._coin_pile(d, cx - 80, hb, min(6, int(p * 6)), g.GOLD, r=13, rot=t_abs * 3)
        g.arrow(d, cx - 220, hb - 140, cx + 20, hb - 140, color=g.GOLD, lw=6)
        for k in range(7):
            fall = clamp01((t_abs * 0.7 + k * 0.16) % 1.0)
            g.coin(d, cx - 60 + k * 22, cy + 20 + 90 + fall * 170, r=12,
                   color=dim_col(g.RED, 0.55 + 0.45 * abs(math.sin(p * 8 + k))), rot=t_abs + k)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 0, 0.12), "THE TRAP", 46, g.RED)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 0, 0.05),
                   "MOST PEOPLE FALL IN", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 0, 0.25),
                   "MONEY IN...  MONEY OUT", 26, g.GRAY)

    elif idx == 1:
        # mirrored stacks: make more vs spend more, one ground line
        halo(d, cx - 240, base - 40, 130, g.GOLD, 0.16)
        halo(d, cx + 240, base - 40, 130, g.RED, 0.16)
        floorline(d, cx, base + 108, span=820)
        g._coin_pile(d, cx - 240, base, int(g.spring(p, k=10) * 10), g.GOLD, r=15)
        g._coin_pile(d, cx + 240, base, int(g.spring(p, k=9.5) * 10), g.RED, r=15)
        g.arrow(d, cx - 130, base - 150, cx + 130, base - 150, color=g.GRAY, lw=6)
        slide_fade(d, cx - 240, base + 130, t_abs, g.beat_abs(c, 1, 0.12), "MAKE", 30, g.GOLD)
        slide_fade(d, cx + 240, base + 130, t_abs, g.beat_abs(c, 1, 0.55), "SPEND", 30, g.RED)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 1, 0.7), "MORE IN...  MORE OUT", 42)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 1, 0.05), "THE TRAP", 24, g.GRAY)

    else:
        # raise card gets swallowed by the lifestyle balloon
        halo(d, cx + 230, cy + 20, 180, g.RED, 0.15)
        floorline(d, cx, base + 108, span=820)
        g.price_tag(d, cx - 230, cy + 10, w=100, h=52, color=g.GOLD, lw=5)
        g.big_text(d, cx - 230, cy + 10, "+$", color=g.GOLD, px=42)
        g.arrow(d, cx - 110, cy + 10, cx + 30, cy + 10, color=g.GOLD, lw=6)
        lr = 60 + g.spring(p, k=9) * 85
        d.ellipse([cx + 230 - lr, cy + 10 - lr, cx + 230 + lr, cy + 10 + lr],
                  outline=g.RED, width=10)
        d.ellipse([cx + 230 - lr * 0.72, cy + 10 + lr * 0.4, cx + 230 + lr * 0.72,
                   cy + 10 + lr * 1.05], outline=g.RED, width=7)
        slide_fade(d, cx - 230, cy + 115, t_abs, g.beat_abs(c, 2, 0.12), "RAISE", 28, g.GOLD)
        slide_fade(d, cx + 230, cy + 210, t_abs, g.beat_abs(c, 2, 0.4), "LIFESTYLE", 26, g.RED)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 2, 0.55), "RAISE -> LIFESTYLE", 42)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 2, 0.05),
                   "THE TRAP", 24, g.GRAY)


def draw3(d, t_abs):
    global _CID, _IDX; _CID = 3
    idx, p = g.local_beat(CLIPS[2], t_abs)
    global _IDX; _IDX = idx
    cx, cy = g.W // 2, g.H // 2 + 90
    base = cy + 190
    c = CLIPS[2]

    if idx == 0:
        halo(d, cx, base, 170, g.GOLD, 0.2)
        floorline(d, cx, base + 108, span=820)
        g._coin_pile(d, cx, base, int(g.spring(p, k=10) * 10), g.GOLD, r=16)
        g.price_tag(d, cx, base - 320, w=150, h=52, color=g.GOLD, lw=5)
        g.big_text(d, cx, base - 320, "$10K", color=g.GOLD, px=38)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 0, 0.12), "MAKE $10K A MONTH", 44)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 0, 0.05), "THE TREADMILL", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 0, 0.3),
                   "EVERY SINGLE MONTH", 26, g.GRAY)

    elif idx == 1:
        halo(d, cx, cy + 10, 200, g.RED, 0.13)
        track_loop(d, cx, cy + 30, 165, p, g.RED, width=9, n=11)
        g.price_tag(d, cx, cy - 150, w=130, h=48, color=g.RED, lw=5)
        g.big_text(d, cx, cy - 150, "$10K", color=g.RED, px=34)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 1, 0.12),
                   "STILL NEED IT NEXT MONTH", 40)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 1, 0.05),
                   "THE TREADMILL", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 1, 0.5),
                   "REQUIRED AGAIN", 28, g.RED)

    else:
        # struck "wealth?" -> the loop only gets bigger
        halo(d, cx, cy - 10, 300, g.RED, 0.10)
        G = g.elastic(clamp01((p - 0.05) / 0.15))
        g.big_text(d, cx, cy - 225, "WEALTH?", px=30, color=g.DIM)
        if G > 0.2:
            g.xmark(d, cx, cy - 210, size=int(26 * G), color=g.RED, lw=6)
        grow = g.spring(clamp01((p - 0.2) / 0.6), k=9)
        track_loop(d, cx, cy + 110, max(50, 60 + grow * 210), clamp01((p - 0.2) / 0.6),
                   g.RED, width=11, n=12)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 2, 0.15), "A BIGGER TREADMILL", 46, g.RED)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 2, 0.05), "THE TREADMILL", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 2, 0.4),
                   "THAT'S NOT WEALTH", 28, g.GRAY)


def draw4(d, t_abs):
    global _CID, _IDX; _CID = 4
    idx, p = g.local_beat(CLIPS[3], t_abs)
    global _IDX; _IDX = idx
    cx, cy = g.W // 2, g.H // 2 + 90
    base = cy + 190
    c = CLIPS[3]

    if idx == 0:
        # earning -> machine that makes money (closed loop drawn readably)
        halo(d, cx + 250, base, 170, g.GOLD, 0.2)
        floorline(d, cx, base + 108, span=820)
        g._coin_pile(d, cx - 250, base, int(g.spring(p, k=10) * 10), g.GOLD, r=15)
        g.arrow(d, cx - 190, base - 160, cx + 90, base - 160, color=g.GOLD, lw=8)
        g.gold_building(d, cx + 250, base, 160, int(170 + g.spring(p, k=9) * 260), 1.0)
        for k in range(7):
            ang = t_abs * 3 + k * math.tau / 7
            g.coin(d, cx + 250 + math.cos(ang) * 130, base - 70 + math.sin(ang) * 65,
                   r=11, color=g.GOLD, rot=t_abs + k)
        g.arrow(d, cx + 180, base - 40, cx - 80, base - 40, color=g.DIM, lw=5)
        slide_fade(d, cx - 250, base + 130, t_abs, g.beat_abs(c, 0, 0.08), "YOU EARN", 28, g.GOLD)
        slide_fade(d, cx + 250, base + 130, t_abs, g.beat_abs(c, 0, 0.45),
                   "IT PAYS YOU", 28, g.GOLD)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 0, 0.55),
                   "MONEY THAT MAKES MONEY", 42)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 0, 0.05),
                   "THE GAME CHANGE", 24, g.GRAY)

    elif idx == 1:
        # heart-shaped frame around a house
        halo(d, cx, cy - 20, 210, g.RED, 0.14)
        hg = g.elastic(clamp01((p - 0.2) / 0.25))
        heart(d, cx, cy - 40, s=0.8 + 0.25 * hg, color=g.RED)
        g.house(d, cx, cy - 40, size=64, color=g.WHITE, lw=5)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 1, 0.2), "I LOVE REAL ESTATE", 44)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 1, 0.05),
                   "THE GAME CHANGE", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 1, 0.5),
                   "ASSETS THAT SHELTER AND PAY", 26, g.GRAY)

    else:
        # one property, looped (financing) -> it's a machine
        halo(d, cx, cy + 20, 200, g.GOLD, 0.16)
        hs = g.elastic(p)
        g.house(d, cx, cy + 60, size=72 + 28 * hs, color=g.GOLD, lw=5)
        track_loop(d, cx, cy + 20, 210, p, g.DIM, width=6, n=9)
        g.price_tag(d, cx, cy - 140, w=130, h=44, color=g.GOLD, lw=4)
        g.big_text(d, cx, cy - 140, "1", color=g.GOLD, px=32)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 2, 0.2), "MORE THAN BUYING", 42)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 2, 0.05),
                   "THE GAME CHANGE", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 2, 0.45),
                   "FINANCING. RENT. APPRECIATION. TIME.", 26, g.GRAY)


def draw5(d, t_abs):
    global _CID, _IDX; _CID = 5
    idx, p = g.local_beat(CLIPS[4], t_abs)
    global _IDX; _IDX = idx
    cx, cy = g.W // 2, g.H // 2 + 90
    base = cy + 190
    c = CLIPS[4]

    if idx == 0:
        # house fed by two feeds: financing (lever) + rental income
        halo(d, cx, cy + 40, 200, g.GOLD, 0.16)
        floorline(d, cx, cy + 260, span=820)
        g.house(d, cx, cy - 20, size=96, color=g.GOLD, lw=5)
        g._coin_pile(d, cx - 270, cy + 200, min(4, int(p * 4)), g.GOLD, r=13)
        g._coin_pile(d, cx + 270, cy + 200, min(4, max(0, int(p * 4) - 1)), g.GOLD, r=13)
        g.arrow(d, cx - 200, cy + 160, cx - 60, cy + 10, color=g.GOLD, lw=5)
        g.arrow(d, cx + 200, cy + 160, cx + 60, cy + 10, color=g.GOLD, lw=5)
        slide_fade(d, cx - 270, cy + 250, t_abs, g.beat_abs(c, 0, 0.12), "FINANCING", 24, g.GRAY)
        slide_fade(d, cx + 270, cy + 250, t_abs, g.beat_abs(c, 0, 0.45), "RENT", 24, g.GRAY)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 0, 0.2),
                   "OTHER PEOPLE'S MONEY", 38)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 0, 0.05),
                   "REAL ESTATE POWERED", 24, g.GRAY)

    elif idx == 1:
        # appreciation (up line) and time (clock) side by side
        halo(d, cx - 210, cy - 20, 140, g.GOLD, 0.16)
        halo(d, cx + 210, cy - 20, 140, g.GRAY, 0.12)
        floorline(d, cx, cy + 240, span=820)
        stock_line(d, cx - 210, cy, w=180, h=140, color=g.GOLD, t=t_abs)
        clock(d, cx + 210, cy, s=50, t=t_abs)
        slide_fade(d, cx - 210, cy + 160, t_abs, g.beat_abs(c, 1, 0.1),
                   "APPRECIATION", 28, g.GOLD)
        slide_fade(d, cx + 210, cy + 160, t_abs, g.beat_abs(c, 1, 0.5), "TIME", 26, g.GRAY)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 1, 0.3), "POWERED BY BOTH", 38)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 1, 0.05),
                   "REAL ESTATE POWERED", 24, g.GRAY)

    else:
        # one investment -> growing asset base (house row + growth curve)
        halo(d, cx, cy + 10, 320, g.GOLD, 0.12)
        floorline(d, cx, cy + 240, span=820)
        g.house(d, cx - 300, cy + 40, size=52, color=g.GRAY, lw=4)
        g.big_text(d, cx - 300, cy - 60, "1", color=g.GRAY, px=38)
        g.arrow(d, cx - 220, cy - 10, cx - 90, cy - 10, color=g.GOLD, lw=6)
        skyline_buildings(d, cx + 130, cy + 150, 560, 130, 4,
                          g.spring(clamp01((p - 0.15) / 0.7), k=9))
        slide_fade(d, cx - 300, cy + 140, t_abs, g.beat_abs(c, 2, 0.05), "ONE", 26, g.GRAY)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 2, 0.6),
                   "ONE INVESTMENT -> ASSET BASE", 40)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 2, 0.05),
                   "REAL ESTATE POWERED", 24, g.GRAY)


def draw6(d, t_abs):
    global _CID, _IDX; _CID = 6
    idx, p = g.local_beat(CLIPS[5], t_abs)
    global _IDX; _IDX = idx
    cx, cy = g.W // 2, g.H // 2 + 90
    base = cy + 190
    c = CLIPS[5]

    if idx == 0:
        halo(d, cx, cy - 30, 190, g.RED, 0.12)
        pop_text(d, cx, cy - 150, t_abs, g.beat_abs(c, 0, 0.12), "10 YEARS", g.WHITE, 62)
        track_loop(d, cx, cy + 90, 120, p, g.RED, width=8, n=9)
        gf = g.elastic(clamp01((p - 0.4) / 0.2))
        if gf > 0.05:
            g.xmark(d, cx, cy + 90, size=int(120 * gf), color=g.RED, lw=14)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 0, 0.3),
                   "DON'T SPEND 10 YEARS EARNING", 38)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 0, 0.05),
                   "WEALTH STARTS", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 0, 0.45),
                   "WORKING HARDER IS NOT THE ANSWER", 26, g.RED)

    elif idx == 1:
        # learn to convert: coin -> arrow -> house with OWNED badge
        halo(d, cx + 230, base, 150, g.GOLD, 0.2)
        floorline(d, cx, base + 108, span=820)
        g._coin_pile(d, cx - 250, base, int(g.spring(p, k=10) * 10), g.GOLD, r=15)
        g.arrow(d, cx - 180, base - 150, cx + 40, base - 150, color=g.GOLD, lw=8)
        g.gold_building(d, cx + 230, base, 150, int(180 + g.spring(p, k=9) * 200), 1.0)
        g.house(d, cx + 230, base, size=30, color=g.GOLD, lw=3)
        bd = g.spring(clamp01((p - 0.25) / 0.35), k=11)
        if bd > 0.1:
            badge(d, cx + 230, base - 150, "OWNED", g.BLUE, px=26)
            g.check(d, cx + 230 - 62, base - 150, size=14, color=g.BLUE)
        slide_fade(d, cx - 250, base + 130, t_abs, g.beat_abs(c, 1, 0.08), "EARN", 30, g.GOLD)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 1, 0.45),
                   "TURN WHAT YOU EARN...", 40)
        slide_fade(d, cx + 230, cy + 330, t_abs, g.beat_abs(c, 1, 0.5),
                   "...INTO WHAT YOU OWN", 30, g.GOLD)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 1, 0.05),
                   "WEALTH STARTS", 24, g.GRAY)

    else:
        # finale: the wealth motor — building + orbit + ascedent spark
        r0 = 125 + g.spring(p, k=9) * 160
        halo(d, cx, cy - 20, r0 + 60, g.GOLD, 0.25)
        d.ellipse([cx - r0, cy - 20 - r0, cx + r0, cy - 20 + r0], outline=g.GOLD, width=10)
        g.gold_building(d, cx, cy + 100, 170, int(140 + g.spring(p, k=8) * 210), 1.0)
        for k in range(10):
            ang = k * math.tau / 10 + t_abs * 1.8
            g.coin(d, cx + math.cos(ang) * r0, cy - 20 + math.sin(ang) * r0 * 0.9, r=14,
                   color=g.GOLD, rot=t_abs + k)
        gm = g.spring(clamp01((p - 0.25) / 0.5), k=9)
        for k in range(5):
            xx = cx - 150 + k * 75
            g.coin(d, xx, cy + 300 + (100 - k * 22) * gm, r=12,
                   color=dim_col(g.GOLD, 0.5 + 0.3 * k / 4), rot=t_abs + k)
        slide_fade(d, cx, cy - 380, t_abs, g.beat_abs(c, 2, 0.12), "WEALTH", 56, g.GOLD)
        slide_fade(d, cx, cy - 470, t_abs, g.beat_abs(c, 2, 0.05),
                   "THAT'S WHERE WEALTH STARTS", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 2, 0.5),
                   "TURN WHAT YOU EARN INTO WHAT YOU OWN", 30, g.WHITE)


REG.update({1: draw1, 2: draw2, 3: draw3, 4: draw4, 5: draw5, 6: draw6})


# ============================================================ frame + clip render

def bg_scene(d, t):
    for x in range(0, g.W, 88):
        d.line([x, 0, x, g.H], fill=g.BG_LINE, width=1)
    for y in range(0, g.H, 88):
        d.line([0, y, g.W, y], fill=g.BG_LINE, width=1)


def render_frame(cid, t_abs):
    img = g.Image.new("RGB", (g.RW, g.RH), g.BLACK)
    raw = g.ImageDraw.Draw(img)
    d = g.D2(raw)
    bg_scene(d, t_abs)
    REG[cid](d, t_abs)
    return g.bloom(img.resize((g.W, g.H), g.Image.LANCZOS))


def render_clip(clip):
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


# ============================================================ intro / outro

def create_intro_clip():
    dirpath = g.FRAMES_DIR / "intro"
    if dirpath.exists():
        shutil.rmtree(dirpath)
    dirpath.mkdir(parents=True, exist_ok=True)
    total = 2 * g.FPS
    for f in range(total):
        t = f / g.FPS
        img = g.Image.new("RGB", (g.RW, g.RH), g.BLACK)
        raw = g.ImageDraw.Draw(img)
        d = g.D2(raw)
        bg_scene(d, t)
        cx = g.W // 2
        iy = g.H // 2 - 20
        flash = max(0.0, 1.0 - t * 4.0)
        if flash > 0.05:
            g.glow_circle(d, cx, iy + 40, 520, g.GOLD, alpha=flash * 0.7)
        # coin flies in from the left into the building
        fly = g.ease(clamp01(t / 0.55))
        fx = lerp(cx - 520, cx - 140, fly)
        fy = iy + 30 + math.sin(fly * 5) * 40
        g.coin(d, fx, fy, r=20, color=g.GOLD, rot=t * 4)
        g.arrow(d, cx - 90, iy + 30, cx - 10, iy + 30, color=g.GOLD, lw=6)
        bz = 60 + g.ease(t) * 170
        g.glow_circle(d, cx + 120, iy + 30, 120, g.GOLD, layers=2, alpha=0.25)
        g.gold_building(d, cx + 120, iy + 30, 150, int(bz + 90), 1.0)
        g.gold_building(d, cx + 120, iy + 240, 150, int(40 + g.ease(t) * 60), 0.6)
        g._coin_pile(d, cx + 120, iy + 300, min(6, int(t * 6)), g.GOLD, r=12)
        # title stamp
        ta = g.elastic(clamp01((t - 0.8) / 0.5))
        g.big_text(d, cx, iy + 200, "INCOME -> ASSETS", px=52,
                   color=(min(255, int(255 * ta)), min(255, int(220 * ta)), min(255, int(60 * ta))))
        g.big_text(d, cx, iy + 260, "START WITH WHAT YOU EARN",
                   color=dim_col(g.GRAY, ta), px=24)
        g.bloom(img.resize((g.W, g.H), g.Image.LANCZOS)).save(dirpath / f"frame_{f:04d}.png")


def create_outro_clip():
    dirpath = g.FRAMES_DIR / "outro"
    if dirpath.exists():
        shutil.rmtree(dirpath)
    dirpath.mkdir(parents=True, exist_ok=True)
    total = 2 * g.FPS
    for f in range(total):
        t = f / g.FPS
        img = g.Image.new("RGB", (g.RW, g.RH), g.BLACK)
        raw = g.ImageDraw.Draw(img)
        d = g.D2(raw)
        bg_scene(d, t)
        cx, cy = g.W // 2, g.H // 2 + 40
        r0 = 70 + g.spring(clamp01(t / 0.6), k=9) * 240
        g.glow_circle(d, cx, cy, r0 + 50, g.GOLD, layers=2, alpha=0.4)
        d.ellipse([cx - r0, cy - r0, cx + r0, cy + r0], outline=g.GOLD, width=10)
        g.gold_building(d, cx, cy, 150, int(120 + g.spring(clamp01(t / 0.7), k=8) * 200), 1.0)
        for k in range(10):
            ang = k * math.tau / 10 + t * 2.2
            g.coin(d, cx + math.cos(ang) * r0, cy + math.sin(ang) * r0 * 0.85, r=13,
                   color=g.GOLD, rot=t + k)
        ta = g.elastic(clamp01((t - 0.4) / 0.45))
        fade_out = 1 - g.ease_out(clamp01((t - 1.5) / 0.5))
        ta *= fade_out
        if ta > 0.1:
            g.big_text(d, cx, cy + 170, "TURN WHAT YOU EARN", px=38,
                       color=dim_col(g.WHITE, ta))
            g.big_text(d, cx, cy + 240, "INTO WHAT YOU OWN", px=46,
                       color=dim_col(g.GOLD, ta))
            g.big_text(d, cx, cy - 260, "THAT'S WHERE WEALTH STARTS",
                       color=dim_col(g.GRAY, ta), px=24)
        g.bloom(img.resize((g.W, g.H), g.Image.LANCZOS)).save(dirpath / f"frame_{f:04d}.png")


def lerp(a, b, t):
    return a + (b - a) * t


# ============================================================ sfx

def sfx_events(clip):
    cid = clip["id"]
    beats = g.clip_beats(clip)
    evs = []
    if not beats:
        return evs
    if cid == 1:
        b = beats[0]
        evs += [(b[0], "whoosh", 0.5), (max(0, b[1] - 0.1), "chime", 0.6)]
        b = beats[1]
        for k in range(3):
            span = b[1] - b[0]
            evs.append((b[0] + span * k / 3, "stamp", 0.5))
        b = beats[2]
        evs += [(b[0], "whoosh", 0.5), (max(0, b[1] - 0.2), "ding", 0.6)]
    elif cid == 2:
        evs += [(beats[0][0], "slam", 0.5), (max(0, beats[0][1] - 0.2), "crumble", 0.4)]
        evs += [(beats[1][0], "rise", 0.5), (beats[1][0] + 0.3, "tick", 0.5)]
        evs += [(beats[2][0], "pop", 0.5), (beats[2][0] + 0.35, "whoosh", 0.4)]
    elif cid == 3:
        evs += [(beats[0][0], "rise", 0.5), (max(0, beats[0][1] - 0.2), "chime", 0.5)]
        evs += [(beats[1][0], "whoosh", 0.5), (beats[1][0] + 0.3, "tick", 0.4)]
        evs += [(beats[2][0], "slam", 0.5), (beats[2][0] + 0.4, "rise", 0.5)]
    elif cid == 4:
        evs += [(beats[0][0], "rise", 0.5), (beats[0][1] - 0.2, "shimmer", 0.5)]
        evs += [(beats[1][0], "pop", 0.5), (beats[1][0] + 0.3, "ding", 0.6)]
        evs += [(beats[2][0], "tick", 0.4), (beats[2][1] - 0.2, "chime", 0.5)]
    elif cid == 5:
        evs += [(beats[0][0], "pop", 0.45), (beats[0][1] - 0.15, "clink", 0.5)]
        evs += [(beats[1][0], "tick", 0.45), (beats[1][0] + 0.4, "shimmer", 0.5)]
        for k in range(5):
            span = beats[2][1] - beats[2][0]
            evs.append((beats[2][0] + span * k / 5, "clink", 0.5))
    else:
        evs += [(beats[0][0], "slam", 0.5), (beats[0][0] + 0.4, "crumble", 0.4)]
        evs += [(beats[1][0], "rise", 0.5), (max(0, beats[1][1] - 0.15), "ding", 0.6)]
        evs += [(beats[2][0], "chime", 0.7)]
        for k in range(6):
            evs.append((beats[2][0] + 0.15 + 0.12 * k, "clink", 0.5))
    evs = [(max(0.0, t), n, gl) for t, n, gl in evs]
    return evs


# ============================================================ pipeline

async def main():
    print("=" * 60)
    print("Stickman Video Generator - income into assets (real estate) v3")
    print("=" * 60)
    if "--audit" in sys.argv:
        print("\n[layout] collision audit (18 beats)")
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