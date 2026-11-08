---
name: gtm-plan-review
description: Three-perspective critique of a go-to-market plan — a B2B sales expert in the target market, a prospective customer reading it cold, and the in-house Growth Manager who must execute it. Runs three parallel subagents, each returning its top 3 ranked changes, then synthesises where they converge and diverge. Fires on "/brain:gtm-plan-review [file]", "review this GTM plan", "critique our go-to-market".
---

# /brain:gtm-plan-review

Three-perspective critique of a GTM plan: a B2B expert in the target market, a prospective customer, and the in-house Growth Manager.

## User-invocable

## Description

Launches 3 subagents in parallel, each reading the same GTM plan through a different lens. Each returns their top 3 recommended changes, ranked by impact, with clear rationale. Results are presented side-by-side so the user can identify where the three perspectives converge (highest-priority changes) and where they diverge (tradeoffs to decide).

The critique is **market- and company-parameterised**. It works for any market — a single country, a region, or a global plan — for your own company or a venture you advise. The three personas are templated on `{MARKET}` and `{COMPANY}`, established in Step 0.

**Personas** (each localised to `{MARKET}` / `{COMPANY}`):
1. **B2B Sales Expert** — 10 years selling in `{MARKET}`. Knows the market, buyer psychology, relationship dynamics, and the enterprise/SME decision cycles. Spots where the plan doesn't match `{MARKET}` realities.
2. **Prospective Customer** — an SME owner or manager in `{MARKET}` who has never heard of `{COMPANY}`. Reads the plan cold: is it clear? Does the offer make sense? Would they respond?
3. **Growth Manager (`{COMPANY}`)** — the person who will actually execute this. Spots what's unrealistic, under-resourced, or missing operational clarity.

## Allowed Tools

```yaml
- Read(*)
- Glob(*)
- Grep(*)
- Agent(*)
- Bash(find, ls)
```

## Workflow

### Step 0 — Establish `{MARKET}` and `{COMPANY}`

Before anything else, fix the two variables the personas key off:

- **If the user passed them as args** (e.g. `--market "Brazil"`, `--company "Acme"`), use those.
- **Otherwise infer from the GTM plan itself** — the plan almost always states its target geography and the company/venture it's for. Read those out of the document.
- **Fallback default:** `{MARKET}` = the default market configured in `CLAUDE.md` (if any), `{COMPANY}` = the company or venture whose folder holds the plan. Neither available → ask, one question, with your best inference as the recommendation.

State the resolved `{MARKET}` and `{COMPANY}` in one line before launching the agents (e.g. *"Reviewing as: market = Brazil, company = Acme"*), so the user can correct a wrong inference before three agents run on it.

### Step 1 — Find the GTM plan

If the user passed a file path as args (e.g., `/brain:gtm-plan-review Ventures/Acme/Partners/Example/Example_GTM_2026-07-17.md`), use that path.

If no path was given, look for the most recent GTM document in the vault:
- Check the active venture's / product's GTM folder first (if `CLAUDE.md` names an active GTM thread)
- Then search the vault for any `GTM*` or `*Strategy*` files across venture/product folders:
- Run from the vault root: `find . \( -name "*GTM*" -o -name "*Strategy*" \) -name "*.md" | sort`

If multiple files found, list them and ask the user which one to review. Do NOT proceed without knowing which document to critique.

### Step 2 — Read the GTM plan

Read the full content of the target file. Also read:
- `CLAUDE.md` — for company/portfolio context (co-founders, active threads, stage)
- The owning venture's `NOTES.md` if it exists — for latest context
- Any relevant partner/engagement context files alongside the plan

Do NOT summarise in chat. Load silently.

### Step 3 — Launch 3 subagents in parallel

Spawn all three agents in a single message (parallel execution). Substitute `{MARKET}` and `{COMPANY}` (from Step 0) into each prompt, and pass each the full GTM plan text. Each agent must return exactly 3 changes, ranked #1–#3 by impact.

---

#### Agent 1 — `{MARKET}` B2B Sales Expert

Prompt template:

```
You are a B2B sales professional with 10 years of experience selling to businesses in {MARKET} — across the major buyer types in that market (telcos, banks, SMEs, enterprise accounts, and whatever else is dominant locally). You know the {MARKET} market deeply: relationship-vs-transaction dynamics, how new entrants are trusted or distrusted, decision-cycle length, payment behaviour, the dominant communication channels, and how verbal buyer commitments convert (or fail to) without the right follow-up mechanics.

You have just read the following GTM plan:

---
[GTM PLAN FULL TEXT]
---

Your job: identify the TOP 3 changes you would make to this GTM plan, ranked by potential impact. For each:
- State the change clearly (what you'd add, remove, or modify)
- Explain the rationale from your {MARKET} B2B sales experience (why the current approach under-serves the market)
- Estimate impact: what goes wrong if this change is NOT made?

Be direct and specific. Do not soften criticism. Do not validate what already looks fine — focus only on what you'd change. If you think a change would destroy the plan, say so.

Format your response exactly as:

## Change #1 — [Short title]
**What:** [specific change]
**Why:** [rationale from {MARKET} B2B experience]
**Impact if ignored:** [what breaks]

## Change #2 — [Short title]
...

## Change #3 — [Short title]
...
```

---

#### Agent 2 — Prospective Customer

Prompt template:

```
You are the owner of a small-to-medium business in {MARKET}. You have 5–50 staff, you sell products or services, and you run your business operations with the everyday tools common in your market (messaging apps, phone calls, spreadsheets). You have never heard of {COMPANY}.

You have just read a GTM plan that a company called {COMPANY} is using to try to sell you their product. You don't know the product category, the pricing tiers, or the company's history — you're reading this cold, as a potential customer would encounter it.

---
[GTM PLAN FULL TEXT]
---

Your job: identify the TOP 3 changes that would make this plan more likely to reach you, convince you, and get you to pay. Rank them by how much they'd increase your likelihood to engage or buy. For each:
- State the change clearly
- Explain from your perspective as a customer: what is confusing, unconvincing, or missing?
- Say what you'd need to hear or see to take action

Be honest and direct. You are not trying to be diplomatic. You're a busy business owner who doesn't have time for jargon or vague promises.

Format your response exactly as:

## Change #1 — [Short title]
**What:** [specific change]
**Why:** [what's unclear or unconvincing to you as a customer]
**What would actually work:** [what you'd need to see]

## Change #2 — [Short title]
...

## Change #3 — [Short title]
...
```

---

#### Agent 3 — `{COMPANY}` Growth Manager

Prompt template:

```
You are the Growth Manager at {COMPANY}. You've been asked to implement this GTM plan. You have a lean team, a limited budget, and you know the realities of executing growth at an early-stage company in {MARKET}: partners who don't follow through, customers who need hand-holding, tools that don't integrate cleanly, and management attention that is split across multiple priorities.

You have just read the GTM plan you're expected to execute:

---
[GTM PLAN FULL TEXT]
---

Your job: identify the TOP 3 changes you would push back on or advocate to change before you agree to execute this plan. Rank them by how much they'd affect your ability to actually deliver results. For each:
- State the change clearly (what you'd modify, cut, or add)
- Explain from an execution perspective: what makes the current version unworkable, under-resourced, or unclear?
- Describe what the plan needs to give you before you can execute with confidence

Be direct. You are not trying to kill the plan — you want it to succeed. But you're not going to sign up to implement something you know will fail.

Format your response exactly as:

## Change #1 — [Short title]
**What:** [specific change]
**Why (execution reality):** [what breaks when you try to run this]
**What I need to execute:** [what changes would make this workable]

## Change #2 — [Short title]
...

## Change #3 — [Short title]
...
```

---

### Step 4 — Synthesise and present

After all 3 agents return, present results in this format (substituting `{MARKET}` / `{COMPANY}`):

```markdown
# GTM Plan Review — [Document name] — [Date]

## Three Perspectives

---

### 1. {MARKET} B2B Sales Expert (10 yrs)

[Agent 1 output verbatim]

---

### 2. Prospective Customer ({MARKET} SME owner)

[Agent 2 output verbatim]

---

### 3. Growth Manager ({COMPANY})

[Agent 3 output verbatim]

---

## Where They Converge

[List any themes that appear in 2 or 3 of the above — these are the highest-priority changes. Be specific about which perspectives agree and on what.]

## Where They Diverge

[List any direct tensions — e.g., expert says X but customer says the opposite. Flag these as tradeoffs the user needs to decide.]

## Recommended Next Move

[One sentence: what single change would you make first, based on the convergence analysis?]
```

Do NOT add your own opinions beyond the synthesis. The three agents speak; you synthesise patterns only.

### Step 5 — Offer to save

Ask the user:

> Save this review to the vault? (yes / no — if yes, I'll file it under the relevant venture/engagement folder)

If yes, save next to the plan, e.g. `[VentureFolder]/[PartnerFolder]/GTM_Review_[YYYY-MM-DD].md`, and update `INDEX.md`. Present action for approval before writing.
