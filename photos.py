"""photos.py - optional stock photos for the story scenes.

Photos are kept in library/photos (shared by every project) as  <keyword>--<id>.jpg , for example  multifamily--3935320.jpg .
A scene that names a thing (a car, a multifamily building ...) can show a real photo of it instead of the line drawing, so the
viewer sees the thing that is being talked about. There are two ways to fill the folder:

  * drop your own pictures in (name them after the thing:  car.jpg ,  multifamily building.jpg ,  warehouse--2.jpg ), or
  * press "Get photos for this script" in the Export tab: the app searches Pexels (free for commercial use, no credit needed
    - see https://www.pexels.com/license/ ) with YOUR free API key and saves the best match for each thing the script names.

Photos are only downloaded when you ask. Rendering never touches the network: it only uses what is already in the folder.
"""
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

import projects

PHOTO_DIR = projects.LIBRARY_DIR / "photos"
KEYS_FILE = projects.DATA_DIR / "keys.json"
CREDITS = PHOTO_DIR / "credits.json"
EXT = (".jpg", ".jpeg", ".png", ".webp")

# icon -> what to search for (a clear, plain photo of the thing)
QUERY = {
    "multifamily": "apartment building exterior", "tower": "office building skyscraper", "warehouse": "warehouse building exterior",
    "store": "retail storefront shopping center", "hotel": "hotel building exterior", "land": "vacant land lot",
    "house": "suburban house exterior", "bldg": "commercial building exterior", "car": "luxury car", "truck": "pickup truck",
    "palm": "tropical beach vacation", "plane": "airplane in flight", "boat": "yacht on the sea", "watch": "luxury wristwatch",
    "ring": "diamond ring", "bag": "designer handbag", "shoe": "sneakers", "phone": "smartphone", "laptop": "laptop on desk",
    "tv": "television living room", "coffee": "cup of coffee", "fork": "restaurant dinner table", "bottle": "champagne bottle",
    "dumbbell": "gym weights", "credit_card": "credit cards", "receipt": "bills and receipts", "piggy": "piggy bank",
    "vault": "bank vault", "candles": "stock market chart", "grad_cap": "graduation cap", "health": "hospital doctor",
    "wrench": "building repair maintenance", "crane": "construction crane", "lightning": "power lines electricity",
    "globe": "world globe", "mail": "email on laptop", "keys_house": "house keys", "bill": "paycheck cash", "moneybag": "pile of money",
}
# the things worth a real photo (an idea like a ceiling or a bank balance stays a drawing)
PHOTO_WORTHY = set(QUERY)


# ------------------------------------------------------------------ the key (stored locally, never committed)
def get_key():
    try:
        return json.loads(KEYS_FILE.read_text(encoding="utf-8")).get("pexels", "")
    except Exception:
        return ""


def set_key(key):
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data["pexels"] = (key or "").strip()
    KEYS_FILE.write_text(json.dumps(data), encoding="utf-8")


# ------------------------------------------------------------------ the setting and the folder
def mode():
    """off | sometimes | often (Export tab). Read from the project's settings."""
    try:
        import studio_config
        return studio_config.load()["render"].get("photos", "sometimes")
    except Exception:
        return "sometimes"


def _tokens(name):
    return set(re.findall(r"[a-z0-9]+", name.lower()))


def _dirs():
    out = [PHOTO_DIR]
    try:
        out.insert(0, projects.project_dir() / "assets" / "photos")
    except Exception:
        pass
    return out


_CACHE = {}


def lookup(icon, label=""):
    """A photo of this thing already on disk (project assets first, then the library), or None."""
    key = (icon, label.lower(), tuple(str(d) for d in _dirs()))
    want = _tokens(icon.replace("_", " ")) | _tokens(label)
    stems = {}
    for d in _dirs():
        if d.is_dir():
            for f in sorted(d.iterdir()):
                if f.suffix.lower() in EXT:
                    stems[f] = _tokens(f.stem.split("--")[0])
    if key in _CACHE and all(f.exists() for f in [_CACHE[key]] if _CACHE[key]):
        return _CACHE[key]
    pick = None
    icon_tokens = _tokens(icon.replace("_", " "))
    for f, toks in stems.items():                       # an exact keyword in the name first
        if icon_tokens and toks == icon_tokens:
            pick = f
            break
    if pick is None:
        for f, toks in stems.items():
            if toks & want and not (toks & {"credits"}):
                pick = f
                break
    _CACHE[key] = pick
    return pick


def count():
    d = PHOTO_DIR
    return len([f for f in d.iterdir() if f.suffix.lower() in EXT]) if d.is_dir() else 0


# ------------------------------------------------------------------ fetching from Pexels (only when asked)
def _request(url, key):
    req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": "FlashVideoDirector/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def fetch_one(icon, key=None, opener=_request):
    """Search Pexels for `icon`, save the first landscape match to library/photos. Returns the path (or None)."""
    key = key or get_key()
    if not key:
        raise ValueError("Add your free Pexels API key first (Export tab -> Stock photos)")
    have = lookup(icon)
    if have and have.stem.split("--")[0].lower().replace(" ", "_") == icon:
        return have
    q = urllib.parse.quote(QUERY.get(icon, icon.replace("_", " ")))
    data = json.loads(opener("https://api.pexels.com/v1/search?query=%s&per_page=5&orientation=landscape" % q, key).decode("utf-8"))
    photos = data.get("photos") or []
    if not photos:
        return None
    p = photos[0]
    url = (p.get("src") or {}).get("large") or (p.get("src") or {}).get("original")
    if not url:
        return None
    raw = opener(url, key)
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    out = PHOTO_DIR / ("%s--%s.jpg" % (icon, p.get("id", "x")))
    out.write_bytes(raw)
    try:
        credits = json.loads(CREDITS.read_text(encoding="utf-8"))
    except Exception:
        credits = {}
    credits[out.name] = {"photographer": p.get("photographer", ""), "url": p.get("url", ""), "source": "Pexels", "license": "https://www.pexels.com/license/"}
    CREDITS.write_text(json.dumps(credits, indent=1), encoding="utf-8")
    _CACHE.clear()
    return out


def things_in(story):
    """The photo-worthy things a story's scenes name: [icon, ...] without repeats."""
    import story_scenes
    seen, out = set(), []
    for cid, feats in sorted(story["feats"].items(), key=lambda kv: int(kv[0])):
        for bi in range(len(feats)):
            sp = story_scenes.scene_of(story, int(cid), bi)
            for nd in sp.get("nodes", []):
                ic = nd.get("icon")
                if sp.get("type") == "objects" and ic in PHOTO_WORTHY and ic not in seen:
                    seen.add(ic)
                    out.append(ic)
    return out


def fetch_for_story(story, key=None, opener=_request):
    """Get a photo for every photo-worthy thing the script names. Returns {"got": [...], "had": [...], "none": [...]}."""
    res = {"got": [], "had": [], "none": []}
    for ic in things_in(story):
        if lookup(ic):
            res["had"].append(ic)
            continue
        p = fetch_one(ic, key, opener)
        (res["got"] if p else res["none"]).append(ic)
    return res
