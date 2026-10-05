"""story_adi.py - draws any script_story in the adi style (headline + hero icon + cards that appear as words are spoken).

generate_adi.apply_to() calls install(adi_module, story): with a story the module's clips, beats, panels, scenes,
intro, outro and sound cues are replaced by the generic ones below; with None the hand-built demo story is restored.
Nothing here is specific to one script: it reads the beat descriptions in story.json (see script_story.py).
"""
import json
import re
from pathlib import Path

import story_icons
import story_scenes

_BUILTIN = {}
_WORDS = {}


# ------------------------------------------------------------------ word timing inside a beat
def beat_words(A, c, bi):
    """[(token, clip time)] of the words spoken inside beat `bi` (same window the beat sync uses)."""
    cid = c["id"]
    path = A.g.TIMING_DIR / f"clip{cid}.json"
    try:
        stamp = path.stat().st_mtime
    except OSError:
        stamp = 0
    key = (cid, bi, str(path), stamp)
    if key in _WORDS:
        return _WORDS[key]
    out = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))["words"]
        bs, be = A.g.clip_beats(c)[bi]
        pad = A.PAD_BEFORE.get(cid, 0.45)
        out = [(w["word"], pad + w["start"]) for w in data if bs - 0.01 <= pad + w["start"] <= be - 0.01]
    except Exception:
        pass
    _WORDS[key] = out
    return out


def t_word(A, c, bi, k):
    """Clip time at which the k-th word of the beat is spoken (clamped; falls back to a point inside the beat)."""
    ws = beat_words(A, c, bi)
    if ws:
        return ws[max(0, min(len(ws) - 1, int(k)))][1]
    bs, be = A.g.clip_beats(c)[bi]
    return bs + (be - bs) * min(0.95, 0.1 + 0.8 * k / 12.0)


def nwords(s):
    return len([w for w in s.split() if re.sub(r"[^A-Za-z0-9]", "", w)])


# ------------------------------------------------------------------ pieces
def _fit_px(A, text, px, maxw):
    while px > 30 and A.text_w("head", px, text, A.TRACK) > maxw:
        px -= 2
    return px


def head_spec(A, f, c, bi, base_k=0):
    """Headline lines with the moment each one starts being spoken, and the accent on the closing words."""
    lines, specs, k = f["head"], [], base_k
    total = sum(nwords(l) for l in lines)
    acc = f.get("accent", 0)
    for line in lines:
        ws = line.split()
        n = nwords(line)
        trig = t_word(A, c, bi, k) if f["kind"] == "statement" or k > 0 else A.g.clip_beats(c)[bi][0] + 0.02
        segs, cur, curcol = [], [], None
        for j, w in enumerate(ws):
            gi = k + j - base_k
            col = A.ORANGE if (acc and gi >= total - acc) else A.INK
            if curcol is not None and col != curcol:
                segs.append((" ".join(cur) + " ", curcol)); cur = []
            cur.append(w); curcol = col
        segs.append((" ".join(cur), curcol))
        specs.append((segs if any(s[1] == A.ORANGE for s in segs) else line, trig))
        k += n
    return specs


def chip_row(A, cv, chips, c, bi, y):
    """Pills (icon + word) for the drawable words of the beat, wrapping to the zone width."""
    ws = beat_words(A, c, bi)
    norm = [re.sub(r"[^a-z0-9]", "", w[0].lower()) for w in ws]
    px_, py_ = A.LM, y
    for i, (word, icon) in enumerate(chips):
        key = re.sub(r"[^a-z0-9]", "", word.lower())
        tr = ws[norm.index(key)][1] if key in norm else A.g.clip_beats(c)[bi][0] + 0.15 + 0.2 * i
        w_ = A.text_w("head", 44, word.lower(), A.TRACK) + 56 + 56
        if px_ + w_ > cv.vw - A.LM:
            px_, py_ = A.LM, py_ + 96
        with A.layer(cv, f"chip{i}", px_, py_, w_, 78, tr, margin=10, group="chips") as l:
            if l:
                l.rrect(px_, py_, px_ + w_, py_ + 78, 39, fill=A.WHITE, outline=A.INK, width=3)
                A.icon(l, icon, px_ + 46, py_ + 39, 50, tr, dur=0.4, claim=False)
                l.text(px_ + 84, py_ + 54, word.lower(), "head", 44, A.INK, track=A.TRACK, claim=False)
                l.claim(f"chip{i}", (px_, py_, px_ + w_, py_ + 78))
        px_ += w_ + 20


def quote_card(A, cv, f, c, bi, y, k0):
    """The quoted words on a card; they appear as spoken and are struck out (wrong) or ticked (right) at the end."""
    x, w = A.LM, cv.maxw
    lines, px = f["qlines"], 56
    h = 52 + len(lines) * 76 + 24
    s0 = A.g.clip_beats(c)[bi][0]
    t_end = beat_words(A, c, bi)[-1][1] + 0.35 if beat_words(A, c, bi) else A.g.clip_beats(c)[bi][1]
    with A.layer(cv, "quote", x, y, w, h, s0 + 0.1, bob=2.0) as l:
        if not l:
            return h
        A.card_frame(l, x, y, w, h, dots=False)
        k = k0
        for i, ln in enumerate(lines):
            by = y + 56 + 48 + i * 76
            tr = t_word(A, c, bi, k)
            l.text(x + 30, by, ln, "head", px, A.INK, track=A.TRACK, trig=tr, claim=False)
            k += nwords(ln)
        l.rect(x + 28, y - 16, x + 150, y + 14, fill=(255, 205, 60, 190))
        if cv.t >= t_end:
            q = A.ease_out((cv.t - t_end) / 0.3)
            if f.get("neg"):
                for i, ln in enumerate(lines):
                    by = y + 56 + 48 + i * 76
                    lw = A.text_w("head", px, ln, A.TRACK)
                    l.line([(x + 24, by - 15), (x + 24 + (lw + 12) * q, by - 15)], A.RED, 7)
                A.xmark(l, x + w - 40, y + 38, 12, A.RED, 7)
            else:
                A.check(l, x + w - 56, y + h - 44, 24 * q, A.ORANGE, 9)
        l.claim("quote", (x, y, x + w + 10, y + h + 10))
    return h


def list_rows(A, cv, f, c, bi, base_y, k0):
    """Numbered rows that appear as the items are spoken."""
    items, icons = f["items"], f["icons"]
    n = len(items)
    gap = 130 if n <= 4 else 112 if n == 5 else 96
    if not A.PORTRAIT:
        gap = int(gap * 0.76)
    k = k0
    rows = []
    for i, item in enumerate(items):
        tr = t_word(A, c, bi, k)
        k += nwords(item)
        px = _fit_px(A, item.lower(), 84 if n <= 4 else 72, cv.maxw - 110 - 160)
        yy = base_y + i * gap
        if cv.t >= tr:
            cv.text(A.LM, yy, f"{i + 1:02d}", "monob", 46, A.ORANGE, trig=tr, track=0.05, claim=True, key=f"n{i}")
            cv.text(A.LM + 110, yy + 12, item.lower(), "head", px, A.INK, trig=tr, track=A.TRACK, key=f"r{i}")
            cv.line([(A.LM, yy + 48), (A.LM + cv.maxw - 12, yy + 48)], A.ROWLINE, 3, dots=False)
            A.icon(cv, icons[i], A.LM + cv.maxw - 80, yy - 20, 84, tr + 0.05, dur=0.5)
        rows.append(tr)
    return rows


# ------------------------------------------------------------------ one beat
# ------------------------------------------------------------------ story scenes (shared with the Dan style, see story_scenes.py)
class AdiBE(story_scenes.Backend):
    """story_scenes primitives drawn with Adi's canvas and palette."""

    def __init__(self, A, cv, ox, oy, k):
        super().__init__(cv.t, ox, oy, k)
        self.A, self.cv = A, cv
        self.pal = {"ink": A.INK, "accent": A.ORANGE, "mute": A.MUTE, "neg": A.RED, "soft": (246, 242, 232), "white": A.WHITE}

    def color(self, name):
        return self.pal.get(name, name)

    def _line(self, pts, color, w):
        self.cv.line(pts, color, w)

    def _rect(self, x0, y0, x1, y1, fill, line, w, r):
        self.cv.rrect(x0, y0, x1, y1, r, fill=fill, outline=line, width=max(1, int(round(w))))

    def _ellipse(self, cx, cy, r, fill, line, w):
        if r > 0.5:
            self.cv.ellipse(cx, cy, r, fill=fill, outline=line, width=max(1, int(round(w))))

    def _text(self, s, x, y, px, color, anchor, trig, dur, key):
        px = max(16, int(round(px)))
        self.cv.text(x, y + 0.36 * px, s, "head", px, color, anchor=anchor, track=self.A.TRACK, trig=trig, dur=dur, key=key)

    def _claim(self, key, box):
        self.cv.claim(key, box)


def scene_region(A, cv, kind):
    """(ox, oy, k) of the scene box inside the visual zone, or None when this format has no room for it."""
    if kind == "quote":
        if A.SQUARE:
            return None
        return 190, 1270, 0.7
    if A.PORTRAIT:
        return 40, 1000, 1.0
    if A.SQUARE:
        return (cv.vw - 800) / 2, 950, 0.8
    return 40, 870, 1.0


def draw_scene(A, story, cid, cv, c, idx, kind):
    spec = story_scenes.scene_of(story, cid, idx)
    s0, s1 = A.g.clip_beats(c)[idx]
    ctx = story_scenes.Ctx(s0, s1, beat_words(A, c, idx), lambda kk: t_word(A, c, idx, kk))
    with A.zone(cv, "V"):
        reg = scene_region(A, cv, kind)
        if reg:
            story_scenes.draw(AdiBE(A, cv, *reg), ctx, spec)


def draw_beat(A, story, cid, cv, t):
    c = A.CLIPS[cid - 1]
    idx, _p = A._beat(c, t)
    f = story["feats"][str(cid)][idx]
    kind = f["kind"]
    s0 = A.g.clip_beats(c)[idx][0]
    n = len(f["head"])
    y_top = max(430, 560 - max(0, n - 2) * 45)
    if kind == "list":
        if f["head"]:
            A.head(cv, head_spec(A, f, c, idx), y_top=min(y_top, 520), px=min(f["px"], 104), lead=1.05)
        draw_scene(A, story, cid, cv, c, idx, kind)
    elif kind == "quote":
        lead_k = nwords(f.get("lead", ""))
        A.head(cv, head_spec(A, f, c, idx), y_top=y_top, px=f["px"], lead=1.05)
        quote_card(A, cv, f, c, idx, 1000, lead_k)
        draw_scene(A, story, cid, cv, c, idx, kind)
    else:
        A.head(cv, head_spec(A, f, c, idx), y_top=y_top, px=f["px"], lead=1.05)
        draw_scene(A, story, cid, cv, c, idx, kind)


# ------------------------------------------------------------------ hook / outro
def hook_times(A, story):
    hook = A.load_hook_timing()
    words = hook["words"]
    k = min(len(words) - 1, story["hook_split"])
    cut = words[k]["start"] if words else hook.get("duration", 2.0) * 0.5
    total = A.g.get_audio_duration(A.g.AUDIO_DIR / f"clip{A.HOOK_ID}.mp3") + A.g.INTRO_PAD_BEFORE + A.g.INTRO_PAD_AFTER
    return A.g.INTRO_PAD_BEFORE + cut, total


def draw_intro(A, story, cv, t):
    cut_t, _total = hook_times(A, story)
    import script_story
    first = script_story.wrap_lines(story["hook_head"][0], 18)
    second = script_story.wrap_lines(story["hook_head"][1], 18)
    cv.head_top = 520
    nlines = len(first) + len(second)
    px = {1: 120, 2: 118, 3: 112, 4: 104, 5: 90}.get(nlines, 78)
    lines = [(l, -1.0) for l in first] + [([(l, A.ORANGE)], cut_t) for l in second]
    A.head(cv, lines, y_top=max(430, 520 - max(0, nlines - 3) * 40), px=px, lead=1.05)
    if t >= cut_t:
        A.hero(cv, story["hook_icon"], cut_t, side="right")
        with A.zone(cv, "V"):
            A.icon(cv, story["hook_icon"], cv.vw / 2, 1240, 380, cut_t + 0.2, dur=0.8, key="hero")


def draw_outro(A, story, cv, t):
    lines = [(l, 0.5 + 0.15 * i) for i, l in enumerate(story["outro"]["lines"])]
    A.head(cv, [([(l, A.ORANGE if i == len(lines) - 1 else A.INK)], tr) for i, (l, tr) in enumerate(lines)], y_top=520, px=128)
    A.hero(cv, story["outro"]["icon"], 0.9, big=420 if A.LANDSCAPE else None)


# ------------------------------------------------------------------ sound cues
def sfx_events(A, story, clip):
    cid = clip["id"]
    beats = A.g.clip_beats(clip)
    evs = []
    if not beats:
        return evs
    for bi in A.pan_beats(cid):
        st, d = A.pan_start_dur(clip, bi)
        evs.append((st + d / 2 - 0.15, "swish", 0.34))
    for bi, f in enumerate(story["feats"][str(cid)]):
        s0 = beats[bi][0]
        if f["kind"] == "list":
            k = nwords(f.get("lead", ""))
            for item in f["items"]:
                evs.append((t_word(A, clip, bi, k) + 0.05, "pop", 0.4))
                k += nwords(item)
        elif f["kind"] == "quote":
            ws = beat_words(A, clip, bi)
            end = (ws[-1][1] + 0.35) if ws else beats[bi][1]
            evs.append((end + 0.05, "slam" if f.get("neg") else "ding", 0.5))
        elif f.get("chips"):
            evs.append((s0 + 0.2, "pop", 0.4))
    return [(max(0.0, t), n, g_) for t, n, g_ in evs]


# ------------------------------------------------------------------ switching the module between stories
def install(A, story):
    """Point generate_adi's globals at `story`, or restore the hand-built demo when story is None."""
    if not _BUILTIN:
        _BUILTIN.update(CLIPS=A.CLIPS, NARR_BEATS=A.NARR_BEATS, HOOK_TEXT=A.HOOK_TEXT, DRAW=A.DRAW, draw_intro=A.draw_intro,
                        draw_outro=A.draw_outro, intro_times=A.intro_times, sfx_events=A.sfx_events, PAD_BEFORE=A.PAD_BEFORE)
    if story is None:
        for k, v in _BUILTIN.items():
            setattr(A, k, v)
        A.STORY = None
    else:
        n = len(story["clips"])
        A.CLIPS = story["clips"]
        A.NARR_BEATS = {int(k): v for k, v in story["beats"].items()}
        A.HOOK_TEXT = story["hook"]
        A.PAD_BEFORE = {i: 0.6 for i in range(1, n + 1)}        # room for the camera to glide into the first frame
        A.DRAW = {i: (lambda cv, t, _i=i: draw_beat(A, story, _i, cv, t)) for i in range(1, n + 1)}
        A.draw_intro = lambda cv, t: draw_intro(A, story, cv, t)
        A.draw_outro = lambda cv, t: draw_outro(A, story, cv, t)
        A.intro_times = lambda: hook_times(A, story)
        A.sfx_events = lambda clip: sfx_events(A, story, clip)
        A.STORY = story
    A.ICONS.update(story_icons.ICONS)                           # the larger icon set (also used by the scenes)
    A.PANELS, A.PANEL_OF = A._build_panels()
    A.NT = len(A.PANELS)
    A._TL = None
    A._SET.clear()
    A._AUTO.clear()
    _WORDS.clear()
