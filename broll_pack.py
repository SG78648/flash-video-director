"""broll_pack.py - grow the stock footage library with a fixed list of subjects (the "pack"), on purpose and not while rendering.

    python broll_pack.py fetch            download the candidates for every subject below (2 per subject, HD, vertical clips first)
    python broll_pack.py fetch kitchen    only the subjects whose tag contains "kitchen"
    python broll_pack.py fetch2           the second pass, several wordings for the thin subjects (PACK2)
    python broll_pack.py sheets           contact sheets (only clips not yet accepted or rejected) of the candidates to look at (library/broll/review/*.png)
    python broll_pack.py accept           put every candidate that is not in library/broll/rejected.json into curated.json under its tag
    python broll_pack.py reject 123 456   mark clip ids as not good enough (never used, kept on disk)

Same rules as broll.py. Pixabay (free for commercial use, no credit needed), the key saved in the app, a polite pause between requests and a limited
number of clips per subject. Clips are cut to 720 x 1280 (the older library is 540 x 960) so a full screen shot is not soft.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import broll
import projects

PER_TAG = 2
SIZE = (720, 1280)
CAND = broll.BROLL_DIR / "candidates.json"
REJ = broll.BROLL_DIR / "rejected.json"
REVIEW = broll.BROLL_DIR / "review"

# tag -> search words. A tag is what a script writes in [broll tag] and what the planner asks for. Several clips can share a tag.
PACK = {
    # property and building
    "apartment": "apartment building exterior", "hallway": "apartment building hallway", "keys": "hand holding house keys", "for sale": "house for sale sign",
    "construction": "construction site workers", "roofer": "roofer repairing roof", "plumbing": "plumber fixing sink", "painting": "painting a wall roller",
    "empty room": "empty apartment room", "moving": "moving boxes new home", "lease": "signing a lease agreement", "landlord": "landlord tenant handing keys",
    "kitchen": "modern kitchen interior", "chef": "restaurant kitchen chef working", "cooking": "chef cooking flames pan", "neighborhood": "suburban neighborhood aerial",
    "office": "glass office building", "skyscraper": "skyscraper looking up", "mobile home": "mobile home park aerial", "townhouse": "row of townhouses street",
    # money
    "cash": "counting cash money", "coins": "coins falling table", "bills": "paying bills at desk", "savings": "piggy bank savings", "card": "credit card payment",
    "chart": "stock market chart screen", "invoice": "invoice documents desk", "atm": "withdrawing money atm",
    # work and life
    "commute": "commuter train morning", "alarm": "alarm clock morning", "tired": "tired employee office night", "burnout": "stressed man head in hands desk",
    "laptop work": "typing on laptop coffee shop", "video call": "video call meeting laptop", "scrolling": "scrolling phone", "notes": "writing notes notebook",
    "whiteboard": "whiteboard planning team", "sunrise": "sunrise over city", "climb": "hiking mountain climb", "run": "running outdoors sunrise", "stairs": "climbing stairs",
    "family": "family dinner table", "kids": "kids playing park", "doctor": "doctor hospital corridor", "heartbeat": "heart monitor hospital", "gym": "gym workout weights",
    "travel": "airport travel walking", "leisure": "relaxing lake boat", "phone call": "business phone call", "email": "reading email laptop",
    "negotiate": "business negotiation table", "crowd walk": "people walking busy city street", "traffic": "city traffic aerial", "rain window": "rain on window", "door light": "opening door light",
}


# the second pass, for the subjects the first one left thin or wrong (a keyword search of free footage is hit and miss, so each subject gets several wordings)
PACK2 = {
    "keys": ["house keys door lock", "real estate agent giving keys", "key in lock door"],
    "landlord": ["tenant renting apartment", "couple moving into apartment", "real estate agent showing house"],
    "chef": ["chef in restaurant kitchen", "cook chopping vegetables kitchen", "restaurant kitchen busy service"],
    "burnout": ["stressed businessman", "tired man rubbing eyes", "overwhelmed worker desk papers"],
    "plumbing": ["plumber at work", "repairman fixing pipe"],
    "moving": ["packing cardboard boxes", "carrying boxes new apartment"],
    "negotiate": ["business handshake", "two businessmen discussing contract", "business meeting table"],
    "whiteboard": ["brainstorming sticky notes", "team planning whiteboard", "writing on whiteboard"],
    "mobile home": ["trailer home", "manufactured home exterior", "small town houses aerial"],
    "video call": ["video conference laptop", "remote work video call"],
    "scrolling": ["scrolling smartphone social media", "hand using smartphone"],
    "run": ["jogging morning", "running sunrise silhouette"],
    "card": ["paying with credit card", "shopping payment card terminal"],
    "atm": ["atm machine", "cash withdrawal atm"],
    "invoice": ["accounting calculator papers", "reviewing financial documents"],
    "email": ["typing email laptop", "checking email phone"],
    "kids": ["children playing outdoors", "family with kids home"],
    "family": ["family walking park", "family home living room"],
    "apartment": ["apartment complex exterior", "modern apartment building", "apartment building drone"],
    "lease": ["signing contract pen", "real estate contract signing"],
    "contract": ["signing documents pen", "lawyer contract desk"],
    "repairs": ["home repair handyman", "fixing leak pipe"],
    "calculator": ["calculator budget", "using calculator desk"],
    "clock": ["clock ticking close", "time passing clock"],
    "chart": ["stock chart rising", "financial graph screen"],
    "coins": ["coins stack", "money coins close up"],
    "empty house": ["empty house interior", "empty living room"],
    "start": ["road ahead", "sunrise road trip"],
}


def _load(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(p, d):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=1), encoding="utf-8")


def _rendition(hit):
    """The best download of a clip that is HD (short side 1080 or more), else None. Returns (url, width, height, bytes)."""
    v = hit.get("videos") or {}
    for key in ("medium", "large"):
        r = v.get(key) or {}
        if r.get("url") and min(r.get("width", 0), r.get("height", 0)) >= 1080:
            return r["url"], r["width"], r["height"], r.get("size", 0)
    return None


def candidates(query, n=PER_TAG):
    out = []
    for h in broll.search(query, per_page=30):
        rend = _rendition(h)
        if not rend or not (5 <= h.get("duration", 0) <= 45):
            continue
        if broll.BAD_TAGS.search(h.get("tags", "")) or h.get("isAiGenerated") or h.get("isLowQuality"):
            continue
        out.append((rend[2] > rend[1], h, rend))             # vertical first
    out.sort(key=lambda x: not x[0])
    return out[:n]


def prepare_hq(cid, src, start):
    out = broll.FRAMES / str(cid)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.jpg"):
        old.unlink()
    vf = "fps=%d,crop='min(iw,ih*9/16)':'min(ih,iw*16/9)',scale=%d:%d:flags=lanczos" % (broll.FPS, SIZE[0], SIZE[1])
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(start), "-i", str(src), "-t", str(broll.LOOP_S), "-vf", vf, "-q:v", "3",
                        "-start_number", "0", str(out / "%05d.jpg")], capture_output=True, text=True)
    if r.returncode != 0 or not (out / "00000.jpg").exists():
        raise RuntimeError(r.stderr[-200:])


def fetch(only=None):
    cand, meta = _load(CAND), broll._meta()
    for tag, query in PACK.items():
        if only and only not in tag:
            continue
        if sum(1 for c in cand.values() if c["tag"] == tag) >= PER_TAG:
            continue
        try:
            picks = candidates(query)
        except Exception as exc:
            print("  search failed for", tag, str(exc)[:100], flush=True)
            time.sleep(5)
            continue
        got = 0
        for vertical, h, (url, w, hgt, size) in picks:
            cid = str(h["id"])
            if cid in cand:
                continue
            raw = broll.RAW / (cid + ".mp4")
            try:
                if not raw.exists():
                    broll.RAW.mkdir(parents=True, exist_ok=True)
                    raw.write_bytes(broll._get(url, timeout=180))
                dur = float(h.get("duration", 8))
                prepare_hq(cid, raw, max(0.0, min(dur - broll.LOOP_S - 0.2, dur * 0.25)))
            except Exception as exc:
                print("  clip", cid, "failed:", str(exc)[:100], flush=True)
                continue
            cand[cid] = {"tag": tag, "query": query, "w": w, "h": hgt, "vertical": vertical, "duration": h.get("duration"), "page": h.get("pageURL", ""), "tags": h.get("tags", "")}
            meta.setdefault(cid, {"queries": [], "tags": h.get("tags", ""), "user": h.get("user", ""), "page": h.get("pageURL", ""), "duration": h.get("duration")})
            got += 1
            _save(CAND, cand)
            broll._save_meta(meta)
        print("%-14s %d clip(s)  (%s)" % (tag, got, query), flush=True)
        time.sleep(1.5)


def fetch2(only=None, per_query=2):
    """The second pass: several wordings per subject (PACK2). Candidates are added to the same list and reviewed the same way."""
    cand, meta = _load(CAND), broll._meta()
    for tag, queries in PACK2.items():
        if only and only not in tag:
            continue
        for query in queries:
            try:
                picks = candidates(query, n=per_query + 2)
            except Exception as exc:
                print("  search failed for", query, str(exc)[:100], flush=True)
                time.sleep(5)
                continue
            got = 0
            for vertical, h, (url, w, hgt, size) in picks:
                cid = str(h["id"])
                if cid in cand or got >= per_query:
                    continue
                raw = broll.RAW / (cid + ".mp4")
                try:
                    if not raw.exists():
                        broll.RAW.mkdir(parents=True, exist_ok=True)
                        raw.write_bytes(broll._get(url, timeout=180))
                    dur = float(h.get("duration", 8))
                    prepare_hq(cid, raw, max(0.0, min(dur - broll.LOOP_S - 0.2, dur * 0.25)))
                except Exception as exc:
                    print("  clip", cid, "failed:", str(exc)[:100], flush=True)
                    continue
                cand[cid] = {"tag": tag, "query": query, "w": w, "h": hgt, "vertical": vertical, "duration": h.get("duration"), "page": h.get("pageURL", ""), "tags": h.get("tags", ""), "pass": 2}
                meta.setdefault(cid, {"queries": [], "tags": h.get("tags", ""), "user": h.get("user", ""), "page": h.get("pageURL", ""), "duration": h.get("duration")})
                got += 1
                _save(CAND, cand)
                broll._save_meta(meta)
            print("%-12s %d clip(s)  (%s)" % (tag, got, query), flush=True)
            time.sleep(1.5)


def sheets():
    from PIL import Image, ImageDraw
    cand = _load(CAND)
    rej = set(_load(REJ).get("ids", []))
    REVIEW.mkdir(parents=True, exist_ok=True)
    done = set(broll.curated())
    items = [(c["tag"], cid) for cid, c in sorted(cand.items(), key=lambda kv: (kv[1]["tag"], kv[0])) if cid not in rej and cid not in done]
    per, cols = 24, 8
    for s in range(0, len(items), per):
        chunk = items[s:s + per]
        tw, th = 180, 320
        rows = -(-len(chunk) // cols)
        sh = Image.new("RGB", (cols * (tw + 4), rows * (th + 4)), (24, 24, 24))
        for i, (tag, cid) in enumerate(chunk):
            n = broll.frame_count(cid)
            im = Image.open(broll.FRAMES / cid / ("%05d.jpg" % (n // 2))).convert("RGB").resize((tw, th))
            d = ImageDraw.Draw(im)
            d.rectangle((0, 0, tw, 24), fill=(0, 0, 0))
            d.text((4, 4), "%s %s" % (tag, cid), fill=(255, 255, 255))
            sh.paste(im, ((i % cols) * (tw + 4), (i // cols) * (th + 4)))
        p = REVIEW / ("sheet_%02d.png" % (s // per + 1))
        sh.save(p)
        print(p)


def accept():
    cand = _load(CAND)
    rej = set(_load(REJ).get("ids", []))
    cur = broll.curated()
    n = 0
    for cid, c in cand.items():
        if cid in rej:
            continue
        tags = cur.setdefault(cid, [])
        if c["tag"] not in tags:
            tags.append(c["tag"])
            n += 1
    (broll.BROLL_DIR / "curated.json").write_text(json.dumps(cur, indent=1), encoding="utf-8")
    print("curated.json now has %d clips (%d tags added)" % (len(cur), n))


def reject(ids):
    d = _load(REJ)
    d["ids"] = sorted(set(d.get("ids", [])) | set(str(i) for i in ids))
    _save(REJ, d)
    print("rejected", d["ids"])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "fetch"
    if cmd == "fetch":
        fetch(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "fetch2":
        fetch2(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "sheets":
        sheets()
    elif cmd == "accept":
        accept()
    elif cmd == "reject":
        reject(sys.argv[2:])
    else:
        print(__doc__)
