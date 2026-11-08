---
name: product-feedback
description: >-
  Logs and analyzes qualitative end-user feedback on the products configured
  for this vault. Use this whenever the user pastes or points to a piece of
  user feedback, a review, a support message, a survey response, or an
  interview snippet about one of these products — or says things like "log
  this feedback", "add this feedback for <product>", "here's what a user
  said", "analyze this feedback", "capture this review". It classifies the
  feedback by product, extracts what the customer liked / didn't like /
  suggested features / bugs into categorised key areas (with full quotes kept
  verbatim), assigns a -2..+2 sentiment rating, appends it to the per-product
  Customer_Feedback.md ledger, recomputes that product's feedback counter and
  qualitative sentiment band, and regenerates a Customer_Feedback.html page.
  Use it even for a single short comment. Do NOT use it for meeting
  transcripts (that's /brain:transcript) or quantitative analytics data
  (that's /brain:analyze).
user-invocable: true
allowed-tools:
  - Read(*)
  - Edit(*)
  - Write(*)
  - Glob(*)
  - Grep(*)
  - Bash(python3*, ls*, cat*, grep*, mkdir*, cp*)
argument-hint: '<paste the feedback, or point to a file>'
---

# /brain:product-feedback — Customer Feedback Ledger

Capture and analyze **qualitative** end-user feedback on your product portfolio
into one living, self-updating brain: a master markdown file that is the source
of truth, and an HTML page rendered from it.

This is the messy, human signal — what real users say in reviews, support
threads, surveys, hallway comments, interview snippets. It is deliberately
**not** statistics. Every view of this data carries a loud qualitative caveat so
nobody mistakes "8 people complained about onboarding" for a measured rate.

## Configuration (set once in the vault's CLAUDE.md)

Add a `## Product feedback` block to `CLAUDE.md` (or the calling agent's
context file). The skill reads it every run; it never invents values.

```markdown
## Product feedback
- Products: Acme Notes, Acme Health, Acme Learn      # the only valid product names
- Routing hints: wearables/sleep → Acme Health; notes/memory → Acme Notes
- Feedback file: <work area>/Products/Customer_Feedback.md
- Status page (optional): <work area>/Products/Status.html   # page that should link the feedback page
- Theme CSS (optional): Instructions/Design_System/theme.css  # must define --ds-* variables
- Publish command (optional): the command or skill that deploys the HTML
```

If the block is missing, ask the user for the product list and the file path
(one question at a time, with a recommendation), then offer to write the block.

## Files

| Thing | Path |
|---|---|
| Master MD (source of truth) | the configured feedback file (one file, all products) |
| Rendered HTML (derived) | same folder, `Customer_Feedback.html` |
| Status page (optional, must link the HTML) | the configured status page |
| Renderer + math | `scripts/render_feedback.py` (in this skill) |
| First-run MD template | `assets/Customer_Feedback_template.md` (in this skill) |
| Theme (optional, read by the renderer) | the configured theme CSS; a neutral built-in theme is used otherwise |

## Core principle: synthesise, don't transcribe

This file is a **categorised brief**, not a feedback dump. The Liked / Don't-like
/ Suggested-features sections hold **key areas** — synthesised themes, one line
each, with at most **1–2 references** (who raised it). The raw, verbatim quotes
live in **one place only: the Verbatim section** at the bottom of each product.
If you find yourself pasting every point a user made into Liked/Don't-like,
you're transcribing — stop and categorise.

**Categorise using the `/brain:analyze` method.** Treat theme extraction as a
mini-analysis pass: read the `/brain:analyze` skill and the analysis framework it
references, then apply its discipline — themes grounded in real evidence (2+
data points where possible), the "so what?" test (cut anything generic enough
that a competitor could say it), no Frankenstein quotes (never stitch words from
different people), and verify each verbatim quote exists exactly. For a large
batch you may run the full `/brain:analyze` skill first and fold its findings
in; for one or two items, applying the method inline is enough.

Two kinds of content live in the MD:

1. **Authored** — the key-area lines (Liked / Don't like / Suggested features),
   the Bugs list, and the Verbatim quotes. You write these from judgment. The
   script never touches them.
2. **Derived** — the **per-product** feedback counter and sentiment band. These
   are computed *only* from that product's **Ledger** table. You never hand-type
   them; the script recomputes them every run.

Each logged feedback = **one ledger row** + its content folded into the product's
key areas (and the Verbatim section if it yields a high-signal quote). This
separation is why the counter and band can never drift out of sync, even after
dozens of edits.

**Counts and sentiment are per product — never rolled up.** There is no overall
score. Mixing feedback across different products into one number is misleading
(different products have different users). Each product card stands alone.

**Sentiment is a band, not a score.** The −2..+2 ratings are averaged internally
*within a product* to pick a qualitative band (Strongly positive · Mostly
positive · Mixed · Mostly negative · Strongly negative), but the number is
**never displayed** — anywhere. A precise score on a tiny, self-selected sample
reads as a verdict; the band keeps it honestly directional.

## Workflow

### 1. Confirm today's date
The counter/score lines and `Last updated` are date-stamped. Use the date the
system provides. The render script stamps the date itself, so you don't
hand-edit it.

### 2. Make sure the master file exists
If the feedback file is absent, create it by copying
`assets/Customer_Feedback_template.md` to the configured path and replacing the
`<Portfolio>` placeholder in its title. The template has the header and the
qualitative caveat — no products yet, and no overall block.

### 3. Identify the product
Map the feedback to exactly one of the **configured products**. Use the
configured routing hints. If a single paste covers multiple products, split it
and log each separately. **If the product is genuinely ambiguous, ask — one
question — rather than guessing.** Misfiled feedback poisons a product's band.

If the product has no section yet, add one by cloning the per-product block from
the template (the five subsections + an empty Ledger table).

### 4. Categorise into key areas (the analysis pass)
Don't transcribe — synthesise. For each feedback item, decide what **key areas**
it belongs to and fold it into the product's three theme sections, plus Bugs and
Verbatim. Apply the `/brain:analyze` discipline (see Core principle):
evidence-grounded themes, the "so what?" test, no Frankenstein quotes, verbatim
verification.

- **👍 Liked — key areas** — the synthesised things that are working. One line
  per area: a bold key-area label + a short explanation, with **≤2 references**
  in parentheses (who raised it). Add to an existing area if it already exists
  (append the new reference); only create a new line for a genuinely new theme.
  Optional `#### Category` sub-headings group the lines; the renderer shows them.
- **👎 Don't like — key areas** — friction, confusion, unmet needs, same format.
  Jobs-to-be-done thinking earns its keep here: capture *what the user was trying
  to do that the product didn't let them*, not just the surface complaint.
- **💡 Suggested features** — concrete things to build, phrased as the feature
  (not the complaint). A dislike often has a matching feature here (e.g. dislike
  "notes have no folders" → feature "user-defined folder tree for notes"). One
  line each, ≤2 references.
- **🐛 Bugs** — concrete defects (something broke, errored, behaved wrong),
  severity-tagged: `**[High]**` (blocks the core job / data loss / can't
  proceed), `**[Med]**` (workaround exists), `**[Low]**` (cosmetic). A bug is not
  a dislike — keep it here. Merge duplicates across users and note who hit it.
  Either a bullet list or a 4-column table (`Severity | Bug | Ticket | Status`)
  works; the renderer handles both.
- **💬 Verbatim** — the raw high-signal quotes, the only place full quotes live.
  Mark tone with 😊 / 😞, tag persona + date. **Quote exactly — never paraphrase
  into quotation marks.** Keep the strongest 1–2 per person, not everything.

Reference format: a key-area line names who raised it so it ties back to the
Verbatim section — e.g. `**Persistent memory** — remembers across sessions vs
competitors' amnesia (user A, user B)`. Cap references at two even if more
people said it; the count lives in the ledger, not in parentheses.

Evidence and accuracy are sacred — this file feeds product decisions. Never
invent a like, a dislike, a feature, a bug, or a quote that isn't in the source.
Thin source → thin entry.

### 5. Rate sentiment (-2 .. +2) — the rubric
Assign the feedback a **net** sentiment. This drives the product's band, so apply
the rubric consistently:

| Rating | Meaning |
|---|---|
| **+2** | Delighted — enthusiastic, would recommend, strong emotional positive |
| **+1** | Net positive — happy overall, minor gripes |
| **0** | Mixed / neutral — balanced pros and cons, or purely factual |
| **−1** | Net negative — frustrated, real friction, but still engaged |
| **−2** | Strongly negative — churned, angry, or hit a blocking bug; would not continue |

If one comment both praises and reports a blocking bug, rate the **net** felt
experience (often −1 or 0), but still log the praise *and* the bug in their
subsections. The rating is the emotional bottom line; the subsections are the
detail.

### 6. Write the ledger row + subsection content
Append a row to that product's **Ledger** table:

```
| <next id> | YYYY-MM-DD | +1 | new user | one-line summary |
```

- ID is sequential per product (look at the last row).
- Rating is the signed integer from step 5.
- Segment is the persona/segment if known, else `—`.
- Summary is one tight line — the gist, so the ledger reads as a log on its own.

Then fold the step-4 key areas / bugs / verbatim into that product's subsections.
**Do not type or edit any feedback-count or sentiment line** — those are auto.

### 7. Recompute + render
Run the bundled script. It parses each product's Ledger table, recomputes that
product's counter, derives its qualitative sentiment band from the average rating
(the number stays internal — only the band is shown), rewrites the AUTO lines in
the MD, stamps the date, and regenerates the per-product HTML.

```bash
python3 "<this-skill>/scripts/render_feedback.py" "<vault>/<configured feedback file>" \
  [--theme "<vault>/<configured theme css>"] \
  [--back-link "Status.html" --back-label "Back to status"]
```

It writes `Customer_Feedback.html` next to the MD and prints the updated totals.
The page title comes from the MD's `# ` heading. Branding: with `--theme` (or
`FEEDBACK_THEME_CSS=<path>`) the script inlines that CSS and styles the page with
its `--ds-*` variables, so the page ships as one self-contained file; without
one it uses a neutral built-in theme. Never hard-code colours or fonts in the
script — change the theme file instead. If it reports a parse problem (e.g. a
malformed ledger row), fix the MD and rerun — don't hand-edit the numbers to
paper over it.

### 8. Ensure the status page links it (optional)
If a status page is configured, open it and confirm its navigation contains a
link to the feedback page. If missing, add it as the last nav item, matching the
existing pattern exactly:

```html
<a href="Customer_Feedback.html">Customer feedback</a>
```

### 9. Report inline, then hand off deploy
Surface a tight summary in chat **every time** (the user reads this, not just the
file):
- which product, the rating you assigned and why (one line),
- that product's new count + band (band, not a number — no overall),
- anything notable (a High-severity bug, a churn signal, a standout quote, or a
  newly surfaced suggested feature).

Then remind: the local MD + HTML are updated; to publish the live page, run the
configured publish command (it should ship both `Customer_Feedback.html` and any
modified status page, with its own auth/verify guardrails). This skill does
**not** deploy — that boundary keeps the verified-live logic in one place.

## Scope guardrails

- **Qualitative, always.** Never present these counts/scores as rates,
  percentages of users, or statistical findings. The caveat banner stays.
- **Don't auto-create action items.** Surface a High-severity bug or churn
  signal in the summary, but adding action items is a separate, approval-gated
  step (propose it, don't auto-write).
- **Synthesise, don't transcribe.** Liked / Don't-like / Suggested-features are
  categorised key areas (≤2 refs each), not a dump of every point. Full quotes
  live only in Verbatim.
- **Per product, never rolled up.** Count + band belong to each product. No
  overall/portfolio score.
- **No fabrication.** Likes, dislikes, features, bugs, quotes, and segments come
  from the source only. Thin source → thin entry.
- **One file, all products.** Everything goes in the single master file, broken
  out per product. Don't spawn per-product feedback files.
- **Configured products only.** Never create a section for a product that isn't
  in the configured list — ask, and offer to add it to the config.
- **Numbers are the script's job.** If a count or score looks wrong, the fix is
  in the ledger rows, then rerun — never hand-type the AUTO lines.
