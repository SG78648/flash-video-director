"""setup_chatterbox.py - install the Chatterbox voice-cloning engine for Flash Studio.

    python setup_chatterbox.py            install (idempotent)
    python setup_chatterbox.py --status   print whether it is ready

Everything lives inside this project folder (the C: drive may be full):
    voice_env/     Python 3.11 virtual environment (CUDA PyTorch 2.6.0 + chatterbox-tts, MIT licence)
    voice_models/  model weights (HuggingFace + torch caches) and pip/temp files
About 6-7 GB in total. Chatterbox needs its own pinned PyTorch, so it never touches
the main Python install.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_DIR = ROOT / "voice_env"
MODELS = ROOT / "voice_models"
PY = ENV_DIR / "Scripts" / "python.exe"
TORCH_INDEX = "https://download.pytorch.org/whl/cu124"


def emit(step, msg=""):
    print("@@" + json.dumps({"event": "setup", "step": step, "msg": msg}), flush=True)


def env_vars():
    e = dict(os.environ)
    (MODELS / "tmp").mkdir(parents=True, exist_ok=True)
    e.update({"HF_HOME": str(MODELS / "hf"), "TORCH_HOME": str(MODELS / "torch"),
              "TMP": str(MODELS / "tmp"), "TEMP": str(MODELS / "tmp"),
              "PIP_CACHE_DIR": str(MODELS / "pip"), "PYTHONIOENCODING": "utf-8",
              "HF_HUB_DISABLE_SYMLINKS_WARNING": "1"})
    return e


def run(cmd, **kw):
    print("$ " + " ".join(str(c) for c in cmd), flush=True)
    r = subprocess.run([str(c) for c in cmd], env=env_vars(), **kw)
    if r.returncode != 0:
        raise SystemExit(f"command failed ({r.returncode}): {' '.join(str(c) for c in cmd[:6])}")


def status():
    """(installed?, detail) - installed means the venv can import chatterbox and see CUDA."""
    if not PY.exists():
        return False, "voice_env not created"
    r = subprocess.run([str(PY), "-c",
                        "import torch, chatterbox; print(torch.cuda.is_available())"],
                       capture_output=True, text=True, env=env_vars())
    if r.returncode != 0:
        return False, "chatterbox not importable"
    cuda = r.stdout.strip().endswith("True")
    return True, "ready (CUDA GPU)" if cuda else "ready (CPU only - slow)"


def find_python311():
    r = subprocess.run(["py", "-3.11", "-c", "import sys;print(sys.executable)"], capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    return None


def main():
    if "--status" in sys.argv:
        ok, detail = status()
        print(json.dumps({"installed": ok, "detail": detail}))
        return 0 if ok else 1

    emit("start", "Installing Chatterbox into voice_env (about 6-7 GB, all inside the project folder)")
    if not PY.exists():
        emit("venv", "creating the Python 3.11 environment")
        py311 = find_python311()
        if py311:
            run([py311, "-m", "venv", ENV_DIR])
        else:
            uv = subprocess.run(["where", "uv"], capture_output=True, text=True).stdout.split("\n")[0].strip()
            if not uv:
                raise SystemExit("Python 3.11 is required (install it from python.org) - none found")
            run([uv, "venv", "--python", "3.11", ENV_DIR])
    run([PY, "-m", "pip", "install", "--upgrade", "pip", "--no-cache-dir"])
    emit("torch", "installing PyTorch 2.6.0 with CUDA 12.4 (about 2.5 GB)")
    run([PY, "-m", "pip", "install", "--no-cache-dir", "torch==2.6.0", "torchaudio==2.6.0",
         "--index-url", TORCH_INDEX])
    emit("chatterbox", "installing chatterbox-tts and its libraries")
    run([PY, "-m", "pip", "install", "--no-cache-dir", "chatterbox-tts", "openai-whisper"])
    emit("weights", "downloading the model weights (about 3 GB) and the aligner (about 0.4 GB)")
    run([PY, str(ROOT / "tts_chatterbox.py"), "--warmup"])
    ok, detail = status()
    if ok:
        (MODELS / "ready.json").write_text(json.dumps({"detail": detail}), encoding="utf-8")
    emit("done" if ok else "failed", detail)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
