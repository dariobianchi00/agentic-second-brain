---
name: tech-news
description: Regional tech news digest for a configured region — fetches RSS feeds and Google News, resolves broken article URLs, filters and categorises stories, writes a dated digest to the vault, and displays the top stories inline. Fires on "/brain:tech-news", "tech news", "what's new in <region> tech", or from an agent's kickoff.
---

# /brain:tech-news

Regional tech news digest — fetches RSS feeds, resolves broken URLs, categorizes stories, writes a digest, displays top stories inline. The region is a config value (Malaysia / Southeast Asia is just the shipped example).

## User-invocable

## Description

Two-stage pipeline:
- **Stage 1 (script, optional schedule):** `scripts/fetch.py` fetches the configured RSS feeds + Google News queries, flags suspect URLs, attempts auto-resolution, writes `_staged_raw.md`. Run it on demand, or daily (e.g. 07:00) via a macOS LaunchAgent — scheduling is macOS-only (launchd); on Linux use cron.
- **Stage 2 (Claude):** this skill processes the staging file — filters, verifies remaining suspect URLs via web search, categorizes, writes digest files, displays top stories inline.

Can be triggered manually (`/brain:tech-news`) or at an agent's first session of the day via its `kickoff` overlay.

## Setup (once)

1. `pip install feedparser requests python-dateutil` (or a venv of your choice).
2. Copy `config.example.json` from this skill to `<vault>/Knowledge/Tech_News/config.json` and edit:
   - `region_name` / `region_short` / `wider_region` — e.g. "Malaysia" / "MY" / "Southeast Asia"
   - `google_news` — `hl` / `gl` / `ceid` locale for Google News
   - `rss_feeds` — name → URL; use site-scoped Google News RSS (`q=site:<domain>+when:2d`) for publishers whose native feed is blocked or gone
   - `google_news_queries` — 4–6 region queries
   - `fintech_focus` / `fintech_key_players` — the always-include fintech beat (delete if you don't want one)
   - `output_dir` — defaults to `Knowledge/Tech_News`
3. Optional schedule (macOS): a LaunchAgent that runs `python3 <skill>/scripts/fetch.py --vault <vault>` daily.

## Allowed Tools

```yaml
- Read(*)
- Write(*)
- Edit(*)
- Bash(python3, date, stat)
- Glob(Knowledge/Tech_News/**)
- Grep(Knowledge/Tech_News/**)
- WebSearch(*)
- WebFetch(*)
```

## Steps

### 0. Load config

Read `Knowledge/Tech_News/config.json` (or the `output_dir` it names). Missing → stop and point the user to Setup; never assume a region.

### 1. Fetch (if needed)

Check if `<output_dir>/_staged_raw.md` exists and was generated today.
- If **missing or stale**: run `python3 "<this-skill>/scripts/fetch.py" --vault "<vault>"` via Bash
- If **fresh** (generated today): skip to Step 2

### 2. Read staging file

Read `<output_dir>/_staged_raw.md`. Note total articles, suspect count, resolved count.

### 3. Fix remaining suspect URLs

For each article still flagged `⚠️ URL_SUSPECT` that you plan to include in the digest:
1. **WebSearch** for the exact headline + source name
2. Replace the bad URL with the correct one
3. If no correct URL found: use a descriptive Google search URL as fallback, or omit the article if low-value

This is the key quality step — never publish suspect URLs.

### 4. Filter & categorize

Discard articles with no relevance to `region_name` / `wider_region` (other countries' purely domestic news). Prioritize:
- **Region-specific** — always include
- **Wider-region** stories with implications for the region
- **Global tech** with clear impact on the region's ecosystem (semiconductor supply chain, AI regulation, hyperscaler moves)
- **Fintech (region / wider region)** — always include if configured: the `fintech_focus` topics and `fintech_key_players` from config.

### 5. Write digest files (MANDATORY — do this before display)

Write to BOTH:
- `<output_dir>/latest_digest.md`
- `<output_dir>/archive/YYYY-MM-DD.md`

Format:

```markdown
# <region_name> Tech News — YYYY-MM-DD

## Top Stories
1. **[Headline]** — 2-3 line summary ([Source](URL))
2. ...
3. ...

## <region_name>
- **[Headline]** — summary ([Source](URL))

## <wider_region>
- **[Headline]** — summary ([Source](URL))

## Fintech <region_short>/<wider_region>
- **[Headline]** — summary ([Source](URL))

## AI & Technology
- **[Headline]** — summary ([Source](URL))

## Other
- One-liner summaries

> Sources: <the feed names from config>
```

Rules:
- Every article MUST include a clickable `[Source](URL)` link
- Empty categories omitted
- Top Stories: exactly 3 items
- Include coverage note if feed issues exist
- Summarise what the article says — no editorialising, no claims the source doesn't make

### 6. Display key news inline

Show the top 3 stories inline in the conversation, each with the source URL as a clickable link, plus a one-line note on why each matters to the user (their role, industry, region, AI). Take the role/industry from `CLAUDE.md`. The MD digest files written in Step 5 are the source of truth — display is the convenience layer.

## Kickoff integration (optional)

During an agent's `kickoff` (first session of the day), the tech news step should:
1. Check if `_staged_raw.md` exists and was generated today
2. If yes: run Steps 2-6 above (or delegate Steps 2-5 to a background agent, but VERIFY files exist before displaying)
3. If stale/missing: skip with note "Tech news staging file not found or stale — run `/brain:tech-news` to refresh"

## Infrastructure

- **Fetch script:** `scripts/fetch.py` (in this skill)
- **Config:** `Knowledge/Tech_News/config.json` (from `config.example.json`)
- **Schedule (optional, macOS):** a LaunchAgent running the fetch script daily
- **Staging file:** `<output_dir>/_staged_raw.md`
- **Digest:** `<output_dir>/latest_digest.md`
- **Archive:** `<output_dir>/archive/YYYY-MM-DD.md`

## Feeds (shipped example — Malaysia / Southeast Asia)

| Source | URL |
|--------|-----|
| Digital News Asia | digitalnewsasia.com/rss.xml |
| e27 | Google News `site:e27.co` (native feed Cloudflare-blocked) |
| Tech in Asia | techinasia.com/feed |
| KrASIA | Google News `site:kr-asia.com` (/feed serves HTML) |
| The Edge | Google News `site:theedgemalaysia.com` + tech intitle filter (/rss removed) |
| Malay Mail Tech | Google News `site:malaymail.com/news/tech-gadgets` (native feed Cloudflare-blocked) |
| Google News | 5 queries: tech startup, AI, digital economy, fintech, regional digital banking |
| Fintech News Malaysia | fintechnews.my/feed/ |

Replace these with your region's publishers in `config.json`.

## Known issues

- **Some RSS feeds return wrong `<link>` elements** (Tech in Asia is a known case). The fetch script (1) detects mismatches via a keyword-overlap heuristic between URL slug and headline, (2) attempts auto-resolution by constructing title-slug URLs and checking with HEAD requests (Tech in Asia only), (3) flags remaining failures as `⚠️ URL_SUSPECT` for Claude to fix via web search in Step 3.
- **Google News RSS** uses encoded `rss/articles/<id>` links that no longer redirect. `_decode_google_news()` exchanges the page's signature/timestamp at Google's `batchexecute` endpoint for the publisher URL (6 parallel workers, ~15s per run). If Google changes the format, links fall back to `URL_SUSPECT` and Step 3 fixes them via WebSearch.
- **Native feeds disappear or get bot-blocked** (Cloudflare 403, `/rss` 404, `/feed` serving HTML). Switch that source to a site-scoped Google News query in config.
