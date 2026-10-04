"""studio_worker.py - the process that actually renders for Flash Studio.

  python studio_worker.py render <style> <config.json>   full render (GPU encode, low priority)
  python studio_worker.py serve  <style>                 live-preview server (JSON lines on stdin/stdout)

One style per process: both styles patch the shared engine's globals, so the
studio keeps a separate preview worker per style and a fresh process per render.
"""
import asyncio
import hashlib
import importlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

import studio_config

STYLES = {"adi": "generate_adi", "dan": "style_dan"}
PREVIEW_DIR = studio_config.DATA_DIR / "preview"


def _load_style(style, cfg_path=None):
    if cfg_path:
        os.environ[studio_config.ENV] = str(cfg_path)
    cfg = studio_config.load(cfg_path)
    studio_config.apply_render_env(cfg)
    import generate_video as g
    mod = importlib.import_module(STYLES[style])
    mod.apply_to(g)
    return mod, cfg, g


def cmd_render(style, cfg_path):
    os.environ[studio_config.ENV] = str(cfg_path)
    studio_config.ensure_aspect_env(studio_config.load(cfg_path))      # before generate_video is imported
    import cooling
    import streaming
    cooling.lower_priority()
    mod, cfg, _g = _load_style(style, cfg_path)
    asyncio.run(mod.prepare())
    streaming.render_all(mod, cfg["render"]["cooling"])


_PEAK = {}


def _narration_gain_db(path):
    """The renderer scales every narration clip to a 0.8 peak before mixing; this is that gain in dB."""
    import math
    import sfx_gen
    key = (str(path), Path(path).stat().st_mtime)
    if key not in _PEAK:
        x = sfx_gen.decode_mp3(path)
        peak = float(abs(x).max()) if len(x) else 0.0
        _PEAK[key] = 20 * math.log10(0.8 / peak) if peak > 0 else 0.0
    return round(_PEAK[key], 3)


def _stem_words(g, clip_id, b0):
    """[[word, base start, base end]] of one narration clip. The display word keeps its punctuation when the
    timing file's words line up with the script's words."""
    try:
        d = json.loads((g.TIMING_DIR / f"clip{clip_id}.json").read_text(encoding="utf-8"))
    except Exception:
        return []
    words = d.get("words") or []
    toks = (d.get("narration") or "").split()
    show = toks if len(toks) == len(words) else [w["word"] for w in words]
    return [[show[i], round(b0 + w["start"], 3), round(b0 + w["end"], 3)] for i, w in enumerate(words)]


def build_program(mod, g, segs):
    """Everything on the final video's timeline, in absolute seconds: segments, narration blocks, spoken
    beats, camera moves and sound effects - what an editor would show as tracks."""
    import math
    import sfxlib
    out = {"fps": g.FPS, "w": g.W, "h": g.H, "aspect": g.ASPECT, "segments": [], "narration": [], "beats": [],
           "pans": [], "sfx": [], "stems": []}
    dur_of = {b["name"]: b["duration"] for b in sfxlib.builtin()}
    db = lambda lin: round(20 * math.log10(max(lin, 1e-6)), 3)
    t = 0.0
    for name, n in segs:
        dur = n / g.FPS
        item = {"name": name, "start": round(t, 3), "end": round(t + dur, 3), "frames": n}
        audio, clip_key = None, None
        if name == "intro":
            item["title"] = "Hook"
            audio = (g.AUDIO_DIR / f"clip{g.INTRO_HOOK_ID}.mp3", g.INTRO_PAD_BEFORE)
            clip_key = g.INTRO_HOOK_ID
            hook_dur = g.get_audio_duration(audio[0])
            end = g.INTRO_PAD_BEFORE + hook_dur + g.INTRO_PAD_AFTER
            out["sfx"] += [{"t": round(t + g.INTRO_PAD_BEFORE + 0.02, 3), "name": "whoosh"},
                           {"t": round(t + max(g.INTRO_PAD_BEFORE + 0.02, end - 0.45), 3), "name": "chime"}]
            ev_list = [(g.INTRO_PAD_BEFORE + 0.02, "whoosh", 0.6 * 0.55), (max(g.INTRO_PAD_BEFORE + 0.02, end - 0.45), "chime", 0.45 * 0.55)]
        elif name == "outro":
            item["title"] = "Close"
            out["sfx"] += [{"t": round(t + 0.25, 3), "name": "shimmer"}, {"t": round(t + 0.6, 3), "name": "chime"}]
            ev_list = [(0.25, "shimmer", 0.25), (0.6, "chime", 0.25)]
        else:
            c = g.CLIPS[int(name[4:]) - 1]
            item["title"] = c["name"]
            audio = (g.AUDIO_DIR / f"clip{c['id']}.mp3", g.PAD_BEFORE.get(c["id"], 0.45))
            clip_key = c["id"]
            for a_, b_ in g.clip_beats(c):
                out["beats"].append([round(t + a_, 3), round(t + b_, 3)])
            if hasattr(mod, "pan_beats"):
                for k in mod.pan_beats(c["id"]):
                    st, d = mod.pan_start_dur(c, k)
                    out["pans"].append([round(t + st, 3), round(t + st + d, 3)])
            ev_list = []
            for tl, nm, gain in g.sfx_events(c):
                out["sfx"].append({"t": round(t + tl, 3), "name": nm})
                ev_list.append((tl, nm, gain * 0.45))
        for k, (tl, nm, lin) in enumerate(ev_list):
            out["stems"].append({"id": f"s:{name}:{k}", "track": "sfx", "kind": "builtin", "name": nm,
                                 "b0": round(t + max(0.0, tl), 3), "b1": round(t + max(0.0, tl) + dur_of.get(nm, 1.0), 3),
                                 "gain_db": db(lin)})
        if audio:
            out["stems"].append({"id": f"n:{name}", "track": "narration", "kind": "narration",
                                 "path": str(audio[0]).replace("\\", "/"), "name": item.get("title", name),
                                 "b0": round(t + audio[1], 3), "b1": round(t + audio[1] + g.get_audio_duration(audio[0]), 3),
                                 "gain_db": _narration_gain_db(audio[0]),
                                 "words": _stem_words(g, clip_key, round(t + audio[1], 3))})
            ad = g.get_audio_duration(audio[0])
            out["narration"].append({"segment": name, "start": round(t + audio[1], 3),
                                     "end": round(t + audio[1] + ad, 3),
                                     "file": str(audio[0]).replace("\\", "/")})
        out["segments"].append(item)
        t += dur
    out["total"] = round(t, 3)
    return out


def cmd_edit(style, cfg_path, payload_path):
    """Export the post-production edit of a style (see edit.py)."""
    os.environ[studio_config.ENV] = str(cfg_path)
    studio_config.ensure_aspect_env(studio_config.load(cfg_path))
    import cooling
    import edit
    import projects
    import streaming
    cooling.lower_priority()
    studio_config.apply_render_env(studio_config.load(cfg_path))
    import generate_video as g
    payload = json.loads(Path(payload_path).read_text(encoding="utf-8"))
    base = Path(payload["base"]).resolve()
    if projects.OUTPUT_DIR.resolve() not in base.parents or not base.exists():
        raise RuntimeError("the render to edit is missing")
    out = projects.final_path(projects.active(), style, g.ASPECT, edited=True)
    t0 = time.time()
    streaming.emit("start", segments=["edit"], frames=1, cooling="-", workers=1)
    edit.export(payload["compiled"], base, out, log=lambda m: print(m, flush=True),
                progress=lambda f: streaming.emit("progress", segment="exporting", done=0, total=1, overall=f))
    print(f"Edited video saved to: {out}", flush=True)
    streaming.emit("done", path=str(out), seconds=round(time.time() - t0, 1))


def cmd_audio(cfg_path):
    """Generate / refresh the narration for both styles with the current voice settings."""
    import cooling
    cooling.lower_priority()
    for style in STYLES:
        mod, _cfg, _g = _load_style(style, cfg_path)
        print(f"narration for {style}...", flush=True)
        asyncio.run(mod.prepare())


def cmd_serve(style):
    if "FLASH_ASPECT" not in os.environ:
        studio_config.ensure_aspect_env()
    import cooling
    cooling.lower_priority()
    proto = sys.stdout                 # keep the protocol channel clean:
    sys.stdout = sys.stderr            # anything printed by libraries goes to stderr
    os.environ.pop(studio_config.ENV, None)
    mod, _cfg, g = _load_style(style)
    asyncio.run(mod.prepare())
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    segs = mod.segments()
    seg_map = dict(segs)
    applied = None

    def reply(obj):
        proto.write(json.dumps(obj) + "\n")
        proto.flush()

    reply({"ok": True, "ready": True, "style": style})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = {}
        try:
            req = json.loads(line)
            cmd = req.get("cmd")
            if cmd == "timeline":
                out = []
                for name, n in segs:
                    item = {"name": name, "frames": n, "fps": g.FPS, "seconds": round(n / g.FPS, 2)}
                    if name.startswith("clip"):
                        c = g.CLIPS[int(name[4:]) - 1]
                        item["title"] = c["name"]
                        item["beats"] = [[round(a, 2), round(b, 2)] for a, b in g.clip_beats(c)]
                        if hasattr(mod, "pan_beats"):
                            item["pans"] = [[round(s, 2), round(s + d, 2)] for s, d in
                                            (mod.pan_start_dur(c, k) for k in mod.pan_beats(c["id"]))]
                    out.append(item)
                reply({"ok": True, "id": req.get("id"), "segments": out})
            elif cmd == "program":
                reply({"ok": True, "id": req.get("id"), "program": build_program(mod, g, segs)})
            elif cmd == "preview":
                cfg = studio_config.normalize(req.get("config"))
                key = hashlib.md5(json.dumps(cfg, sort_keys=True).encode()).hexdigest()
                if key != applied:
                    mod.apply_config(cfg)
                    applied = key
                name = req.get("segment") or segs[1][0]
                total = seg_map[name]
                f = max(0, min(total - 1, int(round(float(req.get("t", 0)) * g.FPS))))
                t0 = time.time()
                img = mod.frame(name, f)
                w = int(req.get("width", 540))
                if w != img.width:
                    img = img.resize((w, int(img.height * w / img.width)))
                path = PREVIEW_DIR / f"{style}_{req.get('id', 0)}.png"
                img.save(path)
                reply({"ok": True, "id": req.get("id"), "path": str(path), "frame": f, "frames": total,
                       "ms": int((time.time() - t0) * 1000)})
            else:
                reply({"ok": False, "id": req.get("id"), "error": f"unknown command {cmd}"})
        except Exception:
            reply({"ok": False, "id": req.get("id"), "error": traceback.format_exc()[-1800:]})


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "render":
        cmd_render(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 5 and sys.argv[1] == "edit":
        cmd_edit(sys.argv[2], sys.argv[3], sys.argv[4])
    elif len(sys.argv) >= 3 and sys.argv[1] == "audio":
        cmd_audio(sys.argv[2])
    elif len(sys.argv) >= 3 and sys.argv[1] == "serve":
        cmd_serve(sys.argv[2])
    else:
        print(__doc__)
        sys.exit(2)
