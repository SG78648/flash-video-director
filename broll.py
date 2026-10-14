"""broll.py - real moving pictures (B-roll) for the story scenes.

A beat that talks about an apartment building, a handshake or a pile of money can sit on top of a few seconds of real footage of it, graded
black and white by the Noir style. Footage comes from Pixabay (free for commercial use, no credit needed, see
https://pixabay.com/service/license-summary/ ) with the same free API key the photo feature uses (Export tab > Stock photos).

Footage is only downloaded when you ask (`fetch_for_story`, the "Get B-roll" button or `python broll.py "Project name"`). Rendering never
touches the network: it only reads what is already in library/broll.

Each clip is kept twice. library/broll/raw/<id>.mp4 is the download. library/broll/frames/<id>/ is a short loop (4 s at 24 fps, cropped to
9:16 and scaled to 540 x 960, as numbered jpg files) so any frame can be read in a few milliseconds, in any order, by any render worker.
"""
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import projects

BROLL_DIR = projects.LIBRARY_DIR / "broll"
RAW = BROLL_DIR / "raw"
FRAMES = BROLL_DIR / "frames"
META = BROLL_DIR / "meta.json"
FPS = 24
LOOP_S = 4.0
W, H = 540, 960
UA = {"User-Agent": "FlashVideoDirector/1.0", "Accept": "application/json"}

# What a scene is about -> a TAG of the curated shot library (library/broll/curated.json: clip id -> tags, chosen by eye after looking at every clip,
# because a keyword search of free stock footage returns many unrelated clips). A beat with no matching tag simply has no footage.
BY_ICON = {
    "multifamily": ["residential aerial"], "mobile_home": ["residential aerial"], "house": ["residential aerial"], "land": ["residential aerial"],
    "bldg": ["city aerial"], "tower": ["city aerial"], "hotel": ["city aerial"], "store": ["crowd"], "warehouse": ["city aerial"],
    "bank": ["stock board"], "moneybag": ["money"], "coins": ["money"], "bill": ["money"], "piggy": ["money"], "vault": ["money"],
    "calculator": ["calculator"], "scroll": ["contract"], "keys_house": ["door"], "key": ["door"], "door": ["door"],
    "person": ["thinking"], "people": ["crowd"], "briefcase": ["walk alone"], "clock": ["clock"], "hourglass": ["clock"],
    "health": ["hospital"], "wrench": ["repairs"], "crane": ["repairs"], "candles": ["stock board"], "bars": ["stock board"],
    "trend_down": ["storm"], "laptop": ["laptop"], "phone": ["phone"], "warning": ["storm"], "padlock": ["door"],
    "bulb": ["thinking"], "percent": ["stock board"], "shield": ["calm"], "target": ["thinking"],
}
BY_TYPE = {
    "calc": ["calculator"], "stat": ["stock board"], "stack": ["documents"], "ask": ["thinking"], "send": ["phone"], "follow": ["phone"],
    "keyword": ["phone"], "count": ["residential aerial"], "cards": ["handshake"],
}
GENERIC = ["city night"]


def _keys_file():
    return projects.DATA_DIR / "keys.json"


def _key():
    import photos
    k = photos.get_key("pixabay")
    if not k:
        raise ValueError("no Pixabay API key saved (Export tab > Stock photos). It is free at pixabay.com/api/docs/")
    return k


def _meta():
    try:
        return json.loads(META.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_meta(m):
    BROLL_DIR.mkdir(parents=True, exist_ok=True)
    META.write_text(json.dumps(m, indent=1), encoding="utf-8")


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def search(query, per_page=20):
    url = "https://pixabay.com/api/videos/?" + urllib.parse.urlencode({"key": _key(), "q": query, "per_page": per_page, "safesearch": "true"})
    return json.loads(_get(url).decode("utf-8")).get("hits", [])


BAD_TAGS = re.compile(r"\b(logo|watermark|text|screen recording|green screen|greenscreen|animation|motion graphics|cartoon|3d|render|intro|template)\b", re.I)


def pick(hits):
    """The best clip of a search: 6 to 60 seconds long, 1080p or better, no motion graphics or green screens, the most popular first."""
    for h in hits:
        v = h.get("videos") or {}
        small = v.get("small") or v.get("medium") or {}
        if not small.get("url") or not (6 <= h.get("duration", 0) <= 60) or small.get("width", 0) < 1280:
            continue
        if BAD_TAGS.search(h.get("tags", "")) or h.get("isAiGenerated") or h.get("isLowQuality"):
            continue
        return h
    return None


def have(query):
    """The id of a prepared clip that was fetched for this exact query, or None."""
    m = _meta()
    for cid, info in m.items():
        if query in info.get("queries", []) and (FRAMES / cid / "00000.jpg").exists():
            return cid
    return None


def prepare(clip_id, src, start=0.6):
    """Cut a 4 second loop out of the download: 9:16 crop, 540 x 960, 24 fps, numbered jpg files."""
    out = FRAMES / str(clip_id)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.jpg"):
        old.unlink()
    vf = "fps=%d,crop='min(iw,ih*9/16)':'min(ih,iw*16/9)',scale=%d:%d:flags=lanczos" % (FPS, W, H)
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(start), "-i", str(src), "-t", str(LOOP_S), "-vf", vf, "-q:v", "3",
                        "-start_number", "0", str(out / "%05d.jpg")], capture_output=True, text=True)
    if r.returncode != 0 or not (out / "00000.jpg").exists():
        raise RuntimeError("ffmpeg could not cut the clip: " + r.stderr[-200:])
    return len(list(out.glob("*.jpg")))


def fetch(query, log=print):
    """Download and prepare the best clip for `query` (nothing happens when one is already there). Returns its id or None."""
    got = have(query)
    if got:
        return got
    hit = pick(search(query))
    if not hit:
        log("  no usable clip for '%s'" % query)
        return None
    cid = str(hit["id"])
    RAW.mkdir(parents=True, exist_ok=True)
    raw = RAW / (cid + ".mp4")
    if not raw.exists():
        v = hit["videos"].get("small") or hit["videos"]["medium"]
        log("  downloading %s (%.1f MB) for '%s'" % (cid, v.get("size", 0) / 1e6, query))
        raw.write_bytes(_get(v["url"], timeout=120))
    if not (FRAMES / cid / "00000.jpg").exists():
        dur = float(hit.get("duration", 8))
        prepare(cid, raw, start=max(0.0, min(dur - LOOP_S - 0.2, dur * 0.25)))
    m = _meta()
    info = m.setdefault(cid, {"queries": [], "tags": hit.get("tags", ""), "user": hit.get("user", ""), "page": hit.get("pageURL", ""), "duration": hit.get("duration")})
    if query not in info["queries"]:
        info["queries"].append(query)
    _save_meta(m)
    return cid


# ------------------------------------------------------------------ which queries a beat wants
def queries_for(story, cid, idx):
    """Up to two queries (two shots) for a beat. A `[broll first shot | second shot]` line in the script wins, else they come from what the beat is about."""
    import story_scenes
    f = story["feats"][str(cid)][idx]
    if f.get("broll"):
        return [q.strip() for q in f["broll"][:2] if q.strip()]
    sp = story_scenes.scene_of(story, cid, idx)
    if sp.get("type") in ("send", "follow", "keyword", "ask"):          # a call to action is a clean card, never footage
        return []
    out = []
    for c in story_scenes.concrete(f["text"]):
        out += BY_ICON.get(c["icon"], [])[:1]
    out += BY_TYPE.get(sp.get("type"), [])[:1]
    if sp.get("icon") in BY_ICON:
        out += BY_ICON[sp["icon"]][:1]
    out += BY_ICON.get(f.get("icon"), [])[:1]
    seen, res = set(), []
    for q in out:
        if q not in seen:
            seen.add(q)
            res.append(q)
    return res[:2] or [GENERIC[(cid * 3 + idx) % len(GENERIC)]]


def hook_queries(story):
    import story_scenes
    if story.get("hook_broll"):
        return [q for q in story["hook_broll"][:2] if q]
    out = []
    for c in story_scenes.concrete(story.get("hook", "")):
        out += BY_ICON.get(c["icon"], [])[:1]
    return out[:2] or BY_ICON.get(story_scenes.hook_icon(story), GENERIC)[:1]


def all_queries(story):
    qs = list(hook_queries(story))
    for cid in sorted(story["feats"], key=int):
        for i in range(len(story["feats"][cid])):
            qs += queries_for(story, int(cid), i)
    seen, res = set(), []
    for q in qs:
        if q not in seen:
            seen.add(q)
            res.append(q)
    return res


def fetch_for_story(story, log=print):
    """Fetch every clip a script wants that is not in the library yet. Returns {query: clip id or None}."""
    out = {}
    for q in all_queries(story):
        try:
            out[q] = fetch(q, log)
        except Exception as exc:
            log("  '%s' failed: %s" % (q, str(exc)[:120]))
            out[q] = None
    return out


# ------------------------------------------------------------------ reading frames (render time, no network)
_COUNT = {}


def frame_count(clip_id):
    if clip_id not in _COUNT:
        _COUNT[clip_id] = len(list((FRAMES / str(clip_id)).glob("*.jpg")))
    return _COUNT[clip_id]


def frame(clip_id, t):
    """The picture of clip `clip_id` at `t` seconds (the loop plays forward, then backward, so it never jumps)."""
    from PIL import Image
    n = frame_count(clip_id)
    if n <= 0:
        return None
    pos = t * FPS
    cyc = max(1, 2 * (n - 1))
    k = int(pos) % cyc
    k = k if k < n else cyc - k
    return Image.open(FRAMES / str(clip_id) / ("%05d.jpg" % k)).convert("RGB")


def curated():
    try:
        return json.loads((BROLL_DIR / "curated.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def lookup(query, pick_n=0):
    """The id of a curated clip for a tag (several clips can share a tag, `pick_n` chooses between them), else None."""
    q = (query or "").strip().lower()
    ids = [i for i, tags in curated().items() if q in tags and (FRAMES / i / "00000.jpg").exists()]
    return ids[pick_n % len(ids)] if ids else None


if __name__ == "__main__":      # python broll.py "Project name"   -> fetches the footage its script wants
    import script_story
    name = sys.argv[1] if len(sys.argv) > 1 else projects.active()
    st = script_story.load(name)
    if st is None:
        print("that project has no script")
        sys.exit(1)
    res = fetch_for_story(st)
    print(json.dumps(res, indent=1))
