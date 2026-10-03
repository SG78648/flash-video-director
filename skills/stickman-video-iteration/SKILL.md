---
name: stickman-video-iteration
description: Use when editing, re-rendering, or improving the locally generated stickman real-estate video build (generate_video.py pipeline). Covers the build-edit-QA-remix loop, cache invalidation, and the improvement gate. Do not use for the upstream director's-pitch skill or for unrelated projects.
---

# Stickman Video Iteration

This build is a Pillow + edge-tts + ffmpeg pipeline that renders a 9:16 real-estate
story (6 clips + intro/outro), word-synced beats, and CC0 motion-graphics SFX.

## Setup gate

Require these before editing:

- the goal (what metric changes: pacing, loudness, style, story, duration)
- the previous `output/qa_report.json` score if it exists (read the FAILs first)

If either is missing, ask in one concise message and stop.

## Workflow

1. Read `docs/IMPROVING.md` lessons table before touching code.
2. Make the edit in `generate_video.py` / `sfx_gen.py`.
3. If `RATE` or `VOICE` changed, delete `output/audio/clipN.mp3` +
   `output/timing/clipN.json` first (cache is reused when both exist).
4. Render: `python generate_video.py`. If only audio/SFX changed,
   `python remix.py` (re-mixes + re-encodes without re-rendering frames).
5. Gate: `python qa_check.py --spot` — must reach 10/10 with no FAIL before
   declaring done. Non-zero exit = unfinished.
6. Append a retro row to `docs/IMPROVING.md` (what changed, what QA caught, next).

## Contract rules

- Never change narration pacing knobs without clearing the audio+timing cache.
- Never rely on a compile check alone: `ImageDraw`-surface mistakes only crash at
  runtime. After any primitive/helper change, render one frame via
  `render_frame(cid, t)` and spot-check `output/spotcheck/`.
- Match the QA expectation formula exactly: `int((mp3_dur + pad_before + pad_after) * FPS)`.
- Keep the video beat-synced: timing regenerates with the voice, scenes must key
  animation off `local_beat` (idx, p), never off wall-clock `t_abs` alone.
- SFX stay softer than narration: mix peak target ~-2dB, mean around -20dB.

## Final check

Apply the checklist in `docs/IMPROVING.md`'s gate rules; repair any FAIL before
responding to the user.