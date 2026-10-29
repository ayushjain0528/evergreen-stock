"""Evergreen Stock - one app for stock, production, dispatch, orders, returns, raw material and reports."""
import io, os, zipfile
from datetime import date, timedelta
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import importlib
import logic as L
import store as _store
RELEASE = "2026-10-29-b"        # change on every release; it makes the app reload its own parts after an update
if getattr(L, "LOGIC_VERSION", None) != RELEASE:
    importlib.reload(_store); importlib.reload(L)
from store import Store, LocalBackend, SheetsBackend, today, new_id, SCHEMA

st.set_page_config(page_title="Evergreen Stock", page_icon="🌿", layout="centered", initial_sidebar_state="collapsed")
st.markdown("""<style>
.block-container{padding-top:1.2rem;padding-bottom:3rem;max-width:760px}
div[data-testid="stMetricValue"]{font-size:1.4rem}
div[role="radiogroup"]{gap:.15rem .8rem}div[role="radiogroup"] label p{font-size:.92rem}
.stButton>button,.stFormSubmitButton>button{width:100%;min-height:2.8rem;font-weight:600}
</style>""", unsafe_allow_html=True)


# ---------------------------------------------------------------- storage
APP_VERSION = RELEASE   # change this on every release so a fresh connection is built


@st.cache_resource
def get_store(version=APP_VERSION):
    try:
        have = any(os.path.exists(os.path.join(d, "secrets.toml")) for d in (os.path.join(os.path.dirname(__file__), ".streamlit"), os.path.expanduser("~/.streamlit")))
        sec = st.secrets if have else {}
        if "gcp_service_account" in sec and "sheet_id" in sec:
            b = SheetsBackend(sec["sheet_id"], dict(sec["gcp_service_account"]))
        else:
            b = None
    except Exception:
        b = None
    if b is None:
        b = LocalBackend(os.environ.get("STOCK_DATA_DIR", os.path.join(os.path.dirname(__file__), "trial_data")))
    s = Store(b)
    s.sync_fn = L.sync_register
    L.seed_if_empty(s, sample=os.environ.get("TRIAL_SAMPLE") == "1")
    return s

NEW = hasattr(st, "iframe")           # newer Streamlit; the code also runs on older ones
WIDE = {"width": "stretch"} if NEW else {"use_container_width": True}
S = get_store()


def choose_other(label, options, key):
    """Plain dropdown with an 'Other' choice; picking Other shows a box to type it."""
    options = [o for o in options if o]
    v = st.selectbox(label, options + ["Other (type it)"], index=None, placeholder="Choose…", key=key)
    if v == "Other (type it)": return st.text_input("Type the new %s" % label.lower(), key=key + "_t").strip()
    return v or ""


def combo(label, options, key, placeholder=""):
    """Pick from a list or type a new value. Returns text."""
    options = [o for o in options if o]
    if NEW:
        return st.selectbox(label, options, index=None, placeholder=placeholder, accept_new_options=True, key=key) or ""
    other = "➕ Type a new one…"
    v = st.selectbox(label, options + [other], index=None, placeholder=placeholder, key=key)
    if v == other: return st.text_input(label + " (type it)", key=key + "_t").strip()
    return v or ""

LIVE = S.b.kind == "sheets"


def run(fn, *a, ok=None, **k):
    """Run a save; show a plain message on a problem. Returns True when saved."""
    try:
        fn(S, *a, **k)
    except L.Problem as e:
        st.error(str(e)); return False
    except Exception as e:
        st.error("Could not save. Please try again. (%s)" % str(e)[:160]); return False
    if ok: st.toast(ok, icon="✅")
    return True


# ---------------------------------------------------------------- login (stays logged in)
def set_cookie(tok, days=365):
    val = tok or ""
    age = days * 86400 if tok else 0
    html = "<script>try{var d=window.parent.document;d.cookie='sb_s=%s; max-age=%d; path=/; SameSite=Lax';}catch(e){}</script>" % (val, age)
    if hasattr(st, "iframe"): st.iframe(html, height=1)
    else: components.html(html, height=0)

def token_in():
    for v in (st.session_state.get("tok"), st.context.cookies.get("sb_s"), st.query_params.get("s")):
        if isinstance(v, str) and v: return v
    return None

def current_user():
    tok = token_in(); u = L.user_from_token(S, tok)
    if u and u["role"] == "admin" and tok != (st.session_state.get("tok") or st.context.cookies.get("sb_s")):
        return None          # an admin login is never accepted from a link, so a copied link cannot open the admin account
    return u

def login_screen():
    st.markdown("## 🌿 Evergreen Stock")
    users = L.users(S)
    if not users:
        st.info("First time here. Create the owner (admin) login. Use a PIN of 6 or more digits.")
        with st.form("setup"):
            nm = st.text_input("Your name", value="Ayush"); p1 = st.text_input("PIN (6+ digits)", type="password"); p2 = st.text_input("Type the PIN again", type="password")
            if st.form_submit_button("Create admin login"):
                if p1 != p2: st.error("The two PINs are not the same.")
                elif run(L.make_user, nm, "admin", p1): st.rerun()
        return
    names = [u["name"] for u in users if str(u["active"]) in ("1", "True", "true")]
    with st.form("login"):
        nm = st.selectbox("Your name", names); pin = st.text_input("PIN", type="password", max_chars=12)
        if st.form_submit_button("Open"):
            try:
                tok, u = L.login(S, nm, pin)
            except L.Problem as e:
                st.error(str(e)); return
            st.session_state["tok"] = tok; (None if u["role"] == "admin" else st.query_params.__setitem__("s", tok)); set_cookie(tok); st.rerun()
    st.caption("You stay signed in on this phone. You will not need to type the PIN again.")


user = current_user()
if not user:
    login_screen(); st.stop()
st.session_state["tok"] = token_in()
if user["role"] == "admin":
    if "s" in st.query_params: del st.query_params["s"]
elif st.query_params.get("s") != st.session_state["tok"]: st.query_params["s"] = st.session_state["tok"]
if st.context.cookies.get("sb_s") != st.session_state["tok"]: set_cookie(st.session_state["tok"])
ME, ROLE = user["name"], user["role"]
S.maybe_backup(L.backup_now)
IS_ADMIN = ROLE == "admin"
CAN_MANAGE = ROLE in ("admin", "supervisor")


# ---------------------------------------------------------------- shared data
def load():
    items = L.items_df(S.rows("Items")); moves = L.moves_df(S.rows("Moves"))
    return items, moves, L.stock_table(items, moves)

def pick_item(pre, items, kinds=None, label=None):
    """Same Category > Brand > Item pick as everywhere else (no 'Other'). Returns the item row or None."""
    _, _, tab = load()
    it, _, _ = entry_picker(pre, items, tab, kinds, allow_new=False)
    return it


def nonce(name):
    k = "nonce_" + name
    if k not in st.session_state: st.session_state[k] = new_id()
    return st.session_state[k]
def burn(name): st.session_state.pop("nonce_" + name, None)

def qty_box(label="Quantity", key=None, unit=""):
    return st.number_input(label + (" (%s)" % unit if unit else ""), min_value=0.0, value=None, step=1.0, format="%g", key=key, placeholder="0")

EDITABLE = ("production", "inward", "opening", "dispatch", "raw_in", "raw_use")

def recent(types, n=8, mine_only=False):
    """Latest entries, each with Edit (quantity) and Undo."""
    rows = [m for m in S.rows("Moves") if m["type"] in types and str(m["void"]) not in ("1", "True", "true") and m["bucket"] in ("good", "hold")]
    if mine_only or not CAN_MANAGE: rows = [m for m in rows if m["user"] == ME and m["date"] == today()]
    show = list(reversed(rows))[:n]
    if not show: return
    items = L.items_df(S.rows("Items"), False).set_index("id")
    st.markdown("**Latest entries**")
    for m in show:
        nm = items.loc[m["item_id"], "name"] if m["item_id"] in items.index else m["item_id"]
        un = items.loc[m["item_id"], "unit"] if m["item_id"] in items.index else ""
        extra = " · ".join(x for x in [m["vehicle"], m["party"], m["machine"], m["shift"]] if x)
        c1, c2, c3 = st.columns([5, 1.3, 1.3])
        c1.write("**%s %s** %s  \n%s · %s%s" % (L.fmt(abs(L.f(m["qty"]))), un, nm, m["date"], m["user"], (" · " + extra) if extra else ""))
        if m["type"] in EDITABLE:
            with c2.popover("Edit"):
                q = st.number_input("Correct quantity", min_value=0.0, value=abs(L.f(m["qty"])), step=1.0, format="%g", key="eq" + m["id"])
                if st.button("Save", key="es" + m["id"]) and run(L.edit_move_qty, ME, m["id"], q, ok="Corrected"): st.rerun()
        if c3.button("Undo", key="u_" + m["id"]):
            run(L.void_move_group if m["type"] in ("waste", "return_decide") else L.void_move, ME, m["id"], ok="Cancelled"); st.rerun()


# ---------------------------------------------------------------- screens
def screen_stock():
    items, moves, tab = load()
    c1, c2 = st.columns([2, 1])
    q = c1.text_input("Search", placeholder="Search item, size, brand…", label_visibility="collapsed")
    cats = ["All categories"] + [c for c in L.categories(S.rows("Items"), S.rows("Lists")) if c in set(tab["category"])]
    cat = c2.selectbox("Category", cats, label_visibility="collapsed")
    only = st.toggle("Only items in stock", value=False)
    v = tab.copy()
    if cat != "All categories": v = v[v["category"] == cat]
    if q.strip():
        for w in q.lower().split(): v = v[(v["brand"] + " " + v["subcategory"] + " " + v["name"] + " " + v["category"]).str.lower().str.contains(w, regex=False)]
    if only: v = v[v["good"] > 0]
    m1, m2, m3 = st.columns(3)
    m1.metric("Items in stock", int((tab["good"] > 0).sum()))
    m2.metric("On hold (returns)", L.fmt(tab["hold"].sum()))
    if IS_ADMIN: m3.metric("Stock value", L.money(tab["value"].sum()))
    else: m3.metric("Low stock", int(((tab["min_level"] > 0) & (tab["good"] < tab["min_level"])).sum()))
    low = tab[(tab["min_level"] > 0) & (tab["good"] < tab["min_level"])]
    if not low.empty:
        with st.expander("⚠️ Below minimum (%d)" % len(low), expanded=True):
            st.dataframe(low[["brand", "name", "unit", "good", "min_level"]].rename(columns={"brand": "Brand", "name": "Item", "unit": "Unit", "good": "In stock", "min_level": "Minimum"}), hide_index=True, **WIDE)
    tm = L.today_movement(S.rows("Items"), S.rows("Moves"))
    with st.expander("Today's movement (%d items)" % len(tm), expanded=not tm.empty):
        if tm.empty: st.caption("Nothing recorded today yet.")
        else: st.dataframe(tm, hide_index=True, **WIDE, column_config={"In": st.column_config.NumberColumn(format="%g"), "Out": st.column_config.NumberColumn(format="%g")})
    cols = ["category", "brand", "subcategory", "name", "unit", "good", "hold"] + (["price", "value"] if IS_ADMIN else [])
    out = v[cols].rename(columns={"category": "Category", "brand": "Brand", "subcategory": "Sub category", "name": "Item", "unit": "Unit", "good": "In stock", "hold": "On hold", "price": "Price", "value": "Value"})
    cfg = {"In stock": st.column_config.NumberColumn(format="%g"), "On hold": st.column_config.NumberColumn(format="%g")}
    if IS_ADMIN: cfg.update({"Price": st.column_config.NumberColumn(format="₹%g"), "Value": st.column_config.NumberColumn(format="₹%d")})
    st.dataframe(out, hide_index=True, **WIDE, column_config=cfg, height=min(640, 38 + 35 * max(len(out), 2)))
    st.caption("%d items shown. Other places stock can sit: B-grade %s · To recycle %s · Scrap %s" % (len(out), L.fmt(tab["bgrade"].sum()), L.fmt(tab["recycle"].sum()), L.fmt(tab["scrap"].sum())))


def entry_picker(pre, items, tab, kinds=None, allow_new=True):
    """Category > Brand > Item. Category and brand stay selected after a save; only the item resets.
    With allow_new, each list ends with 'Other (type it)'. Returns (item_row or None, new_item dict or None, unit text)."""
    ver = st.session_state.setdefault(pre + "_ver", 0); k = lambda n: "%s_%s_%d" % (pre, n, ver); ks = lambda n: "%s_%s" % (pre, n)
    OTHER = "Other (type it)"; extra = [OTHER] if allow_new else []
    if kinds is not None: items = items[items["kind"].isin(kinds)]
    cats = [c for c in L.categories(S.rows("Items"), S.rows("Lists")) if c in set(items["category"])]
    cat = st.selectbox("Category", cats + extra, index=None, placeholder="Choose category", key=ks("c"))
    if cat == OTHER: cat = st.text_input("Type the new category", key=ks("ct")).strip()
    brand = None
    if cat:
        known = sorted(items[items["category"] == cat]["brand"].unique()) if cat in cats else sorted(items["brand"].unique())
        brand = st.selectbox("Brand", list(known) + extra, index=None, placeholder="Choose brand", key=ks("b"))
        if brand == OTHER: brand = st.text_input("Type the new brand", key=ks("bt")).strip()
    if not (cat and brand): return None, None, ""
    sub = items[(items["category"] == cat) & (items["brand"] == brand)]
    subs = sorted(s for s in sub["subcategory"].unique() if s)
    subcat = ""
    if subs or allow_new:
        sc = st.selectbox("Sub category (optional)", subs + extra, index=None, placeholder="Choose sub category" if subs else "None yet - choose Other to add one", key=ks("s"))
        if sc == OTHER: subcat = st.text_input("Type the new sub category", key=ks("st")).strip()
        elif sc: subcat = sc
        if subcat and subcat in subs: sub = sub[sub["subcategory"] == subcat]
    labels = {}
    for i in sub.index:
        lab = sub.loc[i, "name"] if (subcat or not subs) else ((sub.loc[i, "subcategory"] + " - " if sub.loc[i, "subcategory"] else "") + sub.loc[i, "name"])
        while lab in labels: lab += " ·"
        labels[lab] = i
    pick = st.selectbox("Item / size", list(labels) + extra, index=None, placeholder="Choose item / size", key=k("i"))
    if pick == OTHER:
        c1, c2 = st.columns(2)
        nm = c1.text_input("Item name (e.g. 16MM Round)", key=k("nm")).strip(); sp = c2.text_input("Size / details (e.g. 400mtr 40cm)", key=k("sp")).strip()
        unit = st.selectbox("Unit", ["rolls", "pieces", "sets", "bags", "boxes", "kg", "nos", "mtr", OTHER], index=None, placeholder="Choose unit", key=k("u"))
        if unit == OTHER: unit = st.text_input("Type the unit", key=k("ut")).strip()
        return None, dict(cat=cat, brand=brand, nm=nm, sp=sp, unit=unit or "", sub=subcat), unit or ""
    if pick:
        it = sub.loc[labels[pick]]
        st.info("Unit: **%s**   ·   Now in stock: **%s**" % (it["unit"], L.fmt(float(tab.loc[tab["id"] == it["id"], "good"].iloc[0]))))
        return it, None, it["unit"]
    return None, None, ""

def resolve_item(it, new):
    """Existing item id, or create the new item and return its id. Returns None (with a message) when something is missing."""
    if it is not None: return it["id"]
    if new is None: st.error("Choose the category, brand and item first."); return None
    if not (new["nm"] and new["unit"]): st.error("Fill the item name and unit."); return None
    if not run(L.add_item, new["cat"], new["brand"], new["nm"], new["sp"], new["unit"], 0.0, 0.0, new.get("sub", "")): return None
    row = [r for r in S.rows("Items") if r["category"] == new["cat"] and r["brand"] == new["brand"] and r["item"].lower() == new["nm"].lower() and r["spec"].lower() == new["sp"].lower() and r.get("subcategory", "").lower() == new.get("sub", "").lower()]
    return row[-1]["id"] if row else None

def reset_picker(pre): st.session_state[pre + "_ver"] = st.session_state.get(pre + "_ver", 0) + 1


def screen_addstock():
    items, _, tab = load()
    st.subheader("Add stock")
    st.caption("Use this to put in the stock you have now. It is added to what is already there. If something is not in a list, pick 'Other' and type it.")
    it, new, unit = entry_picker("as", items, tab)
    ver = st.session_state["as_ver"]
    qty = qty_box("Quantity to add", key="as_q_%d" % ver, unit=unit)
    if st.button("Save", type="primary", key="as_s_%d" % ver):
        if not qty: st.error("Enter the quantity.")
        else:
            iid = resolve_item(it, new)
            if iid and run(L.add_stock, ME, iid, qty, today(), "", nonce("as"), ok="Added %s" % L.fmt(qty)): burn("as"); reset_picker("as"); st.rerun()
    recent(["opening"])


def screen_inward():
    items, _, tab = load()
    st.subheader("Inward (purchased material / fittings)")
    st.caption("Goods received. Pick 'Other' in any list to add something new.")
    it, new, unit = entry_picker("iw", items, tab)
    ver = st.session_state["iw_ver"]
    qty = qty_box("Quantity received", key="iw_q_%d" % ver, unit=unit)
    if st.button("Save inward", type="primary", key="iw_save_%d" % ver):
        if not qty: st.error("Enter the quantity.")
        else:
            iid = resolve_item(it, new)
            if iid and run(L.add_inward, ME, iid, qty, today(), "", "", "", nonce("iw"), ok="Inward saved: %s" % L.fmt(qty)): burn("iw"); reset_picker("iw"); st.rerun()
    recent(["inward"])


def screen_production():
    items, _, _ = load()
    st.subheader("Production")
    it = pick_item("prod", items, kinds=["finished"])
    machines = L.list_values(S.rows("Lists"), "machine")
    with st.form("prod", clear_on_submit=True):
        qty = qty_box("Quantity made", unit=(it["unit"] if it is not None else ""))
        a, b, c = st.columns(3)
        shift = a.selectbox("Shift", ["", "A", "B"]); mach = b.selectbox("Machine (optional)", [""] + machines); d = c.date_input("Date", value=date.today())
        note = st.text_input("Note (optional)")
        if st.form_submit_button("Save production"):
            if it is None: st.error("Choose the item first.")
            elif run(L.add_production, ME, it["id"], qty, str(d), shift, mach, note, nonce("prod"), ok="Saved %s %s" % (L.fmt(qty), it["name"])): burn("prod"); reset_picker("prod"); st.rerun()
    recent(["production"])


def screen_dispatch():
    items, _, tab = load()
    st.subheader("Dispatch")
    vehicles = L.list_values(S.rows("Lists"), "vehicle"); parties = sorted({o["party"] for o in S.rows("Orders")} | {m["party"] for m in S.rows("Moves") if m["type"] == "dispatch" and m["party"]})
    c1, c2 = st.columns(2)
    with c1: veh = combo("Vehicle", vehicles, "d_veh", "Choose vehicle")
    with c2: party = combo("Customer / place", parties, "d_party", "Type name")
    cart = st.session_state.setdefault("cart", [])
    it = pick_item("disp", items, kinds=["finished"])
    with st.form("addline", clear_on_submit=True):
        qty = qty_box("Quantity to load", unit=(it["unit"] if it is not None else ""))
        if st.form_submit_button("➕ Add to this load"):
            if it is None or not qty: st.error("Choose an item and quantity.")
            else: cart.append((it["id"], float(qty), it["name"], it["unit"])); reset_picker("disp"); st.rerun()
    if cart:
        st.markdown("**This load**")
        for i, (iid, q, nm, un) in enumerate(cart):
            a, b = st.columns([4, 1]); a.write("%s %s — %s" % (L.fmt(q), un, nm))
            if b.button("✖", key="rm%d" % i): cart.pop(i); st.rerun()
        neg = st.checkbox("Allow sending more than stock (admin only)", value=False) if IS_ADMIN else False
        note = st.text_input("Note (optional)", key="d_note")
        if st.button("✅ Save dispatch", type="primary", key="d_save"):
            if run(L.add_dispatch, ME, [(c[0], c[1]) for c in cart], veh or "", party or "", today(), note, neg, nonce("disp"), ok="Dispatch saved"):
                burn("disp"); st.session_state["cart"] = []; st.rerun()
    st.divider(); recent(["dispatch"])


def screen_orders():
    items, _, tab = load()
    st.subheader("Orders")
    a, b = st.tabs(["To produce", "Orders"])
    with a:
        tp = L.to_produce(S)
        if tp.empty: st.info("No open orders.")
        else:
            st.dataframe(tp.rename(columns={"item": "Item", "brand": "Brand", "unit": "Unit", "ordered": "Ordered", "in_stock": "In stock", "to_make": "Make"}).drop(columns=["id"]),
                         hide_index=True, **WIDE, column_config={c: st.column_config.NumberColumn(format="%g") for c in ["Ordered", "In stock", "Make"]})
    with b:
        parties = sorted({o["party"] for o in S.rows("Orders")})
        party = combo("Customer", parties, "o_party", "Type customer name")
        it = pick_item("ord", items, kinds=["finished"])
        with st.form("ord", clear_on_submit=True):
            qty = qty_box("Quantity ordered", unit=(it["unit"] if it is not None else "")); due = st.date_input("Needed by", value=date.today() + timedelta(days=3)); note = st.text_input("Note (optional)")
            if st.form_submit_button("Save order"):
                if it is None: st.error("Choose the item first.")
                elif run(L.add_order, ME, party or "", it["id"], qty, str(due), note, ok="Order saved"): reset_picker("ord"); st.rerun()
        st.markdown("**Open orders**")
        names = items.set_index("id")["name"].to_dict(); n = 0
        for o in reversed(S.rows("Orders")):
            if o["status"] != "open": continue
            n += 1
            c1, c2, c3 = st.columns([4, 1, 1]); c1.write("**%s** — %s %s  \n%s · needed by %s" % (o["party"], L.fmt(o["qty"]), names.get(o["item_id"], "?"), o["user"], o["due"]))
            if c2.button("Done", key="od" + o["id"]): L.set_order_status(S, o["id"], "done"); st.rerun()
            if c3.button("Drop", key="oc" + o["id"]): L.set_order_status(S, o["id"], "cancelled"); st.rerun()
        if not n: st.caption("None open.")


def screen_returns():
    items, _, _ = load()
    st.subheader("Returns")
    names = items.set_index("id")["name"].to_dict(); units = items.set_index("id")["unit"].to_dict()
    st.markdown("**Record a return** — it waits on hold until it is decided.")
    parties = sorted({m["party"] for m in S.rows("Moves") if m["party"]})
    party = combo("From whom", parties, "r_party", "Customer name")
    it = pick_item("ret", items, kinds=["finished"])
    with st.form("ret", clear_on_submit=True):
        qty = qty_box("Quantity returned", unit=(it["unit"] if it is not None else "")); note = st.text_input("Reason (optional)")
        if st.form_submit_button("Save return"):
            if it is None: st.error("Choose the item first.")
            elif run(L.add_return, ME, it["id"], qty, party or "", today(), note, nonce("ret"), ok="Return saved — on hold"): burn("ret"); reset_picker("ret"); st.rerun()
    st.divider(); st.markdown("**Waiting for a decision**")
    pend = L.pending_returns(S)
    if not pend: st.caption("Nothing on hold.")
    for r in sorted(pend, key=lambda x: x["ts"], reverse=True):
        with st.container(border=True):
            st.write("**%s %s** %s  \nfrom %s · %s" % (L.fmt(r["left"]), units.get(r["item_id"], ""), names.get(r["item_id"], "?"), r["party"] or "—", r["date"]))
            if CAN_MANAGE:
                c1, c2, c3 = st.columns([1, 2, 1])
                q = c1.number_input("Qty", min_value=0.0, max_value=float(r["left"]), value=float(r["left"]), step=1.0, format="%g", key="rq" + r["id"])
                dest = c2.selectbox("Decision", ["good", "bgrade", "recycle", "scrap"], format_func=lambda x: {"good": "Back to good stock", "bgrade": "B-grade", "recycle": "Recycle", "scrap": "Scrap"}[x], key="rd" + r["id"])
                c3.write("");
                if c3.button("Apply", key="ra" + r["id"]):
                    if run(L.decide_return, ME, r["id"], q, dest, ok="Done"): st.rerun()
            else:
                st.caption("A supervisor will decide.")


def screen_raw():
    items, _, tab = load()
    st.subheader("Raw material & waste")
    a, b, c = st.tabs(["Raw in", "Raw used", "Waste / scrap"])
    with a:
        it = pick_item("rin", items, kinds=["raw"])
        with st.form("rin", clear_on_submit=True):
            qty = qty_box("Quantity received", unit=(it["unit"] if it is not None else "")); note = st.text_input("Supplier / note (optional)")
            if st.form_submit_button("Save raw in"):
                if it is None: st.error("Choose the material first.")
                elif run(L.add_raw, ME, it["id"], qty, today(), "in", note, nonce("rin"), ok="Saved"): burn("rin"); reset_picker("rin"); st.rerun()
    with b:
        it = pick_item("rout", items, kinds=["raw"])
        with st.form("rout", clear_on_submit=True):
            qty = qty_box("Quantity used", unit=(it["unit"] if it is not None else "")); note = st.text_input("Used for (optional)")
            if st.form_submit_button("Save raw used"):
                if it is None: st.error("Choose the material first.")
                elif run(L.add_raw, ME, it["id"], qty, today(), "out", note, nonce("rout"), ok="Saved"): burn("rout"); reset_picker("rout"); st.rerun()
    with c:
        it = pick_item("waste", items)
        with st.form("waste", clear_on_submit=True):
            qty = qty_box("Quantity wasted", unit=(it["unit"] if it is not None else "")); note = st.text_input("Reason (optional)")
            if st.form_submit_button("Save waste"):
                if it is None: st.error("Choose the item first.")
                elif run(L.add_waste, ME, it["id"], qty, today(), note, nonce("waste"), ok="Saved"): burn("waste"); reset_picker("waste"); st.rerun()
    recent(["raw_in", "raw_use", "waste"])


def screen_count():
    items, _, tab = load()
    st.subheader("Stock count")
    st.caption("Type what you actually counted. Leave blank to skip. Saving sets the stock to your number.")
    cats = [c for c in L.categories(S.rows("Items"), S.rows("Lists")) if c in set(tab["category"])]
    cat = st.selectbox("Category", cats, key="cnt_c")
    v = tab[tab["category"] == cat]
    df = pd.DataFrame({"id": v["id"], "Item": v["brand"] + " | " + (v["subcategory"] + " - " if False else "") + v["name"], "Unit": v["unit"], "System": v["good"], "Counted": [None] * len(v)})
    ed = st.data_editor(df, hide_index=True, **WIDE, disabled=["Item", "Unit", "System", "id"], column_order=["Item", "Unit", "System", "Counted"],
                        column_config={"Counted": st.column_config.NumberColumn(min_value=0, format="%g"), "System": st.column_config.NumberColumn(format="%g")}, key="cnt_ed_" + cat)
    if st.button("Save counts", type="primary"):
        got = {r["id"]: r["Counted"] for _, r in ed.iterrows() if pd.notna(r["Counted"])}
        if not got: st.warning("Nothing typed yet.")
        else:
            try:
                n = L.add_counts(S, ME, got); st.toast("Updated %d items" % n, icon="✅"); st.rerun()
            except L.Problem as e: st.error(str(e))


def screen_reports():
    items, moves, tab = load()
    st.subheader("Reports")
    c1, c2 = st.columns(2); d1 = c1.date_input("From", value=date.today() - timedelta(days=6)); d2 = c2.date_input("To", value=date.today())
    live = moves[~moves["void"] & (moves["date"] >= str(d1)) & (moves["date"] <= str(d2))].merge(items[["id", "name", "brand", "category", "unit", "price"]], left_on="item_id", right_on="id", how="left")
    t1, t2, t3, t4, t5 = st.tabs(["Production", "Dispatch", "Low stock", "Value" if IS_ADMIN else "Stock", "Inward"])
    with t1:
        p = live[live["type"] == "production"]
        if p.empty: st.caption("No production in these dates.")
        else:
            g = p.groupby(["category", "brand", "name", "unit"], as_index=False)["qty"].sum().rename(columns={"qty": "Made"}); st.dataframe(g, hide_index=True, **WIDE)
            st.download_button("Download CSV", g.to_csv(index=False), "production.csv", "text/csv")
    with t2:
        p = live[live["type"] == "dispatch"].copy(); p["qty"] = -p["qty"]
        if p.empty: st.caption("No dispatch in these dates.")
        else:
            by = st.radio("Group by", ["vehicle", "party", "name"], horizontal=True, format_func=lambda x: {"vehicle": "Vehicle", "party": "Customer", "name": "Item"}[x])
            g = p.groupby([by, "unit"], as_index=False)["qty"].sum().rename(columns={"qty": "Sent"}); st.dataframe(g, hide_index=True, **WIDE)
            full = p[["date", "vehicle", "party", "brand", "name", "unit", "qty", "user"]].rename(columns={"qty": "sent"})
            st.download_button("Download full list (CSV)", full.to_csv(index=False), "dispatch.csv", "text/csv")
    with t3:
        low = tab[(tab["min_level"] > 0) & (tab["good"] < tab["min_level"])][["category", "brand", "name", "unit", "good", "min_level"]]
        if low.empty: st.caption("Nothing below its minimum (set minimums in Admin → Items).")
        else: st.dataframe(low.rename(columns={"good": "In stock", "min_level": "Minimum"}), hide_index=True, **WIDE)
    with t5:
        p = live[live["type"] == "inward"]
        if p.empty: st.caption("No inward entries in these dates.")
        else:
            full = p[["date", "category", "brand", "name", "unit", "qty", "user"]].rename(columns={"qty": "received"})
            st.dataframe(full, hide_index=True, **WIDE); st.download_button("Download inward list (CSV)", full.to_csv(index=False), "inward.csv", "text/csv")
    with t4:
        if IS_ADMIN:
            g = tab.groupby("category", as_index=False).agg(Value=("value", "sum")); g["Value"] = g["Value"].round(0)
            st.metric("Total stock value", L.money(tab["value"].sum()))
            st.dataframe(g.rename(columns={"category": "Category"}), hide_index=True, **WIDE, column_config={"Value": st.column_config.NumberColumn(format="₹%d")})
            st.download_button("Download stock sheet (CSV)", tab[["category", "brand", "name", "unit", "good", "hold", "price", "value"]].to_csv(index=False), "stock.csv", "text/csv")
        else:
            st.download_button("Download stock sheet (CSV)", tab[["category", "brand", "name", "unit", "good", "hold"]].to_csv(index=False), "stock.csv", "text/csv")


def screen_admin():
    st.subheader("Admin")
    t1, t2, t3, t4, t5 = st.tabs(["Prices & items", "People", "Lists", "History", "Backup"])
    with t1:
        items = L.items_df(S.rows("Items"), False)
        st.caption("Edit price, minimum level or sub category and press Save. To put several items in a sub category, type it in each row. Untick 'Active' to hide an item.")
        cats = ["All"] + L.categories(S.rows("Items"), S.rows("Lists")); cat = st.selectbox("Category", cats, key="adm_c")
        v = items if cat == "All" else items[items["category"] == cat]
        ed = st.data_editor(v[["_r", "brand", "subcategory", "name", "unit", "price", "min_level", "active"]].rename(columns={"name": "Item"}), hide_index=True, **WIDE,
                            disabled=["_r", "brand", "Item", "unit"], column_order=["brand", "subcategory", "Item", "unit", "price", "min_level", "active"], key="adm_ed_" + cat,
                            column_config={"subcategory": st.column_config.TextColumn("Sub category"), "price": st.column_config.NumberColumn("Price ₹", min_value=0, format="%g"), "min_level": st.column_config.NumberColumn("Minimum", min_value=0, format="%g")})
        if st.button("Save changes", type="primary"):
            raw = {r["_r"]: r for r in S.rows("Items")}; n = 0
            for _, r in ed.iterrows():
                o = raw[int(r["_r"])]; new = dict(o); new["price"] = L.f(r["price"]); new["min_level"] = L.f(r["min_level"]); new["active"] = 1 if r["active"] else 0
                new["subcategory"] = ("" if pd.isna(r["subcategory"]) else str(r["subcategory"])).strip()
                if (L.f(o["price"]), L.f(o["min_level"]), str(o["active"]) in ("1", "True", "true"), o.get("subcategory", "").strip()) != (new["price"], new["min_level"], bool(r["active"]), new["subcategory"]): S.update("Items", int(r["_r"]), new); n += 1
            st.toast("Saved %d changes" % n, icon="✅")
        st.divider(); st.markdown("**Add a new item**")
        allc = L.categories(S.rows("Items"), S.rows("Lists"))
        with st.form("newitem", clear_on_submit=True):
            c1, c2 = st.columns(2); nc = c1.selectbox("Category", allc); br = c2.text_input("Brand", value="Evergreen")
            sc = st.text_input("Sub category (optional)"); nm = st.text_input("Item name (e.g. 16 Round)"); sp = st.text_input("Size / details (e.g. 400mtr 40cm)")
            c3, c4, c5 = st.columns(3); un = c3.selectbox("Unit", ["rolls", "pieces", "sets", "bags", "boxes", "kg", "nos"]); pr = c4.number_input("Price ₹", min_value=0.0, value=0.0); mn = c5.number_input("Minimum", min_value=0.0, value=0.0)
            if st.form_submit_button("Add item"): run(L.add_item, nc, br, nm, sp, un, pr, mn, sc, ok="Item added")
    with t2:
        us = L.users(S)
        st.dataframe(pd.DataFrame(us)[["name", "role", "active"]] if us else pd.DataFrame(), hide_index=True, **WIDE)
        with st.form("newuser", clear_on_submit=True):
            st.markdown("**Add a person**"); c1, c2, c3 = st.columns(3); nm = c1.text_input("Name"); ro = c2.selectbox("Role", L.ROLES, index=2); pn = c3.text_input("PIN (4+ digits)", type="password")
            if st.form_submit_button("Add person"): run(L.make_user, nm, ro, pn, ok="Added")
        with st.form("pinreset", clear_on_submit=True):
            st.markdown("**Change a PIN / switch someone off**"); c1, c2 = st.columns(2); who = c1.selectbox("Person", [u["name"] for u in us]); pn = c2.text_input("New PIN", type="password")
            a, b = st.columns(2)
            if a.form_submit_button("Set new PIN"): run(L.set_pin, who, pn, ok="PIN changed")
            if b.form_submit_button("Switch off / on"):
                u = next(x for x in us if x["name"] == who)
                if who == ME: st.error("You cannot switch yourself off.")
                else: L.update_user(S, who, active=0 if str(u["active"]) in ("1", "True", "true") else 1); st.toast("Done", icon="✅"); st.rerun()
        st.caption("Roles — supervisor: everything except prices/people. operator: production, count, raw. loader: stock, dispatch, returns. sales: stock, orders, returns. Only admin sees prices and value.")
    with t3:
        for kind, title in (("category", "Categories"), ("vehicle", "Vehicles"), ("machine", "Machines")):
            st.markdown("**%s:** %s" % (title, ", ".join(L.list_values(S.rows("Lists"), kind)) or "—"))
            with st.form("l_" + kind, clear_on_submit=True):
                c1, c2 = st.columns([3, 1]); nm = c1.text_input("New %s" % kind, label_visibility="collapsed", placeholder="Add a %s" % kind)
                if c2.form_submit_button("Add"): run(L.add_list, kind, nm, ok="Added")
        st.caption("To rename or remove a list entry, edit the 'Lists' tab of the Google Sheet.")
    with t4:
        items = L.items_df(S.rows("Items"), False).set_index("id")["name"].to_dict()
        rows = [m for m in reversed(S.rows("Moves"))][:60]
        for m in rows:
            c1, c2 = st.columns([5, 1]); gone = str(m["void"]) in ("1", "True", "true")
            c1.write(("~~" if gone else "") + "%s · **%s** %s %s · %s · %s" % (m["ts"][5:16], m["type"], L.fmt(m["qty"]), items.get(m["item_id"], "?"), m["bucket"], m["user"]) + ("~~" if gone else ""))
            if not gone and c2.button("Cancel", key="h" + m["id"]): run(L.void_move_group, ME, m["id"], ok="Cancelled"); st.rerun()
    with t5:
        st.write("**Google Sheet register.** The app keeps a tab called *%s* in your Google Sheet up to date by itself: Opening, In, Out and Closing for every day, in your Excel layout. You never type in the Sheet." % ("Register " + today()[:7]))
        if S.sync_error: st.warning("Last sheet update failed: " + S.sync_error)
        st.write("**Daily backup:** a copy of all your data is saved once a day as a tab called *Backup <date>* in the Google Sheet. The last 7 days are kept. " + ("Today's backup is done." if S.bk_day == today() else "Today's backup is not done yet."))
        if S.bk_error: st.warning("Last backup problem: " + S.bk_error)
        if st.button("Back up now"):
            try: L.backup_now(S, today()); S.bk_day = today(); st.toast("Backup saved", icon="✅")
            except Exception as e: st.error("Could not back up: %s" % str(e)[:200])
        if st.button("Update the Google Sheet now"):
            try: L.sync_register(S); S.synced = S.writes; st.toast("Sheet updated", icon="✅")
            except Exception as e: st.error("Could not update the sheet: %s" % str(e)[:200])
        st.divider(); st.markdown("**Start again with zero stock**")
        st.caption("Sets every item's stock to 0. Nothing is deleted; the history stays. Use it once before you begin.")
        sure = st.text_input("Type RESET to confirm", key="reset_ok")
        if st.button("Set all stock to zero") and sure.strip() == "RESET":
            n = L.reset_all_stock(S, ME); st.toast("Stock set to zero for %d items" % n, icon="✅")
        st.divider()
        st.write("Your data lives in %s." % ("your Google Sheet (you can open it any time)" if LIVE else "the folder `trial_data` on this computer"))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for t in ("Items", "Moves", "Orders", "Lists"):
                z.writestr(t + ".csv", pd.DataFrame(S.rows(t)).drop(columns=["_r"], errors="ignore").to_csv(index=False))
        st.download_button("Download a full backup (zip)", buf.getvalue(), "evergreen-backup-%s.zip" % today(), "application/zip")


SCREENS = {"Stock": screen_stock, "Inward": screen_inward, "Add Stock": screen_addstock, "Production": screen_production, "Dispatch": screen_dispatch, "Orders": screen_orders, "Returns": screen_returns,
           "Raw & Waste": screen_raw, "Count": screen_count, "Reports": screen_reports, "Admin": screen_admin}

st.markdown("### 🌿 Evergreen Stock" + ("" if LIVE else "  ·  TRIAL"))
with st.sidebar:
    st.write("Signed in: **%s** (%s)" % (ME, ROLE))
    if st.button("Sign out"):
        L.end_session(S, st.session_state.get("tok")); set_cookie(None); st.session_state.clear(); st.query_params.clear(); st.rerun()
nav = L.NAV[ROLE]
page = st.radio("Go to", nav, horizontal=True, label_visibility="collapsed", key="page")
try:
    SCREENS[page]()
except Exception as e:  # never show a stack trace to staff
    st.error("Something went wrong. Please refresh the page. (%s)" % str(e)[:140])
    if os.environ.get("STOCK_DEBUG"): raise
