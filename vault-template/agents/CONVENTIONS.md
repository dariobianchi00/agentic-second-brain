---
extends: plugin
principal: <Your first name>
naming: Greek mythology
naming-description: names from Greek mythology — pick for archetype fit
naming-examples: Atlas — carries the load; Hermes — messenger; Athena — strategy; Hephaestus — builder
reserved: [Atlas]
ticket-column: Ticket
inbound: none
scheduler: launchd
gap-notice: 2h
harness: claude
layout: multi-domain
vcs: none
firewalled-scope: Personal
shared-scopes: [Network, Knowledge]
work-mode: on
work-mode-flag: Instructions/.work_mode
commons: on
chief-of-staff: {Work: Atlas}
framework-owner: Atlas
---

# Agent Conventions — workspace

This file carries **workspace facts only**. Every rule (scope firewall, Work Mode, kickoff, commons, handoffs, retro, scheduler limits) lives in the plugin master and is switched on by the frontmatter above. On conflict this file wins.

## 1. Scopes

`agents/<scope>/<name>/`. **Work** (your job) · **Personal** (career, finance, health, family — the firewalled scope) · **Network** and **Knowledge** (shared reads). Work and Personal are never combined.

**Ask when off-lane:** if an instruction would take an agent outside its lane, or says "the file" without naming it, the agent asks in one line before acting. You may have typed into the wrong pane.

## 2. Session end without git

`vcs: none` — session end logs to `/CHANGELOG.md` with `[<Name>]`.

## 3. Commons

`agents/_commons/<scope>/` — `HANDOFFS.md` (agent-to-agent work requests), `RETRO.md` (weekly retro by the chief of staff).

## 4. Scheduler (macOS only)

`agents/scheduler/` (launchd). Every scheduled run writes a run record and, if configured, a Telegram message. No new automation without an entry in `scheduler/automations.json`.

## 5. Reserved names

| Name | Agent | Scope | Status |
|---|---|---|---|
| **Atlas** | Chief of Staff (example) | Work | Active |
