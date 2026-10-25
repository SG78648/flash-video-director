"""style_editorial.py - the Editorial Grain style (from the Motion Graphics starter kit): a printed magazine page, not a screen.

Warm paper (#efe8dc) under visible, animated film grain. Instrument Serif for the words, large, upright with the key words in italic, ink black with one
deep red accent. The key word of every sentence sits on a cut-out slip of red paper, turned a degree or two, with a second paler slip peeking out behind
it, and thin rules sit above and below the block. Motion is unhurried and a little imperfect: words rise and fade in on the moment they are spoken with
travel and time that differ a little from word to word, the slip wipes in from the left, nothing bounces. The kit's page numbers are left out on purpose
(nothing counts or labels the video on screen). Sound is a soft paper rustle on the key word, nothing else.
The shared machinery (timing, segments, sound, the studio interface) is style_text.py.
"""
import hashlib
import os
import sys

import numpy as np

import studio_config

if "FLASH_ASPECT" not in os.environ:     # command line: follow the app's saved format
    studio_config.ensure_aspect_env()

from PIL import Image, ImageDraw

import style_text as T

STYLE_ID = "editorial"
SS, W, H = T.SS, T.W, T.H

THEME = {"paper": (239, 232, 220), "ink": (26, 26, 26), "accent": (194, 65, 45), "grain": 0.6, "click": "paper", "push": 0.015}
REG, ITAL = "InstrumentSerif-400", "InstrumentSerif-400-italic"
EXIT = 0.16

_LAYOUT = {}
_LAYERS = {}
_GRAIN = []
_PAPER = {}


def apply_config(cfg=None):
    cfg = studio_config.normalize(cfg) if cfg else studio_config.load()
    n = cfg["editorial"]
    THEME["paper"] = studio_config.rgb(n["palette"]["paper"])
    THEME["ink"] = studio_config.rgb(n["palette"]["ink"])
    THEME["accent"] = studio_config.rgb(n["palette"]["accent"])
    THEME["grain"] = float(n["look"]["grain"])
    THEME["click"] = "paper" if n["look"]["rustle"] else None
    # grain makes big files (the kit's own warning, 124 MB for 15 s): aim the encoder a little softer than the studio's quality setting, which keeps them small
    os.environ["FLASH_CQ"] = str(min(40, int(cfg["render"]["quality"]) + 6))
    for d in (_LAYOUT, _LAYERS, _PAPER):
        d.clear()


def jitter(sc, i, lo, hi):
    """A steady pseudo-random number in [lo, hi] for word i of a screen: the same on every frame, different from word to word (the 'not perfectly even' of a
    hand-made piece)."""
    h = hashlib.md5(repr((sc["key"], i)).encode()).digest()[0] / 255.0
    return lo + (hi - lo) * h


def layout(sc):
    """Left-aligned ragged lines in the text box. The key word is italic and padded (it gets a slip behind it). Returns the rows and the block's top/bottom."""
    key = (sc["key"], W, H, tuple(t for t, _ in sc["words"]))
    if key in _LAYOUT:
        return _LAYOUT[key]
    x0, y0, x1, y1 = T.text_box()
    bw, bh = x1 - x0, y1 - y0
    toks = [tk for tk, _ in sc["words"]]
    toks[0] = toks[0][:1].upper() + toks[0][1:]
    a = sc["accent"]
    cap = 175 if T.g.ASPECT == "9:16" else 140
    for px in range(cap, 48, -5):
        fr, fi = T.font(REG, px), T.font(ITAL, px * 1.04)
        space = T.text_w(" ", fr)
        pad = px * 0.16
        widths = []
        for i, tk in enumerate(toks):
            widths.append((i, T.text_w(tk, fi) + 2 * pad if i == a else T.text_w(tk, fr)))
        lines = T.flow(widths, bw, space)
        lh = px * 1.06
        total = len(lines) * lh
        if total <= bh * 0.92:
            break
    top = (y0 + y1) / 2 - total / 2
    rows = []
    for li, ln in enumerate(lines):
        x = x0
        items = []
        for i, w in ln:
            items.append((i, x, toks[i], w))
            x += w + space
        rows.append({"y": top + li * lh + px * 0.80, "items": items})
    res = {"rows": rows, "px": px, "pad": pad, "top": top, "bottom": top + total, "x0": x0, "x1": x1}
    _LAYOUT[key] = res
    return res


def layer_of(text, name, px, fill):
    key = (text, name, px, fill)
    if key not in _LAYERS:
        if len(_LAYERS) > 400:
            _LAYERS.clear()
        _LAYERS[key] = T.layer(text, T.font(name, px), fill)
    return _LAYERS[key]


def paper(frame_no):
    """The page: flat paper with a soft darkening toward the edges."""
    key = (W, H, THEME["paper"])
    if key not in _PAPER:
        yy, xx = np.mgrid[0:H // 4, 0:W // 4].astype(np.float32)
        nx, ny = (xx / (W / 4) - 0.5) * 2, (yy / (H / 4) - 0.5) * 2
        v = 1.0 - 0.07 * np.clip((nx ** 2 + ny ** 2) / 1.5, 0, 1)
        v = np.asarray(Image.fromarray((v * 255).astype(np.uint8), "L").resize((W * SS, H * SS), Image.BICUBIC)).astype(np.float32) / 255.0
        arr = np.array(THEME["paper"], dtype=np.float32)[None, None, :] * v[..., None]
        _PAPER[key] = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    return _PAPER[key].copy()


def slip(wd, ht, color, angle):
    """A rotated cut-out rectangle as an RGBA layer."""
    im = Image.new("RGBA", (int(wd), int(ht)), color + (255,))
    big = Image.new("RGBA", (int(wd * 1.5), int(ht * 2.2)), (0, 0, 0, 0))
    big.paste(im, ((big.width - im.width) // 2, (big.height - im.height) // 2))
    return big.rotate(angle, resample=Image.BICUBIC, expand=False)


def paint(sc, t, frame_no=0, seg=""):
    img = paper(frame_no)
    L = layout(sc)
    px, pad = L["px"], L["pad"]
    out = T.ease_in((t - (sc["t1"] - EXIT)) / EXIT, 2) if seg not in ("intro", "outro") else 0.0
    if out >= 1.0:
        return img
    d = ImageDraw.Draw(img)
    ink, red = THEME["ink"], THEME["accent"]
    times = [tm for _tk, tm in sc["words"]]
    # thin rules above and below the block, drawn out from the left as the screen starts
    rp = T.ease_out((t - sc["t0"]) / 0.55, 3) if seg not in ("intro", "outro") else T.ease_out(t / 0.55, 3)
    for yy in (L["top"] - px * 0.22, L["bottom"] + px * 0.02):
        d.rectangle([L["x0"] * SS, yy * SS, (L["x0"] + (L["x1"] - L["x0"]) * rp) * SS, (yy + 2) * SS], fill=ink if out == 0 else THEME["paper"])
    a = sc["accent"]
    ta = times[a]
    for row in L["rows"]:
        for i, x, text, w in row["items"]:
            if i == a:
                # the slips: a paler one behind, the red one in front, both wiped in from the left and turned a little
                p = T.ease_out((t - ta) / 0.40, 3)
                if p > 0.01:
                    ang = 1.0 + 2.0 * jitter(sc, 99, 0, 1)
                    sy = row["y"] - px * 0.80
                    hh = px * 1.02
                    back = slip(w * SS, hh * SS, tuple(min(255, int(c * 0.93)) for c in THEME["paper"]), -ang * 1.3)
                    front = slip(w * SS * p, hh * SS, red, ang)
                    cxm, cym = (x + w / 2) * SS, (sy + hh / 2 + px * 0.02) * SS
                    img.paste(back, (int(cxm - back.width / 2 + px * 0.05 * SS), int(cym - back.height / 2 + px * 0.06 * SS)), back)
                    img.paste(front, (int(cxm - w * SS / 2 - (front.width - w * SS * p) / 2 + 0), int(cym - front.height / 2)), front)
                fill, name, tx = THEME["paper"], ITAL, x + (L["pad"])
                size = px * 1.04
            else:
                fill, name, tx, size = ink, REG, x, px
            dur = jitter(sc, i, 0.40, 0.62)
            rise = jitter(sc, i, 0.14, 0.26) * px
            e = T.ease_out((t - times[i]) / dur, 3)
            if e <= 0:
                continue
            lay, ox, oy = layer_of(text, name, size, fill)
            alpha = e * (1 - out)
            T.paste_layer(img, lay, tx * SS - ox, (row["y"] + rise * (1 - e)) * SS - oy, alpha)
    return img


def finish(img, frame_no):
    """Film grain over everything: a few noise frames cycled, slightly different every frame."""
    if THEME["grain"] <= 0.01:
        return img
    if not _GRAIN:
        rng = np.random.default_rng(7)
        for _ in range(6):
            n = Image.fromarray((rng.random((H // 2, W // 2)) * 255).astype(np.uint8), "L").resize((W, H), Image.BILINEAR)     # grain two pixels wide: filmic, and it encodes smaller
            _GRAIN.append((np.asarray(n).astype(np.float32) / 127.5 - 1.0) * 1.7)
    n = _GRAIN[frame_no % len(_GRAIN)]
    arr = np.asarray(img).astype(np.float32) + (n * 16.0 * THEME["grain"])[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


T.bind(sys.modules[__name__])
