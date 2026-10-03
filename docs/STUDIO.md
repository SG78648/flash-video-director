# Flash Studio

A local app (runs only on this PC, `127.0.0.1`) to configure the layout and style of the
lifestyle-inflation video, preview it live, and render it on the GPU.

## Start it

Double-click **`Flash Studio.bat`**, or run `python studio.py` (opens your browser at
http://127.0.0.1:8765/). Close the window to stop it.

## The interface

Flash Studio is one workspace with one job per area, built around a few rules: show the result, hide the
machinery, one obvious primary action.

- **Top bar:** the style switch (Adi / Dan), a quiet GPU temperature chip, and the one primary button,
  **Render**. While a job runs the button itself becomes the progress bar (percent and time left) with a
  cancel button beside it; narration generation and the Chatterbox install use the same place.
- **Stage (centre):** one preview of the video, always live: change any setting and the frame updates.
  Pressing play plays your last render (with music) in the same frame; if there is no render yet it plays
  a draft. A small chip says which one you are looking at.
- **Side panel, four tabs:** *Look* (colours, layout, elements, camera - presets and reset on top),
  *Voice*, *Music* (drop a song on it), *Export* (render quality, job details, your videos).
  Groups are collapsible, sliders show their value and a reset arrow appears only when a value differs
  from the default. Tracks and voices take their name from the file - no name prompts.
- **Timeline (bottom):** the whole video in time order; click a scene, click or drag the ruler, drag the
  music. `T` hides it. The timeline thumbnails refresh a moment after you change a setting.
- **Finished videos** open in a full-screen viewer (Esc closes); after a render or an export a
  "Watch" button appears.
- **Keyboard:** `Space` play/pause, `Left` / `Right` step 1 s (Shift = 5 s), `Home` start, `T` timeline,
  `R` render.

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

## Formats: 9:16, 1:1, 16:9

The **Format** switch under the preview chooses the shape of the video: 9:16 (vertical, the original),
1:1 (square) or 16:9 (wide). It is a real re-layout, not a crop or a stretch, and it is part of the saved
settings and presets. The preview, timeline thumbnails and the render all follow it, and a finished video is
named `..._1x1_...` / `..._16x9_...` (9:16 files keep their old names). The timeline plays the newest render
of the *current* format.

- **Adi, 16:9:** the page is split into two columns. The hero icon and the headline fill the left half at full
  size; the card / chart / list is centred in the right half (scaled to 0.9); the one-word "NO." beat is centred
  on the whole frame. The closing frame shows a large building illustration on the right.
- **Adi, 1:1:** one scaled page (0.82) on a wider canvas: the headline on the left with the hero icon beside
  it, the card spanning the width underneath, each frame centred vertically.
- **Dan:** it is a centred composition, so it lays out on a compact virtual page (860 x 860 for 1:1, 1529 x 860
  for 16:9) and is scaled to the output size - the panel and caption come out larger relative to the frame.
- **9:16 is unchanged**, pixel for pixel (checked against the previous version on every frame of the board).
- The camera pans between frames get more motion-blur samples on the wide board so they stay smooth.
- A wide render takes longer than a vertical one (about 7 min instead of 3 on an RTX 3050): its frames are bigger.

Safe areas: vertical video keeps 150 px clear above and below (platform UI); square and wide keep 36 px.
The layout audit (`python generate_adi.py --audit`) checks overlaps and the safe area in the current format.

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
| `music.py` | music library, loudness levelling, waveform peaks, the final mix (sidechain ducking, fades, loop) |
| `voice.py`, `tts_chatterbox.py`, `setup_chatterbox.py` | narration engines: Edge / Chatterbox cloning (own environment), word alignment, installer |
| `generate_adi.py`, `style_dan.py` (+ `generate_lifestyle.py`) | the two styles (Adi has the per-format zone layout) |

## Projects and where files live

Everything you make belongs to a **project**: pick, create, rename or delete one from the project menu in the
top bar (next to the logo). Switching projects switches the settings, narration, music and timeline.

```
projects/<Project name>/
    project.json      every setting of the project (style, look, voice, music, format, render)
    adi/  dan/        the working files of each style: narration + timing, video segments, mixed audio
    music/            copies of the library tracks used in this project
library/              yours, shared by every project
    voices/           cloned voices (reference samples)
    presets/          saved presets
    music/            the music library
    cache/            re-usable generated data (synthesised narration, sound effects)
output/               finished videos only, one flat folder
studio_data/          the app's own bookkeeping (active project, jobs, logs) - ignore it
```

- **Finished videos** are named `<Project>_<style>_<format>_<date>_<time>.mp4` (plus `_music` for the version
  with music), so the newest one is at the top of `output/` sorted by date, whatever project made it.
  *Open output folder* is in the project menu and on the Export tab.
- **Music:** dropping a song puts it in the library (levelled once) and copies it into the project. Other
  projects see it in the library list and can *Add to project* - which makes their own copy, so deleting a
  library song never breaks an old project. The project's copy is what the timeline plays and the export mixes.
- **Voices and presets** are not project-specific: a cloned voice or a preset is available in every project.
- **Nothing is deleted behind your back:** the working files stay in the project (no clearing between renders);
  *Delete project* removes only its folder (settings, narration, segments, music copies) and never the
  finished videos in `output/`.
- Older data was moved into this layout by `migrate_layout.py` (the working leftovers of the very first scripts are in
  `archive/legacy-output/`; the finished videos of the older stories stay in `output/`).

Command line (same pipeline, no app; the format comes from the app's saved setting, or `FLASH_ASPECT=16:9`): `python generate_adi.py`, `python remix.py adi|dan` (re-mix audio
without re-rendering), `python qa_check.py --video adi|dan`.

## Voice (Edge voices or Chatterbox voice cloning)

The **Voice** card (above Render) chooses who narrates:

- **Edge voices** (default): Microsoft neural voices, free, needs internet only the first time a
  setting is used. The original narration already on disk is reused.
- **Chatterbox** (Resemble AI, MIT licence): free, runs on your GPU, clones a voice from a short sample.
  Click *Install Chatterbox* once (about 6.5 GB, all inside this project folder: `voice_env/` is its own
  Python 3.11 environment with CUDA PyTorch, `voice_models/` holds the model weights - nothing is written
  to C:). Then *Upload sample...* (a clean 10-25 s clip of ONE person talking; only use voices you have
  permission to clone), pick it under *Voice to clone*, and press *Test this voice*. With no sample
  Chatterbox uses its built-in voice. Chatterbox adds an inaudible watermark to its audio.
- *Generate narration (both styles)* synthesizes the 9 clips + the hook (about 4.5 minutes on an RTX 3050)
  and refreshes the preview timeline; *Render* also does this automatically when the voice settings changed.
  The result is cached in `library/cache/voice/` keyed by the voice settings, so going back to a
  voice you already generated is instant.

How timing still works: narration is synthesized per sentence with a controlled pause after `. ? !`,
sped up to the chosen speaking speed, and every word's start/end time is found by CTC forced alignment
(torchaudio wav2vec2) of the known script against the audio. So the beat sync, camera moves and
pause-only transitions work exactly as with the Edge voices.

Quality controls built into the Chatterbox path (a cloned voice can add artifacts, e.g. a 1 s "hmm" before
a sentence, or skip / repeat words):
- every sentence is cut from its first spoken word - 0.12 s to its last word + 0.18 s (the word times come
  from the forced alignment), which removes the hum / breath / room tone around the speech;
- Whisper (small English recognizer, ~150 MB, installed with Chatterbox) listens to each sentence and
  compares it with the script; if it does not match (similarity < 0.85) the sentence is regenerated with
  another seed, up to 3 attempts;
- the cache key includes a synthesis revision (`voice.SYNTH_REV`), so improving this pipeline regenerates
  stale narration automatically.

Command-line tools (`generate_adi.py`, `remix.py`, `qa_check.py`) read the app's saved settings
(the active project's `project.json`) when no config is given.

## Background music and the timeline

The **timeline** (docked at the bottom) shows the whole video the way an editor would, on a shared time ruler (zoom with
the slider, click the ruler to seek, the playhead follows the video):

| lane | shows |
|------|-------|
| Video | the segments (hook, clips 1-9, close) with thumbnails; click one to jump there |
| Narration | each clip's voice with its real waveform |
| Moves / SFX | camera pans, spoken beats, and every sound effect (swish, stamp, chime...) |
| Music | your track, with its waveform, fade handles and the loop point |

**Music workflow:** *Drop a song on the Music tab* (or click it) (mp3 / wav / m4a / flac / ogg) -> the track is stored in
`library/music/` as FLAC (and copied into the project) and **levelled to -16 LUFS** (one static gain, true peak kept below -1 dBFS,
dynamics untouched) so the volume slider means the same for every track. Then on the Music lane:

- drag the block to choose **where the music starts** on the video (snaps to clip boundaries, beats and
  the playhead - untick *Snap* for free placement);
- drag its left / right edge to trim (*in point* inside the track and *length*);
- drag the fade handles for **fade in / fade out**;
- *Volume*, *Duck under narration* (the music dips while someone speaks, 0 = off) and *Loop* are in the
  Music tab; the settings are part of the saved state / presets like every other control.

Press play on the timeline to hear the latest finished render with the music laid on top (the preview
applies start, trim, volume and fades; **ducking is applied only on export**). *Export with music* (Music tab) mixes
in a few seconds - the video stream is copied, only audio is re-encoded - and writes `<video>_music.mp4`
next to the original, so you can nudge the music and re-export without re-rendering any frame.
*Render video* also adds the music automatically when a track is selected. The Videos list marks the
`_music` files.

CLI: `python remix.py adi|dan` re-muxes narration + SFX and adds the music from the saved settings.

## Adding a control

Add one `_c(...)` line to the style's list in `studio_config.SCHEMA`, read the value in the style's
`apply_config()`. The app shows it automatically.

## Limits

The narration and the scene content (headline wording, which icon, card contents) are fixed to the
lifestyle-inflation script; the app configures layout, style and effects. Changing the wording would
need new scenes and new narration audio.
