# Stickman Studio

A local app (runs only on this PC, `127.0.0.1`) to configure the layout and style of the
lifestyle-inflation video, preview it live, and render it on the GPU.

## Start it

Double-click **`Stickman Studio.bat`**, or run `python studio.py` (opens your browser at
http://127.0.0.1:8765/). Close the window to stop it.

## What you can do

- **Pick a style** at the top: **Adi** (cream storyboard board with a travelling camera) or **Dan**
  (the original dark/light dashboard look). Each style keeps its own settings.
- **Configure it** in the right panel (colours, margins, headline size / position, hero illustration
  position and size, which elements are on - grid, thread, progress line, shadows, icons, marker marks,
  notes, stamps - and camera pan speed, motion blur, drift). Every control has a reset arrow.
  Dan: light/dark theme, accent / alert colours, caption bar height, grid, film finish, push-in.
- **Preview live**: the phone view re-renders as you change a control. Choose the hook / a clip / the
  close, scrub the timeline (grey ticks = spoken beats, orange bars = camera moves) or press Play.
- **Presets**: save and load whole configurations.
- **Render** at the bottom: choose cooling, GPU compositing / encoder, quality, then *Render video*.
  Progress, ETA and the finished videos (with a player) show on the page.

## Keeping the machine cool

Cooling presets (render panel):

| preset   | CPU workers | pause per chunk | GPU temp limit |
|----------|-------------|-----------------|----------------|
| quiet    | 2           | 0.10 s          | 68 C           |
| balanced | 3           | -               | 76 C           |
| fast     | 6           | -               | 83 C           |

All render workers and ffmpeg run at below-normal priority. The GPU does the camera compositing (adi)
and the video encoding (NVENC); the CPU only draws the frames. Work pauses while the GPU is above the
preset's temperature limit. Frames are streamed straight into the encoder: **no PNG frame folders are
written**. The header shows live GPU temperature / load and CPU load.

## Files

| file | role |
|------|------|
| `studio.py` | the app server (UI + preview + render control) |
| `studio_ui/index.html` | the app page (controls are built from the schema) |
| `studio_config.py` | settings schema, defaults, presets (single source of truth) |
| `studio_worker.py` | preview worker / render worker processes |
| `streaming.py`, `cooling.py`, `gpu_view.py` | shared render core: streaming encode, cooling, GPU compositor |
| `generate_adi.py`, `style_dan.py` (+ `generate_lifestyle.py`) | the two styles |

Output goes to `output/adi/` and `output/dan/` (separate from the original `output/` files).
Settings are saved in `studio_data/` (`state.json`, `presets/`).

Command line (same pipeline, no app): `python generate_adi.py`, `python remix.py adi|dan` (re-mix audio
without re-rendering), `python qa_check.py --video adi|dan`.

## Adding a control

Add one `_c(...)` line to the style's list in `studio_config.SCHEMA`, read the value in the style's
`apply_config()`. The app shows it automatically.

## Limits

The narration and the scene content (headline wording, which icon, card contents) are fixed to the
lifestyle-inflation script; the app configures layout, style and effects. Changing the wording would
need new scenes and new narration audio.
