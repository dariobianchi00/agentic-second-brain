---
name: events
description: Regional tech-event discovery, run by hand. Searches configured sources, filters and ranks events by topic-fit and speaking opportunity, writes a digest to the vault, tracks state so events are not re-surfaced forever, and optionally emails a scannable version. Fires on "/brain:events", "scan events", "run events digest", "tune events".
---

# /brain:events

Tech-event discovery for the user's region — searches the configured sources, filters and ranks events by topic-fit and speaking opportunity, writes a digest, and (optionally) emails a scannable version.

## User-invocable

## Description

Routine that surfaces 5–15 ranked events worth the user's time, replacing purely reactive event discovery (whatever lands in the inbox) with a deliberate scan. Designed to surface speaking opportunities 2–4 months ahead.

Triggered manually (`/brain:events`, "scan events", "run events digest"). **Run cadence: by hand.** A cloud routine can't sustain this unless the vault is in a git repo the cloud agent can check out and push back to — it needs to write the digest file and maintain `_state.json`. Only the email half is cloud-capable. If you want laptop-off automation, first put the vault (or at least the events folder) in such a repo, then record the routine ID under Infrastructure.

## Configuration (set once in the vault's CLAUDE.md)

Add an `## Events` block to `CLAUDE.md` (or the career/network agent's context file). The routine reads it every run and never hard-codes a city, month or address.

```markdown
## Events
- Folder: <personal area>/Events_Digest            # digests + _state.json live here
- Home city: Kuala Lumpur (example)                 # always included
- Day-trip cities: Singapore (example)              # included only if no overnight stay, or a confirmed speaking slot
- Flagship-only cities: Bangkok (example)           # included only for a confirmed speaking slot or a flagship event with topic-fit ≥ 4
- Location aliases to strip in dedup: kl, kuala lumpur, singapore, sg, malaysia, my (example)
- Timezone: Asia/Kuala_Lumpur (example)
- Themes (topic-fit 5): <your signature talk themes>
- Themes (topic-fit 4): <adjacent strong themes, e.g. fintech, product leadership, founder/VC>
- Themes (topic-fit 3): <general tech leadership, regional business, digital economy>
- Themes (topic-fit 2): <adjacent, e.g. martech, HR tech>
- Sources: see the source list below — replace the examples with your region's calendars
- Email to (optional): <address>   via <Gmail MCP server name>
- Network DB (optional): Network/<contacts>.db     # SQLite, table `contacts`
```

If the block is missing, ask for the home city and themes (one question at a time, with a recommendation), then offer to write the block.

## Allowed Tools

```yaml
- Read(*)
- Write(*)
- Edit(*)
- Glob(*)
- Bash(date, python3, md5, sqlite3)
- WebSearch(*)
- WebFetch(*)
- <Gmail MCP send tool>   # optional, for Step 10
```

## Steps

Execute every step completely. Do not summarise or skip steps.

### STEP 1 — Setup

Get today's date. Derive the digest filename: `<events folder>/<YYYY-MM-DD>-events.md`. If a file with that name already exists, append a numeric suffix (e.g. `-2`).

Define the lookahead window: today + 4 days (freshness floor) through today + 112 days (16-week / 4-month ceiling). Use event start date for all freshness checks. The extended window is intentional — speaking applications typically require 2–4 months lead time.

Read the state file at `<events folder>/_state.json`. If the file is missing or unreadable, archive it as `_state.corrupted-<YYYY-MM-DD>.json`, start with empty state `{}`, and add a header warning to the digest: "⚠️ State file reset this run — dedup history lost, expect repeat surfacing for 1-2 weeks."

**Record the user's actions from the last digest.** Ask in one line: *"Any events from the <last digest date> digest you RSVP'd to, applied to speak at, or want dropped?"* For each one named, set `user_action` in state to `rsvp`, `applied` or `dropped`. If the user skips or says none, carry on. Events with a `user_action` never resurface.

**Search months:** list the calendar months covered by the lookahead window (e.g. "November 2026", "December 2026", "January 2027", "February 2027") and the years it spans. Use these wherever a query below says `<MONTH YEAR>` or `<YEARS>` — never a hardcoded month or year.

### STEP 2 — Source scouring

Search the configured sources for tech events in the home city and day-trip cities. For each source, extract: event name, date, start/end time, location, format, organiser, registration/contact link.

**How to search a calendar source:** fetch the organisation's events/calendar page directly (WebFetch) and read the listings — `site:` searches miss most calendar entries (in practice most source groups come back empty that way). Only if the page can't be fetched or has no listings, fall back to a web search (`"<organisation>" events <MONTH YEAR>`). Record the working URL in the digest footer so the next run starts from it.

**Source list (example shape — replace with your region's):**

*Structured sources*
1. Lu.ma — home-city page (tech / AI / product / fintech)
2. Lu.ma — day-trip-city page (same topics)
3. Eventbrite — home-city technology events
4. Regional tech media events pages (e.g. Tech in Asia, e27 for Southeast Asia)

*Association / chamber calendars*
5. Local fintech / industry associations
6. Bilateral chambers of commerce (your nationality's chamber, EU chamber, AmCham)

*Ecosystem calendars*
7. Accelerators and VC programmes active in the region (e.g. Endeavor, Antler)
8. Corporate summits — sovereign funds, large banks, regulators, the national digital agency

*Open web (usually the source that works best — run every query, one per search month where marked)*
9. Queries:
   - `<country> tech events <MONTH YEAR>` (each search month)
   - `<home city> AI summit <YEARS>`
   - `<day-trip city> fintech conference <MONTH YEAR>` (each search month)
   - `<home city> product conference <YEARS>`
   - `<country> invite-only dinner tech founders <YEARS>`
   - `<flagship-only city> AI fintech summit conference <YEARS>`
   - the regional editions of flagship events in your field (e.g. `Money20/20 Asia <YEARS>`)

Log any source that fails (rate-limited, 404, no results) in a `failed_sources` list. If more than half the sources fail, flag in the digest header: "⚠️ >50% of sources unavailable this run — digest may be incomplete."

### STEP 3 — Filter

For each event found, apply ALL of the following filters. Fail any filter = exclude the event.

**Geography filter:**
- Home city (and its metro area): always include
- Day-trip cities: include ONLY if it is a day-trip (no overnight stay required), OR if the user has a confirmed speaking slot
- Flagship-only cities: include ONLY if the user has a confirmed speaking slot, OR if it is a flagship regional event with topic-fit ≥ 4
- Virtual/hybrid: include only if the topic-fit score is 4+
- Any other location: exclude

**Topic-fit filter (must score ≥ 2 to proceed):**
Score 1–5 based on alignment with the configured themes:
- 5: the user's signature themes
- 4: the topic-fit-4 themes
- 3: the topic-fit-3 themes
- 2: the adjacent themes
- 1: No clear tech/product angle
Exclude score 1.

**Hard excludes (any of these = auto-exclude regardless of other scores):**
- Marketing seminars / growth hacking / SEO events
- Vendor sales pitches / product demos disguised as conferences
- Junior-level meetups ("intro to coding", "learn Python", bootcamp demos)
- Generic business networking (no specific industry or topic)
- MLM / affiliate marketing events
- Religious or political events

### STEP 4 — Deduplicate

For each event that passes filters:
1. Compute `event_hash = md5(normalize(name) + "|" + date)`
2. Normalize rules (apply in order): lowercase → strip punctuation → strip 4-digit year tokens (e.g. 2026, 2027) → strip the configured location aliases → collapse whitespace
3. If the same hash appears from multiple sources, keep the most complete record and note the dedup count.

### STEP 5 — State check & section assignment

For each deduplicated event, check the state file. Runs are irregular, so sections are relative to the **last run**, not to a week:

- **NEW SINCE LAST RUN:** event_hash NOT in state
- **STILL OPEN:** event_hash in state, user_action = null, surface_count < 4

Do not include in digest:
- user_action set (rsvp / applied / dropped) — the user has already decided
- surface_count ≥ 4 AND user_action = null (auto-suppress)

Add each included event to state (or update if existing):
- new event: `first_surfaced = today, last_surfaced = today, surface_count = 1`
- returning event: `last_surfaced = today, surface_count += 1`

Track count of auto-suppressed events for the footer.

### STEP 6 — Network cross-reference (optional)

Only if a network DB is configured. For each event where attendee or speaker names are scrapable from verifiable sources (organiser website speaker list, published event attendee lists, official programme PDF):

1. Read the configured SQLite database
2. Query the active contacts, e.g. `SELECT first_name, last_name, priority, status, last_contact_date, next_action FROM contacts WHERE status = 'Live'` (adapt to your schema)
3. Fuzzy-match each scraped name against (first_name + " " + last_name) — use token overlap, not exact match
4. For matches: include in the digest row with a source link per name (hallucination guard — only names sourced from verifiable pages)
5. Cap display at top 5 matches by priority; summarise the rest as "+N others"
6. If the DB is unavailable or not configured: skip cross-ref, add footer note "Network cross-reference unavailable this run"

### STEP 7 — Score & rank

For each event, compute composite score:
- Topic-fit (1–5) × 0.40
- Format priority × 0.30: invite-only-dinner=5, multi-day-with-speaking=4, half-day-conference=3, cocktail-reception=2, virtual=1
- Speaking opportunity × 0.20: yes=3, maybe=2, no=1
- Date proximity × 0.10: next 4 weeks=2, next 4–8 weeks=1

Network adjustment: if ≥3 active contacts are attending/speaking, add +0.3 to composite score regardless of other factors.

Sort descending by composite score. Tie-break: date proximity → format priority → alphabetical name.

Target 5–15 events total. If more than 15 pass all filters, take the top 15 by score.

### STEP 8 — Recommended action logic

Assign one recommended action per event:

- **Apply to speak** — speaking_opportunity = yes AND topic-fit ≥ 3
- **RSVP** — format = invite-only-dinner AND topic-fit ≥ 4
- **RSVP** — format = multi-day-with-speaking AND topic-fit ≥ 4 AND speaking_opportunity ≠ no
- **Watch** — topic-fit ≥ 3, none of the above
- **Skip** — topic-fit < 3 OR format = cocktail-reception (unless ≥3 active network contacts attending)

If ALL events score Skip: include them anyway with a note "⚠️ Low-quality run — consider tuning sources or filters."

### STEP 9 — Write digest

Write the digest file at `<events folder>/<YYYY-MM-DD>-events.md`:

```
---
date: <YYYY-MM-DD>
run: <run number from _meta.total_runs + 1>
events_found: <total before filter>
events_included: <count in this digest>
events_suppressed: <auto-suppressed this run>
sources_failed: <comma-separated list or "none">
---

# Events Digest — <YYYY-MM-DD>

> Lookahead: <start date> → <end date> | Sources checked: <N> | Dedup removed: <N> | Auto-suppressed: <N>

## NEW SINCE LAST RUN

### 1. [Event Name]
- **Date:** YYYY-MM-DD | **Time:** HH:MM–HH:MM | **Location:** <city> / Virtual
- **Format:** invite-only-dinner / multi-day-conference / half-day-workshop / cocktail / virtual
- **Topic-fit:** X/5 | **Theme:** <which configured theme>
- **Speaking opportunity:** Yes / No / Maybe — [note if call-for-speakers open]
- **Likely attendees:** [1-line summary if scrapable]
- **Network contacts:** ⚡ N active contacts attending: [Name (priority, status, last touch)] | [source link]
- **Link:** [direct registration or contact URL]
- **Recommended action:** Apply to speak / RSVP / Watch / Skip
- **Rationale:** [one line]

[repeat for each event]

## STILL OPEN

[same format, add: **Previously surfaced:** N times, first seen YYYY-MM-DD]

---
*Digest generated <YYYY-MM-DD HH:MM local time> | State file: _state.json | Dedup count: N | Auto-suppressed this run: N | Actions recorded: N*
*Working source URLs: <list>*
```

### STEP 10 — Email digest (optional)

Only if an email address and a Gmail MCP server are configured. Send a **clean, scannable** email every run, regardless of event scores. **Readability first — match the `/brain:tech-news` display standard** (per-item blocks, generous whitespace, the key facts bold and up front). The email is the SCANNABLE convenience layer, **NOT a raw dump of the digest markdown** — the full field-level detail lives in the digest `.md` file (source of truth). Do not paste the whole digest into the body.

- **Subject:** `📅 Events Digest — <YYYY-MM-DD> (<N> events, <N> actionable)`
- **Send as HTML** (use the Gmail tool's HTML body if available) so bolding and spacing render. If HTML is not supported, send well-structured text with blank lines between events and the event name/action visually prominent — never a dense field-by-field bullet dump.
- **Body structure:**
  1. **One-line summary** at the very top: "This run: <N> events — <e.g. 2× Apply to speak, 1× Watch, 1× Skip>."
  2. Heading **NEW SINCE LAST RUN**, then **one compact block per event** (3–5 scannable lines, blank line between blocks):
     - **Line 1 (bold):** ⚡ (only if topic-fit=5 AND speaking=yes) + **Event name** — then the recommended action in bold caps: **APPLY TO SPEAK** / **RSVP** / **WATCH** / **SKIP**
     - **Line 2 (light/grey):** Date · Time · Location · Format · Topic-fit X/5
     - **Line 3:** one-line rationale (why it matters to the user — role, themes, region, speaking)
     - **Line 4 (only if any):** ⚡ network contacts attending — Name (priority, status)
     - **Line 5:** a single **Register / details** hyperlink (not a bare URL — anchor text)
  3. Heading **STILL OPEN**, same per-event block, append "· surfaced N× since <date>".
- **Triage-in-seconds test:** the user should be able to scan the bold event names + actions and know what to do without reading the detail. If a block runs longer than ~5 lines, cut it — depth stays in the `.md`.

### STEP 11 — Update state file

Write back to `<events folder>/_state.json`:
- Update `_meta.last_run`, `_meta.total_runs += 1`, `_meta.total_events_surfaced`, `_meta.total_events_suppressed`
- For each event included in the digest: upsert the event record with updated `last_surfaced`, `surface_count`
- For each auto-suppressed event: keep existing record, do not update `last_surfaced`

State schema:
```json
{
  "_meta": {"schema_version": "1.0", "created": "YYYY-MM-DD", "last_run": "YYYY-MM-DD",
            "total_runs": 0, "total_events_surfaced": 0, "total_events_suppressed": 0},
  "<event_hash>": {
    "first_surfaced": "YYYY-MM-DD",
    "last_surfaced": "YYYY-MM-DD",
    "surface_count": 1,
    "user_action": null,
    "event_name_canonical": "<normalized name>",
    "event_date": "YYYY-MM-DD",
    "source": "<first source where found>"
  }
}
```

### DONE

Report back: "Events digest written: <events folder>/<filename> — <N> events, <N> new, <N> returning, <N> suppressed. Email: <sent / not configured>."

## Kickoff integration (optional)

If an agent's `kickoff` (see `/agents:*`) surfaces events at the first session of the week, the events step should:

1. Find the most recent digest file: `Glob("<events folder>/????-??-??-events.md")` → sort by name descending → take first
2. Check if it was generated within the last 7 days
3. **If fresh AND it's Monday:** surface top 3 events inline, prefixed *"From this week's events digest:"*
   - Format: **Event name** | Date | Location | Recommended action | One-line rationale
   - ⚡ events go first regardless of rank
4. **If fresh AND it's NOT Monday:** skip silently (digest is current and was already surfaced)
5. **If stale or missing:** note "Events digest stale or missing — run `/brain:events` to refresh"

Do NOT run the full search pipeline during kickoff unless explicitly asked. Kickoff only reads and surfaces.

## Infrastructure

- **Config:** the `## Events` block in `CLAUDE.md`
- **State file:** `<events folder>/_state.json`
- **Digest files:** `<events folder>/<YYYY-MM-DD>-events.md`
- **Scheduled agent:** none by default — cadence is manual (see Description). Do not assume a cron is running; if laptop-off automation is set up later, record the routine ID here.

## Tuning

Only when the user asks ("tune events") — no fixed cadence, no nudges:
1. Read `_state.json` — surface stats: events surfaced, suppressed, actioned, action distribution
2. Ask the user: which themes over/under-surfaced? Which sources had best yield?
3. Update the `## Events` config block (themes, sources, cities) per the user's direction

## Key decisions

- **Lookahead:** 16 weeks / 4 months — long enough to catch speaker application deadlines
- **Email:** full digest every run (not escalation-only), when configured
- **Self-tuning:** none — tuning only when the user asks
- **State:** N=4 auto-suppress rule — events surfaced 4× without action stop appearing
- **Network cross-ref:** mandatory when attendee data is scrapable and a DB is configured; hallucination guard via source links
