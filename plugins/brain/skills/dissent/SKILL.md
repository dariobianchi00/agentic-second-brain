---
name: dissent
description: Produces the strongest single counterargument to a decision, plan, or framing the user has converged on — a forcing function against agreeing by default. Grounds the dissent in vault evidence (and optionally external sources), names the weakest load-bearing assumption, and labels confidence, in 200 words or fewer. Fires on /brain:dissent or "stress-test this", "argue against this".
user-invocable: true
allowed-tools:
  - Read(*)
  - Grep(*)
  - Glob(*)
  - Bash(grep, find, wc)
  - WebSearch
  - WebFetch
---

# /brain:dissent

Produce the strongest single counterargument to a decision, plan, or framing the user holds. Forcing function for an always-on adversarial mode (if the vault's `CLAUDE.md` defines one).

## Description

When the user presents a decision, plan, or framing that they have converged on — and Claude is at risk of agreeing by default — invoke `/brain:dissent` to force a structured counterargument. Reads relevant vault context (NOTES, people profiles, action items, transcripts) to ground the dissent in evidence. Optionally checks the internet for comp benchmarks, competitor data, regulatory context, or other external grounding. Outputs ≤ 200 words.

Use cases: job-offer evaluation, product positioning calls, responding to pressure from a CEO or board, org changes, pricing decisions, anything where the user has already settled on an answer and wants stress-testing.

## Workflow

### Step 1 — Restate the user's position in one sentence

Verify the framing before attacking it. If unclear, ask one clarifying question and stop. Steelman before dissent — if you can't restate accurately, you can't dissent usefully.

### Step 2 — Ask about internet grounding

Before gathering evidence, ask:

> *"Should I check the internet to ground the challenge?"* (y/n)

Default = no. Say yes when topic involves: comp benchmarks, competitor positioning, market data, pricing comparables, tech architecture trade-offs, hiring/role comparables, regulatory/legal context.

Skip the question entirely (default vault-only) for: internal org decisions, coaching of direct reports, personal/family decisions, vault-internal process changes.

### Step 3 — Gather grounding evidence

**Vault context (always)** — use the folders the vault's `CLAUDE.md` maps for the topic. Typical routing in the starter vault:
- Career / job decisions → the personal area's career folder, `Network/` contacts
- Work / product decisions → the work area's `NOTES.md` + the relevant product or project NOTES
- People decisions (a direct report, a hire) → that person's profile, plus the user's own leadership-patterns file if they keep one (read its summary section only)
- Launches and commitments → relevant product NOTES + `ACTION_ITEMS.md`

Grep the memory index (`MEMORY.md`, and the active agent's memory if running as an agent) for any episodic (`episodic_*.md`) or feedback memory that touches the topic. Cite memory names when used.

**Internet context (only if Step 2 = yes):**
- Use WebSearch first to find credible sources (industry publications, official company data, regulatory filings, salary benchmarks like Levels.fyi / Glassdoor for comp). Skip random blogs and content-marketing posts.
- Use WebFetch only on specific URLs that look authoritative.
- Cap: 3–5 sources max. More breeds noise.
- **Label external claims explicitly** in the dissent output (e.g., "Per Levels.fyi 2026 band for <role, city>..." — not "data shows..."). Distinguishable from vault-grounded claims.

### Step 4 — Identify the weakest load-bearing assumption

One assumption only. The one that, if false, collapses the decision. Not a list of concerns — the single strongest pressure point.

If after Step 3 the position looks sound (no weak load-bearing assumption found), say so explicitly and stop. Output: `Tested, holds up. Considered: [briefly list the assumptions probed]`. This is a valid result — don't manufacture dissent.

### Step 5 — Write the dissent

Format (≤ 200 words total):

```
**Position restated:** [one sentence]

**Weakest assumption:** [the load-bearing claim]

**Why it fails:** [evidence — cite files/memories/patterns; web sources labeled with source name]

**What changes if it fails:** [downstream consequences]

**Confidence in this dissent:** high | medium | low — because [reason]
```

If confidence is `low`, say so and explain why — a weak dissent surfaced as weak is more useful than a strong-sounding bluff.

## Principles

- **Steelman before attack.** Restate the position so the user recognizes it. Strawman dissent is worse than no dissent.
- **One assumption, not a list.** Pick the strongest single pressure point.
- **Evidence over rhetoric.** Cite specific files, memories, dated patterns. "I disagree because X" without grounding is noise.
- **Confidence labeled.** Low-confidence dissents are still surfaced — but flagged. Don't fake conviction.
- **Vault vs internet claims always distinguishable.** Vault evidence has been seen by the user; web evidence hasn't and is noisier.

## Anti-patterns

- **Don't be contrarian for contrarian's sake.** If after Step 3 the position looks sound, say so and stop. "Tested, holds up" is a valid output.
- **Don't pile on.** Multiple dissents dilute the strongest one.
- **Don't restate the user's argument back slightly twisted.** That's strawman, not dissent.
- **Don't exceed 200 words.** The word cap is the discipline. If you need more, the dissent isn't sharp enough.
- **Don't dissent on already-executed decisions.** This is forward-looking pressure-testing, not post-mortem.
- **Don't conflate internet and vault claims.** Always label which is which.

## When NOT to use

- Trivial tactical decisions (where to put a file, which tool to use).
- Decisions the user is openly uncertain about — those need exploration, not dissent.
- Post-mortems on shipped work — different skill needed.
