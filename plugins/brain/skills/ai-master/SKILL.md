---
name: ai-master
description: Turns a rough AI idea (pasted text, article, link, or half-formed thought) into a workable "experiment card" grounded in the user's actual setup — their installed skills, agents, MCP servers, scheduled routines, and vault conventions. Files it into Knowledge/AI-Master/ as a status-tracked backlog item. Fires on /brain:ai-master, "expand this AI idea", "add this to AI-Master", or "what should I try next with AI". Supports `deep` (build spec) and `list` (show backlog) modes.
user-invocable: true
allowed-tools:
  - Read(*)
  - Write(*)
  - Edit(*)
  - Glob(*)
  - Grep(*)
  - Bash(ls*, cat*, date*, grep*, find*)
  - WebFetch(*)
  - WebSearch(*)
argument-hint: '<rough idea text or link>  |  deep <slug or new text>  |  list'
---

# /brain:ai-master — expand AI ideas into things you can actually build

The user captures rough AI ideas they want to try. This skill turns each one into a **workable experiment card**, grounded in their real setup, and files it into a status-tracked backlog. When an idea graduates, `deep` produces a build-ready spec.

**Home folder:** `Knowledge/AI-Master/`
**Backlog spine:** `Knowledge/AI-Master/INDEX.md`
**Templates:** `_TEMPLATE_experiment_card.md`, `_TEMPLATE_deep_spec.md` (in that folder)

> **First run:** if `Knowledge/AI-Master/` or its templates don't exist, create the folder, an `INDEX.md` with three sections (**Backlog** table, **Seed candidates** list, **Done — what I learned** table), and the two templates from the section lists in this skill (card: Summary · ① Fit · ② Effort-to-value · ③ Learning value · How to try it · First 15-min move · Success signal · Straight talk · Open questions · Retro · Related; spec: Problem/outcome · What we're building and why this shape · Behaviour spec · Build steps · Test/eval plan · Risks · Definition of done). Tell the user you did so.

The point of this skill is **capture with low friction, expansion with high grounding.** Don't over-confirm — write the card, update the index, show the result. Don't fabricate — every "fit" claim must point at a tool that actually exists in the user's stack.

---

## Modes

Parse the argument:

- **`list`** (or `next`) → read `INDEX.md`, show the backlog ordered by *best-to-try-next*, recommend one. No file writes.
- **`deep <slug or text>`** → produce a build-ready spec from an existing card (or fresh text) using `_TEMPLATE_deep_spec.md`.
- **anything else** (the default) → treat the argument as a rough idea and expand it into an experiment card.

If invoked with no argument, ask what idea to expand (or offer `list`).

---

## Default mode — expand a rough idea into a card

### Step 1 — Ingest the raw input
- If the input is **pasted text or a thought**, use it directly.
- If it's a **link/URL**, `WebFetch` it and pull the actual idea (don't guess from the URL).
- If it points at a **vault file**, `Read` it.
- Extract: what the idea *is*, and — if present — why the user flagged it. Don't invent intent they didn't express.

### Step 2 — Survey the user's actual stack (this is what makes the card useful)
Before writing the "Fit" lens, ground yourself in what the user actually has. **Read the live sources each time — never rely on a remembered or hard-coded roster.** Check whichever of these exist:
- **Skills:** list the installed skills — user-level (`ls ~/.claude/skills/`), project-level (`ls .claude/skills/`), and plugin skills (the skills listed as available in this session, e.g. `/brain:*`).
- **Agents + scopes:** the agents table in the vault's root `CLAUDE.md` and `Agents/CONVENTIONS.md` (if present) — canonical roles and scope boundaries. Also `ls Agents/` for what's on disk.
- **MCP servers:** the MCP tools available in this session, plus any MCP/automation doc the vault keeps (e.g. under `Instructions/`, as referenced from `CLAUDE.md`). If none is documented, `claude mcp list` output (ask the user to run it) is the source.
- **Scheduled routines:** `Instructions/Routines/`, `Instructions/scripts/`, and any scheduler register (e.g. `Agents/scheduled-tasks.md`) if present.
- **Conventions:** root `CLAUDE.md` + `Agents/CONVENTIONS.md` (memory schema, action-item format, adversarial mode, one-by-one approvals).

Only cite tools that **exist**. If the idea needs something the user doesn't have, say "new build — no current tool covers this" — that's a valid, honest fit answer. Don't describe a specific agent's role from memory; read it.

### Step 3 — Write the card
Copy `_TEMPLATE_experiment_card.md`. Fill every section. Lead with three lenses (do not add a priority/career lens — this is capability-building):

1. **① Fit to how you work here** — map the idea onto a concrete shape: **skill / agent / scheduled routine / MCP hookup / workflow / prompt-pattern**. Name the specific existing thing it extends or the exact gap it fills. Set the `fit:` frontmatter field accordingly.
2. **② Effort-to-value** — rate effort **S/M/L** and payoff, give a one-line verdict. Set `effort:`.
3. **③ Learning value** — the new AI capability trying this builds (agents / evals / orchestration / MCP / RAG / prompting). Set `learning:` to the one-word capability.

Then: **How to try it** (concrete steps using the user's real tools), **First 15-min move**, **Success signal**, **Straight talk**, **Open questions**, **Retro** (leave BLANK — filled after trying), **Related** (cross-link other notes in `Knowledge/`, existing skills, other cards).

**Straight talk is two-part and mandatory** (adversarial by default): (a) name the idea's **load-bearing assumption** and judge whether it's actually *true* or just hype/vibes — premise-test it, don't assume the source is right; (b) name where **execution** might fail or the cheaper alternative. Never skip either. The premise check is first-class.

Leave the **Retro** block empty on creation — it gets filled after the user actually tries the idea (see close-out below). It is the point of the whole system; do not pre-fill it with guesses.

**Frontmatter:** set `status: expanded`, `created:` and `last_updated:` to today (`date +%Y-%m-%d`), a kebab `slug:`, and `source:`.

**Filename:** `Knowledge/AI-Master/<slug>.md`. If a card with that slug exists, UPDATE it (bump `last_updated`) rather than duplicating — run SKIP→UPDATE→ADD.

### Step 4 — Update the backlog
Add/refresh the row in `INDEX.md`'s **Backlog** table: `Idea (linked) | Status emoji | Fit | Effort | Learning | Updated`. Remove the empty-state placeholder row on first add. Bump the file's `Last updated:` date. If the idea matches a **Seed candidate**, remove it from that list (it's a card now).

### Step 5 — Show it inline
Surface a tight summary in chat: the one-liner, the three-lens verdict, and the **first 15-min move**. Then the one honest challenge from *Straight talk*. Don't paste the whole card back.

---

## `deep` mode — build-ready spec

For an idea that's graduating from "try someday" to "build this":
1. Resolve the target — an existing card slug (Read it) or fresh text.
2. Copy `_TEMPLATE_deep_spec.md`, fill it: problem/outcome, what you're building (and why that shape not the others), behaviour spec, build steps, **test/eval plan** (cheapest test first; for anything agentic, define eval cases up front), risks, definition of done.
3. Write to `Knowledge/AI-Master/<slug>_spec.md`, link it from the card, flip the card's `status: trying`, update INDEX.
4. If the build type is a **skill**, note that a skill-authoring tool (e.g. `skill-creator`, if installed) can scaffold it; if an **agent**, the agent framework's create command (e.g. `/agents:*`, if installed); if a **scheduled routine**, the scheduler the user has (e.g. the `schedule` skill or the repo's macOS-only launchd scheduler).

---

## `list` mode — what to try next
1. Read `INDEX.md` (and card frontmatter if needed).
2. Show the backlog as a numbered list ordered by try-next appeal (bias: high learning value + low effort + clear fit float up; `trying` items surface first as "already in flight").
3. Recommend ONE with a one-line why. State the recommendation explicitly ("Recommendation: X — because…").

---

## Close-out (retro) — when the user says they tried a card
This is the loop that actually builds skill, so treat it as first-class, not housekeeping.
1. Find the card (by slug/title), fill its **Retro** block from what they report: *What happened · What I learned · Did it change how I work here.*
2. Set `status: done` (retro filled) or `status: dropped` (with the reason in Straight talk / a note). Bump `last_updated`.
3. In `INDEX.md`: move the row out of **Backlog** and add a one-liner to the **Done — what I learned** table (Idea · Tried date · What I learned · Changed how I work?). Done cards stay visible — do NOT delete them.
4. If the retro says a real tool changed (a skill/agent/CLAUDE.md edit), that edit is the actual deliverable — make sure it happened or flag it.

---

## Resurfacing — don't let the backlog go write-only
The graveyard risk is real: capture is frictionless but nothing pulls cards back. Resurfacing happens on `list`: when the `🧪 trying` lane is empty, surface one card to try. If asked to run that surfacing (or during `list`, or from a weekly review routine if the user has one), pick the single best try-next card and name the 15-min first move — one nudge, not a dump.

---

## Rules
- **Low friction on capture** — default mode writes the card without a confirm gate (it's the user's own idea in their own vault). Only pause if the slug/title is genuinely ambiguous.
- **No fabrication** — never claim a tool, capability, or benchmark that isn't real. Ground "fit" in the actual stack; if unsure what a tool does, check or say so.
- **Adversarial always** — the *Straight talk* section is mandatory. If you can't find a real weakness in 30 seconds, the idea is under-examined — dig.
- **Scope-neutral** — this is capability-building, not priority tracking. Do NOT auto-add action items. The AI-Master INDEX is the only tracker this skill touches.
- **No CHANGELOG spam** — idea capture lives in the AI-Master INDEX, not the root CHANGELOG. Only log to CHANGELOG if `deep` mode produces a real deployed artifact.
- **One question at a time** if you must ask (rare — capture should be frictionless).
