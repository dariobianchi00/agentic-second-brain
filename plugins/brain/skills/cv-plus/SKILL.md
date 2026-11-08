---
name: cv-plus
description: Tailors the user's CV to a specific job description (JD), selling hard without inventing hard facts. Fires on "/brain:cv-plus <Company>" with a JD pasted, linked or file-pathed, or on "tailor my CV to this JD / role". Reads CV_Master as the fact base, runs a worth-it gate, tailors to the JD, writes the .md to the vault, reports changes and rationale, and only after the user approves the .md renders a parse-checked two-page PDF, plus a short LinkedIn message via /brain:writer.
---

# /brain:cv-plus — Tailor your CV to a JD

Personal-scope skill (career agent, if you run one). Turns a job description into a tailored CV that sells you, plus a short LinkedIn message.

## Configuration (in the vault's `CLAUDE.md` or the career agent's context file)

| Key | Meaning | Example |
|---|---|---|
| `career_dir` | Career folder inside the vault | `<personal area>/Career` |
| `cv_master` | The fact base | `<career_dir>/CVs/CV_Master.md` |
| `cv_pdf_dir` | Where finished PDFs go (can be outside the vault) | `$HOME/Documents/Job hunt/CVs` |
| `target_region` | Where you want to work | `<country or region>` |
| `hard_constraints` | Non-negotiables that cap the worth-it score (visa / work-permit continuity, relocation limits, minimum comp) | `must be employed by a local entity` |
| `comp_floor` | Minimum package | `<currency amount>` |
| `target_map` | Optional file of target segments (rows TM1…TMn) | `<career_dir>/Target_Map.md` |
| `positioning_docs` | Optional brand / positioning files read for emphasis | `<career_dir>/Brand/Positioning.md` |
| `job_tracker` | Optional application tracker | `<career_dir>/Job_Search_Tracker.md` |
| Contact details | For the PDF header: set env vars `CV_NAME`, `CV_LOCATION`, `CV_PHONE`, `CV_EMAIL`, `CV_LINKEDIN` (or pass `--contact=<file.json>` to the renderer) | |

First run: if `cv_master` does not exist, copy `templates/CV_Master.md` there and ask the user to fill it before tailoring anything.

## Hard rules (non-negotiable)
1. **A CV sells. Sell hard, and keep the hard facts true.**
   - **Fixed:** employers, titles held, dates, degrees and numbers. Never invent or change these.
   - **The user's to stretch:** verbs, ownership, scope and framing. Write the strongest version they can defend for five minutes in an interview.
   - **a. The user's word is a source.** If they say it in chat, use it. Don't ask for proof.
   - **b. One flag per claim.** One line on the interview risk, then write it. Don't raise it again unless they do. Step 3 dissent is about whether to apply, never about their claims.
   - **c. Headline:** no title they have never held. Functions and levels may stretch.
2. **CV_Master is the fact base.** Add the user's new claims to it, marked `user, YYYY-MM-DD`. Never delete from it; retracted claims stay with a ⛔ marker. Follow any per-line inclusion rules recorded in it (e.g. "never on a CV", "only for fintech roles").
3. **Two-page hard cap** on the PDF. Cut, don't shrink to illegibility.
4. **PDF is produced ONLY after the user approves the `.md`.** No auto-export.
5. **On every `.md` build, report the change-log** (Step 6) so the user reviews the rationale before approving.
6. **Work Mode:** if Work Mode is active (see the agents conventions), refuse — "Blocked — Work Mode active. Say `normal mode` to proceed."
7. **Bullets: max 2 rendered lines each.** Tighten the wording or split it. Check the rendered PDF and re-trim if any bullet wraps past 2 lines.
8. **No hyphenated compounds in the headline.** A hyphen that lands on a line break is fused by every text extractor: "Digital-Bank Director" extracts as "DigitalBank Director", a word no recruiter search will match. Applies to the headline and bold lead-ins; Step 7b catches the rest.
9. **No AI-generated-text tells.** Plain, human CV prose. No em dashes (`—`) in prose (the `COMPANY — Location` and headline separators are template structure and may stay). Avoid: delve, leverage (as filler), seamless, robust, spearhead, testament to, underscore, pivotal, in today's landscape, boasts, harness, elevate, unlock, tapestry.

## Inputs
- **Base:** `cv_master`.
- **JD (auto-detect the form):** pasted text · file path · URL. For LinkedIn job URLs use a browser MCP (e.g. Playwright `browser_navigate` + `browser_snapshot`); other URLs use WebFetch.
- **Positioning guardrails** (read for emphasis, do NOT copy verbatim): `positioning_docs`, and the `target_map` row for the company if one exists.

## Procedure

### 1. Parse & intake
Parse `<Company>` from the args. Detect the JD form and load it. If no JD is present, ask for it before proceeding.

### 2. Analyse the JD
Extract: role title, seniority, must-have requirements, hard keywords (skills/tools/domains), industry, geography, comp/level signals. Map the company to a `target_map` row if one exists. Check every `hard_constraints` item (e.g. does the employing entity keep the user's work permit valid?) and flag any that break.

### 2b. Classify the CHANNEL (decides what the CV optimises for)

The same CV faces three different filters. Decide which one applies, state it in the change-log, and record it in `job_tracker`.

| Channel | Route | What actually filters | Optimise for | Render |
|---|---|---|---|---|
| **A — Portal / Easy Apply** (Workday, Greenhouse, Taleo, LinkedIn Easy Apply) | no named human | knockout questions, then match-score ranking, then a 7-second skim | parse safety + keyword coverage | `--header=first-page`, contact block in the body |
| **B — Agency recruiter** | named consultant; the CV is parsed into their database and **re-searched for months against other mandates** | the consultant's keyword search, now and later | **findability across future mandates** — do NOT strip sectors, domains or scale markers a recruiter may search on later, even when not in this JD | `--header=first-page` |
| **C — Retained search / founder direct** | one human reads the whole thing | narrative, altitude, proof | story and evidence; keyword work is wasted | default (repeating header) |

⚑ **Channel A requires a named recipient before the PDF renders.** Senior processes that reach a human almost always arrive through a named person; cold portal applications rarely get replies. If there is no name, say so and ask for an explicit *"lottery ticket, accepted"* before rendering. This is a stop, not a warning.

### 3. Worth-it gate — dissent + 0–10 score (run BEFORE any tailoring)
Decide whether the role is worth applying to *before* spending a tailoring pass.

**Rubric (0–10 composite):**
- **Hard constraints — GATE:** a role that breaks any `hard_constraints` item **caps the score at ~4**, unless the user explicitly overrides.
- **Geography — GATE:** outside `target_region` caps low unless the user marks it exceptional.
- **Target fit** (`target_map` row vs off-target) — high weight.
- **Seniority / scope match** — high weight.
- **Comp vs `comp_floor`** — medium.
- **Company quality / stage / brand** — medium.
- **Realistic win-probability** (the user's profile vs the JD's must-haves) — medium.

**Output, one block up top:**
- **Score /10** + **verdict: Apply (≥7) · Borderline (5–6) · Skip (<5)**
- **Dissent (mandatory):** one paragraph — the single strongest reason *not* to apply. Always write it, even for a strong role.
- **Fit line:** target row · constraints OK Y/N · seniority + geography match.

**Hard-stop:** if **score < 5, STOP** — present the score + dissent and ask "proceed anyway?". Do not tailor, write the `.md`, or render anything until the user says proceed. At 5+, present the verdict + dissent and continue. Tailoring a CV is never an endorsement — the dissent stands regardless of score.

### 4. Select & tailor (from CV_Master only)
- **Summary:** pick the closest summary variant in CV_Master and lightly tune it to the JD's language.
- **Competencies:** select the subset that matches the JD's keywords.
- **Experience:** reorder, re-emphasise and rewrite bullets into the JD's own words; lead with the most JD-relevant sourced achievements; drop the least relevant to hit 2 pages.
- **Non-full-time roles (board seats, advisory, side ventures):** calibrate prominence by JD — lead with them when the role wants governance or domain weight; keep them compact for a pure operating role (several recent part-time roles can read as divided attention).
- **Through-line:** when the JD is domain-specific (e.g. payments), cluster the relevant roles so a screener reads one coherent specialist, not a generalist who touched the domain. Supporting details that never shipped stay labelled as such (MVP, pilot).
- **Board & Advisory block:** when space is tight or governance matters, consolidate board/advisory roles into one compact block.
- **Qualitative where the number is weak:** if CV_Master marks a metric as unverified or internal-only, keep the claim qualitative.
- **Contact block:** match the location shown to `target_region` where honest.

### 5. Write the `.md`
Save to `<career_dir>/Job_Interviews/<Company>/CV_<Company>.md` (create the folder if needed).

### 5b. Keyword-coverage diff (channels A and B only — skip for C)

Employers filter far more through **search and ranking** than through auto-rejection: 88% of employers say their ATS screens out qualified candidates whose CV does not match the JD's exact criteria (Harvard Business School / Accenture, *Hidden Workers*, 2021). The fix is surfacing, never inventing.

Extract the JD's hard terms. Diff them against the finished CV text. Report one table, three buckets:

| Bucket | Meaning | Action |
|---|---|---|
| **Covered** | the term, or an unambiguous equivalent, appears in the CV | nothing |
| **Missing but true** | CV_Master supports it; the tailored CV just does not say it | propose the exact line to add or reword, one per row; **the user approves each** |
| **Missing, no record** | no support in CV_Master | ask the user once whether any of it is true; use the answer (Hard rule 1a) and add it to CV_Master; whatever they don't claim goes in the gaps list |

Hard rule 1 governs this step: fit real experience to the JD's words; don't stuff terms the user can't talk to.

### 6. Report the change-log — THEN STOP
Output, in chat:
- the **fit read** (Step 3),
- a **change-log table**: what was reordered / re-emphasised / rewritten / cut, each mapped to the JD requirement that drove it,
- **flagged gaps**: JD asks X → user has not claimed it → closest is Y (or "none"),
- **stretch list**: each oversold or user-sourced claim and the interview question it invites, one line each (doubles as interview prep),
- the **channel** (Step 2b) and, for A and B, the keyword-coverage table with the "missing but true" rows presented for approval one at a time.
Then **stop and wait for the user to approve or edit the `.md`.** Do not render the PDF yet.

### 7. On approval — render the PDF
- Copy this skill's `template.html` → `<career_dir>/Job_Interviews/<Company>/CV_<Company>.html`.
- Replace only the region between `<!-- CONTENT-START -->` and `<!-- CONTENT-END -->` with the approved content, using the template's CSS classes (`.headline`, `.section`, `.role`, `.role-head .co/.dates`, `.role-title`, `.role-desc`, `ul/li`, `.role-oneline`, `.edu-row`). Do not touch the `<style>` block. The repeating name/contact header and A4 margins come from the renderer (`cdp_pdf.py`), not the HTML.
- Render, **channel-aware**:
  - **Channel C:** `bash <skill_dir>/render.sh "<...>.html" "<cv_pdf_dir>/<...>.pdf"` — repeating name/contact header.
  - **Channels A and B:** add the contact block to the top of the HTML body (centred div: name 14pt bold, then location + phone, then email + LinkedIn), then render with `--header=first-page`:
    `bash <skill_dir>/render.sh --header=first-page "<...>.html" "<cv_pdf_dir>/<...>.pdf"`
    This stops the contact block repeating into the text layer of every page, where it breaks section detection.
- **Verify the PDF is ≤ 2 pages** (render.sh warns if not). If it overflows, diagnose before cutting (below).

**Renderer requirements:** Google Chrome or Chromium (path from `CHROME_PATH`; defaults to the macOS app location), Python 3 (stdlib only), and optionally poppler (`pdfinfo`, `pdftotext`) for the page-count and parse checks.

### 7b. Parse check — the render is not done until the text layer is read
`render.sh` runs `parse_check.py` automatically and prints a PASS/WARN/FAIL block: text layer present, section headings in order, no hyphen-break corruption, each role header carrying its dates, contact block appearing once, 2-page cap.

**Any FAIL is fixed before the CV goes anywhere.** A WARN on the repeating contact block is expected on channel C; on A or B it means the wrong render flag was used. A render is not a readable CV until it has been read back the way a machine reads it.

### 8. Short LinkedIn message
Produce a short outbound LinkedIn message via **`/brain:writer`**, calibrated to the recipient (recruiter = concise/professional; hiring manager = precise/no fluff). Save to `<career_dir>/Job_Interviews/<Company>/linkedin_message.md`. Claude drafts; the user sends.

### 9. Log
- The personal area's `CHANGELOG.md` — one entry (company, JD source, key tailoring calls, constraint verdict, files produced).
- Update `job_tracker` if this is a new application.

## Two-page overflow — diagnose before cutting

**The tell: you cut two lines and the page count does not move.** That is a trapped block, not excess content. `.role { page-break-inside: avoid }` holds a long role together, so a block that no longer fits jumps whole to the next page and leaves a dead gap behind it.

1. Count the lines per page: `pdftotext -f N -l N file.pdf - | sed '/^$/d' | wc -l`. A page well short of its neighbour is the gap.
2. Set `style="page-break-inside:auto"` **inline on the offending role div only**. Never edit the template `<style>` block.
3. Re-render, then cut on merit if it is still over.

**Restore anything cut while chasing the wrong problem.**

## Files
- `template.html` — dedicated 2-page layout (body only). Do not alter the `<style>` block.
- `render.sh` — HTML→PDF renderer (A4, page-count check, then the parse check). Optional `--header=repeat|first-page` first argument; `repeat` is the default.
- `cdp_pdf.py` — the Chrome DevTools Protocol renderer behind it (Chrome's CLI `--print-to-pdf` ignores CSS `@page` size and defaults to US Letter). Reads the contact header from `CV_*` env vars or `--contact=<file.json>`.
- `parse_check.py` — Step 7b. Run standalone with `python3 <skill_dir>/parse_check.py <file.pdf> [--expect-repeating-header] [--allow-camel=Word1,Word2]`.
- `templates/CV_Master.md` — empty fact-base template (headings only).
