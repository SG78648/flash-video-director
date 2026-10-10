"""tighten.py - shortens the long silences of a narration clip (Lee style, fast pace).

The voice leaves roughly 0.8 s of silence after every sentence. Fast pace keeps each gap between two words at
most GAP seconds by cutting the middle out of the silence, then moves every word timing to match, so beats, pans
and sound cues follow the shorter audio without any other change.

The untouched narration lives in <audio|timing>/orig/ so calm pace (or a different GAP) can always rebuild from it,
and a freshly generated clip (no "tight" key in its timing file) simply replaces the saved original.
"""
import json
import shutil
import subprocess
from pathlib import Path

GAP = 0.30            # longest silence left between two words
TAIL = 0.12           # silence left after the last word


def _plan(words, duration, gap, tail):
    """[(keep_from, keep_to)] of the original clip and the new (start, end) of every word."""
    cuts = []
    for a, b in zip(words, words[1:]):
        silence = b["start"] - a["end"]
        if silence > gap + 0.02:
            cuts.append((a["end"] + gap / 2, b["start"] - gap / 2))
    end = words[-1]["end"] + tail
    if duration - end > 0.05:
        cuts.append((end, duration))
    keep, pos = [], 0.0
    for c0, c1 in cuts:
        keep.append((pos, c0))
        pos = c1
    if pos < duration - 1e-3:
        keep.append((pos, duration))
    return keep, cuts


def _shift(t, cuts):
    return t - sum(min(c1, t) - c0 for c0, c1 in cuts if t > c0)


def _cut_audio(src, dst, keep):
    parts = "".join(f"[0:a]atrim=start={a:.4f}:end={b:.4f},asetpts=PTS-STARTPTS[s{i}];" for i, (a, b) in enumerate(keep))
    chain = "".join(f"[s{i}]" for i in range(len(keep)))
    graph = f"{parts}{chain}concat=n={len(keep)}:v=0:a=1[out]"
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-filter_complex", graph, "-map", "[out]",
                        "-c:a", "libmp3lame", "-q:a", "2", str(dst)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("tighten: " + r.stderr[-400:])


def apply(audio_dir, timing_dir, ids, fast, gap=GAP, tail=TAIL):
    """Bring every clip of `ids` to the requested state (tight for fast pace, original for calm). Returns the seconds saved."""
    audio_dir, timing_dir = Path(audio_dir), Path(timing_dir)
    saved = 0.0
    for cid in ids:
        a_path, t_path = audio_dir / f"clip{cid}.mp3", timing_dir / f"clip{cid}.json"
        if not (a_path.exists() and t_path.exists()):
            continue
        cur = json.loads(t_path.read_text(encoding="utf-8"))
        oa, ot = audio_dir / "orig" / f"clip{cid}.mp3", timing_dir / "orig" / f"clip{cid}.json"
        if "tight" not in cur:                      # a freshly generated clip: keep it as the original
            oa.parent.mkdir(parents=True, exist_ok=True)
            ot.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(a_path, oa)
            shutil.copy(t_path, ot)
            cur_tight = None
        else:
            cur_tight = cur["tight"]
        want = round(gap, 3) if fast else None
        if cur_tight == want:
            continue
        base = json.loads(ot.read_text(encoding="utf-8"))
        if not fast or not base.get("words"):
            shutil.copy(oa, a_path)
            out = dict(base)
        else:
            keep, cuts = _plan(base["words"], float(base["duration"]), gap, tail)
            if not cuts:
                shutil.copy(oa, a_path)
                out = dict(base)
            else:
                _cut_audio(oa, a_path, keep)
                out = dict(base)
                out["words"] = [dict(w, start=round(_shift(w["start"], cuts), 6), end=round(_shift(w["end"], cuts), 6))
                                for w in base["words"]]
                out["duration"] = round(_shift(float(base["duration"]), cuts), 6)
                saved += float(base["duration"]) - out["duration"]
        if want is not None:
            out["tight"] = want
        else:
            out.pop("tight", None)
        t_path.write_text(json.dumps(out), encoding="utf-8")
    return saved
