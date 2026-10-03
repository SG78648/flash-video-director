"""studio.py - Stickman Studio: a local app to configure the layout and style
(adi / Dan) of the video, preview it live, and render it on the GPU.

    python studio.py            starts the app and opens it in your browser
    python studio.py --no-browser --port 8765

Everything runs on this machine (127.0.0.1 only). Previews and renders run in
separate worker processes (studio_worker.py); renders use the GPU encoder and
the cooling presets from cooling.py.
"""
import argparse
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
import studio_config  # noqa: E402

UI_DIR = ROOT / "studio_ui"
DATA = ROOT / studio_config.DATA_DIR
STATE_FILE = DATA / "state.json"
STYLES = ("adi", "dan")


# ------------------------------------------------------------------ preview workers
class PreviewWorker:
    def __init__(self, style):
        self.style = style
        self.proc = None
        self.lock = threading.Lock()
        self.seq = 0
        self.timeline = None

    def _spawn(self):
        DATA.mkdir(exist_ok=True)
        log = open(DATA / f"preview_{self.style}.log", "w")
        self.proc = subprocess.Popen(
            [sys.executable, "studio_worker.py", "serve", self.style], cwd=ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True, bufsize=1,
            creationflags=cooling.popen_flags())
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError(f"{self.style} preview worker failed to start (see studio_data/preview_{self.style}.log)")

    def ask(self, obj):
        with self.lock:
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

    def get_timeline(self):
        if self.timeline is None:
            r = self.ask({"cmd": "timeline"})
            if not r.get("ok"):
                raise RuntimeError(r.get("error"))
            self.timeline = r["segments"]
        return self.timeline

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

    def start(self, style, cfg):
        with self.lock:
            if self.state == "running":
                raise RuntimeError("a render is already running")
            self.reset()
            jobs = DATA / "jobs"
            jobs.mkdir(parents=True, exist_ok=True)
            cfg_path = jobs / f"{time.strftime('%Y%m%d_%H%M%S')}_{style}.json"
            studio_config.save(cfg, cfg_path)
            self.style, self.state, self.started = style, "running", time.time()
            self.proc = subprocess.Popen(
                [sys.executable, "studio_worker.py", "render", style, str(cfg_path)], cwd=ROOT,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                creationflags=cooling.popen_flags())
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
            elif line:
                self.log.append(line[-300:])
        rc = self.proc.wait()
        with self.lock:
            if self.state == "cancelled":
                return
            if rc == 0 and self.final:
                self.state, self.progress = "done", 1.0
            else:
                self.state = "error"
                self.error = "render failed (exit %s) - see the log" % rc

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
        return {"state": self.state, "style": self.style, "progress": round(self.progress, 4),
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
    if STATE_FILE.exists():
        try:
            return studio_config.normalize(json.loads(STATE_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return studio_config.defaults()


def list_videos():
    out = []
    for style, folder, pattern in (("adi", "output/adi", "lifestyle_inflation_adi_*.mp4"),
                                   ("dan", "output/dan", "lifestyle_inflation_dan_*.mp4"),
                                   ("dan", "output", "lifestyle_inflation_2*.mp4")):
        for p in (ROOT / folder).glob(pattern):
            out.append({"style": style, "name": p.name, "size": p.stat().st_size, "mtime": p.stat().st_mtime,
                        "url": "/videos/" + p.relative_to(ROOT).as_posix(),
                        "legacy": folder == "output"})
    return sorted(out, key=lambda v: -v["mtime"])[:40]


# ------------------------------------------------------------------ HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "StickmanStudio/1.0"

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
            if u.path == "/api/schema":
                return self._json({"schema": studio_config.SCHEMA, "defaults": studio_config.defaults(),
                                   "presets": studio_config.list_presets(),
                                   "cooling": {k: v for k, v in cooling.PRESETS.items()}})
            if u.path == "/api/state":
                return self._json(load_state())
            if u.path == "/api/timeline":
                style = q.get("style", ["adi"])[0]
                return self._json({"segments": WORKERS[style].get_timeline()})
            if u.path == "/api/system":
                return self._json(system_stats())
            if u.path == "/api/render":
                return self._json(JOB.status())
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
                DATA.mkdir(exist_ok=True)
                studio_config.save(body, STATE_FILE)
                return self._json({"ok": True})
            if u.path == "/api/preview":
                style = body.get("style", "adi")
                r = WORKERS[style].ask({"cmd": "preview", "config": body.get("config"),
                                        "segment": body.get("segment"), "t": body.get("t", 0),
                                        "width": body.get("width", 540)})
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
                JOB.start(body.get("style", "adi"), body.get("config"))
                return self._json(JOB.status())
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
    print(f"Stickman Studio running at {url}  (Ctrl+C to stop)", flush=True)
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
