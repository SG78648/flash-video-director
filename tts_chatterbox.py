"""tts_chatterbox.py - synthesize narration with Chatterbox (voice cloning) + word timings.

Runs INSIDE the voice_env Python (CUDA PyTorch + chatterbox-tts); stdlib + torch only,
so it does not import anything from the rest of the project.

  python tts_chatterbox.py --warmup                  download weights, check the GPU path
  python tts_chatterbox.py --job job.json            synthesize narration items

job.json:
  {"items": [{"id": "clip1", "narration": "...", "out": "path/without/extension"}],
   "ref": "reference.wav" | null,         voice to clone (null = Chatterbox's built-in voice)
   "speed": 1.12, "exaggeration": 0.5, "cfg_weight": 0.5, "temperature": 0.8,
   "pause": 0.75,                         seconds of silence after . ? !
   "seed": 7, "tag": "chatterbox:..."}

For each item it writes <out>.mp3 (trimmed like the edge-tts files: last word + 0.30 s) and
<out>.json {"words": [{word,start,end}], "duration", "narration", "voice"} - the same shape the
video pipeline already reads, so beat sync keeps working. Word times come from CTC forced
alignment (torchaudio wav2vec2) of the KNOWN script against the generated audio, so the words
always match the script exactly.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


def emit(event, **kw):
    print("@@" + json.dumps({"event": event, **kw}), flush=True)


def device():
    import torch
    return "cuda" if torch.cuda.is_available() else "cpu"


# ---------------------------------------------------------------- audio helpers
def trim_silence(wav, sr, rel_db=18.0, floor_db=-60.0, lead=0.06, tail=0.14):
    """Cut the quiet lead-in / tail around the speech of one sentence. The threshold is
    relative to that sentence's own speech level (90th percentile of its frame loudness),
    because a cloned voice reproduces the reference clip's room tone at about -35 dB, which an
    absolute threshold would keep as 'speech'."""
    import torch
    x = wav.squeeze(0)
    hop = int(sr * 0.01)
    n = x.numel() // hop
    if n < 3:
        return wav
    db = 20 * torch.log10(x[: n * hop].reshape(n, hop).pow(2).mean(dim=1).sqrt().clamp_min(1e-8))
    live = db[db > floor_db]
    if live.numel() == 0:
        return wav
    ref = torch.quantile(live, 0.90)
    idx = (db >= ref - rel_db).nonzero()
    if idx.numel() == 0:
        return wav
    a = max(0, int(idx[0]) * hop - int(lead * sr))
    b = min(x.numel(), (int(idx[-1]) + 1) * hop + int(tail * sr))
    return wav[:, a:b]


def split_sentences(text):
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


# ---------------------------------------------------------------- forced alignment
_ALIGN = None


def aligner():
    global _ALIGN
    if _ALIGN is None:
        import torchaudio
        bundle = torchaudio.pipelines.WAV2VEC2_ASR_BASE_960H
        model = bundle.get_model().to(device()).eval()
        _ALIGN = (bundle, model, bundle.get_labels())
    return _ALIGN


def align_words(wav, sr, narration):
    """[{word,start,end}] for every whitespace-separated word of `narration`."""
    import torch
    import torchaudio
    bundle, model, labels = aligner()
    dictionary = {c: i for i, c in enumerate(labels)}
    raw_words = narration.split()
    cleaned = []
    for w in raw_words:
        c = "".join(ch for ch in w.upper() if ch in dictionary and ch not in "-|")
        cleaned.append(c)
    idx = [i for i, c in enumerate(cleaned) if c]
    transcript = "|".join(cleaned[i] for i in idx)
    targets = torch.tensor([[dictionary[ch] for ch in transcript]], dtype=torch.int32)
    w16 = torchaudio.functional.resample(wav, sr, bundle.sample_rate)
    with torch.inference_mode():
        emission, _ = model(w16.to(device()))
        emission = torch.log_softmax(emission, dim=-1).cpu()
    blank = 0
    alignment, scores = torchaudio.functional.forced_align(emission, targets, blank=blank)
    spans = torchaudio.functional.merge_tokens(alignment[0], scores[0].exp())
    ratio = w16.size(1) / emission.size(1) / bundle.sample_rate
    sep = dictionary["|"]
    words, cur = [], []
    for sp in spans:
        if sp.token == sep:
            if cur:
                words.append((cur[0].start, cur[-1].end))
                cur = []
        else:
            cur.append(sp)
    if cur:
        words.append((cur[0].start, cur[-1].end))
    if len(words) != len(idx):
        raise RuntimeError(f"alignment found {len(words)} words, expected {len(idx)}")
    out = []
    pos = {i: k for k, i in enumerate(idx)}
    for i, w in enumerate(raw_words):
        shown = w.strip(".,!?;:\"“”()[]")
        if i in pos:
            s, e = words[pos[i]]
            out.append({"word": shown, "start": round(s * ratio, 3), "end": round(e * ratio, 3)})
        else:      # token with nothing alignable (e.g. a bare symbol): park it at the previous word end
            t = out[-1]["end"] if out else 0.0
            out.append({"word": shown, "start": t, "end": t})
    return out


# ---------------------------------------------------------------- synthesis
_MODEL = None


def load_model():
    global _MODEL
    if _MODEL is None:
        from chatterbox.tts import ChatterboxTTS
        _MODEL = ChatterboxTTS.from_pretrained(device=device())
    return _MODEL


_WHISPER = None


def whisper_model():
    """Small English recognizer used as a quality gate (None if it is not installed)."""
    global _WHISPER
    if _WHISPER is None:
        try:
            import whisper
            _WHISPER = whisper.load_model("base.en", device=device(),
                                          download_root=str(Path(__file__).resolve().parent / "voice_models" / "whisper"))
        except Exception:
            _WHISPER = False
    return _WHISPER or None


def _norm_words(text):
    return re.findall(r"[a-z0-9']+", text.lower().replace("’", "'"))


def heard_similarity(piece, sr, sentence):
    """0..1 similarity between what Whisper hears in `piece` and the script sentence."""
    import difflib
    import torchaudio
    m = whisper_model()
    if m is None:
        return 1.0
    a16 = torchaudio.functional.resample(piece, sr, 16000).squeeze(0).numpy().astype("float32")
    heard = m.transcribe(a16, language="en", fp16=(device() == "cuda"), condition_on_previous_text=False)["text"]
    return difflib.SequenceMatcher(None, _norm_words(heard), _norm_words(sentence)).ratio()


def synth_sentence(model, sentence, job, sr):
    """One sentence -> (piece, words). Up to 3 attempts (different seeds) until Whisper hears the
    script. The piece is cut from the first word's start - 0.12 s to the last word's end + 0.18 s,
    which removes the 'hmm' / breath / room-tone the cloned voice puts before and after speech."""
    import torch
    best = None
    for attempt in range(3):
        torch.manual_seed(int(job.get("seed", 7)) + attempt)
        wav = model.generate(sentence, exaggeration=float(job.get("exaggeration", 0.5)),
                             cfg_weight=float(job.get("cfg_weight", 0.5)),
                             temperature=float(job.get("temperature", 0.8))).cpu()
        words = align_words(wav, sr, sentence)
        start = max(0.0, words[0]["start"] - 0.12)
        end = min(wav.shape[1] / sr, words[-1]["end"] + 0.18)
        piece = wav[:, int(start * sr):int(end * sr)]
        shifted = [{"word": w["word"], "start": round(w["start"] - start, 3), "end": round(w["end"] - start, 3)}
                   for w in words]
        sim = heard_similarity(piece, sr, sentence)
        if best is None or sim > best[0]:
            best = (sim, piece, shifted)
        if sim >= 0.85:
            break
        emit("retry", sentence=sentence[:40], similarity=round(sim, 2), attempt=attempt + 1)
    return best[1], best[2]


def synth_text(model, text, job, ref_ready):
    """Synthesize `text` sentence by sentence. Returns (audio [1,N], sr, parts) where parts is
    [(offset_seconds, piece, words_relative_to_piece)] - the exact position of every sentence."""
    import torch
    sr = model.sr
    pieces, parts, cursor = [], [], 0
    sentences = split_sentences(text)
    for k, sentence in enumerate(sentences):
        piece, words = synth_sentence(model, sentence, job, sr)
        parts.append((cursor / sr, piece, words))
        pieces.append(piece)
        cursor += piece.shape[1]
        if k < len(sentences) - 1:
            gap = torch.zeros(1, int(float(job.get("pause", 0.75)) * sr))
            pieces.append(gap)
            cursor += gap.shape[1]
    return torch.cat(pieces, dim=1), sr, parts


def apply_speed(path_in, path_out, speed):
    if abs(speed - 1.0) < 1e-3:
        os.replace(path_in, path_out)
        return
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(path_in), "-filter:a", f"atempo={speed:.4f}",
                    str(path_out)], check=True)
    os.remove(path_in)


def run_job(job):
    import torchaudio
    model = load_model()
    if job.get("ref"):
        model.prepare_conditionals(job["ref"], exaggeration=float(job.get("exaggeration", 0.5)))
    items = job["items"]
    speed = float(job.get("speed", 1.0))
    for n, item in enumerate(items):
        t0 = time.time()
        out = Path(item["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        wav, sr, parts = synth_text(model, item["narration"], job, bool(job.get("ref")))
        words = []
        for offset, _piece, pw in parts:
            for w in pw:
                words.append({"word": w["word"], "start": w["start"] + offset, "end": w["end"] + offset})
        raw, fast = out.with_suffix(".raw.wav"), out.with_suffix(".fast.wav")
        torchaudio.save(str(raw), wav, sr)
        raw_dur = wav.shape[1] / sr
        apply_speed(raw, fast, speed)
        info = torchaudio.info(str(fast))
        scale = (info.num_frames / info.sample_rate) / raw_dur          # exact time-stretch factor
        for w in words:
            w["start"], w["end"] = round(w["start"] * scale, 3), round(w["end"] * scale, 3)
        dur = words[-1]["end"]
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(fast), "-t", f"{dur + 0.30:.3f}",
                        "-c:a", "libmp3lame", "-b:a", "192k", str(out.with_suffix(".mp3"))], check=True)
        os.remove(fast)
        out.with_suffix(".json").write_text(json.dumps(
            {"words": words, "duration": dur, "narration": item["narration"], "voice": job["tag"]}),
            encoding="utf-8")
        emit("voice", done=n + 1, total=len(items), item=item["id"], seconds=round(time.time() - t0, 1),
             audio=round(dur, 2))


def warmup():
    import torch
    emit("warmup", step="gpu", cuda=torch.cuda.is_available(),
         name=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)
    model = load_model()                      # downloads the weights on first use
    emit("warmup", step="model loaded")
    aligner()                                 # downloads the wav2vec2 aligner
    emit("warmup", step="aligner loaded")
    wav, sr, _parts = synth_text(model, "Quick test.", {"seed": 7}, False)
    emit("warmup", step="synth ok", seconds=round(wav.shape[1] / sr, 2))


if __name__ == "__main__":
    if "--warmup" in sys.argv:
        warmup()
    elif "--job" in sys.argv:
        run_job(json.loads(Path(sys.argv[sys.argv.index("--job") + 1]).read_text(encoding="utf-8")))
    else:
        print(__doc__)
        sys.exit(2)
