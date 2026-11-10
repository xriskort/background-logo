#!/usr/bin/env python3
"""Your live dashboard: one page with everything the trader pack knows. Standard library only.

It reads the files the other skills write and shows them together: the account
and today's change, positions against their targets, every proposed order and
where it stands (risk check, your yes, placed), price alerts, how fresh each
monitor is, what the gatekeeper refused, and what the Claudes said to each other.

    python3 dash.py serve                  # http://127.0.0.1:8765, refreshes itself every 5 s
    python3 dash.py serve --port 9000 --every 10 --open
    python3 dash.py build                  # trader/dashboard.html, a snapshot that opens anywhere
    python3 dash.py text                   # the same, as text for the chat
    python3 dash.py json                   # the state behind the page

It never writes to trader/ except the snapshot file `build` makes, never places
an order, and the server only listens on this computer (127.0.0.1) and only
answers GET. Prices are whatever trader/prices.json holds (delayed quotes from
trader-alerts); refresh them with alerts.py quote --holdings --write.

It reuses the pack's own code, so the numbers match the other skills exactly:
trader-rebalance for drift against targets, trader-broker for each order's
status, trader-alerts for the NYSE clock. If one of those skills is missing,
that part of the page says so instead.
"""

import argparse
import datetime
import http.server
import importlib.util
import json
import os
import sys
import threading
import webbrowser

sys.dont_write_bytecode = True  # importing sibling skills must not leave __pycache__ folders behind
HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS = os.path.dirname(HERE)
TEMPLATE = os.path.join(HERE, "dashboard.html")


# ---------------------------------------------------------------- reading

def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def sibling(skill, filename, modname):
    path = os.path.join(SKILLS, skill, filename)
    if not os.path.exists(path):
        return None
    try:
        spec = importlib.util.spec_from_file_location(modname, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:  # noqa: BLE001 - a broken sibling must not take the page down
        return None


def parse_time(s):
    """ISO time -> aware datetime (naive strings are local time)."""
    if not s:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt


def minutes_ago(s, now):
    dt = parse_time(s)
    return None if dt is None else round((now - dt).total_seconds() / 60.0, 1)


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def r2(x):
    return None if x is None else round(x, 2)


# ---------------------------------------------------------------- the state

def account_and_positions(cfg, pf, prices, detail, weights_doc, notes):
    rebalance = sibling("trader-rebalance", "rebalance.py", "_dash_rebalance")
    positions, cash = [], None
    budget = f(cfg.get("budget"))
    fresh = pf is None
    if pf is None:
        cash = budget
    else:
        cash = f(pf.get("cash")) or 0.0
    for p in (pf or {}).get("positions", []):
        t = str(p.get("ticker") or p.get("symbol") or "").upper()
        if not t:
            continue
        lots = p.get("lots") or []
        shares = f(p.get("shares", p.get("qty")))
        if shares is None:
            shares = sum(f(l.get("shares")) or 0 for l in lots)
        cost = sum(f(l.get("cost")) or 0 for l in lots) if lots else f(p.get("cost"))
        price = prices.get(t)
        prev = f((detail.get(t) or {}).get("prev_close"))
        value = shares * price if price else cost
        if not price:
            notes.append("no price for %s: valued at cost (refresh with trader-alerts)" % t)
        row = {"ticker": t, "shares": round(shares, 6), "price": price, "value": r2(value), "cost": r2(cost),
               "gain": r2(value - cost) if price and cost else None,
               "gain_pct": r2(100.0 * (value / cost - 1)) if price and cost else None,
               "day_change": r2(shares * (price - prev)) if price and prev else None,
               "day_pct": r2(100.0 * (price / prev - 1)) if price and prev else None,
               "has_price": bool(price)}
        positions.append(row)
    invested = sum(p["value"] or 0 for p in positions)
    total = (cash or 0) + invested
    cost = sum(p["cost"] or 0 for p in positions if p["has_price"])
    gain = sum(p["gain"] or 0 for p in positions if p["gain"] is not None)
    day = [p["day_change"] for p in positions if p["day_change"] is not None]
    day_change = sum(day) if day else None
    buffer_pct = f(cfg.get("cash_buffer_pct"))
    buffer_pct = 10.0 if buffer_pct is None else buffer_pct
    for p in positions:
        p["weight_pct"] = r2(100.0 * p["value"] / total) if total and p["value"] is not None else None

    # targets and drift, with trader-rebalance's own math
    band = f(cfg.get("rebalance_band_pct")) or 5.0
    targets = {"source": None, "band": band, "available": False}
    if weights_doc and rebalance is not None:
        targets["source"] = weights_doc.get("source") if isinstance(weights_doc, dict) else None
        names = {}
        rows = weights_doc.get("weights", []) if isinstance(weights_doc, dict) else []
        for r in rows if isinstance(rows, list) else []:
            if isinstance(r, dict) and r.get("name"):
                names[str(r.get("ticker", "")).upper()] = r["name"]
        try:
            weights = rebalance.parse_targets(weights_doc, cfg.get("blocked"))
            base_pf = pf if pf is not None else {"cash": budget or 0, "positions": []}
            res = rebalance.plan(base_pf, prices, weights, cfg)
            by = {row["ticker"]: row for row in res["rows"]}
            have = {p["ticker"] for p in positions}
            for t, row in by.items():
                if t not in have:
                    positions.append({"ticker": t, "shares": 0, "price": prices.get(t), "value": 0, "cost": 0,
                                      "gain": None, "gain_pct": None, "day_change": None, "day_pct": None,
                                      "has_price": bool(prices.get(t)), "weight_pct": 0.0})
            for p in positions:
                row = by.get(p["ticker"])
                p["name"] = names.get(p["ticker"])
                if row:
                    p["target_pct"] = row["target_pct"]
                    p["drift"] = row["drift"]
                    p["outside_band"] = row["tracked"] and abs(row["drift"]) > band + 1e-9
                    p["tracked"] = row["tracked"]
            targets["available"] = True
        except Exception as e:  # noqa: BLE001 - rebalance raises its own error type for missing prices
            notes.append("targets: %s" % e)
    elif weights_doc and rebalance is None:
        notes.append("trader-rebalance is missing, so drift against targets is not shown")
    positions.sort(key=lambda p: -(p.get("value") or 0))

    acct = {"paper": bool(cfg.get("paper", True)), "broker": cfg.get("broker", "alpaca"), "fresh": fresh,
            "budget": budget, "cash": r2(cash), "invested": r2(invested), "total": r2(total), "cost": r2(cost),
            "gain": r2(gain) if positions else None, "gain_pct": r2(100.0 * gain / cost) if cost else None,
            "day_change": r2(day_change), "day_pct": r2(100.0 * day_change / (total - day_change))
            if day_change is not None and total - day_change else None,
            "buffer_pct": buffer_pct, "buffer_usd": r2(total * buffer_pct / 100.0) if total else None,
            "max_position_pct": f(cfg.get("max_position_pct")) or 25.0}
    return acct, positions, targets


def orders_state(base, cfg, today, notes):
    ticket = sibling("trader-broker", "ticket.py", "_dash_ticket")
    doc = read_json(os.path.join(base, "trader", "orders.json"))
    orders = doc.get("orders", doc) if isinstance(doc, dict) else doc
    if not isinstance(orders, list):
        return [], {}
    if ticket is None:
        notes.append("trader-broker is missing, so order status is not shown")
        return [], {}
    risk = read_json(os.path.join(base, "trader", "state", "risk.json"))
    state = ticket.load_state(os.path.join(base, "trader", "state", "broker.json"))
    out, counts = [], {}
    for i, o in enumerate(orders, 1):
        if not isinstance(o, dict):
            continue
        ready, label, rv = ticket.status_of(o, risk, state, today)
        rec = ticket.latest(state, ticket.fingerprint(o), today)
        if label.startswith("NOT READY"):
            key, step = "proposed", 1
        elif label.startswith("BLOCKED"):
            key, step = "blocked", 2
        elif ready:
            key, step = "ready", 2
        elif rec and rec.get("status") == "approved":
            key, step = "approved", 3
        elif rec:
            key = rec.get("status") or "done"
            step = 4 if key == "placed" else 3
        else:
            key, step = "proposed", 1
        counts[key] = counts.get(key, 0) + 1
        out.append({"index": i, "plain": ticket.plain(o), "symbol": str(o.get("symbol", "")).upper(),
                    "side": o.get("side"), "why": o.get("why", ""), "status": key, "step": step,
                    "label": label, "reasons": (rv or {}).get("reasons", []) if key == "blocked" else [],
                    "warnings": (rv or {}).get("warnings", []), "at": (rec or {}).get("at"),
                    "broker_order_id": (rec or {}).get("broker_order_id")})
    counts["total"] = len(out)
    return out, counts


def describe_rule(r):
    t, sym = r.get("type"), str(r.get("symbol", "")).upper()
    price = r.get("price")
    if t == "opening_bell":
        return "Opening bell"
    if t in ("above", "target"):
        d = "%s at or above $%s" % (sym, price)
    elif t == "stop":
        d = "%s stop at $%s" % (sym, price)
    elif t == "below":
        d = "%s at or below $%s" % (sym, price)
    elif t == "pct_move":
        d = "%s moves %s%%%s" % (sym, r.get("pct"), (" " + r["direction"]) if r.get("direction") else "")
    else:
        d = "%s %s" % (sym, t)
    if r.get("rearm"):
        d += " (re-arms)"
    if r.get("note"):
        d += " - " + str(r["note"])
    return d


def alerts_state(base, today):
    rules = (read_json(os.path.join(base, "trader", "alerts.json")) or {}).get("rules", [])
    st = read_json(os.path.join(base, "trader", "state", "alerts.json")) or {}
    rung = st.get("rung", {})
    out = []
    for r in rules if isinstance(rules, list) else []:
        if not isinstance(r, dict):
            continue
        rid = r.get("id") or "%s-%s" % (r.get("symbol", "market"), r.get("type"))
        at = rung.get(rid)
        daily = r.get("type") in ("pct_move", "opening_bell")
        rang = bool(at) and (not daily or local_day(at) == today)
        out.append({"id": rid, "text": describe_rule(r), "rang": rang, "rang_at": at if rang else None,
                    "symbol": str(r.get("symbol", "")).upper()})
    return out, st.get("last_check")


def local_day(s):
    dt = parse_time(s)
    return dt.astimezone().date().isoformat() if dt else ""


def monitors(base, pdoc, alerts_last, market, now):
    st = lambda name: read_json(os.path.join(base, "trader", "state", name)) or {}  # noqa: E731
    risk = st("risk.json")
    rows = [
        ("Prices", pdoc.get("as_of"), "trader-alerts quote", 30 if market and market.get("open") else 60 * 72),
        ("Price alerts", alerts_last, "trader-alerts check", 30 if market and market.get("open") else 60 * 72),
        ("News", st("news.json").get("last_check"), "trader-news", 60 * 24),
        ("Pelosi filings", st("pelosi.json").get("last_check"), "trader-pelosi", 60 * 24 * 2),
        ("Risk check", risk.get("checked_at"), "trader-risk", 60 * 24),
    ]
    out = []
    for name, last, skill, limit in rows:
        age = minutes_ago(last, now)
        status = "never" if age is None else ("fresh" if age <= limit else "stale")
        out.append({"name": name, "last": last, "age_min": age, "status": status, "skill": skill,
                    "limit_min": limit})
    return out


def gate_state(base, today):
    path = os.environ.get("GATEKEEPER_LOG") or os.path.join(base, "trader", "state", "gatekeeper.jsonl")
    rows = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    installed = []
    for p in (os.path.join(base, ".claude", "settings.json"), os.path.join(base, ".claude", "settings.local.json"),
              os.path.join(os.path.expanduser("~"), ".claude", "settings.json")):
        try:
            with open(p, encoding="utf-8") as fh:
                if "gatekeeper/gate.py" in fh.read():
                    installed.append(p)
        except OSError:
            pass
    td = [r for r in rows if str(r.get("at", ""))[:10] == today]
    return {"installed": bool(installed), "skill_present": os.path.exists(os.path.join(SKILLS, "gatekeeper")),
            "today": {k: sum(1 for r in td if r.get("decision") == k) for k in ("deny", "ask", "ok")},
            "recent": [{k: r.get(k) for k in ("at", "decision", "rules", "reason", "what", "tool")}
                       for r in rows[-12:]][::-1]}


def talk_state(base, me):
    d = os.environ.get("CLAUDE_TALK_DIR") or os.path.join(base, "trader", "talk")
    msgs = []
    mdir = os.path.join(d, "messages")
    if os.path.isdir(mdir):
        for fn in os.listdir(mdir):
            if fn.endswith(".json"):
                m = read_json(os.path.join(mdir, fn))
                if isinstance(m, dict) and m.get("id"):
                    msgs.append(m)
    msgs.sort(key=lambda m: (str(m.get("at", "")), m["id"]))
    names = set()
    for m in msgs:
        names.add(m.get("from"))
        if m.get("to") != "all":
            names.add(m.get("to"))
    sdir = os.path.join(d, "seen")
    seen = {}
    if os.path.isdir(sdir):
        for fn in os.listdir(sdir):
            if fn.endswith(".json"):
                seen[fn[:-5]] = read_json(os.path.join(sdir, fn)) or {}
    names |= set(seen)
    names.discard(None)
    people = []
    for n in sorted(names):
        read = (seen.get(n) or {}).get("read", {})
        unread = [m for m in msgs if m.get("to") in (n, "all") and m.get("from") != n and m["id"] not in read]
        sent = [m for m in msgs if m.get("from") == n]
        people.append({"name": n, "unread": len(unread), "sent": len(sent),
                       "last_active": (seen.get(n) or {}).get("last_active") or (sent[-1]["at"] if sent else None)})
    waiting = [m for m in msgs if m.get("expects_reply") and not any(
        x.get("reply_to") == m["id"] and x.get("from") != m.get("from") for x in msgs)]
    recent = [{k: m.get(k) for k in ("id", "at", "from", "to", "kind", "subject", "expects_reply")}
              for m in msgs[-12:]][::-1]
    return {"total": len(msgs), "people": people, "open": len(waiting), "recent": recent, "me": me,
            "open_list": [{k: m.get(k) for k in ("id", "at", "from", "to", "subject")} for m in waiting[-5:]]}


def collect(base=".", me=None):
    base = os.path.abspath(base)
    now = datetime.datetime.now().astimezone()
    today = now.date().isoformat()
    notes = []
    tdir = os.path.join(base, "trader")
    cfg = read_json(os.path.join(tdir, "config.json")) or {}
    pdoc = read_json(os.path.join(tdir, "prices.json")) or {}
    raw = pdoc.get("prices", {}) if isinstance(pdoc, dict) else {}
    prices = {str(k).upper(): f(v) for k, v in (raw or {}).items() if f(v)}
    detail = {str(k).upper(): v for k, v in (pdoc.get("detail", {}) or {}).items()}
    pf = read_json(os.path.join(tdir, "portfolio.json"))
    weights_doc = read_json(os.path.join(tdir, "targets.json"))

    alerts_mod = sibling("trader-alerts", "alerts.py", "_dash_alerts")
    market = None
    if alerts_mod is not None:
        try:
            market = alerts_mod.market_status(datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None))
        except Exception as e:  # noqa: BLE001
            notes.append("market clock: %s" % e)

    acct, positions, targets = account_and_positions(cfg, pf, prices, detail, weights_doc, notes)
    orders, counts = orders_state(base, cfg, today, notes)
    alerts, alerts_last = alerts_state(base, today)
    return {
        "generated_at": now.replace(microsecond=0).isoformat(),
        "today": today,
        "base": base,
        "has_trader": os.path.isdir(tdir),
        "market": market,
        "account": acct,
        "positions": positions,
        "targets": targets,
        "prices_as_of": pdoc.get("as_of"),
        "orders": orders,
        "order_counts": counts,
        "alerts": alerts,
        "monitors": monitors(base, pdoc, alerts_last, market, now),
        "gate": gate_state(base, today),
        "talk": talk_state(base, me or os.environ.get("CLAUDE_TALK_AS") or "desk"),
        "notes": sorted(set(notes)),
    }


# ---------------------------------------------------------------- outputs

def page(state=None, every=5):
    with open(TEMPLATE, encoding="utf-8") as fh:
        html = fh.read()
    blob = "null" if state is None else json.dumps(state).replace("</", "<\\/")
    return (html.replace("/*__STATE__*/null", blob)
                .replace("/*__EVERY__*/5", str(int(every))))


def money(x, sign=False):
    if x is None:
        return "-"
    s = "${:,.2f}".format(abs(x))
    return ("+" if x >= 0 else "-") + s if sign else ("-" + s if x < 0 else s)


def pct(x, sign=True):
    return "-" if x is None else ("%+.2f%%" % x if sign else "%.1f%%" % x)


def ago(m):
    if m is None:
        return "never"
    if m < 1:
        return "just now"
    if m < 60:
        return "%dm ago" % m
    if m < 60 * 48:
        return "%dh ago" % (m // 60)
    return "%dd ago" % (m // 1440)


def text(s):
    a, mk = s["account"], s["market"]
    out = []
    head = "YOUR LIVE DASHBOARD  %s  %s" % (s["generated_at"][:16].replace("T", " "),
                                            "PAPER account" if a["paper"] else "LIVE ACCOUNT, REAL MONEY")
    if mk:
        head += "  NYSE %s" % ("open, closes %s ET" % mk.get("closes") if mk.get("open") else
                               "closed (%s), next open %s ET" % (mk.get("reason"), mk.get("next_open", "?")))
    out.append(head)
    if not s["has_trader"]:
        out.append("No trader/ folder here yet. Start with /trader-copycat or /trader-budget.")
        return "\n".join(out)
    if a["fresh"]:
        out.append("Not invested yet. Budget %s." % money(a["budget"]))
    else:
        out.append("Account %s   today %s (%s)   cash %s (buffer %s)   unrealized %s (%s)" % (
            money(a["total"]), money(a["day_change"], True), pct(a["day_pct"]), money(a["cash"]),
            money(a["buffer_usd"]), money(a["gain"], True), pct(a["gain_pct"])))
    if s["positions"]:
        out.append("")
        out.append("Positions" + ("  (band %s pts)" % int(s["targets"]["band"]) if s["targets"]["available"] else ""))
        for p in s["positions"]:
            tgt = ""
            if p.get("target_pct") is not None:
                tgt = "  target %.1f%% (%+.1f pts%s)" % (p["target_pct"], p["drift"],
                                                         ", OUTSIDE BAND" if p.get("outside_band") else "")
            out.append("  %-6s %10s sh  %10s  %11s  %6s%s  %s" % (
                p["ticker"], ("%.4f" % p["shares"]).rstrip("0").rstrip("."), money(p["price"]),
                money(p["value"]), pct(p.get("weight_pct"), False), tgt,
                money(p["gain"], True) if p["gain"] is not None else ""))
    if s["orders"]:
        c = s["order_counts"]
        out.append("")
        out.append("Orders: " + ", ".join("%d %s" % (v, k) for k, v in c.items() if k != "total"))
        for o in s["orders"]:
            out.append("  #%d %-38s %s" % (o["index"], o["plain"], o["label"]))
    if s["alerts"]:
        out.append("")
        out.append("Alerts: " + "; ".join("%s %s" % (r["text"], "RANG" if r["rang"] else "armed")
                                          for r in s["alerts"]))
    out.append("Monitors: " + "; ".join("%s %s%s" % (m["name"].lower(), ago(m["age_min"]),
                                                      " (stale)" if m["status"] == "stale" else "")
                                         for m in s["monitors"]))
    g = s["gate"]
    out.append("Gatekeeper: %s; today %d denied, %d asked, %d yes verified" % (
        "installed" if g["installed"] else "not installed", g["today"]["deny"], g["today"]["ask"], g["today"]["ok"]))
    t = s["talk"]
    if t["total"]:
        unread = ", ".join("%s %d" % (p["name"], p["unread"]) for p in t["people"] if p["unread"])
        last = t["recent"][0]
        out.append("Messages: %d total, %d open request%s%s; last %s -> %s \"%s\"" % (
            t["total"], t["open"], "" if t["open"] == 1 else "s", ("; unread " + unread) if unread else "",
            last["from"], last["to"], last["subject"]))
    for n in s["notes"]:
        out.append("note: " + n)
    out.append("Read-only. Education and tooling, not financial advice.")
    return "\n".join(out)


class Handler(http.server.BaseHTTPRequestHandler):
    base, every, me = ".", 5, None

    def _send(self, code, body, ctype):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, page(None, self.every), "text/html; charset=utf-8")
        elif path == "/api/state":
            try:
                self._send(200, json.dumps(collect(self.base, self.me)), "application/json")
            except Exception as e:  # noqa: BLE001
                self._send(500, json.dumps({"error": str(e)}), "application/json")
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):  # noqa: N802
        self._send(405, "read-only", "text/plain")

    do_PUT = do_DELETE = do_PATCH = do_POST

    def log_message(self, *args):
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(description="Your live dashboard for the trader pack. Read-only.")
    ap.add_argument("--base", default=".", help="the project folder that holds trader/ (default: here)")
    ap.add_argument("--as", dest="me", help="your name in the Claude mailbox (default desk)")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("serve", help="a live page on http://127.0.0.1:PORT")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--every", type=int, default=5, help="refresh every N seconds (default 5)")
    p.add_argument("--open", action="store_true", help="open it in the browser")
    p = sub.add_parser("build", help="write a snapshot HTML file")
    p.add_argument("--out", default=os.path.join("trader", "dashboard.html"))
    sub.add_parser("text", help="the dashboard as text")
    sub.add_parser("json", help="the state as JSON")
    a = ap.parse_args(argv)
    if a.cmd is None:
        ap.print_help()
        return 1
    if a.cmd == "json":
        print(json.dumps(collect(a.base, a.me), indent=2))
    elif a.cmd == "text":
        print(text(collect(a.base, a.me)))
    elif a.cmd == "build":
        out = a.out if os.path.isabs(a.out) else os.path.join(a.base, a.out)
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(page(collect(a.base, a.me)))
        print("Wrote %s (a snapshot; open it in any browser)." % out)
    else:
        Handler.base, Handler.every, Handler.me = os.path.abspath(a.base), max(1, a.every), a.me
        try:
            srv = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
        except OSError as e:
            print("dash.py: port %d is busy (%s); try --port %d" % (a.port, e, a.port + 1), file=sys.stderr)
            return 1
        url = "http://127.0.0.1:%d/" % a.port
        print("Your live dashboard: %s  (refreshes every %ds; Ctrl+C stops it)" % (url, Handler.every))
        if a.open:
            threading.Timer(0.5, lambda: webbrowser.open(url)).start()
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
