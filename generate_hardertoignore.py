"""generate_hardertoignore.py - long-form story: "harder to ignore".

A 3.5-minute male-voice coaching piece about real estate excuses. Same
collision-free layout engine (layout_guard) + same design rhythm as the
assets project:

    kicker    y = cy - 460   (small gray, scene title)
    statement y = cy - 360   (bold white/colored, the line said that beat)
    diagram   y in [cy-240 .. cy+260]
    footnote  y = cy + 430   (small gray/golded, reinforcing line)

11 clips x 3 beats = 33 beats, all planned/audited before rendering.
"""
import asyncio
import json
import math
import shutil
import sys
from pathlib import Path

import generate_video as g

from layout_guard import (Scene, ground_box, coin_pile_box, house_box,
                          building_box, arrow_box, tag_box, card_box,
                          loop_box, gate_box_r, clock_box, glyph_box,
                          heart_box, skyline_box, phone_box, door_box)
from layout_guard import (GROUND, PROP, ACCENT, TEXT,
                          PRIO_PIECE, PRIO_KICKER, PRIO_FOOT, PRIO_STATEMENT)

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
    for cid in range(1, 12):
        for idx in (0, 1, 2):
            out.extend(scene(cid, idx).problems)
    return sorted(set(out))


def layout_report():
    lines = []
    for cid in range(1, 12):
        for idx in (0, 1, 2):
            lines.append(scene(cid, idx).report())
    return "\n".join(lines)


def build_scene(sc, cid, idx):
    cx, cy = g.W // 2, g.H // 2 + 90
    base = cy + 190
    if cid == 1:
        if idx == 0:
            sc.fixed("floor", ground_box(cx, base + 60, 430), GROUND)
            sc.fixed("pile", coin_pile_box(cx - 250, base, 6, 15), PROP)
            sc.fixed("house", house_box(cx + 250, base, 46), PROP)
            sc.fixed("arrow", arrow_box((cx - 180, base - 150), (cx + 110, base - 150)), PROP)
            sc.text("THE REAL BOTTLENECK", cx, cy - 460, "THE REAL BOTTLENECK", 24, PRIO_KICKER)
            sc.text("MONEY ISN'T THE BOTTLENECK", cx, cy - 360,
                    "MONEY ISN'T THE BOTTLENECK", 40)
            sc.text("TO START BUILDING IN REAL ESTATE", cx, cy + 430,
                    "TO START BUILDING IN REAL ESTATE", 24, PRIO_FOOT)
        elif idx == 1:
            sc.fixed("floor", ground_box(cx, cy + 240, 400), GROUND)
            for i, dx in enumerate((-240, 0, 240)):
                sc.fixed(f"tag{i}", tag_box(cx + dx, cy + 30, 92, 32), PROP, "leak")
                sc.fixed(f"arr{i}", arrow_box((cx + dx, cy + 90), (cx + dx, cy + 200)), PROP, "leak")
            sc.text("STOP WASTING WHAT YOU HAVE", cx, cy - 360,
                    "STOP WASTING WHAT YOU HAVE", 38)
            sc.text("THE REAL BOTTLENECK", cx, cy - 460, "THE REAL BOTTLENECK", 24, PRIO_KICKER)
            for i, (dx, lab) in enumerate(((-240, "MONEY"), (0, "TIME"), (240, "OPPORTUNITY"))):
                sc.text(lab, cx + dx, cy + 300, lab, 26, PRIO_PIECE, "leak")
        else:
            for i, dx in enumerate((-230, -77, 77, 230)):
                sc.fixed(f"card{i}", card_box(cx + dx, cy + 10, 250, 130), PROP, "exc")
            sc.text("THE SAME EXCUSES. EVERY TIME.", cx, cy - 360,
                    "THE SAME EXCUSES. EVERY TIME.", 36)
            sc.text("THE REAL BOTTLENECK", cx, cy - 460, "THE REAL BOTTLENECK", 24, PRIO_KICKER)
    elif cid == 2:
        if idx == 0:
            sc.fixed("desk", card_box(cx, cy + 20, 250, 190), PROP, "job")
            sc.accent("clock", clock_box(cx, cy - 20, 62), "job")
            sc.text("EXCUSE 1 OF 4", cx, cy - 120, "EXCUSE 1 OF 4", 22, PRIO_PIECE, "job")
            sc.text("I HAVE A FULL-TIME JOB", cx, cy - 360, "I HAVE A FULL-TIME JOB", 40)
            sc.text("THE EXCUSES", cx, cy - 460, "THE EXCUSES", 24, PRIO_KICKER)
            sc.text("BUT THAT'S NOT THE BLOCKER", cx, cy + 430,
                    "BUT THAT'S NOT THE BLOCKER", 24, PRIO_FOOT)
        elif idx == 1:
            sc.fixed("pouch", card_box(cx, cy + 20, 250, 180), PROP, "job")
            sc.fixed("pile", coin_pile_box(cx - 60, cy + 120, 3, 15), PROP, "job")
            sc.accent("q", glyph_box(cx + 70, cy - 10, 70, 70), "job")
            sc.text("EXCUSE 2 OF 4", cx, cy - 120, "EXCUSE 2 OF 4", 22, PRIO_PIECE, "job")
            sc.text("I DON'T HAVE ENOUGH CAPITAL", cx, cy - 360,
                    "I DON'T HAVE ENOUGH CAPITAL", 36)
            sc.text("THE EXCUSES", cx, cy - 460, "THE EXCUSES", 24, PRIO_KICKER)
        else:
            sc.fixed("book", card_box(cx - 230, cy + 20, 250, 180), PROP, "exc2")
            sc.fixed("lag", card_box(cx + 230, cy + 20, 250, 180), PROP, "exc2")
            sc.text("I DON'T KNOW ENOUGH", cx - 230, cy + 160, "I DON'T KNOW ENOUGH", 24, PRIO_PIECE, "exc2")
            sc.text("SOMEDAY", cx + 230, cy + 160, "SOMEDAY", 30, PRIO_PIECE, "exc2")
            sc.text("I'LL START WHEN LIFE GETS EASIER", cx, cy - 360,
                    "I'LL START WHEN LIFE GETS EASIER", 34)
            sc.text("THE EXCUSES", cx, cy - 460, "THE EXCUSES", 24, PRIO_KICKER)
    elif cid == 3:
        if idx == 0:
            sc.fixed("phone", phone_box(cx - 120, cy + 50, 1.5), PROP)
            sc.accent("clock", clock_box(cx + 210, cy + 50, 66), "ck")
            sc.text("3 HOURS SCROLLING EVERY NIGHT", cx, cy - 360,
                    "3 HOURS SCROLLING EVERY NIGHT", 34)
            sc.text("THE SCROLL TRAP", cx, cy - 460, "THE SCROLL TRAP", 24, PRIO_KICKER)
            sc.text("EVERY SINGLE NIGHT", cx, cy + 430, "EVERY SINGLE NIGHT", 24, PRIO_FOOT)
        elif idx == 1:
            for i, dx in enumerate((-240, 0, 240)):
                sc.fixed(f"tile{i}", card_box(cx + dx, cy + 40, 210, 150), PROP, "tile")
            sc.text("WATCH. SAVE. TALK.", cx, cy - 360, "WATCH. SAVE. TALK.", 40)
            sc.text("THE SCROLL TRAP", cx, cy - 460, "THE SCROLL TRAP", 24, PRIO_KICKER)
            for i, (dx, lab) in enumerate(((-240, "VIDEOS ABOUT WEALTH"),
                                          (0, "POSTS YOU SAVE"),
                                          (240, "FREEDOM TALKS"))):
                sc.text(lab, cx + dx, cy + 150, lab, 22, PRIO_PIECE, "tile")
        else:
            sc.fixed("phone", phone_box(cx - 250, cy + 40, 1.3), PROP)
            sc.fixed("loop", loop_box(cx + 150, cy + 30, 120), PROP, "loop")
            sc.text("SAME MORNING", cx + 150, cy + 190, "SAME MORNING", 24, PRIO_PIECE, "loop")
            sc.text("DOING NOTHING DIFFERENT", cx, cy - 360,
                    "DOING NOTHING DIFFERENT", 34)
            sc.text("THE SCROLL TRAP", cx, cy - 460, "THE SCROLL TRAP", 24, PRIO_KICKER)
    elif cid == 4:
        if idx == 0:
            sc.fixed("card", card_box(cx, cy + 60, 360, 150), PROP, "truth")
            sc.accent("stamp", glyph_box(cx, cy + 60, 250, 120), "truth")
            sc.text("THAT'S THE UNCOMFORTABLE PART", cx, cy - 360,
                    "THAT'S THE UNCOMFORTABLE PART", 32)
            sc.text("THE UNCOMFORTABLE PART", cx, cy - 460,
                    "THE UNCOMFORTABLE PART", 24, PRIO_KICKER)
        elif idx == 1:
            sc.fixed("job", glyph_box(cx - 250, cy + 40, 170, 170), PROP, "job")
            sc.fixed("prop", house_box(cx + 250, cy + 40, 60), PROP, "prop")
            sc.accent("x1", glyph_box(cx - 250, cy + 40, 200, 200), "job")
            sc.accent("x2", glyph_box(cx + 250, cy + 40, 200, 200), "prop")
            sc.text("DON'T QUIT YOUR JOB TOMORROW", cx, cy - 360,
                    "DON'T QUIT YOUR JOB TOMORROW", 34)
            sc.text("THE UNCOMFORTABLE PART", cx, cy - 460,
                    "THE UNCOMFORTABLE PART", 24, PRIO_KICKER)
            sc.text("AND NOT BUY A PROPERTY NEXT MONTH", cx, cy + 430,
                    "AND NOT BUY A PROPERTY NEXT MONTH", 24, PRIO_FOOT)
        else:
            sc.fixed("cal", card_box(cx - 220, cy + 40, 300, 190), PROP, "cal")
            sc.accent("x", glyph_box(cx - 220, cy + 40, 260, 150), "cal")
            sc.fixed("arrow", arrow_box((cx - 30, cy + 50), (cx + 120, cy + 50)), PROP, "now")
            sc.accent("now", glyph_box(cx + 260, cy + 40, 200, 120), "now")
            sc.text("STOP WAITING FOR PERFECT", cx, cy - 360,
                    "STOP WAITING FOR PERFECT", 38)
            sc.text("THE UNCOMFORTABLE PART", cx, cy - 460,
                    "THE UNCOMFORTABLE PART", 24, PRIO_KICKER)
    elif cid == 5:
        if idx == 0:
            sc.fixed("lst", card_box(cx, cy + 40, 300, 150), PROP, "ck1")
            sc.accent("chk", glyph_box(cx + 100, cy + 40, 60, 60), "ck1")
            sc.text("ANALYZE A DEAL", cx - 80, cy + 40, "ANALYZE A DEAL", 26, PRIO_PIECE, "ck1")
            sc.text("LEARN HOW TO ANALYZE A DEAL", cx, cy - 360,
                    "LEARN HOW TO ANALYZE A DEAL", 36)
            sc.text("THE WORK", cx, cy - 460, "THE WORK", 24, PRIO_KICKER)
            sc.text("USE YOUR EVENINGS", cx, cy + 430, "USE YOUR EVENINGS", 24, PRIO_FOOT)
        elif idx == 1:
            for i, dx in enumerate((-240, 0, 240)):
                sc.fixed(f"tile{i}", card_box(cx + dx, cy + 40, 210, 150), PROP, "wk")
            sc.text("TALK. STUDY. BUILD.", cx, cy - 360, "TALK. STUDY. BUILD.", 42)
            sc.text("THE WORK", cx, cy - 460, "THE WORK", 24, PRIO_KICKER)
            for i, (dx, lab) in enumerate(((-240, "BROKERS"), (0, "YOUR MARKET"),
                                          (240, "RELATIONSHIPS"))):
                sc.text(lab, cx + dx, cy + 150, lab, 24, PRIO_PIECE, "wk")
        else:
            sc.fixed("badge", glyph_box(cx, cy + 30, 300, 130), PROP, "useful")
            sc.fixed("fin", card_box(cx, cy - 110, 320, 90), PROP, "useful")
            sc.text("LEARN HOW FINANCING WORKS", cx, cy - 110,
                    "LEARN HOW FINANCING WORKS", 24, PRIO_PIECE, "useful")
            sc.text("BECOME USEFUL TO THE BUSINESS", cx, cy - 360,
                    "BECOME USEFUL TO THE BUSINESS", 32)
            sc.text("THE WORK", cx, cy - 460, "THE WORK", 24, PRIO_KICKER)
    elif cid == 6:
        if idx == 0:
            sc.fixed("door", door_box(cx + 30, cy + 10, 300), PROP, "room")
            sc.fixed("ticket", tag_box(cx - 260, cy + 60, 120, 46), PROP, "room")
            sc.accent("x", glyph_box(cx - 260, cy + 60, 150, 150), "tkt")
            sc.text("NOBODY OWES YOU AN OPPORTUNITY", cx, cy - 360,
                    "NOBODY OWES YOU AN OPPORTUNITY", 34)
            sc.text("THE ROOM", cx, cy - 460, "THE ROOM", 24, PRIO_KICKER)
            sc.text("JUST BECAUSE YOU WANT ONE", cx, cy + 430,
                    "JUST BECAUSE YOU WANT ONE", 24, PRIO_FOOT)
        elif idx == 1:
            sc.fixed("door", door_box(cx + 30, cy + 10, 300), PROP)
            sc.fixed("badge", glyph_box(cx - 260, cy + 60, 230, 110), PROP, "val")
            sc.text("VALUE", cx - 260, cy + 60, "VALUE", 30, PRIO_PIECE, "val")
            sc.text("BECOME VALUABLE ENOUGH", cx, cy - 360, "BECOME VALUABLE ENOUGH", 40)
            sc.text("THE ROOM", cx, cy - 460, "THE ROOM", 24, PRIO_KICKER)
        else:
            sc.fixed("door", door_box(cx + 30, cy + 10, 300), PROP, "room")
            sc.fixed("ticket", tag_box(cx - 260, cy + 60, 130, 48), PROP, "room")
            sc.text("INVITED", cx - 260, cy + 60, "INVITED", 30, PRIO_PIECE, "inv")
            sc.text("INVITED INTO THE ROOM", cx, cy - 360, "INVITED INTO THE ROOM", 40)
            sc.text("THE ROOM", cx, cy - 460, "THE ROOM", 24, PRIO_KICKER)
    elif cid == 7:
        if idx == 0:
            sc.fixed("chart", card_box(cx, cy + 40, 360, 190), PROP, "mrk")
            sc.accent("x", glyph_box(cx, cy + 40, 300, 140), "mrk")
            sc.text("STOP BLAMING THE MARKET", cx, cy - 360, "STOP BLAMING THE MARKET", 36)
            sc.text("THE MIRROR", cx, cy - 460, "THE MIRROR", 24, PRIO_KICKER)
            sc.text("LOOK AT YOUR OWN PROCESS", cx, cy + 430,
                    "LOOK AT YOUR OWN PROCESS", 24, PRIO_FOOT)
        elif idx == 1:
            sc.fixed("chk", card_box(cx, cy + 40, 300, 190), PROP, "mir")
            sc.accent("q1", glyph_box(cx - 90, cy + 40, 60, 60), "mir")
            sc.accent("q2", glyph_box(cx - 90, cy + 130, 60, 60), "mir")
            sc.text("ARE YOUR NUMBERS REALISTIC?", cx, cy - 360,
                    "ARE YOUR NUMBERS REALISTIC?", 32)
            sc.text("THE MIRROR", cx, cy - 460, "THE MIRROR", 24, PRIO_KICKER)
            sc.text("ARE YOU FOLLOWING UP?", cx, cy + 430, "ARE YOU FOLLOWING UP?", 24, PRIO_FOOT)
        else:
            sc.fixed("p1", card_box(cx - 230, cy + 40, 230, 170), PROP, "q")
            sc.fixed("p2", card_box(cx + 230, cy + 40, 230, 170), PROP, "q")
            sc.text("TALKING TO ENOUGH PEOPLE?", cx, cy - 360,
                    "TALKING TO ENOUGH PEOPLE?", 34)
            sc.text("THE MIRROR", cx, cy - 460, "THE MIRROR", 24, PRIO_KICKER)
            sc.text("DO YOU UNDERSTAND THE RISKS?", cx, cy + 430,
                    "DO YOU UNDERSTAND THE RISKS?", 24, PRIO_FOOT)
    elif cid == 8:
        if idx == 0:
            sc.fixed("con", card_box(cx - 230, cy + 40, 220, 170), PROP, "c0")
            sc.fixed("exe", card_box(cx + 230, cy + 40, 220, 170), PROP, "e0")
            sc.text("JUST CONSUMING", cx - 230, cy + 150, "JUST CONSUMING", 24, PRIO_PIECE, "c0")
            sc.text("REALLY LEARNING", cx + 230, cy + 150, "REALLY LEARNING", 24, PRIO_PIECE, "e0")
            sc.text("LEARNING OR JUST CONSUMING?", cx, cy - 360,
                    "LEARNING OR JUST CONSUMING?", 32)
            sc.text("CONSUME OR EXECUTE", cx, cy - 460, "CONSUME OR EXECUTE", 24, PRIO_KICKER)
        elif idx == 1:
            sc.fixed("alone", card_box(cx - 230, cy + 40, 220, 170), PROP, "a1")
            sc.fixed("help", card_box(cx + 230, cy + 40, 220, 170), PROP, "h1")
            sc.text("DOING IT ALONE", cx - 230, cy + 150, "DOING IT ALONE", 24, PRIO_PIECE, "a1")
            sc.text("ASKING FOR HELP", cx + 230, cy + 150, "ASKING FOR HELP", 24, PRIO_PIECE, "h1")
            sc.text("TOO PROUD TO ASK FOR HELP?", cx, cy - 360,
                    "TOO PROUD TO ASK FOR HELP?", 34)
            sc.text("CONSUME OR EXECUTE", cx, cy - 460, "CONSUME OR EXECUTE", 24, PRIO_KICKER)
        else:
            sc.fixed("strat", card_box(cx - 240, cy + 40, 210, 190), PROP, "s2")
            sc.accent("x", glyph_box(cx - 240, cy + 40, 180, 150), "s2")
            sc.fixed("bar", card_box(cx + 220, cy + 40, 210, 190), PROP, "b2")
            sc.text("NEW STRATEGY", cx - 240, cy + 160, "NEW STRATEGY", 24, PRIO_PIECE, "s2")
            sc.text("EXECUTE THE BASICS LONG ENOUGH", cx, cy - 360,
                    "EXECUTE THE BASICS LONG ENOUGH", 34)
            sc.text("CONSUME OR EXECUTE", cx, cy - 460, "CONSUME OR EXECUTE", 24, PRIO_KICKER)
    elif cid == 9:
        if idx == 0:
            sc.fixed("job", glyph_box(cx, cy + 30, 200, 190), PROP, "job")
            sc.accent("x", glyph_box(cx, cy + 30, 240, 220), "job")
            sc.text("JOB", cx, cy + 165, "JOB", 26, PRIO_PIECE, "job")
            sc.text("YOUR JOB IS NOT THE ENEMY", cx, cy - 360,
                    "YOUR JOB IS NOT THE ENEMY", 36)
            sc.text("THE REAL ENEMY", cx, cy - 460, "THE REAL ENEMY", 24, PRIO_KICKER)
            sc.text("YOUR LACK OF DIRECTION IS", cx, cy + 430,
                    "YOUR LACK OF DIRECTION IS", 24, PRIO_FOOT)
        elif idx == 1:
            sc.fixed("compass", clock_box(cx, cy + 40, 105), PROP, "dir")
            sc.accent("x", glyph_box(cx, cy + 40, 230, 230), "dir")
            sc.text("LACK OF DIRECTION", cx, cy - 360, "LACK OF DIRECTION", 38)
            sc.text("THE REAL ENEMY", cx, cy - 460, "THE REAL ENEMY", 24, PRIO_KICKER)
        else:
            sc.fixed("c1", card_box(cx - 230, cy + 40, 220, 170), PROP, "w2")
            sc.fixed("c2", card_box(cx + 230, cy + 40, 220, 170), PROP, "w2")
            sc.text("YOUR HABIT OF WAITING IS", cx, cy - 360,
                    "YOUR HABIT OF WAITING IS", 34)
            sc.text("THE REAL ENEMY", cx, cy - 460, "THE REAL ENEMY", 24, PRIO_KICKER)
            sc.text("LACK OF CONSISTENCY", cx - 230, cy + 160,
                    "LACK OF CONSISTENCY", 24, PRIO_PIECE, "w2")
            sc.text("HABIT OF WAITING", cx + 230, cy + 160, "HABIT OF WAITING", 24, PRIO_PIECE, "w2")
    elif cid == 10:
        if idx == 0:
            sc.fixed("brief", glyph_box(cx - 250, base - 60, 180, 170), PROP)
            sc.fixed("bld", building_box(cx + 250, base, 140, 260), PROP)
            sc.fixed("arrow", arrow_box((cx - 140, base - 160), (cx + 60, base - 160)), PROP)
            sc.text("KEEP THE JOB. BUILD THE PLAN.", cx, cy - 360,
                    "KEEP THE JOB. BUILD THE PLAN.", 36)
            sc.text("THE BREAK", cx, cy - 460, "THE BREAK", 24, PRIO_KICKER)
            sc.text("BUILD SOMETHING MEANINGFUL", cx, cy + 430,
                    "BUILD SOMETHING MEANINGFUL", 26, PRIO_FOOT)
        elif idx == 1:
            sc.fixed("loop", loop_box(cx, cy + 40, 150), PROP, "loop")
            sc.accent("tick", glyph_box(cx - 40, cy + 40, 60, 60), "loop")
            sc.text("SAME LIFE. SAME RESULT.", cx, cy - 360, "SAME LIFE. SAME RESULT.", 40)
            sc.text("THE BREAK", cx, cy - 460, "THE BREAK", 24, PRIO_KICKER)
            sc.text("DON'T EXPECT A DIFFERENT FUTURE", cx, cy + 430,
                    "DON'T EXPECT A DIFFERENT FUTURE", 24, PRIO_FOOT)
        else:
            sc.fixed("som", card_box(cx - 230, cy + 40, 300, 180), PROP, "som")
            sc.accent("x", glyph_box(cx - 230, cy + 40, 280, 150), "som")
            sc.fixed("arrow", arrow_box((cx - 40, cy + 60), (cx + 90, cy + 60)), PROP, "wk2")
            sc.accent("wk", glyph_box(cx + 260, cy + 50, 230, 120), "wk2")
            sc.text("STOP SAYING SOMEDAY", cx, cy - 360, "STOP SAYING SOMEDAY", 40)
            sc.text("THE BREAK", cx, cy - 460, "THE BREAK", 24, PRIO_KICKER)
            sc.text("AND START ASKING...", cx, cy + 430, "AND START ASKING...", 24, PRIO_FOOT)
    else:
        if idx == 0:
            sc.fixed("q", card_box(cx, cy + 20, 430, 300), PROP, "q0")
            sc.text("WHAT AM I DOING THIS WEEK", cx, cy - 360,
                    "WHAT AM I DOING THIS WEEK", 38)
            sc.text("THE QUESTION", cx, cy - 460, "THE QUESTION", 24, PRIO_KICKER)
            sc.text("THAT MAKES ME HARDER TO IGNORE?", cx, cy + 430,
                    "THAT MAKES ME HARDER TO IGNORE?", 24, PRIO_FOOT)
        elif idx == 1:
            sc.fixed("q", card_box(cx, cy + 40, 400, 250), PROP, "q1")
            sc.text("THAT ANSWER WILL TELL YOU A LOT", cx, cy - 360,
                    "THAT ANSWER WILL TELL YOU A LOT", 32)
            sc.text("THE QUESTION", cx, cy - 460, "THE QUESTION", 24, PRIO_KICKER)
        else:
            sc.fixed("m", glyph_box(cx - 300, cy + 40, 140, 300), PROP, "brk")
            sc.fixed("t", glyph_box(cx - 100, cy + 40, 140, 300), PROP, "brk")
            sc.fixed("k", glyph_box(cx + 100, cy + 40, 140, 300), PROP, "brk")
            sc.fixed("f", glyph_box(cx + 300, cy + 40, 140, 300), PROP, "brk")
            sc.text("MONEY. TIME. KNOWLEDGE. FEAR.", cx, cy - 360,
                    "MONEY. TIME. KNOWLEDGE. FEAR.", 34)
            sc.text("THE QUESTION", cx, cy - 460, "THE QUESTION", 24, PRIO_KICKER)
            sc.text("WHICH ONE IS HOLDING YOU BACK?", cx, cy + 430,
                    "WHICH ONE IS HOLDING YOU BACK?", 24, PRIO_FOOT)


# ============================================================ story data

VIDEO_TITLE = "harder_to_ignore"
VOICE = "en-US-GuyNeural"      # male narrator for this story
QA_MAX_DUR = 340                # single long-form video (about 3.5-4 min)

CLIPS = [
    {"id": 1, "name": "The Real Bottleneck",
     "narration": "Most people don't need more money to start in real estate. "
                  "They need to stop wasting the money, time, and opportunities "
                  "they already have. I hear the same excuses all the time."},
    {"id": 2, "name": "The Excuses",
     "narration": "I have a full-time job. I don't have enough capital. "
                  "I don't know enough. I'll start when life gets easier."},
    {"id": 3, "name": "The Scroll Trap",
     "narration": "But then those same people spend three hours scrolling every night. "
                  "They watch videos about becoming wealthy. They save posts about "
                  "real estate. They talk about wanting financial freedom. And then "
                  "they do absolutely nothing different the next morning."},
    {"id": 4, "name": "The Uncomfortable Part",
     "narration": "That's the uncomfortable part. You don't need to quit your job "
                  "tomorrow. You don't need to buy a property next month. You need "
                  "to stop waiting for the perfect moment."},
    {"id": 5, "name": "The Work",
     "narration": "Use your evenings. Learn how to analyze a deal. Talk to brokers. "
                  "Study your market. Build relationships. Learn how financing "
                  "actually works. Become useful to people already doing the business."},
    {"id": 6, "name": "The Room",
     "narration": "Because nobody owes you an opportunity just because you want one. "
                  "You have to become valuable enough to be invited into the room."},
    {"id": 7, "name": "The Mirror",
     "narration": "And if you're already investing but struggling, stop blaming the "
                  "market for everything. Look at your own process. Are your numbers "
                  "realistic? Are you following up? Are you talking to enough people? "
                  "Do you understand the risks?"},
    {"id": 8, "name": "Consume or Execute",
     "narration": "Are you learning, or just consuming content? Are you trying to do "
                  "everything alone because you're too proud to ask for help? "
                  "Sometimes the problem isn't that you need another strategy. "
                  "Sometimes the problem is that you haven't executed the basic ones "
                  "long enough."},
    {"id": 9, "name": "The Real Enemy",
     "narration": "Your job is not the enemy. Your lack of direction is. Your lack "
                  "of consistency is. Your habit of waiting is."},
    {"id": 10, "name": "The Break",
     "narration": "You can keep your job and still build something meaningful. But "
                  "you cannot keep living the exact same way and expect a completely "
                  "different financial future. At some point, you have to stop saying, "
                  "Someday I'll get into real estate."},
    {"id": 11, "name": "The Question",
     "narration": "And start asking, what am I doing this week that makes me harder "
                  "to ignore? That answer will tell you a lot. What's the biggest "
                  "thing holding you back right now: money, time, knowledge, or fear?"},
]

NARR_BEATS = {
    1: ["Most people don't need more money to start in real estate",
        "They need to stop wasting the money time and opportunities they already have",
        "I hear the same excuses all the time"],
    2: ["I have a full-time job",
        "I don't have enough capital",
        "I don't know enough I'll start when life gets easier"],
    3: ["But then those same people spend three hours scrolling every night",
        "They watch videos about becoming wealthy They save posts about real estate They talk about wanting financial freedom",
        "And then they do absolutely nothing different the next morning"],
    4: ["That's the uncomfortable part",
        "You don't need to quit your job tomorrow You don't need to buy a property next month",
        "You need to stop waiting for the perfect moment"],
    5: ["Use your evenings Learn how to analyze a deal",
        "Talk to brokers Study your market Build relationships",
        "Learn how financing actually works Become useful to people already doing the business"],
    6: ["Because nobody owes you an opportunity just because you want one",
        "You have to become valuable enough",
        "to be invited into the room"],
    7: ["And if you're already investing but struggling stop blaming the market for everything",
        "Look at your own process Are your numbers realistic",
        "Are you following up Are you talking to enough people Do you understand the risks"],
    8: ["Are you learning or just consuming content",
        "Are you trying to do everything alone because you're too proud to ask for help",
        "Sometimes the problem isn't that you need another strategy Sometimes the problem is that you haven't executed the basic ones long enough"],
    9: ["Your job is not the enemy",
        "Your lack of direction is",
        "Your lack of consistency is Your habit of waiting is"],
    10: ["You can keep your job and still build something meaningful",
         "But you cannot keep living the exact same way and expect a completely different financial future",
         "At some point you have to stop saying Someday I'll get into real estate"],
    11: ["And start asking What am I doing this week that makes me harder to ignore",
         "That answer will tell you a lot",
         "What's the biggest thing holding you back right now money time knowledge or fear"],
}

PAD_BEFORE = {1: 0.5, 4: 0.5, 6: 0.5, 11: 0.55}
PAD_AFTER = 0.35


def apply_to(gm):
    """Point engine module globals at this story (used before render/compile/QA)."""
    gm.VIDEO_TITLE = VIDEO_TITLE
    gm.CLIPS = CLIPS
    gm.NARR_BEATS = NARR_BEATS
    gm.PAD_BEFORE = PAD_BEFORE
    gm.PAD_AFTER = PAD_AFTER
    gm.QA_MAX_DUR = QA_MAX_DUR
    gm.VOICE = VOICE
    gm.MUSIC_BED = "warm"
    gm._TIMING_CACHE.clear()
    gm._WORD_P_CACHE.clear()
    gm.sfx_events = sfx_events
    gm._SC = _SC if hasattr(gm, "_SC") else _SC


# ============================================================ design system

def clamp01(t):
    return g.clamp01(t)


def dim_col(color, a):
    return tuple(min(255, int(v * a)) for v in color)


def halo(d, cx, cy, r, color, alpha=0.16):
    g.glow_circle(d, cx, cy, r, color, layers=2, alpha=alpha)


def floorline(d, cx, cy, span=820):
    d.line([cx - span, cy, cx + span, cy], fill=dim_col(g.GRAY, 0.55), width=3)


def card(d, x, y, w, h, color, radius=20, a=1.0, shadow=True):
    if shadow and a > 0.05:
        off = 8
        d.rounded_rectangle([x - w / 2 + off, y - h / 2 + off, x + w / 2 + off, y + h / 2 + off],
                            radius=radius, fill=(14, 14, 18))
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


# ---- glyphs -----------------------------------------------------------

def phone_g(d, x, y, s, color, a=1.0):
    c = dim_col(color, a)
    w, h = 104 * s, 208 * s
    d.rounded_rectangle([x - w / 2, y - h / 2, x + w / 2, y + h / 2],
                        radius=int(22 * s), outline=c, width=5)
    d.rounded_rectangle([x - w / 2 + 10 * s, y - h / 2 + 10 * s,
                         x + w / 2 - 10 * s, y + h / 2 - 26 * s],
                        radius=int(10 * s), outline=dim_col(c, 0.6), width=3)
    d.ellipse([x - 8 * s, y + h / 2 - 16 * s, x + 8 * s, y + h / 2],
              outline=c, width=4)


def door_g(d, x, y, wh, color, a=1.0, open=0.0, glow=0.0):
    c = dim_col(color, a)
    if glow > 0.02:
        g.glow_circle(d, x + open * wh * 0.22, y - wh * 0.45, int(wh * (0.55 + glow * 0.25)),
                      g.GOLD, layers=2, alpha=0.5 * glow)
    yb = y + wh / 5
    d.rectangle([x - wh / 2, y - wh, x + wh / 2, yb], outline=c, width=6)
    if open > 0.02:
        sw = int(open * wh / 2)
        d.line([x + sw, y - wh, x + sw, yb], fill=dim_col(c, 0.5), width=5)
    d.ellipse([x + wh / 2 - 26, yb - 40, x + wh / 2 - 18, yb - 32], fill=c)


def brief_g(d, x, y, s, color, a=1.0):
    c = dim_col(color, a)
    w, h = 150 * s, 100 * s
    d.rounded_rectangle([x - w / 2, y - h / 2, x + w / 2, y + h / 2],
                        radius=16, outline=c, width=5)
    d.arc([x - 40 * s, y - h / 2 - 45 * s, x + 40 * s, y - h / 2 + 25 * s],
          180, 360, fill=c, width=5)


def book_g(d, x, y, s, color, a=1.0):
    c = dim_col(color, a)
    w, h = 130 * s, 110 * s
    for dx in (-12, 12):
        d.rounded_rectangle([x - w / 2 + dx, y - h / 2, x + w / 2 + dx, y + h / 2],
                            radius=8, outline=dim_col(c, 0.8), width=4)
    d.line([x, y - h / 2, x, y + h / 2], fill=c, width=4)


def clock_g(d, x, y, r, color, a=1.0, deg=0.0):
    c = dim_col(color, a)
    d.ellipse([x - r, y - r, x + r, y + r], outline=c, width=5)
    ang = math.radians(deg)
    d.line([x, y, x + math.cos(ang) * r * 0.7, y + math.sin(ang) * r * 0.7],
           fill=c, width=4)


def chart_g(d, x, y, w, h, color, a=1.0, down=1.0):
    c = dim_col(color, a)
    pts = [(x - w / 2, y + h / 2)]
    for i in range(5):
        xx = x - w / 2 + i * (w / 4)
        wavy = math.sin(i * 1.4 + 2) * 16
        yy = y - h / 4 - i * (h / 6) * (1 if down else 0.4) - wavy * (0.5 if down else 0.9)
        pts.append((xx, yy))
    pts.append((x + w / 2, y + h / 2 - (0 if down else h / 3)))
    d.line(pts, fill=c, width=5, joint="curve")


def ripple(d, x, y, t, r0, color):
    for i in range(3):
        rr = r0 + ((t * 120 + i * 60) % 180)
        d.ellipse([x - rr, y - rr, x + rr, y + rr],
                  outline=dim_col(color, max(0.0, 0.4 - 0.004 * rr)), width=4)


# ============================================================ scene: story clips

REG = {}


def draw1(d, t_abs):
    set_beat(1, g.local_beat(CLIPS[0], t_abs)[0])
    idx, p = g.local_beat(CLIPS[0], t_abs)
    cx, cy = g.W // 2, g.H // 2 + 90
    base = cy + 190
    c = CLIPS[0]

    if idx == 0:
        halo(d, cx + 250, base, 200, g.GOLD, 0.18)
        floorline(d, cx, base + 60, span=430)
        g._coin_pile(d, cx - 250, base, 3, g.GOLD, r=15)
        g.arrow(d, cx - 180, base - 150, cx + 110, base - 150, color=g.GOLD, lw=7)
        grow = g.spring(p, k=10)
        g.house(d, cx + 250, base, size=46, color=g.WHITE, lw=4, shadow=True,
                fill=dim_col(g.WHITE, 0.9 + 0.1 * math.sin(t_abs * 3)))
        for k in range(5):
            g.coin(d, cx + 250 + math.cos(t_abs * 2.4 + k) * 70,
                   base - 20 + math.sin(t_abs * 2.4 + k) * 24, r=10,
                   color=g.GOLD, rot=t_abs + k, shadow=True) if grow > 0.3 else None
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 0, 0.2),
                   "MONEY ISN'T THE BOTTLENECK", 38)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 0, 0.1),
                   "THE REAL BOTTLENECK", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 0, 0.35),
                   "TO START BUILDING IN REAL ESTATE", 24, g.GRAY)

    elif idx == 1:
        halo(d, cx, cy + 40, 300, g.RED, 0.10)
        floorline(d, cx, cy + 240, span=400)
        labels = [(-240, "MONEY", g.GOLD), (0, "TIME", g.GRAY), (240, "OPPORTUNITY", g.RED)]
        for i, (dx, lab, col) in enumerate(labels):
            ap = max(0.0, clamp01((p - (0.1 + i * 0.18)) / 0.16))
            if ap <= 0.02:
                continue
            g.price_tag(d, cx + dx, cy + 30, w=92, h=32, color=col, lw=4)
            g.arrow(d, cx + dx, cy + 90, cx + dx, cy + 200, color=dim_col(col, ap), lw=6)
            g.coin(d, cx + dx, cy + 212 + abs(math.sin(t_abs * 3 + i)) * 16, r=9,
                   color=col, rot=t_abs + i, shadow=True) if ap > 0.9 else None
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 1, 0.15),
                   "STOP WASTING WHAT YOU HAVE", 38)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 1, 0.05),
                   "THE REAL BOTTLENECK", 24, g.GRAY)
        for i, (dx, lab, col) in enumerate(labels):
            pop_text(d, cx + dx, cy + 300, t_abs, g.beat_abs(c, 1, 0.55 + i * 0.1),
                     lab, color=col, px=26)

    else:
        halo(d, cx, cy + 10, 340, g.GRAY, 0.10)
        phrases = ["I HAVE A JOB", "NO CAPITAL", "NO KNOWLEDGE", "SOMEDAY"]
        cols = [g.GRAY, g.GRAY, g.GRAY, g.RED]
        for i, dx in enumerate((-230, -77, 77, 230)):
            ap = max(0.0, clamp01((p - (0.08 + i * 0.12)) / 0.14))
            if ap <= 0.02:
                continue
            tilt = max(0.0, 1 - ap) * 10
            card(d, cx + dx, cy + 10, 250, 130, cols[i], radius=18, a=ap)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 2, 0.16),
                   "THE SAME EXCUSES. EVERY TIME.", 36)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 2, 0.08),
                   "THE REAL BOTTLENECK", 24, g.GRAY)


def draw2(d, t_abs):
    set_beat(2, g.local_beat(CLIPS[1], t_abs)[0])
    idx, p = g.local_beat(CLIPS[1], t_abs)
    cx, cy = g.W // 2, g.H // 2 + 90
    c = CLIPS[1]

    if idx == 0:
        halo(d, cx, cy + 10, 260, g.GRAY, 0.12)
        ap = max(0.0, clamp01((p - 0.1) / 0.18))
        card(d, cx, cy + 20, 250, 190, g.DIM, radius=22, a=ap)
        clock_g(d, cx, cy - 20, 62, g.GOLD, ap, deg=90 + p * 260)
        badge(d, cx, cy + 70, "9 TO 5", g.GRAY, px=24, w=150, h=40, a=ap) if ap > 0.2 else None
        pop_text(d, cx, cy - 120, t_abs, g.beat_abs(c, 0, 0.35), "EXCUSE 1 OF 4", g.GOLD, 22)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 0, 0.25),
                   "I HAVE A FULL-TIME JOB", 40)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 0, 0.1),
                   "THE EXCUSES", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 0, 0.55),
                   "BUT THAT'S NOT THE BLOCKER", 24, g.GRAY)

    elif idx == 1:
        halo(d, cx, cy + 10, 260, g.RED, 0.10)
        ap = max(0.0, clamp01((p - 0.1) / 0.18))
        card(d, cx, cy + 20, 250, 180, g.DIM, radius=22, a=ap)
        g._coin_pile(d, cx - 60, cy + 120, 2, g.GRAY, r=15)
        g.big_text(d, cx + 70, cy - 10, "?", color=dim_col(g.RED, ap), px=60) if ap > 0.1 else None
        pop_text(d, cx, cy - 120, t_abs, g.beat_abs(c, 1, 0.35), "EXCUSE 2 OF 4", g.GOLD, 22)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 1, 0.2),
                   "I DON'T HAVE ENOUGH CAPITAL", 36)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 1, 0.1),
                   "THE EXCUSES", 24, g.GRAY)

    else:
        halo(d, cx, cy + 10, 320, g.RED, 0.10)
        for dx, glow in ((-230, g.GRAY), (230, g.GOLD)):
            ap = max(0.0, clamp01((p - 0.12) / 0.16))
            card(d, cx + dx, cy + 20, 250, 180, glow, radius=22, a=ap)
        book_g(d, cx - 230, cy + 10, 0.9, g.GOLD, ap)
        cup_col = dim_col(g.GRAY, ap)
        d.rounded_rectangle([cx + 150, cy - 25, cx + 230, cy + 45], radius=12,
                            outline=cup_col, width=4) if ap > 0.1 else None
        d.arc([cx + 230, cy - 25, cx + 260, cy + 15], 270, 90,
              fill=cup_col, width=4) if ap > 0.1 else None
        pop_text(d, cx - 230, cy + 160, t_abs, g.beat_abs(c, 2, 0.25), "I DON'T KNOW ENOUGH",
                 g.GOLD, 24)
        pop_text(d, cx + 230, cy + 160, t_abs, g.beat_abs(c, 2, 0.25), "SOMEDAY", g.RED, 30)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 2, 0.35),
                   "I'LL START WHEN LIFE GETS EASIER", 34)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 2, 0.1),
                   "THE EXCUSES", 24, g.GRAY)


def draw3(d, t_abs):
    set_beat(3, g.local_beat(CLIPS[2], t_abs)[0])
    idx, p = g.local_beat(CLIPS[2], t_abs)
    cx, cy = g.W // 2, g.H // 2 + 90
    c = CLIPS[2]

    if idx == 0:
        halo(d, cx, cy + 50, 300, g.RED, 0.15)
        ap = max(0.0, clamp01((p - 0.1) / 0.2))
        phone_g(d, cx - 120, cy + 50, 1.5, dim_col(g.WHITE, ap) if ap > 0.02 else g.WHITE)
        clock_g(d, cx + 210, cy + 50, 66, g.GOLD, ap, deg=p * 360)
        for k in range(5):
            g.glow_circle(d, cx - 120 + math.cos(t_abs * 2 + k) * 140,
                          cy + 50 + math.sin(t_abs * 2 + k) * 60, 12, g.GOLD,
                          layers=1, alpha=0.3)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 0, 0.3),
                   "3 HOURS SCROLLING EVERY NIGHT", 34)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 0, 0.1),
                   "THE SCROLL TRAP", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 0, 0.5),
                   "EVERY SINGLE NIGHT", 24, g.GRAY)

    elif idx == 1:
        halo(d, cx, cy + 40, 320, g.GRAY, 0.10)
        icons = [(-240, g.GRAY), (0, g.GRAY), (240, g.GRAY)]
        for i, (dx, col) in enumerate(icons):
            ap = max(0.0, clamp01((p - (0.1 + i * 0.16)) / 0.15))
            if ap <= 0.02:
                continue
            card(d, cx + dx, cy + 40, 210, 150, col, radius=18, a=ap)
            if i == 0:
                d.polygon([(cx + dx - 26, cy - 5), (cx + dx + 30, cy - 5),
                           (cx + dx + 30, cy + 45), (cx + dx - 26, cy + 45)],
                          outline=dim_col(g.GOLD, ap), width=4)
                d.line([cx + dx + 30, cy - 5, cx + dx + 30, cy + 45],
                       fill=dim_col(g.GOLD, ap), width=4)
            elif i == 1:
                d.rounded_rectangle([cx + dx - 24, cy - 20, cx + dx + 24, cy + 40],
                                    radius=6, outline=dim_col(g.GOLD, ap), width=4)
                d.line([cx + dx - 24, cy + 52, cx + dx + 8, cy + 52], fill=dim_col(g.GOLD, ap), width=4)
            else:
                d.rounded_rectangle([cx + dx - 34, cy - 18, cx + dx + 34, cy + 42],
                                    radius=14, outline=dim_col(g.GOLD, ap), width=4)
                d.arc([cx + dx - 8, cy + 10, cx + dx + 6, cy + 26], 0, 180,
                      fill=dim_col(g.GOLD, ap), width=3)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 1, 0.3),
                   "WATCH. SAVE. TALK.", 40)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 1, 0.05),
                   "THE SCROLL TRAP", 24, g.GRAY)
        for i, (dx, lab, _) in enumerate(zip((-240, 0, 240), ("VIDEOS ABOUT WEALTH", "POSTS YOU SAVE",
                                                              "FREEDOM TALKS"), icons)):
            pop_text(d, cx + dx, cy + 150, t_abs, g.beat_abs(c, 1, 0.35 + i * 0.12),
                     lab, g.GOLD, 22)

    else:
        halo(d, cx, cy + 30, 320, g.RED, 0.12)
        ap = max(0.0, clamp01((p - 0.2) / 0.25))
        phone_g(d, cx - 250, cy + 40, 1.3, g.DIM)
        loop_growth = g.spring(max(0.0, clamp01((p - 0.4) / 0.4)), k=8)
        rr = 120 * loop_growth
        if rr > 8:
            d.ellipse([cx + 150 - rr, cy + 30 - rr, cx + 150 + rr, cy + 30 + rr],
                      outline=dim_col(g.RED, 0.9), width=6)
            g.arrow(d, cx + 150 + (rr - 8) * math.cos(math.pi / 4),
                    cy + 30 - (rr - 8) * math.sin(math.pi / 4),
                    cx + 150 + rr * math.cos(math.pi / 4),
                    cy + 30 - rr * math.sin(math.pi / 4),
                    color=g.RED, lw=6)
        badge(d, cx + 150, cy + 190, "SAME MORNING", g.RED, px=24, w=210, h=44, a=ap)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 2, 0.3),
                   "DOING NOTHING DIFFERENT", 34)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 2, 0.1),
                   "THE SCROLL TRAP", 24, g.GRAY)


def draw4(d, t_abs):
    set_beat(4, g.local_beat(CLIPS[3], t_abs)[0])
    idx, p = g.local_beat(CLIPS[3], t_abs)
    cx, cy = g.W // 2, g.H // 2 + 90
    c = CLIPS[3]

    if idx == 0:
        halo(d, cx, cy + 60, 260, g.RED, 0.15)
        ap = max(0.0, clamp01((p - 0.1) / 0.2))
        card(d, cx, cy + 60, 360, 150, g.DIM, radius=20, a=ap)
        st = max(0.0, clamp01((p - 0.3) / 0.2))
        g.stamp_x(d, cx, cy + 60, size=int(100 * st), color=g.RED, rot=0.30 * st,
                  opaque=0.9 * st) if st > 0.05 else None
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 0, 0.2),
                   "THAT'S THE UNCOMFORTABLE PART", 32)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 0, 0.08),
                   "THE UNCOMFORTABLE PART", 24, g.GRAY)

    elif idx == 1:
        halo(d, cx, cy + 40, 340, g.RED, 0.10)
        for dx in (-250, 250):
            ap = max(0.0, clamp01((p - (0.1 + (0 if dx < 0 else 0.18))) / 0.18))
            if ap <= 0.02:
                continue
            card(d, cx + dx, cy + 40, 190, 190, g.DIM, radius=20, a=ap)
        brief_g(d, cx - 250, cy + 30, 0.9, g.WHITE, ap)
        g.house(d, cx + 250, cy + 40, size=60, color=g.WHITE, lw=4, shadow=True)
        for dx in (-250, 250):
            xs = max(0.0, clamp01((p - (0.35 if dx < 0 else 0.5)) / 0.2))
            g.xmark(d, cx + dx, cy + 40, size=int(56 * xs), color=g.RED, lw=6)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 1, 0.2),
                   "DON'T QUIT YOUR JOB TOMORROW", 34)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 1, 0.05),
                   "THE UNCOMFORTABLE PART", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 1, 0.4),
                   "AND NOT BUY A PROPERTY NEXT MONTH", 24, g.GRAY)

    else:
        halo(d, cx, cy + 40, 340, g.RED, 0.10)
        ap = max(0.0, clamp01((p - 0.15) / 0.2))
        card(d, cx - 220, cy + 40, 300, 190, g.DIM, radius=20, a=ap)
        g.big_text(d, cx - 220, cy + 30, "SOMEDAY", color=dim_col(g.GRAY, ap), px=40)
        xs = max(0.0, clamp01((p - 0.45) / 0.25))
        g.xmark(d, cx - 220, cy + 60, size=int(70 * xs), color=g.RED, lw=6)
        g.arrow(d, cx - 40, cy + 45, cx + 120, cy + 45, color=g.GOLD, lw=6)
        bad = max(0.0, clamp01((p - 0.55) / 0.2))
        if bad > 0.02:
            d.rounded_rectangle([cx + 150, cy + 5, cx + 370, cy + 80], radius=14,
                                outline=dim_col(g.GOLD, bad), width=5) if False else badge(
                d, cx + 260, cy + 50, "NOW", g.GOLD, px=30, w=200, h=70, a=bad)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 2, 0.2),
                   "STOP WAITING FOR PERFECT", 38)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 2, 0.05),
                   "THE UNCOMFORTABLE PART", 24, g.GRAY)


def draw5(d, t_abs):
    set_beat(5, g.local_beat(CLIPS[4], t_abs)[0])
    idx, p = g.local_beat(CLIPS[4], t_abs)
    cx, cy = g.W // 2, g.H // 2 + 90
    c = CLIPS[4]

    if idx == 0:
        halo(d, cx, cy + 40, 240, g.GOLD, 0.14)
        ap = max(0.0, clamp01((p - 0.15) / 0.2))
        card(d, cx, cy + 40, 300, 150, g.GOLD, radius=20, a=ap)
        book_g(d, cx - 80, cy + 40, 0.9, g.GOLD, ap)
        ch = max(0.0, clamp01((p - 0.5) / 0.2))
        g.check(d, cx + 100, cy + 40, size=int(30 * ch), color=g.GOLD, lw=6) if ch > 0.05 else None
        pop_text(d, cx - 80, cy + 40, t_abs, g.beat_abs(c, 0, 0.35), "ANALYZE A DEAL", g.GOLD, 26)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 0, 0.3),
                   "LEARN HOW TO ANALYZE A DEAL", 36)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 0, 0.1),
                   "THE WORK", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 0, 0.45),
                   "USE YOUR EVENINGS", 24, g.GRAY)

    elif idx == 1:
        halo(d, cx, cy + 40, 320, g.GOLD, 0.10)
        icons = [(-240, g.GRAY), (0, g.GOLD), (240, g.GRAY)]
        for i, (dx, col) in enumerate(icons):
            ap = max(0.0, clamp01((p - (0.1 + i * 0.16)) / 0.15))
            if ap <= 0.02:
                continue
            card(d, cx + dx, cy + 40, 210, 150, col, radius=18, a=ap)
            if i == 0:
                clock_g(d, cx + dx, cy + 40, 40, g.GOLD, ap)
            elif i == 1:
                g.house(d, cx + dx, cy + 40, size=44, color=g.GOLD, lw=4, shadow=True)
            else:
                g.glow_circle(d, cx + dx, cy + 40, 34, g.GOLD, layers=2, alpha=0.3 * ap)
                d.ellipse([cx + dx - 30, cy + 18, cx + dx - 12, cy + 36],
                          outline=dim_col(g.GOLD, ap), width=4)
                d.ellipse([cx + dx + 12, cy + 18, cx + dx + 30, cy + 36],
                          outline=dim_col(g.GOLD, ap), width=4)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 1, 0.3),
                   "TALK. STUDY. BUILD.", 42)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 1, 0.05),
                   "THE WORK", 24, g.GRAY)
        for i, (dx, lab, _) in enumerate(zip((-240, 0, 240), ("BROKERS", "YOUR MARKET",
                                                              "RELATIONSHIPS"), icons)):
            pop_text(d, cx + dx, cy + 150, t_abs, g.beat_abs(c, 1, 0.35 + i * 0.1),
                     lab, g.GRAY if i in (0, 2) else g.GOLD, 24)

    else:
        halo(d, cx, cy + 40, 260, g.GOLD, 0.18)
        ap = max(0.0, clamp01((p - 0.15) / 0.2))
        card(d, cx, cy - 110, 320, 90, g.GOLD, radius=16, a=ap)
        pop_text(d, cx, cy - 110, t_abs, g.beat_abs(c, 2, 0.3),
                 "LEARN HOW FINANCING WORKS", g.GOLD, 24)
        sz = g.spring(max(0.0, clamp01((p - 0.45) / 0.5)), k=9)
        r0 = 30 + sz * 62
        if r0 > 8:
            d.rounded_rectangle([cx - r0, cy + 40 - r0 / 3, cx + r0, cy + 40 + r0 / 3],
                                radius=16, outline=dim_col(g.GOLD, 0.95), width=6)
            g.big_text(d, cx, cy + 40, "USEFUL", color=g.GOLD, px=int(20 + sz * 14))
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 2, 0.35),
                   "BECOME USEFUL TO THE BUSINESS", 32)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 2, 0.05),
                   "THE WORK", 24, g.GRAY)


def draw6(d, t_abs):
    set_beat(6, g.local_beat(CLIPS[5], t_abs)[0])
    idx, p = g.local_beat(CLIPS[5], t_abs)
    cx, cy = g.W // 2, g.H // 2 + 90
    c = CLIPS[5]

    open_p = max(0.0, clamp01((p - 0.35) / 0.55) - 0.15) if idx == 2 else \
        (0.3 * max(0.0, clamp01((p - 0.35) / 0.4)))
    glow_p = clamp01((p - 0.4) / 0.5) if idx == 2 else clamp01((p - 0.3) / 0.5)

    if idx == 0:
        halo(d, cx, cy + 10, 300, g.GRAY, 0.12)
        ap = max(0.0, clamp01((p - 0.1) / 0.2))
        door_g(d, cx + 30, cy + 10, 300, g.DIM, ap, open=0.0, glow=0.0)
        g.price_tag(d, cx - 260, cy + 60, w=120, h=46, color=g.RED, lw=4)
        xs = max(0.0, clamp01((p - 0.5) / 0.25))
        g.xmark(d, cx - 260, cy + 60, size=int(44 * xs), color=g.RED, lw=6)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 0, 0.2),
                   "NOBODY OWES YOU AN OPPORTUNITY", 34)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 0, 0.08),
                   "THE ROOM", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 0, 0.35),
                   "JUST BECAUSE YOU WANT ONE", 24, g.GRAY)

    elif idx == 1:
        halo(d, cx, cy + 10, 300, g.GOLD, 0.14)
        door_g(d, cx + 30, cy + 10, 300, g.WHITE, 1.0, open=0.25, glow=glow_p * 0.5)
        ap = max(0.0, clamp01((p - 0.2) / 0.2))
        d.rounded_rectangle([cx - 365, cy + 5, cx - 155, cy + 115], radius=14,
                            outline=dim_col(g.GOLD, ap), width=5) if ap > 0.02 else None
        pop_text(d, cx - 260, cy + 60, t_abs, g.beat_abs(c, 1, 0.35), "VALUE", g.GOLD, 30)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 1, 0.2),
                   "BECOME VALUABLE ENOUGH", 40)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 1, 0.05),
                   "THE ROOM", 24, g.GRAY)

    else:
        halo(d, cx, cy + 10, 320, g.GOLD, 0.2)
        door_g(d, cx + 30, cy + 10, 300, g.WHITE, 1.0, open=0.55, glow=glow_p)
        ap = max(0.0, clamp01((p - 0.2) / 0.2))
        d.rounded_rectangle([cx - 370, cy + 5, cx - 150, cy + 115], radius=14,
                            outline=dim_col(g.GOLD, ap), width=5) if ap > 0.02 else None
        pop_text(d, cx - 260, cy + 60, t_abs, g.beat_abs(c, 2, 0.3), "INVITED", g.GOLD, 30)
        for k in range(6):
            g.coin(d, cx + 90 + math.cos(t_abs * 2 + k * 1.05) * 150,
                   cy + 10 - 90 + math.sin(t_abs * 2 + k * 1.05) * 60, r=10,
                   color=g.GOLD, rot=t_abs + k, shadow=True) if glow_p > 0.5 else None
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 2, 0.25),
                   "INVITED INTO THE ROOM", 40)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 2, 0.05),
                   "THE ROOM", 24, g.GRAY)


def draw7(d, t_abs):
    set_beat(7, g.local_beat(CLIPS[6], t_abs)[0])
    idx, p = g.local_beat(CLIPS[6], t_abs)
    cx, cy = g.W // 2, g.H // 2 + 90
    c = CLIPS[6]

    if idx == 0:
        halo(d, cx, cy + 40, 280, g.RED, 0.14)
        ap = max(0.0, clamp01((p - 0.15) / 0.2))
        card(d, cx, cy + 40, 360, 190, g.DIM, radius=20, a=ap)
        chart_g(d, cx, cy + 60, 300, 120, g.RED, ap, down=1.0)
        xs = max(0.0, clamp01((p - 0.45) / 0.25))
        g.xmark(d, cx, cy + 40, size=int(70 * xs), color=g.RED, lw=6)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 0, 0.2),
                   "STOP BLAMING THE MARKET", 36)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 0, 0.05),
                   "THE MIRROR", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 0, 0.3),
                   "LOOK AT YOUR OWN PROCESS", 24, g.GRAY)

    elif idx == 1:
        halo(d, cx, cy + 40, 260, g.GRAY, 0.12)
        ap = max(0.0, clamp01((p - 0.15) / 0.2))
        card(d, cx, cy + 40, 300, 190, g.DIM, radius=20, a=ap)
        for i, (dxx, lab, col) in enumerate(((cx - 90, "NUMBERS REALISTIC?", g.GOLD),
                                             (cx - 90, "FOLLOWING UP?", g.RED))):
            pass
        rows = [("NUMBERS REALISTIC?", 0.45, g.GOLD), ("FOLLOWING UP?", 0.65, g.RED)]
        for i, (lab, trig, col) in enumerate(rows):
            ry = cy + 40 + i * 90
            qp = max(0.0, clamp01((p - (trig - 0.1)) / 0.2))
            if qp <= 0.02:
                continue
            g.big_text(d, cx + 35, ry, lab, color=dim_col(g.GRAY, 0.9), px=22)
            g.check(d, cx - 90, ry, size=int(22 * qp), color=col, lw=5)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 1, 0.25),
                   "ARE YOUR NUMBERS REALISTIC?", 32)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 1, 0.05),
                   "THE MIRROR", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 1, 0.5),
                   "ARE YOU FOLLOWING UP?", 24, g.GRAY)

    else:
        halo(d, cx, cy + 40, 300, g.RED, 0.12)
        for dx in (-230, 230):
            ap = max(0.0, clamp01((p - (0.1 + (0 if dx < 0 else 0.15))) / 0.18))
            if ap <= 0.02:
                continue
            card(d, cx + dx, cy + 40, 230, 170, g.DIM, radius=20, a=ap)
        ap1 = clamp01((p - 0.3) / 0.25)
        g.big_text(d, cx - 230, cy - 10, "PEOPLE?", color=dim_col(g.RED, ap1), px=40)
        ap2 = clamp01((p - 0.55) / 0.25)
        g.big_text(d, cx + 230, cy - 10, "RISKS?", color=dim_col(g.GRAY, ap2), px=40)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 2, 0.2),
                   "TALKING TO ENOUGH PEOPLE?", 34)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 2, 0.05),
                   "THE MIRROR", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 2, 0.4),
                   "DO YOU UNDERSTAND THE RISKS?", 24, g.GRAY)


def draw8(d, t_abs):
    set_beat(8, g.local_beat(CLIPS[7], t_abs)[0])
    idx, p = g.local_beat(CLIPS[7], t_abs)
    cx, cy = g.W // 2, g.H // 2 + 90
    c = CLIPS[7]

    if idx == 0:
        halo(d, cx, cy + 40, 320, g.GRAY, 0.10)
        for dx in (-230, 230):
            ap = max(0.0, clamp01((p - (0.1 + (0 if dx < 0 else 0.18))) / 0.18))
            if ap <= 0.02:
                continue
            card(d, cx + dx, cy + 40, 220, 170, g.DIM, radius=20, a=ap)
        ap1 = clamp01((p - 0.35) / 0.25)
        if ap1 > 0.02:
            d.rounded_rectangle([cx - 230 - 44, cy - 12, cx - 230 + 44, cy + 66],
                                radius=18, outline=dim_col(g.WHITE, ap1), width=4)
            d.arc([cx - 230 - 44, cy + 40, cx - 230 + 44, cy + 90], 0, 180,
                  fill=dim_col(g.RED, ap1), width=4)
            g.xmark(d, cx - 230, cy + 20, size=int(40 * ap1), color=g.RED, lw=6)
        ap2 = clamp01((p - 0.55) / 0.25)
        if ap2 > 0.02:
            book_g(d, cx + 230, cy + 10, 1.0, g.GOLD, ap2)
            g.check(d, cx + 230, cy + 60, size=int(30 * ap2), color=g.GOLD, lw=6)
        pop_text(d, cx - 230, cy + 150, t_abs, g.beat_abs(c, 0, 0.3),
                 "JUST CONSUMING", g.RED, 24)
        pop_text(d, cx + 230, cy + 150, t_abs, g.beat_abs(c, 0, 0.6),
                 "REALLY LEARNING", g.GOLD, 24)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 0, 0.25),
                   "LEARNING OR JUST CONSUMING?", 32)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 0, 0.05),
                   "CONSUME OR EXECUTE", 24, g.GRAY)

    elif idx == 1:
        halo(d, cx, cy + 40, 320, g.RED, 0.10)
        ap1 = max(0.0, clamp01((p - 0.15) / 0.2))
        card(d, cx - 230, cy + 40, 220, 170, g.DIM, radius=20, a=ap1)
        if ap1 > 0.02:
            d.rectangle([cx - 230 - 34, cy - 40, cx - 230 + 34, cy + 30],
                        outline=dim_col(g.WHITE, ap1), width=4)
            d.ellipse([cx - 230 - 30, cy + 30, cx - 230 + 30, cy + 110],
                      outline=dim_col(g.WHITE, ap1), width=4)
            g.xmark(d, cx - 230, cy + 20, size=int(30 * ap1), color=g.RED, lw=5)
        ap2 = max(0.0, clamp01((p - 0.5) / 0.25))
        card(d, cx + 230, cy + 40, 220, 170, g.GOLD, radius=20, a=ap2)
        if ap2 > 0.02:
            g.glow_circle(d, cx + 230, cy + 50, 60, g.GOLD, layers=2, alpha=0.3 * ap2)
            d.ellipse([cx + 230 - 34, cy + 50 - 26, cx + 230 - 8, cy + 50 - 6],
                      outline=dim_col(g.GOLD, ap2), width=4)
            d.ellipse([cx + 230 + 8, cy + 50 - 26, cx + 230 + 34, cy + 50 - 6],
                      outline=dim_col(g.GOLD, ap2), width=4)
            d.arc([cx + 230 - 26, cy + 50 + 6, cx + 230 + 26, cy + 50 + 34], 0, 180,
                  fill=dim_col(g.GOLD, ap2), width=4)
        pop_text(d, cx - 230, cy + 150, t_abs, g.beat_abs(c, 1, 0.2),
                 "DOING IT ALONE", g.RED, 24)
        pop_text(d, cx + 230, cy + 150, t_abs, g.beat_abs(c, 1, 0.7),
                 "ASKING FOR HELP", g.GOLD, 24)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 1, 0.3),
                   "TOO PROUD TO ASK FOR HELP?", 34)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 1, 0.05),
                   "CONSUME OR EXECUTE", 24, g.GRAY)

    else:
        halo(d, cx, cy + 40, 300, g.RED, 0.12)
        ap1 = max(0.0, clamp01((p - 0.15) / 0.2))
        card(d, cx - 240, cy + 40, 210, 190, g.DIM, radius=20, a=ap1)
        xs = max(0.0, clamp01((p - 0.45) / 0.2))
        g.xmark(d, cx - 240, cy + 40, size=int(60 * xs), color=g.RED, lw=6)
        pop_text(d, cx - 240, cy + 160, t_abs, g.beat_abs(c, 2, 0.2),
                 "NEW STRATEGY", g.RED, 24)
        ap2 = max(0.0, clamp01((p - 0.25) / 0.3))
        card(d, cx + 220, cy + 40, 210, 190, g.GOLD, radius=20, a=ap2)
        bar_h = int(120 * clamp01((p - 0.5) / 0.35))
        if bar_h > 4:
            d.rectangle([cx + 180, cy + 90 - bar_h, cx + 260, cy + 90],
                        fill=dim_col(g.GOLD, 0.75))
            g.check(d, cx + 220, cy + 30, size=int(26 * clamp01((p - 0.6) / 0.2)),
                    color=g.GOLD, lw=5)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 2, 0.3),
                   "EXECUTE THE BASICS LONG ENOUGH", 34)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 2, 0.1),
                   "CONSUME OR EXECUTE", 24, g.GRAY)


def draw9(d, t_abs):
    set_beat(9, g.local_beat(CLIPS[8], t_abs)[0])
    idx, p = g.local_beat(CLIPS[8], t_abs)
    cx, cy = g.W // 2, g.H // 2 + 90
    c = CLIPS[8]

    if idx == 0:
        halo(d, cx, cy + 30, 260, g.RED, 0.12)
        ap = max(0.0, clamp01((p - 0.1) / 0.2))
        brief_g(d, cx, cy + 30, 1.2, g.WHITE, ap)
        xs = max(0.0, clamp01((p - 0.4) / 0.3))
        g.xmark(d, cx, cy + 30, size=int(80 * xs), color=g.RED, lw=7)
        pop_text(d, cx, cy + 165, t_abs, g.beat_abs(c, 0, 0.2), "JOB", g.RED, 26)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 0, 0.25),
                   "YOUR JOB IS NOT THE ENEMY", 36)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 0, 0.05),
                   "THE REAL ENEMY", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 0, 0.45),
                   "YOUR LACK OF DIRECTION IS", 24, g.GRAY)

    elif idx == 1:
        halo(d, cx, cy + 40, 250, g.RED, 0.14)
        ap = max(0.0, clamp01((p - 0.15) / 0.2))
        clock_g(d, cx, cy + 40, 105, g.WHITE, ap, deg=30)
        d.polygon([(cx - 64, cy + 40), (cx + 64, cy + 40), (cx, cy + 40)],
                  outline=dim_col(g.GOLD, ap), width=5) if False else None
        d.line([cx - 52, cy + 40, cx + 52, cy + 40], fill=dim_col(g.GOLD, ap), width=5)
        fwd = max(0.0, clamp01((p - 0.35) / 0.3))
        g.arrow(d, cx - 40, cy + 40, cx + 40, cy + 40, color=dim_col(g.GOLD, fwd), lw=5) \
            if fwd > 0.05 else None
        xs = max(0.0, clamp01((p - 0.5) / 0.25))
        g.xmark(d, cx + 8, cy + 40, size=int(46 * xs), color=g.RED, lw=6) if xs > 0.05 else None
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 1, 0.25),
                   "LACK OF DIRECTION", 38)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 1, 0.05),
                   "THE REAL ENEMY", 24, g.GRAY)

    else:
        halo(d, cx, cy + 40, 320, g.RED, 0.10)
        for dx in (-230, 230):
            ap = max(0.0, clamp01((p - (0.12 + (0 if dx < 0 else 0.2))) / 0.2))
            if ap <= 0.02:
                continue
            card(d, cx + dx, cy + 40, 220, 170, g.DIM, radius=20, a=ap)
        xs1 = clamp01((p - 0.45) / 0.25)
        g.xmark(d, cx - 230, cy + 40, size=int(48 * xs1), color=g.RED, lw=6) if xs1 > 0.05 else None
        xs2 = clamp01((p - 0.75) / 0.2)
        g.xmark(d, cx + 230, cy + 40, size=int(48 * xs2), color=g.RED, lw=6) if xs2 > 0.05 else None
        pop_text(d, cx - 230, cy + 160, t_abs, g.beat_abs(c, 2, 0.3),
                 "LACK OF CONSISTENCY", g.RED, 24)
        pop_text(d, cx + 230, cy + 160, t_abs, g.beat_abs(c, 2, 0.5),
                 "HABIT OF WAITING", g.RED, 24)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 2, 0.35),
                   "YOUR HABIT OF WAITING IS", 34)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 2, 0.05),
                   "THE REAL ENEMY", 24, g.GRAY)


def draw10(d, t_abs):
    set_beat(10, g.local_beat(CLIPS[9], t_abs)[0])
    idx, p = g.local_beat(CLIPS[9], t_abs)
    cx, cy = g.W // 2, g.H // 2 + 90
    base = cy + 190
    c = CLIPS[9]

    if idx == 0:
        halo(d, cx + 250, base, 220, g.GOLD, 0.16)
        brief_g(d, cx - 250, base - 60, 1.0, g.WHITE)
        g.arrow(d, cx - 140, base - 160, cx + 60, base - 160, color=g.GOLD, lw=7)
        grow = g.spring(p, k=10)
        g.gold_building(d, cx + 250, base, 140, int(150 + grow * 250), 1.0, shadow=True)
        g._coin_pile(d, cx + 250, base + 4, 3, g.GOLD, r=13)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 0, 0.2),
                   "KEEP THE JOB. BUILD THE PLAN.", 36)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 0, 0.05),
                   "THE BREAK", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 0, 0.35),
                   "BUILD SOMETHING MEANINGFUL", 26, g.GRAY)

    elif idx == 1:
        halo(d, cx, cy + 40, 260, g.RED, 0.14)
        ap = max(0.0, clamp01((p - 0.2) / 0.3))
        grow = g.spring(clamp01((p - 0.2) / 0.4), k=9)
        rr = 150 * grow
        if rr > 8:
            d.ellipse([cx - rr, cy + 40 - rr, cx + rr, cy + 40 + rr],
                      outline=dim_col(g.RED, 0.9), width=6)
            g.arrow(d, cx + (rr - 10) * math.cos(math.pi / 4),
                    cy + 40 - (rr - 10) * math.sin(math.pi / 4),
                    cx + rr * math.cos(math.pi / 4),
                    cy + 40 - rr * math.sin(math.pi / 4),
                    color=g.RED, lw=6)
        g.big_text(d, cx - 40, cy + 40, "SAME", color=dim_col(g.WHITE, ap), px=24) if ap > 0.3 else None
        g.big_text(d, cx + 40, cy + 150, "ROUTE", color=dim_col(g.RED, ap), px=24) if ap > 0.5 else None
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 1, 0.45),
                   "SAME LIFE. SAME RESULT.", 40)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 1, 0.05),
                   "THE BREAK", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 1, 0.55),
                   "DON'T EXPECT A DIFFERENT FUTURE", 24, g.GRAY)

    else:
        halo(d, cx, cy + 40, 330, g.RED, 0.10)
        ap = max(0.0, clamp01((p - 0.2) / 0.2))
        card(d, cx - 230, cy + 40, 300, 180, g.DIM, radius=20, a=ap)
        g.big_text(d, cx - 230, cy + 30, "SOMEDAY", color=dim_col(g.GRAY, ap), px=44)
        xs = max(0.0, clamp01((p - 0.5) / 0.3))
        g.xmark(d, cx - 230, cy + 70, size=int(80 * xs), color=g.RED, lw=7)
        g.arrow(d, cx - 40, cy + 60, cx + 90, cy + 60, color=g.GOLD, lw=6)
        bad = max(0.0, clamp01((p - 0.6) / 0.25))
        if bad > 0.02:
            badge(d, cx + 260, cy + 50, "THIS WEEK", g.GOLD, px=28, w=220, h=70, a=bad)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 2, 0.3),
                   "STOP SAYING SOMEDAY", 40)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 2, 0.05),
                   "THE BREAK", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 2, 0.45),
                   "AND START ASKING...", 24, g.GRAY)


def draw11(d, t_abs):
    set_beat(11, g.local_beat(CLIPS[10], t_abs)[0])
    idx, p = g.local_beat(CLIPS[10], t_abs)
    cx, cy = g.W // 2, g.H // 2 + 90
    c = CLIPS[10]

    if idx == 0:
        halo(d, cx, cy + 20, 330, g.GOLD, 0.16)
        ap = max(0.0, clamp01((p - 0.15) / 0.25))
        card(d, cx, cy + 20, 430, 300, g.GOLD, radius=28, a=ap)
        g.big_text(d, cx, cy - 40, "?", color=dim_col(g.GOLD, ap), px=120) if ap > 0.1 else None
        for k in range(7):
            dx = cx - 165 + k * 55
            on = k < int(4 + p * 3)
            d.ellipse([dx - 12, cy + 115, dx + 12, cy + 139],
                      outline=dim_col(g.GOLD if on else g.GRAY, 0.7 if on else 0.4),
                      width=3) if ap > 0.4 else None
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 0, 0.35),
                   "WHAT AM I DOING THIS WEEK", 38)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 0, 0.08),
                   "THE QUESTION", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 0, 0.65),
                   "THAT MAKES ME HARDER TO IGNORE?", 24, g.GOLD)

    elif idx == 1:
        halo(d, cx, cy + 40, 280, g.GOLD, 0.18)
        ap = max(0.0, clamp01((p - 0.1) / 0.25))
        card(d, cx, cy + 40, 400, 250, g.GOLD, radius=24, a=ap)
        ripple(d, cx, cy + 40, max(0.0, t_abs - g.beat_abs(c, 1, 0.3)), 30, g.GOLD)
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 1, 0.25),
                   "THAT ANSWER WILL TELL YOU A LOT", 32)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 1, 0.05),
                   "THE QUESTION", 24, g.GRAY)

    else:
        halo(d, cx, cy + 40, 340, g.GOLD, 0.12)
        quads = [(-300, "MONEY", g.GOLD), (-100, "TIME", g.WHITE),
                 (100, "KNOWLEDGE", g.GRAY), (300, "FEAR", g.RED)]
        for i, (dx, lab, col) in enumerate(quads):
            ap = max(0.0, clamp01((p - (0.12 + i * 0.16)) / 0.16))
            if ap <= 0.02:
                continue
            card(d, cx + dx, cy + 40, 140, 300, col, radius=22, a=ap)
            pp = clamp01((t_abs - g.beat_abs(c, 2, 0.15 + i * 0.15)) * 3)
            g.big_text(d, cx + dx, cy + 40, lab, color=dim_col(col, ap),
                       px=int(20 + 16 * clamp01(pp)))
        slide_fade(d, cx, cy - 360, t_abs, g.beat_abs(c, 2, 0.3),
                   "MONEY. TIME. KNOWLEDGE. FEAR.", 34)
        slide_fade(d, cx, cy - 460, t_abs, g.beat_abs(c, 2, 0.05),
                   "THE QUESTION", 24, g.GRAY)
        slide_fade(d, cx, cy + 430, t_abs, g.beat_abs(c, 2, 0.6),
                   "WHICH ONE IS HOLDING YOU BACK?", 24, g.GRAY)


for _i in range(1, 12):
    REG[_i] = globals()[f"draw{_i}"]


# ============================================================ render pipeline

def bg_scene(d, t_abs):
    for x in range(0, g.W, 88):
        d.line([x, 0, x, g.H], fill=g.BG_LINE, width=1)
    for y in range(0, g.H, 88):
        d.line([0, y, g.W, y], fill=g.BG_LINE, width=1)
    d.line([0, g.H - 90, g.W, g.H - 90], fill=g.DIM, width=2)


def render_frame(cid, t_abs):
    img = g.Image.new("RGB", (g.RW, g.RH), g.BLACK)
    raw = g.ImageDraw.Draw(img)
    d = g.D2(raw)
    bg_scene(d, t_abs)
    REG[cid](d, t_abs)
    clip = g.CLIPS[cid - 1]
    scale, px, py = g.camera_state(clip, t_abs)
    framed = g.apply_camera(img, scale, px, py)
    return g.post_process(g.bloom(framed), frame_idx=round(t_abs * g.FPS))


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
    cx, cy = g.W // 2, g.H // 2 - 40
    for f in range(2 * g.FPS):
        t = f / g.FPS
        img = g.Image.new("RGB", (g.RW, g.RH), g.BLACK)
        raw = g.ImageDraw.Draw(img)
        d = g.D2(raw)
        bg_scene(d, t)
        fl = max(0.0, 1.0 - t * 4.0)
        if fl > 0.05:
            g.glow_circle(d, cx, cy + 40, 620, g.GOLD, alpha=fl * 0.7)
        card(d, cx - 235, cy, 110, 300, g.GOLD, radius=24, a=1.0)
        card(d, cx + 235, cy, 110, 300, g.WHITE, radius=24, a=1.0)
        y0 = cy - 106 + t * 70
        g.glow_circle(d, cx - 235, cy, 120, g.GOLD, layers=2, alpha=0.35)
        g.coin(d, cx - 235, cy, r=16, color=g.GOLD, rot=t * 2, shadow=True)
        g.big_text(d, cx - 235, cy + 200, "MONEY", color=g.GOLD, px=26)
        g.big_text(d, cx + 235, cy - 60, "SO WHAT?", color=g.WHITE, px=22)
        a = elastic(clamp01((t - 0.9) / 0.5))
        fade_out = 1 - ease_out(clamp01((t - 1.6) / 0.4))
        a *= fade_out
        g.big_text(d, cx, cy + 300, "HARDER TO IGNORE", px=46,
                   color=(min(255, int(255 * a)), min(255, int(220 * a)), min(255, int(60 * a))))
        punch = 0.07 * math.exp(-(t - 1.05) / 0.2) if t >= 1.05 else 0.0
        cam_scale = 1.0 + 0.03 * g.ease(clamp01(t / 2.0)) + punch
        framed = g.apply_camera(img, cam_scale, 0.0, 0.0)
        g.post_process(g.bloom(framed), frame_idx=f).save(dirpath / f"frame_{f:04d}.png")


def create_outro_clip():
    dirpath = g.FRAMES_DIR / "outro"
    if dirpath.exists():
        shutil.rmtree(dirpath)
    dirpath.mkdir(parents=True, exist_ok=True)
    cx, cy = g.W // 2, g.H // 2 + 40
    for f in range(2 * g.FPS):
        t = f / g.FPS
        img = g.Image.new("RGB", (g.RW, g.RH), g.BLACK)
        raw = g.ImageDraw.Draw(img)
        d = g.D2(raw)
        bg_scene(d, t)
        av = clamp01(t / 0.6)
        g.glow_circle(d, cx, cy, 300, g.GOLD, layers=2, alpha=0.35 * av)
        for k in range(8):
            ang = k * math.tau / 8 + t * 2
            g.coin(d, cx + math.cos(ang) * 240, cy + math.sin(ang) * 200, r=12,
                   color=g.GOLD, rot=t + k, shadow=True) if av > 0.3 else None
        a2 = elastic(clamp01((t - 0.5) / 0.45))
        fade_out = 1 - ease_out(clamp01((t - 1.5) / 0.5))
        a2 *= fade_out
        if a2 > 0.1:
            g.big_text(d, cx, cy + 80, "MAKE YOURSELF", px=40, color=dim_col(g.WHITE, a2))
            g.big_text(d, cx, cy + 170, "HARDER TO IGNORE", px=44,
                       color=dim_col(g.GOLD, a2))
        punch = 0.08 * math.exp(-(t - 0.5) / 0.2) if t >= 0.5 else 0.0
        cam_scale = 1.0 + 0.03 * g.ease(clamp01(t / 2.0)) + punch
        framed = g.apply_camera(img, cam_scale, 0.0, 0.0)
        g.post_process(g.bloom(framed), frame_idx=f).save(dirpath / f"frame_{f:04d}.png")


def ease_out(t):
    return g.ease_out(t)


def elastic(t):
    return g.elastic(t)


# ============================================================ sfx

def sfx_events(clip):
    cid = clip["id"]
    beats = g.clip_beats(clip)
    evs = []
    if not beats:
        return evs
    if cid == 1:
        evs += [(beats[0][0], "whoosh", 0.5), (max(0, beats[0][1] - 0.2), "ding", 0.5)]
        evs += [(beats[1][0], "whoosh", 0.5), (beats[1][0] + 0.3, "tick", 0.4)]
        for k in range(4):
            evs.append((beats[2][0] + 0.25 + 0.35 * k, "pop", 0.5))
    elif cid == 2:
        evs += [(beats[0][0], "tick", 0.5), (max(0, beats[0][1] - 0.2), "chime", 0.5)]
        evs += [(beats[1][0], "pop", 0.5), (beats[1][0] + 0.3, "clink", 0.5)]
        for k in range(2):
            evs.append((beats[2][0] + 0.25 + 0.3 * k, "pop", 0.5))
    elif cid == 3:
        evs += [(beats[0][0], "tick", 0.5)]
        for k in range(3):
            evs.append((beats[0][0] + 0.4 + 0.5 * k, "tick", 0.4))
        evs += [(beats[1][0], "shimmer", 0.5)]
        for k in range(3):
            evs.append((beats[1][0] + 0.4 + 0.5 * k, "pop", 0.45))
        evs += [(beats[2][0], "slam", 0.5), (beats[2][1] - 0.25, "ding", 0.5)]
    elif cid == 4:
        evs += [(beats[0][0] + 0.2, "slam", 0.5), (beats[0][0] + 0.55, "stamp", 0.5)]
        evs += [(beats[1][0], "pop", 0.5), (beats[1][0] + 0.4, "pop", 0.45)]
        evs += [(beats[2][0], "whoosh", 0.5), (beats[2][1] - 0.2, "chime", 0.6)]
    elif cid == 5:
        evs += [(beats[0][0], "pop", 0.5), (beats[0][1] - 0.2, "clink", 0.6)]
        for k in range(3):
            evs.append((beats[1][0] + 0.3 + 0.4 * k, "pop", 0.5))
        evs += [(beats[2][0], "rise", 0.5), (beats[2][1] - 0.2, "chime", 0.6)]
    elif cid == 6:
        evs += [(beats[0][0], "slam", 0.5), (beats[0][1] - 0.2, "crumble", 0.4)]
        evs += [(beats[1][0], "rise", 0.5), (beats[1][1] - 0.15, "shimmer", 0.5)]
        evs += [(beats[2][0], "whoosh", 0.6), (beats[2][1] - 0.1, "chime", 0.7)]
    elif cid == 7:
        evs += [(beats[0][0], "slam", 0.5), (beats[0][1] - 0.2, "crumble", 0.45)]
        evs += [(beats[1][0], "tick", 0.5), (beats[1][0] + 0.4, "tick", 0.45),
                (max(0, beats[1][1] - 0.2), "chime", 0.5)]
        evs += [(beats[2][0], "pop", 0.5), (beats[2][0] + 0.4, "pop", 0.5)]
    elif cid == 8:
        evs += [(beats[0][0], "stamp", 0.5), (beats[0][1] - 0.2, "whoosh", 0.45)]
        evs += [(beats[1][0], "rise", 0.5), (beats[1][1] - 0.2, "chime", 0.5)]
        evs += [(beats[2][0], "slam", 0.5), (beats[2][1] - 0.2, "ding", 0.5)]
    elif cid == 9:
        evs += [(beats[0][0], "stamp", 0.55), (beats[0][1] - 0.2, "crumble", 0.4)]
        evs += [(beats[1][0], "slam", 0.5), (beats[1][1] - 0.2, "shimmer", 0.5)]
        evs += [(beats[2][0], "pop", 0.5)]
        for k in range(2):
            evs.append((beats[2][0] + 0.5 + 0.45 * k, "pop", 0.5))
    elif cid == 10:
        evs += [(beats[0][0], "whoosh", 0.5), (beats[0][1] - 0.2, "chime", 0.5)]
        evs += [(beats[1][0], "slam", 0.5), (beats[1][1] - 0.2, "crumble", 0.45)]
        evs += [(beats[2][0], "stamp", 0.55), (beats[2][1] - 0.15, "ding", 0.6)]
    else:
        evs += [(beats[0][0], "chime", 0.6), (beats[0][1] - 0.15, "shimmer", 0.5)]
        evs += [(beats[1][0], "rise", 0.5), (beats[1][1] - 0.15, "chime", 0.6)]
        for k in range(4):
            evs.append((beats[2][0] + 0.4 + 0.45 * k, "pop", 0.5))
    evs = [(max(0.0, t), n, gl) for t, n, gl in evs]
    return evs


# ============================================================ pipeline

async def main():
    print("=" * 60)
    print("Stickman Video Generator - Harder To Ignore (male voice)")
    print("=" * 60)
    if "--audit" in sys.argv:
        print("\n[layout] collision audit (33 beats)")
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