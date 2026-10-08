"""studio.py - Flash Studio: a local app to configure the layout and style
(adi / Dan) of the video, preview it live, and render it on the GPU.

    python studio.py            starts the app and opens it in your browser
    python studio.py --no-browser --port 8765

Everything runs on this machine (127.0.0.1 only). Previews and renders run in
separate worker processes (studio_worker.py); renders use the GPU encoder and
the cooling presets from cooling.py.
"""
import argparse
import base64
import collections
import ctypes
import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

import cooling  # noqa: E402
import edit  # noqa: E402
import music  # noqa: E402
import photos  # noqa: E402
import projects  # noqa: E402
import sfxlib  # noqa: E402
import studio_config  # noqa: E402
import voice  # noqa: E402

UI_DIR = ROOT / "studio_ui"
DATA = projects.DATA_DIR
STYLES = ("adi", "dan", "flash")


# ------------------------------------------------------------------ preview workers
class PreviewWorker:
    def __init__(self, style):
        self.style = style
        self.proc = None
        self.lock = threading.Lock()
        self.seq = 0
        self.timeline = None
        self.aspect = "9:16"          # the format this process was started for (the engine reads it once, at import)
        self.project = None           # ... and the project (it decides which folder the narration is read from)

    def _spawn(self):
        DATA.mkdir(exist_ok=True)
        log = open(DATA / f"preview_{self.style}.log", "w")
        self.proc = subprocess.Popen(
            [sys.executable, "studio_worker.py", "serve", self.style], cwd=ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=cooling.popen_flags(),
            env=dict(os.environ, FLASH_ASPECT=self.aspect, FLASH_PROJECT=self.project))
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError(f"{self.style} preview worker failed to start (see studio_data/preview_{self.style}.log)")

    def ask(self, obj, aspect=None):
        with self.lock:
            proj = projects.active()
            if (aspect in ("9:16", "1:1", "16:9") and aspect != self.aspect) or proj != self.project:
                self._stop()                       # a different format / project needs a fresh engine process
                self.aspect, self.project, self.timeline = (aspect if aspect in ("9:16", "1:1", "16:9") else self.aspect), proj, None
            if self.proc is None or self.proc.poll() is not None:
                self._spawn()
            self.seq += 1
            obj = dict(obj, id=self.seq)
            self.proc.stdin.write(json.dumps(obj) + "\n")
            self.proc.stdin.flush()
            line = self.proc.stdout.readline()
            if not line:
                self.proc = None
                raise RuntimeError("preview worker stopped unexpectedly")
            return json.loads(line)

    def _stop(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.close()
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
        self.proc = None

    def get_timeline(self, aspect=None):
        if self.timeline is None or (aspect and aspect != self.aspect) or projects.active() != self.project:
            r = self.ask({"cmd": "timeline"}, aspect)
            if not r.get("ok"):
                raise RuntimeError(r.get("error"))
            self.timeline = r["segments"]
        return self.timeline

    def get_program(self, aspect=None):
        r = self.ask({"cmd": "program"}, aspect)
        if not r.get("ok"):
            raise RuntimeError(r.get("error"))
        return r["program"]

    def close(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.close()
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()


WORKERS = {s: PreviewWorker(s) for s in STYLES}


# ------------------------------------------------------------------ render job
class RenderJob:
    def __init__(self):
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        self.state = "idle"          # idle | running | done | error | cancelled
        self.kind = None             # render | audio | install | edit
        self.on_done = getattr(self, "on_done", None)
        self.style = None
        self.progress = 0.0
        self.segment = ""
        self.log = collections.deque(maxlen=60)
        self.final = None
        self.seconds = None
        self.error = None
        self.proc = None
        self.started = None
        self.frames = 0
        self.workers = 0

    def start(self, kind, style, cfg, payload=None):
        with self.lock:
            if self.state == "running":
                raise RuntimeError("another job is already running (" + str(self.kind) + ")")
            on_done = self.on_done
            self.reset()
            self.on_done = on_done
            jobs = DATA / "jobs"
            jobs.mkdir(parents=True, exist_ok=True)
            cfg_path = jobs / f"{time.strftime('%Y%m%d_%H%M%S')}_{kind}_{style}.json"
            studio_config.save(cfg or studio_config.defaults(), cfg_path)
            if kind == "render":
                cmd = [sys.executable, "studio_worker.py", "render", style, str(cfg_path)]
            elif kind == "audio":
                cmd = [sys.executable, "studio_worker.py", "audio", str(cfg_path)]
            elif kind == "edit":
                payload_path = jobs / f"{time.strftime('%Y%m%d_%H%M%S')}_edit_{style}_payload.json"
                payload_path.write_text(json.dumps(payload), encoding="utf-8")
                cmd = [sys.executable, "studio_worker.py", "edit", style, str(cfg_path), str(payload_path)]
            elif kind == "install":
                cmd = [sys.executable, "setup_chatterbox.py"]
            else:
                raise RuntimeError("unknown job " + kind)
            self.kind, self.style, self.state, self.started = kind, style, "running", time.time()
            self.proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=cooling.popen_flags(),
                                         env=dict(os.environ, FLASH_PROJECT=projects.active()))
            threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            line = line.rstrip()
            if line.startswith("@@"):
                try:
                    ev = json.loads(line[2:])
                except ValueError:
                    continue
                if ev["event"] == "start":
                    self.frames, self.workers = ev["frames"], ev["workers"]
                elif ev["event"] == "progress":
                    self.progress, self.segment = ev["overall"], ev["segment"]
                elif ev["event"] == "muxing":
                    self.segment = "muxing audio"
                    self.progress = 0.99
                elif ev["event"] == "done":
                    self.final, self.seconds = ev["path"], ev["seconds"]
                elif ev["event"] == "voice":
                    self.progress = ev["done"] / max(1, ev["total"])
                    self.segment = "narration %d/%d" % (ev["done"], ev["total"])
                elif ev["event"] == "setup":
                    steps = {"start": 0.02, "venv": 0.05, "torch": 0.12, "chatterbox": 0.55, "weights": 0.75,
                             "done": 1.0, "failed": 0.0}
                    self.progress = steps.get(ev["step"], self.progress)
                    self.segment = ev.get("msg") or ev["step"]
            elif line:
                self.log.append(line[-300:])
        rc = self.proc.wait()
        with self.lock:
            if self.state == "cancelled":
                return
            if rc == 0 and (self.final or self.kind not in ("render", "edit")):
                self.state, self.progress = "done", 1.0
            else:
                self.state = "error"
                self.error = "%s failed (exit %s) - see the log" % (self.kind, rc)
            if self.on_done:
                try:
                    self.on_done(self.kind, self.state)
                except Exception:
                    pass

    def cancel(self):
        with self.lock:
            if self.state == "running" and self.proc:
                self.state = "cancelled"
                subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], capture_output=True)

    def status(self):
        elapsed = (time.time() - self.started) if self.started else 0
        eta = None
        if self.state == "running" and self.progress > 0.02:
            eta = round(elapsed / self.progress - elapsed)
        return {"state": self.state, "kind": self.kind, "style": self.style, "progress": round(self.progress, 4),
                "segment": self.segment, "log": list(self.log), "final": self.final,
                "seconds": self.seconds, "error": self.error, "elapsed": round(elapsed),
                "eta": eta, "workers": self.workers}


JOB = RenderJob()


# ------------------------------------------------------------------ system stats
class _FT(ctypes.Structure):
    _fields_ = [("lo", ctypes.c_uint32), ("hi", ctypes.c_uint32)]


_cpu_prev = [None]


def _ft(v):
    return (v.hi << 32) | v.lo


def cpu_percent():
    try:
        idle, kern, user = _FT(), _FT(), _FT()
        ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user))
        cur = (_ft(idle), _ft(kern) + _ft(user))
        prev, _cpu_prev[0] = _cpu_prev[0], cur
        if not prev:
            return None
        d_total, d_idle = cur[1] - prev[1], cur[0] - prev[0]
        return None if d_total <= 0 else round(100 * (1 - d_idle / d_total))
    except Exception:
        return None


def system_stats():
    st = cooling.gpu_stats()
    return {"cpu": cpu_percent(),
            "gpu": None if st is None else {"temp": st[0], "util": st[1], "encoder": st[2], "name": st[3]}}


# ------------------------------------------------------------------ helpers
def load_state():
    """The active project's settings."""
    return studio_config.load(projects.config_path())


def save_state(cfg, project=None):
    name = project or projects.active()
    if not projects.exists(name):
        raise ValueError("no such project")
    studio_config.save(cfg, projects.config_path(name))


def latest_base(style, aspect="9:16"):
    """Newest finished render of this project's style in this format WITHOUT music (the timeline plays this one)."""
    proj = projects.active()
    for v in projects.list_finals():
        if v["project"] == proj and v["style"] == style and v["aspect"] == aspect and not v["music"]:
            return v["path"]
    return None


def fit_plan(style, aspect, aha=None):
    import re
    """(length, aha second, where it came from) for a piece of music fitted to this project's video.
    The aha is the moment the idea lands: your number, or - automatically - the first word of the script's answer
    (the first positive quote after a negative thought), else 76 % of the way through."""
    segs = WORKERS[style].get_timeline(aspect)
    total = round(sum(s["seconds"] for s in segs), 2)
    base = latest_base(style, aspect)
    length = round(music.video_duration(base), 2) if base else total
    if aha not in (None, ""):
        a = float(aha)
        if not 5.0 <= a <= length - 5.0:
            raise ValueError("the aha moment must be between 5 s and %.0f s (the video is %.1f s long)" % (length - 5, length))
        return length, a, "your choice"
    import script_story
    story = script_story.load(projects.active())
    if story:
        best, seen_neg = None, False                 # the pivot: the first positive quote after a negative one
        for cid, feats in sorted(story["feats"].items(), key=lambda kv: int(kv[0])):
            for bi, f in enumerate(feats):
                if f["kind"] != "quote":
                    continue
                if f.get("neg"):
                    seen_neg = True
                elif best is None or (seen_neg and not best[3]):
                    best = (int(cid), bi, f, seen_neg)
        if not best:
            # no positive quote: the turn is the beat after the last negative thought that reframes it ("Maybe they're the exact things ...")
            order = [(int(c), i, f) for c, feats in sorted(story["feats"].items(), key=lambda kv: int(kv[0])) for i, f in enumerate(feats)]
            last_neg = max([k for k, (_c, _i, f) in enumerate(order) if f["kind"] == "quote" and f.get("neg")], default=None)
            if last_neg is not None:
                strong = re.compile(r"\b(exact|real|the goal|truth|answer)\b", re.I)
                weak = re.compile(r"\b(maybe|but|instead|actually|so)\b", re.I)
                scored = [(2 if strong.search(f["text"]) else 1 if weak.search(f["text"]) else 0, -k, k) for k, (_c, _i, f) in enumerate(order[last_neg + 1:last_neg + 5], last_neg + 1)]
                scored = [x for x in scored if x[0] > 0]
                if scored:
                    k = max(scored)[2]
                    cid, bi, f = order[k]
                    best = (cid, bi, f, True)
        if best:
            cid, bi, f, _after_neg = best
            start = sum(s["seconds"] for s in segs[:cid])             # intro + the clips before this one
            seg = segs[cid]
            if seg.get("beats") and bi < len(seg["beats"]):
                b0, b1 = seg["beats"][bi]
                words = max(1, len(f["text"].split()))
                lead = len((f.get("lead") or "").split())
                t = start + b0 + (b1 - b0) * min(0.8, lead / words)
                what = ("the answer: \u201c" + f["quote"][:60] + "\u201d") if f["kind"] == "quote" else ("the turn: \u201c" + f["text"][:60] + "\u201d")
                return length, round(min(max(t, 5.0), length - 5.0), 2), what
    return length, round(length * 0.76, 2), "76 % through the video (no clear answer found in the script)"


def safe_output_path(rel):
    """A narration file inside a project (the timeline draws its waveform)."""
    p = (ROOT / rel).resolve()
    if projects.PROJECTS_DIR.resolve() in p.parents and p.suffix in (".mp3", ".wav", ".mp4") and p.exists():
        return p
    raise ValueError("bad path")


def voice_state():
    cfg = load_state()
    v = cfg["voice"]
    tag = voice.tag_for(v)
    disk = {s: voice.on_disk_tag(projects.style_dir(s) / "timing") for s in STYLES}
    return {"installed": voice.chatterbox_installed(), "voices": studio_config.list_voices(), "tag": tag,
            "on_disk": disk, "in_sync": all(t == tag for t in disk.values() if t is not None) and any(t is not None for t in disk.values()), "setup_gb": 6.5}


def reset_workers():
    """Close the preview engines so the next request starts them on the new narration / script."""
    for w in WORKERS.values():
        w.close()
        w.proc = None
        w.timeline = None


def after_job(kind, state):
    """New narration changes every beat time: restart the preview workers."""
    if kind == "audio" and state == "done":
        reset_workers()


def script_state():
    import script_story
    proj = projects.active()
    story = script_story.load(proj)
    p = script_story.script_path(proj)
    return {"project": proj, "has_script": story is not None,
            "script": p.read_text(encoding="utf-8") if story is not None and p.exists() else "",
            "clips": len(story["clips"]) if story else None}


JOB.on_done = after_job


def list_videos():
    """Everything the studio has rendered - one flat folder, output/ - newest first."""
    return [{"project": v["project"], "style": v["style"], "aspect": v["aspect"], "name": v["name"], "size": v["size"],
             "mtime": v["mtime"], "url": "/videos/output/" + v["name"], "music": v["music"],
             "edited": v["name"].endswith("_edit.mp4")}
            for v in projects.list_finals()][:80]


def sfx_lists():
    return {"builtin": sfxlib.builtin(), "library": sfxlib.list_library(), "project": sfxlib.list_project()}


def photos_state():
    return {"mode": photos.mode(), "has_key": bool(photos.get_key()), "provider": photos.provider(), "count": photos.count(),
            "dir": str(photos.PHOTO_DIR), "have": {n: bool(photos.get_key(n)) for n in photos.PROVIDERS}}


def projects_state():
    return {"active": projects.active(), "projects": projects.list_projects()}


def open_folder(what):
    path = {"output": projects.OUTPUT_DIR, "project": projects.project_dir(), "library": projects.LIBRARY_DIR, "photos": photos.PHOTO_DIR}[what]
    path.mkdir(parents=True, exist_ok=True)
    os.startfile(str(path))


# ------------------------------------------------------------------ HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "FlashStudio/1.0"

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _file(self, path, ctype=None):
        path = Path(path)
        size = path.stat().st_size
        ctype = ctype or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        rng = self.headers.get("Range")
        start, end, code = 0, size - 1, 200
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            start = int(a) if a else 0
            end = int(b) if b else size - 1
            end = min(end, size - 1)
            code = 206
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(path, "rb") as fh:
            fh.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = fh.read(min(1 << 20, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    return
                left -= len(chunk)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path in ("/", "/index.html"):
                return self._file(UI_DIR / "index.html", "text/html; charset=utf-8")
            if u.path.startswith("/ui/"):                        # the page's script files
                f = (UI_DIR / unquote(u.path[len("/ui/"):])).resolve()
                if UI_DIR.resolve() in f.parents and f.suffix in (".js", ".css") and f.exists():
                    return self._file(f, "text/javascript; charset=utf-8" if f.suffix == ".js" else "text/css")
            if u.path == "/api/schema":
                return self._json({"schema": studio_config.SCHEMA, "defaults": studio_config.defaults(),
                                   "presets": studio_config.list_presets(),
                                   "cooling": {k: v for k, v in cooling.PRESETS.items()}})
            if u.path == "/api/state":
                return self._json(load_state())
            if u.path == "/api/timeline":
                style = q.get("style", ["adi"])[0]
                return self._json({"segments": WORKERS[style].get_timeline(q.get("aspect", [None])[0])})
            if u.path == "/api/system":
                return self._json(system_stats())
            if u.path == "/api/render":
                return self._json(JOB.status())
            if u.path == "/api/voice":
                return self._json(voice_state())
            if u.path == "/api/music":
                return self._json({"library": music.list_library(), "project": music.list_project()})
            if u.path == "/api/script":
                return self._json(script_state())
            if u.path == "/api/photos":
                return self._json(photos_state())
            if u.path == "/api/photos/list":       # the review list: every photo with where it came from
                return self._json({"photos": photos.list_photos(), "credits": photos.credits_text()})
            if u.path.startswith("/photo/"):       # a photo of the library (thumbnails in the review list)
                f = (photos.PHOTO_DIR / unquote(u.path[len("/photo/"):])).resolve()
                if photos.PHOTO_DIR.resolve() in f.parents and f.suffix.lower() in photos.EXT and f.exists():
                    return self._file(f)
            if u.path == "/api/photos/things":     # the things the active project's script names that can have a photo
                import script_story
                story = script_story.load(projects.active())
                things = photos.things_in(story) if story else []
                return self._json({"things": [{"icon": ic, "label": photos.pretty(ic), "have": bool(photos.lookup(ic))} for ic in (things or sorted(photos.PHOTO_WORTHY))]})
            if u.path == "/api/projects":
                return self._json(projects_state())
            if u.path == "/api/sfx":
                return self._json(sfx_lists())
            if u.path == "/api/assets":
                return self._json({"assets": edit.list_assets()})
            if u.path.startswith("/asset/"):
                p = edit.asset_path(unquote(u.path[len("/asset/"):]).rsplit(".", 1)[0])
                if p:
                    return self._file(p, "image/png")
            if u.path == "/api/edit":
                style = q.get("style", ["adi"])[0]
                return self._json({"edit": edit.load(style)})
            if u.path.startswith("/sfx/"):                       # the project's copy of an effect
                p = sfxlib.path_of(unquote(u.path[len("/sfx/"):]).rsplit(".", 1)[0])
                if p:
                    return self._file(p, "audio/flac")
            if u.path.startswith("/builtin/"):                   # the renderer's own effects
                p = sfxlib.builtin_path(unquote(u.path[len("/builtin/"):]).rsplit(".", 1)[0])
                if p:
                    return self._file(p, "audio/wav")
            if u.path.startswith("/lib/"):                       # the libraries (to audition before adding)
                _, kind, fname = u.path.split("/", 2)[0:1] + u.path[len("/lib/"):].split("/", 1)
                nm = unquote(fname).rsplit(".", 1)[0]
                p = music.library_path(nm) if kind == "music" else sfxlib.library_path(nm) if kind == "sfx" else None
                if p:
                    return self._file(p, "audio/flac")
            if u.path == "/stem":                                # a narration file of the project
                return self._file(safe_output_path(q["path"][0]), "audio/mpeg")
            if u.path == "/api/program":
                style = q.get("style", ["adi"])[0]
                asp = q.get("aspect", ["9:16"])[0]
                prog = WORKERS[style].get_program(asp)
                base = latest_base(style, asp)
                prog["video"] = ("/videos/" + base.relative_to(ROOT).as_posix()) if base else None
                return self._json(prog)
            if u.path == "/api/waveform":
                kind = q.get("kind", ["file"])[0]
                if kind in ("music", "sfx", "builtin", "libmusic", "libsfx"):
                    nm = q["name"][0]
                    p = {"music": music.path_of, "sfx": sfxlib.path_of, "builtin": sfxlib.builtin_path,
                         "libmusic": music.library_path, "libsfx": sfxlib.library_path}[kind](nm)
                    if not p:
                        raise ValueError("unknown track")
                else:
                    p = safe_output_path(q["path"][0])
                per = int(q.get("per_sec", ["50"])[0])
                return self._json({"peaks": music.peaks(p, per), "per_sec": per, "duration": music.duration(p)})
            if u.path.startswith("/music/"):
                p = music.path_of(unquote(u.path[len("/music/"):]).rsplit(".", 1)[0])
                if p:
                    return self._file(p, "audio/flac")
            if u.path == "/api/videos":
                return self._json(list_videos())
            if u.path.startswith("/api/presets/"):
                return self._json(studio_config.load_preset(unquote(u.path.split("/", 3)[3])))
            if u.path.startswith("/videos/"):
                p = (ROOT / unquote(u.path[len("/videos/"):])).resolve()
                if ROOT in p.parents and p.suffix == ".mp4" and p.exists():
                    return self._file(p, "video/mp4")
            self._json({"error": "not found"}, 404)
        except Exception as exc:
            self._json({"error": str(exc)}, 500)

    def do_POST(self):
        u = urlparse(self.path)
        try:
            body = self._body()
            if u.path == "/api/state":
                proj = parse_qs(u.query).get("project", [None])[0]
                if not proj:      # a page that does not say which project it edits (an old tab) must not overwrite the active one
                    raise RuntimeError("reload the page - this tab is out of date")
                save_state(body, proj)
                return self._json({"ok": True})
            if u.path.startswith("/api/projects/"):
                if JOB.status()["state"] == "running":
                    raise RuntimeError("wait for the running job to finish")
                act = u.path.rsplit("/", 1)[1]
                if act == "create":
                    projects.set_active(projects.create(body.get("name", ""), body.get("script"),
                                                      studio_config.normalize(body["config"]) if body.get("config") else None))
                elif act == "select":
                    if not projects.exists(body.get("name")):
                        raise ValueError("no such project")
                    projects.set_active(body["name"])
                elif act == "rename":
                    projects.rename(body.get("old", ""), body.get("new", ""))
                elif act == "delete":
                    projects.delete(body.get("name", ""))
                else:
                    raise ValueError("unknown action")
                return self._json(projects_state())
            if u.path == "/api/script":
                if JOB.status()["state"] == "running":
                    raise RuntimeError("wait for the running job to finish")
                import script_story
                script_story.save_script(body.get("script", ""), projects.active())
                reset_workers()
                return self._json(script_state())
            if u.path == "/api/photos/key":
                photos.set_key(body.get("key", ""), body.get("provider", "pexels"))
                return self._json(photos_state())
            if u.path == "/api/photos/remove":
                photos.remove_photo(body.get("file", ""))
                reset_workers()
                return self._json(photos_state())
            if u.path == "/api/photos/upload":      # a photo you chose yourself for one of the things in the script
                photos.save_own(body.get("icon", ""), base64.b64decode(body.get("data", "")))
                reset_workers()
                return self._json(photos_state())
            if u.path == "/api/photos/fetch":      # only when asked: search Pexels with the user's key, save to library/photos
                import script_story
                story = script_story.load(projects.active())
                if story is None:
                    raise ValueError("this project uses the built-in story: stock photos are for projects made from a script")
                res = photos.fetch_for_story(story)
                reset_workers()
                return self._json(dict(photos_state(), **res))
            if u.path == "/api/open":
                open_folder(body.get("what", "output"))
                return self._json({"ok": True})
            if u.path == "/api/preview":
                style = body.get("style", "adi")
                asp = ((body.get("config") or {}).get("render") or {}).get("aspect", "9:16")
                r = WORKERS[style].ask({"cmd": "preview", "config": body.get("config"),
                                        "segment": body.get("segment"), "t": body.get("t", 0),
                                        "width": body.get("width", 540)}, asp)
                if not r.get("ok"):
                    return self._json({"error": r.get("error")}, 500)
                data = Path(r["path"]).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("X-Frame", str(r["frame"]))
                self.send_header("X-Frames", str(r["frames"]))
                self.send_header("X-Ms", str(r["ms"]))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
                return
            if u.path == "/api/render":
                JOB.start("render", body.get("style", "adi"), body.get("config"))
                return self._json(JOB.status())
            if u.path == "/api/assets/upload":
                name = edit.save_asset(body.get("name", ""), base64.b64decode(body.get("data", "")), body.get("ext", ".png"))
                return self._json({"ok": True, "name": name, "assets": edit.list_assets()})
            if u.path == "/api/assets/remove":
                edit.delete_asset(body.get("name", ""))
                return self._json({"ok": True, "assets": edit.list_assets()})
            if u.path == "/api/sfx/upload":
                name = sfxlib.save_to_library(body.get("name", ""), base64.b64decode(body.get("data", "")), body.get("ext", ".wav"))
                if body.get("add", True):
                    sfxlib.import_to_project(name)
                return self._json(dict(sfx_lists(), ok=True, name=name))
            if u.path == "/api/sfx/import":
                name = sfxlib.import_to_project(body.get("name", ""))
                return self._json(dict(sfx_lists(), ok=True, name=name))
            if u.path == "/api/sfx/remove":
                if body.get("scope") == "library":
                    sfxlib.delete_library(body.get("name", ""))
                else:
                    sfxlib.delete_project_copy(body.get("name", ""))
                return self._json(dict(sfx_lists(), ok=True))
            if u.path == "/api/edit":
                edit.save(parse_qs(u.query).get("style", ["adi"])[0], body, parse_qs(u.query).get("project", [None])[0])
                return self._json({"ok": True})
            if u.path == "/api/edit/export":
                style = body.get("style", "adi")
                cfg = studio_config.normalize(body.get("config") or load_state())
                base = latest_base(style, cfg["render"]["aspect"])
                if not base:
                    raise RuntimeError("render the " + style + " video in " + cfg["render"]["aspect"] + " first - the edit is applied to a finished render")
                JOB.start("edit", style, cfg, {"base": str(base), "compiled": body.get("compiled")})
                return self._json(JOB.status())
            if u.path == "/api/music/upload":      # into the library, and (by default) straight into this project
                name = music.save_to_library(body.get("name", ""), base64.b64decode(body.get("data", "")),
                                             body.get("ext", ".mp3"))
                if body.get("add", True):
                    music.import_to_project(name)
                return self._json({"ok": True, "name": name, "library": music.list_library(), "project": music.list_project()})
            if u.path == "/api/music/import":      # library -> a copy inside the project
                name = music.import_to_project(body.get("name", ""))
                return self._json({"ok": True, "name": name, "library": music.list_library(), "project": music.list_project()})
            if u.path == "/api/music/remove":
                if body.get("scope") == "library":
                    music.delete_library(body.get("name", ""))
                else:
                    music.delete_project_copy(body.get("name", ""))
                return self._json({"ok": True, "library": music.list_library(), "project": music.list_project()})
            if u.path == "/api/music/fit":         # original music with its aha on the video's idea, the video's length
                import music_gen
                mood = body.get("mood", "Dark Pulse")
                if mood not in music_gen.MOODS:
                    raise ValueError("unknown mood")
                style = body.get("style", "adi")
                cfg = studio_config.normalize(body.get("config") or load_state())
                length, aha, source = fit_plan(style, cfg["render"]["aspect"], body.get("aha"))
                name = music_gen.make(mood, length, aha, "%s - %s (aha %ds)" % (projects.active(), mood, round(aha)))
                dur = music.duration(music.library_path(name))
                return self._json({"ok": True, "name": name, "duration": dur, "length": length, "aha": aha, "source": source})
            if u.path == "/api/music/export":
                style = body.get("style", "adi")
                cfg = studio_config.normalize(body.get("config") or load_state())
                asp = cfg["render"]["aspect"]
                base = latest_base(style, asp)
                if not base:
                    raise RuntimeError("render the " + style + " video in " + asp + " first - the music is mixed onto a finished render")
                out = music.mix(base, base.with_name(base.stem + "_music.mp4"), cfg["music"])
                if not out:
                    raise RuntimeError("no music selected (or it is switched off)")
                return self._json({"ok": True, "file": out.name, "url": "/videos/output/" + out.name})
            if u.path == "/api/voice/generate":
                JOB.start("audio", "both", body.get("config") or load_state())
                return self._json(JOB.status())
            if u.path == "/api/voice/install":
                JOB.start("install", "voice", None)
                return self._json(JOB.status())
            if u.path == "/api/voice/upload":
                name = voice.save_reference(body.get("name", ""), base64.b64decode(body.get("data", "")),
                                            body.get("ext", ".wav"))
                return self._json({"ok": True, "name": name, "voices": studio_config.list_voices()})
            if u.path == "/api/voice/delete":
                voice.delete_reference(body.get("name", ""))
                return self._json({"ok": True, "voices": studio_config.list_voices()})
            if u.path == "/api/voice/test":
                if JOB.status()["state"] == "running":
                    raise RuntimeError("wait for the running job to finish")
                mp3 = voice.make_test_clip(studio_config.normalize(body.get("config") or load_state()))
                data = mp3.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
                return
            if u.path == "/api/render/cancel":
                JOB.cancel()
                return self._json(JOB.status())
            if u.path == "/api/presets":
                name = studio_config.save_preset(body.get("name", ""), body.get("config"))
                return self._json({"ok": True, "name": name, "presets": studio_config.list_presets()})
            self._json({"error": "not found"}, 404)
        except RuntimeError as exc:
            self._json({"error": str(exc)}, 409)
        except Exception as exc:
            self._json({"error": str(exc)}, 500)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    cooling.lower_priority()
    cpu_percent()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Flash Studio running at {url}  (Ctrl+C to stop)", flush=True)
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        JOB.cancel()
        for w in WORKERS.values():
            w.close()


if __name__ == "__main__":
    main()
