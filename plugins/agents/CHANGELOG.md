# Changelog — agents plugin

## 1.0.0 — first public release

Based on [Norman Noble's agent-framework](https://github.com/normannoble/agent-framework) v1.10.2 (MIT). Changes in this branch:

1. **Scope firewall and multi-domain layout** — agents grouped by scope; a firewalled scope (e.g. Personal) is never read by agents of other scopes.
2. **Commons** — shared `HANDOFFS.md` (agent-to-agent work requests with a status lifecycle) and a weekly `RETRO.md` per scope.
3. **No-git session end** (`vcs: none`) for vaults that live in a synced folder instead of a repo.
4. **Scheduler toolkit (macOS launchd; Linux systemd/cron and Windows via WSL, dry-run tested)** — cheap gate (no model call unless a task is due), retry cap, `Only if:` preconditions (e.g. run only when a handoff is open), `Created:` dates, run records, optional Telegram reports, daily health check, token-expiry checks.
5. **Hooks** — gap notice after long idle; live inbox notice when an unattended run writes to an agent's inbox mid-session; a "⏳ NEEDS <you>" marker that lights up the Herdr sidebar when an agent is waiting on you.
6. **Kickoff** — a fixed emoji legend for the session-open brief.
7. Removed: the Go installer CLI (install with the plugin marketplace instead).
