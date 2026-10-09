"""script_story.py - turn a pasted script into a story the renderers can draw.

A project made from a script (projects/<name>/script.txt) is converted once into projects/<name>/story.json:

    hook   the first line, spoken as the intro            clips  [{id, name, narration}]   (3 beats each)
    beats  {clip id: [beat, beat, beat]}                 outro  closing words

Every beat is one phrase of the narration plus how to draw it:

    statement   a headline (the phrase, wrapped, key words in the accent colour) + a hero icon + keyword chips
    quote       "lead-in:" as the headline and the quoted words on a quote card (negative quotes get struck out)
    list        a short lead-in and a numbered list of items that appear as they are spoken

The renderers (story_adi.py, story_dan.py) only read this file, so it can also be edited by hand.
"""
import json
import re

import projects

MAX_WORDS_BEAT = 14
ICON_RULES = [        # (pattern, icon) - the first match wins; icons are the adi icon names
    (r"\b(retire|retired|retiring|retirement|vacation|holiday)\b", "palm"),
    (r"\b(money|income|paycheck|salary|cash|dollar|dollars|millions?|rich|wealth|profit|earn|earning|afford|cost|price|pay|paid|funds?)\b", "coin"),
    (r"\b(real estate|building|buildings|property|properties|commercial|asset|assets|tenant|landlord|rent|mortgage)\b", "bldg"),
    (r"\b(house|home|apartment)\b", "house"),
    (r"\b(hours?|time|clock|ceiling|deadline|schedule|day|days|years?|hustle|work|working|job|jobs)\b", "clock"),
    (r"\b(raise|grow|growth|increase|more|bigger|scale|income stops)\b", "bars"),
    (r"\b(stuck|trapped|stops?|limit|lock|cage|prison)\b", "padlock"),
    (r"\b(free|freedom|independence)\b", "sun"),
    (r"\b(investors?|lenders?|partners?|operators?|everyone|people|team|together|deal|deals|ask|question|think|conversation|talk|say|learn)\b", "bubble"),
    (r"\b(idea|better|learn|understand|start|starting|begin)\b", "bulb"),
    (r"\b(own|owning|owner|keys?)\b", "key"),
    (r"\b(bank|account|savings|wallet|budget)\b", "wallet"),
    (r"\b(grow|sprout|seed|future|passive)\b", "sprout"),
    (r"\b(warning|risk|never|ceiling|problem|uncomfortable)\b", "warning"),
]
FALLBACK_ICONS = ["bulb", "bars", "key", "sprout", "coin", "bldg", "clock", "bubble"]
STOP = set("""a an the and or but if so to of in on at for with from by as is are was were be been being it its it's that this these those
i i'm i'd i've you you're you'd you've your yours we we're our us they they're them their he she his her not no just more most very can
could would should may might will do does did don't doesn't didn't have has had how what why when where who which there here than then
because maybe even also only some any all one two out up down over into about like get got""".split())
CONJ_START = ("but", "and", "because", "so", "that's", "if", "they", "i", "now", "then", "when", "what", "how")


# ------------------------------------------------------------------ cleaning
def clean_line(s):
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[*_`#>]+", "", s).strip()
    s = s.replace("\u2026", "...").replace("\u2794", "\u2192")
    if s.count("\u2192") >= 2:
        s = re.sub(r"\s*\u2192\s*", ", ", s).rstrip(", ").strip() + ("," if s.rstrip().endswith("\u2192") else "")
    s = s.replace("\u2192", " to ")
    s = re.sub(r"(\d)\s*[\u2013\u2014-]\s*(\d)", r"\1 to \2", s)              # 9-5, 2020-2024 are read as "9 to 5"
    s = re.sub(r"^[-•]\s+", "", s)
    s = s.replace("&", " and ").replace("%", " percent").replace("—", ", ").replace("–", ", ")
    return re.sub(r"\s+", " ", s).strip()


def no_colons(s):
    """House rule: no colon and no semicolon in anything spoken or shown. A colon ends the sentence, a semicolon becomes a comma
    (times and ratios like 5:30 are left alone). Lines that END in a colon are still read as lead-ins before this runs."""
    s = re.sub(r"(?<=\d):(?=\d)", "\x00", s)
    s = re.sub(r"\s*:\s*$", ".", s)
    s = re.sub(r"\s*;\s*", ", ", s)
    s = re.sub(r":\s+(?=[A-Z\"'])", ". ", s)
    s = re.sub(r"\s*:\s*", ", ", s)
    return s.replace("\x00", ":")


def narration_text(s):
    """What is spoken: no quote marks, hyphens read as two words (the timing words must match the script's words), no colons or semicolons."""
    return re.sub(r"\s+", " ", no_colons(s.replace('"', "").replace("-", " "))).strip()


def is_quote(s):
    return len(s) > 2 and s[0] == '"' and s[-1] == '"'


def words(s):
    return [w for w in s.split() if re.sub(r"[^A-Za-z0-9]", "", w)]


def sentence_split(line):
    return [p.strip() for p in re.split(r"(?<=[.!?])\s+", line) if p.strip()]


# ------------------------------------------------------------------ units
CLAUSE = {"to", "in", "when", "that", "because", "and", "but", "with", "for", "so", "where", "which", "if", "as", "than", "into", "about"}


WEAK_END = {"a", "an", "the", "of", "to", "in", "on", "for", "with", "and", "or", "but", "my", "your", "our", "their", "its", "that", "this", "real",
            "commercial", "deal", "how", "what", "some", "any", "every", "no", "not", "so", "as", "at", "by", "than", "into", "about", "per", "one",
            "two", "three", "very", "more", "most", "just", "also", "only", "even"}


def split_clauses(text, max_words=9, min_words=3):
    """Cut a long sentence at its natural breaks (after a comma, before a connecting word) until the pieces are short."""
    ws = text.split()
    if len(ws) <= max_words:
        return [text]
    best, best_score = None, None
    for k in range(min_words, len(ws) - min_words + 1):
        score = abs(k - len(ws) / 2.0)
        if ws[k - 1].endswith((",", ";", ":")):
            score -= 3
        elif ws[k].lower().strip(",") in CLAUSE:
            score -= 1.5
        if not ws[k - 1].endswith((",", ";", ":", ".")) and ws[k - 1].lower() in WEAK_END:
            score += 3                                                   # a piece must not end on "the", "to", "real" ...
        if ws[k].lower().strip(".,") in ("million", "billion", "thousand", "percent", "estate"):
            score += 6                                                   # "$3 | million" and "real | estate" stay together
        if best_score is None or score < best_score:
            best, best_score = k, score
    if best is None:
        return [text]
    return split_clauses(" ".join(ws[:best]), max_words, min_words) + split_clauses(" ".join(ws[best:]), max_words, min_words)


def to_units(lines):
    """Statement lines, plus the special blocks that need their own drawing (quote, list)."""
    units, i = [], 0
    while i < len(lines):
        l = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        # lead-in with a colon followed by a quote
        if l.endswith(":") and not is_quote(l) and nxt and is_quote(nxt):
            units.append({"kind": "quote", "lead": narration_text(l), "text": narration_text(l + " " + nxt), "quote": narration_text(nxt)})
            i += 2
            continue
        # lead-in with a colon followed by short lines -> the lead-in is a statement, the lines are a list
        if l.endswith(":") and not is_quote(l):
            items, j = [], i + 1
            while j < len(lines) and not is_quote(lines[j]) and not lines[j].lower().startswith(CONJ_START) and not lines[j].endswith(":") and not lines[j].endswith("..."):
                n = len(words(lines[j]))
                # a longer line still belongs to the list when it is parallel to its neighbour ("The ability to ..." twice)
                head2 = [w.lower() for w in lines[j].split()[:2]]
                parallel = (j + 1 < len(lines) and [w.lower() for w in lines[j + 1].split()[:2]] == head2) or bool(items and [w.lower() for w in items[-1].split()[:2]] == head2)
                import story_scenes
                verb = bool(re.match(story_scenes.VERBS, lines[j].lower().strip())) and len(sentence_split(lines[j])) == 1
                if not (n <= 5 or (n <= 8 and verb) or (n <= 10 and parallel and len(sentence_split(lines[j])) == 1 and "," not in lines[j])):
                    break
                items.append(lines[j]); j += 1
            if len(items) >= 2:
                lead_text = narration_text(l)
                if len(items) >= 4 and len(words(items[0])) <= 2:          # "...something your salary can't:" / "options." - the payoff word belongs to the sentence
                    lead_text = narration_text(l + " " + items[0])
                    items = items[1:]
                for m in split_clauses(lead_text):
                    units.append({"kind": "statement", "text": m})
                units.append({"kind": "list", "lead": "", "items": [narration_text(x).rstrip(".!?") for x in items], "text": narration_text(" ".join(items))})
                i = j
                continue
        if is_quote(l):
            units.append({"kind": "quote", "lead": "", "text": narration_text(l), "quote": narration_text(l)})
            i += 1
            continue
        # a short lead-in followed by a run of one- or two-word lines ("There can be investors." Lenders. Partners. Operators.)
        j = i + 1
        while j < len(lines) and len(words(lines[j])) <= 2 and not is_quote(lines[j]):
            j += 1
        if j - (i + 1) >= 3 and len(words(l)) <= 5 and not l.endswith(":"):
            wl = words(l)
            first = wl[-1].rstrip(".!?,:;")
            lead = " ".join(wl[:-1])
            items = [first] + [narration_text(x).rstrip(".!?") for x in lines[i + 1:j]]
            units.append({"kind": "list", "lead": narration_text(lead), "items": items, "text": narration_text(" ".join(lines[i:j]))})
            i = j
            continue
        # a full sentence followed by a run of short lines ("I'm talking about commercial real estate." / Apartment buildings. / Retail. ...):
        # the sentence stays a sentence, the short lines are the list
        j = i + 1
        while (j < len(lines) and len(words(lines[j])) <= 3 and not is_quote(lines[j]) and not lines[j].endswith(":")
               and not lines[j].rstrip().endswith(",") and lines[j].strip().lower().rstrip(".") not in ("to", "and", "or", "but", "then", "into")):
            j += 1                                    # (a fragment that trails off, or a bare joining word, is not a list item)
        if j - (i + 1) >= 3 and len(words(l)) > 5 and not l.endswith(":") and not is_quote(l):
            for m in split_clauses(narration_text(l)):
                units.append({"kind": "statement", "text": m})
            items = [narration_text(x).rstrip(".!?") for x in lines[i + 1:j]]
            units.append({"kind": "list", "lead": "", "items": items, "text": narration_text(" ".join(lines[i + 1:j]))})
            i = j
            continue
        # three or more short lines that each start with a verb (Learn how investing works. / Study real estate. / Build ...) are steps
        import story_scenes
        j = i
        while (j < len(lines) and 2 <= len(words(lines[j])) <= 7 and not is_quote(lines[j]) and not lines[j].endswith(":")
               and not lines[j].endswith("...") and re.match(story_scenes.VERBS, lines[j].lower().strip()) and len(sentence_split(lines[j])) == 1):
            j += 1
        if j - i >= 3:
            units.append({"kind": "list", "lead": "", "items": [narration_text(x).rstrip(".!?") for x in lines[i:j]], "text": narration_text(" ".join(lines[i:j]))})
            i = j
            continue
        # three or more parallel questions-in-disguise ("How they're financed." / "How investors make money." / ...) are a list
        first = l.split()[0].lower() if l.split() else ""
        if first in ("how", "what", "why", "when", "where", "who"):
            j = i
            while (j < len(lines) and lines[j].split() and lines[j].split()[0].lower() == first and 3 <= len(words(lines[j])) <= 10
                   and not is_quote(lines[j]) and len(sentence_split(lines[j])) == 1 and not lines[j].endswith((":", "..."))):
                j += 1
            if j - i >= 3:
                units.append({"kind": "list", "lead": "", "items": [narration_text(x).rstrip(".!?") for x in lines[i:j]], "text": narration_text(" ".join(lines[i:j]))})
                i = j
                continue
        # a normal line; very long ones are split at a comma so they can become separate beats
        whole = narration_text(l)
        if story_scenes.verb_triple(whole) and len(words(whole)) <= 16:       # "bring value, understand risk, earn trust" stays in ONE beat (three ticked rows)
            units.append({"kind": "statement", "text": whole, "solo": True})
        else:
            for m in split_clauses(whole):
                units.append({"kind": "statement", "text": m})
        i += 1
    return units


# ------------------------------------------------------------------ beats
def group_statements(run, k):
    """Split a run of statement units into k groups with balanced word counts (dynamic programming)."""
    n = len(run)
    k = max(1, min(k, n))
    w = [len(words(u["text"])) for u in run]
    pre = [0]
    for x in w:
        pre.append(pre[-1] + x)
    target = pre[-1] / k
    INF = float("inf")
    best = [[INF] * (n + 1) for _ in range(k + 1)]
    cut = [[0] * (n + 1) for _ in range(k + 1)]
    best[0][0] = 0
    for g in range(1, k + 1):
        for i in range(g, n + 1):
            for j in range(g - 1, i):
                if best[g - 1][j] == INF:
                    continue
                size = pre[i] - pre[j]
                cost = best[g - 1][j] + (size - target) ** 2 + (60 if size > MAX_WORDS_BEAT + 2 else 0)
                if cost < best[g][i]:
                    best[g][i], cut[g][i] = cost, j
    groups, i = [], n
    for g in range(k, 0, -1):
        j = cut[g][i]
        groups.append(run[j:i])
        i = j
    return [{"kind": "statement", "text": " ".join(u["text"] for u in grp)} for grp in reversed(groups)]


def make_beats(units):
    total = sum(len(words(u["text"])) for u in units)
    special = sum(1 for u in units if u["kind"] != "statement" or u.get("solo"))
    runs, cur = [], []                     # runs of consecutive statements, with the specials between them
    seq = []
    for u in units:
        if u["kind"] == "statement" and not u.get("solo"):
            cur.append(u)
        else:
            if cur:
                seq.append(("run", cur)); cur = []
            seq.append(("one", u))
    if cur:
        seq.append(("run", cur))
    nruns = sum(1 for k, _ in seq if k == "run")
    max_beats = special + sum(len(r) for k, r in seq if k == "run")
    want = max(3, int(round(total / 8.0 / 3.0)) * 3)
    want = max(want, special + nruns)
    want = min(want, max_beats)
    if want % 3:                           # three beats per clip: round to the nearest feasible multiple of three
        lo, hi = want - want % 3, want + (3 - want % 3)
        want = hi if hi <= max_beats and (want - lo >= 2 or lo < special + nruns) else (lo if lo >= max(3, special + nruns) else min(hi, max_beats))
    # words of every run decide how many groups it gets
    run_words = [sum(len(words(u["text"])) for u in r) for k, r in seq if k == "run"]
    spare = want - special
    alloc = [1] * nruns
    left = spare - nruns
    while left > 0:
        i = max(range(nruns), key=lambda x: run_words[x] / alloc[x] if alloc[x] < len(seq_run(seq, x)) else -1)
        if alloc[i] >= len(seq_run(seq, i)):
            break
        alloc[i] += 1
        left -= 1
    beats, ri = [], 0
    for kind, item in seq:
        if kind == "one":
            beats.append(dict(item))
        else:
            beats.extend(group_statements(item, alloc[ri])); ri += 1
    return beats


def seq_run(seq, n):
    return [r for k, r in seq if k == "run"][n]


# ------------------------------------------------------------------ how a beat is drawn
def pick_icon(text, i=0):
    low = text.lower()
    for pat, icon in ICON_RULES:
        if re.search(pat, low):
            return icon
    return FALLBACK_ICONS[i % len(FALLBACK_ICONS)]


def keywords(text, n=3):
    """[(word, icon)] for the words of the beat that mean something drawable (money, hours, building, ...)."""
    out, seen = [], set()
    for w in re.findall(r"[A-Za-z']+", text):
        lw = w.lower()
        if lw in STOP or len(lw) < 4 or lw in seen:
            continue
        for pat, icon in ICON_RULES:
            if re.search(pat, lw):
                out.append([w, icon]); seen.add(lw)
                break
    return out[:n]


def wrap_lines(text, width=18):
    """Break a headline into lines; "9 to 5" and "$150,000 a year" style groups stay on one line."""
    glue = "\ue000"
    text = re.sub(r"(\d) to (\d)", lambda m: m.group(1) + glue + "to" + glue + m.group(2), text)
    ws = text.split()
    lines, cur = [], ""
    for w in ws:
        if cur and len(cur.replace(glue, " ")) + 1 + len(w.replace(glue, " ")) > width:
            lines.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return [l.replace(glue, " ") for l in lines]


def headline_px(n_lines):
    return {1: 132, 2: 124, 3: 112, 4: 98, 5: 86}.get(n_lines, 76)


def describe(beat, idx):
    """Everything the drawers need for one beat."""
    kind, text = beat["kind"], beat["text"]
    d = {"kind": kind, "text": text}
    low = text.lower()
    neg = bool(re.search(r"\b(don't|can't|cannot|not|never|no|won't|isn't|aren't|nothing)\b", low))
    if kind == "quote":
        lead = beat.get("lead", "")
        quote = beat["quote"]
        wrong = (bool(re.search(r"\b(don't|can't|cannot|not|never|won't|nothing|quit|hate|give up|stuck)\b", quote.lower())) or lead.lower().startswith("not")
                 or bool(re.search(r"(different from|instead of|rather than|unlike|opposite of)", lead.lower())))
        d.update(lead=lead, quote=quote, qlines=wrap_lines(quote, 24), neg=wrong,
                 icon="bubble", head=wrap_lines(lead.rstrip(":").lower(), 18) if lead else wrap_lines(quote, 16))
        d["px"] = headline_px(len(d["head"]))
        d["accent"] = 0
    elif kind == "list":
        lead = beat.get("lead", "")
        items = beat["items"]
        recap = " ".join(beat.get("recap", "").split()[-4:])
        d.update(lead=lead, items=items, icons=[pick_icon(x, idx + k) for k, x in enumerate(items)],
                 head=wrap_lines(lead.lower().rstrip(":") if lead else (re.sub(r"[.!?:,;]+$", "", recap.lower().strip()) if recap else ""), 18), icon=pick_icon(text, idx))
        d["px"] = headline_px(max(1, len(d["head"])))
    else:
        lines = wrap_lines(text.lower() if False else text, 18)
        n_acc = 2 if len(words(text)) > 5 else 1
        d.update(head=lines, px=headline_px(len(lines)), accent=n_acc, icon=pick_icon(text, idx), chips=keywords(text, 3))
    d["neg"] = d.get("neg", False)
    if beat.get("calc"):
        d["calc"] = list(beat["calc"])
    return d


# ------------------------------------------------------------------ the whole story
def _value_token(calc):
    """The digits of the answer of a calculation ("$4,000 a month" -> "4000"), used to find the beat that says it."""
    c = calc.strip()
    if c.lower().startswith("stack "):
        body, show = c[5:], None
        if "|" in body:
            body, opt = body.split("|", 1)
            m = re.search(r"show\s+(\d+)", opt)
            show = int(m.group(1)) if m else None
        parts = re.split(r"\s+\+\s+", body.split("=", 1)[-1].strip())
        c = parts[min(len(parts), show or len(parts)) - 1]
    else:
        c = c.split("=")[-1]
    m = re.search(r"\d[\d,]*(?:\.\d+)?", c)
    return re.sub(r"[^0-9]", "", m.group(0)) if m else ""


def _outro_phrase(last):
    """The closing words shown on the last frame - what the script heads toward ("building wealth"), not its last five words."""
    tail = " ".join(last[-14:]).strip(" ,.:;?!")
    m = re.search(r"\b(?:toward|towards)\s+(.+)$", tail, re.I)
    phrase = m.group(1) if m else " ".join(last[-5:])
    phrase = re.sub(r"\s+(?:through|with|from|by|in|for|of|to)\s+(?:them|it|that|this|these|those|you|me|us)$", "", phrase, flags=re.I)
    phrase = re.sub(r"\s+(?:them|it|that|this)$", "", phrase, flags=re.I)
    return phrase.strip(" ,.:;?!")


def build(text):
    # a line in square brackets is a calculation to SHOW (not to say): "[$100 x 40 units = $4,000 a month]" belongs to the line above it
    lines, calcs = [], []
    for raw in text.splitlines():
        m = re.match(r"^\s*\[(.+)\]\s*$", raw)
        if m:
            if lines:
                calcs.append((lines[-1], m.group(1).strip()))
            continue
        c = clean_line(raw)
        if c:
            lines.append(c)
    if len(lines) < 4 and len(sentence_split(" ".join(lines))) >= 4:      # one paragraph: every sentence is a line
        lines = sentence_split(" ".join(lines))
    if not lines:
        raise ValueError("the script is empty")
    hook_line = lines[0]
    if len(words(hook_line)) > 26:
        sents = sentence_split(hook_line)
        hook_line, rest = sents[0], " ".join(sents[1:])
        lines = [hook_line] + ([rest] if rest else []) + lines[1:]
    hook = narration_text(hook_line)
    units = to_units(lines[1:])
    if sum(len(words(u["text"])) for u in units) < 12:
        raise ValueError("the script is too short - it needs a few sentences after the first line")
    beats = make_beats(units)
    for k, b in enumerate(beats):
        if b["kind"] == "list" and not b.get("lead") and k > 0:
            b["recap"] = beats[k - 1]["text"]
    # every clip has exactly three beats: pad with a tiny repeat-free split if needed
    while len(beats) % 3:
        i = max(range(len(beats)), key=lambda x: len(words(beats[x]["text"])) if beats[x]["kind"] == "statement" else -1)
        b = beats[i]
        ws = b["text"].split()
        if b["kind"] != "statement" or len(ws) < 4:
            break
        h = len(ws) // 2
        beats[i:i + 1] = [{"kind": "statement", "text": " ".join(ws[:h])}, {"kind": "statement", "text": " ".join(ws[h:])}]
    def _norm(s):
        return re.findall(r"[a-z0-9]+", s.lower())
    def _has(bt, toks):
        return bool(toks) and any(bt[i:i + len(toks)] == toks for i in range(len(bt) - len(toks) + 1))
    pos = 0
    for anchor, calc in calcs:                      # each calculation goes to the beat of the line above it that SAYS its answer
        atoks = _norm(narration_text(anchor))
        start = next((k for k in range(pos, len(beats)) if _has(_norm(beats[k]["text"]), atoks[:5])), None)
        end = next((k for k in range(pos, len(beats)) if _has(_norm(beats[k]["text"]), atoks[-5:])), None)
        if end is None and start is None:
            continue
        start = end if start is None else start
        end = start if end is None or end < start else end
        vt = _value_token(calc)
        pick = next((k for k in range(start, end + 1) if vt and vt in [re.sub(r"[^a-z0-9]", "", w.lower()) for w in beats[k]["text"].split()]), end)
        beats[pick].setdefault("calc", []).append(calc)
        pos = pick
    clips, beat_map, feats = [], {}, {}
    for c in range(0, len(beats) - len(beats) % 3, 3):
        cid = c // 3 + 1
        trio = beats[c:c + 3]
        name = " ".join(w[:1].upper() + w[1:] for w in trio[0]["text"].split()[:4]).strip(" ,.:;?!")
        clips.append({"id": cid, "name": name, "narration": " ".join(b["text"] for b in trio)})
        beat_map[str(cid)] = [b["text"] for b in trio]
        feats[str(cid)] = [describe(b, c + k) for k, b in enumerate(trio)]
    hw = hook.split()
    half = len(hw) // 2
    found = False
    for k in range(max(2, half - 3), min(len(hw) - 2, half + 4)):          # split the hook at a comma if there is one near the middle
        if hw[k - 1].endswith((",", ":", ";")):
            half, found = k, True
            break
    if not found:                                                         # else before a joining word ("... without having $10 million")
        for k in range(max(2, half - 3), min(len(hw) - 2, half + 5)):
            if hw[k].lower() in ("without", "while", "because", "but", "and", "so", "when", "if", "that", "which", "than", "before", "after", "until"):
                half = k
                break
    if half < len(hw) and hw[half].lower().strip(".,") in ("million", "billion", "thousand", "percent"):
        half += 1                                                         # "$10 | million" stays together
    while half > 2 and hw[half - 1].lower().strip(",") in WEAK_END:
        half -= 1                                                         # the first part must not end on "the", "to", "a" ...
    last = clips[-1]["narration"].split()
    return {
        "hook": hook, "hook_split": half, "hook_icon": pick_icon(hook, 0), "hook_head": [" ".join(hw[:half]), " ".join(hw[half:])],
        "clips": clips, "beats": beat_map, "feats": feats,
        "outro": {"lines": wrap_lines(_outro_phrase(last), 14), "icon": pick_icon(" ".join(last[-12:]), 3)},
    }


# ------------------------------------------------------------------ files
def script_path(project=None):
    return projects.project_dir(project) / "script.txt"


def story_path(project=None):
    return projects.project_dir(project) / "story.json"


def has_script(project=None):
    return script_path(project).exists()


def save_script(text, project=None):
    """Store the script and (re)build the story from it. Raises ValueError if the script cannot be used."""
    story = build(text)
    script_path(project).parent.mkdir(parents=True, exist_ok=True)
    script_path(project).write_text(text, encoding="utf-8")
    story_path(project).write_text(json.dumps(story, indent=1, ensure_ascii=False), encoding="utf-8")
    return story


def load(project=None):
    """The story of a project made from a script, or None for the built-in demo story."""
    p = story_path(project)
    if not script_path(project).exists():
        return None
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return save_script(script_path(project).read_text(encoding="utf-8"), project)
    except Exception:
        return None


if __name__ == "__main__":      # python script_story.py script.txt  -> shows how the script is split
    import sys
    st = build(open(sys.argv[1], encoding="utf-8").read())
    print("HOOK:", st["hook_head"], st["hook_icon"])
    for c in st["clips"]:
        print(f"\nclip {c['id']}  {c['name']}")
        for b in st["feats"][str(c["id"])]:
            extra = b.get("items") or b.get("quote") or b.get("chips")
            print(f"   [{b['kind']:9}] {b['text']}   -> {b['head']} icon={b['icon']} {extra}")
    print("\nOUTRO:", st["outro"])
