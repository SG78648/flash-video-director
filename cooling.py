"""cooling.py - keep the machine cool while rendering.

  * render workers (and ffmpeg) run at BELOW_NORMAL priority so the PC stays
    responsive and the CPU is never the first thing starved;
  * presets cap how many CPU workers draw frames and add a small idle pause
    between chunks (a duty cycle) so the CPU does not sit at 100%;
  * a GPU temperature guard pauses work while the card is above a limit.

The GPU does the heavy lifting (camera compositing + NVENC encode); the CPU only
draws the board tiles, so a few workers are plenty.
"""
import subprocess
import sys
import time

PRESETS = {
    # name: workers drawing frames, idle pause per 4-frame chunk (s), GPU temp limit (C)
    "quiet":    {"workers": 2, "pause": 0.10, "gpu_limit": 68},
    "balanced": {"workers": 3, "pause": 0.00, "gpu_limit": 76},
    "fast":     {"workers": 6, "pause": 0.00, "gpu_limit": 83},
}
DEFAULT_PRESET = "balanced"

BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
_last_check = 0.0
_last_temp = None


def preset(name):
    return dict(PRESETS.get(name, PRESETS[DEFAULT_PRESET]))


def lower_priority():
    """Run the current process at below-normal priority (Windows)."""
    if sys.platform == "win32":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetPriorityClass(k.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)
        except Exception:
            pass


def popen_flags():
    """creationflags for subprocess.Popen so child processes (ffmpeg) are low priority too."""
    return BELOW_NORMAL_PRIORITY_CLASS if sys.platform == "win32" else 0


def gpu_stats():
    """(temp C, GPU util %, encoder util %, name) from nvidia-smi, or None."""
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu,utilization.encoder,name",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return None
        t, u, e, name = [x.strip() for x in r.stdout.strip().splitlines()[0].split(",", 3)]
        return int(t), int(u), int(e), name
    except Exception:
        return None


def guard(limit, log=None, every=3.0):
    """Block while the GPU is hotter than `limit` (checked at most every `every` s)."""
    global _last_check, _last_temp
    now = time.time()
    if now - _last_check < every:
        return
    _last_check = now
    st = gpu_stats()
    if st is None:
        return
    _last_temp = st[0]
    while st is not None and st[0] > limit:
        if log:
            log(f"GPU at {st[0]} C (limit {limit}) - cooling down...")
        time.sleep(4)
        st = gpu_stats()
        if st is not None:
            _last_temp = st[0]
    _last_check = time.time()
