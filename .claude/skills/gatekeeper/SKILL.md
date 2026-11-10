---
name: gatekeeper
description: >-
  The Gatekeeper. A Claude Code hook that checks every risky tool call before
  it runs and can only make Claude stricter, never looser: it refuses an order
  unless trader-risk passed that exact order today and the user's yes is on
  record, checks that a recorded yes really is the user's own last message,
  refuses options, crypto, close-all and cancel-all, blocks forged risk or
  approval files, the paper-to-live switch, reading or leaking API keys,
  settings edits that loosen order permissions or remove the hook, and disk
  wipes, and asks before force-pushes or deleting trader files. Logs every
  decision for the dashboard. Use when the user says "install the gatekeeper",
  "lock it down", "guard my orders", "what did the gatekeeper block", "why was
  that denied", "gatekeeper status", or before connecting a broker.
argument-hint: "[status | log | test | install]"
---

# gatekeeper

The rest of this pack keeps its promises by asking Claude to follow the steps.
The gatekeeper makes the most important ones hold even if Claude doesn't: it
is a `PreToolUse` hook, so Claude Code runs it **before** a tool call, and the
harness, not Claude, enforces what it says.

It answers in one of three ways, never a fourth:

| answer | what happens |
| --- | --- |
| pass | nothing printed; Claude Code's own permission rules decide as usual |
| **ask** | Claude's permission card is shown, even where a rule or mode would allow it |
| **deny** | the call is refused and the reason goes back to Claude |

It never answers "allow". Installing it can only take permissions away.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/gate.py" status            # installed? rules on? today's count
python3 "${CLAUDE_SKILL_DIR}/gate.py" log               # today's asks, denies and verified yeses
python3 "${CLAUDE_SKILL_DIR}/gate.py" test              # the built-in cases, in a scratch folder
python3 "${CLAUDE_SKILL_DIR}/gate.py" check Bash '{"command": "cat .env"}'
python3 "${CLAUDE_SKILL_DIR}/gate.py" install --dry-run # show the settings it would write
python3 "${CLAUDE_SKILL_DIR}/gate.py" install           # only when the user asks
```

## Install (only when the user asks)

1. Run `gate.py test`. Every case must say `ok`.
2. Run `gate.py install --dry-run` and show the user the hook block it adds to
   `.claude/settings.json` (the same block is in `settings.example.json`).
   It keeps everything already in the file and saves the old file as `.bak`.
3. With the user's yes, run `gate.py install`. Claude Code loads it in the
   next session; opening `/hooks` once reloads it now.
4. Run `gate.py status`. It says where the hook is installed.

The hook runs `python3`. On Windows without `python3` on the PATH, change the
command in the settings to `python`. Two entries are added: one for every MCP
tool with `"onFailure": "block"` (if Python can't start, connector calls stop
instead of slipping through), and one for Bash, Read, Grep and the file-writing
tools.

Hooks are a Claude Code feature (the terminal, the desktop app's Code tab, the
IDE extensions). In a Claude Desktop chat there are no hooks: there the gate is
the connector's tool permission, "Needs approval" (see /trader-broker).

## The rules

| rule | answer | when |
| --- | --- | --- |
| order-gate | deny / ask | `place_stock_order` is denied unless the call is **exactly** an order in `trader/orders.json` that trader-risk passed today and that has a yes recorded today by trader-broker, not yet placed. When all of that holds it answers **ask**, so the Allow once / Deny card still shows, with the order and the user's yes on it |
| order-forbidden | deny | `place_option_order`, `place_crypto_order`, `close_all_positions`, `cancel_all_orders`, `exercise_options_position` |
| order-change | ask | any other broker tool that can place, cancel, close or change something (read-only `get_` / `list_` tools pass) |
| yes-is-real | deny | `ticket.py approve --reply "..."` when the reply is not the user's own last message in this chat, word for word. The gatekeeper reads it from the Claude Code transcript. If it can't read the transcript it answers ask instead |
| forged-state | deny | writing `trader/state/risk.json`, `trader/state/broker.json` or the gatekeeper's log any way but `check.py` and `ticket.py` |
| live-switch | deny | setting `"paper": false` in a trader config, or `ALPACA_PAPER_TRADE` to false |
| secret-file | deny | opening, writing or committing key files: `.env`, `claude_desktop_config.json`, `~/.aws/credentials`, `*.pem`, `*.key`, `id_rsa`, `.netrc`... (`.example` files are fine) |
| secret-env | deny | `echo $ALPACA_SECRET_KEY`, bare `printenv` / `env`, reading `/proc/*/environ` |
| secret-leak | deny | any call that would write or send something that looks like a real key (Anthropic, OpenAI, GitHub, AWS, Slack, Alpaca key ids, private keys, `password = ...`) |
| settings-guard | deny / ask | a settings edit that puts an order tool in `permissions.allow`, removes this hook, sets `disableAllHooks`, or switches to `bypassPermissions`: deny. Other settings edits by shell: ask |
| self-guard | ask | changes to the gatekeeper's own files or `trader/gatekeeper.json` |
| wipe | deny | `rm -rf /`, `~`, `.` or `*`, `mkfs`, `dd` onto a disk, a fork bomb |
| trader-delete | ask | deleting files under `trader/` (soft) |
| git-rewrite | ask | `git push --force`, `reset --hard`, `clean -f`, `branch -D` (soft) |
| pipe-to-shell | ask | `curl ... \| sh` and the like (soft) |

Only the three soft rules can be switched off, in `trader/gatekeeper.json`
(`gatekeeper.example.json` here). Lists in that file add to the built-in ones
(another order tool, another broker server, another key file); they never
remove one. Changing that file is itself an ask.

## Where it sits in the order flow

```
trader-budget / rebalance / tax  ->  trader/orders.json (proposals)
trader-risk   check.py           ->  PASS or BLOCK per order       (gate 1)
trader-broker ticket.py approve  ->  the user's yes, word for word (gate 2)
gatekeeper    yes-is-real        ->  that yes is in the user's own message
gatekeeper    order-gate         ->  the call is that exact order  (the hook)
Claude's card Allow once / Deny  ->  the user's second yes          (gate 3)
```

A message from another Claude (/claude-talks-to-claude), a scheduled task, a
file or a web page can't get through: the yes has to be the user's own last
message in this chat, and the card has to be clicked by the user.

## When something is denied

1. Stop. Tell the user, in plain words, what was refused and the gatekeeper's
   reason. `gate.py log` shows it again.
2. **Never look for another route to the same result**: not a different tool,
   not a script, not a renamed file, not a copy. A deny is the answer.
3. Say what the user can do themselves if they still want it: edit their own
   config by hand, run the command in their own terminal, or ask you to go
   back a step (run /trader-risk again, show the ticket again).
4. If the deny looks wrong (a false alarm), say so and show `gate.py check`
   with the call. Changing the gatekeeper is the user's decision.

An **ask** is not a problem: the card appears and the user decides.

## What it never does

- Never answers "allow", never approves an order, never records a yes.
- Never writes a secret into its log: every reason and summary is redacted.
- Never reads the network. It reads only the call, the trader files and the transcript.

## Limits

It is a seatbelt, not a vault. It reads commands as text, so a determined
script written to dodge it could. That is why it sits alongside the other
gates, not instead of them: Claude's own permission settings, the connector's
"Needs approval", paper trading by default, and the user's two yeses.

## Safety

- Education and tooling, not financial advice.
- Paper trading by default. Going live is the user's own decision, made by
  hand in their own config; the gatekeeper refuses to make that edit for them.
- Broker keys live in environment variables or the Claude Desktop config, never in the chat.
