"""story_scenes.py - the visual vocabulary of a script story, shared by the Adi and Dan styles.

A *scene* is a small drawn story for one beat (a protagonist who gets stuck under a ceiling, an income line that stops,
roles around a deal ...). `plan()` reads the beat's words and chooses a scene and fills it in (a plain dict, stored in the
story file); `draw()` paints it through a *backend* that each style provides, so both styles show the same idea:

    be.icon(name, x, y, size, trig)         be.figure(pose, x, y, height, trig, until=None)
    be.text(s, x, y, px, trig, color=)      be.line(points, trig, color=, w=, dur=)      be.arrow(p0, p1, trig)
    be.rect(x0, y0, x1, y1, trig, fill=, line=, until=)    be.circle(x, y, r, trig, fill=, line=)
    be.flow(p0, p1, trig)  (little coins travelling along a path)    be.check / be.cross(x, y, size, trig)

Scene coordinates live in a 1000 x 760 box, origin top-left; the backend maps the box into its page. `ctx.at(word, frac)`
is the second at which `word` is spoken in the beat (or `frac` of the way through it), `ctx.item(k)` the time of the
k-th spoken word. Colours are names: ink, accent, mute, neg, soft, white.
"""
import math
import re

W, H = 1000, 760

# keyword -> icon (the first match wins; specific before general). Icon names are those of story_icons.ICONS.
RULES = [
    (r"\b(ceiling|cap|limit|limits|stuck|plateau)\b", "ladder"),
    (r"\b(investors?|lenders?|partners?|operators?|everyone|people|someone|team|clients?|customers?|friends|family|buyers?|sellers?|tenants?|owners?|founders?|employees?|mentors?|managers?)\b", "person"),
    (r"\b(deal|deals|agreement|contract|terms|document|paperwork)\b", "scroll"),
    (r"\b(conversation|talk|talking|discuss|chat|tell|said|say|ask)\b", "chat"),
    (r"\b(question|why|wonder|think|thinks|thought|idea|ideas|better|understand|learn)\b", "bulb"),
    (r"\b(bank|banks|loan|loans|lender|credit|borrow|debt)\b", "bank"),
    (r"\b(real estate|building|buildings|property|properties|commercial|asset|assets|landlord|rent|mortgage|office|tower)\b", "bldg"),
    (r"\b(house|home|apartment)\b", "house"),
    (r"\b(millions?|million|rich|wealth|wealthy|fortune)\b", "coins"),
    (r"\b(money|income|paycheck|salary|cash|dollar|dollars|profit|earn|earning|earns|afford|cost|price|pay|paid|funds?)\b", "coin"),
    (r"\b(percent|rate|interest|yield|return|returns)\b", "percent"),
    (r"\b(hours?|time|clock|deadline|day|days|years?|minutes?|schedule|calendar|month|months)\b", "clock"),
    (r"\b(job|jobs|career|boss|work|working|worker|employer|hustle|side hustle|business|company)\b", "briefcase"),
    (r"\b(raise|grow|growth|increase|increases|bigger|higher|scale|compound|rise|rising|climb|promotion)\b", "bars"),
    (r"\b(decline|drop|fall|loss|lose|losing|shrink|less|cut|expenses|spend|spending)\b", "trend_down"),
    (r"\b(free|freedom|independence|dream|future|morning|hope)\b", "sun"),
    (r"\b(own|owning|owner|ownership|keys?|access|enter)\b", "key"),
    (r"\b(door|opportunity|opportunities|opens?)\b", "door"),
    (r"\b(goal|goals|target|aim|focus|plan)\b", "target"),
    (r"\b(system|systems|process|operations?|manage|managing|machine|automate)\b", "gear"),
    (r"\b(risk|risks|protect|safe|safety|insurance|secure|security)\b", "shield"),
    (r"\b(start|starting|begin|launch|launching|startup|first)\b", "rocket"),
    (r"\b(share|shares|split|equity|portion|slice|stake)\b", "pie"),
    (r"\b(save|saving|savings|stack|accumulate|wallet|budget|account)\b", "wallet"),
    (r"\b(buy|buying|shop|shopping|purchase|bought|spent)\b", "cart"),
    (r"\b(online|laptop|remote|computer|digital|website)\b", "laptop"),
    (r"\b(network|networking|connections|contacts|community)\b", "network"),
    (r"\b(repeat|cycle|loop|again|every|routine|forever)\b", "cycle"),
    (r"\b(grow|sprout|seed|passive|harvest)\b", "tree"),
    (r"\b(balance|weigh|fair|compare)\b", "scale"),
    (r"\b(announce|announcement|message|voice|marketing)\b", "megaphone"),
    (r"\b(warning|problem|problems|uncomfortable|danger|never|can't|cannot|won't|don't)\b", "warning"),
    (r"\b(together|join|partnership|link|connected)\b", "link"),
    (r"\b(steps?|levels?|stairs|progress)\b", "stairs"),
]
FALLBACK_ICONS = ["bulb", "bars", "key", "sprout", "coin", "bldg", "clock", "chat"]

PEOPLE = r"(investors?|lenders?|partners?|operators?|clients?|customers?|friends?|family|buyers?|sellers?|tenants?|owners?|founders?|employees?|mentors?|managers?|brokers?|advisors?|people|members?|donors?|backers?|sponsors?|lawyers?|agents?|builders?|developers?)"
VERBS = r"^(get|work|start|build|save|buy|sell|earn|invest|cut|stop|learn|ask|find|make|take|try|keep|put|use|open|plan|pay|apply|hire|ask|call|sign|join|read|write|set|grow|spend|track|check|list|pick|choose|look)\b"


def pick_icon(text, i=0):
    low = text.lower()
    for pat, icon in RULES:
        if re.search(pat, low):
            return icon
    return FALLBACK_ICONS[i % len(FALLBACK_ICONS)]


# ------------------------------------------------------------------ planning: which scene tells this beat?
def _short(s, n=14):
    s = re.sub(r"[^A-Za-z0-9' $%-]", "", s).strip()
    return s.upper() if len(s) <= n else s.upper()[:n].rsplit(" ", 1)[0]


def _center_for(text):
    low = text.lower()
    if re.search(r"deal|agreement|contract", low):
        return "scroll", "THE DEAL"
    if re.search(r"building|real estate|property|asset", low):
        return "bldg", "THE ASSET"
    if re.search(r"business|company|startup", low):
        return "briefcase", "THE BUSINESS"
    return "link", "TOGETHER"


def plan(beat, prev_text=""):
    """The scene for one beat: {"type": ..., ...} with everything the drawers need (words to wait for, labels, icons)."""
    kind, text = beat["kind"], beat["text"]
    low = text.lower()
    ctxlow = (prev_text + " " + low).lower()
    if kind == "list":
        items = beat["items"]
        lead = (beat.get("lead") or "").lower()
        ppl = sum(1 for it in items if re.fullmatch(r"\W*" + PEOPLE + r"\W*", it.lower().strip()))
        k, nodes = nwords(lead), []
        for it in items:
            nodes.append({"label": it, "k": k})
            k += nwords(it)
        if ppl >= max(2, int(len(items) * 0.6)):
            icon, label = _center_for(ctxlow)
            return {"type": "hub", "center": icon, "center_label": label,
                    "nodes": [{"label": _short(n["label"]), "icon": "person", "k": n["k"]} for n in nodes]}
        if sum(1 for it in items if re.match(VERBS, it.lower().strip())) >= max(2, len(items) // 2):
            return {"type": "steps", "nodes": [{"label": n["label"], "k": n["k"]} for n in nodes]}
        return {"type": "flow", "nodes": [{"icon": pick_icon(n["label"], i), "label": _short(n["label"]), "k": n["k"]} for i, n in enumerate(nodes[:4])]}
    if kind == "quote":
        neg = bool(beat.get("neg"))
        return {"type": "question", "neg": neg, "icon": pick_icon(beat["quote"], 0)}
    # statements, by what they say
    if re.search(r"(income|paycheck|pay|money|salary).{0,40}\b(stops?|ends?|dries|disappears)\b|\bstop working\b|\bwhen you stop\b", low):
        return {"type": "income_stop"}
    if re.search(r"\b(ceiling|plateau|cap|maxed)\b|\bthere'?s a limit\b", low):
        return {"type": "ceiling"}
    if re.search(r"run out of|out of (hours|time)|\bonly (so many|\d+) hours\b|\bhours\b.*\b(day|week)\b", low):
        return {"type": "hours"}
    if re.search(r"millions|bank account|savings|rich first|enough money|big money", low) and re.search(r"\b(don'?t|do not|no\b|without|sitting|need|have to|necessarily)\b", low):
        return {"type": "bank"}
    if re.search(r"\b(buying|buy|own|owning|invest|investing|income[- ]producing|asset|real estate|commercial|property)\b", low) and \
            re.search(r"\b(building|asset|estate|property|income|rental|producing|owning)\b", low):
        return {"type": "own"}
    if re.search(r"\bfreedom\b|\bindependence\b|\bfree to\b", low):
        return {"type": "freedom"}
    if re.search(r"\b(conversation|talking|discussion|start having|let'?s talk)\b", low):
        return {"type": "chat"}
    if re.search(r"everyone brings|each (one )?brings|something different|different to the", low):
        return {"type": "hub", "center": "link", "center_label": "THE DEAL", "mixed": True,
                "nodes": [{"label": "MONEY", "icon": "person", "item": "coin"}, {"label": "SKILLS", "icon": "person", "item": "gear"},
                          {"label": "TIME", "icon": "person", "item": "clock"}, {"label": "CONTACTS", "icon": "person", "item": "network"}]}
    if re.search(r"\b(never learn|never learn|nobody tells|nobody teaches|no one tells|never taught|never taught)\b", low):
        return {"type": "question", "neg": True, "icon": "question", "taught": True}
    if re.search(r"\b(grow|growth|increase|raise|rise|higher|bigger|compound|scale)\b", low):
        return {"type": "growth", "dir": "up"}
    if re.search(r"\b(decline|decrease|lose|losing|drop|shrink|fall|cut)\b", low):
        return {"type": "growth", "dir": "down"}
    kws = _kw_nodes(text)
    if re.search(r"\bbecause\b|\bso\b|\btherefore\b|which means|leads? to|\bthen\b", low) and len(kws) >= 2:
        return {"type": "flow", "nodes": kws[:3], "cause": True}
    pose = "shrug" if re.search(r"\b(can'?t|don'?t|never|not|no one|nothing|uncomfortable|problem)\b", low) else \
        "think" if re.search(r"\b(think|wonder|question|why|how|learn)\b", low) else "stand"
    return {"type": "pictogram", "pose": pose, "nodes": kws[:3] or [{"icon": pick_icon(text, 0), "label": "", "word": ""}]}


def nwords(s):
    return len([w for w in s.split() if re.sub(r"[^A-Za-z0-9]", "", w)])


def _kw_nodes(text):
    """Icon nodes for the drawable words of a sentence, in the order they are spoken."""
    out, seen = [], set()
    for w in re.findall(r"[A-Za-z']+", text):
        lw = w.lower()
        if len(lw) < 4 or lw in seen:
            continue
        for pat, icon in RULES:
            if re.search(pat, lw):
                if icon not in [o["icon"] for o in out]:
                    out.append({"icon": icon, "label": w.upper()[:12], "word": lw})
                seen.add(lw)
                break
    return out


# ------------------------------------------------------------------ drawing helpers
def _node(be, x, y, icon, label, trig, size=150, lpx=30, color="accent"):
    be.icon(icon, x, y, size, trig, dur=0.6)
    if label:
        be.text(label, x, y + size / 2 + 38, lpx, trig + 0.15)


def _wrap(s, n):
    ws, lines, cur = s.split(), [], ""
    for w in ws:
        if cur and len(cur) + 1 + len(w) > n:
            lines.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    return lines + ([cur] if cur else [])


# ------------------------------------------------------------------ the scenes
def s_pictogram(be, ctx, sp):
    nodes = sp["nodes"]
    n = len(nodes)
    if sp.get("fig"):
        be.figure(sp.get("pose", "stand"), 170, 400, 420, ctx.t0 + 0.05)
        xs = {1: [640], 2: [520, 800], 3: [450, 650, 850]}[min(3, max(1, n))]
        prev = (300, 400)
    else:                                                         # just the things the beat is about, in the order they are spoken
        xs = {1: [500], 2: [340, 660], 3: [190, 500, 810]}[min(3, max(1, n))]
        prev = None
    for node, x in zip(nodes, xs):
        tr = ctx.at(node.get("word"), 0.3 if prev is None and node is nodes[0] else 0.35)
        if prev:
            be.arrow((prev[0] + 10, 400), (x - 84, 400), tr - 0.1, color="mute")
        _node(be, x, 400, node["icon"], node.get("label", ""), tr, size=170 if n == 1 else 150)
        prev = (x + 70, 400)


def s_income_stop(be, ctx, sp):
    x0, y0, x1, y1 = 130, 120, 900, 600
    be.line([(x0, y0), (x0, y1), (x1, y1)], ctx.t0 + 0.05, color="ink", w=6, dur=0.5)
    be.text("INCOME", x0 + 10, y0 - 22, 28, ctx.t0 + 0.2, anchor="l", color="mute")
    stop = ctx.at("stops", 0.5)
    xs = 520
    be.line([(x0 + 10, 250), (xs, 250)], ctx.t0 + 0.2, color="accent", w=12, dur=max(0.5, stop - ctx.t0 - 0.2))
    be.icon("coin", x0 + 40, 215, 70, ctx.t0 + 0.25)
    be.text("YOU WORK", (x0 + xs) / 2, 330, 30, ctx.t0 + 0.7, color="mute")
    be.line([(xs, 250), (xs, y1 - 8)], stop, color="neg", w=12, dur=0.3)
    be.line([(xs, y1 - 8), (x1 - 10, y1 - 8)], stop + 0.3, color="neg", w=12, dur=0.7)
    be.cross(xs, y1 - 8, 28, stop + 0.2, color="neg")
    be.text("YOU STOP", xs + 150, 330, 30, stop + 0.1, color="neg")
    be.text("$0", (xs + x1) / 2 + 40, y1 - 60, 64, stop + 0.6, color="neg")


def s_steps(be, ctx, sp):
    nodes = sp["nodes"][:5]
    n = len(nodes)
    w = min(200, 880 // n)
    x0 = (W - n * w) / 2
    base = 650
    step_h = 92 if n > 3 else 108
    trig = [ctx.item(nd["k"]) for nd in nodes]
    be.line([(x0 - 20, base), (x0 + n * w + 20, base)], ctx.t0 + 0.05, color="ink", w=6, dur=0.4)
    for i, nd in enumerate(nodes):
        top = base - (i + 1) * step_h
        xa = x0 + i * w
        be.rect(xa, top, xa + w, base, trig[i], fill="soft", line="ink", w=4, r=6)
        for j, ln in enumerate(_wrap(nd["label"], max(7, int(w / getattr(be, "char_w", 17))))[:3]):
            be.text(ln, xa + w / 2, top + 34 + j * 34, 25, trig[i] + 0.1, color="ink")
        until = trig[i + 1] if i + 1 < n else None
        if sp.get("fig"):
            be.figure("climb" if i < n - 1 else "stand", xa + w / 2, top - 82, 150, trig[i] + 0.15, until=until)
        else:                                                     # a coin rides up the steps instead
            be.icon("coin", xa + w / 2, top - 50, 80, trig[i] + 0.15, dur=0.4, until=until)


def s_ceiling(be, ctx, sp):
    base = 650
    for i in range(3):
        top = base - (i + 1) * 100
        be.rect(150 + i * 170, top, 320 + i * 170, base, ctx.t0 + 0.1 + i * 0.15, fill="soft", line="ink", w=4, r=6)
    c = ctx.at("ceiling", 0.4)
    if sp.get("fig"):
        be.figure("reach", 150 + 2 * 170 + 85, 650 - 300 - 90, 170, ctx.t0 + 0.5)
    else:
        be.icon("coin", 150 + 2 * 170 + 85, 650 - 300 - 55, 90, ctx.t0 + 0.5, dur=0.4)
    be.rect(110, 70, 900, 118, c, fill="ink", line="ink", w=4, r=4)
    for k in range(10):
        be.line([(130 + k * 78, 118), (100 + k * 78, 150)], c + 0.1, color="mute", w=4, dur=0.2)
    be.text("CEILING", 505, 94, 32, c + 0.2, color="white")
    be.cross(597, 165, 24, c + 0.5, color="neg")
    be.text("YOU HIT IT", 790, 300, 32, c + 0.7, color="neg")


def s_hours(be, ctx, sp):
    be.icon("clock", 500, 190, 230, ctx.t0 + 0.15, dur=0.9)
    out = ctx.at("out", 0.7)
    n = 10
    for i in range(n):
        x = 100 + i * 80
        t_in = ctx.t0 + 0.4 + i * 0.09
        be.rect(x, 440, x + 64, 520, t_in, fill=None, line="ink", w=4, r=8)
        be.rect(x + 6, 446, x + 58, 514, t_in + 0.05, fill="accent", line=None, r=6, until=out + i * 0.06)
    be.text("HOURS IN A DAY", 500, 580, 28, ctx.t0 + 0.9, color="mute")
    be.text("0 LEFT", 500, 650, 64, out + 0.6, color="neg")


def s_own(be, ctx, sp):
    t = ctx.t0
    be.icon("wallet", 120, 400, 170, t + 0.05)
    be.text("YOUR MONEY", 120, 520, 24, t + 0.2)
    tb = ctx.at("building", 0.3)
    be.arrow((220, 420), (330, 420), tb - 0.1, color="mute")
    be.icon("bldg", 460, 400, 250, tb, dur=0.8)
    be.text("ASSET", 460, 560, 34, tb + 0.2)
    ti = ctx.at("income", 0.65)
    be.arrow((600, 400), (730, 400), ti - 0.1, color="mute")
    be.icon("coins", 840, 400, 200, ti, dur=0.7)
    be.text("INCOME", 840, 540, 34, ti + 0.2)
    be.flow((600, 400), (730, 400), ti + 0.3)
    be.text("PAYS YOU EVERY MONTH", 790, 620, 24, ti + 0.7, color="mute")


def s_hub(be, ctx, sp):
    nodes = sp["nodes"][:6]
    n = len(nodes)
    cx, cy, rx, ry = 500, 380, 340, 250
    c0 = ctx.t0 + 0.1
    be.icon(sp.get("center", "link"), cx, cy, 170, c0, dur=0.7)
    if sp.get("center_label"):
        be.text(sp["center_label"], cx, cy + 118, 30, c0 + 0.2)
    for i, nd in enumerate(nodes):
        ang = -math.pi / 2 + 2 * math.pi * (i + 0.5) / n if n > 2 else (-math.pi * 0.75 + i * math.pi * 1.5)
        x, y = cx + rx * math.cos(ang), cy + ry * math.sin(ang)
        tr = ctx.item(nd["k"]) if "k" in nd else ctx.t0 + 0.4 + i * (max(0.2, (ctx.t1 - ctx.t0 - 0.8) / max(1, n)))
        ux, uy = math.cos(ang), math.sin(ang)
        be.line([(cx + ux * 100, cy + uy * 80), (x - ux * 62, y - uy * 62)], tr - 0.05, color="mute", w=5, dur=0.35)
        be.icon(nd.get("icon", "person"), x, y - 6, 112, tr, dur=0.5)
        be.text(nd["label"], x, y + 82, 28, tr + 0.15)
        if nd.get("item"):
            be.circle(x + 62, y - 44, 30, tr + 0.3, fill="white", line="accent", w=4)
            be.icon(nd["item"], x + 62, y - 44, 38, tr + 0.35, dur=0.4, claim=False)


def s_bank(be, ctx, sp):
    tm = ctx.at("millions", 0.3)
    be.icon("bank", 250, 330, 280, ctx.t0 + 0.1, dur=0.8)
    be.text("YOUR BANK", 250, 520, 30, ctx.t0 + 0.4)
    be.text("$1,000,000", 250, 590, 52, tm, color="mute")
    be.line([(120, 590), (380, 590)], tm + 0.3, color="neg", w=10, dur=0.3)
    tp = ctx.at("participate", 0.8)
    be.arrow((420, 330), (560, 330), tp - 0.5, color="mute")
    be.icon("scroll", 700, 330, 220, tp - 0.4, dur=0.7)
    be.text("THE DEAL", 700, 500, 30, tp - 0.2)
    be.icon("check_circle", 880, 205, 90, tp, dur=0.5)
    be.text("YOU'RE IN", 700, 580, 40, tp + 0.2, color="accent")


def s_freedom(be, ctx, sp):
    t = max(ctx.t0 + 0.9, ctx.at("freedom", 0.3))
    be.line([(80, 604), (920, 604)], ctx.t0 + 0.05, color="ink", w=6, dur=0.5)
    if sp.get("fig"):
        be.figure("stand", 500, 512, 190, ctx.t0 + 0.2, until=t + 0.3)
        be.figure("up", 500, 512, 190, t + 0.3)
        be.icon("sun", 500, 275, 240, t, dur=1.0)
        be.icon("padlock", 800, 500, 130, t + 0.6, dur=0.7)
    else:
        be.icon("padlock", 330, 480, 190, ctx.t0 + 0.2, dur=0.7)
        be.icon("sun", 640, 330, 340, t, dur=1.0)
    be.text("FREE", 500, 670, 60, t + 0.8, color="accent")


def s_chat(be, ctx, sp):
    t = ctx.at("conversation", 0.3)
    be.icon("person", 160, 430, 170, ctx.t0 + 0.05)
    be.icon("person", 840, 430, 170, t)
    be.icon("chat", 500, 330, 300, t, dur=0.7)
    be.arrow((260, 430), (350, 380), t + 0.2, color="mute")
    be.arrow((740, 430), (650, 380), t + 0.4, color="mute")
    be.text("CONVERSATION", 500, 560, 32, t + 0.5)


def s_flow(be, ctx, sp):
    nodes = sp["nodes"][:4]
    n = len(nodes)
    xs = [500] if n == 1 else [140 + i * (720 / (n - 1)) for i in range(n)]
    for i, (nd, x) in enumerate(zip(nodes, xs)):
        tr = ctx.item(nd["k"]) if "k" in nd else ctx.at(nd.get("word"), 0.2 + 0.25 * i)
        if i:
            be.arrow((xs[i - 1] + 85, 380), (x - 85, 380), tr - 0.15, color="accent")
        _node(be, x, 380, nd["icon"], nd.get("label", ""), tr, size=140)
    if sp.get("cause"):
        be.text("BECAUSE", xs[0], 250, 24, ctx.t0 + 0.3, color="mute")
        be.text("SO", xs[-1], 250, 24, ctx.at(nodes[-1].get("word"), 0.7), color="mute")


def s_growth(be, ctx, sp):
    up = sp.get("dir", "up") == "up"
    base, n = 620, 5
    for i in range(n):
        h = (110 + i * 80) if up else (430 - i * 80)
        x = 140 + i * 150
        tr = ctx.t0 + 0.2 + i * max(0.18, (ctx.t1 - ctx.t0 - 0.8) / (n + 1))
        be.rect(x, base - h, x + 100, base, tr, fill="soft", line="ink", w=4, r=6)
    pts = [(190 + i * 150, base - ((110 + i * 80) if up else (430 - i * 80)) - 50) for i in range(n)]
    be.line(pts, ctx.t0 + 0.9, color="accent" if up else "neg", w=10, dur=max(0.6, ctx.t1 - ctx.t0 - 1.2))
    be.icon("bars" if up else "trend_down", 840, 150, 140, ctx.t0 + 1.0)


def s_question(be, ctx, sp):
    t = ctx.t0 + 0.1
    neg = sp.get("neg")
    if sp.get("fig"):
        be.figure("shrug", 260, 400, 400, t)
        qx = 640
    else:
        qx = 500
    be.icon("question", qx, 290, 300, t + 0.25, dur=0.8)
    be.icon(sp.get("icon", "coin"), qx - 80, 590, 110, t + 0.7, dur=0.5)
    be.arrow((qx - 10, 590), (qx + 90, 590), t + 0.9, color="mute")
    be.icon("x_circle" if neg else "check_circle", qx + 180, 590, 110, t + 1.0, dur=0.5, color="neg" if neg else "ink")


SCENES = {"pictogram": s_pictogram, "income_stop": s_income_stop, "steps": s_steps, "ceiling": s_ceiling, "hours": s_hours,
          "own": s_own, "hub": s_hub, "bank": s_bank, "freedom": s_freedom, "chat": s_chat, "flow": s_flow, "growth": s_growth,
          "question": s_question}


def draw(be, ctx, spec):
    SCENES.get(spec.get("type"), s_pictogram)(be, ctx, spec)


# ------------------------------------------------------------------ the part both styles share: timing and strokes
import story_icons


def _ease_out(v):
    v = max(0.0, min(1.0, v))
    return 1 - (1 - v) ** 3


def _plen(pts):
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def _prog(pts, p):
    """The first `p` (0..1) of a polyline."""
    if p <= 0:
        return []
    segs = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    target = sum(segs) * min(1.0, p)
    out, acc = [pts[0]], 0.0
    for i, sl in enumerate(segs):
        if acc + sl <= target + 1e-9:
            out.append(pts[i + 1])
            acc += sl
        else:
            r = (target - acc) / sl if sl else 0
            out.append((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * r, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * r))
            break
    return out


class Ctx:
    """When things are spoken in this beat. `words` = [(word, second)], `item_fn(k)` = second of the k-th word."""

    def __init__(self, t0, t1, words, item_fn):
        self.t0, self.t1, self.words, self._item = t0, t1, words, item_fn

    def at(self, word=None, frac=0.0):
        if word:
            w = re.sub(r"[^a-z0-9]", "", word.lower())
            for sw, st in self.words:
                s = re.sub(r"[^a-z0-9]", "", sw.lower())
                if s == w or (len(w) >= 4 and len(s) >= 4 and (s.startswith(w[:4]) or w.startswith(s[:4]))):
                    return st
        return self.t0 + (self.t1 - self.t0) * frac

    def item(self, k):
        return self._item(k)


class Backend:
    """Draws scene primitives. A style subclasses it and supplies the low-level calls (_line, _rect, _ellipse, _text, _claim,
    color); `k` scales the 1000 x 760 scene box, (ox, oy) is where its corner lands on the style's page."""

    def __init__(self, t, ox, oy, k):
        self.t, self.ox, self.oy, self.k = t, ox, oy, k
        self._n = 0

    def P(self, x, y):
        return (self.ox + self.k * x, self.oy + self.k * y)

    def _uid(self, kind):
        self._n += 1
        return "%s%d" % (kind, self._n)

    # ---- strokes: icons and the figure
    def _strokes(self, spec, x, y, size, trig, dur, lw, color, accent, until, key, claim_w=1.0, claim=True):
        if self.t < trig or (until is not None and self.t >= until):
            return
        q = _ease_out((self.t - trig) / dur)
        cx, cy = self.P(x, y)
        s = size * self.k
        ox, oy = cx - s / 2, cy - s / 2
        total = sum(_plen(pts) for _c, pts in spec)
        target, acc = total * q, 0.0
        w = max(3.5, lw * self.k)
        for ck, pts in spec:
            if acc >= target:
                break
            ln = _plen(pts)
            seg = _prog([(ox + px * s / 100.0, oy + py * s / 100.0) for px, py in pts], min(1.0, (target - acc) / ln) if ln > 0 else 1.0)
            if len(seg) >= 2:
                self._line(seg, self.color(color if ck == "i" else accent), w)
            acc += ln
        if claim:
            self._claim(key, (cx - s * claim_w / 2, oy, cx + s * claim_w / 2, oy + s))

    def icon(self, name, x, y, size, trig, dur=0.6, color="ink", accent="accent", until=None, claim=True):
        self._strokes(story_icons.ICONS[name], x, y, size, trig, dur, size / 24.0, color, accent, until, self._uid("i"), claim=claim)

    def figure(self, pose, x, y, h, trig, dur=0.55, until=None, color="ink", accent="accent"):
        self._strokes(story_icons.FIGURE[pose], x, y, h, trig, dur, h / 17.0, color, accent, until, self._uid("f"), claim_w=0.62)

    # ---- lines, shapes, text
    def line(self, pts, trig, color="ink", w=6, dur=0.5, until=None):
        if self.t < trig or (until is not None and self.t >= until):
            return
        q = _ease_out((self.t - trig) / max(0.05, dur))
        seg = _prog([self.P(*p) for p in pts], q)
        if len(seg) >= 2:
            self._line(seg, self.color(color), max(3.0, w * self.k))

    def arrow(self, p0, p1, trig, color="ink", w=6, dur=0.45):
        self.line([p0, p1], trig, color, w, dur)
        if self.t >= trig + dur * 0.8:
            a = _ease_out((self.t - trig - dur * 0.8) / 0.15)
            (x0, y0), (x1, y1) = self.P(*p0), self.P(*p1)
            d = math.dist((x0, y0), (x1, y1)) or 1.0
            ux, uy = (x1 - x0) / d, (y1 - y0) / d
            s = 20 * self.k * a
            self._line([(x1 - ux * s - uy * s * 0.6, y1 - uy * s + ux * s * 0.6), (x1, y1),
                        (x1 - ux * s + uy * s * 0.6, y1 - uy * s - ux * s * 0.6)], self.color(color), max(3.0, w * self.k))

    def rect(self, x0, y0, x1, y1, trig, fill=None, line="ink", w=4, r=10, until=None, dur=0.35):
        if self.t < trig or (until is not None and self.t >= until):
            return
        q = _ease_out((self.t - trig) / dur)
        ax, ay = self.P(x0, y1 - (y1 - y0) * q)
        bx, by = self.P(x1, y1)
        self._rect(ax, ay, bx, by, self.color(fill) if fill else None, self.color(line) if line else None, max(2.0, w * self.k), r * self.k)

    def circle(self, x, y, r, trig, fill=None, line="ink", w=4, until=None, dur=0.3):
        if self.t < trig or (until is not None and self.t >= until):
            return
        q = _ease_out((self.t - trig) / dur)
        cx, cy = self.P(x, y)
        self._ellipse(cx, cy, r * self.k * q, self.color(fill) if fill else None, self.color(line) if line else None, max(2.0, w * self.k))

    def text(self, s, x, y, px, trig, anchor="m", color="ink", dur=0.22):
        cx, cy = self.P(x, y)
        self._text(s, cx, cy, px * self.k * 1.22, self.color(color), anchor, trig, dur, self._uid("t"))

    def check(self, x, y, size, trig, color="accent"):
        self.line([(x - size, y), (x - size * 0.25, y + size * 0.8), (x + size * 1.05, y - size * 0.8)], trig, color, 9, 0.3)

    def cross(self, x, y, size, trig, color="neg"):
        self.line([(x - size, y - size), (x + size, y + size)], trig, color, 9, 0.2)
        self.line([(x + size, y - size), (x - size, y + size)], trig + 0.12, color, 9, 0.2)

    def flow(self, p0, p1, trig, color="accent", n=3):
        """Little dots travelling along a path (money moving)."""
        if self.t < trig:
            return
        for j in range(n):
            u = ((self.t - trig) * 0.7 + j / n) % 1.0
            x, y = p0[0] + (p1[0] - p0[0]) * u, p0[1] + (p1[1] - p0[1]) * u
            cx, cy = self.P(x, y)
            self._ellipse(cx, cy, 11 * self.k, self.color(color), None, 1)


_PLANS = {}


def scene_of(story, cid, idx):
    """The planned scene of beat `idx` of clip `cid` (planned on first use from the beat's words, then remembered)."""
    key = (id(story), cid, idx)
    if key not in _PLANS:
        feats = story["feats"][str(cid)]
        f = feats[idx]
        if f.get("scene"):
            _PLANS[key] = dict(f["scene"])
        else:
            if idx > 0:
                prev = feats[idx - 1]["text"]
            else:
                prev = story["feats"][str(cid - 1)][-1]["text"] if str(cid - 1) in story["feats"] else story.get("hook", "")
            _PLANS[key] = plan(f, prev)
        if idx > 0 or cid > 1:
            # the same picture twice in a row is dull: a repeated scene becomes a pictogram of what the beat mentions
            pc, pi = (cid, idx - 1) if idx > 0 else (cid - 1, len(story["feats"][str(cid - 1)]) - 1)
            before = scene_of(story, pc, pi)
            if before.get("type") == _PLANS[key].get("type") and _PLANS[key]["type"] not in ("pictogram", "hub", "steps", "question"):
                kws = _kw_nodes(f["text"])
                _PLANS[key] = {"type": "pictogram", "pose": "stand", "nodes": kws[:3] or [{"icon": pick_icon(f["text"], 0), "label": "", "word": ""}]}
        sp = _PLANS[key]
        # the figure is for moments where an emotion carries the idea (stuck under a ceiling, freedom, a climb, a shrug) -
        # and never in more than one of three beats in a row
        wants = sp.get("type") in ("ceiling", "freedom") or (sp.get("type") == "question" and sp.get("neg"))
        recent = any(_prev_fig(story, cid, idx, back) for back in (1, 2))
        sp["fig"] = bool(wants and not recent)
    return _PLANS[key]


def _prev_fig(story, cid, idx, back):
    """Whether the beat `back` places before (cid, idx) draws the figure."""
    order = [(int(c), i) for c in sorted(story["feats"], key=int) for i in range(len(story["feats"][c]))]
    pos = order.index((cid, idx)) - back
    if pos < 0:
        return False
    pc, pi = order[pos]
    return bool(scene_of(story, pc, pi).get("fig"))
