---
description: Manage the workspace's unattended scheduled tasks — list, add, remove, enable, disable a task in agents/scheduled-tasks.md; check the timer and last runs with status; install the timer (launchd on macOS, systemd user timer or cron on Linux, Task Scheduler + WSL on Windows). Use /agents:schedule, /agents:schedule add, /agents:schedule status.
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(date), Bash(ls), Bash(tail), Bash(launchctl list), Bash(crontab -l), Bash(bash agents/scheduler/tick.sh --dry-run), Bash(bash agents/scheduler/install-launchd.sh), Bash(bash agents/scheduler/install-linux.sh), Bash(bash agents/scheduler/install-linux.sh --print), Bash(systemctl --user list-timers), Bash(uname), AskUserQuestion
argument-hint: [list | add | remove <id> | enable <id> | disable <id> | status | install]
---

# /agents:schedule — Scheduled Tasks

You manage the task register at `agents/scheduled-tasks.md` and the timer that runs it. You never run a task yourself and never change anything but the register and the timer.

## Setup check

Glob for `agents/scheduled-tasks.md` and `agents/scheduler/tick.sh`. If either is missing, say `Scheduler not set up. Run /agents:init (it backfills the scheduler folder).` and stop.

Read the register. Each task is a `### <id>` block with these fields, one per line: `Schedule` (cron in backticks + human note), `Agent`, `Execution` (`direct` | `agent`), `Autonomy ceiling` (L3–L5), `Task`, `Enabled`, `Last run`, `Created`, and optional `Note`/`Updated` lines.

Route on the first word of `$ARGUMENTS` (empty = `list`).

## list

Table, one row per task: `| Id | Agent | Schedule | Mode | Ceiling | Enabled | Last run |`. Below it one line: `Timer: <installed as <label> | not installed>` (macOS: `launchctl list | grep agent-scheduler`; Linux: `systemctl --user list-timers` then `crontab -l`, look for `agent-scheduler`; WSL: say `Windows timer: check with schtasks /Query /TN <workspace>-agent-scheduler from Windows`). End with `Add: /agents:schedule add · Status: /agents:schedule status`.

## add

Ask, in one AskUserQuestion call, for what is not obvious from `$ARGUMENTS`:
1. **Agent** — must be an existing active agent (glob `agents/*/context.md`).
2. **When** — plain words ("every Friday 10:00", "1st of the month 09:00"). Convert to a 5-field cron. Confirm the conversion back in words.
3. **Mode** — `direct` (mechanical, no judgment, reads only named files) or `agent` (loads the agent's trimmed tick context).
4. **What** — the task text. Push for precision: every file to read, every channel or record ID, and what must NOT be touched. Ticks cannot ask questions.

Then set the ceiling: `direct` → L4; `agent` → L3 unless the principal asks for L4. Never L2/L1 (the scheduler skips those).

Read `agents/scheduler/policies.md` and check the task against it (no email sends, no writes to shared records without an explicit ID, no messages outside the named channels). Say if something in the task text conflicts and get a fix before writing.

Append the block to `## Tasks` with `Enabled: true`, `Last run: never`, `Created: <today>`. Id is a lowercase-hyphen slug. Remove the shipped `example-task` block if it is still there and still disabled.

If the agent has no `memory/scheduled/inbox.md`, create it with a one-line header (`# Scheduled-run inbox — <Agent>`) so ticks have somewhere to write.

Finish: show the block, then `Timer: <installed | not installed — run /agents:schedule install>`. Say that the register change is uncommitted and the next interactive session with the agent commits it.

## remove <id> / enable <id> / disable <id>

Find the block. `remove` deletes it (show it first, one confirmation). `enable`/`disable` flip the `Enabled` field. Say what changed and that it is uncommitted.

## status

Show:
- Timer: label and whether loaded (`launchctl list` / `crontab -l`).
- `bash agents/scheduler/tick.sh --dry-run` → what is due right now.
- Last 5 gate lines from `agents/scheduler/logs/cron.log` (`tail`).
- The newest `## ` entry in the newest `agents/scheduler/logs/YYYY-MM.md`.
- For each agent with `memory/scheduled/inbox.md`: count of `UNPROCESSED` entries. If any, say `Drain: /agents:start <Agent>`.

## install

`uname` (and, on Linux, `/proc/version` containing `microsoft` = WSL):
- macOS: run `bash agents/scheduler/install-launchd.sh`. Set `scheduler: launchd`. Say: `Timer ticks every 10 minutes and at login. Claude runs only when a task is due and the Mac is fully awake. Check: /agents:schedule status. Optional: install-health-launchd.sh (daily health check) and install-tokencheck-launchd.sh (weekly token check), see agents/scheduler/README.md.`
- Linux: run `bash agents/scheduler/install-linux.sh --print` first and show it, then `bash agents/scheduler/install-linux.sh`. It uses systemd user timers, or crontab lines when `systemctl --user` is unavailable, and also installs the health/token checks when `automations.json` / `credentials.json` exist. Set `scheduler: systemd` or `cron` (the script prints which). Say: `Timer ticks every 10 minutes and after login. Check: /agents:schedule status. Timers stop at logout unless you run: loginctl enable-linger "$USER".`
- WSL (Windows): do not install from inside WSL. Tell the principal to run, from Windows PowerShell in the `agents\scheduler` folder: `powershell -ExecutionPolicy Bypass -File install-windows.ps1 -Print`, then the same without `-Print`. Claude Code must be installed inside WSL. Set `scheduler: windows-task` once they confirm.
Show the script's output. Write the `scheduler:` value in the frontmatter of `agents/CONVENTIONS.md`.

## Rules

- Do not commit.
- Do not edit `agents/scheduler/prompt.md` or `policies.md`; those come from the plugin.
- Do not run a task by hand. To test one, tell the principal to lower nothing and use `--dry-run` plus wait for the timer, or run `bash agents/scheduler/tick.sh` themselves.
