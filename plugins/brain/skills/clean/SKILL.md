---
name: clean
description: Audits and cleans up a markdown vault for structure, token efficiency and findability — loose files, tracker and changelog archival, bloated or stub files, orphaned and ghost INDEX entries, stale content, naming, duplicates, non-markdown leftovers, and agent-framework hygiene (trackers, memory, commons). Runs interactively, one issue at a time, with Execute / Edit / Skip. Fires on /brain:clean or "clean up the vault", "vault health check".
user-invocable: true
allowed-tools:
  - Read(*)
  - Glob(*)
  - Grep(*)
  - Bash(find, ls, wc, stat, mv, rm, grep, sed)
  - Edit(*)
  - Write(*)
---

# /brain:clean

Audit and clean up the user's vault for optimal structure, token efficiency, and findability.

## Description

A full health check of a vault. Scans for structural issues, bloated files, stale content, token inefficiencies, and **agent-framework hygiene debt** (trackers, memory, commons). Runs interactively — presents each issue one at a time with a proposed action. The user responds **Execute**, **Edit**, or **Skip** for each.

**Goal:** Fewest files, smallest footprint, fastest context loading — without losing any active information.

**Framework alignment:** if the vault runs an agent framework (e.g. the `agents` plugin, with `Agents/CONVENTIONS.md` extending the plugin's master conventions — workspace file wins on conflict), agent structure is governed by that framework. `/brain:clean` handles **archival and bloat** inside that structure; it never restructures agents — structural problems are `/agents:doctor <name>`'s job and are surfaced as a recommendation to run it, not fixed here.

## Workflow

### Step 0: Detect vault + guards

**Vault detection** — the vault is the current working directory if it has a root `CLAUDE.md`. If not, ask which folder to clean (one question). One vault per run. If the user keeps several vaults, treat them as firewalled: never cross-reference, never move files between them.

**Vault profile** — read the root `CLAUDE.md` (and `Agents/CONVENTIONS.md` if present) and build this profile before scanning. Use the defaults where the vault says nothing:

| Setting | Default |
|---|---|
| Root system files (exclude from Check 1) | `CLAUDE.md`, `INDEX.md`, `ACTION_ITEMS.md`, `ACTION_ITEMS_ARCHIVE.md`, `CHANGELOG.md`, `CHANGELOG_ARCHIVE.md` — plus any other root file `CLAUDE.md` names as a system file (e.g. `MILESTONES.md`, `DECISIONS.md`, `NOTES.md`) |
| Tracker | `ACTION_ITEMS.md` (sections **At Risk → Open → Completed**, status via tags). Optional: `MILESTONES.md` with evidence-based closure (Check 2b) |
| Run log | root + area-level `CHANGELOG.md`. If the vault has none, the run log is a one-liner in root `NOTES.md` (+ `DECISIONS.md` only when a real choice was made) |
| Agent layout | `Agents/<scope>/<name>/` or `Agents/<name>/` — whatever is on disk |
| Commons | `Agents/_commons/<scope>/` (DEBATES, JOURNAL, HANDOFFS, RETRO) if present |
| Scheduler | `Agents/scheduler/`, `Agents/scheduled-tasks.md` if present (the bundled scheduler is macOS-only, launchd) |
| Content folders (Check 5) | the top-level areas listed in `CLAUDE.md` (starter vault: the work area, the personal area, `Knowledge/`, `Network/`, `Inbox/`) |
| Never-auto-load files (size/stat only — never Read contents) | `*_ARCHIVE.md`, plus any file `CLAUDE.md` marks sensitive (e.g. financials) |

**Work Mode guard.** If the vault defines a screen-share / work mode that hides personal content, and it is active, REFUSE to run: `/brain:clean` scans the personal area and would surface sensitive content on screen. Respond: "Blocked — Work Mode active. `/brain:clean` touches personal content. Say `normal mode` to proceed." Do not scan.

**Plugin-managed paths — never modify, never flag for merge/rename/delete:**
- `Agents/scheduler/` (workspace copy of the plugin scheduler; refreshed by the framework's init command), `Agents/scheduled-tasks.md`, `Agents/tools/`, `Agents/skills/`
- `.claude/skills/`, `.agents/skills/`
- `Agents/**/peer/` (created on demand by `/agents:ask`)
- `Agents/**/playbooks/.gitkeep`
- `Agents/scheduler/logs/` — may be reported as a size note only; no action.

---

### Step 1: Full Scan

Run all checks silently before presenting anything. Gather all issues first, then present them in priority order. Skip any check whose files don't exist in this vault.

#### Check 1 — Loose files in vault root
Glob for `*.md` files directly in the vault root (not in subfolders). Exclude the profile's root system files.
- **Flag**: Any unprocessed loose files.
- **Action**: Process each (route to the right `NOTES.md` / extract action items — follow the vault's notes-processing routine if it has one, e.g. `Instructions/Routines/notes_processing.md`) and delete.

#### Check 2a — ACTION_ITEMS.md hygiene
Read `ACTION_ITEMS.md`. The default schema is section-based (**At Risk → Open → Completed**) with status conveyed by tags (`#at-risk`, `#in-progress`, `#blocked`) and section placement — only `[ ]` and `[x]` checkboxes are renderer-safe.
- **Flag**: `[x]` items in the Completed section older than 7 days (use the `Updated:` date, or `Created:` if none).
- **Action**: Move flagged items to `ACTION_ITEMS_ARCHIVE.md`.
- **Also flag**: any item using a non-standard bracket variant (e.g. `[/]`, `[-]`, `[>]`) — Obsidian renders these as checked. **Action**: convert to `[ ]` + appropriate status tag.

#### Check 2b — MILESTONES / evidence-closed trackers (if the vault uses them)
If the vault tracks rows that close only on cited evidence (e.g. `MILESTONES.md`, or an `ACTION_ITEMS.md` with Open / Waiting on / Rotting / Completed sections), read them (never the archives).
- **Flag**: rows already marked closed/done → move to the matching `*_ARCHIVE.md`. Rows dated in the past and marked `DONE`/`SLIPPED`-and-superseded → archive. Past-dated rows with no status → flag as "needs status", do not move.
- **NEVER close on age.** A row closes only with cited evidence. `/brain:clean` archives rows that are *already closed*; it does not close open rows. Open rows >45 days with no movement are surfaced as **Rotting candidates** for the user's decision — flag only.
- **Parked rows are never archived.** If the vault marks rows parked for the user's decision (e.g. a `⏸ USER:` tag), they are the parked queue. If a parked row looks done, flag it as "untag candidate — needs evidence", do not touch.

#### Check 3 — Run-log archival
- **CHANGELOG vaults**: Glob every `CHANGELOG.md` (root and area-level). Entries older than 30 days → matching `CHANGELOG_ARCHIVE.md` (create an area-level one if missing). Never merge across areas/scopes. Preserve agent identity tags (e.g. `[<agent>]`).
- **NOTES-as-log vaults**: check root and area `NOTES.md` for entries older than 90 days → propose moving to `NOTES_ARCHIVE.md` (append, newest first). `DECISIONS.md` is append-only — never archive or edit.

#### Check 4 — NOTES.md bloat
Read each live `NOTES.md` (never `NOTES_ARCHIVE.md`).
- **Flag**: Any NOTES.md with 20+ entries.
- **Action**: Identify the top 3-5 entries that warrant promotion to standalone docs. Suggest creating dedicated files and removing those entries from NOTES.md.

#### Check 5 — Orphaned files (not in INDEX.md)
For each content folder in the profile, glob all `.md` files and compare against the relevant `INDEX.md` (if the vault has a single root `INDEX.md`, it is authoritative).
- **Flag**: Files that exist but aren't listed in INDEX.md.
- **Action**: Add to INDEX.md (or confirm deletion if truly orphaned).
- **`Agents/` is exempt.** An agent framework indexes agents through `Agents/CONVENTIONS.md`, each agent's `MEMORY.md`, `memory/archive/INDEX.md` and `Agents/tools/INDEX.md` — not the vault INDEX. Do not add agent files to the vault INDEX and do not flag them as orphans.

#### Check 6 — INDEX.md accuracy (ghost entries)
Read each `INDEX.md` and verify every listed file actually exists on disk. Include agent-side indexes: each agent's `MEMORY.md` (Standing + Sessions links), `memory/archive/INDEX.md`, `Agents/tools/INDEX.md`.
- **Flag**: Entries pointing to non-existent files.
- **Action**: Remove ghost entries. For `MEMORY.md` ghosts, check `memory/archive/` first — a consolidated entry may have moved; fix the link rather than deleting it.

#### Check 7 — Stale files (60-day threshold)
Use `find`/`stat` to identify `.md` files not modified in 60+ days. Cross-reference: if still referenced in INDEX.md as active or a knowledge/context file, deprioritise. Focus on: meeting transcripts, snapshots, project files, notes, `Inbox/`.
- **EXCLUDE — staleness-immune agent files:** never flag anything under `Agents/**/memory/sessions/` or `Agents/**/memory/archive/` — dated historical records, not stale content. `Agents/**/memory/standing/` >90 days is a **re-verify** note only (surface, don't propose archiving — consolidation is Check 15). Never flag `role.md`, `soul.md`, `name.md`, `autonomy.md`, `tools.md`, `context.md` for age — they change rarely by design.
- **Flag**: Files both old (60+ days) AND apparently no longer active.
- **Action**: Move to the appropriate `_archive/` subfolder (closed projects go to whatever archive folder the vault uses), OR delete if trivial.

#### Check 8 — Oversized files (token bloat)
Flag any `.md` file over 150KB or 500+ lines (`wc -l`).
- **Agent-specific thresholds:** `soul.md` should be under 20 lines, `name.md` under 15; `actions.md` `Last reviewed:` line must be one line, date only, under 600 characters (session narrative belongs in `memory/sessions/`); a single `memory/standing/` entry that is a data dump (export, scan, table >100 lines) belongs under content folders with a one-page pointer left behind.
- **Flag**: Files too large to load efficiently.
- **Action**: Suggest splitting at natural points (date, topic, section). For agent files, apply the framework's fix (trim `Last reviewed:`, move the dump out, leave a summary) — never invent a new agent file.

#### Check 9 — Undersized/stub files (merge candidates)
Flag `.md` files under 500 bytes that aren't INDEX.md, NOTES.md, or system files.
- **EXCLUDE — canonical agent files:** never flag `Agents/**/{role,soul,name,autonomy,tools,actions,actions-archive,context,MEMORY}.md`, anything in `memory/`, `playbooks/`, `peer/`, `memory/scheduled/inbox.md`, `Agents/tools/*.md`, `Agents/scheduler/*`. Short is by design (`soul.md` <20 lines, `name.md` <15; an empty `actions-archive.md` is created at agent birth and fills at the first 30-day archival). Merging them breaks the agent.
- **Flag**: Tiny content files that add overhead without value.
- **Action**: Suggest merging into the parent NOTES.md or a related file, then delete.

#### Check 10 — Naming convention violations
Glob all files. Content files: snake_case or Title_Case with underscores. Flag files with spaces (except known dated-transcript patterns), ambiguous names.
- **EXCLUDE — framework naming:** the convention is *system files UPPERCASE, content files lowercase*. Lowercase agent directories (`Agents/<scope>/<name>/`), lowercase agent files (`role.md`, `actions-archive.md`), hyphenated session-memory slugs (`2026-08-21-tracker-purge.md`), `memory/scheduled/inbox.md`, playbook slugs — all compliant. Never flag them.
- **AGENT-PATH GUARD (run before proposing ANY folder or file rename):** `grep -rIl "<name>" Agents/ .claude/ Instructions/` — if any `context.md`, `role.md`, `tools.md`, `memory/`, `playbooks/`, `scheduled-tasks.md`, `Agents/scheduler/`, `CLAUDE.md`, `INDEX.md` or skill references it, **flag-don't-rename**: the path is wired into an agent's startup cascade or a scheduled tick, and a rename silently breaks it. A rename either updates every referencing file in the same operation or is skipped. Space-named folders that several agents reference are left as-is unless the user explicitly asks for a coordinated rename.
- **Action**: Rename with `mv` only when the guard passes.

#### Check 11 — Duplicate/near-duplicate files
Look for very similar names in the same folder; grep for overlapping content sections.
- **Agent-specific:** a fact tracked in two homes is a duplicate (one item, one home — e.g. a row in `ACTION_ITEMS.md` *and* an agent's `actions.md`, or the same item in two agents' `actions.md` without a HANDOFFS pointer). Flag with both locations; proposed fix = keep the row where the *next actor* lives, replace the other with a one-line pointer. **Never renumber action IDs** on migration — they are cited in session memories.
- **Flag**: Files/rows that duplicate information.
- **Action**: Merge into one canonical home; delete or pointer-ise the other.

#### Check 12 — Non-MD files audit
Scan the vault for non-markdown files, excluding:
- Hidden directories (`.obsidian/`, `.claude/`, `.agents/`, `.playwright-mcp/`, `.venv/`, `__pycache__/`)
- `.DS_Store`, `.gitkeep`
- Operational scripts and code (`Instructions/scripts/`, `Agents/scheduler/` — Python, shell, plists, logs)
- Databases the vault's tools depend on (e.g. a contacts `*.db` under `Network/`) — check `CLAUDE.md`
- Agent portraits (`Agents/**/portrait.png`) — framework artefacts, keep.

**Flag**: Any other non-MD file — images, PDFs, HTML exports, ZIPs, audio, config, JSX, and **migration leftovers** (`*.bak-YYYY-MM-DD` written by a framework migration — `context.md.bak-*`, `actions.md.bak-*`, `MEMORY.md.bak-*`, whether at agent root or already under `memory/archive/`).

**Action per type:**
- **`*.bak-*` migration files** → if the live file exists and is newer, propose deletion (archive copy to `Agents/_archive/<scope>/<name>/` first if the user wants belt-and-braces). Never touch a `.bak` whose live counterpart is missing — flag for `/agents:doctor`.
- **HTML exports/decks** → convert to MD and delete HTML
- **Work PDFs/ZIPs** → propose moving to the user's work file store (e.g. a shared drive, if configured) — ask for the destination, never guess one
- **Files that belong to a different vault or project** → flag, do not move (cross-vault moves are the user's call)
- **Unprocessed documents** → `Inbox/documents/` (or the vault's equivalent); processed ones go to the relevant project folder, listed in `INDEX.md`
- **Images used as standalone assets** → move out or delete if orphaned
- **Processed voice notes / transcripts** → delete (already processed; check any `_processed/` folder first)
- **Test files** → delete

Present each file or logical group one at a time.

#### Check 13 — Folder structure review
Evaluate folder granularity:
- **Too granular**: a subfolder with 1-2 files — consider merging up.
- **Too flat**: a folder with 20+ files on mixed topics — consider splitting.
- **Misplaced**: files or folders in the wrong area (e.g. closed projects still in an active folder → the archive folder; only on a formal close per `CLAUDE.md`'s closure rule, if it has one).
- **NOTE — `Agents/` is structured by the framework, not by taste.** Never flag an agent directory for "too granular" — `playbooks/` with only `.gitkeep`, an empty `peer/`, `memory/scheduled/` with one file, `memory/archive/{standing,sessions}/` are all mandated or on-demand. Never propose creating an `INDEX.md` inside `Agents/` beyond the ones the framework defines (`Agents/tools/INDEX.md`, `memory/archive/INDEX.md`). A **missing** canonical file (`tools.md`, `actions-archive.md`, `MEMORY.md`) is not `/brain:clean`'s to create — recommend `/agents:doctor <name>`.

#### Check 14 — Agent tracker hygiene (`actions.md`) — all agents
Read every `Agents/**/actions.md`. Per the framework's tracker-hygiene rules:
- **Completed rows older than 30 days** → move to `actions-archive.md` in the same directory (same table format; create the file if missing and note that `/agents:doctor` should have caught it).
- **Ghosts in Open** — struck-through or completed rows still in the Open table → move to Completed (or archive if >30 days). No strikethrough-then-leave-it.
- **`Last reviewed:` line** longer than one line / 600 chars → trim to the date; narrative goes to the most recent session memory or is dropped if already there.
- **Rows whose owner is not the agent** (a person-owned row is "a commitment wearing a costume") → flag for migration to `ACTION_ITEMS.md` or a HANDOFFS entry. Flag only — the owning agent migrates at its next session; never renumber.
- **Never** edit Open-row status, priority, or parked tags — those belong to the agent and the user. `/brain:clean` archives and de-ghosts; it does not decide.

#### Check 15 — Agent memory consolidation
For each agent, count `memory/standing/*.md` and `memory/sessions/*.md` and read `MEMORY.md`. Per the framework's memory rules:
- **Consolidation trigger:** >5 standing entries or >10 session entries. Every standing entry and all of `MEMORY.md` load at every startup — a 40-entry standing memory is ~60k tokens before the agent says hello.
- **Flag**: agents over either limit; standing entries >90 days old (re-verify note); `MEMORY.md` summaries longer than one line.
- **Action** (per the framework's memory reference): superseded standing entries → `memory/archive/standing/`; keep the 10 most recent sessions, older → `memory/archive/sessions/`; write/refresh `memory/archive/INDEX.md` listing every archived file with its one-line summary; update `MEMORY.md` links. **Which standing entries are "superseded" is a judgment call — list candidates with a one-line reason, let the user pick.** Session memories are moved, never deleted, never merged.
- **`memory/scheduled/inbox.md`** (agents with scheduled ticks): all-`PROCESSED` entries older than 30 days → flag as trim candidates (move to `memory/archive/scheduled-inbox-<YYYY-MM>.md`). Never touch an `UNPROCESSED` entry — that is the agent's next interactive session's job.
- **`memory/reference/`** (where present) is agent-curated reference material — size note only.

#### Check 16 — Agent commons archival (if commons exist)
Read each `Agents/_commons/<scope>/` file. Archives follow the `<FILE>_ARCHIVE.md` pattern in the same folder:
- **DEBATES.md**: `Status: decided (...)` entries >30 days after decision date → `DEBATES_ARCHIVE.md` (create if missing). Open debates are never touched — only the user closes.
- **HANDOFFS.md**: `[STATUS: closed]` entries >30 days → `HANDOFFS_ARCHIVE.md`. Open entries never touched; `/brain:clean` never closes a handoff (the sender closes, two-file rule).
- **RETRO.md**: keep the last 2 ISO weeks live; older → `RETRO_ARCHIVE.md`.
- **JOURNAL.md**: >50 entries or entries >60 days → `JOURNAL_ARCHIVE.md`.
- Respect scope asymmetry — never merge commons across scopes (e.g. personal into work). Preserve agent attribution. Shared-read commons (e.g. `Knowledge/`, `Network/`) follow the same rules with their own archives.

---

### Step 2: Triage Results

After scanning, present a summary first:

```
## <Vault> Health Check

Found X issues:
- 🔴 Critical (blocking efficiency): N
- 🟡 Important (structural): N
- 🟢 Minor (housekeeping): N
- ↪ Deferred to /agents:doctor: N

Starting interactive review...
```

Then present issues in this priority order:
1. 🔴 Loose files (unprocessed = active noise)
2. 🔴 Tracker archival (ACTION_ITEMS; MILESTONES already-closed rows)
3. 🔴 Oversized files (active token drain) — incl. bloated `Last reviewed:` lines
4. 🔴 Agent memory over consolidation limits (startup-cost drain)
5. 🟡 Agent tracker hygiene (Completed >30d, ghosts in Open)
6. 🟡 Run-log archival (CHANGELOG >30d / NOTES-as-log >90d)
7. 🟡 NOTES.md bloat
8. 🟡 Orphaned files
9. 🟡 Ghost INDEX / MEMORY.md entries
10. 🟡 Folder structure issues
11. 🟡 Agent commons archival
12. 🟢 Stale files
13. 🟢 Undersized/stub files
14. 🟢 Naming violations
15. 🟢 Duplicate files / duplicate tracker rows
16. 🟢 Non-MD files (incl. `*.bak-*` migration leftovers)

Items deferred to `/agents:doctor` (missing canonical files, broken `context.md` paths, retired-agent frontmatter) are listed once at the end, not walked through.

---

### Step 3: Interactive Review

Present each issue in this format:

```
─────────────────────────────────
Issue 3 of 12 | 🔴 Critical

FILE: Agents/<scope>/<agent>/memory/standing/  (7 entries — limit 5)
PROBLEM: 7 standing entries load at every <agent> startup (~11k tokens)
IMPACT: Every <agent> session pays this before its first reply

PROPOSED ACTION:
Consolidate per the framework's memory rules — archive 2 superseded entries:
- 2026-05-baseline.md → superseded by 2026-08-baseline.md
- 2026-06-invoicing-rule.md → folded into autonomy.md 2026-07-12
Move to memory/archive/standing/, update memory/archive/INDEX.md + MEMORY.md

[E] Execute  [D] Edit proposal  [S] Skip
─────────────────────────────────
```

Wait for the user's response:
- **E / Execute**: Perform the action immediately, confirm done, move to next issue.
- **D / Edit**: The user types the modified instruction. Execute the edited version.
- **S / Skip**: Log as skipped, move to next issue.

---

### Step 4: Batch System File Updates

After all issues are reviewed, perform ONE batch update:

**CHANGELOG vaults:**
1. Update all affected `INDEX.md` files and any `MEMORY.md` / `memory/archive/INDEX.md` touched.
2. Add ONE root `CHANGELOG.md` entry (`[clean]` tag) summarising the run; area-level CHANGELOG entries only for areas whose files moved.

**NOTES-as-log vaults:**
1. Update root `INDEX.md` and any `MEMORY.md` / `memory/archive/INDEX.md` touched.
2. Add ONE line to root `NOTES.md` (newest first) summarising the run.
3. `DECISIONS.md` only if the user made a real choice during the run (e.g. chose to retire a folder) — append-only, with Counter-view + Review trigger. Housekeeping is not a decision.

**Both:** if any agent's `actions.md`, `MEMORY.md` or memory folders were touched, list the agents at the end so the user knows the agent's next startup will see a changed state. `/brain:clean` never writes session memories on an agent's behalf.

Report final stats:

```
## Clean Complete — <Vault>

✅ Executed: X actions
⏭️ Skipped: X issues
📁 Files archived: X
🗑️ Files deleted: X
📄 Files merged/split: X
🤖 Agents touched: <names> (tracker / memory / commons)
↪ Deferred to /agents:doctor: <names or none>
💾 Estimated token savings: ~X% reduction in vault size (+ ~Yk tokens off agent startup)
```

---

## Principles

- **Never delete without archiving first** — move to `_archive/` (or the framework's `memory/archive/`, `*_ARCHIVE.md`, `actions-archive.md`) before proposing a hard delete. Hard delete only on a second pass when clearly trivial (`*.bak-*` with a newer live counterpart qualifies).
- **Don't merge active files** — referenced in the last 30 days of the run log, in an open tracker row, in a `context.md` startup path, or in a `scheduled-tasks.md` register = active. Don't merge, rename or archive it.
- **Archive, never adjudicate.** `/brain:clean` moves rows that are *already* closed/completed/decided past their retention window. It never closes a commitment, a handoff, a debate or an action, never untags a parked row, never changes a priority. Evidence-based closure belongs to the agents and the user.
- **Structure is the framework's.** Missing or malformed canonical agent files → `/agents:doctor <name>`. `/brain:clean` does not create, rename or restructure anything under an agent's folder beyond the archival moves the framework itself prescribes.
- **Preserve all information** — restructuring is about organisation, not deletion. No content is lost.
- **Token efficiency first** — when in doubt about splitting a content file, split. For agent startup cost, when in doubt about a standing entry, list it as a candidate and let the user decide.
- **One pass, one scope** — don't cascade. If an action reveals another issue, log it; don't act on it in the same run. One vault per run.
