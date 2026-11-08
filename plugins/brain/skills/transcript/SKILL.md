---
name: transcript
description: Processes a meeting transcript or meeting summary that the user pastes or points to into notes, action items, decisions and people updates, using the rules of whoever is calling — the active agent or the vault's default meetings profile. Fires on "/brain:transcript", "process this transcript", "process these notes", "here's the meeting notes", "here's the Gemini summary", or when the user pastes a block that is clearly a meeting transcript/summary/recording-notes (speaker names, timestamps, "Summary/Decisions/Next steps" headers, Gemini/Otter/Granola/Wispr formatting). Use this skill whenever the input is a meeting artefact, even if the user didn't attend, even in multi-transcript batches, and even if the message is short. Do not just summarise in chat — this skill writes to files.
---

# /brain:transcript — Meeting Transcript Processing (adaptive)

Processes ONE meeting end-to-end with the rules of the **caller**. This file holds the routine every vault and agent shares; the caller's **meetings profile** holds where things go and what is specific (trackers, NOTES routing, people files, extra steps such as a leadership-quotes file or a contacts-DB log, what is forbidden). Start a profile from `meetings-profile.template.md` in this folder.

## User-invocable

## Allowed Tools

```yaml
- Read(*)
- Edit(*)
- Write(*)
- Glob(*)
- Grep(*)
- Bash(sqlite3, mkdir, ls, date)
```

## Step 0 — Resolve the caller and load the profile

1. **Who is calling?**
   - This session ran `/agents:start <name>` → that agent. Profile = `<agent dir>/meetings-profile.md` (e.g. `Agents/<scope>/<agent>/meetings-profile.md`).
   - No agent active → the vault default: `Instructions/meetings-profile.md` in the current vault (working directory).
2. **No profile found → stop.** Say which file was missing and offer to create it from `meetings-profile.template.md`. Never guess an agent, never borrow another vault's or agent's profile, never fall back to "how it used to work".
3. **Read the profile in full, every run.** Do not work from memory of it or of this skill. (Known failure mode: in batches, the profile's extra steps, people assessments and the log get skipped because the steps were "remembered".)
4. A default profile may route the meeting to an agent profile — then that profile governs the meeting.

## Input — what a "meeting" can be

- **Pasted** text → nothing to fetch.
- **A file** (e.g. `Inbox/transcripts/…`) → read it; deleted in Step 8.
- **A Gemini doc in Drive** → `gdrive files export --overwrite <FILE_ID> "<tmp>/<safe-name>.txt"` where `<tmp>` = `$CLAUDE_JOB_DIR/tmp` if set, else the session scratchpad, else `$TMPDIR` (create it). Two positional args, no `--mime-type`. Work from the **Full notes** (attendees + Decisions) and the verbatim **Transcript** section if the doc has one. Requires the `gdrive` CLI v3.
- **A Wispr Flow meeting** → `get_meeting` with `view_transcript`, paging until complete. The transcript is the source; Wispr's notes are a summary. Requires the Wispr Flow MCP.
- **Paraphrase only** (AI notes with no verbatim transcript) → say so in the source line; no quotation marks around paraphrase; auto-close is impossible by construction.
- **Dates:** compute the meeting date's real weekday; if the header's weekday disagrees ("Mon 13 Oct" that is a Tuesday), flag it and trust the numeric date. Relative dates ("today", "next Monday", "Wednesday") resolve against the **meeting** date.
- **Late processing:** a user action whose due date has already passed → propose it with "was this done?" (done → straight to Completed; not done → re-date). `Created:` = processing date.
- **Dry run** (testing the skill): write nothing, delete nothing — including the input file.
- If the input has an ID (Drive / Wispr), record it in the caller's state file after processing (`outcome: processed`, `via: /brain:transcript`) so `/brain:meeting-sync` doesn't re-surface it. If a claim file is used (`~/.claude/state/meeting_claims.json`), add it there too (id → vault + agent, no title).

## ⚠️ MANDATORY STEP-ZERO — output this block before touching any file

```
TRANSCRIPT RUN — [Meeting name] — [Date]
Caller: [agent name / default] · Profile: [path read this run]
Skill file read: ✓ (re-read this session, not from memory)
Memories scanned: [specific files from the profile's pre-flight list + topic memories] (mark any with last_verified > 90 days as `(stale)` — use them, but list them for the session-end re-verify)
[profile's extra Step-Zero lines]
Steps to execute: lane · reconcile · actions · notes · people · [profile extras] · log · cleanup
```

Do not proceed until this block is out. One block per meeting in a batch. If "Memories scanned" says "all relevant memories" or is empty, re-scan and fix it first. **This block is the contract** — if it is absent, the routine has not started.

## Running inside /brain:meeting-sync (batch mode)

If `/brain:meeting-sync` invoked you, its batch table overrides **where decisions land** — ambiguous items and status flips go to its deferred queue instead of stopping to ask; act-and-inform edits the profile allows (e.g. a self-patterns summary edited in place) still happen and are reported; the log gets one entry for the whole run; the closing block is replaced by its run report. **Nothing else changes** — every file still gets written, and key points still appear per meeting. Outside `/brain:meeting-sync`, ignore this section.

## The steps

Execute every step the profile defines. A step with nothing to do is reported as such ("Contacts: no external contacts") — never silently skipped.

### Step 1 — Already processed? Then lane check
**Meeting-level dedup first:** check the caller's state file (by Drive/Wispr ID), grep the destination NOTES for an entry with this date + topic, and grep `CHANGELOG.md` for the meeting / file name. Already processed → stop and say where it lives (offer to reprocess only if the user asks).

**Lane check:**
Is the meeting in the profile's **Owns**? Use the Wispr folder if there is one; otherwise judge by content.
- Not this caller's → name the owning vault/agent, record only what the profile's not-mine rule says (usually "routed to X"), and stop. Do not summarise another lane's meeting.
- Unclear → ask the user (one question, with a recommendation).

### Step 2 — Reconcile existing actions (FIRST, before extracting anything)
Read the trackers the profile lists, end-to-end, this turn. For every open item touching this meeting's topic or product, or a person **with attributed content** in it (an invite list alone doesn't count) — whether or not anything new came out of it — decide: **DONE · KILLED · PROGRESSED · BLOCKED/AT RISK · SUPERSEDED · NO CHANGE**. A meeting is at least as likely to close work as to create it.
- **Auto-close only on clear evidence:** verdict DONE + the **verbatim** transcript (never a summary or "Decisions" block — they harden hedges into commitments) has **the item's Owner or the user** stating completion in the past tense (anyone else = a third-party report → propose) + the item is unambiguous. Report each with the quote and an undo.
- Everything else → proposed one-by-one. On approval, PROGRESSED / BLOCKED on **another agent's** tracker = append one dated line to that item, tagged with the caller (`[<caller> YYYY-MM-DD: …]`); never rewrite their item. Where closes land is in the profile.
- Deferred / Killed items with a reactivation trigger that the meeting hits → flag to that tracker's owner (proposal), don't reopen.

### Step 3 — New actions
Per the profile: which tracker and section, which schema, the ownership bar and the approval rule. Shared rules:
- **Dedup before add** — grep the tracker first; classify SKIP / UPDATE / CLOSE + REPLACE / ADD and show it.
- **The user's tracker holds the user's items.** What others committed to goes where the profile says (NOTES block, a `Waiting on` section, an agent tracker).
- **Never invent an owner or a date.** Unclear → propose, with the gap stated.
- **Check it isn't already done.** Before proposing any commitment (especially from an older meeting), grep `CHANGELOG.md` and the relevant agents' recent outputs / Completed sections for the same deliverable. Already delivered → log "covered by <file / agent, date>", don't propose. (Real failure: a one-pager proposed as a new action two days after another agent had delivered it.)

### Step 4 — Notes
Per the profile's routing table and entry format. Shared rules: ordered by **meeting date**, newest first (same date → the one processed last on top); bump the file's `Last updated:`; decisions, blockers, shifts, critical context — no small talk; never create a new NOTES file without approval; ambiguous → ask with options. Give the entry a **source line** (Wispr share link / Drive doc / "pasted" / "file drop <name>, deleted", plus `paraphrase only` or `verbatim`, plus any transcription mangling, e.g. a name the transcriber consistently mishears). Empty Commitments/Decisions blocks are omitted, not written as "none".

### Step 5 — People
Per the profile (direct-report profiles and the user's self-assessment, interview debrief, People.md, candidate hand-off…). **Use the headings the target file already uses** — the file's house format wins over any list in the profile. Shared rules:
- **Only what the transcript supports.** Paraphrased notes support "what someone did", not quotes. No dialogue attributed to the user → no self-assessment; say so.
- **Names: best guess, don't ask.** Grep memory and the vault, then write the closest match and mark it once in the source line (`"<as heard>" → <closest match> (best guess)`). No match at all → keep the name as heard. **Ask only when it's critical**: the person would own an action item, appear in a people/HR file, or receive a send. Otherwise never put a name in the decision queue.
- **Never assume who gave feedback** unless the user confirms.

### Step 6 — Profile extra steps
Run every extra step the profile lists, in its order (e.g. a leadership-quotes file, a contacts-DB interaction log, a financials file, a private-content rule). These are the steps most often skipped — the closing block must account for each.

### Step 7 — Log
The profile's log (`CHANGELOG.md` by default): one entry per meeting (one per `/brain:meeting-sync` run), under the **processing** date, with the caller's tag, ≤ 600 characters. A new file created → also update the relevant `INDEX.md`.

### Step 8 — Cleanup (no raw transcripts)
No vault keeps raw transcript files. If the input came from a file on disk (an `Inbox/transcripts/` drop, an export in a temp dir), delete it once processed. Pasted → nothing to delete. Wispr and Drive are the archive; the NOTES entry links to them.

## Closing — always

```
TRANSCRIPT COMPLETE — [Meeting name] — Caller: [name] · Profile: [path]
Lane: [mine / routed to X]
[the profile's closing-block lines, one per step]
Cleanup: [file deleted / pasted, no file]
```
Any step reading "skipped" is a failure — do it now before continuing.

Then inline in chat, every time, even for meetings the user didn't attend:
1. **Key points** — ≤ 5 bullets, decisions first.
2. **The profile's inline items** (e.g. the user's self-assessment, the interview-debrief headline).
3. **Proposals awaiting approval** — one at a time, each with a recommendation.

Closing ≤ 25 lines. The file holds the detail; chat holds the headline.

## Tone

Direct, concise, executive-level. Lead with the answer.

## Anti-patterns

- **Working from memory** of this skill or the profile. Re-read both every run.
- **Running without a profile**, or with another caller's profile.
- **Processing another lane's meeting** "because it was there".
- **Skipping the reconcile step** because nothing new came out of the meeting.
- **Storing a raw transcript.**
- **Fabricating names, owners, dates or attributions.**
- **Editorialising** outside the assessment sections.
