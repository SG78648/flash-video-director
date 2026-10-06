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
    "Slow Burn": dict(bpm=72, kick=False, build=[[38, 50, 53, 57], [34, 46, 50, 53], [43, 55, 58, 62], [33, 45, 49, 52]],
                      release=[[41, 53, 57, 60], [36, 48, 52, 55], [38, 50, 53, 57], [34, 46, 50, 53]],
                      hook=[74, 77, 81, 86], payoff=[77, 81, 84, 89], sub_8ths=False),
    "Rising Tension": dict(bpm=120, kick=True, build=[[40, 52, 55, 59], [36, 48, 52, 55], [40, 52, 55, 59], [35, 47, 51, 54]],
                           release=[[43, 55, 59, 62], [38, 50, 54, 57], [40, 52, 55, 59], [36, 48, 52, 55]],
                           hook=[76, 79, 83, 88], payoff=[79, 83, 86, 91], sub_8ths=True),
    "Midnight Drive": dict(bpm=108, kick=True, build=[[43, 55, 58, 62], [39, 51, 55, 58], [43, 55, 58, 62], [38, 50, 54, 57]],
                           release=[[34, 46, 50, 53], [41, 53, 57, 60], [43, 55, 58, 62], [39, 51, 55, 58]],
                           hook=[67, 70, 74, 79], payoff=[70, 74, 77, 82], sub_8ths=True, hat16=True),
    "Golden Hour": dict(bpm=88, kick=False, build=[[36, 48, 51, 55], [32, 44, 48, 51], [36, 48, 51, 55], [43, 55, 59, 62]],
                        release=[[39, 51, 55, 58], [34, 46, 50, 53], [36, 48, 51, 55], [32, 44, 48, 51]],
                        hook=[72, 75, 79, 84], payoff=[75, 79, 82, 87], sub_8ths=False, arp_step=0.25),
    "Quiet Storm": dict(bpm=60, kick=False, build=[[35, 47, 50, 54], [43, 55, 59, 62], [35, 47, 50, 54], [42, 54, 58, 61]],
                        release=[[38, 50, 54, 57], [45, 57, 61, 64], [35, 47, 50, 54], [43, 55, 59, 62]],
                        hook=[71, 74, 78, 83], payoff=[74, 78, 81, 86], sub_8ths=False),
    "Clockwork": dict(bpm=126, kick=True, build=[[41, 53, 56, 60], [37, 49, 53, 56], [41, 53, 56, 60], [36, 48, 52, 55]],
                      release=[[44, 56, 60, 63], [39, 51, 55, 58], [41, 53, 56, 60], [37, 49, 53, 56]],
                      hook=[65, 68, 72, 77], payoff=[68, 72, 75, 80], sub_8ths=True, hat16=True, arp_step=0.25),
}


def clap(seed=0):
    rng = np.random.default_rng(seed)
    n = int(0.16 * SR)
    x = rng.standard_normal(n)
    x = lp_fast(x, 6000) - lp_fast(x, 900)
    return x * np.exp(-np.arange(n) / SR * 26)


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
        seg = np.zeros(ln)
        for note in notes:
            seg += saw(hz(note), ln, detune=(-9, 0, 8))
        major_now = t >= aha - 0.01
        cutoff = 380 + 1700 * min(1.2, I(t) + (0.15 if major_now else 0))
        seg = lp_fast(seg, cutoff) * adsr(ln, 1.2 if not major_now else 0.15, 0.4, 0.9, 1.2)
        if major_now:                                               # light above the pad: the lift
            sh = np.zeros(ln)
            for note in notes[1:]:
                sh += np.sin(2 * np.pi * hz(note + 12) * np.arange(ln) / SR)
            seg += lp_fast(sh, 3500) * 0.18 * adsr(ln, 0.3, 0.3, 0.8, 1.2)
        i0 = int(t * SR)
        pad[i0:i0 + ln] += seg * (0.35 + 0.35 * min(1.2, I(t))) / 2.4
        t = seg_end
    # ---- bass: a heartbeat in the intrigue, a pulse in the build, a drive after the aha
    t, k = 3.0, 0
    while t < T - 3.5:
        chord = chord_at(t)
        root = chord[0]
        if t < t_build:                                             # heartbeat: one soft low note per bar
            bass_note = tone(hz(root), beat * 1.6, "sine", 0.01, 0.2)
            place(bass, bass_note, t, 0.5)
            t += bar
        else:
            step = beat / 2 if m["sub_8ths"] else beat
            place(bass, tone(hz(root), step * 0.9, "sine", 0.004, 0.05), t, 0.45 + 0.35 * min(1.2, I(t)))
            t += step
        k += 1
    # ---- drums
    nb = int(T / beat)
    for b in range(nb):
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
    place(fx, boom(1.6, 44), 0.0, 1.0)
    for j, note in enumerate(m["hook"]):
        place(bells, pluck(hz(note), 1.6), 0.18 + j * beat / 2, 0.85)
    # the motif returns, quietly, in the intrigue, and as a rising arpeggio in the build
    tt = t_build * 0.5
    while tt < t_build - 2:
        for j, note in enumerate(m["hook"][:3]):
            place(bells, pluck(hz(note), 1.4), tt + j * beat, 0.28)
        tt += bar * 2
    tt = t_build
    j = 0
    while tt < aha - 1.0:
        chord = chord_at(tt)
        note = chord[1 + j % 3] + 24 + (12 if (j // 3) % 2 else 0)
        place(bells, pluck(hz(note), 0.5), tt, 0.14 + 0.2 * min(1.0, I(tt)))
        tt += beat * m.get("arp_step", 0.5)
        j += 1
    # ---- riser into the aha, then the aha itself
    ra = max(1.0, aha - 8.0)
    place(fx, riser(aha - 0.9 - ra, 300, 4500, seed=9), ra, 0.32)
    rl = int((aha - 0.9 - ra) * SR)
    sweep_f = hz(m["build"][3][0] + 12) * (1 + 3 * (np.arange(rl) / max(1, rl)) ** 2)
    sweep = np.sin(2 * np.pi * np.cumsum(sweep_f) / SR) * (np.arange(rl) / max(1, rl)) ** 2
    place(fx, sweep, ra, 0.18)
    place(fx, boom(3.4, 40), aha, 1.1)
    place(fx, riser(1.6, 300, 3500, seed=11)[::-1], aha, 0.16)      # a soft swell falling away
    for j, note in enumerate(m["payoff"]):
        place(bells, pluck(hz(note), 2.2), aha + 0.05 + j * beat / 2, 1.0)
        place(bells, pluck(hz(note - 12), 2.2), aha + 0.05 + j * beat / 2, 0.45)
    # ---- the ending: a decisive major chord and a hit, then the tail
    end_t = T - 3.4
    for note in m["release"][0]:
        place(pad, tone(hz(note), 3.0, "saw", 0.02, 1.2), end_t, 0.16)
    place(fx, boom(2.6, 40), end_t, 0.85)
    for j, note in enumerate(m["payoff"][::-1][:3]):
        place(bells, pluck(hz(note), 2.0), end_t + 0.05 + j * 0.05, 0.4)

    # ---- the held breath: the dry music drops out for ~0.9 s before the aha (the reverb tail keeps ringing)
    gate = np.ones(n)
    a0, a1 = int(breath[0] * SR), int(breath[1] * SR)
    r = int(0.05 * SR)
    gate[a0:a1] = 0.04
    gate[a0 - r:a0] = np.linspace(1, 0.04, r)
    gate[a1:a1 + r] = np.linspace(0.04, 1, r)
    wet_in = (pad + bells) * gate
    st = reverb(wet_in, 2.8, 0.30)
    st += (bass * gate)[:, None] * 0.95 + (drums * gate)[:, None] * 0.6
    fxg = fx.copy()
    st += reverb(fxg, 2.2, 0.25, seed=8) * 0.9
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
