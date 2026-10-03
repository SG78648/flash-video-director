"""voice.py - narration voice engines for the studio: edge-tts (default) or Chatterbox cloning.

ensure_audio() makes sure a style's audio/ and timing/ folders hold narration that matches the
current voice settings. Every timing file carries a "voice" tag; a file is reused only when its
tag AND its narration text match, so changing any voice setting regenerates exactly what is stale.

  edge       -> tag "en-US-GuyNeural" (or "...@+20%" when the speed is not the default). The
                original lifestyle narration already on disk is reused, so the default costs nothing.
  chatterbox -> tag "chatterbox:<hash of reference clip + settings>". Synthesized ONCE into
                library/cache/voice/<tag>/ (GPU, ~minutes) and copied into each style folder.

Chatterbox runs in its own environment (voice_env, see setup_chatterbox.py) through
tts_chatterbox.py; this module only needs the standard library.
"""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import cooling
import projects
import studio_config

ROOT = Path(__file__).resolve().parent
VOICE_ENV_PY = ROOT / "voice_env" / "Scripts" / "python.exe"
READY = ROOT / "voice_models" / "ready.json"
CACHE = projects.LIB_CACHE / "voice"                  # synthesised narration, shared by every project
ORIGINAL = projects.ORIGINAL_NARRATION               # the original lifestyle narration (edge GuyNeural, +12%)
SYNTH_REV = 3                       # bump when the synthesis / trimming / alignment changes -> cached narration regenerates
TEST_TEXT = "You're not broke because you don't make enough money."


def settings(cfg=None):
    return (cfg or studio_config.load())["voice"]


def edge_rate(speed):
    return f"{round((float(speed) - 1) * 100):+d}%"


def chatterbox_installed():
    return VOICE_ENV_PY.exists() and READY.exists()


def _ref_hash(name):
    p = studio_config.voice_path(name)
    return hashlib.sha1(p.read_bytes()).hexdigest()[:10] if p else "builtin"


def tag_for(v):
    if v["engine"] == "chatterbox":
        key = json.dumps([SYNTH_REV, _ref_hash(v["reference"]), v["exaggeration"], v["cfg_weight"], v["speed"],
                          v["pause"], v["seed"]], sort_keys=True)
        return "chatterbox:" + hashlib.sha1(key.encode()).hexdigest()[:12]
    rate = edge_rate(v["speed"])
    return v["edge_voice"] if rate == "+12%" else f"{v['edge_voice']}@{rate}"


def desired_tag(cfg=None):
    return tag_for(settings(cfg))


def _read(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def _fresh(audio_dir, timing_dir, i, tag, text):
    t = _read(Path(timing_dir) / f"clip{i}.json")
    return bool(t) and t.get("voice") == tag and t.get("narration") == text and (Path(audio_dir) / f"clip{i}.mp3").exists()


def on_disk_tag(timing_dir):
    t = _read(Path(timing_dir) / "clip1.json")
    return t.get("voice") if t else None


def _copy_pair(src_dir_audio, src_dir_timing, dst_audio, dst_timing, i):
    Path(dst_audio).mkdir(parents=True, exist_ok=True)
    Path(dst_timing).mkdir(parents=True, exist_ok=True)
    shutil.copy(Path(src_dir_audio) / f"clip{i}.mp3", Path(dst_audio) / f"clip{i}.mp3")
    shutil.copy(Path(src_dir_timing) / f"clip{i}.json", Path(dst_timing) / f"clip{i}.json")


# ---------------------------------------------------------------- chatterbox
def _chatterbox_env():
    sys.path.insert(0, str(ROOT))
    import setup_chatterbox
    return setup_chatterbox.env_vars()


def run_chatterbox(job, log=print):
    """Run tts_chatterbox.py inside voice_env for `job`; progress lines are passed through."""
    if not chatterbox_installed():
        raise RuntimeError("Chatterbox is not installed - use 'Install Chatterbox' in the Voice panel")
    CACHE.mkdir(parents=True, exist_ok=True)
    job_file = CACHE / "job.json"
    job_file.write_text(json.dumps(job), encoding="utf-8")
    proc = subprocess.Popen([str(VOICE_ENV_PY), str(ROOT / "tts_chatterbox.py"), "--job", str(job_file)],
                            cwd=ROOT, env=_chatterbox_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=cooling.popen_flags())
    tail = []
    for line in proc.stdout:
        line = line.rstrip()
        if line.startswith("@@"):
            print(line, flush=True)
        elif line:
            tail.append(line)
            tail = tail[-12:]
    if proc.wait() != 0:
        raise RuntimeError("Chatterbox failed:\n" + "\n".join(tail[-8:]))


def _job_base(v, tag):
    ref = studio_config.voice_path(v["reference"])
    return {"ref": str(ref) if ref else None, "speed": float(v["speed"]), "exaggeration": float(v["exaggeration"]),
            "cfg_weight": float(v["cfg_weight"]), "pause": float(v["pause"]), "seed": int(v["seed"]),
            "temperature": 0.8, "tag": tag}


def synth_chatterbox_cache(v, tag, items, log=print):
    """Make sure the cache folder for `tag` holds every (id, text) in `items`; returns that folder."""
    folder = CACHE / tag.replace(":", "_")
    todo = [(i, t) for i, t in items if not _fresh(folder, folder, i, tag, t)]
    if todo:
        folder.mkdir(parents=True, exist_ok=True)
        job = _job_base(v, tag)
        job["items"] = [{"id": i, "narration": t, "out": str(folder / f"clip{i}")} for i, t in todo]
        log(f"Chatterbox: synthesizing {len(todo)} narration clip(s) on the GPU...")
        run_chatterbox(job, log)
    return folder


def make_test_clip(cfg=None):
    """Synthesize one sentence with the current voice settings; returns the mp3 path."""
    cfg = cfg or studio_config.load()
    v = settings(cfg)
    tag = tag_for(v)
    if v["engine"] != "chatterbox":
        raise RuntimeError("the test clip is for the Chatterbox engine")
    out = CACHE / ("test_" + tag.replace(":", "_"))
    if not out.with_suffix(".mp3").exists():
        job = _job_base(v, tag)
        job["items"] = [{"id": "test", "narration": TEST_TEXT, "out": str(out)}]
        run_chatterbox(job)
    return out.with_suffix(".mp3")


# ---------------------------------------------------------------- ensure narration for a style
async def ensure_audio(gm, clips, hook_id, hook_text, cfg=None, log=print):
    """Bring gm.AUDIO_DIR / gm.TIMING_DIR in line with the current voice settings."""
    cfg = cfg or studio_config.load()
    v = settings(cfg)
    tag = tag_for(v)
    items = [(str(c["id"]), c["narration"]) for c in clips] + [(hook_id, hook_text)]
    stale = [(i, t) for i, t in items if not _fresh(gm.AUDIO_DIR, gm.TIMING_DIR, i, tag, t)]
    if not stale:
        return tag
    if v["engine"] == "chatterbox":
        folder = synth_chatterbox_cache(v, tag, items, log)
        for i, _t in stale:
            _copy_pair(folder, folder, gm.AUDIO_DIR, gm.TIMING_DIR, i)
        return tag
    for i, text in stale:
        if _fresh(ORIGINAL / "audio", ORIGINAL / "timing", i, tag, text):       # original narration, no network
            _copy_pair(ORIGINAL / "audio", ORIGINAL / "timing", gm.AUDIO_DIR, gm.TIMING_DIR, i)
            continue
        log(f"edge-tts: synthesizing clip {i} ({tag})...")
        gm.VOICE, gm.RATE = v["edge_voice"], edge_rate(v["speed"])
        await gm.gen_audio_and_timing({"id": i, "narration": text})
        tf = Path(gm.TIMING_DIR) / f"clip{i}.json"
        data = _read(tf)
        data["voice"] = tag
        tf.write_text(json.dumps(data), encoding="utf-8")
    return tag


def save_reference(name, raw_bytes, ext=".wav"):
    """Store an uploaded sample as 24 kHz mono wav (max 25 s) under library/voices/."""
    safe = "".join(ch for ch in name if ch.isalnum() or ch in " -_").strip()
    if not safe:
        raise ValueError("give the voice a name")
    studio_config.VOICE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = studio_config.VOICE_DIR / f"_upload{ext if ext.startswith('.') else '.' + ext}"
    tmp.write_bytes(raw_bytes)
    out = studio_config.VOICE_DIR / f"{safe}.wav"
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp), "-t", "25", "-ac", "1", "-ar", "24000",
                        str(out)], capture_output=True, text=True)
    tmp.unlink(missing_ok=True)
    if r.returncode != 0:
        raise ValueError("could not read that audio file: " + r.stderr[-200:])
    return safe


def delete_reference(name):
    p = studio_config.voice_path(name)
    if p:
        p.unlink()
