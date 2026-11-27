"""Business rules. Stock is never stored: it is always the sum of the Moves ledger (void entries ignored)."""
import json, os
import pandas as pd
from store import SCHEMA, new_id, stamp, today, hash_pin, check_hash, token_hash, new_token, now
from datetime import timedelta, date as _date

LOGIC_VERSION = "2026-11-27-e"
BUCKETS = ["good", "hold", "bgrade", "recycle", "scrap"]
BUCKET_NAME = {"good": "Good stock", "hold": "On hold (returns)", "bgrade": "B-grade", "recycle": "To recycle", "scrap": "Scrap"}
ROLES = ["admin", "supervisor", "operator", "loader", "sales"]
NAV = {
    "admin":      ["Stock", "Production", "Dispatch", "Orders", "Customers", "Inward", "Add Stock", "WhatsApp", "Returns", "Raw & Waste", "Count", "Reports", "Fix entries", "Admin"],
    "supervisor": ["Stock", "Production", "Dispatch", "Orders", "Customers", "Inward", "Add Stock", "WhatsApp", "Returns", "Raw & Waste", "Count", "Reports", "Fix entries"],
    "operator":   ["Stock", "Production", "Inward", "Add Stock", "Raw & Waste", "Count"],
    "loader":     ["Stock", "Dispatch", "Customers", "Inward", "Returns"],
    "sales":      ["Stock", "Orders", "Customers", "Returns"],
}
NAV_MAIN = ["Stock", "Production", "Dispatch", "Orders", "Customers", "Inward"]   # the rest sit under "More"
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

def add_production(store, user, item_id, qty, date, shift="", machine="", note="", ref="", party=""):
    q = check_qty(qty); ref = ref or new_id()
    if already(store, ref): return
    store.append("Moves", [_move(item_id, q, "good", "production", ref, user, date, shift=shift, machine=machine, note=note, party=" ".join(str(party or "").split()))])

def add_dispatch(store, user, lines, vehicle, party, date, note="", allow_negative=False, ref=""):
    """lines = [(item_id, qty)]"""
    if not lines: raise Problem("Add at least one item.")
    vehicle = " ".join(vehicle.upper().split())
    if not vehicle: raise Problem("Type the vehicle number.")
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
    """rows: dicts with id (optional), category, brand, item, spec, unit, qty, note. Adds opening stock; makes missing items.
    Everything is written in two saves (items, then stock) so it cannot stop half way, and loading the same file twice adds nothing."""
    key = lambda x: (str(x["category"]).strip().lower(), str(x["brand"]).strip().lower(), str(x["item"]).strip().lower(), str(x["spec"]).strip().lower())
    its = store.rows("Items"); by_id = {x["id"]: x for x in its}; by_key = {key(x): x for x in its}
    have = {m["ref"] for m in store.rows("Moves")}
    new_items = []; updates = {}; moves = []; seen = {}; made = 0
    for r in rows:
        q = f(r.get("qty"), 0)
        if q <= 0: continue
        rid = str(r.get("id", "") or "").strip(); it = by_id.get(rid) if rid else None
        if it is None: it = by_key.get(key(r))
        if it is None:
            if not str(r["category"]).strip() or not str(r["item"]).strip(): raise Problem("A line has no category or item name.")
            it = dict(id="I" + new_id()[:6], category=str(r["category"]).strip(), brand=str(r["brand"]).strip(), item=str(r["item"]).strip(), spec=str(r["spec"]).strip(),
                      unit=(str(r.get("unit") or "").strip() or "rolls"), kind="raw" if str(r["category"]).strip().lower().startswith("raw") else "finished",
                      price=0.0, min_level=0.0, std_weight=0, active=1, subcategory="")
            new_items.append(it); by_id[it["id"]] = it; by_key[key(it)] = it; made += 1
        else:
            chg = dict(updates.get(it["id"], it)); unit = str(r.get("unit") or "").strip()
            if str(chg["active"]) not in ("1", "True", "true", "1.0"): chg["active"] = 1
            if unit and unit != chg["unit"]: chg["unit"] = unit
            if chg != it and "_r" in it: updates[it["id"]] = chg
        seen[it["id"]] = seen.get(it["id"], 0) + 1
        ref = "open1-%s-%d" % (it["id"], seen[it["id"]])
        if ref in have: continue
        have.add(ref)
        moves.append(_move(it["id"], q, "good", "opening", ref, user, date, note=(str(r.get("note", "")).strip() or "Opening stock")))
    if new_items: store.append("Items", new_items)
    for iid, chg in updates.items(): store.update("Items", by_id[iid]["_r"], chg)
    if moves: store.append("Moves", moves)
    return made, len(moves)

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

def edit_move_date(store, user, move_id, new_date):
    """Change the date of an entry; for a dispatch this moves the whole load (all lines saved together)."""
    m = next((x for x in store.rows("Moves") if x["id"] == move_id), None)
    if not m or str(m["void"]) in ("1", "True", "true"): raise Problem("Entry not found.")
    new_date = str(new_date)
    if new_date > today(): raise Problem("The date cannot be in the future.")
    group = [x for x in store.rows("Moves") if x["ref"] == m["ref"] and x["type"] == m["type"] and str(x["void"]) not in ("1", "True", "true")]
    for g in group:
        if g["date"] == new_date: continue
        row = dict(g); row["date"] = new_date; row["note"] = (g["note"] + " [date %s -> %s by %s]" % (g["date"], new_date, user)).strip(); store.update("Moves", g["_r"], row)
    return len(group)

FIXABLE = ("production", "inward", "opening", "dispatch", "raw_in", "raw_use", "waste")

def _is_void(m): return str(m["void"]) in ("1", "True", "true")

def _item_name(store, iid):
    r = next((x for x in store.rows("Items") if x["id"] == iid), None)
    return ("%s %s %s" % (r.get("brand", ""), r.get("item", ""), r.get("spec", ""))).strip() if r else iid

def edit_entry(store, user, move_id, item_id=None, qty=None, date=None, party=None, vehicle=None, shift=None, machine=None, note=None, whole_load=False, allow_negative=False):
    """Correct a wrong entry in place. Nothing is deleted: every change is written into the entry's note (who, what it was before).
    item and quantity change only this line. Customer, vehicle, date, shift, machine apply to the whole load (every line saved together) when whole_load is true."""
    rows = store.rows("Moves"); m = next((x for x in rows if x["id"] == move_id), None)
    if not m or _is_void(m): raise Problem("Entry not found.")
    if m["type"] not in FIXABLE: raise Problem("This kind of entry cannot be fixed here. Cancel it and enter it again.")
    if date is not None and str(date) > today(): raise Problem("The date cannot be in the future.")
    old_q = f(m["qty"]); sign = 1 if old_q >= 0 else -1
    new_item = item_id or m["item_id"]
    if item_id and not any(x["id"] == item_id for x in store.rows("Items")): raise Problem("Choose the item.")
    new_q = sign * check_qty(qty) if qty is not None else old_q
    if m["bucket"] == "good" and not allow_negative and (new_item != m["item_id"] or abs(new_q - old_q) > 1e-9):
        delta = {}
        delta[m["item_id"]] = delta.get(m["item_id"], 0.0) - old_q
        delta[new_item] = delta.get(new_item, 0.0) + new_q
        for iid, d in delta.items():
            if d < -1e-9 and good_now(store, iid) + d < -1e-9:
                raise Problem("That would make %s go below zero (it would be %s)." % (_item_name(store, iid), fmt(good_now(store, iid) + d)))
    group = [x for x in rows if x["ref"] == m["ref"] and x["type"] == m["type"] and not _is_void(x)] if whole_load else [m]
    n = 0
    for g in group:
        row = dict(g); ch = []
        if g["id"] == m["id"]:
            if new_item != g["item_id"]: ch.append("item %s -> %s" % (_item_name(store, g["item_id"]), _item_name(store, new_item))); row["item_id"] = new_item
            if abs(new_q - old_q) > 1e-9: ch.append("qty %s -> %s" % (fmt(abs(old_q)), fmt(abs(new_q)))); row["qty"] = round(new_q, 3)
        for key, val in (("date", date), ("party", party), ("vehicle", vehicle), ("shift", shift), ("machine", machine)):
            if val is None: continue
            val = " ".join(str(val).upper().split()) if key == "vehicle" else str(val).strip()
            if key == "vehicle" and not val and m["type"] == "dispatch": raise Problem("Type the vehicle number.")
            if val != str(g.get(key, "")):
                if key in ("party", "vehicle", "date", "shift", "machine") and g is not m and not whole_load: continue
                ch.append("%s %s -> %s" % (key, g.get(key, "") or "-", val or "-")); row[key] = val
        if note is not None and g["id"] == m["id"] and note.strip() != str(g["note"]).strip():
            row["note"] = note.strip(); ch.append("note changed")
        if ch:
            row["note"] = (str(row["note"]) + " [fixed by %s: %s]" % (user, "; ".join(ch))).strip(); store.update("Moves", g["_r"], row); n += 1
    return n

def move_entries_to_item(store, user, move_ids, new_item_id, allow_negative=False):
    """Put several wrongly booked lines on the right item (for example 330 MFQ booked on 330 Metal)."""
    n = 0
    for mid in move_ids: n += edit_entry(store, user, mid, item_id=new_item_id, allow_negative=allow_negative)
    return n

# ---------- tie dispatch to orders ----------
_GENERIC = {"traders", "agro", "enterprises", "solutions", "pipes", "agencies", "irrigation", "company", "stores", "marketing", "agri"}

def _tokens(s):
    return {t for t in "".join(c if c.isalnum() else " " for c in str(s).lower()).split() if len(t) >= 5 and t not in _GENERIC}

def party_match(a, b):
    na, nb = " ".join(str(a).lower().split()), " ".join(str(b).lower().split())
    if not na or not nb: return False
    return na == nb or bool(_tokens(a) & _tokens(b))

OWN_STOCK = "Own stock (safety)"

def all_parties(store):
    """One shared customer list for Orders, Dispatch and Returns: names from orders and dispatches, trimmed, no case-duplicates."""
    seen = {}
    names = [o["party"] for o in store.rows("Orders")] + [m["party"] for m in store.rows("Moves") if m["type"] in ("dispatch", "return", "return_decide")]
    for n in names:
        n = " ".join(str(n or "").split())
        if n and n != OWN_STOCK and n.lower() not in seen: seen[n.lower()] = n
    return sorted(seen.values(), key=str.lower)

def open_orders_for(store, party, item_ids=None):
    """Open orders of this customer (name need not be typed exactly the same) for the items being loaded, oldest first, with how much is still pending."""
    out = []
    for o in store.rows("Orders"):
        if o["status"] != "open" or (item_ids is not None and o["item_id"] not in item_ids) or not party_match(o["party"], party): continue
        pend = f(o["qty"]) - f(o.get("sent"))
        if pend > 1e-9: out.append(dict(o, pending=pend))
    return sorted(out, key=lambda r: (r["date"], r["ts"]))

def apply_dispatch_to_orders(store, ticked_ids, lines):
    """Count what was just loaded against the ticked orders (oldest first). An order is finished when everything ordered has been sent. Returns what was done."""
    left = {}
    for iid, q in lines: left[iid] = left.get(iid, 0.0) + q
    done = []
    for o in sorted([x for x in store.rows("Orders") if x["id"] in set(ticked_ids) and x["status"] == "open"], key=lambda r: (r["date"], r["ts"])):
        have = left.get(o["item_id"], 0.0)
        if have <= 1e-9: continue
        pend = f(o["qty"]) - f(o.get("sent")); take = min(pend, have)
        if take <= 1e-9: continue
        row = dict(o); row["sent"] = round(f(o.get("sent")) + take, 3)
        finished = row["sent"] >= f(o["qty"]) - 1e-9
        if finished: row["status"] = "done"
        store.update("Orders", o["_r"], row); left[o["item_id"]] = have - take
        done.append((o["party"], o["item_id"], take, finished))
    return done

def trip_of(ref): return (ref or "").split(".")[0]

def dispatch_load(store, ref):
    """One vehicle trip: every drop (customer) saved with the same trip id, for the slip."""
    trip = trip_of(ref)
    ms = [m for m in store.rows("Moves") if m["type"] == "dispatch" and trip_of(m["ref"]) == trip and str(m["void"]) not in ("1", "True", "true")]
    if not ms: return None
    its = {i["id"]: i for i in store.rows("Items")}
    drops = {}
    for m in ms:
        it = its.get(m["item_id"], {})
        drops.setdefault(m["party"], []).append(dict(brand=it.get("brand", ""), name=(it.get("item", "") + " " + it.get("spec", "")).strip(), unit=it.get("unit", ""), qty=-f(m["qty"])))
    m0 = ms[0]
    return dict(ref=trip, date=m0["date"], vehicle=m0["vehicle"], user=m0["user"], note=m0["note"], drops=list(drops.items()),
                party=", ".join(p for p in drops if p), lines=[l for v in drops.values() for l in v])

def add_dispatch_trip(store, user, drops, vehicle, date, note="", allow_negative=False, trip="", trip_no=""):
    """One vehicle, one or more customers. drops = [(party, [(item_id, qty)])]. All saved together or not at all."""
    drops = [(p, ls) for p, ls in drops if ls]
    if not drops: raise Problem("Add at least one item.")
    vehicle = " ".join(vehicle.upper().split())
    if not vehicle: raise Problem("Type the vehicle number.")
    trip = trip or new_id()
    if already(store, trip + ".0"): return
    need = {}
    for _, ls in drops:
        for iid, q in ls: need[iid] = need.get(iid, 0.0) + check_qty(q)
    if not allow_negative:
        for iid, q in need.items():
            have = good_now(store, iid)
            if q > have + 1e-9:
                nm = next((r for r in store.rows("Items") if r["id"] == iid), {})
                raise Problem("Not enough stock for %s %s: you have %s, trying to send %s in total. Fix the count in the Count tab first." % (nm.get("item", ""), nm.get("spec", ""), fmt(have), fmt(q)))
    rows = []
    for k, (party, ls) in enumerate(drops):
        agg = {}
        for iid, q in ls: agg[iid] = agg.get(iid, 0.0) + q
        rows += [_move(i, -q, "good", "dispatch", "%s.%d" % (trip, k), user, date, vehicle=vehicle, party=party.strip(), note=note, shift=str(trip_no or "")) for i, q in agg.items()]
    store.append("Moves", rows)

def add_order(store, user, party, item_id, qty, due, note=""):
    q = check_qty(qty)
    if not party.strip(): raise Problem("Enter the customer name.")
    store.append("Orders", [dict(id=new_id(), ts=stamp(), date=today(), due=due, party=party.strip(), item_id=item_id, qty=q, status="open", note=note, user=user, sent=0)])

def set_order_status(store, oid, status):
    o = next((x for x in store.rows("Orders") if x["id"] == oid), None)
    if o: row = dict(o); row["status"] = status; store.update("Orders", o["_r"], row)

def to_produce(store):
    items = items_df(store.rows("Items"), False); st = stock_table(items, moves_df(store.rows("Moves"))).set_index("id")
    need = {}; who = {}
    for o in store.rows("Orders"):
        if o["status"] == "open":
            p = max(0.0, f(o["qty"]) - f(o.get("sent")))
            if p <= 1e-9: continue
            need[o["item_id"]] = need.get(o["item_id"], 0.0) + p
            nm = " ".join(str(o["party"]).split()) or "(no customer)"
            who.setdefault(o["item_id"], {}); who[o["item_id"]][nm] = who[o["item_id"]].get(nm, 0.0) + p
    rows = []
    for iid, n in need.items():
        if iid not in st.index: continue
        have = st.loc[iid, "good"]
        cust = ", ".join("%s (%s)" % (k, fmt(v)) for k, v in sorted(who[iid].items(), key=lambda kv: -kv[1]))
        rows.append(dict(id=iid, category=st.loc[iid, "category"], item=st.loc[iid, "name"], brand=st.loc[iid, "brand"], unit=st.loc[iid, "unit"], customers=cust, ordered=n, in_stock=have, to_make=max(0.0, n - have)))
    return pd.DataFrame(rows, columns=["id", "category", "item", "brand", "unit", "customers", "ordered", "in_stock", "to_make"]).sort_values("to_make", ascending=False)

def pending_orders(store, party=None):
    """Every open order with something still to send: customer, category, item, pending, needed-by and days left (negative = late)."""
    items = items_df(store.rows("Items"), False).set_index("id"); out = []
    for o in store.rows("Orders"):
        if o["status"] != "open": continue
        if party is not None and not party_match(o["party"], party): continue
        p = f(o["qty"]) - f(o.get("sent"))
        if p <= 1e-9: continue
        it = items.loc[o["item_id"]] if o["item_id"] in items.index else None
        try: left = (_date.fromisoformat(str(o["due"])) - _date.fromisoformat(today())).days
        except Exception: left = None
        out.append(dict(Customer=" ".join(str(o["party"]).split()) or "(no customer)", Category=it["category"] if it is not None else "", Item=(it["brand"] + " | " + it["name"]) if it is not None else o["item_id"],
                        Pending=p, Unit=it["unit"] if it is not None else "", Needed_by=str(o["due"]), Days_left=left))
    cols = ["Customer", "Category", "Item", "Pending", "Unit", "Needed_by", "Days_left"]
    return pd.DataFrame(out, columns=cols).sort_values(["Days_left", "Customer"], na_position="last") if out else pd.DataFrame(columns=cols)

def daily_summary(store, day=None):
    """Plain text of the day, ready to paste into WhatsApp."""
    day = day or today(); items = items_df(store.rows("Items"), False).set_index("id")
    made = {}; sent = {}
    for m in store.rows("Moves"):
        if m["date"] != day or str(m["void"]) in ("1", "True", "true", "1.0") or m["bucket"] != "good": continue
        it = items.loc[m["item_id"]] if m["item_id"] in items.index else None
        nm = ("%s %s" % (it["brand"], it["name"]) if it is not None else m["item_id"]); un = it["unit"] if it is not None else ""
        if m["type"] == "production": made[(nm, un)] = made.get((nm, un), 0.0) + f(m["qty"])
        elif m["type"] == "dispatch":
            p = " ".join(str(m["party"]).split()) or "(no customer)"; sent.setdefault(p, {}); sent[p][(nm, un)] = sent[p].get((nm, un), 0.0) + abs(f(m["qty"]))
    t = ["Evergreen Stock summary, " + day, ""]
    t.append("MADE TODAY"); t += ["- %s %s %s" % (fmt(q), u, n) for (n, u), q in sorted(made.items())] or ["- nothing"]
    t += ["", "SENT TODAY"]
    for p, d in sorted(sent.items()): t.append(p); t += ["  - %s %s %s" % (fmt(q), u, n) for (n, u), q in sorted(d.items())]
    if not sent: t.append("- nothing")
    pend = pending_orders(store); t += ["", "PENDING ORDERS (%d lines)" % len(pend)]
    for c, g in pend.groupby("Customer"): t.append("%s: %s" % (c, "; ".join("%s %s %s" % (fmt(r.Pending), r.Unit, r.Item.split(" | ")[-1]) for r in g.itertuples())))
    return "\n".join(t)

# ---------- items / lists / users ----------
def add_item(store, category, brand, item, spec, unit, price=0.0, min_level=0.0):
    if not category.strip() or not item.strip(): raise Problem("Category and item name are needed.")
    dup = [r for r in store.rows("Items") if r["category"].lower() == category.strip().lower() and r["brand"].lower() == brand.strip().lower()
           and r["item"].lower() == item.strip().lower() and r["spec"].lower() == spec.strip().lower()]
    if dup: raise Problem("This item already exists.")
    store.append("Items", [dict(id="I" + new_id()[:6], category=category.strip(), brand=brand.strip(), item=item.strip(), spec=spec.strip(), unit=unit.strip() or "nos",
                                kind="raw" if category.strip().lower().startswith("raw") else "finished", price=price, min_level=min_level, std_weight=0, active=1, subcategory="")])

def edit_item(store, user, item_id, category=None, brand=None, item=None, spec=None, unit=None, active=None):
    """Rename / re-describe an item. Stock and history follow the item id, so nothing moves. Returns a short text of what changed ('' if nothing)."""
    rows = {r["id"]: r for r in store.rows("Items")}
    if item_id not in rows: raise Problem("That item was not found.")
    o = rows[item_id]; n = dict(o)
    for k, v in (("category", category), ("brand", brand), ("item", item), ("spec", spec), ("unit", unit)):
        if v is not None: n[k] = str(v).strip()
    if active is not None: n["active"] = 1 if active else 0
    if not n["category"] or not n["item"]: raise Problem("Category and item name are needed.")
    key = lambda r: (str(r["category"]).strip().lower(), str(r["brand"]).strip().lower(), str(r["item"]).strip().lower(), str(r["spec"]).strip().lower())
    if any(r["id"] != item_id and key(r) == key(n) for r in rows.values()): raise Problem("Another item already has exactly this category, brand, name and size.")
    ch = []
    for k in ("category", "brand", "item", "spec", "unit"):
        if str(o[k]).strip() != str(n[k]).strip(): ch.append("%s: %s -> %s" % (k, str(o[k]).strip() or "-", str(n[k]).strip() or "-"))
    if (str(o["active"]) in ("1", "True", "true", "1.0")) != bool(int(n["active"])): ch.append("active: %s -> %s" % (o["active"], n["active"]))
    if not ch: return ""
    n["kind"] = "raw" if str(n["category"]).lower().startswith("raw") else "finished"
    store.update("Items", o["_r"], n)
    return "; ".join(ch)

# ---------- weekly list for the factory, and customer history ----------
def weekly_list(items_rows, moves_rows, start, end):
    """Per item: opening, made, received, sent, other changes, closing, for start..end (dates 'YYYY-MM-DD'). Good stock only."""
    items = items_df(items_rows, False); mv = moves_df(moves_rows); mv = mv[(~mv["void"]) & (mv["bucket"] == "good")]
    def s(mask): return mv[mask].groupby("item_id")["qty"].sum()
    before = s(mv["date"] < start); within = (mv["date"] >= start) & (mv["date"] <= end)
    made = s(within & (mv["type"] == "production")); recv = s(within & (mv["type"] == "inward"))
    sent = -s(within & (mv["type"] == "dispatch")); other = s(within & ~mv["type"].isin(["production", "inward", "dispatch"]))
    upto = s(mv["date"] <= end)
    rows = []
    for _, it in items.iterrows():
        i = it["id"]; v = [float(x.get(i, 0.0)) for x in (before, made, recv, sent, other, upto)]
        if not any(abs(x) > 1e-9 for x in v): continue
        rows.append(dict(Category=it["category"], Brand=it["brand"], Item=it["name"], Unit=it["unit"], Opening=v[0], Made=v[1], Received=v[2], Sent=v[3], Other=v[4], Closing=v[5]))
    return pd.DataFrame(rows, columns=["Category", "Brand", "Item", "Unit", "Opening", "Made", "Received", "Sent", "Other", "Closing"])

def customer_history(items_rows, moves_rows, text, d1, d2):
    """Dispatch lines for customers whose name contains `text` (all customers if empty), between d1 and d2."""
    items = items_df(items_rows, False).set_index("id")
    t = " ".join((text or "").lower().split()); out = []
    for m in moves_rows:
        if m["type"] != "dispatch" or str(m["void"]) in ("1", "True", "true", "1.0") or m["bucket"] != "good" or not (d1 <= m["date"] <= d2): continue
        p = " ".join(str(m["party"]).split())
        if t and t not in p.lower(): continue
        it = items.loc[m["item_id"]] if m["item_id"] in items.index else None
        out.append(dict(Date=m["date"], Customer=p or "(no customer named)", Vehicle=m["vehicle"], Item=(it["brand"] + " | " + it["name"]) if it is not None else m["item_id"], Qty=abs(f(m["qty"])), Unit=it["unit"] if it is not None else ""))
    return pd.DataFrame(out, columns=["Date", "Customer", "Vehicle", "Item", "Qty", "Unit"]).sort_values(["Customer", "Date"], ascending=[True, False]) if out else pd.DataFrame(columns=["Date", "Customer", "Vehicle", "Item", "Qty", "Unit"])

def vehicle_trip_nos(moves_rows, vehicle, day):
    """Trip numbers already saved for this vehicle on this day (a blank counts as trip 1)."""
    v = "".join(str(vehicle).upper().split())
    return sorted({str(m["shift"]).strip() or "1" for m in moves_rows if m["type"] == "dispatch" and not (str(m["void"]) in ("1", "True", "true", "1.0")) and m["date"] == day and "".join(str(m["vehicle"]).upper().split()) == v})

def vehicle_days(moves_rows, text, d1, d2):
    """For each vehicle and date it dispatched: how many trips (saved trip number, blank = 1), how many customers and who. No items."""
    t = "".join((text or "").upper().split()); g = {}
    for m in moves_rows:
        if m["type"] != "dispatch" or str(m["void"]) in ("1", "True", "true", "1.0") or m["bucket"] != "good" or not (d1 <= m["date"] <= d2): continue
        v = "".join(str(m["vehicle"]).upper().split())
        if t and t not in v: continue
        e = g.setdefault((v, m["date"]), dict(parties={}, trips=set()))
        p = " ".join(str(m["party"]).split()) or "(no customer named)"; e["parties"].setdefault(p.lower(), p); e["trips"].add(str(m["shift"]).strip() or "1")
    rows = [dict(Date=d, Vehicle=v, Trips=len(e["trips"]), Customers=len(e["parties"]), Names=", ".join(sorted(e["parties"].values()))) for (v, d), e in g.items()]
    cols = ["Date", "Vehicle", "Trips", "Customers", "Names"]
    return pd.DataFrame(rows, columns=cols).sort_values(["Vehicle", "Date"], ascending=[True, False]) if rows else pd.DataFrame(columns=cols)

def vehicle_sheet(moves_rows, upto=None):
    upto = upto or today(); month = upto[:7]
    df = vehicle_days(moves_rows, "", month + "-01", month + "-31").sort_values(["Date", "Vehicle"])
    rows = [["VEHICLE TRIPS " + month, "Updated " + stamp()], ["Date", "Vehicle", "Trips", "Customers", "Customer names"]]
    rows += [[r["Date"], r["Vehicle"], r["Trips"], r["Customers"], r["Names"]] for _, r in df.iterrows()]
    rows += [[], ["", "", "", "", ""]]
    summ = df.groupby("Vehicle").agg(days=("Date", "nunique"), trips=("Trips", "sum"), customers=("Customers", "sum")).reset_index()
    rows += [["TOTAL FOR THE MONTH", "Vehicle", "Days it went", "Trips", "Customers carried"]]
    rows += [["", r["Vehicle"], int(r["days"]), int(r["trips"]), int(r["customers"])] for _, r in summ.iterrows()]
    return "Vehicles %s" % month, rows

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

def login(store, name, pin, keep=True):
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
    return new_session(store, u["name"], u["role"] == "admin" and keep), u

def new_session(store, name, link_ok=False):
    """link_ok: an admin who ticked 'keep me signed in' gets a token starting 'r.', which the page address may carry (iPhone browsers drop the cookie)."""
    tok = ("r." if link_ok else "") + new_token()
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

def dispatch_sheet(items_rows, moves_rows, upto=None):
    """Returns (tab_name, rows): every dispatched line of the month, one row each, oldest first, with a total per vehicle trip."""
    upto = upto or today(); month = upto[:7]
    items = items_df(items_rows, False).set_index("id")
    head = ["Date", "Slip no.", "Vehicle", "Customer / place", "Category", "Brand", "Item", "Size / details", "Qty", "Unit", "Entered by", "Note"]
    out = []
    for m in moves_rows:
        if m["type"] != "dispatch" or str(m["void"]) in ("1", "True", "true", "1.0") or m["bucket"] != "good" or not str(m["date"]).startswith(month): continue
        it = items.loc[m["item_id"]] if m["item_id"] in items.index else None
        out.append((m["date"], m["ts"], trip_of(m["ref"]), m, it))
    out.sort(key=lambda x: (x[0], x[1], x[2]))
    rows = [["DISPATCH " + month, "Updated " + stamp()], head]
    for d, _, trip, m, it in out:
        q = abs(f(m["qty"]))
        rows.append([d, trip[:6].upper(), m["vehicle"], m["party"], it["category"] if it is not None else "", it["brand"] if it is not None else "",
                     it["item"] if it is not None else m["item_id"], it["spec"] if it is not None else "", q, it["unit"] if it is not None else "", m["user"], m["note"]])
    rows.append([]); rows.append(["Lines", len(out), "", "", "", "", "", "", "(quantities are not added up here because items use different units)"])
    return "Dispatch %s" % month, rows

def sync_register(store):
    tab, rows = register(store.rows("Items"), store.rows("Moves"))
    store.b.replace_tab(tab, rows)
    try:
        t2, r2 = dispatch_sheet(store.rows("Items"), store.rows("Moves"))
        store.b.replace_tab(t2, r2, header_rows=2)
        t3, r3 = vehicle_sheet(store.rows("Moves"))
        store.b.replace_tab(t3, r3, header_rows=2)
    except Exception as e:
        store.sync_error = "Dispatch / vehicle sheet: " + str(e)[:150]
    return tab


# ---------- daily backup, today's movement ----------
def backup_now(store, day):
    """One tab called 'Backup' holding Items, Moves and Orders as they are now. It is rewritten each day, never added to; the old dated Backup tabs are removed."""
    rows = [["BACKUP", day, stamp()], [], ["ITEMS"], SCHEMA["Items"]]
    rows += [[r.get(c, "") for c in SCHEMA["Items"]] for r in store.rows("Items")]
    rows += [[], ["MOVES"], SCHEMA["Moves"]] + [[r.get(c, "") for c in SCHEMA["Moves"]] for r in store.rows("Moves")]
    rows += [[], ["ORDERS"], SCHEMA["Orders"]] + [[r.get(c, "") for c in SCHEMA["Orders"]] for r in store.rows("Orders")]
    store.b.replace_tab("Backup", rows, header_rows=1)
    store.b.prune_tabs("Backup 20", 0)     # the old 'Backup 2026-..' day tabs

def today_movement(items_rows, moves_rows, day=None):
    day = day or today(); items = items_df(items_rows, False).set_index("id"); mv = moves_df(moves_rows)
    mv = mv[(~mv["void"]) & (mv["bucket"] == "good") & (mv["date"] == day)]
    out = []
    for iid, g in mv.groupby("item_id"):
        if iid not in items.index: continue
        out.append(dict(Item=items.loc[iid, "brand"] + " | " + items.loc[iid, "name"], Unit=items.loc[iid, "unit"], In=g[g["qty"] > 0]["qty"].sum(), Out=-g[g["qty"] < 0]["qty"].sum()))
    return pd.DataFrame(out, columns=["Item", "Unit", "In", "Out"])


# ---------- unsaved work (so a half-entered dispatch survives a log-out or a reload) ----------
def draft_get(store, user, screen):
    r = next((x for x in store.rows("Drafts") if x["user"] == user and x["screen"] == screen), None)
    if not r or not r["data"]: return None
    try: return json.loads(r["data"])
    except Exception: return None

def draft_put(store, user, screen, data):
    """data=None clears it. One row per person per screen; written only when it changed."""
    payload = json.dumps(data, separators=(",", ":")) if data else ""
    r = next((x for x in store.rows("Drafts") if x["user"] == user and x["screen"] == screen), None)
    if r:
        if r["data"] == payload: return
        store.update("Drafts", r["_r"], dict(user=user, screen=screen, data=payload, ts=stamp()))
    elif payload:
        store.append("Drafts", [dict(user=user, screen=screen, data=payload, ts=stamp())])
