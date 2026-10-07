"""story_dan.py - draws any script_story in the Dan style (a centred panel or glyph and a caption bar).

generate_lifestyle.apply_to() calls install(L, story): with a story the module's clips, beats, scenes, intro, outro
and sound cues come from the script; with None the hand-built demo story is restored. Lists / dicts that other
modules hold references to (CLIPS, NARR_BEATS, PAD_BEFORE) are changed in place.
"""
import json
import math
import re

import story_scenes

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
    """Break text into lines of about `width` characters; "9 to 5" stays together."""
    glue = ""
    text = re.sub(r"(\d) (to|TO) (\d)", lambda m: m.group(1) + glue + m.group(2) + glue + m.group(3), text)
    lines, cur = [], ""
    for w in text.split():
        if cur and len(cur.replace(glue, " ")) + 1 + len(w.replace(glue, " ")) > width:
            lines.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    return [l.replace(glue, " ") for l in lines + ([cur] if cur else [])]


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
    aq = L.clamp01((t_abs - trig) / max(0.08, 0.3 * story_scenes.anim_scale()))
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


class DanBE(story_scenes.Backend):
    """story_scenes primitives drawn with Dan's palette on its virtual page."""

    def __init__(self, L, d, t, ox, oy, k):
        super().__init__(t, ox, oy, k)
        self.L, self.d = L, d
        self.char_w = 22                  # capitals are wide: wrap labels earlier
        self.pal = {"ink": L.FG, "accent": L.SKY, "mute": (140, 140, 148), "neg": L.g.RED,
                    "soft": L.dim_col(L.FG, 0.07), "white": L.PANEL_BG}

    def color(self, name):
        return self.pal.get(name, name)

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
        a = max(0.0, min(1.0, (self.t - trig) / dur))
        if a <= 0.02:
            return
        px = max(16, int(round(px)))
        col = self.L.dim_col(color, a * a * (3 - 2 * a))
        s = s.upper()
        if anchor == "m":
            self.L.g.big_text(self.d, x, y, s, color=col, px=px)
        else:
            self.d.text((x, y - px / 2), s, fill=col, font=self.L.g.Fonts.get(px))

    def _claim(self, key, box):
        pass

    def photo_path(self, node, sp):
        return story_scenes.photo_for(node)

    def _photo(self, path, ax, ay, bx, by, q, r):
        SS = self.L.g.SS
        w, h = int(round((bx - ax) * SS)), int(round((by - ay) * SS))
        if w < 8 or h < 8:
            return
        im = story_scenes.photo_image(path, w, h, int(r * SS))
        if q < 0.99:
            im = im.copy()
            im.putalpha(im.getchannel("A").point(lambda v: int(v * q)))
        self.d.r._image.paste(im, (int(round(ax * SS)), int(round(ay * SS))), im)
        self.d.rounded_rectangle([ax, ay, bx, by], radius=r, outline=self.pal["ink"], width=3)


def scene_region(L, kind):
    """(ox, oy, k) of the scene box on the page, plus the (x, y, w) of a quote card when the beat has one."""
    cx, cy = L.page_centre()
    if L.VW <= 1100 and L.VH > 1500 and story_scenes.safe_area():       # 9:16 with the Reels / Shorts safe area
        band_x = story_scenes.SAFE_LEFT + (L.VW - story_scenes.SAFE_LEFT - story_scenes.SAFE_RIGHT) / 2
        if kind == "quote":
            return (band_x - 350, 640, 0.7), (band_x, 300, 700)
        return (band_x - 430, 320, 0.86), (band_x, 300, 700)
    if L.VW <= 1100 and L.VH > 1500:                       # 9:16
        return (40, cy - 540, 1.0) if kind != "quote" else (140, cy - 250, 0.8), (cx, cy - 470, 700)
    k = 0.8 if kind != "quote" else 0.5
    ox = (L.VW - 1000 * k) / 2
    return (ox, 15, k) if kind != "quote" else (ox, 235, k), (L.VW / 2, 120, 640)


def draw_beat(L, story, cid, d, t_abs):
    g = L.g
    c = L.CLIPS[cid - 1]
    idx, p = g.local_beat(c, t_abs)
    L.set_beat(cid, idx)
    f = story["feats"][str(cid)][idx]
    s0, s1 = g.clip_beats(c)[idx]
    ctx = story_scenes.Ctx(s0, s1, beat_words(L, c, idx), lambda kk: t_word(L, c, idx, kk))
    reg, card = scene_region(L, f["kind"])
    if f["kind"] == "quote":
        a = g.ease_out(L.clamp01((t_abs - s0) / 0.3))
        qx, qy, qw = card
        qlines = wrap(f["quote"], 22 if L.VW > 1000 and L.VH > 1500 else 30)[:3]
        qpx = 36 if L.VH > 1500 else 30
        ph = 60 + len(qlines) * (qpx + 14)
        L.explainer_card(d, qx, qy + ph / 2, qw, ph, a=a)
        if a > 0.3:
            for i, ln in enumerate(qlines):
                g.big_text(d, qx, qy + 40 + qpx / 2 + i * (qpx + 14), ln, color=L.dim_col(L.INK, a), px=qpx)
        t_end = (beat_words(L, c, idx)[-1][1] + 0.3) if beat_words(L, c, idx) else s1
        if t_abs > t_end and f.get("neg"):
            q = g.ease_out(L.clamp01((t_abs - t_end) / 0.25))
            d.line([qx - qw / 2 + 20, qy + ph / 2, qx - qw / 2 + 20 + (qw - 40) * q, qy + ph / 2], fill=g.RED, width=6)
    story_scenes.draw(DanBE(L, d, t_abs, *reg), ctx, story_scenes.scene_of(story, cid, idx))
    safe = L.VW <= 1100 and L.VH > 1500 and story_scenes.safe_area()
    cap_x = (story_scenes.SAFE_LEFT + (L.VW - story_scenes.SAFE_RIGHT)) / 2 if safe else L.page_centre()[0]
    cap_y = 1250 if safe else L.page_centre()[1] + L.CAP_Y
    caption_block(L, d, cap_x, cap_y, t_abs, s0 + 0.05, f["text"], 34)


# ------------------------------------------------------------------ the scene solver sees the same boxes
def build_scene(L, story, sc, cid, idx):
    f = story["feats"][str(cid)][idx]
    (ox, oy, k), _card = scene_region(L, f["kind"])
    sc.fixed("scene", (ox, oy, ox + 1000 * k, oy + 760 * k), L.PROP, "p")


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
        DanBE(L, d, t, cx - 160, cy + 150, 0.32).icon(story_scenes.hook_icon(story), 500, 400, 560, cut_t + 0.05, dur=0.5)   # the thing the hook names
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
