# Agent scheduler

## Platforms

| Platform | Timer | Installer | Status |
|----------|-------|-----------|--------|
| macOS | launchd LaunchAgents | `install-launchd.sh`, `install-health-launchd.sh`, `install-tokencheck-launchd.sh` | Tested (in daily use) |
| Linux | systemd user timers; crontab fallback when `systemctl --user` is unavailable | `install-linux.sh` | Dry-run tested: the generated units and crontab lines are checked by `test_platform.py`; not yet run on a real Linux machine |
| Windows | Task Scheduler running `wsl.exe -e bash -lc …` inside WSL | `install-windows.ps1` | Dry-run tested: static checks only, `-Print` is executed only where PowerShell (`pwsh`) is installed; not yet run on a real Windows machine |

What differs by platform:

- **Sleep awareness is macOS only.** On macOS the tick skips DarkWake (`pmset`), holds `caffeinate -i` during a run, and the health check counts grace windows in *awake* time. On Linux and WSL there is no wake probe (systemd, cron and Task Scheduler do not fire while the machine is suspended, so a tick that runs counts as awake), no sleep lock during a run, and grace windows are wall-clock time; the health message says so.
- **Windows needs WSL.** The scheduler is bash and Python, so it runs inside a WSL distro. Install Claude Code, `python3` and `bash` **inside WSL** (a Claude Code installed on Windows itself is not used) and keep the workspace in the WSL file system (e.g. `/home/<you>/<workspace>`).
- `SCHED_PLATFORM=macos|linux|wsl` overrides platform detection (used by the tests).

The scheduler runs Claude Code agents unattended. You list tasks in `agents/scheduled-tasks.md` (a cron schedule, an agent, what to do). A cheap timer checks that register every 10 minutes and starts `claude -p` only when a task is actually due. Every run leaves a run record and sends you one short outcome message. A daily health check tells you when something stopped running.

## How a tick works

```
timer (every 10 min + at login: launchd / systemd / cron / Task Scheduler → WSL)
  └─ tick.sh
       ├─ gate.py        no Claude: which enabled tasks are due now?
       │                 · cron slot, with a 7-day catch-up for slots missed while asleep
       │                 · retry cap (3 failed attempts per slot, then held until the next slot)
       │                 · `Only if:` preconditions (e.g. an open handoff exists)
       │                 · `Created:` date (no catch-up of slots before the task existed)
       │   nothing due → one log line, exit
       ├─ wake check     macOS: DarkWake (lid closed, Power Nap) → defer, the next tick retries
       ├─ claude -p prompt.md   (macOS: under caffeinate; runs only the tasks the gate named)
       │    └─ each task ends with: runrecord.py report  → run record + notify.sh
       └─ runrecord.py postrun  a task that crashed or never reported is caught here:
                                failed attempt counted, ❌ alert at the cap, ⚠️ if no report

health.py      (timer, hourly at :30)  daily health check over automations.json + the register
tokencheck.py  (timer, hourly at :00)  weekly login/token check over credentials.json
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
| `install-linux.sh` | Linux: the timer and both checks as systemd user timers, or crontab lines. `--print` shows them without installing, `--uninstall` removes them. |
| `install-windows.ps1` | Windows: the timer and both checks as Task Scheduler tasks that run inside WSL. `-Print` / `-WhatIf` shows them, `-Uninstall` removes them. |
| `setup.sh` | Older entry point, kept for compatibility: runs `install-linux.sh --cron tick` (plain cron, any Unix). |
| `notify.env.example` | Telegram settings template. |
| `test_*.py` | Tests. Fixtures only: nothing is sent and no real state is touched. |

Created at runtime (keep them out of git): `logs/`, `state/`, `runs/`, `notify.env`, `automations.json`, `credentials.json`.

## Install

Requirements on every platform: `bash`, `python3` 3.9+ (stdlib only), `curl` for Telegram, and the `claude` CLI (or set `harness:` in `agents/CONVENTIONS.md` to `codex`, `gemini` or `opencode`). On Windows all of these live inside WSL.

Common steps:

1. Run `/agents:init` (it copies this folder to `agents/scheduler/` and creates `agents/scheduled-tasks.md`).
2. Optional, Telegram: create a bot with @BotFather, copy `notify.env.example` to `notify.env` and fill in `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Test it: `bash agents/scheduler/notify.sh "hello"`. Without it, every message goes to `agents/scheduler/logs/notify.log` and records say `telegram: logged`.
3. Add or enable a task (below), then check: `bash agents/scheduler/tick.sh --dry-run`.
4. Optional, health check: `cp automations.example.json automations.json` and edit it. Set the timer field for your platform on each timer job: `plist` (macOS), `systemd_timer` and/or `cron_marker` (Linux), `windows_task` (Windows). The installers name them `<workspace>-agent-scheduler`, `<workspace>-health-check`, `<workspace>-token-check` (`<workspace>` = the workspace folder name, lowercased, other characters turned into `-`).
5. Optional, token check: `cp credentials.example.json credentials.json` and edit it (paths to where secrets live, never the secrets).
6. Install the timer for your platform (below), or run `/agents:schedule install`.
7. Run the tests from this folder: `python3 -I test_gate.py`, `python3 -I test_runrecord.py`, `python3 -I test_health.py`, `python3 -I test_tokencheck.py`, `python3 -I test_platform.py`.

**macOS (launchd)**

```bash
bash agents/scheduler/install-launchd.sh              # the tick, every 10 min + at login
bash agents/scheduler/install-health-launchd.sh       # optional: health check (needs automations.json)
bash agents/scheduler/install-tokencheck-launchd.sh   # optional: token check (needs credentials.json)
```

Remove: `launchctl unload -w ~/Library/LaunchAgents/com.<workspace>.agent-scheduler.plist` (same pattern for `health-check` and `token-check`), then delete the plist.

**Linux (systemd user timers, cron fallback)**

```bash
bash agents/scheduler/install-linux.sh --print       # review the units and crontab lines first
bash agents/scheduler/install-linux.sh               # tick + health (if automations.json) + token (if credentials.json)
bash agents/scheduler/install-linux.sh --cron        # force cron even when systemd is available
bash agents/scheduler/install-linux.sh --uninstall   # remove units and crontab lines
```

- systemd: units go to `~/.config/systemd/user/`; `Persistent=true` runs a slot missed while suspended once, on resume. Timers run while you are logged in; to keep them running after logout: `loginctl enable-linger "$USER"`. Output: `journalctl --user -u <workspace>-agent-scheduler`.
- cron: one line per job tagged `# <workspace>-<job>`; the tick line is wrapped in `flock -n` (util-linux) so a long run never overlaps the next tick. cron skips slots while suspended; the next tick catches up.
- Check: `systemctl --user list-timers | grep <workspace>` or `crontab -l | grep <workspace>`.

**Windows (Task Scheduler + WSL)**

1. Install WSL (`wsl --install` in an admin PowerShell), open the distro, and install Claude Code, `python3` and `curl` **inside it**. Log in to Claude Code there once.
2. Put the workspace in the WSL file system and run `/agents:init` there. `chmod +x agents/scheduler/*.sh`.
3. From Windows PowerShell, in `\\wsl.localhost\<distro>\home\<you>\<workspace>\agents\scheduler`:

```powershell
powershell -ExecutionPolicy Bypass -File install-windows.ps1 -Print       # review the tasks first (-WhatIf does the same)
powershell -ExecutionPolicy Bypass -File install-windows.ps1              # tick + health/token when their registries exist
powershell -ExecutionPolicy Bypass -File install-windows.ps1 -Uninstall
```

Options: `-Distro <name>` (default: your default distro), `-SchedulerDir /home/<you>/<workspace>/agents/scheduler` (default: this folder via `wslpath`), `-Jobs tick,health,token`, `-Headless` (no console flash every 10 minutes; needs a recent conhost, untested). Tasks run only while you are logged on; a run missed while the PC slept starts on wake. Check: `schtasks /Query /TN <workspace>-agent-scheduler`; the tick log is `agents/scheduler/logs/cron.log` inside WSL.

Unattended runs start Claude with `--dangerously-skip-permissions`, because nobody is there to approve a prompt. The guardrails are the task text, `policies.md` and the autonomy ceiling. Read `policies.md` before enabling a task.

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

- **Schedule** is cron (`M H DoM Mon DoW`, local time). A slot missed while the machine slept runs on the next (full) wake, up to 7 days later.
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
- ❌ failing, with what happened, `🆕` or `since MM-DD`, and the `fix:` line from the registry. Codes: `missed`, `failed`, `retry-cap`, `output-stale`, `tick-stale`, `hung`, `plist` (macOS) / `timer` (Linux, Windows), `down`, `mcp-registered`, `mcp-credentials`, `mcp-reachable`.
- ⚠️ warning: a partial run, or a task that reported but did not update `Last run`.
- ⏳ pending: still inside its grace window, counted in **awake** minutes on macOS. A task due at 07:00 while the lid was closed until 11:00 is not "missed" until the Mac has been awake for the grace window. On Linux and Windows the window is wall-clock time.
- `✅ resolved:` failures from the last report that are now fixed.
- An unchanged failure is repeated every `resend_days` (3); a new or changed one is sent the same day.
- Separate, urgent: `🚨 Scheduler not ticking` arrives on any run when the timer has not ticked for 3 hours of awake time (wall-clock time on Linux and Windows).

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

- `tail -20 agents/scheduler/logs/cron.log`: one `gate:` line per tick. `deferred: not fully awake` is normal on macOS with the lid closed. `CLI not found` means the harness is not on the timer's PATH (tick.sh also looks in `~/.local/bin`, `~/.claude/bin`, `~/.npm-global/bin`, `/usr/local/bin`, `/opt/homebrew/bin` and nvm); on Windows, Claude Code is probably installed on Windows instead of inside WSL.
- No `gate:` lines at all: the timer is not firing. macOS `launchctl list | grep agent-scheduler`; Linux `systemctl --user list-timers` / `journalctl --user -u <workspace>-agent-scheduler` or `crontab -l`; Windows Task Scheduler → the task's History tab, or `schtasks /Query /TN <workspace>-agent-scheduler /V /FO LIST`.
- A task held by the retry cap: read its newest run record, fix the cause, then delete its key from `agents/scheduler/state/attempts.json` (or wait for the next slot).
- Manual run that skips the wake check: `TICK_SKIP_WAKE_CHECK=1 bash agents/scheduler/tick.sh`.
