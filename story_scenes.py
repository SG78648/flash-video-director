"""story_scenes.py - the visual vocabulary of a script story, shared by the Lee and Dan styles.

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
    (r"\b(ceiling|cap(?! rates?)|limit|limits|stuck|plateau)\b", "ladder"),
    (r"\b(investors?|lenders?|partners?|operators?|everyone|people|someone|team|clients?|customers?|friends|family|buyers?|sellers?|tenants?|owners?|founders?|employees?|mentors?|managers?)\b", "person"),
    (r"\b(capital|equity|funding|investment|investments)\b", "moneybag"),
    (r"\b(financing|finance|financed)\b", "bank"),
    (r"\b(operate|operates|operating|operation|operations)\b", "gear"),
    (r"\b(market|markets)\b", "candles"),
    (r"\b(numbers|math|calculations?|figures)\b", "calculator"),
    (r"\b(relationships?)\b", "network"),
    (r"\b(wait|waiting|delay|later|procrastinate)\b", "hourglass"),
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
    (r"\b(retire|retired|retiring|retirement|vacation|holiday)\b", "palm"),
    (r"\b(free|freedom|independence|dream|future|morning|hope)\b", "sun"),
    (r"\b(ownership)\b", "keys_house"),
    (r"\b(own|owning|owner|keys?|access|enter)\b", "key"),
    (r"\b(door|opportunity|opportunities|opens?)\b", "door"),
    (r"\b(goal|goals|target|aim|focus|plan)\b", "target"),
    (r"\b(system|systems|process|operations?|manage|managing|machine|automate)\b", "gear"),
    (r"\b(risk|risks|protect|safe|safety|insurance|secure|security)\b", "shield"),
    (r"\b(start|starting|begin|launch|launching|startup|first)\b", "rocket"),
    (r"\b(share|shares|split|equity|portion|slice|stake)\b", "pie"),
    (r"\b(save|saving|savings|stack|accumulate|wallet|budget|account)\b", "wallet"),
    (r"\b(buy|buying|shop|shopping|purchase|bought|spent|consume|consumption|consuming|consumer)\b", "cart"),
    (r"\b(online|laptop|remote|computer|digital|website)\b", "laptop"),
    (r"\b(network|networking|connections|contacts|community)\b", "network"),
    (r"\b(repeat|cycle|loop|again|routine|forever)\b", "cycle"),
    (r"\b(grow|sprout|seed|passive|harvest)\b", "tree"),
    (r"\b(balance|weigh|fair|compare)\b", "scale"),
    (r"\b(announce|announcement|message|voice|marketing)\b", "megaphone"),
    (r"\b(warning|problem|problems|uncomfortable|danger|never|can't|cannot|won't|don't)\b", "warning"),
    (r"\b(together|join|partnership|link|connected)\b", "link"),
    (r"\b(steps?|levels?|stairs|progress)\b", "stairs"),
]
FALLBACK_ICONS = ["bulb", "bars", "key", "sprout", "coin", "bldg", "clock", "chat"]

PEOPLE = r"(investors?|lenders?|partners?|operators?|clients?|customers?|friends?|family|buyers?|sellers?|tenants?|owners?|founders?|employees?|mentors?|managers?|brokers?|advisors?|people|members?|donors?|backers?|sponsors?|lawyers?|agents?|builders?|developers?)"
VERBS = r"^(get|work|start|build|save|buy|sell|earn|invest|cut|stop|learn|ask|find|make|take|try|keep|put|use|open|plan|pay|apply|hire|ask|call|sign|join|read|write|set|grow|spend|track|check|list|pick|choose|look|study|review|create|begin|talk|meet|research|understand|focus|avoid|remember|think|protect|stay|move|turn|let|show|teach|practice|test|compare|negotiate|network|escape|quit|fix|improve|raise|lower|reduce|increase|add|lease|refinance|underwrite|analyze|package|close|offer|call|visit|inspect|upgrade|repair|bring|structure|coordinate|evaluate)\b"


def pick_icon(text, i=0):
    low = text.lower()
    for pat, icon in RULES:
        if re.search(pat, low):
            return icon
    return FALLBACK_ICONS[i % len(FALLBACK_ICONS)]


# ------------------------------------------------------------------ planning: which scene tells this beat?

# ------------------------------------------------------------------ the concrete things a beat talks about
# (pattern, icon, strong). Strong nouns are things you can point at (a car, a warehouse): a beat that names one is
# drawn as those things appearing as they are spoken. Weak ones (money, a bank) only join a picture that already has one.
NOUNS = [
    (r"\$\d[\d,\.]*(?: ?(?:million|billion|thousand|[kmb]\b))?", "moneybag", True),
    (r"bank accounts?", "bank", True),
    (r"lottery|jackpot|casino|gambling|scratch[- ]offs?", "trophy", True),
    (r"reits?", "candles", True),
    (r"richest(?: person)?|wealthiest(?: person)?", "person", True),
    (r"multi[- ]?family(?: propert(?:y|ies)| building| buildings| units?| housing| apartments?)?|apartment (?:buildings?|complex(?:es)?)|apartments?|duplex(?:es)?|fourplex(?:es)?", "multifamily", True),
    (r"skyscrapers?|office (?:buildings?|towers?|space)|offices?|towers?", "tower", True),
    (r"self[- ]?storage|storage units?", "storage", True),
    (r"warehouses?|industrial|distribution centers?", "warehouse", True),
    (r"retail|shopping (?:centers?|malls?)|strip malls?|storefronts?|stores?|shops?", "store", True),
    (r"hotels?|motels?|hospitality|airbnbs?|short[- ]term rentals?", "hotel", True),
    (r"vacant land|land|lots?|acres?|plots?", "land", True),
    (r"for sale|listings?|realtors?|brokers?", "for_sale", True),
    (r"single[- ]family(?: homes?| houses?)?|houses?|homes?|condos?|townhouses?", "house", True),
    (r"commercial real estate|real estate|propert(?:y|ies)|buildings?|commercial", "bldg", True),
    (r"cars?|suvs?|lexus|bmw|tesla|mercedes|porsche|ferrari|lamborghini", "car", True),
    (r"trucks?|pickups?", "truck", True),
    (r"vacations?|holidays?|trips?|beach(?:es)?|resorts?|traveling|travel", "palm", True),
    (r"flights?|planes?|jets?|airlines?", "plane", True),
    (r"boats?|yachts?|sailing", "boat", True),
    (r"watch(?:es)?|rolex(?:es)?", "watch", True),
    (r"jewelry|rings?|diamonds?", "ring", True),
    (r"handbags?|designer bags?|purses?|bags?", "bag", True),
    (r"sneakers?|shoes?|heels", "shoe", True),
    (r"iphones?|phones?|smartphones?|gadgets?", "phone", True),
    (r"laptops?|computers?", "laptop", True),
    (r"tvs?|televisions?|netflix|streaming", "tv", True),
    (r"coffee|lattes?|starbucks", "coffee", True),
    (r"restaurants?|dinners?|dining|eating out|meals?|food", "fork", True),
    (r"bottle service|champagne|bottles?", "bottle", True),
    (r"gyms?|fitness", "dumbbell", True),
    (r"credit cards?|cards?|debt", "credit_card", True),
    (r"bills?|invoices?|receipts?|expenses|subscriptions?|payments?", "receipt", True),
    (r"cages?|prison|trapped", "padlock", True),
    (r"launchpads?|rockets?", "rocket", True),
    (r"cash[- ]?flow", "coins", True),
    (r"portfolios?", "candles", True),
    (r"savings|piggy bank", "piggy", True),
    (r"vaults?|safes?", "vault", True),
    (r"stock market|stocks?|shares|trading(?! (?:your |my |our |their )?(?:time|hours))|index funds?|etfs?", "candles", True),
    (r"school|college|degree|tuition|education|universit(?:y|ies)", "grad_cap", True),
    (r"health|medical|hospitals?|doctors?|insurance", "health", True),
    (r"repairs?|maintenance|renovations?|rehab|fixing", "wrench", True),
    (r"construction|developers?|development|cranes?", "crane", True),
    (r"utilities|electricity|electric", "lightning", True),
    (r"world|global|international|overseas", "globe", True),
    (r"emails?|inbox", "mail", True),
    (r"tenants?|rentals?|renters?|landlords?|rent", "keys_house", True),
    (r"paychecks?|salary|wages?", "bill", True),
    (r"millions?|fortune", "moneybag", True),
    (r"promotions?", "ladder", True),
    (r"six figures?|six[- ]figure|seven figures?", "moneybag", True),
    (r"engines?|machines?", "gear", True),
    (r"millionaires?|billionaires?", "moneybag", True),
    (r"business(?:es)?|compan(?:y|ies)|startups?", "briefcase", True),
    (r"jobs?|careers?", "briefcase", True),
    (r"desks?", "laptop", True),
    (r"bank|banks|mortgages?|lenders?|loans?", "bank", False),
    (r"family|kids|children", "people", False),
    (r"calculators?|numbers|budget", "calculator", False),
    (r"coins?|dollars?|money|income|profit", "coin", False),
]
def _noun_re(pat):
    if pat.startswith("\\$"):              # a dollar amount starts with a symbol, so \b would never match in front of it
        return re.compile(r"(?<![A-Za-z0-9$])(?:%s)(?![A-Za-z0-9])" % pat)
    return re.compile(r"\b(?:%s)\b" % pat)


_NOUN_RES = [(_noun_re(pat), icon, strong) for pat, icon, strong in NOUNS]


def concrete(text):
    """The things a sentence names, in the order they are spoken: [{"icon", "label", "word", "strong"}]."""
    low = text.lower()
    hits = []
    for rx, icon, strong in _NOUN_RES:
        for m in rx.finditer(low):
            hits.append((m.start(), -(m.end() - m.start()), m.end(), m.group(0), icon, strong))
    hits.sort()
    out, taken, seen = [], [], set()
    DET = {"a", "an", "the", "this", "that", "these", "those", "your", "my", "our", "their", "his", "her", "another", "new", "big", "tall",
           "office", "apartment", "commercial", "one", "each", "every", "any", "first", "second", "next", "whole", "entire"}
    for start, _neg, end, mt, icon, strong in hits:
        if icon in seen or any(start < e and end > s for s, e in taken):
            continue
        if mt in ("building", "watch"):                   # as verbs (building wealth, watch what happens) these are not things
            prev_word = re.findall(r"[a-z']+", low[:start])[-1:] or [""]
            if (prev_word[0] not in DET and prev_word[0] not in ("luxury", "expensive", "fancy", "nice", "gold", "swiss", "unit", "units", "story", "stories", "floor", "bedroom", "family")
                    and not re.fullmatch(r"(million|billion|thousand|hundred|[0-9][0-9,.]*k?)", prev_word[0])):    # "a $5 million building" is a building
                continue
        taken.append((start, end))
        seen.add(icon)
        label = re.sub(r"\s+", " ", mt.replace("-", " ")).upper()
        if len(label) > 18 and " " in label:
            label = " ".join(label.split()[-2:])
        negated = bool(re.search(r"(?:\bnot\b|n't\b|\bnever\b|\bno\b)[^.,;]*$", low[:start][-45:]))
        out.append({"neg": negated, "icon": icon, "label": label[:18].rsplit(" ", 1)[0] if len(label) > 18 and " " in label[:19] else label[:18],
                    "word": mt.split()[0].replace("-", ""), "strong": strong})
    if any(c["icon"] in ("multifamily", "tower", "warehouse", "storage", "store", "hotel", "land", "house") for c in out):
        out = [c for c in out if c["icon"] != "bldg"]      # a named kind of property replaces the generic building
    return out


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


_COUNT_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
                "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20}
_NOT_COUNTED = ("moneybag", "receipt", "keys_house", "coins", "candles", "gear", "bill", "wrench", "lightning", "globe", "mail", "briefcase")


def counted(text):
    """'take five small apartment buildings' -> {"n": 5, "icon": "multifamily", "label": "APARTMENT BUILDINGS", "word": "five"}: a number and the
    thing it counts (2 to 20, and only things you can point at). None when the sentence does not count anything."""
    low = text.lower()
    num = r"(\d{1,2}|" + "|".join(_COUNT_WORDS) + r")"
    for rx, icon, strong in _NOUN_RES:
        if not strong or icon in _NOT_COUNTED:
            continue
        m = re.search(r"(?<![$\d.,])\b" + num + r"\b(?![ ]?(?:percent|%|million|billion|thousand|hundred|years?|months?|days?|hours?|weeks?|minutes?|k\b))\s+((?:[a-z'-]+\s+){0,3}?)(" + rx.pattern + r")", low)
        if not m:
            continue
        n = _COUNT_WORDS.get(m.group(1)) or int(m.group(1))
        if not 2 <= n <= 20:
            continue
        if icon == "bldg" and m.group(3).strip() in ("building", "buildings") and re.search(r"\b(units?|story|stories|floors?)\b", m.group(2)):
            continue                                       # "a 24 unit building" is one building
        label = re.sub(r"\s+", " ", m.group(3).replace("-", " ")).upper()
        return {"n": n, "icon": icon, "label": label, "word": m.group(1)}
    return None


def _open_question(text, prev_text="", next_text=""):
    """A question put to the viewer ("What can you bring to a deal that makes people want you involved?"), also when the beat holds only
    the start or only the end of it."""
    qw = r"(?:what|how|why|who|where|when|can|could|should|would|will|do|does|is|are)\b"
    if re.search(r"\d", text):
        return False
    for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
        if re.match(qw, sent.lower()) and re.search(r"\byou\b", sent.lower() + " " + next_text.lower()) and ("?" in text or next_text.strip().endswith("?")):
            return True
    if text.strip().endswith("?") and prev_text and not prev_text.rstrip().endswith((".", "?", "!")):
        last = re.split(r"(?<=[.!?])\s+", prev_text.strip())[-1].lower()
        return bool(re.match(qw, last) and re.search(r"\byou\b", last + " " + text.lower()))
    return False


def plan(beat, prev_text="", next_text=""):
    """The scene for one beat: {"type": ..., ...} with everything the drawers need (words to wait for, labels, icons)."""
    kind, text = beat["kind"], beat["text"]
    low = text.lower()
    ctxlow = (prev_text + " " + low).lower()
    raw_calc = beat.get("calc") or []
    stack = next((parse_stack(x) for x in raw_calc if x.lower().startswith("stack ")), None)
    calc = [c for c in (parse_calc(x) for x in raw_calc if not x.lower().startswith("stack ")) if c] or ([] if stack else auto_calc(text))
    if stack:                                      # a whole split into its parts, as a bar (with the sum underneath when the beat has one)
        return dict(stack, type="stack", eq=(calc[0]["left"] + " = " + calc[0]["value"]) if calc else "")
    if calc:                                       # a sum is shown as a sum: the working, then the answer
        return {"type": "calc", "rows": calc[:4]}
    if kind == "list":
        items = beat["items"]
        lead = (beat.get("lead") or "").lower()
        ppl = sum(1 for it in items if re.fullmatch(r"\W*" + PEOPLE + r"\W*", it.lower().strip()))
        k, nodes = nwords(lead), []
        for it in items:
            nodes.append({"label": it, "k": k})
            k += nwords(it)
        things = [c for it in items for c in concrete(it)[:1] if c["strong"]]
        if len(things) >= 2 and ppl < 2:
            for c, n in zip(things, nodes):
                c["k"] = n["k"]
            return {"type": "objects", "nodes": things[:4]}
        if ppl >= max(2, int(len(items) * 0.6)):
            icon, label = _center_for(ctxlow + " " + next_text.lower())
            return {"type": "hub", "center": icon, "center_label": label,
                    "nodes": [{"label": _short(n["label"]), "icon": ("person" if re.fullmatch(r"\W*" + PEOPLE + r"\W*", n["label"].lower().strip()) else pick_icon(n["label"], 0)), "k": n["k"]} for n in nodes]}
        if sum(1 for it in items if re.match(VERBS, it.lower().strip())) >= max(2, len(items) // 2):
            return {"type": "steps", "nodes": [{"label": n["label"], "k": n["k"]} for n in nodes]}
        def key_word(label):
            ws = re.findall(r"[A-Za-z']+", label)
            return ws[-1] if ws else label
        if max(nwords(it) for it in items) >= 5:             # sentences, not names of things: rows with a tick, not one key word each
            return {"type": "steps", "rows": True, "mark": "check", "nodes": [{"label": n["label"], "k": n["k"]} for n in nodes[:6]]}
        return {"type": "flow", "nodes": [{"icon": pick_icon(key_word(n["label"]), i), "label": key_word(n["label"]).upper(), "k": n["k"]} for i, n in enumerate(nodes[:4])]}
    if kind == "quote":
        neg = bool(beat.get("neg"))
        return {"type": "question", "neg": neg, "icon": pick_icon(beat["quote"], 0)}
    cnt = counted(text)
    if cnt:                                        # "five apartment buildings": five of them are drawn
        return dict(cnt, type="count")
    if re.search(r"\bfollow me\b", low):                    # the call to action gets a Follow button
        return {"type": "follow"}
    mk = re.search(r"\b[Cc]omment (?:the word )?([A-Z]{3,})\b", text)
    mine = re.search(r"\b[Cc]omment your (\w+)", text)
    if mk or mine:                                         # "Comment DEAL and I'll send you the checklist": a comment, an arrow, a message
        lab = re.search(r"send you (?:the |my |our |a )?([a-z' -]+?)(?:[.!?]|$)", low)
        return {"type": "keyword", "word": mk.group(1) if mk else mine.group(1).upper(),
                "label": lab.group(1).strip().upper() if lab else ("YOUR NUMBER" if mine else "THE FREE PACK")}
    if re.search(r"\bA or B\b", text):                     # a poll
        return {"type": "ab"}
    if _open_question(text, prev_text, next_text):
        icon, label = _center_for(low + " " + next_text.lower() + " " + prev_text.lower())      # "what can you bring to a deal?": you, a big question, the deal
        return {"type": "ask", "icon": icon, "label": label if icon != "link" else "THE DEAL"}
    tri = verb_triple(text)
    if tri:                                        # "bring real value, understand the risks, and earn trust": three things to do, as ticked rows
        return {"type": "steps", "rows": True, "mark": "check", "nodes": tri}
    # statements, by what they say
    if re.search(r"\bearning to owning\b|\bfrom earning to own", low):
        return {"type": "flow", "nodes": [{"icon": "briefcase", "label": "EARNING", "word": "earning"}, {"icon": "keys_house", "label": "OWNING", "word": "owning"}]}
    if re.search(r"difference between", low) and next_text:
        return {"type": "compare", "stage": "left", "left": _side(low.split("between", 1)[1]), "right": _side(next_text)}
    if re.search(r"difference between", prev_text.lower()):
        return {"type": "compare", "stage": "both", "left": _side(prev_text.lower().split("between", 1)[1]), "right": _side(text)}
    if re.search(r"(income|paycheck|pay|money|salary).{0,40}\b(stops?|ends?|dries|disappears)\b|\bstop working\b|\bwhen you stop\b", low):
        return {"type": "income_stop"}
    if re.search(r"\b(ceiling|plateau|maxed)\b|\bcap\b(?! rates?)|\bthere'?s a limit\b", low):
        return {"type": "ceiling"}
    if re.search(r"run out of|out of (hours|time)|\bonly (so many|\d+) hours\b|\bhours\b.*\b(day|week)\b", low):
        return {"type": "hours"}
    if re.search(r"millions|bank account|savings|rich first|enough money|big money", low) and re.search(r"\b(don'?t|do not|no\b|without|sitting|need|have to|necessarily)\b", low):
        return {"type": "bank"}
    bld = [c for c in concrete(text) if c["icon"] in ("multifamily", "tower", "warehouse", "storage", "store", "hotel", "land", "house", "bldg")]
    amount = [c for c in concrete(text) if c["icon"] == "moneybag" and c["label"].startswith("$")]
    negated_ctx = bool(re.search(r"\b(don't|do not|doesn't|not|never|isn't|aren't)\b[^.]{0,45}\b(own|owning|owns|buy|buying|bought)\b", (prev_text + " " + low).lower()))
    if bld and (amount or negated_ctx):
        nodes = (amount + bld)[:3]
        if negated_ctx:
            for n in nodes:
                if n["icon"] in [b["icon"] for b in bld]:
                    n["neg"] = True
        return {"type": "objects", "nodes": nodes}
    if re.search(r"\b(buying|buy|bought|own|owns|owning|invest|investing|income[- ]producing)\b", low) and \
            re.search(r"\b(building|asset|estate|property|income|rental|producing|owning)\b", low):
        building = [c for c in concrete(text) if c["icon"] in ("multifamily", "tower", "warehouse", "storage", "store", "hotel", "land", "house", "bldg")]
        return {"type": "own", "asset": building[0]["icon"] if building else "bldg", "asset_label": building[0]["label"] if building else "ASSET"}
    if re.search(r"\bnot\b[^.]{0,25}\bfreedom\b|\bcage\b|\bprison\b|\btrapped\b", low):
        # "that's not financial freedom, that's a cage": the freedom crossed out, next to what it really is
        nodes = []
        if re.search(r"\bfreedom\b", low):
            nodes.append({"icon": "sun", "label": "FREEDOM", "word": "freedom", "strong": True, "neg": bool(re.search(r"\bnot\b", low))})
        word = "cage" if "cage" in low else "prison" if "prison" in low else "trapped"
        nodes.append({"icon": "padlock", "label": word.upper(), "word": word, "strong": True, "neg": False})
        if re.search(r"launchpad|rocket", low):
            nodes.append({"icon": "rocket", "label": "LAUNCHPAD", "word": "launchpad", "strong": True, "neg": False})
        return {"type": "objects", "nodes": nodes}
    if re.search(r"\bfreedom\b|\bindependence\b|\bfree to\b", low):
        return {"type": "freedom"}
    if re.search(r"\b(conversation|discussion|start having|have a conversation|let'?s talk)\b", low):
        return {"type": "chat"}
    if re.search(r"everyone brings|each (one )?brings|something different|different to the", low):
        return {"type": "hub", "center": "link", "center_label": "THE DEAL", "mixed": True,
                "nodes": [{"label": "MONEY", "icon": "person", "item": "coin"}, {"label": "SKILLS", "icon": "person", "item": "gear"},
                          {"label": "TIME", "icon": "person", "item": "clock"}, {"label": "CONTACTS", "icon": "person", "item": "network"}]}
    m = re.search(r"([a-z' ]{3,22}?) first[.,]?\s+([a-z' ]{3,22}?) second", low)
    if m:
        k0 = len(low[:m.start(1)].split())
        a, b = m.group(1).strip(), m.group(2).strip()
        return {"type": "steps", "nodes": [{"label": (a + " first").capitalize(), "k": k0}, {"label": (b + " second").capitalize(), "k": k0 + len(a.split()) + 1}]}
    nouns = concrete(text)
    if any(c["strong"] for c in nouns):
        # a sentence cut across two beats ("I'm not talking about winning the lottery / or buying a piece of a REIT") keeps its "not"
        if prev_text and not prev_text.rstrip().endswith((".", "?", "!")) and re.search(r"(?:\bnot\b|n't\b|\bnever\b|\bno\b)[^.,;]*$", prev_text.lower()[-45:]):
            for n_ in nouns:
                n_["neg"] = True
        return {"type": "objects", "nodes": nouns[:4]}
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


_DET = {"a", "an", "the", "this", "that", "these", "those", "your", "my", "our", "their", "his", "her", "another", "new", "big", "tall",
        "office", "apartment", "commercial", "one", "each", "every", "any", "first", "second", "next", "whole", "entire"}


def _kw_nodes(text):
    """Icon nodes for the drawable words of a sentence, in the order they are spoken."""
    out, seen = [], set()
    prev = ""
    for w in re.findall(r"[A-Za-z']+", text):
        lw = w.lower()
        before, prev = prev, lw
        if len(lw) < 4 or lw in seen:
            continue
        if lw == "building" and before not in _DET:       # building as a verb (building wealth) is not a picture of a building
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
        be.figure(sp.get("pose", "stand"), 170, 400, 420, ctx.t0 + be.lag(0.05))
        xs = {1: [640], 2: [520, 800], 3: [450, 650, 850]}[min(3, max(1, n))]
        prev = (300, 400)
    else:                                                         # just the things the beat is about, in the order they are spoken
        xs = {1: [500], 2: [340, 660], 3: [190, 500, 810]}[min(3, max(1, n))]
        prev = None
    for node, x in zip(nodes, xs):
        tr = ctx.at(node.get("word"), 0.3 if prev is None and node is nodes[0] else 0.35)
        if prev:
            be.arrow((prev[0] + 10, 400), (x - 84, 400), tr - 0.1, color="mute")
        _node(be, x, 400, node["icon"], node.get("label", ""), tr, size=260 if n == 1 else 150)
        prev = (x + 70, 400)


def s_income_stop(be, ctx, sp):
    x0, y0, x1, y1 = 130, 120, 900, 600
    be.line([(x0, y0), (x0, y1), (x1, y1)], ctx.t0 + be.lag(0.05), color="ink", w=6, dur=0.5)
    be.text("INCOME", x0 + 10, y0 - 22, 28, ctx.t0 + be.lag(0.2), anchor="l", color="mute")
    stop = ctx.at("stops", 0.5)
    xs = 520
    be.line([(x0 + 10, 250), (xs, 250)], ctx.t0 + be.lag(0.2), color="accent", w=12, dur=max(0.5, stop - ctx.t0 - 0.2))
    be.icon("coin", x0 + 40, 215, 70, ctx.t0 + be.lag(0.25))
    be.text("YOU WORK", (x0 + xs) / 2, 330, 30, ctx.t0 + be.lag(0.7), color="mute")
    be.line([(xs, 250), (xs, y1 - 8)], stop, color="neg", w=12, dur=0.3)
    be.line([(xs, y1 - 8), (x1 - 10, y1 - 8)], stop + be.lag(0.3), color="neg", w=12, dur=0.7)
    be.cross(xs, y1 - 8, 28, stop + be.lag(0.2), color="neg")
    be.text("YOU STOP", xs + 150, 330, 30, stop + be.lag(0.1), color="neg")
    be.text("$0", (xs + x1) / 2 + 40, y1 - 60, 64, stop + be.lag(0.6), color="neg")


def s_steps(be, ctx, sp):
    nodes = sp["nodes"][:6]
    n = len(nodes)
    trig = [ctx.item(nd["k"]) for nd in nodes]
    if n >= 5 or sp.get("rows"):
        # many steps: a column of numbered rows (stairs would be too narrow for the words); a long label takes two lines
        top, rh = 60, 640 // n
        for i, nd in enumerate(nodes):
            y = top + i * rh
            cy = y + (rh - 16) / 2
            be.rect(40, y, 960, y + rh - 16, trig[i], fill="soft", line="ink", w=4, r=22)
            be.circle(110, cy, 34, trig[i], fill="accent", line=None)
            if sp.get("mark") == "check":
                be.check(110, cy, 13, trig[i] + be.lag(0.05), color="white")
            else:
                be.text(str(i + 1), 110, cy, 34, trig[i] + be.lag(0.05), color="white")
            big = sp.get("mark") == "check" and n <= 4                  # a few sentences: larger type
            px, wrap_n = (44, 25) if big else (34, 28)
            lines = _wrap(nd["label"], wrap_n) if len(nd["label"]) > wrap_n else [nd["label"]]
            for j, ln in enumerate(lines[:2]):
                be.text(ln, 170, cy + (j - (len(lines[:2]) - 1) / 2) * (px + 8), px, trig[i] + be.lag(0.05), anchor="l")
        return
    w = min(280, 880 // n)
    x0 = (W - n * w) / 2
    base = 650
    step_h = 118 if n <= 3 else 96
    px = 34 if n <= 3 else 26
    be.line([(x0 - 20, base), (x0 + n * w + 20, base)], ctx.t0 + be.lag(0.05), color="ink", w=6, dur=0.4)
    for i, nd in enumerate(nodes):
        top = base - (i + 1) * step_h
        xa = x0 + i * w
        be.rect(xa, top, xa + w, base, trig[i], fill="soft", line="ink", w=4, r=6)
        for j, ln in enumerate(_wrap(nd["label"], max(6, int(w / (px * 0.82))))[:3]):
            be.text(ln, xa + w / 2, top + 40 + j * (px + 10), px, trig[i] + be.lag(0.1), color="ink")
        until = trig[i + 1] if i + 1 < n else None
        if sp.get("fig"):
            be.figure("climb" if i < n - 1 else "stand", xa + w / 2, top - 82, 150, trig[i] + be.lag(0.15), until=until)
        else:                                                     # a coin rides up the steps instead
            be.icon("coin", xa + w / 2, top - 50, 80, trig[i] + be.lag(0.15), dur=0.4, until=until)


def s_ceiling(be, ctx, sp):
    base = 650
    for i in range(3):
        top = base - (i + 1) * 100
        be.rect(150 + i * 170, top, 320 + i * 170, base, ctx.t0 + be.lag(0.1) + be.lag(i * 0.15), fill="soft", line="ink", w=4, r=6)
    c = ctx.at("ceiling", 0.4)
    if sp.get("fig"):
        be.figure("reach", 150 + 2 * 170 + 85, 650 - 300 - 90, 170, ctx.t0 + be.lag(0.5))
    else:
        be.icon("coin", 150 + 2 * 170 + 85, 650 - 300 - 55, 90, ctx.t0 + be.lag(0.5), dur=0.4)
    be.rect(110, 70, 900, 118, c, fill="ink", line="ink", w=4, r=4)
    for k in range(10):
        be.line([(130 + k * 78, 118), (100 + k * 78, 150)], c + be.lag(0.1), color="mute", w=4, dur=0.2)
    be.text("CEILING", 505, 94, 32, c + be.lag(0.2), color="white")
    be.cross(597, 165, 24, c + be.lag(0.5), color="neg")
    be.text("YOU HIT IT", 790, 300, 32, c + be.lag(0.7), color="neg")


def s_hours(be, ctx, sp):
    be.icon("clock", 500, 190, 230, ctx.t0 + be.lag(0.15), dur=0.9)
    out = ctx.at("out", 0.7)
    n = 10
    for i in range(n):
        x = 100 + i * 80
        t_in = ctx.t0 + be.lag(0.4) + be.lag(i * 0.09)
        be.rect(x, 440, x + 64, 520, t_in, fill=None, line="ink", w=4, r=8)
        be.rect(x + 6, 446, x + 58, 514, t_in + be.lag(0.05), fill="accent", line=None, r=6, until=out + be.lag(i * 0.06))
    be.text("HOURS IN A DAY", 500, 580, 28, ctx.t0 + be.lag(0.9), color="mute")
    be.text("0 LEFT", 500, 650, 64, out + be.lag(0.6), color="neg")


def s_own(be, ctx, sp):
    t = ctx.t0
    be.icon("wallet", 120, 400, 170, t + be.lag(0.05))
    be.text("YOUR MONEY", 120, 520, 24, t + be.lag(0.2))
    tb = ctx.at("building", 0.3)
    be.arrow((220, 420), (330, 420), tb - 0.1, color="mute")
    be.icon(sp.get("asset", "bldg"), 460, 400, 250, tb, dur=0.8)
    be.text(sp.get("asset_label", "ASSET"), 460, 560, 34, tb + be.lag(0.2))
    ti = ctx.at("income", 0.65)
    be.arrow((600, 400), (730, 400), ti - 0.1, color="mute")
    be.icon("coins", 840, 400, 200, ti, dur=0.7)
    be.text("INCOME", 840, 540, 34, ti + be.lag(0.2))
    be.flow((600, 400), (730, 400), ti + be.lag(0.3))
    be.text("PAYS YOU EVERY MONTH", 790, 620, 24, ti + be.lag(0.7), color="mute")


def s_hub(be, ctx, sp):
    nodes = sp["nodes"][:6]
    n = len(nodes)
    cx, cy, rx, ry = 500, 380, 340, 250
    c0 = ctx.t0 + be.lag(0.1)
    be.icon(sp.get("center", "link"), cx, cy, 170, c0, dur=0.7)
    if sp.get("center_label"):
        be.text(sp["center_label"], cx, cy + 118, 30, c0 + 0.2)
    for i, nd in enumerate(nodes):
        ang = -math.pi / 2 + 2 * math.pi * (i + 0.5) / n if n > 2 else (-math.pi * 0.75 + i * math.pi * 1.5)
        x, y = cx + rx * math.cos(ang), cy + ry * math.sin(ang)
        tr = ctx.item(nd["k"]) if "k" in nd else ctx.t0 + be.lag(0.4) + i * (max(0.2, (ctx.t1 - ctx.t0 - 0.8) / max(1, n)))
        ux, uy = math.cos(ang), math.sin(ang)
        be.line([(cx + ux * 100, cy + uy * 80), (x - ux * 62, y - uy * 62)], tr - 0.05, color="mute", w=5, dur=0.35)
        be.icon(nd.get("icon", "person"), x, y - 6, 112, tr, dur=0.5)
        be.text(nd["label"], x, y + 82, 28, tr + be.lag(0.15))
        if nd.get("item"):
            be.circle(x + 62, y - 44, 30, tr + be.lag(0.3), fill="white", line="accent", w=4)
            be.icon(nd["item"], x + 62, y - 44, 38, tr + be.lag(0.35), dur=0.4, claim=False)


def s_bank(be, ctx, sp):
    tm = ctx.at("millions", 0.3)
    be.icon("bank", 250, 330, 280, ctx.t0 + be.lag(0.1), dur=0.8)
    be.text("YOUR BANK", 250, 520, 30, ctx.t0 + be.lag(0.4))
    be.text("$1,000,000", 250, 590, 52, tm, color="mute")
    be.line([(120, 590), (380, 590)], tm + be.lag(0.3), color="neg", w=10, dur=0.3)
    tp = ctx.at("participate", 0.8)
    be.arrow((420, 330), (560, 330), tp - 0.5, color="mute")
    be.icon("scroll", 700, 330, 220, tp - 0.4, dur=0.7)
    be.text("THE DEAL", 700, 500, 30, tp - 0.2)
    be.icon("check_circle", 880, 205, 90, tp, dur=0.5)
    be.text("YOU'RE IN", 700, 580, 40, tp + be.lag(0.2), color="accent")


def s_freedom(be, ctx, sp):
    t = max(ctx.t0 + be.lag(0.9), ctx.at("freedom", 0.3))
    be.line([(80, 604), (920, 604)], ctx.t0 + be.lag(0.05), color="ink", w=6, dur=0.5)
    if sp.get("fig"):
        be.figure("stand", 500, 512, 190, ctx.t0 + be.lag(0.2), until=t + be.lag(0.3))
        be.figure("up", 500, 512, 190, t + be.lag(0.3))
        be.icon("sun", 500, 275, 240, t, dur=1.0)
        be.icon("padlock", 800, 500, 130, t + be.lag(0.6), dur=0.7)
    else:
        be.icon("padlock", 330, 480, 190, ctx.t0 + be.lag(0.2), dur=0.7)
        be.icon("sun", 640, 330, 340, t, dur=1.0)
    be.text("FREE", 500, 670, 60, t + be.lag(0.8), color="accent")


def s_chat(be, ctx, sp):
    t = ctx.at("conversation", 0.3)
    be.icon("person", 160, 430, 170, ctx.t0 + be.lag(0.05))
    be.icon("person", 840, 430, 170, t)
    be.icon("chat", 500, 330, 300, t, dur=0.7)
    be.arrow((260, 430), (350, 380), t + be.lag(0.2), color="mute")
    be.arrow((740, 430), (650, 380), t + be.lag(0.4), color="mute")
    be.text("CONVERSATION", 500, 560, 32, t + be.lag(0.5))


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
        be.text("BECAUSE", xs[0], 250, 24, ctx.t0 + be.lag(0.3), color="mute")
        be.text("SO", xs[-1], 250, 24, ctx.at(nodes[-1].get("word"), 0.7), color="mute")


def s_growth(be, ctx, sp):
    up = sp.get("dir", "up") == "up"
    base, n = 620, 5
    for i in range(n):
        h = (110 + i * 80) if up else (430 - i * 80)
        x = 140 + i * 150
        tr = ctx.t0 + be.lag(0.2) + i * max(0.18, (ctx.t1 - ctx.t0 - 0.8) / (n + 1))
        be.rect(x, base - h, x + 100, base, tr, fill="soft", line="ink", w=4, r=6)
    pts = [(190 + i * 150, base - ((110 + i * 80) if up else (430 - i * 80)) - 50) for i in range(n)]
    be.line(pts, ctx.t0 + be.lag(0.9), color="accent" if up else "neg", w=10, dur=max(0.6, ctx.t1 - ctx.t0 - 1.2))
    be.icon("bars" if up else "trend_down", 840, 150, 140, ctx.t0 + be.lag(1.0))


def s_question(be, ctx, sp):
    t = ctx.t0 + be.lag(0.1)
    neg = sp.get("neg")
    if sp.get("fig"):
        be.figure("shrug", 260, 400, 400, t)
        qx = 640
    else:
        qx = 500
    be.icon("question", qx, 290, 300, t + be.lag(0.25), dur=0.8)
    be.icon(sp.get("icon", "coin"), qx - 80, 590, 110, t + be.lag(0.7), dur=0.5)
    be.arrow((qx - 10, 590), (qx + 90, 590), t + be.lag(0.9), color="mute")
    be.icon("x_circle" if neg else "check_circle", qx + 180, 590, 110, t + be.lag(1.0), dur=0.5, color="neg" if neg else "ink")




def _side(t):
    """One side of 'the difference between A and B': an icon, what it is called, and the amount if there is one."""
    low = t.lower()
    m = re.search(r"\$[\d,]+(?:\.\d+)?(?:\s?[kKmM])?", t)
    amount = m.group(0).upper() if m else ""
    if re.search(r"\b(own|owning|owns|assets?|generate|generates|producing|invest)\b", low):
        icon, tag = "bldg", "OWNING ASSETS"
        b = [c for c in concrete(t) if c["strong"]]
        if b:
            icon = b[0]["icon"]
    elif re.search(r"\b(earn|earning|earns|work|working|job|salary|paycheck|wages?)\b", low):
        icon, tag = "briefcase", "EARNING"
    else:
        icon, tag = pick_icon(t, 0), " ".join(t.split()[:2]).upper()
    return {"icon": icon, "tag": tag, "amount": amount, "per": "A YEAR" if re.search(r"\byear\b", low) else ""}


def s_compare(be, ctx, sp):
    """Two things side by side (earning vs owning ...). Stage 'left': the first one, the second still a question mark;
    stage 'both': the first is already there and the second arrives."""
    L, R = sp["left"], sp["right"]
    both = sp.get("stage") == "both"
    t_left = ctx.t0 - 5 if both else ctx.at(None, 0.12)
    t_right = ctx.at("owning", 0.15) if both else ctx.t1 + 5
    for side, (x0, x1), tr in ((L, (30, 470), t_left), (R, (530, 970), t_right)):
        cx = (x0 + x1) / 2
        be.rect(x0, 90, x1, 670, tr, fill="soft", line="ink", w=4, r=28)
        be.icon(side["icon"], cx, 270, 210, tr + be.lag(0.1), dur=0.6)
        be.text(side["tag"], cx, 440, 34, tr + be.lag(0.3))
        if side["amount"]:
            be.text(side["amount"], cx, 528, 62, tr + be.lag(0.5), color="accent")
        if side["per"]:
            be.text(side["per"], cx, 600, 30, tr + be.lag(0.6), color="mute")
    if not both:
        be.text("?", 750, 380, 190, ctx.t0 + be.lag(0.5), color="mute")
    be.circle(500, 380, 40, ctx.t0 - 5 if both else ctx.t0 + be.lag(0.4), fill="ink", line=None)
    be.text("VS", 500, 380, 30, ctx.t0 - 5 if both else ctx.t0 + be.lag(0.45), color="white")


def s_objects(be, ctx, sp):
    """The things the beat names, each in a card that appears at the word that names it (a photo instead of the drawing
    when one is available)."""
    nodes = sp["nodes"][:4]
    n = len(nodes)
    boxes = {1: [(230, 80, 770, 600)],
             2: [(60, 130, 480, 640), (520, 130, 940, 640)],
             3: [(20, 150, 330, 620), (345, 150, 655, 620), (670, 150, 980, 620)],
             4: [(50, 50, 480, 360), (520, 50, 950, 360), (50, 400, 480, 710), (520, 400, 950, 710)]}[n]
    for i, (nd, (x0, y0, x1, y1)) in enumerate(zip(nodes, boxes)):
        tr = ctx.at(nd.get("word"), 0.2 + 0.25 * i)
        cx, w, h = (x0 + x1) / 2, x1 - x0, y1 - y0
        _cross = (lambda: be.cross(cx, (y0 + y1) / 2, min(w, h) * 0.24, tr + be.lag(0.55), color="neg")) if nd.get("neg") else (lambda: None)
        photo = be.photo_path(nd, sp) if sp.get("photo") else None
        if photo:
            be.photo(photo, x0, y0, x1, y1, tr)
            be.rect(x0 + 30, y1 - 86, x1 - 30, y1 - 22, tr + be.lag(0.2), fill="white", line=None, r=14, dur=0.2)
            be.text(nd["label"], cx, y1 - 54, 34 if n < 4 else 30, tr + be.lag(0.25))
            _cross()
            continue
        be.rect(x0, y0, x1, y1, tr, fill="soft", line="ink", w=4, r=26)
        size = min(w * 0.62, h * 0.58)
        be.icon(nd["icon"], cx, y0 + h * 0.42, size, tr + be.lag(0.1), dur=0.6)
        be.text(nd["label"], cx, y1 - h * 0.12, 38 if n == 1 else 30 if n == 4 else 32, tr + be.lag(0.3))
        _cross()


# ------------------------------------------------------------------ calculations: the working, line by line
_VALUE = re.compile(r"^\s*[~≈]?\s*(-?\$?\d[\d,]*(?:\.\d+)?\s?(?:%|percent|million|billion|thousand|[KMB]\b)?)\s*(.*)$", re.I)
_NUM = r"(\$?\d[\d,]*(?:\.\d+)?(?:\s?(?:percent|%|million|billion|thousand))?)"
_OPS = {"divided by": "÷", "times": "×", "multiplied by": "×", "plus": "+", "minus": "−"}


def _tidy_calc(s):
    return re.sub(r"\s*percent\b", "%", s).strip()


def parse_calc(s):
    """'$100 x 40 units = $4,000 a month' -> {"left": "$100 × 40 units", "value": "$4,000", "unit": "a month"} (None without an =)."""
    if "=" not in s:
        return None
    left, right = s.split("=", 1)
    left = re.sub(r"(?<=[\w$%)])\s+[xX*]\s+(?=[\w$(])", " × ", left.strip())
    left = re.sub(r"\s+/\s+", " ÷ ", left).replace(" - ", " − ")
    m = _VALUE.match(right)
    if not m:
        return {"left": _tidy_calc(left), "value": _tidy_calc(right), "unit": ""}
    return {"left": _tidy_calc(left), "value": _tidy_calc(m.group(1)), "unit": m.group(2).strip()}


def _amount(v):
    """'$7 million' -> 7e6, '70%' -> 70, None when it is not a number."""
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(million|billion|thousand|[KMB])?", v, re.I)
    if not m:
        return None
    x = float(m.group(1).replace(",", ""))
    return x * {"million": 1e6, "billion": 1e9, "thousand": 1e3, "k": 1e3, "m": 1e6, "b": 1e9}.get((m.group(2) or "").lower(), 1)


def parse_stack(s):
    """'stack $10 million building = $7 million lender + $3 million equity | show 1' -> a bar split into its parts.
    `show N` reveals only the first N parts (the rest of the bar stays an open question)."""
    body, show = s.strip()[5:].strip(), None
    if "|" in body:
        body, opt = body.split("|", 1)
        m = re.search(r"show\s+(\d+)", opt)
        show = int(m.group(1)) if m else None
    if "=" not in body:
        return None
    total, rest = body.split("=", 1)
    parts = []
    for p in re.split(r"\s+\+\s+", rest.strip()):
        m = _VALUE.match(p)
        if m:
            parts.append({"value": _tidy_calc(m.group(1)), "label": m.group(2).strip().upper()})
    if len(parts) < 2:
        return None
    nums = [_amount(p["value"]) for p in parts]
    if None in nums or sum(nums) <= 0:
        nums = [1.0] * len(parts)
    for p, v in zip(parts, nums):
        p["share"] = v / sum(nums)
    return {"total": _tidy_calc(total).strip(), "parts": parts, "show": show or len(parts)}


def auto_calc(text):
    """Calculations that are spoken as a sentence ("$300,000 divided by 6 percent is $5 million") are shown without being written down."""
    out = []
    for m in re.finditer(_NUM + r"\s+(divided by|times|multiplied by|plus|minus)\s+" + _NUM + r"\s+(?:is|equals|makes|gives)\s+" + _NUM, text, re.I):
        a, op, b, r = m.groups()
        out.append({"left": _tidy_calc(a + " " + _OPS[op.lower()] + " " + b), "value": _tidy_calc(r), "unit": ""})
    return out


def spoken_amount_time(ctx, value):
    """The moment a number is said, even when it is said rounded ("$2.54 million" for 2,544,000) - the first spoken amount within 3 percent of `value`."""
    want = _amount(value)
    if not want:
        return None
    ws = ctx.words
    for j, (w, t) in enumerate(ws):
        digits = re.sub(r"[^0-9.]", "", w)
        if not digits or digits.count(".") > 1 or digits == ".":
            continue
        x = float(digits)
        nxt = re.sub(r"[^a-z]", "", ws[j + 1][0].lower()) if j + 1 < len(ws) else ""
        x *= {"million": 1e6, "billion": 1e9, "thousand": 1e3, "percent": 1}.get(nxt, 1)
        if "%" in value or "percent" in value.lower():
            x = float(digits)
        if want and abs(x - want) / want <= 0.03:
            return t
    return None


def s_calc(be, ctx, sp):
    """The working of a number: each row is the sum, then the answer in a box that appears when the answer is spoken."""
    rows = sp["rows"][:4]
    n = len(rows)
    rh = {1: 300, 2: 270, 3: 210, 4: 165}[n]
    top = (760 - n * rh) / 2
    cw = 0.78                                   # width of one capital per unit of px (the scene scales its type by 1.22)
    for i, r in enumerate(rows):
        y0 = top + i * rh
        vtok = re.sub(r"[^A-Za-z0-9]", "", r["value"].split()[0]) if r["value"] else ""
        tv = spoken_amount_time(ctx, r["value"])
        if tv is None:
            tv = ctx.at(vtok, min(0.6, 0.25 + 0.35 * (i + 1) / n) if vtok else 0.45)
        tl = max(ctx.t0 + be.lag(0.08), tv - 0.9)
        if tv - tl < 0.3:
            tv = tl + 0.3
        lpx = {1: 52, 2: 46, 3: 40, 4: 34}[n]
        lpx = min(lpx, 880 / max(1.0, len(r["left"]) * cw))
        vpx = {1: 100, 2: 84, 3: 66, 4: 52}[n]
        upx = max(24, lpx * 0.75)
        uw = len(r["unit"]) * upx * cw + 30 if r["unit"] else 0
        vpx = min(vpx, (900 - 130 - uw) / max(1.0, len(r["value"]) * cw))
        pw = len(r["value"]) * vpx * cw + 56
        total = 64 + pw + uw
        xs = 500 - total / 2
        yl, yv = y0 + rh * 0.27, y0 + rh * 0.69
        be.text(r["left"], 500, yl, lpx, tl, color="ink")
        be.text("=", xs + 22, yv, vpx * 0.7, tv - be.lag(0.05), color="mute")
        px0, px1 = xs + 64, xs + 64 + pw
        hh = vpx * 1.22 * 0.62
        be.rect(px0, yv - hh, px1, yv + hh, tv, fill="soft", line="accent", w=4, r=22)
        be.text(r["value"], (px0 + px1) / 2, yv, vpx, tv + be.lag(0.08), color="ink")
        if r["unit"]:
            be.text(r["unit"], px1 + 26, yv + 4, upx, tv + be.lag(0.16), anchor="l", color="mute")


def s_count(be, ctx, sp):
    """N of the thing, drawn one after the other from the moment the number is said, with the count and the name below."""
    n = max(2, min(20, int(sp["n"])))
    rows = 1 if n <= 3 else 2 if n <= 8 else 3 if n <= 12 else 4
    cols = -(-n // rows)
    cw, ch = 880 / cols, 560 / rows
    size = min(cw * 0.82, ch * 0.8, 260)
    t0 = ctx.at(sp.get("word"), 0.15)
    step = min(0.22, max(0.06, (ctx.t1 - 0.12 - t0 - 0.5) / n))
    for i in range(n):
        r, c = divmod(i, cols)
        left = n - r * cols if r == rows - 1 else cols                      # the last row is centred
        x = 500 + (c - (left - 1) / 2) * cw
        y = 70 + ch * (r + 0.5) + (30 if rows == 1 else 0)
        be.icon(sp["icon"], x, y, size, t0 + i * step, dur=0.3)
    be.text("%d %s" % (n, sp["label"]), 500, 690, 46, t0 + n * step + be.lag(0.1), color="accent")


def s_stack(be, ctx, sp):
    """One whole as a bar split into its parts (a $10 million building = $7 million lender + $3 million equity). Each part grows in when its amount
    is said; a part not yet named stays an open box with a question mark."""
    parts, show = sp["parts"], sp["show"]
    x0, x1, y0, h = 60, 940, 300, 190
    be.text(sp["total"], 500, 170, 54 if len(sp["total"]) < 22 else 42, ctx.t0 + be.lag(0.05), color="ink")
    be.line([(x0, 240), (x1, 240)], ctx.t0 + be.lag(0.1), color="mute", w=3, dur=0.3)
    x = x0
    for i, p in enumerate(parts):
        w = (x1 - x0) * p["share"]
        tok = re.sub(r"[^A-Za-z0-9]", "", p["value"].split()[0])
        if i < show:
            tr = ctx.at(tok, 0.25 + 0.4 * i)
            be.rect(x, y0, x + w - 6, y0 + h, tr, fill="accent" if i == 0 else "soft", line="ink", w=5, r=22)
            col = "white" if i == 0 else "ink"
            be.text(p["label"], x + w / 2 - 3, y0 + h * 0.34, 34, tr + be.lag(0.12), color=col)
            be.text(p["value"], x + w / 2 - 3, y0 + h * 0.70, 46 if w > 300 else 36, tr + be.lag(0.2), color=col)
            be.text("%d%%" % round(p["share"] * 100), x + w / 2 - 3, y0 + h + 62, 40, tr + be.lag(0.3), color="mute")
        else:
            be.rect(x, y0, x + w - 6, y0 + h, ctx.t0 + be.lag(0.15), fill=None, line="mute", w=4, r=22)
            be.text("?", x + w / 2 - 3, y0 + h / 2, 110, ctx.t0 + be.lag(0.3), color="mute")
        x += w
    if sp.get("eq"):
        be.text(sp["eq"], 500, 640, 40, ctx.at(re.sub(r"[^A-Za-z0-9]", "", parts[min(show, len(parts)) - 1]["value"].split()[0]), 0.5) + be.lag(0.3), color="accent")


def s_cards(be, ctx, sp):
    """First / Second / Third as numbered cards that stay on screen. The ones already explained are simply there, the current one is
    highlighted and (in the beat where its ordinal is said) appears at that word."""
    items, cur = sp["items"][:5], sp["current"]
    n = len(items) if sp.get("all") else cur + 1
    rh = {1: 300, 2: 250, 3: 200, 4: 145, 5: 110}[len(items)]
    gap = 22
    block = len(items) * rh + (len(items) - 1) * gap
    top = (760 - block) / 2
    be.reserve(40, top, 960, top + block)                  # the same size in every beat, so the cards do not move when the next one arrives
    roles, alln = sp.get("roles"), sp.get("all")
    for i in range(min(n, len(items))):
        it = items[i]
        now = bool(alln) or i == cur
        y0 = top + i * (rh + gap)
        cy = y0 + rh / 2
        sw = sp.get("starts_words") or ({cur: sp.get("word")} if sp.get("starts") else {})
        tr = ctx.at(sw[i], 0.08 + 0.12 * len(sw) * (i / max(1, len(items)))) if i in sw else ctx.t0 - 5
        quick = 0.001 if tr < ctx.t0 - 1 else 0.35
        late = lambda d: tr + (be.lag(d) if quick > 0.01 else 0)
        be.rect(40, y0, 960, y0 + rh, tr, fill="soft" if now else "white", line="accent" if now else "ink", w=6 if now else 4, r=26, dur=quick)
        if roles:                                                    # a role (who) with what they bring, under it
            be.circle(135, cy, rh * 0.36, tr, fill="white", line="accent" if now else "ink", w=4, dur=min(0.3, quick))
            be.icon(it["icon"], 135, cy, rh * 0.46, late(0.1), dur=0.001 if quick < 0.01 else 0.4)
            be.text(it["label"], 255, cy - (rh * 0.17 if it.get("sub") else 0), 44 if len(items) <= 3 else 40, late(0.12), anchor="l", color="ink", dur=min(0.22, quick))
            if it.get("sub"):
                be.text(it["sub"], 255, cy + rh * 0.2, 30 if len(items) <= 3 else 27, late(0.25), anchor="l", color="mute", dur=min(0.22, quick))
            continue
        be.circle(120, cy, rh * 0.26, tr, fill="accent" if now else "ink", line=None, dur=min(0.3, quick))
        be.text(str(i + 1), 120, cy, rh * 0.26, late(0.05), color="white", dur=min(0.2, quick))
        be.icon(it["icon"], 262, cy, rh * 0.5, late(0.1), dur=0.001 if quick < 0.01 else 0.4)
        be.text(it["label"], 340, cy, 44 if len(items) <= 3 else 38, late(0.12), anchor="l", color="ink", dur=min(0.22, quick))


def s_ask(be, ctx, sp):
    """An open question put to the viewer: YOU, a big question mark, and the thing they are asked about."""
    t = ctx.t0 + be.lag(0.08)
    be.icon("person", 190, 360, 250, t, dur=0.6)
    be.text("YOU", 190, 560, 46, t + be.lag(0.3))
    be.icon("question", 500, 330, 320, t + be.lag(0.5), dur=0.8)
    be.arrow((310, 400), (390, 400), t + be.lag(0.7), color="mute")
    be.icon(sp.get("icon", "scroll"), 810, 360, 250, t + be.lag(0.9), dur=0.6)
    be.text(sp.get("label", "THE DEAL"), 810, 560, 46, t + be.lag(1.1))


def s_keyword(be, ctx, sp):
    """The keyword offer. A comment box with the word typed in it, an arrow, and the message that arrives."""
    t0 = ctx.at("comment", 0.08)
    be.rect(110, 120, 890, 320, t0, fill="white", line="ink", w=5, r=40)
    be.circle(200, 220, 44, t0 + be.lag(0.1), fill="soft", line="ink", w=4)
    be.icon("person", 200, 220, 56, t0 + be.lag(0.12), dur=0.3, claim=False)
    tw = ctx.at(sp["word"].split()[-1].lower(), 0.25)
    be.text(sp["word"], 560, 222, 92 if len(sp["word"]) <= 6 else 62, tw, color="accent")
    ta = ctx.at("send", 0.55)
    be.arrow((500, 350), (500, 440), ta, color="mute")
    be.icon("mail", 500, 545, 200, ta + be.lag(0.3), dur=0.5)
    be.text(sp["label"], 500, 700, 46 if len(sp["label"]) < 22 else 36, ta + be.lag(0.6))


def s_ab(be, ctx, sp):
    """A poll. Two big cards, A and B, and the question."""
    t = ctx.t0 + be.lag(0.1)
    be.rect(100, 150, 460, 530, t + be.lag(0.1), fill="soft", line="ink", w=6, r=34)
    be.text("A", 280, 345, 220, t + be.lag(0.2), color="ink")
    be.rect(540, 150, 900, 530, t + be.lag(0.5), fill="soft", line="ink", w=6, r=34)
    be.text("B", 720, 345, 220, t + be.lag(0.6), color="accent")
    be.circle(500, 340, 46, t + be.lag(0.4), fill="ink", line=None)
    be.text("OR", 500, 340, 32, t + be.lag(0.45), color="white")
    be.text("WHICH ONE?", 500, 650, 60, t + be.lag(0.9))


def s_follow(be, ctx, sp):
    """The call to action: a profile and a Follow button."""
    t = ctx.at("follow", 0.15)
    be.circle(500, 290, 170, t, fill="soft", line="ink", w=5)
    be.icon("person", 500, 290, 200, t + be.lag(0.15), dur=0.5)
    be.rect(250, 530, 750, 670, t + be.lag(0.4), fill="accent", line=None, r=70)
    be.text("+ FOLLOW", 500, 600, 58, t + be.lag(0.55), color="white")


SCENES = {"pictogram": s_pictogram, "income_stop": s_income_stop, "steps": s_steps, "ceiling": s_ceiling, "hours": s_hours,
          "own": s_own, "hub": s_hub, "bank": s_bank, "freedom": s_freedom, "chat": s_chat, "flow": s_flow, "growth": s_growth,
          "question": s_question, "objects": s_objects, "compare": s_compare, "calc": s_calc, "count": s_count, "cards": s_cards, "stack": s_stack, "ask": s_ask, "follow": s_follow, "keyword": s_keyword, "ab": s_ab}


def draw(be, ctx, spec):
    be.deadline = ctx.t1 - 0.12
    be.earliest = ctx.t0 + 0.06
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
        self.s = anim_scale()
        self.deadline = None             # the second by which everything must be fully drawn (the beat's end, less a little)
        self.earliest = 0.0              # the beat's start

    def _tr(self, trig):
        """A trigger never later than half a second before the deadline: a thing named at the very end of the beat is shown
        a little early instead of flashing up as the camera leaves."""
        if self.deadline is None:
            return trig
        return min(trig, max(self.earliest, self.deadline - 0.5))

    def _d(self, dur, trig):
        """How long an element may take to appear: its own length at the current level, but only as long as the time that
        is left before the deadline allows. Too little room means it simply appears (no animation)."""
        d = dur * self.s
        if self.deadline is not None:
            d = min(d, max(0.0, self.deadline - trig - 0.04))
        return 0.001 if d < 0.07 else d

    def lag(self, x):
        """A small delay (an element's label, the next step ...) at the current animation level."""
        return x * self.s

    def P(self, x, y):
        return (self.ox + self.k * x, self.oy + self.k * y)

    def _uid(self, kind):
        self._n += 1
        return "%s%d" % (kind, self._n)

    # ---- strokes: icons and the figure
    def _strokes(self, spec, x, y, size, trig, dur, lw, color, accent, until, key, claim_w=1.0, claim=True):
        trig = self._tr(trig)
        if self.t < trig or (until is not None and self.t >= until):
            return
        q = _ease_out((self.t - trig) / self._d(dur, trig))
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
        trig = self._tr(trig)
        if self.t < trig or (until is not None and self.t >= until):
            return
        q = _ease_out((self.t - trig) / self._d(dur, trig))
        seg = _prog([self.P(*p) for p in pts], q)
        if len(seg) >= 2:
            self._line(seg, self.color(color), max(3.0, w * self.k))

    def arrow(self, p0, p1, trig, color="ink", w=6, dur=0.45):
        self.line([p0, p1], trig, color, w, dur)
        trig = self._tr(trig)
        d = self._d(dur, trig)
        if self.t >= trig + d * 0.8:
            a = _ease_out((self.t - trig - d * 0.8) / self._d(0.15, trig + d * 0.8))
            (x0, y0), (x1, y1) = self.P(*p0), self.P(*p1)
            d = math.dist((x0, y0), (x1, y1)) or 1.0
            ux, uy = (x1 - x0) / d, (y1 - y0) / d
            s = 20 * self.k * a
            self._line([(x1 - ux * s - uy * s * 0.6, y1 - uy * s + ux * s * 0.6), (x1, y1),
                        (x1 - ux * s + uy * s * 0.6, y1 - uy * s - ux * s * 0.6)], self.color(color), max(3.0, w * self.k))

    def rect(self, x0, y0, x1, y1, trig, fill=None, line="ink", w=4, r=10, until=None, dur=0.35):
        trig = self._tr(trig)
        if self.t < trig or (until is not None and self.t >= until):
            return
        q = _ease_out((self.t - trig) / self._d(dur, trig))
        ax, ay = self.P(x0, y1 - (y1 - y0) * q)
        bx, by = self.P(x1, y1)
        self._rect(ax, ay, bx, by, self.color(fill) if fill else None, self.color(line) if line else None, max(2.0, w * self.k), r * self.k)

    def circle(self, x, y, r, trig, fill=None, line="ink", w=4, until=None, dur=0.3):
        trig = self._tr(trig)
        if self.t < trig or (until is not None and self.t >= until):
            return
        q = _ease_out((self.t - trig) / self._d(dur, trig))
        cx, cy = self.P(x, y)
        self._ellipse(cx, cy, r * self.k * q, self.color(fill) if fill else None, self.color(line) if line else None, max(2.0, w * self.k))

    def text(self, s, x, y, px, trig, anchor="m", color="ink", dur=0.22):
        cx, cy = self.P(x, y)
        trig = self._tr(trig)
        self._text(s, cx, cy, px * self.k * 1.22, self.color(color), anchor, trig, self._d(dur, trig), self._uid("t"))

    def photo(self, path, x0, y0, x1, y1, trig, r=26, dur=0.4):
        """A photo cropped to the box, with rounded corners."""
        trig = self._tr(trig)
        if self.t < trig:
            return
        q = _ease_out((self.t - trig) / self._d(dur, trig))
        ax, ay = self.P(x0, y0)
        bx, by = self.P(x1, y1)
        self._photo(path, ax, ay, bx, by, q, r * self.k)

    def photo_path(self, node, sp):
        return None

    def reserve(self, x0, y0, x1, y1):
        """Tell a backend that measures a scene (to fit it to its frame) how big the scene will be once everything has appeared."""
        pass

    def check(self, x, y, size, trig, color="accent"):
        self.line([(x - size, y), (x - size * 0.25, y + size * 0.8), (x + size * 1.05, y - size * 0.8)], trig, color, 9, 0.3)

    def cross(self, x, y, size, trig, color="neg"):
        self.line([(x - size, y - size), (x + size, y + size)], trig, color, 9, 0.2)
        self.line([(x + size, y - size), (x - size, y + size)], trig + self.lag(0.12), color, 9, 0.2)

    def flow(self, p0, p1, trig, color="accent", n=3):
        """Little dots travelling along a path (money moving)."""
        trig = self._tr(trig)
        if self.t < trig:
            return
        for j in range(n):
            u = ((self.t - trig) * 0.7 + j / n) % 1.0 if self.s >= 0.9 else (j + 0.5) / n
            x, y = p0[0] + (p1[0] - p0[0]) * u, p0[1] + (p1[1] - p0[1]) * u
            cx, cy = self.P(x, y)
            self._ellipse(cx, cy, 11 * self.k, self.color(color), None, 1)



class Extent(Backend):
    """Draws a scene to nothing and records the box it covers (in scene units), so a style can enlarge the scene to fill its frame."""

    def __init__(self, k=1.0):
        super().__init__(99.0, 0.0, 0.0, k)
        self.pts = []
        self.trigs = []
        self.char_w = 22

    def color(self, name):
        return name

    def _tr(self, trig):
        self.trigs.append(trig)
        return trig

    def _line(self, pts, color, w):
        self.pts += list(pts)

    def _rect(self, x0, y0, x1, y1, fill, line, w, r):
        self.pts += [(x0, y0), (x1, y1)]

    def _ellipse(self, cx, cy, r, fill, line, w):
        self.pts += [(cx - r, cy - r), (cx + r, cy + r)]

    def _text(self, s, x, y, px, color, anchor, trig, dur, key):
        w = len(s) * px * 0.64
        self.pts += [(x - (w / 2 if anchor == "m" else 0), y - px / 2), (x + (w / 2 if anchor == "m" else w), y + px / 2)]

    def _claim(self, key, box):
        pass

    def reserve(self, x0, y0, x1, y1):
        self.pts += [(x0, y0), (x1, y1)]

    def photo_path(self, node, sp):
        return photo_for(node)

    def _photo(self, path, ax, ay, bx, by, q, r):
        self.pts += [(ax, ay), (bx, by)]


_MEASURED = {}


def measure(ctx, spec):
    """(x0, y0, x1, y1, first) of everything the scene draws, in scene units (the scene box is 1000 x 760), and the moment its first element starts."""
    key = (id(spec), round(ctx.t0, 3), round(ctx.t1, 3))
    if key not in _MEASURED:
        be = Extent()
        try:
            draw(be, ctx, spec)
        except Exception:
            be.pts = []
        first = min(be.trigs) if be.trigs else None
        if be.pts:
            xs, ys = [q[0] for q in be.pts], [q[1] for q in be.pts]
            _MEASURED[key] = (min(xs), min(ys), max(xs), max(ys), first)
        else:
            _MEASURED[key] = (0.0, 0.0, 1000.0, 760.0, first)
    return _MEASURED[key]


def fit_box(ctx, spec, ox, oy, k, cap=1.9):
    """The scene is drawn at its normal size inside the box (ox, oy, 1000 k x 760 k). This returns (ox, oy, k) for the same box with the scene
    enlarged to fill it (a lone icon is shown big, never beyond `cap` times the normal size) and centred."""
    ex0, ey0, ex1, ey1, _f = measure(ctx, spec)
    kk = max(k, min(cap * k, 1000 * k / (ex1 - ex0 + 60.0), 760 * k / (ey1 - ey0 + 60.0)))
    return ox + 500 * k - kk * (ex0 + ex1) / 2, oy + 380 * k - kk * (ey0 + ey1) / 2, kk


# ------------------------------------------------------------------ photos (shared helper)
_IMG = {}


def photo_image(path, w, h, r):
    """The photo cropped to w x h (cover), with rounded corners, as RGBA. Cached."""
    from PIL import Image, ImageDraw
    key = (str(path), w, h, r)
    if key not in _IMG:
        if len(_IMG) > 24:
            _IMG.clear()
        im = Image.open(path).convert("RGB")
        k = max(w / im.width, h / im.height)
        im = im.resize((max(w, int(im.width * k + 0.5)), max(h, int(im.height * k + 0.5))), Image.LANCZOS)
        left, top = (im.width - w) // 2, (im.height - h) // 2
        im = im.crop((left, top, left + w, top + h)).convert("RGBA")
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=max(1, r), fill=255)
        im.putalpha(mask)
        _IMG[key] = im
    return _IMG[key]


def photo_for(node):
    """A photo on disk for this node (or None) - only when the photo setting allows it."""
    import photos
    return photos.lookup(node.get("icon", ""), node.get("label", ""))



# ------------------------------------------------------------------ how much the elements animate
_ANIM = {"full": 1.0, "reduced": 0.25, "minimal": 0.0}
_ANIM_CACHE = {}


def anim_scale():
    """Multiplier for animation lengths and for the small delays between an element and its label (Export tab: Animation).
    full = draw-on and pops as designed, reduced = quick, minimal = elements simply appear."""
    try:
        import os
        import studio_config
        from pathlib import Path
        import projects
        path = Path(os.environ[studio_config.ENV]) if os.environ.get(studio_config.ENV) else projects.config_path()
        stamp = path.stat().st_mtime if path.exists() else 0
        key = (str(path), stamp)
        if key not in _ANIM_CACHE:
            _ANIM_CACHE.clear()
            _ANIM_CACHE[key] = _ANIM.get(studio_config.load()["render"].get("animation", "reduced"), 0.25)
        return _ANIM_CACHE[key]
    except Exception:
        return 0.25



_SAFE_CACHE = {}


def safe_area():
    """True when the Reels / Shorts safe area is on (Export tab): on 9:16 nothing important sits under the profile bar at the top,
    the caption and buttons at the bottom, or the like / comment / share column on the right."""
    try:
        import os
        import studio_config
        from pathlib import Path
        import projects
        path = Path(os.environ[studio_config.ENV]) if os.environ.get(studio_config.ENV) else projects.config_path()
        stamp = path.stat().st_mtime if path.exists() else 0
        key = (str(path), stamp)
        if key not in _SAFE_CACHE:
            _SAFE_CACHE.clear()
            _SAFE_CACHE[key] = studio_config.load()["render"].get("safe_area", "reels") == "reels"
        return _SAFE_CACHE[key]
    except Exception:
        return True


# the 9:16 frame (1080 x 1920): where the apps cover the picture
SAFE_LEFT, SAFE_RIGHT = 108, 130          # the right column holds the like / comment / share buttons
SAFE_TOP, SAFE_BOTTOM_Y = 270, 1500       # profile bar above; caption, music line and buttons below 1500


def head_dur():
    """How long a headline line takes to appear at the current animation level."""
    return max(0.05, 0.17 * anim_scale())


_PLANS = {}


_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}
_ORD_CACHE = {}
_FILLER = {"you", "can", "could", "should", "will", "would", "may", "might", "sometimes", "often", "also", "just", "really", "actually", "then", "simply",
           "to", "need", "must", "have", "get", "usually", "always", "even", "still"}
_ORD_ICONS = ["rocket", "target", "key", "gear", "bank", "link"]


def ordinal_label(sentence):
    """'you can start small' -> 'start small'; 'sellers sometimes finance part of the price' -> 'sellers finance part'."""
    head = sentence.split(",")[0] if "," in sentence and len(sentence.split(",")[0].split()) >= 2 else sentence      # "your experience, or the team you bring" -> "your experience"
    ws = [w.strip(".,") for w in re.findall(r"[A-Za-z0-9'$%.,-]+", head) if w.lower().strip(".,") not in _FILLER]
    while len(ws) > 1 and ws[0].lower() in ("the", "a", "an", "your", "my", "our", "their", "his", "her"):
        ws.pop(0)                                                                           # no leading "your" or "the"
    ws = ws[:4]
    while len(ws) > 1 and ws[-1].lower() in ("of", "the", "a", "an", "and", "or", "to", "in", "for", "with", "your", "my", "our", "their"):
        ws.pop()
    return " ".join(ws).upper()


def ordinal_map(story):
    """{(clip, beat): {"items", "current", "starts", "word"}} for a run of First / Second / Third ...: the cards build up and stay while each
    one is explained (from its own beat to the beat before the next ordinal; the last one for one more beat)."""
    key = id(story)
    if key in _ORD_CACHE:
        return _ORD_CACHE[key]
    order = [(int(c), i) for c in sorted(story["feats"], key=int) for i in range(len(story["feats"][c]))]
    found = []
    for pos, (c, i) in enumerate(order):
        for m in re.finditer(r"(?:^|[.!?]\s+)(first|second|third|fourth|fifth)\b,?\s+([^.!?]*)", story["feats"][str(c)][i]["text"], re.I):
            found.append((pos, _ORDINALS[m.group(1).lower()], m.group(1).lower(), m.group(2).strip()))      # several ordinals can share one beat
    out = {}
    run = []
    for f in found + [None]:
        if f is not None and ((not run and f[1] == 1) or (run and f[1] == run[-1][1] + 1 and f[0] - run[-1][0] <= 8)):
            run.append(f)
            continue
        if len(run) >= 2:
            used, items = set(), []
            for k, r in enumerate(run):
                label = ordinal_label(r[3]) or ("STEP %d" % r[1])
                low = label.lower()
                icon = "bank" if re.search(r"financ|loan|lend|mortgage", low) else "link" if re.search(r"partner|together|join|team|investor", low) else pick_icon(label, k)
                if icon in used or icon in ("bulb",):
                    icon = next((x for x in _ORD_ICONS if x not in used), "gear")
                used.add(icon)
                items.append({"label": label, "icon": icon, "word": r[2]})
            last_pos = run[-1][0]
            for pos in range(run[0][0], min(len(order), last_pos + 2)):
                starting = {k: r[2] for k, r in enumerate(run) if r[0] == pos}
                cur_k = max(k for k, r in enumerate(run) if r[0] <= pos)
                out[order[pos]] = {"items": items, "current": cur_k, "starts": bool(starting), "starts_words": starting,
                                   "word": run[cur_k][2]}
        run = [f] if f is not None and f[1] == 1 else []
    _ORD_CACHE[key] = out
    return out


_ROLE_RX = re.compile(r"^(?:the |a |an )?(deal sponsor|sponsor|lenders?|investors?|operators?|brokers?|buyers?|sellers?|developers?|property managers?|managers?|"
                      r"general partners?|limited partners?|partners?|tenants?|owners?)\b\s*(.*)$", re.I)
_ROLE_ICON = {"sponsor": "target", "lender": "bank", "investor": "moneybag", "operator": "gear", "broker": "for_sale", "buyer": "person",
              "seller": "person", "developer": "crane", "manager": "gear", "partner": "link", "tenant": "keys_house", "owner": "key"}
_ROLE_CACHE = {}


def _role_key(word):
    w = re.sub(r"^(deal|property|general|limited) ", "", word.lower())
    w = re.sub(r"s$", "", w)
    return w.split()[-1] if w else w


def roles_map(story):
    """A run of sentences that each start with who does it ("The lender provides financing. Investors provide capital. The operator runs
    the property.") becomes a stack of role cards (who, and what they bring) that builds up, one card per role, like First / Second / Third.
    Several roles can start inside one beat, each card then appears at its own word."""
    key = id(story)
    if key in _ROLE_CACHE:
        return _ROLE_CACHE[key]
    order = [(int(c), i) for c in sorted(story["feats"], key=int) for i in range(len(story["feats"][c]))]
    events = []                                       # (position of the beat, role key, label, what they do)
    for pos, (c, i) in enumerate(order):
        for sent in re.split(r"(?<=[.!?])\s+", story["feats"][str(c)][i]["text"]):
            m = _ROLE_RX.match(sent.strip())
            if m:
                rest = re.split(r",| who | that | which ", m.group(2))[0].strip(" .")
                events.append((pos, _role_key(m.group(1)), re.sub(r"^deal ", "", m.group(1), flags=re.I).upper(),
                               " ".join(rest.split()[:4]), sent.lower().startswith(("a ", "an "))))
    out = {}
    runs, cur = [], []
    for ev in events:                                 # consecutive events close together form a run
        if cur and ev[0] - cur[-1][0] > 3:
            runs.append(cur)
            cur = []
        cur.append(ev)
    runs.append(cur)
    for run in runs:
        roles, first, label, desc = [], {}, {}, {}
        for pos, rk, lab, rest, intro in run:
            if rk not in first:
                roles.append(rk)
                first[rk], label[rk] = pos, lab
            if rest and (rk not in desc or not intro):
                desc[rk] = rest
        if len(roles) < 3:
            continue
        roles = roles[:5]
        items = [{"label": label[r], "icon": _ROLE_ICON.get(r, "person"), "sub": desc.get(r, "")} for r in roles]
        last_first = first[roles[-1]]
        for pos in range(first[roles[0]], min(len(order), last_first + 3)):
            starting = {k: r for k, r in enumerate(roles) if first[r] == pos}
            cur_k = max(k for k, r in enumerate(roles) if first[r] <= pos)
            out[order[pos]] = {"items": items, "current": cur_k, "starts": bool(starting), "starts_words": {k: r.split()[-1] for k, r in starting.items()},
                               "roles": True, "all": pos > last_first}
    _ROLE_CACHE[key] = out
    return out


def verb_triple(text):
    """'You need to bring real value, understand the risks, and earn people's trust.' -> three things to do. None if it is not that."""
    for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
        body = sent.strip(" .!?")
        chunks = [c.strip() for c in re.split(r",\s*(?:and\s+)?|\s+and\s+", body) if c.strip()]
        if len(chunks) < 3 or len(chunks) > 4:
            continue
        chunks[0] = re.sub(r"^.*\bto\s+", "", chunks[0], count=1) if re.search(r"\bto\s+\w", chunks[0]) else chunks[0]
        chunks = [re.split(r"\s+(?:can|will|could|would|should|may|might)\s+", c)[0] for c in chunks]
        if all(re.match(VERBS, c.lower()) and 2 <= len(c.split()) <= 6 for c in chunks):
            low = text.lower()
            out = []
            for c in chunks:
                pos = low.find(c.lower())
                out.append({"label": c[:1].upper() + c[1:], "k": nwords(text[:pos]) if pos >= 0 else len(out) * 3})
            return out
    return None


def scene_of(story, cid, idx):
    """The planned scene of beat `idx` of clip `cid` (planned on first use from the beat's words, then remembered)."""
    key = (id(story), cid, idx)
    if key not in _PLANS:
        feats = story["feats"][str(cid)]
        f = feats[idx]
        if f.get("scene"):
            _PLANS[key] = dict(f["scene"])
        elif not f.get("calc") and ordinal_map(story).get((cid, idx)):          # First / Second / Third cards
            _PLANS[key] = dict(ordinal_map(story)[(cid, idx)], type="cards")
        elif not f.get("calc") and roles_map(story).get((cid, idx)):            # who does what, as role cards
            _PLANS[key] = dict(roles_map(story)[(cid, idx)], type="cards")
        else:
            if idx > 0:
                prev = feats[idx - 1]["text"]
            else:
                prev = story["feats"][str(cid - 1)][-1]["text"] if str(cid - 1) in story["feats"] else story.get("hook", "")
            nxt = ""
            if idx + 1 < len(feats):
                nxt = feats[idx + 1]["text"]
            elif str(cid + 1) in story["feats"]:
                nxt = story["feats"][str(cid + 1)][0]["text"]
            _PLANS[key] = plan(f, prev, nxt)
        if idx > 0 or cid > 1:
            # the same picture twice in a row is dull: a repeated scene becomes a pictogram of what the beat mentions
            pc, pi = (cid, idx - 1) if idx > 0 else (cid - 1, len(story["feats"][str(cid - 1)]) - 1)
            before = scene_of(story, pc, pi)
            if before.get("type") == _PLANS[key].get("type") and _PLANS[key]["type"] not in ("pictogram", "hub", "steps", "question", "objects", "compare", "calc", "count", "cards", "stack", "ask", "follow", "keyword", "ab"):
                kws = _kw_nodes(f["text"])
                _PLANS[key] = {"type": "pictogram", "pose": "stand", "nodes": kws[:3] or [{"icon": pick_icon(f["text"], 0), "label": "", "word": ""}]}
        sp = _PLANS[key]
        # the figure is for moments where an emotion carries the idea (stuck under a ceiling, freedom, a climb, a shrug) -
        # and never in more than one of three beats in a row
        wants = sp.get("type") in ("ceiling", "freedom") or (sp.get("type") == "question" and sp.get("neg"))
        recent = any(_prev_fig(story, cid, idx, back) for back in (1, 2))
        sp["fig"] = bool(wants and not recent)
        if sp.get("type") == "objects":                    # a real photo of the things, now and then (setting: off / sometimes / often)
            import photos
            mode = photos.mode()
            have = any(photos.lookup(n["icon"], n.get("label", "")) for n in sp["nodes"])
            recent_photo = any(_prev_flag(story, cid, idx, back, "photo") for back in (1, 2))
            sp["photo"] = bool(mode != "off" and have and (mode == "often" or not recent_photo))
    return _PLANS[key]


def _prev_fig(story, cid, idx, back):
    return _prev_flag(story, cid, idx, back, "fig")


def _prev_flag(story, cid, idx, back, flag):
    """Whether the beat `back` places before (cid, idx) has `flag` set (fig / photo)."""
    order = [(int(c), i) for c in sorted(story["feats"], key=int) for i in range(len(story["feats"][c]))]
    pos = order.index((cid, idx)) - back
    if pos < 0:
        return False
    pc, pi = order[pos]
    return bool(scene_of(story, pc, pi).get(flag))


def hook_icon(story):
    """The picture of the hook: the first concrete thing it names (a car, a building ...), else the icon the parser chose."""
    for c in concrete(story.get("hook", "")):
        if c["strong"]:
            return c["icon"]
    return story.get("hook_icon", "bulb")
