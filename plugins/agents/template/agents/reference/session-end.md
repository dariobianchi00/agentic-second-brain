# Session End Protocol

Reference for `agents/CONVENTIONS.md` (the master). Loaded on demand, not at startup.

## Session End Protocol

Triggered by `/agents:start <name> close`, `/agents:start <name> end`, `/agents:start <name> wrap up`, or when {{PRINCIPAL}} signals the session is ending.

### Step 1: Review the session

Scan the full conversation and identify:
- Topics discussed
- Decisions made (with rationale)
- Action items created or completed (who, what, by when)
- Open questions or unresolved items
- Communications sent or received
- Documents created, updated, or shared
- Any changes to project state
- **Session focus reconciliation:** Which declared focus items were addressed? Which were not, and why? Did any side topics emerge that need P1/P2 actions?

### Step 2: Update action tracker

Update `actions.md`:
- Add new action items to Open, each Action cell starting with a bold label (master § actions.md: 3–8 words, under 60 characters, no dates or status words). Give any row you touch a label if it has none
- Move completed items to Completed with date
- Update statuses and flag items at risk or overdue. Each status starts with one of the four states (master § actions.md): `Not started`, `In progress`, `Waiting on <who>`, `Parked`; a short note may follow ` — `. Bring any row you touch onto them
- Rewrite the `Next session:` line under `Last reviewed:` with the focus you would propose next time, up to three items (`Next session: #14 Career sweep → #11 close worktrees`). One line; add it if the tracker has none. {{PRINCIPAL}} reads it from the dashboard without starting you, so make it what you would actually declare.

### Step 3: Review autonomy

Check if {{PRINCIPAL}} gave any explicit signals about authority levels during the session:
- "Good call, just do that next time" or similar → **promotion**
- "Check with me before doing that" or similar → **demotion**
- Agent felt uncertain about authority level → note for clarification next session

If any changes occurred, update `autonomy.md` (both the level sections and the changelog).

### Step 4: Create session memory

Write to `memory/sessions/YYYY-MM-DD-<topic>.md`:
```yaml
---
date: YYYY-MM-DD
type: session
session_id: ${CLAUDE_SESSION_ID}
resume: claude --resume ${CLAUDE_SESSION_ID}
herdr_pane: ${HERDR_PANE_ID}   # omit the line outside Herdr
---
```
**Always write this file** — every interactive session that is closed gets one, however short or read-only it was. A session with no file is invisible to the next startup and shows as a gap in the health check.

**Multi-day sessions need `spans:`.** Before writing, work out the session's first day: the `[session span]` line the hook injected on the close prompt if there is one; otherwise the earliest date in this conversation (startup step 1 `date` output, `[gap notice]` lines, dated CHANGELOG entries you wrote). If it is not today, add a line at the very start of a line — in the frontmatter for the YAML form, as the first body line for the short form — exactly:
```
spans: YYYY-MM-DD → YYYY-MM-DD
```
(first day → today, ISO dates, `→` or `->`). The health check reads only `date:`, `spans: A → B` at line start, and the date in the filename; every CHANGELOG day carrying `[<Name>]` that none of them covers is reported as a gap. Set `date:` to today (the close day) and name the file with today's date. If a session memory for this same `session_id` already exists (the session was wrapped earlier and then continued), update that file in place — extend its `spans:` to today and add the later days' topics and decisions — instead of writing a second file.

Include topics discussed, decisions made, and open questions. Do NOT duplicate action items — reference `actions.md`.

Never invent a `session_id`. In Claude Code, if `${CLAUDE_SESSION_ID}` is empty, the ID is the filename (without `.jsonl`) of the active conversation file. Look it up from the workspace root:
```bash
find ~/.claude/projects/-$(pwd | tr '/' '-' | cut -c2-) -name "*.jsonl" -mmin -60 -not -path "*/subagents/*" | head -1 | xargs basename | sed 's/.jsonl//'
```

**Other harnesses.** The `session_id` and `resume` lines depend on the CLI you are running in. Use the row that matches; if the harness shows no session ID, write `session_id: none`.

| Harness | `session_id` | `resume` |
|---------|--------------|----------|
| Claude Code | `${CLAUDE_SESSION_ID}` or the lookup above | `claude --resume <id>` |
| Codex | `none` unless shown | `codex resume` (picker) |
| Gemini CLI | `none` unless shown | `gemini --resume` (pick from `gemini --list-sessions`) |
| OpenCode | `none` unless shown | `opencode run --continue` |

If the session produced durable rules or decisions, write a separate entry to `memory/standing/` and add it to the Standing section in MEMORY.md. If it produced exact detail the agent will need only in some sessions (an ID, a recipe, an incident fix), add it to the matching section of a `reference/` file instead, with a pointer from the standing rule (master conventions § Agent reference).

### Step 5: Update memory index

Add a one-line summary with link to `MEMORY.md` under the appropriate section.

### Step 6: Update project files

Read `context.md` for the list of project files. Update relevant project logs and status files if progress was made.

### Step 7: Commit and push

Stage all session changes, commit with a descriptive message, push to origin.

### Step 8: Confirm

Before confirming, re-open the session memory file from step 4 and check it exists, has a `date:` line, and — if the session ran over more than one day — a `spans:` line covering first day → today. If any check fails, fix the file first. Then show {{PRINCIPAL}} a brief summary of what was saved (including the session memory path and its `spans:` line, if any) and the current action item status.
