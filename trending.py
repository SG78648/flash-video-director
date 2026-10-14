"""trending.py - what music is trending, so you can pick a track for a video.

Two sources, both official and free:

  instagram   Meta's Instagram Audio API (GET /ig_audio on the Graph API). With no search term it returns the trending music (or original sounds) that Instagram allows
              third parties to use. It needs an Instagram Business or Creator account linked to a Facebook Page, a Meta app with the instagram_basic and
              instagram_content_publish permissions and a user access token (Facebook Login). The account id and the token are kept in studio_data/keys.json,
              never shown again. https://developers.facebook.com/documentation/instagram-platform/content-publishing/audio-api
  charts      Apple Music's public "most played" chart (no key) with the 30 second preview of every song (iTunes lookup). It is not Instagram's list, but what is
              charting is what Reels trend on; use it when the Instagram connection is not set up.

Neither gives you a licence to publish a popular song inside your own video file. Instagram's own library is for personal accounts, and a business account is
limited to Meta's Sound Collection, so the safest way to use a trending sound is to attach it in Instagram when you post and use the studio's copy only to time the edit.
"""
import json
import time
import urllib.parse
import urllib.request

import projects

KEYS_FILE = projects.DATA_DIR / "keys.json"
CACHE = projects.LIB_CACHE / "trending"
UA = {"User-Agent": "Mozilla/5.0 FlashStudio/1.0"}
GRAPH = "https://graph.facebook.com/v22.0"
TTL = 6 * 3600


def _keys():
    try:
        return json.loads(KEYS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def ig_status():
    k = _keys()
    return {"connected": bool(k.get("ig_token") and k.get("ig_user_id"))}


def set_ig(user_id, token):
    """Save the Instagram account id and access token (an empty value keeps what is saved)."""
    data = _keys()
    if (user_id or "").strip():
        data["ig_user_id"] = user_id.strip()
    if (token or "").strip():
        data["ig_token"] = token.strip()
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEYS_FILE.write_text(json.dumps(data), encoding="utf-8")
    return ig_status()


def clear_ig():
    data = _keys()
    data.pop("ig_user_id", None)
    data.pop("ig_token", None)
    KEYS_FILE.write_text(json.dumps(data), encoding="utf-8")


def _get(url, tries=3, timeout=25):
    last = None
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()
        except Exception as e:           # a hiccup of the service: wait a moment and ask again
            last = e
            time.sleep(1.5)
    raise RuntimeError(f"could not reach the service ({last})")


def _cached(name, loader):
    f = CACHE / (name + ".json")
    try:
        if time.time() - f.stat().st_mtime < TTL:
            return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        pass
    data = loader()
    CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data), encoding="utf-8")
    return data


def instagram(query="", audio_type="music"):
    """Trending music (or search results for `query`) from Instagram's Audio API."""
    k = _keys()
    if not (k.get("ig_token") and k.get("ig_user_id")):
        raise RuntimeError("connect your Instagram account first (account id and access token)")
    qs = {"audio_type": audio_type, "user_id": k["ig_user_id"], "access_token": k["ig_token"]}
    if query:
        qs["search_query"] = query
    try:
        raw = json.loads(_get(GRAPH + "/ig_audio?" + urllib.parse.urlencode(qs)))
    except RuntimeError as e:
        raise RuntimeError(str(e).replace(k["ig_token"], "***"))
    if raw.get("error"):
        raise RuntimeError("Instagram said: " + str(raw["error"].get("message", raw["error"]))[:240])
    out = []
    for i, r in enumerate(raw.get("data", [])):
        out.append({"id": str(r.get("id")), "rank": i + 1, "title": r.get("title") or "", "artist": r.get("display_artist") or r.get("ig_username") or "",
                    "seconds": round((r.get("duration_in_ms") or 0) / 1000.0), "preview": r.get("download_url") or r.get("on_platform_audio_preview_link") or "",
                    "ads_ok": r.get("is_ads_eligible"), "source": "instagram", "kind": audio_type})
    return out


def charts(country="us", n=30):
    """Apple Music's most played songs with their 30 second previews."""
    def load():
        feed = json.loads(_get(f"https://rss.applemarketingtools.com/api/v2/{country}/music/most-played/{n}/songs.json"))["feed"]["results"]
        ids = ",".join(r["id"] for r in feed)
        info = {}
        try:
            for r in json.loads(_get(f"https://itunes.apple.com/lookup?id={ids}&country={country}&entity=song")).get("results", []):
                info[str(r.get("trackId"))] = r
        except RuntimeError:
            pass
        out = []
        for i, r in enumerate(feed):
            x = info.get(r["id"], {})
            out.append({"id": r["id"], "rank": i + 1, "title": r["name"], "artist": r["artistName"], "seconds": round((x.get("trackTimeMillis") or 0) / 1000.0),
                        "preview": x.get("previewUrl", ""), "art": (r.get("artworkUrl100") or "").replace("100x100", "200x200"),
                        "genre": x.get("primaryGenreName", ""), "source": "charts", "url": r.get("url", "")})
        return out
    return _cached(f"charts_{country}_{n}", load)


def trending(source="charts", query="", kind="music"):
    return instagram(query, kind) if source == "instagram" else charts()


def fetch_preview(url):
    """The bytes of a preview (a 30 second clip) so it can be put in the music library. Only http(s) links to the services above are fetched."""
    host = urllib.parse.urlparse(url).netloc.lower()
    ok = ("itunes.apple.com", "mzstatic.com", "fbcdn.net", "cdninstagram.com", "facebook.com", "fbsbx.com", "instagram.com")
    if not url.startswith("https://") or not any(host == h or host.endswith("." + h) for h in ok):
        raise ValueError("that preview link is not from a known source")
    return _get(url, timeout=40)
