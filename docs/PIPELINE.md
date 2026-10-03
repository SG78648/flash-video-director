# Video Generation Pipeline

End-to-end process for generating a 9:16 motion-graphics real estate video.

## Architecture

```
generate_video.py   — orchestrator: narration, timing, frame rendering, encoding
sfx_gen.py          — SFX download, decode, track mixing (numpy + ffmpeg)
qa_check.py         — 35-check quality gate (resolution, codec, audio, beats, frames)
remix.py            — re-mix/re-encode audio without re-rendering frames
```

## Pipeline stages

### 1. Narration + word timing (`gen_all_audio`)

- edge-tts synthesizes MP3 per clip using `VOICE` (en-US-JennyNeural) at `RATE` (-5%).
- `boundary="WordBoundary"` yields per-word offset/duration in 100ns units (`offset / 1e7`).
- Trailing silence trimmed: ffmpeg cuts MP3 to `last_word_end + 0.30s`.
- Output: `output/audio/clipN.mp3` + `output/timing/clipN.json` (cached; delete to re-voice).

### 2. Beat alignment (`beat_ranges_abs`)

- Each clip has 3 narrated beats defined in `NARR_BEATS[cid]`.
- Token-matching walks the word list to find each beat's start/end in clip-time.
- `PAD_BEFORE` (default 0.45s, clip1=0.45s, clip6=0.5s) offsets all beats.
- `local_beat(clip, t_abs)` returns `(beat_index, progress_0_to_1)` for any frame.
- All draw functions use `p` (progress) to drive animation in sync with narration.

### 3. Frame rendering (`render_clip`, `create_intro_clip`, `create_outro_clip`)

- Each frame: `Image.new("RGB", (RW, RH), BLACK)` at 2x supersample (2160x3840).
- `D2` proxy scales all draw coordinates/widths by `SS=2` for anti-aliasing.
- Grid background drawn at final coords (not supersampled).
- Clip-specific `draw_clipN(d, t_abs)` renders scene objects.
- Downscale to 1080x1920 via LANCZOS, then `bloom()` applied (additive glow).
- Output: `output/frames/clipN/frame_NNNN.png`.

### 4. Bloom/glow post-processing (`bloom`)

- Gaussian blur radius=30 on downscaled frame.
- Blurred pixels scaled by intensity=0.50.
- Additive blend via `ImageChops.add` — bright elements glow, black background unaffected.

### 5. SFX + audio mixing (`build_mixed_audio`)

- 11 CC0 WAVs in `output/sfx/` (48kHz stereo) sourced from videoeditingsfx.com.
- `sfx_events(clip)` maps beat timestamps to SFX events with per-event gain.
- `make_track()` mixes: narration WAV + SFX events with configurable `sfx_gain`.
- Intro/outro: SFX-only tracks (no narration).
- Output: `output/audio/clipN_mixed.wav`.

### 6. Video encoding + concat (`compile_video`)

- Per-clip: ffmpeg encodes frames + mixed audio → `output/clipN.mp4` (h264, CRF 17, AAC 192k).
- Final: ffmpeg concat demuxer joins intro + 6 clips + outro → timestamped output file.
- Output naming: `output/<title>_<YYYY-MM-DD_HHMMSS>.mp4`.

## Key parameters

| Parameter | Value | Location |
|---|---|---|
| Resolution | 1080x1920 (9:16) | `W, H` |
| Supersample | 2x (2160x3840 render) | `SS` |
| FPS | 24 | `FPS` |
| Voice | en-US-JennyNeural | `VOICE` |
| Rate | -5% | `RATE` |
| PAD_BEFORE | 0.45s (clip1, default), 0.5s (clip6) | `PAD_BEFORE` |
| PAD_AFTER | 0.35s | `PAD_AFTER` |
| Bloom radius | 30px | `bloom()` |
| Bloom intensity | 0.50 | `bloom()` |
| SFX gain (clips) | 0.45 | `build_mixed_audio` |
| SFX gain (intro) | 0.60 | `build_mixed_audio` |
| SFX gain (outro) | 0.50 | `build_mixed_audio` |

## Caching

- `output/audio/clipN.mp3` + `output/timing/clipN.json` — cached per clip; delete to re-voice.
- `output/sfx/*.wav` — cached SFX downloads; delete `output/sfx_src/` to re-download.
- Frame caches are always regenerated (directories wiped on render).

## Render command

```bash
python generate_video.py
```

Output: `output/<title>_<YYYY-MM-DD_HHMMSS>.mp4`

## QA gate

```bash
python qa_check.py        # full check
python qa_check.py --spot # + export spot frames to output/spotcheck/
```

35 checks: resolution, FPS, codec, duration, file size, audio loudness/clipping per clip,
beat validity per clip, frame counts per clip, intro/outro frame counts.

## Improvement loop

See `docs/IMPROVING.md` for lessons learned and iteration retros.
