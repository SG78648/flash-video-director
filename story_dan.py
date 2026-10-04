"""story_dan.py - draws any script_story in the Dan style (a centred panel or glyph and a caption bar).

generate_lifestyle.apply_to() calls install(L, story): with a story the module's clips, beats, scenes, intro, outro
and sound cues come from the script; with None the hand-built demo story is restored. Lists / dicts that other
modules hold references to (CLIPS, NARR_BEATS, PAD_BEFORE) are changed in place.
"""
import json
import math
import re

_BUILTIN = {}
_WORDS = {}


# ------------------------------------------------------------------ word timing (same window the beat sync uses)
def beat_words(L, c, bi):
    g = L.g
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


def t_word(L, c, bi, k):
    ws = beat_words(L, c, bi)
    if ws:
        return ws[max(0, min(len(ws) - 1, int(k)))][1]
    bs, be = L.g.clip_beats(c)[bi]
    return bs + (be - bs) * min(0.95, 0.1 + 0.8 * k / 12.0)


def nwords(s):
    return len([w for w in s.split() if re.sub(r"[^A-Za-z0-9]", "", w)])


def wrap(text, width):
    lines, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    return lines + ([cur] if cur else [])


# ------------------------------------------------------------------ pieces
def caption_block(L, d, cx, y, t_abs, trig, text, px=34, color=None):
    """The lower-third caption: one rounded bar holding the beat's words (up to three lines)."""
    g = L.g
    lines = wrap(text.upper(), 26)[:3]
    for shrink in range(px, 21, -2):
        widest = max(d.textlength(ln, font=g.Fonts.get(shrink)) for ln in lines)
        if widest + 64 <= L.VW - 90:
            px = shrink
            break
    aq = L.clamp01((t_abs - trig) / 0.3)
    aq = aq * aq * (3 - 2 * aq)
    if aq <= 0.02:
        return None
    widest = max(d.textlength(ln, font=g.Fonts.get(px)) for ln in lines)
    bw, lh = widest + 64, px + 14
    bh = len(lines) * lh + 26
    cy = y - (len(lines) - 1) * lh / 2 + (1 - aq) * 10
    d.rounded_rectangle([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], radius=14, fill=L.CAP_BG,
                        outline=L.CAP_BORDER, width=2 if L.CAP_BORDER else 0)
    col = L.FG if color is None else color
    for i, ln in enumerate(lines):
        g.big_text(d, cx, cy - bh / 2 + 13 + lh / 2 + i * lh, ln, color=L.dim_col(col, aq), px=px)
    return (cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)


def glyph(L, d, name, cx, cy, p, t_abs, a=1.0):
    """A small drawing for the beat's icon, centred on (cx, cy)."""
    g = L.g
    sky, red = L.SKY, g.RED
    if name == "coin":
        n = max(1, int(g.spring(p, k=10) * 6))
        g._coin_pile(d, cx, cy + 110, n, sky, r=34, gap=40, rot=t_abs * 0.5)
        L.halo(d, cx, cy, 150, sky, alpha=0.16 * a)
    elif name in ("bldg", "house"):
        h = max(20, int(220 * g.spring(p, k=9)))
        g.gold_building(d, cx, cy + 130, 240, h, alpha=1.0, shadow=True, color=sky, shadow_color=L.PANEL_SHADOW)
        L.halo(d, cx, cy + 30, 190, sky, alpha=0.16 * a)
    elif name == "clock":
        L.clock_g(d, cx, cy, 78, sky, deg=t_abs * 90)
        L.halo(d, cx, cy, 160, sky, alpha=0.2 * a)
    elif name == "bars":
        rise = g.ease_out(L.clamp01(p / 0.7))
        g.arrow(d, cx - 120, cy + 110, cx + 90, cy + 110 - rise * 200, color=sky, lw=9)
        L.halo(d, cx + 90, cy + 110 - rise * 200, 70, sky, alpha=0.3 * a)
    elif name == "warning":
        pulse = 0.5 + 0.5 * math.sin(t_abs * 4)
        L.halo(d, cx, cy, 150 + 30 * pulse, red, alpha=0.2)
        g.big_text(d, cx, cy, "!", color=red, px=150)
    else:        # padlock / bubble / bulb / key / wallet / sprout: a card with a document mark
        L.explainer_card(d, cx, cy, 300, 200, a=a)
        L.doc_icon(d, cx, cy, s=70, color=sky, a=a)


# ------------------------------------------------------------------ one beat
def draw_beat(L, story, cid, d, t_abs):
    g = L.g
    c = L.CLIPS[cid - 1]
    L.set_beat(cid, g.local_beat(c, t_abs)[0])
    idx, p = g.local_beat(c, t_abs)
    f = story["feats"][str(cid)][idx]
    cx, cy = L.page_centre()
    s0 = g.clip_beats(c)[idx][0]
    kind = f["kind"]
    if kind == "list":
        items = f["items"][:6]
        pw = 560
        ph = 110 + len(items) * 62
        pcy = cy - 70
        L.dashboard_panel(d, cx, pcy, pw, ph)
        title = (f.get("lead") or " ".join(f.get("head", [""])).rstrip(":")).upper()[:26] or "LIST"
        L.dash_header(d, cx, pcy - ph / 2 + 34, pw - 40, title)
        k = nwords(f.get("lead", ""))
        for i, item in enumerate(items):
            tr = t_word(L, c, idx, k)
            k += nwords(item)
            L.checklist_row(d, cx - 235, pcy - ph / 2 + 100 + i * 62, item.upper()[:26], t_abs, tr, color=L.SKY, px=24, dur=0.32)
    elif kind == "quote":
        a = g.ease_out(L.clamp01((t_abs - s0) / 0.3))
        qlines = wrap(f["quote"], 24)[:4]
        ph = 100 + len(qlines) * 56
        L.explainer_card(d, cx, cy - 30, 600, ph, a=a)
        if a > 0.3:
            for i, ln in enumerate(qlines):
                g.big_text(d, cx, cy - 30 - ph / 2 + 62 + i * 56, ln, color=L.dim_col(L.INK, a), px=38)
        ws = beat_words(L, c, idx)
        t_end = (ws[-1][1] + 0.3) if ws else g.clip_beats(c)[idx][1]
        if t_abs > t_end:
            q = g.ease_out(L.clamp01((t_abs - t_end) / 0.25))
            if f.get("neg"):
                g.xmark(d, cx, cy - 30, size=int(70 * q), color=g.RED, lw=8)
            else:
                g.check(d, cx, cy - 30 + ph / 2 + 10, size=int(28 * q), color=L.SKY, lw=7)
    else:
        glyph(L, d, f["icon"], cx, cy + 10, p, t_abs)
        if f.get("chips"):
            word = f["chips"][0][0].upper()
            ws = beat_words(L, c, idx)
            norm = [re.sub(r"[^a-z0-9]", "", w[0].lower()) for w in ws]
            key = re.sub(r"[^a-z0-9]", "", f["chips"][0][0].lower())
            tr = ws[norm.index(key)][1] if key in norm else s0 + 0.3
            L.pop_text(d, cx, cy - 200, t_abs, tr, word[:18], L.SKY, 40, dur=0.3, grow=1.04)
    caption_block(L, d, cx, cy + L.CAP_Y, t_abs, s0 + 0.05, f["text"], 34, g.RED if f.get("neg") and kind == "quote" and False else None)


# ------------------------------------------------------------------ the scene solver sees the same boxes
def build_scene(L, story, sc, cid, idx):
    cx, cy = L.page_centre()
    f = story["feats"][str(cid)][idx]
    h = 110 + len(f.get("items", [])[:6]) * 62 if f["kind"] == "list" else 260
    sc.fixed("panel", (cx - 300, cy - 70 - h / 2, cx + 300, cy - 70 + h / 2), L.PROP, "p")


# ------------------------------------------------------------------ hook / outro
def intro_setup(L, story):
    g = L.g
    hook = L.load_hook_timing()
    words = hook["words"]
    k = min(len(words) - 1, story["hook_split"])
    cut_local = words[k]["start"] if words else hook["duration"] * 0.5
    hook_dur = g.get_audio_duration(g.AUDIO_DIR / f"clip{L.HOOK_ID}.mp3")
    total_dur = hook_dur + g.INTRO_PAD_BEFORE + g.INTRO_PAD_AFTER
    return total_dur, max(1, int(total_dur * g.FPS)), g.INTRO_PAD_BEFORE + cut_local


def intro_frame(L, story, f, setup=None):
    g = L.g
    total_dur, _tf, cut_t = setup or intro_setup(L, story)
    cx, cy = L.VW // 2, L.VH // 2 - 20
    t = f / g.FPS
    img = g.Image.new("RGB", (L.VRW, L.VRH), L.PAGE_BG)
    d = g.D2(g.ImageDraw.Draw(img))
    L.bg_scene(d, t)
    cut_f = int(cut_t * g.FPS)
    first, second = wrap(story["hook_head"][0].upper(), 22)[:2], wrap(story["hook_head"][1].upper(), 22)[:2]
    lines, col = (first, L.FG) if f < cut_f else (second, g.RED)
    px = 52 if f < cut_f else 58
    L.halo(d, cx, cy, 300 if f < cut_f else 340, col if f >= cut_f else L.FG, alpha=0.16 if f < cut_f else 0.22)
    for i, ln in enumerate(lines):
        g.big_text(d, cx, cy - (len(lines) - 1) * (px + 10) / 2 + i * (px + 10), ln, px=px, color=col)
    if f >= cut_f:
        g._coin_pile(d, cx, cy + 330, 5, L.SKY, r=14, gap=22)
    frames_since = f - cut_f
    flash = max(0.0, 1.0 - frames_since * 0.55) if 0 <= frames_since < 2 else 0.0
    if flash > 0.02:
        d.rectangle([0, 0, L.VW, L.VH], fill=L.dim_col(L.FLASH_COLOR, flash * 0.22))
    fade_out = 1 - g.ease_out(L.clamp01((t - (total_dur - 0.25)) / 0.25))
    punch = 0.02 * math.exp(-(t - cut_t) / 0.3) if cut_t <= t < cut_t + 0.5 else 0.0
    cam = 1.0 + 0.02 * g.ease(L.clamp01(t / max(0.5, total_dur))) + punch
    out = L.finish_frame(g.apply_camera(img, cam, 0.0, 0.0), f)
    if fade_out < 0.999:
        out = g.Image.blend(g.Image.new("RGB", out.size, L.PAGE_BG), out, fade_out)
    return out


def outro_frame(L, story, f):
    g = L.g
    cx, cy = L.VW // 2, L.VH // 2 + 40
    t = f / g.FPS
    img = g.Image.new("RGB", (L.VRW, L.VRH), L.PAGE_BG)
    d = g.D2(g.ImageDraw.Draw(img))
    L.bg_scene(d, t)
    h = int(240 * g.spring(L.clamp01(t / 0.6), k=9))
    g.gold_building(d, cx, cy + 160, 260, h, alpha=1.0, shadow=True, color=L.SKY, shadow_color=L.PANEL_SHADOW)
    L.halo(d, cx, cy + 160 - h // 2, 120 + h * 0.6, L.SKY, alpha=0.3)
    a2 = g.elastic(L.clamp01((t - 0.5) / 0.45)) * (1 - g.ease_out(L.clamp01((t - 1.5) / 0.5)))
    if a2 > 0.1:
        lines = [l.upper() for l in story["outro"]["lines"]][:3]
        for i, ln in enumerate(lines):
            g.big_text(d, cx, cy - 280 + i * 60, ln, px=44, color=L.dim_col(L.SKY if i == len(lines) - 1 else L.FG, a2))
    return L.finish_frame(img.resize((g.W, g.H), g.Image.LANCZOS), f)


# ------------------------------------------------------------------ sound cues
def sfx_events(L, story, clip):
    cid = clip["id"]
    beats = L.g.clip_beats(clip)
    evs = []
    if not beats:
        return evs
    evs.append((beats[0][0], "whoosh" if cid % 2 else "rise", 0.45))
    for bi, f in enumerate(story["feats"][str(cid)]):
        if f["kind"] == "list":
            k = nwords(f.get("lead", ""))
            for item in f["items"][:6]:
                evs.append((t_word(L, clip, bi, k) + 0.05, "tick", 0.4))
                k += nwords(item)
        elif f["kind"] == "quote":
            ws = beat_words(L, clip, bi)
            end = (ws[-1][1] + 0.3) if ws else beats[bi][1]
            evs += [(end + 0.02, "slam", 0.55), (end + 0.06, "crumble", 0.35)] if f.get("neg") else [(end + 0.02, "ding", 0.5)]
    evs.append((beats[-1][1] - 0.3, "chime", 0.4))
    return [(max(0.0, t), n, g_) for t, n, g_ in evs]


# ------------------------------------------------------------------ switching the module between stories
def install(L, story):
    if not _BUILTIN:
        _BUILTIN.update(CLIPS=list(L.CLIPS), NARR_BEATS=dict(L.NARR_BEATS), PAD_BEFORE=dict(L.PAD_BEFORE), HOOK_TEXT=L.HOOK_TEXT, REG=dict(L.REG),
                        build_scene=L.build_scene, intro_setup=L.intro_setup, intro_frame=L.intro_frame, outro_frame=L.outro_frame,
                        sfx_events=L.sfx_events)
    L.CLIPS[:] = _BUILTIN["CLIPS"] if story is None else story["clips"]
    L.NARR_BEATS.clear()
    L.NARR_BEATS.update(_BUILTIN["NARR_BEATS"] if story is None else {int(k): v for k, v in story["beats"].items()})
    L.PAD_BEFORE.clear()
    if story is None:
        L.PAD_BEFORE.update(_BUILTIN["PAD_BEFORE"])
        for k in ("HOOK_TEXT", "REG", "build_scene", "intro_setup", "intro_frame", "outro_frame", "sfx_events"):
            setattr(L, k, _BUILTIN[k])
        L.STORY = None
    else:
        n = len(story["clips"])
        L.PAD_BEFORE.update({i: 0.5 for i in range(1, n + 1)})
        L.HOOK_TEXT = story["hook"]
        L.REG = {i: (lambda d, t, _i=i: draw_beat(L, story, _i, d, t)) for i in range(1, n + 1)}
        L.build_scene = lambda sc, cid, idx: build_scene(L, story, sc, cid, idx)
        L.intro_setup = lambda: intro_setup(L, story)
        L.intro_frame = lambda f, setup=None: intro_frame(L, story, f, setup)
        L.outro_frame = lambda f: outro_frame(L, story, f)
        L.sfx_events = lambda clip: sfx_events(L, story, clip)
        L.STORY = story
    L._SC.clear()
    _WORDS.clear()
