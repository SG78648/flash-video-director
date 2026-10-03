"""streaming.py - shared GPU-friendly render pipeline for the style modules.

A style module (generate_adi, style_dan, ...) provides:
    OUT_DIR, VIDEO_TITLE
    apply_to(gm)                      point the engine at the story (+ config)
    segments() -> [(name, frames)]    intro, clip1..clipN, outro in order
    frame_bytes(name, f) -> bytes     raw RGB (W*H*3) for frame f of a segment

This module renders every segment with a few low-priority CPU workers, streams
the frames straight into the GPU encoder (no PNG files), then muxes each
segment with its mixed audio (video stream copied, not re-encoded) and
concatenates the result.
"""
import importlib
import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

import cooling
import generate_video as g
import projects

_MOD = None
_COOL = None


def emit(event, **kw):
    """Machine-readable progress line for the studio (stdout, one JSON per line)."""
    print("@@" + json.dumps({"event": event, **kw}), flush=True)


def _init_worker(mod_name, cool):
    global _MOD, _COOL
    cooling.lower_priority()
    _MOD = importlib.import_module(mod_name)
    _COOL = cool
    _MOD.apply_to(g)


def _chunk(args):
    seg, frames = args
    cooling.guard(_COOL["gpu_limit"])
    blob = b"".join(_MOD.frame_bytes(seg, f) for f in frames)
    if _COOL["pause"]:
        time.sleep(_COOL["pause"])
    return blob


def seed_audio(out_dir, ids, src=projects.ORIGINAL_NARRATION):
    """Reuse narration + word timing already synthesized by another style
    (same script / voice / rate) instead of calling the TTS service again."""
    src = Path(src)
    for sub, pat in (("audio", "clip{}.mp3"), ("timing", "clip{}.json")):
        dst_dir = Path(out_dir) / sub
        dst_dir.mkdir(parents=True, exist_ok=True)
        for i in ids:
            s, d = src / sub / pat.format(i), dst_dir / pat.format(i)
            if s.exists() and not d.exists():
                shutil.copy(s, d)


def render_segment(mod, name, total, cool, base_done, grand_total, step=4):
    g.VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    out = g.VIDEO_DIR / f"{name}.mp4"
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{g.W}x{g.H}", "-r", str(g.FPS), "-i", "-", *g.video_codec_args(), "-an", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, creationflags=cooling.popen_flags())
    workers = max(1, min(cool["workers"], total))
    tasks = [(name, list(range(i, min(i + step, total)))) for i in range(0, total, step)]
    done = 0
    try:
        with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker,
                                 initargs=(mod.__name__, cool)) as ex:
            for blob, task in zip(ex.map(_chunk, tasks), tasks):
                proc.stdin.write(blob)
                done += len(task[1])
                emit("progress", segment=name, done=done, total=total,
                     overall=(base_done + done) / grand_total)
    finally:
        proc.stdin.close()
        rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed encoding {name}")


def _video_frames(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=nb_frames", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return int(r.stdout.strip().split(",")[0])


def compile_segments(mod):
    """Mux every streamed segment with its mixed audio and concatenate."""
    print("Muxing audio + concatenating...", flush=True)
    outs = []
    for name, _n in mod.segments():
        vid = g.VIDEO_DIR / f"{name}.mp4"
        if name.startswith("clip"):
            g.CLIPS[int(name[4:]) - 1]["total_frames"] = _video_frames(vid)
        wav = g.build_mixed_audio(name)
        seg_out = g.OUTPUT_DIR / f"{name}.mp4"
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(vid), "-i", str(wav),
                            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(seg_out)],
                           capture_output=True, creationflags=cooling.popen_flags())
        if r.returncode != 0:
            print(r.stderr.decode()[-1500:])
        outs.append(seg_out)
    with open(g.OUTPUT_DIR / "concat.txt", "w") as fh:
        for o in outs:
            fh.write(f"file '{o.name}'\n")
    # the finished video goes to the one flat output/ folder; everything else stays in the project's style folder
    final = projects.final_path(projects.active(), mod.STYLE_ID, g.ASPECT)
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(g.OUTPUT_DIR / "concat.txt"),
                    "-c", "copy", str(final)], capture_output=True, creationflags=cooling.popen_flags())
    print(f"Video saved to: {final}", flush=True)
    return add_music(final)


def add_music(final):
    """If background music is configured, mix it onto the finished video (video stream copied) and
    return that file; otherwise return `final`."""
    try:
        import music
        import studio_config
        mixed = music.mix(final, final.with_name(final.stem + "_music.mp4"), studio_config.load()["music"],
                          log=lambda m: print(m, flush=True))
        if mixed:
            print(f"Video with music saved to: {mixed}", flush=True)
            return mixed
    except Exception as exc:
        print(f"music mix skipped: {exc}", flush=True)
    return final


def render_all(mod, cooling_name="balanced"):
    """Render every segment of the style, then mux + concatenate. Returns the final path."""
    cool = cooling.preset(cooling_name)
    segs = mod.segments()
    grand = sum(n for _s, n in segs)
    base = 0
    t0 = time.time()
    g.sfx_gen.ensure_sfx()
    emit("start", segments=[s for s, _n in segs], frames=grand, cooling=cooling_name, workers=cool["workers"])
    for name, total in segs:
        print(f"  {name} ({total} frames)", flush=True)
        render_segment(mod, name, total, cool, base, grand)
        base += total
    emit("muxing")
    final = compile_segments(mod)
    emit("done", path=str(final), seconds=round(time.time() - t0, 1))
    return final
