---
title: Scheduled Tasks
type: operational
owner: agents
updated: YYYY-MM-DD
---

# Scheduled Tasks

Task register for automated agent execution. Read by the gate (`agents/scheduler/gate.py`, no Claude) on every tick and by the scheduler prompt (`agents/scheduler/prompt.md`) when something is due. Agents add and modify tasks during their interactive sessions; ticks only update `Last run`.

See `agents/scheduler/policies.md` for the safety constraints that apply to every scheduled execution, and `agents/scheduler/README.md` for how the scheduler works.

## Task fields

| Field | Required | Meaning |
|-------|----------|---------|
| `### <task-id>` | yes | Heading = the task id (lowercase, hyphens). Used in logs, run records and alerts. |
| **Schedule** | yes | Cron expression in backticks, `M H DoM Mon DoW`, local time. A slot missed while the Mac slept is caught up within 7 days. |
| **Agent** | yes | The agent that runs it. Its folder decides the run-record scope. |
| **Execution** | yes | `direct` or `agent` (below). |
| **Autonomy ceiling** | yes | L3–L5. L1/L2 tasks are never scheduled. |
| **Task** | yes | Exactly what to do: every file to read, every channel or record id, what must NOT be touched. |
| **Only if** | no | A precondition checked by the gate before Claude starts, e.g. `` `open-handoff <Agent>` `` = run only while an open handoff is addressed to that agent. Unknown condition = not due. |
| **Enabled** | yes | `true` or `false` (a trailing note is allowed: `false (waiting for review)`). |
| **Last run** | yes | `never`, or the ISO 8601 timestamp written by the tick. |
| **Created** | yes | `YYYY-MM-DD`. Slots before this day are not caught up. |

## Execution Modes

- **`direct`** — the scheduler reads the task description and referenced files and executes mechanically. No agent context loaded. Low token cost. For templated, repeatable tasks that need no judgment.
- **`agent`** — the scheduler loads the agent's trimmed tick context (see `agents/CONVENTIONS.md` § Session Types) and executes with judgment. Full context load. For tasks that need interpretation or multi-step reasoning.

## Tasks

The two tasks below are examples. Both are disabled; rename the agent, rewrite the task text for your workspace, then set `Enabled: true`.

### inbox-triage
- **Schedule:** `30 7 * * 1-5` (weekdays 07:30 local)
- **Agent:** <Name>
- **Execution:** agent
- **Autonomy ceiling:** L3
- **Task:** Read the unread messages in `Inbox/` (files added since `Last run`). For each, write one line — sender, subject, the ask, a suggested next step — into a new `UNPROCESSED` entry in `agents/<Name>/memory/scheduled/inbox.md`. Do not move, rename or delete anything in `Inbox/`. Do not reply to anyone. End with the outcome report (`prompt.md` § Outcome report): count of items and the two most urgent.
- **Enabled:** false
- **Last run:** never
- **Created:** YYYY-MM-DD

### weekly-review
- **Schedule:** `0 16 * * 5` (Friday 16:00 local)
- **Agent:** <Name>
- **Execution:** direct
- **Autonomy ceiling:** L4
- **Task:** Read `agents/<Name>/actions.md`. List every open item whose due date is in the next 7 days or already passed. Write the list to `agents/<Name>/memory/scheduled/inbox.md` as one `UNPROCESSED` entry headed `Weekly review — YYYY-MM-DD`. Do not edit `actions.md`. End with the outcome report: overdue count, due-next-week count.
- **Enabled:** false
- **Last run:** never
- **Created:** YYYY-MM-DD
