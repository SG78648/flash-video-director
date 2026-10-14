"""start_studio.py - run Flash Studio as its own background process, independent of whatever started it.

    python start_studio.py            start it if it is not running, wait until it answers, print the address
    python start_studio.py --stop     stop it (a running job is cancelled, so use this on purpose)
    python start_studio.py --status   running or not, and what it is doing

Why this exists: a studio started from a terminal tab, an editor or an assistant session is a child of that session.
When the session ends, Ctrl+C or a tree kill reaches the server, and its shutdown cancels the narration or render that
was running. Started here (through WMI) the server is not a child of the launcher and is in no job object, so nothing
that ends the session can reach it. It also ignores Ctrl+C / Ctrl+Break (--service) and keeps the PC awake while a job runs.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "studio_data"
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000


def ask(port, path, post=False, timeout=3):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), data=b"{}" if post else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def running(port):
    try:
        return ask(port, "/api/render")
    except Exception:
        return None


def _spawn_outside_session(cmd, cwd):
    """Windows: create the process through WMI. Its parent is the WMI service, not the caller, and it is in no job object, so closing the
    terminal, IDE or assistant session that ran this script (which may terminate every process of its job) cannot reach it.
    It still runs in the user's own session, so the GPU is available. Returns the pid."""
    line = " ".join('"%s"' % c if " " in c else c for c in cmd)
    ps = ("$si = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[uint16]0}; "
          "$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine=%s; CurrentDirectory=%s; ProcessStartupInformation=$si}; "
          "if ($r.ReturnValue -ne 0) { exit $r.ReturnValue }; $r.ProcessId" % ("'" + line.replace("'", "''") + "'", "'" + str(cwd).replace("'", "''") + "'"))
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True, text=True, timeout=60)
    if r.returncode != 0 or not r.stdout.strip().isdigit():
        raise OSError("WMI create failed (%s) %s" % (r.returncode, r.stderr.strip()[:200]))
    return int(r.stdout.strip())


def start(port):
    st = running(port)
    if st is not None:
        print("Flash Studio is already running at http://127.0.0.1:%d/ (job: %s)" % (port, st.get("state")))
        return 0
    DATA.mkdir(exist_ok=True)
    with open(DATA / "server.log", "a", encoding="utf-8") as out:
        out.write("--- start_studio %s ---" % time.strftime("%Y-%m-%d %H:%M:%S") + chr(10))
    cmd = [sys.executable, "studio.py", "--no-browser", "--service", "--port", str(port)]     # the server writes its own log files in --service mode
    proc = None
    try:
        pid = _spawn_outside_session(cmd, ROOT) if sys.platform == "win32" else subprocess.Popen(cmd, cwd=ROOT, start_new_session=True, stdin=subprocess.DEVNULL).pid
    except (OSError, subprocess.SubprocessError) as exc:
        print("Could not start it outside this session (%s), starting it normally instead." % exc)
        proc = subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.DEVNULL, creationflags=(CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP) if sys.platform == "win32" else 0)
        pid = proc.pid
    (DATA / "server.pid").write_text(str(pid), encoding="utf-8")
    for _ in range(80):
        if running(port) is not None:
            print("Flash Studio started at http://127.0.0.1:%d/ (pid %d)" % (port, pid))
            return 0
        if proc is not None and proc.poll() is not None:
            break
        time.sleep(0.25)
    print("Flash Studio did not start, see studio_data/server.err.log")
    return 1


def stop(port):
    st = running(port)
    if st is None:
        print("Flash Studio is not running")
        return 0
    if st.get("state") == "running":
        print("A %s job is running and will be cancelled." % st.get("kind"))
    try:
        ask(port, "/api/shutdown", post=True)
    except Exception:
        pass
    for _ in range(40):
        if running(port) is None:
            print("Flash Studio stopped")
            return 0
        time.sleep(0.25)
    pid = (DATA / "server.pid").read_text().strip() if (DATA / "server.pid").exists() else ""
    if pid and sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True)
    print("Flash Studio stopped (forced)")
    return 0


def status(port):
    st = running(port)
    if st is None:
        print("Flash Studio is not running")
        return 1
    print("Flash Studio is running at http://127.0.0.1:%d/ - job: %s %s" % (port, st.get("state"), st.get("kind") or ""))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--stop", action="store_true")
    g.add_argument("--status", action="store_true")
    a = ap.parse_args()
    sys.exit(stop(a.port) if a.stop else status(a.port) if a.status else start(a.port))
