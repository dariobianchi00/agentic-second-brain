# Agent scheduler

> **macOS only (launchd).** The timer, the wake check (`pmset`), `caffeinate` and the sleep-aware health check all rely on macOS. `setup.sh` installs a plain cron entry for other Unix machines, but there the wake check is skipped and the health/token checks are not supported.

The scheduler runs Claude Code agents unattended. You list tasks in `agents/scheduled-tasks.md` (a cron schedule, an agent, what to do). A cheap timer checks that register every 10 minutes and starts `claude -p` only when a task is actually due. Every run leaves a run record and sends you one short outcome message. A daily health check tells you when something stopped running.

## How a tick works

```
launchd (every 10 min + at login)
  └─ tick.sh
       ├─ gate.py        no Claude: which enabled tasks are due now?
       │                 · cron slot, with a 7-day catch-up for slots missed while asleep
       │                 · retry cap (3 failed attempts per slot, then held until the next slot)
       │                 · `Only if:` preconditions (e.g. an open handoff exists)
       │                 · `Created:` date (no catch-up of slots before the task existed)
       │   nothing due → one log line, exit
       ├─ wake check     DarkWake (lid closed, Power Nap) → defer, the next tick retries
       ├─ claude -p prompt.md   (under caffeinate; runs only the tasks the gate named)
       │    └─ each task ends with: runrecord.py report  → run record + notify.sh
       └─ runrecord.py postrun  a task that crashed or never reported is caught here:
                                failed attempt counted, ❌ alert at the cap, ⚠️ if no report

health.py      (launchd, hourly at :30)  daily health check over automations.json + the register
tokencheck.py  (launchd, hourly at :00)  weekly login/token check over credentials.json
notify.sh      Telegram sender used by all of the above; logs instead when Telegram is not set up
```

## Files

| File | What it is |
|------|------------|
| `tick.sh` | Entrypoint the timer calls. `--dry-run` prints what is due and the wake state; `--wake-check` prints only the wake probe. |
| `gate.py` | Decides what is due. Pure Python, no Claude, no network. |
| `prompt.md` | What the headless Claude session follows on each run. |
| `policies.md` | Safety rules every run obeys (no sends outside the named channels, no destructive actions, tool-call caps, autonomy ceiling). |
| `scheduled-tasks.md` | Register template. `/agents:init` copies it to `agents/scheduled-tasks.md`. |
| `runrecord.py` | Writes run records (`runs/<scope>/YYYY-MM/<date>_<HHMM>_<task>.md`) and sends outcomes; `postrun` does the retry accounting. |
| `notify.sh` | Sends one plain-text message to your own Telegram chat, or appends it to `logs/notify.log`. |
| `health.py` | Daily health check. Registry: `automations.json` (start from `automations.example.json`). |
| `tokencheck.py` | Weekly check that logins and API tokens still work. Registry: `credentials.json` (start from `credentials.example.json`). |
| `install-launchd.sh` | Installs the scheduler timer (macOS). |
| `install-health-launchd.sh`, `install-tokencheck-launchd.sh` | Install the two checks (macOS). `--print-plist` shows the plist without installing. |
| `setup.sh` | Cron alternative for non-macOS machines. |
| `notify.env.example` | Telegram settings template. |
| `test_*.py` | Tests. Fixtures only: nothing is sent and no real state is touched. |

Created at runtime (keep them out of git): `logs/`, `state/`, `runs/`, `notify.env`, `automations.json`, `credentials.json`.

## Install

Requirements: macOS, `python3` (the checks use `/usr/bin/python3`, stdlib only), the `claude` CLI on your PATH (or set `harness:` in `agents/CONVENTIONS.md` to `codex`, `gemini` or `opencode`).

1. Run `/agents:init` (it copies this folder to `agents/scheduler/` and creates `agents/scheduled-tasks.md`).
2. Optional, Telegram: create a bot with @BotFather, copy `notify.env.example` to `notify.env` and fill in `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Test it: `bash agents/scheduler/notify.sh "hello"`. Without it, every message goes to `agents/scheduler/logs/notify.log` and records say `telegram: logged`.
3. Add or enable a task (below), then check: `bash agents/scheduler/tick.sh --dry-run`.
4. Install the timer: `bash agents/scheduler/install-launchd.sh` (or `/agents:schedule install`).
5. Optional, health check: `cp automations.example.json automations.json`, edit it, then `bash agents/scheduler/install-health-launchd.sh`.
6. Optional, token check: `cp credentials.example.json credentials.json`, edit it (paths to where secrets live, never the secrets), then `bash agents/scheduler/install-tokencheck-launchd.sh`.
7. Run the tests from this folder: `python3 -I test_gate.py`, `python3 -I test_runrecord.py`, `python3 -I test_health.py`, `python3 -I test_tokencheck.py`.

Unattended runs start Claude with `--dangerously-skip-permissions`, because nobody is there to approve a prompt. The guardrails are the task text, `policies.md` and the autonomy ceiling. Read `policies.md` before enabling a task.

To remove the timer: `launchctl unload -w ~/Library/LaunchAgents/com.<workspace>.agent-scheduler.plist` (same pattern for `health-check` and `token-check`).

## Add a task

Use `/agents:schedule add`, or add a block to `agents/scheduled-tasks.md`:

```markdown
### inbox-triage
- **Schedule:** `30 7 * * 1-5`
- **Agent:** Assistant
- **Execution:** agent
- **Autonomy ceiling:** L3
- **Task:** <what to read, what to write where, what must not be touched>
- **Enabled:** true
- **Last run:** never
- **Created:** 2026-01-05
```

- **Schedule** is cron (`M H DoM Mon DoW`, local time). A slot missed while the Mac slept runs on the next full wake, up to 7 days later.
- **Execution:** `direct` for mechanical tasks (no agent context, cheap), `agent` for tasks that need judgment (loads the agent's trimmed context).
- **Autonomy ceiling:** L3 drafts go to the agent's `memory/scheduled/inbox.md` and to you; L4/L5 act and log. L1/L2 are never scheduled.
- **Only if** (optional): `` `open-handoff <Agent>` `` runs the task only while an open handoff in `agents/_commons/` is addressed to that agent and not yet answered.
- End the task text with the outcome report (`prompt.md` § Outcome report), or let the standard shape apply.
- To have the health check verify an output file, add the task id under `scheduler_tasks.overrides` in `automations.json` with its `outputs`.

Then `bash agents/scheduler/tick.sh --dry-run` shows whether it is due now.

## Read the health check

One message a day, only when something changed; Mondays always, as proof of life:

```
🩺 Health check — 2026-01-05 Mon · 5/7 green · 1 failing · 1 warning(s)
❌ inbox-triage — missed: due Mon 07:30, not run after 2.1h awake 🆕
   fix: Open the lid ~10 min; check `tail -20 agents/scheduler/logs/cron.log` …
⚠️ weekly-review — last run (Fri 16:02) partial → runs/general/2026-01/…
⏳ rss-digest-fetch — slot Mon 07:00: 12/30 awake min elapsed
✅ resolved: mcp:notes-search
```

- Header: green items / items checked, then counts of failing, warnings and pending.
- ❌ failing, with what happened, `🆕` or `since MM-DD`, and the `fix:` line from the registry. Codes: `missed`, `failed`, `retry-cap`, `output-stale`, `tick-stale`, `hung`, `plist`, `down`, `mcp-registered`, `mcp-credentials`, `mcp-reachable`.
- ⚠️ warning: a partial run, or a task that reported but did not update `Last run`.
- ⏳ pending: still inside its grace window, counted in **awake** minutes. A task due at 07:00 while the lid was closed until 11:00 is not "missed" until the Mac has been awake for the grace window.
- `✅ resolved:` failures from the last report that are now fixed.
- An unchanged failure is repeated every `resend_days` (3); a new or changed one is sent the same day.
- Separate, urgent: `🚨 Scheduler not ticking` arrives on any run when the timer has not ticked for 3 hours of awake time.

Run it by hand: `python3 agents/scheduler/health.py --dry-run --force-daily` prints every finding and the message without sending or saving anything.

Every message also lands as a run record under `runs/<scope>/`. The scope is the folder the agent lives in (`agents/<scope>/<agent>/`; single-domain workspaces use `general`). A record only holds its own scope's items, so a private scope never leaks into another scope's record. An unknown agent goes to the `firewalled-scope` named in `agents/CONVENTIONS.md`.

## Read the token check

```
🔑 Token check — 2026-01-05 Mon · 2/4 ok · 1 dead · 1 expiring
❌ example-api — HTTP 401 — token rejected
   ↳ Create a new token in the example.com settings and paste it into ~/.config/example-api/.env
⚠️ google-mail — expires Thu 01-08 09:00 (before the next weekly check)
   ↳ Re-run the mail server's auth command (see its README)
✅ github-cli
```

❌ dead, ⚠️ expiring before next week's run, ❓ unknown (network or a check that could not run), each with the exact re-login command from `credentials.json`. Run it by hand: `python3 agents/scheduler/tokencheck.py --dry-run`.

## Troubleshooting

- `tail -20 agents/scheduler/logs/cron.log`: one `gate:` line per tick. `deferred: not fully awake` is normal with the lid closed. `CLI not found` means the harness is not on launchd's PATH.
- A task held by the retry cap: read its newest run record, fix the cause, then delete its key from `agents/scheduler/state/attempts.json` (or wait for the next slot).
- Manual run that skips the wake check: `TICK_SKIP_WAKE_CHECK=1 bash agents/scheduler/tick.sh`.
