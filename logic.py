"""Business rules. Stock is never stored: it is always the sum of the Moves ledger (void entries ignored)."""
import json, os
import pandas as pd
from store import SCHEMA, new_id, stamp, today, hash_pin, check_hash, token_hash, new_token, now
from datetime import timedelta

LOGIC_VERSION = "2026-10-29-e"
BUCKETS = ["good", "hold", "bgrade", "recycle", "scrap"]
BUCKET_NAME = {"good": "Good stock", "hold": "On hold (returns)", "bgrade": "B-grade", "recycle": "To recycle", "scrap": "Scrap"}
ROLES = ["admin", "supervisor", "operator", "loader", "sales"]
NAV = {
    "admin":      ["Stock", "Inward", "Add Stock", "Production", "Dispatch", "Orders", "Returns", "Raw & Waste", "Count", "Reports", "Admin"],
    "supervisor": ["Stock", "Inward", "Add Stock", "Production", "Dispatch", "Orders", "Returns", "Raw & Waste", "Count", "Reports"],
    "operator":   ["Stock", "Inward", "Add Stock", "Production", "Raw & Waste", "Count"],
    "loader":     ["Stock", "Inward", "Dispatch", "Returns"],
    "sales":      ["Stock", "Orders", "Returns"],
}
SESSION_DAYS = 365

def f(x, d=0.0):
    try: return float(x)
    except Exception: return d

def fmt(q):
    q = round(f(q), 3)
    return str(int(q)) if q == int(q) else ("%g" % q)

def money(v): return "₹{:,.0f}".format(v)

# ---------- reading ----------
def items_df(rows, active_only=True):
    df = pd.DataFrame(rows, columns=SCHEMA["Items"] + ["_r"])
    for c in ("price", "min_level", "std_weight"): df[c] = df[c].map(f)
    df["subcategory"] = df["subcategory"].fillna("").astype(str).str.strip()
    df["active"] = df["active"].astype(str).isin(["1", "True", "true", "1.0"])
    if active_only: df = df[df["active"]]
    df["name"] = (df["item"].str.strip() + " " + df["spec"].str.strip()).str.strip()
    df["label"] = df["brand"].str.strip() + " | " + df["name"] + "  [" + df["unit"] + "]"
    return df.reset_index(drop=True)

def moves_df(rows):
    df = pd.DataFrame(rows, columns=SCHEMA["Moves"] + ["_r"])
    df["qty"] = df["qty"].map(f)
    df["void"] = df["void"].astype(str).isin(["1", "True", "true", "1.0"])
    return df

def stock_table(items, moves):
    live = moves[~moves["void"]]
    p = live.pivot_table(index="item_id", columns="bucket", values="qty", aggfunc="sum", fill_value=0.0)
    for b in BUCKETS:
        if b not in p.columns: p[b] = 0.0
    p = p[BUCKETS]
    out = items.set_index("id").join(p).fillna({b: 0.0 for b in BUCKETS})
    out["value"] = out["good"] * out["price"]
    return out.reset_index().rename(columns={"index": "id"})

def list_values(rows, kind):
    return sorted({r["name"] for r in rows if r["kind"] == kind and str(r["active"]) in ("1", "True", "true", "1.0")}, key=str.lower)

def categories(items_rows, list_rows):
    order = ["ISI Pipe", "Non-ISI Pipe", "Microtube & Tubing", "Rain Pipe", "Filters", "Valves & Venturi", "Drippers & Emitters", "Sprinkler", "Raw Material"]
    have = {r["category"] for r in items_rows if r["category"]} | set(list_values(list_rows, "category"))
    return [c for c in order if c in have] + sorted(have - set(order))

# ---------- writing ----------
class Problem(Exception): pass

def _move(item_id, qty, bucket, typ, ref, user, date=None, **kw):
    return dict(id=new_id(), ts=stamp(), date=date or today(), item_id=item_id, qty=round(float(qty), 3), bucket=bucket, type=typ, ref=ref,
                party=kw.get("party", ""), vehicle=kw.get("vehicle", ""), machine=kw.get("machine", ""), shift=kw.get("shift", ""),
                note=kw.get("note", ""), user=user, void="")

def check_qty(q, allow_zero=False):
    q = f(q, -1)
    if q < 0 or (q == 0 and not allow_zero): raise Problem("Please enter a quantity greater than zero.")
    if q > 1_000_000: raise Problem("That quantity looks too large. Please check it.")
    return q

def already(store, ref):
    return any(m["ref"] == ref for m in store.rows("Moves")[-400:])

def good_now(store, item_id):
    tot = 0.0
    for m in store.rows("Moves"):
        if m["item_id"] == item_id and m["bucket"] == "good" and str(m["void"]) not in ("1", "True", "true"): tot += f(m["qty"])
    return tot

def add_production(store, user, item_id, qty, date, shift="", machine="", note="", ref=""):
    q = check_qty(qty); ref = ref or new_id()
    if already(store, ref): return
    store.append("Moves", [_move(item_id, q, "good", "production", ref, user, date, shift=shift, machine=machine, note=note)])

def add_dispatch(store, user, lines, vehicle, party, date, note="", allow_negative=False, ref=""):
    """lines = [(item_id, qty)]"""
    if not lines: raise Problem("Add at least one item.")
    if not vehicle.strip(): raise Problem("Choose or type the vehicle.")
    ref = ref or new_id()
    if already(store, ref): return
    need = {}
    for iid, q in lines: need[iid] = need.get(iid, 0.0) + check_qty(q)
    if not allow_negative:
        for iid, q in need.items():
            have = good_now(store, iid)
            if q > have + 1e-9:
                nm = next((r for r in store.rows("Items") if r["id"] == iid), {})
                raise Problem("Not enough stock for %s %s: you have %s, trying to send %s. Fix the count in the Count tab first." % (nm.get("item", ""), nm.get("spec", ""), fmt(have), fmt(q)))
    store.append("Moves", [_move(i, -q, "good", "dispatch", ref, user, date, vehicle=vehicle.strip(), party=party.strip(), note=note) for i, q in need.items()])

def add_stock(store, user, item_id, qty, date, note="", ref=""):
    """Opening / extra stock: simply adds to good stock."""
    q = check_qty(qty); ref = ref or new_id()
    if already(store, ref): return
    store.append("Moves", [_move(item_id, q, "good", "opening", ref, user, date, note=note or "Stock added")])

def add_inward(store, user, item_id, qty, date, supplier="", bill="", note="", ref=""):
    """Purchased material / fittings received."""
    q = check_qty(qty); ref = ref or new_id()
    if already(store, ref): return
    n = " · ".join(x for x in [("Bill " + bill.strip()) if bill.strip() else "", note.strip()] if x)
    store.append("Moves", [_move(item_id, q, "good", "inward", ref, user, date, party=supplier.strip(), note=n)])

def import_opening(store, user, rows, date):
    """rows: dicts with id (optional), category, brand, item, spec, unit, qty, note. Adds opening stock; makes missing items; safe to run twice."""
    made = added = 0; seen = {}
    for r in rows:
        q = f(r.get("qty"), 0)
        if q <= 0: continue
        its = store.rows("Items"); it = None; rid = str(r.get("id", "") or "").strip()
        if rid: it = next((x for x in its if x["id"] == rid), None)
        if it is None:
            it = next((x for x in its if x["category"].lower() == str(r["category"]).strip().lower() and x["brand"].lower() == str(r["brand"]).strip().lower()
                       and x["item"].lower() == str(r["item"]).strip().lower() and x["spec"].lower() == str(r["spec"]).strip().lower()), None)
        if it is None:
            add_item(store, r["category"], r["brand"], r["item"], r["spec"], r.get("unit") or "rolls"); made += 1
            it = next(x for x in store.rows("Items") if x["category"].lower() == str(r["category"]).strip().lower() and x["brand"].lower() == str(r["brand"]).strip().lower()
                      and x["item"].lower() == str(r["item"]).strip().lower() and x["spec"].lower() == str(r["spec"]).strip().lower())
        new = dict(it); unit = str(r.get("unit") or "").strip()
        if str(it["active"]) not in ("1", "True", "true", "1.0"): new["active"] = 1
        if unit and unit != it["unit"]: new["unit"] = unit
        if new != it: store.update("Items", it["_r"], new)
        seen[it["id"]] = seen.get(it["id"], 0) + 1       # the same item twice in one file adds both lines
        ref = "open1-%s-%d" % (it["id"], seen[it["id"]])
        if already(store, ref): continue
        store.append("Moves", [_move(it["id"], q, "good", "opening", ref, user, date, note=(str(r.get("note", "")).strip() or "Opening stock"))]); added += 1
    return made, added

def reset_all_stock(store, user):
    """Sets every item's good stock to zero by adding offsetting entries (nothing is deleted)."""
    t = stock_table(items_df(store.rows("Items"), False), moves_df(store.rows("Moves")))
    return add_counts(store, user, {r["id"]: 0 for _, r in t.iterrows() if abs(r["good"]) > 1e-9}, note="Stock reset to zero")

def add_return(store, user, item_id, qty, party, date, note="", ref=""):
    q = check_qty(qty); ref = ref or new_id()
    if already(store, ref): return
    store.append("Moves", [_move(item_id, q, "hold", "return", ref, user, date, party=party.strip(), note=note)])

def pending_returns(store):
    moves = store.rows("Moves"); res = {}
    for m in moves:
        if str(m["void"]) in ("1", "True", "true"): continue
        if m["type"] == "return": res.setdefault(m["id"], dict(m, left=0.0, _r=m["_r"]))["left"] += f(m["qty"])
    for m in moves:
        if str(m["void"]) in ("1", "True", "true"): continue
        if m["type"] == "return_decide" and m["bucket"] == "hold" and m["ref"] in res: res[m["ref"]]["left"] += f(m["qty"])
    return [r for r in res.values() if r["left"] > 1e-9]

def decide_return(store, user, ret_id, qty, dest, note=""):
    if dest not in ("good", "bgrade", "recycle", "scrap"): raise Problem("Choose what to do with it.")
    left = next((r for r in pending_returns(store) if r["id"] == ret_id), None)
    if not left: raise Problem("That return was already settled.")
    q = check_qty(qty)
    if q > left["left"] + 1e-9: raise Problem("Only %s is waiting on hold." % fmt(left["left"]))
    store.append("Moves", [_move(left["item_id"], -q, "hold", "return_decide", ret_id, user, note=note, party=left["party"]),
                           _move(left["item_id"], q, dest, "return_decide", ret_id, user, note=note, party=left["party"])])

def add_waste(store, user, item_id, qty, date, note="", ref=""):
    q = check_qty(qty); ref = ref or new_id()
    if already(store, ref): return
    store.append("Moves", [_move(item_id, -q, "good", "waste", ref, user, date, note=note), _move(item_id, q, "scrap", "waste", ref, user, date, note=note)])

def add_raw(store, user, item_id, qty, date, direction, note="", ref=""):
    q = check_qty(qty); ref = ref or new_id()
    if already(store, ref): return
    if direction == "out" and q > good_now(store, item_id) + 1e-9: raise Problem("Not enough raw material in stock for that.")
    store.append("Moves", [_move(item_id, q if direction == "in" else -q, "good", "raw_in" if direction == "in" else "raw_use", ref, user, date, note=note)])

def add_counts(store, user, counts, date=None, note="Stock count"):
    """counts = {item_id: counted_qty}; writes the difference vs the system as an adjustment."""
    st = {r["id"]: r for r in stock_table(items_df(store.rows("Items"), False), moves_df(store.rows("Moves"))).to_dict("records")}
    ref = new_id(); out = []
    for iid, c in counts.items():
        c = f(c, None) if c not in (None, "") else None
        if c is None: continue
        if c < 0 or c > 1_000_000: raise Problem("A counted quantity is not valid.")
        diff = round(c - st.get(iid, {}).get("good", 0.0), 3)
        if abs(diff) > 1e-9: out.append(_move(iid, diff, "good", "count", ref, user, date, note=note))
    if out: store.append("Moves", out)
    return len(out)

def void_move_group(store, user, move_id):
    """Void an entry and everything saved with it."""
    rows = store.rows("Moves"); m = next((x for x in rows if x["id"] == move_id), None)
    if not m: raise Problem("Entry not found.")
    for x in rows:
        if x["ref"] == m["ref"] and x["type"] == m["type"] and str(x["void"]) not in ("1", "True", "true"):
            row = dict(x); row["void"] = "1"; row["note"] = (x["note"] + " [cancelled by %s]" % user).strip(); store.update("Moves", x["_r"], row)

def void_move(store, user, move_id):
    """Cancel one entry (nothing is deleted)."""
    m = next((x for x in store.rows("Moves") if x["id"] == move_id), None)
    if not m: raise Problem("Entry not found.")
    row = dict(m); row["void"] = "1"; row["note"] = (m["note"] + " [cancelled by %s]" % user).strip(); store.update("Moves", m["_r"], row)

def edit_move_qty(store, user, move_id, qty):
    """Correct the quantity of one entry; keeps its direction and records who changed it."""
    m = next((x for x in store.rows("Moves") if x["id"] == move_id), None)
    if not m or str(m["void"]) in ("1", "True", "true"): raise Problem("Entry not found.")
    if m["type"] not in ("production", "inward", "opening", "dispatch", "raw_in", "raw_use"): raise Problem("This kind of entry cannot be edited. Cancel it and enter it again.")
    q = check_qty(qty); old = f(m["qty"]); new = q if old >= 0 else -q
    if new < old and m["bucket"] == "good" and good_now(store, m["item_id"]) + (new - old) < -1e-9:
        raise Problem("That would make the stock go below zero.")
    row = dict(m); row["qty"] = round(new, 3); row["note"] = (m["note"] + " [edited %s -> %s by %s]" % (fmt(abs(old)), fmt(q), user)).strip(); store.update("Moves", m["_r"], row)

def add_order(store, user, party, item_id, qty, due, note=""):
    q = check_qty(qty)
    if not party.strip(): raise Problem("Enter the customer name.")
    store.append("Orders", [dict(id=new_id(), ts=stamp(), date=today(), due=due, party=party.strip(), item_id=item_id, qty=q, status="open", note=note, user=user)])

def set_order_status(store, oid, status):
    o = next((x for x in store.rows("Orders") if x["id"] == oid), None)
    if o: row = dict(o); row["status"] = status; store.update("Orders", o["_r"], row)

def to_produce(store):
    items = items_df(store.rows("Items"), False); st = stock_table(items, moves_df(store.rows("Moves"))).set_index("id")
    need = {}
    for o in store.rows("Orders"):
        if o["status"] == "open": need[o["item_id"]] = need.get(o["item_id"], 0.0) + f(o["qty"])
    rows = []
    for iid, n in need.items():
        if iid not in st.index: continue
        have = st.loc[iid, "good"]
        rows.append(dict(id=iid, item=st.loc[iid, "name"], brand=st.loc[iid, "brand"], unit=st.loc[iid, "unit"], ordered=n, in_stock=have, to_make=max(0.0, n - have)))
    return pd.DataFrame(rows, columns=["id", "item", "brand", "unit", "ordered", "in_stock", "to_make"]).sort_values("to_make", ascending=False)

# ---------- items / lists / users ----------
def add_item(store, category, brand, item, spec, unit, price=0.0, min_level=0.0):
    if not category.strip() or not item.strip(): raise Problem("Category and item name are needed.")
    dup = [r for r in store.rows("Items") if r["category"].lower() == category.strip().lower() and r["brand"].lower() == brand.strip().lower()
           and r["item"].lower() == item.strip().lower() and r["spec"].lower() == spec.strip().lower()]
    if dup: raise Problem("This item already exists.")
    store.append("Items", [dict(id="I" + new_id()[:6], category=category.strip(), brand=brand.strip(), item=item.strip(), spec=spec.strip(), unit=unit.strip() or "nos",
                                kind="raw" if category.strip().lower().startswith("raw") else "finished", price=price, min_level=min_level, std_weight=0, active=1, subcategory="")])

def add_list(store, kind, name):
    name = name.strip()
    if not name: raise Problem("Type a name first.")
    if any(r["kind"] == kind and r["name"].lower() == name.lower() for r in store.rows("Lists")): return
    store.append("Lists", [dict(kind=kind, name=name, active=1)])

# users
def users(store): return store.rows("Users")

def make_user(store, name, role, pin):
    name = name.strip()
    if not name: raise Problem("Enter a name.")
    if role not in ROLES: raise Problem("Choose a role.")
    if not pin.isdigit() or len(pin) < (6 if role == "admin" else 4): raise Problem("PIN must be %d or more digits." % (6 if role == "admin" else 4))
    if any(u["name"].lower() == name.lower() for u in users(store)): raise Problem("That name is already used.")
    salt = new_token()[:12]
    store.append("Users", [dict(name=name, role=role, salt=salt, pin_hash=hash_pin(pin, salt), active=1, fails=0, locked_until="", created=stamp())])

def set_pin(store, name, pin):
    u = next((x for x in users(store) if x["name"] == name), None)
    if not u: raise Problem("User not found.")
    if not pin.isdigit() or len(pin) < (6 if u["role"] == "admin" else 4): raise Problem("PIN must be %d or more digits." % (6 if u["role"] == "admin" else 4))
    row = dict(u); row["salt"] = new_token()[:12]; row["pin_hash"] = hash_pin(pin, row["salt"]); row["fails"] = 0; row["locked_until"] = ""
    store.update("Users", u["_r"], row)

def update_user(store, name, **ch):
    u = next((x for x in users(store) if x["name"] == name), None)
    if u: row = dict(u); row.update(ch); store.update("Users", u["_r"], row)

def login(store, name, pin):
    u = next((x for x in users(store) if x["name"].lower() == name.strip().lower()), None)
    if not u or str(u["active"]) not in ("1", "True", "true"): raise Problem("Wrong name or PIN.")
    lk = u["locked_until"]
    if lk and lk > stamp(): raise Problem("Too many wrong tries. Try again in a few minutes.")
    if not check_hash(pin, u["salt"], u["pin_hash"]):
        row = dict(u); n = int(f(u["fails"])) + 1; row["fails"] = n
        if n >= 5: row["locked_until"] = (now() + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S"); row["fails"] = 0
        store.update("Users", u["_r"], row); raise Problem("Wrong name or PIN.")
    if int(f(u["fails"])) or u["locked_until"]:
        row = dict(u); row["fails"] = 0; row["locked_until"] = ""; store.update("Users", u["_r"], row)
    return new_session(store, u["name"]), u

def new_session(store, name):
    tok = new_token()
    store.append("Sessions", [dict(token_hash=token_hash(tok), user=name, expires=(now() + timedelta(days=SESSION_DAYS)).strftime("%Y-%m-%d %H:%M:%S"), created=stamp())])
    return tok

def user_from_token(store, tok):
    if not tok: return None
    h = token_hash(tok); s = next((x for x in reversed(store.rows("Sessions")) if x["token_hash"] == h), None)
    if not s or s["expires"] < stamp(): return None
    u = next((x for x in users(store) if x["name"] == s["user"]), None)
    if not u or str(u["active"]) not in ("1", "True", "true"): return None
    if s["expires"] < (now() + timedelta(days=SESSION_DAYS - 7)).strftime("%Y-%m-%d %H:%M:%S"):
        row = dict(s); row["expires"] = (now() + timedelta(days=SESSION_DAYS)).strftime("%Y-%m-%d %H:%M:%S"); store.update("Sessions", s["_r"], row)
    return u

def end_session(store, tok):
    if not tok: return
    h = token_hash(tok); s = next((x for x in store.rows("Sessions") if x["token_hash"] == h), None)
    if s: row = dict(s); row["expires"] = "2000-01-01 00:00:00"; store.update("Sessions", s["_r"], row)

# ---------- seeding ----------
def seed_if_empty(store, sample=False):
    if store.rows("Items"): return False
    m = json.load(open(os.path.join(os.path.dirname(__file__), "seed", "master.json"), encoding="utf-8"))
    store.append("Items", [dict(id=x["id"], category=x["category"], brand=x["brand"], item=x["item"], spec=x["spec"], unit=x["unit"], kind=x["kind"],
                                price=x["price"], min_level=0, std_weight=x["std_weight"], active=x["active"]) for x in m])
    store.append("Lists", [dict(kind="category", name=c, active=1) for c in ["ISI Pipe", "Non-ISI Pipe", "Microtube & Tubing", "Rain Pipe", "Filters", "Valves & Venturi", "Drippers & Emitters", "Sprinkler", "Raw Material"]]
                 + [dict(kind="machine", name="Machine %d" % i, active=1) for i in range(1, 7)]
                 + [dict(kind="vehicle", name="Vehicle %d" % i, active=1) for i in range(1, 9)])
    if sample:
        ref = new_id()
        store.append("Moves", [_move(x["id"], x["sample_qty"], "good", "count", ref, "setup", note="SAMPLE count from Oct statement (trial only)")
                               for x in m if x.get("sample_qty") and x["active"]])
    return True


# ---------- Google Sheet register (same layout as the Excel: Opening / In / Out / Closing per day) ----------
def register(items_rows, moves_rows, upto=None):
    """Returns (tab_name, rows) for the current month. Only 'good' stock is shown, like the Excel."""
    import calendar
    from datetime import date as _d, datetime as _dt
    upto = upto or today(); y, m = int(upto[:4]), int(upto[5:7]); first = "%04d-%02d-01" % (y, m)
    days = ["%04d-%02d-%02d" % (y, m, d) for d in range(1, int(upto[8:10]) + 1)]
    items = items_df(items_rows, True); mv = moves_df(moves_rows); mv = mv[(~mv["void"]) & (mv["bucket"] == "good")]
    before = mv[mv["date"] < first].groupby("item_id")["qty"].sum()
    inn = mv[(mv["date"] >= first) & (mv["qty"] > 0)].groupby(["item_id", "date"])["qty"].sum()
    out = mv[(mv["date"] >= first) & (mv["qty"] < 0)].groupby(["item_id", "date"])["qty"].sum()
    h1 = [""] * 8; h2 = ["Category", "Brand", "Item", "Size / details", "Unit", "Price", "Current QTY", "Amount"]
    for d in days:
        lab = _dt.strptime(d, "%Y-%m-%d").strftime("%d %b %Y")
        h1 += [lab, "", "", ""]; h2 += ["Opening", "In", "Out", "Closing"]
    rows = [h1, h2]
    for _, it in items.iterrows():
        bal = float(before.get(it["id"], 0.0)); line = [it["category"], it["brand"], it["item"], it["spec"], it["unit"], it["price"], 0, 0]; cells = []
        for d in days:
            i_ = float(inn.get((it["id"], d), 0.0)); o_ = -float(out.get((it["id"], d), 0.0)); cl = bal + i_ - o_
            cells += [round(bal, 3), round(i_, 3), round(o_, 3), round(cl, 3)]; bal = cl
        line[6] = round(bal, 3); line[7] = round(bal * it["price"], 2)
        rows.append(line + cells)
    return "Register %s" % first[:7], rows

def sync_register(store):
    tab, rows = register(store.rows("Items"), store.rows("Moves"))
    store.b.replace_tab(tab, rows)
    return tab


# ---------- daily backup, today's movement ----------
def backup_now(store, day):
    """One tab 'Backup YYYY-MM-DD' holding Items, Moves and Orders as they are now. Keeps the last 7."""
    rows = [["BACKUP", day, stamp()], [], ["ITEMS"], SCHEMA["Items"]]
    rows += [[r.get(c, "") for c in SCHEMA["Items"]] for r in store.rows("Items")]
    rows += [[], ["MOVES"], SCHEMA["Moves"]] + [[r.get(c, "") for c in SCHEMA["Moves"]] for r in store.rows("Moves")]
    rows += [[], ["ORDERS"], SCHEMA["Orders"]] + [[r.get(c, "") for c in SCHEMA["Orders"]] for r in store.rows("Orders")]
    store.b.replace_tab("Backup " + day, rows, header_rows=1)
    store.b.prune_tabs("Backup ", 7)

def today_movement(items_rows, moves_rows, day=None):
    day = day or today(); items = items_df(items_rows, False).set_index("id"); mv = moves_df(moves_rows)
    mv = mv[(~mv["void"]) & (mv["bucket"] == "good") & (mv["date"] == day)]
    out = []
    for iid, g in mv.groupby("item_id"):
        if iid not in items.index: continue
        out.append(dict(Item=items.loc[iid, "brand"] + " | " + items.loc[iid, "name"], Unit=items.loc[iid, "unit"], In=g[g["qty"] > 0]["qty"].sum(), Out=-g[g["qty"] < 0]["qty"].sum()))
    return pd.DataFrame(out, columns=["Item", "Unit", "In", "Out"])
