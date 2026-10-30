"""Storage layer: one interface, two backends (local CSV for trial, Google Sheets for live)."""
import csv, os, threading, time, uuid, hashlib, hmac, secrets, urllib.parse
from datetime import datetime
from datetime import timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
SCHEMA = {
    "Items":    ["id", "category", "brand", "item", "spec", "unit", "kind", "price", "min_level", "std_weight", "active", "subcategory"],
    "Moves":    ["id", "ts", "date", "item_id", "qty", "bucket", "type", "ref", "party", "vehicle", "machine", "shift", "note", "user", "void"],
    "Orders":   ["id", "ts", "date", "due", "party", "item_id", "qty", "status", "note", "user"],
    "Lists":    ["kind", "name", "active"],
    "Users":    ["name", "role", "salt", "pin_hash", "active", "fails", "locked_until", "created"],
    "Sessions": ["token_hash", "user", "expires", "created"],
    "Log":      ["ts", "date", "user", "role", "action", "screen", "detail", "result", "ms"],
}
READ = [t for t in SCHEMA if t != "Log"]      # the activity log is write-only for the app (it can grow large)

def now(): return datetime.now(IST)
def today(): return now().strftime("%Y-%m-%d")
def stamp(): return now().strftime("%Y-%m-%d %H:%M:%S")
def new_id(): return uuid.uuid4().hex[:10]

def hash_pin(pin, salt): return hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), 60000).hex()
def check_hash(pin, salt, h): return hmac.compare_digest(hash_pin(pin, salt), h)
def token_hash(tok): return hashlib.sha256(tok.encode()).hexdigest()
def new_token(): return secrets.token_urlsafe(32)


class LocalBackend:
    kind = "local"
    def __init__(self, path):
        self.path = path; self.lock = threading.Lock(); os.makedirs(path, exist_ok=True)
    def _f(self, t): return os.path.join(self.path, t + ".csv")
    def ensure(self):
        for t, cols in SCHEMA.items():
            if not os.path.exists(self._f(t)):
                with open(self._f(t), "w", newline="", encoding="utf-8") as f: csv.writer(f).writerow(cols)
            else:                       # a newer version added columns: pad the old file
                with open(self._f(t), newline="", encoding="utf-8") as f: lines = list(csv.reader(f))
                if lines and lines[0] != cols and lines[0] == cols[:len(lines[0])]:
                    pad = len(cols) - len(lines[0]); lines[0] = cols
                    lines = [lines[0]] + [r + [""] * pad for r in lines[1:]]
                    with open(self._f(t), "w", newline="", encoding="utf-8") as f: csv.writer(f).writerows(lines)
    def read_all(self):
        out = {}
        with self.lock:
            for t in READ:
                cols = SCHEMA[t]
                with open(self._f(t), newline="", encoding="utf-8") as f:
                    rows = list(csv.DictReader(f))
                for i, r in enumerate(rows): r["_r"] = i + 2
                out[t] = rows
        return out
    def append(self, t, rows):
        cols = SCHEMA[t]
        with self.lock, open(self._f(t), "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            for r in rows: w.writerow([r.get(c, "") for c in cols])
    def replace_tab(self, tab, rows, **kw):
        with self.lock, open(os.path.join(self.path, tab.replace(" ", "_") + ".csv"), "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
    def prune_tabs(self, prefix, keep):
        names = sorted(f for f in os.listdir(self.path) if f.startswith(prefix.replace(" ", "_")))
        for f in names[:-keep]: os.remove(os.path.join(self.path, f))
    def update_row(self, t, r, row):
        cols = SCHEMA[t]
        with self.lock:
            with open(self._f(t), newline="", encoding="utf-8") as f: lines = list(csv.reader(f))
            lines[r - 1] = [row.get(c, "") for c in cols]
            tmp = self._f(t) + ".tmp"
            with open(tmp, "w", newline="", encoding="utf-8") as f: csv.writer(f).writerows(lines)
            os.replace(tmp, self._f(t))


class SheetsBackend:
    kind = "sheets"
    API = "https://sheets.googleapis.com/v4/spreadsheets"
    def __init__(self, sheet_id, creds_info=None, session=None):
        self.sid = sheet_id
        if session is None:
            from google.oauth2 import service_account
            from google.auth.transport.requests import AuthorizedSession
            creds = service_account.Credentials.from_service_account_info(
                dict(creds_info), scopes=["https://www.googleapis.com/auth/spreadsheets"])
            session = AuthorizedSession(creds)
        self.s = session
    def _call(self, method, url, **kw):
        last = None
        for attempt in range(4):
            r = self.s.request(method, url, timeout=30, **kw)
            if r.status_code in (429, 500, 502, 503):
                time.sleep(1.5 * (attempt + 1)); last = r; continue
            if r.status_code >= 400:
                raise RuntimeError("Google Sheets said: %s %s" % (r.status_code, r.text[:300]))
            return r.json()
        raise RuntimeError("Google Sheets is busy, try again. (%s)" % (last.status_code if last else "?"))
    def ensure(self):
        meta = self._call("GET", "%s/%s?fields=sheets.properties.title" % (self.API, self.sid))
        have = {s["properties"]["title"] for s in meta.get("sheets", [])}
        need = [t for t in SCHEMA if t not in have]
        if need:
            self._call("POST", "%s/%s:batchUpdate" % (self.API, self.sid),
                       json={"requests": [{"addSheet": {"properties": {"title": t}}} for t in need]})
        for t in SCHEMA:
            r = self._call("GET", "%s/%s/values/%s!1:1" % (self.API, self.sid, t))
            have_h = (r.get("values") or [[]])[0]
            if not have_h or (have_h != SCHEMA[t] and have_h == SCHEMA[t][:len(have_h)]):     # new sheet, or a newer version added columns
                self._call("PUT", "%s/%s/values/%s!A1?valueInputOption=RAW" % (self.API, self.sid, t), json={"values": [SCHEMA[t]]})
    def read_all(self):
        q = "&".join("ranges=%s!A:Z" % t for t in READ)
        r = self._call("GET", "%s/%s/values:batchGet?%s&valueRenderOption=UNFORMATTED_VALUE" % (self.API, self.sid, q))
        out = {}
        for t, vr in zip(READ, r["valueRanges"]):
            vals = vr.get("values", []); cols = SCHEMA[t]; rows = []
            for i, v in enumerate(vals[1:], start=2):
                if not any(str(x).strip() for x in v): continue
                row = {c: ("" if j >= len(v) else _s(v[j])) for j, c in enumerate(cols)}
                row["_r"] = i; rows.append(row)
            out[t] = rows
        return out
    def append(self, t, rows):
        if not rows: return
        vals = [[r.get(c, "") for c in SCHEMA[t]] for r in rows]
        self._call("POST", "%s/%s/values/%s!A1:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS" % (self.API, self.sid, t), json={"values": vals})
    def prune_tabs(self, prefix, keep):
        meta = self._call("GET", "%s/%s?fields=sheets.properties" % (self.API, self.sid))
        old = sorted((x["properties"]["title"], x["properties"]["sheetId"]) for x in meta["sheets"] if x["properties"]["title"].startswith(prefix))
        if len(old) > keep:
            self._call("POST", "%s/%s:batchUpdate" % (self.API, self.sid), json={"requests": [{"deleteSheet": {"sheetId": sid}} for _, sid in old[:-keep]]})
    def replace_tab(self, tab, rows, header_rows=2, fixed_cols=9):
        """Rewrite a human-readable report tab (created if missing). The app owns this tab; nobody types in it."""
        meta = self._call("GET", "%s/%s?fields=sheets.properties" % (self.API, self.sid))
        sid = next((x["properties"]["sheetId"] for x in meta["sheets"] if x["properties"]["title"] == tab), None)
        if sid is None:
            r = self._call("POST", "%s/%s:batchUpdate" % (self.API, self.sid), json={"requests": [{"addSheet": {"properties": {"title": tab}}}]})
            sid = r["replies"][0]["addSheet"]["properties"]["sheetId"]
        q = urllib.parse.quote(tab)
        self._call("POST", "%s/%s/values/%s:clear" % (self.API, self.sid, q), json={})
        for i in range(0, len(rows), 400):
            self._call("PUT", "%s/%s/values/%s!A%d?valueInputOption=RAW" % (self.API, self.sid, q, i + 1), json={"values": rows[i:i + 400]})
        try:
            self._call("POST", "%s/%s:batchUpdate" % (self.API, self.sid), json={"requests": [
                {"updateSheetProperties": {"properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": header_rows, "frozenColumnCount": 3}}, "fields": "gridProperties(frozenRowCount,frozenColumnCount)"}},
                {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": header_rows}, "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.85, "green": 0.93, "blue": 0.85}}}, "fields": "userEnteredFormat(textFormat,backgroundColor)"}}]})
        except Exception:
            pass   # looks only
    def update_row(self, t, r, row):
        self._call("PUT", "%s/%s/values/%s!A%d?valueInputOption=RAW" % (self.API, self.sid, t, r), json={"values": [[row.get(c, "") for c in SCHEMA[t]]]})

def _s(x):
    if isinstance(x, float) and x.is_integer(): return str(int(x))
    return str(x)


class Store:
    """Cached snapshot of all tables. Reads are shared by every visitor; any write refreshes it."""
    TTL = 10
    def __init__(self, backend):
        self.b = backend; self.lock = threading.RLock(); self.snap = None; self.t = 0
        self.sync_fn = None; self.writes = 0; self.synced = 0; self.last_sync = 0.0; self.busy = False; self.timer = False; self.sync_error = ""
        self.bk_day = None; self.bk_busy = False; self.bk_error = ""; self.bk_next = 0.0
        self.logq = []; self.log_timer = False; self.log_error = ""
        backend.ensure()
    def data(self):
        with self.lock:
            if self.snap is None or time.time() - self.t > self.TTL:
                self.snap = self.b.read_all(); self.t = time.time()
            return self.snap
    def refresh(self):
        with self.lock: self.snap = None
    def rows(self, t): return self.data()[t]
    def append(self, t, rows):
        with self.lock:
            self.b.append(t, rows); self.snap = None
        self._dirty(t)
    def update(self, t, r, row):
        with self.lock:
            clean = {k: v for k, v in row.items() if k != "_r"}
            self.b.update_row(t, r, clean); self.snap = None
        self._dirty(t)

    # ---- activity log: every action is queued and written to the Log tab in small batches (never slows the screen)
    def log(self, user="", role="", action="", screen="", detail="", result="ok", ms=""):
        e = dict(ts=stamp(), date=today(), user=user, role=role, action=action, screen=screen, detail=str(detail)[:300], result=result, ms=ms)
        with self.lock:
            self.logq.append(e); self.logq = self.logq[-800:]
            if not self.log_timer:
                self.log_timer = True; t = threading.Timer(6, self._flush_log); t.daemon = True; t.start()
    def _flush_log(self):
        with self.lock:
            batch, self.logq = self.logq, []; self.log_timer = False
        if not batch: return
        try:
            self.b.append("Log", batch); self.log_error = ""
        except Exception as ex:
            self.log_error = str(ex)[:200]
            with self.lock: self.logq = (batch + self.logq)[-800:]

    # ---- keep the Google Sheet "Register" tab up to date in the background (at most once every GAP seconds)
    GAP = 40
    def _dirty(self, table):
        if table in ("Items", "Moves"):
            self.writes += 1; self.kick()
    def kick(self, force=False):
        if not self.sync_fn: return
        with self.lock:
            if self.busy or (self.writes == self.synced and not force): return
            wait = self.GAP - (time.time() - self.last_sync)
            if wait > 0 and not force:
                if not self.timer:
                    self.timer = True; t = threading.Timer(wait + 1, self._timer); t.daemon = True; t.start()
                return
            self.busy = True; mark = self.writes
        threading.Thread(target=self._work, args=(mark,), daemon=True).start()
    def _timer(self):
        self.timer = False; self.kick()
    def _work(self, mark):
        ok = False
        try:
            self.sync_fn(self); ok = True; self.sync_error = ""
        except Exception as e:
            self.sync_error = str(e)[:200]
        finally:
            with self.lock:
                self.busy = False; self.last_sync = time.time()
                if ok: self.synced = max(self.synced, mark)

    # ---- one backup copy per day, kept inside the same Google Sheet (last 7 days)
    def maybe_backup(self, fn):
        d = today()
        with self.lock:
            if self.bk_day == d or self.bk_busy or time.time() < self.bk_next or not self.sync_fn: return
            self.bk_busy = True; self.bk_next = time.time() + 600
        def work():
            ok = False
            try: fn(self, d); ok = True; self.bk_error = ""
            except Exception as e: self.bk_error = str(e)[:200]
            finally:
                with self.lock:
                    self.bk_busy = False
                    if ok: self.bk_day = d
        threading.Thread(target=work, daemon=True).start()
