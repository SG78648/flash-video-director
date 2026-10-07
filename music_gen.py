"""music_gen.py - original background music for short videos, synthesised from scratch.

Nothing here is sampled or copied from any recording, so the tracks carry no third-party rights: they are compositions
made by this code (chords, rhythms and sounds written below). Each track follows one emotional arc made for short-form
video: an instant hook, intrigue, a build, a held breath, the "aha" lift and a resolved ending (see below).

    python music_gen.py                                  # three moods, 75 s, added to the music library
    python music_gen.py --mood "Dark Pulse" --length 73 --aha 58 --name "My video"
"""
import io
import sys
import wave

import numpy as np

SR = 48000


def hz(note):                       # MIDI note number -> frequency
    return 440.0 * 2 ** ((note - 69) / 12)


# ---------------------------------------------------------------- sound building blocks
def saw(f, n, detune=(0.0,), phase0=0.0):
    """Band-limited-ish saw: a stack of detuned additive saws (soft, string-like)."""
    t = np.arange(n) / SR
    out = np.zeros(n)
    for d in detune:
        ff = f * 2 ** (d / 1200.0)
        k = int(min(14, (SR / 2.4) // ff))
        for h in range(1, max(2, k)):
            out += np.sin(2 * np.pi * ff * h * t + phase0 + h) / h
    return out / max(1, len(detune))


def lowpass(x, cutoff):
    """One-pole low-pass; `cutoff` is a number or an array (a filter sweep)."""
    c = np.broadcast_to(np.asarray(cutoff, dtype=np.float64), x.shape)
    a = 1 - np.exp(-2 * np.pi * c / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += a[i] * (x[i] - acc)
        y[i] = acc
    return y


def lp_fast(x, cutoff, passes=2):
    """Vectorised steady low-pass (FFT) for constant cutoffs: much faster than the loop above."""
    n = len(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    h = 1 / (1 + (f / cutoff) ** 4)
    for _ in range(passes - 1):
        h = h * h
        break
    return np.fft.irfft(np.fft.rfft(x) * h, n)


def adsr(n, a, d, s, r):
    e = np.ones(n)
    ia, idc, ir = int(a * SR), int(d * SR), int(r * SR)
    ia, idc, ir = min(ia, n), min(idc, max(0, n - ia)), min(ir, n)
    e[:ia] = np.linspace(0, 1, ia, endpoint=False) if ia else e[:0]
    if idc:
        e[ia:ia + idc] = np.linspace(1, s, idc)
    e[ia + idc:] = s
    if ir:
        e[n - ir:] *= np.linspace(1, 0, ir)
    return e


def reverb(x, seconds=2.6, wet=0.35, seed=1):
    """Cheap room: convolution with decaying noise (stereo, decorrelated)."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    out = []
    for ch in range(2):
        ir = rng.standard_normal(n) * np.exp(-t * (6.9 / seconds))
        ir = lp_fast(ir, 3500)
        ir /= np.sqrt(np.sum(ir ** 2)) + 1e-9
        size = len(x) + n
        wetch = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:len(x)]
        out.append(x * (1 - wet) + wetch * wet)
    return np.stack(out, axis=1)


def place(buf, sig, start_s, gain=1.0):
    i = int(start_s * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[:j - i] * gain


def kick(dur=0.45):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 42 + 90 * np.exp(-t * 28)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)


def boom(dur=2.4, f0=38):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f0 + 55 * np.exp(-t * 6)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 1.9)
    rng = np.random.default_rng(3)
    noise = lp_fast(rng.standard_normal(n), 400) * np.exp(-t * 3.5) * 2.5
    return body + noise


def hat(dur=0.06, seed=0):
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    x = rng.standard_normal(n)
    x = x - lp_fast(x, 5000)
    return x * np.exp(-np.arange(n) / SR * 70)


def pluck(f, dur=1.2):
    """Soft bell-like note (two sines, a little FM)."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    m = np.sin(2 * np.pi * f * 2.0 * t) * 0.6 * np.exp(-t * 6)
    return (np.sin(2 * np.pi * f * t + m) * 0.8 + np.sin(2 * np.pi * f * 2 * t) * 0.15) * np.exp(-t * 2.6)


def riser(dur, f_lo=300, f_hi=4500, seed=5):
    """Noise whose pitch rises: a band-pass swept smoothly (no seams, no hiss above ~8 kHz), louder towards the end."""
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    x = rng.standard_normal(n)
    t = np.linspace(0.0, 1.0, n)
    c = f_lo * (f_hi / f_lo) ** t
    band = lowpass(x, c * 1.5) - lowpass(x, c * 0.55)
    band = lowpass(band, np.minimum(c * 3.0, 9000.0))
    band /= np.abs(band).max() + 1e-9
    return band * t ** 2.2


def fade_ends(x, a=1.5, b=3.0):
    n = len(x)
    ia, ib = int(a * SR), int(b * SR)
    x[:ia] *= np.linspace(0, 1, ia)[:, None]
    x[n - ib:] *= np.linspace(1, 0, ib)[:, None]
    return x


def finish(stereo, peak=0.89):
    stereo = np.tanh(stereo * 1.25) / np.tanh(1.25)          # gentle glue / limiting
    stereo = stereo / (np.abs(stereo).max() + 1e-9) * peak
    return stereo


# ---------------------------------------------------------------- the arc (made for short videos)
#
#   0.0 s   HOOK        an impact and a four-note rising motif in the first second (no fade-in): stops the scroll
#   3 s     INTRIGUE    sparse and dark: a heartbeat bass, a low pad, the motif now and then. Room for the voice.
#   ~30 %   BUILD       layers arrive one by one (pulse, kick, hats, rising arpeggio), the harmony turns tense
#   aha-8   RISER       a noise + pitch riser into the moment
#   aha-0.9 BREATH      everything drops out except the reverb tail: a held breath
#   aha     THE AHA     a huge hit, the harmony lifts from minor to its relative major, the motif is played again, bright
#   after   RESOLUTION  fuller and warmer, the payoff; a decisive final chord and a natural tail at the end
#
# `aha` is the second of the video where the idea lands (the answer, the reveal). Make the track fit the video with
#   python music_gen.py --mood "Dark Pulse" --length 73 --aha 58 --name "My video bed"

MOODS = {
    "Dark Pulse": dict(bpm=100, kick=True, build=[[45, 57, 60, 64], [41, 53, 57, 60], [45, 57, 60, 64], [40, 52, 56, 59]],
                       release=[[48, 60, 64, 67], [43, 55, 59, 62], [45, 57, 60, 64], [41, 53, 57, 60]],
                       hook=[69, 72, 76, 81], payoff=[72, 76, 79, 84], sub_8ths=True),
    "Slow Burn": dict(bpm=72, kick=False, sub=0.5, pad="strings", lead="piano", drums="minimal", tex="wind", impact="swell", build=[[38, 50, 53, 57], [34, 46, 50, 53], [43, 55, 58, 62], [33, 45, 49, 52]],
                      release=[[41, 53, 57, 60], [36, 48, 52, 55], [38, 50, 53, 57], [34, 46, 50, 53]],
                      hook=[74, 77, 81, 86], payoff=[77, 81, 84, 89], sub_8ths=False),
    "Rising Tension": dict(bpm=120, kick=True, sub=0.6, pad="gate", gate=0.25, pad_gain=0.8, lead="marimba", pump=True, build=[[40, 52, 55, 59], [36, 48, 52, 55], [40, 52, 55, 59], [35, 47, 51, 54]],
                           release=[[43, 55, 59, 62], [38, 50, 54, 57], [40, 52, 55, 59], [36, 48, 52, 55]],
                           hook=[76, 79, 83, 88], payoff=[79, 83, 86, 91], sub_8ths=True),
    "Midnight Drive": dict(bpm=108, kick=True, sub=0.55, pad="gate", gate=0.5, lead="bell", pump=True, impact="hit", build=[[43, 55, 58, 62], [39, 51, 55, 58], [43, 55, 58, 62], [38, 50, 54, 57]],
                           release=[[34, 46, 50, 53], [41, 53, 57, 60], [43, 55, 58, 62], [39, 51, 55, 58]],
                           hook=[67, 70, 74, 79], payoff=[70, 74, 77, 82], sub_8ths=True, hat16=True),
    "Golden Hour": dict(bpm=88, kick=False, sub=0.3, pad="glass", lead="marimba", drums="shaker", impact="swell", build=[[36, 48, 51, 55], [32, 44, 48, 51], [36, 48, 51, 55], [43, 55, 59, 62]],
                        release=[[39, 51, 55, 58], [34, 46, 50, 53], [36, 48, 51, 55], [32, 44, 48, 51]],
                        hook=[72, 75, 79, 84], payoff=[75, 79, 82, 87], sub_8ths=False, arp_step=0.25),
    "Quiet Storm": dict(bpm=60, kick=False, sub=0.3, pad="glass", lead="bell", drums="none", tex="rain", impact="swell", build=[[35, 47, 50, 54], [43, 55, 59, 62], [35, 47, 50, 54], [42, 54, 58, 61]],
                        release=[[38, 50, 54, 57], [45, 57, 61, 64], [35, 47, 50, 54], [43, 55, 59, 62]],
                        hook=[71, 74, 78, 83], payoff=[74, 78, 81, 86], sub_8ths=False),
    # --- cold, minimal, tense: the sound of money and power (original pieces in that spirit, not copies of any score)
    "Cold Open": dict(bpm=92, kick=False, sub=0.45, lead="piano", drums="minimal", pad_cut=0.7, impact="hit",
                      build=[[42, 54, 57, 61], [38, 50, 54, 57], [42, 54, 57, 61], [37, 49, 53, 56]],
                      release=[[45, 57, 61, 64], [40, 52, 56, 59], [42, 54, 57, 61], [38, 50, 54, 57]],
                      hook=[66, 69, 73, 78], payoff=[69, 73, 76, 81], sub_8ths=False),
    "Boardroom": dict(bpm=76, kick=True, sub=1.0, pad="strings", lead="piano", bass="808", drums="trap", pad_cut=0.8, impact="hit",
                      build=[[37, 49, 52, 56], [33, 45, 49, 52], [40, 52, 56, 59], [35, 47, 51, 54]],
                      release=[[40, 52, 56, 59], [35, 47, 51, 54], [37, 49, 52, 56], [33, 45, 49, 52]],
                      hook=[73, 76, 80, 85], payoff=[76, 80, 83, 88], sub_8ths=False),
    "Short Squeeze": dict(bpm=132, kick=True, sub=0.7, pad="gate", gate=0.25, pad_gain=0.5, lead="acid", bass="techno", hat16=True, arp_step=0.25, pad_cut=0.9, pump=True, impact="hit",
                          build=[[38, 50, 53, 57], [34, 46, 50, 53], [38, 50, 53, 57], [45, 57, 61, 64]],
                          release=[[41, 53, 57, 60], [36, 48, 52, 55], [38, 50, 53, 57], [34, 46, 50, 53]],
                          hook=[62, 65, 69, 74], payoff=[65, 69, 72, 77], sub_8ths=True),
    "Closing Bell": dict(bpm=60, kick=False, sub=0.8, pad="strings", lead="piano", drums="minimal", pad_cut=0.72, impact="bell",
                         build=[[34, 46, 49, 53], [30, 42, 46, 49], [34, 46, 49, 53], [29, 41, 45, 48]],
                         release=[[37, 49, 53, 56], [32, 44, 48, 51], [34, 46, 49, 53], [30, 42, 46, 49]],
                         hook=[58, 61, 65, 70], payoff=[61, 65, 68, 73], sub_8ths=False),
    "Clockwork": dict(bpm=126, kick=True, sub=0.4, pad_gain=0.3, lead="marimba", impact="hit", build=[[41, 53, 56, 60], [37, 49, 53, 56], [41, 53, 56, 60], [36, 48, 52, 55]],
                      release=[[44, 56, 60, 63], [39, 51, 55, 58], [41, 53, 56, 60], [37, 49, 53, 56]],
                      hook=[65, 68, 72, 77], payoff=[68, 72, 75, 80], sub_8ths=True, hat16=True, arp_step=0.25),
}


def clap(seed=0):
    rng = np.random.default_rng(seed)
    n = int(0.16 * SR)
    x = rng.standard_normal(n)
    x = lp_fast(x, 6000) - lp_fast(x, 900)
    return x * np.exp(-np.arange(n) / SR * 26)


def marimba(f, dur=0.7):
    """A wooden, mallet-like note: a short tone with a bright click that dies fast."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = (np.sin(2 * np.pi * f * t) * np.exp(-t * 7.5) + 0.38 * np.sin(2 * np.pi * 3.9 * f * t) * np.exp(-t * 22)
         + 0.18 * np.sin(2 * np.pi * 9.2 * f * t) * np.exp(-t * 40))
    return x * np.minimum(1.0, t / 0.002)


def hit_metal(dur=1.2, f0=60):
    """A short metallic hit instead of a sub boom: a click and a few inharmonic partials."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(4)
    x = sum(a * np.sin(2 * np.pi * f * t + p) * np.exp(-t * d)
            for a, f, d, p in ((1.0, 520, 3.2, 0.0), (0.7, 1432, 4.5, 1.0), (0.45, 2810, 6.5, 2.0), (0.3, 4630, 9.0, 0.5)))
    click = lp_fast(rng.standard_normal(n), 5000) * np.exp(-t * 60)
    return (x * 0.5 + click * 1.4) * np.minimum(1.0, t / 0.001)


def big_bell(dur=3.0, f0=110):
    """A large, low bell: inharmonic partials with a long ring."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    ratios = ((0.5, 0.7, 0.9), (1.0, 1.0, 1.0), (1.19, 0.6, 1.4), (1.56, 0.45, 1.8), (2.0, 0.5, 2.2), (2.74, 0.28, 3.0), (3.76, 0.18, 4.0))
    x = sum(a * np.sin(2 * np.pi * f0 * 2 * r * t) * np.exp(-t * d) for r, a, d in ratios)
    return x * np.minimum(1.0, t / 0.002) * 0.6


def soft_swell(dur=2.5, f0=60):
    """No hit at all: a soft, low swell that blooms and settles (calm moods)."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    env = np.sin(np.pi * np.minimum(1.0, t / dur)) ** 2
    return (np.sin(2 * np.pi * f0 * 1.5 * t) + 0.5 * np.sin(2 * np.pi * f0 * 3.01 * t)) * env * 0.6


def pad_voice(notes, ln, kind, beat, gate_beats=0.5):
    """The sustained chord of a mood: bowed strings, glassy air, a pulsing gate, or the original saw pad."""
    t = np.arange(ln) / SR
    seg = np.zeros(ln)
    if kind == "strings":
        for note in notes:
            seg += saw(hz(note), ln, detune=(-14, -5, 4, 13))
        return seg * (1.0 + 0.09 * np.sin(2 * np.pi * 5.3 * t))
    if kind == "glass":
        for note in notes[1:] + [notes[0] + 12]:
            f = hz(note + 12)
            for det in (-3, 3):
                ff = f * 2 ** (det / 1200.0)
                seg += (np.sin(2 * np.pi * ff * t) + 0.5 * np.sin(2 * np.pi * 2 * ff * t) + 0.25 * np.sin(2 * np.pi * 3 * ff * t)
                        + 0.12 * np.sin(2 * np.pi * 5 * ff * t))
        return seg * 0.28
    for note in notes:
        seg += saw(hz(note), ln, detune=(-9, 0, 8))
    if kind == "gate":
        per = max(0.05, beat * gate_beats)
        gate = (np.sin(2 * np.pi * t / per) > -0.2).astype(float)
        k = int(0.012 * SR)
        gate = np.convolve(gate, np.ones(k) / k, mode="same")
        return seg * (0.25 + 0.75 * gate)
    return seg


def texture(kind, n):
    """A quiet bed of sound under everything (rain, wind) - makes a mood feel like a place."""
    rng = np.random.default_rng(12)
    t = np.arange(n) / SR
    out = []
    for ch in range(2):
        x = rng.standard_normal(n)
        if kind == "rain":
            x = lp_fast(x - lp_fast(x, 1800), 7000) * (0.55 + 0.45 * np.sin(2 * np.pi * 0.06 * t + ch))
            x *= 0.05
        else:                                                      # wind
            x = lp_fast(x, 520) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.045 * t + ch * 1.3)) * 0.16
        out.append(x * np.minimum(1.0, t / 3.0))
    return np.stack(out, axis=1)


def piano(f, dur=1.8):
    """A soft, cold piano-like note: a few decaying partials and a gentle hammer."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = (np.sin(2 * np.pi * f * t) * np.exp(-t * 2.0) + 0.5 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 3.4)
         + 0.25 * np.sin(2 * np.pi * 3 * f * t) * np.exp(-t * 5.0) + 0.1 * np.sin(2 * np.pi * 4.01 * f * t) * np.exp(-t * 7.0))
    return x * np.minimum(1.0, t / 0.004)


def acid(f, dur=0.5, cutoff=1500):
    """A plucked, filtered saw: the classic techno arpeggio sound."""
    n = int(dur * SR)
    x = lp_fast(saw(f, n, detune=(0,)), cutoff)
    return x * np.exp(-np.arange(n) / SR * 7.5) * np.minimum(1.0, np.arange(n) / (0.003 * SR))


def b808(f, dur=1.2):
    """A long, round 808-style bass note that falls a little in pitch at the start."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    fr = f * (1 + 1.4 * np.exp(-t * 32))
    return np.tanh(1.9 * np.sin(2 * np.pi * np.cumsum(fr) / SR)) * np.exp(-t * 2.4) * np.minimum(1.0, t / 0.003)


def tbass(f, dur=0.18):
    """A short, dark techno bass stab."""
    n = int(dur * SR)
    x = lp_fast(saw(f, n, detune=(0,)), 420)
    return x * np.exp(-np.arange(n) / SR * 14) * np.minimum(1.0, np.arange(n) / (0.002 * SR))


def tone(f, dur, kind="sine", a=0.004, r=0.05):
    n = int(dur * SR)
    t = np.arange(n) / SR
    if kind == "sine":
        x = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)
    else:
        x = saw(f, n, detune=(-6, 6))
    return x * adsr(n, a, 0.06, 0.7, r)


def compose(mood="Dark Pulse", seconds=75.0, aha=None):
    m = MOODS[mood]
    T = float(seconds)
    aha = float(aha) if aha else T * 0.76
    aha = min(max(aha, 14.0), T - 6.0)
    beat = 60.0 / m["bpm"]
    bar = beat * 4
    n = int(T * SR)
    t_build = max(6.0, min(0.32 * T, aha - 14.0))
    breath = (aha - 0.9, aha - 0.02)
    # how intense the music is, second by second
    keys = [(0, 1.0), (0.7, 1.0), (1.9, 0.55), (3.2, 0.25), (t_build, 0.35), (aha - 8, 0.85), (aha - 1.0, 1.0),
            (aha, 1.2), (aha + 6, 0.95), (T - 5, 0.7), (T, 0.35)]
    keys.sort()
    ts = np.arange(n) / SR
    inten = np.interp(ts, [k[0] for k in keys], [k[1] for k in keys])
    I = lambda t: float(np.interp(t, [k[0] for k in keys], [k[1] for k in keys]))

    style_lead = m.get("lead", "bell")
    LEAD = {"bell": pluck, "piano": piano, "acid": lambda f, d: acid(f, min(d, 0.5)), "marimba": lambda f, d: marimba(f, min(d, 0.8))}[style_lead]
    sub = m.get("sub", 1.0)
    pad_type, pad_gain, gate_beats = m.get("pad", "saw"), m.get("pad_gain", 1.0), m.get("gate", 0.5)
    imp = m.get("impact", "boom")
    IMP = {"boom": lambda d, f: boom(d, f) * sub, "hit": hit_metal, "bell": big_bell, "swell": soft_swell}[imp]
    bass_style, drum_style = m.get("bass", "sub"), m.get("drums", "four")

    pad = np.zeros(n)
    bass = np.zeros(n)
    drums = np.zeros(n)
    bells = np.zeros(n)
    fx = np.zeros(n)

    # ---- harmony: tense minor before the aha, relative major after it
    def chord_at(t):
        if t < aha:
            prog, t0 = m["build"], 0.0
        else:
            prog, t0 = m["release"], aha
        return prog[int((t - t0) // (bar * 2)) % 4]

    t = 0.0
    while t < T:
        edge = aha if t < aha <= t + bar * 2 else None
        seg_end = edge if edge else t + bar * 2
        notes = chord_at(t)
        ln = int((seg_end - t + 0.9) * SR)
        ln = min(ln, n - int(t * SR))
        if ln <= 0:
            break
        seg = pad_voice(notes, ln, pad_type, beat, gate_beats)
        major_now = t >= aha - 0.01
        cutoff = (380 + 1700 * min(1.2, I(t) + (0.15 if major_now else 0))) * m.get("pad_cut", 1.0)
        seg = lp_fast(seg, cutoff) * adsr(ln, 1.2 if not major_now else 0.15, 0.4, 0.9, 1.2)
        if major_now:                                               # light above the pad: the lift
            sh = np.zeros(ln)
            for note in notes[1:]:
                sh += np.sin(2 * np.pi * hz(note + 12) * np.arange(ln) / SR)
            seg += lp_fast(sh, 3500) * 0.18 * adsr(ln, 0.3, 0.3, 0.8, 1.2)
        i0 = int(t * SR)
        pad[i0:i0 + ln] += seg * (0.35 + 0.35 * min(1.2, I(t))) / 2.4 * pad_gain
        t = seg_end
    # ---- bass: a heartbeat in the intrigue, a pulse in the build, a drive after the aha
    t, k = 3.0, 0
    while t < T - 3.5:
        chord = chord_at(t)
        root = chord[0]
        if t < t_build:                                             # heartbeat: one soft low note per bar
            bass_note = tone(hz(root), beat * 1.6, "sine", 0.01, 0.2)
            place(bass, bass_note, t, 0.5 * sub)
            t += bar
        elif bass_style == "808":                                      # long round notes on 1 and the and-of-2, sliding up on the last bar of four
            g_ = (0.5 + 0.3 * min(1.2, I(t))) * sub
            place(bass, b808(hz(root), beat * 2.2), t, g_)
            place(bass, b808(hz(root), beat * 1.2), t + beat * 2.5, g_ * 0.8)
            t += bar
        elif bass_style == "techno":                                   # off-beat stabs, the classic driving pulse
            g_ = (0.42 + 0.3 * min(1.2, I(t))) * sub
            for q_ in (0.5, 0.75):
                place(bass, tbass(hz(root + (12 if q_ == 0.75 and k % 2 else 0)), beat * 0.22), t + beat * q_, g_)
            t += beat
        else:
            step = beat / 2 if m["sub_8ths"] else beat
            place(bass, tone(hz(root), step * 0.9, "sine", 0.004, 0.05), t, (0.45 + 0.35 * min(1.2, I(t))) * sub)
            t += step
        k += 1
    # ---- drums
    nb = int(T / beat)
    if drum_style == "trap":                                           # half-time: kick pattern, clap on 3, hats with rolls
        step_s = beat / 4
        for q_ in range(int(T / step_s)):
            tt = q_ * step_s
            if tt < 1.8 or tt >= T - 3.4 or (breath[0] <= tt < breath[1] + 0.05):
                continue
            if not (t_build + 3 <= tt):
                continue
            st_ = q_ % 16
            lvl = min(1.2, I(tt))
            if st_ in (0, 7, 10) or (st_ == 13 and (q_ // 16) % 4 == 3):
                place(drums, kick(0.42), tt, 0.55 + 0.3 * lvl)
            if st_ == 8:
                place(drums, clap(q_), tt, 0.45)
            if tt >= t_build + 6:
                place(drums, hat(0.045, seed=q_), tt, (0.16 if st_ % 2 == 0 else 0.09) + 0.05 * lvl)
                if st_ in (14, 15) and (q_ // 16) % 2 == 1:                 # a roll at the end of every second bar
                    place(drums, hat(0.03, seed=q_ + 500), tt + step_s / 2, 0.12)
    elif drum_style == "minimal":                                      # almost nothing: a low thud each bar and a quiet tick
        for b in range(nb):
            tt = b * beat
            if tt < 1.8 or tt >= T - 3.4 or (breath[0] <= tt < breath[1] + 0.05) or tt < t_build + 3:
                continue
            if b % 4 == 0:
                place(drums, kick(0.5), tt, 0.35 + 0.2 * min(1.2, I(tt)))
            place(drums, hat(0.04, seed=b), tt + beat / 2, 0.08 + 0.05 * min(1.2, I(tt)))
    if drum_style == "shaker":                                         # soft shaker on the off-beats, nothing else
        for b in range(nb):
            tt = b * beat
            if tt < t_build + 3 or tt >= T - 3.4 or (breath[0] <= tt < breath[1] + 0.05):
                continue
            place(drums, lp_fast(hat(0.07, seed=b + 200), 9000), tt + beat / 2, 0.16 + 0.08 * min(1.2, I(tt)))
            if b % 2 == 0:
                place(drums, lp_fast(hat(0.05, seed=b + 300), 9000), tt, 0.09)
    for b in (range(nb) if drum_style == "four" else range(0)):
        tt = b * beat
        if tt < 1.8 or tt >= T - 3.4:
            continue
        if breath[0] <= tt < breath[1] + 0.05:
            continue
        inten_t = I(tt)
        in_build = t_build + 3 <= tt < aha
        after = tt >= aha
        if m["kick"] and (in_build or after) and (after or tt > t_build + 6):
            place(drums, kick(0.42), tt, 0.5 + 0.3 * min(1.2, inten_t))
        if in_build or after:
            place(drums, hat(seed=b), tt + beat / 2, 0.14 + 0.1 * min(1.2, inten_t))
            if m.get("hat16"):                                      # busier hats for the energetic moods
                place(drums, hat(0.04, seed=b + 31), tt + beat * 0.25, 0.08)
                place(drums, hat(0.04, seed=b + 57), tt + beat * 0.75, 0.1)
            if after and b % 2 == 1:
                place(drums, clap(b), tt, 0.35)
            if (in_build and tt > aha - 10) and b % 2 == 0:         # a snare-roll feel in the last 10 s
                place(drums, hat(0.05, seed=b + 7), tt + beat * 0.75, 0.2)
    # ---- the hook: an impact and the four-note motif right at the start
    place(fx, IMP(1.6, 44), 0.0, 1.0)
    for j, note in enumerate(m["hook"]):
        place(bells, LEAD(hz(note), 1.6), 0.18 + j * beat / 2, 0.85)
    # the motif returns, quietly, in the intrigue, and as a rising arpeggio in the build
    tt = t_build * 0.5
    while tt < t_build - 2:
        for j, note in enumerate(m["hook"][:3]):
            place(bells, LEAD(hz(note), 1.4), tt + j * beat, 0.28)
        tt += bar * 2
    tt = t_build
    j = 0
    while tt < aha - 1.0:
        chord = chord_at(tt)
        note = chord[1 + j % 3] + 24 + (12 if (j // 3) % 2 else 0)
        place(bells, LEAD(hz(note), 0.5), tt, 0.14 + 0.2 * min(1.0, I(tt)))
        tt += beat * m.get("arp_step", 0.5)
        j += 1
    # ---- riser into the aha, then the aha itself
    ra = max(1.0, aha - 8.0)
    place(fx, riser(aha - 0.9 - ra, 300, 4500, seed=9), ra, 0.32)
    rl = int((aha - 0.9 - ra) * SR)
    sweep_f = hz(m["build"][3][0] + 12) * (1 + 3 * (np.arange(rl) / max(1, rl)) ** 2)
    sweep = np.sin(2 * np.pi * np.cumsum(sweep_f) / SR) * (np.arange(rl) / max(1, rl)) ** 2
    place(fx, sweep, ra, 0.18)
    place(fx, IMP(3.4, 40), aha, 1.1)
    place(fx, riser(1.6, 300, 3500, seed=11)[::-1], aha, 0.16)      # a soft swell falling away
    for j, note in enumerate(m["payoff"]):
        place(bells, LEAD(hz(note), 2.2), aha + 0.05 + j * beat / 2, 1.0)
        place(bells, LEAD(hz(note - 12), 2.2), aha + 0.05 + j * beat / 2, 0.45)
    # ---- the ending: a decisive major chord and a hit, then the tail
    end_t = T - 3.4
    for note in m["release"][0]:
        place(pad, tone(hz(note), 3.0, "saw", 0.02, 1.2), end_t, 0.16)
    place(fx, IMP(2.6, 40), end_t, 0.85)
    for j, note in enumerate(m["payoff"][::-1][:3]):
        place(bells, LEAD(hz(note), 2.0), end_t + 0.05 + j * 0.05, 0.4)

    # ---- the held breath: the dry music drops out for ~0.9 s before the aha (the reverb tail keeps ringing)
    gate = np.ones(n)
    a0, a1 = int(breath[0] * SR), int(breath[1] * SR)
    r = int(0.05 * SR)
    gate[a0:a1] = 0.04
    gate[a0 - r:a0] = np.linspace(1, 0.04, r)
    gate[a1:a1 + r] = np.linspace(0.04, 1, r)
    if m.get("pump"):                                               # the pad ducks on every beat, like a kick pushing it aside
        env = np.ones(n)
        d = int(beat * 0.8 * SR)
        for b_ in range(int(T / beat)):
            i = int(b_ * beat * SR)
            if i < n:
                env[i:i + d] *= (np.linspace(0.3, 1.0, min(d, n - i)) ** 1.3)
        pad = pad * env
    wet_in = (pad + bells) * gate
    st = reverb(wet_in, 2.8, 0.30)
    st += (bass * gate)[:, None] * 0.95 + (drums * gate)[:, None] * 0.6
    fxg = fx.copy()
    st += reverb(fxg, 2.2, 0.25, seed=8) * 0.9
    if m.get("tex"):
        st = st + texture(m["tex"], n)
    st = finish(st)
    # the ending: ring out over the last 2.2 s, and only a few ms at the very start (the hook must hit at once)
    e = int(2.2 * SR)
    st[n - e:] *= (np.cos(np.linspace(0, np.pi / 2, e)) ** 1.5)[:, None]
    s0 = int(0.004 * SR)
    st[:s0] *= np.linspace(0, 1, s0)[:, None]
    return st


def to_wav_bytes(stereo):
    pcm = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
    bio = io.BytesIO()
    with wave.open(bio, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return bio.getvalue()


def make(mood, seconds=75.0, aha=None, name=None, add=True):
    st = compose(mood, seconds, aha)
    if not add:
        return st
    import music
    return music.save_to_library(name or f"Hook to Aha - {mood}", to_wav_bytes(st), ".wav")


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="Original short-form music with an emotional arc (hook -> build -> aha -> resolve)")
    ap.add_argument("--mood", choices=list(MOODS), help="make only this mood (default: all)")
    ap.add_argument("--length", type=float, default=75.0, help="seconds")
    ap.add_argument("--aha", type=float, default=None, help="second where the idea lands (default: 76% of the length)")
    ap.add_argument("--name", default=None, help="library name (single mood only)")
    a = ap.parse_args(argv)
    for mood in ([a.mood] if a.mood else list(MOODS)):
        print(f"making {mood}...", flush=True)
        print("  added:", make(mood, a.length, a.aha, a.name if a.mood else None), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
