---
name: analyze
description: Structured, verified analysis of customer research and product data — interviews, surveys, feedback, transcripts, metrics, cohorts, funnels, or a mix. Use when the user asks to analyze, dig into, make sense of, or find insights in a dataset or a set of interviews ("/brain:analyze", "analyze this data", "what do these interviews say", "why is X dropping"). Pulls data from connected analytics tools (e.g. Metabase, Amplitude, PostHog, BigQuery) or files; every quote and number is checked against source; findings carry confidence ratings; answer first. Not for financial or HR data.
---

# /brain:analyze

Structured data analysis with verification — for customer research, product metrics and mixed datasets.

## Method

Applies Caitlin Sullivan's AI-analysis framework (Lenny's Newsletter, 2026) against four predictable failure modes:

1. **Invented evidence** — the model generates plausible quotes instead of retrieving real ones, or stitches "Frankenstein quotes" from several sources. *Counter:* strict quote rules (Step 3) + a verification pass that confirms every quote verbatim or marks it `NOT FOUND` (Step 4).
2. **Generic insights** — consensus patterns ("price is a factor", "users value reliability") that could apply to any product. *Counter:* load four pieces of context before analysing — project, decision, product context, who generated the data (Step 1).
3. **Signal that doesn't guide decisions** — ambiguous answers compressed into meaningless averages. *Counter:* explore multiple readings of ambiguous answers and their product implications; weight evidence by relevance to the decision; segment before averaging.
4. **Contradictory insights** — conflicting themes presented side by side without weighing. *Counter:* explicitly hunt for contradictions, explain why they exist, and say which evidence better predicts behaviour.

Prompting principles that run through every step: define ambiguous terms explicitly · load context before analysis · demand evidence chains from conclusion to source · separate retrieval from generation (verify in a separate pass) · admit messy data rather than forcing artificial structure.

**Scope:** customer research + product metrics. Not financial or HR data.

## Data sources

Use whichever of these the user has connected; none is required. Never guess hosts, project IDs, table names or event names — discover them.

| Source | How |
|---|---|
| Metabase (MCP, if connected) | Read the instance's glossary/definitions first (they override yours), then run a structured query; raw SQL only when the query builder can't express it |
| Amplitude (MCP, if connected) | Get the org/project context first; discover event and property names, never guess them |
| PostHog (MCP, if connected) | Use the MCP's query/exec command; discover event names first |
| BigQuery (if the `bq` CLI is configured) | `bq query` against the dataset the user names |
| Files (CSV, Excel, pasted numbers, screenshots, transcripts) | Read; compute with Python |

## Workflow

Six steps, in order.

### Step 1: Context

Establish four things, filling gaps from the vault (relevant `NOTES.md`, prior analyses) before asking:

1. **Project** — what is being analyzed.
2. **Decision** — what this analysis will inform.
3. **Product context** — domain, constraints, benchmarks.
4. **Data** — who or what generated it, sample size, selection, freshness.

Play it back in one block and wait for the user's confirmation:

```
## Context
**Project:** … · **Decision:** … · **Product context:** … · **Data:** …
Confirm or adjust?
```

Then ask **where to save** (Step 6 rule) — in the same message is fine.

### Step 2: Data

1. **Inventory** — one table: source, type (qual/quant), records, quality notes.
2. **Quantitative:** compute in Python straight from the query result or file. Keep the query or script so every number can be re-run. The vault gets **aggregates only — never customer-level rows** (emails, names, IDs).
3. **Qualitative:** tag each item with a participant ID and timestamp where available. Quotes stay verbatim.
4. Save `[Topic]_Raw_Data.md` in the chosen folder: the aggregates, the queries/scripts, and (qual) the tagged excerpts. This is the source for verification in Step 4.

### Step 3: Analysis

**Qualitative**
- Themes grounded in specific evidence, not generic patterns.
- Quote rules: start where the thought begins and run until it ends; keep the reasoning, hedges and emotional language; cite `[P02 ~14:30]`; never combine statements from different sections or participants; split quotes longer than 3 sentences.
- Consider more than one reading of ambiguous answers.
- Weight evidence by relevance to the decision.

**Quantitative**
- Descriptive stats first (means, medians, distributions).
- Segment before averaging — never report an overall average without the segments.
- Flag small samples and high variance.
- Compare against benchmarks in the vault where they exist.

**Mixed** — analyze each separately first, then cross-reference: do the numbers support what people say? Where do they diverge?

### Step 4: Verification

Every analysis is verified. **When the output will be shared with anyone other than the user, a subagent with fresh context runs this step** — give it only the raw data file and the draft findings (no conclusions or framing in the prompt), and have it report each check as pass / fail / NOT FOUND. For an analysis only the user reads, run the checks yourself.

- **Quotes:** each exists verbatim in the source; paraphrases flagged with the actual wording; unverifiable claims marked `NOT FOUND`; each theme backed by 2+ independent data points.
- **Numbers:** re-run the calculations; percentages add up; comparisons use the same baseline; metrics that mislead without context are flagged.
- **All findings:** check for contradictions — flag the tension, explain it, say which evidence better predicts behaviour. Apply the "so what?" test: if a competitor could claim the same insight about their product, cut it.

### Step 5: Output

One file, answer first.

```markdown
# [Analysis Title]

Last updated: [date] · **Decision:** [from Step 1] · **Data:** [one line]

## The answer
1. **[Finding]** (🟢 High) — [one-sentence implication]
2. **[Finding]** (🟡 Medium) — […]
3. **[Finding]** (🔴 Low) — […]

**Recommendation:** [2–3 sentences]
**Key risk:** [biggest uncertainty]

## Findings

### 1. [Specific, actionable title]
**Confidence:** 🟢 High · **Evidence:** [N sources, N data points]
[Finding with specific evidence]
> "[Verbatim quote]" — [P02 ~14:30]
**Metric support:** […] · **Implication:** […]

## Contradictions & tensions
| # | Tension | Evidence A | Evidence B | Assessment |

## Confidence summary
| # | Finding | Confidence | Evidence count | Verified |

## Limitations
1. [Sample size, freshness, selection bias, what this cannot answer]
```

The answer section must stand alone. If an HTML or PDF version is wanted, follow the vault's design system if it has one, and use the user's document-conversion tool (e.g. `/brain:gdocs`, if installed).

### Step 6: Storage & handoff

**Ask the user where to save — before writing anything** (Step 2's raw data included). One line, with a suggested folder: *"Save to `<suggested folder>`? Or tell me where."* Suggest from the topic and the vault's folder map in `CLAUDE.md`:

| Context | Suggest |
|---|---|
| Work product or area | `<work area>/<Area or Product>/Analysis/` (cross-cutting: `<work area>/Product/Analysis/`) |
| Anything that belongs to a different vault or project the user keeps separate | Not this vault — say so and ask |

Wait for the answer; never pick the folder silently.

**Naming:** `[Topic]_Analysis_[YYYY-MM-DD].md` + `[Topic]_Raw_Data.md` alongside.

**After saving:**
1. Update the folder's `INDEX.md` and add a `CHANGELOG.md` entry.
2. Propose any action items one at a time, per the vault's action-item approval flow.
3. Show "The answer" section in chat.

## Confidence ratings

| Level | Criteria |
|---|---|
| 🟢 High | 5+ independent data points, consistent across sources, verified |
| 🟡 Medium | 2–4 data points, mostly consistent, minor gaps, partly verified |
| 🔴 Low | 1–2 data points, conflicting or unverified, or inferred from limited data |

## Anti-patterns

1. **Generic insights** — "users want a better experience" is not a finding. Say what experience, who, and why it matters for the decision.
2. **Frankenstein quotes** — never stitch statements from different parts of a transcript or different people.
3. **Consensus bias** — the most common theme is not automatically the most important; outliers often carry the actionable signal.
4. **Premature averaging** — a 50% average can hide a 90/10 split that changes the decision.
5. **Unweighted contradictions** — say which evidence is more reliable and why.
6. **Missing "so what?"** — a finding that doesn't inform the decision gets cut.
