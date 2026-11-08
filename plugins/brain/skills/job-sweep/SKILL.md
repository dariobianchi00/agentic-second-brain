---
name: job-sweep
description: People-first role sweep across LinkedIn Jobs and target companies' careers pages. Finds new senior roles in the user's configured region and hands back a named person per role (poster, first-degree connection, known contact) with talking points, opening every run with applications already ready but unsent. Use on "/brain:job-sweep", "run the sweep", or a weekly job-search check.
---

# /brain:job-sweep — LinkedIn + careers-page role sweep (people-first)

Personal-scope skill (career agent, if you run one). Finds new leadership roles and hands the user **a named person per role**, not a list of postings.

## Why it is shaped this way
- Senior roles are filled mostly through people: networking accounts for roughly 46–68% of senior hires vs 3–18% from online postings across executive surveys (HR Magazine/PCS, BPI, ExecuNet; data mostly 10+ years old). Cold portal applications at senior level rarely get a reply; processes that reach a human usually come through a named person.
- **Discovery is rarely the bottleneck; sending is.** Ready application packs tend to sit unsent for weeks. So every sweep opens with what is already ready and unsent.

## Configuration

All search scope lives in the companies file (copy `templates/companies.md` to `<vault>/<personal area>/Career/Job_Sweeps/companies.md` on first run, or wherever `CLAUDE.md` sets `job_sweep_companies`). Its **Config** block holds:

| Key | Meaning |
|---|---|
| `region` | Country/region used as the LinkedIn `location=` value and the geography screen |
| `employing_entity_rule` | e.g. "must be employed by a local entity" (work-permit or tax reasons); roles failing it are out |
| `titles` | Title groups to search |
| `sectors` | Target sectors (optionally mapped to `target_map` rows) |
| `window_days` | Posting age: 7 on a weekly run, 30 on the first |
| `attended_until` | Date until which every run must be attended |

Other inputs (all optional, configured in `CLAUDE.md`): `target_map` (target segments), `job_tracker` (Active / Pipeline / Archive, for dedupe), a contacts database or `Network/` files (contacts by company), and previous sweep files in the sweeps folder.

## Hard rules
1. **Never apply, never send, never connect.** Output is a file and a chat summary. The user sends.
2. **Never fabricate.** Every role line links to the posting. Every person's title/employer comes from **their own** LinkedIn profile (top card or experience), never from a sidebar, "people also viewed", a company post or a conference listing.
3. **Run attended** until `attended_until` (suggest the first month). No unattended run before the user approves it. Reason: an unattended script on the user's main LinkedIn account risks restriction, and profile visits show in "who viewed your profile".
4. **Minimise profile visits.** Read people from the company "People" tab and search results first; open an individual profile only for names that make the final list.
5. **Conflict flag on every name.** If the user is searching confidentially, flag anyone connected to their current employer (mutuals there, ex-colleagues, customers). Never present a name as cleared; the user clears it.
6. **Work Mode:** refuse. "Blocked — Work Mode active. Say `normal mode` to proceed."
7. **Outreach = talking points only** (hook + source, question, ask). No message drafts unless the user asks; then route through `/brain:writer`.

## Procedure

### 0. Pre-flight
- `date`. Check Work Mode. Browser: a browser-automation MCP (e.g. Playwright), logged in to LinkedIn by the user. On a login wall, stop and ask the user to sign in; never enter credentials. If the browser profile is in use by another session, ask before stopping it.

### 1. Ready and unsent — always first
From `job_tracker` Pipeline, list every row marked not sent or with an unsent outbound message. For each: role, age in days, what blocks it (no named person / conflict check owed / user's send), and the named person if one exists in the contacts or tracker. Never skip this section: if there are none, say "none".

### 2. Search
**LinkedIn Jobs.** One query per title group in `titles`, each built as a URL:
`https://www.linkedin.com/jobs/search-results/?keywords=<q>&location=<region>&f_TPR=<r604800|r2592000>`
(`r604800` = 7 days, `r2592000` = 30 days.)
- **Verify on the first page of each run** that the results header shows `region`. LinkedIn's newer AI job search (`/jobs/search-results/`) drops the seniority filter (`f_E`), so **screen titles by hand**. Results mix in inexact matches and older postings, and a company name in the query does not restrict results to that company. LinkedIn changes these URLs often; re-check the format when results look wrong.
- Read result cards from the `main` element's innerText; click a card by its title text (`force: true`) and read the detail panel.

**Tier 1 careers pages.** Visit each URL in the companies file's Tier 1 **in the browser, not a web fetch or a fetch-only subagent** (most portals need JavaScript; a plain fetch reports them as empty). Scan for the title groups. Call a site unreadable only after the browser fails, and record which: listings read / no public listing / site down. For the last two, fall back to LinkedIn. Tier 2 companies are covered by the LinkedIn search plus a company-jobs check only when the company appears in results.

**Browser discipline.** One browser script at a time: parallel calls share the page and corrupt each other. Close the browser at the end of the sweep so other sessions are not locked out.

### 3. Dedupe
Drop a role if it is: already in the tracker (any section, incl. killed rows), shown in a previous sweep file, held by a recruiter already working for the user, or at a company where a contact conversation about a role is already live. Note dropped counts per reason.

### 4. Light screen — three checks
For each remaining role: **(a) employing entity meets `employing_entity_rule`?** (Y / N / unclear — for multinationals check the posting's entity) **(b) seniority at or above the configured floor?** **(c) target row?** (a `sectors` / `target_map` match, or none). Pass = Y or unclear on (a), Y on (b), and a row on (c). One fit line per role. **No 0–10 score here** — the full `/brain:cv-plus` gate runs only on roles the user picks.

### 5. People — for each survivor
- **Job poster / hiring team** if LinkedIn shows one.
- **The user's 1st-degree connections currently at the company** (company page → People, filter 1st).
- **Known contacts at the company** from the contacts database or `Network/` files, with status and last contact.
- For each name: current title from their own profile, the conflict flag (rule 5), and 2–3 talking points (hook + source, question, ask).
- Roles with no reachable person go to a separate "no route yet" list.

### 6. Output
Write `<sweeps folder>/sweep_YYYY-MM-DD.md`:
1. **Ready and unsent** (step 1)
2. **New roles with a person** (3–8 target; ranked target row → seniority → strength of route)
3. **No route yet**
4. **Run log:** queries run, filters verified Y/N, counts found / deduped / screened out / kept, pages that failed
Then in chat: a short table of section 2 and the ask — "which do you want through `/brain:cv-plus`?"

### 7. Log and measure
- The personal area's `CHANGELOG.md`: one `[sweep]` entry (counts, file path).
- Roles the user picks → `job_tracker` Pipeline row (status "Sweep pick YYYY-MM-DD") and `/brain:cv-plus`.
- New people the user wants kept → contacts database / `Network/` via the normal approval flow.
- **Success measure:** conversations started from sweep results. Record per run in the sweep file. **Two runs in a row with zero sends → propose dropping to monthly.**
- **Promotion rule:** a Tier 2 company that posts a matching role in two runs moves to Tier 1.

## Cadence
- On demand: `/brain:job-sweep` (or "run the sweep").
- Weekly, **attended** until `attended_until`; after that, the user decides whether it may run unattended via `/agents:schedule` (the scheduler is macOS-only, launchd).

## Files
- `SKILL.md` — this file.
- `templates/companies.md` — config block, target companies, tiers, exclusions, careers URLs (template with fictional rows).
