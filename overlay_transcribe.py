"""overlay_transcribe.py - word timings of a video's speech (run with the voice environment's python: it has Whisper).

    voice_env/Scripts/python overlay_transcribe.py clip.mp4 words.json

Writes [{"word", "start", "end"}] in seconds. The audio is decoded with ffmpeg to 16 kHz mono and fed to Whisper's word timestamps.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent


def main(src, out):
    import torch
    import whisper
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True, check=True).stdout
    audio = np.frombuffer(raw, dtype=np.float32)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    m = whisper.load_model("base.en", device=dev, download_root=str(ROOT / "voice_models" / "whisper"))
    res = m.transcribe(audio, language="en", word_timestamps=True, fp16=(dev == "cuda"), condition_on_previous_text=False)
    words = []
    for seg in res["segments"]:
        for w in seg.get("words", []):
            words.append({"word": w["word"].strip(), "start": round(float(w["start"]), 3), "end": round(float(w["end"]), 3)})
    Path(out).write_text(json.dumps(words, indent=1), encoding="utf-8")
    print(f"{len(words)} words, {words[-1]['end'] if words else 0:.1f}s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
