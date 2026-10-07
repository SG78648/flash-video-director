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
import urllib.error
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
    "multifamily": "apartment building exterior", "tower": "office building skyscraper", "warehouse": "warehouse building exterior", "storage": "self storage units facility",
    "store": "retail storefront shopping center", "hotel": "hotel building exterior", "land": "vacant land lot",
    "house": "suburban house exterior", "bldg": "commercial building exterior", "car": "luxury car", "truck": "pickup truck",
    "palm": "tropical beach vacation", "plane": "airplane in flight", "boat": "yacht on the sea", "watch": "luxury wristwatch",
    "ring": "diamond ring", "bag": "designer handbag", "shoe": "sneakers", "phone": "smartphone", "laptop": "laptop on desk",
    "tv": "television living room", "coffee": "cup of coffee", "fork": "restaurant dinner table", "bottle": "champagne bottle",
    "dumbbell": "gym weights", "credit_card": "credit cards", "receipt": "bills and receipts", "piggy": "piggy bank",
    "vault": "bank vault", "candles": "stock market chart", "grad_cap": "graduation cap", "health": "hospital doctor",
    "wrench": "building repair maintenance", "crane": "construction crane", "lightning": "power lines electricity",
    "globe": "world globe", "mail": "email on laptop", "keys_house": "house keys", "bank": "classic bank building columns facade", "coins": "stack of coins", "calculator": "calculator and documents", "door": "open door", "bill": "paycheck cash", "moneybag": "pile of money",
}
PRETTY = {"bldg": "commercial building", "multifamily": "apartment building", "tower": "office tower", "store": "retail store",
          "grad_cap": "degree / school", "moneybag": "money / millionaire", "keys_house": "rental / tenant", "credit_card": "credit card",
          "candles": "stock market", "palm": "vacation", "fork": "restaurant", "bill": "paycheck", "wrench": "repairs", "crane": "construction",
          "for_sale": "for sale", "keys": "keys", "lightning": "utilities", "piggy": "savings", "vault": "vault / safe", "bottle": "bottle service"}


def pretty(icon):
    return PRETTY.get(icon, icon.replace("_", " "))


# the things worth a real photo (an idea like a ceiling or a bank balance stays a drawing)
PHOTO_WORTHY = set(QUERY)


# ------------------------------------------------------------------ the key (stored locally, never committed)
PROVIDERS = {
    "pexels": {"name": "Pexels", "license": "https://www.pexels.com/license/"},
    "pixabay": {"name": "Pixabay", "license": "https://pixabay.com/service/license-summary/"},
}


def _keys():
    try:
        return json.loads(KEYS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def provider():
    """The photo library the app searches when asked: the one chosen last, else the first one that has a key."""
    k = _keys()
    p = k.get("provider")
    if p in PROVIDERS:
        return p
    for name in PROVIDERS:
        if k.get(name):
            return name
    return "pixabay"


def get_key(which=None):
    return _keys().get(which or provider(), "")


def set_key(key, which="pexels"):
    if which not in PROVIDERS:
        raise ValueError("unknown photo library")
    data = _keys()
    if (key or "").strip():                  # an empty key only switches the library, it never erases a saved key
        data[which] = key.strip()
    data["provider"] = which
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEYS_FILE.write_text(json.dumps(data), encoding="utf-8")


# ------------------------------------------------------------------ keeping to what the licence allows
# Everything the Pixabay API returns is under the Pixabay Content License: free for commercial use, no credit needed.
# What it does NOT allow (https://pixabay.com/service/license-summary/): selling or sharing a picture as it is, using a
# recognisable trademark / logo / brand to promote goods or services, and using recognisable people in an immoral, illegal or
# misleading way. The app therefore (1) asks only for photos (no illustrations), safe-search on, (2) skips any result whose
# tags mention people or well-known brands, and (3) lists every photo it fetched so you can look at it and remove it.
BLOCK_TAGS = set("""people person man men woman women girl boy child children kid kids baby couple family portrait face faces smile
    model models crowd group team friends student students worker workers businessman businesswoman doctor nurse patient lady guy
    logo logos brand brands trademark
    tesla bmw mercedes audi porsche ferrari lamborghini lexus toyota honda ford chevrolet bentley rolls royce jaguar maserati bugatti
    apple iphone ipad macbook samsung google microsoft amazon nike adidas gucci prada louis vuitton chanel rolex starbucks netflix
    coca cola pepsi mcdonalds walmart ikea""".split())


def tags_ok(tags):
    """False when a photo's tags name people or a known brand (those are the cases the licence restricts)."""
    return not (set(re.findall(r"[a-z0-9]+", (tags or "").lower())) & BLOCK_TAGS)


SEARCH_CACHE = PHOTO_DIR / "search_cache.json"
CACHE_SECONDS = 24 * 3600                   # Pixabay requires search results to be cached for 24 hours
PAUSE = 0.7                                 # and allows 100 requests per minute: stay far below it


def _cached_search(query, loader):
    import time
    try:
        cache = json.loads(SEARCH_CACHE.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    hit = cache.get(query)
    if hit and time.time() - hit["t"] < CACHE_SECONDS:
        return hit["data"]
    data = loader()
    cache = {k: v for k, v in cache.items() if time.time() - v["t"] < CACHE_SECONDS}
    cache[query] = {"t": time.time(), "data": data}
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    SEARCH_CACHE.write_text(json.dumps(cache), encoding="utf-8")
    return data


def list_photos():
    """Every photo in the library with where it came from, for the review list in the Export tab."""
    try:
        credits = json.loads(CREDITS.read_text(encoding="utf-8"))
    except Exception:
        credits = {}
    out = []
    for f in sorted(PHOTO_DIR.iterdir()) if PHOTO_DIR.is_dir() else []:
        if f.suffix.lower() in EXT:
            c = credits.get(f.name, {})
            out.append({"file": f.name, "thing": f.stem.split("--")[0], "source": c.get("source", "your own"),
                        "user": c.get("photographer", ""), "page": c.get("url", ""), "license": c.get("license", "")})
    return out


def remove_photo(name):
    p = (PHOTO_DIR / name).resolve()
    if PHOTO_DIR.resolve() not in p.parents or p.suffix.lower() not in EXT or not p.exists():
        raise ValueError("no such photo")
    p.unlink()
    try:
        credits = json.loads(CREDITS.read_text(encoding="utf-8"))
        credits.pop(name, None)
        CREDITS.write_text(json.dumps(credits, indent=1), encoding="utf-8")
    except Exception:
        pass
    _CACHE.clear()


def credits_text():
    """A ready-to-paste credit list (not required by the licence, but kind to the photographers)."""
    lines = []
    for p in list_photos():
        if p["user"]:
            lines.append("Photo by %s on %s%s" % (p["user"], p["source"], " - " + p["page"] if p["page"] else ""))
    return "\n".join(lines)


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
def _request(url, key=None):
    headers = {"User-Agent": "FlashVideoDirector/1.0"}
    if key and "pexels" in url:
        headers["Authorization"] = key
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _search(which, icon, key, opener):
    """(photo id, download url, photographer, page url) of the best match, or None."""
    q = urllib.parse.quote(QUERY.get(icon, icon.replace("_", " ")))
    if which == "pixabay":
        # https://pixabay.com/api/docs/ : photos only, landscape, big enough for a card, safe-search on, cached for 24 hours
        url = ("https://pixabay.com/api/?key=%s&q=%s&image_type=photo&orientation=horizontal&safesearch=true&min_width=1000"
               "&order=popular&per_page=30" % (urllib.parse.quote(key), q))

        def load():
            raw = opener(url, None)
            try:
                return json.loads(raw.decode("utf-8"))
            except Exception:
                raise ValueError("Pixabay did not accept the request: check your API key in your Pixabay account (%s)" % raw[:80].decode("utf-8", "replace"))
        data = _cached_search("pixabay|" + q, load)
        for h in data.get("hits") or []:
            if h.get("type", "photo") != "photo" or not tags_ok(h.get("tags", "")):
                continue                                                  # illustrations, people and brands are skipped
            url = h.get("largeImageURL") or (h.get("webformatURL") or "").replace("_640", "_960")      # webformatURL: 640 px, 960 on request
            if url:
                return (h.get("id", "x"), url, h.get("user", ""), h.get("pageURL", ""))
        return None
    data = json.loads(opener("https://api.pexels.com/v1/search?query=%s&per_page=5&orientation=landscape" % q, key).decode("utf-8"))
    photos = data.get("photos") or []
    if not photos:
        return None
    p = photos[0]
    url = (p.get("src") or {}).get("large") or (p.get("src") or {}).get("original")
    return (p.get("id", "x"), url, p.get("photographer", ""), p.get("url", "")) if url else None


def fetch_one(icon, key=None, opener=_request, which=None):
    """Search the chosen photo library for `icon`, save the best landscape match to library/photos. Returns the path (or None)."""
    which = which or provider()
    key = key or get_key(which)
    if not key:
        raise ValueError("Add your free %s API key first (Export tab -> Stock photos), or add your own photos" % PROVIDERS[which]["name"])
    have = lookup(icon)
    if have and have.stem.split("--")[0].lower().replace(" ", "_") == icon:
        return have
    found = _search(which, icon, key, opener)
    if not found:
        return None
    pid, url, who, page = found
    try:
        raw = opener(url, key if which == "pexels" else None)
    except Exception:
        if which == "pixabay" and "_960" in url:
            raw = opener(url.replace("_960", "_640"), None)
        else:
            raise
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    out = PHOTO_DIR / ("%s--%s.jpg" % (icon, pid))
    out.write_bytes(raw)
    try:
        credits = json.loads(CREDITS.read_text(encoding="utf-8"))
    except Exception:
        credits = {}
    credits[out.name] = {"photographer": who, "url": page, "source": PROVIDERS[which]["name"], "license": PROVIDERS[which]["license"]}
    CREDITS.write_text(json.dumps(credits, indent=1), encoding="utf-8")
    _CACHE.clear()
    return out


def save_own(icon, raw_bytes):
    """Add a photo you chose yourself for this thing (any image file); stored as a JPEG named after the thing."""
    from PIL import Image
    import io
    if icon not in PHOTO_WORTHY:
        raise ValueError("unknown thing")
    im = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    if max(im.size) > 2000:
        im.thumbnail((2000, 2000))
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    out = PHOTO_DIR / ("%s--mine.jpg" % icon)
    im.save(out, "JPEG", quality=90)
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
        try:
            p = fetch_one(ic, key, opener)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise ValueError("Pixabay's limit of 100 requests a minute was reached: wait a minute and press the button again")
            if e.code in (400, 401, 403):
                raise ValueError("Pixabay did not accept the API key: check it in your Pixabay account")
            raise
        (res["got"] if p else res["none"]).append(ic)
        import time
        time.sleep(PAUSE)
    return res
