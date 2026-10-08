"""qa_check.py - post-build quality gate for the flash video.

    python qa_check.py            # run all checks, print scorecard
    python qa_check.py --spot     # also export one frame per clip for eyeballing
    python qa_check.py --json     # skip render-related checks (report only audio/video)

Checks:
  1. final mp4 exists, 1080x1920, 24fps, h264+aac, duration sane, size sane
  2. every *mixed.wav has audible narration (mean) without clipping (peak)
  3. every clip beat range: 3 beats, ascending, finite, inside the clip
  4. rendered frame counts == expected (speech + pads) * FPS
  5. (optional) frame-count/mixed-file consistency

Exit code is 1 on any FAIL, 0 otherwise. Writes output/qa_report.json.
"""
import json
import subprocess
import sys
from pathlib import Path

import os

if "FLASH_ASPECT" not in os.environ and ("adi" in sys.argv or "dan" in sys.argv or "flash" in sys.argv):
    import studio_config
    studio_config.ensure_aspect_env()     # gate the format the app is set to

import generate_video as g

OUT = Path("output")
REPORT = OUT / "qa_report.json"
VID = None

# which story + final video to gate. Default: whichever project's mp4 is newest.
TITLES = {
    "income": "income_vs_wealth",
    "assets": "flash_real_estate",
    "harder_to_ignore": "harder_to_ignore",
    "lifestyle": "lifestyle_inflation",
    "adi": "lifestyle_inflation_adi",
    "dan": "lifestyle_inflation_dan",
    "flash": "flash",
}
MODS = {"assets": "generate_assets", "harder_to_ignore": "generate_hardertoignore",
        "lifestyle": "generate_lifestyle", "adi": "generate_adi", "dan": "style_dan", "flash": "style_flash"}
VID = None
LAYOUT = None

if "--video" in sys.argv:
    key = sys.argv[sys.argv.index("--video") + 1]
    title = TITLES.get(key) or key
    # point engine globals at that story so beats/frame-counts match
    if key in MODS:
        conf = __import__(MODS[key])
        conf.apply_to(g)
        LAYOUT = conf
        OUT = g.OUTPUT_DIR            # a story may render into its own folder (adi -> output/adi)
        REPORT = OUT / "qa_report.json"
    _cands = list(OUT.glob(f"{title}_*.mp4"))
    if key in ("adi", "dan", "flash"):          # gate the newest render of the active project in the selected format (they all live in output/)
        import projects
        _cands = [v["path"] for v in projects.list_finals()
                  if v["project"] == projects.active() and v["style"] == key and v["aspect"] == g.ASPECT and not v["music"]]
    if _cands:
        VID = max(_cands, key=lambda p: p.stat().st_mtime)
else:
    key = None
    _cands = []
    for _t in ("income_vs_wealth", "flash_real_estate", "harder_to_ignore"):
        _cands += list(OUT.glob(f"{_t}_*.mp4"))
    if _cands:
        VID = max(_cands, key=lambda p: p.stat().st_mtime)
        for _prefix, _mod in (("flash_real_estate", "generate_assets"),
                              ("harder_to_ignore", "generate_hardertoignore")):
            if VID.name.startswith(_prefix):
                _conf = __import__(_mod)
                _conf.apply_to(g)
                LAYOUT = _conf
                break

W, H, FPS = g.W, g.H, 24

def run(args):
    return subprocess.run(args, capture_output=True, text=True)

def ffprobe(*args):
    r = run(["ffprobe", "-v", "error", *args])
    return r.stdout.strip()

def seg_frame_count(name):
    """Frames of a segment: PNG files if the story writes them, else the frame
    count of the video-only segment encoded straight from the render stream."""
    n = len(list((g.FRAMES_DIR / name).glob("frame_*.png")))
    vd = getattr(g, "VIDEO_DIR", None)
    if n == 0 and vd is not None and (vd / f"{name}.mp4").exists():
        out = ffprobe("-select_streams", "v:0", "-show_entries", "stream=nb_frames",
                      "-of", "csv=p=0", str(vd / f"{name}.mp4"))
        try:
            n = int(out.split(",")[0])
        except ValueError:
            n = 0
    return n


def loudness(wav_path):
    r = run(["ffmpeg", "-i", str(wav_path), "-af", "volumedetect", "-f", "null", "NUL" if sys.platform == "win32" else "/dev/null"])
    mean = peak = None
    for line in r.stderr.splitlines():
        toks = line.split()
        for i, t in enumerate(toks):
            if t.startswith("mean_volume:"):
                mean = float(toks[i + 1].rstrip("dB"))
            elif t.startswith("max_volume:"):
                peak = float(toks[i + 1].rstrip("dB"))
    return mean, peak


def main():
    checks = []
    def chk(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    # 1. final file
    if VID and VID.exists() and VID.stat().st_size > 0:
        dur = float(ffprobe("-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(VID)))
        ve = ffprobe("-select_streams", "v:0", "-show_entries", "stream=width,height,avg_frame_rate,codec_name",
                     "-of", "json", str(VID))
        ae = ffprobe("-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "json", str(VID))
        vj, aj = json.loads(ve), json.loads(ae)
        v = vj["streams"][0]
        w, h, vr = v.get("width"), v.get("height"), v.get("avg_frame_rate")
        fps_ok = False
        try:
            num, den = vr.split("/")
            fps_ok = abs(float(num) / float(den) - FPS) < 0.5
        except (ValueError, ZeroDivisionError, AttributeError):
            fps_ok = False
        chk(f"final is {W}x{H}", w == W and h == H, f"{w}x{h}")
        chk("final fps == 24", fps_ok, vr)
        chk("final h264+aac", v.get("codec_name") == "h264" and aj["streams"][0]["codec_name"] == "aac",
            f"{v.get('codec_name')}+{aj['streams'][0]['codec_name']}")
        chk("duration sane", 35 <= dur <= getattr(g, "QA_MAX_DUR", 75), f"{dur:.2f}s")
        chk("size < 60MB", VID.stat().st_size < 60 * 1024 * 1024, f"{VID.stat().st_size/1048576:.1f}MB")
    else:
        chk("final exists", False, f"missing {VID.name}")

    # 2. audio loudness
    for m in sorted(OUT.glob("audio/*_mixed.wav")):
        mean, peak = loudness(m)
        chk(f"audible {m.stem}", mean is not None and -34 <= mean <= -7, f"mean {mean} dB")
        chk(f"not clipped {m.stem}", peak is not None and -13 <= peak <= -0.3, f"peak {peak} dB")

    # 3. beats
    for c in g.CLIPS:
        beats = g.beat_ranges_abs(c)
        ov = any(beats[i][1] > beats[i + 1][0] for i in range(len(beats) - 1))
        inside = all(0 <= s <= e <= g.clip_beats(c)[-1][1] + 0.6 for s, e in beats)
        chk(f"beats valid clip{c['id']}", len(beats) == 3 and not ov and inside,
            " ".join(f"{a:.2f}-{b:.2f}" for a, b in beats))

    # 4. frames - mirror render_clip: int((mp3_dur + pad_before + pad_after) * FPS)
    for c in g.CLIPS:
        cid = c["id"]
        n = seg_frame_count(f"clip{cid}")
        expected = c.get("total_frames")
        if expected is None:
            adur = float(ffprobe("-show_entries", "format=duration",
                                 "-of", "default=noprint_wrappers=1:nokey=1",
                                 str(g.AUDIO_DIR / f"clip{cid}.mp3")))
            expected = max(1, int((adur + g.PAD_BEFORE.get(cid, 0.45) + g.PAD_AFTER) * FPS))
        chk(f"frames clip{cid}", n == expected, f"{n} vs {expected}")
    for name in ("intro", "outro"):
        n = seg_frame_count(name)
        if name == "intro" and getattr(g, "INTRO_HOOK_ID", None):
            hdur = float(ffprobe("-show_entries", "format=duration",
                                 "-of", "default=noprint_wrappers=1:nokey=1",
                                 str(g.AUDIO_DIR / f"clip{g.INTRO_HOOK_ID}.mp3")))
            expected = max(1, int((hdur + g.INTRO_PAD_BEFORE + g.INTRO_PAD_AFTER) * FPS))
            chk(f"frames {name}", n == expected, f"{n} vs {expected}")
        else:
            chk(f"frames {name}", n == 2 * FPS, f"{n}")

    # 5. layout collisions (stories that carry layout_problems)
    if LAYOUT is not None:
        n_prob = len(LAYOUT.layout_problems())
        chk("layout no collisions", n_prob == 0, f"{n_prob} unresolved")

    # 6. spot frames
    if "--spot" in sys.argv:
        spot = OUT / "spotcheck"
        spot.mkdir(exist_ok=True)
        for c in g.CLIPS:
            frames = sorted((g.FRAMES_DIR / f"clip{c['id']}").glob("frame_*.png"))
            for frac in (0.15, 0.5, 0.9):
                if frames:
                    picks = frames[max(0, int(len(frames) * frac) - 1)]
                    import shutil
                    shutil.copy(picks, spot / f"clip{c['id']}_{frac}.png")
                else:
                    vid = getattr(g, "VIDEO_DIR", OUT) / f"clip{c['id']}.mp4"
                    n = seg_frame_count(f"clip{c['id']}")
                    run(["ffmpeg", "-y", "-v", "error", "-i", str(vid), "-vf",
                         f"select=eq(n\\,{max(0, int(n * frac) - 1)})", "-frames:v", "1",
                         str(spot / f"clip{c['id']}_{frac}.png")])
        print("  spot frames written to output/spotcheck/")

    # scorecard
    print("=" * 44)
    print("QA SCORECARD")
    print("=" * 44)
    n_pass = 0
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {detail}")
        n_pass += ok
    total = len(checks) or 1
    score = round(10 * n_pass / total, 1)
    print("-" * 44)
    print(f"  {n_pass}/{total} passed -> score {score}/10")
    REPORT.write_text(json.dumps({
        "score": score, "passed": n_pass, "total": total,
        "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks],
    }, indent=2))
    return 0 if n_pass == total else 1


if __name__ == "__main__":
    sys.exit(main())
