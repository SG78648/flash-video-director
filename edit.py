"""edit.py - apply a post-production edit to a finished render (the non-destructive "export").

The studio's timeline keeps an edit (cuts, trims, reordered scenes, freeze frames, speed, audio clips...)
next to the project. When you press Export the page "compiles" it into plain time ranges and this module
turns that into one ffmpeg run on the project's latest render:

    compiled = {
      "total": 79.9, "fps": 24, "duck_db": 8,
      "video": [ {"type": "clip",   "in": 0.0, "out": 1.6, "speed": 1.0, "fade_in": 0, "fade_out": 0},
                 {"type": "freeze", "at": 5.0, "dur": 1.0} ],
      "audio": [ {"bus": "narration|sfx|music",
                  "src": {"type": "narration|builtin|sfx|music", "path"/"name": ...},
                  "in": 0.0, "out": 3.2,      # seconds of the source file
                  "start": 0.4,               # where it lands on the edited timeline
                  "gain_db": -1.2, "fade_in": 0, "fade_out": 0, "speed": 1.0} ],
      "adjust": {"brightness": 0, "contrast": 1, "saturation": 1}, "fade_out_video": 0 }

The video is rebuilt from the render clip by clip (each clip is its own seek of the render, so nothing is
buffered), the audio is rebuilt from the stems (narration, effects, music) so every piece can be edited, and
the music bus is ducked under the narration bus.
"""
import json
import subprocess
from pathlib import Path

import cooling
import music
import projects
import sfxlib


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def resolve_audio(src):
    """Safe path of an audio source reference."""
    t = src.get("type")
    if t == "narration":
        p = Path(src.get("path", "")).resolve()
        if projects.PROJECTS_DIR.resolve() not in p.parents or p.suffix.lower() not in (".mp3", ".wav") or not p.exists():
            raise ValueError("bad narration path")
        return p
    if t == "builtin":
        p = sfxlib.builtin_path(src.get("name", ""))
    elif t == "sfx":
        p = sfxlib.path_of(src.get("name", ""))
    elif t == "music":
        p = music.path_of(src.get("name", ""))
    else:
        p = None
    if not p:
        raise ValueError(f"missing audio: {src}")
    return Path(p)


_CHANNELS = {}


def _channels(path):
    key = str(path)
    if key not in _CHANNELS:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=channels",
                            "-of", "csv=p=0", key], capture_output=True, text=True)
        try:
            _CHANNELS[key] = int(r.stdout.strip().split(",")[0])
        except ValueError:
            _CHANNELS[key] = 2
    return _CHANNELS[key]


def _chain_audio(label_in, a, dur, mono=False):
    """Filter chain that cuts, speeds, levels, fades and delays one audio piece."""
    sp = max(0.25, min(4.0, _f(a.get("speed"), 1.0)))
    parts = [f"atrim=start={_f(a['in']):.4f}:end={_f(a['out']):.4f}", "asetpts=PTS-STARTPTS"]
    if abs(sp - 1.0) > 1e-3:
        r = sp
        while r > 2.0:
            parts.append("atempo=2.0")
            r /= 2.0
        while r < 0.5:
            parts.append("atempo=0.5")
            r /= 0.5
        parts.append(f"atempo={r:.5f}")
    # a mono source is copied to both channels (ffmpeg's own up-mix would lose 3 dB)
    parts += ["pan=stereo|c0=c0|c1=c0" if mono else "aformat=channel_layouts=stereo",
              "aformat=sample_fmts=fltp:sample_rates=48000", f"volume={_f(a.get('gain_db')):.2f}dB"]
    fi, fo = max(0.0, _f(a.get("fade_in"))), max(0.0, _f(a.get("fade_out")))
    if fi > 0:
        parts.append(f"afade=t=in:st=0:d={min(fi, dur):.3f}")
    if fo > 0:
        parts.append(f"afade=t=out:st={max(0.0, dur - fo):.3f}:d={min(fo, dur):.3f}")
    ms = max(0, int(round(_f(a["start"]) * 1000)))
    parts.append(f"adelay={ms}|{ms}")
    return f"[{label_in}]" + ",".join(parts)


def _ass_color(hex_color, opacity=1.0):
    h = (hex_color or "#ffffff").lstrip("#")
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        r = g = b = 255
    a = int(round((1.0 - max(0.0, min(1.0, opacity))) * 255))
    return f"&H{a:02X}{b:02X}{g:02X}{r:02X}"


def _ass_time(t):
    t = max(0.0, t)
    cs = int(round(t * 100))
    return f"{cs // 360000}:{(cs // 6000) % 60:02d}:{(cs // 100) % 60:02d}.{cs % 100:02d}"


BS = chr(92)      # backslash (ASS override tags are written with it)
NL = chr(10)


def _ass_text(s):
    s = s.replace(BS, BS + BS).replace("{", BS + "{").replace("}", BS + "}").replace(chr(13), "")
    return s.replace(NL, BS + "N")


def make_ass(texts, width, height, path):
    """Subtitle file for the text clips: one style per clip (font, size, outline or box), fades, and optional
    per-word highlighting. Positions are fractions of the frame."""
    out = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}", "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
           "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
           "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"]
    lines = []
    for i, t in enumerate(texts):
        st = t.get("st") or {}
        size = max(8.0, _f(st.get("size"), 5.4) / 100.0 * min(width, height))      # % of the frame's shorter side
        box = bool(st.get("box"))
        outline = size * (0.25 if box else max(0.0, _f(st.get("ow"), 0.08)))
        ml = int(width * 0.06)
        edge = _ass_color(st.get("boxColor", "#000000"), _f(st.get("boxOp"), 0.6)) if box else _ass_color(st.get("outline", "#000000"))
        out.append(f"Style: t{i},{st.get('font', 'Arial')},{size:.1f},{_ass_color(st.get('color', '#ffffff'))},&H00FFFFFF,{edge},"
                   f"&H00000000,{-1 if st.get('bold', True) else 0},0,0,0,100,100,0,0,{3 if box else 1},{outline:.1f},0,5,{ml},{ml},0,1")
        raw = t.get("text", "")
        text = _ass_text(raw.upper() if st.get("upper") else raw)
        start, dur = _f(t.get("start")), max(0.05, _f(t.get("dur")))
        tags = f"{BS}an5{BS}pos({_f(st.get('x'), 0.5) * width:.0f},{_f(st.get('y'), 0.78) * height:.0f})"
        fi, fo = _f(st.get("fi")), _f(st.get("fo"))
        if fi > 0 or fo > 0:
            tags += f"{BS}fad({int(fi * 1000)},{int(fo * 1000)})"
        words, hl = t.get("words"), st.get("hl")
        if hl and words:                     # the spoken word lights up, then goes back to the normal colour
            norm, hi = _ass_color(st.get("color", "#ffffff")), _ass_color(hl)
            parts = []
            for w in words:
                ws, we = int(max(0, _f(w[1]) - start) * 1000), int(max(0, _f(w[2]) - start) * 1000)
                word = str(w[0])
                parts.append("{" + f"{BS}1c{norm}&{BS}t({ws},{ws + 1},{BS}1c{hi}&){BS}t({we},{we + 1},{BS}1c{norm}&)" + "}"
                             + _ass_text(word.upper() if st.get("upper") else word))
            text = " ".join(parts)
        lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(start + dur)},t{i},,0,0,0,,{{{tags}}}{text}")
    out += ["", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text", *lines]
    Path(path).write_text(NL.join(out) + NL, encoding="utf-8")


def build(compiled, base_video, out_path, codec_args, fps=24):
    """(ffmpeg argv, total seconds). Raises ValueError for anything that does not check out."""
    video = compiled.get("video") or []
    if not video:
        raise ValueError("the edit has no video")
    inputs, chains, count = [], [], [0]

    def add_input(*pre, path):
        inputs.extend([*pre, "-i", str(path)])
        count[0] += 1
        return count[0] - 1

    # ---- video
    vlabels, total = [], 0.0
    for i, v in enumerate(video):
        if v.get("type") == "freeze":
            at, dur = max(0.0, _f(v["at"])), max(0.1, _f(v["dur"]))
            k = add_input("-ss", f"{at:.4f}", "-t", "0.5", path=base_video)
            n = max(1, int(round(dur * fps)))      # one frame, repeated: loop re-reads it, setpts re-times every copy
            chains.append(f"[{k}:v]trim=end_frame=1,setpts=PTS-STARTPTS,loop=loop={n - 1}:size=1:start=0,"
                          f"setpts=N/({fps}*TB),fps={fps},setsar=1,format=yuv420p[v{i}]")
            dur = n / fps
        else:
            a, b = max(0.0, _f(v["in"])), _f(v["out"])
            sp = max(0.25, min(4.0, _f(v.get("speed"), 1.0)))
            if b - a < 0.05:
                continue
            dur = (b - a) / sp
            k = add_input("-ss", f"{a:.4f}", "-t", f"{b - a + 0.1:.4f}", path=base_video)
            f = f"[{k}:v]trim=duration={b - a:.4f},setpts=(PTS-STARTPTS)/{sp:.5f},fps={fps},setsar=1,format=yuv420p"
            fi, fo = max(0.0, _f(v.get("fade_in"))), max(0.0, _f(v.get("fade_out")))
            if fi > 0:
                f += f",fade=t=in:st=0:d={min(fi, dur):.3f}"
            if fo > 0:
                f += f",fade=t=out:st={max(0.0, dur - fo):.3f}:d={min(fo, dur):.3f}"
            chains.append(f + f"[v{i}]")
        vlabels.append(f"[v{i}]")
        total += dur
    if not vlabels:
        raise ValueError("the edit has no video")
    vout = "vc"
    chains.append("".join(vlabels) + f"concat=n={len(vlabels)}:v=1:a=0[{vout}]")
    adj = compiled.get("adjust") or {}
    br, ct, sa = _f(adj.get("brightness"), 0.0), _f(adj.get("contrast"), 1.0), _f(adj.get("saturation"), 1.0)
    if abs(br) > 1e-3 or abs(ct - 1) > 1e-3 or abs(sa - 1) > 1e-3:
        chains.append(f"[{vout}]eq=brightness={br:.3f}:contrast={ct:.3f}:saturation={sa:.3f}[vadj]")
        vout = "vadj"
    texts = [t for t in (compiled.get("texts") or []) if (t.get("text") or "").strip() and _f(t.get("start")) < total]
    ass_path = None
    if texts:
        ass_path = Path(out_path).with_suffix(".ass")
        make_ass(texts, int(_f(compiled.get("w"), 1080)), int(_f(compiled.get("h"), 1920)), ass_path)
        rel = Path(ass_path).relative_to(projects.ROOT).as_posix() if projects.ROOT in Path(ass_path).parents else Path(ass_path).as_posix()
        chains.append(f"[{vout}]ass=filename='{rel}'[vtxt]")
        vout = "vtxt"
    fv = max(0.0, _f(compiled.get("fade_out_video")))
    if fv > 0:
        chains.append(f"[{vout}]fade=t=out:st={max(0.0, total - fv):.3f}:d={fv:.3f}[vfade]")
        vout = "vfade"

    # ---- audio
    buses = {"narration": [], "sfx": [], "music": []}
    for j, a in enumerate(compiled.get("audio") or []):
        bus = a.get("bus") if a.get("bus") in buses else "sfx"
        src_in, src_out = _f(a["in"]), _f(a["out"])
        if src_out - src_in < 0.02:
            continue
        start = _f(a["start"])
        if start >= total:
            continue
        sp = max(0.25, min(4.0, _f(a.get("speed"), 1.0)))
        dur = (src_out - src_in) / sp
        path = resolve_audio(a["src"])
        k = add_input(path=path)
        lab = f"a{j}"
        chains.append(_chain_audio(f"{k}:a", a, dur, mono=_channels(path) == 1) + f"[{lab}]")
        buses[bus].append(f"[{lab}]")
    bus_out = {}
    for name, labs in buses.items():
        if not labs:
            continue
        if len(labs) == 1:
            chains.append(f"{labs[0]}anull[bus_{name}]")
        else:
            chains.append("".join(labs) + f"amix=inputs={len(labs)}:normalize=0:dropout_transition=0:duration=longest[bus_{name}]")
        bus_out[name] = f"bus_{name}"
    duck = _f(compiled.get("duck_db"), 0.0)
    final_in = []
    if "narration" in bus_out:
        if "music" in bus_out and duck > 0:
            chains.append(f"[{bus_out['narration']}]asplit=2[narr_mix][narr_key]")
            ratio = min(20.0, 1.0 + duck * 0.9)
            chains.append(f"[{bus_out['music']}][narr_key]sidechaincompress=threshold=0.04:ratio={ratio:.1f}:attack=25:release=400[music_d]")
            final_in += ["[narr_mix]", "[music_d]"]
            bus_out.pop("music")
        else:
            final_in.append(f"[{bus_out['narration']}]")
    for name in ("sfx", "music"):
        if name in bus_out:
            final_in.append(f"[{bus_out[name]}]")
    if final_in:
        chains.append("".join(final_in) + f"amix=inputs={len(final_in)}:normalize=0:dropout_transition=0:duration=longest,"
                      + ("loudnorm=I=-14:TP=-1.5:LRA=11," if compiled.get("loudnorm") else "")
                      + f"alimiter=limit=0.95,apad=whole_dur={total:.3f},atrim=duration={total:.3f}[aout]")
    else:
        chains.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={total:.3f}[aout]")

    script = Path(out_path).with_suffix(".filter.txt")
    script.write_text(";\n".join(chains), encoding="utf-8")
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostats", "-progress", "pipe:1", *inputs,
           "-filter_complex_script", str(script), "-map", f"[{vout}]", "-map", "[aout]", *codec_args,
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", f"{total:.3f}", str(out_path)]
    return cmd, total, script


def export(compiled, base_video, out_path, log=print, progress=None):
    import generate_video as g
    cmd, total, script = build(compiled, base_video, out_path, g.video_codec_args(), g.FPS)
    log(f"edit: {len(compiled.get('video') or [])} video clip(s), {len(compiled.get('audio') or [])} audio clip(s), {total:.1f}s")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=cooling.popen_flags())
    err_lines = []
    import threading
    threading.Thread(target=lambda: err_lines.extend(proc.stderr.read().splitlines()[-12:]), daemon=True).start()
    for line in proc.stdout:
        if line.startswith("out_time_us=") and progress:
            try:
                progress(min(0.99, int(line.split("=")[1]) / 1e6 / max(total, 0.1)))
            except ValueError:
                pass
    rc = proc.wait()
    script.unlink(missing_ok=True)
    Path(out_path).with_suffix(".ass").unlink(missing_ok=True)
    if rc != 0 or not Path(out_path).exists():
        raise RuntimeError("export failed: " + " | ".join(err_lines[-6:]))
    return Path(out_path)


def load(style, project=None):
    p = projects.edit_path(style, project)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def save(style, data, project=None):
    p = projects.edit_path(style, project)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, separators=(",", ":"))
    if len(text) > 2_000_000:
        raise ValueError("the edit is too large")
    p.write_text(text, encoding="utf-8")
