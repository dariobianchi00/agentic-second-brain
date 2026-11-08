---
name: meeting-sync
description: Finds the caller's unprocessed meetings (Wispr Flow folders; Gemini "Notes by Gemini" docs in Google Drive where the caller's profile allows) and batch-processes them through /brain:transcript, unattended, with every human decision deferred to a single queue at the end. Adapts to the caller — whichever agent is active, or the vault default. Fires on "/brain:meeting-sync", "process my meeting transcripts", "catch up on transcripts", "any new meeting notes to process", "sync transcripts from drive", or whenever the user asks what meetings have gone unprocessed or how far behind they are. Use this instead of /brain:transcript whenever the meetings are NOT already pasted into the conversation.
---

# /brain:meeting-sync — Batch meeting sync (adaptive)

Finds every meeting **this caller** hasn't processed, runs each through `/brain:transcript` without stopping, then presents one decision queue at the end. The user can start it and walk away: everything that writes to files happens unattended; everything that needs their judgement waits in one place. **If this skill blocks mid-run asking a question, it has failed at its main job.**

`/brain:meeting-sync` = `/brain:transcript` + sources. The caller's **meetings profile** (`<agent dir>/meetings-profile.md`, or `Instructions/meetings-profile.md` for a default session — template in the `transcript` skill folder, `meetings-profile.template.md`) decides which sources, which meetings, and where everything goes.

## User-invocable

## Requirements (all optional — use what the profile lists)

- **Google Drive** via the `gdrive` CLI v3 (https://github.com/glotlabs/gdrive), with the account that receives Gemini meeting notes added via `gdrive account add`.
- **Wispr Flow MCP** (connected in `/mcp`) for Wispr meeting folders.
- A state file per caller (the profile names it; default `Instructions/state/meeting_sync_processed.json`) and an optional cross-vault claim file `~/.claude/state/meeting_claims.json` if you run more than one vault or several agents that could see the same meeting.

## Allowed Tools

```yaml
- Bash(gdrive, mkdir, ls, rm, date, pgrep)
- Read(*)
- Edit(*)
- Write(*)
- Glob(*)
- Grep(*)
- mcp__<wispr-flow server>__*
```

## Step 0 — Caller and profile

Resolve the caller exactly as `/brain:transcript` Step 0 does (read that skill's `SKILL.md`). Read the profile in full. **No profile → stop.** Read the profile's `/brain:meeting-sync rules` section: sources, classification, report extras.

## Step 1 — Window

Confirm today's date with `date`. Read the caller's state file (the profile names it).
- Normal run: window starts at `last_run`.
- No state / first run: last 7 days.
- Explicit override (`/brain:meeting-sync 30d`, `/brain:meeting-sync 2026-08-01`, `/brain:meeting-sync since monday`): honour it.

## Step 2 — Discover (only the sources the profile lists)

**Gemini notes (Drive)** — only if the profile lists it. Read Drive through the `gdrive` CLI — not Gmail (OAuth tokens on some Workspace accounts expire within days) and not a local Drive sync folder (sync can silently stop for weeks).
```bash
gdrive files list \
  --query "name contains 'Notes by Gemini' and createdTime > 'YYYY-MM-DDT00:00:00'" \
  --order-by "createdTime desc" --max 50
```
One query finds owned and shared docs — do not filter on `sharedWithMe`. Drop `shortcut` rows and `Recording` files; collapse duplicates by title + date.

**Wispr** — only if the profile lists it **and marks it enabled**. `list_folders` → for each folder the profile owns, `list_folder_meetings` (paginate) within the window. Read a meeting with `get_meeting` + `view_transcript` — the transcript is the verbatim source; Wispr's notes are a summary. Unfiled meetings (no folder) → handled per the profile (e.g. listed with titles only for personal-scope callers; a bare count for everyone else, since titles may be private).

**A source error is not "nothing new".** If `gdrive` or Wispr errors, report it as a failure. "You're all caught up" when you aren't is the worst outcome this skill can produce.

## Step 3 — Dedup

1. **State file** — skip anything already recorded (Drive file ID / Wispr meeting ID).
   **Claim file** `~/.claude/state/meeting_claims.json` (if used) — skip anything claimed by **another** vault or agent (key `gdrive:<id>` / `wispr:<id>`). It holds ids + vault only, never titles.
2. **Wispr ↔ Gemini** (callers with both) — same calendar event, or same start ±10 min → one meeting: Wispr transcript as source, Gemini notes as a secondary summary.
3. **NOTES cross-check** — grep the destination NOTES for an entry with the same date and topic (catches meetings the user pasted by hand). Record those as `skipped-already-in-notes`.

## Step 4 — Lane and classify

- Not in the profile's **Owns** → `routed-elsewhere` (note the owning vault/agent), not processed. **One recording can hold several meetings** (back-to-back calls in one Wispr note): check the lane **per segment** — process your segments, route the rest by name only.
- Then the profile's classification: **AUTO** (process) · **SKIP** (list only — recurring no-decision calls; judge substance, not title) · **PROPOSE** (one-line reason + recommendation).
- More than ~8 AUTO meetings → say so and offer the most recent 8 first; a 20-meeting batch makes the decision queue unusable.

## Step 5 — Fetch

- Drive: `gdrive files export --overwrite <FILE_ID> "<tmp>/<safe-name>.txt"` where `<tmp>` = `$CLAUDE_JOB_DIR/tmp` if set, else the session scratchpad, else `$TMPDIR` (two positional args, no `--mime-type`). Work from the **Full notes** section (attendees + Decisions).
- Wispr: `get_meeting` with `view_transcript`, paging until complete.
- **Delete every export once processed** — no raw transcripts are stored anywhere.

## Step 6 — Process each meeting through /brain:transcript, deferred mode

Read the `/brain:transcript` skill and follow it with the caller's profile — reconcile first, then actions, notes, people, the profile's extras, log. Batch mode changes **only where decisions land**:

| /brain:transcript step | Batch behaviour |
|---|---|
| Step-Zero block | One per meeting, as normal |
| Reconcile — clear DONE | Auto-close per the profile, quote + undo in the report |
| Reconcile — anything else | **Don't ask** → deferred queue |
| Actions — clear, profile-approved auto-adds | Auto-add as usual |
| Actions — ambiguous / external-facing | **Don't ask** → deferred queue |
| People, profile extras (e.g. a leadership-quotes file, a contacts-DB interaction log) | As the profile says |
| Proposals the profile marks "propose only" (e.g. contact status changes) | **Don't ask** → deferred queue |
| Log | **One entry for the whole run** |
| Per-meeting closing block | Replaced by the Step 8 run report |

**Uncertainty is an output.** Can't tell whether to add, close or leave something → put it in the UNCERTAIN block with **what you'd need to know** ("unclear whether this closes #41 — depends on which team"). Never guess in either direction.

**Speaker labels can be wrong.** Diarisation often mislabels (every line attributed to one person; the user as "Speaker 2"). If labels are broken, treat attributions as paraphrase-grade: no auto-close, no quotes put in anyone's mouth, flag it in the source line. AI meeting summaries harden hedges into decisions ("Decision: vendor stays engaged" from a hedge) — never take decisions from them.

**Back-processing** (meetings weeks old): trackers were usually rebuilt from later events, so few closes are expected — the "clean report" warning below doesn't apply; say "back-processing" in the report header.

**Step-Zero in a batch:** one consolidated Step-Zero table at the top of the run report (one row per meeting) is acceptable when the run's output is a single report.

**Temp files:** prefix with `tmp_` — macOS paths are case-insensitive, so `alex.md` collides with `Alex.md`.

**Attendance matters.** No dialogue attributed to the user → no self-assessment; say so. Summaries support "what someone did", not quotes.

**One failure doesn't strand the rest.** Export error, unreadable doc, ambiguous routing → record it, move on, report it.

Work Mode active (see `/agents:*` conventions) → skip personal-scope meetings silently; report only a count.

## Step 7 — Update state

Record every meeting handled (processed, skipped, proposed-declined, routed-elsewhere, failed) in the state file, then advance `last_run` **only for the sources this run actually discovered** — keep one `last_run` per source (`last_run_gdrive`, `last_run_wispr`). A run on a supplied list of meetings discovers nothing and advances nothing. Also write each processed meeting to the claim file (if used): `"wispr:<id>": {"brain": "<vault>", "agent": "<caller>", "source": "wispr", "status": "processed", "at": "<date>"}`. Without SKIP/declined records, every run re-surfaces the same standups.
```json
{"last_run_gdrive": "2026-08-09T15:30:00+00:00",
 "last_run_wispr": "2026-08-09T15:30:00+00:00",
 "processed": [{"id": "<drive id or wispr:<meeting id>>", "title": "…", "meeting_date": "2026-08-07",
   "processed_at": "2026-08-09", "outcome": "processed", "caller": "<agent or default>"}]}
```
`outcome`: `processed` · `skipped-ops` · `skipped-already-in-notes` · `proposed-declined` · `routed-elsewhere` · `failed`.

## Step 8 — Run report (the deliverable)

Files are written by now; this report is what the user consumes. Write it for someone who wasn't in any of these meetings and has ninety seconds. Lead with what's new.

```
MEETING SYNC — <caller> — <window> — <N> found · <A> processed · <S> skipped · <P> proposed · <R> routed elsewhere

[profile report extras — e.g. an OPEN HANDOFFS block, always first]

⚑ WHAT'S NEW — read this if you read nothing else
  • …

CLOSED (auto, clear evidence) — <n>     reply "undo <#>" to reopen
  <file · #/name> — "<verbatim quote>" (<meeting, date>)

ACTIONS TO CLOSE — <n> proposed
⚠ UNCERTAIN — needs your call
PROCESSED
  <Meeting> (<date>) → <path>
    • up to 3 key points, decisions first
    • You: 1–2 lines, or "not present — no dialogue attributed"
YOUR COMMITMENTS WITHOUT A DATE — <n>   (propose a date for each)
FILES WRITTEN · SKIPPED · PROPOSED · ROUTED ELSEWHERE · UNFILED · FAILED
```

**WHAT'S NEW** is not a summary. It is the few things that would make the user stop scrolling: a new fact that changes a plan · a first appearance (check the vault before claiming novelty) · a contradiction with the tracker, a profile or a prior decision · something decided without the user · a risk nobody owned. Nothing clears the bar → `Nothing new — routine week.` A padded WHAT'S NEW trains the reader to skip it.

Key points and the "You" line appear for **every** processed meeting.

## Step 9 — Decision pass

Only now, work the deferred queue **one item at a time**, each with a recommendation, waiting for the user's call. Order by consequence:
1. Actions to close (first ask "any undo on the auto-closes?" in one line)
2. Uncertain items — each with the question that settles it
3. Status flips on items that stay open
4. Ambiguous / external-facing new actions
5. The user's commitments without a date
6. PROPOSE-bucket meetings — process or skip? · unfiled meetings — where do they belong?
7. The profile's propose-only items (patterns-sync lines, contact status batch…)

Then the caller's session-end steps and the root `CLAUDE.md` Session End Checklist (if the vault defines one).

## Failure modes

- **"Nothing new" that is an auth failure** — report source errors (`gdrive account add` for Drive; reconnect Wispr in `/mcp`).
- **Duplicate NOTES entries** — the cross-check in Step 3 prevents it; never skip it to save a read.
- **Over-processing** — cap at ~8 AUTO per run.
- **A clean report that isn't true** — real meetings almost always yield at least one close and one uncertainty. If a run shows neither, the reconcile was skimmed: go back through the tracker before reporting.
- **Drift back to pasting** — if the user is still pasting most meetings a month from now, raise it rather than quietly maintaining an unused skill.
