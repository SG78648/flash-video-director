"""desk_rich.py - richer pages for the Desk, Board and Mint styles.

Why it exists. The Desk family drew almost every sentence the same way, one taped print or one icon card and big type under it, on 40 clips of
footage, so a reel looked the same from the first beat to the last. This module adds three things and nothing else changes.
  1. Page layouts. A sentence that is only words is no longer always "card + type". It is rotated through full screen footage with type over it,
     a footage window with a sticker on its corner, a phone with the footage on it, two overlapping prints, a cluster of drawn icons, one giant
     number, type with a hand drawn underline and circle, and a handwritten sticky note. The choice is made once for the whole story (never the
     same layout twice in a row, footage layouts are limited to two in a row, a clip is not used twice while an unused one exists).
  2. Elements. Comparison bars ("from 11 to 1", "$550 against $850"), a percent ring, a duration meter ("18 months", "8 days"), and hand drawn
     marks (scribbled underline, circle, curved arrow, stars) that animate in as the words are spoken.
  3. Footage. A beat gets footage from what it says (words first, then the pictures it names), not only from a [broll tag] in the script. A tag
     still wins. The library is bigger now (broll_pack.py) and new clips are cut at 720 x 1280.
style_desk.py binds itself here (bind) and calls page() for a beat that would have been plain type, accents() on card pages and object_spec() for the new
elements. Everything reads style_desk's colours at the moment it draws, so the Board and Mint palettes apply. Set ENABLED = False to get the old pages.
"""
import hashlib
import math
import random
import re

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

import broll
import story_icons
import story_scenes

D = None
S = 2
ENABLED = True


def bind(mod):
    global D, S
    D = mod
    S = mod.SS


def c01(v):
    return max(0.0, min(1.0, v))


def eo(v):
    v = c01(v)
    return 1 - (1 - v) ** 3


def eio(v):
    v = c01(v)
    return v * v * (3 - 2 * v)


def spr(a):
    return D.spring(c01(a), 12.0)


# ------------------------------------------------------------------ fonts and marks
_HF = {}


def hand(px):
    """A handwriting face (Ink Free, else Segoe Print) for notes and scribbles."""
    px = max(10, int(round(px)))
    if px not in _HF:
        f = None
        for fn in ("inkfree.ttf", "segoepr.ttf", "comic.ttf"):
            try:
                f = ImageFont.truetype(fn, px * S)
                break
            except Exception:
                pass
        _HF[px] = f or D.F("ital", px)
    return _HF[px]


def _seg_len(pts):
    return [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]


def _upto(pts, frac):
    """The first `frac` of a polyline (by length)."""
    if frac >= 0.999:
        return pts
    ls = _seg_len(pts)
    want = sum(ls) * frac
    out, acc = [pts[0]], 0.0
    for i, l in enumerate(ls):
        if acc + l >= want:
            k = (want - acc) / l if l else 0
            out.append((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * k, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * k))
            return out
        acc += l
        out.append(pts[i + 1])
    return out


def stroke(img, pts, frac, color, w):
    """A hand drawn stroke, revealed from its start up to `frac`, with round ends."""
    if frac <= 0.01 or len(pts) < 2:
        return
    p = _upto(pts, frac)
    if len(p) < 2:
        return
    d = ImageDraw.Draw(img)
    q = [(x * S, y * S) for x, y in p]
    d.line(q, fill=tuple(color), width=max(2, int(w * S)), joint="curve")
    for x, y in (q[0], q[-1]):
        r = w * S / 2
        d.ellipse([x - r, y - r, x + r, y + r], fill=tuple(color))


def _wob(pts, seed, amp):
    rnd = random.Random(seed)
    return [(x + rnd.uniform(-amp, amp), y + rnd.uniform(-amp, amp)) for x, y in pts]


def scribble_underline(img, x0, x1, y, t, t0, color, w=9, seed=1):
    a = eo((t - t0) / 0.42)
    if a <= 0.01:
        return
    n = 10
    one = _wob([(x0 + (x1 - x0) * i / n, y + 3 * math.sin(i * 1.3)) for i in range(n + 1)], seed, 3.0)
    two = _wob([(x1 - (x1 - x0) * 0.04 - (x1 - x0) * 0.9 * i / n, y + 14 + 3 * math.sin(i * 1.7)) for i in range(n + 1)], seed + 7, 3.0)
    path = one + two
    stroke(img, path, a, color, w)


def scribble_circle(img, cx, cy, rx, ry, t, t0, color, w=8, seed=2):
    a = eo((t - t0) / 0.5)
    if a <= 0.01:
        return
    rnd = random.Random(seed)
    ph = rnd.uniform(0, 6.28)
    pts = []
    n = 46
    for i in range(n + 1):
        th = -0.25 * math.pi + (2.25 * math.pi) * i / n
        k = 1 + 0.035 * math.sin(3 * th + ph) + 0.05 * (i / n)
        pts.append((cx + rx * k * math.cos(th), cy + ry * k * math.sin(th)))
    stroke(img, pts, a, color, w)


def curved_arrow(img, p0, p1, bend, t, t0, color, w=8):
    a = eo((t - t0) / 0.5)
    if a <= 0.01:
        return
    mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    ln = math.hypot(dx, dy) or 1
    cx, cy = mx - dy / ln * bend, my + dx / ln * bend
    pts = [((1 - u) ** 2 * p0[0] + 2 * (1 - u) * u * cx + u * u * p1[0], (1 - u) ** 2 * p0[1] + 2 * (1 - u) * u * cy + u * u * p1[1]) for u in [i / 24 for i in range(25)]]
    stroke(img, pts, a, color, w)
    if a > 0.92:
        ex, ey = pts[-1]
        vx, vy = pts[-1][0] - pts[-4][0], pts[-1][1] - pts[-4][1]
        vl = math.hypot(vx, vy) or 1
        vx, vy = vx / vl, vy / vl
        for s in (-1, 1):
            hx, hy = ex - vx * 30 + s * (-vy) * 18, ey - vy * 30 + s * vx * 18
            stroke(img, [(ex, ey), (hx, hy)], 1.0, color, w)


def star(img, cx, cy, r, t, t0, color, rot=0.0, points=4):
    a = c01((t - t0) / 0.35)
    if a <= 0.01:
        return
    sc = spr(a) * (1 + 0.05 * math.sin(t * 3 + cx))
    pts = []
    for i in range(points * 2):
        rr = r * sc * (1.0 if i % 2 == 0 else 0.34)
        th = rot + math.pi * i / points - math.pi / 2
        pts.append(((cx + rr * math.cos(th)) * S, (cy + rr * math.sin(th)) * S))
    ImageDraw.Draw(img).polygon(pts, fill=tuple(color))


def accents(img, t, t0, seed, zones=None, n=3):
    """A few small hand drawn marks (stars, squiggles, arrows, plus signs) in the free corners of a page, popping in after the page lands."""
    D_ = D
    zones = zones or [(40, 150, 340, 270), (740, 150, 1040, 270)]
    rnd = random.Random(seed)
    col = D_.ACCENT
    soft = D_.mix(D_.ACCENT, D_.INK, 0.45)
    for i in range(n):
        z = zones[i % len(zones)]
        x, y = rnd.uniform(z[0] + 40, z[2] - 40), rnd.uniform(z[1] + 30, z[3] - 30)
        kind = rnd.choice(("star", "star", "squiggle", "plus", "dots", "arc"))
        ts = t0 + 0.25 + 0.14 * i
        if kind == "star":
            star(img, x, y, rnd.uniform(26, 44), t, ts, col, rot=rnd.uniform(0, 1.5))
        elif kind == "squiggle":
            a = eo((t - ts) / 0.4)
            pts = [(x - 60 + 15 * i2, y + 12 * math.sin(i2 * 1.9 + rnd.uniform(0, 1))) for i2 in range(9)]
            stroke(img, pts, a, soft, 7)
        elif kind == "plus":
            a = c01((t - ts) / 0.3)
            if a > 0.02:
                r = 20 * spr(a)
                stroke(img, [(x - r, y), (x + r, y)], 1.0, col, 7)
                stroke(img, [(x, y - r), (x, y + r)], 1.0, col, 7)
        elif kind == "dots":
            a = c01((t - ts) / 0.3)
            for k in range(3):
                if a > 0.02:
                    r = 8 * spr(a)
                    ImageDraw.Draw(img).ellipse([(x + k * 26 - r) * S, (y - r) * S, (x + k * 26 + r) * S, (y + r) * S], fill=tuple(soft))
        else:
            scribble_circle(img, x, y, 34, 26, t, ts, soft, w=6, seed=int(x))


# ------------------------------------------------------------------ footage
_GR = {}


def _grad(w, h, top, bottom, y0, y1):
    """An L mask w x h (page units x S): `top` alpha above y0, ramping to `bottom` at y1 and below."""
    key = (w, h, top, bottom, y0, y1)
    if key not in _GR:
        ys = np.arange(h * S, dtype=np.float32)
        u = np.clip((ys - y0 * S) / max(1.0, (y1 - y0) * S), 0, 1)
        col = (top + (bottom - top) * u * u * (3 - 2 * u))
        arr = np.repeat(col[:, None], w * S, axis=1).astype(np.uint8)
        _GR[key] = Image.fromarray(arr, "L")
    return _GR[key]


_SOLID = {}


def solid(size, color):
    """A cached flat RGB picture (pasting a flat colour through a mask is how every shade on footage is made)."""
    k = (size, tuple(color))
    if k not in _SOLID:
        _SOLID[k] = Image.new("RGB", size, tuple(color))
    return _SOLID[k]


def shade(img, mask):
    img.paste(solid(img.size, (8, 8, 10)), (0, 0), mask)


def _combo(w, h, parts):
    """Several shading masks as one (the strongest of them at every pixel), cached."""
    key = ("combo", w, h, tuple(parts))
    if key not in _GR:
        masks = [(_grad(w, h, *a[1:]) if a[0] == "g" else _band(w, h, *a[1:])) for a in parts]
        out = masks[0]
        for m in masks[1:]:
            out = ImageChops.lighter(out, m)
        _GR[key] = out
    return _GR[key]


def _band(w, h, y0, y1, alpha, feather=160):
    """An L mask w x h: `alpha` between y0 and y1 (page units), fading to 0 over `feather` above and below. A dark band behind a block of text."""
    key = ("band", w, h, int(y0), int(y1), alpha, feather)
    if key not in _GR:
        ys = np.arange(h * S, dtype=np.float32) / S
        up = np.clip((ys - (y0 - feather)) / feather, 0, 1)
        dn = np.clip(((y1 + feather) - ys) / feather, 0, 1)
        col = alpha * (up * up * (3 - 2 * up)) * (dn * dn * (3 - 2 * dn))
        _GR[key] = Image.fromarray(np.repeat(col[:, None], w * S, axis=1).astype(np.uint8), "L")
    return _GR[key]


def cover(fr, w, h, z=1.0, px=0.0, py=0.0, tone=None):
    """The part of footage frame `fr` that fills w x h (page units) at zoom z, panned by px, py in [-1, 1]; returned at S x resolution.
    `tone` (a function) is applied to the cropped piece before it is enlarged, which is many times cheaper than toning the big picture."""
    bw, bh = fr.size
    ar = w / float(h)
    cw = min(bw, bh * ar) / z
    ch = cw / ar
    x0 = (bw - cw) / 2 * (1 + px)
    y0 = (bh - ch) / 2 * (1 + py)
    piece = fr.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch)))
    if tone:
        piece = tone(piece)
    return piece.resize((int(w * S), int(h * S)), Image.BILINEAR)


def grade(im, warm=0.10, sat=0.86):
    im = ImageEnhance.Color(im).enhance(sat)
    return Image.blend(im, Image.new("RGB", im.size, D.PHOTO_TINT), warm)


def motion(mode, u):
    """(zoom, pan x, pan y) of the slow camera move on a clip, u from 0 to 1 over the beat."""
    if mode == "in":
        return 1.05 + 0.12 * u, 0.0, 0.0
    if mode == "out":
        return 1.19 - 0.12 * u, 0.0, 0.0
    if mode == "left":
        return 1.14, 0.7 - 1.4 * u, 0.0
    if mode == "right":
        return 1.14, -0.7 + 1.4 * u, 0.0
    if mode == "up":
        return 1.14, 0.0, 0.6 - 1.2 * u
    return 1.10, 0.0, 0.0


MODES = ("in", "left", "out", "right", "up")


def footage_img(clip, t, s0, s1, w, h, mode, off=0.0):
    fr = broll.frame(clip, max(0.0, t - s0) + off)
    if fr is None:
        return None
    u = c01((t - s0) / max(2.0, s1 - s0))
    z, px, py = motion(mode, u)
    return cover(fr, w, h, z, px, py, tone=grade)


def rounded(im, r):
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, im.width - 1, im.height - 1], radius=int(r * S), fill=255)
    out = im.convert("RGBA")
    out.putalpha(m)
    return out


# ------------------------------------------------------------------ type (the sentence, big), with word positions back
def _shadow_light(img, x, y, s, f, px, anchor, a):
    """A soft black shadow under light text on footage."""
    l, t0, r, b = [int(v) for v in f.getbbox(s, anchor=anchor)]
    blur = max(2, int(px * 0.07 * S))
    pad = blur * 3 + int(px * 0.1 * S)
    w, h = r - l + 2 * pad, b - t0 + 2 * pad
    lay = Image.new("L", (w, h), 0)
    ImageDraw.Draw(lay).text((pad - l, pad - t0), s, font=f, fill=255, anchor=anchor)
    m = lay.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * 0.85 * a))
    img.paste(Image.new("RGB", (w, h), (0, 0, 0)), (int(x * S) + l - pad, int(y * S) + t0 - pad + int(px * 0.05 * S)), m)


def rtype(img, text, tw_of, t, box, pxmax=150, dark=False, accent_tail=True):
    """The kinetic sentence, a word at a time (heavy caps first, italic accent for the tail). Returns [(i, x, y_base, w, px, heavy)] of every word."""
    x0, y0, x1, y1 = box
    maxw = x1 - x0
    k, toks = D.split_emph(text)
    px = pxmax
    while True:
        lines, cur, curw = [], [], 0.0
        for i, w in enumerate(toks):
            heavy = i < k
            s = w.upper() if heavy else (w[:1].upper() + w[1:] if i == 0 else w)
            f = D.F("heavy", px * 1.06) if heavy else D.F("ital", px * 1.16)
            ww = D.width(s, f)
            sp = D.width(" ", f)
            if cur and curw + sp + ww > maxw:
                lines.append(cur)
                cur, curw = [], 0.0
            cur.append((i, s, heavy, f, ww))
            curw += (sp if len(cur) > 1 else 0) + ww
        if cur:
            lines.append(cur)
        if len(lines) * px * 1.12 <= (y1 - y0) * 0.92 or px <= 52:
            break
        px -= 6
    lh = px * 1.12
    top = (y0 + y1) / 2 - len(lines) * lh / 2
    d = ImageDraw.Draw(img)
    cx = (x0 + x1) / 2
    boxes = []
    light = D.LIGHT
    for li, ln in enumerate(lines):
        sp = D.width(" ", ln[0][3])
        total = sum(e[4] for e in ln) + sp * (len(ln) - 1)
        xx = cx - total / 2
        by = top + li * lh + px * 0.86
        for i, s, heavy, f, ww in ln:
            a = eo((t - tw_of(i)) / 0.17)
            boxes.append((i, xx, by, ww, px, heavy))
            if a > 0.02:
                bad = D.word_color(s) == D.RED
                if dark:
                    col = D.RED if bad else (light if heavy else D.mix(D.ACCENT, (255, 255, 255), 0.75))
                    _shadow_light(img, xx, by + (1 - a) * 26, s, f, px, "ls", a)
                else:
                    col = D.RED if bad else (D.BONE if heavy else D.ACCENT)
                    D.shadow_text(img, xx, by + (1 - a) * 26, s, f, px, anchor="ls", strength=a)
                d.text((xx * S, (by + (1 - a) * 26) * S), s, font=f, fill=D.mix(col, D.INK if not dark else (0, 0, 0), a), anchor="ls")
            xx += ww + sp
    if accent_tail and boxes and not boxes[-1][5] and len(toks) > 1:
        i, xl, bl, wl, pxl, _h = boxes[-1]
        a = eo((t - tw_of(i) - 0.1) / 0.35)
        d.rectangle([xl * S, (bl + px * 0.16) * S, (xl + wl * a) * S, (bl + px * 0.16 + 5) * S], fill=tuple(D.ACCENT))
    return boxes


# ------------------------------------------------------------------ the plan: which layout and which footage for every beat of the story
_PLAN = {}
_USED = set()
_HOOK = {}
_CUR = None

# what a sentence is about (by its words) -> footage tags, tried before the pictures it names
BY_WORD = [
    (r"\b(kitchens?|restaurants?|chefs?|cook\w*|menus?|food)\b", ["chef", "kitchen", "cooking"]),
    (r"\bkeys?\b|\bdoors?\b|\block(s|ed)?\b", ["keys", "door", "door light"]),
    (r"\broofs?\b|\bboilers?\b|\bmold\b|\brepair\w*|\bleak\w*|\bplumb\w*|\bmaintenance\b", ["roofer", "plumbing", "repairs"]),
    (r"\bwins?\b|\bproofs?\b|\bprove[sd]?\b|\bprogress\b|\bmomentum\b|\bachiev\w*|\bconfiden\w*|\bbeliev\w*|\beffort\b", ["climb", "sunrise", "run"]),
    (r"\b(think\w*|thought\w*|doubt\w*|overthink\w*|wonder\w*|decid\w*|choice)\b", ["thinking", "burnout"]),
    (r"\bpaint\w*|\brenovat\w*|\bremodel\w*|\bupgrad\w*", ["painting", "construction"]),
    (r"\bconstruction\b|\bcrews?\b|\bcontractors?\b|\bjob ?sites?\b", ["construction", "repairs"]),
    (r"\b(tenants?|landlords?|leases?|residents?|renters?)\b", ["landlord", "lease", "keys"]),
    (r"\b(cash|money|dollars?|paychecks?|salary|income)\b", ["cash", "coins", "bills"]),
    (r"\b(bills?|invoices?|expenses?|costs?)\b", ["bills", "invoice"]),
    (r"\b(loans?|banks?|lenders?|debt|mortgages?|interest|financ\w*)\b", ["card", "atm", "negotiate"]),
    (r"\b(stress\w*|burnout|exhaust\w*|overwhelm\w*|pressure|anxious|worr\w*|weekends?)\b", ["burnout", "tired", "rain window"]),
    (r"\b(tired|lazy|discourag\w*|stuck|give up|procrastinat\w*)\b", ["tired", "burnout", "rain window"]),
    (r"\b(hospitals?|heart attack|doctors?|health)\b", ["doctor", "heartbeat", "hospital"]),
    (r"\b(family|wife|husband|kids?|children|home)\b", ["family", "kids"]),
    (r"\b(commute|9 to 5|nine to five|boss|office|jobs?|employees?)\b", ["commute", "office", "tired"]),
    (r"\b(start\w*|begin\w*|moving|momentum)\b|\bfirst (step|move)\b", ["run", "climb", "sunrise"]),
    (r"\b(wait\w*|clock|time|years?|months?|late|deadline)\b", ["alarm", "clock"]),
    (r"\bwalk(ed)? away\b|\bpass(ed)? on\b|\b(leave|leaves|left|quit)\b", ["crowd walk", "walk alone", "door light"]),
    (r"\b(phones?|texts?|calls?|called|dms?)\b", ["phone call", "scrolling"]),
    (r"\b(emails?|inbox|decks?|slides?)\b", ["email", "laptop work"]),
    (r"\b(meetings?|partners?|investors?|operators?|teams?)\b", ["meeting", "negotiate", "video call"]),
    (r"\b(deals?|contracts?|signed?|offers?|negotiat\w*)\b", ["contract", "negotiate", "lease"]),
    (r"\b(apartments?|buildings?|units?|propert(y|ies)|multifamily)\b", ["apartment", "residential aerial", "hallway"]),
    (r"\b(neighborhoods?|streets?|houses?)\b", ["neighborhood", "residential aerial", "keys"]),
    (r"\bmobile homes?\b|\bparks?\b|\blots?\b", ["mobile home", "residential aerial"]),
    (r"\b(storm\w*|risks?|danger\w*|collapse\w*|crash\w*|lose|loses|lost|fail\w*)\b", ["storm", "rain window", "collapse"]),
    (r"\b(calm|peace\w*|quiet|freedom|free)\b", ["calm", "leisure", "sunrise"]),
    (r"\b(grow\w*|raise[sd]?|increase[sd]?|profits?|wealth\w*|rich)\b", ["chart", "climb", "stairs"]),
    (r"\b(learn\w*|study|books?|notes?|plan(ning)?|whiteboard|numbers?|math|spreadsheets?|underwrit\w*)\b", ["notes", "whiteboard", "laptop work"]),
    (r"\b(travel\w*|trips?|vacations?)\b", ["travel", "leisure"]),
    (r"\b(gym|workouts?|exercise|fitness)\b", ["gym", "run"]),
]


def _curated():
    return broll.curated()


def _have(tag):
    return [i for i, tags in _curated().items() if tag in tags and (broll.FRAMES / i / "00000.jpg").exists()]


def tags_for(cid, idx, f_):
    out = []
    low = f_["text"].lower()
    for rx, tags in BY_WORD:                     # what the sentence says comes first (the script's [broll] tags were written for a library of 42 clips)
        if re.search(rx, low):
            out += tags
    out += [q for q in (f_.get("broll") or []) if q and q.lower() != "none"]
    try:
        out += broll.queries_for(D.story(), cid, idx)
    except Exception:
        pass
    seen, res = set(), []
    for q in out:
        if q not in seen:
            seen.add(q)
            res.append(q)
    return res


def take_clips(tags, n, rnd):
    """Up to n distinct curated clips for the tags, unused ones first (the same clip is not reused while another one exists)."""
    got = []
    for tag in tags:
        ids = _have(tag)
        rnd.shuffle(ids)
        for cid in ids:
            if cid not in _USED and cid not in got:
                got.append(cid)
                break
        if len(got) >= n:
            break
    if len(got) < n:
        for tag in tags:
            for cid in _have(tag):
                if cid not in got:
                    got.append(cid)
                    break
            if len(got) >= n:
                break
    for cid in got:
        _USED.add(cid)
    return got[:n]


HERO = re.compile(r"(\$\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:million|billion|thousand|k|m)\b)?|\b\d+(?:\.\d+)?\s?(?:%|percent)|\b\d[\d,]*\s?(?:unit|units|doors|days?|months?|years?|weeks?|deals?|people|offers?|videos?|hours?)\b)", re.I)


def hero_of(text):
    """The number a beat is about ($550, 89 percent, 128 units), None when there is none. A span of time counts only when time is passing ('two years later')."""
    for m in HERO.finditer(text):
        h = m.group(1)
        if re.search(r"(years?|months?|weeks?|days?|hours?)$", h, re.I) and not TIME_CUE.search(text):
            continue
        return h
    return None


def punchy(text):
    n = len(text.split())
    return n <= 15 and bool(re.search(r"\b(never|rule|always|only|isn't|doesn't|don't|not|if|nobody|everyone|stop|best|worst|truth|lie|lying)\b", text.lower()))


def _seed(cid, idx):
    return int(hashlib.md5(("%s|%s|%s" % (D.projects.active(), cid, idx)).encode()).hexdigest()[:8], 16)


FOOT_VARIANTS = ("full", "window", "device", "collage", "print")
FREE_VARIANTS = ("cluster", "bigword", "annot", "note", "card")


def plan_all():
    """Choose the layout and the footage of every plain beat, in story order, once."""
    global _CUR
    st = D.story()
    key = (id(st), D.projects.active(), _forced())
    if _CUR == key:
        return
    _PLAN.clear()
    _USED.clear()
    _CUR = key
    prev, run, uses = None, 0, {}
    _HOOK.clear()
    try:
        hf = {"text": st.get("hook", ""), "broll": st.get("hook_broll") or []}
        hr = random.Random(_seed(0, 0))
        hc = take_clips(tags_for(0, 0, hf), 1, hr) if D.FOOTAGE else []
        if hc:
            _HOOK.update(clip=hc[0], mode=hr.choice(MODES))
    except Exception:
        pass
    order = [(int(c), i) for c in sorted(st["feats"], key=int) for i in range(len(st["feats"][str(c)]))]
    for cid, idx in order:
        f_ = st["feats"][str(cid)][idx]
        pl = D.plan_beat(cid, idx)
        if pl["route"] != "type":
            prev, run = "other", 0
            continue
        rnd = random.Random(_seed(cid, idx))
        tags = tags_for(cid, idx, f_)
        have_foot = bool(D.FOOTAGE) and any(_have(t) for t in tags)
        hero = hero_of(f_["text"])
        noun = D.noun_of(f_["text"])
        cand = {}
        if have_foot:
            cand.update({"full": 3.0, "window": 3.0, "device": 2.2, "collage": 2.0, "print": 1.2})
        cand.update({"annot": 1.6, "card": 0.7})
        if hero:
            cand["bigword"] = 3.2
        if noun or len(story_scenes.concrete(f_["text"])) >= 1:
            cand["cluster"] = 1.8
        if punchy(f_["text"]) or f_["kind"] == "quote":
            cand["note"] = 3.0
        nwords_ = len(f_["text"].split())
        if nwords_ > 16:                                  # a long sentence on type alone is a wall of text, give it a picture
            cand.pop("annot", None)
            if nwords_ > 20:
                cand.pop("note", None)
        for v in list(cand):
            w = cand[v] / (1.0 + 0.9 * uses.get(v, 0))
            if v == prev:
                w = 0.0
            if v in FOOT_VARIANTS and run >= 2:
                w *= 0.1 if nwords_ <= 16 else 0.6
            cand[v] = w
        if sum(cand.values()) <= 0:
            cand = {"annot": 1.0}
        v = rnd.choices(list(cand), weights=list(cand.values()))[0]
        clips = []
        if v in FOOT_VARIANTS:
            clips = take_clips(tags, 2 if v == "collage" else 1, rnd)
            if v == "collage" and len(clips) < 2:
                v = "window"
            if not clips:
                v = "annot"
        uses[v] = uses.get(v, 0) + 1
        run = run + 1 if v in FOOT_VARIANTS else 0
        prev = v
        _PLAN[(cid, idx)] = {"variant": v, "clips": clips, "mode": rnd.choice(MODES), "hero": hero, "seed": _seed(cid, idx)}
        forced = _forced()
        if forced:                                                # a test aid, see _forced()
            fv = forced
            need = 2 if fv == "collage" else 1 if fv in FOOT_VARIANTS else 0
            cl = take_clips(tags, need, rnd) if need else []
            if len(cl) >= need and (fv != "bigword" or hero):
                _PLAN[(cid, idx)].update(variant=fv, clips=cl)


def _forced():
    """studio_data/rich_force.json = {"variant": "window"} makes every plain beat use that layout (to look at one layout at a time). Absent in normal use."""
    try:
        import json
        import projects
        return json.loads((projects.DATA_DIR / "rich_force.json").read_text(encoding="utf-8")).get("variant")
    except Exception:
        return None


def variant_of(cid, idx):
    try:
        plan_all()
    except Exception:
        return None
    return _PLAN.get((cid, idx))


# ------------------------------------------------------------------ the layouts
def _foot_card(clip, t, s0, s1, w, h, mode, r=34, border=0, tape=False, off=0.0):
    """A white card carrying a footage picture inside a border (a window, or a print when border and tape are set)."""
    im = footage_img(clip, t, s0, s1, w - 2 * border, h - 2 * border, mode, off)
    if im is None:
        return None
    c = D.Card(w, h, r=r)
    c.im.paste(rounded(im, max(8, r - border)), (border * S, border * S), rounded(im, max(8, r - border)))
    if tape:
        tp = Image.new("RGBA", (190 * S, 54 * S), D.TAPE_RGBA).rotate(-4, expand=True, resample=Image.BICUBIC)
        c.im.alpha_composite(tp, (int((w / 2 - 95) * S), 0))
    return c


def v_full(img, B, pl):
    t, s0, s1 = B["t"], B["s0"], B["s1"]
    W, H = D.VW, D.VH
    a = eo((t - s0) / 0.28)
    z_in = 1.0 + 0.10 * (1 - a)
    fr = footage_img(pl["clips"][0], t, s0, s1, W * z_in, H * z_in, pl["mode"], 0.25 * B["idx"])
    if fr is None:
        return False
    if z_in > 1.001:
        ox, oy = int((fr.width - W * S) / 2), int((fr.height - H * S) / 2)
        fr = fr.crop((ox, oy, ox + W * S, oy + H * S))
    img.paste(fr, (0, 0))
    shade(img, _combo(W, H, [("g", 36, 150, 640, H - 120), ("b", 1000, 1500, 90, 200)]))
    boxes = rtype(img, B["text"], B["tw_of"], t, (60, 1020, W - 60, 1560), pxmax=134, dark=True)
    if boxes:
        bx = boxes[0]
        d = ImageDraw.Draw(img)
        aw = eo((t - s0 - 0.1) / 0.4)
        d.rectangle([60 * S, 996 * S, (60 + 220 * aw) * S, 1004 * S], fill=tuple(D.ACCENT))
    return True


def v_window(img, B, pl):
    t, s0, s1 = B["t"], B["s0"], B["s1"]
    W = D.VW
    card = _foot_card(pl["clips"][0], t, s0, s1, 940, 880, pl["mode"], r=46, border=10, off=0.25 * B["idx"])
    if card is None:
        return False
    D.place(img, card, W / 2, 640, t, s0 + 0.04, rot=-1.2 if B["idx"] % 2 else 1.2, sc=1.0)
    noun = D.noun_of(B["text"])
    if noun:
        sc_ = D.icon_card(noun["icon"], noun.get("neg", False), size=300)
        D.place(img, sc_, W - 190 if B["idx"] % 2 else 190, 1010, t, B["ctx"].at(noun["word"], 0.25) - 0.1, rot=7.0 if B["idx"] % 2 else -7.0, sc=1.0)
    rtype(img, B["text"], B["tw_of"], t, (50, 1150, W - 50, 1560), pxmax=124)
    accents(img, t, s0, pl["seed"], zones=[(30, 140, 350, 230), (730, 140, 1050, 230)], n=2)
    return True


def _phone_card(clip, t, s0, s1, mode, off):
    w, h = 580, 1100
    im = footage_img(clip, t, s0, s1, w - 44, h - 44, mode, off)
    if im is None:
        return None
    c = D.Card(w, h, r=74, fill=D.DEEP)
    scr = rounded(im, 54)
    c.im.paste(scr, (22 * S, 22 * S), scr)
    c.rect(w / 2 - 80, 34, w / 2 + 80, 62, D.DEEP, r=14)
    return c


def v_device(img, B, pl):
    t, s0, s1 = B["t"], B["s0"], B["s1"]
    W = D.VW
    ph = _phone_card(pl["clips"][0], t, s0, s1, pl["mode"], 0.25 * B["idx"])
    if ph is None:
        return False
    left = B["idx"] % 2 == 0
    D.place(img, ph, 400 if left else W - 400, 640, t, s0 + 0.04, rot=5.0 if left else -5.0, sc=0.92)
    ico = D.noun_of(B["text"])
    label = B.get("hero") or (ico["label"].title() if ico else "")
    if label:
        ch = D.Card(420, 170, r=40)
        ch.rect(26, 30, 26 + 110, 30 + 110, D.mix(D.ACCENT, D.INK, 0.2), r=30)
        if ico:
            spec = story_icons.ICONS[ico["icon"]]
            isz, ox = 70, 26 + 20
            for ck, pts in spec:
                ch.line([(ox + px * isz / 100.0, 50 + py * isz / 100.0) for px, py in pts], D.TXT if ck == "i" else D.ACCENT, 5)
        f = D.F("heavy", 46)
        ch.text(160, 85, label[:16].upper(), f, D.TXT, "lm")
        D.place(img, ch, W - 260 if left else 260, 360, t, B["ctx"].at(ico["word"] if ico else None, 0.35) - 0.05, rot=-4.0 if left else 4.0, sc=1.0)
    rtype(img, B["text"], B["tw_of"], t, (50, 1230, W - 50, 1590), pxmax=112)
    return True


def v_collage(img, B, pl):
    t, s0, s1 = B["t"], B["s0"], B["s1"]
    W = D.VW
    a = _foot_card(pl["clips"][0], t, s0, s1, 860, 960, pl["mode"], r=18, border=36, tape=True, off=0.25 * B["idx"])
    b = _foot_card(pl["clips"][1], t, s0, s1, 600, 700, MODES[(MODES.index(pl["mode"]) + 2) % len(MODES)], r=18, border=28, tape=True, off=0.5 + 0.25 * B["idx"])
    if a is None or b is None:
        return False
    left = B["idx"] % 2 == 0
    D.place(img, a, 410 if left else W - 410, 590, t, s0 + 0.04, rot=-4.5 if left else 4.5, sc=0.74)
    D.place(img, b, W - 300 if left else 300, 860, t, s0 + 0.30, rot=5.5 if left else -5.5, sc=0.66)
    rtype(img, B["text"], B["tw_of"], t, (50, 1230, W - 50, 1590), pxmax=112)
    return True


def v_print(img, B, pl):
    t, s0, s1 = B["t"], B["s0"], B["s1"]
    W = D.VW
    card = D.o_footage(pl["clips"][0], t, s0, 0.3 * B["idx"])
    if card is None:
        return False
    D.place(img, card, W / 2, 700, t, s0 + 0.04, rot=-1.5 if B["idx"] % 2 else 1.5, sc=min(780 / card.h, 860 / card.w))
    rtype(img, B["text"], B["tw_of"], t, (50, 1110, W - 50, 1480), pxmax=118)
    return True


def _icons_for(text, n=3):
    out = []
    for c in story_scenes.concrete(text):
        if c["icon"] in story_icons.ICONS and c["icon"] not in [o[0] for o in out]:
            out.append((c["icon"], c.get("neg", False), c["word"]))
    for kw in story_scenes._kw_nodes(text):
        if kw["icon"] in story_icons.ICONS and kw["icon"] not in [o[0] for o in out]:
            out.append((kw["icon"], False, kw["word"]))
    return out[:n]


def v_cluster(img, B, pl):
    t, s0 = B["t"], B["s0"]
    W = D.VW
    ics = _icons_for(B["text"], 3)
    if not ics:
        return False
    slots = {1: [(W / 2, 600, 640, 0.0)],
             2: [(330, 520, 460, -5.0), (740, 760, 420, 5.0)],
             3: [(330, 470, 430, -5.0), (760, 600, 400, 5.0), (470, 930, 360, -2.0)]}[len(ics)]
    for (ic, neg, word), (x, y, size, rot) in zip(ics, slots):
        card = D.icon_card(ic, neg, size=size)
        D.place(img, card, x, y, t, B["ctx"].at(word, 0.15) - 0.1, rot=rot, sc=1.0)
    rtype(img, B["text"], B["tw_of"], t, (50, 1140, W - 50, 1560), pxmax=124)
    accents(img, t, s0, pl["seed"], n=3)
    return True


def v_bigword(img, B, pl):
    t, s0 = B["t"], B["s0"]
    W = D.VW
    hero = pl["hero"]
    if not hero:
        return False
    m = re.search(r"\d", hero)
    word_t = B["ctx"].at(re.sub(r"[^A-Za-z0-9]", "", hero.split()[0]), 0.2)
    a = c01((t - word_t + 0.05) / 0.55)
    # soft blobs behind the number
    for i, (bx, by, br) in enumerate(((300, 560, 330), (780, 700, 260))):
        k = eo((t - s0) / 0.6)
        pad = 140
        blob = Image.new("L", (int((2 * br + 2 * pad) * S), int((2 * br + 2 * pad) * S)), 0)
        ImageDraw.Draw(blob).ellipse([pad * S, pad * S, (pad + 2 * br) * S, (pad + 2 * br) * S], fill=int(46 * k))
        blob = blob.filter(ImageFilter.GaussianBlur(44 * S))
        img.paste(Image.new("RGB", blob.size, D.ACCENT), (int((bx - br - pad + 14 * math.sin(t * 0.8 + i)) * S), int((by - br - pad) * S)), blob)
    # the number, counted up when it is a plain number
    shown = hero
    nm = re.match(r"^(\$?\s?)(\d[\d,]*)(\.\d+)?(.*)$", hero)
    if nm and a < 1:
        n = float((nm.group(2) + (nm.group(3) or "")).replace(",", ""))
        v = n * eo(a)
        txt = ("{:,.0f}".format(v) if not nm.group(3) else "{:,.1f}".format(v))
        shown = nm.group(1) + txt + nm.group(4)
    shown = shown.upper().replace("PERCENT", "%").replace(" %", "%")
    px = 330
    f = D.F("heavy", px)
    while D.width(shown, f) > W - 120 and px > 90:
        px -= 10
        f = D.F("heavy", px)
    if a > 0.02:
        sc = 0.85 + 0.15 * spr(a)
        D.shadow_text(img, W / 2, 560, shown, D.F("heavy", px * sc), px * sc, anchor="mm", strength=min(1.0, a * 2))
        ImageDraw.Draw(img).text((W / 2 * S, 560 * S), shown, font=D.F("heavy", px * sc), fill=D.mix(D.ACCENT, D.INK, c01(a * 2.2)), anchor="mm")
        w_ = D.width(shown, D.F("heavy", px * sc))
        scribble_underline(img, W / 2 - w_ / 2, W / 2 + w_ / 2, 560 + px * 0.55, t, word_t + 0.45, D.BONE, w=9, seed=pl["seed"] % 90)
    rtype(img, B["text"], B["tw_of"], t, (50, 930, W - 50, 1500), pxmax=104)
    return True


def v_annot(img, B, pl):
    t, s0 = B["t"], B["s0"]
    W = D.VW
    boxes = rtype(img, B["text"], B["tw_of"], t, (50, 330, W - 50, 1230), pxmax=160)
    if not boxes:
        return True
    words = B["text"].split()
    # underline the last words (the italic tail)
    tail = [b for b in boxes if not b[5]]
    if tail:
        by = max(b[2] for b in tail)
        x0 = min(b[1] for b in tail if b[2] == by)
        x1 = max(b[1] + b[3] for b in tail if b[2] == by)
        scribble_underline(img, x0, x1, by + boxes[0][4] * 0.30, t, B["tw_of"](tail[-1][0]) + 0.25, D.ACCENT, w=10, seed=pl["seed"] % 90)
    # circle a number
    for b in boxes:
        wtxt = re.sub(r"[^0-9$%.,]", "", words[b[0]]) if b[0] < len(words) else ""
        if wtxt and re.search(r"\d", wtxt):
            scribble_circle(img, b[1] + b[3] / 2, b[2] - b[4] * 0.32, b[3] / 2 + 26, b[4] * 0.62, t, B["tw_of"](b[0]) + 0.2, D.RED, w=9, seed=pl["seed"] % 70)
            break
    accents(img, t, s0, pl["seed"], zones=[(40, 170, 340, 290), (740, 1260, 1040, 1380), (40, 1260, 340, 1380)], n=3)
    return True


def v_note(img, B, pl):
    t, s0 = B["t"], B["s0"]
    W = D.VW
    text = B["text"]
    if B["kind"] == "quote" and B["f"].get("quote"):
        text = "“" + B["f"]["quote"] + "”"
    paper = (255, 232, 130) if sum(D.PAPER) > 700 else D.PAPER
    w, h = 820, 860
    c = D.Card(w, h, fill=paper, r=14)
    px = 108 if len(text) < 48 else 92 if len(text) < 80 else 76
    f = hand(px)
    lines = D.wrap(text, f, w - 120)
    while len(lines) * px * 1.22 > h - 150 and px > 56:
        px -= 6
        f = hand(px)
        lines = D.wrap(text, f, w - 120)
    lh = px * 1.22
    y = h / 2 - len(lines) * lh / 2 + lh / 2
    words_total = len(text.split())
    seen = 0
    toks_t = lambda i: B["tw_of"](min(i, max(0, words_total - 1)))
    for ln in lines:
        xx = 62
        for w_ in ln.split():
            a = eo((t - toks_t(seen)) / 0.2)
            seen += 1
            ww = c.tw(w_, f)
            if a > 0.02:
                c.text(xx, y + (1 - a) * 12, w_, f, D.mix((50, 36, 22), paper, a), "lm")
                if D.word_color(w_) == D.RED:
                    c.rect(xx - 4, y + 22, xx + ww + 4, y + 30, D.RED)
            xx += ww + c.tw(" ", f)
        y += lh
    tp = Image.new("RGBA", (200 * S, 56 * S), D.TAPE_RGBA).rotate(2, expand=True, resample=Image.BICUBIC)
    c.im.alpha_composite(tp, (int((w / 2 - 100) * S), 0))
    D.place(img, c, W / 2, 700, t, s0 + 0.04, rot=-3.0 if B["idx"] % 2 else 3.0, sc=1.0)
    accents(img, t, s0, pl["seed"], zones=[(40, 140, 340, 230), (740, 140, 1040, 230), (40, 1250, 340, 1380), (740, 1250, 1040, 1380)], n=3)
    return True


def hook_page(img, t, total):
    """The hook on full screen footage when the library has a shot for it (headline over a dark gradient, a quick white flash on the first frames)."""
    if not (ENABLED and D.PORTRAIT and D.FOOTAGE):
        return False
    try:
        plan_all()
        if not _HOOK:
            return False
        W, H = D.VW, D.VH
        a = eo(t / 0.35)
        z = 1.0 + 0.10 * (1 - a)
        fr = footage_img(_HOOK["clip"], t, 0.0, max(total, 3.0), W * z, H * z, _HOOK["mode"], 0.0)
        if fr is None:
            return False
        if z > 1.001:
            ox, oy = int((fr.width - W * S) / 2), int((fr.height - H * S) / 2)
            fr = fr.crop((ox, oy, ox + W * S, oy + H * S))
        img.paste(fr, (0, 0))
        L = D.hook_layout()
        px = L["px"]
        n1, n2 = len(L["l1"]), len(L["l2"])
        block = (n1 + n2) * px * 1.12
        yy = max(420, 960 - block / 2)
        shade(img, _combo(W, H, [("g", 46, 46, 0, H), ("b", int(yy - 40), int(yy + block + 40), 170, 220)]))
        d = ImageDraw.Draw(img)
        cx = W / 2
        a0, a1 = eo(t / 0.28), eo((t - 0.12) / 0.3)
        for ln in L["l1"]:
            f = D.F("heavy", px)
            _shadow_light(img, cx, yy + px * 0.62 + (1 - a0) * 24, ln, f, px, "mm", a0)
            d.text((cx * S, (yy + px * 0.62 + (1 - a0) * 24) * S), ln, font=f, fill=D.mix(D.LIGHT, (0, 0, 0), a0), anchor="mm")
            yy += px * 1.06
        yy += px * 0.1
        for ln in L["l2"]:
            f = D.F("ital", px * 1.14)
            _shadow_light(img, cx, yy + px * 0.62 + (1 - a1) * 24, ln, f, px, "mm", a1)
            d.text((cx * S, (yy + px * 0.62 + (1 - a1) * 24) * S), ln, font=f, fill=D.mix(D.mix(D.ACCENT, (255, 255, 255), 0.78), (0, 0, 0), a1), anchor="mm")
            yy += px * 1.16
        flash = max(0.0, 1 - t / 0.14) * 0.55
        if flash > 0.01:
            img.paste(solid(img.size, (255, 255, 255)), (0, 0), Image.new("L", img.size, int(255 * flash)))
        return True
    except Exception:
        _log_error("hook", {"cid": 0, "idx": 0})
        return False


def v_card(img, B, pl):
    """The old page (one icon card and type, or type alone) so the mix always keeps some quiet beats."""
    return False


VARIANTS = {"full": v_full, "window": v_window, "device": v_device, "collage": v_collage, "print": v_print,
            "cluster": v_cluster, "bigword": v_bigword, "annot": v_annot, "note": v_note, "card": v_card}


def page(img, B):
    """Draw the plain beat B in its planned layout. Returns True when it did (the caller then skips the old page and the small caption)."""
    if not ENABLED:
        return False
    pl = variant_of(B["cid"], B["idx"])
    if not pl:
        return False
    fn = VARIANTS.get(pl["variant"])
    if fn is None:
        return False
    try:
        B = dict(B, hero=pl.get("hero"))
        return bool(fn(img, B, pl))
    except Exception:
        _log_error(pl["variant"], B)
        return False


_LOGGED = set()


def _log_error(variant, B):
    """A layout that fails falls back to the old page, and the reason is kept in studio_data/rich_errors.log (once per layout and beat)."""
    key = (variant, B.get("cid"), B.get("idx"))
    if key in _LOGGED:
        return
    _LOGGED.add(key)
    try:
        import traceback
        import projects
        with open(projects.DATA_DIR / "rich_errors.log", "a", encoding="utf-8") as fh:
            fh.write("--- %s clip %s beat %s" % (variant, B.get("cid"), B.get("idx")) + chr(10) + traceback.format_exc() + chr(10))
    except Exception:
        pass


# ------------------------------------------------------------------ new elements (cards for D.object_spec / D.build_obj)
_NUM = r"\$?\d[\d,]*(?:\.\d+)?"
_WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
            "fifteen": 15, "eighteen": 18, "twenty": 20, "thirty": 30}


def _val(s):
    try:
        return float(re.sub(r"[^0-9.]", "", s))
    except ValueError:
        return None


def compare_of(text):
    """'from 11 deals to 1' / '$550 against $850' -> {"a": (label, value), "b": (label, value)} (None when the sentence has no two numbers to set side by side)."""
    low = text
    m = re.search(r"from\s+(" + _NUM + r")\s*([a-zA-Z ]{0,18}?)\s+(?:down |up )?to\s+(" + _NUM + r")", low, re.I)
    if m and _val(m.group(1)) is not None and _val(m.group(3)) is not None:
        return {"a": (m.group(1), _val(m.group(1))), "b": (m.group(3), _val(m.group(3))), "unit": m.group(2).strip()}
    m = re.search(r"(" + _NUM + r")\s*(?:vs\.?|versus|instead of|compared (?:to|with)|against|rather than)\s*(" + _NUM + r")", low, re.I)
    if m and _val(m.group(1)) is not None and _val(m.group(2)) is not None:
        return {"a": (m.group(2), _val(m.group(2))), "b": (m.group(1), _val(m.group(1))), "unit": ""}
    return None


DUR = re.compile(r"\b(\d+|" + "|".join(_WORDNUM) + r")\s+(years?|months?|weeks?|days?)\b", re.I)


TIME_CUE = re.compile(r"\b(ago|later)\b|\b(over|within|takes?|took|in|for|every)\s+(about\s+|almost\s+|more than\s+|only\s+)?(\d+|" + "|".join(_WORDNUM) + r")\s+(years?|months?|weeks?|days?)\b", re.I)


def duration_of(text):
    """'two years later', 'over 18 months', 'takes 8 days' -> a time span. Not '15 years running kitchens' (an age, not time passing)."""
    if not TIME_CUE.search(text):
        return None
    m = DUR.search(text)
    if not m:
        return None
    n = _WORDNUM.get(m.group(1).lower()) or int(m.group(1))
    unit = m.group(2).lower().rstrip("s")
    return {"n": n, "unit": unit, "label": "%d %s%s" % (n, unit.upper(), "" if n == 1 else "S"), "word": m.group(1)}


def object_spec(text, f_, money, pct):
    """New kinds the old planner did not know. Called after the loan, calendar, rent roll, grid, listing, sheet and thread checks and before a plain amount."""
    if not ENABLED:
        return None
    cmp_ = compare_of(text)
    if cmp_:
        return dict(cmp_, kind="bars")
    if pct and not money:
        v = _val(pct.group(1))
        if v is not None and 0 < v <= 100:
            return {"kind": "ring", "pct": v, "label": re.sub(r"[^a-z ]", "", text.lower().replace(pct.group(0), " "))[:28].strip()}
    d = duration_of(text)
    if d and not money:
        return dict(d, kind="meter")
    return None


def _fmt(v, sample):
    s = "${:,.0f}" if sample.strip().startswith("$") else "{:,.0f}"
    return s.format(v) if v >= 100 or float(v).is_integer() else ("${:,.1f}" if sample.strip().startswith("$") else "{:,.1f}").format(v)


def o_bars(sp, t, at):
    W_, H_ = 900, 700
    c = D.Card(W_, H_)
    c.text(56, 62, "BEFORE", D.F("sans", 26), D.MUTED)
    (al, av), (bl, bv) = sp["a"], sp["b"]
    top = max(av, bv) or 1.0
    t_a = at(re.sub(r"[^A-Za-z0-9]", "", al), 0.2)
    t_b = at(re.sub(r"[^A-Za-z0-9]", "", bl), 0.55)
    for i, (lab, val, ts, col, name) in enumerate(((al, av, t_a, D.MUTED, "FROM"), (bl, bv, t_b, D.ACCENT, "TO"))):
        y = 150 + i * 240
        a = eo((t - ts) / 0.6)
        c.text(56, y - 26, name, D.F("sans", 26), D.MUTED)
        c.rect(56, y, W_ - 56, y + 120, D.PAPER2, r=26)
        wbar = max(30, (W_ - 112) * (val / top) * a)
        if a > 0.01:
            c.rect(56, y, 56 + wbar, y + 120, col, r=26)
            shown = val * a
            c.text(56 + 36, y + 62, _fmt(shown, lab).upper(), D.F("heavy", 62), D.LIGHT if i == 1 else D.TXT, "lm")
    if bv != av:
        pct = (bv - av) / av * 100 if av else 0
        a = eo((t - t_b - 0.5) / 0.4)
        if a > 0.02:
            chip = ("%+.0f%%" % pct).replace("-", "−")
            c.rect(W_ - 56 - 250, H_ - 120, W_ - 56, H_ - 40, D.RED if pct < 0 else D.GREEN, r=40)
            c.text(W_ - 56 - 125, H_ - 80, chip, D.F("heavy", 52), D.LIGHT, "mm")
    return c


def o_ring(sp, t, at):
    size = 760
    c = D.Card(size, size)
    word = None
    a = eo((t - at(word, 0.25)) / 0.9)
    cx = cy = size / 2
    R = 250
    ang = 360 * sp["pct"] / 100.0 * a
    c.d.arc([cx - R, cy - R, cx + R, cy + R], -90, 270, fill=tuple(D.PAPER2) + (255,), width=64)
    if ang > 0.5:
        c.d.arc([cx - R, cy - R, cx + R, cy + R], -90, -90 + ang, fill=tuple(D.ACCENT) + (255,), width=64)
    c.text(cx, cy - 10, "%d%%" % round(sp["pct"] * a), D.F("heavy", 150), D.TXT, "mm")
    if sp.get("label"):
        lines = D.wrap(sp["label"].upper(), D.F("sans", 34), 420)[:2]
        for i, ln in enumerate(lines):
            c.text(cx, cy + 96 + i * 40, ln, D.F("sans", 34), D.MUTED, "mm")
    return c


def o_meter(sp, t, at):
    W_, H_ = 900, 560
    c = D.Card(W_, H_)
    scale = {"day": 30, "week": 12, "month": 24, "year": 10}[sp["unit"]]
    frac = min(1.0, sp["n"] / float(scale))
    ts = at(sp["word"], 0.2)
    a = eo((t - ts) / 0.8)
    c.text(56, 64, "TIME", D.F("sans", 26), D.MUTED)
    c.rect(56, 170, W_ - 56, 250, D.PAPER2, r=40)
    if a > 0.01:
        c.rect(56, 170, 56 + max(60, (W_ - 112) * frac * a), 250, D.ACCENT, r=40)
    ticks = 12
    for i in range(ticks + 1):
        x = 56 + (W_ - 112) * i / ticks
        c.line([(x, 268), (x, 286 if i % 3 else 300)], D.MUTED, 4)
    c.text(W_ / 2, 400, sp["label"], D.F("heavy", 120), D.TXT, "mm")
    return c


def build(sp, t, at):
    k = sp["kind"]
    if k == "bars":
        return o_bars(sp, t, at)
    if k == "ring":
        return o_ring(sp, t, at)
    return o_meter(sp, t, at)


KINDS = ("bars", "ring", "meter")
