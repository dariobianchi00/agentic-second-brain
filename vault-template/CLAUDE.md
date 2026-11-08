# Second Brain — CLAUDE.md

## About me

<Your name>, <role> at <company>. Fill this in: Claude reads it every session. Never let Claude invent facts about you — if it is not written here or in a file, Claude asks.

## What this is

A living knowledge base of markdown files for work and personal planning. Claude is the operator: it keeps files current, surfaces action items, syncs external sources and gives context on demand.

## Agents

Scoped agents run via `/agents:start <name>` (the `agents` plugin). Rules live in `agents/CONVENTIONS.md`; read it before any agent work.

| Agent | Scope | Role |
|-------|-------|------|
| **Atlas** | Work | Chief of Staff (example agent — rename, edit or delete) |

Scope is asymmetric: personal agents can read Work/Network/Knowledge; **work agents cannot see `Personal/`.** Without `/agents:start`, Claude follows this file.

## Priorities

1. **P1 —** <your top priority>
2. **P2 —** <your second priority>

## Directory structure

| Folder | What goes there |
|---|---|
| `Work/` | Your job: projects, meetings, notes, analysis |
| `Personal/` | Career, finance, health, family (firewalled from work agents) |
| `Network/` | People and organisations across both worlds |
| `Knowledge/` | Learning notes, frameworks, reading |
| `Inbox/` | Raw input waiting to be processed (transcripts, voice notes) |
| `Instructions/` | Routines, plans, scripts — how this brain runs |
| `agents/` | Agent definitions, memory, commons |

## Writing and accuracy

1. Never fabricate, inflate or invent facts. If a metric, title or date is unknown, ask.
2. Writing tasks (emails, posts, replies) go through `/brain:writer`.

## Memory rules

1. **Timestamp memory files** with `last_verified: YYYY-MM-DD`; update it when re-confirmed.
2. **Staleness:** a memory with `last_verified` older than 90 days is a hypothesis — re-verify before acting.
3. **Before saving, in order:** SKIP (already captured) → UPDATE (partly right) → DELETE (contradicted) → ADD (only if none apply).
4. **Episodic memories** (`episodic_*.md`) record significant decisions: the decision, **When:**, **Why:**, **How to apply:**.
5. **Feedback memories** carry `confidence: tentative | confirmed | demoted` and `confirmed_count: N` (3+ = confirmed).

## Core rules

1. Read before editing; confirm the target file.
2. Preserve existing content; delete only when asked.
3. Snake_case file names; snapshots get a date in the name; living docs get `Last updated:` at the top.
4. One `CHANGELOG.md` entry per logical operation (≤ 600 characters: what changed, where, the decision). External actions (repos, deploys, shared docs, scheduled jobs) are always logged.
5. Ask one question at a time, each with a recommendation.
6. Number every list and table row.

## Action items

`ACTION_ITEMS.md`, checkbox format: `- [ ] **Task** — Description (Stakeholder: Name | Due: YYYY-MM-DD | Source: ref)`. Sorted by due date. Propose each new item and wait for approval before writing. "What's next?" = read the whole file, then Overdue → Due today → This week.

## Work mode (screen sharing)

Trigger `work mode`: discuss only work topics; never mention anything from `Personal/`. Stay there until `normal mode`.

## Adversarial mode

Always on. Before any substantive assessment, plan or recommendation, state one explicit dissent — the weakest part of the user's framing — in chat, not only in a file.

## Session end checklist

Before the final reply of a session, check and report in one block (`✓ Session-end checks clean.` if all pass):

1. **Dissent written** in chat this session?
2. **Memory re-verify:** any memory used with `last_verified` > 90 days (names only).
3. **Stale action items:** any item not updated in 14+ days — up to 5, one at a time, each with a kill / keep / push recommendation.
4. **Episodic memory candidate:** a significant decision with no `episodic_*.md` yet.

## Routines

| Command | What it does | File |
|---|---|---|
| `kickoff` | Agent session-open brief | `Instructions/Routines/kickoff.md` |
| `/brain:transcript` | Process a meeting transcript into notes and action items | skill |
| `/brain:meeting-sync` | Batch-process unprocessed meeting notes | skill |
| `/brain:writer` | Draft in your own voice | skill |

## Date

Always compute the day of the week from the date; never assume a date.
