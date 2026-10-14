"""style_board.py - the Board style: Lee's drawing board and camera, with the Desk style's motion graphics on it.

Why it exists. Lee's style has the best movement (every beat is a frame on one long sheet of grid paper and the camera travels from frame to frame with an
eased pan, a small zoom-out and motion blur) but its elements are plain. The Desk style has the best elements (a drawn object for every sentence, line
icons, kinetic type, a paper card with a soft shadow) but it cuts between pages. Board keeps Lee's whole engine (generate_lee.py - the board, the thread,
the pan timing, the GPU camera, the narration plumbing) and replaces only what is drawn inside each frame, using style_desk.py to draw it:
  - a sentence with a drawn object (loan sheet, calendar, rent roll, grid of units, listing, ...) gets that object as a card on its frame;
  - a sentence the script gave a [broll tag] gets a print of that stock footage, taped on, with the sentence in big type under it;
  - otherwise a line icon on a card and kinetic type, or the type alone;
  - captions are small serif lines on a white strip, sound is a soft thud on an amount and a stamp on a decision (no swishes on the pans).
Everything else (settings of the camera, the thread, the grid) is Lee's. The studio talks to this module exactly as it talks to generate_lee: every name it
does not define itself is forwarded to generate_lee.
"""
import os

import projects
import studio_config

if "FLASH_ASPECT" not in os.environ:     # command line: follow the app's saved format
    studio_config.ensure_aspect_env()

from PIL import Image

import generate_lee as L
import generate_video as g
import style_desk as D

STYLE_ID = "board"
L.STYLE_ID = STYLE_ID
INTRO_SFX = []            # the studio reads these two lists for its program: no chime on the hook, no shimmer on the close
OUTRO_SFX = []


def __getattr__(name):
    """Whatever this module does not define is generate_lee's (segments, frame_bytes, prepare, OUT_DIR, pan_beats ...)."""
    return getattr(L, name)


def _box():
    """The pixel box of the frame (W x H) inside a board tile (a tile has GAP / 2 of paper on its left and MV above and below)."""
    ss = L.SS
    return (L.GAP // 2 * ss, L.MV * ss, (L.GAP // 2 + L.W) * ss, (L.MV + L.H) * ss)


def _paint(img, draw, t, ghost, t_ghost):
    """Draw one frame's content onto the paper of tile `img`. While the camera is still travelling into a frame its content is shown faintly
    (as Lee does) by drawing it as it will look when finished and blending that over the bare paper."""
    box = _box()
    base = img.crop(box)
    if ghost > 0.01:
        full = draw(base.copy(), t_ghost)
        page = Image.blend(base, full, min(0.4, ghost * 1.6))
    else:
        page = draw(base, t)
    img.paste(page, box[:2])


def make_tile(n, t, ghost=0.0, rec=None, force=None, _auto=True):
    """Board frame n at clip time t: Lee's paper and thread, Desk's content."""
    img = L.tile_bg()
    L.thread(L.Canvas(img, t, ox=-L.GAP / 2, oy=-L.MV), n)
    info = L.PANELS[n]
    if info[0] == "intro":
        total = D.intro_setup()[0]
        _paint(img, lambda im, tt: (D.intro_draw(im, tt, total), im)[1], t, ghost, total * 0.9)
    elif info[0] == "outro":
        _paint(img, lambda im, tt: (D.outro_draw(im, tt), im)[1], t, ghost, 3.0)
    else:
        cid = info[1]
        c = L.CLIPS[cid - 1]
        idx = force if force is not None else g.local_beat(c, t)[0]
        s1 = g.clip_beats(c)[idx][1]
        _paint(img, lambda im, tt: D.page_for(cid, idx, tt, base=im, progress=False), t, ghost, s1 - 0.05)
    return img


def apply_config(cfg=None):
    """Lee's settings first (palette, board, camera), then the Board group on top."""
    L.apply_config(cfg)
    cfg = studio_config.normalize(cfg) if cfg else studio_config.load()
    n = cfg["board"]
    L.ORANGE = studio_config.rgb(n["palette"]["accent"])
    L.SHOW_GRID, L.SHOW_THREAD = bool(n["layout"]["show_grid"]), bool(n["layout"]["show_thread"])
    L.PAN_D_MAX = float(n["camera"]["pan_ms"]) / 1000.0
    L.BLUR_SAMPLES = max(1, min(16, int(n["camera"]["blur_samples"])))
    L.FOLLOW = float(n["camera"]["follow"])
    L.GHOST = float(n["camera"]["ghost"])
    L._TILE_BG = None
    L._SET.clear()
    D.ACCENT, D.RED, D.BONE, D.INK = L.ORANGE, L.RED, L.INK, L.BG          # Desk draws in the board's colours
    D.CAPTION_SCALE = float(n["layout"]["caption_size"])
    D.KINETIC = bool(n["layout"]["kinetic_caption"])
    D._PLAN.clear()


def apply_to(gm):
    L.STYLE_ID = STYLE_ID
    L.apply_to(gm)                                        # story, folders, panels, camera timing (Lee's)
    D._STORY = L.STORY
    D.CLIPS[:] = L.CLIPS
    D._WORDS.clear()
    D._PLAN.clear()
    D._PHR.clear()
    D.FOOTAGE = True                                      # the script's [broll tag] shots appear as taped prints
    L.make_tile = make_tile                               # the one thing that changes: what is drawn inside a frame
    gm.sfx_events = D.sfx_events                          # a soft thud on an amount, a stamp on a decision, nothing on the pans
    gm.build_mixed_audio = D.mixed_audio
    apply_config()
