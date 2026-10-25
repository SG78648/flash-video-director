"""overlay.py - motion graphics on top of your own video, and a transparent export of them (from the Motion Graphics starter kit).

    python overlay.py clip.mp4                       graphics on the clip -> output/clip_overlay.mp4 (the clip's picture size, frame rate, cut and voice stay as they are)
    python overlay.py clip.mp4 --transparent         ALSO the graphics alone on a transparent background: output/clip_overlay.mov (ProRes 4444 with alpha)
                                                     and output/clip_overlay_png/00001.png ... (a PNG sequence), for Premiere or After Effects
    python overlay.py clip.mp4 --transparent-only    only the transparent files (no picture of the clip)
    python overlay.py clip.mp4 --plan-only           transcribe and write the plan (clip.overlay.json) and stop, so it can be edited by hand
    python overlay.py clip.mp4 --plan clip.overlay.json   draw exactly that plan (change a time, delete a moment) instead of planning again

How it decides (the starter kit's rules):
  - the speech is transcribed with Whisper (word times), then each moment is made for what is said right then and starts on the exact word:
      "from 40 a week to over 90"   -> a counter that rolls from 40 to 90      "1,200 members" -> a counter that rolls up to 1,200
      "better photos, faster replies, and real reviews" -> a checklist whose items tick in on their own words
  - nothing in the first 3 seconds (the hook), nothing in the bottom third (captions), nothing in the left and right 10%, and nothing on the face:
      the card sits in a band between a talking head's chin and the caption area ("chest", the default for upright video) or on the right ("right", for wide video)
  - one style throughout: a solid white card (it stays a card with nothing behind it, so it works as an overlay), Inter and Space Grotesk, green only for ticks
  - --full adds the rest of an edit: spoken-word captions (a few words at a time, the word being said lit in lime), punch-in zooms on the lines that
    matter, and a card for every numbered point ("the second thing ..."). The plan file also takes "fixes" (what the transcript heard -> what was said) so a
    wrong word never reaches a caption.
  - sound follows the kit: a tick on every list item, the counter sound while a number rolls, a chime on the last card, nothing for cards that come or go and no
    whooshes, all about 20 dB under the voice.
"""
import argparse
import json
import math
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
FONT_DIR = ROOT / "assets" / "fonts"
OUT_DIR = ROOT / "output"
VOICE_PY = ROOT / "voice_env" / "Scripts" / "python.exe"
SS = 2                      # cards are drawn at twice the size and scaled down

MIN_START = 3.0             # nothing in the first 3 seconds
SIDE = 0.10                 # keep the left and right 10% clear
INK, MUTED, GREEN = (29, 29, 31), (134, 134, 139), (52, 199, 89)
WEAK = set("a an the and or but of in on at to for with from by as is are was were it its that this these those".split())


# ------------------------------------------------------------------ the video
def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate,duration,nb_frames:format=duration",
                        "-of", "json", str(path)], capture_output=True, check=True)
    d = json.loads(r.stdout)
    s = d["streams"][0]
    num, den = (s["r_frame_rate"].split("/") + ["1"])[:2]
    fps = float(num) / float(den or 1)
    dur = float(d["format"].get("duration") or s.get("duration") or 0)
    a = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(path)], capture_output=True)
    return {"w": int(s["width"]), "h": int(s["height"]), "fps": fps, "fps_str": s["r_frame_rate"], "dur": dur, "audio": bool(a.stdout.strip())}


def transcribe(path, out_json):
    """Word times with Whisper (the voice environment has it)."""
    py = str(VOICE_PY) if VOICE_PY.exists() else sys.executable
    r = subprocess.run([py, str(ROOT / "overlay_transcribe.py"), str(path), str(out_json)], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("Could not transcribe the video (Whisper). Run the voice setup first.\n" + r.stderr[-800:])
    return json.loads(Path(out_json).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ the plan
NUM = re.compile(r"^[\$£€]?\d[\d,]*(\.\d+)?[%kKmM]?[.,!?]?$")


def _num(tok):
    """(value, decimals, prefix, suffix) of a number token, or None."""
    t = tok.strip()
    if not NUM.match(t):
        return None
    t = t.rstrip(".,!?")
    prefix = t[0] if t[0] in "$£€" else ""
    body = t[len(prefix):]
    suffix = ""
    if body and body[-1] in "%kKmM":
        suffix, body = body[-1], body[:-1]
    dec = len(body.split(".")[1]) if "." in body else 0
    try:
        return float(body.replace(",", "")), dec, prefix, suffix
    except ValueError:
        return None


def _clean(tok):
    return re.sub(r"[^A-Za-z0-9'$%.,\- ]", "", tok).strip()


def _label(words, i, n=2):
    """The (up to) n content words after word i, as the label of a number (stops at punctuation)."""
    out = []
    for w in words[i + 1:i + 1 + n + 2]:
        t = re.sub(r"[^A-Za-z']", "", w["word"])
        if not t:
            continue
        out.append(t)
        if w["word"][-1:] in ".,!?" or len(out) >= n:
            break
    return " ".join(out)


def plan_moments(words, info, zone="chest", full=False):
    """[{"type": "counter" | "checklist", ...}] in time order, every moment starting on the word it is about."""
    moments = []
    used = set()
    n = len(words)
    # counters: "from A ... to [over] B"
    for i, w in enumerate(words):
        if w["word"].lower().strip(",.") != "from":
            continue
        a = next((j for j in range(i + 1, min(n, i + 4)) if _num(words[j]["word"])), None)
        if a is None:
            continue
        to = next((j for j in range(a + 1, min(n, a + 6)) if words[j]["word"].lower().strip(",.") == "to"), None)
        if to is None:
            continue
        b = next((j for j in range(to + 1, min(n, to + 4)) if _num(words[j]["word"])), None)
        if b is None:
            continue
        va, vb = _num(words[a]["word"]), _num(words[b]["word"])
        label = " ".join(re.sub(r"[^A-Za-z']", "", x["word"]) for x in words[a + 1:to] if re.sub(r"[^A-Za-z']", "", x["word"]))
        ta, tb = words[to]["start"], words[b]["end"]
        used.update(range(i, b + 1))
        moments.append({"type": "counter", "t0": round(words[i]["start"], 2), "from": va[0], "to": vb[0], "dec": max(va[1], vb[1]), "prefix": vb[2] or va[2],
                        "suffix": vb[3] or va[3], "label": label, "roll": [round(min(ta, tb - 0.8), 2), round(tb, 2)], "t1": round(tb + 1.5, 2), "was": words[a]["word"].strip(",.")})
    # counters: one number on its own
    for i, w in enumerate(words):
        if i in used:
            continue
        v = _num(w["word"])
        if not v or v[0] < 2 or (v[0] < 2100 and v[0] > 1900 and not v[2] and not v[3]):          # skip a bare 1 and years
            continue
        nxt = words[i + 1]["word"].lower().strip(",.") if i + 1 < n else ""
        suffix = "%" if nxt in ("percent", "per") and not v[3] else v[3]
        label = _label(words, i + (1 if suffix == "%" and nxt == "percent" else 0), 2)
        used.add(i)
        moments.append({"type": "counter", "t0": round(w["start"] - 0.1, 2), "from": 0, "to": v[0], "dec": v[1], "prefix": v[2], "suffix": suffix, "label": label,
                        "roll": [round(w["start"] - 0.1, 2), round(w["end"] + 0.9, 2)], "t1": round(w["end"] + 2.6, 2), "was": ""})
    # checklists: a sentence of three or more short items split by commas
    start = 0
    for i, w in enumerate(words):
        if w["word"][-1:] in ".?!" or i == n - 1:
            sent = list(range(start, i + 1))
            start = i + 1
            if any(j in used for j in sent):
                continue
            groups, cur = [], []
            for j in sent:
                cur.append(j)
                if words[j]["word"][-1:] == ",":
                    groups.append(cur)
                    cur = []
            if cur:
                groups.append(cur)
            items = []
            for gr in groups:
                gr = [j for j in gr]
                while gr and words[gr[0]]["word"].lower().strip(",.") in ("and", "or", "plus"):
                    gr = gr[1:]
                if gr:
                    items.append(gr)
            if len(items) >= 3 and all(len(gr) <= 5 for gr in items):
                its = []
                for gr in items:
                    txt = " ".join(re.sub(r"[,.!?]+$", "", words[j]["word"]) for j in gr).strip()
                    its.append({"text": txt[:1].upper() + txt[1:], "t": round(words[gr[0]]["start"], 2)})
                moments.append({"type": "checklist", "t0": round(its[0]["t"] - 0.2, 2), "items": its, "t1": round(words[items[-1][-1]]["end"] + 1.8, 2)})
    if full:
        moments += plan_points(words)
    moments.sort(key=lambda m: m["t0"])
    # rules: nothing in the first 3 s, nothing overlapping, nothing past the end
    out = []
    for m in moments:
        if m["t0"] < MIN_START:
            continue
        if out and m["t0"] < out[-1]["t1"] + 0.2:
            out[-1]["t1"] = max(out[-1]["t0"] + 1.0, m["t0"] - 0.25)
            if out[-1]["t1"] > m["t0"] - 0.2:
                continue
        m["t1"] = round(min(m["t1"], info["dur"] - 0.05), 2)
        if m["t1"] - m["t0"] < 0.8:
            continue
        out.append(m)
    return out


# ------------------------------------------------------------------ transcript fixes, captions, points, punch-ins
def norm_tok(w):
    return re.sub(r"[^a-z0-9']", "", w.lower())


def apply_fixes(words, fixes):
    """Replace what the transcript heard with what was said: {"find": "heard words", "text": "right words"} (the first match; the new words share the time of the old)."""
    words = [dict(w) for w in words]
    for fx in fixes or []:
        find = [t for t in (norm_tok(x) for x in fx["find"].split()) if t]
        toks = [norm_tok(w["word"]) for w in words]
        for i in range(len(words) - len(find) + 1):
            if find and toks[i:i + len(find)] == find:
                j = i + len(find) - 1
                new = fx.get("text", "").split()
                t0, t1 = words[i]["start"], words[j]["end"]
                if not new:                           # an empty replacement drops the words
                    del words[i:j + 1]
                    break
                words[i:j + 1] = [{"word": tok, "start": round(t0 + (t1 - t0) * k / len(new), 3), "end": round(t0 + (t1 - t0) * (k + 1) / len(new), 3)} for k, tok in enumerate(new)]
                break
    return words


def build_captions(words):
    """[{"t0", "t1", "words": [{"text", "t0", "t1"}]}]: phrases of up to three words, cut at punctuation, each word on its own time."""
    phrases, cur = [], []
    for w in words:
        cur.append(w)
        chars = sum(len(x["word"]) for x in cur) + len(cur) - 1
        if len(cur) >= 3 or w["word"][-1:] in ",.?!" or chars >= 16:
            phrases.append(cur)
            cur = []
    if cur:
        if phrases and len(cur) == 1 and len(cur[0]["word"]) <= 4 and len(phrases[-1]) < 3 and phrases[-1][-1]["word"][-1:] not in ".?!":
            phrases[-1] += cur
        else:
            phrases.append(cur)
    out = []
    for i, ph in enumerate(phrases):
        nxt = phrases[i + 1][0]["start"] if i + 1 < len(phrases) else 1e9
        t1 = min(ph[-1]["end"] + 0.30, nxt)
        ws = []
        for k, x in enumerate(ph):
            text = re.sub(r"[:;]", "", x["word"]).upper().rstrip(".,")
            ws.append({"text": text, "t0": x["start"], "t1": ph[k + 1]["start"] if k + 1 < len(ph) else t1})
        out.append({"t0": ph[0]["start"], "t1": t1, "words": [w for w in ws if w["text"]]})
    return [c for c in out if c["words"]]


ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}


def plan_points(words):
    """A card for every numbered point: "the second thing I learned, never get on a call without a clear objective" -> a 2 badge and the line."""
    out = []
    for i, w in enumerate(words[:-1]):
        n = ORDINALS.get(norm_tok(w["word"]))
        if not n or norm_tok(words[i + 1]["word"]) != "thing":
            continue
        j = i + 2
        while j < len(words) and norm_tok(words[j]["word"]) in ("i", "learned", "is", "was", "that", "the", "easiest", "way") and j < i + 5:
            j += 1
        line = []
        for x in words[j:j + 12]:
            line.append(re.sub(r"[:;]", "", x["word"]).rstrip(".,"))
            if x["word"][-1:] in ".?!" or len(line) >= 9:
                break
        t0 = words[max(0, i - 1)]["start"] if norm_tok(words[max(0, i - 1)]["word"]) == "the" else w["start"]
        txt = " ".join(line).strip()
        out.append({"type": "point", "number": n, "text": txt[:1].upper() + txt[1:], "t0": round(t0, 2), "t1": round(t0 + 4.0, 2)})
    return out


def plan_punches(words, dur):
    """Punch-in zooms on the lines that matter: sentence starts that carry a numbered point or a strong word, spaced out, never in the first 3 seconds."""
    strong = {"never", "always", "clear", "objective", "secret", "mistake", "biggest", "only", "framework", "nothing", "everything", "constantly", "hours"}
    cands, start = [], 0
    for i, w in enumerate(words):
        if w["word"][-1:] in ".?!" or i == len(words) - 1:
            sent = words[start:i + 1]
            start = i + 1
            if not sent or sent[0]["start"] < MIN_START + 0.2:
                continue
            toks = [norm_tok(x["word"]) for x in sent]
            ordinal = any(toks[k] in ORDINALS and k + 1 < len(toks) and toks[k + 1] == "thing" for k in range(len(toks)))
            score = (3 if ordinal else 0) + 2 * len(strong & set(toks)) + (1 if any(_num(x["word"]) for x in sent) else 0)
            if score:
                cands.append((score, sent[0]["start"], min(1.6, max(0.8, (sent[-1]["end"] - sent[0]["start"]) * 0.45))))
    cands.sort(key=lambda c: (-c[0], c[1]))
    chosen = []
    for sc, t, hold in cands:
        if all(abs(t - c[0]) >= 7.0 for c in chosen) and len(chosen) < max(2, int(dur / 8)):
            chosen.append((t, round(hold, 2)))
    return [{"t": round(t, 2), "hold": hold, "amount": 0.14} for t, hold in sorted(chosen)]


GRADES = {      # colour grades for the picture under the graphics (the graphics keep their own colours)
    # old money: muted warm tones, softly lifted blacks, a brown-black shadow, a dark vignette and a little film grain
    "oldmoney": "eq=contrast=0.97:saturation=0.74,curves=all='0/0.04 0.25/0.24 0.5/0.5 0.85/0.84 1/0.93',"
                "colorbalance=rs=0.04:gs=0.01:bs=-0.03:rm=0.03:bm=-0.03:rh=0.05:gh=0.02:bh=-0.05,vignette=angle=PI/3.2,noise=alls=6:allf=t",
}


def zoom_expr(punches):
    """ffmpeg expression of time for the zoom factor: 1, plus each punch rising fast (0.12 s), holding, and easing back (0.3 s)."""
    terms = []
    for p in punches:
        a, up, h, dn, amt = p["t"], 0.12, p.get("hold", 1.0), 0.30, p.get("amount", 0.14)
        b = a + up + h
        terms.append(f"{amt}*(between(t,{a:.3f},{a + up:.3f})*(1-pow(1-(t-{a:.3f})/{up},3))+between(t,{a + up:.3f},{b:.3f})+between(t,{b:.3f},{b + dn:.3f})*pow(1-(t-{b:.3f})/{dn},2))")
    return "(1+" + "+".join(terms) + ")"


# ------------------------------------------------------------------ drawing
_FONTS = {}


def font(name, px):
    key = (name, int(round(px)))
    if key not in _FONTS:
        _FONTS[key] = ImageFont.truetype(str(FONT_DIR / f"{name}.ttf"), key[1] * SS)
    return _FONTS[key]


def ease_out(v, p=3):
    return 1 - (1 - max(0.0, min(1.0, v))) ** p


def back_out(v, s=2.0):
    v = max(0.0, min(1.0, v)) - 1
    return v * v * ((s + 1) * v + s) + 1


def zone_box(info, zone):
    """(x0, y0, x1, y1) in pixels where a card may be. Never the left and right 10%, never the bottom third, and for upright video not the face
    (a talking head's face is in the upper half: the band under the chin down to the caption area)."""
    w, h = info["w"], info["h"]
    if zone == "right" or (zone == "auto" and w > h):
        return int(w * 0.58), int(h * 0.22), int(w * (1 - SIDE)), int(h * 0.62)
    if zone == "top":
        return int(w * SIDE), int(h * 0.03), int(w * (1 - SIDE)), int(h * 0.215)
    return int(w * SIDE), int(h * 0.455), int(w * (1 - SIDE)), int(h * 0.655)


_BASE = {}


def card_base(w, h, r):
    """The white rounded card with a soft shadow, as an RGBA layer (2x), cached by size. Returns (image, margin)."""
    key = (w, h, r)
    if key not in _BASE:
        m = int(36 * SS)
        im = Image.new("RGBA", (w * SS + 2 * m, h * SS + 2 * m), (0, 0, 0, 0))
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([m, m + 10 * SS, m + w * SS, m + h * SS + 10 * SS], r * SS, fill=(0, 0, 0, 70))
        im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(14 * SS)))
        ImageDraw.Draw(im).rounded_rectangle([m, m, m + w * SS, m + h * SS], r * SS, fill=(255, 255, 255, 245), outline=(255, 255, 255, 255), width=2 * SS)
        _BASE[key] = (im, m)
    return _BASE[key]


def fit_font(name, texts, maxw, px, floor=18):
    while px > floor and max(font(name, px).getlength(t) for t in texts) / SS > maxw:
        px -= 2
    return px


def fmt_number(v, m):
    s = f"{v:,.{m['dec']}f}"
    return f"{m['prefix']}{s}{m['suffix']}"


def draw_check(d, cx, cy, r, p):
    """A green disc with a white tick drawn on as p goes 0..1."""
    s = max(0.0, back_out(p, 2.2)) if p < 1 else 1.0
    rr = r * s
    if rr < 1:
        return
    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=GREEN)
    q = max(0.0, (p - 0.35) / 0.65)
    pts = [(cx - rr * 0.42, cy + rr * 0.02), (cx - rr * 0.1, cy + rr * 0.34), (cx + rr * 0.46, cy - rr * 0.3)]
    seg = [math.dist(pts[0], pts[1]), math.dist(pts[1], pts[2])]
    run = q * sum(seg)
    path = [pts[0]]
    for k in range(2):
        if run <= 0:
            break
        f = min(1.0, run / seg[k])
        path.append((pts[k][0] + (pts[k + 1][0] - pts[k][0]) * f, pts[k][1] + (pts[k + 1][1] - pts[k][1]) * f))
        run -= seg[k]
    if len(path) > 1:
        d.line(path, fill=(255, 255, 255), width=max(2, int(rr * 0.2)), joint="curve")


def card_geometry(m, info, box):
    """Card size (1x px) and layout numbers for moment m inside the zone box."""
    x0, y0, x1, y1 = box
    zw, zh = x1 - x0, y1 - y0
    k = info["w"] / 1080.0
    if m["type"] == "checklist":
        pad = 40 * k
        rows = len(m["items"])
        rowh = min(96 * k, (zh - 2 * pad) / rows)
        px = fit_font("Inter-700", [i["text"] for i in m["items"]], zw - 2 * pad - rowh * 1.1, rowh * 0.46)
        widest = max(font("Inter-700", px).getlength(i["text"]) / SS for i in m["items"])
        w = min(zw, widest + 2 * pad + rowh * 1.1)
        h = rows * rowh + 2 * pad
        return {"w": int(w), "h": int(h), "pad": pad, "rowh": rowh, "px": px, "r": int(30 * k)}
    if m["type"] == "point":
        pad = 40 * k
        badge = 92 * k if m.get("number") else 0
        gap = 26 * k if badge else 0
        maxw = zw - 2 * pad - badge - gap
        px = 56 * k
        while True:
            f = font("Inter-700", px)
            lines, cur = [], ""
            for wd in m["text"].split():
                trial = (cur + " " + wd).strip()
                if cur and f.getlength(trial) / SS > maxw:
                    lines.append(cur)
                    cur = wd
                else:
                    cur = trial
            lines.append(cur)
            if (len(lines) <= 2 and max(f.getlength(x) for x in lines) / SS <= maxw) or px <= 28 * k:
                break
            px -= 3
        h = max(len(lines) * px * 1.22 + 2 * pad, badge + 2 * pad)
        w = min(zw, max(f.getlength(x) for x in lines) / SS + 2 * pad + badge + gap)
        return {"w": int(w), "h": int(min(h, zh)), "pad": pad, "badge": badge, "gap": gap, "px": px, "lines": lines, "r": int(30 * k)}
    pad = 38 * k
    big = fit_font("SpaceGrotesk-700", [fmt_number(max(m["from"], m["to"]), m)], zw - 2 * pad, min(190 * k, zh * 0.5))
    lab = max(16 * k, big * 0.17)
    h = pad * 2 + lab * 1.5 + big * 1.0 + (lab * 1.4 if m.get("was") else 0)
    wnum = font("SpaceGrotesk-700", big).getlength(fmt_number(max(m["from"], m["to"]), m)) / SS
    w = min(zw, max(wnum, 4 * lab * 5) + 2 * pad)
    return {"w": int(w), "h": int(min(h, zh)), "pad": pad, "big": big, "lab": lab, "r": int(30 * k)}


def render_card(m, geo, t):
    """RGBA (1x) of the card of moment m at time t seconds after the moment began, and its centre offset; None while it is not on screen."""
    life = m["t1"] - m["t0"]
    a_in = ease_out(t / 0.6)
    a_out = 1.0 - ease_out((t - (life - 0.3)) / 0.3, 2)
    alpha = max(0.0, min(1.0, a_in * a_out))
    if alpha <= 0.003:
        return None
    w, h = geo["w"], geo["h"]
    base, mg = card_base(w, h, geo["r"])
    im = base.copy()
    d = ImageDraw.Draw(im)
    ox, oy = mg, mg
    if m["type"] == "checklist":
        rowh, pad, px = geo["rowh"], geo["pad"], geo["px"]
        f = font("Inter-700", px)
        for k, it in enumerate(m["items"]):
            p = (t + m["t0"] - it["t"]) / 0.45
            if p <= 0:
                continue
            cy = oy + (pad + rowh * (k + 0.5)) * SS
            slide = (1 - ease_out(p)) * 24 * SS
            tcol = tuple(int(255 + (c - 255) * min(1.0, p * 2.2)) for c in INK)
            draw_check(d, ox + (pad + rowh * 0.4) * SS, cy, rowh * 0.34 * SS, p)
            d.text((ox + (pad + rowh * 1.0) * SS + slide, cy), it["text"], font=f, fill=tcol, anchor="lm")
    elif m["type"] == "point":
        pad, badge, gap, px = geo["pad"], geo["badge"], geo["gap"], geo["px"]
        cy = oy + geo["h"] * SS / 2
        if badge:
            bx = ox + (pad + badge / 2) * SS
            d.ellipse([bx - badge / 2 * SS, cy - badge / 2 * SS, bx + badge / 2 * SS, cy + badge / 2 * SS], fill=INK)
            d.text((bx, cy), str(m["number"]), font=font("SpaceGrotesk-700", badge * 0.56), fill=(255, 255, 255), anchor="mm")
        f = font("Inter-700", px)
        lh = px * 1.22 * SS
        y0 = cy - lh * len(geo["lines"]) / 2 + lh / 2
        for k_, ln in enumerate(geo["lines"]):
            p_ = (t - 0.12 * k_) / 0.5
            if p_ <= 0:
                continue
            col = tuple(int(255 + (c - 255) * min(1.0, p_ * 2.0)) for c in INK)
            d.text((ox + (pad + badge + gap) * SS + (1 - ease_out(p_)) * 20 * SS, y0 + k_ * lh), ln, font=f, fill=col, anchor="lm")
    else:
        pad, big, lab = geo["pad"], geo["big"], geo["lab"]
        tt = t + m["t0"]
        r0, r1 = m["roll"]
        q = ease_out((tt - r0) / max(0.3, r1 - r0), 3)
        val = m["from"] + (m["to"] - m["from"]) * q
        y = oy + pad * SS
        if m["label"]:
            d.text((ox + geo["w"] * SS / 2, y + lab * 0.7 * SS), m["label"].upper(), font=font("Inter-400", lab), fill=MUTED, anchor="mm")
        y += lab * 1.5 * SS
        d.text((ox + geo["w"] * SS / 2, y + big * 0.52 * SS), fmt_number(val, m), font=font("SpaceGrotesk-700", big), fill=INK, anchor="mm")
        if m.get("was"):
            y += big * 1.02 * SS
            d.text((ox + geo["w"] * SS / 2, y + lab * 0.5 * SS), f"up from {m['was']}", font=font("Inter-400", lab * 0.95), fill=MUTED, anchor="mm")
    # arrive: rise 30 px and scale up from 0.96
    sc = (0.96 + 0.04 * a_in)
    im = im.resize((int(im.width * sc / SS), int(im.height * sc / SS)), Image.LANCZOS)
    if alpha < 0.995:
        im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
    return im, mg * sc / SS, (1 - a_in) * 30


# ------------------------------------------------------------------ frames
CAPF = "ArchivoBlack-400"
LIME, WHITE = (198, 255, 61), (255, 255, 255)
_CAPL = {}


def cap_layer(text, px, fill):
    """One caption word as an RGBA layer at 1x with a black outline (readable on any picture): (image, origin x, baseline y)."""
    key = (text, int(px), fill)
    if key not in _CAPL:
        if len(_CAPL) > 600:
            _CAPL.clear()
        f = font(CAPF, px)
        st = max(2, int(px * 0.075 * SS))
        asc, desc = f.getmetrics()
        w = int(f.getlength(text)) + 2 * st + 8
        im = Image.new("RGBA", (w, asc + desc + 2 * st + 8), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((st + 4, st + 4 + asc), text, font=f, fill=fill + (255,), anchor="ls", stroke_width=st, stroke_fill=(0, 0, 0, 255))
        sm = im.resize((max(1, im.width // SS), max(1, im.height // SS)), Image.LANCZOS)
        _CAPL[key] = (sm, (st + 4) / SS, (st + 4 + asc) / SS)
    return _CAPL[key]


def draw_caption(canvas, info, ph, t):
    k = info["w"] / 1080.0
    px = int(80 * k)
    texts = [w["text"] for w in ph["words"]]
    f = font(CAPF, px)
    space = f.getlength(" ") / SS
    total = sum(f.getlength(x) / SS for x in texts) + space * (len(texts) - 1)
    maxw = info["w"] * (1 - 2 * SIDE)
    if total > maxw:
        px = int(px * maxw / total)
        f = font(CAPF, px)
        space = f.getlength(" ") / SS
    shown = [w_["text"] for w_ in ph["words"] if w_["t0"] <= t]           # the words said so far stay centred as the phrase grows
    x = (info["w"] - (sum(f.getlength(x_) / SS for x_ in shown) + space * (len(shown) - 1))) / 2
    base = info["h"] * 0.80
    fade = 1.0 - ease_out((t - (ph["t1"] - 0.08)) / 0.08, 1)
    for wd in ph["words"]:
        ww = f.getlength(wd["text"]) / SS
        if wd["t0"] > t:
            break
        p = (t - wd["t0"]) / 0.14
        if p > 0:
            lay, ox, oy = cap_layer(wd["text"], px, LIME if wd["t0"] <= t < wd["t1"] else WHITE)
            sc = 0.78 + 0.22 * back_out(p, 1.8) if p < 1 else 1.0
            if sc != 1.0:
                lay = lay.resize((max(1, int(lay.width * sc)), max(1, int(lay.height * sc))), Image.BILINEAR)
            if fade < 0.995:
                lay = lay.copy()
                lay.putalpha(lay.getchannel("A").point(lambda v: int(v * fade)))
            px_, py_ = int(x + ww * (1 - sc) / 2 - ox * sc), int(base - oy * sc)
            canvas.alpha_composite(lay, dest=(max(px_, 0), max(py_, 0)), source=(max(-px_, 0), max(-py_, 0)))
        x += ww + space


class Frames:
    """Every frame of the graphics alone: transparent RGBA bytes, one per video frame."""

    def __init__(self, info, moments, zone, captions=None):
        self.captions = captions or []
        self.info, self.moments = info, moments
        self.box = zone_box(info, zone)
        self.geo = [card_geometry(m, info, self.box) for m in moments]
        self.n = int(round(info["dur"] * info["fps"]))
        self.blank = bytes(info["w"] * info["h"] * 4)

    def frame(self, f):
        t = f / self.info["fps"]
        canvas = None
        for m, geo in zip(self.moments, self.geo):
            if m["t0"] <= t <= m["t1"]:
                got = render_card(m, geo, t - m["t0"])
                if got is None:
                    break
                im, mg, rise = got
                x0, y0, x1, y1 = self.box
                canvas = Image.new("RGBA", (self.info["w"], self.info["h"]), (0, 0, 0, 0))
                cx = (x0 + x1) / 2
                cy = (y0 + y1) / 2
                x, y = int(cx - im.width / 2), int(cy - im.height / 2 + rise)
                canvas.alpha_composite(im, dest=(max(x, 0), max(y, 0)), source=(max(-x, 0), max(-y, 0)))
                break
        for ph in self.captions:
            if ph["t0"] <= t <= ph["t1"]:
                if canvas is None:
                    canvas = Image.new("RGBA", (self.info["w"], self.info["h"]), (0, 0, 0, 0))
                draw_caption(canvas, self.info, ph, t)
                break
        return canvas.tobytes() if canvas is not None else self.blank


# ------------------------------------------------------------------ sound (the kit's rule: small clicks on what matters, ~20 dB under the voice)
def _decode(path):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", "48000", "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype=np.float32)


def _sound(name):
    for p in (ROOT / "library" / "sfx" / f"kit-{name}.wav", ROOT / "library" / "sfx" / f"{name}.wav"):
        if p.exists():
            return _decode(p)
    import sfx_gen
    sfx_gen.ensure_sfx()
    return _decode(sfx_gen.SFX_DIR / f"{'type' if name == 'counter' else name}.wav")


def sound_events(moments, punches=()):
    """[(time, sound)]: a tick per list item and numbered point, the counter sound while a number rolls, a soft snap on each punch-in, the chime on the last card."""
    ev = []
    for m in moments:
        if m["type"] == "checklist":
            ev += [(it["t"], "tick") for it in m["items"]]
        elif m["type"] == "point":
            ev.append((m["t0"] + 0.1, "tick"))
        else:
            ev.append((m["roll"][0], "counter"))
    ev += [(p["t"], "snap") for p in punches]
    if moments:
        last = moments[-1]
        if last["type"] == "counter":
            t_end = last["roll"][1]
        elif last["type"] == "checklist":
            t_end = last["items"][-1]["t"] + 0.25
        else:
            t_end = last["t0"] + 0.1
        ev.append((t_end, "chime"))
    return ev


def sound_track(src, info, moments, out_wav, punches=()):
    """A mono 48 kHz track of the effects, scaled to sit about 20 dB under the speech (by loudness)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(src), "-vn", "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr)
    mean_db = float(m.group(1)) if m else -24.0
    gain = 10 ** ((mean_db - 6.0) / 20.0)          # a short click peaking 6 dB under the voice's average level sits about 20 dB under the voice by loudness
    n = int((info["dur"] + 1) * 48000)
    track = np.zeros(n, dtype=np.float32)
    cache = {}
    for t, name in sound_events(moments, punches):
        x = cache.setdefault(name, _sound(name))
        x = x / (np.abs(x).max() or 1.0) * 0.85 * gain * {"tick": 0.7, "snap": 0.6}.get(name, 1.0)
        i = int(t * 48000)
        if i < n:
            seg = x[:n - i]
            track[i:i + len(seg)] += seg
    pcm = (np.clip(track, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(pcm.tobytes())
    return out_wav


# ------------------------------------------------------------------ encode
def _encoder(cq=19):
    r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1:r=24", "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True)
    if r.returncode == 0:
        return ["-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq", "-profile:v", "high", "-rc", "vbr", "-cq", str(cq), "-b:v", "0", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p"]


EVENTS = False          # the studio asks for progress as @@{json} lines (its job runner reads them)


def emit(event, **kw):
    if EVENTS:
        print("@@" + json.dumps(dict(event=event, **kw)), flush=True)


def _feed(proc, frames, lo=0.0, hi=1.0, what="drawing"):
    """Write every frame to ffmpeg; progress is reported between lo and hi (parts of the whole job)."""
    try:
        for f in range(frames.n):
            proc.stdin.write(frames.frame(f))
            if f % 12 == 0:
                emit("progress", segment=what, overall=round(lo + (hi - lo) * f / frames.n, 4))
            if f % 48 == 0:
                print(f"  frame {f}/{frames.n}", flush=True)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    return proc.wait()


def raw_input_args(info):
    return ["-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{info['w']}x{info['h']}", "-framerate", info["fps_str"], "-i", "-"]


def export_composite(src, info, frames, moments, out, sound=True, lo=0.0, hi=1.0, punches=(), grade=None):
    wav = None
    if sound and info["audio"] and (moments or punches):
        wav = sound_track(src, info, moments, Path(out).with_suffix(".sfx.wav"), punches)
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), *raw_input_args(info)]
    if wav:
        cmd += ["-i", str(wav)]
    W, H = info["w"], info["h"]
    steps = []
    if punches:       # the punch-ins zoom the picture (about a point just under the hair line, so the face stays out of the cards); the graphics are drawn after it and never zoom
        z = zoom_expr(punches)
        steps.append(f"scale=w='trunc({W}*{z}/2)*2':h='trunc({H}*{z}/2)*2':eval=frame:flags=bicubic,crop={W}:{H}:'(in_w-out_w)*0.5':'(in_h-out_h)*0.30'")
    if grade in GRADES:
        steps.append(GRADES[grade])
    fc = ("[0:v]" + ",".join(steps) + "[b];[b]" if steps else "[0:v]") + "[1:v]overlay=0:0:format=auto:shortest=1[v]"
    if wav:
        fc += ";[0:a][2:a]amix=inputs=2:duration=first:normalize=0[a]"
    cmd += ["-filter_complex", fc, "-map", "[v]"]
    if wav:
        cmd += ["-map", "[a]"]
    elif info["audio"]:
        cmd += ["-map", "0:a"]
    cmd += [*_encoder(25 if grade in GRADES else 19), "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)]
    code = _feed(subprocess.Popen(cmd, stdin=subprocess.PIPE), frames, lo, hi, "adding graphics to the video")
    if wav:
        Path(wav).unlink(missing_ok=True)
    return code


def export_transparent(info, frames, mov, png_dir, lo=0.0, hi=1.0):
    """ProRes 4444 with alpha and a PNG sequence from one pass over the frames."""
    Path(png_dir).mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error", *raw_input_args(info),
           "-map", "0:v", "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-vendor", "apl0", str(mov),
           "-map", "0:v", "-c:v", "png", "-pix_fmt", "rgba", str(Path(png_dir) / "%05d.png")]
    return _feed(subprocess.Popen(cmd, stdin=subprocess.PIPE), frames, lo, hi, "transparent export")


# ------------------------------------------------------------------ command line
def main(argv=None):
    ap = argparse.ArgumentParser(description="Motion graphics over your own video, plus a transparent export.")
    ap.add_argument("video")
    ap.add_argument("--out", help="the finished video (default output/<name>_overlay.mp4)")
    ap.add_argument("--zone", default="auto", choices=["auto", "chest", "top", "right"], help="where cards sit (auto: the band under the chin for upright video, the right for wide)")
    ap.add_argument("--plan", help="draw this plan file instead of planning again")
    ap.add_argument("--plan-only", action="store_true", help="write the plan and stop")
    ap.add_argument("--transparent", action="store_true", help="also write the graphics alone with alpha (.mov ProRes 4444 + PNG sequence)")
    ap.add_argument("--transparent-only", action="store_true", help="only the transparent files")
    ap.add_argument("--no-sound", action="store_true")
    ap.add_argument("--grade", choices=sorted(GRADES), help="colour grade for the picture (the plan file's \"grade\" does the same)")
    ap.add_argument("--full", action="store_true", help="a full edit: also spoken-word captions, punch-in zooms and a card for every numbered point")
    ap.add_argument("--outdir", help="where the finished files go (default output/)")
    ap.add_argument("--workdir", help="where the transcript and the plan are kept (default output/)")
    ap.add_argument("--events", action="store_true", help="report progress as @@{json} lines (for the studio)")
    a = ap.parse_args(argv)
    global EVENTS
    EVENTS = a.events
    src = Path(a.video).resolve()
    info = probe(src)
    name = src.stem
    out_dir = Path(a.outdir) if a.outdir else OUT_DIR
    work_dir = Path(a.workdir) if a.workdir else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    plan_path = Path(a.plan) if a.plan else work_dir / f"{name}.overlay.json"
    words_path = work_dir / f"{name}.words.json"
    if a.plan:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        words = None
    else:
        print("Transcribing...", flush=True)
        emit("progress", segment="listening to the speech", overall=0.03)
        words = transcribe(src, words_path)
        moments = plan_moments(words, info, a.zone, a.full)
        plan = {"video": src.name, "moments": moments}
        if a.full:
            plan.update({"captions": True, "punches": plan_punches(words, info["dur"]), "fixes": []})
        plan_path.write_text(json.dumps(plan, indent=1), encoding="utf-8")
    moments, punches = plan["moments"], plan.get("punches") or []
    captions = []
    if plan.get("captions"):
        if words is None:
            words = json.loads(words_path.read_text(encoding="utf-8")) if words_path.exists() else transcribe(src, words_path)
        captions = build_captions(apply_fixes(words, plan.get("fixes")))
    print(f"{len(moments)} moments, {len(punches)} punch-ins, {len(captions)} caption phrases:", flush=True)
    for m in moments:
        what = (m["label"] or "number") if m["type"] == "counter" else m["text"] if m["type"] == "point" else f"{len(m['items'])} items"
        print(f"  {m['t0']:6.2f}s to {m['t1']:6.2f}s  {m['type']:9s} {what}", flush=True)
    if a.plan_only:
        print(f"Plan written to {plan_path}")
        emit("done", path=str(plan_path), seconds=0)
        return 0
    frames = Frames(info, moments, a.zone, captions)
    if not a.transparent_only:
        out = Path(a.out) if a.out else out_dir / f"{name}_overlay.mp4"
        print("Compositing...", flush=True)
        two = a.transparent or a.transparent_only
        if export_composite(src, info, frames, moments, out, not a.no_sound, 0.1, 0.55 if two else 0.97, punches, a.grade or plan.get("grade")):
            raise SystemExit("ffmpeg failed")
        print(f"Video saved to: {out}")
        final = out
    if a.transparent or a.transparent_only:
        mov, png = out_dir / f"{name}_overlay.mov", out_dir / f"{name}_overlay_png"
        print("Transparent export...", flush=True)
        if export_transparent(info, frames, mov, png, 0.1 if a.transparent_only else 0.55, 0.97):
            raise SystemExit("ffmpeg failed")
        print(f"Transparent video: {mov}\nPNG sequence: {png}")
        final = mov if a.transparent_only else final
    emit("done", path=str(final), seconds=0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
