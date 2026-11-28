"""Evergreen Stock - one app for stock, production, dispatch, orders, returns, raw material and reports."""
import html
import io, os, time, zipfile, hashlib
from datetime import date, timedelta
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import importlib
import logic as L
import wa
import store as _store
RELEASE = "2026-11-28-a"        # change on every release; it makes the app reload its own parts after an update
if getattr(L, "LOGIC_VERSION", None) != RELEASE or "Fleet" not in _store.SCHEMA:
    importlib.reload(_store); importlib.reload(L)
from store import Store, LocalBackend, SheetsBackend, today, new_id, SCHEMA

st.set_page_config(page_title="Evergreen Stock", page_icon="🌿", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
:root{--g1:#0f5132;--g2:#1b7f4b;--g3:#e7f4ec;--ink:#17261d;--mute:#5f7366;--line:#e3ebe5;--card:#ffffff;--bg:#f4f7f5}
html,body,.stApp,.stApp p,.stApp label,.stApp button,.stApp input,.stApp textarea,.stApp h1,.stApp h2,.stApp h3,.stApp li,.stApp td,.stApp th{font-family:system-ui,-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif}
span[data-testid="stIconMaterial"]{font-family:'Material Symbols Rounded'!important}
.stApp{background:var(--bg)}
header[data-testid="stHeader"]{background:transparent}
.block-container{padding-top:1rem;padding-bottom:4rem;max-width:1080px}
/* top banner */
.eg-hero{background:linear-gradient(135deg,var(--g1),var(--g2));color:#fff;border-radius:18px;padding:1rem 1.2rem;margin:0 0 .9rem;display:flex;justify-content:space-between;align-items:center;gap:.8rem;box-shadow:0 8px 22px rgba(15,81,50,.22)}
.eg-hero .t{font-size:1.35rem;font-weight:700;letter-spacing:-.01em;line-height:1.2}
.eg-hero .s{font-size:.82rem;opacity:.85;margin-top:.15rem}
.eg-hero .pill{background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.3);border-radius:999px;padding:.3rem .75rem;font-size:.8rem;font-weight:600;white-space:nowrap}
/* page menu as pills */
.st-key-menu div[role="radiogroup"]{flex-wrap:nowrap!important;overflow-x:auto;gap:.4rem!important;padding:.2rem .1rem .5rem;scrollbar-width:none}
.st-key-menu div[role="radiogroup"]::-webkit-scrollbar{display:none}
.st-key-menu div[role="radiogroup"]>div{flex:0 0 auto}
.st-key-menu label[data-testid="stRadioOption"],.st-key-menu label[data-baseweb="radio"]{background:var(--card);border:1px solid var(--line);border-radius:999px;padding:.42rem .95rem;margin:0;white-space:nowrap;cursor:pointer;transition:all .15s;box-shadow:0 1px 2px rgba(0,0,0,.04);flex:0 0 auto}
.st-key-menu label[data-testid="stRadioOption"]>div>div:first-child,.st-key-menu label[data-baseweb="radio"]>div:first-child{display:none}
.st-key-menu label p{font-size:.9rem;font-weight:500;color:var(--ink);white-space:nowrap}
.st-key-menu label[data-testid="stRadioOption"]:hover,.st-key-menu label[data-baseweb="radio"]:hover{border-color:var(--g2)}
.st-key-menu label[data-selected="true"],.st-key-menu label:has(input:checked){background:var(--g2);border-color:var(--g2);box-shadow:0 4px 12px rgba(27,127,75,.3)}
.st-key-menu label[data-selected="true"] p,.st-key-menu label:has(input:checked) p{color:#fff;font-weight:600}
.sh{background:#fff;border:1px solid var(--line);border-radius:16px;padding:.7rem .8rem;box-shadow:0 2px 8px rgba(23,38,29,.05)}
.sh-t{font-weight:700;color:var(--g1);font-size:1rem;margin-bottom:.4rem;display:flex;justify-content:space-between;gap:.5rem}.sh-t span{font-weight:500;color:var(--mute);font-size:.8rem}
.sh{overflow-x:auto}.sh table{width:100%;border-collapse:collapse;font-size:.82rem}
.sh th{text-align:left;color:var(--mute);font-weight:600;font-size:.72rem;text-transform:uppercase;letter-spacing:.03em;padding:.35rem .4rem;border-bottom:2px solid var(--line)}
.sh td{padding:.38rem .4rem;border-bottom:1px solid var(--line);vertical-align:top;word-break:break-word;color:var(--ink)}
.sh .sm{color:var(--mute);font-size:.72em}.sh .n{text-align:right;white-space:nowrap}.sh .b{font-weight:700;color:#b3261e}
.sh tr:nth-child(even) td{background:#f8fbf9}
@media(max-width:640px){.sh table{font-size:.72rem}.sh td,.sh th{padding:.3rem .25rem}}
/* cards */
div[data-testid="stMetric"]{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:.8rem 1rem;box-shadow:0 2px 8px rgba(23,38,29,.05)}
div[data-testid="stMetricValue"]{font-size:1.5rem;font-weight:700;color:var(--g1)}
div[data-testid="stMetricLabel"] p{font-size:.78rem;color:var(--mute);font-weight:500;text-transform:uppercase;letter-spacing:.04em}
div[data-testid="stExpander"]{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:0 2px 8px rgba(23,38,29,.04)}
div[data-testid="stForm"],div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > div[data-testid="stVerticalBlock"] > .stMarkdown){border-radius:16px}
div[data-testid="stForm"]{background:var(--card);border:1px solid var(--line);box-shadow:0 2px 8px rgba(23,38,29,.04)}
div[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:0 2px 8px rgba(23,38,29,.04)}
/* inputs */
div[data-baseweb="input"]>div,div[data-baseweb="select"]>div,div[data-baseweb="base-input"]{border-radius:12px;border-color:var(--line);background:var(--card)}
div[data-baseweb="input"]:focus-within>div,div[data-baseweb="select"]:focus-within>div{border-color:var(--g2);box-shadow:0 0 0 3px rgba(27,127,75,.15)}
label p{font-weight:500;color:var(--ink)}
/* buttons */
.stButton button,.stFormSubmitButton button,.stDownloadButton button{width:100%;min-height:2.8rem;font-weight:600;border-radius:12px;border:1px solid var(--line);background:var(--card);color:var(--ink);transition:all .15s}
.stButton button:hover,.stFormSubmitButton button:hover{border-color:var(--g2);color:var(--g2);transform:translateY(-1px)}
.stButton button[kind="primary"],.stFormSubmitButton button[kind="primary"]{background:linear-gradient(135deg,var(--g2),var(--g1));color:#fff;border:0;box-shadow:0 6px 16px rgba(27,127,75,.3)}
.stButton button[kind="primary"]:hover{color:#fff;filter:brightness(1.07)}
/* tabs */
div[data-baseweb="tab-list"]{overflow-x:auto;gap:.3rem;border-bottom:1px solid var(--line)}
button[data-baseweb="tab"]{padding:.5rem .9rem;border-radius:10px 10px 0 0;font-weight:500}
button[data-baseweb="tab"][aria-selected="true"]{color:var(--g1);font-weight:700}
div[data-baseweb="tab-highlight"]{background:var(--g2);height:3px;border-radius:3px}
h3,h2{letter-spacing:-.01em;color:var(--ink)}
div[data-testid="stAlert"]{border-radius:12px}
hr{border-color:var(--line)}
@media(min-width:900px){.st-key-menu div[role="radiogroup"]{flex-wrap:wrap!important;overflow:visible!important}}
@media(max-width:640px){div[data-testid="stHorizontalBlock"]:has(div[data-testid="stMetric"]){flex-wrap:nowrap!important;gap:.5rem!important}div[data-testid="stHorizontalBlock"]:has(div[data-testid="stMetric"])>div{min-width:0!important;flex:1 1 0!important}div[data-testid="stMetric"]{padding:.55rem .6rem}div[data-testid="stMetricValue"]{font-size:.92rem}div[data-testid="stMetricLabel"] *{white-space:normal!important;overflow:visible!important;text-overflow:clip!important}div[data-testid="stMetricLabel"] p{font-size:.62rem}.block-container{padding-left:.8rem;padding-right:.8rem}.eg-hero .t{font-size:1.15rem}.eg-hero{padding:.8rem .9rem}}
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
S = get_store(APP_VERSION)


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


QUIET = {"make_user", "set_pin", "login"}      # never write PINs into the log


def act(action, detail="", result="ok", t0=None):
    """Record one activity (who, where, what, how long) in the Log tab. Never breaks the app."""
    try:
        S.log(st.session_state.get("me", ""), st.session_state.get("role", ""), action, st.session_state.get("page", ""), detail, result, int((time.time() - t0) * 1000) if t0 else "")
    except Exception:
        pass


def run(fn, *a, ok=None, **k):
    """Run a save; show a plain message on a problem. Returns True when saved."""
    t0 = time.time(); name = fn.__name__
    detail = ", ".join(str(x) for x in a)[:240] if name not in QUIET else str(a[0])
    try:
        fn(S, *a, **k)
    except L.Problem as e:
        act(name, detail + " -> " + str(e), "problem", t0); st.error(str(e)); return False
    except Exception as e:
        act(name, detail + " -> " + str(e)[:120], "error", t0); st.error("Could not save. Please try again. (%s)" % str(e)[:160]); return False
    act(name, detail, "ok", t0)
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
    if u and u["role"] == "admin" and not (tok or "").startswith("r.") and tok != (st.session_state.get("tok") or st.context.cookies.get("sb_s")):
        return None          # an admin login is accepted from a link only if the admin chose "keep me signed in" (token starts r.)
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
        keep = st.checkbox("Keep me signed in on this phone (admin: do not share the page link afterwards)", value=True)
        if st.form_submit_button("Open"):
            try:
                tok, u = L.login(S, nm, pin, keep)
            except L.Problem as e:
                S.log(nm, "", "login", "login", str(e), "problem"); st.error(str(e)); return
            S.log(nm, u["role"], "login", "login", "signed in")
            st.session_state["tok"] = tok; (None if (u["role"] == "admin" and not tok.startswith("r.")) else st.query_params.__setitem__("s", tok)); set_cookie(tok); st.rerun()
    st.caption("You stay signed in on this phone. You will not need to type the PIN again.")


try:
    user = current_user()
except RuntimeError as e:      # the Google Sheet could not be reached: say why in plain words instead of a red stack trace
    st.markdown("### 🌿 Evergreen Stock")
    msg = str(e)
    st.error("The app could not reach the Google Sheet. " + ("Google said: " + msg[:260] if "Google Sheets" in msg else msg[:260]))
    st.caption("Wait one minute and press the button. If it keeps happening, send this message to your helper.")
    if st.button("Try again"): st.rerun()
    st.stop()
if not user:
    login_screen(); st.stop()
st.session_state["tok"] = token_in()
if user["role"] == "admin" and not (st.session_state["tok"] or "").startswith("r."):
    if "s" in st.query_params: del st.query_params["s"]
elif st.query_params.get("s") != st.session_state["tok"]: st.query_params["s"] = st.session_state["tok"]
if st.context.cookies.get("sb_s") != st.session_state["tok"]: set_cookie(st.session_state["tok"])
ME, ROLE = user["name"], user["role"]
st.session_state["me"], st.session_state["role"] = ME, ROLE
if not st.session_state.get("_opened"):          # once per visit: who opened the app, on what kind of device
    st.session_state["_opened"] = True
    try: ua = (st.context.headers.get("User-Agent") or "").lower()
    except Exception: ua = ""
    act("open", "phone" if ("mobile" in ua or "android" in ua or "iphone" in ua) else ("computer" if ua else ""))
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

def slip_button(ref, label, key):
    try:
        load = L.dispatch_load(S, ref)
        if not load: return
        import slip as _slip
        st.download_button(label, _slip.make_slip(load), "dispatch-%s.pdf" % L.trip_of(ref)[:6], "application/pdf", key=key)
    except Exception as e:
        st.caption("Slip not available (%s)" % str(e)[:80])


def recent(types, n=8, mine_only=False):
    """Latest entries, each with Edit (quantity) and Undo."""
    rows = [m for m in S.rows("Moves") if m["type"] in types and str(m["void"]) not in ("1", "True", "true") and m["bucket"] in ("good", "hold")]
    if mine_only or not CAN_MANAGE: rows = [m for m in rows if m["user"] == ME and m["date"] == today()]
    show = list(reversed(rows))[:n]
    if not show: return
    items = L.items_df(S.rows("Items"), False).set_index("id")
    st.markdown("**Latest entries**"); shown_refs = set()
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
                nd = st.date_input("Correct date" + (" (whole load)" if m["type"] == "dispatch" else ""), value=date.fromisoformat(m["date"]), max_value=date.today(), key="ed" + m["id"])
                if st.button("Change date", key="ec" + m["id"]) and run(L.edit_move_date, ME, m["id"], str(nd), ok="Date changed"): st.rerun()
        if m["type"] == "dispatch" and L.trip_of(m["ref"]) not in shown_refs:
            shown_refs.add(L.trip_of(m["ref"])); slip_button(m["ref"], "Slip (PDF)", "sl_" + m["id"])
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
        for w in q.lower().split(): v = v[(v["brand"] + " " + v["name"] + " " + v["category"]).str.lower().str.contains(w, regex=False)]
    if only: v = v[v["good"] > 0]
    m1, m2, m3 = st.columns(3)
    m1.metric("Items in stock", int((tab["good"] > 0).sum()))
    m2.metric("On hold (returns)", L.fmt(tab["hold"].sum()))
    if IS_ADMIN: m3.metric("Stock value", L.money(tab["value"].sum()))
    else: m3.metric("Low stock", int(((tab["min_level"] > 0) & (tab["good"] < tab["min_level"])).sum()))
    low = tab[(tab["min_level"] > 0) & (tab["good"] < tab["min_level"])]
    if not low.empty:
        with st.expander("⚠️ Below minimum (%d)" % len(low), expanded=True):
            df_share("Below minimum", low[["brand", "name", "unit", "good", "min_level"]].rename(columns={"brand": "Brand", "name": "Item", "unit": "Unit", "good": "In stock", "min_level": "Minimum"}), bold=("In stock",))
    po = L.pending_orders(S)
    if not po.empty:
        late = int((po["Days_left"].fillna(1) < 0).sum())
        with st.expander("📦 Pending orders (%d lines%s)" % (len(po), ", %d late" % late if late else ""), expanded=bool(late)):
            po = po.copy(); po["When"] = po["Days_left"].map(lambda d: "" if d is None or d != d else ("%d day(s) late" % -d if d < 0 else ("due today" if d == 0 else "in %d day(s)" % d)))
            df_share("Pending orders", po[["Customer", "Category", "Item", "Pending", "Unit", "Needed_by", "When"]].rename(columns={"Needed_by": "Needed by"}))
    if CAN_MANAGE:
        with st.expander("📋 Today's summary, ready to copy"):
            st.code(L.daily_summary(S), language=None)
    with st.expander("↩️ My latest entries (undo a mistake)"):
        recent(["production", "dispatch", "inward", "opening", "return", "raw_in", "raw_use", "waste"], n=10, mine_only=True)
    tm = L.today_movement(S.rows("Items"), S.rows("Moves"))
    with st.expander("Today's movement (%d items)" % len(tm), expanded=not tm.empty):
        if tm.empty: st.caption("Nothing recorded today yet.")
        else: df_share("Today's movement", tm)
    cols = ["category", "brand", "name", "unit", "good", "hold"] + (["price", "value"] if IS_ADMIN else [])
    out = v[cols].rename(columns={"category": "Category", "brand": "Brand", "name": "Item", "unit": "Unit", "good": "In stock", "hold": "On hold", "price": "Price", "value": "Value"})
    cfg = {"In stock": st.column_config.NumberColumn(format="%g"), "On hold": st.column_config.NumberColumn(format="%g")}
    if IS_ADMIN:
        cfg.update({"Price": st.column_config.NumberColumn(format="₹%g")}); out["Value"] = out["Value"].map(L.money)
    df_share("Stock" if cat == "All categories" else cat, out, sub="%s · %d items" % (date.today().strftime("%d %b %Y"), len(out)))
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
    labels = {}
    for i in sub.index:
        lab = sub.loc[i, "name"]
        while lab in labels: lab += " ·"
        labels[lab] = i
    pick = st.selectbox("Item / size", list(labels) + extra, index=None, placeholder="Choose item / size", key=k("i"))
    if pick == OTHER:
        c1, c2 = st.columns(2)
        nm = c1.text_input("Item name (e.g. 16MM Round)", key=k("nm")).strip(); sp = c2.text_input("Size / details (e.g. 400mtr 40cm)", key=k("sp")).strip()
        unit = st.selectbox("Unit", ["rolls", "pieces", "sets", "bags", "boxes", "kg", "nos", "mtr", OTHER], index=None, placeholder="Choose unit", key=k("u"))
        if unit == OTHER: unit = st.text_input("Type the unit", key=k("ut")).strip()
        return None, dict(cat=cat, brand=brand, nm=nm, sp=sp, unit=unit or ""), unit or ""
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
    if not run(L.add_item, new["cat"], new["brand"], new["nm"], new["sp"], new["unit"], 0.0, 0.0): return None
    row = [r for r in S.rows("Items") if r["category"] == new["cat"] and r["brand"] == new["brand"] and r["item"].lower() == new["nm"].lower() and r["spec"].lower() == new["sp"].lower()]
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


def draft_restore(screen, pre_keys):
    """Once per visit: put back what was half-typed on this screen (stored per person in the Drafts tab)."""
    fl = "_dr_" + screen
    if st.session_state.get(fl): return
    st.session_state[fl] = True
    try: dr = L.draft_get(S, ME, screen)
    except Exception: dr = None
    if not dr: return
    ver = st.session_state.get(pre_keys[0] + "_ver", 0) if pre_keys else 0
    for k, v in dr.items():
        k = k.replace("@v", str(ver))
        if k not in st.session_state: st.session_state[k] = v
    st.session_state["_dr_back_" + screen] = True

def draft_save(screen, keys, pre=None):
    """After the widgets: write what is typed so far, only when it changed. Empty = clear."""
    ver = st.session_state.get(pre + "_ver", 0) if pre else 0
    snap = {}
    for k in keys:
        if k in st.session_state:
            v = st.session_state[k]
            if isinstance(v, (str, int, float, bool)) and v not in ("", None): snap[k] = v
    if pre:
        for k, v in list(st.session_state.items()):
            if k.startswith(pre + "_") and k.endswith("_%d" % ver) and isinstance(v, (str, int, float, bool)) and v not in ("", None): snap[k[:-len(str(ver))] + "@v"] = v
        for k in (pre + "_c", pre + "_b", pre + "_ct", pre + "_bt"):
            v = st.session_state.get(k)
            if isinstance(v, str) and v: snap[k] = v
    key = "_dl_" + screen
    if st.session_state.get(key) == snap: return
    if snap and time.time() - st.session_state.get("_dlt_" + screen, 0) < 6: return      # at most one write every few seconds, so typing stays fast
    st.session_state["_dlt_" + screen] = time.time()
    st.session_state[key] = snap
    try: L.draft_put(S, ME, screen, snap or None)
    except Exception as e: act("draft_error", str(e)[:120], "error")

def draft_banner(screen, keys, pre=None):
    if st.session_state.get("_dr_back_" + screen):
        a, b = st.columns([4, 1]); a.info("What you had typed here before was brought back. Check it, then save. Or press Discard.")
        if b.button("Discard", key="drd_" + screen):
            for k in list(st.session_state.keys()):
                if k in keys or (pre and k.startswith(pre + "_")): st.session_state.pop(k, None)
            st.session_state["_dr_back_" + screen] = False; st.session_state["_dl_" + screen] = {}
            try: L.draft_put(S, ME, screen, None)
            except Exception: pass
            st.rerun()


def screen_production():
    items, _, tab = load()
    st.subheader("Production")
    PK = ["p_qty", "p_shift", "p_mach", "p_note"]
    draft_restore("production", ["prod"]); draft_banner("production", PK, "prod")
    st.caption("Making something that is not in the list yet? Pick 'Other (type it)' in Category, Brand or Item. It is added as a new product when you save.")
    it, new, unit = entry_picker("prod", items, tab, kinds=["finished"])
    machines = L.list_values(S.rows("Lists"), "machine")
    qty = qty_box("Quantity made", key="p_qty", unit=unit)
    a, b, c = st.columns(3)
    shift = a.selectbox("Shift", ["", "A", "B"], key="p_shift"); mach = b.selectbox("Machine (optional)", [""] + machines, key="p_mach"); d = c.date_input("Date", value=date.today(), max_value=date.today(), key="p_date")
    note = st.text_input("Note (optional)", key="p_note")
    if st.button("Save production", type="primary", key="p_save"):
        iid = resolve_item(it, new)
        if iid and run(L.add_production, ME, iid, qty, str(d), shift, mach, note, nonce("prod"), ok="Saved %s" % L.fmt(qty)):
            burn("prod"); reset_picker("prod")
            for k in ("p_qty", "p_note"): st.session_state.pop(k, None)
            st.session_state["_dl_production"] = {}
            try: L.draft_put(S, ME, "production", None)
            except Exception: pass
            st.session_state["_dr_back_production"] = False; st.rerun()
    draft_save("production", PK, "prod")
    recent(["production"])


def trip_no_pick(vehicle, day, key):
    """If this vehicle already has a dispatch saved for the day, ask whether this is the same trip or another one. Returns the trip number to save ('' for trip 1)."""
    done = L.vehicle_trip_nos(S.rows("Moves"), vehicle or "", day) if (vehicle or "").strip() else []
    if not done: return ""
    nxt = str(max(int(x) for x in done if x.isdigit()) + 1) if any(x.isdigit() for x in done) else "2"
    ch = st.radio("%s already has a dispatch saved on this date (trip %s). This load is:" % (" ".join(vehicle.upper().split()), ", ".join(done)), ["The same trip (more customers)", "Another trip (it came back and went again)"], key=key)
    return "" if ch.startswith("The same") else nxt


def dispatch_draft_save(cart):
    try:
        L.draft_put(S, ME, "dispatch", dict(cart=[list(c) for c in cart], veh=st.session_state.get("d_veh", ""), note=st.session_state.get("d_note", ""),
                                            date=str(st.session_state.get("d_date", date.today()))) if cart else None)
    except Exception as e: act("draft_error", str(e)[:120], "error")


def screen_dispatch():
    items, _, tab = load()
    st.subheader("Dispatch")
    if not st.session_state.get("_dd_done"):      # once per visit: bring back a dispatch that was half-entered when the page reloaded or logged out
        st.session_state["_dd_done"] = True
        try: dr = L.draft_get(S, ME, "dispatch")
        except Exception: dr = None
        if dr and dr.get("cart") and not st.session_state.get("cart"):
            st.session_state["cart"] = [tuple(c) for c in dr["cart"]]
            if dr.get("veh"): st.session_state["d_veh"] = dr["veh"]
            if dr.get("note"): st.session_state["d_note"] = dr["note"]
            try:
                dd = date.fromisoformat(dr.get("date", ""))
                if dd <= date.today(): st.session_state["d_date"] = dd
            except Exception: pass
            st.session_state["_dd_back"] = True
    if st.session_state.get("_dd_back") and st.session_state.get("cart"):
        ca, cb = st.columns([4, 1]); ca.info("Your unsaved dispatch was brought back. Check it, then save. Or press Discard to start fresh.")
        if cb.button("Discard", key="dd_discard"):
            st.session_state["cart"] = []; st.session_state["_dd_back"] = False; dispatch_draft_save([]); st.rerun()
    vehicles = L.list_values(S.rows("Lists"), "vehicle"); parties = L.all_parties(S)
    c1, c2 = st.columns(2)
    with c1:
        veh = st.text_input("Vehicle number", key="d_veh", placeholder="Type it, e.g. KA 06 AB 1234")
        recent_v = []
        for m in reversed(S.rows("Moves")):
            if m["type"] == "dispatch" and m["vehicle"] and m["vehicle"] not in recent_v: recent_v.append(m["vehicle"])
            if len(recent_v) >= 6: break
        if recent_v:
            pick = st.selectbox("Or choose a recent vehicle", recent_v, index=None, placeholder="Recent vehicles", key="d_veh_r")
            if pick and not veh.strip(): veh = pick
    st.caption("One vehicle can carry several customers: choose the customer, add their items, then change the customer and add more. Save once at the end.")
    with c2: party = combo("Customer / place for the next items", parties, "d_party", "Type name")
    ddate = st.date_input("Dispatch date", value=date.today(), max_value=date.today(), key="d_date")
    cart = st.session_state.setdefault("cart", [])
    if (party or "").strip():
        have = {c[0] for c in cart if c[4] == (party or "").strip()}
        pend = [o for o in L.open_orders_for(S, party.strip()) if o["item_id"] not in have]
        if pend:
            nm = items.set_index("id")["name"].to_dict(); un = items.set_index("id")["unit"].to_dict()
            st.markdown("**Pending orders of %s.** Tick what goes on this vehicle." % party.strip())
            chosen = []
            for o in pend:
                if st.checkbox("%s: pending %s %s (ordered %s, sent %s)" % (nm.get(o["item_id"], "?"), L.fmt(o["pending"]), un.get(o["item_id"], ""), L.fmt(L.f(o["qty"])), L.fmt(L.f(o.get("sent")))), value=True, key="pp_" + o["id"]): chosen.append(o)
            if chosen and st.button("➕ Add the ticked pending items to this vehicle (%d)" % len(chosen), key="pp_add"):
                for o in chosen: cart.append((o["item_id"], float(o["pending"]), nm.get(o["item_id"], "?"), un.get(o["item_id"], ""), party.strip()))
                dispatch_draft_save(cart); st.rerun()
    it = pick_item("disp", items, kinds=["finished"])
    with st.form("addline", clear_on_submit=True):
        qty = qty_box("Quantity to load", unit=(it["unit"] if it is not None else ""))
        if st.form_submit_button("➕ Add to this vehicle"):
            if it is None or not qty: st.error("Choose an item and quantity.")
            else: cart.append((it["id"], float(qty), it["name"], it["unit"], (party or "").strip())); dispatch_draft_save(cart); reset_picker("disp"); st.rerun()
    if cart:
        st.markdown("**On this vehicle**")
        groups = []
        for c in cart:
            if c[4] not in groups: groups.append(c[4])
        for gp in groups:
            if len(groups) > 1 or gp: st.markdown("**→ %s**" % (gp or "(no customer named)"))
            for i, c in enumerate(cart):
                if c[4] != gp: continue
                a, b = st.columns([4, 1]); a.write("%s %s — %s" % (L.fmt(c[1]), c[3], c[2]))
                if b.button("✖", key="rm%d" % i): cart.pop(i); dispatch_draft_save(cart); st.rerun()
        neg = st.checkbox("Allow sending more than stock (admin only)", value=False) if IS_ADMIN else False
        tno = trip_no_pick(veh, str(ddate), "d_tno")
        note = st.text_input("Note (optional)", key="d_note")
        tr = None; cost = None
        if CAN_MANAGE:
            tnames = L.transporter_names(S); cur = L.transporter_of(S, veh) if (veh or "").strip() else ""
            tr = st.selectbox("Transporter", tnames, index=tnames.index(cur) if cur in tnames else None, placeholder="Which transporter's vehicle is this?", key="d_tr_" + L.vkey(veh or ""))
            cost = st.number_input("Transport cost for this vehicle (₹, optional, you can fill it later in Transport)", min_value=0.0, value=None, step=100.0, format="%g", key="d_cost_" + L.vkey(veh or ""), placeholder="Decide later")
        ticked = {}
        names = items.set_index("id")["name"].to_dict()
        for gp in groups:
            cands = L.open_orders_for(S, gp, {c[0] for c in cart if c[4] == gp}) if gp else []
            if cands: st.markdown("**Open orders of %s. Ticked ones are counted against this load.**" % gp)
            for o in cands:
                if o["id"] in ticked.get(gp, []) or any(o["id"] in v for v in ticked.values()): continue
                if st.checkbox("%s: %s (ordered %s, already sent %s, pending %s)" % (o["party"], names.get(o["item_id"], "?"), L.fmt(L.f(o["qty"])), L.fmt(L.f(o.get("sent"))), L.fmt(o["pending"])),
                               value=True, key="dk_" + o["id"]): ticked.setdefault(gp, []).append(o["id"])
        if st.button("✅ Save dispatch", type="primary", key="d_save"):
            trip = nonce("disp")
            drops = [(gp, [(c[0], c[1]) for c in cart if c[4] == gp]) for gp in groups]
            if run(L.add_dispatch_trip, ME, drops, veh or "", str(ddate), note, neg, trip, tno, ok="Dispatch saved"):
                if CAN_MANAGE and (veh or "").strip():
                    try:
                        if tr: L.set_transporter(S, veh, tr)
                        if tr or cost is not None: L.set_freight(S, ME, L.trip_key(str(ddate), veh, tno), str(ddate), " ".join(veh.upper().split()), ", ".join(g for g in groups if g), tr, cost)
                    except Exception as e: act("freight_error", str(e)[:120], "error")
                msg = ""; n_ord = 0; n_fin = 0
                for gp, lines in drops:
                    if not ticked.get(gp): continue
                    try:
                        res = L.apply_dispatch_to_orders(S, ticked[gp], lines); n_ord += len(res); n_fin += sum(1 for x in res if x[3])
                    except Exception as e: act("orders_ticked", str(e)[:120], "error")
                if n_ord: act("orders_ticked", "%d orders" % n_ord); msg = "%d order(s) updated, %d finished" % (n_ord, n_fin)
                st.session_state["last_slip"] = trip + ".0"; st.session_state["last_slip_msg"] = msg
                burn("disp"); st.session_state["cart"] = []; st.session_state["_dd_back"] = False; dispatch_draft_save([]); st.rerun()
    ls = st.session_state.get("last_slip")
    if ls and not cart:
        st.success("Dispatch saved. " + st.session_state.get("last_slip_msg", ""))
        slip_button(ls, "Download vehicle slip (PDF)", "slip_last")
    st.divider(); recent(["dispatch"])


def share_table(title, headers, rows, num=(), bold=(), sub="", w0="34%"):
    """A plain table that shows every row on the page at once (no inner scrolling), so one screenshot can be shared."""
    th = "".join('<th class="%s"%s>%s</th>' % ("n" if i in num else "", ' style="width:%s"' % w0 if i == 0 else "", html.escape(h)) for i, h in enumerate(headers))
    body = ""
    for r in rows:
        body += "<tr>" + "".join('<td class="%s%s">%s</td>' % ("n" if i in num else "", " b" if i in bold else "", "<br>".join(('<span class="sm">%s</span>' % html.escape(p)) if k else html.escape(p) for k, p in enumerate(str(c).split("\n")))) for i, c in enumerate(r)) + "</tr>"
    st.markdown('<div class="sh"><div class="sh-t">%s<span>%s</span></div><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>' % (html.escape(title), html.escape(sub), th, body), unsafe_allow_html=True)


def df_share(title, df, sub="", bold=(), w0=None, cap=None):
    """Any table as the same one-page card as To produce: every row on the page, fits phone and desktop."""
    df = df.copy(); cols = list(df.columns); low = {c.lower(): c for c in cols}
    ic = low.get("item") or low.get("name"); bc = low.get("brand"); cc = low.get("category")
    if ic:
        def cell(r):
            first = ("%s %s" % (r[bc], r[ic]) if bc and str(r[bc]).strip() else str(r[ic])).strip()
            return first + (("\n" + str(r[cc])) if cc and str(r[cc]).strip() else "")
        df[ic] = df.apply(cell, axis=1); df = df.drop(columns=[c for c in (bc, cc) if c])
    if "date" in [c.lower() for c in df.columns] and "time" in [c.lower() for c in df.columns]:
        dc = [c for c in df.columns if c.lower() == "date"][0]; tc = [c for c in df.columns if c.lower() == "time"][0]
        df[dc] = df[dc].astype(str).str[5:] + "\n" + df[tc].astype(str); df = df.drop(columns=[tc])
    heads = list(df.columns); num = set()
    for i, c in enumerate(heads):
        if pd.api.types.is_numeric_dtype(df[c]): num.add(i)
    def f(v):
        if v is None or (isinstance(v, float) and v != v): return ""
        if isinstance(v, (int, float)) and not isinstance(v, bool): return L.fmt(v)
        return str(v)
    rows = [tuple(f(v) for v in r) for r in df.itertuples(index=False, name=None)]
    share_table(title, [str(h).replace("_", " ") for h in heads], rows, num=num, bold={heads.index(b) for b in bold if b in heads}, sub=sub or ("%d rows" % len(rows)), w0=w0 or ("38%" if ic or heads[0].lower() in ("customer", "item") else "auto"))
    if cap: st.caption(cap)


def screen_orders():
    items, _, tab = load()
    st.subheader("Orders")
    a, b = st.tabs(["To produce", "Orders"])
    with a:
        tp = L.to_produce(S)
        if tp.empty: st.info("No open orders.")
        else:
            view = st.radio("Show", ["By item (what to make)", "By customer (who wants what)"], horizontal=True, key="tp_view", label_visibility="collapsed")
            if view.startswith("By item"):
                rows = [("%s %s\n%s · %s" % (r.brand, r.item, r.category, r.unit), r.customers, L.fmt(r.ordered), L.fmt(r.in_stock), L.fmt(r.to_make) if r.to_make > 0 else "-") for r in tp.itertuples()]
                share_table("To produce", ["Item", "Customers", "Order", "Stock", "Make"], rows, num={2, 3, 4}, bold={4}, sub=date.today().strftime("%d %b %Y"))
            else:
                po = L.pending_orders(S).sort_values(["Customer", "Category", "Item"])
                rows = [(r.Customer, "%s\n%s" % (r.Item.replace(" | ", " "), r.Category), "%s %s" % (L.fmt(r.Pending), r.Unit), r.Needed_by[5:]) for r in po.itertuples()]
                share_table("Pending orders by customer", ["Customer", "Item", "Pending", "By"], rows, num={2}, sub=date.today().strftime("%d %b %Y"))
            st.caption("The whole list is on one page. Take a screenshot to share it.")
    with b:
        parties = L.all_parties(S)
        own = st.checkbox("Just for our own stock (safety stock, no customer)", key="o_own")
        party = L.OWN_STOCK if own else combo("Customer", parties, "o_party", "Type customer name")
        st.caption("Customised product that is not in the list? Pick 'Other (type it)' in Category, Brand or Item. It is added as a new product when you save the order, and then shows in To produce, Production and Dispatch.")
        it, new, unit = entry_picker("ord", items, tab, kinds=["finished"])
        with st.form("ord", clear_on_submit=True):
            qty = qty_box("Quantity ordered", unit=unit); due = st.date_input("Needed by", value=date.today() + timedelta(days=3)); note = st.text_input("Note (optional)")
            if st.form_submit_button("Save order"):
                if it is None and new is None: st.error("Choose the item first.")
                elif not qty: st.error("Enter the quantity.")
                else:
                    iid = resolve_item(it, new)
                    if iid and run(L.add_order, ME, party or "", iid, qty, str(due), note, ok="Order saved"): reset_picker("ord"); st.rerun()
        st.markdown("**Open orders**")
        names = items.set_index("id")["name"].to_dict(); n = 0
        for o in reversed(S.rows("Orders")):
            if o["status"] != "open": continue
            n += 1
            c1, c2, c3 = st.columns([4, 1, 1]); c1.write("**%s** — %s %s  \n%s · needed by %s%s" % (o["party"], L.fmt(o["qty"]), names.get(o["item_id"], "?"), o["user"], o["due"],
                                                         (" · **sent %s, pending %s**" % (L.fmt(L.f(o.get("sent"))), L.fmt(L.f(o["qty"]) - L.f(o.get("sent"))))) if L.f(o.get("sent")) > 0 else ""))
            if c2.button("Done", key="od" + o["id"]): L.set_order_status(S, o["id"], "done"); act("order_done", o["id"]); st.rerun()
            if c3.button("Drop", key="oc" + o["id"]): L.set_order_status(S, o["id"], "cancelled"); act("order_dropped", o["id"]); st.rerun()
        if not n: st.caption("None open.")


def screen_summary():
    st.subheader("Summary")
    a, b = st.tabs(["Period summary", "Item movement"])
    with a:
        c1, c2 = st.columns(2); td = date.today()
        per = c1.selectbox("Period", ["This week", "Last week", "Last 7 days", "This month", "Last month", "Pick dates"], key="su_per")
        mon = td - timedelta(days=td.weekday())
        if per == "This week": d1, d2 = mon, td
        elif per == "Last week": d1, d2 = mon - timedelta(days=7), mon - timedelta(days=1)
        elif per == "Last 7 days": d1, d2 = td - timedelta(days=6), td
        elif per == "This month": d1, d2 = td.replace(day=1), td
        elif per == "Last month": d2 = td.replace(day=1) - timedelta(days=1); d1 = d2.replace(day=1)
        else:
            x1, x2 = c2.columns(2); d1 = x1.date_input("From", value=td - timedelta(days=6), key="su_d1"); d2 = x2.date_input("To", value=td, key="su_d2")
        S_ = L.period_summary(S, str(d1), str(d2)); sub = "%s to %s" % (d1.strftime("%d %b"), d2.strftime("%d %b %Y"))
        m1, m2, m3, m4 = st.columns(4); m1.metric("Made", L.fmt(sum(S_["made"].values()))); m2.metric("Sent", L.fmt(sum(S_["sent"].values()))); m3.metric("Transport cost", L.money(sum(v["cost"] for v in S_["transport"].values()))); m4.metric("Pending order lines", S_["pending"])
        cats = sorted(set(S_["made"]) | set(S_["sent"]))
        rows = [(c, L.fmt(S_["made"].get(c, 0)), L.fmt(S_["sent"].get(c, 0))) for c in cats] + [("TOTAL", L.fmt(sum(S_["made"].values())), L.fmt(sum(S_["sent"].values())))]
        share_table("Made and sent by category", ["Category", "Made", "Sent"], rows, num={1, 2}, sub=sub, w0="50%"); st.write("")
        if S_["cust"]:
            share_table("Top customers (quantity sent)", ["Customer", "Qty sent"], [(k, L.fmt(v)) for k, v in list(S_["cust"].items())[:15]], num={1}, sub=sub, w0="70%"); st.write("")
        if S_["transport"]:
            share_table("Transport", ["Transporter", "Trips", "Cost", "Not decided"], [(k, v["trips"], L.money(v["cost"]), v["undecided"] or "") for k, v in S_["transport"].items()], num={1, 2, 3}, sub=sub, w0="40%")
    with b:
        days = st.selectbox("Look at the last", [30, 60, 90], index=1, format_func=lambda n: "%d days" % n, key="im_days")
        im = L.item_movement(S, days)
        if im.empty: st.info("Nothing to show yet.")
        else:
            fast = im[im["Tag"] == "Fast"].sort_values("Cover_days").head(15); dead = im[im["Tag"] == "Dead stock"].sort_values("Stock", ascending=False).head(20); top = im.sort_values("Sent", ascending=False).head(10)
            top = top[top["Sent"] > 0]
            if not top.empty: share_table("Selling most (last %d days)" % days, ["Item", "Sent", "Stock", "Made"], [("%s\n%s" % (r.Item, r.Category), L.fmt(r.Sent), L.fmt(r.Stock), L.fmt(r.Made)) for r in top.itertuples()], num={1, 2, 3}, w0="55%"); st.write("")
            if not fast.empty: share_table("Running out soon (less than 14 days of stock)", ["Item", "Stock", "Days left"], [("%s\n%s" % (r.Item, r.Category), L.fmt(r.Stock), "%d" % round(r.Cover_days)) for r in fast.itertuples()], num={1, 2}, bold={2}, w0="60%"); st.write("")
            if not dead.empty: share_table("Dead stock (in stock, nothing sent in %d days)" % days, ["Item", "Stock", "Last sent"], [("%s\n%s" % (r.Item, r.Category), "%s %s" % (L.fmt(r.Stock), r.Unit), r.Last_sent or "never") for r in dead.itertuples()], num={1}, w0="55%")
            st.download_button("Download all (CSV)", im.to_csv(index=False).encode(), "item-movement.csv", "text/csv", key="im_dl")


def screen_transport():
    st.subheader("Transport")
    names = L.transporter_names(S)
    t1, t2, tp, ts, t3 = st.tabs(["Transporter's list", "Enter costs", "Payments", "Monthly statement", "Vehicles"])
    with t1:
        c1, c2 = st.columns(2)
        who = c1.selectbox("Transporter", ["All"] + names, key="tl_who")
        per = c2.selectbox("Period", ["Last 7 days", "Last 14 days", "This month", "Last month", "Pick dates"], key="tl_per")
        td = date.today()
        if per == "Last 7 days": d1, d2 = td - timedelta(days=6), td
        elif per == "Last 14 days": d1, d2 = td - timedelta(days=13), td
        elif per == "This month": d1, d2 = td.replace(day=1), td
        elif per == "Last month": d2 = td.replace(day=1) - timedelta(days=1); d1 = d2.replace(day=1)
        else:
            a, b = st.columns(2); d1 = a.date_input("From", value=td - timedelta(days=6), key="tl_d1"); d2 = b.date_input("To", value=td, key="tl_d2")
        dr = [x for x in L.freight_drops(S, str(d1), str(d2)) if who == "All" or x["transporter"] == who]
        if not dr: st.info("Nothing was dispatched in these dates.")
        else:
            dr = sorted(dr, key=lambda r: (r["date"], r["vehicle"], r["trip"]))
            tot = sum(x["amount"] or 0 for x in dr); undec = sum(1 for x in dr if x["amount"] is None)
            m1, m2, m3 = st.columns(3); m1.metric("Vehicle trips", len(dr)); m2.metric("Total cost", L.money(tot)); m3.metric("Cost not decided", undec)
            rows = [(x["date"][8:] + "/" + x["date"][5:7], x["vehicle"] + (" (trip %s)" % x["trip"] if x["trip"] != "1" else ""), x["party"] + (" (%s)" % x["transporter"] if who == "All" and x["transporter"] else ""), ("-" if x["amount"] is None else L.money(x["amount"]) + (" ✓" if x["paid"] else ""))) for x in dr]
            rows.append(("", "", "TOTAL", L.money(tot)))
            share_table("Transport list, %s" % (who if who != "All" else "all transporters"), ["Date", "Vehicle", "Went to", "Amount"], rows, num={3}, bold=set(), sub="%s to %s" % (d1.strftime("%d %b"), d2.strftime("%d %b %Y")), w0="13%")
            st.caption("One page, so you can take a screenshot and share it. A dash means the cost is not decided yet. A tick means it is paid.")
            csv = pd.DataFrame([dict(Date=x["date"], Vehicle=x["vehicle"], Trip=x["trip"], Place=x["party"], Transporter=x["transporter"], Amount="" if x["amount"] is None else x["amount"]) for x in dr])
            st.download_button("Download (CSV)", csv.to_csv(index=False).encode(), "transport.csv", "text/csv", key="tl_dl")
    with t2:
        c1, c2, c3 = st.columns([2, 2, 2])
        tfil = c1.selectbox("Transporter", ["All"] + [n for n in names if n != L.PERSONAL] + ["Not allotted"], key="ec_tr")
        only = c2.checkbox("Only where cost is not decided", value=True, key="ec_only")
        days = c3.selectbox("Look back", [7, 14, 30, 60], index=1, format_func=lambda n: "%d days" % n, key="ec_days")
        dr = L.freight_drops(S, str(date.today() - timedelta(days=days)), str(date.today()))
        if tfil == "Not allotted": dr = [x for x in dr if not x["transporter"]]
        elif tfil != "All": dr = [x for x in dr if x["transporter"] == tfil]
        tlist = [x for x in dr if (not only) or x["amount"] is None]
        if not tlist: st.success("Nothing to fill here.")
        shown = 0
        for grp in [n for n in names if n != L.PERSONAL] + [""]:
            gl = [x for x in tlist if x["transporter"] == grp]
            if not gl: continue
            allg = [x for x in dr if x["transporter"] == grp]
            st.markdown("#### %s" % (grp or "Transporter not allotted"))
            st.caption("%d vehicle trip(s) to fill · entered so far %s" % (len(gl), L.money(sum(x["amount"] or 0 for x in allg))))
            for x in gl:
                if shown >= 40: break
                shown += 1
                with st.container(border=True):
                    top1, top2 = st.columns([3, 2])
                    top1.write("**%s** · %s%s" % (x["vehicle"], x["date"], " · trip %s" % x["trip"] if x["trip"] != "1" else ""))
                    top1.caption("Went to: " + x["party"])
                    tsel = top2.selectbox("Transporter", names, index=names.index(x["transporter"]) if x["transporter"] in names else None, placeholder="Transporter", key="et_" + x["ref"], label_visibility="collapsed")
                    amt = top2.number_input("Cost for this vehicle (₹)", min_value=0.0, value=x["amount"], step=100.0, format="%g", key="ea_" + x["ref"], placeholder="Cost (₹), not decided", label_visibility="collapsed")
                    if st.button("Save", key="es_" + x["ref"], type="primary"):
                        if run(L.set_freight, ME, x["ref"], x["date"], x["vehicle"], x["party"], tsel, amt, x["note"], ok="Saved"):
                            if tsel: L.set_transporter(S, x["vehicle"], tsel)
                            st.rerun()
        if len(tlist) > 40: st.caption("Showing the latest 40 trips. Fill these, then the rest appear.")
    with tp:
        who = st.selectbox("Transporter", [n for n in names if n != L.PERSONAL], key="pay_who")
        allf = [x for x in L.freight_drops(S, "2000-01-01", str(date.today())) if x["transporter"] == who and x["amount"] is not None]
        due = [x for x in allf if not x["paid"]]; paid = [x for x in allf if x["paid"]]
        m1, m2, m3 = st.columns(3); m1.metric("You owe", L.money(sum(x["amount"] for x in due))); m2.metric("Trips unpaid", len(due)); m3.metric("Paid so far", L.money(sum(x["amount"] for x in paid)))
        und = [x for x in L.freight_drops(S, "2000-01-01", str(date.today())) if x["transporter"] == who and x["amount"] is None]
        if und: st.warning("%d trip(s) of %s have no cost yet. Fill them in Enter costs." % (len(und), who))
        if not due: st.success("Nothing unpaid for %s." % who)
        else:
            st.markdown("**Unpaid trips.** Tick what you have paid, then press the button.")
            pick = []
            for x in sorted(due, key=lambda r: r["date"]):
                if st.checkbox("%s · %s · %s · %s" % (x["date"], x["vehicle"], x["party"], L.money(x["amount"])), key="pk_" + x["ref"]): pick.append(x)
            pd_ = st.date_input("Paid on", value=date.today(), max_value=date.today(), key="pay_on")
            if st.button("Mark %d trip(s) as paid (%s)" % (len(pick), L.money(sum(x["amount"] for x in pick))), type="primary", disabled=not pick, key="pay_go"):
                if run(L.set_paid, ME, [x["ref"] for x in pick], str(pd_), True, ok="Marked as paid"): st.rerun()
        if paid:
            with st.expander("Paid trips (%d)" % len(paid)):
                for x in sorted(paid, key=lambda r: r["date"], reverse=True)[:40]:
                    a, b = st.columns([5, 1]); a.write("%s · %s · %s · %s · paid %s" % (x["date"], x["vehicle"], x["party"], L.money(x["amount"]), x["paid_on"]))
                    if b.button("Undo", key="pu_" + x["ref"]): L.set_paid(S, ME, [x["ref"]], "", False); st.rerun()
    with ts:
        c1, c2 = st.columns(2)
        td = date.today(); months = [(td.replace(day=1) - timedelta(days=31 * i)).strftime("%Y-%m") for i in range(0, 12)]
        months = sorted(set(months), reverse=True)
        mo = c1.selectbox("Month", months, key="st_mo"); whoS = c2.selectbox("Transporter", ["All"] + [n for n in names if n != L.PERSONAL], key="st_who")
        y, m_ = int(mo[:4]), int(mo[5:]); d1 = date(y, m_, 1); d2 = (date(y + (m_ == 12), m_ % 12 + 1, 1) - timedelta(days=1))
        dr = [x for x in L.freight_drops(S, str(d1), str(d2)) if whoS == "All" or x["transporter"] == whoS]
        if not dr: st.info("No dispatch in this month.")
        else:
            for grp in sorted({x["transporter"] or "(not allotted)" for x in dr}):
                gl = sorted([x for x in dr if (x["transporter"] or "(not allotted)") == grp], key=lambda r: (r["date"], r["vehicle"]))
                tot = sum(x["amount"] or 0 for x in gl); pdv = sum(x["amount"] or 0 for x in gl if x["paid"]); und = sum(1 for x in gl if x["amount"] is None)
                rows = [(x["date"][8:] + "/" + x["date"][5:7], x["vehicle"], x["party"], "-" if x["amount"] is None else L.money(x["amount"]), "paid" if x["paid"] else ("" if x["amount"] is None else "due")) for x in gl]
                rows.append(("", "", "TOTAL (%d trips)" % len(gl), L.money(tot), "paid %s · due %s" % (L.money(pdv), L.money(tot - pdv))))
                share_table("%s · %s" % (grp, d1.strftime("%B %Y")), ["Date", "Vehicle", "Went to", "Amount", "Status"], rows, num={3}, sub=("%d cost(s) not decided" % und) if und else "", w0="12%")
                st.write("")
    with t3:
        st.caption("Which transporter owns which vehicle. Once set, the Dispatch screen picks the transporter by itself when you type that vehicle number.")
        known = []
        for m in reversed(S.rows("Moves")):
            if m["type"] == "dispatch" and m["vehicle"] and L.vkey(m["vehicle"]) not in [L.vkey(k) for k in known]: known.append(" ".join(m["vehicle"].split()))
            if len(known) >= 40: break
        for v in known:
            a, b = st.columns([2, 2]); a.write("**%s**" % v); cur = L.transporter_of(S, v)
            sel = b.selectbox("Transporter", names, index=names.index(cur) if cur in names else None, placeholder="Not set", key="vt_" + L.vkey(v), label_visibility="collapsed")
            if sel and sel != cur: L.set_transporter(S, v, sel); st.rerun()
        st.markdown("**Last payment settled up to**")
        st.caption("Trips on or before this date are left out of every Transport screen. Change it each time you settle with a transporter.")
        for n_ in [n for n in names if n != L.PERSONAL]:
            cur = L.settled_upto(S, n_)
            a, b = st.columns([2, 2]); a.write("**%s**" % n_)
            nd = b.date_input("Settled up to", value=date.fromisoformat(cur) if cur else None, max_value=date.today(), key="sd_" + n_, label_visibility="collapsed", format="DD/MM/YYYY")
            if nd and str(nd) != cur: L.set_settled(S, n_, str(nd)); st.rerun()
        st.markdown("**Add a vehicle or a new transporter**")
        a, b = st.columns(2); nv = a.text_input("Vehicle number", key="vt_new_v"); nt = b.text_input("Transporter name", key="vt_new_t", placeholder="Type to pick or add")
        if st.button("Save", key="vt_new_s"):
            if nv.strip() and nt.strip(): L.set_transporter(S, nv, nt); st.rerun()
            else: st.error("Type both the vehicle number and the transporter.")


def screen_customers():
    st.subheader("Customers")
    parties = L.all_parties(S)
    c = combo("Customer", parties, "cs_party", "Type or choose a customer")
    if not (c or "").strip():
        po = L.pending_orders(S)
        st.caption("Choose a customer to see what is pending and everything sent to them." if not po.empty else "Choose a customer to see everything sent to them.")
        if not po.empty:
            g = po.groupby("Customer", as_index=False).agg(Lines=("Item", "count"), Pending_qty=("Pending", "sum"), Earliest_due=("Needed_by", "min"))
            st.markdown("**Who has pending orders**"); df_share("Who has pending orders", g.rename(columns={"Pending_qty": "Pending qty", "Earliest_due": "Earliest due"}))
        return
    c = c.strip()
    po = L.pending_orders(S, c)
    h = L.customer_history(S.rows("Items"), S.rows("Moves"), "", "2000-01-01", "2999-12-31")
    h = h[h["Customer"].map(lambda x: L.party_match(x, c))] if not h.empty else h
    m1, m2, m3 = st.columns(3)
    m1.metric("Pending lines", len(po)); m2.metric("Dispatches", int(h[["Date", "Vehicle"]].drop_duplicates().shape[0]) if not h.empty else 0); m3.metric("Last sent", h["Date"].max() if not h.empty else "-")
    st.markdown("**Pending orders**")
    if po.empty: st.caption("Nothing pending.")
    else: df_share("Pending orders, " + c, po[["Category", "Item", "Pending", "Unit", "Needed_by", "Days_left"]].rename(columns={"Needed_by": "Needed by", "Days_left": "Days left"}))
    st.markdown("**Total sent, by item**")
    if h.empty: st.caption("Nothing sent yet.")
    else:
        tot = h.groupby(["Item", "Unit"], as_index=False)["Qty"].sum().sort_values("Qty", ascending=False)
        df_share("Total sent, " + c, tot)
        with st.expander("Every dispatch (%d lines)" % len(h)):
            df_share("Every dispatch, " + c, h.drop(columns=["Customer"]))
        st.download_button("Download (CSV)", h.to_csv(index=False).encode(), "customer-%s.csv" % "".join(ch for ch in c if ch.isalnum())[:20], "text/csv", key="cs_dl")


def screen_returns():
    items, _, _ = load()
    st.subheader("Returns")
    names = items.set_index("id")["name"].to_dict(); units = items.set_index("id")["unit"].to_dict()
    st.markdown("**Record a return** — it waits on hold until it is decided.")
    parties = L.all_parties(S)
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
                n = L.add_counts(S, ME, got); act("add_counts", "%d items" % n); st.toast("Updated %d items" % n, icon="✅"); st.rerun()
            except L.Problem as e: st.error(str(e))


KIND = {"opening": "Opening / stock added", "production": "Production", "dispatch": "Dispatch", "inward": "Inward (purchase)", "return": "Return (on hold)",
        "return_decide": "Return decided", "waste": "Waste / scrap", "raw_in": "Raw in", "raw_use": "Raw used", "count": "Count correction"}


def item_history(items, moves):
    """Every movement of one item, oldest to newest with a running balance, so a count can be reconciled line by line."""
    st.caption("Pick one item to see everything that happened to it: opening, production, dispatch, returns, counts, and the balance after each line.")
    it = pick_item("hist", items)
    if it is None: return
    m = moves[moves["item_id"] == it["id"]].copy().sort_values(["date", "ts"])
    if m.empty: st.info("Nothing has been entered for this item yet."); return
    m["good"] = m.apply(lambda r: 0.0 if (r["void"] or r["bucket"] != "good") else r["qty"], axis=1); m["Balance"] = m["good"].cumsum()
    live = m[~m["void"] & (m["bucket"] == "good")]
    c1, c2, c3 = st.columns(3)
    c1.metric("In stock now", L.fmt(live["qty"].sum()) + " " + it["unit"])
    c2.metric("Total in", L.fmt(live[live["qty"] > 0]["qty"].sum())); c3.metric("Total out", L.fmt(-live[live["qty"] < 0]["qty"].sum()))
    by = live.groupby("type")["qty"].sum().rename(index=lambda t: KIND.get(t, t)).reset_index().rename(columns={"type": "Type", "qty": "Total"})
    df_share("Totals by type", by)
    m["Date"] = m["date"]; m["Time"] = m["ts"].str[11:16]; m["What"] = m["type"].map(lambda t: KIND.get(t, t))
    m["In (+)"] = m["qty"].where((m["qty"] > 0) & (m["bucket"] == "good")); m["Out (-)"] = (-m["qty"]).where((m["qty"] < 0) & (m["bucket"] == "good"))
    m["Where / who"] = m.apply(lambda r: " · ".join(x for x in [r["vehicle"], r["party"], ("Shift " + r["shift"]) if r["shift"] else "", r["machine"]] if x) + ("" if r["bucket"] == "good" else " [%s]" % r["bucket"]), axis=1)
    m["Status"] = m["void"].map({True: "CANCELLED", False: ""}); m["By"] = m["user"]; m["Note"] = m["note"]
    out = m[["Date", "Time", "What", "In (+)", "Out (-)", "Balance", "Where / who", "By", "Note", "Status"]]
    newest = st.checkbox("Newest first", value=True, key="hist_new")
    out = out.iloc[::-1] if newest else out
    df_share("History", out.assign(Details=out[["Where / who", "By", "Note", "Status"]].apply(lambda r: "\n".join(x for x in r if str(x).strip()), axis=1)).drop(columns=["Where / who", "By", "Note", "Status"]))
    st.download_button("Download this item's history (CSV)", out.to_csv(index=False), "history-%s.csv" % it["id"], "text/csv")


def units_line(df, col="qty"):
    """'120 rolls · 40 sets' - totals kept apart per unit because rolls and pieces must never be added together."""
    if df.empty: return "0"
    g = df.groupby("unit")[col].sum()
    return " · ".join("%s %s" % (L.fmt(v), u) for u, v in g.items() if v)


def report_period():
    pick = st.radio("Period", ["Today", "Yesterday", "Last 7 days", "This month", "Pick dates"], horizontal=True, index=2, key="rp_per", label_visibility="collapsed")
    t = date.today()
    if pick == "Today": d1 = d2 = t
    elif pick == "Yesterday": d1 = d2 = t - timedelta(days=1)
    elif pick == "Last 7 days": d1, d2 = t - timedelta(days=6), t
    elif pick == "This month": d1, d2 = t.replace(day=1), t
    else:
        c1, c2 = st.columns(2); d1 = c1.date_input("From", value=t - timedelta(days=6), key="rp_d1"); d2 = c2.date_input("To", value=t, key="rp_d2")
    st.caption("Showing %s to %s" % (d1.strftime("%d %b"), d2.strftime("%d %b %Y")))
    return d1, d2


def screen_reports():
    items, moves, tab = load()
    st.subheader("Reports")
    st.caption("Period for Made, Sent and Received:"); d1, d2 = report_period()
    t_stock, t_made, t_sent, t_in, t_low, t_hist, t_week, t_cust, t_veh = st.tabs(["Stock now", "Made", "Sent", "Received", "Low stock", "Item history", "Weekly list", "Customers", "Vehicles"])
    base = moves[~moves["void"]].merge(items[["id", "name", "brand", "category", "unit", "price"]], left_on="item_id", right_on="id", how="left")
    QTY = {"qty": st.column_config.NumberColumn("Qty", format="%g")}

    with t_stock:
        cats = ["All categories"] + sorted(tab["category"].dropna().unique().tolist())
        c1, c2 = st.columns([2, 1]); cat = c1.selectbox("Category", cats, key="rs_cat"); hide0 = c2.checkbox("Hide zero stock", value=True, key="rs_h0")
        v = tab if cat == cats[0] else tab[tab["category"] == cat]
        if hide0: v = v[(v["good"] != 0) | (v["hold"] != 0)]
        c1, c2, c3 = st.columns(3); c1.metric("Items", len(v)); c2.metric("Total quantity", L.fmt(v["good"].sum()))
        if IS_ADMIN: c3.metric("Stock value", L.money(v["value"].sum()))
        else: c3.metric("On hold", L.fmt(v["hold"].sum()))
        cols = ["category", "brand", "name", "unit", "good", "hold"] + (["price", "value"] if IS_ADMIN else [])
        cc = {"category": "Category", "brand": "Brand", "name": "Item", "unit": "Unit", "good": st.column_config.NumberColumn("In stock", format="%g"), "hold": st.column_config.NumberColumn("On hold", format="%g")}
        if IS_ADMIN: cc.update({"price": st.column_config.NumberColumn("Price", format="₹%g"), "value": "Value"}); v = v.assign(value=v["value"].map(L.money))
        df_share("Stock, " + cat if cat != cats[0] else "Stock", v[cols].rename(columns={"category": "Category", "brand": "Brand", "name": "Item", "unit": "Unit", "good": "In stock", "hold": "On hold", "price": "Price", "value": "Value"}))
        st.download_button("Download stock sheet (CSV)", v[cols].to_csv(index=False), "stock.csv", "text/csv")

    with t_made:
        live = base[(base["date"] >= str(d1)) & (base["date"] <= str(d2))]
        p = live[live["type"] == "production"].copy()
        added = live[(live["type"] == "opening") & (live["date"] > "2026-10-29")]        # typed in through Add Stock after the opening count
        if p.empty and added.empty: st.info("Nothing was made in these dates.")
        if not p.empty:
            p["time"] = p["ts"].str[11:16]
            c1, c2, c3 = st.columns(3); c1.metric("Entries", len(p)); c2.metric("Different items", p["item_id"].nunique()); c3.metric("Made", units_line(p))
            by = st.selectbox("Show totals by", ["name", "date", "machine", "shift", "user"], key="rp_by", format_func=lambda x: {"name": "Item", "date": "Day", "machine": "Machine", "shift": "Shift", "user": "Person"}[x])
            g = p.assign(**{by: p[by].replace("", "(not noted)")}).groupby([by, "unit"], as_index=False)["qty"].sum().rename(columns={"qty": "Made"}).sort_values("Made", ascending=False)
            df_share("Made, by " + {"name": "item", "date": "day", "machine": "machine", "shift": "shift", "user": "person"}[by], g.rename(columns={by: {"name": "Item", "date": "Day", "machine": "Machine", "shift": "Shift", "user": "Person"}[by], "unit": "Unit"}), sub="%s to %s" % (d1, d2))
            full = p[["date", "time", "shift", "machine", "brand", "name", "unit", "qty", "user", "note"]].rename(columns={"qty": "made"}).sort_values(["date", "time"], ascending=False)
            with st.expander("Every production entry (%d)" % len(full)):
                df_share("Every production entry", full)
            st.download_button("Download CSV", full.to_csv(index=False), "production.csv", "text/csv")
        if not added.empty:
            ad = added.assign(time=added["ts"].str[11:16])[["date", "time", "category", "brand", "name", "unit", "qty", "user", "note"]].rename(columns={"qty": "added"}).sort_values(["date", "time"], ascending=False)
            with st.expander("Stock added directly with Add Stock, not as production (%d)" % len(ad)):
                df_share("Stock added directly", ad)

    with t_sent:
        live = base[(base["date"] >= str(d1)) & (base["date"] <= str(d2))]
        p = live[live["type"] == "dispatch"].copy(); p["qty"] = -p["qty"]
        if p.empty: st.info("Nothing was sent in these dates.")
        else:
            c1, c2, c3 = st.columns(3); c1.metric("Loads", p["ref"].nunique() if "ref" in p else len(p)); c2.metric("Vehicles", p[p["vehicle"] != ""]["vehicle"].nunique()); c3.metric("Sent", units_line(p))
            by = st.selectbox("Show totals by", ["party", "vehicle", "name", "date"], key="rd_by", format_func=lambda x: {"party": "Customer", "vehicle": "Vehicle", "name": "Item", "date": "Day"}[x])
            g = p.assign(**{by: p[by].replace("", "(not noted)")}).groupby([by, "unit"], as_index=False)["qty"].sum().rename(columns={"qty": "Sent"}).sort_values("Sent", ascending=False)
            df_share("Sent, by " + {"party": "customer", "vehicle": "vehicle", "name": "item", "date": "day"}[by], g.rename(columns={by: {"party": "Customer", "vehicle": "Vehicle", "name": "Item", "date": "Day"}[by], "unit": "Unit"}), sub="%s to %s" % (d1, d2))
            full = p.assign(time=p["ts"].str[11:16])[["date", "time", "vehicle", "party", "brand", "name", "unit", "qty", "user"]].rename(columns={"qty": "sent"}).sort_values(["date", "time"], ascending=False)
            with st.expander("Every dispatch entry (%d)" % len(full)):
                df_share("Every dispatch entry", full)
            st.download_button("Download full list (CSV)", full.to_csv(index=False), "dispatch.csv", "text/csv")

    with t_in:
        p = base[(base["type"] == "inward") & (base["date"] >= str(d1)) & (base["date"] <= str(d2))]
        if p.empty: st.info("Nothing was received in these dates.")
        else:
            st.metric("Received", units_line(p))
            full = p[["date", "category", "brand", "name", "unit", "qty", "user"]].rename(columns={"qty": "received"})
            df_share("Received", full); st.download_button("Download inward list (CSV)", full.to_csv(index=False), "inward.csv", "text/csv")

    with t_low:
        low = tab[(tab["min_level"] > 0) & (tab["good"] < tab["min_level"])][["category", "brand", "name", "unit", "good", "min_level"]]
        if low.empty: st.success("Nothing is below its minimum. (Set minimums in Admin → Items.)")
        else:
            st.warning("%d items are below their minimum." % len(low))
            df_share("Below minimum", low.rename(columns={"good": "In stock", "min_level": "Minimum"}), bold=("In stock",))

    with t_hist: item_history(items, moves)

    with t_week:
        st.caption("One list for the factory to confirm: what each item had at the start, what was made, received and sent, and the stock at the end. Print it or download it; the last two columns are empty for the factory to fill.")
        tt = date.today(); mon = tt - timedelta(days=tt.weekday())
        c1, c2 = st.columns(2); w1 = c1.date_input("From", value=mon - timedelta(days=7), key="wk_1"); w2 = c2.date_input("To", value=mon - timedelta(days=1), key="wk_2")
        st.caption("Default is last week, Monday to Sunday.")
        wl = L.weekly_list(S.rows("Items"), S.rows("Moves"), str(w1), str(w2))
        if wl.empty: st.info("Nothing moved in these dates.")
        else:
            c1, c2, c3 = st.columns(3); c1.metric("Items", len(wl)); c2.metric("Made", L.fmt(wl["Made"].sum())); c3.metric("Sent", L.fmt(wl["Sent"].sum()))
            df_share("Weekly list", wl, sub="%s to %s" % (w1, w2))
            ex = wl.copy(); ex["Factory count"] = ""; ex["Difference"] = ""
            try:
                buf = io.BytesIO(); ex.to_excel(buf, index=False, sheet_name="Weekly list"); st.download_button("Download (Excel)", buf.getvalue(), "weekly-list-%s-to-%s.xlsx" % (w1, w2), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="wk_x")
            except Exception:
                st.download_button("Download (CSV)", ex.to_csv(index=False).encode(), "weekly-list-%s-to-%s.csv" % (w1, w2), "text/csv", key="wk_c")

    with t_cust:
        q = st.text_input("Customer name (part of it is enough; empty shows everyone)", key="cu_q")
        h = L.customer_history(S.rows("Items"), S.rows("Moves"), q, str(d1), str(d2))
        if h.empty: st.info("No dispatch to this customer in the period above.")
        else:
            names_ = sorted(h["Customer"].unique()); st.caption("%d customer(s), %d lines, in the period chosen at the top." % (len(names_), len(h)))
            sel = st.multiselect("Show these customers", names_, default=names_[:1] if q.strip() and len(names_) > 1 else names_, key="cu_sel") if len(names_) > 1 else names_
            hh = h[h["Customer"].isin(sel)] if sel else h
            st.markdown("**Total sent, by item**")
            tot = hh.groupby(["Customer", "Item", "Unit"], as_index=False)["Qty"].sum()
            df_share("Total sent, by item", tot)
            st.markdown("**Every dispatch**")
            df_share("Every dispatch", hh)
            st.download_button("Download (CSV)", hh.to_csv(index=False).encode(), "customer-history.csv", "text/csv", key="cu_dl")

    with t_veh:
        st.caption("For the transporter: which vehicle went on which day and how many customers it carried. No items here.")
        vq = st.text_input("Vehicle number (part of it is enough, e.g. 2801; empty shows all)", key="vh_q")
        vd = L.vehicle_days(S.rows("Moves"), vq, str(d1), str(d2))
        if vd.empty: st.info("No dispatch by this vehicle in the period chosen at the top.")
        else:
            c1, c2, c3 = st.columns(3); c1.metric("Days it went", len(vd)); c2.metric("Trips", int(vd["Trips"].sum())); c3.metric("Customers carried", int(vd["Customers"].sum()))
            df_share("Vehicle days", vd)
            st.caption("A vehicle counts as 1 trip per day unless a second trip was saved. If it really went twice on a day, open Fix entries and set 'Trip of the day' to 2 on that dispatch.")
            st.download_button("Download (CSV)", vd.to_csv(index=False).encode(), "vehicle-days.csv", "text/csv", key="vh_dl")


def screen_admin():
    st.subheader("Admin")
    t1, t2, t3, t4, t5, t6 = st.tabs(["Prices & items", "People", "Lists", "History", "Backup", "Opening stock file"])
    with t1:
        items = L.items_df(S.rows("Items"), False)
        st.caption("Edit price or minimum level and press Save. Untick 'Active' to hide an item.")
        cats = ["All"] + L.categories(S.rows("Items"), S.rows("Lists")); cat = st.selectbox("Category", cats, key="adm_c")
        v = items if cat == "All" else items[items["category"] == cat]
        ed = st.data_editor(v[["_r", "brand", "name", "unit", "price", "min_level", "active"]].rename(columns={"name": "Item"}), hide_index=True, **WIDE,
                            disabled=["_r", "brand", "Item", "unit"], column_order=["brand", "Item", "unit", "price", "min_level", "active"], key="adm_ed_" + cat,
                            column_config={"price": st.column_config.NumberColumn("Price ₹", min_value=0, format="%g"), "min_level": st.column_config.NumberColumn("Minimum", min_value=0, format="%g")})
        if st.button("Save changes", type="primary"):
            raw = {r["_r"]: r for r in S.rows("Items")}; n = 0
            for _, r in ed.iterrows():
                o = raw[int(r["_r"])]; new = dict(o); new["price"] = L.f(r["price"]); new["min_level"] = L.f(r["min_level"]); new["active"] = 1 if r["active"] else 0
                if (L.f(o["price"]), L.f(o["min_level"]), str(o["active"]) in ("1", "True", "true")) != (new["price"], new["min_level"], bool(r["active"])): S.update("Items", int(r["_r"]), new); n += 1
            st.toast("Saved %d changes" % n, icon="✅")
        st.divider(); st.markdown("**Add a new item**")
        allc = L.categories(S.rows("Items"), S.rows("Lists"))
        with st.form("newitem", clear_on_submit=True):
            c1, c2 = st.columns(2); nc = c1.selectbox("Category", allc); br = c2.text_input("Brand", value="Evergreen")
            nm = st.text_input("Item name (e.g. 16 Round)"); sp = st.text_input("Size / details (e.g. 400mtr 40cm)")
            c3, c4, c5 = st.columns(3); un = c3.selectbox("Unit", ["rolls", "pieces", "sets", "bags", "boxes", "kg", "nos"]); pr = c4.number_input("Price ₹", min_value=0.0, value=0.0); mn = c5.number_input("Minimum", min_value=0.0, value=0.0)
            if st.form_submit_button("Add item"): run(L.add_item, nc, br, nm, sp, un, pr, mn, ok="Item added")
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
                else: L.update_user(S, who, active=0 if str(u["active"]) in ("1", "True", "true") else 1); act("user_switch", who); st.toast("Done", icon="✅"); st.rerun()
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
        st.write("**Google Sheet register.** The app keeps a tab called *%s* in your Google Sheet up to date by itself: Opening, In, Out and Closing for every day, in your Excel layout. A new one starts by itself every month. You never type in the Sheet. There are also tabs *%s* (every dispatch of the month) and *%s* (which vehicle went each day, how many trips and customers)." % ("Register " + today()[:7], "Dispatch " + today()[:7], "Vehicles " + today()[:7]))
        if S.sync_error: st.warning("Last sheet update failed: " + S.sync_error)
        st.write("**Activity log:** every login, screen opened, save, edit, undo and error is written to a tab called *Log* in the Google Sheet (who, when, what, how long it took). Use it to see what staff do and where things go wrong.")
        if S.log_error: st.warning("Last log write failed: " + S.log_error)
        st.write("**Daily backup:** a dated copy of your data is saved once a day as a tab called *Backup YYYY-MM-DD* in the Google Sheet. The last 7 days are kept and older ones are removed. " + ("Today's backup is done." if S.bk_day == today() else "Today's backup is not done yet."))
        if S.bk_error: st.warning("Last backup problem: " + S.bk_error)
        if st.button("Back up now"):
            try: L.backup_now(S, today()); S.bk_day = today(); act("backup_now"); st.toast("Backup saved", icon="✅")
            except Exception as e: st.error("Could not back up: %s" % str(e)[:200])
        if st.button("Update the Google Sheet now"):
            try: L.sync_register(S); S.synced = S.writes; st.toast("Sheet updated", icon="✅")
            except Exception as e: st.error("Could not update the sheet: %s" % str(e)[:200])
        st.divider(); st.markdown("**Start again with zero stock**")
        st.caption("Sets every item's stock to 0. Nothing is deleted; the history stays. Use it once before you begin.")
        sure = st.text_input("Type RESET to confirm", key="reset_ok")
        if st.button("Set all stock to zero") and sure.strip() == "RESET":
            n = L.reset_all_stock(S, ME); act("reset_all_stock", "%d items" % n); st.toast("Stock set to zero for %d items" % n, icon="✅")
        st.divider()
        st.write("Your data lives in %s." % ("your Google Sheet (you can open it any time)" if LIVE else "the folder `trial_data` on this computer"))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for t in ("Items", "Moves", "Orders", "Lists"):
                z.writestr(t + ".csv", pd.DataFrame(S.rows(t)).drop(columns=["_r"], errors="ignore").to_csv(index=False))
        st.download_button("Download a full backup (zip)", buf.getvalue(), "evergreen-backup-%s.zip" % today(), "application/zip")
    with t6:
        st.write("Load your counted opening stock from a file. Items that are missing are created. Loading the same file twice does not double the stock.")
        up = st.file_uploader("Opening stock file (CSV)", type=["csv"], key="open_up")
        if up is not None:
            try: df = pd.read_csv(up, dtype=str).fillna("")
            except Exception: df = None; st.error("Could not read that file.")
            if df is not None:
                need = {"id", "category", "brand", "item", "spec", "unit", "qty"}
                if not need.issubset(df.columns): st.error("The file must have these columns: " + ", ".join(sorted(need)))
                else:
                    st.dataframe(df[["category", "brand", "item", "spec", "unit", "qty"]], hide_index=True, **WIDE)
                    st.caption("%d lines. Check them, then press the button." % len(df))
                    if st.button("Load this opening stock", type="primary"):
                        try:
                            made, added = L.import_opening(S, ME, df.to_dict("records"), today()); act("import_opening", "%d lines, %d new items" % (added, made))
                            st.success("Done. %d lines entered, %d new items created." % (added, made))
                        except L.Problem as e: st.error(str(e))
                        except Exception as e: st.error("Could not load. (%s)" % str(e)[:160])


def screen_fix():
    """Correct wrong entries: change the item, quantity, date, customer, vehicle, shift or note of a saved entry. Everything stays in the history."""
    items, moves, tab = load()
    st.subheader("Fix entries")
    st.caption("Pick a saved entry and correct it. Nothing is deleted: the old value is written into the entry's note with your name.")
    names = {r["id"]: ("%s | %s" % (r["brand"], r["name"]) if r["brand"] and r["brand"].lower() != "evergreen" else r["name"]) for _, r in items.iterrows()}
    units = items.set_index("id")["unit"].to_dict()
    t1, t2, t3 = st.tabs(["Fix one entry", "Move many to another item", "Rename an item"])
    TYPES = {"All": None, "Dispatch": ("dispatch",), "Production": ("production",), "Inward": ("inward",), "Stock added / opening": ("opening",), "Raw / waste": ("raw_in", "raw_use", "waste")}
    def pool(prefix):
        c1, c2 = st.columns(2); tp = c1.selectbox("Type", list(TYPES), key=prefix + "_t"); q = c2.text_input("Search (item, customer, vehicle)", key=prefix + "_q")
        c3, c4 = st.columns(2); d1 = c3.date_input("From", value=date.today() - timedelta(days=7), key=prefix + "_d1"); d2 = c4.date_input("To", value=date.today(), key=prefix + "_d2")
        rows = [m for m in S.rows("Moves") if m["type"] in L.FIXABLE and not L._is_void(m) and str(d1) <= m["date"] <= str(d2) and (TYPES[tp] is None or m["type"] in TYPES[tp])]
        if q.strip():
            ql = q.strip().lower(); rows = [m for m in rows if ql in (names.get(m["item_id"], "") + " " + m["party"] + " " + m["vehicle"] + " " + m["note"]).lower()]
        return sorted(rows, key=lambda m: (m["date"], m["ts"]), reverse=True)[:150]
    def label(m):
        return "%s · %s · %s%s · %s %s" % (m["date"][5:], KIND.get(m["type"], m["type"]).split(" /")[0], (m["party"] + " · ") if m["party"] else "", names.get(m["item_id"], m["item_id"]), L.fmt(abs(L.f(m["qty"]))), units.get(m["item_id"], ""))
    with t1:
        rows = pool("fx")
        if not rows: st.info("No entries found for these choices.")
        else:
            pick = st.selectbox("Entry to fix (%d shown)" % len(rows), [m["id"] for m in rows], index=None, placeholder="Choose the entry", format_func=lambda i: (label(next(x for x in rows if x["id"] == i)) if any(x["id"] == i for x in rows) else str(i)), key="fx_pick")
            m = next((x for x in rows if x["id"] == pick), None)
            if m:
                st.markdown("**Now:** " + label(m) + (" · vehicle %s" % m["vehicle"] if m["vehicle"] else "") + (" · shift %s" % m["shift"] if m["shift"] else "") + " · entered by %s" % m["user"])
                kinds = ["raw"] if m["type"] in ("raw_in", "raw_use") else ["finished"]
                st.markdown("**Change the item** (leave empty to keep the same item)")
                newit = pick_item("fxi", items, kinds=kinds)
                c1, c2 = st.columns(2)
                qty = c1.number_input("Quantity", min_value=0.0, value=float(abs(L.f(m["qty"]))), step=1.0, format="%g", key="fx_q_" + m["id"])
                dt = c2.date_input("Date", value=date.fromisoformat(m["date"]), max_value=date.today(), key="fx_d_" + m["id"])
                c3, c4 = st.columns(2)
                party = c3.text_input("Customer / place", value=m["party"], key="fx_p_" + m["id"]) if m["type"] in ("dispatch", "inward") else None
                veh = c4.text_input("Vehicle", value=m["vehicle"], key="fx_v_" + m["id"]) if m["type"] == "dispatch" else None
                shift = machine = None
                if m["type"] == "dispatch":
                    shift = st.selectbox("Trip of the day (the vehicle's 1st, 2nd... trip)", ["1", "2", "3", "4"], index=(["1", "2", "3", "4"].index(m["shift"]) if m["shift"] in ("1", "2", "3", "4") else 0), key="fx_s_" + m["id"])
                    shift = "" if shift == "1" else shift
                if m["type"] == "production":
                    c5, c6 = st.columns(2); shift = c5.selectbox("Shift", ["", "A", "B"], index=["", "A", "B"].index(m["shift"]) if m["shift"] in ("", "A", "B") else 0, key="fx_s_" + m["id"])
                    machine = c6.text_input("Machine", value=m["machine"], key="fx_m_" + m["id"])
                nt = st.text_input("Note", value=m["note"].split(" [")[0], key="fx_n_" + m["id"])
                whole = st.checkbox("Apply date, customer, vehicle and shift to every line saved with this entry (the whole load)", value=m["type"] == "dispatch", key="fx_w_" + m["id"]) if m["type"] in ("dispatch", "production") else False
                neg = st.checkbox("Allow stock to go below zero (admin only)", key="fx_neg") if IS_ADMIN else False
                if st.button("Save the correction", type="primary", key="fx_save"):
                    keep_note = None if nt.strip() == m["note"].split(" [")[0].strip() else nt
                    try:
                        n = L.edit_entry(S, ME, m["id"], item_id=(newit["id"] if newit is not None else None), qty=qty, date=str(dt), party=party, vehicle=veh, shift=shift, machine=machine, note=keep_note, whole_load=whole, allow_negative=neg)
                        act("fix_entry", "%s %s" % (m["type"], m["id"])); st.toast("Corrected %d line(s)" % n if n else "Nothing was different", icon="✅"); reset_picker("fxi"); st.rerun()
                    except L.Problem as e: st.error(str(e))
                    except Exception as e: st.error("Could not save. (%s)" % str(e)[:160])
    with t2:
        st.caption("For a mix-up that happened several times: tick the lines, choose the right item, press move.")
        rows = pool("fm")
        if rows:
            df = pd.DataFrame([dict(Move=False, id=m["id"], Date=m["date"], Type=KIND.get(m["type"], m["type"]).split(" /")[0], Customer=m["party"], Item=names.get(m["item_id"], m["item_id"]), Qty=abs(L.f(m["qty"]))) for m in rows])
            ed = st.data_editor(df, hide_index=True, disabled=["id", "Date", "Type", "Customer", "Item", "Qty"], column_order=["Move", "Date", "Type", "Customer", "Item", "Qty"], key="fm_ed", **WIDE)
            chosen = ed[ed["Move"]]["id"].tolist(); st.caption("%d lines ticked" % len(chosen))
            st.markdown("**Move them to this item**"); target = pick_item("fmi", items)
            neg = st.checkbox("Allow stock to go below zero (admin only)", key="fm_neg") if IS_ADMIN else False
            if st.button("Move the ticked lines", type="primary", key="fm_go"):
                if not chosen or target is None: st.error("Tick the lines and choose the item.")
                else:
                    try:
                        n = L.move_entries_to_item(S, ME, chosen, target["id"], neg); act("move_entries", "%d lines to %s" % (n, target["id"])); st.toast("Moved %d line(s)" % n, icon="✅"); reset_picker("fmi"); st.rerun()
                    except L.Problem as e: st.error(str(e))
                    except Exception as e: st.error("Could not move. (%s)" % str(e)[:160])
    with t3:
        st.caption("Change an item's name, size, brand, category or unit. Its stock and all its history stay with it; only the name changes everywhere.")
        alli = L.items_df(S.rows("Items"), False)
        lab = {r["id"]: "%s | %s  [%s]%s" % (r["brand"], r["name"], r["category"], "" if r["active"] else "  (switched off)") for _, r in alli.iterrows()}
        q = st.text_input("Search the item (e.g. 11.2kg)", key="rn_q")
        ids = [i for i in lab if not q.strip() or q.strip().lower() in lab[i].lower()]
        pk = st.selectbox("Item to change (%d shown)" % len(ids), ids, index=None, placeholder="Choose the item", format_func=lambda i: lab.get(i, str(i)), key="rn_pick")
        if pk:
            r = alli[alli["id"] == pk].iloc[0]
            cats = L.categories(S.rows("Items"), S.rows("Lists")); cats = cats if r["category"] in cats else [r["category"]] + cats
            c1, c2 = st.columns(2); cat = c1.selectbox("Category", cats, index=cats.index(r["category"]), key="rn_c_" + pk); br = c2.text_input("Brand", value=r["brand"], key="rn_b_" + pk)
            nm = st.text_input("Item name", value=r["item"], key="rn_i_" + pk); sp = st.text_input("Size / details", value=r["spec"], key="rn_s_" + pk)
            units = ["rolls", "pieces", "sets", "bags", "boxes", "kg", "nos", "bundle"]; units = units if r["unit"] in units else [r["unit"]] + units
            c3, c4 = st.columns(2); un = c3.selectbox("Unit", units, index=units.index(r["unit"]), key="rn_u_" + pk); ac = c4.checkbox("Active (shown in lists)", value=bool(r["active"]), key="rn_a_" + pk)
            st.markdown("**It will read:** " + ("%s | %s %s" % (br, nm, sp)).strip())
            if st.button("Save the new name", type="primary", key="rn_save"):
                try:
                    c = L.edit_item(S, ME, pk, category=cat, brand=br, item=nm, spec=sp, unit=un, active=ac)
                    if c: act("rename_item", "%s %s" % (pk, c)); st.toast("Saved", icon="✅"); st.rerun()
                    else: st.info("Nothing was different.")
                except L.Problem as e: st.error(str(e))
                except Exception as e: st.error("Could not save. (%s)" % str(e)[:160])
    st.caption("Note: fixing a dispatch does not change the orders it ticked off. A return needs to be entered on the Returns screen.")


def wa_draft_done():
    t = st.session_state.get("wa_txt")
    st.session_state["_dl_whatsapp"] = {"wa_txt": t} if t else {}
    try: L.draft_put(S, ME, "whatsapp", None)
    except Exception: pass


def wa_review(parsed, tag):
    """Show what was read, one line at a time, for the person to check and correct. Saves only when the button is pressed."""
    items, _, tab = load()
    recs = items[items["kind"] == "finished"].to_dict("records"); ids = [r["id"] for r in recs]
    nm = {r["id"]: "%s | %s" % (r["brand"], r["name"]) for r in recs}; good = tab.set_index("id")["good"].to_dict()
    kind = parsed["kind"]; today_ = date.today()
    def pdate(s):
        try: d = date.fromisoformat(s)
        except Exception: d = today_
        return min(d, today_)
    c1, c2 = st.columns(2)
    dt = c1.date_input("Date", value=pdate(parsed.get("date", "")), max_value=today_, key=tag + "_dt")
    shift = vehicle = ""
    if kind == "production": shift = c2.selectbox("Shift", ["", "A", "B"], index=["", "A", "B"].index(parsed.get("shift", "")) if parsed.get("shift", "") in ("", "A", "B") else 0, key=tag + "_sh")
    elif kind == "order": due = c2.date_input("Needed by", value=date.today() + timedelta(days=3), key=tag + "_due")
    else: vehicle = c2.text_input("Vehicle", value=parsed.get("vehicle", ""), key=tag + "_veh")
    groups = parsed["groups"] if kind in ("dispatch", "order") else [dict(party="", lines=parsed["lines"])]
    have = {m["ref"] for m in S.rows("Moves")} if kind == "production" else set()
    out = []; needs = 0
    for gi, g in enumerate(groups):
        party = g["party"]
        if kind in ("dispatch", "order"): party = st.text_input("Customer / place", value=g["party"], key="%s_p%d" % (tag, gi))
        lines = []
        for li, l in enumerate(g["lines"]):
            best, cands, sure = wa.match(l["text"] + ((" (%s)" % wa.brand_of(g["party"])) if kind in ("dispatch", "order") and wa.brand_of(g["party"]) and wa.brand_of(g["party"]) not in l["text"].lower() else ""), recs)
            k = "%s_%d_%d" % (tag, gi, li)
            with st.container(border=True) if NEW else st.container():
                st.markdown("**%s** — %s" % ("\u2705" if sure else "\u26a0\ufe0f check this", l["text"]) + ("  \u2014 **no quantity found, type it below**" if l["qty"] <= 0 else ""))
                a, b, c = st.columns([1, 2, 6])
                inc = a.checkbox("Use", value=True, key=k + "_u")
                q = b.number_input("Qty", min_value=0.0, value=float(l["qty"]), step=1.0, format="%g", key=k + "_q", label_visibility="collapsed")
                it = c.selectbox("Item", ids, index=ids.index(best["id"]) if (sure and best["id"] in ids) else None, placeholder="Choose the item", format_func=lambda i: nm.get(i, i), key=k + "_i", label_visibility="collapsed")
                if not sure: st.caption("Closest: " + " · ".join(nm[x["id"]] for _, x in cands[:3] if x["id"] in nm))
                if it: st.caption("Stock now: %s %s" % (L.fmt(good.get(it, 0)), next((r["unit"] for r in recs if r["id"] == it), "")))
                if kind == "production" and it and "wa-%s-%s-%s" % (dt, shift or "x", it) in have: st.warning("This item already has a WhatsApp production entry for this date and shift. It will not be added again.")
            if inc:
                if not it or q <= 0: needs += 1
                else: lines.append((it, float(q)))
        out.append((party, lines))
    if needs: st.warning("%d line(s) still need an item and quantity. Pick the item, or untick 'Use' to skip the line." % needs)
    if kind == "production":
        merged = {}
        for _, ls in out:
            for i, q in ls: merged[i] = merged.get(i, 0.0) + q
        if st.button("\u2705 Save %d production line(s)" % len(merged), type="primary", key=tag + "_save", disabled=bool(needs) or not merged):
            try:
                for i, q in merged.items():
                    L.add_production(S, ME, i, q, str(dt), shift, "", "From WhatsApp", "wa-%s-%s-%s" % (dt, shift or "x", i))
                wa_draft_done(); act("wa_production", "%d lines %s %s" % (len(merged), dt, shift)); st.success("Saved %d production line(s) for %s shift %s." % (len(merged), dt, shift or "-"))
            except L.Problem as e: st.error(str(e))
            except Exception as e: st.error("Could not save. (%s)" % str(e)[:160])
    elif kind == "order":
        drops = [(p, ls) for p, ls in out if ls]
        miss = [p for p, ls in drops if not p.strip()]
        if miss: st.warning("Type the customer name for every group.")
        n_l = sum(len(ls) for _, ls in drops)
        if st.button("\u2705 Save %d order line(s)" % n_l, type="primary", key=tag + "_save", disabled=bool(needs) or not drops or bool(miss)):
            try:
                for p, ls in drops:
                    for i, q in ls: L.add_order(S, ME, p, i, q, str(due), "From WhatsApp")
                wa_draft_done(); act("wa_order", "%d lines" % n_l); st.success("Saved %d order line(s). They now show in Orders and To produce." % n_l)
            except L.Problem as e: st.error(str(e))
            except Exception as e: st.error("Could not save. (%s)" % str(e)[:160])
    else:
        drops = [(p, ls) for p, ls in out if ls]
        neg = st.checkbox("Allow sending more than stock (admin only)", key=tag + "_neg") if IS_ADMIN else False
        tno = trip_no_pick(vehicle, str(dt), tag + "_tno")
        if st.button("\u2705 Save this dispatch (%d customer(s))" % len(drops), type="primary", key=tag + "_save", disabled=bool(needs) or not drops):
            trip = wa.trip_key(str(dt), vehicle, [dict(party=p, lines=[dict(item=i, qty=q) for i, q in ls]) for p, ls in drops])
            if any(m["ref"] == trip + ".0" for m in S.rows("Moves")): st.warning("This exact dispatch is already saved.")
            else:
              try:
                L.add_dispatch_trip(S, ME, drops, vehicle, str(dt), "From WhatsApp", neg, trip, tno)
                wa_draft_done(); act("wa_dispatch", "%d customers %s" % (len(drops), dt)); st.success("Dispatch saved."); st.session_state["last_slip"] = trip + ".0"; slip_button(trip + ".0", "Download vehicle slip (PDF)", tag + "_slip")
              except L.Problem as e: st.error(str(e))
              except Exception as e: st.error("Could not save. (%s)" % str(e)[:160])


def screen_wa():
    st.subheader("From WhatsApp")
    st.caption("Paste a production, dispatch or customer order message from WhatsApp. The app shows what it understood, line by line. Nothing is saved until you check it and press Save.")
    draft_restore("whatsapp", []); draft_banner("whatsapp", ["wa_txt"])
    txt = st.text_area("Paste the message here", height=200, key="wa_txt", placeholder="Production details\nDate- 12/11/26\nShift-B\n\n8mil 7.3kg 20cm 800mtrs(evg) -06rolls ...")
    draft_save("whatsapp", ["wa_txt"])
    if txt.strip():
        kind = st.radio("This is a", ["Production", "Dispatch", "Order"], index=0 if wa.guess_kind(txt) == "production" else 1, horizontal=True, key="wa_kind")
        parsed = wa.parse_production(txt) if kind == "Production" else wa.parse_dispatch(txt)
        if kind == "Order": parsed = dict(parsed, kind="order")
        n = len(parsed["lines"]) if kind == "Production" else sum(len(g["lines"]) for g in parsed["groups"])
        if not n: st.error("I could not find any lines. Each line should end with a quantity, like '16R nisi 300mtrs 10kg 40cm -112rolls'.")
        else: wa_review(parsed, "wp" + hashlib.md5((kind + txt).encode()).hexdigest()[:6])


SCREENS = {"Summary": screen_summary, "Transport": screen_transport, "Customers": screen_customers, "Stock": screen_stock, "Inward": screen_inward, "Add Stock": screen_addstock, "Production": screen_production, "Dispatch": screen_dispatch, "WhatsApp": screen_wa, "Orders": screen_orders, "Returns": screen_returns,
           "Raw & Waste": screen_raw, "Count": screen_count, "Reports": screen_reports, "Fix entries": screen_fix, "Admin": screen_admin}

st.markdown('<div class="eg-hero"><div><div class="t">🌿 Evergreen Stock%s</div><div class="s">Evergreen Irrigation · %s</div></div><div class="pill">%s</div></div>' % ("" if LIVE else " · TRIAL", date.today().strftime("%a, %d %b %Y"), html.escape(str(ME))), unsafe_allow_html=True)
with st.sidebar:
    st.write("Signed in: **%s** (%s)" % (ME, ROLE))
    if st.button("Sign out"):
        act("logout"); L.end_session(S, st.session_state.get("tok")); set_cookie(None); st.session_state.clear(); st.query_params.clear(); st.rerun()
nav = L.NAV[ROLE]
main = [p for p in nav if p in L.NAV_MAIN]; more = [p for p in nav if p not in L.NAV_MAIN]
with st.container(key="menu"):
    page = st.radio("Go to", main + (["More ▾"] if more else []), horizontal=True, label_visibility="collapsed", key="page")
    if page == "More ▾":
        page = st.radio("More screens", more, horizontal=True, label_visibility="collapsed", key="page2")
if st.session_state.get("_lastpage") != page:    # one line each time someone opens a different screen
    st.session_state["_lastpage"] = page; act("view", page)
try:
    SCREENS[page]()
except Exception as e:  # never show a stack trace to staff
    act("screen_error", str(e)[:200], "error")
    for _d in ("production", "whatsapp"):
        try: L.draft_put(S, ME, _d, None)
        except Exception: pass
    st.error("Something went wrong. Please refresh the page. (%s)" % str(e)[:140])
    if os.environ.get("STOCK_DEBUG"): raise
