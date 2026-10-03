"""layout_guard.py - collision-free scene planning for the stickman generator.

Reusable layout subsystem: every on-screen element is *claimed* as an AABB
region with a layer and an optional group. The planner then guarantees:

  * TEXT never overlaps a non-grouped element (no caption sitting on a
    floor line, a prop, another label, or outside the canvas);
  * a solid PROP never overlaps a different-group PROP;
  * ACCENT marks (stamps/badges/xmarks) may only overlay their own host.

Text is MOVABLE: each text carries an anchor (x, y) + priority, and every
text is auto-fit so it never clips the canvas. On a conflict the lower-
priority text re-flows around the design grid (prefer y rows, then x).
Fixed elements keep their authored positions, so a clean scene is rendered
pixel-identical to the day's art direction - the guard only intervenes
where something would actually collide.

Usage from a generator:
    from layout_guard import Scene
    sc = Scene.builder(cid, idx, g)      # generator registers claims via callbacks
    sc.fixed("floor", box, GROUND)
    sc.fixed("card1", box, PROP, group="q")          # group "q" can overlap freely
    sc.accent("xmark1", box, group="q")              # stamp allowed on its host
    sc.text("DON'T START THERE", 540, 690, px, PRIO_STATEMENT)
    sc.solve()
    x, y, px = sc.pos("DON'T START THERE")           # planned, margin-safe value
    print(sc.report())

`audit(fn)` runs a builder across a whole project and returns a list of
problem strings for a QA gate.
"""
import generate_video as g

__all__ = ["Scene", "audit", "GROUND", "PROP", "ACCENT", "TEXT",
           "PRIO_PIECE", "PRIO_KICKER", "PRIO_FOOT", "PRIO_STATEMENT"]

W, H = g.W, g.H
MARGIN = 26                      # keep text clear of screen edges
MAXW = W - 2 * MARGIN            # widest caption before we shrink it
MIN_PX = 20

GROUND, PROP, ACCENT, TEXT = 1, 2, 3, 4

PRIO_PIECE = 10                  # small in-scene labels (MAKE / SPEND / ...)
PRIO_KICKER = 20                 # gray kicker line
PRIO_FOOT = 30                   # footnote line
PRIO_STATEMENT = 40              # hero statement (kept at its anchor first)


def _inter(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def text_box(x, y, s, px):
    """Screen-space bbox of a centered caption, padded for stroke width."""
    f = g.Fonts.get(max(4, int(px)))
    w = f.getlength(s) + 12
    h = px + 10
    return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)


def fitted_px(s, px):
    """Shrink px so the caption fits MAXW (auto-fit = never clip canvas)."""
    px = int(px)
    w = g.Fonts.get(px).getlength(s)
    if w <= MAXW:
        return px
    for trial in range(int(px), MIN_PX - 1, -1):
        if g.Fonts.get(trial).getlength(s) <= MAXW:
            return trial
    return MIN_PX


# ---- glyph half-spans (must mirror the actual draw code) -------------

def ground_box(cx, cy, span):
    return (cx - span, cy - 3, cx + span, cy + 3)


def coin_pile_box(x, y, n, r=15, gap=26):
    n = max(0, int(n))
    if n <= 0:
        n = 1
    top = y - 12 - (n - 1) * gap - r
    return (x - r, top, x + r, y - 12 + r)


def house_box(x, y, s):
    return (x - 1.2 * s, y - 1.31 * s, x + 1.2 * s, y + 3)


def building_box(x, y, w, h):
    return (x - w / 2 - 3, y - h - 3, x + w / 2 + 3, y + 3)


def arrow_box(p1, p2, lw=6):
    (a, b), (c, e) = p1, p2
    return (min(a, c) - 8, min(b, e) - 18, max(a, c) + 34, max(b, e) + 10)


def tag_box(x, y, w, h):
    return (x - w - 22, y - h - 3, x + w + 22, y + h + 24)


def card_box(x, y, w, h):
    return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)


def loop_box(cx, cy, r):
    return (cx - r - 5, cy - r - 5, cx + r + 5, cy + r + 5)


def gate_box_r(x, y, w, h):
    return (x - w - 3, y - h - 3, x + w + 3, y + h + 3)


def clock_box(x, y, s):
    return (x - s, y - s, x + s, y + s)


def glyph_box(x, y, w, h):
    return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)


def heart_box(x, y, s):
    r = 34 * s
    return (x - 2 * r, y - 2 * r, x + 2 * r, y + 1.9 * r)


def skyline_box(cx, cy, w, h, count=4):
    base = cy + 30
    return (cx - w / 2, base - (h + 60), cx + w / 2, base + 22)


def phone_box(cx, cy, s):
    return (cx - 62 * s, cy - 112 * s, cx + 62 * s, cy + 112 * s)


def door_box(cx, cy, wh):
    return (cx - wh / 2 - 8, cy - wh, cx + wh / 2 + 8, cy + wh / 5)


class Scene:
    """One frozen beat: fixed claims + movable text; solved in one pass."""

    def __init__(self, cid, idx):
        self.cid, self.idx = cid, idx
        self._fixed = []       # (key, box, layer, group)
        self.texts = []       # (key, x, y, s, px, prio, group)
        self._pos = None
        self.problems = []    # strings: collisions still present after solve

    # ---- builder API -------------------------------------------------
    def fixed(self, key, box, layer=PROP, group=None):
        self._fixed.append((key, box, layer, group))

    def accent(self, key, box, group=None):
        self._fixed.append((key, box, ACCENT, group))

    def text(self, key, x, y, s, px, prio=PRIO_STATEMENT, group=None):
        self.texts.append((key, x, y, s, px, prio, group))

    # ---- solving -----------------------------------------------------
    def solve(self):
        self._pos = {}
        self.problems = []
        placed = list(self._fixed)

        # 1) fixed solid props must not overlap different-group solid props.
        solids = [t for t in self._fixed if t[2] in (PROP, GROUND)]
        for i in range(len(solids)):
            for j in range(i + 1, len(solids)):
                k1, b1, l1, g1 = solids[i]
                k2, b2, l2, g2 = solids[j]
                if g1 == g2 or l1 == l2 == GROUND:
                    continue
                if _inter(b1, b2):
                    self.problems.append(
                        f"prop overlap: {k1} vs {k2} (clip{self.cid} beat{self.idx})")

        # 2) text placed highest priority first so it keeps its anchor.
        for key, x, y, s, px, prio, group in sorted(
                self.texts, key=lambda t: -t[5]):
            px = fitted_px(s, px)
            box = text_box(x, y, s, px)
            if not self._clean(box, group, placed):
                x, y, px, box = self._reflow(s, x, y, group, placed, px)
            self._pos[key] = (x, y, px)
            placed.append((key, box, TEXT, group))
        return self

    def _clean(self, box, group, placed):
        if box[0] < MARGIN or box[2] > W - MARGIN:
            return False
        if box[1] < 14 or box[3] > H - 14:
            return False
        for _, ob, _ol, og in placed:
            if og == group:
                continue
            if _inter(box, ob):
                return False
        return True

    def _reflow(self, s, ax, ay, group, placed, px):
        for dyy in (0, 40, -40, 80, -80, 120, -120, 160, -160, 200):
            y = ay + dyy
            for dxx in (0, 60, -60, 120, -120, 180, -180):
                x = ax + dxx
                b = text_box(x, y, s, px)
                if self._clean(b, group, placed):
                    return x, y, px, b
        # fallback: first in-canvas spot
        for y in range(0, H - px, 40):
            for x in range(0, W, 100):
                b = text_box(x, y, s, px)
                if self._clean(b, group, placed):
                    return x, y, px, b
        return ax, ay, px, text_box(ax, ay, s, px)

    def pos(self, key):
        return self._pos.get(key)

    def report(self):
        out = [f"clip{self.cid} beat{self.idx}: {len(self._pos)} texts planned"]
        for key, (x, y, px) in self._pos.items():
            row = [t for t in self.texts if t[0] == key][0]
            x0, y0, s, old_px = row[1], row[2], row[3], row[4]
            tag = ""
            if px != old_px:
                tag += f" fit px{old_px}->{px}"
            if (x, y) != (x0, y0):
                tag += f" shift -> ({x},{y})"
            out.append(f"    {key!r}{tag}")
        out += [f"    !! {p}" for p in self.problems]
        return "\n".join(out)


def audit(items):
    """Solve several beats and collect all problems (for a QA gate)."""
    out = []
    seen = set()
    for cid, idx, build in items:
        sc = Scene(cid, idx)
        build(sc)
        sc.solve()
        out += sc.problems
        key = (cid, idx)
        if key not in seen:
            seen.add(key)
    return out