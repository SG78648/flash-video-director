"""beats.py - the beat grid of a music file: tempo, every beat, the bar starts, and where the music "drops".

No extra libraries (numpy and ffmpeg only). The method is the classic one: an onset-strength curve (how much new energy appears in each 11 ms frame, per
frequency band), the tempo from its autocorrelation, then a dynamic-programming pass that picks the beat times that line up best with the onsets at that tempo
(Ellis 2007). Bars are found by asking which of the four beat positions carries the most low-frequency energy. Results are cached next to the music.

    analyze(path) -> {"bpm", "beats": [s...], "downbeats": [s...], "duration", "drop": s or None, "energy": [[s, 0..1]...]}
"""
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np

import projects

SR = 22050
N_FFT = 1024
HOP = 256
FRAME = HOP / SR
CACHE = projects.LIB_CACHE / "beats"
REV = 2


def _decode(path, max_s=300):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-t", str(max_s), "-vn", "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"], capture_output=True)
    if r.returncode != 0 or not r.stdout:
        raise ValueError("could not read that audio file")
    return np.frombuffer(r.stdout, dtype=np.float32)


def _stft_mag(x):
    win = np.hanning(N_FFT).astype(np.float32)
    n = 1 + (len(x) - N_FFT) // HOP
    if n < 8:
        raise ValueError("that audio is too short to find a beat")
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n)[:, None]
    return np.abs(np.fft.rfft(x[idx] * win, axis=1)).astype(np.float32)


def _bands(mag, n_bands=40):
    """Magnitudes folded into log-spaced bands (30 Hz to 8 kHz)."""
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / SR)
    edges = np.geomspace(30, 8000, n_bands + 1)
    out = np.zeros((mag.shape[0], n_bands), dtype=np.float32)
    for b in range(n_bands):
        m = (freqs >= edges[b]) & (freqs < edges[b + 1])
        if m.any():
            out[:, b] = mag[:, m].sum(axis=1)
    return out


def onset_strength(x):
    mag = _stft_mag(x)
    bands = np.log1p(_bands(mag) * 8.0)
    flux = np.maximum(0.0, bands[1:] - bands[:-1]).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    k = int(0.5 / FRAME)                                              # subtract a local mean: what is new compared with the last half second
    local = np.convolve(flux, np.ones(k) / k, mode="same")
    env = np.maximum(0.0, flux - local)
    p = np.percentile(env, 99) or 1.0
    return np.clip(env / p, 0, 1.5), bands


def _tempo(env):
    """The tempo (BPM) whose period best explains the onset curve, with a gentle preference for 70 to 150 BPM (where music usually sits)."""
    e = env - env.mean()
    n = len(e)
    ac = np.correlate(e, e, mode="full")[n - 1:]
    ac = ac / (ac[0] + 1e-9)
    lo, hi = int(60.0 / (190 * FRAME)), int(60.0 / (60 * FRAME))
    lags = np.arange(lo, hi)
    bpm = 60.0 / (lags * FRAME)
    prior = np.exp(-0.5 * (np.log2(bpm / 112.0) / 0.55) ** 2)
    # a lag and its double are both candidates: add the support of the multiples so the true beat beats its sub-multiples
    score = ac[lags] * prior
    for mult in (2, 3, 4):
        idx = lags * mult
        ok = idx < len(ac)
        score[ok] += 0.5 * ac[idx[ok]] * prior[ok] / mult
    best = lags[int(np.argmax(score))]
    # parabolic refinement of the peak
    if 1 <= best < len(ac) - 1:
        a, b, c = ac[best - 1], ac[best], ac[best + 1]
        d = (a - 2 * b + c)
        best = best + (0.5 * (a - c) / d if abs(d) > 1e-9 else 0.0)
    return 60.0 / (best * FRAME), best


def _beat_track(env, period):
    """Ellis dynamic programming: the beat sequence with the best onsets and the steadiest spacing near `period` frames."""
    n = len(env)
    local = np.convolve(env, np.hanning(max(3, int(period / 4) * 2 + 1)), mode="same")
    cum = local.copy()
    back = np.full(n, -1, dtype=np.int64)
    tight = 100.0
    lo, hi = int(round(period * 0.6)), int(round(period * 1.7))
    for i in range(n):
        a, b = i - hi, i - lo
        if b < 0:
            continue
        a = max(0, a)
        prev = np.arange(a, b + 1)
        pen = -tight * np.log((i - prev) / period) ** 2
        cand = cum[prev] + pen
        k = int(np.argmax(cand))
        cum[i] = local[i] + cand[k]
        back[i] = prev[k]
    end = int(np.argmax(cum[-int(period):])) + n - int(period) if n > period else int(np.argmax(cum))
    beats = [end]
    while back[beats[-1]] >= 0:
        beats.append(int(back[beats[-1]]))
    return np.array(beats[::-1])


def analyze(path):
    path = Path(path)
    key = hashlib.sha1(f"{path.resolve()}|{path.stat().st_mtime_ns}|{path.stat().st_size}|{REV}".encode()).hexdigest()[:20]
    cf = CACHE / f"{key}.json"
    try:
        return json.loads(cf.read_text(encoding="utf-8"))
    except Exception:
        pass
    x = _decode(path)
    dur = len(x) / SR
    env, bands = onset_strength(x)
    bpm, lag = _tempo(env)
    idx = _beat_track(env, lag)
    beats = idx * FRAME + 0.5 * N_FFT / SR            # frame centre
    # bars: which of the four beat positions has the most bass energy (kick on the one)
    bass = np.maximum(0.0, np.log1p(_bands(_stft_mag(x), 12)[:, :4].sum(axis=1)))
    bass = np.convolve(bass, np.ones(3) / 3, mode="same")
    pos = np.array([bass[min(len(bass) - 1, i)] for i in idx])
    phase = int(np.argmax([pos[p::4].sum() for p in range(4)])) if len(pos) >= 8 else 0
    down = beats[phase::4]
    # energy curve (0.5 s steps) and the drop: the biggest jump in loudness in the first 80 s that is not in the first 2 s
    step = int(0.5 * SR)
    rms = np.array([np.sqrt(np.mean(x[i:i + step] ** 2)) for i in range(0, len(x) - step, step)])
    rms = rms / (rms.max() + 1e-9)
    drop = None
    if len(rms) > 12:
        sm = np.convolve(rms, np.ones(4) / 4, mode="same")
        jump = sm[6:] - sm[:-6]
        lim = min(len(jump), 160)
        j = int(np.argmax(jump[4:lim])) + 4 if lim > 4 else 0
        if jump[j] > 0.12:
            drop = float((j + 6) * 0.5)
            near = down[np.argmin(np.abs(down - drop))] if len(down) else drop
            drop = float(near) if abs(near - drop) < 1.5 else drop
    res = {"bpm": round(float(bpm), 1), "beats": [round(float(b), 3) for b in beats], "downbeats": [round(float(b), 3) for b in down],
           "duration": round(dur, 2), "drop": None if drop is None else round(drop, 2),
           "energy": [[round(i * 0.5, 1), round(float(v), 3)] for i, v in enumerate(rms[::2])][:300]}
    CACHE.mkdir(parents=True, exist_ok=True)
    cf.write_text(json.dumps(res), encoding="utf-8")
    return res


if __name__ == "__main__":
    import sys
    r = analyze(sys.argv[1])
    print(r["bpm"], "bpm", len(r["beats"]), "beats", "first", r["beats"][:6], "downbeats", r["downbeats"][:4], "drop", r["drop"])
