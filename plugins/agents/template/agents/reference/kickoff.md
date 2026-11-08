# Kickoff — the first session of the day

Reference for `agents/CONVENTIONS.md` § Startup Sequence step 13b. Loaded when `kickoff:` is set and the command exits 0. The per-agent **overlays** live in the workspace (the file the workspace's `kickoff:` entry points at); this is the spine every agent runs.

## When it fires

Once per agent per calendar day, decided by the kickoff command from a state file — never inferred from `memory/sessions/` (those are written at session end, and read-only sessions leave none). Exit `0` + full scan = due. Exit `10` = already ran today → skip to the priority declaration. {{PRINCIPAL}} can force it any time ("kickoff", "good morning", "start the day").

## The spine — identical for every agent

1. **Run the scan.** It emits the deterministic report: overdue and due-today action items, stale open actions (>14 d), standing memory past 90 d, whether this ISO week's retro is written, open handoffs and debates, changelog rotation, index drift.
2. **Read it; do not re-derive it.** If the script errors, say so — never fall back to hand-deriving and never report "all clear" on a failed scan.
3. **Retro gate.** If the current week's retro is unwritten and this agent is the scope's `chief-of-staff`, write it **before** other work (§ Weekly Retro).
4. **Handoffs and debates.** Surface open handoffs addressed to this agent — for some agents that *is* the work queue — and open debates in scope.
5. **Scope overlay.** Run the agent's own block from the workspace overlay file, if it has one.
6. **Priority declaration.** Up to 3 focus items, most consequential first; get {{PRINCIPAL}}'s agreement before starting. Never optional, never removed.

## The chief-of-staff ACTIONS block (cross-agent, every kickoff)

The `chief-of-staff` agent reads the workspace action list, every agent's `actions.md` in its scope and the open HANDOFFS **that turn** — the scope scan command, if the workspace has one, provides the inputs deterministically — and prints one block, numbered continuously so {{PRINCIPAL}} can reply `ok all` · `ok 2,5` · `7 push Fri` · `9 kill`:

```
ACTIONS — <Day DD Mon>
YOU            overdue + due in the next 7 days (rolling) + any item {{PRINCIPAL}} must personally decide or send
               + one count line: "<n> undated · <n> untouched 14d+"
AGENTS         P1s only, per agent; stale flags (no session in 7d+, item untouched 14d+)
HANDOFFS OPEN  From → To — title — days open — whose gate it waits on
CLOSED         auto-closed since last kickoff — evidence — undo?
NEEDS YOUR CALL
```

**Every line carries a recommendation** (`→`): **DO** (within the agent's mapped level; "ok" runs it) · **PUSH** (new date + the dependency; a third push becomes a KILL rec) · **DELEGATE** (to an agent or a person — the agent writes the handoff/draft) · **KILL** (one line why) · **YOU** (only when the decision or send is genuinely {{PRINCIPAL}}'s — then say what the agent would do in their place). "ok" never sends anything external; sends stay at draft. Cap ~25 lines; this block is exempt from the brief cap below, nothing else is.

**Emoji on every line, from a fixed legend — never improvised**:
- Sections: 👤 YOU · 🤖 AGENTS · 🔁 HANDOFFS · ✅ CLOSED · ❓ NEEDS YOUR CALL
- When: 🔴 overdue · 🟠 today/tomorrow · 🟡 this week · ⚪ later/undated · 🔥 a workspace-defined always-surface item (any date)
- Rec: ▶️ DO · ⏭️ PUSH · ➡️ DELEGATE · 🗑️ KILL · 🙋 YOU
- State: ⏳ waiting on · 🅿️ parked · ⚠️ stale/broken

## Output contract

Kickoff is a **brief, not a report**. ≤12 lines before the priority declaration. Lead with the single most load-bearing item. Clean checks get one line in total. Detail belongs in the files the scan points at — name the file, don't re-narrate it. If there is nothing to raise, say so in one line and declare priorities.

## What Kickoff must never do

Cross its scope. Re-derive by hand anything the scan computes. Report a clean scan when the scan failed. Auto-close, auto-kill or auto-re-date anything — it surfaces, {{PRINCIPAL}} disposes. Run on the second or later session of a day unless asked.
