"""Read WhatsApp production / dispatch messages and match each line to an item.
Nothing here saves anything: it only proposes. The screen shows every line for you to check first."""
import re, hashlib

IGNORE = re.compile(r"(loading|delivery|edited|deleted|omitted|attached|image|video|sticker|drip dispatch|^dispatch\b|production details|good morning|^note)", re.I)
UNIT = r"(?:rolls?|roll|bags?|bag|boxes|box|pcs|pieces|piece|nos|bundles?|sets?|kg)"
QTY_END = re.compile(r"[-–:=]\s*(\d+(?:\.\d+)?)\s*(" + UNIT + r")?\s*\.?\s*$", re.I)
PHONE = re.compile(r"^\s*(?:\+?91[\s-]*)?\d{10}\s*$")
VEHICLE = re.compile(r"\bK\s*A\s*[-\s]?\s*(\d{1,2})\s*[-\s]?\s*([A-Z]{1,3})\s*[-\s]?\s*(\d{3,4})\b", re.I)
WA_HEAD = re.compile(r"^‎?\[\d{1,2}/\d{1,2}/\d{2,4},[^\]]*\]\s*[^:]*:\s*")
DATE = re.compile(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})")


def _clean(t):
    t = (t or "").replace("‎", "").replace(" ", " ").replace("\xa0", " ")
    out = []
    for ln in t.splitlines():
        ln = WA_HEAD.sub("", ln.strip())
        out.append(ln.strip())
    return out


def find_date(lines):
    for ln in lines[:12]:
        m = DATE.search(ln)
        if m and not re.search(r"\d{10}", ln):
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 100: y += 2000
            if 1 <= d <= 31 and 1 <= mo <= 12: return "%04d-%02d-%02d" % (y, mo, d)
    return ""


def find_vehicle(lines):
    for ln in lines:
        m = VEHICLE.search(ln)
        if m: return ("KA%02d%s%s" % (int(m.group(1)), m.group(2).upper(), m.group(3)))
    return ""


def split_qty(line):
    """'16R nisi 300mtrs 10kg 40cm -112rolls' -> ('16R nisi 300mtrs 10kg 40cm', 112.0, 'rolls') or None"""
    m = QTY_END.search(line)
    if not m: return None
    desc = line[:m.start()].strip(" -–:=")
    if not desc: return None
    return desc, float(m.group(1)), (m.group(2) or "").lower()


def parse_production(text):
    lines = _clean(text)
    date = find_date(lines); shift = ""
    for ln in lines[:12]:
        m = re.search(r"shift\s*[-:]?\s*([AB])\b", ln, re.I)
        if m: shift = m.group(1).upper(); break
    out = []
    for ln in lines:
        if not ln or IGNORE.search(ln) or re.match(r"^(date|shift)\b", ln, re.I): continue
        s = split_qty(ln)
        if s: out.append(dict(text=s[0], qty=s[1], unit=s[2]))
    return dict(kind="production", date=date, shift=shift, lines=out)


def parse_dispatch(text):
    lines = _clean(text)
    date = find_date(lines); vehicle = find_vehicle(lines)
    groups = []; cur = None; pend = []; ctx = ""
    def start():
        nonlocal cur, pend, ctx
        if cur is None:
            cur = dict(party=re.sub(r"\s+", " ", re.sub(r"\+?\d[\d\s-]{8,}\d", "", " ".join(pend))).strip(), lines=[]); groups.append(cur); pend = []
    for ln in lines:
        if not ln:
            continue
        if IGNORE.search(ln) and not split_qty(ln): continue
        if VEHICLE.search(ln) and not split_qty(ln): continue
        if PHONE.match(ln): continue
        if re.match(r"^\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\s*$", ln): continue
        s = split_qty(ln)
        if s:
            desc, q, u = s
            # a short line like "20cm" or "40cm 7kg" after a heading such as "8mil :" belongs to that heading
            if ctx and not re.search(r"mil|mm|plain|round|flat|\d\s*[rp]\b|pipe|filter|valve|sprinkler|tube|drip", desc, re.I):
                desc = ctx + " " + desc
            if cur is None or (pend and cur):   # new customer started by the text lines just before
                cur = None; start()
            elif cur is None: start()
            cur["lines"].append(dict(text=desc, qty=q, unit=u))
        elif ln.endswith(":") and not re.search(r"\d{10}", ln) and re.search(r"\d\s*mil|mm|plain|round|flat|pipe", ln, re.I):
            ctx = ln.rstrip(": ").strip()
        else:
            # a customer / place line
            if cur is not None and cur["lines"] and not pend: cur = None   # first text line after items = next customer begins
            ctx = ""; pend.append(re.sub(r"\s+", " ", ln.rstrip(":")))
    groups = [g for g in groups if g["lines"]]
    return dict(kind="dispatch", date=date, vehicle=vehicle, groups=groups)


def guess_kind(text):
    t = text.lower()
    if "production" in t: return "production"
    if "dispatch" in t or VEHICLE.search(text): return "dispatch"
    return "production" if find_date(_clean(text)) and not VEHICLE.search(text) else "dispatch"


# ------------------------------------------------------------------ matching
BRANDS = [("saha siri", "saha siri"), ("sahasiri", "saha siri"), ("saha", "saha siri"), ("bindu", "bindu"), ("everflow", "everflow"), ("tulsi", "tulsi"),
          ("ganavi", "ganavi"), ("nidhi", "nidhi"), ("platinum", "platinum"), ("nandi", "nandi"), ("rishab", "rishab")]


def feats(text, category="", brand=""):
    t = " " + text.lower() + " "
    t = t.replace("mtrs", "mtr").replace("meter", "mtr").replace("kgs", "kg")
    f = {}
    m = re.search(r"(\d+(?:\.\d+)?)\s*mil\b", t)
    if m: f["mil"] = float(m.group(1))
    m = re.search(r"(\d{2})\s*(?:mm\b|\s*(?=[rpf]\b)|\s*(?=round|plain|plane|flat|lateral))", t)
    if m and "mil" not in f: f["dia"] = int(m.group(1))
    if re.search(r"rain\s*pipe|rainpipe", t): f["type"] = "rain"
    elif re.search(r"round|\d\s*r\b|\br\b", t): f["type"] = "round"
    elif re.search(r"plain|plane|\d\s*p\b|lateral", t): f["type"] = "plain"
    elif re.search(r"flat|\d\s*f\b", t): f["type"] = "flat"
    m = re.search(r"(\d{2,4})\s*mtr", t)
    if m: f["mtr"] = int(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*kg", t)
    if m: f["kg"] = float(m.group(1))
    m = re.search(r"(\d{2})\s*cm", t)
    if m: f["cm"] = int(m.group(1))
    for k, v in BRANDS:
        if k in t: f["brand"] = v; break
    if re.search(r"\bevg\b|evergreen", t): f["brand"] = "evergreen"
    cat = category.lower()
    if re.search(r"non[\s-]*isi|\bn[\s-]*isi|\bnisi\b", t): f["isi"] = False
    elif re.search(r"\bisi\b", t): f["isi"] = True
    if cat: f["isi"] = not cat.startswith("non") if "pipe" in cat and "rain" not in cat else f.get("isi")
    if f.get("isi") is None: f.pop("isi", None)
    if "mil" in f and "dia" in f: f.pop("dia")
    if not f.get("type") and re.search(r"gold|diamond", t): f["type"] = "rain"
    if brand and "brand" not in f and category and not re.search(r"pipe", category.lower()): pass
    return f


def item_feats(it):
    text = "%s %s" % (it["item"], it["spec"])
    f = feats(text, it["category"])
    if it["category"].lower().startswith("rain"): f["type"] = "rain"; f.setdefault("dia", f.get("dia"))
    b = it["brand"].strip().lower()
    f["brand"] = b if any(b == v or b.startswith(v) or v in b for _, v in BRANDS) else "evergreen"
    return f


def score(line, it, lf=None):
    lf = lf or feats(line); itf = item_feats(it); s = 0.0
    W = dict(mil=6, dia=3, type=5, mtr=4, kg=4, cm=3, brand=4, isi=4)
    for k, w in W.items():
        if k in lf:
            if k not in itf:
                s -= w * 0.5 if k in ("kg", "cm") else w
            elif itf[k] == lf[k]: s += w
            else: s -= w * 1.5
        elif k in itf and k == "brand" and itf[k] != "evergreen": s -= 5     # item of another brand but line names none
        elif k in itf and k in ("kg", "cm", "mtr") and k not in lf: s -= 0.4   # item more specific than the line
        elif k == "isi" and k in itf and "type" in lf: s -= 2 if itf[k] else 0    # lines with no 'isi' are normally non-ISI
    return s


def match(line, items, n=4):
    """items = list of dicts (active, finished). Returns (best_item_or_None, [(score, item)], sure)"""
    lf = feats(line)
    sc = sorted(((score(line, it, lf), it) for it in items), key=lambda x: -x[0])[:n]
    if not sc: return None, [], False
    best = sc[0]; second = sc[1][0] if len(sc) > 1 else -99
    need = sum(w for k, w in dict(mil=6, dia=3, type=5, mtr=4, kg=4, cm=3).items() if k in lf)
    sure = best[0] >= 0.75 * need and best[0] - second >= 2.5 and best[0] > 4
    return best[1], sc, sure


def trip_key(date, vehicle, groups):
    s = "|".join([date, vehicle] + ["%s:%s" % (g["party"], ",".join("%s=%g" % (l["item"], l["qty"]) for l in g["lines"])) for g in groups])
    return "wa" + hashlib.sha1(s.encode()).hexdigest()[:8]
