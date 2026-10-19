"""profile.py - whose account a video is for: the Instagram handle and the profile picture shown on the closing card and the follow card.

A project can have a `profile.json` in its folder:
    {"handle": "lilanthagunasinghe", "name": "Lilantha Gunasinghe", "picture": "lilantha.jpg", "tagline": "real numbers behind every deal"}
`picture` is a file in library/profile (a square or portrait photo, any size). Without a profile.json a project shows the generic icon, as before.
"""
import json
from pathlib import Path

import projects

LIB = projects.LIB_CACHE.parent / "profile"
_CIRCLES = {}


def load(name=None):
    """{"handle", "name", "picture" (a Path or None)} of the project, or None when the project has no profile."""
    try:
        data = json.loads((projects.project_dir(name) / "profile.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    handle = str(data.get("handle", "")).strip().lstrip("@")
    if not handle:
        return None
    pic = LIB / str(data["picture"]) if data.get("picture") else None
    return {"handle": handle, "name": data.get("name") or handle, "picture": pic if pic and pic.exists() else None,
            "tagline": data.get("tagline") or "real numbers behind every deal"}


def initials(prof):
    words = [w for w in (prof.get("name") or prof["handle"]).replace(".", " ").replace("_", " ").split() if w]
    return ("".join(w[0] for w in words[:2]) or prof["handle"][:1]).upper()


def circle(path, px):
    """The picture as a round RGBA image `px` pixels wide (centre-cropped to a square, smooth edge). Cached."""
    from PIL import Image, ImageDraw
    key = (str(path), int(px))
    if key not in _CIRCLES:
        im = Image.open(path).convert("RGB")
        w, h = im.size
        s = min(w, h)
        top = int((h - s) * 0.30)                              # faces sit in the upper part of a portrait photo
        im = im.crop(((w - s) // 2, top, (w - s) // 2 + s, top + s)).resize((int(px), int(px)), Image.LANCZOS)
        big = Image.new("L", (int(px) * 4, int(px) * 4), 0)
        ImageDraw.Draw(big).ellipse([0, 0, int(px) * 4 - 1, int(px) * 4 - 1], fill=255)
        mask = big.resize((int(px), int(px)), Image.LANCZOS)
        out = im.convert("RGBA")
        out.putalpha(mask)
        _CIRCLES[key] = out
    return _CIRCLES[key]
