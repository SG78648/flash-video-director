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


def build_program(mod, g, segs):
    """Everything on the final video's timeline, in absolute seconds: segments, narration blocks, spoken
    beats, camera moves and sound effects - what an editor would show as tracks."""
    out = {"fps": g.FPS, "w": g.W, "h": g.H, "aspect": g.ASPECT, "segments": [], "narration": [], "beats": [],
           "pans": [], "sfx": []}
    t = 0.0
    for name, n in segs:
        dur = n / g.FPS
        item = {"name": name, "start": round(t, 3), "end": round(t + dur, 3), "frames": n}
        audio = None
        if name == "intro":
            item["title"] = "Hook"
            audio = (g.AUDIO_DIR / f"clip{g.INTRO_HOOK_ID}.mp3", g.INTRO_PAD_BEFORE)
            hook_dur = g.get_audio_duration(audio[0])
            end = g.INTRO_PAD_BEFORE + hook_dur + g.INTRO_PAD_AFTER
            out["sfx"] += [{"t": round(t + g.INTRO_PAD_BEFORE + 0.02, 3), "name": "whoosh"},
                           {"t": round(t + max(g.INTRO_PAD_BEFORE + 0.02, end - 0.45), 3), "name": "chime"}]
        elif name == "outro":
            item["title"] = "Close"
            out["sfx"] += [{"t": round(t + 0.25, 3), "name": "shimmer"}, {"t": round(t + 0.6, 3), "name": "chime"}]
        else:
            c = g.CLIPS[int(name[4:]) - 1]
            item["title"] = c["name"]
            audio = (g.AUDIO_DIR / f"clip{c['id']}.mp3", g.PAD_BEFORE.get(c["id"], 0.45))
            for a_, b_ in g.clip_beats(c):
                out["beats"].append([round(t + a_, 3), round(t + b_, 3)])
            if hasattr(mod, "pan_beats"):
                for k in mod.pan_beats(c["id"]):
                    st, d = mod.pan_start_dur(c, k)
                    out["pans"].append([round(t + st, 3), round(t + st + d, 3)])
            for tl, nm, _gain in g.sfx_events(c):
                out["sfx"].append({"t": round(t + tl, 3), "name": nm})
        if audio:
            ad = g.get_audio_duration(audio[0])
            out["narration"].append({"segment": name, "start": round(t + audio[1], 3),
                                     "end": round(t + audio[1] + ad, 3),
                                     "file": str(audio[0]).replace("\\", "/")})
        out["segments"].append(item)
        t += dur
    out["total"] = round(t, 3)
    return out


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
    elif len(sys.argv) >= 3 and sys.argv[1] == "audio":
        cmd_audio(sys.argv[2])
    elif len(sys.argv) >= 3 and sys.argv[1] == "serve":
        cmd_serve(sys.argv[2])
    else:
        print(__doc__)
        sys.exit(2)
