---
name: your-live-dashboard
description: >-
  Your Live Dashboard. One page with everything the trader pack knows, updating
  itself every few seconds: account value and today's change, unrealized gain,
  cash against the buffer, every position against its target with the drift
  band, each proposed order and where it stands (risk check, your yes, placed,
  blocked and why), price alerts that rang, how fresh prices, news, Pelosi
  filings and the risk check are, what the gatekeeper denied or asked, and what
  the Claudes said to each other. Runs a read-only page on this computer, or
  writes a snapshot file, or prints the same as text in the chat. Also starts
  the multi-agent observability dashboard, where hooks stream what every
  Claude agent and subagent is doing in real time. Use when the user says
  "show my dashboard", "open the dashboard", "how am I doing", "where do my
  orders stand", "give me the overview", "status of everything", "morning
  summary", "what's going on with my portfolio", "show what the agents are
  doing", "start the observability server", or "open the agent dashboard".
argument-hint: "[serve | build | text]"
---

# your-live-dashboard

The other skills each write a file. This one reads all of them and puts them
on one page, so the user sees the whole picture at a glance and watches it
change as the other skills (or another Claude) work.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/dash.py" text                 # the dashboard as text, for the chat
python3 "${CLAUDE_SKILL_DIR}/dash.py" serve                # live page: http://127.0.0.1:8765
python3 "${CLAUDE_SKILL_DIR}/dash.py" serve --port 9000 --every 10 --open
python3 "${CLAUDE_SKILL_DIR}/dash.py" build                # trader/dashboard.html, a snapshot
python3 "${CLAUDE_SKILL_DIR}/dash.py" json                 # the state behind the page
```

Run it from the project folder that holds `trader/` (or pass `--base PATH`).

## Three ways to show it

| way | when | how it updates |
| --- | --- | --- |
| `text` | any chat; the quickest answer to "how am I doing?" | run it again |
| `serve` | the user is at their own computer | the page asks for fresh data every 5 seconds (`--every`); the pill in the corner says "Live, updated 3s ago", or "Offline" if the server stopped |
| `build` | to keep, send or open somewhere else | a snapshot; the pill says "Snapshot" and the time. Build it again for new numbers |

`serve` keeps running until it is stopped (Ctrl+C), so start it in the
background if your Claude can, and give the user the address. It listens
only on this computer (127.0.0.1), answers only GET, and has no buttons that
do anything: it cannot place, approve or change a thing. If the port is busy,
it says so; use `--port`.

## What is on the page

| panel | reads | from |
| --- | --- | --- |
| header | paper or LIVE account, NYSE open or closed and the next open, how old the prices are | `trader/config.json`, trader-alerts' clock, `trader/prices.json` |
| tiles | account value and today's change (from the previous close), unrealized gain on cost, cash against the buffer, orders placed today | `trader/portfolio.json`, `trader/prices.json`, `trader/config.json` |
| allocation vs target | each stock's share of the account as a bar, its target as a tick, the drift band shaded, the drift in points; outside the band is flagged | trader-rebalance's own drift math on `trader/targets.json` |
| positions | shares, price, today, value, gain, weight, cash and the total | the same |
| orders | every proposal on a four-step track: proposed, risk PASS or Blocked (with the reasons), your yes, placed | trader-broker's own status for `trader/orders.json`, `trader/state/risk.json`, `trader/state/broker.json` |
| alerts and monitors | each price alert, armed or rang and when; how long ago prices, alerts, news, Pelosi filings and the risk check last ran, with stale ones flagged | `trader/alerts.json`, `trader/state/*.json` |
| gatekeeper | installed or not; today's denies, asks and verified yeses; the latest decisions with their reasons | `trader/state/gatekeeper.jsonl`, `.claude/settings*.json` |
| Claude to Claude | who is talking, unread counts, open requests, the latest messages | `trader/talk/` |

A panel with nothing to show says which skill fills it (for example "No
proposed orders. /trader-budget"). If a sibling skill is missing, that panel
says so instead of guessing.

## Steps

1. If the user wants fresh prices first, run trader-alerts:
   `alerts.py quote --holdings --write`. The dashboard never fetches anything.
2. For a question in the chat ("how am I doing?"), run `text` and answer from
   it in plain words: the account, today's change, anything that needs the
   user (an order waiting for their yes, a stock outside its band, an alert
   that rang, a monitor gone stale, unread messages).
3. For "show me the dashboard", run `serve` (in the background) and give the
   address, or `build` and give the file path when they want something to keep.
4. Never present the numbers as advice. A stock outside its band means
   /trader-rebalance has something to propose; an order waiting means
   /trader-broker shows the ticket and asks.

## Example: the reel

```
YOUR LIVE DASHBOARD  2026-11-10 10:44  PAPER account  NYSE open, closes 16:00 ET
Account $5,378.39   today -$21.59 (-0.40%)   cash $900.00 (buffer $537.84)   unrealized -$21.61 (-0.48%)

Positions  (band 5 pts)
  AAPL       3.6628 sh     $345.10    $1,264.03   23.5%  target 25.0% (-1.5 pts)  +$14.03
  BAC       11.1193 sh      $49.80      $553.74   10.3%  target 12.0% (-1.7 pts)  -$46.26
  ...
Orders: 1 placed, 1 approved, 1 blocked
  #3 BUY $400 of AAPL ... BLOCKED by trader-risk: cash: leaves $290 cash, under your 10% buffer
Alerts: BAC stop at $50 RANG; AAPL at or above $350 armed; ...
Monitors: prices 3m ago; price alerts 4m ago; news 2h ago; pelosi filings 3d ago (stale); risk check just now
Gatekeeper: installed; today 2 denied, 2 asked, 1 yes verified
Messages: 3 total, 1 open request; unread desk 2; last monitor -> desk "BAC hit your stop $50"
```

Read out loud: the account is down 40 cents in a hundred today, mostly BAC,
which hit the user's $50 stop. Nothing was sold. Everything is inside the
band. The AAPL top-up was blocked by the cash buffer and the 25% cap, the
GOOGL buy is waiting for the Allow once card, and the Pelosi check is three
days old.

## Agent activity: the multi-agent observability dashboard

The page above shows the portfolio. To watch the *agents* (every tool call,
prompt, subagent start and stop, as it happens), this project sends Claude
Code hook events to the dashboard from
github.com/disler/claude-code-hooks-multi-agent-observability.

What is installed in this project:

- `.claude/settings.json`: all 12 hook events (SessionStart, SessionEnd,
  UserPromptSubmit, PreToolUse, PostToolUse, PostToolUseFailure,
  PermissionRequest, Notification, SubagentStart, SubagentStop, Stop,
  PreCompact) run `.claude/hooks/send_event.py --source-app background-logo`.
  They are `async`, so they never slow Claude down, and they always exit 0,
  so nothing breaks when the dashboard isn't running (the event is dropped).
- `.claude/hooks/send_event.py` and `utils/summarizer.py`, `utils/llm/anth.py`
  from that repository; `utils/model_extractor.py` is a stand-in written here
  because upstream references it but doesn't ship it.

To start the dashboard on the user's computer (needs Bun and uv):

```bash
git clone https://github.com/disler/claude-code-hooks-multi-agent-observability
cd claude-code-hooks-multi-agent-observability
(cd apps/server && bun install) && (cd apps/client && bun install)
./scripts/start-system.sh        # server on :4000, dashboard on :5173 (or: just start)
```

Then open http://localhost:5173 and use Claude Code in this project; events
appear within a second. Each session gets its own color and swim lane; the
filter panel narrows by session or event type. `./scripts/reset-system.sh`
stops it.

Notes to tell the user when it matters:

- Events stay on their computer: the hooks post to `localhost:4000`, which
  keeps them in a SQLite file (`apps/server/events.db`). The Stop event
  includes the chat transcript.
- `--summarize` asks Claude Haiku for a one-line summary of each prompt and
  tool call, **only if** `ANTHROPIC_API_KEY` is set where Claude Code runs
  (or in a `.env` in the project). That is a small paid API call per event,
  sending up to 1,000 characters of it. Remove `--summarize` from
  `.claude/settings.json` to turn it off.
- On Windows, the hook commands use `$CLAUDE_PROJECT_DIR` and `uv`; run Claude
  Code from Git Bash or WSL, or adjust the commands.

## Safety

- Education and tooling, not financial advice. Prices are delayed quotes; the broker's price is the one that fills.
- Read-only: it never places, approves, edits or deletes anything, and the live page listens only on this computer.
- Paper trading by default. A LIVE account shows a red "LIVE account, real money" badge on every view.
