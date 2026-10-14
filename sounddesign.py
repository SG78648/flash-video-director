"""sounddesign.py - one sound design for every style: quiet effects on the things you see, and the music laid on the cuts.

The studio's timeline already holds a finished render, its narration and the effects the style made. "Sound design" looks at WHEN things happen on the video
(the hook turning into the body, every new frame or object, every camera move, every amount and decision) and does two jobs:

  1. effects: a small palette (sfx_gen: air, paper, boom, riser, thud, stamp, tick) placed on those moments, always far below the voice. The style's own
     busier effects (pops, dings, chimes, swooshes, key clicks) are not used, so every style sounds the same, calm and designed. `intensity` is off / light / full.
  2. music: the tempo, beats and bars of the chosen track (beats.py) are matched against the cuts. The track's in-point and its speed (within 6 percent, which is
     inaudible on music) are chosen so that the hook-to-body cut lands on a bar line and as many other cuts as possible land on a beat, a loop (a track shorter than
     the video) is cut on bar lines so it never skips, and the fade-out ends on the last frame. Effects are then nudged onto the nearest beat when one is within 60 ms.

Everything is in TIMELINE seconds (the edit the page is showing), the page does the mapping from the render's own times. The result is plain data the page
writes into the edit (free clips and one music clip), so it is visible, editable and undoable on the timeline like anything else.
"""
import math

import numpy as np

import beats as beats_mod
import music

LIGHT = {"boom": -19.0, "thud": -22.0, "stamp": -20.0, "air": -27.0}
FULL_EXTRA = {"paper": -26.0, "riser": -25.0, "tick": -29.0}
KEEP = {"thud": "thud", "stamp": "stamp", "kaching": "thud", "slam": "stamp"}          # what a style's own effect becomes (everything else is dropped)
SNAPPABLE = {"paper", "tick", "thud", "stamp", "air"}


def anchors(prog):
    """[(time, weight, kind)] the moments the music should line up with."""
    segs = prog.get("segments") or []
    out = []
    body = segs[1]["start"] if len(segs) > 1 else None
    if body is not None:
        out.append((body, 4.0, "body"))
    for a, _b in prog.get("beats") or []:
        if body is None or abs(a - body) > 0.2:
            out.append((a, 1.0, "beat"))
    for a, b in prog.get("pans") or []:
        out.append((b, 1.5, "pan"))
    if len(segs) > 2:
        out.append((segs[-1]["start"], 2.0, "outro"))
    return sorted(out)


def _grid(an, start_in, out_pt, speed, total, loop):
    """Beat times on the timeline for a track played from `start_in` to `out_pt` at `speed` (repeated when it loops), plus the bar starts."""
    b = np.array(an["beats"])
    d = np.array(an["downbeats"])
    L = (out_pt - start_in) / speed
    res_b, res_d = [], []
    n = 0
    while True:
        off = n * L
        if off > total + 1:
            break
        res_b += list((b[(b >= start_in - 1e-6) & (b < out_pt - 1e-6)] - start_in) / speed + off)
        res_d += list((d[(d >= start_in - 1e-6) & (d < out_pt - 1e-6)] - start_in) / speed + off)
        n += 1
        if not loop:
            break
    return np.array(res_b), np.array(res_d), L


def _near(grid, times):
    """Distance from each time to the nearest grid point."""
    idx = np.clip(np.searchsorted(grid, times), 1, len(grid) - 1)
    return np.minimum(np.abs(grid[idx] - times), np.abs(grid[idx - 1] - times))


def _score(tb, td, anc, body):
    """How well the cuts sit on the music: a full mark for a cut on a beat, 0.6 for one on the half beat between two, a bonus for the hook cut on a bar line."""
    if len(tb) < 3:
        return -1e9, 0
    times = np.array([a[0] for a in anc])
    w = np.array([a[1] for a in anc])
    mids = (tb[1:] + tb[:-1]) / 2
    d1, d2 = _near(tb, times), _near(mids, times)
    s = float((w * np.maximum(np.exp(-(d1 / 0.05) ** 2), 0.6 * np.exp(-(d2 / 0.05) ** 2))).sum())
    hits = int(((d1 < 0.06) | (d2 < 0.06)).sum())
    if body is not None and len(td):
        s += 3.0 * math.exp(-((np.abs(td - body).min()) / 0.05) ** 2)          # the hook cut on a bar line
    return s, hits


def align(prog, track_name, total):
    """Best (in point, speed, loop) for the track under this video. Returns None when the track cannot be analysed."""
    p = music.path_of(track_name) or music.library_path(track_name)
    if not p:
        return None
    an = beats_mod.analyze(p)
    anc = anchors(prog)
    segs = prog.get("segments") or []
    body = segs[1]["start"] if len(segs) > 1 else None
    td = an["duration"]
    if len(an["beats"]) < 8:
        return {"analysis": an, "in": 0.0, "speed": 1.0, "loop": False, "out": td, "score": 0.0, "hits": 0}
    down = np.array(an["downbeats"]) if an["downbeats"] else np.array(an["beats"][::4])
    best = None
    for speed in (1.0, 0.99, 1.01, 0.98, 1.02, 0.97, 1.03, 0.96, 1.04, 0.95, 1.05, 0.94, 1.06):
        need = total * speed
        loop = td < need - 1.0                                   # only a track that is clearly too short is looped (a near fit just ends a little early, with its fade)
        cands = down if len(down) else np.array(an["beats"])
        for k0 in cands:
            if loop:
                outs = down[(down > k0 + 10.0) & (down <= td - 0.05)]
                if not len(outs):
                    continue
                out_pt = float(outs[-1])
                inn = float(k0)
            else:
                # the in-point is chosen so that a bar line sits on the hook cut (or on the very start when there is no cut)
                a0 = body if body is not None else 0.0
                inn = float(k0) - a0 * speed
                if inn < 0 or inn + need > td + 1.5:
                    continue
                out_pt = min(td, inn + need + 0.5)
            tb, tdn, L = _grid(an, inn, out_pt, speed, total, loop)
            s, hits = _score(tb, tdn, anc, body)
            s -= 0.35 * abs(speed - 1.0) / 0.01 * 0.1          # prefer the music untouched when the gain is small
            s -= 0.02 * inn                                       # and the start of the track over a late part of it (a loop of the last bars is a poor choice)
            if best is None or s > best["score"]:
                best = {"in": round(inn, 3), "speed": speed, "loop": loop, "out": round(out_pt, 3), "score": round(s, 2), "hits": hits, "L": L}
    if best is None:                                            # nothing fits (a very short track): play it from the start, looped
        best = {"in": 0.0, "speed": 1.0, "loop": td < total, "out": td, "score": 0.0, "hits": 0, "L": td}
    best["analysis"] = {k: an[k] for k in ("bpm", "duration", "drop")}
    best["anchors"] = len(anc)
    best["_beats"] = an
    return best


def _tl_beats(best, total):
    tb, td, _L = _grid(best["_beats"], best["in"], best["out"], best["speed"], total, best["loop"])
    return tb, td


def sfx_plan(prog, intensity, total):
    """[(time, name, gain_db)] the designed effects for this video."""
    if intensity == "off":
        return []
    segs = prog.get("segments") or []
    body = segs[1]["start"] if len(segs) > 1 else None
    ev = []
    if body is not None and body > 0.8:
        ev.append((body - 0.02, "boom", LIGHT["boom"]))
        if intensity == "full":
            ev.append((body - 1.4, "riser", FULL_EXTRA["riser"]))
    pans = prog.get("pans") or []
    for a, b in pans:
        ev.append((a + 0.12, "air", LIGHT["air"]))
    if len(segs) > 2 and pans:
        ev.append((segs[-1]["start"] - 0.35, "air", LIGHT["air"]))
    for e in prog.get("sfx") or []:
        nm = KEEP.get(e.get("name"))
        if nm:
            ev.append((float(e["t"]), nm, LIGHT[nm]))
        elif intensity == "full" and e.get("name") in ("pop", "tick", "ding"):
            ev.append((float(e["t"]), "tick", FULL_EXTRA["tick"]))
    if intensity == "full":
        for a, _b in prog.get("beats") or []:
            if body is not None and abs(a - body) < 0.3:
                continue
            if any(abs(a - pb) < 0.7 for _pa, pb in pans):          # a camera move already carries this frame
                continue
            ev.append((a - 0.04, "paper", FULL_EXTRA["paper"]))
    return sorted((round(max(0.0, t), 3), n, g) for t, n, g in ev if t < total - 0.05)


def _snap(events, tb, td, drop_tl):
    out = []
    for t, n, g in events:
        if n in SNAPPABLE and len(tb):
            j = int(np.argmin(np.abs(tb - t)))
            if abs(tb[j] - t) <= 0.06:
                t = float(tb[j])
        out.append((round(t, 3), n, g))
    return out


def design(prog, track_name=None, intensity="light", snap=True):
    """The whole design as plain data: {"sfx": [...], "music": {...} | None, "notes": [...]}."""
    total = float(prog.get("total") or (prog["segments"][-1]["end"] if prog.get("segments") else 0))
    notes = []
    m = None
    best = None
    if track_name:
        best = align(prog, track_name, total)
        if best:
            a = best["analysis"]
            m = {"name": track_name, "in": best["in"], "out": best["out"], "speed": best["speed"], "loop": best["loop"], "span": round(total, 3),
                 "fi": 0.4, "fo": min(2.5, max(1.0, total * 0.05))}
            notes.append(f"{a['bpm']:.0f} BPM" + (f", sped {abs(best['speed'] - 1) * 100:.0f}% {'down' if best['speed'] < 1 else 'up'} to fit" if best["speed"] != 1.0 else ", played at its own speed"))
            notes.append(f"{best['hits']} of {best['anchors']} cuts land on the beat grid")
            if best["loop"]:
                notes.append("the track is shorter than the video, so it loops on a bar line")
    ev = sfx_plan(prog, intensity, total)
    if snap and best:
        tb, td = _tl_beats(best, total)
        ev = _snap(ev, tb, td, None)
        # the boom lands on a bar line when one is within a quarter of a second
        if len(td):
            ev = [((float(td[int(np.argmin(np.abs(td - t)))]) if n == "boom" and abs(td[int(np.argmin(np.abs(td - t)))] - t) < 0.25 else t), n, g) for t, n, g in ev]
    return {"sfx": [{"name": n, "start": round(t, 3), "gain": g} for t, n, g in ev], "music": m, "notes": notes,
            "analysis": best["analysis"] if best else None, "score": best["score"] if best else None, "total": total}
