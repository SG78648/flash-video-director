"""style_mint.py - the Mint style: the Board style (Lee's drawing board and camera, the Desk style's drawn objects, kinetic type and footage prints) in the Flash palette.

Nothing about the movement or the content changes. Only the colours do: a white page with a faint mint dotted background (Flash's), deep teal-ink text,
teal for the spoken word, rules and strokes (the darker hue of the bolt, readable on white), mint for fills (bars, dots, lit windows), cards of the pale mint
tint with a mint hairline and a cool teal shadow, red for what hurts. The studio talks to this module like to generate_lee: every name it does not define is
forwarded to generate_lee (see style_board.py).
"""
import os

import projects
import studio_config

if "FLASH_ASPECT" not in os.environ:     # command line: follow the app's saved format
    studio_config.ensure_aspect_env()

from PIL import Image, ImageDraw

import style_board as B

L, D = B.L, B.D

STYLE_ID = "mint"
INTRO_SFX = []
OUTRO_SFX = []

# the Flash palette (style_flash.py)
PAGE = (255, 255, 255)
CARD = (238, 252, 248)
CARD_LINE = (190, 238, 226)
SOFT = (214, 246, 237)
BAR = (9, 36, 40)
MUTE = (118, 148, 146)
DOT = (203, 238, 228)
THREAD = (150, 204, 196)


def __getattr__(name):
    return getattr(L, name)


def _tile_bg():
    """The board's sheet: a white page with a dot at every grid crossing (Flash's dotted background) instead of Lee's lines."""
    if L._TILE_BG is None:
        th = L.H + 2 * L.MV
        im = Image.new("RGB", (L.P * L.SS, th * L.SS), L.BG)
        if L.SHOW_GRID:
            dr = ImageDraw.Draw(im)
            r = 3 * L.SS
            for x in range(L.GAP // 2 + L.GRID // 2, L.P, L.GRID):
                for y in range(L.MV + L.GRID // 2 - 2 * L.GRID, th, L.GRID):
                    if y >= 0:
                        dr.ellipse([x * L.SS - r, y * L.SS - r, x * L.SS + r, y * L.SS + r], fill=L.GRID_C)
        L._TILE_BG = im
    return L._TILE_BG.copy()


def apply_config(cfg=None):
    B.apply_config(cfg, "mint")                       # Lee's engine settings, then this style's own group
    cfg = studio_config.normalize(cfg) if cfg else studio_config.load()
    n = cfg["mint"]["palette"]
    rgb = studio_config.rgb
    ink, teal, mint, neg = rgb(n["ink"]), rgb(n["accent"]), rgb(n["mint"]), rgb(n["negative"])
    # Lee's board: page, dots, thread, progress line
    L.BG, L.GRID_C, L.INK, L.ORANGE, L.RED = PAGE, DOT, ink, teal, neg
    L.WHITE, L.SHADOW, L.CURVE, L.MUTE, L.BLACK = CARD, (176, 222, 212), THREAD, MUTE, BAR
    L.tile_bg = _tile_bg
    L._TILE_BG = None
    L._SET.clear()
    # the Desk content drawn on it
    D.INK, D.BONE, D.ASH, D.CARD = PAGE, ink, MUTE, CARD
    D.ACCENT, D.RED, D.GREEN, D.LIGHT = teal, neg, mint, (255, 255, 255)
    D.PAPER, D.PAPER2, D.TXT, D.MUTED, D.LINE, D.DEEP = CARD, SOFT, ink, MUTE, CARD_LINE, (12, 48, 52)
    D.SHADOW_RGB, D.TEXT_SHADOW_RGB, D.HAIR = (20, 80, 80), (10, 50, 54), CARD_LINE
    D.TAPE_RGBA, D.PHOTO_TINT = (190, 238, 226, 210), (232, 244, 242)
    D.BLDG = {"body": (40, 84, 88), "cornice": (30, 68, 72), "off": (26, 56, 60), "base": (20, 46, 50), "on": mint}
    D.CALC = {"edge": (40, 96, 100), "unit": (170, 215, 208), "op_hit": (150, 250, 225), "fn_hit": (90, 150, 150), "fn": (44, 96, 100), "hit": (60, 120, 124), "key": (30, 72, 76)}
    D.SHEETBAR = (40, 96, 100)
    D._PLAN.clear()


def apply_to(gm):
    B.apply_to(gm, STYLE_ID, apply_config)
