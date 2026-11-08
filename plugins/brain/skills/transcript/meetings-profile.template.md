---
title: Meetings profile — <agent name or "vault default">
caller: <agent name> (<role>)   # or: default Claude session in this vault (no /agents:start)
used_by: /brain:transcript, /brain:meeting-sync
last_updated: YYYY-MM-DD
---

<!--
TEMPLATE — copy to <agent dir>/meetings-profile.md (one per agent that processes
meetings) or to Instructions/meetings-profile.md (the vault default), then fill
in every <placeholder>. The shared skills hold the routine; this file holds the
caller's rules. When a step here is more specific than the skill, this file wins.
Delete sections you don't use, but keep the headings the skills look for:
Owns · Pre-flight memories · reconcile · new actions · notes · people · extra
steps · Log · Never · Closing block lines · /brain:meeting-sync rules.

A VAULT-DEFAULT profile can be just a routing table: "meeting is about X → apply
agents/<scope>/<agent>/meetings-profile.md". Then add the default-run rules:
print the profile actually applied in Step-Zero ("Profile: …(via default)"), tag
CHANGELOG entries [default], skip personal-scope meetings in Work Mode, and pull
every source the routed profiles list.
-->

# Meetings profile — <caller>

## Owns

- **Wispr folder(s):** `<folder name>` (optional).
- **Gemini notes** from Google Drive (`gdrive` CLI, account `<configured account>`) — optional; usually only one caller owns this source.
- **Pasted / file transcripts** about: <topics this caller owns — e.g. product, exec meetings, direct-report 1:1s>.
- **Not this caller's:** <other lanes> → name the owning agent/vault, process nothing. Private-scope material other agents must not see → record only "1 out-of-scope item skipped", never a title or summary.
- **Unfiled Wispr meetings:** <rule — e.g. all participants from your company domain → list by title with a process/skip recommendation; otherwise count only, since titles may be private>.

## Pre-flight memories (Step-Zero "Memories scanned")

<list the memory files every run must scan: action-item schema, approval rule, name-mapping rule, no-fabricated-names rule, the current direct-report list…> · plus topic memories for the participants, products and projects in this meeting.

Step-Zero extra lines (optional): `Direct reports in transcript: [names / none]` · `<key stakeholder>: [present / invited, absent / not invited]` (an absence can itself be news — say so in key points).

## Step: reconcile existing actions (run FIRST)

Read end-to-end this turn, not from memory:
- `ACTION_ITEMS.md` — sections <names>;
- the **Open** section of every `agents/<scope>/*/actions.md` (if you run agents);
- the **Open** entries of any shared handoffs file (e.g. `agents/_commons/<scope>/HANDOFFS.md`).

For every open item touching this meeting's topic, product or people — whether or not the meeting produced anything new — decide: DONE · KILLED · PROGRESSED · BLOCKED/AT RISK · SUPERSEDED · NO CHANGE.

**Auto-close only on clear evidence:** (a) verdict DONE; (b) the **verbatim transcript** (never an AI summary or Decisions block) has the owner or the user stating completion in the past tense — "shipped", "sent", "it's live", "signed"; (c) the item it closes is unambiguous. Plans, approvals, "will do", "almost there", third-party reports are not clear.
- `ACTION_ITEMS.md` and this caller's own `actions.md` → close (move to Completed).
- Another agent's `actions.md` → close, tagged `[closed by <caller> — <meeting, date>: "<quote>"]`.
- A handoffs file → **never close**; append `**EVIDENCE (<caller>, <date>):** looks done per <meeting> — "<quote>"`.
- Every auto-close is reported with its quote and an undo offer. Everything else is proposed one-by-one.

## Step: new actions

- **Tracker:** `ACTION_ITEMS.md` → section `<section name>`, inserted by due date (earliest first).
- **Only items the user owns:** the user executes it, or a launch/external milestone whose slip changes the user's posture, or a direct report's deliverable feeding a decision the user is about to make. Everything other people committed to → the **Commitments** block of the NOTES entry, not the tracker.
- **Schema (two lines; only `[ ]` / `[x]` checkboxes, status via tags + section):**
  ```
  - [ ] **Task name** #tag1 #tag2 — Description.
    Owner: <name> | Stakeholder: <name> | Due: YYYY-MM-DD | Created: YYYY-MM-DD | Source: YYYYMMDD - Topic
  ```
  Theme tags: <your tags>. Urgency tags: <e.g. #ceo-direct #legal-direct #critical>. Stakeholder ≠ Owner — never conflate.
- **Mandatory dedup:** grep `ACTION_ITEMS.md` by owner, stakeholder, topic, system names → classify each candidate SKIP / UPDATE existing / CLOSE + REPLACE / ADD new, and show the classification.
- **Approval:** AUTO-ADD when Owner = the user + Date + Stakeholder are all clear from a confirmed meeting transcript (report in the closing block). PROPOSE one-by-one when any is unclear. **ALWAYS approval** for items affecting external counterparts (outbound messages, commitments to your CEO/board) regardless of clarity.
- **Launch / external milestones owned by others** are always proposals, with the real owner in `Owner:` and the user as Stakeholder.
- **Every commitment the user makes leaves with a date.** If the user promised, delegated or "left it with me" without a date, propose one.
- Build/deploy work generated by a meeting (page, deck, render, deploy) → a handoff to your builder agent, if you have one.

## Step: notes

| Meeting type | Destination |
|---|---|
| <topic A> | `<work area>/NOTES.md` |
| <product B> | `<work area>/<Product B>/NOTES.md` |
| <performance reviews> | <the HR record governs — add only what's new to the person's profile, with a pointer; no NOTES entry> |

- Product-specific meetings go in the product's own NOTES, never the area-level one.
- Not clearly mappable → look for a more specific sibling `NOTES.md` (`find . -name NOTES.md`); still ambiguous or multi-domain → ask the user with options (a/b/both/new). Never create a new NOTES.md without approval.
- **Entry format:** newest first, at the TOP. Title `### YYYY-MM-DD — [Topic] ([Key people]; attendance notes) — ⚑ **headline**` (the ⚑ headline is optional, for the one thing that matters). Next line, italic: source + `paraphrase only`/`verbatim` + transcription mangling + unmapped names. Then bullets + bold key terms: decisions, blockers, strategic shifts, personnel changes, critical context. Quotation marks only for verbatim words. Omit small talk and process detail.
- **Commitments block:** `**Commitments:**` — one line per commitment someone other than the user made: `Owner — what — date (or "no date")`.
- **Decisions block:** `**Decisions:**` — one line per decision taken in the meeting (or route to a `DECISIONS.md` if you keep one).
- **Source:** in the italic line under the title (no raw transcript is stored).

## Step: people

- **The user's self-assessment** → `<work area>/People/Self.md`, under `## Transcript Assessments`, newest first, `### YYYY-MM-DD — [Meeting Topic]`: how they ran the conversation · what they contributed · what they could have done better · observations on other participants · patterns confirmed/updated. No dialogue attributed to the user → no assessment; say so in chat.
- **Direct-report assessments** — direct reports are **<list, kept current>** only → `<work area>/People/<Name>.md` under `## Recent Assessments`, newest first: performance (initiative, ownership, problem-solving, communication) · strengths · coaching points · dynamics. Everyone else → observations inside the user's entry only.
- **Patterns sync (optional):** if `Self.md` has a `## Current patterns` summary, update it **in place** after a substantive entry — edit the matching line's confidence · instances · last seen; add a line only for a genuinely new pattern; never append dated notes there. Act-and-inform: write it, then say in chat what changed, one line per change.
- **Size guardrail:** any profile over ~1,500 lines → propose an archive pass (entries > 8 weeks → `*_Archive.md`) before writing.
- **Known name traps** (transcription mishearings, nicknames): <"as heard" = real name, …>.

## Extra steps (optional — delete what you don't use)

- **Leadership quotes:** if <key stakeholder> is in the meeting → `<work area>/Context/<Name>_Quotes.md`, newest first, extreme statements only (money/valuation claims, speed claims, capability claims). Update `Last updated:`.
- **Contacts DB:** log an interaction for each external contact in `Network/<contacts>.db`; status changes are propose-only.

## Log

`CHANGELOG.md` — one entry per meeting (one per run in `/brain:meeting-sync`), tag `[<caller>]`, ≤ 600 characters.

## Never

<folders, files or databases this caller must never write — e.g. the personal area, another vault>.

## Closing block lines

```
Step reconcile: [X auto-closed / Y proposed / none]
Step actions: [X auto-added / Y proposed / none]
Step notes: [path] (+ Commitments n · Decisions n)
Step people: [Self ✓ / not present] · Direct reports: [files / none]
Step <extra>: [X added / not applicable]
Step log: [✓]
```
Inline after: key points (≤ 5) · the user's self-assessment (≤ 3 did well + ≤ 3 could improve) · proposed items · patterns lines changed.

## /brain:meeting-sync rules

**Sources:** Gemini notes via `gdrive` (query `name contains 'Notes by Gemini'`, owned + shared) — <yes/no>; Wispr folder `<name>` (id `<folder id>`) — **enabled: <yes/no>**. Wispr ids are recorded in the same state file as `wispr:<meeting id>`. State: `Instructions/state/meeting_sync_processed.json`.

**Classify:**
- **AUTO** — <e.g. squad calls · 1:1s with direct reports · exec & strategy sessions>.
- **SKIP** — recurring status/ops calls with no decision content (daily huddles, standups). Judge substance, not title.
- **PROPOSE** — everything else, with a one-line reason and a recommendation.

**Run report extra (optional):** an `OPEN HANDOFFS` block first: `<From> → <To> — <title> — <d> days open — waiting on <whose gate> → <recommendation>`, plus handoffs a transcript says look done.

**Judgement rules during a run:** <autonomy level — e.g. act-then-inform for processing, NOTES, people entries and clear-evidence closes; one question at a time in the decision pass; any stakeholder playbooks to apply>.
