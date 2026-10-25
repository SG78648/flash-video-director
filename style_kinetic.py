"""style_kinetic.py - the Kinetic Type style (from the Motion Graphics starter kit): the words are the whole video.

Black, huge all-caps Archivo Black, no cards and no boxes. One screen per sentence. Each word slams in on the moment it is spoken, fast and snappy
(power4.out, 0.25 to 0.4 s), and the moves are mixed: in from the left, stretched up from squashed, in from the right, letters split apart and back
together. The key word of the sentence is picked out in one accent colour and punches in a little bigger on its own line. Every screen exits fast before
the next one hits, so the cut falls on the rhythm of the speech like a beat. Sound is one quiet tick on the key word and nothing else.
The shared machinery (timing, segments, sound, the studio interface) is style_text.py.
"""
import os

import studio_config

if "FLASH_ASPECT" not in os.environ:     # command line: follow the app's saved format
    studio_config.ensure_aspect_env()

from PIL import Image

import style_text as T

STYLE_ID = "kinetic"
SS, W, H = T.SS, T.W, T.H

THEME = {"bg": (0, 0, 0), "ink": (255, 255, 255), "accent": (198, 255, 61), "dur": 0.30, "click": "tick", "push": 0.02}
FONT = "ArchivoBlack-400"
EXIT = 0.11                       # seconds a screen takes to leave before the next one


def apply_config(cfg=None):
    cfg = studio_config.normalize(cfg) if cfg else studio_config.load()
    n = cfg["kinetic"]
    THEME["accent"] = studio_config.rgb(n["palette"]["accent"])
    THEME["bg"] = studio_config.rgb(n["palette"]["bg"])
    THEME["dur"] = float(n["motion"]["slam"])
    THEME["click"] = "tick" if n["motion"]["click"] else None
    _LAYOUT.clear()
    _LAYERS.clear()


_LAYOUT = {}
_LAYERS = {}


def shown(tok):
    """What is drawn for a token: capitals, without the full stops and commas that would only add dots to a headline."""
    return tok.upper().rstrip(".,")


def layout(sc):
    """The lines of a screen: the words before the key word, the key word alone (larger), the words after. Returns [{"y", "px", "items": [(i, x, text)]}]
    in 1x pixels, each line centred, the block centred in the text box."""
    key = (sc["key"], W, H, tuple(t for t, _ in sc["words"]))
    if key in _LAYOUT:
        return _LAYOUT[key]
    x0, y0, x1, y1 = T.text_box()
    bw, bh = x1 - x0, y1 - y0
    toks = [shown(tk) for tk, _ in sc["words"]]
    a = sc["accent"]
    cap = 250 if g_portrait() else 190
    for px in range(cap, 50, -6):
        f = T.font(FONT, px)
        space = T.text_w(" ", f)
        groups = [list(range(0, a)), [a], list(range(a + 1, len(toks)))]
        rows = []
        for gi, idxs in enumerate(groups):
            if not idxs:
                continue
            if gi == 1:
                fa = T.font(FONT, px)
                wa = T.text_w(toks[a], fa)
                pa = min(px * 1.6, px * bw / max(wa, 1))      # the key word grows to fill the width, never past 1.6 x
                rows.append(([(a, T.text_w(toks[a], T.font(FONT, pa)))], pa))
                continue
            for ln in T.flow([(i, T.text_w(toks[i], f)) for i in idxs], bw, space):
                rows.append((ln, px))
        total = sum(p * 0.98 for _l, p in rows)
        widest = max(sum(w for _i, w in ln) + T.text_w(" ", T.font(FONT, p)) * (len(ln) - 1) for ln, p in rows)
        if total <= bh and widest <= bw + 1:
            break
    out, y = [], (y0 + y1) / 2 - total / 2
    for ln, p in rows:
        f = T.font(FONT, p)
        sp = T.text_w(" ", f)
        line_w = sum(w for _i, w in ln) + sp * (len(ln) - 1)
        x = (x0 + x1) / 2 - line_w / 2
        items = []
        for i, w in ln:
            items.append((i, x, toks[i], w))
            x += w + sp
        out.append({"y": y + p * 0.98 * 0.86, "px": p, "items": items})     # baseline of an all-caps line sits about 0.86 of the line height down
        y += p * 0.98
    _LAYOUT[key] = out
    return out


def g_portrait():
    return T.g.ASPECT == "9:16"


def word_layer(text, px, fill):
    key = (text, px, fill)
    if key not in _LAYERS:
        if len(_LAYERS) > 400:
            _LAYERS.clear()
        _LAYERS[key] = T.layer(text, T.font(FONT, px), fill)
    return _LAYERS[key]


def paint(sc, t, frame_no=0, seg=""):
    img = Image.new("RGB", (W * SS, H * SS), THEME["bg"])
    dur = THEME["dur"]
    out = T.ease_in((t - (sc["t1"] - EXIT)) / EXIT) if seg not in ("intro", "outro") else 0.0
    if out >= 1.0:
        return img
    times = [tm for _tk, tm in sc["words"]]
    for row in layout(sc):
        px = row["px"]
        for i, x, text, w in row["items"]:
            p = (t - times[i]) / dur
            if p <= 0:
                continue
            accent = i == sc["accent"]
            fill = THEME["accent"] if accent else THEME["ink"]
            e = T.ease_out(p, 4)
            lay, ox, oy = word_layer(text, px, fill)
            move = 4 if accent else i % 4
            dx = dy = 0.0
            alpha = min(1.0, p * 5)
            if move == 0:                                  # in from the left
                dx = -W * 0.55 * (1 - e)
            elif move == 2:                                # in from the right
                dx = W * 0.55 * (1 - e)
            elif move == 1:                                # stretched up from squashed, anchored on the baseline
                sy = 0.10 + 0.90 * T.back_out(p, 1.2)
                lay = lay.resize((lay.width, max(2, int(lay.height * sy))), Image.BILINEAR)
                oy = oy * sy
            elif move == 3:                                # the letters split apart and come back together
                spread = (1 - e) * px * 0.22
                base_f = T.font(FONT, px)
                n = len(text)
                lay2 = Image.new("RGBA", (lay.width + int(2 * spread * SS * n / 2) + 4, lay.height), (0, 0, 0, 0))
                xx = ox
                for k, ch in enumerate(text):
                    cl, cox, coy = word_layer(ch, px, fill) if ch.strip() else (None, 0, 0)
                    off = (k - (n - 1) / 2) * spread * SS
                    if cl is not None:
                        lay2.paste(cl, (int(xx - cox + off + spread * SS * n / 2), int(oy - coy)), cl)
                    xx += T.text_w(ch, base_f) * SS
                ox += spread * SS * n / 2
                lay = lay2
            else:                                          # the key word: punches in bigger and settles
                sc_ = 1.0 + 0.45 * (1 - e)
                lay = lay.resize((int(lay.width * sc_), int(lay.height * sc_)), Image.BILINEAR)
                ox, oy = ox * sc_, oy * sc_
            if out > 0:
                dy -= px * 0.5 * out
                alpha *= 1 - out
            # the word's text origin (baseline left) goes to (x, y) in 1x pixels
            cx = (x + dx) * SS - ox
            if move == 4:                                  # grow from the middle of the word, not its corner
                cx -= (lay.width - word_layer(text, px, fill)[0].width) / 2
            T.paste_layer(img, lay, cx, (row["y"] + dy) * SS - oy, alpha)
    return img


def finish(img, frame_no):
    return img


T.bind(__import__("sys").modules[__name__])
