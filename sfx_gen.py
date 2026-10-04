import math
import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 48000
import projects

SFX_DIR = projects.LIB_CACHE / "sfx"          # generated once, shared by every project

def _env(n, attack, release, sustain=1.0):
    a = max(1, int(attack * SR))
    r = max(1, int(release * SR))
    e = np.ones(n, dtype=np.float32)
    if n > a:
        e[:a] = np.linspace(0, 1, a)
    else:
        e = np.linspace(0, 1, n)
    if n > a + r:
        e[a:] = np.linspace(1.0, 0.0, n - a)
    e = np.minimum(e, sustain)
    return e

def _norm(x):
    p = np.abs(x).max()
    if p > 0:
        x = x / p * 0.85
    return x.astype(np.float32)

def _sine(dur, f0, f1=None, vibrato=0.0):
    n = int(dur * SR)
    t = np.linspace(0, dur, n, endpoint=False)
    if f1 is None:
        f = np.full(n, f0, dtype=np.float64)
    else:
        f = np.geomspace(f0, f1, n)
    phase = 2 * np.pi * np.cumsum(f) / SR
    if vibrato > 0:
        phase += 2 * np.pi * 5 * np.sin(2 * np.pi * 5.5 * t) * vibrato / 5.5
    return np.sin(phase).astype(np.float32)

def _noise(dur, seed=None):
    return np.random.default_rng(seed).random(int(dur * SR)).astype(np.float32) * 2 - 1

def one_pole(x, cutoff_start, cutoff_end, dur):
    n = len(x)
    out = np.empty(n, dtype=np.float32)
    acc = 0.0
    t = np.linspace(0, 1, n)
    for i in range(n):
        fc = cutoff_start + (cutoff_end - cutoff_start) * t[i]
        al = 1.0 - math.exp(-2 * math.pi * fc / SR)
        acc += al * (x[i] - acc)
        out[i] = acc
    return out

def sfx_whoosh(dur=0.75):
    x = _noise(dur)
    x = one_pole(x, 300, 6000, dur)
    e = _env(len(x), 0.18, dur - 0.18)
    x *= e
    x += _sine(dur, 1600, 240, vibrato=12) * _env(len(x), 0.2, dur - 0.2) * 0.5
    return _norm(x)

def sfx_swish(dur=0.30):
    """Soft camera-move sound: low-passed noise with a smooth bell envelope,
    no tonal glide and no bright top end (much gentler than sfx_whoosh)."""
    n = int(dur * SR)
    x = _noise(dur, seed=7)
    x = one_pole(x, 180, 1500, dur)
    x = one_pole(x, 1800, 1100, dur)          # second pole: softer slope
    t = np.linspace(0, 1, n)
    env = np.sin(np.pi * t) ** 2.2
    x = x * env
    p = np.abs(x).max()
    return (x / p * 0.5).astype(np.float32) if p > 0 else x.astype(np.float32)


def sfx_stamp(dur=0.6):
    n = int(dur * SR)
    body = _sine(dur, 78, 40) * _env(n, 0.004, dur * 0.75)
    thump = _sine(0.12, 55, 90) * _env(int(0.12 * SR), 0.003, 0.12)
    noise = _noise(0.10) * _env(int(0.10 * SR), 0.001, 0.09) * 0.5
    boom = np.concatenate([thump, noise, np.zeros(n - len(thump) - len(noise))])
    # wood/hard slap transient
    slap = _noise(0.03) * _env(int(0.03 * SR), 0.001, 0.028) * 0.6
    slap = np.concatenate([slap, np.zeros(n - len(slap))])
    return _norm(body + boom + slap)

def sfx_pop(dur=0.18):
    n = int(dur * SR)
    s = _sine(dur, 420, 1150)
    e = _env(n, 0.006, dur * 0.8)
    return _norm(s * e)

def sfx_clink(dur=0.4):
    n = int(dur * SR)
    out = np.zeros(n, dtype=np.float32)
    for f, g in [(1760, 1.0), (2345, 0.55), (3520, 0.28), (2693, 0.35)]:
        out += _sine(dur, f) * np.exp(np.linspace(0, -14, n)) * g
    click = _noise(0.008) * 0.5
    out[: len(click)] += click
    return _norm(out)

def sfx_ding(dur=0.8):
    n = int(dur * SR)
    out = _sine(dur, 1318.5) * np.exp(np.linspace(0, -12, n))
    out += _sine(dur, 1975.5) * np.exp(np.linspace(0, -14, n)) * 0.4
    out += _sine(dur, 2637) * np.exp(np.linspace(0, -16, n)) * 0.25
    return _norm(out)

def sfx_chime(dur=1.25):
    n = int(dur * SR)
    out = np.zeros(n, dtype=np.float32)
    tones = [1046.5, 1568.0, 2093.0]
    seg = int(0.42 * SR)
    pos = 0
    for f in tones:
        tone = _sine(0.42, f) * np.exp(np.linspace(0, -10, seg))
        end = min(n, pos + seg)
        out[pos:end] += tone[:end - pos]
        pos += int(0.42 * SR)
    return _norm(out)

def sfx_slam(dur=0.4):
    n = int(dur * SR)
    thud = _sine(dur, 88, 45) * _env(n, 0.002, dur * 0.7)
    clang = (_sine(dur, 880) * np.exp(np.linspace(0, -9, n)) * 0.5
             + _sine(dur, 1174) * np.exp(np.linspace(0, -12, n)) * 0.3)
    crack = _noise(dur) * _env(n, 0.001, 0.05) * 0.6
    return _norm(thud + clang + crack)

def sfx_crumble(dur=1.5):
    n = int(dur * SR)
    rng = np.random.default_rng(7)
    r = rng.random(n).astype(np.float32) * 2 - 1
    lr = one_pole(r, 500, 120, dur)
    amp = np.linspace(1.0, 0.0, n) * (0.6 + 0.4 * np.abs(np.sin(np.linspace(0, 9, n))))
    out = lr * amp
    # crackle bursts
    for _ in range(14):
        t = rng.uniform(0, dur * 0.85)
        i = int(t * SR)
        bl = int(0.02 * SR)
        if i + bl < n:
            out[i:i + bl] += rng.random(bl).astype(np.float32) * 2 - 1 * 0.25
    return _norm(out)

def sfx_rise(dur=1.1):
    n = int(dur * SR)
    s = _sine(dur, 220, 1600, vibrato=6)
    e = _env(n, dur * 0.35, dur * 0.45)
    shine = _sine(dur, 3200, 4800) * _env(n, dur * 0.7, dur * 0.15) * 0.3
    return _norm(s * e + shine)

def sfx_shimmer(dur=1.4):
    n = int(dur * SR)
    out = np.zeros(n, dtype=np.float32)
    rng = np.random.default_rng(3)
    for _ in range(40):
        t = rng.uniform(0, dur)
        i = int(t * SR)
        f = rng.uniform(2000, 6500)
        bl = int(rng.uniform(0.05, 0.3) * SR)
        if i + bl < n:
            seg = np.arange(bl) / SR
            out[i:i + bl] += np.sin(2 * np.pi * f * seg).astype(np.float32) \
                * np.exp(-seg * rng.uniform(8, 22)) * rng.uniform(0.2, 0.5)
    gliss = _sine(dur, 900, 2400) * _env(n, dur * 0.3, dur * 0.4) * 0.4
    return _norm(out + gliss)

def sfx_tick(dur=0.08):
    n = int(dur * SR)
    click = _noise(0.006) * 1.0
    blip = _sine(dur, 1750, 1900) * _env(n, 0.001, dur * 0.7)
    return _norm(np.concatenate([click, np.zeros(n - len(click))]) + blip)

def pad_bed(duration, key="warm", seed=0):
    """Quiet ambient synth pad, meant to sit continuously under narration+SFX.
    Normalized to a much lower peak than _norm()'s 0.85, since a continuous
    bed's duration-weighted contribution to mean_volume dwarfs sparse SFX."""
    n = int(duration * SR)
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    t = np.linspace(0, duration, n, endpoint=False)
    fund = {"warm": 55.0, "tense": 49.0}.get(key, 55.0)
    out = np.zeros(n, dtype=np.float32)
    for mult, det, amp in [(1.0, 0.0, 0.5), (1.5, 0.3, 0.28), (2.0, -0.2, 0.16)]:
        out += np.sin(2 * np.pi * (fund * mult + det) * t).astype(np.float32) * amp
    lfo = 0.75 + 0.25 * np.sin(2 * np.pi * 0.07 * t + seed)
    out *= lfo
    out = one_pole(out, 1200, 900, duration)
    peak = np.abs(out).max()
    return (out / peak * 0.4).astype(np.float32) if peak > 0 else out


GENERATORS = {
    "whoosh": sfx_whoosh,
    "swish": sfx_swish,
    "stamp": sfx_stamp,
    "pop": sfx_pop,
    "clink": sfx_clink,
    "ding": sfx_ding,
    "chime": sfx_chime,
    "slam": sfx_slam,
    "crumble": sfx_crumble,
    "rise": sfx_rise,
    "shimmer": sfx_shimmer,
    "tick": sfx_tick,
}

def ensure_sfx():
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    for name, fn in GENERATORS.items():
        p = SFX_DIR / f"{name}.wav"
        if not p.exists():
            _write_wav(p, fn())
            print(f"  generated sfx: {name}")

def _write_wav(path, mono):
    st = np.ascontiguousarray(mono).astype(np.float32)
    if st.ndim == 1:
        st = np.stack([st, st], axis=1)
    st = np.clip(st, -1.0, 1.0)
    pcm = (st * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())

def decode_mp3(path):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path),
                        "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                       capture_output=True)
    x = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32767.0
    return x

def _load_sfx():
    clips = {}
    for name in GENERATORS:
        p = SFX_DIR / f"{name}.wav"
        if p.exists():
            raw = wave.open(str(p), "rb")
            data = raw.readframes(raw.getnframes())
            raw.close()
            clips[name] = np.frombuffer(data, dtype=np.int16).reshape(-1, 2)[:, 0].astype(np.float32) / 32767.0
        else:
            clips[name] = GENERATORS[name]()
    return clips

# percussive sounds are pulled back a little and every sound starts with a short ramp, so effects never click or jump out
SOFT = {"swish": 0.8, "whoosh": 0.75, "slam": 0.7, "stamp": 0.75, "crumble": 0.8, "rise": 0.85, "pop": 0.85, "tick": 0.9}
ATTACK_S = 0.012          # fade-in of every effect
TAIL_S = 0.30             # effects ring out over the end of a segment instead of being cut off
EDGE_S = 0.006            # tiny fade on both ends of the whole track (no click where segments join)


def _ramp(n):
    return (0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, max(2, n)))).astype(np.float32)


def make_track(duration, events, narration=None, narration_offset=0.0, out_path=None,
                sfx_gain=1.0, bed=None, bed_gain=0.16):
    """Build a stereo 48k track. events: list of (t, sfx_name[, gain]).
    narration: mono float array. narration_offset: seconds delay.
    sfx_gain: global level applied on top of per-event gain.
    bed: optional mono ambient pad (e.g. from pad_bed()), mixed under everything
    at bed_gain; the final peak-clamp below still protects against clipping."""
    n = int(duration * SR)
    l = np.zeros(n, dtype=np.float32)
    r = np.zeros(n, dtype=np.float32)
    if bed is not None and len(bed):
        ln = min(len(bed), n)
        l[:ln] += bed[:ln] * bed_gain
        r[:ln] += bed[:ln] * bed_gain
    sl = np.zeros(n, dtype=np.float32)          # effects bus (faded at the end of the segment)
    clips = _load_sfx()
    for ev in events:
        t, name = ev[0], ev[1]
        gain = ev[2] if len(ev) > 2 else 1.0
        x = clips.get(name)
        if x is None:
            continue
        i = int(t * SR)
        seg = (x * gain * sfx_gain * SOFT.get(name, 1.0)).astype(np.float32)
        a = min(len(seg), int(ATTACK_S * SR))
        seg[:a] *= _ramp(a)
        ln = min(len(seg), n - i)
        if ln <= 0:
            continue
        sl[i:i + ln] += seg[:ln]
    f = min(int(TAIL_S * SR), n // 3)
    if f > 1:
        sl[n - f:] *= _ramp(f)[::-1]
    l += sl
    r += sl
    if narration is not None and len(narration):
        i = int(narration_offset * SR)
        ln = min(len(narration), n - i)
        if ln > 0:
            peak = np.abs(narration[:ln]).max()
            g = 0.8 / peak if peak > 0 else 1.0
            l[i:i + ln] += narration[:ln] * g
            r[i:i + ln] += narration[:ln] * g
    e = min(int(EDGE_S * SR), n // 4)
    if e > 1:
        ramp = _ramp(e)
        for ch in (l, r):
            ch[:e] *= ramp
            ch[n - e:] *= ramp[::-1]
    mix = np.stack([l, r], axis=1)
    peak = np.abs(mix).max()
    if peak > 0.95:
        mix = mix * (0.95 / peak)
    pcm = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
    if out_path is None:
        return pcm
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())