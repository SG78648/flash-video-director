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
  *Voice*, *Music* (drop a song on it), *Text*, *Effects*, *Export* (render quality, job details, your videos).
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
| `edit.py`, `studio_ui/editor-*.js` | the post-production editor: export engine (ffmpeg) and the timeline (model, UI, playback, text) |
| `sfxlib.py` | the sound-effect library (library + project copies + the built-in effects) |
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

## Making a video from your own script

Project menu → **New project…** opens **Pre-production**, where every choice is yours before anything is generated:
name, script, a saved look to start from, style (Adi / Dan), format, narration (an Edge voice, or a saved cloned voice),
speaking speed, and whether to generate the narration right away (off by default). Nothing is chosen for you; music is
added afterwards in the Music tab. **Script…** in the same menu changes the words later.

How the script is read (`script_story.py`, `python script_story.py file.txt` prints the result):

- sentences are split into short *beats* of a few words, three per clip, and the narration is one clip per group;
- a line in quotation marks becomes a **quote card** (struck out when it is a negative thought such as "I can't ...",
  ticked otherwise), a line ending in a colon followed by short lines becomes a **numbered list**;
- words the app can draw (money, building, clock, ...) get an icon chip; the rest is a large headline with the closing
  words in the accent colour;
- the first sentence becomes the spoken hook, the last line the closing card.

The two styles draw the same story: `story_adi.py` (storyboard board) and `story_dan.py` (centred cards).

**Literal pictures, and optional stock photos.** When a beat names a concrete thing (a car, a multifamily building, a warehouse,
retail, a hotel, a boat, a vacation, a credit card ...), the scene is an *objects* scene: one card per thing, in the order they
are spoken, each appearing at the word that names it (`NOUNS` in `story_scenes.py`; about 90 icons in `story_icons.py`, including
the kinds of property). The hook shows the first thing it names. Now and then a card can be a **real photo** instead of the
drawing: set *Stock photos in scenes* (off / sometimes / often) in the Export tab. Photos live in `library/photos` (see `photos.py`).
Add photos in any of three ways: **your own** (Export tab -> Stock photos: pick the thing from your script and choose a picture; no
account needed, or drop files named after the thing into the photos folder), or **Pixabay** / **Pexels** (free for commercial use, no credit needed) with
your own free API key and the *Get photos for this script* button (it searches only when you press it and saves a credit list). Rendering never uses the network.

**Scenes: what is drawn for each beat.** Every beat gets a small drawn story, chosen from what it says (`story_scenes.py`,
shared by both styles; the icons and the recurring stick-figure protagonist are in `story_icons.py`): an income line that
stops when you stop working, steps the figure climbs, a ceiling it hits, hours running out, owning an asset that pays income,
roles around a deal (a hub), an empty bank next to the deal you can still join, freedom, a conversation, cause and effect,
growth or decline, a question with its answer, or a pictogram of the beat's key words. Elements appear when the word that
introduces them is spoken. The same picture twice in a row is replaced by a pictogram. Add a scene by writing one function
in `story_scenes.py` against the backend primitives (icon, figure, text, line, arrow, rect, circle ...) and a rule in `plan()`.
 The story is
stored in the project (`script.txt`, `story.json`); a project without a script uses the built-in sample.

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

## Editing: the timeline (post-production)

The **timeline** at the bottom is a small video editor for your finished render. It is **non-destructive**: the
render is never touched. Your edit (cuts, trims, added sounds, text...) is saved next to the project in
`projects/<name>/<style>/edit.json` and is applied only when you press **Export edit**, which writes a new
`..._edit.mp4` into `output/` in about 15 seconds - nothing is re-rendered. Drag the grip on the dock's top edge to
make it taller; `T` hides it.

**Tracks:** *Text*, *Overlay* (pictures), *Video*, *Voice*, *Effects*, *Music*. Voice and Effects are the narration and sound effects the
renderer made, split into real clips you can edit; Effects and Music are also where the sounds you add live. Each
audio track has a mute button. Clips on the same track that overlap stack into rows.

**The picture follows the sound.** The video is a row of clips placed back to back (a "magnetic" track). The voice and
effects of the render belong to the video clip they were made for: split, trim, delete, move or restore a clip and its
sound goes with it. Effects, music and text you add are *free*: they keep their own place (turn **Ripple** on and they
also shift when you cut or trim video, so they stay lined up with the picture).

| you want to | do this |
|---|---|
| Select | click a clip (Shift / Ctrl-click for several, `Ctrl+A` for all, `Esc` clears) |
| Cut | put the playhead where you want it and press **S** (or *Split*): splits the selected clips, or every clip under the playhead |
| Trim **or expand** | drag a clip's **left or right edge**. Dragging outward restores what was cut: a video clip gets its picture *and its voice and effects* back, up to the end of the render; a sound clip up to the end of its file |
| Delete | **Del** (video clips ripple closed) |
| Reorder scenes | drag a video clip to a new slot - its voice and effects move with it |
| Move a sound | drag a voice / effect clip sideways: it detaches from its scene and becomes a free clip |
| Duplicate | `Ctrl+D` |
| Freeze frame | **F**: holds the frame at the playhead for 1 s (change the length by dragging its right edge) |
| Marker | **M** adds a marker at the playhead (click a marker to jump to it; add a note in the inspector) |
| Undo / redo | `Ctrl+Z`, `Ctrl+Shift+Z` (or `Ctrl+Y`), also the arrows in the toolbar |
| Zoom | the slider, `Ctrl` + mouse wheel, or *Fit* |
| Snap | clips snap to the playhead, markers, beats and other clips (untick *Snap* for free placement) |
| Play / scrub | **Space**, click or drag the ruler, `<` `>` step, `Shift` + arrows jump 5 s, `Home` start |

**The inspector** (the strip under the toolbar) changes with the selection: a video clip has *Speed* (0.25x - 4x),
*Fade in / out*; a sound clip has *Volume*, *Fade in / out*, *Mute* (and *Speed* / *Loop to fill* for clips you
added); a text clip has its text, size and position. With nothing selected it shows the **project** settings: how far
the music dips under speech, the *Voice / Effects / Music level*, *Even out loudness (-14 LUFS)*, brightness /
contrast / saturation, a *Fade out at the end*, and *Reset edit* (undoable).

**Sound libraries.** *Music* and *Effects* tabs work the same way: drop a file on the tab (it goes into the library
and into the project), listen with the play button, drag a row onto the timeline or press *Add* to place it at the
playhead. Music is levelled to -16 LUFS and starts at -12 dB; effects are peak-levelled and start at -10 dB. The
*Built-in* list in the Effects tab holds the twelve sounds the renderer itself uses (whoosh, pop, stamp, ding...).

**Text and captions** (the *Text* tab). *Add text* puts a title at the playhead. *Auto-captions* builds captions from
the narration's word timings (so they follow every cut, move and speed change); *Words per caption* and the
caption look (Classic, Box, Pop with the spoken word lit up, Title, Hand) are set there. Select a text clip to change its
font, size, colour, outline, background box, capitals, highlight, position and fades, or to use its look for every
caption. Text is burned into the exported video with the same look as the preview.

**Pictures** (also in the *Text* tab). Drop a logo, sticker or end card (PNG with transparency works best; it is stored in
the project as a PNG), press *Add* to put it on the *Overlay* lane at the playhead, then use the inspector for size,
opacity, position and fades - *Whole video* turns it into a watermark.

**Preview.** Play runs the last render clip by clip, with every sound scheduled in the browser, so cuts, trims,
speed, volume, fades and the music dip are what you hear; export uses the same list. If you change a Look setting the
stage switches to the live preview until you move the playhead. If a new render changes the timing (for example after
new narration) the editor asks whether to keep or restart your edit.

**CLI:** `python remix.py adi|dan` re-muxes the render's own narration and effects (the older flow); the editor replaces
the old single music block - an earlier music setting is converted into a music clip the first time you open the
timeline.

## Adding a control

Add one `_c(...)` line to the style's list in `studio_config.SCHEMA`, read the value in the style's
`apply_config()`. The app shows it automatically.

## Limits

The narration and the scene content (headline wording, which icon, card contents) are fixed to the
lifestyle-inflation script; the app configures layout, style and effects. Changing the wording would
need new scenes and new narration audio.

**Original music, built for short videos.** `python music_gen.py` synthesises seven background tracks from scratch (*Dark Pulse*, *Slow Burn*,
*Rising Tension*, *Midnight Drive*, *Golden Hour*, *Quiet Storm*, *Clockwork*; no samples or recordings, so no third-party rights) and adds them to the music library, levelled
to -16 LUFS. Each follows one emotional arc: an **instant hook** (an impact and a four-note motif in the first second, no
fade-in), a sparse **intrigue** with room for the voice, a **build** (pulse, kick, hats, a rising arpeggio, tense harmony), a
**riser**, a held-breath **drop-out**, then **the aha**: a huge hit as the harmony lifts from minor to its relative major and
the motif returns bright, a warm **resolution** and a decisive ending. Fit one to a video with the second where its idea lands:
`python music_gen.py --mood "Dark Pulse" --length 73 --aha 58 --name "My video"`.

**Fit it to a video from the Music tab.** *Make music for this video* builds one of the three moods at the exact length of the
project's latest render and puts it on the timeline at 0:00 (no fade-in, so the hook hits at once). **Aha at** is the second
where the idea lands: type one, or leave it empty and the aha is placed automatically on the script's answer (the first positive
quote after a negative thought, e.g. "What can I bring to a deal?"; without a script, 76 % through the video). The options
*Replace the music already on the timeline* and *Export the video with it right away* (the same as pressing Export edit) are on by default.

**Calmer pacing.** Scene elements no longer draw themselves on slowly: *Animation of scene elements* (Export tab) is **reduced**
by default (about 4x quicker; the small delays between an element and its label shrink the same way), **minimal** makes elements
simply appear, **full** is the original draw-on. At any level an element only animates if there is room: everything is drawn before the
camera leaves the frame, and a thing named at the very end of a beat is shown a little early (never flashed up as the scene changes). The sweeping sounds (whoosh, swish) are not used any more in any style. With scenes
that complete quickly the voice can be faster: raise *Speaking speed* in the Voice tab and generate the narration again.

**Render and your timeline edit.** *Render* makes the plain video; everything you put on the timeline (music, effects, text, pictures,
cuts) is an edit that only becomes part of a video when it is applied (*Export edit*). So that music on the timeline is not left
out of a normal render, the Export tab has *After rendering, apply my timeline edit* (on by default): when a render finishes and the
timeline has changes, the edit is exported automatically (about 15 s) and that is the file to watch.

**Pixabay photos and the licence.** *Get photos for this script* uses the Pixabay API (https://pixabay.com/api/docs/) with your own key (Export tab ->
Stock photos). Everything Pixabay serves is under the Pixabay Content License (https://pixabay.com/service/license-summary/): free for commercial use, no
credit needed. It does not allow selling or sharing a picture as it is, using a recognisable trademark / logo / brand to promote goods or services,
or using recognisable people in an immoral, illegal or misleading way - and you remain responsible for checking rights such as releases. So the app
asks only for photos (no illustrations), landscape, at least 1000 px wide, safe-search on; skips any result whose tags name people or well-known
brands (`photos.BLOCK_TAGS`); caches searches for 24 hours and pauses between requests (Pixabay's rules: 100 requests a minute, no automated mass downloads);
downloads each chosen photo to `library/photos` (Pixabay forbids permanent hotlinking); and lists every photo with its photographer and a link to its
page, a *Remove* button and *Copy photo credits*. Look at each photo before you publish.
